/**
 * String → string formatters and small score → tier/tone resolvers used
 * by the cross-market backtest panel. Pure helpers, easy to unit-test.
 */

import { CONSTRUCTION_MODE_LABELS } from './crossMarketDefaults';

export const formatConstructionMode = (value) =>
    CONSTRUCTION_MODE_LABELS[value] || value || '未设置';

const normalizeDisplayText = (value = '') =>
    String(value || '').replace(/\s+/g, ' ').trim();

const TEMPLATE_NAME_LABELS = {
    utilities_vs_growth: '美股公用事业 vs 纳指成长',
    'US utilities vs NASDAQ growth': '美股公用事业 vs 纳指成长',
    copper_vs_semis: '铜期货 vs 半导体 ETF',
    'Copper futures vs semis ETF': '铜期货 vs 半导体 ETF',
    energy_vs_ai_apps: '能源基建 vs AI 应用 ETF',
    'Energy infrastructure vs AI application ETF': '能源基建 vs AI 应用 ETF',
    defensive_beta_hedge: '防御 Beta 对冲（OLS）',
    'Defensive beta hedge (OLS)': '防御 Beta 对冲（OLS）',
    'Defensive beta hedge': '防御 Beta 对冲',
    rates_pressure_vs_duration_tech: '利率压力 vs 长久期科技',
    'Rates pressure vs duration tech': '利率压力 vs 长久期科技',
    dollar_squeeze_vs_china_beta: '美元挤压 vs 中国 Beta',
    'Dollar squeeze vs China beta': '美元挤压 vs 中国 Beta',
    credit_stress_defensive_hedge: '信用压力防御对冲',
    'Credit stress defensive hedge': '信用压力防御对冲',
    people_decay_short_vs_cashflow_defensive: '组织衰退空头 vs 现金流防御',
    'People decay short vs cashflow defensive': '组织衰退空头 vs 现金流防御',
    'People Decay / Cashflow Defensive': '组织衰退空头 vs 现金流防御',
    'Energy vs AI': '能源 vs AI',
};

const TEMPLATE_THEME_LABELS = {
    'Policy-fragile defensives vs growth beta': '政策脆弱防御资产 vs 成长 Beta',
    'Physical bottlenecks vs semiconductor beta': '实物瓶颈 vs 半导体 Beta',
    'Baseload scarcity vs AI application enthusiasm': '基荷稀缺 vs AI 应用热度',
    'Talent dilution and defensive beta hedge': '人才稀释与防御 Beta 对冲',
    'Higher real-rate pressure vs duration-heavy tech': '实际利率压力 vs 长久期科技',
    'Dollar mismatch vs China beta': '美元错配 vs 中国 Beta',
    'Credit spread stress vs fragile beta': '信用利差压力 vs 脆弱 Beta',
    'People-layer decay vs resilient cashflow': '人的维度衰退 vs 韧性现金流',
    'People Decay': '组织衰退',
};

