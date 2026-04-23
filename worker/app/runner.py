from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx

from .config import Settings
from .emailer import send_briefing_email
from .models import AnalyzeRequest, CallbackPayload
from .pdf import generate_pdf
from .store import JobStore

ANALYZER_TIMEOUT_SECONDS = 120


async def _send_callback(callback_url: str, callback_secret: str, payload: CallbackPayload) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            callback_url,
            headers={"x-internal-token": callback_secret},
            json=payload.model_dump(by_alias=True, exclude_none=True),
        )
        response.raise_for_status()


async def run_analysis_job(
    *,
    job_id: str,
    payload: AnalyzeRequest,
    settings: Settings,
    store: JobStore,
) -> None:
    await store.mark_running(job_id)
    await store.append_log(job_id, f">> {payload.ticker} 任务进入运行态")
    await store.append_log(job_id, ">> 启动 Python 风险引擎...")
    await store.append_log(job_id, f">> Skill 目录: {settings.python_skill_dir}")

    try:
        with tempfile.TemporaryDirectory(prefix=f"sentinel-{payload.ticker.lower()}-") as tmpdir:
            output_dir = Path(tmpdir)
            skill_dir = Path(settings.python_skill_dir).resolve()
            if not skill_dir.exists():
                raise FileNotFoundError(f"Python skill directory not found: {skill_dir}")

            command = [
                settings.python_executable,
                "analyze_stock.py",
                payload.ticker,
                "--output",
                "json",
                "--output-dir",
                str(output_dir),
                "--verbose",
            ]

            if payload.requested_mode == "basic":
                command.append("--fast")
            else:
                command.extend(["--deep", payload.deep_mode or "valuation"])

            env = os.environ.copy()
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(skill_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def consume_stderr() -> None:
                assert process.stderr is not None
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    message = line.decode("utf-8", errors="replace").strip()
                    if message:
                        await store.append_log(job_id, message)

            stderr_task = asyncio.create_task(consume_stderr())
            assert process.stdout is not None
            stdout_task = asyncio.create_task(process.stdout.read())

            try:
                await asyncio.wait_for(process.wait(), timeout=ANALYZER_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                await store.append_log(
                    job_id,
                    f"!! 分析超时（>{ANALYZER_TIMEOUT_SECONDS}s），正在终止 Python 进程...",
                )
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                for pending in (stdout_task, stderr_task):
                    pending.cancel()
                    try:
                        await pending
                    except (asyncio.CancelledError, Exception):
                        pass
                raise RuntimeError(
                    f"[WORKER_TIMEOUT] Python analyzer exceeded {ANALYZER_TIMEOUT_SECONDS}s and was killed"
                )

            stdout_bytes = await stdout_task
            await stderr_task

            if process.returncode != 0:
                raise RuntimeError(
                    f"Python analyzer exited with code {process.returncode}"
                )

            stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
            result_json = json.loads(stdout_text)
            await store.append_log(job_id, ">> JSON 结果解析完成")

            markdown_candidates = sorted(output_dir.glob("*综合报告*.md"))
            markdown_report = (
                markdown_candidates[-1].read_text(encoding="utf-8")
                if markdown_candidates
                else ""
            )

            pdf_path: Path | None = None
            if markdown_report:
                try:
                    pdf_path = output_dir / f"{payload.ticker}-Sentinel-Briefing.pdf"
                    await store.append_log(job_id, ">> 正在生成 PDF 附件...")
                    await generate_pdf(
                        markdown_report,
                        pdf_path,
                        title=f"{payload.ticker} Sentinel Intelligence Briefing",
                        chromium_executable=settings.playwright_chromium_executable or None,
                    )
                    await store.append_log(job_id, ">> PDF 生成完成")
                except Exception as pdf_exc:
                    pdf_path = None
                    await store.append_log(job_id, f"!! PDF 生成失败，已降级为仅邮件正文: {pdf_exc}")

            email_delivery_id = None
            try:
                if settings.resend_api_key:
                    await store.append_log(job_id, ">> 正在通过 Resend 发送邮件...")
                else:
                    await store.append_log(job_id, ">> 未配置 Resend，进入 Mock Email Mode（打印邮件内容到控制台）...")

                email_delivery_id = await send_briefing_email(
                    api_key=settings.resend_api_key,
                    from_email=settings.resend_from_email,
                    to_email=payload.email,
                    ticker=payload.ticker,
                    result=result_json,
                    pdf_path=pdf_path,
                )
                await store.append_log(job_id, ">> 邮件投递流程已完成")
            except Exception as mail_exc:
                await store.append_log(job_id, f"!! 邮件发送失败: {mail_exc}")

            await store.complete(job_id, result_json, markdown_report, email_delivery_id)

            try:
                await _send_callback(
                    payload.callback_url,
                    payload.callback_secret,
                    CallbackPayload(
                        historyId=payload.history_id,
                        jobId=job_id,
                        status="completed",
                        resultJson=result_json,
                        markdownReport=markdown_report,
                        emailDeliveryId=email_delivery_id,
                    ),
                )
            except Exception as callback_exc:
                await store.append_log(job_id, f"!! 完成回调失败: {callback_exc}")
    except Exception as exc:
        error_message = str(exc)
        await store.append_log(job_id, f"!! {error_message}")
        await store.fail(job_id, error_message)

        try:
            await _send_callback(
                payload.callback_url,
                payload.callback_secret,
                CallbackPayload(
                    historyId=payload.history_id,
                    jobId=job_id,
                    status="failed",
                    errorMessage=error_message,
                ),
            )
        except Exception:
            await store.append_log(job_id, "!! 结果回调失败，请检查 Next API 可达性")
