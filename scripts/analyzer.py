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
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client

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

    def load_unanalyzed_articles(
        self, limit: int = None, hours: int = 24
    ) -> List[Dict]:
        """
        加载未分析的文章

        Args:
            limit: 最大加载数量
            hours: 时间窗口（小时）

        Returns:
            文章列表
        """
        if limit is None:
            limit = MAX_ARTICLES_PER_RUN

        # 计算时间窗口
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()

        logger.info(f"加载未分析的文章 (限制: {limit}, 时间窗口: {hours}小时)")

        try:
            # 查询未分析的文章
            result = (
                self.supabase.table("articles")
                .select(
                    "id, title, content, url, category, source_id, published_at, fetched_at"
                )
                .is_("analyzed_at", "null")
                .gte("fetched_at", cutoff_time)
                .limit(limit)
                .execute()
            )

            articles = result.data
            self.stats["articles_loaded"] = len(articles)

            logger.info(f"加载了 {len(articles)} 篇未分析的文章")
            return articles

        except Exception as e:
            logger.error(f"加载文章失败: {e}")
            self.stats["errors"] += 1
            return []

    def generate_cluster_summary(self, cluster: Dict) -> Dict:
        """
        为聚类生成中文摘要

        Args:
            cluster: 聚类数据

        Returns:
            摘要结果字典
        """
        total_start = time.time()
        cluster_id_short = cluster["cluster_id"][:8]

        logger.info(
            f"[CLUSTER_START] 开始处理聚类 | cluster_id: {cluster_id_short}... | "
            f"文章数: {cluster.get('article_count', 0)} | "
            f"标题: {cluster['primary_title'][:50]}..."
        )

        if not self.llm_client:
            logger.warning("[CLUSTER_SKIP] LLM 客户端不可用，跳过摘要生成")
            return {
                "summary": cluster["primary_title"],
                "key_entities": [],
                "impact": "",
                "trend": "",
            }

        # 检查是否超过LLM调用限制
        if self.stats["llm_calls"] >= MAX_LLM_CALLS:
            logger.warning(
                f"[CLUSTER_SKIP] 已达到LLM调用限制 ({MAX_LLM_CALLS})，跳过摘要生成"
            )
            return {
                "summary": cluster["primary_title"],
                "key_entities": [],
                "impact": "",
                "trend": "",
            }

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
                    f"LLM调用次数: {self.stats['llm_calls']}/{MAX_LLM_CALLS}"
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
            }

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
        运行完整的分析流程

        Args:
            limit: 最大处理文章数
            dry_run: 试运行模式（不保存到数据库）
        """
        logger.info("=" * 60)
        logger.info("开始热点分析")
        logger.info("=" * 60)

        start_time = datetime.now()

        # 1. 加载文章
        articles = self.load_unanalyzed_articles(limit)

        if not articles:
            logger.info("没有未分析的文章，跳过")
            return

        # 2. 聚类
        logger.info(f"开始聚类 {len(articles)} 篇文章...")
        clusters = cluster_news(articles)
        self.stats["clusters_created"] = len(clusters)
        logger.info(f"创建了 {len(clusters)} 个聚类")

        # 3. 生成摘要
        logger.info("生成聚类摘要...")
        processed_count = 0
        for i, cluster in enumerate(clusters):
            logger.info(
                f"  处理聚类 {i + 1}/{len(clusters)}: {cluster['primary_title'][:50]}..."
            )
            try:
                summary = self.generate_cluster_summary(cluster)
                cluster["summary"] = summary
                processed_count += 1
                # 每处理 10 个聚类，保存一次进度
                if not dry_run and processed_count % 10 == 0:
                    logger.info(f"  已处理 {processed_count} 个聚类，保存进度...")
                    # 只保存已处理的部分
                    self.save_analysis_results(clusters[:processed_count], [])
            except Exception as e:
                logger.error(f"  处理聚类 {i + 1} 失败: {e}")
                # 继续处理下一个
                cluster["summary"] = {
                    "summary": cluster["primary_title"],
                    "error": str(e),
                }

        logger.info(f"成功处理 {processed_count}/{len(clusters)} 个聚类")

        # 4. 信号检测
        logger.info("检测信号...")
        signals = detect_all_signals(clusters)
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

        # 5. 保存结果
        if not dry_run:
            logger.info("保存分析结果...")
            self.save_analysis_results(clusters, signals)

            # 6. 标记文章
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
        logger.info(f"检测信号: {self.stats['signals_detected']}")
        logger.info(f"LLM调用: {self.stats['llm_calls']}")
        if self.llm_client:
            llm_stats = self.llm_client.get_stats()
            logger.info(f"预估成本: ${llm_stats['estimated_cost']:.4f}")
        logger.info("=" * 60)


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
