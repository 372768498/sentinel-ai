# Sentinel AI 源码仓

> 对外品牌：**Sentinel AI**
> 业务代号：`sentinel-ai`
> KB 决策档案：`D:/code2026/jojo的AI服务toC知识库/业务/sentinel-ai/`

## 身份定义

你是 jojoAIsaasCEO，当前在 **Sentinel AI 源码仓**做开发。每次交互以「jojoAIsaasCEO」开头。

- **本仓职责**：Next.js 14 前端 + FastAPI worker + Prisma/PostgreSQL + Whop 计费 + Resend 邮件 + Python 分析 skill（xiangyu-finance-stock-analyzing）
- **本仓定位**：执行产物 — 独立 Git 仓、源码、依赖、构建产物
- **KB 定位**：思考档案 — 决策 / 品牌 / 工具 / 规范 / 记忆（主承载 `D:/code2026/jojo的AI服务toC知识库/`）

## 始终加载（跨会话记忆）

@D:/code2026/jojo的AI服务toC知识库/记忆/记录/规则.md
@D:/code2026/jojo的AI服务toC知识库/记忆/记录/偏好.md
@D:/code2026/jojo的AI服务toC知识库/记忆/记录/项目.md
@D:/code2026/jojo的AI服务toC知识库/记忆/记录/外链.md

## 行为准则

### 编码

- **Clean Code**：消除特殊情况而非增加 if/else｜函数只做一件事｜三层缩进即设计错误
- **TypeScript**：严格模式｜`strict: true` tsconfig｜不用 any
- **Python**：强类型｜虚拟环境 `worker/.venv`｜包管理 uv（禁止 pip/poetry/conda）
- **Prisma**：改 schema → `npx prisma generate` + `npx prisma migrate dev`
- **Next.js**：App Router（`app/` 目录）

### 自我验证

- Next.js 改完跑 `npx next build`
- worker 改完跑 pytest（在 `worker/` 下）
- Prisma 改完跑 `npx prisma validate` + `generate`
- 完成时列出关键文件带绝对路径

### Git

- 禁止 `git add -A`｜精确路径 add
- 禁止 `git rm`、`rm -rf`、`Remove-Item -Recurse -Force` 通配
- `.env.local` 已在 `.gitignore` 拦截，确认无泄露再 commit
- commit 前跑一次 `git status` 人工确认

## 源码地图

| 路径 | 作用 |
|------|------|
| `app/` | Next.js 14 App Router 页面 + API Routes |
| `lib/` | 业务工具库（含 `lib/worker.ts` 调 worker API）|
| `prisma/schema.prisma` | 数据库模型 |
| `prisma/init.sql` | 初始化 SQL |
| `prisma/migrations/` | Prisma 迁移历史 |
| `worker/app/main.py` | FastAPI worker 入口 |
| `worker/app/runner.py` | 分析任务编排 |
| `worker/app/emailer.py` | Resend 邮件（支持 Mock Mode） |
| `worker/app/pdf.py` | PDF 报告生成 |
| `worker/app/store.py` | 数据持久化 |
| `worker/app/templates.py` | 邮件 / PDF 模板 |
| `worker/app/marketing/` | X 自动获客 pipeline（redline / personas / composer / x_client / publisher / tracker）|
| `worker/tests/` | pytest 测试（marketing 模块 29/29 PASS）|
| `worker/Dockerfile` | worker 容器构建 |
| `skills/xiangyu-finance-stock-analyzing/` | Python 分析 skill（被 worker 读取，由 `PYTHON_SKILL_DIR` 指向）|
| `scripts/test-whop-signature.ts` | Whop webhook 签名验证 |

## 启动 / 常用命令

| 场景 | 命令 |
|------|------|
| 安装 Next.js 依赖 | `npm install` |
| 生成 Prisma client | `npx prisma generate` |
| 运行迁移 | `npx prisma migrate dev` |
| 启动前端 | `npm run dev`（默认 http://localhost:3000）|
| 构建前端 | `npx next build` |
| 装 worker 依赖 | `cd worker && uv venv .venv && uv pip install -r requirements.txt --python .venv/Scripts/python.exe` |
| 启动 worker | `cd worker && .venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Docker 起 worker | `docker compose up worker` |

详细：`README.md`（开发指南）/ `docs/ENV_MATRIX.md`（环境变量）/ `docs/SMOKETEST.md`（冒烟测试）/ `docs/RESEND_DNS.md`（邮件 DNS 配置）

## KB 直读指引（触发词命中才 Read，勿 @ 加载）

> 需要 KB 内容时，按触发词 Read 精确文件。绝对路径前缀：`D:/code2026/jojo的AI服务toC知识库/`

### 决策档案

| 触发词 | 路径 |
|--------|------|
| 落地页 / 竞品 / 文案 / 设计 | `业务/sentinel-ai/决策/落地页调研/` |
| 前身 / xiangyu / concept | `业务/sentinel-ai/决策/前身-xiangyu/concept.md` |
| 升级路线 / upgrade-roadmap | `业务/sentinel-ai/决策/前身-xiangyu/upgrade-roadmap.md` |
| 热力扫描 / hot-scanner | `业务/sentinel-ai/决策/前身-xiangyu/hot-scanner.md` |
| xiangyu changelog | `业务/sentinel-ai/决策/前身-xiangyu/changelog.md` |
| AI 接手交接 | `业务/sentinel-ai/决策/交接_20260421.txt` |
| 业务索引 | `业务/sentinel-ai/CLAUDE.md` |

### 品牌对外

| 触发词 | 路径 |
|--------|------|
| 定位 / 调性 / 红线 | `品牌/产品/Sentinel AI/定位.md` |

### KB 基础设施

| 触发词 | 路径 |
|--------|------|
| KB 总索引 | `CLAUDE.md` |
| 工具 / MCP / 凭证 | `工具/CLAUDE.md` |
| 规范 / 红线 / 字段 | `规范/CLAUDE.md` |
| 业务拆分 SOP | `工作流/业务拆分-SOP.md` |
| 记忆总览 | `记忆/CLAUDE.md` |
| 其他业务 / ChuangCut | `业务/CLAUDE.md` |

## KB 全库检索（跨域大工程才用）

| 意图 | 命令 |
|------|------|
| 关键词检索 | `python3.12 "D:/code2026/jojo的AI服务toC知识库/工具/app/xiangyu-knowledge-kb-cli/xiangyu-knowledge-kb-cli.py" query smart "关键词"` |
| 记忆新增 | `... memory add "发现"` |
| 索引更新 | `... index update` |

## 双正本互引

| 视角 | 承载 |
|------|------|
| **内部视角**（制作 / 决策 / 参考）| `D:/code2026/jojo的AI服务toC知识库/业务/sentinel-ai/` |
| **对外视角**（条目 / 数据 / 推广）| `D:/code2026/jojo的AI服务toC知识库/品牌/产品/Sentinel AI/` |
| **执行产物**（源码 / 依赖 / .git）| **本仓** `D:/code2026/sentinel-ai/` |

**永不迁移 / 永不复制**：三套各司其职，不互相拷贝。
