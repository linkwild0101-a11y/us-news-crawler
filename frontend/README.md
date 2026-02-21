# US-Monitor Mobile Frontend

移动端优先的 Next.js + Tailwind 前端，读取 Supabase 只读数据并展示四个 Tab：市场总览、哨兵信号、股票看板、新闻与关系。

## 本地运行

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

环境变量：

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

## Cloudflare Pages

- Framework preset: `Next.js`
- Build command: `npm run build`
- Output directory: `.next`
- Root directory: `frontend`

部署后请在环境变量中配置上述两个 `NEXT_PUBLIC_` 变量。

## GitHub 自动部署

仓库已提供 `.github/workflows/deploy-mobile-frontend.yml`：

- 当 `main` 分支下 `frontend/**` 变更时自动触发部署
- 使用 `npx @cloudflare/next-on-pages@1` 构建并发布到
  `us-monitor-mobile-dashboard`

需要在 GitHub Secrets 中配置：

- `CLOUDFLARE_API_TOKEN`（或 `CF_API_TOKEN` / `CLOUDFLARE_TOKEN`）

另外请在 Cloudflare Pages 项目环境变量中配置：

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
