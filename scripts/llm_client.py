#!/usr/bin/env python3
"""
LLM Client Module
集成阿里 Qwen3-Plus API 进行中文摘要生成
"""

import os
import json
import time
import hashlib
import logging
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
import aiohttp

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API 配置
API_KEY = os.getenv("ALIBABA_API_KEY")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 模型配置
MODEL_NAME = "qwen-plus"
MAX_TOKENS = 4000
TEMPERATURE = 0.7

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

# 缓存配置
_cache = {}
_cache_ttl = timedelta(hours=1)


class LLMClient:
    """LLM API 客户端"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 LLM 客户端

        Args:
            api_key: API key，如果不提供则从环境变量 ALIBABA_API_KEY 获取
        """
        self.api_key = api_key or API_KEY
        if not self.api_key:
            raise ValueError(
                "API key 未设置。请设置 ALIBABA_API_KEY 环境变量或传入 api_key 参数"
            )

        self.total_calls = 0
        self.total_tokens = 0
        self.failed_calls = 0

        logger.info("LLMClient 初始化完成")

    def _generate_cache_key(self, prompt: str, model: str = MODEL_NAME) -> str:
        """生成缓存键"""
        content = f"{model}:{prompt}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """从缓存获取结果"""
        if cache_key in _cache:
            result, timestamp = _cache[cache_key]
            if datetime.now() - timestamp < _cache_ttl:
                logger.info(f"缓存命中: {cache_key[:8]}...")
                return result
            else:
                # 过期，删除
                del _cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, result: Dict):
        """保存结果到缓存"""
        _cache[cache_key] = (result, datetime.now())
        logger.info(f"已缓存: {cache_key[:8]}...")

    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数量（粗略估计）"""
        # 英文平均 1 token ≈ 4 字符，中文平均 1 token ≈ 1.5 字符
        # 保守估计，按平均 1 token ≈ 2 字符
        return len(text) // 2

    async def _call_api(self, prompt: str, model: str = MODEL_NAME) -> Dict:
        """
        调用 LLM API

        Args:
            prompt: 提示词
            model: 模型名称

        Returns:
            API 响应
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": prompt}]},
            "parameters": {
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
                "result_format": "message",
            },
        }

        for attempt in range(MAX_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        BASE_URL,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.total_calls += 1

                            # 估算 token 使用量
                            output_text = (
                                data.get("output", {})
                                .get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )
                            tokens_used = self._estimate_tokens(
                                prompt
                            ) + self._estimate_tokens(output_text)
                            self.total_tokens += tokens_used

                            logger.info(f"API 调用成功 (尝试 {attempt + 1})")
                            return data
                        elif response.status == 429:
                            # 速率限制，等待后重试
                            wait_time = RETRY_DELAY * (2**attempt)
                            logger.warning(f"速率限制，等待 {wait_time} 秒后重试...")
                            await asyncio.sleep(wait_time)
                        else:
                            error_text = await response.text()
                            logger.error(
                                f"API 错误: HTTP {response.status}, {error_text}"
                            )
                            if attempt == MAX_RETRIES - 1:
                                self.failed_calls += 1
                                raise Exception(
                                    f"API 调用失败: HTTP {response.status}, {error_text}"
                                )
                            await asyncio.sleep(RETRY_DELAY)

            except aiohttp.ClientError as e:
                logger.error(f"网络错误 (尝试 {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    self.failed_calls += 1
                    raise Exception(f"网络错误: {e}")
                await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"错误 (尝试 {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    self.failed_calls += 1
                    raise
                await asyncio.sleep(RETRY_DELAY)

        raise Exception("达到最大重试次数")

    async def summarize(self, prompt: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        生成摘要

        Args:
            prompt: 提示词
            use_cache: 是否使用缓存

        Returns:
            解析后的 JSON 结果
        """
        # 生成缓存键（无论是否使用缓存，都需要用于一致性）
        cache_key = self._generate_cache_key(prompt)

        # 检查缓存
        if use_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

        # 调用 API
        response = await self._call_api(prompt)

        # 提取内容
        content = ""  # 初始化，避免未绑定错误
        try:
            content = (
                response.get("output", {})
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )

            # 尝试解析 JSON
            # 有时候 LLM 会在 JSON 外面加 markdown 代码块标记
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            result = json.loads(content)

            # 保存到缓存
            if use_cache:
                self._save_to_cache(cache_key, result)

            return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析错误: {e}, 内容: {content[:200]}")
            # 返回原始内容
            return {"raw_content": content, "error": "JSON 解析失败", "parsed": False}

    async def chat(self, messages: list, use_cache: bool = True) -> str:
        """
        对话式 API

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}, ...]
            use_cache: 是否使用缓存

        Returns:
            文本回复
        """
        # 生成缓存键（无论是否使用缓存）
        cache_key = self._generate_cache_key(str(messages))
        if use_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result.get("content", "")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": MODEL_NAME,
            "input": {"messages": messages},
            "parameters": {
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE,
                "result_format": "message",
            },
        }

        for attempt in range(MAX_RETRIES):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        BASE_URL,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            self.total_calls += 1

                            content = (
                                data.get("output", {})
                                .get("choices", [{}])[0]
                                .get("message", {})
                                .get("content", "")
                            )

                            # 保存到缓存
                            if use_cache:
                                self._save_to_cache(cache_key, {"content": content})

                            return content
                        else:
                            error_text = await response.text()
                            logger.error(
                                f"API 错误: HTTP {response.status}, {error_text}"
                            )
                            if attempt == MAX_RETRIES - 1:
                                self.failed_calls += 1
                                raise Exception(f"API 调用失败: HTTP {response.status}")
                            await asyncio.sleep(RETRY_DELAY)

            except Exception as e:
                logger.error(f"错误 (尝试 {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    self.failed_calls += 1
                    raise
                await asyncio.sleep(RETRY_DELAY)

        raise Exception("达到最大重试次数")

    def get_stats(self) -> Dict:
        """获取调用统计"""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "failed_calls": self.failed_calls,
            "cache_size": len(_cache),
            "estimated_cost": self.total_tokens
            * 0.002
            / 1000,  # 粗略估计 $0.002/1K tokens
        }


