# Railway RSS Proxy

用于代理访问被屏蔽或反爬的 RSS 源

## 端点

- `GET /health` - 健康检查
- `GET /rss?url={feed_url}` - 代理 RSS feed
- `POST /extract` - 提取网页内容
  - Body: `{ "url": "https://example.com", "raw": true }`

## 部署到 Railway

### 方法 1: 通过 Railway CLI

1. 安装 Railway CLI:
```bash
npm install -g @railway/cli
```

2. 登录 Railway:
```bash
railway login
```

3. 初始化项目:
```bash
cd railway-rss-proxy
railway init
```

4. 部署:
```bash
railway up
```

### 方法 2: 通过 GitHub 集成（推荐）

1. 将代码推送到 GitHub
2. 在 Railway Dashboard 创建新项目
3. 选择 "Deploy from GitHub repo"
4. 选择此仓库
5. Railway 会自动部署

### 方法 3: 通过 Railway Dashboard 手动上传

1. 压缩项目文件为 zip
2. 在 Railway Dashboard 创建新项目
3. 选择 "Upload code"
4. 上传 zip 文件

## 获取域名

部署成功后，Railway 会提供一个域名:
- `https://your-service-name.railway.app`

在 Railway Dashboard 的 Settings 中可以查看和修改域名。

## 测试

```bash
# 测试健康检查
curl https://your-domain.railway.app/health

# 测试 RSS 代理
curl "https://your-domain.railway.app/rss?url=https://feeds.bbci.co.uk/news/rss.xml"

# 测试内容提取
curl -X POST https://your-domain.railway.app/extract \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "raw": true}'
```
