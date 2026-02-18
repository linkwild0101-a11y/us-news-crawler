#!/usr/bin/env python3
"""
US-Monitor UI 仪表板
使用 Streamlit 构建中文界面
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from supabase import create_client

from config.entity_config import (
    ENTITY_TYPES,
    PERSON_RULES,
    DETECTION_PRIORITY,
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

# 主题配置 - 简洁黑白风，高对比度
THEME = {
    "bg_main": "#111111",
    "bg_card": "#1a1a1a",
    "bg_sidebar": "#0d0d0d",
    "text_main": "#ffffff",
    "text_body": "#e0e0e0",
    "text_muted": "#888888",
    "primary": "#ffffff",
    "accent": "#00ff88",
    "border": "#333333",
}


# 生成 CSS
def get_css():
    t = THEME
    return f"""
<style>
    /* Streamlit 全局覆盖 */
    .stApp {{
        background: {t["bg_main"]};
    }}
    
    /* 侧边栏 */
    [data-testid="stSidebar"] {{
        background: {t["bg_sidebar"]};
    }}
    
    /* 所有文字白色高亮 */
    .stMarkdown, .stText, p, h1, h2, h3, h4, h5, h6, label {{
        color: {t["text_main"]} !important;
    }}
    
    /* 主标题 */
    .main-header {{
        font-size: 2rem;
        font-weight: 700;
        color: {t["text_main"]};
        margin-bottom: 1.5rem;
        border-bottom: 2px solid {t["accent"]};
        padding-bottom: 0.5rem;
    }}
    
    /* 指标卡片 */
    [data-testid="stMetric"] {{
        background: {t["bg_card"]};
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid {t["border"]};
    }}
    
    [data-testid="stMetricLabel"] {{
        color: {t["text_muted"]} !important;
    }}
    
    [data-testid="stMetricValue"] {{
        color: {t["text_main"]} !important;
    }}
    
    /* 热点卡片 */
    .hotspot-card {{
        background: {t["bg_card"]};
        padding: 1.25rem;
        border-radius: 8px;
        border: 1px solid {t["border"]};
        margin-bottom: 1rem;
        border-left: 3px solid {t["accent"]};
    }}
    
    .hotspot-card h4 {{
        color: {t["text_main"]};
        font-weight: 600;
        font-size: 1.1rem;
        margin-bottom: 0.75rem;
    }}
    
    .hotspot-card h5 {{
        color: {t["text_body"]};
        font-weight: 600;
    }}
    
    .hotspot-card p {{
        color: {t["text_body"]};
        font-size: 0.95rem;
    }}
    
    .hotspot-card .meta-text {{
        color: {t["text_muted"]};
        font-size: 0.85rem;
    }}
    
    /* 信号徽章 */
    .signal-high {{
        color: #ff6b6b;
    }}
    .signal-medium {{
        color: #ffd93d;
    }}
    .signal-low {{
        color: #6bcb77;
    }}
    
    /* 分割线 */
    hr {{
        border: none;
        height: 1px;
        background: {t["border"]};
        margin: 1.5rem 0;
    }}
    
    /* 滚动条 */
    ::-webkit-scrollbar {{
        width: 6px;
    }}
    ::-webkit-scrollbar-track {{
        background: {t["bg_main"]};
    }}
    ::-webkit-scrollbar-thumb {{
        background: {t["border"]};
    }}
    
    /* 按钮 */
    .stButton > button {{
        background: {t["bg_card"]};
        color: {t["text_main"]};
        border: 1px solid {t["border"]};
    }}
    .stButton > button:hover {{
        background: {t["border"]};
    }}
    
    /* 下拉框 */
    .stSelectbox > div > div {{
        background: {t["bg_card"]};
        color: {t["text_main"]};
    }}
    
    /* 单选按钮 */
    .stRadio > div {{
        color: {t["text_body"]};
    }}
    
    /* 链接按钮 */
    .stLinkButton > button {{
        background: transparent;
        border: 1px solid {t["accent"]};
        color: {t["accent"]} !important;
    }}
    .stLinkButton > button:hover {{
        background: {t["accent"]};
        color: {t["bg_main"]} !important;
    }}
    
    /* 展开框 */
    .streamlit-expanderHeader {{
        color: {t["text_body"]} !important;
        background: {t["bg_card"]};
    }}
    
    /* 表格 */
    .stDataFrame {{
        background: {t["bg_card"]};
    }}
    
    /* 图表 */
    [data-testid="stChart"] {{
        background: {t["bg_card"]};
    }}
    
    /* 分类标签 */
    .category-military {{ color: #ff6b6b; font-weight: 600; }}
    .category-politics {{ color: #a78bfa; font-weight: 600; }}
    .category-economy {{ color: #6bcb77; font-weight: 600; }}
    
    /* 快速翻译徽章 */
    .shallow-badge {{
        background: #ffd93d;
        color: #1a1a1a;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        margin-left: 8px;
    }}
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
def get_clusters(_supabase, hours: int = 24, category: str = None) -> pd.DataFrame:
    """获取聚类数据"""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    query = _supabase.table("analysis_clusters").select("*").gte("created_at", cutoff)

    if category and category != "全部":
        query = query.eq("category", category)

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
        ["🏠 概览首页", "🔥 热点详情", "📡 信号中心", "📁 实体档案", "📈 数据统计"],
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚙️ 设置")

    time_range = st.sidebar.selectbox("时间范围:", ["24小时", "7天", "30天"], index=0)

    hours_map = {"24小时": 24, "7天": 168, "30天": 720}

    category = st.sidebar.selectbox(
        "分类筛选:", ["全部", "military", "politics", "economy"]
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
    clusters_df = get_clusters(supabase, hours, category)
    signals_df = get_signals(supabase, hours)

    # 最新热点
    st.markdown("### 🔥 最新热点 (TOP 5)")

    if clusters_df.empty:
        st.info("暂无热点数据")
    else:
        for idx, row in clusters_df.head(5).iterrows():
            with st.container():
                # 判断分析深度
                is_shallow = row.get("analysis_depth") == "shallow"
                depth_badge = (
                    "<span style='background-color: rgba(245, 158, 11, 0.3); color: #fbbf24; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; margin-left: 8px;'>快速翻译</span>"
                    if is_shallow
                    else ""
                )

                st.markdown(
                    f"""
                <div class="hotspot-card">
                    <h4>{row.get("primary_title", "N/A")[:80]}...{depth_badge}</h4>
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

                # 根据分析深度显示不同按钮
                col1, col2 = st.columns([1, 1])
                with col1:
                    if row.get("primary_link"):
                        st.link_button("🔗 查看英文原文", row["primary_link"])
                with col2:
                    if is_shallow:
                        # 浅层分析显示深度分析按钮
                        if st.button(
                            f"🔍 深度分析", key=f"deep_analysis_{row.get('id')}"
                        ):
                            with st.spinner("正在进行深度分析，请稍候..."):
                                try:
                                    # 调用后端API进行深度分析
                                    result = trigger_deep_analysis(
                                        supabase, row.get("id")
                                    )
                                    if result:
                                        st.success("✅ 深度分析完成！")
                                        st.rerun()
                                    else:
                                        st.error("❌ 分析失败，请稍后重试")
                                except Exception as e:
                                    st.error(f"❌ 分析出错: {str(e)}")

    # 最新信号
    st.markdown("### 📡 最新信号")

    if signals_df.empty:
        st.info("暂无信号数据")
    else:
        for idx, row in signals_df.head(5).iterrows():
            confidence = row.get("confidence", 0)
            if confidence >= 0.8:
                level_class = "signal-high"
                level_text = "高"
            elif confidence >= 0.6:
                level_class = "signal-medium"
                level_text = "中"
            else:
                level_class = "signal-low"
                level_text = "低"

            # 获取信号名称，如果没有name字段，使用signal_type转换
            signal_name = row.get("name")
            if not signal_name or signal_name == "N/A":
                signal_type = row.get("signal_type", "unknown")
                # 信号类型到中文名称的映射
                type_names = {
                    "velocity_spike": "🚀 速度激增",
                    "convergence": "🔄 多源聚合",
                    "triangulation": "📐 三角验证",
                    "hotspot_escalation": "🔥 热点升级",
                    "economic_indicator_alert": "📊 经济指标异常",
                    "natural_disaster_signal": "🌋 自然灾害",
                    "geopolitical_intensity": "🌍 地缘政治紧张",
                }
                signal_name = type_names.get(signal_type, f"⚡ {signal_type}")

            st.markdown(
                f"""
            <div class="hotspot-card">
                <h5>
                    {row.get("icon", "⚡")} {signal_name}
                    <span class="signal-badge {level_class}">{level_text} 置信度</span>
                </h5>
                <p>{row.get("description", "N/A")[:100]}...</p>
                <p class="meta-text">
                    置信度: {confidence:.2f} | 时间: {row.get("created_at", "N/A")[:16]}
                </p>
            </div>
            """,
                unsafe_allow_html=True,
            )


# 热点详情页
def render_hotspots(supabase, hours: int, category: str):
    """渲染热点详情页"""
    st.markdown('<div class="main-header">🔥 热点详情</div>', unsafe_allow_html=True)

    clusters_df = get_clusters(supabase, hours, category)

    if clusters_df.empty:
        st.info("暂无热点数据")
        return

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
                with st.expander(f"📰 {row.get('primary_title', 'N/A')[:60]}..."):
                    st.markdown(f"**中文摘要:**")
                    st.write(row.get("summary", "N/A"))

                    st.markdown(f"**关键实体:**")
                    try:
                        entities = eval(row.get("key_entities", "[]"))
                        if entities:
                            st.write(", ".join(entities))
                        else:
                            st.write("无")
                    except:
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
                        if row.get("primary_link"):
                            st.link_button("🔗 查看原文", row["primary_link"])


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

    st.write(f"共 {len(signals_df)} 个信号")

    # 显示信号列表
    for idx, row in signals_df.iterrows():
        confidence = row.get("confidence", 0)

        if confidence >= 0.8:
            level_color = "#ff4b4b"
        elif confidence >= 0.6:
            level_color = "#ffa500"
        else:
            level_color = "#4caf50"

        # 获取信号名称，如果没有name字段，使用signal_type转换
        signal_name = row.get("name")
        if not signal_name or signal_name == "N/A":
            signal_type = row.get("signal_type", "unknown")
            # 信号类型到中文名称的映射
            type_names = {
                "velocity_spike": "🚀 速度激增",
                "convergence": "🔄 多源聚合",
                "triangulation": "📐 三角验证",
                "hotspot_escalation": "🔥 热点升级",
                "economic_indicator_alert": "📊 经济指标异常",
                "natural_disaster_signal": "🌋 自然灾害",
                "geopolitical_intensity": "🌍 地缘政治紧张",
            }
            signal_name = type_names.get(signal_type, f"⚡ {signal_type}")

        st.markdown(
            f"""
        <div class="hotspot-card" style="border-left: 4px solid {level_color};">
            <h4>{row.get("icon", "⚡")} {signal_name}</h4>
            <p>{row.get("description", "N/A")}</p>
            <p>
                <span style="color: {level_color}; font-weight: bold;">
                    置信度: {confidence:.2f}
                </span> |
                <span class="meta-text">时间: {row.get("created_at", "N/A")[:16]}</span>
            </p>
        </div>
        """,
            unsafe_allow_html=True,
        )

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


# 实体管理函数
def get_cluster_articles(supabase, cluster_id: int) -> list:
    """获取聚类关联的所有文章"""
    try:
        # 获取关联的文章ID
        relations = (
            supabase.table("article_analyses")
            .select("article_id")
            .eq("cluster_id", cluster_id)
            .execute()
        )

        if not relations.data:
            return []

        article_ids = [r["article_id"] for r in relations.data]

        # 获取文章详情
        articles = []
        for aid in article_ids:
            result = (
                supabase.table("articles")
                .select("id, title, content, url, category")
                .eq("id", aid)
                .execute()
            )
            if result.data:
                articles.append(result.data[0])

        return articles
    except Exception as e:
        logger.error(f"获取聚类文章失败: {e}")
        return []


def _detect_entity_type(entity_name: str) -> str:
    """
    检测实体类型

    从配置文件读取关键词进行检测

    Args:
        entity_name: 实体名称

    Returns:
        实体类型: person/organization/location/event/concept
    """
    name = entity_name.strip()

    # 按优先级检测
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


def update_entities(supabase, cluster_id: int, entities: list, category: str):
    """更新实体表和实体-聚类关联表"""
    try:
        for entity_name in entities:
            if not entity_name or len(entity_name) < 2:
                continue

            # 自动检测实体类型
            entity_type = _detect_entity_type(entity_name)

            # 检查实体是否已存在
            existing = (
                supabase.table("entities")
                .select("id, mention_count_total")
                .eq("name", entity_name)
                .execute()
            )

            if existing.data:
                # 更新现有实体
                entity_id = existing.data[0]["id"]
                new_count = existing.data[0]["mention_count_total"] + 1

                supabase.table("entities").update(
                    {
                        "last_seen": datetime.now().isoformat(),
                        "mention_count_total": new_count,
                        "category": category,
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

        logger.info(f"实体更新完成: {len(entities)} 个实体")
    except Exception as e:
        logger.error(f"更新实体失败: {e}")


def trigger_deep_analysis(supabase, cluster_id: int) -> bool:
    """
    触发对浅层分析聚类的深度分析

    Args:
        supabase: Supabase 客户端
        cluster_id: 聚类ID

    Returns:
        是否成功
    """
    try:
        import sys
        import os

        # 添加项目根目录到路径
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        from scripts.llm_client import LLMClient
        from config.analysis_config import LLM_PROMPTS

        logger.info(f"开始深度分析聚类 {cluster_id}")

        # 1. 获取聚类信息
        cluster_result = (
            supabase.table("analysis_clusters")
            .select("*")
            .eq("id", cluster_id)
            .execute()
        )

        if not cluster_result.data:
            logger.error(f"聚类 {cluster_id} 不存在")
            return False

        cluster = cluster_result.data[0]

        # 2. 获取关联的文章
        articles = get_cluster_articles(supabase, cluster_id)

        if not articles:
            logger.warning(f"聚类 {cluster_id} 没有关联文章")
            # 仍然尝试分析，使用已有标题
            articles = [{"title": cluster["primary_title"], "content": ""}]

        # 3. 准备分析数据
        titles = [a["title"] for a in articles]
        content_samples = "\n".join([a.get("content", "")[:500] for a in articles[:3]])

        # 4. 调用LLM进行完整分析
        llm_client = LLMClient()

        prompt = LLM_PROMPTS["cluster_summary"].format(
            article_count=cluster["article_count"],
            sources=", ".join(titles[:5]),
            primary_title=cluster["primary_title"],
            content_samples=content_samples[:1000],
        )

        logger.info(f"调用LLM进行深度分析...")
        result = llm_client.summarize(prompt, model="qwen-plus")

        # 5. 更新聚类数据
        update_data = {
            "summary": result.get("summary", cluster["primary_title"]),
            "key_entities": json.dumps(result.get("key_entities", [])),
            "impact": result.get("impact", ""),
            "trend": result.get("trend", ""),
            "analysis_depth": "full",
            "full_analysis_triggered": True,
            "is_hot": cluster["article_count"] >= 3,
            "updated_at": datetime.now().isoformat(),
        }

        supabase.table("analysis_clusters").update(update_data).eq(
            "id", cluster_id
        ).execute()

        # 6. 更新实体追踪
        entities = result.get("key_entities", [])
        if entities:
            update_entities(supabase, cluster_id, entities, cluster["category"])

        logger.info(f"深度分析完成: 聚类 {cluster_id}")
        return True

    except Exception as e:
        logger.error(f"深度分析失败: {e}")
        return False


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
            ["全部", "person", "organization", "location", "event", "concept"],
        )
    with col2:
        category = st.selectbox(
            "所属分类:", ["全部", "military", "politics", "economy"]
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
                    st.write(f"- {cluster.get('primary_title', 'N/A')[:60]}...")
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
