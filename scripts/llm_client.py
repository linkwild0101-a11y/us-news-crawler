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

# 配置日志 - 同时输出到控制台和文件
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 清除现有的处理器
if logger.handlers:
    logger.handlers.clear()

# 创建格式器 - 包含时间戳
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 文件处理器 - 记录到日志文件
log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "..", "logs", "llm_client.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)

file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

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
        start_time = time.time()
        prompt_length = len(prompt)

        for attempt in range(MAX_RETRIES):
            try:
                api_start = time.time()
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                )
                api_duration = time.time() - api_start

                self.total_calls += 1
                self.total_tokens += (
                    response.usage.total_tokens if response.usage else 0
                )

                total_duration = time.time() - start_time
                logger.info(
                    f"API 调用成功 | "
                    f"尝试: {attempt + 1}/{MAX_RETRIES} | "
                    f"API耗时: {api_duration:.2f}s | "
                    f"总耗时: {total_duration:.2f}s | "
                    f"提示词长度: {prompt_length}字符 | "
                    f"Token使用: {response.usage.total_tokens if response.usage else 'N/A'}"
                )
                return response.choices[0].message.content

            except Exception as e:
                error_duration = time.time() - start_time
                logger.error(
                    f"API 错误 | "
                    f"尝试: {attempt + 1}/{MAX_RETRIES} | "
                    f"耗时: {error_duration:.2f}s | "
                    f"错误: {str(e)[:100]}"
                )
                if attempt == MAX_RETRIES - 1:
                    self.failed_calls += 1
                    raise
                time.sleep(RETRY_DELAY)

        raise Exception("达到最大重试次数")

    def summarize(
        self, prompt: str, use_cache: bool = True, model: str = None
    ) -> Dict[str, Any]:
        """
        生成摘要 (同步)

        Args:
            prompt: 提示词
            use_cache: 是否使用缓存
            model: 模型名称，不传则使用默认 MODEL_NAME

        Returns:
            解析后的 JSON 结果
        """
        total_start = time.time()
        cache_key = self._generate_cache_key(prompt + (model or MODEL_NAME))

        logger.info(
            f"[SUMMARIZE_START] 开始生成摘要 | cache_key: {cache_key[:8]}... | use_cache: {use_cache}"
        )

        # 检查缓存
        cache_check_start = time.time()
        if use_cache:
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                cache_duration = time.time() - cache_check_start
                total_duration = time.time() - total_start
                logger.info(
                    f"[SUMMARIZE_CACHE_HIT] 缓存命中 | "
                    f"检查缓存耗时: {cache_duration:.3f}s | "
                    f"总耗时: {total_duration:.3f}s"
                )
                return cached_result
        cache_check_duration = time.time() - cache_check_start
        logger.info(f"[CACHE_CHECK] 缓存未命中 | 检查耗时: {cache_check_duration:.3f}s")

        # 调用 API
        api_start = time.time()
        content = self._call_api(prompt, model=model or MODEL_NAME)
        api_duration = time.time() - api_start
        content_length = len(content)
        logger.info(
            f"[API_COMPLETE] API调用完成 | 耗时: {api_duration:.2f}s | 返回内容长度: {content_length}字符"
        )

        # 清理 markdown
        clean_start = time.time()
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        clean_duration = time.time() - clean_start

        # 解析 JSON
        parse_start = time.time()
        try:
            result = json.loads(content)
            parse_duration = time.time() - parse_start

            # 保存到缓存
            if use_cache:
                cache_save_start = time.time()
                self._save_to_cache(cache_key, result)
                cache_save_duration = time.time() - cache_save_start
            else:
                cache_save_duration = 0

            total_duration = time.time() - total_start
            logger.info(
                f"[SUMMARIZE_SUCCESS] 摘要生成成功 | "
                f"总耗时: {total_duration:.2f}s | "
                f"API调用: {api_duration:.2f}s | "
                f"清理格式: {clean_duration:.3f}s | "
                f"JSON解析: {parse_duration:.3f}s | "
                f"缓存保存: {cache_save_duration:.3f}s | "
                f"返回结果键: {list(result.keys())}"
            )
            return result

        except json.JSONDecodeError as e:
            parse_duration = time.time() - parse_start
            logger.warning(
                f"[JSON_PARSE_ERROR] JSON解析错误 | "
                f"解析耗时: {parse_duration:.3f}s | "
                f"错误: {str(e)[:100]} | "
                f"尝试修复..."
            )

            # 尝试修复截断的 JSON
            fix_start = time.time()
            fixed_content = self._fix_truncated_json(content)
            fix_duration = time.time() - fix_start

            if fixed_content:
                try:
                    result = json.loads(fixed_content)
                    total_duration = time.time() - total_start
                    logger.info(
                        f"[SUMMARIZE_FIXED] JSON修复成功 | "
                        f"总耗时: {total_duration:.2f}s | "
                        f"修复耗时: {fix_duration:.3f}s"
                    )
                    if use_cache:
                        self._save_to_cache(cache_key, result)
                    return result
                except:
                    pass

            total_duration = time.time() - total_start
            logger.error(
                f"[SUMMARIZE_FAILED] 摘要生成失败 | "
                f"总耗时: {total_duration:.2f}s | "
                f"API: {api_duration:.2f}s | "
                f"清理: {clean_duration:.3f}s | "
                f"解析: {parse_duration:.3f}s | "
                f"修复: {fix_duration:.3f}s | "
                f"内容前200字符: {content[:200]}"
            )
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

    def translate_text(
        self, text: str, model: str = None, use_cache: bool = True
    ) -> str:
        """
        纯文本翻译（不解析 JSON，用于快速翻译模式）

        Args:
            text: 需要翻译的文本
            model: 模型名称
            use_cache: 是否使用缓存

        Returns:
            翻译后的纯文本
        """
        total_start = time.time()
        prompt = f"请将以下英文翻译成中文，只返回翻译结果，不要任何解释：\n\n{text}"
        cache_key = self._generate_cache_key(f"translate_{text}_{model or MODEL_NAME}")

        logger.debug(f"[TRANSLATE_START] 开始翻译 | cache_key: {cache_key[:8]}...")

        # 检查缓存
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached and "translation" in cached:
                total_duration = time.time() - total_start
                logger.debug(
                    f"[TRANSLATE_CACHE_HIT] 翻译缓存命中 | 耗时: {total_duration:.3f}s"
                )
                return cached["translation"]

        # 调用 API
        try:
            content = self._call_api(prompt, model=model or MODEL_NAME)
            translation = content.strip()

            # 保存到缓存
            if use_cache:
                self._save_to_cache(cache_key, {"translation": translation})

            total_duration = time.time() - total_start
            logger.debug(
                f"[TRANSLATE_SUCCESS] 翻译成功 | "
                f"耗时: {total_duration:.2f}s | "
                f"原文长度: {len(text)} | 译文长度: {len(translation)}"
            )
            return translation

        except Exception as e:
            total_duration = time.time() - total_start
            logger.error(
                f"[TRANSLATE_FAILED] 翻译失败 | "
                f"耗时: {total_duration:.2f}s | 错误: {str(e)[:100]}"
            )
            return text  # 失败时返回原文

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