# 便捷函数
async def summarize_cluster(
    article_count: int,
    sources: list,
    primary_title: str,
    content_samples: str,
    client: Optional[LLMClient] = None,
) -> Dict:
    """
    为聚类生成摘要（便捷函数）

    Args:
        article_count: 文章数量
        sources: 来源列表
        primary_title: 主要标题
        content_samples: 内容片段
        client: LLMClient 实例，如果不提供则创建新实例

    Returns:
        摘要结果字典
    """
    from config.analysis_config import LLM_PROMPTS

    if client is None:
        client = LLMClient()

    prompt = LLM_PROMPTS["cluster_summary"].format(
        article_count=article_count,
        sources=", ".join(sources[:5]),
        primary_title=primary_title,
        content_samples=content_samples[:1000],
    )

    return await client.summarize(prompt)


# 示例用法
if __name__ == "__main__":
    import asyncio

    async def test():
        # 测试客户端
        try:
            client = LLMClient()

            # 测试简单提示
            prompt = """请将以下新闻标题总结为一句话：
            "Fed Raises Interest Rates by 0.25% to Combat Inflation"
            
            输出JSON格式: {"summary": "..."}"""

            result = await client.summarize(prompt)
            print("结果:", json.dumps(result, ensure_ascii=False, indent=2))

            # 打印统计
            stats = client.get_stats()
            print("\n统计:", json.dumps(stats, ensure_ascii=False, indent=2))

        except Exception as e:
            print(f"错误: {e}")

    asyncio.run(test())
