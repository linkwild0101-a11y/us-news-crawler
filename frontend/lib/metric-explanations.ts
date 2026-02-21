export interface MetricExplanation {
  title: string;
  definition: string;
  calc?: string;
  tip?: string;
}

export const METRIC_EXPLANATIONS = {
  dashboard_risk_level: {
    title: "风险等级（L1-L4）",
    definition: "表示当前看板风险热度，等级越高代表风险事件密度和强度越高。",
    calc: "由信号层评分映射：L4>=82，L3>=72，L2>=60，L1>=45。",
    tip: "高等级并不等于不能做多，建议结合 LONG/SHORT 与市场状态联动判断。"
  },
  market_state_summary: {
    title: "市场状态",
    definition: "由波动率、利率、美元强弱推导出的宏观风险偏好状态。",
    calc: "综合 VIX、10Y、美元指数 DXY 计算 regime_score，再映射 risk_on/risk_off。",
    tip: "可作为方向过滤器：risk_on 更偏 LONG，risk_off 更偏 SHORT。"
  },
  total_opportunities: {
    title: "总机会数",
    definition: "当前窗口内仍有效（未到期）的机会条数。",
    tip: "先看数量，再看分数和置信度。数量少时更适合精选而非分散。"
  },
  horizon_a: {
    title: "Horizon A",
    definition: "短周期机会，通常由更高强度信号触发。",
    calc: "signal_score >= 65 归入 A，否则归入 B。",
    tip: "A 更强调时效，建议优先关注并更频繁复核失效条件。"
  },
  long_count: {
    title: "LONG 数量",
    definition: "当前可做多机会数量。",
    tip: "用来观察看板整体偏多还是偏空，避免逆着主导方向重仓。"
  },
  short_count: {
    title: "SHORT 数量",
    definition: "当前可做空机会数量。",
    tip: "当 SHORT 显著增多，通常意味着风险偏好走弱。"
  },
  opportunity_score: {
    title: "机会分",
    definition: "综合交易优先级分数，越高越值得优先研究。",
    calc: "由信号分与市场状态联合计算，并裁剪到 0-100。",
    tip: "先按机会分排序，再用证据页验证催化与关系。"
  },
  confidence: {
    title: "置信度",
    definition: "模型对当前结论稳定性的估计。",
    calc: "由事件一致性、信号强弱和聚合密度共同决定，范围 0-1。",
    tip: "低置信度高分机会，建议降权或分批验证。"
  },
  invalid_if: {
    title: "失效条件",
    definition: "触发后应下调优先级或移除该机会的条件。",
    tip: "这是风控锚点，建议在交易前先确认触发阈值。"
  },
  spy: {
    title: "SPY",
    definition: "标普500 ETF 价格，反映美股大盘风险偏好。"
  },
  qqq: {
    title: "QQQ",
    definition: "纳斯达克100 ETF 价格，偏成长/科技风格。"
  },
  dia: {
    title: "DIA",
    definition: "道琼斯工业指数 ETF 价格，偏传统蓝筹。"
  },
  vix: {
    title: "VIX",
    definition: "市场隐含波动率指数，常被视作恐慌温度计。",
    tip: "VIX 越高通常意味着波动放大与风险偏好下降。"
  },
  us10y: {
    title: "10Y",
    definition: "美国10年期国债收益率，反映长期资金成本。"
  },
  dxy: {
    title: "DXY",
    definition: "美元指数，反映美元相对强弱。",
    tip: "美元走强常压制部分风险资产估值。"
  },
  signal_count_24h: {
    title: "24h 信号",
    definition: "该标的在过去 24 小时内累计的相关信号条数。"
  },
  related_cluster_count_24h: {
    title: "关联热点",
    definition: "该标的对应的热点事件簇数量，反映催化覆盖面。"
  },
  sentinel_level_score: {
    title: "Lx · 分值",
    definition: "Lx 为离散风险等级，后面的数值是标准化风险分（0-100）。"
  },
  trigger_reasons: {
    title: "触发原因",
    definition: "导致信号成立的核心原因摘要（如财报、宏观、政策等）。"
  },
  cluster_article_count: {
    title: "文章数",
    definition: "该热点事件簇覆盖的文章数量。",
    tip: "数量高代表热度高，但仍需结合质量与方向判断。"
  },
  relation_confidence: {
    title: "关系置信度",
    definition: "实体共现关系的可信程度，越高代表共现更稳定。",
    calc: "由共现次数与映射置信度综合得到。"
  }
} as const satisfies Record<string, MetricExplanation>;

export type MetricKey = keyof typeof METRIC_EXPLANATIONS;
