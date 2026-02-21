#!/usr/bin/env python3
"""
US-Monitor UI 仪表板
使用 Streamlit 构建中文界面
"""

import os
import sys
import json
import html
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from supabase import create_client

from scripts.entity_classification import (
    ENTITY_TYPE_FILTER_OPTIONS,
    merge_entity_metadata,
    normalize_entity_mentions,
)

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# 页面配置
st.set_page_config(
    page_title="US-Monitor 热点分析",
    page_icon="🇺🇸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 主题配置 - 技术风格，高对比度
THEME = {
    "bg_main": "#0b1020",
    "bg_panel": "#0f172a",
    "bg_card": "#111c34",
    "bg_sidebar": "#0a1328",
    "text_main": "#e6edf7",
    "text_body": "#c7d2e7",
    "text_muted": "#8ea0bf",
    "primary": "#8bd3ff",
    "accent": "#29f0ff",
    "border": "#1f2d49",
    "danger": "#ff6b7a",
    "warn": "#ffd166",
    "ok": "#67f7c2",
}


# 生成 CSS
def get_css():
    t = THEME
    return f"""
<style>
    :root {{
        color-scheme: dark !important;
        --bg-main: {t["bg_main"]};
        --bg-panel: {t["bg_panel"]};
        --bg-card: {t["bg_card"]};
        --bg-sidebar: {t["bg_sidebar"]};
        --text-main: {t["text_main"]};
        --text-body: {t["text_body"]};
        --text-muted: {t["text_muted"]};
        --accent: {t["accent"]};
        --primary: {t["primary"]};
        --border: {t["border"]};
    }}

    html, body {{
        background: var(--bg-main) !important;
        color: var(--text-main) !important;
        font-family: "Inter", "SF Pro Text", "Segoe UI", sans-serif;
    }}

    /* 顶部白条和部署区域：统一深色，避免与主界面冲突 */
    [data-testid="stHeader"] {{
        background: var(--bg-panel) !important;
        border-bottom: 1px solid var(--border);
    }}
    [data-testid="stToolbar"] {{
        background: transparent !important;
    }}
    [data-testid="stAppDeployButton"] {{
        display: none !important;
    }}

    /* Streamlit 全局容器 */
    .stApp {{
        background: var(--bg-main) !important;
        color: var(--text-main) !important;
    }}
    [data-testid="stAppViewContainer"] {{
        background: linear-gradient(180deg, #0b1020 0%, #0a1120 100%) !important;
    }}
    [data-testid="stMain"] {{
        background: transparent !important;
    }}
    [data-testid="block-container"] {{
        max-width: 1500px;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }}
    
    /* 侧边栏 */
    [data-testid="stSidebar"] {{
        background: var(--bg-sidebar) !important;
        border-right: 1px solid var(--border);
    }}
    
    /* 统一文本颜色（无视系统明暗模式） */
    .stMarkdown, .stText, p, li, h1, h2, h3, h4, h5, h6, label, span, div {{
        color: var(--text-main) !important;
    }}
    
    /* 主标题 */
    .main-header {{
        font-size: 2.1rem;
        font-weight: 700;
        letter-spacing: 0.2px;
        color: var(--text-main);
        margin-bottom: 1.2rem;
        border-bottom: 2px solid var(--accent);
        padding-bottom: 0.7rem;
        text-shadow: 0 0 20px rgba(41, 240, 255, 0.15);
    }}
    
    /* 指标卡片 */
    [data-testid="stMetric"] {{
        background: var(--bg-card);
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid var(--border);
        box-shadow: inset 0 0 0 1px rgba(139, 211, 255, 0.05);
    }}
    
    [data-testid="stMetricLabel"] {{
        color: var(--text-muted) !important;
        font-weight: 600;
    }}
    
    [data-testid="stMetricValue"] {{
        color: var(--text-main) !important;
        font-family: "JetBrains Mono", "SF Mono", "Consolas", monospace;
        font-weight: 700;
    }}
    
    /* 热点卡片 */
    .hotspot-card {{
        background: var(--bg-card);
        padding: 1.25rem;
        border-radius: 10px;
        border: 1px solid var(--border);
        margin-bottom: 1rem;
        border-left: 3px solid var(--accent);
    }}
    
    .hotspot-card h4 {{
        color: var(--text-main);
        font-weight: 600;
        font-size: 1.1rem;
        margin-bottom: 0.75rem;
    }}
    
    .hotspot-card h5 {{
        color: var(--text-body);
        font-weight: 600;
    }}
    
    .hotspot-card p {{
        color: var(--text-body);
        font-size: 0.95rem;
        line-height: 1.55;
    }}
    
    .hotspot-card .meta-text {{
        color: var(--text-muted);
        font-size: 0.85rem;
    }}
    
    /* 信号徽章 */
    .signal-high {{
        color: {t["danger"]};
        font-weight: 700;
    }}
    .signal-medium {{
        color: {t["warn"]};
        font-weight: 700;
    }}
    .signal-low {{
        color: {t["ok"]};
        font-weight: 700;
    }}
    
    /* 分割线 */
    hr {{
        border: none;
        height: 1px;
        background: var(--border);
        margin: 1.5rem 0;
    }}
    
    /* 滚动条 */
    ::-webkit-scrollbar {{
        width: 8px;
    }}
    ::-webkit-scrollbar-track {{
        background: var(--bg-main);
    }}
    ::-webkit-scrollbar-thumb {{
        background: #2b3e62;
        border-radius: 8px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: #3c5689;
    }}
    
    /* 按钮 */
    .stButton > button {{
        background: var(--bg-panel);
        color: var(--text-main);
        border: 1px solid var(--border);
        border-radius: 8px;
        font-weight: 600;
    }}
    .stButton > button:hover {{
        border-color: var(--primary);
        color: var(--primary) !important;
        box-shadow: 0 0 0 1px rgba(139, 211, 255, 0.35);
    }}
    
    /* 输入组件 */
    [data-baseweb="select"] > div,
    .stSelectbox > div > div,
    .stTextInput > div > div > input,
    .stNumberInput input {{
        background: var(--bg-panel) !important;
        color: var(--text-main) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
    }}
    [data-baseweb="select"] svg {{
        fill: var(--text-muted) !important;
    }}
    /* 选中值和占位符在命令模式下保持可读 */
    [data-baseweb="select"] [data-testid="stMarkdownContainer"] p,
    [data-baseweb="select"] span,
    [data-baseweb="select"] input {{
        color: var(--text-main) !important;
        opacity: 1 !important;
    }}
    /* 下拉选项菜单（portal 弹层） */
    [data-baseweb="popover"] {{
        background: transparent !important;
    }}
    [data-baseweb="popover"] [role="listbox"] {{
        background: #0f172a !important;
        border: 1px solid #8bd3ff !important;
        border-radius: 10px !important;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55) !important;
    }}
    [data-baseweb="popover"] [role="option"] {{
        background: #0f172a !important;
        color: #f8fafc !important;
        opacity: 1 !important;
        font-weight: 600 !important;
    }}
    [data-baseweb="popover"] [role="option"]:hover {{
        background: #1e3a5f !important;
        color: #ffffff !important;
    }}
    [data-baseweb="popover"] [aria-selected="true"][role="option"] {{
        background: #2d5b8f !important;
        color: #ffffff !important;
    }}
    /* 兼容不同版本 BaseWeb 菜单节点 */
    [role="listbox"],
    ul[role="listbox"] {{
        background: #0f172a !important;
        color: #f8fafc !important;
        border: 1px solid #8bd3ff !important;
    }}
    [role="option"] {{
        color: #f8fafc !important;
        background: #0f172a !important;
    }}
    [role="option"][aria-disabled="true"] {{
        color: #cbd5e1 !important;
        opacity: 0.95 !important;
    }}
    
    /* 单选按钮 */
    .stRadio > div {{
        color: var(--text-body);
    }}
    [data-testid="stRadio"] label {{
        background: transparent !important;
    }}
    
    /* 链接按钮 */
    .stLinkButton > button {{
        background: transparent;
        border: 1px solid var(--accent);
        color: var(--accent) !important;
        border-radius: 8px;
        font-weight: 600;
    }}
    .stLinkButton > button:hover {{
        background: rgba(41, 240, 255, 0.12);
        color: var(--text-main) !important;
    }}
    
    /* 展开框 */
    [data-testid="stExpander"] {{
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
    }}
    .streamlit-expanderHeader, [data-testid="stExpander"] summary {{
        color: var(--text-body) !important;
        background: var(--bg-card) !important;
    }}
    [data-testid="stExpander"] summary {{
        align-items: flex-start !important;
    }}
    [data-testid="stExpander"] summary p {{
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
        word-break: break-word !important;
        line-height: 1.45 !important;
    }}
    
    /* Tabs / DataFrame / 图表 */
    [data-baseweb="tab-list"] {{
        gap: 4px;
    }}
    [data-baseweb="tab"] {{
        background: var(--bg-panel) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px 8px 0 0;
        color: var(--text-muted) !important;
    }}
    [aria-selected="true"][data-baseweb="tab"] {{
        color: var(--text-main) !important;
        border-color: var(--primary) !important;
    }}
    .stDataFrame, [data-testid="stChart"] {{
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
    }}
    /* 隐藏元素工具栏（命令模式下对比度不稳定，影响可读性） */
    [data-testid="stElementToolbar"] {{
        display: none !important;
    }}
    /* Vega/Altair tooltip 对比度修复 */
    .vg-tooltip,
    .vega-embed .vg-tooltip {{
        background: var(--bg-panel) !important;
        color: var(--text-main) !important;
        border: 1px solid var(--border) !important;
        border-radius: 8px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35) !important;
        font-size: 14px !important;
        line-height: 1.5 !important;
    }}
    .vg-tooltip td,
    .vg-tooltip th,
    .vega-embed .vg-tooltip td,
    .vega-embed .vg-tooltip th {{
        color: var(--text-main) !important;
    }}
    
    /* 分类标签 */
    .category-military {{ color: {t["danger"]}; font-weight: 600; }}
    .category-politics {{ color: #b39cff; font-weight: 600; }}
    .category-economy {{ color: {t["ok"]}; font-weight: 600; }}
    .category-tech {{ color: #67e8f9; font-weight: 600; }}
    
</style>
"""


# 应用主题 CSS
st.markdown(get_css(), unsafe_allow_html=True)


# 初始化 Supabase
@st.cache_resource
def init_supabase():
    """初始化 Supabase 客户端"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        st.error("缺少 Supabase 配置。请设置 SUPABASE_URL 和 SUPABASE_KEY 环境变量。")
        return None

    return create_client(url, key)


# 数据获取函数
@st.cache_data(ttl=300)  # 缓存5分钟
def get_clusters(
    _supabase, hours: int = 24, category: str = None, only_hot: bool = False
) -> pd.DataFrame:
    """获取聚类数据"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    query = _supabase.table("analysis_clusters").select("*").gte("created_at", cutoff)

    if category and category != "全部":
        query = query.eq("category", category)
    if only_hot:
        query = query.eq("is_hot", True)

    result = query.order("created_at", desc=True).execute()

    if result.data:
        return pd.DataFrame(result.data)
    return pd.DataFrame()


@st.cache_data(ttl=300)
def get_signals(_supabase, hours: int = 24) -> pd.DataFrame:
    """获取信号数据"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    result = (
        _supabase.table("analysis_signals")
        .select("*")
        .gte("created_at", cutoff)
        .order("confidence", desc=True)
        .execute()
    )

    if result.data:
        return pd.DataFrame(result.data)
    return pd.DataFrame()


@st.cache_data(ttl=300)
def get_watchlist_signals(_supabase, hours: int = 24) -> pd.DataFrame:
    """获取哨兵告警信号。"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    result = (
        _supabase.table("analysis_signals")
        .select("*")
        .eq("signal_type", "watchlist_alert")
        .gte("created_at", cutoff)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    )
    if result.data:
        return pd.DataFrame(result.data)
    return pd.DataFrame()


