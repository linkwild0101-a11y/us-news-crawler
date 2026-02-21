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
from itertools import combinations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client

from config.analysis_config import (
    MAX_ARTICLES_PER_RUN,
    LLM_PROMPTS,
    SIGNAL_TYPES,
)
from scripts.entity_classification import (
    extract_entity_names,
    merge_entity_metadata,
    normalize_entity_mentions,
    normalize_relation_items,
    normalize_entity_type,
)
from scripts.llm_client import LLMClient
from scripts.clustering import cluster_news
from scripts.signal_detector import detect_all_signals, detect_watchlist_signals

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

        # 分析配置
        self.hot_threshold = 3  # 信号检测目标阈值：文章数>=3
        self.concurrent_workers = 10  # 完整分析并发数
        self.analysis_model = "qwen-plus"  # 统一使用完整分析模型
        self.signal_related_events_limit = 5  # 每个信号最多关联事件数
        self.signal_llm_explain_max = 30  # 每轮最多用LLM解释的信号数量
        self.signal_llm_min_confidence = 0.6  # LLM解释最低置信度
        self.cluster_reuse_hours = 24  # 聚类结果复用窗口（小时）
        self.db_max_retries = 4  # DB瞬时故障重试次数
        self.db_retry_base_seconds = 1.0  # DB重试基础退避
        self.db_batch_size = 200  # 批量写库默认分片
        self.enable_entity_relations = True  # 是否提取实体关系
        self.entity_relation_min_confidence = 0.55
        self.entity_relation_max_clusters = 40
        self._signal_extended_columns_supported: Optional[bool] = None

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
            # Supabase/PostgREST 常见单次返回上限为 1000，这里分页读取。
            articles: List[Dict] = []
            page_size = min(1000, limit)
            offset = 0

            while len(articles) < limit:
                query = (
                    self.supabase.table("articles")
                    .select(
                        "id, title, content, url, category, source_id, published_at, fetched_at"
                    )
                    .is_("analyzed_at", "null")
                    .order("id")
                    .range(offset, offset + page_size - 1)
                )

                # 如果时间窗口不为None，添加时间过滤
                if hours is not None:
                    cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
                    query = query.gte("fetched_at", cutoff_time)

                result = query.execute()
                batch = result.data or []
                if not batch:
                    break

                articles.extend(batch)
                if len(batch) < page_size:
                    break

                offset += page_size
                remaining = limit - len(articles)
                page_size = min(1000, remaining)

            articles = articles[:limit]
            self.stats["articles_loaded"] = len(articles)

            logger.info(f"加载了 {len(articles)} 篇未分析的文章")
            return articles

        except Exception as e:
            logger.error(f"加载文章失败: {e}")
            self.stats["errors"] += 1
            return []

    def _parse_json_array_field(self, value: Any) -> List[Any]:
        """解析 JSON 数组字段，兼容字符串/列表两种格式"""
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        return []

    def _is_transient_db_error(self, error: Exception) -> bool:
        """判断是否属于可重试的数据库/网关瞬时错误"""
        message = str(error).lower()
        transient_flags = [
            "code': 500",
            "code': 502",
            "code': 503",
            "code': 504",
            "internal server error",
            "cloudflare",
            "json could not be generated",
            "timeout",
            "temporarily",
        ]
        return any(flag in message for flag in transient_flags)

    def _execute_with_retry(self, operation_name: str, operation):
        """执行数据库操作并自动重试瞬时错误"""
        last_error: Optional[Exception] = None
        for attempt in range(1, self.db_max_retries + 1):
            try:
                return operation()
            except Exception as e:
                last_error = e
                is_transient = self._is_transient_db_error(e)
                if not is_transient or attempt == self.db_max_retries:
                    raise

                delay = self.db_retry_base_seconds * (2 ** (attempt - 1))
                logger.warning(
                    f"[DB_RETRY] {operation_name} 失败，{delay:.1f}s后重试 "
                    f"({attempt}/{self.db_max_retries}) | 错误: {str(e)[:120]}"
                )
                time.sleep(delay)

        if last_error:
            raise last_error
        raise RuntimeError(f"{operation_name} 执行失败")

    def _reuse_existing_cluster_summaries(self, clusters: List[Dict]) -> int:
        """复用已有聚类摘要，减少重复 LLM 调用"""
        if not clusters:
            return 0

        cluster_keys = list(
            dict.fromkeys(
                [
                    cluster.get("cluster_id")
                    for cluster in clusters
                    if cluster.get("cluster_id")
                ]
            )
        )
        if not cluster_keys:
            return 0

        cutoff = (datetime.now() - timedelta(hours=self.cluster_reuse_hours)).isoformat()
        existing_map: Dict[str, Dict[str, Any]] = {}
        batch_size = 200

        try:
            for i in range(0, len(cluster_keys), batch_size):
                batch_keys = cluster_keys[i : i + batch_size]
                rows = (
                    self.supabase.table("analysis_clusters")
                    .select(
                        "cluster_key, summary, impact, trend, confidence, key_entities, "
                        "analysis_depth, is_hot, processing_time, primary_link, updated_at"
                    )
                    .in_("cluster_key", batch_keys)
                    .gte("updated_at", cutoff)
                    .execute()
                )
                for row in rows.data or []:
                    existing_map[row["cluster_key"]] = row
        except Exception as e:
            logger.warning(f"复用聚类摘要失败，回退为全量分析: {e}")
            return 0

        reused_count = 0
        for cluster in clusters:
            cached = existing_map.get(cluster.get("cluster_id"))
            if not cached:
                continue

            cached_key_entities = self._parse_json_array_field(cached.get("key_entities"))
            cluster["summary"] = {
                "summary": cached.get("summary", cluster.get("primary_title", "")),
                "key_entities": cached_key_entities,
                "entity_mentions": [],
                "impact": cached.get("impact", ""),
                "trend": cached.get("trend", ""),
                "confidence": cached.get("confidence", 0.8),
                "analysis_depth": cached.get("analysis_depth", "full"),
                "is_hot": bool(cached.get("is_hot", False)),
                "processing_time": cached.get("processing_time", 0.0),
                "model_name": "cache_reuse",
                "prompt_version": "cluster_summary_v2",
            }

            if not cluster.get("primary_link") and cached.get("primary_link"):
                cluster["primary_link"] = cached.get("primary_link")

            reused_count += 1

        return reused_count

    def generate_cluster_summary(self, cluster: Dict) -> Dict:
        """
        为聚类生成中文摘要（完整分析）

        Args:
            cluster: 聚类数据

        Returns:
            摘要结果字典
        """
        total_start = time.time()
        cluster_id_short = cluster["cluster_id"][:8]
        article_count = cluster.get("article_count", 0)

        # 是否属于信号检测目标聚类
        is_hot = article_count >= self.hot_threshold

        logger.info(
            f"[CLUSTER_START] 开始处理聚类 | cluster_id: {cluster_id_short}... | "
            f"文章数: {article_count} | 深度: full | "
            f"信号目标: {'是' if is_hot else '否'} | 标题: {cluster['primary_title'][:50]}..."
        )

        if not self.llm_client:
            logger.warning("[CLUSTER_SKIP] LLM 客户端不可用，跳过摘要生成")
            return {
                "summary": cluster["primary_title"],
                "key_entities": [],
                "entity_mentions": [],
                "impact": "",
                "trend": "",
                "analysis_depth": "full",
                "is_hot": is_hot,
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
            used_model = self.analysis_model
            result = self.llm_client.summarize(prompt, model=used_model)
            llm_duration = time.time() - llm_start

            self.stats["llm_calls"] += 1
            total_duration = time.time() - total_start

            entity_mentions = normalize_entity_mentions(
                result.get("entity_mentions") or result.get("key_entities", [])
            )

            # 添加元数据
            result["entity_mentions"] = entity_mentions
            result["key_entities"] = extract_entity_names(entity_mentions)
            result["analysis_depth"] = "full"
            result["is_hot"] = is_hot
            result["processing_time"] = total_duration
            result["model_name"] = used_model
            result["prompt_version"] = "cluster_summary_v2"

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
                "entity_mentions": [],
                "impact": "",
                "trend": "",
                "analysis_depth": "full",
                "is_hot": is_hot,
                "error": str(e),
            }

    def _build_signal_related_events(
        self, signal: Dict, cluster_lookup: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """根据信号内容提取关联事件（聚类）"""
        cluster_keys: List[str] = []
        affected_clusters = signal.get("affected_clusters", [])
        if isinstance(affected_clusters, list):
            cluster_keys.extend([str(item) for item in affected_clusters if item])

        # 兼容增强信号中直接写 cluster_id=cluster_key 的场景
        cluster_id_value = signal.get("cluster_id")
        if isinstance(cluster_id_value, str) and cluster_id_value:
            cluster_keys.append(cluster_id_value)

        unique_cluster_keys = list(dict.fromkeys(cluster_keys))
        related_events: List[Dict[str, Any]] = []

        for cluster_key in unique_cluster_keys[: self.signal_related_events_limit]:
            event = cluster_lookup.get(cluster_key)
            if not event:
                continue
            related_events.append(
                {
                    "cluster_id": event["cluster_id"],
                    "cluster_key": cluster_key,
                    "title": event["primary_title"],
                    "summary": event["summary"],
                    "article_count": event["article_count"],
                    "category": event["category"],
                }
            )

        return related_events

    def _build_signal_rationale_fallback(
        self, signal: Dict, related_events: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """构建无 LLM 时的信号解释兜底文案"""
        signal_type = signal.get("signal_type", "unknown")
        confidence = float(signal.get("confidence", 0) or 0)
        description = signal.get("description", "")
        details = signal.get("details", {}) or {}

        if signal_type == "velocity_spike":
            cluster_count = details.get("cluster_count", "N/A")
            threshold = details.get("threshold", "N/A")
            importance = f"短时间聚类数量达到 {cluster_count}，超过阈值 {threshold}。"
            meaning = "说明新闻热度上升，事件可能进入快速发酵阶段。"
            actionable = "建议优先跟踪新增聚类并观察扩散速度。"
        elif signal_type == "convergence":
            source_count = details.get("source_count", "N/A")
            source_types = details.get("source_types", [])
            source_text = (
                ", ".join(source_types) if isinstance(source_types, list) else "N/A"
            )
            importance = f"同一事件被 {source_count} 类来源报道（{source_text}）。"
            meaning = "说明可验证性增强，单一来源偏差风险下降。"
            actionable = "建议比对各来源差异并核实关键事实。"
        elif signal_type == "triangulation":
            importance = "事件出现关键来源交叉验证，可信度通常较高。"
            meaning = "说明该事件具备更强的真实性与持续关注价值。"
            actionable = "建议将其纳入重点预警清单。"
        elif signal_type == "hotspot_escalation":
            level = details.get("escalation_level", "unknown")
            score = details.get("total_score", "N/A")
            importance = f"热点升级等级为 {level}，综合评分 {score}。"
            meaning = "说明事件影响面和传播势能正在抬升。"
            actionable = "建议结合实体趋势做连续复核。"
        elif signal_type == "watchlist_alert":
            level = signal.get("alert_level") or details.get("alert_level", "L1")
            risk_score = signal.get("risk_score") or details.get("risk_score", 0)
            sentinel_name = details.get("sentinel_name", signal.get("name", "场景哨兵"))
            importance = (
                f"{sentinel_name} 触发 {level} 告警，风险分 "
                f"{float(risk_score or 0):.2f}。"
            )
            trigger_reasons = details.get("trigger_reasons", [])
            if isinstance(trigger_reasons, list) and trigger_reasons:
                meaning = f"触发依据: {'；'.join([str(x) for x in trigger_reasons[:3]])}"
            else:
                meaning = "说明目标场景出现多维信号收敛，需重点复核。"
            actionable = details.get("suggested_action", "建议值班分析员尽快复核证据。")
        else:
            importance = description or "系统检测到异常信号。"
            meaning = description or "说明该事件存在进一步关注价值。"
            actionable = "建议结合上下文做人工复核。"

        if related_events:
            top_titles = [event["title"] for event in related_events[:3]]
            importance = f"{importance} 关联事件: {'；'.join(top_titles)}"

        return {
            "importance": importance,
            "meaning": meaning,
            "actionable": actionable,
            "confidence_reason": f"当前系统置信度评分为 {confidence:.2f}。",
            "generated_by": "rule_fallback",
        }

    def _generate_signal_rationale(
        self, signal: Dict, related_events: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """使用 LLM 生成信号解释"""
        fallback = self._build_signal_rationale_fallback(signal, related_events)
        if not self.llm_client or not related_events:
            return fallback

        try:
            event_lines = []
            for event in related_events[:3]:
                summary = (event.get("summary") or "").replace("\n", " ").strip()
                event_lines.append(
                    f"- {event['title']}（{event['article_count']}篇，{event['category']}）: {summary[:180]}"
                )
            cluster_summary = (
                "\n".join(event_lines) if event_lines else signal.get("description", "")
            )
            article_count = sum(
                int(event.get("article_count", 0) or 0) for event in related_events
            )

            prompt = LLM_PROMPTS["signal_rationale"].format(
                signal_type=signal.get("signal_type", "unknown"),
                confidence=round(float(signal.get("confidence", 0) or 0), 2),
                article_count=article_count,
                cluster_summary=cluster_summary[:1200],
            )

            result = self.llm_client.summarize(prompt, model=self.analysis_model)
            self.stats["llm_calls"] += 1
            if not isinstance(result, dict) or result.get("error"):
                return fallback

            importance = (
                str(result.get("importance", "")).strip() or fallback["importance"]
            )
            meaning = str(result.get("meaning", "")).strip() or fallback["meaning"]
            actionable = (
                str(result.get("actionable", "")).strip() or fallback["actionable"]
            )
            confidence_reason = (
                str(result.get("confidence_reason", "")).strip()
                or fallback["confidence_reason"]
            )

            return {
                "importance": importance,
                "meaning": meaning,
                "actionable": actionable,
                "confidence_reason": confidence_reason,
                "generated_by": "llm",
            }
        except Exception as e:
            logger.warning(f"[SIGNAL_RATIONALE_FALLBACK] LLM信号解释失败: {e}")
            return fallback

    def _update_entities_bulk(self, entity_tasks: List[Dict[str, Any]]):
        """批量更新实体与实体-聚类关联，减少数据库往返"""
        if not entity_tasks:
            return

        try:
            now_iso = datetime.now().isoformat()
            entity_agg: Dict[Tuple[str, str], Dict[str, Any]] = {}
            relation_counts: Dict[Tuple[str, str, int], int] = {}

            for task in entity_tasks:
                cluster_id = int(task["cluster_id"])
                category = task.get("category", "unknown")
                model_name = task.get("model_name", "")
                prompt_version = task.get("prompt_version", "")
                normalized_entities = normalize_entity_mentions(task.get("entities", []))

                for entity in normalized_entities:
                    key = (entity["canonical_name"], entity["entity_type"])
                    agg = entity_agg.setdefault(
                        key,
                        {
                            "count": 0,
                            "category": category,
                            "entity": entity,
                            "model_name": model_name,
                            "prompt_version": prompt_version,
                            "metadata": {},
                        },
                    )
                    agg["count"] += 1
                    agg["entity"] = entity
                    if category:
                        agg["category"] = category
                    if model_name:
                        agg["model_name"] = model_name
                    if prompt_version:
                        agg["prompt_version"] = prompt_version
                    agg["metadata"] = merge_entity_metadata(
                        existing_metadata=agg.get("metadata"),
                        entity=entity,
                        model_name=agg.get("model_name", ""),
                        prompt_version=agg.get("prompt_version", ""),
                    )

                    relation_key = (key[0], key[1], cluster_id)
                    relation_counts[relation_key] = relation_counts.get(relation_key, 0) + 1

            if not entity_agg:
                return

            names_by_type: Dict[str, List[str]] = {}
            for name, entity_type in entity_agg.keys():
                names_by_type.setdefault(entity_type, []).append(name)

            existing_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
            name_query_batch_size = 100
            for entity_type, names in names_by_type.items():
                unique_names = list(dict.fromkeys(names))
                for i in range(0, len(unique_names), name_query_batch_size):
                    batch_names = unique_names[i : i + name_query_batch_size]
                    existing_rows = self._execute_with_retry(
                        "load_existing_entities",
                        lambda et=entity_type, bn=batch_names: (
                            self.supabase.table("entities")
                            .select(
                                "id, name, entity_type, mention_count_total, metadata, category"
                            )
                            .eq("entity_type", et)
                            .in_("name", bn)
                            .execute()
                        ),
                    )
                    for row in existing_rows.data or []:
                        existing_map[(row["name"], row["entity_type"])] = row

            upsert_rows: List[Dict[str, Any]] = []
            for key, agg in entity_agg.items():
                name, entity_type = key
                existing = existing_map.get(key)
                metadata = agg.get("metadata", {})

                if existing:
                    mention_total = (existing.get("mention_count_total") or 0) + agg["count"]
                    metadata = merge_entity_metadata(
                        existing_metadata=existing.get("metadata"),
                        entity=agg["entity"],
                        model_name=agg.get("model_name", ""),
                        prompt_version=agg.get("prompt_version", ""),
                    )
                else:
                    mention_total = agg["count"]

                upsert_rows.append(
                    {
                        "name": name,
                        "entity_type": entity_type,
                        "category": agg.get("category", "unknown"),
                        "last_seen": now_iso,
                        "mention_count_total": mention_total,
                        "metadata": metadata,
                    }
                )

            for i in range(0, len(upsert_rows), self.db_batch_size):
                batch_rows = upsert_rows[i : i + self.db_batch_size]
                self._execute_with_retry(
                    "upsert_entities_batch",
                    lambda rows=batch_rows: (
                        self.supabase.table("entities")
                        .upsert(rows, on_conflict="name,entity_type")
                        .execute()
                    ),
                )

            entity_id_map: Dict[Tuple[str, str], int] = {}
            for entity_type, names in names_by_type.items():
                unique_names = list(dict.fromkeys(names))
                for i in range(0, len(unique_names), name_query_batch_size):
                    batch_names = unique_names[i : i + name_query_batch_size]
                    rows = self._execute_with_retry(
                        "load_entity_ids_after_upsert",
                        lambda et=entity_type, bn=batch_names: (
                            self.supabase.table("entities")
                            .select("id, name, entity_type")
                            .eq("entity_type", et)
                            .in_("name", bn)
                            .execute()
                        ),
                    )
                    for row in rows.data or []:
                        entity_id_map[(row["name"], row["entity_type"])] = row["id"]

            relation_rows: List[Dict[str, Any]] = []
            for relation_key, mention_count in relation_counts.items():
                name, entity_type, cluster_id = relation_key
                entity_id = entity_id_map.get((name, entity_type))
                if not entity_id:
                    continue
                relation_rows.append(
                    {
                        "entity_id": entity_id,
                        "cluster_id": cluster_id,
                        "mention_count": mention_count,
                    }
                )

            for i in range(0, len(relation_rows), self.db_batch_size):
                batch_rows = relation_rows[i : i + self.db_batch_size]
                self._execute_with_retry(
                    "upsert_entity_cluster_relations_batch",
                    lambda rows=batch_rows: (
                        self.supabase.table("entity_cluster_relations")
                        .upsert(rows, on_conflict="entity_id,cluster_id")
                        .execute()
                    ),
                )

            logger.info(
                f"[ENTITIES_BULK_UPDATED] 聚类: {len(entity_tasks)} | "
                f"实体: {len(entity_agg)} | 关联: {len(relation_rows)}"
            )
        except Exception as e:
            logger.error(f"批量更新实体失败: {e}")

    def _supports_extended_signal_columns(self) -> bool:
        """检测 analysis_signals 是否已完成哨兵字段迁移。"""
        if self._signal_extended_columns_supported is not None:
            return self._signal_extended_columns_supported

        try:
            self.supabase.table("analysis_signals").select("id,sentinel_id").limit(1).execute()
            self._signal_extended_columns_supported = True
        except Exception:
            self._signal_extended_columns_supported = False
            logger.info(
                "[SIGNAL_SCHEMA_FALLBACK] analysis_signals 未包含哨兵扩展字段，"
                "将仅写入 rationale.details"
            )
        return self._signal_extended_columns_supported

    def _extract_cluster_relations(self, cluster: Dict[str, Any], summary: Dict[str, Any]) -> List[Dict]:
        """提取聚类内实体关系（LLM优先，失败回退规则法）。"""
        entity_mentions = normalize_entity_mentions(
            summary.get("entity_mentions") or summary.get("key_entities", [])
        )
        entities = []
        for entity in entity_mentions:
            canonical_name = str(entity.get("canonical_name") or "").strip()
            if not canonical_name:
                continue
            entities.append(
                {
                    "name": canonical_name,
                    "entity_type": normalize_entity_type(entity.get("entity_type")),
                }
            )
        if len(entities) < 2:
            return []

        relations: List[Dict[str, Any]] = []
        if self.llm_client and cluster.get("article_count", 0) >= self.hot_threshold:
            title_samples = "\n".join(
                [str(title) for title in cluster.get("titles", [])[:5] if title]
            )
            known_entities = ", ".join([item["name"] for item in entities[:12]])
            prompt = LLM_PROMPTS["entity_relation_extraction"].format(
                primary_title=cluster.get("primary_title", ""),
                title_samples=title_samples[:600],
                cluster_summary=str(summary.get("summary", ""))[:1000],
                known_entities=known_entities[:400],
            )
            try:
                result = self.llm_client.summarize(prompt, model=self.analysis_model)
                self.stats["llm_calls"] += 1
                if isinstance(result, dict) and not result.get("error"):
                    relations = normalize_relation_items(result.get("relations", []))
            except Exception as e:
                logger.warning(f"LLM关系提取失败，回退规则法: {str(e)[:100]}")

        if relations:
            return relations

        # 规则回退：实体共现关系（用于保证基础覆盖）
        dedup_entities: List[Dict[str, str]] = []
        seen_pairs = set()
        for item in entities:
            key = (item["name"], item["entity_type"])
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            dedup_entities.append(item)

        fallback_relations: List[Dict[str, Any]] = []
        for left, right in list(combinations(dedup_entities[:8], 2))[:12]:
            fallback_relations.append(
                {
                    "from": left["name"],
                    "from_type": left["entity_type"],
                    "to": right["name"],
                    "to_type": right["entity_type"],
                    "description": "在同一新闻聚类中被共同提及",
                    "confidence": 0.58,
                }
            )
        return fallback_relations

    def _update_entity_relations_bulk(self, relation_tasks: List[Dict[str, Any]]):
        """批量写入实体关系与关系证据。"""
        if not relation_tasks:
            return

        try:
            now_iso = datetime.now().isoformat()
            entity_keys = set()
            for task in relation_tasks:
                for relation in task.get("relations", []):
                    from_name = str(relation.get("from") or "").strip()
                    to_name = str(relation.get("to") or "").strip()
                    from_type = normalize_entity_type(relation.get("from_type"))
                    to_type = normalize_entity_type(relation.get("to_type"))
                    if from_name:
                        entity_keys.add((from_name, from_type, task.get("category", "unknown")))
                    if to_name:
                        entity_keys.add((to_name, to_type, task.get("category", "unknown")))

            if not entity_keys:
                return

            names_by_type: Dict[str, List[str]] = {}
            category_map: Dict[Tuple[str, str], str] = {}
            for name, entity_type, category in entity_keys:
                names_by_type.setdefault(entity_type, []).append(name)
                category_map[(name, entity_type)] = category

            entity_id_map: Dict[Tuple[str, str], int] = {}
            query_batch = 200
            for entity_type, names in names_by_type.items():
                unique_names = list(dict.fromkeys(names))
                for i in range(0, len(unique_names), query_batch):
                    batch_names = unique_names[i : i + query_batch]
                    rows = self._execute_with_retry(
                        "load_entities_for_relations",
                        lambda et=entity_type, bn=batch_names: (
                            self.supabase.table("entities")
                            .select("id, name, entity_type")
                            .eq("entity_type", et)
                            .in_("name", bn)
                            .execute()
                        ),
                    )
                    for row in rows.data or []:
                        entity_id_map[(row["name"], row["entity_type"])] = row["id"]

            missing_rows = []
            for name, entity_type, _ in entity_keys:
                if (name, entity_type) in entity_id_map:
                    continue
                missing_rows.append(
                    {
                        "name": name,
                        "entity_type": entity_type,
                        "category": category_map.get((name, entity_type), "unknown"),
                        "last_seen": now_iso,
                        "mention_count_total": 0,
                    }
                )

            for i in range(0, len(missing_rows), self.db_batch_size):
                batch_rows = missing_rows[i : i + self.db_batch_size]
                self._execute_with_retry(
                    "upsert_entities_for_relations",
                    lambda rows=batch_rows: (
                        self.supabase.table("entities")
                        .upsert(rows, on_conflict="name,entity_type")
                        .execute()
                    ),
                )

            # 补齐缺失实体ID
            for entity_type, names in names_by_type.items():
                unique_names = list(dict.fromkeys(names))
                for i in range(0, len(unique_names), query_batch):
                    batch_names = unique_names[i : i + query_batch]
                    rows = self._execute_with_retry(
                        "reload_entities_for_relations",
                        lambda et=entity_type, bn=batch_names: (
                            self.supabase.table("entities")
                            .select("id, name, entity_type")
                            .eq("entity_type", et)
                            .in_("name", bn)
                            .execute()
                        ),
                    )
                    for row in rows.data or []:
                        entity_id_map[(row["name"], row["entity_type"])] = row["id"]

            relation_agg: Dict[Tuple[int, int, str], Dict[str, Any]] = {}
            for task in relation_tasks:
                article_ids = [
                    int(article_id)
                    for article_id in task.get("article_ids", [])
                    if isinstance(article_id, int)
                ]
                for relation in task.get("relations", []):
                    from_name = str(relation.get("from") or "").strip()
                    to_name = str(relation.get("to") or "").strip()
                    relation_text = str(relation.get("description") or "").strip()
                    if not from_name or not to_name or not relation_text:
                        continue
                    from_type = normalize_entity_type(relation.get("from_type"))
                    to_type = normalize_entity_type(relation.get("to_type"))
                    from_id = entity_id_map.get((from_name, from_type))
                    to_id = entity_id_map.get((to_name, to_type))
                    if not from_id or not to_id or from_id == to_id:
                        continue
                    key = (from_id, to_id, relation_text[:180])
                    agg = relation_agg.setdefault(
                        key,
                        {
                            "entity1_id": from_id,
                            "entity2_id": to_id,
                            "relation_text": relation_text[:180],
                            "confidence": 0.0,
                            "source_article_ids": set(),
                            "first_seen": now_iso,
                            "last_seen": now_iso,
                        },
                    )
                    agg["confidence"] = max(
                        float(agg["confidence"]),
                        float(relation.get("confidence", 0.6) or 0.6),
                    )
                    agg["source_article_ids"].update(article_ids)
                    agg["last_seen"] = now_iso

            if not relation_agg:
                return

            relation_rows = []
            for item in relation_agg.values():
                article_ids = sorted([aid for aid in item["source_article_ids"] if aid > 0])
                relation_rows.append(
                    {
                        "entity1_id": item["entity1_id"],
                        "entity2_id": item["entity2_id"],
                        "relation_text": item["relation_text"],
                        "confidence": round(min(1.0, max(0.0, item["confidence"])), 4),
                        "source_article_ids": article_ids,
                        "source_count": len(article_ids),
                        "first_seen": item["first_seen"],
                        "last_seen": item["last_seen"],
                    }
                )

            relation_id_map: Dict[Tuple[int, int, str], int] = {}
            for i in range(0, len(relation_rows), self.db_batch_size):
                batch_rows = relation_rows[i : i + self.db_batch_size]
                upsert_result = self._execute_with_retry(
                    "upsert_entity_relations_batch",
                    lambda rows=batch_rows: (
                        self.supabase.table("entity_relations")
                        .upsert(rows, on_conflict="entity1_id,entity2_id,relation_text")
                        .execute()
                    ),
                )
                for row in upsert_result.data or []:
                    relation_key = (
                        row.get("entity1_id"),
                        row.get("entity2_id"),
                        row.get("relation_text"),
                    )
                    relation_id = row.get("id")
                    if relation_key[0] and relation_key[1] and relation_key[2] and relation_id:
                        relation_id_map[relation_key] = relation_id

            evidence_rows = []
            for row in relation_rows:
                relation_key = (
                    row["entity1_id"],
                    row["entity2_id"],
                    row["relation_text"],
                )
                relation_id = relation_id_map.get(relation_key)
                if not relation_id:
                    continue
                for article_id in row.get("source_article_ids", []):
                    evidence_rows.append(
                        {
                            "relation_id": relation_id,
                            "article_id": article_id,
                            "extracted_at": now_iso,
                        }
                    )

            for i in range(0, len(evidence_rows), self.db_batch_size):
                batch_rows = evidence_rows[i : i + self.db_batch_size]
                self._execute_with_retry(
                    "upsert_relation_evidence_batch",
                    lambda rows=batch_rows: (
                        self.supabase.table("relation_evidence")
                        .upsert(rows, on_conflict="relation_id,article_id")
                        .execute()
                    ),
                )

            logger.info(
                f"[RELATIONS_BULK_UPDATED] 聚类: {len(relation_tasks)} | "
                f"关系: {len(relation_rows)} | 证据: {len(evidence_rows)}"
            )
        except Exception as e:
            logger.warning(f"实体关系写入失败（可能尚未执行迁移）: {str(e)[:160]}")

    def save_analysis_results(self, clusters: List[Dict], signals: List[Dict]):
        """
        保存分析结果到数据库

        Args:
            clusters: 聚类列表
            signals: 信号列表
        """
        logger.info(f"保存分析结果: {len(clusters)} 个聚类, {len(signals)} 个信号")

        try:
            cluster_lookup: Dict[str, Dict[str, Any]] = {}
            entity_tasks: List[Dict[str, Any]] = []
            relation_tasks: List[Dict[str, Any]] = []
            relation_clusters_left = self.entity_relation_max_clusters

            # 保存聚类
            for cluster in clusters:
                try:
                    summary = cluster.get("summary", {})
                    entity_mentions = normalize_entity_mentions(
                        summary.get("entity_mentions") or summary.get("key_entities", [])
                    )
                    key_entities = extract_entity_names(entity_mentions)

                    cluster_data = {
                        "cluster_key": cluster["cluster_id"],
                        "category": cluster["category"],
                        "primary_title": cluster["primary_title"],
                        "primary_link": cluster.get("primary_link", ""),
                        "summary": summary.get("summary", cluster["primary_title"]),
                        "summary_en": cluster["primary_title"],
                        "article_count": cluster["article_count"],
                        "key_entities": json.dumps(key_entities),
                        "impact": summary.get("impact", ""),
                        "trend": summary.get("trend", ""),
                        "confidence": summary.get("confidence", 0.8),
                        "analysis_depth": summary.get("analysis_depth", "full"),
                        "is_hot": summary.get("is_hot", cluster["article_count"] >= 3),
                        "full_analysis_triggered": summary.get("analysis_depth") == "full",
                        "processing_time": summary.get("processing_time", 0.0),
                    }
                    result = self._execute_with_retry(
                        "upsert_analysis_cluster",
                        lambda payload=cluster_data: (
                            self.supabase.table("analysis_clusters")
                            .upsert(payload, on_conflict="cluster_key")
                            .execute()
                        ),
                    )
                    cluster_id = (result.data or [{}])[0].get("id")
                    if not cluster_id:
                        fallback = self._execute_with_retry(
                            "fetch_cluster_id_by_key",
                            lambda ck=cluster["cluster_id"]: (
                                self.supabase.table("analysis_clusters")
                                .select("id")
                                .eq("cluster_key", ck)
                                .execute()
                            ),
                        )
                        cluster_id = fallback.data[0]["id"] if fallback.data else None

                    if cluster_id:
                        cluster_lookup[cluster["cluster_id"]] = {
                            "cluster_id": cluster_id,
                            "primary_title": cluster["primary_title"],
                            "summary": summary.get("summary", cluster["primary_title"]),
                            "article_count": cluster["article_count"],
                            "category": cluster["category"],
                        }

                    if cluster_id and cluster.get("article_ids"):
                        relations = [
                            {"article_id": article_id, "cluster_id": cluster_id}
                            for article_id in cluster["article_ids"]
                        ]
                        for i in range(0, len(relations), self.db_batch_size):
                            batch_rows = relations[i : i + self.db_batch_size]
                            self._execute_with_retry(
                                "upsert_article_analyses_batch",
                                lambda rows=batch_rows: (
                                    self.supabase.table("article_analyses")
                                    .upsert(rows, on_conflict="article_id,cluster_id")
                                    .execute()
                                ),
                            )

                    if (
                        summary.get("analysis_depth") == "full"
                        and entity_mentions
                        and cluster_id
                    ):
                        entity_tasks.append(
                            {
                                "cluster_id": cluster_id,
                                "entities": entity_mentions,
                                "category": cluster["category"],
                                "model_name": summary.get("model_name", ""),
                                "prompt_version": summary.get("prompt_version", ""),
                            }
                        )
                        if self.enable_entity_relations and relation_clusters_left > 0:
                            relations = self._extract_cluster_relations(cluster, summary)
                            if relations:
                                relation_tasks.append(
                                    {
                                        "cluster_id": cluster_id,
                                        "cluster_key": cluster["cluster_id"],
                                        "article_ids": cluster.get("article_ids", []),
                                        "category": cluster["category"],
                                        "relations": relations,
                                    }
                                )
                                relation_clusters_left -= 1
                except Exception as e:
                    logger.error(
                        f"[CLUSTER_SAVE_FAILED] cluster_key={cluster.get('cluster_id')} | "
                        f"错误: {str(e)[:160]}"
                    )
                    self.stats["errors"] += 1
                    continue

            if entity_tasks:
                self._update_entities_bulk(entity_tasks)
            if relation_tasks:
                self._update_entity_relations_bulk(relation_tasks)

            # 保存信号
            logger.info("信号解释模式: 先写规则解释，LLM增强由 signal_explainer 异步补充")
            supports_extended_signal_columns = self._supports_extended_signal_columns()
            sorted_signals = sorted(
                signals,
                key=lambda item: float(item.get("confidence", 0) or 0),
                reverse=True,
            )
            for signal in sorted_signals:
                try:
                    related_events = self._build_signal_related_events(signal, cluster_lookup)
                    primary_cluster_id = (
                        related_events[0]["cluster_id"] if related_events else None
                    )
                    signal_category = signal.get("category", "unknown")
                    if signal_category == "unknown" and related_events:
                        signal_category = related_events[0]["category"]

                    confidence = float(signal.get("confidence", 0) or 0)
                    rationale_result = self._build_signal_rationale_fallback(
                        signal, related_events
                    )
                    explain_status = (
                        "pending"
                        if related_events and confidence >= self.signal_llm_min_confidence
                        else "rule_only"
                    )

                    rationale_payload = {
                        "details": signal.get("details", {}),
                        "related_events": related_events,
                        "importance": rationale_result.get("importance", ""),
                        "meaning": rationale_result.get(
                            "meaning", signal.get("description", "")
                        ),
                        "actionable": rationale_result.get("actionable", ""),
                        "confidence_reason": rationale_result.get("confidence_reason", ""),
                        "generated_by": rationale_result.get(
                            "generated_by", "rule_fallback"
                        ),
                        "explain_status": explain_status,
                    }

                    signal_data = {
                        "signal_type": signal["signal_type"],
                        "signal_key": signal["signal_id"],
                        "cluster_id": primary_cluster_id,
                        "category": signal_category,
                        "confidence": signal["confidence"],
                        "description": signal["description"],
                        "description_en": signal.get("description_en", ""),
                        "rationale": json.dumps(rationale_payload, ensure_ascii=False),
                        "actionable_insight": rationale_payload.get("actionable", ""),
                        "data_source": signal.get("data_source", "llm_analysis"),
                        "expires_at": signal.get("expires_at"),
                        "created_at": (
                            signal.get("created_at") or datetime.now().isoformat()
                        ),
                    }
                    if supports_extended_signal_columns:
                        signal_data.update(
                            {
                                "sentinel_id": signal.get("sentinel_id"),
                                "alert_level": signal.get("alert_level"),
                                "risk_score": signal.get("risk_score"),
                                "trigger_reasons": signal.get("trigger_reasons", []),
                                "evidence_links": signal.get("evidence_links", []),
                            }
                        )
                    self._execute_with_retry(
                        "upsert_analysis_signal",
                        lambda payload=signal_data: (
                            self.supabase.table("analysis_signals")
                            .upsert(payload, on_conflict="signal_key")
                            .execute()
                        ),
                    )
                    logger.debug(f"写入信号: {signal['signal_type']}")
                except Exception as e:
                    logger.error(
                        f"[SIGNAL_SAVE_FAILED] signal_key={signal.get('signal_id')} | "
                        f"错误: {str(e)[:160]}"
                    )
                    self.stats["errors"] += 1
                    continue

            logger.info("分析结果保存成功")

        except Exception as e:
            logger.error(f"保存分析结果失败: {e}")
            self.stats["errors"] += 1
            raise

    def enrich_pending_signal_rationales(
        self, hours: int = 24, limit: int = 30, max_workers: int = 3
    ) -> int:
        """异步补充信号 LLM 解释，避免阻塞主分析流程"""
        if not self.llm_client:
            logger.warning("LLM 客户端不可用，跳过信号解释增强")
            return 0

        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = self._execute_with_retry(
            "load_pending_signal_rationales",
            lambda: (
                self.supabase.table("analysis_signals")
                .select(
                    "signal_key, signal_type, confidence, description, rationale, "
                    "actionable_insight, created_at"
                )
                .gte("created_at", cutoff)
                .order("confidence", desc=True)
                .limit(limit * 3)
                .execute()
            ),
        )

        candidates: List[Dict[str, Any]] = []
        for row in rows.data or []:
            rationale_raw = row.get("rationale")
            rationale = {}
            if isinstance(rationale_raw, dict):
                rationale = rationale_raw
            elif isinstance(rationale_raw, str) and rationale_raw.strip():
                try:
                    parsed = json.loads(rationale_raw)
                    if isinstance(parsed, dict):
                        rationale = parsed
                except Exception:
                    rationale = {}

            if rationale.get("generated_by") == "llm":
                continue
            if rationale.get("explain_status") == "rule_only":
                continue

            related_events = rationale.get("related_events", [])
            if not isinstance(related_events, list) or not related_events:
                continue

            signal_payload = {
                "signal_type": row.get("signal_type", "unknown"),
                "confidence": row.get("confidence", 0),
                "description": row.get("description", ""),
                "details": rationale.get("details", {}),
            }
            candidates.append(
                {
                    "signal_key": row.get("signal_key"),
                    "signal": signal_payload,
                    "related_events": related_events,
                    "rationale": rationale,
                }
            )
            if len(candidates) >= limit:
                break

        if not candidates:
            logger.info("没有待增强的信号解释")
            return 0

        logger.info(f"开始异步增强 {len(candidates)} 个信号解释...")
        success_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {
                executor.submit(
                    self._generate_signal_rationale,
                    item["signal"],
                    item["related_events"],
                ): item
                for item in candidates
            }

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                signal_key = item.get("signal_key")
                try:
                    result = future.result()
                    if result.get("generated_by") != "llm":
                        continue

                    rationale_payload = dict(item["rationale"])
                    rationale_payload.update(
                        {
                            "importance": result.get(
                                "importance", rationale_payload.get("importance", "")
                            ),
                            "meaning": result.get(
                                "meaning", rationale_payload.get("meaning", "")
                            ),
                            "actionable": result.get(
                                "actionable", rationale_payload.get("actionable", "")
                            ),
                            "confidence_reason": result.get(
                                "confidence_reason",
                                rationale_payload.get("confidence_reason", ""),
                            ),
                            "generated_by": "llm",
                            "explain_status": "done",
                        }
                    )

                    self._execute_with_retry(
                        "update_signal_rationale",
                        lambda payload=rationale_payload, sk=signal_key: (
                            self.supabase.table("analysis_signals")
                            .update(
                                {
                                    "rationale": json.dumps(
                                        payload, ensure_ascii=False
                                    ),
                                    "actionable_insight": payload.get("actionable", ""),
                                }
                            )
                            .eq("signal_key", sk)
                            .execute()
                        ),
                    )
                    success_count += 1
                except Exception as e:
                    logger.warning(f"信号解释增强失败 {signal_key}: {e}")

        logger.info(f"信号解释增强完成: {success_count}/{len(candidates)}")
        return success_count

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
            batch_size = 300
            for i in range(0, len(article_ids), batch_size):
                batch_ids = article_ids[i : i + batch_size]
                self.supabase.table("articles").update({"analyzed_at": now}).in_(
                    "id", batch_ids
                ).execute()

            logger.info("文章标记完成")

        except Exception as e:
            logger.error(f"标记文章失败: {e}")
            self.stats["errors"] += 1

    def run_analysis(
        self,
        limit: int = None,
        workers: int = 10,
        dry_run: bool = False,
        enrich_signals_after_run: bool = False,
        enrich_hours: int = 24,
        enrich_limit: int = 30,
        enrich_workers: int = 5,
    ):
        """
        运行完整的分析流程（全量完整分析 + 并发）

        Args:
            limit: 最大处理文章数
            workers: 主分析并发 worker 数
            dry_run: 试运行模式（不保存到数据库）
            enrich_signals_after_run: 分析完成后是否补充信号 LLM 解释
            enrich_hours: 信号解释回看窗口（小时）
            enrich_limit: 本轮最多补充解释的信号数
            enrich_workers: 信号解释并发 worker 数
        """
        if workers and workers > 0:
            self.concurrent_workers = int(workers)

        logger.info("=" * 60)
        logger.info("开始新闻分析（全量完整分析 + 并发处理）")
        logger.info(
            f"配置: 信号目标阈值={self.hot_threshold}, 并发数={self.concurrent_workers}"
        )
        logger.info("=" * 60)

        start_time = datetime.now()

        # 1. 加载文章
        articles = self.load_unanalyzed_articles(limit=limit, hours=None)

        if not articles:
            logger.info("没有未分析的文章，跳过")
            if enrich_signals_after_run and not dry_run:
                self.enrich_pending_signal_rationales(
                    hours=enrich_hours,
                    limit=enrich_limit,
                    max_workers=enrich_workers,
                )
            return

        # 2. 聚类
        logger.info(f"开始聚类 {len(articles)} 篇文章...")
        clusters = cluster_news(articles)
        self.stats["clusters_created"] = len(clusters)
        logger.info(f"创建了 {len(clusters)} 个聚类")

        # 3. 统计信号检测目标聚类（用于信号检测和统计）
        hot_clusters = [
            c for c in clusters if c.get("article_count", 0) >= self.hot_threshold
        ]
        cold_clusters = [
            c for c in clusters if c.get("article_count", 0) < self.hot_threshold
        ]

        logger.info(
            f"聚类统计: 信号目标 {len(hot_clusters)} 个, 其他 {len(cold_clusters)} 个"
        )

        # 4. 复用近期聚类结果，减少重复 LLM 调用
        reused_clusters = self._reuse_existing_cluster_summaries(clusters)
        clusters_to_analyze = [cluster for cluster in clusters if not cluster.get("summary")]
        logger.info(
            f"摘要复用: {reused_clusters} 个 | 待新增分析: {len(clusters_to_analyze)} 个"
        )

        # 5. 并发完整分析剩余聚类
        if clusters_to_analyze:
            logger.info(f"开始并发完整分析 {len(clusters_to_analyze)} 个聚类...")
            self._process_clusters_concurrent(clusters_to_analyze, dry_run=dry_run)
        logger.info(f"聚类处理完成: 总计 {len(clusters)} 个")

        # 6. 信号检测（只对信号目标聚类）
        logger.info("检测信号（仅信号目标聚类）...")
        signals = detect_all_signals(hot_clusters)
        watchlist_signals = detect_watchlist_signals(clusters)
        if watchlist_signals:
            logger.info(f"检测到 {len(watchlist_signals)} 个哨兵告警信号")
            signals.extend(watchlist_signals)
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

            if enrich_signals_after_run:
                self.enrich_pending_signal_rationales(
                    hours=enrich_hours,
                    limit=enrich_limit,
                    max_workers=enrich_workers,
                )
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
        logger.info(f"信号目标聚类: {len(hot_clusters)} (完整分析)")
        logger.info(f"其他聚类: {len(cold_clusters)} (完整分析)")
        logger.info(f"检测信号: {self.stats['signals_detected']}")
        logger.info(f"LLM调用: {self.stats['llm_calls']}")
        if self.llm_client:
            llm_stats = self.llm_client.get_stats()
            logger.info(f"预估成本: ${llm_stats['estimated_cost']:.4f}")
        logger.info("=" * 60)

    def _process_clusters_concurrent(self, clusters: List[Dict], dry_run: bool = False):
        """
        并发处理聚类列表

        Args:
            clusters: 聚类列表
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
                executor.submit(self.generate_cluster_summary, cluster): cluster
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
                        "analysis_depth": "full",
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
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="主分析并发 worker 数",
    )
    parser.add_argument("--hours", type=int, default=24, help="兼容参数（已不用于主分析）")
    parser.add_argument(
        "--enrich-signals-only",
        action="store_true",
        help="仅执行信号解释增强，不跑主分析",
    )
    parser.add_argument(
        "--enrich-signals-after-run",
        action="store_true",
        help="主分析完成后自动补充信号解释",
    )
    parser.add_argument(
        "--enrich-hours",
        type=int,
        default=24,
        help="信号解释增强回看窗口（小时）",
    )
    parser.add_argument(
        "--enrich-limit",
        type=int,
        default=30,
        help="本次最多增强的信号数量",
    )
    parser.add_argument(
        "--enrich-workers",
        type=int,
        default=5,
        help="信号解释增强并发 worker 数",
    )

    args = parser.parse_args()

    try:
        analyzer = HotspotAnalyzer()
        if args.enrich_signals_only:
            analyzer.enrich_pending_signal_rationales(
                hours=args.enrich_hours,
                limit=args.enrich_limit,
                max_workers=args.enrich_workers,
            )
            return

        analyzer.run_analysis(
            limit=args.limit,
            workers=args.workers,
            dry_run=args.dry_run,
            enrich_signals_after_run=args.enrich_signals_after_run,
            enrich_hours=args.enrich_hours,
            enrich_limit=args.enrich_limit,
            enrich_workers=args.enrich_workers,
        )
    except Exception as e:
        logger.error(f"分析器运行失败: {e}")
        raise


if __name__ == "__main__":
    main()
