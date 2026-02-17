#!/usr/bin/env python3
"""
LLM Client Module
集成阿里 Qwen API 进行中文摘要生成 (使用 OpenAI 同步模式)
"""

import os
import json
import hashlib
import logging
import time
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from openai import OpenAI

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API 配置
API_KEY = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIBABA_API_KEY")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 模型配置
MODEL_NAME = "qwen3.5-plus"
MAX_TOKENS = 6000  # 增加 token 限制，防止 JSON 被截断
TEMPERATURE = 0.7

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

# 缓存配置
_cache = {}
_cache_ttl = timedelta(hours=1)


class LLMClient:
    """LLM API 客户端 (使用 OpenAI 同步 SDK)"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化 LLM 客户端

        Args:
            api_key: API key，如果不提供则从环境变量获取
        """
        self.api_key = api_key or API_KEY
        if not self.api_key:
            raise ValueError(
                "API key 未设置。请设置 DASHSCOPE_API_KEY 或 ALIBABA_API_KEY 环境变量"
            )

        # 初始化 OpenAI 客户端 (同步)
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=BASE_URL,
        )

        self.total_calls = 0
        self.total_tokens = 0
        self.failed_calls = 0

        logger.info("LLMClient 初始化完成 (使用 OpenAI 同步 SDK)")

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
                del _cache[cache_key]
        return None

    def _save_to_cache(self, cache_key: str, result: Dict):
        """保存结果到缓存"""
        _cache[cache_key] = (result, datetime.now())
        logger.info(f"已缓存: {cache_key[:8]}...")

    def _call_api(self, prompt: str, model: str = MODEL_NAME) -> str:
        """
        调用 LLM API (同步)

        Args:
            prompt: 提示词
            model: 模型名称

        Returns:
            API 响应内容 (字符串)
        """
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                )

                self.total_calls += 1
                self.total_tokens += (
                    response.usage.total_tokens if response.usage else 0
                )

                logger.info(f"API 调用成功 (尝试 {attempt + 1})")
                return response.choices[0].message.content

            except Exception as e:
                logger.error(f"错误 (尝试 {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    self.failed_calls += 1
                    raise
                time.sleep(RETRY_DELAY)

        raise Exception("达到最大重试次数")

    def summarize(self, prompt: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        生成摘要 (同步)

        Args:
            prompt: 提示词
            use_cache: 是否使用缓存

        Returns:
            解析后的 JSON 结果
        """
        cache_key = self._generate_cache_key(prompt)

        if use_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result

        content = self._call_api(prompt)

        # 清理 markdown 代码块标记
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            result = json.loads(content)
            if use_cache:
                self._save_to_cache(cache_key, result)
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析错误，尝试修复: {e}")
            # 尝试修复截断的 JSON
            fixed_content = self._fix_truncated_json(content)
            if fixed_content:
                try:
                    result = json.loads(fixed_content)
                    logger.info("JSON 修复成功")
                    if use_cache:
                        self._save_to_cache(cache_key, result)
                    return result
                except:
                    pass

            logger.error(f"JSON 解析错误: {e}, 内容: {content[:200]}")
            # 返回原始内容
            return {"raw_content": content, "error": "JSON 解析失败", "parsed": False}

    def _fix_truncated_json(self, content: str) -> str:
        """
        尝试修复截断的 JSON

        Args:
            content: 可能截断的 JSON 字符串

        Returns:
            修复后的 JSON 字符串，如果无法修复则返回空字符串
        """
        content = content.strip()

        # 统计未闭合的括号
        open_braces = content.count("{") - content.count("}")
        open_brackets = content.count("[") - content.count("]")

        # 补全缺失的闭合符号
        fixed = content
        if open_braces > 0:
            fixed += "}" * open_braces
        if open_brackets > 0:
            fixed += "]" * open_brackets

        # 如果最后一个字符是逗号，移除它
        if fixed.rstrip().endswith(","):
            fixed = fixed.rstrip()[:-1]

        # 确保以 } 结尾
        if not fixed.rstrip().endswith("}"):
            # 找到最后一个完整的键值对，然后闭合
            last_brace = fixed.rfind("}")
            if last_brace > 0:
                fixed = fixed[: last_brace + 1]

        return fixed

    def chat(self, messages: list, use_cache: bool = True) -> str:
        """
        对话式 API (同步)

        Args:
            messages: 消息列表
            use_cache: 是否使用缓存

        Returns:
            文本回复
        """
        cache_key = self._generate_cache_key(str(messages))
        if use_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                return cached_result.get("content", "")

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                )

                self.total_calls += 1
                self.total_tokens += (
                    response.usage.total_tokens if response.usage else 0
                )

                content = response.choices[0].message.content

                if use_cache:
                    self._save_to_cache(cache_key, {"content": content})

                return content

            except Exception as e:
                logger.error(f"错误 (尝试 {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    self.failed_calls += 1
                    raise
                time.sleep(RETRY_DELAY)

        raise Exception("达到最大重试次数")

    def get_stats(self) -> Dict:
        """获取调用统计"""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "failed_calls": self.failed_calls,
            "cache_size": len(_cache),
            "estimated_cost": self.total_tokens * 0.002 / 1000,
        }


# 便捷函数
def summarize_cluster(
    article_count: int,
    sources: list,
    primary_title: str,
    content_samples: str,
    client: Optional[LLMClient] = None,
) -> Dict:
    """
    为聚类生成摘要（便捷函数）
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

    return client.summarize(prompt)


# 示例用法
if __name__ == "__main__":
    try:
        client = LLMClient()

        prompt = """请将以下新闻标题总结为一句话：
        "Fed Raises Interest Rates by 0.25% to Combat Inflation"
        
        输出JSON格式: {"summary": "..."}"""

        result = client.summarize(prompt)
        print("结果:", json.dumps(result, ensure_ascii=False, indent=2))

        stats = client.get_stats()
        print("\n统计:", json.dumps(stats, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"错误: {e}")