const TEMPLATE_TEXT_LABELS = {
    'Defensive regulated utilities against growth-heavy tech beta.': '用受监管的防御型公用事业，对冲高成长科技 Beta。',
    'When bureaucratic friction rises and physical grid demand keeps building, regulated utilities can absorb capital while long-duration growth beta rerates lower.': '当官僚摩擦上升且实体电网需求继续扩张时，受监管公用事业更容易承接资金，而久期较长的成长 Beta 可能被重新定价。',
    'Commodity tightness against semiconductor beta.': '用商品供给紧张表达，对冲半导体 Beta。',
    'When copper inventories tighten and trade frictions rise, upstream physical scarcity can outperform semiconductor beta that already embeds optimistic AI demand.': '当铜库存收紧且贸易摩擦上升时，上游实物稀缺更可能跑赢已经计入乐观 AI 需求的半导体 Beta。',
    'Physical energy backbone against application-layer AI enthusiasm.': '用实体能源骨架，对冲应用层 AI 热度。',
    'When power bottlenecks and baseload mismatch worsen, the physical energy backbone can outperform application-layer AI names whose demand assumptions are too smooth.': '当电力瓶颈和基荷错配恶化时，实体能源骨架可能跑赢需求假设过于平滑的应用层 AI 标的。',
    'Low-beta utility basket hedged against broad tech beta with rolling OLS.': '用低 Beta 公用事业篮子，通过滚动 OLS 对冲广义科技 Beta。',
    'When tech leadership quality deteriorates or the market starts punishing weak execution, a low-beta utility basket hedged against broad tech beta becomes a cleaner defensive expression.': '当科技领导层质量恶化，或市场开始惩罚执行力偏弱的公司时，低 Beta 公用事业篮子叠加科技 Beta 对冲，是更清晰的防御表达。',
    'Treasury pressure proxy against long-duration software beta.': '用利率压力代理，对冲长久期软件 Beta。',
    'When rate-curve pressure and credit stress reprice duration, long-duration software beta tends to be more fragile than listed rate/short-duration proxies.': '当利率曲线压力和信用压力重新定价久期时，长久期软件 Beta 往往比上市利率或短久期代理更脆弱。',
    'Dollar funding squeeze proxy against China beta ETFs/ADRs.': '用美元融资挤压代理，对冲中国 Beta ETF/ADR。',
    'When dollar mismatch and policy execution noise rise together, China-beta assets can underperform defensive dollar-linked proxies.': '当美元错配与政策执行噪音一起升温时，中国 Beta 资产可能跑输防御型美元相关代理。',
    'Defensive cashflow proxies against high-beta credit-sensitive equity.': '用防御型现金流代理，对冲高 Beta、信用敏感权益资产。',
    'When credit spreads widen and leadership quality weakens, stable cashflow defensives can outperform high-beta, financing-sensitive risk assets.': '当信用利差走阔且领导质量走弱时，稳定现金流防御资产可能跑赢高 Beta、融资敏感的风险资产。',
    'Short fragile-people-layer tech beta against stable cashflow defensives.': '做空人的维度脆弱的科技 Beta，同时做多稳定现金流防御资产。',
    "When people's-layer fragility, executive dilution and source degradation rise together, the cleaner expression is to short fragile growth beta against resilient cashflow defensives.": '当人的维度脆弱、管理层稀释和来源退化同时升温时，更清晰的表达是做空脆弱成长 Beta，并用韧性现金流防御资产承接。',
    'Physical energy against AI apps.': '实体能源对冲 AI 应用热度。',
    'Baseload scarcity theme.': '基荷稀缺主题。',
    'Utilities against tech beta.': '公用事业对冲科技 Beta。',
    'Execution quality hedge.': '执行质量对冲。',
};

const SIGNAL_LABELS = {
    policy_fragility_defensive: '政策脆弱防御腿',
    baseload_capacity: '基荷容量',
    department_chaos: '部门混乱',
    physical_world_vs_ai_beta: '实体供给 vs AI Beta',
    inventory_tightness: '库存紧张',
    trade_flow: '贸易流',
    energy_backbone_vs_ai_apps: '能源骨架 vs AI 应用',
    baseload_mismatch: '基荷错配',
    people_fragility: '组织脆弱性',
    defensive_beta_repricing: '防御 Beta 重估',
    tech_dilution: '技术/人才稀释',
    rates_vs_duration: '利率 vs 久期',
    rate_curve_pressure: '利率曲线压力',
    credit_spread_stress: '信用利差压力',
    dollar_strength_vs_china_beta: '美元强势 vs 中国 Beta',
    fx_mismatch: '汇率错配',
    policy_execution_disorder: '政策执行扰动',
    credit_stress_defensive: '信用压力防御腿',
    people_decay_short: '组织衰退空头腿',
    source_mode_summary: '来源模式摘要',
    defensive_spread: '防御价差',
    commodity_vs_growth: '商品 vs 成长',
    physical_vs_narrative: '实物约束 vs 叙事弹性',
    ols_hedged_defensive: 'OLS 防御对冲',
    macro_rate_spread: '宏观利率价差',
    fx_macro_spread: '外汇宏观价差',
    defensive_credit_hedge: '防御信用对冲',
    people_fragility_pair: '组织脆弱配对',
    spread_zscore: '价差 Z 分数',
    project_pipeline: '项目管线',
    logistics: '物流',
    inventory: '库存',
    trade: '贸易',
    customs: '海关',
    investment_activity: '投资活动',
    people_layer: '人的维度',
    talent_structure: '人才结构',
    rates: '利率',
    credit: '信用',
    market_indicators: '市场指标',
    fx: '汇率',
    source_health: '来源健康',
};

