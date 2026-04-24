# Sentinel AI 本地开发指南

本指南用于本地启动 Sentinel AI 的三部分能力：

- Next.js 前端
- FastAPI worker
- PostgreSQL / Supabase 兼容数据库

当前仓库已经内置 Python Skill：

- `./skills/xiangyu-finance-stock-analyzing`

worker 默认会从这里读取分析脚本；如需覆盖，设置 `PYTHON_SKILL_DIR` 即可。

## 1. 环境准备

本地已验证的基础工具：

- Node.js 24+
- npm 11+
- Python 3.12+
- Docker Desktop

首次准备：

```powershell
cd D:\code2026\sentinel-ai
copy .env.example .env.local
```

如果你在 PowerShell 中不想用 `copy`，也可以手动复制 `.env.example` 为 `.env.local`。

关键环境变量：

- `DATABASE_URL`
- `WORKER_API_BASE_URL`
- `WORKER_INTERNAL_TOKEN`
- `INTERNAL_CALLBACK_SECRET`
- `PYTHON_SKILL_DIR`
- `RESEND_API_KEY`
- `RESEND_FROM_EMAIL`
- `LEMON_SQUEEZY_*`

说明：

- 如果 `RESEND_API_KEY` 留空，worker 会自动进入 Mock Mode。
- Mock Mode 下不会真正发信，而是把邮件主题、收件人、HTML 内容、PDF 文件名打印到 worker 控制台。
- 如果你使用本文提供的 `docker compose` 启动 worker，建议本地 `.env.local` 中至少设置为：

```env
WORKER_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_WORKER_URL=http://localhost:8000
WORKER_INTERNAL_TOKEN=local-dev-worker-token
INTERNAL_CALLBACK_SECRET=local-dev-callback-secret
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sentinel_ai?schema=public
```

如果 Next.js 跑在宿主机，而 worker 跑在 Docker 容器内，请额外设置：
```env
NEXT_PUBLIC_APP_URL=http://localhost:3000
APP_URL=http://host.docker.internal:3000
```

说明：
- `NEXT_PUBLIC_APP_URL` 给浏览器访问使用
- `APP_URL` 给 worker 容器回调 Next.js API 使用
- 如果容器内也写成 `localhost:3000`，worker 会回调到它自己，导致 `Connection Refused` 或 `All connection attempts failed`

## 2. 推荐数据库初始化方式：Prisma

这是推荐方式，因为它与代码中的 Prisma schema 保持一致。

### 2.1 启动本地 PostgreSQL

```powershell
docker compose up -d postgres
```

默认连接信息：

- Host: `localhost`
- Port: `5432`
- DB: `sentinel_ai`
- User: `postgres`
- Password: `postgres`

对应 `DATABASE_URL`：

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/sentinel_ai?schema=public
```

### 2.2 生成 Prisma Client

```powershell
npm install
npm run prisma:generate
```

### 2.3 创建本地迁移并落库

```powershell
npm run prisma:migrate -- --name init
```

执行后会：

- 创建 Prisma migration
- 在本地 PostgreSQL 中创建表结构
- 生成最新 Prisma Client

## 3. 可直接用于 Supabase SQL Editor 的初始化 SQL

如果你不想先走 Prisma，也可以直接使用：

- `prisma/init.sql`

在 Supabase SQL Editor 中执行该文件内容即可。

它会创建：

- `AnalysisStatus`
- `ReportTier`
- `SubscriptionPlan`
- `SubscriptionState`
- `"User"`
- `"AnalysisHistory"`
- `"SubscriptionStatus"`

以及必要索引。

注意：

- 这些表名和字段名使用了 Prisma 默认的大小写映射。
- 如果你之后仍然要使用 Prisma，建议长期还是以 Prisma migration 为准，不要手工改表结构。

## 4. 本地启动方式

### 方式 A：Docker 启动 PostgreSQL + worker，前端本机跑

这是最适合日常开发的方式。

```powershell
docker compose up -d postgres worker
npm run dev
```

此时：

- 前端：`http://localhost:3000`
- worker：`http://localhost:8000`
- PostgreSQL：`localhost:5432`

### 方式 B：只启动数据库

```powershell
docker compose up -d postgres
```

然后分别启动：

```powershell
npm run dev
npm run worker:dev
```

## 5. Docker Compose 说明

根目录已提供：

- `docker-compose.yml`

包含服务：

- `postgres`
- `worker`

worker 特性：

- 直接挂载当前仓库目录
- 默认使用项目内 `./skills/xiangyu-finance-stock-analyzing/scripts/python`
- 未配置 `RESEND_API_KEY` 时自动 Mock Email

## 6. E2E 本地联调建议

建议按这个顺序：

1. 启动数据库

```powershell
docker compose up -d postgres
```

2. 初始化数据库

```powershell
npm run prisma:generate
npm run prisma:migrate -- --name init
```

3. 启动 worker

```powershell
docker compose up -d worker
```

4. 启动 Next.js 前端

```powershell
npm run dev
```

5. 在浏览器打开：

```text
http://localhost:3000
```

6. 输入 ticker 和邮箱，观察：

- 前端终端日志是否持续刷新
- worker 控制台是否输出 Python stderr 日志
- 若无 `RESEND_API_KEY`，控制台是否打印 Mock Email HTML
- 是否生成 PDF
- 数据库中是否写入 `AnalysisHistory`

## 7. Mock Mode 验证点

当 `RESEND_API_KEY` 为空时：

- worker 不会请求 Resend API
- 会在控制台打印：
  - 发件人
  - 收件人
  - subject
  - PDF 附件文件名
  - HTML 邮件正文

你可以直接在终端里审查：

- 邮件标题是否正确
- HTML 是否符合预期
- PDF 是否已生成

## 8. 常见问题

### 8.1 `Ticker data unavailable`

通常是：

- 网络不可达
- Yahoo Finance 临时限流
- 本地沙箱或代理阻断

### 8.2 PDF 生成失败

优先检查：

- Docker 镜像是否包含 Chromium 依赖
- `playwright install --with-deps chromium` 是否成功
- 是否缺少系统字体或 `libnss3` / `libatk-bridge2.0-0` 等库

### 8.3 Supabase 联调

如果你切换到真实 Supabase：

1. 替换 `.env.local` 中的 `DATABASE_URL`
2. 运行：

```powershell
npm run prisma:generate
npm run prisma:migrate -- --name init
```

如果不想让 Prisma 改库，也可直接在 Supabase SQL Editor 执行 `prisma/init.sql`。
