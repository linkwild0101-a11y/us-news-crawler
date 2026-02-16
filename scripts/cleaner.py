#!/usr/bin/env python3
"""
数据清洗模块
"""

import re
from typing import Optional


def clean_html_tags(text: str) -> str:
    """清理HTML标签"""
    if not text:
        return ""
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def normalize_whitespace(text: str) -> str:
    """规范化空白字符"""
    if not text:
        return ""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def decode_html_entities(text: str) -> str:
    """解码HTML实体"""
    if not text:
        return ""

    entities = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&apos;": "'",
        "&#39;": "'",
    }

    for entity, char in entities.items():
        text = text.replace(entity, char)

    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)

    return text


def clean_text(text: str) -> str:
    """完整清洗流程"""
    text = clean_html_tags(text)
    text = decode_html_entities(text)
    text = normalize_whitespace(text)
    return text


def truncate_text(text: str, max_length: int = 10000) -> str:
    """截断文本"""
    if not text or len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def extract_summary(content: str, max_length: int = 200) -> str:
    """提取摘要"""
    if not content:
        return ""

    cleaned = clean_text(content)
    cleaned = cleaned.replace("\n", " ")

    if len(cleaned) <= max_length:
        return cleaned

    return cleaned[:max_length].rsplit(" ", 1)[0] + "..."
