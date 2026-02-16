/**
 * Cloudflare Worker - 内容提取服务
 * 修复: 处理 header 过长和提取正文
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    if (url.pathname === '/health') {
      return new Response(JSON.stringify({ status: 'ok' }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    if (url.pathname === '/extract' && request.method === 'POST') {
      return await handleExtract(request);
    }
    
    return new Response(JSON.stringify({
      service: 'Content Extractor',
      version: '1.1.0',
      endpoints: {
        '/health': 'GET - Health check',
        '/extract': 'POST - Extract content from URL'
      }
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
  },
};

async function handleExtract(request) {
  try {
    const body = await request.json();
    const targetUrl = body.url;
    
    if (!targetUrl) {
      return new Response(JSON.stringify({
        success: false,
        error: 'Missing url parameter'
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    // 跳过 Twitter/X 链接
    if (targetUrl.includes('twitter.com') || targetUrl.includes('x.com')) {
      return new Response(JSON.stringify({
        success: false,
        error: 'Twitter/X links are not supported'
      }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    // 简化的 headers 避免 header 过长
    const response = await fetch(targetUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,*/*',
        'Accept-Encoding': 'gzip',
      },
    });
    
    if (!response.ok) {
      return new Response(JSON.stringify({
        success: false,
        error: 'HTTP ' + response.status
      }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' }
      });
    }
    
    const html = await response.text();
    const extracted = extractContent(html);
    
    return new Response(JSON.stringify({
      ...extracted,
      success: true
    }), {
      headers: { 'Content-Type': 'application/json' }
    });
    
  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message || 'Unknown error'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

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
