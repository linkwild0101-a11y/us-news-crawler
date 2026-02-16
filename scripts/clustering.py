#!/usr/bin/env python3
"""
聚类引擎模块
使用Jaccard相似度进行新闻聚类
"""

import hashlib
import re
from typing import List, Dict, Set, Tuple
from collections import defaultdict
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.analysis_config import STOP_WORDS, SIMILARITY_THRESHOLD


def tokenize(text: str) -> Set[str]:
    """
    分词函数

    Args:
        text: 输入文本

    Returns:
        单词集合（已去停用词）
    """
    # 转换为小写
    text = text.lower()

    # 移除非字母数字字符，替换为空格
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # 分割成单词
    words = text.split()

    # 过滤停用词和短词
    tokens = set()
    for word in words:
        if len(word) > 2 and word not in STOP_WORDS:
            tokens.add(word)

    return tokens


def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """
    计算Jaccard相似度

    Jaccard(A, B) = |A ∩ B| / |A ∪ B|

    Args:
        set1: 第一个集合
        set2: 第二个集合

    Returns:
        相似度值（0.0 - 1.0）
    """
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    if union == 0:
        return 0.0

    return intersection / union


def generate_cluster_hash(titles: List[str]) -> str:
    """
    生成聚类哈希

    Args:
        titles: 聚类内所有标题列表

    Returns:
        16字符的MD5哈希
    """
    # 合并所有标题
    combined = " ".join(sorted(titles))
    # 计算MD5
    hash_obj = hashlib.md5(combined.encode("utf-8"))
    return hash_obj.hexdigest()[:16]


def cluster_news(
    articles: List[Dict], threshold: float = SIMILARITY_THRESHOLD
) -> List[Dict]:
    """
    主聚类函数

    使用倒排索引优化，将相似文章分组

    Args:
        articles: 文章列表，每个文章是dict包含 'id', 'title', 可选'category'
        threshold: 相似度阈值

    Returns:
        聚类列表，每个聚类包含：
        - cluster_id: 聚类唯一ID
        - articles: 文章ID列表
        - titles: 标题列表
        - primary_title: 主标题（最长的）
        - token_set: 合并后的token集合
        - category: 分类（如果有）
    """
    if not articles:
        return []

    # 1. 为每篇文章分词
    article_tokens = {}
    for article in articles:
        article_id = article["id"]
        title = article.get("title", "")
        tokens = tokenize(title)
        article_tokens[article_id] = {
            "article": article,
            "tokens": tokens,
            "title": title,
        }

    # 2. 构建倒排索引: token -> article_ids
    inverted_index = defaultdict(set)
    for article_id, data in article_tokens.items():
        for token in data["tokens"]:
            inverted_index[token].add(article_id)

    # 3. 初始化：每篇文章是一个独立聚类
    clusters = []
    processed = set()

    article_ids = list(article_tokens.keys())

    for i, article_id in enumerate(article_ids):
        if article_id in processed:
            continue

        # 新聚类
        current_cluster = {
            "article_ids": [article_id],
            "titles": [article_tokens[article_id]["title"]],
            "token_set": article_tokens[article_id]["tokens"].copy(),
            "categories": [
                article_tokens[article_id]["article"].get("category", "unknown")
            ],
        }

        # 使用倒排索引找到候选文章
        candidate_ids = set()
        for token in article_tokens[article_id]["tokens"]:
            candidate_ids.update(inverted_index[token])

        # 移除已处理的和当前文章
        candidate_ids -= processed
        candidate_ids.discard(article_id)

        # 与候选文章比较相似度
        for candidate_id in candidate_ids:
            if candidate_id in processed:
                continue

            candidate_tokens = article_tokens[candidate_id]["tokens"]
            similarity = jaccard_similarity(
                current_cluster["token_set"], candidate_tokens
            )

            if similarity >= threshold:
                # 合并到当前聚类
                current_cluster["article_ids"].append(candidate_id)
                current_cluster["titles"].append(article_tokens[candidate_id]["title"])
                current_cluster["token_set"].update(candidate_tokens)
                current_cluster["categories"].append(
                    article_tokens[candidate_id]["article"].get("category", "unknown")
                )
                processed.add(candidate_id)

        processed.add(article_id)
        clusters.append(current_cluster)

    # 4. 格式化输出
    result = []
    for cluster in clusters:
        # 找出最长的标题作为主标题
        primary_title = max(cluster["titles"], key=len)

        # 生成聚类ID
        cluster_id = generate_cluster_hash(cluster["titles"])

        # 确定主要分类（出现次数最多的）
        from collections import Counter

        category_counter = Counter(cluster["categories"])
        main_category = category_counter.most_common(1)[0][0]

        result.append(
            {
                "cluster_id": cluster_id,
                "article_ids": cluster["article_ids"],
                "titles": cluster["titles"],
                "primary_title": primary_title,
                "token_set": cluster["token_set"],
                "category": main_category,
                "article_count": len(cluster["article_ids"]),
            }
        )

    # 5. 按文章数量排序（多的在前）
    result.sort(key=lambda x: x["article_count"], reverse=True)

    return result


