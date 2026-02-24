#!/usr/bin/env python3
"""
文本标准化工具
用于繁体中文兼容与关键词匹配
"""

import re
from typing import Iterable, List, Set

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_TOKEN_RE = re.compile(r"[a-z0-9]+")

# 仅覆盖当前分析场景常见繁简差异，避免引入额外依赖。
_TRAD_TO_SIMP_TABLE = str.maketrans(
    {
        "兩": "两",
        "與": "与",
        "為": "为",
        "亞": "亚",
        "佈": "布",
        "來": "来",
        "個": "个",
        "價": "价",
        "內": "内",
        "關": "关",
        "協": "协",
        "區": "区",
        "升": "升",
        "參": "参",
        "台": "台",
        "號": "号",
        "圍": "围",
        "國": "国",
        "圖": "图",
        "壓": "压",
        "實": "实",
        "對": "对",
        "導": "导",
        "將": "将",
        "層": "层",
        "彈": "弹",
        "戰": "战",
        "應": "应",
        "數": "数",
        "會": "会",
        "條": "条",
        "機": "机",
        "權": "权",
        "檢": "检",
        "氣": "气",
        "灣": "湾",
        "發": "发",
        "監": "监",
        "礎": "础",
        "級": "级",
        "統": "统",
        "續": "续",
        "罰": "罚",
        "習": "习",
        "聲": "声",
        "聯": "联",
        "衝": "冲",
        "規": "规",
        "覺": "觉",
        "觀": "观",
        "觸": "触",
        "證": "证",
        "讓": "让",
        "該": "该",
        "說": "说",
        "調": "调",
        "護": "护",
        "轉": "转",
        "運": "运",
        "選": "选",
        "邊": "边",
        "釋": "释",
        "錄": "录",
        "際": "际",
        "電": "电",
        "體": "体",
        "點": "点",
    }
)


def normalize_zh_text(text: str) -> str:
    """统一文本用于关键词匹配（含繁转简）。"""
    if not text:
        return ""
    normalized = text.translate(_TRAD_TO_SIMP_TABLE).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def contains_keyword(text: str, keyword: str) -> bool:
    """判断关键词是否命中（自动做繁体兼容）。"""
    if not text or not keyword:
        return False
    return normalize_zh_text(keyword) in normalize_zh_text(text)


def contains_any_keyword(text: str, keywords: Iterable[str]) -> bool:
    """判断是否命中任意关键词。"""
    normalized_text = normalize_zh_text(text)
    for keyword in keywords:
        if normalize_zh_text(keyword) in normalized_text:
            return True
    return False


def extract_cjk_ngrams(text: str, min_n: int = 2, max_n: int = 3) -> Set[str]:
    """提取中文 n-gram，用于聚类相似度计算。"""
    normalized = normalize_zh_text(text)
    chars = [ch for ch in normalized if _CJK_RE.match(ch)]
    ngrams: Set[str] = set()
    length = len(chars)
    for n in range(min_n, max_n + 1):
        if length < n:
            continue
        for idx in range(length - n + 1):
            ngrams.add("".join(chars[idx : idx + n]))
    return ngrams


def extract_latin_tokens(text: str, stop_words: Set[str]) -> List[str]:
    """提取英文/数字 token。"""
    normalized = normalize_zh_text(text)
    tokens = _LATIN_TOKEN_RE.findall(normalized)
    return [token for token in tokens if len(token) > 2 and token not in stop_words]