const STATUS_LABELS = {
    mixed: '混合',
    positive: '正向',
    negative: '负向',
    stable: '稳定',
    full: '完整强度',
    compressed: '已收缩',
    cautious: '谨慎',
    decay_guarded: '衰败防守',
    decay_watch: '衰败观察',
    chaos_guarded: '混乱防守',
    chaos_watch: '混乱观察',
    people_guarded: '组织防守',
    people_watch: '组织观察',
    fragile: '脆弱',
    watch: '观察',
    healthy: '健康',
    robust: '稳健',
    unknown: '未知',
    chaotic: '混乱',
    'official-led': '官方来源主导',
    'fallback-heavy': '回退来源偏高',
    proxy: '代理源',
    degraded: '降级',
    original: '原始强度',
    softened: '收缩强度',
    auto_downgraded: '自动降级',
    balanced: '均衡',
    aligned: '已对齐',
    biweekly: '双周',
    yes: '是',
    no: '否',
};

export const formatTemplateName = (templateOrName = '') => {
    const matchCandidates = typeof templateOrName === 'object'
        ? [templateOrName.id, templateOrName.name, templateOrName.template_name]
        : [templateOrName];
    const fallbackCandidates = typeof templateOrName === 'object'
        ? [templateOrName.name, templateOrName.template_name, templateOrName.id]
        : [templateOrName];
    const match = matchCandidates
        .map(normalizeDisplayText)
        .find((item) => item && TEMPLATE_NAME_LABELS[item]);
    return match ? TEMPLATE_NAME_LABELS[match] : (normalizeDisplayText(fallbackCandidates.find(Boolean)) || '未命名模板');
};

export const formatTemplateTheme = (templateOrTheme = '') => {
    const candidates = typeof templateOrTheme === 'object'
        ? [templateOrTheme.theme, templateOrTheme.name, templateOrTheme.id]
        : [templateOrTheme];
    const match = candidates
        .map(normalizeDisplayText)
        .find((item) => item && (TEMPLATE_THEME_LABELS[item] || TEMPLATE_NAME_LABELS[item]));
    if (match) {
        return TEMPLATE_THEME_LABELS[match] || TEMPLATE_NAME_LABELS[match];
    }
    return formatSignalLabel(candidates.find(Boolean)) || '未设置主题';
};

export const formatTemplateNarrative = (value = '') => {
    const normalized = normalizeDisplayText(value);
    return TEMPLATE_TEXT_LABELS[normalized] || normalized;
};

export const formatSignalLabel = (value = '') => {
    const normalized = normalizeDisplayText(value);
    return SIGNAL_LABELS[normalized] || STATUS_LABELS[normalized] || normalized.replaceAll('_', ' ');
};

export const formatSignalList = (value = '') => {
    const parts = Array.isArray(value)
        ? value
        : normalizeDisplayText(value).split(/[、,，/]+/);
    return parts
        .map((item) => formatSignalLabel(item))
        .filter(Boolean)
        .join('、');
};

export const formatStatusLabel = (value = '') => {
    const normalized = normalizeDisplayText(value);
    return STATUS_LABELS[normalized] || formatSignalLabel(normalized) || '-';
};

export const formatBiasQualityLabel = (value = '') => formatStatusLabel(value);

export const buildDisplayTier = (score) => {
    if (score >= 2.6) return '优先部署';
    if (score >= 1.4) return '重点跟踪';
    return '候选模板';
};

export const buildDisplayTone = (score) => {
    if (score >= 2.6) return 'volcano';
    if (score >= 1.4) return 'gold';
    return 'blue';
};

export const formatTradeAction = (value) => {
    const action = String(value || '').toUpperCase();
    if (!action) return '-';
    return action
        .replace('OPEN', '开仓')
        .replace('CLOSE', '平仓')
        .replace('LONG', '多头')
        .replace('SHORT', '空头')
        .replaceAll('_', ' ');
};

const EXECUTION_CHANNEL_LABELS = {
    cash_equity: '现货股票',
    futures: '期货通道',
};

export const formatExecutionChannel = (value = '') =>
    EXECUTION_CHANNEL_LABELS[value] || value || '-';

const VENUE_LABELS = {
    US_EQUITY: '美股主板',
    US_ETF: '美股 ETF',
    COMEX_CME: 'CME / COMEX',
};

export const formatVenue = (value = '') =>
    VENUE_LABELS[value] || value || '-';
