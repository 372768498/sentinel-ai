"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Cpu, Database, Lock, Mail, Radar, Search, ShieldAlert, Terminal } from "lucide-react";

type AnalyzeResponse = {
  historyId: string;
  jobId: string;
  eventsUrl: string;
  pollUrl: string;
  isPro: boolean;
  quota: {
    limit: number;
    used: number;
    unlimited?: boolean;
  };
};

type AnalyzeErrorResponse = {
  error?: string;
  upgradeRequired?: boolean;
  quotaExceeded?: boolean;
};

type FinalResult = {
  score_100?: number;
  rating?: string;
  recommendation?: string;
  supporting_points?: string[];
  caveats?: string[];
};

declare global {
  interface Window {
    LemonSqueezy?: {
      Url?: {
        Open?: (url: string) => void;
      };
    };
    createLemonSqueezy?: () => void;
  }
}

const tierMap: Record<string, string> = {
  BUY: "看多",
  STRONG_BUY: "看多",
  HOLD: "中性",
  SELL: "看空",
  STRONG_SELL: "看空"
};

const formatTier = (reco?: string | null) => {
  if (!reco) return null;
  return tierMap[reco.toUpperCase()] ?? reco;
};

const loadingFallback = [
  ">> 初始化任务调度器...",
  ">> 连接 SEC / FMP / yfinance 数据源...",
  ">> 拉取财务、估值、技术面与市场情绪...",
  ">> 计算 10 维量化评分...",
  ">> 生成 Markdown 报告与 PDF 摘要...",
  ">> 准备邮件投递..."
];

