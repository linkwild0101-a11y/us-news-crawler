#!/usr/bin/env python3
"""
哨兵告警配置
"""

from typing import Dict, List

WATCHLIST_LEVEL_THRESHOLDS = {
    "L1": 0.35,
    "L2": 0.55,
    "L3": 0.72,
    "L4": 0.88,
}

WATCHLIST_RISK_WEIGHTS = {
    "scenario_match": 0.30,
    "velocity": 0.20,
    "convergence": 0.20,
    "source_credibility": 0.20,
    "entity_spike": 0.10,
}

WATCHLIST_HARD_GATES = {
    "L3": {"official_sources_min": 1, "unique_domains_min": 3},
    "L4": {"official_text_effective": True, "independent_high_trust_min": 2},
}

WATCHLIST_REVIEW_WINDOW_MINUTES = {"L1": 240, "L2": 120, "L3": 30, "L4": 15}

WATCHLIST_SUGGESTED_ACTIONS = {
    "L1": "保留观察，等待多源收敛后再升级。",
    "L2": "启动快速核验，补齐关键证据链接。",
    "L3": "触发预警流程，15分钟内完成复核并同步值班。",
    "L4": "进入紧急响应，立即上报并持续跟踪官方更新。",
}

OFFICIAL_DOMAIN_HINTS = [
    ".gov",
    ".mil",
    "mod.go.jp",
    "gov.ph",
    "mindef.gov.sg",
    "defence.gov.au",
    "fmprc.gov.cn",
    "mod.gov.cn",
]

HIGH_TRUST_DOMAIN_HINTS = [
    "reuters.com",
    "apnews.com",
    "ap.org",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "state.gov",
    "federalregister.gov",
    "bis.doc.gov",
    "treasury.gov",
    "home.treasury.gov",
    "defense.gov",
    "navy.mil",
    "af.mil",
    "indo-pacificcommand.mil",
    "mod.go.jp",
    "defence.gov.au",
]

OFFICIAL_EFFECTIVE_KEYWORDS = [
    "effective",
    "final rule",
    "executive order",
    "official statement",
    "生效",
    "正式生效",
    "最终规则",
    "正式发布",
    "正式發布",
    "公告",
    "條款生效",
]

WATCHLIST_SENTINELS: List[Dict[str, object]] = [
    {
        "id": "taiwan_strait_military",
        "name": "台海军事动态",
        "category": "military",
        "min_groups_hit": 2,
        "required_groups": [],
        "keyword_groups": {
            "action": [
                "越线",
                "越線",
                "战备警巡",
                "戰備警巡",
                "实弹",
                "實彈",
                "封控",
                "拦截",
                "攔截",
                "演训",
                "演訓",
            ],
            "geo": ["台海", "台湾海峡", "臺灣海峽", "东海", "東海", "巴士海峡", "巴士海峽"],
            "platform": ["航母", "导弹", "導彈", "舰机", "艦機", "战机", "戰機"],
        },
    },
    {
        "id": "tech_export_controls",
        "name": "科技出口管制",
        "category": "tech",
        "min_groups_hit": 2,
        "required_groups": ["policy"],
        "keyword_groups": {
            "policy": [
                "实体清单",
                "實體清單",
                "许可",
                "許可",
                "最终规则",
                "最終規則",
                "出口管制",
                "出口管制",
            ],
            "technology": ["ai芯片", "eda", "先进制程", "先進製程", "高端晶片", "高端芯片"],
            "enforcement": ["长臂", "長臂", "罚单", "罰單", "次级制裁", "次級制裁"],
        },
    },
    {
        "id": "allied_exercises",
        "name": "周边同盟军演",
        "category": "military",
        "min_groups_hit": 2,
        "required_groups": ["alliance"],
        "keyword_groups": {
            "alliance": ["美日", "美韩", "美韓", "美菲", "aukus", "quad"],
            "intensity": ["实弹", "實彈", "反导", "反導", "跨域", "前沿部署"],
            "sensitive_area": ["台海", "臺海", "东海", "南海", "西太平洋", "第一岛链", "第一島鏈"],
        },
    },
]
