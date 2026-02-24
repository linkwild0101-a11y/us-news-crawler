/**
 * Railway RSS Proxy Service
 * 用于代理访问被屏蔽或反爬的 RSS 源
 */

const express = require('express');
const cors = require('cors');
const fetch = require('node-fetch');

const app = express();
const PORT = process.env.PORT || 3000;

// 启用 CORS
app.use(cors({
  origin: '*',
  methods: ['GET', 'POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type']
}));

app.use(express.json());

// 健康检查
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'Railway RSS Proxy' });
});

// RSS 代理端点
app.get('/rss', async (req, res) => {
  const feedUrl = req.query.url;
  
  if (!feedUrl) {
    return res.status(400).json({ error: 'Missing url parameter' });
  }
  
  try {
    // 验证 URL 格式
    const parsedUrl = new URL(feedUrl);
    
    console.log(`[RSS Proxy] Fetching: ${feedUrl}`);
    
    // 获取 RSS 内容
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000); // 20秒超时
    
    const response = await fetch(feedUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
      },
      signal: controller.signal,
      redirect: 'follow',
    });
    
    clearTimeout(timeout);
    
    if (!response.ok) {
      console.error(`[RSS Proxy] HTTP ${response.status} for ${feedUrl}`);
      return res.status(response.status).json({
        error: `HTTP ${response.status}`,
        url: feedUrl
      });
    }
    
    const contentType = response.headers.get('content-type') || '';
    const data = await response.text();
    
    console.log(`[RSS Proxy] Success: ${feedUrl} (${data.length} bytes)`);
    
    // 返回原始 RSS 内容
    res.set('Content-Type', contentType.includes('xml') ? contentType : 'application/xml');
    res.set('Cache-Control', 'public, max-age=300');
    res.send(data);
    
  } catch (error) {
    console.error(`[RSS Proxy] Error fetching ${feedUrl}:`, error.message);
    
    const isTimeout = error.name === 'AbortError';
    res.status(isTimeout ? 504 : 502).json({
      error: isTimeout ? 'Request timeout' : 'Failed to fetch feed',
      details: error.message,
      url: feedUrl
    });
  }
});

// 内容提取端点（类似 Cloudflare Worker）
app.post('/extract', async (req, res) => {
  const { url, raw = false } = req.body;
  
  if (!url) {
    return res.status(400).json({ success: false, error: 'Missing url parameter' });
  }
  
  try {
    console.log(`[Extract] Fetching: ${url} (raw: ${raw})`);
    
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000); // 30秒超时
    
    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
      },
      signal: controller.signal,
      redirect: 'follow',
    });
    
    clearTimeout(timeout);
    
    if (!response.ok) {
      return res.status(response.status).json({
        success: false,
        error: `HTTP ${response.status}`
      });
    }
    
    const html = await response.text();
    
    if (raw) {
      // 返回原始内容
      const titleMatch = html.match(/<title[^>]*>([^<]*)<\/title>/i);
      const title = titleMatch ? titleMatch[1].trim() : '';
      
      return res.json({
        success: true,
        title,
        content: html,
        is_raw: true
      });
    }
    
    // 提取内容
    const extracted = extractContent(html);
    res.json({
      ...extracted,
      success: true
    });
    
  } catch (error) {
    console.error(`[Extract] Error:`, error.message);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// 内容提取函数
function extractContent(html) {
  let title = '';
  let content = '';
  let excerpt = '';
  let author = '';
  let published_time = '';
  
  // 提取标题
  const titleMatch = html.match(/<title[^>]*>([^<]*)<\/title>/i);
  if (titleMatch) {
    title = titleMatch[1].trim();
  }
  
  // Open Graph 标题
  const ogTitleMatch = html.match(/<meta[^>]*property=["']og:title["'][^>]*content=["']([^"']*)["']/i);
  if (ogTitleMatch && ogTitleMatch[1]) {
    title = ogTitleMatch[1];
  }
  
  // 描述
  const descMatch = html.match(/<meta[^>]*name=["']description["'][^>]*content=["']([^"']*)["']/i);
  if (descMatch) {
    excerpt = descMatch[1];
  }
  
  // 作者
  const authorMatch = html.match(/<meta[^>]*name=["']author["'][^>]*content=["']([^"']*)["']/i);
  if (authorMatch) {
    author = authorMatch[1];
  }
  
  // 发布时间
  const timeMatch = html.match(/<meta[^>]*property=["']article:published_time["'][^>]*content=["']([^"']*)["']/i);
  if (timeMatch) {
    published_time = timeMatch[1];
  }
  
  // 清理 HTML
  let cleanedHtml = html
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<!--[\s\S]*?-->/g, '');
  
  // 提取正文
  const articleMatch = cleanedHtml.match(/<article[^>]*>([\s\S]*?)<\/article>/i);
  const mainMatch = cleanedHtml.match(/<main[^>]*>([\s\S]*?)<\/main>/i);
  
  let rawContent = '';
  if (articleMatch) {
    rawContent = articleMatch[1];
  } else if (mainMatch) {
    rawContent = mainMatch[1];
  }
  
  // 转文本
  content = rawContent
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  
  if (content.length > 10000) {
    content = content.substring(0, 10000) + '...';
  }
  
  return {
    title,
    content,
    excerpt: excerpt || content.substring(0, 200) + '...',
    author,
    published_time
  };
}

// 根路径
app.get('/', (req, res) => {
  res.json({
    service: 'Railway RSS Proxy',
    version: '1.0.0',
    endpoints: {
      '/health': 'GET - Health check',
      '/rss?url={feed_url}': 'GET - Proxy RSS feed',
      '/extract': 'POST - Extract content from URL'
    }
  });
});

app.listen(PORT, () => {
  console.log(`Railway RSS Proxy running on port ${PORT}`);
  console.log(`Health check: http://localhost:${PORT}/health`);
});