export default function SentinelPage() {
  const [ticker, setTicker] = useState("");
  const [email, setEmail] = useState("");
  const [mode, setMode] = useState<"basic" | "deep">("basic");
  const [deepMode, setDeepMode] = useState("valuation");
  const [status, setStatus] = useState<"idle" | "submitting" | "running" | "completed" | "failed">("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<FinalResult | null>(null);
  const [quota, setQuota] = useState<{ limit: number; used: number } | null>(null);
  const [isPro, setIsPro] = useState(false);
  const [checkoutPending, setCheckoutPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const fallbackTimerRef = useRef<number | null>(null);

  const modeLabel = useMemo(() => {
    if (mode === "basic") {
      return "基础版";
    }

    return `Pro 深度版 / ${deepMode}`;
  }, [deepMode, mode]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  useEffect(() => {
    const existingScript = document.querySelector<HTMLScriptElement>("script[data-lemon-squeezy='true']");
    if (existingScript) {
      window.createLemonSqueezy?.();
      return;
    }

    const script = document.createElement("script");
    script.src = "https://app.lemonsqueezy.com/js/lemon.js";
    script.async = true;
    script.dataset.lemonSqueezy = "true";
    script.onload = () => window.createLemonSqueezy?.();
    document.body.appendChild(script);

    return () => {
      script.onload = null;
    };
  }, []);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      if (fallbackTimerRef.current) {
        window.clearInterval(fallbackTimerRef.current);
      }
    };
  }, []);

  const appendLog = (entry: string) => {
    setLogs((current) => [...current, entry]);
  };

  const startFallbackLogs = () => {
    let index = 0;
    fallbackTimerRef.current = window.setInterval(() => {
      if (index >= loadingFallback.length) {
        window.clearInterval(fallbackTimerRef.current ?? undefined);
        fallbackTimerRef.current = null;
        return;
      }

      appendLog(loadingFallback[index]);
      index += 1;
    }, 2500);
  };

  const stopFallbackLogs = () => {
    if (fallbackTimerRef.current) {
      window.clearInterval(fallbackTimerRef.current);
      fallbackTimerRef.current = null;
    }
  };

  const openCheckout = async () => {
    try {
      setCheckoutPending(true);

      const response = await fetch("/api/checkout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ email })
      });

      const payload = await response.json();

      if (!response.ok) {
        setMessage(payload.error ?? "无法创建升级结账链接。");
        return;
      }

      const overlayOpen = window.LemonSqueezy?.Url?.Open;
      if (typeof overlayOpen === "function") {
        overlayOpen(payload.url);
        return;
      }

      window.location.href = payload.url;
    } finally {
      setCheckoutPending(false);
    }
  };

  const connectToEvents = (eventsUrl: string) => {
    const source = new EventSource(eventsUrl);
    eventSourceRef.current = source;

    source.addEventListener("log", (event) => {
      appendLog((event as MessageEvent).data);
    });

    source.addEventListener("result", (event) => {
      const payload = JSON.parse((event as MessageEvent).data) as FinalResult;
      stopFallbackLogs();
      setResult(payload);
      setStatus("completed");
      setMessage("分析完成，PDF 已生成并会通过邮件发送。");
    });

    source.addEventListener("error", (event) => {
      const data = (event as MessageEvent).data;
      if (data) {
        appendLog(`!! ${data}`);
      }

      stopFallbackLogs();
      setStatus("failed");
      setMessage(data || "分析任务失败。");
      source.close();
    });

    source.onerror = async () => {
      source.close();
      eventSourceRef.current = null;
    };
  };

  const handleStart = async (event: FormEvent) => {
    event.preventDefault();

    if (!ticker || !email) {
      setMessage("请先填写股票代码和邮箱。");
      return;
    }

    eventSourceRef.current?.close();
    stopFallbackLogs();
    setLogs([]);
    setResult(null);
    setMessage("");
    setStatus("submitting");

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          ticker,
          email,
          requestedMode: mode,
          deepMode: mode === "deep" ? deepMode : undefined
        })
      });

      const payload = (await response.json()) as AnalyzeResponse & AnalyzeErrorResponse;

      if (!response.ok) {
        setStatus("failed");
        setMessage(payload.error ?? "任务创建失败。");
        if (response.status === 403 || response.status === 429) {
          appendLog(payload.error ?? "当前权限或额度不足。");
        }
        if (response.status === 403 && payload.upgradeRequired) {
          void openCheckout();
        }
        return;
      }

      setQuota(payload.quota);
      setIsPro(payload.isPro);
      setStatus("running");
      appendLog(`>> 任务已创建: ${payload.jobId}`);
      appendLog(`>> 当前模式: ${modeLabel}`);
      startFallbackLogs();
      connectToEvents(payload.eventsUrl);
    } catch (error) {
      setStatus("failed");
      setMessage(error instanceof Error ? error.message : "请求失败。");
    }
  };

  return (
    <div className="min-h-screen bg-sentinel-bg px-4 py-6 text-sentinel-glow md:px-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8 flex flex-col gap-4 border-b border-sentinel-line pb-4 text-xs text-sentinel-glow/70 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-2">
              <Activity size={14} />
              SYSTEM: ACTIVE
            </span>
            <span className="flex items-center gap-2">
              <Radar size={14} />
              PIPELINE: {mode === "basic" ? "BASIC" : "DEEP"}
            </span>
          </div>
          <div>SENTINEL AI / 哨兵投研 / BLOOMBERG-STYLE RISK RADAR</div>
        </header>

        <main className="grid gap-8 lg:grid-cols-[380px_minmax(0,1fr)]">
          <section className="space-y-6">
            <div className="rounded-sm border border-sentinel-line bg-sentinel-panel p-6 shadow-terminal">
              <div className="mb-6 flex items-center gap-3">
                <ShieldAlert className="text-sentinel-glow" />
                <div>
                  <h1 className="text-xl font-semibold text-white">Sentinel Intelligence Briefing</h1>
                  <p className="mt-1 text-xs text-sentinel-glow/55">15 秒模拟日志 + PDF 邮件投递 + Pro 深度模式</p>
                  <p className="mt-2 text-[11px] uppercase tracking-[0.14em] text-sentinel-muted">
                    Not investment advice · Read-only portfolio · Cancel anytime
                  </p>
                </div>
              </div>

              <form className="space-y-4" onSubmit={handleStart}>
                <label className="block text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/60">
                  股票代码
                  <div className="relative mt-2">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-sentinel-glow/35" size={16} />
                    <input
                      value={ticker}
                      onChange={(event) => setTicker(event.target.value.toUpperCase())}
                      className="w-full border border-sentinel-line bg-black px-10 py-3 text-sm text-white outline-none transition focus:border-sentinel-glow"
                      placeholder="例如 NVDA / TSLA / AAPL"
                    />
                  </div>
                </label>

                <label className="block text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/60">
                  收件邮箱
                  <div className="relative mt-2">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-sentinel-glow/35" size={16} />
                    <input
                      type="email"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      className="w-full border border-sentinel-line bg-black px-10 py-3 text-sm text-white outline-none transition focus:border-sentinel-glow"
                      placeholder="investor@example.com"
                    />
                  </div>
                </label>

                <div className="space-y-3">
                  <div className="text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/60">分析模式</div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <button
                      type="button"
                      onClick={() => setMode("basic")}
                      className={`border px-3 py-3 text-left transition ${
                        mode === "basic"
                          ? "border-sentinel-glow bg-sentinel-glow/10 text-white"
                          : "border-sentinel-line bg-black text-sentinel-glow/65"
                      }`}
                    >
                      基础版
                      <div className="mt-1 text-xs text-sentinel-glow/45">免费用户每日 1 次</div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setMode("deep")}
                      className={`border px-3 py-3 text-left transition ${
                        mode === "deep"
                          ? "border-sentinel-glow bg-sentinel-glow/10 text-white"
                          : "border-sentinel-line bg-black text-sentinel-glow/65"
                      }`}
                    >
                      Pro 深度版
                      <div className="mt-1 text-xs text-sentinel-glow/45">$19.9 / 月</div>
                    </button>
                  </div>

                  {mode === "deep" ? (
                    <select
                      value={deepMode}
                      onChange={(event) => setDeepMode(event.target.value)}
                      className="w-full border border-sentinel-line bg-black px-3 py-3 text-sm text-white outline-none"
                    >
                      <option value="valuation">valuation / 估值</option>
                      <option value="growth">growth / 成长</option>
                      <option value="technical">technical / 技术面</option>
                      <option value="fundamentals">fundamentals / 基本面</option>
                      <option value="peers">peers / 同行对比</option>
                      <option value="dividends">dividends / 股息</option>
                    </select>
                  ) : null}
                </div>

                <button
                  type="submit"
                  disabled={status === "submitting" || status === "running"}
                  className={`flex w-full items-center justify-center gap-2 py-3 font-semibold uppercase tracking-[0.18em] transition ${
                    status === "submitting" || status === "running"
                      ? "cursor-not-allowed bg-neutral-800 text-neutral-500"
                      : "bg-sentinel-glow text-black hover:bg-[#38ff9f]"
                  }`}
                >
                  {status === "submitting" || status === "running" ? <Cpu className="animate-spin" size={16} /> : <Terminal size={16} />}
                  {status === "submitting" || status === "running" ? "分析执行中" : "启动扫描"}
                </button>
              </form>
            </div>

            <div className="grid gap-3 text-xs uppercase text-sentinel-glow/60">
              <div className="flex items-center justify-between border border-sentinel-line bg-sentinel-panel px-4 py-3">
                <span>账户等级</span>
                <span className={isPro ? "text-amber-400" : "text-white"}>{isPro ? "PRO" : "FREE"}</span>
              </div>
              <div className="flex items-center justify-between border border-sentinel-line bg-sentinel-panel px-4 py-3">
                <span>基础版当日额度</span>
                <span className="text-white">{isPro ? "UNLIMITED" : quota ? `${quota.used}/${quota.limit}` : "0/1"}</span>
              </div>
              <button
                type="button"
                onClick={openCheckout}
                disabled={checkoutPending}
                className="flex items-center justify-center gap-2 border border-amber-400/50 bg-amber-400/10 px-4 py-3 text-amber-300 transition hover:bg-amber-400 hover:text-black disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Lock size={14} />
                {checkoutPending ? "Opening Checkout..." : "升级 Pro 订阅"}
              </button>
            </div>

            {message ? (
              <div className="border border-sentinel-line bg-sentinel-panel px-4 py-3 text-sm text-sentinel-glow/75">
                {message}
              </div>
            ) : null}
          </section>

          <section className="relative overflow-hidden rounded-sm border border-sentinel-line bg-sentinel-panel shadow-terminal">
            <div className="flex items-center gap-2 border-b border-sentinel-line px-4 py-2 text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/55">
              <div className="h-2 w-2 rounded-full bg-red-500" />
              <div className="h-2 w-2 rounded-full bg-yellow-500" />
              <div className="h-2 w-2 rounded-full bg-green-500" />
              <span className="ml-2">sentinel_core_system_log</span>
            </div>

            <div ref={scrollRef} className="h-[620px] overflow-y-auto px-6 py-5">
              {logs.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-4 text-center text-sentinel-glow/25">
                  <Database size={54} />
                  <div className="space-y-2">
                    <p className="text-base text-sentinel-glow/35">Awaiting Signal</p>
                    <p className="text-sm">输入股票代码后，系统会异步调度 Python 风险引擎，并将实时日志回流到前端终端。</p>
                  </div>
                </div>
              ) : (
                <div className="space-y-2 text-sm">
                  {logs.map((log, index) => (
                    <div key={`${log}-${index}`} className="flex gap-3">
                      <span className="shrink-0 text-sentinel-glow/30">[{String(index + 1).padStart(2, "0")}]</span>
                      <span className={index === logs.length - 1 && status === "running" ? "animate-blink" : ""}>{log}</span>
                    </div>
                  ))}
                </div>
              )}

              {result ? (
                <div className="mt-8 border border-sentinel-glow bg-sentinel-glow/5 p-5 text-white">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h2 className="text-lg font-semibold">{ticker} 分析完成</h2>
                      <p className="mt-1 text-xs uppercase tracking-[0.18em] text-sentinel-glow/60">{modeLabel}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/50">Overall Score</div>
                      <div className="text-3xl font-semibold">{result.score_100 ?? "--"}/100</div>
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="border border-sentinel-line bg-black/40 p-4">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/50">评级</div>
                      <div className="mt-2 text-2xl">{result.rating ?? "--"}</div>
                    </div>
                    <div className="border border-sentinel-line bg-black/40 p-4">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/50">评分参考</div>
                      <div className="mt-2 text-2xl">{formatTier(result.recommendation) ?? "--"}</div>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    <div className="border border-sentinel-line bg-black/40 p-4">
                      <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/50">支撑点</div>
                      <ul className="space-y-2 text-sm text-sentinel-glow/80">
                        {(result.supporting_points ?? []).slice(0, 4).map((item) => (
                          <li key={item}>- {item}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="border border-sentinel-line bg-black/40 p-4">
                      <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-sentinel-glow/50">风险提示</div>
                      <ul className="space-y-2 text-sm text-sentinel-glow/80">
                        {(result.caveats ?? []).slice(0, 4).map((item) => (
                          <li key={item}>- {item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            {status === "running" ? (
              <div className="pointer-events-none absolute inset-0 opacity-10">
                <div className="absolute h-1 w-full animate-scan-line bg-sentinel-glow shadow-[0_0_18px_#00ff88]" />
              </div>
            ) : null}
          </section>
        </main>
      </div>
    </div>
  );
}