@st.cache_data(ttl=300)
def get_entity_relations_graph(
    _supabase,
    min_confidence: float = 0.55,
    limit: int = 400,
) -> pd.DataFrame:
    """获取实体关系图谱数据。"""
    relation_rows = (
        _supabase.table("entity_relations")
        .select("*")
        .gte("confidence", min_confidence)
        .order("last_seen", desc=True)
        .limit(limit)
        .execute()
    )
    relations = relation_rows.data or []
    if not relations:
        return pd.DataFrame()

    def _as_int(value: Any) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return -1

    entity_ids = sorted(
        {
            _as_int(entity_id)
            for row in relations
            for entity_id in [row.get("entity1_id"), row.get("entity2_id")]
            if _as_int(entity_id) > 0
        }
    )
    if not entity_ids:
        return pd.DataFrame()

    entity_map: Dict[int, Dict[str, str]] = {}
    batch_size = 200
    for i in range(0, len(entity_ids), batch_size):
        batch_ids = entity_ids[i : i + batch_size]
        entity_rows = (
            _supabase.table("entities")
            .select("id,name,entity_type,category")
            .in_("id", batch_ids)
            .execute()
        )
        for row in entity_rows.data or []:
            entity_id = _as_int(row.get("id"))
            if entity_id <= 0:
                continue
            entity_map[entity_id] = {
                "name": str(row.get("name", "")),
                "entity_type": str(row.get("entity_type", "other")),
                "category": str(row.get("category", "unknown")),
            }

    normalized_rows: List[Dict[str, Any]] = []
    for row in relations:
        entity1_id = _as_int(row.get("entity1_id"))
        entity2_id = _as_int(row.get("entity2_id"))
        if entity1_id not in entity_map or entity2_id not in entity_map:
            continue
        left = entity_map[entity1_id]
        right = entity_map[entity2_id]
        normalized_rows.append(
            {
                "id": row.get("id"),
                "entity1_id": entity1_id,
                "entity2_id": entity2_id,
                "entity1_name": left["name"],
                "entity1_type": left["entity_type"],
                "entity2_name": right["name"],
                "entity2_type": right["entity_type"],
                "relation_text": row.get("relation_text", ""),
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "source_count": int(row.get("source_count", 0) or 0),
                "last_seen": row.get("last_seen"),
                "source_article_ids": row.get("source_article_ids", []),
            }
        )

    return pd.DataFrame(normalized_rows)


