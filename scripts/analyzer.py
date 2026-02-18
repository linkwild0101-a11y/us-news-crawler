#!/usr/bin/env python3
"""
US-Monitor 热点分析器主流水线
协调聚类、LLM摘要、信号检测和数据库操作
"""

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client

from config.entity_config import (
    ENTITY_TYPES,
    PERSON_RULES,
    CONCEPT_RULES,
    DETECTION_PRIORITY,
    MIN_ENTITY_LENGTH,
)
from config.analysis_config import (
    MAX_ARTICLES_PER_RUN,
    MAX_LLM_CALLS,
    LLM_PROMPTS,
    SIGNAL_TYPES,
)
from scripts.llm_client import LLMClient
from scripts.clustering import cluster_news
from scripts.signal_detector import detect_all_signals, generate_dedupe_key

# 配置日志 - 同时输出到控制台和文件
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 清除现有的处理器
if logger.handlers:
    logger.handlers.clear()

# 创建格式器
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# 文件处理器
log_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(log_dir, "..", "logs", "analyzer.log")
os.makedirs(os.path.dirname(log_file), exist_ok=True)

file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class HotspotAnalyzer:
    """热点分析器主类"""

    def __init__(self):
        """初始化分析器"""
        # Supabase 客户端
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            raise ValueError(
                "缺少 Supabase 配置。请设置 SUPABASE_URL 和 SUPABASE_KEY 环境变量"
            )

        self.supabase = create_client(supabase_url, supabase_key)

        # LLM 客户端
        try:
            self.llm_client = LLMClient()
            logger.info("LLM 客户端初始化成功")
        except ValueError as e:
            logger.warning(f"LLM 客户端初始化失败: {e}")
            self.llm_client = None

        self.stats = {
            "articles_loaded": 0,
            "clusters_created": 0,
            "signals_detected": 0,
            "llm_calls": 0,
            "errors": 0,
        }

        # 分层分析配置
        self.hot_threshold = 3  # 热点阈值：文章数>=3
        self.concurrent_workers = 5  # 并发数
        self.cold_model = "qwen-flash"  # 冷门新闻使用轻量级模型
        self.hot_model = "qwen-plus"  # 热点新闻使用高质量模型

    def load_unanalyzed_articles(
        self, limit: Optional[int] = None, hours: Optional[int] = None
    ) -> List[Dict]:
        """
        加载未分析的文章

        Args:
            limit: 最大加载数量
            hours: 时间窗口（小时），None表示不限制时间

        Returns:
            文章列表
        """
        if limit is None:
            limit = MAX_ARTICLES_PER_RUN

        logger.info(
            f"加载未分析的文章 (限制: {limit}, 时间窗口: {'不限制' if hours is None else f'{hours}小时'})"
        )

        try:
            # 构建查询
            query = (
                self.supabase.table("articles")
                .select(
                    "id, title, content, url, category, source_id, published_at, fetched_at"
                )
                .is_("analyzed_at", "null")
            )

            # 如果时间窗口不为None，添加时间过滤
            if hours is not None:
                cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
                query = query.gte("fetched_at", cutoff_time)

            result = query.limit(limit).execute()

            articles = result.data
            self.stats["articles_loaded"] = len(articles)

            logger.info(f"加载了 {len(articles)} 篇未分析的文章")
            return articles

        except Exception as e:
            logger.error(f"加载文章失败: {e}")
            self.stats["errors"] += 1
            return []

    def generate_cluster_summary(self, cluster: Dict, depth: str = "full") -> Dict:
        """
        为聚类生成中文摘要（支持分层处理）

        Args:
            cluster: 聚类数据
            depth: 分析深度，"full"=完整分析，"shallow"=快速翻译

        Returns:
            摘要结果字典
        """
        total_start = time.time()
        cluster_id_short = cluster["cluster_id"][:8]
        article_count = cluster.get("article_count", 0)

        # 判断是否为热点
        is_hot = article_count >= self.hot_threshold

        logger.info(
            f"[CLUSTER_START] 开始处理聚类 | cluster_id: {cluster_id_short}... | "
            f"文章数: {article_count} | 类型: {'热点' if is_hot else '冷门'} | "
            f"深度: {depth} | 标题: {cluster['primary_title'][:50]}..."
        )

        if not self.llm_client:
            logger.warning("[CLUSTER_SKIP] LLM 客户端不可用，跳过摘要生成")
            return {
                "summary": cluster["primary_title"],
                "key_entities": [],
                "impact": "",
                "trend": "",
                "analysis_depth": depth,
                "is_hot": is_hot,
            }

        # 快速翻译模式（冷门新闻）
        if depth == "shallow":
            return self._quick_translate(cluster, is_hot)

        # 完整分析模式（热点新闻）
        try:
            # 准备提示词
            prep_start = time.time()
            content_samples = "\n".join(cluster["titles"][:3])  # 最多取3个标题作为样本

            prompt = LLM_PROMPTS["cluster_summary"].format(
                article_count=cluster["article_count"],
                sources=", ".join([t[:30] for t in cluster["titles"][:5]]),
                primary_title=cluster["primary_title"],
                content_samples=content_samples[:500],
            )
            prep_duration = time.time() - prep_start
            prompt_length = len(prompt)

            logger.info(
                f"[CLUSTER_PREP] 提示词准备完成 | cluster_id: {cluster_id_short}... | "
                f"耗时: {prep_duration:.3f}s | 提示词长度: {prompt_length}字符"
            )

            # 调用LLM
            llm_start = time.time()
            logger.info(
                f"[CLUSTER_LLM_CALL] 调用LLM | cluster_id: {cluster_id_short}..."
            )
            result = self.llm_client.summarize(prompt)
            llm_duration = time.time() - llm_start

            self.stats["llm_calls"] += 1
            total_duration = time.time() - total_start

            # 添加元数据
            result["analysis_depth"] = "full"
            result["is_hot"] = is_hot
            result["processing_time"] = total_duration

            # 检查结果是否成功
            if result.get("error"):
                logger.warning(
                    f"[CLUSTER_LLM_PARTIAL] LLM返回部分结果 | cluster_id: {cluster_id_short}... | "
                    f"LLM耗时: {llm_duration:.2f}s | 总耗时: {total_duration:.2f}s | "
                    f"错误: {result.get('error')}"
                )
            else:
                logger.info(
                    f"[CLUSTER_SUCCESS] 聚类处理成功 | cluster_id: {cluster_id_short}... | "
                    f"准备: {prep_duration:.3f}s | LLM: {llm_duration:.2f}s | "
                    f"总耗时: {total_duration:.2f}s | "
                    f"摘要长度: {len(result.get('summary', ''))}字符 | "
                    f"LLM调用次数: {self.stats['llm_calls']}"
                )

            return result

        except Exception as e:
            error_duration = time.time() - total_start
            logger.error(
                f"[CLUSTER_ERROR] 生成摘要失败 | cluster_id: {cluster_id_short}... | "
                f"耗时: {error_duration:.2f}s | 错误: {str(e)}"
            )
            self.stats["errors"] += 1
            return {
                "summary": cluster["primary_title"],
                "key_entities": [],
                "impact": "",
                "trend": "",
                "analysis_depth": "full",
                "is_hot": is_hot,
                "error": str(e),
            }

    def _quick_translate(self, cluster: Dict, is_hot: bool) -> Dict:
        """
        快速翻译模式（仅翻译标题，低成本）

        Args:
            cluster: 聚类数据
            is_hot: 是否为热点

        Returns:
            简化版结果字典
        """
        total_start = time.time()
        cluster_id_short = cluster["cluster_id"][:8]

        try:
            # 准备简化提示词（只翻译标题）
            title = cluster["primary_title"]

            # 使用纯文本翻译方法（避免 JSON 解析错误）
            llm_start = time.time()
            translated_title = self.llm_client.translate_text(
                title, model=self.cold_model
            )
            llm_duration = time.time() - llm_start

            self.stats["llm_calls"] += 1
            total_duration = time.time() - total_start

            logger.info(
                f"[CLUSTER_QUICK_DONE] 快速翻译完成 | cluster_id: {cluster_id_short}... | "
                f"耗时: {total_duration:.2f}s | 原文: {title[:50]}... | "
                f"译文: {translated_title[:50]}..."
            )

            return {
                "summary": translated_title,
                "key_entities": [],
                "impact": "",
                "trend": "",
                "analysis_depth": "shallow",
                "is_hot": is_hot,
                "processing_time": total_duration,
                "note": "点击进行深度分析",
            }

        except Exception as e:
            logger.error(
                f"[CLUSTER_QUICK_ERROR] 快速翻译失败 | cluster_id: {cluster_id_short}... | 错误: {str(e)}"
            )
            return {
                "summary": cluster["primary_title"],
                "key_entities": [],
                "impact": "",
                "trend": "",
                "analysis_depth": "shallow",
                "is_hot": is_hot,
                "error": str(e),
            }

    def _detect_entity_type(self, entity_name: str) -> str:
        """
        检测实体类型

        从配置文件读取关键词进行检测

        Args:
            entity_name: 实体名称

        Returns:
            实体类型: person/organization/location/event/concept
        """
        name = entity_name.strip()

        # 按优先级检测（event -> organization -> location -> person -> concept）
        for entity_type in DETECTION_PRIORITY:
            if entity_type == "concept":
                continue

            if entity_type == "person":
                # 人名特殊处理
                rules = PERSON_RULES
                name_len = len(name)
                min_len = rules["chinese_name_length"]["min"]
                max_len = rules["chinese_name_length"]["max"]

                # 中文人名长度判断
                if min_len <= name_len <= max_len:
                    return "person"

                # 英文人名判断
                indicators = rules["english_indicators"]
                if "contains_space" in indicators and " " in name:
                    return "person"
                if "title_capitalized" in indicators and name and name[0].isupper():
                    # 检查是否是常见英文名
                    common_names = rules.get("common_english_names", [])
                    name_parts = name.split()
                    for part in name_parts:
                        if part in common_names:
                            return "person"

                continue

            # 其他类型：从配置读取关键词
            config = ENTITY_TYPES.get(entity_type, {})
            keywords_config = config.get("keywords", {})

            # 合并中英文关键词
            all_keywords = []
            all_keywords.extend(keywords_config.get("zh", []))
            all_keywords.extend(keywords_config.get("en", []))

            # 检查关键词匹配
            for keyword in all_keywords:
                if keyword in name:
                    return entity_type

        # 默认为概念
        return "concept"

    def _update_entities(self, cluster_id: int, entities: List[str], category: str):
        """
        更新实体表和实体-聚类关联表

        Args:
            cluster_id: 聚类ID
            entities: 实体名称列表
            category: 分类
        """
        try:
            for entity_name in entities:
                if not entity_name or len(entity_name) < 2:
                    continue

                # 清理实体名称
                entity_name = entity_name.strip()

                # 自动检测实体类型
                entity_type = self._detect_entity_type(entity_name)

                # 检查实体是否已存在
                existing = (
                    self.supabase.table("entities")
                    .select("id, mention_count_total")
                    .eq("name", entity_name)
                    .execute()
                )

                if existing.data:
                    # 更新现有实体
                    entity_id = existing.data[0]["id"]
                    new_count = existing.data[0]["mention_count_total"] + 1

                    self.supabase.table("entities").update(
                        {
                            "last_seen": datetime.now().isoformat(),
                            "mention_count_total": new_count,
                            "category": category,
                        }
                    ).eq("id", entity_id).execute()
                else:
                    # 创建新实体
                    result = (
                        self.supabase.table("entities")
                        .insert(
                            {
                                "name": entity_name,
                                "entity_type": entity_type,
                                "category": category,
                                "mention_count_total": 1,
                            }
                        )
                        .execute()
                    )
                    entity_id = result.data[0]["id"]

                # 创建或更新实体-聚类关联
                try:
                    # 检查是否已存在
                    existing_rel = (
                        self.supabase.table("entity_cluster_relations")
                        .select("id")
                        .eq("entity_id", entity_id)
                        .eq("cluster_id", cluster_id)
                        .execute()
                    )

                    if not existing_rel.data:
                        self.supabase.table("entity_cluster_relations").insert(
                            {
                                "entity_id": entity_id,
                                "cluster_id": cluster_id,
                                "mention_count": 1,
                            }
                        ).execute()
                except Exception as e:
                    logger.debug(f"实体关联创建失败: {e}")

        except Exception as e:
            logger.error(f"更新实体失败: {e}")

    def save_analysis_results(self, clusters: List[Dict], signals: List[Dict]):
        """
        保存分析结果到数据库

        Args:
            clusters: 聚类列表
            signals: 信号列表
        """
        logger.info(f"保存分析结果: {len(clusters)} 个聚类, {len(signals)} 个信号")

        try:
            # 保存聚类
            for cluster in clusters:
                cluster_data = {
                    "cluster_key": cluster["cluster_id"],
                    "category": cluster["category"],
                    "primary_title": cluster["primary_title"],
                    "primary_link": "",  # 可以添加主文章链接
                    "summary": cluster.get("summary", {}).get(
                        "summary", cluster["primary_title"]
                    ),
                    "summary_en": cluster["primary_title"],
                    "article_count": cluster["article_count"],
                    "key_entities": json.dumps(
                        cluster.get("summary", {}).get("key_entities", [])
                    ),
                    "impact": cluster.get("summary", {}).get("impact", ""),
                    "trend": cluster.get("summary", {}).get("trend", ""),
                    "confidence": cluster.get("summary", {}).get("confidence", 0.8),
                    # 新增分层分析字段
                    "analysis_depth": cluster.get("summary", {}).get(
                        "analysis_depth", "full"
                    ),
                    "is_hot": cluster.get("summary", {}).get(
                        "is_hot", cluster["article_count"] >= 3
                    ),
                    "full_analysis_triggered": cluster.get("summary", {}).get(
                        "analysis_depth"
                    )
                    == "full",
                    "processing_time": cluster.get("summary", {}).get(
                        "processing_time", 0.0
                    ),
                }

                # 检查是否已存在
                existing = (
                    self.supabase.table("analysis_clusters")
                    .select("id")
                    .eq("cluster_key", cluster["cluster_id"])
                    .execute()
                )

                if existing.data:
                    # 更新
                    cluster_id = existing.data[0]["id"]
                    self.supabase.table("analysis_clusters").update(cluster_data).eq(
                        "id", cluster_id
                    ).execute()
                    logger.debug(f"更新聚类: {cluster['cluster_id'][:8]}...")
                else:
                    # 插入
                    result = (
                        self.supabase.table("analysis_clusters")
                        .insert(cluster_data)
                        .execute()
                    )
                    cluster_id = result.data[0]["id"]
                    logger.debug(f"插入聚类: {cluster['cluster_id'][:8]}...")

                    # 保存 article_analyses 关联
                    for article_id in cluster["article_ids"]:
                        try:
                            self.supabase.table("article_analyses").insert(
                                {"article_id": article_id, "cluster_id": cluster_id}
                            ).execute()
                        except Exception as e:
                            # 可能已存在，忽略错误
                            pass

                # 更新实体追踪（只对完整分析的聚类）
                if cluster.get("summary", {}).get("analysis_depth") == "full":
                    entities = cluster.get("summary", {}).get("key_entities", [])
                    if entities and cluster_id:
                        self._update_entities(cluster_id, entities, cluster["category"])

            # 保存信号
            for signal in signals:
                signal_data = {
                    "signal_type": signal["signal_type"],
                    "signal_key": signal["signal_id"],
                    "category": signal.get("category", "unknown"),
                    "confidence": signal["confidence"],
                    "description": signal["description"],
                    "description_en": signal.get("description_en", ""),
                    "rationale": json.dumps(signal.get("details", {})),
                    "data_source": "llm_analysis",
                    "expires_at": signal.get("expires_at"),
                    "created_at": signal.get("created_at"),
                }

                # 检查是否已存在
                existing = (
                    self.supabase.table("analysis_signals")
                    .select("id")
                    .eq("signal_key", signal["signal_id"])
                    .execute()
                )

                if not existing.data:
                    self.supabase.table("analysis_signals").insert(
                        signal_data
                    ).execute()
                    logger.debug(f"插入信号: {signal['signal_type']}")

            logger.info("分析结果保存成功")

        except Exception as e:
            logger.error(f"保存分析结果失败: {e}")
            self.stats["errors"] += 1
            raise

    def mark_articles_analyzed(self, article_ids: List[int]):
        """
        标记文章为已分析

        Args:
            article_ids: 文章ID列表
        """
        if not article_ids:
            return

        logger.info(f"标记 {len(article_ids)} 篇文章为已分析")

        try:
            now = datetime.now().isoformat()

            # 批量更新
            for article_id in article_ids:
                self.supabase.table("articles").update({"analyzed_at": now}).eq(
                    "id", article_id
                ).execute()

            logger.info("文章标记完成")

        except Exception as e:
            logger.error(f"标记文章失败: {e}")
            self.stats["errors"] += 1

    def run_analysis(self, limit: int = None, dry_run: bool = False):
        """
        运行完整的分析流程（支持分层处理和并发）

        Args:
            limit: 最大处理文章数
            dry_run: 试运行模式（不保存到数据库）
        """
        logger.info("=" * 60)
        logger.info("开始热点分析（智能分层 + 并发处理）")
        logger.info(
            f"配置: 热点阈值={self.hot_threshold}, 并发数={self.concurrent_workers}"
        )
        logger.info("=" * 60)

        start_time = datetime.now()

        # 1. 加载文章
        articles = self.load_unanalyzed_articles(limit=limit, hours=None)

        if not articles:
            logger.info("没有未分析的文章，跳过")
            return

        # 2. 聚类
        logger.info(f"开始聚类 {len(articles)} 篇文章...")
        clusters = cluster_news(articles)
        self.stats["clusters_created"] = len(clusters)
        logger.info(f"创建了 {len(clusters)} 个聚类")

        # 3. 分层：分离热点和冷门
        hot_clusters = [
            c for c in clusters if c.get("article_count", 0) >= self.hot_threshold
        ]
        cold_clusters = [
            c for c in clusters if c.get("article_count", 0) < self.hot_threshold
        ]

        logger.info(
            f"分层结果: 热点 {len(hot_clusters)} 个, 冷门 {len(cold_clusters)} 个"
        )

        # 4. 并发处理热点（完整分析）
        logger.info(f"开始并发处理 {len(hot_clusters)} 个热点聚类...")
        self._process_clusters_concurrent(hot_clusters, depth="full", dry_run=dry_run)

        # 5. 快速处理冷门（仅翻译）
        logger.info(f"开始快速处理 {len(cold_clusters)} 个冷门聚类...")
        self._process_clusters_concurrent(
            cold_clusters, depth="shallow", dry_run=dry_run
        )

        logger.info(
            f"成功处理 {len(hot_clusters) + len(cold_clusters)}/{len(clusters)} 个聚类"
        )

        # 6. 信号检测（只对热点聚类）
        logger.info("检测信号（仅热点聚类）...")
        signals = detect_all_signals(hot_clusters)
        self.stats["signals_detected"] = len(signals)

        if signals:
            logger.info(f"检测到 {len(signals)} 个信号:")
            for signal in signals[:5]:  # 只显示前5个
                icon = SIGNAL_TYPES.get(signal["signal_type"], {}).get("icon", "⚡")
                signal_name = SIGNAL_TYPES.get(signal["signal_type"], {}).get(
                    "name", signal["signal_type"]
                )
                logger.info(
                    f"  {icon} {signal_name}: 置信度 {signal['confidence']:.2f}"
                )

        # 7. 保存结果
        if not dry_run:
            logger.info("保存分析结果...")
            self.save_analysis_results(clusters, signals)

            # 8. 标记文章
            article_ids = [a["id"] for a in articles]
            self.mark_articles_analyzed(article_ids)
        else:
            logger.info("试运行模式: 跳过保存")

        # 统计
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info("=" * 60)
        logger.info("分析完成!")
        logger.info(f"耗时: {duration:.1f} 秒")
        logger.info(f"处理文章: {self.stats['articles_loaded']}")
        logger.info(f"创建聚类: {self.stats['clusters_created']}")
        logger.info(f"热点聚类: {len(hot_clusters)} (完整分析)")
        logger.info(f"冷门聚类: {len(cold_clusters)} (快速翻译)")
        logger.info(f"检测信号: {self.stats['signals_detected']}")
        logger.info(f"LLM调用: {self.stats['llm_calls']}")
        if self.llm_client:
            llm_stats = self.llm_client.get_stats()
            logger.info(f"预估成本: ${llm_stats['estimated_cost']:.4f}")
        logger.info("=" * 60)

    def _process_clusters_concurrent(
        self, clusters: List[Dict], depth: str = "full", dry_run: bool = False
    ):
        """
        并发处理聚类列表

        Args:
            clusters: 聚类列表
            depth: 分析深度，"full" 或 "shallow"
            dry_run: 试运行模式
        """
        if not clusters:
            return

        total = len(clusters)
        processed = 0
        errors = 0

        logger.info(
            f"启动 {self.concurrent_workers} 个并发 worker 处理 {total} 个聚类..."
        )

        with ThreadPoolExecutor(max_workers=self.concurrent_workers) as executor:
            # 提交所有任务
            future_to_cluster = {
                executor.submit(self.generate_cluster_summary, cluster, depth): cluster
                for cluster in clusters
            }

            # 处理完成的任务
            for future in as_completed(future_to_cluster):
                cluster = future_to_cluster[future]
                cluster_id_short = cluster.get("cluster_id", "")[:8]

                try:
                    result = future.result()
                    cluster["summary"] = result
                    processed += 1

                    # 每处理10个聚类保存一次进度
                    if not dry_run and processed % 10 == 0:
                        logger.info(
                            f"  并发进度: {processed}/{total} ({processed / total * 100:.1f}%)"
                        )

                except Exception as e:
                    logger.error(
                        f"  并发处理失败 {cluster_id_short}...: {str(e)[:100]}"
                    )
                    cluster["summary"] = {
                        "summary": cluster["primary_title"],
                        "error": str(e),
                        "analysis_depth": depth,
                    }
                    errors += 1

        logger.info(f"并发处理完成: 成功 {processed}, 失败 {errors}, 总计 {total}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="US-Monitor 热点分析器")
    parser.add_argument("--limit", type=int, default=None, help="最大处理文章数")
    parser.add_argument(
        "--dry-run", action="store_true", help="试运行模式（不保存到数据库）"
    )
    parser.add_argument("--hours", type=int, default=24, help="时间窗口（小时）")

    args = parser.parse_args()

    try:
        analyzer = HotspotAnalyzer()
        analyzer.run_analysis(limit=args.limit, dry_run=args.dry_run)
    except Exception as e:
        logger.error(f"分析器运行失败: {e}")
        raise


if __name__ == "__main__":
    main()
