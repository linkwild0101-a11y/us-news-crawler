#!/usr/bin/env python3
"""
US-Monitor UI 仪表板
使用 Streamlit 构建中文界面
"""

import os
import sys
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from supabase import create_client

# 页面配置
st.set_page_config(
    page_title="US-Monitor 热点分析",
    page_icon="🇺🇸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS 样式 (适配明亮/黑暗模式)
st.markdown(
    """
<style>
    /* 主标题 */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    
    /* 指标卡片 - 使用 Streamlit 主题色 */
    .metric-card {
        background-color: rgba(128, 128, 128, 0.1);
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    
    /* 热点卡片 - 使用主题背景色 */
    .hotspot-card {
        background-color: rgba(128, 128, 128, 0.05);
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid rgba(128, 128, 128, 0.2);
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        color: inherit;
    }
    
    /* 热点卡片标题 */
    .hotspot-card h4, .hotspot-card h5 {
        color: inherit;
        margin-bottom: 0.5rem;
    }
    
    /* 热点卡片段落 */
    .hotspot-card p {
        color: inherit;
        margin-bottom: 0.5rem;
    }
    
    /* 元信息文字 */
    .hotspot-card .meta-text {
        color: rgba(128, 128, 128, 0.8);
        font-size: 0.9rem;
    }
    
    /* 信号徽章 */
    .signal-badge {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .signal-high { background-color: #ff4b4b; color: white; }
    .signal-medium { background-color: #ffa500; color: black; }
    .signal-low { background-color: #4caf50; color: white; }
</style>
""",
    unsafe_allow_html=True,
)


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
        "选择页面:", ["🏠 概览首页", "🔥 热点详情", "📡 信号中心", "📈 数据统计"]
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
                st.markdown(
                    f"""
                <div class="hotspot-card">
                    <h4>{row.get("primary_title", "N/A")[:80]}...</h4>
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

                # 添加原文链接按钮
                if row.get("primary_link"):
                    st.link_button("🔗 查看英文原文", row["primary_link"])

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

            st.markdown(
                f"""
            <div class="hotspot-card">
                <h5>
                    {row.get("icon", "⚡")} {row.get("name", "N/A")}
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

        st.markdown(
            f"""
        <div class="hotspot-card" style="border-left: 4px solid {level_color};">
            <h4>{row.get("icon", "⚡")} {row.get("name", "N/A")}</h4>
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
        st.pie_chart(cat_counts)


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
    elif page == "📈 数据统计":
        render_stats(supabase)


if __name__ == "__main__":
    main()
