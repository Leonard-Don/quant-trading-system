const DIMENSION_META = {
  investment_activity: { label: '投资活跃度', group: 'Supply Chain' },
  project_pipeline: { label: '项目管线', group: 'Supply Chain' },
  talent_structure: { label: '人才结构', group: 'Supply Chain' },
  inventory: { label: '库存压力', group: 'Macro HF' },
  trade: { label: '贸易脉冲', group: 'Macro HF' },
  logistics: { label: '物流摩擦', group: 'Macro HF' },
};

const SIGNAL_LABEL = {
  1: '猎杀窗口',
  0: '观察中',
  '-1': '逆风区',
};

const ACTION_MAP = {
  pricing: { label: '去定价研究', target: 'pricing' },
  cross_market: { label: '去跨市场回测', target: 'cross-market' },
  observe: { label: '继续观察', target: 'observe' },
};

const formatFactorName = (name = '') => {
  const mapping = {
    bureaucratic_friction: '官僚摩擦',
    tech_dilution: '技术稀释',
    baseload_mismatch: '基荷错配',
  };
  return mapping[name] || name.replace(/_/g, ' ');
};

const toPercentScale = (value) => {
  const numeric = Number(value || 0);
  return Math.min(100, Math.max(8, Math.abs(numeric) * 40 + 15));
};

const scoreTone = (score) => {
  if (score >= 0.35) return 'hot';
  if (score <= -0.35) return 'cold';
  return 'neutral';
};

export const getSignalLabel = (value) => SIGNAL_LABEL[value] || SIGNAL_LABEL[0];

export const buildHeatmapModel = (snapshot = {}, history = {}) => {
  const supplyDimensions = snapshot?.signals?.supply_chain?.dimensions || {};
  const macroDimensions = snapshot?.signals?.macro_hf?.dimensions || {};
  const records = history?.records || [];

  const cells = Object.entries(DIMENSION_META).map(([key, meta]) => {
    const source = supplyDimensions[key] || macroDimensions[key] || {};
    const relatedRecords = records.filter((item) => {
      if (meta.group === 'Supply Chain') {
        return ['bidding', 'env_assessment', 'hiring'].includes(item.category);
      }
      return ['commodity_inventory', 'customs', 'port_congestion'].includes(item.category);
    });

    const score = Number(source.score || 0);
    return {
      key,
      label: meta.label,
      group: meta.group,
      score,
      tone: scoreTone(score),
      count: Number(source.count || relatedRecords.length || 0),
      summary:
        meta.group === 'Supply Chain'
          ? `最近供应链记录 ${relatedRecords.length}`
          : `最近宏观高频记录 ${relatedRecords.length}`,
    };
  });

  const anomalies = [];
  const supplyAlerts = snapshot?.signals?.supply_chain?.alerts || [];
  supplyAlerts.slice(0, 3).forEach((alert) => {
    anomalies.push({
      key: `supply-alert-${alert.company || 'unknown'}`,
      title: alert.company || '供应链异常',
      description: alert.message || `dilution ratio ${alert.dilution_ratio || 0}`,
      type: 'alert',
    });
  });

  cells
    .filter((cell) => Math.abs(cell.score) >= 0.3)
    .slice(0, 3)
    .forEach((cell) => {
      anomalies.push({
        key: `heat-${cell.key}`,
        title: `${cell.label}出现显著偏移`,
        description: `${cell.group} score=${cell.score.toFixed(3)}`,
        type: cell.tone,
      });
    });

  return { cells, anomalies };
};

export const buildRadarModel = (overview = {}) => {
  const factors = overview?.factors || [];
  return factors.map((factor) => ({
    factor: formatFactorName(factor.name),
    intensity: toPercentScale(factor.z_score || factor.value),
    confidence: Math.min(100, Math.max(10, Number(factor.confidence || 0) * 100)),
    rawValue: Number(factor.value || 0),
    zScore: Number(factor.z_score || 0),
    signal: factor.signal,
  }));
};

export const buildFactorPanelModel = (overview = {}, snapshot = {}) => {
  const factors = (overview?.factors || []).map((factor) => ({
    ...factor,
    displayName: formatFactorName(factor.name),
  }));

  const topFactors = [...factors]
    .sort((a, b) => Math.abs(Number(b.z_score || 0)) - Math.abs(Number(a.z_score || 0)))
    .slice(0, 3);

  return {
    topFactors,
    factors,
    providerHealth: overview?.provider_health || snapshot?.provider_health || {},
    staleness: overview?.data_freshness || snapshot?.staleness || {},
  };
};

export const buildTimelineModel = (policyHistory = {}) => {
  const records = policyHistory?.records || [];
  return records.map((item) => {
    const raw = item.raw_value || {};
    const shift = Number(raw.policy_shift || 0);
    return {
      key: item.record_id,
      title: raw.title || item.source,
      timestamp: item.timestamp,
      source: item.source,
      direction: shift > 0.15 ? 'stimulus' : shift < -0.15 ? 'tightening' : 'neutral',
      directionLabel: shift > 0.15 ? '偏刺激' : shift < -0.15 ? '偏收紧' : '中性',
      tags: Object.keys(raw.industry_impact || {}),
      score: shift,
      confidence: Number(item.confidence || 0),
      details: raw.industry_impact || {},
    };
  });
};

export const buildHunterModel = ({ snapshot = {}, overview = {}, status = {} }) => {
  const alerts = [];
  const refreshStatus = snapshot?.refresh_status || status?.refresh_status || {};
  Object.entries(refreshStatus).forEach(([name, info]) => {
    if (['degraded', 'error'].includes(info.status)) {
      alerts.push({
        key: `provider-${name}`,
        title: `${name} 数据状态 ${info.status}`,
        severity: info.status === 'error' ? 'high' : 'medium',
        description: info.error || '继续使用最近成功快照',
        action: ACTION_MAP.observe,
      });
    }
  });

  const supplyAlerts = snapshot?.signals?.supply_chain?.alerts || [];
  supplyAlerts.forEach((item, index) => {
    alerts.push({
      key: `supply-${index}`,
      title: `${item.company || '未知公司'} 人才结构预警`,
      severity: 'high',
      description: item.message || `dilution ratio ${item.dilution_ratio || 0}`,
      action: ACTION_MAP.cross_market,
    });
  });

  (overview?.factors || [])
    .filter((item) => item.signal !== 0)
    .forEach((factor) => {
      alerts.push({
        key: `factor-${factor.name}`,
        title: `${formatFactorName(factor.name)} 出现偏移`,
        severity: Math.abs(Number(factor.z_score || 0)) > 1 ? 'high' : 'medium',
        description: `value=${Number(factor.value || 0).toFixed(3)} z=${Number(factor.z_score || 0).toFixed(3)}`,
        action: factor.signal === 1 ? ACTION_MAP.cross_market : ACTION_MAP.pricing,
      });
    });

  alerts.sort((a, b) => {
    const priority = { high: 0, medium: 1, low: 2 };
    return priority[a.severity] - priority[b.severity];
  });

  return alerts.slice(0, 8);
};

export const buildCrossMarketCards = (payload = {}) => {
  const templates = payload?.templates || [];
  return templates.map((template) => {
    const longCount = template.assets.filter((asset) => asset.side === 'long').length;
    const shortCount = template.assets.filter((asset) => asset.side === 'short').length;
    return {
      ...template,
      longCount,
      shortCount,
      stance: longCount >= shortCount ? '偏防守/资源端' : '偏对冲/做空端',
      action: ACTION_MAP.cross_market,
    };
  });
};