def find_similar_clusters(
    cluster1: Dict, cluster2: Dict, threshold: float = 0.3
) -> bool:
    """
    检查两个聚类是否相似（用于聚类合并）

    Args:
        cluster1: 第一个聚类
        cluster2: 第二个聚类
        threshold: 相似度阈值

    Returns:
        是否相似
    """
    similarity = jaccard_similarity(cluster1["token_set"], cluster2["token_set"])
    return similarity >= threshold


# 测试代码
if __name__ == "__main__":
    # 测试数据
    test_articles = [
        {"id": 1, "title": "Fed Raises Interest Rates by 0.25%", "category": "economy"},
        {
            "id": 2,
            "title": "Federal Reserve Increases Interest Rate",
            "category": "economy",
        },
        {
            "id": 3,
            "title": "Pentagon Announces New Defense Strategy",
            "category": "military",
        },
        {
            "id": 4,
            "title": "Defense Department Reveals Military Plan",
            "category": "military",
        },
        {
            "id": 5,
            "title": "Congress Passes New Tax Legislation",
            "category": "politics",
        },
        {"id": 6, "title": "Senate Approves Tax Bill", "category": "politics"},
        {"id": 7, "title": "Stock Market Hits Record High", "category": "economy"},
        {"id": 8, "title": "Dow Jones Reaches All-Time Peak", "category": "economy"},
    ]

    print("=" * 60)
    print("测试聚类引擎")
    print("=" * 60)

    # 测试分词
    print("\n1. 测试分词:")
    text = "The quick brown fox jumps over the lazy dog"
    tokens = tokenize(text)
    print(f"输入: '{text}'")
    print(f"输出: {sorted(tokens)}")

    # 测试Jaccard相似度
    print("\n2. 测试Jaccard相似度:")
    set1 = {"quick", "brown", "fox"}
    set2 = {"quick", "brown", "fox", "jumps"}
    set3 = {"cat", "dog", "bird"}

    print(f"set1: {set1}")
    print(f"set2: {set2}")
    print(f"相似度: {jaccard_similarity(set1, set2):.2f}")

    print(f"\nset1: {set1}")
    print(f"set3: {set3}")
    print(f"相似度: {jaccard_similarity(set1, set3):.2f}")

    # 测试聚类
    print("\n3. 测试聚类:")
    clusters = cluster_news(test_articles, threshold=0.3)

    print(f"创建了 {len(clusters)} 个聚类:\n")
    for i, cluster in enumerate(clusters, 1):
        print(f"聚类 {i}:")
        print(f"  ID: {cluster['cluster_id']}")
        print(f"  主标题: {cluster['primary_title']}")
        print(f"  文章数: {cluster['article_count']}")
        print(f"  分类: {cluster['category']}")
        print(f"  标题列表:")
        for title in cluster["titles"]:
            print(f"    - {title}")
        print()

    print("=" * 60)
    print("测试完成!")
    print("=" * 60)