@st.cache_data(ttl=300)
def get_cluster_article_links(
    _supabase, cluster_ids: Tuple[int, ...], per_cluster: int = 3
) -> Dict[int, List[Dict[str, str]]]:
    """批量获取聚类关联文章原文链接"""
    if not cluster_ids:
        return {}

    relation_rows: List[Dict] = []
    id_list = [int(item) for item in cluster_ids]
    batch_size = 200
    for i in range(0, len(id_list), batch_size):
        batch_cluster_ids = id_list[i : i + batch_size]
        result = (
            _supabase.table("article_analyses")
            .select("id, cluster_id, article_id")
            .in_("cluster_id", batch_cluster_ids)
            .order("id")
            .execute()
        )
        relation_rows.extend(result.data or [])

    cluster_article_ids: Dict[int, List[int]] = {}
    for row in relation_rows:
        cluster_id = int(row.get("cluster_id"))
        article_id = int(row.get("article_id"))
        ids = cluster_article_ids.setdefault(cluster_id, [])
        if article_id not in ids and len(ids) < per_cluster:
            ids.append(article_id)

    all_article_ids = sorted(
        {article_id for ids in cluster_article_ids.values() for article_id in ids}
    )
    if not all_article_ids:
        return {}

    article_map: Dict[int, Dict[str, str]] = {}
    for i in range(0, len(all_article_ids), batch_size):
        batch_article_ids = all_article_ids[i : i + batch_size]
        result = (
            _supabase.table("articles")
            .select("id, title, url")
            .in_("id", batch_article_ids)
            .execute()
        )
        for article in result.data or []:
            article_map[int(article["id"])] = {
                "title": article.get("title", "原文链接"),
                "url": article.get("url", ""),
            }

    links_map: Dict[int, List[Dict[str, str]]] = {}
    for cluster_id, article_ids in cluster_article_ids.items():
        links: List[Dict[str, str]] = []
        for article_id in article_ids:
            article = article_map.get(article_id)
            if not article or not article.get("url"):
                continue
            links.append(article)
        links_map[cluster_id] = links

    return links_map


SIGNAL_TYPE_NAMES = {
    "velocity_spike": "🚀 速度激增",
    "convergence": "🔄 多源聚合",
    "triangulation": "📐 三角验证",
    "hotspot_escalation": "🔥 热点升级",
    "economic_indicator_alert": "📊 经济指标异常",
    "natural_disaster_signal": "🌋 自然灾害",
    "geopolitical_intensity": "🌍 地缘政治紧张",
    "watchlist_alert": "🛰️ 场景哨兵告警",
}

WATCHLIST_LEVEL_COLORS = {
    "L1": "#67f7c2",
    "L2": "#ffd166",
    "L3": "#ff9f43",
    "L4": "#ff6b7a",
}


def parse_json_field(value: Any, expected_type: type):
    """解析 JSON 字段（兼容对象和字符串）。"""
    if isinstance(value, expected_type):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, expected_type):
                return parsed
        except Exception:
            return expected_type()
    return expected_type()


def parse_string_list(value: Any) -> List[str]:
    """解析字符串列表字段。"""
    parsed = parse_json_field(value, list)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def get_signal_name(row: pd.Series) -> str:
    """获取信号展示名称"""
    signal_name = row.get("name")
    if signal_name and signal_name != "N/A":
        return signal_name
    signal_type = row.get("signal_type", "unknown")
    return SIGNAL_TYPE_NAMES.get(signal_type, f"⚡ {signal_type}")


def parse_signal_explanation(row: pd.Series) -> dict:
    """解析信号解释信息，优先使用 LLM/数据库中的结构化解释"""
    confidence = float(row.get("confidence", 0) or 0)
    signal_type = row.get("signal_type", "unknown")
    details = {}

    raw_rationale = row.get("rationale")
    if isinstance(raw_rationale, dict):
        details = raw_rationale
    elif isinstance(raw_rationale, str) and raw_rationale.strip():
        try:
            parsed = json.loads(raw_rationale)
            if isinstance(parsed, dict):
                details = parsed
        except Exception:
            details = {}

    parsed_details = (
        details.get("details") if isinstance(details.get("details"), dict) else details
    )
    related_events = details.get("related_events", []) if isinstance(details, dict) else []
    if not isinstance(related_events, list):
        related_events = []

    # 兼容后续可能接入的 LLM 解释字段
    if any(k in details for k in ["importance", "actionable", "confidence_reason"]):
        return {
            "why": details.get("importance", row.get("description", "暂无触发原因")),
            "meaning": details.get("meaning", row.get("description", "暂无含义解释")),
            "action": details.get("actionable", "建议继续观察后续变化"),
            "confidence_reason": details.get(
                "confidence_reason", f"当前系统评分置信度为 {confidence:.2f}"
            ),
            "events": related_events,
            "alert_level": details.get("alert_level"),
        }

    def _format_source_types(value) -> str:
        if isinstance(value, list):
            return ", ".join(str(v) for v in value if v)
        if value:
            return str(value)
        return "N/A"

    if signal_type == "velocity_spike":
        cluster_count = parsed_details.get("cluster_count", "N/A")
        threshold = parsed_details.get("threshold", "N/A")
        window_hours = parsed_details.get("time_window_hours", 1)
        why = f"{window_hours}小时内聚类数达到 {cluster_count}，超过阈值 {threshold}"
        meaning = "代表短时间内相关新闻密度上升，事件可能进入快速发酵阶段。"
        action = "建议优先跟踪该时段新增聚类，观察是否出现跨主题扩散。"
    elif signal_type == "convergence":
        source_count = parsed_details.get("source_count", "N/A")
        source_types = _format_source_types(parsed_details.get("source_types", []))
        why = f"同一事件被 {source_count} 类来源同时报道（{source_types}）"
        meaning = "代表事件可验证性上升，单一来源偏差风险下降。"
        action = "建议重点查看来源差异，确认关键事实是否一致。"
    elif signal_type == "triangulation":
        source_types = _format_source_types(parsed_details.get("source_types", []))
        why = f"已出现多类关键来源交叉验证（{source_types}）"
        meaning = "代表信号可靠性高，事件真实性通常更强。"
        action = "建议将该类信号作为重点预警输入。"
    elif signal_type == "hotspot_escalation":
        level = parsed_details.get("escalation_level", "unknown")
        score = parsed_details.get("total_score", "N/A")
        article_count = parsed_details.get("article_count", "N/A")
        why = f"升级等级 {level}，总评分 {score}，聚类文章数 {article_count}"
        meaning = "代表事件热度和影响面正在抬升，后续可能升级。"
        action = "建议结合实体趋势与来源变化，持续复核升级方向。"
    elif signal_type == "watchlist_alert":
        sentinel_name = parsed_details.get("sentinel_name", row.get("description", "场景哨兵"))
        level = row.get("alert_level") or parsed_details.get("alert_level", "L1")
        risk_score = row.get("risk_score") or parsed_details.get("risk_score", "N/A")
        trigger_reasons = parsed_details.get("trigger_reasons", [])
        why = f"{sentinel_name} 当前等级 {level}，风险分 {risk_score}"
        if isinstance(trigger_reasons, list) and trigger_reasons:
            meaning = "；".join([str(item) for item in trigger_reasons[:3]])
        else:
            meaning = "已命中场景规则，建议关注来源收敛与官方确认。"
        action = parsed_details.get("suggested_action", "建议快速复核并更新哨兵态势。")
    else:
        why = row.get("description", "暂无触发原因")
        meaning = "代表系统检测到值得关注的异常变化。"
        action = "建议结合上下文进一步人工复核。"

    return {
        "why": why,
        "meaning": meaning,
        "action": action,
        "confidence_reason": f"当前系统评分置信度为 {confidence:.2f}",
        "events": related_events,
        "alert_level": parsed_details.get("alert_level"),
    }


