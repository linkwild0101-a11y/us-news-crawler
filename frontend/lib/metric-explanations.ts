export interface MetricExplanation {
  title: string;
  definition: string;
  calc?: string;
  tip?: string;
  category?: string;
  aliases?: string[];
}

export const METRIC_EXPLANATIONS = {
  dashboard_risk_level: {
    title: "风险等级（L1-L4）",
    definition: "表示当前看板风险热度，等级越高代表风险事件密度和强度越高。",
    calc: "由信号层评分映射：L4>=82，L3>=72，L2>=60，L1>=45。",
    tip: "高等级并不等于不能做多，建议结合 LONG/SHORT 与市场状态联动判断。",
    category: "风险"
  },
  market_state_summary: {
    title: "市场状态",
    definition: "由波动率、利率、美元强弱推导出的宏观风险偏好状态。",
    calc: "综合 VIX、10Y、美元指数 DXY 计算 regime_score，再映射 risk_on/risk_off。",
    tip: "可作为方向过滤器：risk_on 更偏 LONG，risk_off 更偏 SHORT。",
    category: "市场"
  },
  total_opportunities: {
    title: "总机会数",
    definition: "当前窗口内仍有效（未到期）的机会条数。",
    tip: "先看数量，再看分数和置信度。数量少时更适合精选而非分散。",
    category: "机会"
  },
  alert_total: {
    title: "提醒总数",
    definition: "当前提醒中心展示的提醒条数（按过滤条件前的总量）。",
    tip: "用于评估当前提醒负荷，过高时建议提高阈值或缩小关注池。",
    category: "提醒"
  },
  alert_unread: {
    title: "未读提醒",
    definition: "尚未在当前会话中标记为已读的提醒数量。",
    tip: "优先处理未读中的 L3/L4 与高 alert_score 提醒。",
    category: "提醒"
  },
  alert_pending_count: {
    title: "待发送提醒",
    definition: "状态为 pending 的提醒数量，通常表示刚生成待投递。",
    tip: "若长期偏高，需检查 dispatch 步骤是否稳定执行。",
    category: "提醒"
  },
  alert_deduped_count: {
    title: "已去重提醒",
    definition: "命中冷却窗口后被去重的提醒数量。",
    tip: "去重偏高代表冷却生效，能减少重复噪音提醒。",
    category: "提醒"
  },
  horizon_a: {
    title: "Horizon A",
    definition: "短周期机会，通常由更高强度信号触发。",
    calc: "signal_score >= 65 归入 A，否则归入 B。",
    tip: "A 更强调时效，建议优先关注并更频繁复核失效条件。",
    category: "机会"
  },
  long_count: {
    title: "LONG 数量",
    definition: "当前可做多机会数量。",
    tip: "用来观察看板整体偏多还是偏空，避免逆着主导方向重仓。",
    category: "机会"
  },
  short_count: {
    title: "SHORT 数量",
    definition: "当前可做空机会数量。",
    tip: "当 SHORT 显著增多，通常意味着风险偏好走弱。",
    category: "机会"
  },
  opportunity_score: {
    title: "机会分",
    definition: "综合交易优先级分数，越高越值得优先研究。",
    calc: "由信号分与市场状态联合计算，并裁剪到 0-100。",
    tip: "先按机会分排序，再用证据页验证催化与关系。",
    category: "机会"
  },
  confidence: {
    title: "置信度",
    definition: "模型对当前结论稳定性的估计。",
    calc: "由事件一致性、信号强弱和聚合密度共同决定，范围 0-1。",
    tip: "低置信度高分机会，建议降权或分批验证。",
    category: "机会"
  },
  invalid_if: {
    title: "失效条件",
    definition: "触发后应下调优先级或移除该机会的条件。",
    tip: "这是风控锚点，建议在交易前先确认触发阈值。",
    category: "风控"
  },
  spy: {
    title: "SPY",
    definition: "标普500 ETF 价格，反映美股大盘风险偏好。",
    category: "市场"
  },
  qqq: {
    title: "QQQ",
    definition: "纳斯达克100 ETF 价格，偏成长/科技风格。",
    category: "市场"
  },
  dia: {
    title: "DIA",
    definition: "道琼斯工业指数 ETF 价格，偏传统蓝筹。",
    category: "市场"
  },
  vix: {
    title: "VIX",
    definition: "市场隐含波动率指数，常被视作恐慌温度计。",
    tip: "VIX 越高通常意味着波动放大与风险偏好下降。",
    category: "市场"
  },
  us10y: {
    title: "10Y",
    definition: "美国10年期国债收益率，反映长期资金成本。",
    category: "市场"
  },
  dxy: {
    title: "DXY",
    definition: "美元指数，反映美元相对强弱。",
    tip: "美元走强常压制部分风险资产估值。",
    category: "市场"
  },
  signal_count_24h: {
    title: "24h 信号",
    definition: "该标的在过去 24 小时内累计的相关信号条数。",
    category: "信号"
  },
  related_cluster_count_24h: {
    title: "关联热点",
    definition: "该标的对应的热点事件簇数量，反映催化覆盖面。",
    category: "信号"
  },
  sentinel_level_score: {
    title: "Lx · 分值",
    definition: "Lx 为离散风险等级，后面的数值是标准化风险分（0-100）。",
    category: "信号"
  },
  trigger_reasons: {
    title: "触发原因",
    definition: "导致信号成立的核心原因摘要（如财报、宏观、政策等）。",
    category: "信号"
  },
  source_mix_badge: {
    title: "信源徽章",
    definition: "标识当前信号/机会主要来自 News、X 或两者混合（Mixed）。",
    tip: "Mixed 通常代表交叉验证更充分，可优先关注。",
    category: "信号",
    aliases: ["source mix", "X", "news", "mixed"]
  },
  x_source_ratio: {
    title: "X 来源占比",
    definition: "在该信号/机会关联事件中，来自 X 信源的比例。",
    calc: "x_ratio = x_count / source_total。",
    tip: "占比越高越依赖社交源，建议结合新闻源确认后再执行。",
    category: "信号",
    aliases: ["x ratio", "x占比", "来源构成"]
  },
  cluster_article_count: {
    title: "文章数",
    definition: "该热点事件簇覆盖的文章数量。",
    tip: "数量高代表热度高，但仍需结合质量与方向判断。",
    category: "证据"
  },
  relation_confidence: {
    title: "关系置信度",
    definition: "实体共现关系的可信程度，越高代表共现更稳定。",
    calc: "由共现次数与映射置信度综合得到。",
    category: "证据"
  },
  eval_hit_rate_proxy: {
    title: "Eval 命中率代理",
    definition: "使用稳定性代理口径计算的历史信号命中率。",
    calc: "按窗口内样本 hit_flag / total 计算。",
    tip: "这是代理标签，不等于真实交易收益命中率。",
    category: "评估",
    aliases: ["hit rate", "eval", "命中率"]
  },
  paper_realized_pnl: {
    title: "Paper 已实现盈亏",
    definition: "纸上交易已平仓仓位的累计 PnL。",
    tip: "用于评估执行规则是否具备正向收益倾向。",
    category: "组合",
    aliases: ["paper", "pnl", "回测"]
  },
  drift_overall_status: {
    title: "Drift 状态",
    definition: "机会分布相对基线窗口的偏移等级（normal/warn/critical）。",
    calc: "比较 LONG 比例、集中度、置信度等指标与基线差值。",
    tip: "critical 代表输入分布发生显著变化，建议谨慎使用旧阈值。",
    category: "治理",
    aliases: ["drift", "漂移"]
  },
  cc_promote_candidate: {
    title: "晋级候选数",
    definition: "Champion/Challenger 对照中满足晋级边际的候选数量。",
    tip: "数量增加代表 challenger 在当前窗口更有优势。",
    category: "评估",
    aliases: ["champion", "challenger", "晋级"]
  },
  lifecycle_active_count: {
    title: "生命周期活跃数",
    definition: "复盘快照中仍处于活跃状态的机会数量。",
    tip: "结合临近到期与失效数量判断机会池老化速度。",
    category: "复盘",
    aliases: ["lifecycle", "active"]
  },
  subscription_sent_24h: {
    title: "订阅告警发送数(24h)",
    definition: "过去 24 小时成功推送的订阅告警数量。",
    tip: "可用于观察告警覆盖与静默策略是否合理。",
    category: "通知",
    aliases: ["subscription", "alert", "飞书"]
  },
  data_freshness_badge: {
    title: "数据新鲜度徽章",
    definition: "显示当前看板数据离最新刷新时间的分钟数与等级。",
    calc: "fresh<=30分钟，stale<=120分钟，critical>120分钟。",
    tip: "当新鲜度为 critical 时，建议先确认抓取/分析链路是否异常。",
    category: "治理",
    aliases: ["freshness", "新鲜度", "滞后"]
  },
  source_health_badge: {
    title: "数据质量徽章",
    definition: "按 source health 日快照汇总 H/D/C 状态。",
    calc: "critical>0 为红色，degraded>0 为黄色，否则绿色。",
    tip: "quality 徽章异常时，优先检查源站与降级逻辑。",
    category: "治理",
    aliases: ["source health", "质量", "HDC"]
  }
} as const satisfies Record<string, MetricExplanation>;

export type MetricKey = keyof typeof METRIC_EXPLANATIONS;

export interface MetricDictionaryItem extends MetricExplanation {
  key: MetricKey;
}

export const METRIC_DICTIONARY_ITEMS: MetricDictionaryItem[] = (
  Object.entries(METRIC_EXPLANATIONS) as Array<[MetricKey, MetricExplanation]>
).map(([key, value]) => ({
  key,
  ...value
}));
