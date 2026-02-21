#!/usr/bin/env python3
"""实体关系增量处理队列。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.analyzer import HotspotAnalyzer

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


class EntityRelationWorker:
    """关系增量队列处理器。"""

    def __init__(self):
        self.analyzer = HotspotAnalyzer()

    @staticmethod
    def _parse_key_entities(raw_value: Any) -> List[Dict[str, Any]]:
        if isinstance(raw_value, list):
            names = [str(item).strip() for item in raw_value if str(item).strip()]
        elif isinstance(raw_value, str) and raw_value.strip():
            try:
                parsed = json.loads(raw_value)
                names = [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                names = []
        else:
            names = []

        unique_names: List[str] = []
        for name in names:
            if name not in unique_names:
                unique_names.append(name)

        return [
            {
                "mention": name,
                "canonical_name": name,
                "entity_type": "other",
                "confidence": 0.6,
            }
            for name in unique_names[:12]
        ]

    def _load_candidate_clusters(
        self,
        hours: int,
        limit: int,
        min_article_count: int,
    ) -> List[Dict[str, Any]]:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = (
            self.analyzer.supabase.table("analysis_clusters")
            .select(
                "id,cluster_key,primary_title,summary,key_entities,"
                "category,article_count,created_at"
            )
            .gte("created_at", cutoff)
            .gte("article_count", min_article_count)
            .order("created_at", desc=True)
            .limit(limit * 4)
            .execute()
        )
        return rows.data or []

    def _load_article_ids(self, cluster_id: int) -> List[int]:
        rows = (
            self.analyzer.supabase.table("article_analyses")
            .select("article_id")
            .eq("cluster_id", cluster_id)
            .limit(200)
            .execute()
        )
        ids: List[int] = []
        for row in rows.data or []:
            article_id = row.get("article_id")
            if isinstance(article_id, int) and article_id not in ids:
                ids.append(article_id)
        return ids

    def _cluster_has_relation_evidence(self, article_ids: List[int]) -> bool:
        if not article_ids:
            return False
        rows = (
            self.analyzer.supabase.table("relation_evidence")
            .select("article_id")
            .in_("article_id", article_ids[:100])
            .limit(1)
            .execute()
        )
        return bool(rows.data)

    def run(
        self,
        hours: int = 72,
        limit: int = 60,
        min_article_count: int = 2,
        force: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, int]:
        metrics = {
            "candidate_clusters": 0,
            "processed_clusters": 0,
            "skipped_existing": 0,
            "relation_tasks": 0,
        }

        candidates = self._load_candidate_clusters(hours, limit, min_article_count)
        metrics["candidate_clusters"] = len(candidates)

        relation_tasks: List[Dict[str, Any]] = []
        for row in candidates:
            if metrics["processed_clusters"] >= limit:
                break

            cluster_id = int(row.get("id") or 0)
            if cluster_id <= 0:
                continue

            article_ids = self._load_article_ids(cluster_id)
            if len(article_ids) < 1:
                continue

            if not force and self._cluster_has_relation_evidence(article_ids):
                metrics["skipped_existing"] += 1
                continue

            summary = {
                "summary": str(row.get("summary") or ""),
                "entity_mentions": self._parse_key_entities(row.get("key_entities")),
            }
            cluster = {
                "primary_title": str(row.get("primary_title") or ""),
                "titles": [str(row.get("primary_title") or "")],
                "article_count": int(row.get("article_count") or 0),
            }

            relations = self.analyzer._extract_cluster_relations(cluster, summary)
            if not relations:
                continue

            relation_tasks.append(
                {
                    "cluster_id": cluster_id,
                    "cluster_key": row.get("cluster_key"),
                    "article_ids": article_ids,
                    "category": row.get("category", "unknown"),
                    "relations": relations,
                }
            )
            metrics["processed_clusters"] += 1

        metrics["relation_tasks"] = len(relation_tasks)
        if dry_run:
            logger.info(f"[RELATION_WORKER_DRY_RUN] {metrics}")
            return metrics

        if relation_tasks:
            self.analyzer._update_entity_relations_bulk(relation_tasks)

        logger.info(f"[RELATION_WORKER_COMPLETE] {metrics}")
        return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="实体关系增量处理队列")
    parser.add_argument("--hours", type=int, default=72, help="回看窗口（小时）")
    parser.add_argument("--limit", type=int, default=60, help="最多处理聚类数")
    parser.add_argument(
        "--min-article-count",
        type=int,
        default=2,
        help="最小文章数阈值",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略已有 relation_evidence，强制重算",
    )
    parser.add_argument("--dry-run", action="store_true", help="试运行")

    args = parser.parse_args()
    worker = EntityRelationWorker()
    worker.run(
        hours=args.hours,
        limit=args.limit,
        min_article_count=args.min_article_count,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