def format_related_events(events: list, limit: int = 2) -> str:
    """格式化关联事件标题列表"""
    if not events:
        return ""
    titles = []
    for event in events[:limit]:
        if isinstance(event, dict) and event.get("title"):
            titles.append(str(event["title"]))
    return "；".join(titles)


def get_related_event_links(
    events: list, cluster_links_map: Dict[int, List[Dict[str, str]]]
) -> List[Dict[str, str]]:
    """将信号关联事件转换为可点击链接信息"""
    results: List[Dict[str, str]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        title = str(event.get("title") or "关联事件").strip()
        cluster_id_raw = event.get("cluster_id")
        cluster_id = None
        if isinstance(cluster_id_raw, int):
            cluster_id = cluster_id_raw
        elif isinstance(cluster_id_raw, str) and cluster_id_raw.isdigit():
            cluster_id = int(cluster_id_raw)

        url = ""
        if cluster_id is not None:
            candidates = cluster_links_map.get(cluster_id, [])
            if candidates:
                url = candidates[0].get("url", "")

        results.append({"title": title, "url": url})
    return results


def render_external_link(label: str, url: str):
    """渲染外部链接，兼容不支持 key 参数的旧版 Streamlit"""
    if not url:
        return
    safe_label = html.escape(label)
    safe_url = html.escape(url, quote=True)
    st.markdown(
        f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">🔗 {safe_label}</a>',
        unsafe_allow_html=True,
    )


def short_text(text: str, max_len: int = 80) -> str:
    """压缩文本，便于在列表中快速扫描"""
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_len:
        return cleaned
    return f"{cleaned[:max_len]}..."


def normalize_watchlist_record(row: pd.Series) -> Dict[str, Any]:
    """标准化哨兵记录，便于页面渲染。"""
    details = parse_json_field(row.get("details"), dict)
    trigger_reasons = parse_string_list(
        row.get("trigger_reasons", details.get("trigger_reasons", []))
    )
    evidence_links = parse_string_list(
        row.get("evidence_links", details.get("evidence_links", []))
    )
    related_entities = parse_string_list(details.get("related_entities", []))

    created_at = str(row.get("created_at", ""))
    sentinel_name = str(
        details.get("sentinel_name")
        or row.get("name")
        or row.get("description")
        or "场景哨兵"
    )

    return {
        "signal_key": str(row.get("signal_key", "")),
        "sentinel_id": str(
            row.get("sentinel_id") or details.get("sentinel_id") or "unknown"
        ),
        "sentinel_name": sentinel_name,
        "alert_level": str(row.get("alert_level") or details.get("alert_level") or "L1"),
        "risk_score": float(row.get("risk_score") or details.get("risk_score") or 0.0),
        "confidence": float(row.get("confidence") or 0.0),
        "trigger_reasons": trigger_reasons,
        "evidence_links": evidence_links,
        "related_entities": related_entities,
        "suggested_action": str(details.get("suggested_action") or "建议人工复核。"),
        "next_review_time": str(details.get("next_review_time") or ""),
        "description": str(row.get("description") or ""),
        "created_at": created_at,
    }


@st.cache_data(ttl=300)
def get_stats(_supabase) -> dict:
    """获取统计信息"""
    today = datetime.now().strftime("%Y-%m-%d")

    # 今日聚类数
    clusters_today = (
        _supabase.table("analysis_clusters")
        .select("*", count="exact")
        .gte("created_at", today)
        .execute()
    )

    # 今日信号数
    signals_today = (
        _supabase.table("analysis_signals")
        .select("*", count="exact")
        .gte("created_at", today)
        .execute()
    )

    # 总文章数
    articles_total = _supabase.table("articles").select("*", count="exact").execute()

    # 未分析文章数
    articles_unanalyzed = (
        _supabase.table("articles")
        .select("*", count="exact")
        .is_("analyzed_at", "null")
        .execute()
    )

    return {
        "clusters_today": clusters_today.count,
        "signals_today": signals_today.count,
        "articles_total": articles_total.count,
        "articles_unanalyzed": articles_unanalyzed.count,
    }


# 侧边栏
def render_sidebar():
    """渲染侧边栏"""
    st.sidebar.markdown("## 📊 导航")

    page = st.sidebar.radio(
        "选择页面:",
        [
            "🏠 概览首页",
            "🛰️ 哨兵态势",
            "🕸️ 关系图谱",
            "🔥 热点详情",
            "📡 信号中心",
            "📁 实体档案",
            "📈 数据统计",
        ],
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ 设置")

    time_range = st.sidebar.selectbox("时间范围:", ["24小时", "7天", "30天"], index=0)

    hours_map = {"24小时": 24, "7天": 168, "30天": 720}

    category = st.sidebar.selectbox(
        "分类筛选:", ["全部", "military", "politics", "economy", "tech"]
    )

    return page, hours_map[time_range], category


# 概览首页
def render_overview(supabase, hours: int, category: str):
    """渲染概览首页"""
    st.markdown(
        '<div class="main-header">🇺🇸 US-Monitor 热点分析</div>', unsafe_allow_html=True
    )

    # 获取统计数据
    stats = get_stats(supabase)

    # 显示关键指标
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("今日聚类", stats["clusters_today"])
    with col2:
        st.metric("今日信号", stats["signals_today"])
    with col3:
        st.metric("总文章数", f"{stats['articles_total']:,}")
    with col4:
        st.metric("待分析", stats["articles_unanalyzed"])

    st.markdown("---")

    # 获取数据
    clusters_df = get_clusters(supabase, hours, category, only_hot=True)
    signals_df = get_signals(supabase, hours)

    # 最新热点
    st.markdown("### 🔥 最新热点 (TOP 5)")

    if clusters_df.empty:
        st.info("暂无热点数据")
    else:
        top_clusters = clusters_df.head(5)
        top_cluster_ids = tuple(
            int(cluster_id)
            for cluster_id in top_clusters["id"].tolist()
            if pd.notna(cluster_id)
        )
        top_links_map = get_cluster_article_links(
            supabase, top_cluster_ids, per_cluster=1
        )

        for idx, row in top_clusters.iterrows():
            with st.container():
                st.markdown(
                    f"""
                <div class="hotspot-card">
                    <h4>{row.get("primary_title", "N/A")}</h4>
                    <p><strong>中文摘要:</strong> {row.get("summary", "N/A")[:150]}...</p>
                    <p class="meta-text">
                        📁 {row.get("category", "N/A")} |
                        📄 {row.get("article_count", 0)} 篇文章 |
                        ⏰ {row.get("created_at", "N/A")[:10]}
                    </p>
                </div>
                """,
                    unsafe_allow_html=True,
                )

                cluster_id = int(row["id"]) if pd.notna(row.get("id")) else None
                primary_link = row.get("primary_link")
                if not primary_link and cluster_id:
                    candidates = top_links_map.get(cluster_id, [])
                    primary_link = candidates[0]["url"] if candidates else ""

                if primary_link:
                    render_external_link("查看英文原文", primary_link)

    # 最新信号
    st.markdown("### 📡 最新信号")

    if signals_df.empty:
        st.info("暂无信号数据")
    else:
        for idx, row in signals_df.head(5).iterrows():
            confidence = row.get("confidence", 0)
            explanation = parse_signal_explanation(row)
            alert_level = str(
                row.get("alert_level") or explanation.get("alert_level") or ""
            ).strip().upper()
            if alert_level in {"L4", "L3"}:
                level_class = "signal-high"
                level_text = alert_level
            elif alert_level == "L2":
                level_class = "signal-medium"
                level_text = alert_level
            elif alert_level == "L1":
                level_class = "signal-low"
                level_text = alert_level
            elif confidence >= 0.8:
                level_class = "signal-high"
                level_text = "高"
            elif confidence >= 0.6:
                level_class = "signal-medium"
                level_text = "中"
            else:
                level_class = "signal-low"
                level_text = "低"

            signal_name = get_signal_name(row)
            event_text = format_related_events(explanation.get("events", []), limit=2)
            compact_why = short_text(explanation.get("why", ""), 68)
            compact_meaning = short_text(explanation.get("meaning", ""), 68)
            compact_events = short_text(event_text or "无可用关联事件", 56)
            created_at = str(row.get("created_at", "N/A"))[:16]

            st.markdown(
                f"""
            <div class="hotspot-card">
                <h5>
                    {html.escape(str(row.get("icon", "⚡")))} {html.escape(signal_name)}
                    <span class="signal-badge {level_class}">{level_text}</span>
                </h5>
                <p class="meta-text">
                    置信度: {confidence:.2f} | 时间: {html.escape(created_at)}
                </p>
                <p><strong>原因:</strong> {html.escape(compact_why)}</p>
                <p><strong>含义:</strong> {html.escape(compact_meaning)}</p>
                <p class="meta-text">关联: {html.escape(compact_events)}</p>
            </div>
            """,
                unsafe_allow_html=True,
            )


# 热点详情页
def render_hotspots(supabase, hours: int, category: str):
    """渲染热点详情页"""
    st.markdown('<div class="main-header">🔥 热点详情</div>', unsafe_allow_html=True)

    clusters_df = get_clusters(supabase, hours, category, only_hot=True)

    if clusters_df.empty:
        st.info("暂无热点数据")
        return

    cluster_ids = tuple(
        int(cluster_id)
        for cluster_id in clusters_df["id"].tolist()
        if pd.notna(cluster_id)
    )
    links_map = get_cluster_article_links(supabase, cluster_ids, per_cluster=3)

    # 分类标签
    tabs = st.tabs(["全部", "军事", "政治", "经济"])
    categories = [None, "military", "politics", "economy"]

    for tab, cat in zip(tabs, categories):
        with tab:
            if cat:
                filtered_df = clusters_df[clusters_df["category"] == cat]
            else:
                filtered_df = clusters_df

            st.write(f"共 {len(filtered_df)} 个热点")

            for idx, row in filtered_df.iterrows():
                with st.expander(f"📰 {row.get('primary_title', 'N/A')}"):
                    st.markdown(f"**中文摘要:**")
                    st.write(row.get("summary", "N/A"))

                    st.markdown(f"**关键实体:**")
                    try:
                        raw_entities = row.get("key_entities", "[]")
                        entities = (
                            raw_entities
                            if isinstance(raw_entities, list)
                            else json.loads(raw_entities)
                        )
                        if entities:
                            st.write(", ".join(entities))
                        else:
                            st.write("无")
                    except Exception:
                        st.write("无")

                    st.markdown(f"**影响分析:**")
                    st.write(row.get("impact", "暂无分析"))

                    st.markdown(f"**趋势判断:**")
                    st.write(row.get("trend", "暂无判断"))

                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"📁 分类: {row.get('category', 'N/A')}")
                        st.write(f"📄 文章数: {row.get('article_count', 0)}")
                    with col2:
                        st.write(f"⏰ 创建时间: {row.get('created_at', 'N/A')[:16]}")

                    cluster_id = int(row["id"]) if pd.notna(row.get("id")) else None
                    primary_link = row.get("primary_link")
                    article_links = links_map.get(cluster_id, []) if cluster_id else []
                    if not primary_link and article_links:
                        primary_link = article_links[0]["url"]

                    if primary_link:
                        render_external_link("查看主原文", primary_link)

                    if article_links:
                        st.markdown("**相关新闻原文:**")
                        for link_idx, link in enumerate(article_links[:3], 1):
                            title = (link.get("title") or "原文链接").strip()[:80]
                            render_external_link(
                                f"原文{link_idx}: {title}",
                                link.get("url", ""),
                            )


# 信号中心页
def render_signals(supabase, hours: int):
    """渲染信号中心页"""
    st.markdown('<div class="main-header">📡 信号中心</div>', unsafe_allow_html=True)

    signals_df = get_signals(supabase, hours)

    if signals_df.empty:
        st.info("暂无信号数据")
        return

    # 信号类型筛选
    signal_types = signals_df["signal_type"].unique().tolist()
    selected_type = st.selectbox("信号类型:", ["全部"] + signal_types)

    if selected_type != "全部":
        signals_df = signals_df[signals_df["signal_type"] == selected_type]

    # 置信度筛选
    min_confidence = st.slider("最小置信度:", 0.0, 1.0, 0.5, 0.1)
    signals_df = signals_df[signals_df["confidence"] >= min_confidence]

    col_a, col_b = st.columns([1, 1])
    with col_a:
        view_mode = st.radio(
            "展示模式:",
            ["精简", "详细"],
            horizontal=True,
            index=0,
        )
    with col_b:
        max_per_type = st.slider("同类型最多显示:", 1, 20, 5, 1)

    if "signal_type" in signals_df.columns:
        type_counts = signals_df["signal_type"].value_counts()
        if not type_counts.empty:
            dominant_type = type_counts.index[0]
            dominant_count = int(type_counts.iloc[0])
            if dominant_count >= 10 and dominant_count >= len(signals_df) * 0.7:
                st.warning(
                    f"当前信号高度集中在 `{dominant_type}`（{dominant_count}/{len(signals_df)}）。"
                    "已按同类型上限做压缩展示。"
                )
        signals_df = (
            signals_df.sort_values("confidence", ascending=False)
            .groupby("signal_type", group_keys=False)
            .head(max_per_type)
            .reset_index(drop=True)
        )

    st.write(f"当前展示 {len(signals_df)} 个信号")

    parsed_signals: List[Tuple[int, pd.Series, Dict]] = []
    related_cluster_ids = set()
    for idx, row in signals_df.iterrows():
        explanation = parse_signal_explanation(row)
        parsed_signals.append((idx, row, explanation))
        for event in explanation.get("events", []):
            if not isinstance(event, dict):
                continue
            cluster_id_raw = event.get("cluster_id")
            if isinstance(cluster_id_raw, int):
                related_cluster_ids.add(cluster_id_raw)
            elif isinstance(cluster_id_raw, str) and cluster_id_raw.isdigit():
                related_cluster_ids.add(int(cluster_id_raw))

    related_links_map = get_cluster_article_links(
        supabase, tuple(sorted(related_cluster_ids)), per_cluster=1
    )

    # 显示信号列表
    for idx, row, explanation in parsed_signals:
        confidence = row.get("confidence", 0)

        if confidence >= 0.8:
            level_color = "#ff4b4b"
        elif confidence >= 0.6:
            level_color = "#ffa500"
        else:
            level_color = "#4caf50"

        signal_name = get_signal_name(row)
        event_text = format_related_events(explanation.get("events", []), limit=3)

        if view_mode == "精简":
            compact_event = short_text(event_text or "无可用关联事件", 72)
            compact_reason = short_text(explanation["why"], 90)
            compact_meaning = short_text(explanation["meaning"], 90)
            st.markdown(
                f"""
            <div class="hotspot-card" style="border-left: 4px solid {level_color};">
                <h4>{row.get("icon", "⚡")} {signal_name}</h4>
                <p><strong>事件:</strong> {compact_event}</p>
                <p><strong>触发:</strong> {compact_reason}</p>
                <p><strong>含义:</strong> {compact_meaning}</p>
                <p class="meta-text">
                    置信度: {confidence:.2f} | 时间: {row.get("created_at", "N/A")[:16]}
                </p>
            </div>
            """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
            <div class="hotspot-card" style="border-left: 4px solid {level_color};">
                <h4>{row.get("icon", "⚡")} {signal_name}</h4>
                <p><strong>触发原因:</strong> {explanation["why"]}</p>
                <p><strong>代表含义:</strong> {explanation["meaning"]}</p>
                <p><strong>建议动作:</strong> {explanation["action"]}</p>
                <p><strong>关联事件:</strong> {event_text or "无可用关联事件"}</p>
                <p>
                    <span style="color: {level_color}; font-weight: bold;">
                        置信度: {confidence:.2f}
                    </span> |
                    <span class="meta-text">时间: {row.get("created_at", "N/A")[:16]}</span> |
                    <span class="meta-text">依据: {explanation["confidence_reason"]}</span>
                </p>
            </div>
            """,
                unsafe_allow_html=True,
            )

        event_links = get_related_event_links(
            explanation.get("events", []), related_links_map
        )
        if event_links:
            st.markdown("**关联事件原文:**")
            for link_idx, event_link in enumerate(event_links[:3], 1):
                event_title = event_link.get("title", "关联事件原文")[:80]
                event_url = event_link.get("url", "")
                if event_url:
                    render_external_link(f"事件{link_idx}: {event_title}", event_url)
                else:
                    st.write(f"- {event_title}（暂无原文链接）")

    # 信号统计图表
    if not signals_df.empty:
        st.markdown("### 📊 信号统计")

        col1, col2 = st.columns(2)

        with col1:
            # 按类型统计
            type_counts = signals_df["signal_type"].value_counts()
            st.bar_chart(type_counts)

        with col2:
            # 按置信度分布
            conf_dist = pd.cut(
                signals_df["confidence"],
                bins=[0, 0.6, 0.8, 1.0],
                labels=["低", "中", "高"],
            ).value_counts()
            st.bar_chart(conf_dist)


def render_monitor(supabase, hours: int):
    """渲染哨兵态势页。"""
    st.markdown('<div class="main-header">🛰️ 哨兵态势</div>', unsafe_allow_html=True)

    watchlist_df = get_watchlist_signals(supabase, hours)
    if watchlist_df.empty:
        st.info("最近时间窗口内暂无哨兵告警。")
        return

    records = [normalize_watchlist_record(row) for _, row in watchlist_df.iterrows()]
    records_df = pd.DataFrame(records)
    records_df["created_dt"] = pd.to_datetime(records_df["created_at"], errors="coerce")
    records_df = records_df.sort_values("created_dt", ascending=False)

    l34_count = int(records_df["alert_level"].isin(["L3", "L4"]).sum())
    sentinel_count = int(records_df["sentinel_id"].nunique())
    latest_time = records_df["created_dt"].max()
    latest_text = "N/A" if pd.isna(latest_time) else str(latest_time)[:16]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("告警总数", len(records_df))
    with col2:
        st.metric("L3/L4", l34_count)
    with col3:
        st.metric("哨兵数量", sentinel_count)
    with col4:
        st.metric("最新告警", latest_text)

    levels = ["L1", "L2", "L3", "L4"]
    selected_levels = st.multiselect("等级筛选", levels, default=levels)
    sentinel_options = ["全部"] + sorted(records_df["sentinel_name"].dropna().unique().tolist())
    selected_sentinel = st.selectbox("哨兵筛选", sentinel_options)

    filtered_df = records_df[records_df["alert_level"].isin(selected_levels)]
    if selected_sentinel != "全部":
        filtered_df = filtered_df[filtered_df["sentinel_name"] == selected_sentinel]

    if filtered_df.empty:
        st.info("筛选条件下暂无告警。")
        return

    st.markdown("### 场景态势卡")
    latest_df = (
        filtered_df.sort_values("created_dt", ascending=False)
        .drop_duplicates(subset=["sentinel_id"])
        .reset_index(drop=True)
    )

    columns = st.columns(2)
    for idx, (_, row) in enumerate(latest_df.iterrows()):
        level = str(row.get("alert_level", "L1")).upper()
        card_color = WATCHLIST_LEVEL_COLORS.get(level, "#8ea0bf")
        with columns[idx % 2]:
            st.markdown(
                f"""
<div class="hotspot-card" style="border-left: 4px solid {card_color};">
  <h4>{html.escape(str(row.get("sentinel_name", "场景哨兵")))} · {level}</h4>
  <p><strong>风险分:</strong> {float(row.get("risk_score", 0.0)):.2f}</p>
  <p class="meta-text">时间: {str(row.get("created_at", "N/A"))[:16]}</p>
  <p><strong>建议动作:</strong> {html.escape(str(row.get("suggested_action", "")))}</p>
</div>
""",
                unsafe_allow_html=True,
            )
            reasons = row.get("trigger_reasons", [])
            if isinstance(reasons, list) and reasons:
                st.markdown("**触发原因**")
                for reason in reasons[:4]:
                    st.write(f"- {reason}")
            entities = row.get("related_entities", [])
            if isinstance(entities, list) and entities:
                st.caption(f"相关实体: {', '.join([str(item) for item in entities[:8]])}")
            next_review = str(row.get("next_review_time", "")).strip()
            if next_review:
                st.caption(f"下次复核: {next_review[:16]}")
            links = row.get("evidence_links", [])
            if isinstance(links, list) and links:
                for link_idx, link in enumerate(links[:3], 1):
                    render_external_link(f"证据链接 {link_idx}", str(link))

    st.markdown("### 等级分布")
    level_counts = (
        filtered_df["alert_level"].value_counts().reindex(["L4", "L3", "L2", "L1"]).fillna(0)
    )
    st.bar_chart(level_counts)

    st.markdown("### 告警明细")
    detail_df = filtered_df[
        [
            "created_at",
            "sentinel_name",
            "alert_level",
            "risk_score",
            "confidence",
            "description",
        ]
    ].rename(
        columns={
            "created_at": "时间",
            "sentinel_name": "哨兵",
            "alert_level": "等级",
            "risk_score": "风险分",
            "confidence": "置信度",
            "description": "摘要",
        }
    )
    st.dataframe(detail_df, use_container_width=True, hide_index=True)


def render_graph(supabase, hours: int):
    """渲染实体关系图谱页。"""
    st.markdown('<div class="main-header">🕸️ 关系图谱</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        min_confidence = st.slider("最小置信度", 0.3, 1.0, 0.55, 0.05)
    with col2:
        min_source_count = st.slider("最小来源数", 1, 10, 1, 1)
    with col3:
        limit = st.slider("最大关系数", 100, 800, 400, 50)

    search_term = st.text_input("搜索实体/关系关键词", "")

    graph_df = get_entity_relations_graph(
        supabase,
        min_confidence=min_confidence,
        limit=limit,
    )
    if graph_df.empty:
        st.info("暂无可展示的实体关系数据。")
        return

    graph_df = graph_df[graph_df["source_count"] >= min_source_count]
    if search_term.strip():
        pattern = search_term.strip().lower()
        graph_df = graph_df[
            graph_df["entity1_name"].str.lower().str.contains(pattern, na=False)
            | graph_df["entity2_name"].str.lower().str.contains(pattern, na=False)
            | graph_df["relation_text"].str.lower().str.contains(pattern, na=False)
        ]

    watchlist_df = get_watchlist_signals(supabase, hours=72)
    watchlist_entities = set()
    for _, row in watchlist_df.iterrows():
        normalized = normalize_watchlist_record(row)
        for entity in normalized.get("related_entities", []):
            watchlist_entities.add(str(entity).strip().lower())

    graph_df["watchlist_related"] = graph_df.apply(
        lambda row: (
            str(row.get("entity1_name", "")).lower() in watchlist_entities
            or str(row.get("entity2_name", "")).lower() in watchlist_entities
        ),
        axis=1,
    )
    only_watchlist_related = st.checkbox("仅显示哨兵相关关系", value=False)
    if only_watchlist_related:
        graph_df = graph_df[graph_df["watchlist_related"]]

    if graph_df.empty:
        st.info("筛选条件下暂无关系数据。")
        return

    unique_entities = pd.unique(
        pd.concat([graph_df["entity1_name"], graph_df["entity2_name"]], ignore_index=True)
    )
    avg_conf = float(graph_df["confidence"].mean() or 0.0)
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("关系数量", len(graph_df))
    with col_b:
        st.metric("实体数量", len(unique_entities))
    with col_c:
        st.metric("平均置信度", f"{avg_conf:.2f}")

    st.markdown("### 关系表")
    table_df = graph_df[
        [
            "entity1_name",
            "entity1_type",
            "relation_text",
            "entity2_name",
            "entity2_type",
            "confidence",
            "source_count",
            "watchlist_related",
        ]
    ].sort_values(["watchlist_related", "confidence", "source_count"], ascending=False)
    st.dataframe(table_df, use_container_width=True, hide_index=True)

    st.markdown("### 图谱预览")
    preview_df = graph_df.sort_values(
        ["watchlist_related", "source_count", "confidence"],
        ascending=False,
    ).head(80)

    def _dot_escape(text: str) -> str:
        return str(text or "").replace("\\", "\\\\").replace('"', '\\"')

    node_types: Dict[str, str] = {}
    for _, row in preview_df.iterrows():
        left_name = str(row.get("entity1_name", "")).strip()
        right_name = str(row.get("entity2_name", "")).strip()
        if left_name and left_name not in node_types:
            node_types[left_name] = str(row.get("entity1_type", "other"))
        if right_name and right_name not in node_types:
            node_types[right_name] = str(row.get("entity2_type", "other"))

    lines = [
        "digraph Relations {",
        "rankdir=LR;",
        'node [shape=ellipse, style=filled, fillcolor="#111c34",'
        ' color="#1f2d49", fontcolor="#e6edf7"];',
        'edge [color="#8bd3ff", fontcolor="#8ea0bf"];',
    ]

    for entity_name, entity_type in list(node_types.items())[:120]:
        label = _dot_escape(f"{entity_name}\\n({entity_type})")
        lines.append(f'"{_dot_escape(entity_name)}" [label="{label}"];')

    for _, row in preview_df.iterrows():
        left_name = str(row.get("entity1_name", "")).strip()
        right_name = str(row.get("entity2_name", "")).strip()
        if not left_name or not right_name:
            continue
        rel_text = short_text(str(row.get("relation_text", "")), 24)
        conf = float(row.get("confidence", 0.0) or 0.0)
        source_count = int(row.get("source_count", 0) or 0)
        edge_label = _dot_escape(f"{rel_text} | {conf:.2f} | {source_count}")
        penwidth = 1.0 + min(3.0, conf * 2.0) + min(2.0, source_count * 0.15)
        lines.append(
            f'"{_dot_escape(left_name)}" -> "{_dot_escape(right_name)}" '
            f'[label="{edge_label}", penwidth={penwidth:.2f}];'
        )

    lines.append("}")
    dot_graph = "\n".join(lines)

    try:
        st.graphviz_chart(dot_graph, use_container_width=True)
    except Exception as e:
        st.warning(f"图谱渲染失败，已降级为列表展示: {str(e)[:100]}")

    st.markdown("### 关系详情")
    for _, row in preview_df.head(20).iterrows():
        left_name = str(row.get("entity1_name", "N/A"))
        right_name = str(row.get("entity2_name", "N/A"))
        relation_text = str(row.get("relation_text", ""))
        confidence = float(row.get("confidence", 0.0) or 0.0)
        source_count = int(row.get("source_count", 0) or 0)
        with st.expander(f"{left_name} → {right_name} ({confidence:.2f})"):
            st.write(f"关系描述: {relation_text}")
            st.write(f"来源数: {source_count}")
            st.write(f"最后出现: {str(row.get('last_seen', 'N/A'))[:16]}")
            if bool(row.get("watchlist_related")):
                st.caption("该关系与最近哨兵告警实体存在交集。")
            source_article_ids = row.get("source_article_ids", [])
            if not isinstance(source_article_ids, list):
                source_article_ids = parse_json_field(source_article_ids, list)
            if source_article_ids:
                st.caption(f"样本文章ID: {', '.join([str(i) for i in source_article_ids[:8]])}")


def update_entities(supabase, cluster_id: int, entities: list, category: str):
    """更新实体表和实体-聚类关联表"""
    try:
        normalized_entities = normalize_entity_mentions(entities)
        for entity in normalized_entities:
            entity_name = entity["canonical_name"]
            entity_type = entity["entity_type"]
            metadata = merge_entity_metadata(
                existing_metadata={},
                entity=entity,
                model_name="qwen-plus",
                prompt_version="cluster_summary_v2",
            )

            # 检查实体是否已存在
            existing = (
                supabase.table("entities")
                .select("id, mention_count_total, metadata")
                .eq("name", entity_name)
                .eq("entity_type", entity_type)
                .execute()
            )

            if existing.data:
                # 更新现有实体
                entity_id = existing.data[0]["id"]
                new_count = existing.data[0]["mention_count_total"] + 1
                metadata = merge_entity_metadata(
                    existing_metadata=existing.data[0].get("metadata"),
                    entity=entity,
                    model_name="qwen-plus",
                    prompt_version="cluster_summary_v2",
                )

                supabase.table("entities").update(
                    {
                        "last_seen": datetime.now().isoformat(),
                        "mention_count_total": new_count,
                        "category": category,
                        "metadata": metadata,
                    }
                ).eq("id", entity_id).execute()
            else:
                # 创建新实体
                result = (
                    supabase.table("entities")
                    .insert(
                        {
                            "name": entity_name,
                            "entity_type": entity_type,
                            "category": category,
                            "mention_count_total": 1,
                            "metadata": metadata,
                        }
                    )
                    .execute()
                )
                entity_id = result.data[0]["id"]

            # 创建或更新实体-聚类关联
            try:
                supabase.table("entity_cluster_relations").upsert(
                    {
                        "entity_id": entity_id,
                        "cluster_id": cluster_id,
                        "mention_count": 1,
                    }
                ).execute()
            except Exception as e:
                logger.warning(f"实体关联创建失败（可能已存在）: {e}")

        logger.info(f"实体更新完成: {len(normalized_entities)} 个实体")
    except Exception as e:
        logger.error(f"更新实体失败: {e}")


# 实体数据获取函数
@st.cache_data(ttl=300)
def get_entities(
    _supabase, entity_type: str = None, category: str = None, limit: int = 50
) -> pd.DataFrame:
    """获取实体列表"""
    query = _supabase.table("entities").select("*")

    if entity_type and entity_type != "全部":
        query = query.eq("entity_type", entity_type)
    if category and category != "全部":
        query = query.eq("category", category)

    result = query.order("mention_count_total", desc=True).limit(limit).execute()

    if result.data:
        return pd.DataFrame(result.data)
    return pd.DataFrame()


@st.cache_data(ttl=300)
def get_entity_related_clusters(
    _supabase, entity_id: int, limit: int = 10
) -> pd.DataFrame:
    """获取实体关联的聚类"""
    # 获取关联的聚类ID
    relations = (
        _supabase.table("entity_cluster_relations")
        .select("cluster_id")
        .eq("entity_id", entity_id)
        .limit(limit)
        .execute()
    )

    if not relations.data:
        return pd.DataFrame()

    cluster_ids = [r["cluster_id"] for r in relations.data]

    # 获取聚类详情
    clusters = (
        _supabase.table("analysis_clusters")
        .select("id, primary_title, summary, category, created_at, article_count")
        .in_("id", cluster_ids)
        .execute()
    )

    if clusters.data:
        return pd.DataFrame(clusters.data)
    return pd.DataFrame()


@st.cache_data(ttl=300)
def get_trending_entities(_supabase, hours: int = 24, limit: int = 10) -> pd.DataFrame:
    """获取趋势上升的实体"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    result = (
        _supabase.table("entities")
        .select("*")
        .gte("last_seen", cutoff)
        .eq("trend_direction", "rising")
        .order("mention_count_24h", desc=True)
        .limit(limit)
        .execute()
    )

    if result.data:
        return pd.DataFrame(result.data)
    return pd.DataFrame()


# 实体档案页
def render_entities(supabase):
    """渲染实体档案页"""
    st.markdown('<div class="main-header">📁 实体档案</div>', unsafe_allow_html=True)

    # 获取筛选条件
    col1, col2 = st.columns(2)
    with col1:
        entity_type = st.selectbox(
            "实体类型:",
            ["全部"] + ENTITY_TYPE_FILTER_OPTIONS,
        )
    with col2:
        category = st.selectbox(
            "所属分类:", ["全部", "military", "politics", "economy", "tech"]
        )

    # 获取实体列表
    entities_df = get_entities(supabase, entity_type, category, limit=100)

    if entities_df.empty:
        st.info("暂无实体数据")
        return

    # 显示热门实体
    st.markdown("### 🔥 热门实体")

    top_entities = entities_df.head(10)
    cols = st.columns(5)
    for idx, (_, row) in enumerate(top_entities.iterrows()):
        with cols[idx % 5]:
            mention_count = row.get("mention_count_total", 0)
            st.metric(label=row.get("name", "N/A")[:15], value=f"{mention_count}次")

    st.markdown("---")

    # 实体列表
    st.markdown("### 📋 实体列表")

    for idx, row in entities_df.iterrows():
        entity_id = row.get("id")
        entity_name = row.get("name", "N/A")
        entity_type_val = row.get("entity_type", "未知")
        mention_count = row.get("mention_count_total", 0)
        last_seen = row.get("last_seen", "N/A")

        # 趋势指示
        trend = row.get("trend_direction", "stable")
        trend_icon = "📈" if trend == "rising" else "📉" if trend == "falling" else "➡️"

        with st.expander(
            f"{trend_icon} {entity_name} ({entity_type_val}) - 提及{mention_count}次"
        ):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**类型:** {entity_type_val}")
                st.write(f"**分类:** {row.get('category', 'N/A')}")
            with col2:
                st.write(f"**24h提及:** {row.get('mention_count_24h', 0)}")
                st.write(f"**7天提及:** {row.get('mention_count_7d', 0)}")
            with col3:
                st.write(f"**趋势:** {trend}")
                st.write(f"**最后出现:** {str(last_seen)[:10] if last_seen else 'N/A'}")

            # 显示关联聚类
            st.markdown("**相关热点:**")
            related_clusters = get_entity_related_clusters(supabase, entity_id, limit=5)
            if not related_clusters.empty:
                for _, cluster in related_clusters.iterrows():
                    st.write(f"- {cluster.get('primary_title', 'N/A')}")
            else:
                st.write("暂无关联热点")

    # 实体统计图表
    st.markdown("---")
    st.markdown("### 📊 实体统计")

    col1, col2 = st.columns(2)
    with col1:
        # 按类型统计
        if not entities_df.empty and "entity_type" in entities_df.columns:
            type_counts = entities_df["entity_type"].value_counts()
            st.bar_chart(type_counts)
    with col2:
        # 按提及次数分布
        if not entities_df.empty and "mention_count_total" in entities_df.columns:
            mention_dist = pd.cut(
                entities_df["mention_count_total"],
                bins=[0, 1, 5, 10, 50, 1000],
                labels=["1次", "2-5次", "6-10次", "11-50次", "50+次"],
            ).value_counts()
            st.bar_chart(mention_dist)


# 数据统计页
def render_stats(supabase):
    """渲染数据统计页"""
    st.markdown('<div class="main-header">📈 数据统计</div>', unsafe_allow_html=True)

    # 获取统计数据
    stats = get_stats(supabase)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("总文章数", f"{stats['articles_total']:,}")
    with col2:
        st.metric(
            "已分析文章", f"{stats['articles_total'] - stats['articles_unanalyzed']:,}"
        )
    with col3:
        st.metric("待分析文章", stats["articles_unanalyzed"])

    st.markdown("---")

    # 聚类趋势
    st.markdown("### 📊 聚类趋势 (最近7天)")

    # 获取7天数据
    days_7 = (datetime.now() - timedelta(days=7)).isoformat()
    clusters_7d = (
        supabase.table("analysis_clusters")
        .select("created_at, category")
        .gte("created_at", days_7)
        .execute()
    )

    if clusters_7d.data:
        df = pd.DataFrame(clusters_7d.data)
        df["created_at"] = pd.to_datetime(df["created_at"]).dt.date

        # 按天和分类统计
        daily_counts = (
            df.groupby(["created_at", "category"]).size().unstack(fill_value=0)
        )
        st.line_chart(daily_counts)
    else:
        st.info("暂无数据")

    # 分类占比
    st.markdown("### 🥧 分类占比")

    all_clusters = supabase.table("analysis_clusters").select("category").execute()
    if all_clusters.data:
        df = pd.DataFrame(all_clusters.data)
        cat_counts = df["category"].value_counts()
        # 使用条形图代替饼图
        st.bar_chart(cat_counts)


# 主函数
def main():
    """主函数"""
    # 初始化 Supabase
    supabase = init_supabase()

    if not supabase:
        st.error("无法连接到数据库。请检查配置。")
        return

    # 渲染侧边栏
    page, hours, category = render_sidebar()

    # 根据页面渲染内容
    if page == "🏠 概览首页":
        render_overview(supabase, hours, category)
    elif page == "🛰️ 哨兵态势":
        render_monitor(supabase, hours)
    elif page == "🕸️ 关系图谱":
        render_graph(supabase, hours)
    elif page == "🔥 热点详情":
        render_hotspots(supabase, hours, category)
    elif page == "📡 信号中心":
        render_signals(supabase, hours)
    elif page == "📁 实体档案":
        render_entities(supabase)
    elif page == "📈 数据统计":
        render_stats(supabase)


if __name__ == "__main__":
    main()
