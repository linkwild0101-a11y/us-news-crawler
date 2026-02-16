#!/usr/bin/env python3
"""
SimHash去重模块
"""

from simhash import Simhash
from typing import List, Dict, Optional


def get_simhash(text: str) -> Optional[str]:
    """计算文本的SimHash指纹"""
    if not text:
        return None
    text = text[:1000].lower()
    return str(Simhash(text).value)


def hamming_distance(hash1: str, hash2: str) -> int:
    """计算两个SimHash的汉明距离"""
    try:
        h1 = int(hash1)
        h2 = int(hash2)
        x = (h1 ^ h2) & ((1 << 64) - 1)
        distance = 0
        while x:
            distance += 1
            x &= x - 1
        return distance
    except (ValueError, TypeError):
        return 100


def find_similar_articles(
    simhash: str, articles: List[Dict], threshold: int = 3
) -> List[Dict]:
    """查找相似文章"""
    duplicates = []
    for article in articles:
        if article.get("simhash"):
            distance = hamming_distance(simhash, article["simhash"])
            if distance <= threshold:
                duplicates.append(
                    {"id": article["id"], "url": article["url"], "distance": distance}
                )
    return duplicates


def is_duplicate(
    new_simhash: str, existing_hashes: List[str], threshold: int = 3
) -> bool:
    """检查是否重复"""
    for existing_hash in existing_hashes:
        if hamming_distance(new_simhash, existing_hash) <= threshold:
            return True
    return False
