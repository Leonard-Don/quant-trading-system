import { buildCrossMarketCards as buildScoredCrossMarketCards } from '../../utils/crossMarketRecommendations';
import { buildResearchTaskRefreshSignals } from '../../utils/researchTaskSignals';
import { buildMacroMispricingRefreshPriorityEvent } from '../../utils/workbenchPriorityEvents';
import {
  ACTION_MAP,
  COMPANY_SYMBOL_MAP,
  FACTOR_SYMBOL_MAP,
  FACTOR_TEMPLATE_MAP,
  buildCrossMarketAction,
  buildDisplayTier,
  buildDisplayTone,
  buildPricingAction,
  buildWorkbenchAction,
  extractAllocationOverlay,
  extractDominantDriver,
  extractRecentComparisonLead,
  extractTemplateIdentity,
  extractTemplateMeta,
  formatDriverLabel,
  formatFactorName,
  formatTemplateName,
  getInputReliabilityActionLabel,
  getReviewContextActionLabel,
} from './viewModelShared';

const buildNarrativeShiftAlerts = (tasks = []) => {
  const grouped = tasks.reduce((accumulator, task) => {
    if (task?.type !== 'cross_market' || task?.status === 'archived') {
      return accumulator;
    }
    const meta = extractTemplateMeta(task);
    const templateId = extractTemplateIdentity(task, meta);
    if (!templateId) {
      return accumulator;
    }
    const history = task?.snapshot_history || [];
    if (history.length < 2) {
      return accumulator;
    }
    const currentMeta = history[0]?.payload?.template_meta || meta;
    const previousMeta = history[1]?.payload?.template_meta || {};
    const currentDriver = extractDominantDriver(currentMeta);
    const previousDriver = extractDominantDriver(previousMeta);
    const currentCore = currentMeta?.theme_core || '';
    const previousCore = previousMeta?.theme_core || '';

    if (!currentDriver && !previousDriver && !currentCore && !previousCore) {
      return accumulator;
    }

    accumulator.push({
      templateId,
      taskId: task.id,
      title: task.title || formatTemplateName(templateId),
      currentDriver,
      previousDriver,
      currentCore,
      previousCore,
    });
    return accumulator;
  }, []);

  return grouped
    .filter((item) => {
      const driverChanged = item.currentDriver?.key && item.previousDriver?.key && item.currentDriver.key !== item.previousDriver.key;
      const coreChanged = item.currentCore && item.previousCore && item.currentCore !== item.previousCore;
      return driverChanged || coreChanged;
    })
    .map((item) => {
      const currentDriverLabel = formatDriverLabel(item.currentDriver);
      const previousDriverLabel = formatDriverLabel(item.previousDriver);
      const details = [];
      if (previousDriverLabel && currentDriverLabel && previousDriverLabel !== currentDriverLabel) {
        details.push(`主导驱动从 ${previousDriverLabel} 切换到 ${currentDriverLabel}`);
      }
      if (item.previousCore && item.currentCore && item.previousCore !== item.currentCore) {
        details.push(`主题核心腿从 ${item.previousCore} 变为 ${item.currentCore}`);
      }

      return {
        key: `narrative-shift-${item.templateId}`,
        title: `${item.title} 主导叙事切换`,
        severity: 'high',
        description: details.join(' · '),
        action: buildCrossMarketAction(
          item.templateId,
          'alert_hunter',
          `${item.title} 最近两版的主导叙事发生切换，建议打开跨市场剧本重新确认当前模板。`
        ),
      };
    });
};

const buildNarrativeTrendLookup = (tasks = []) => {
  return tasks.reduce((accumulator, task) => {
    if (task?.type !== 'cross_market' || task?.status === 'archived') {
      return accumulator;
    }
    const meta = extractTemplateMeta(task);
    const templateId = extractTemplateIdentity(task, meta);
    if (!templateId) {
      return accumulator;
    }

    const currentDriver = extractDominantDriver(meta);
    const history = task?.snapshot_history || [];
    const previousMeta = history[1]?.payload?.template_meta || {};
    const previousDriver = extractDominantDriver(previousMeta);
    const latestOverlay = extractAllocationOverlay(task);
    const latestThemeCore = meta?.theme_core || '';
    const latestThemeSupport = meta?.theme_support || '';
    const latestTopCompressedAsset = latestOverlay?.compressed_assets?.[0] || '';

    let trendLabel = '保持观察';
    let trendSummary = '最近没有检测到显著的叙事切换。';
    if (previousDriver?.key && currentDriver?.key && previousDriver.key !== currentDriver.key) {
      trendLabel = '主导切换';
      trendSummary = `主导驱动从 ${formatDriverLabel(previousDriver)} 切换到 ${formatDriverLabel(currentDriver)}`;
    } else if (currentDriver?.value && previousDriver?.value && Number(currentDriver.value) > Number(previousDriver.value)) {
      trendLabel = '驱动增强';
      trendSummary = `${formatDriverLabel(currentDriver)} 持续增强`;
    } else if (currentDriver?.value && previousDriver?.value && Number(currentDriver.value) < Number(previousDriver.value)) {
      trendLabel = '驱动走弱';
      trendSummary = `${formatDriverLabel(currentDriver)} 较前期走弱`;
    }

    accumulator[templateId] = {
      trendLabel,
      trendSummary,
      latestThemeCore,
      latestThemeSupport,
      latestTopCompressedAsset,
    };
    return accumulator;
  }, {});
};

export const buildHunterModel = ({ snapshot = {}, overview = {}, status = {}, researchTasks = [] }) => {
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
    const symbol = COMPANY_SYMBOL_MAP[item.company] || null;
    alerts.push({
      key: `supply-${index}`,
      title: `${item.company || '未知公司'} 人才结构预警`,
      severity: 'high',
      description: item.message || `dilution ratio ${item.dilution_ratio || 0}`,
      action: symbol
        ? buildPricingAction(symbol, 'alert_hunter', item.message || '人才结构预警')
        : buildCrossMarketAction('defensive_beta_hedge', 'alert_hunter', item.message || '人才结构预警'),
    });
  });

  const peopleSummary = overview?.people_layer_summary || {};
  (peopleSummary.fragile_companies || []).slice(0, 2).forEach((item) => {
    const symbol = item.symbol || COMPANY_SYMBOL_MAP[item.company_name] || null;
    alerts.push({
      key: `people-${item.symbol || item.company_name}`,
      title: `${item.company_name || item.symbol || '重点公司'} 组织脆弱度偏高`,
      severity: Number(item.people_fragility_score || 0) >= 0.7 ? 'high' : 'medium',
      description: item.summary || `people fragility ${Number(item.people_fragility_score || 0).toFixed(2)}`,
      action: symbol
        ? buildPricingAction(
            symbol,
            'alert_hunter',
            `${item.company_name || item.symbol} 的管理层/组织结构风险偏高，建议先回到定价研究确认是否属于结构性错价。`
          )
        : ACTION_MAP.observe,
    });
  });

  const departmentChaosSummary = overview?.department_chaos_summary || {};
  (departmentChaosSummary.top_departments || [])
    .filter((item) => item.label === 'chaotic' || Number(item.chaos_score || 0) >= 0.58)
    .slice(0, 2)
    .forEach((item) => {
      const departmentLabel = item.department_label || item.department || '政策主体';
      alerts.push({
        key: `department-chaos-${item.department || departmentLabel}`,
        title: `${departmentLabel} 政策混乱度偏高`,
        severity: Number(item.chaos_score || 0) >= 0.7 ? 'high' : 'medium',
        description: item.reason || `department chaos ${Number(item.chaos_score || 0).toFixed(2)}`,
        action: buildCrossMarketAction(
          'utilities_vs_growth',
          'alert_hunter',
          `${departmentLabel} 出现部门级政策反复或长官意志波动，建议先用跨市场模板确认政策错价传导。`
        ),
      });
    });

  const structuralDecayRadar = overview?.structural_decay_radar || {};
  const structuralDecayScore = Number(structuralDecayRadar.score || 0);
  if (structuralDecayRadar.label === 'decay_alert' || structuralDecayScore >= 0.68) {
    alerts.push({
      key: 'structural-decay-radar',
      title: '系统级结构衰败雷达进入警报区',
      severity: 'high',
      description: `${structuralDecayRadar.display_label || '结构衰败警报'} · ${structuralDecayRadar.action_hint || ''}`,
      action: buildCrossMarketAction(
        'defensive_beta_hedge',
        'decay_radar',
        structuralDecayRadar.action_hint || '结构衰败雷达进入警报区，建议先用防御模板复核宏观错价传导。'
      ),
    });
  } else if (structuralDecayRadar.label === 'decay_watch' || structuralDecayScore >= 0.44) {
    alerts.push({
      key: 'structural-decay-radar-watch',
      title: '系统级结构衰败信号升温',
      severity: 'medium',
      description: `${structuralDecayRadar.display_label || '衰败风险升温'} · ${structuralDecayRadar.action_hint || ''}`,
      action: buildCrossMarketAction(
        'defensive_beta_hedge',
        'decay_radar',
        structuralDecayRadar.action_hint || '结构衰败雷达进入观察区，建议复核人的维度和政策治理。'
      ),
    });
  }

  const sourceModeSummary = overview?.source_mode_summary || snapshot?.source_mode_summary || {};
  if (sourceModeSummary.label === 'fallback-heavy') {
    alerts.push({
      key: 'source-mode-fallback-heavy',
      title: '研究输入来源治理进入回退主导',
      severity: 'medium',
      description: sourceModeSummary.reason || '当前研究输入由 proxy/curated 回退源主导，建议压缩偏置强度并优先复核来源质量。',
      action: ACTION_MAP.observe,
    });
  } else if (sourceModeSummary.label === 'mixed' && sourceModeSummary.reason) {
    alerts.push({
      key: 'source-mode-mixed-watch',
      title: '研究输入来源治理处于混合观察态',
      severity: 'medium',
      description: sourceModeSummary.reason,
      action: ACTION_MAP.observe,
    });
  }

  (overview?.factors || [])
    .filter((item) => item.signal !== 0)
    .forEach((factor) => {
      alerts.push({
        key: `factor-${factor.name}`,
        title: `${formatFactorName(factor.name)} 出现偏移`,
        severity: Math.abs(Number(factor.z_score || 0)) > 1 ? 'high' : 'medium',
        description: `value=${Number(factor.value || 0).toFixed(3)} z=${Number(factor.z_score || 0).toFixed(3)}`,
        action:
          factor.signal === 1
            ? buildCrossMarketAction(
                FACTOR_TEMPLATE_MAP[factor.name],
                'alert_hunter',
                `${formatFactorName(factor.name)} 提示适合先看跨市场模板`
              )
            : buildPricingAction(
                FACTOR_SYMBOL_MAP[factor.name],
                'alert_hunter',
                `${formatFactorName(factor.name)} 提示适合先看单标的定价研究`
              ),
      });
    });

  const resonance = overview?.resonance_summary || {};
  const resonanceFactors = [
    ...(resonance.positive_cluster || []),
    ...(resonance.negative_cluster || []),
    ...(resonance.reversed_factors || []),
    ...(resonance.precursor || []),
    ...(resonance.weakening || []),
  ];
  if (resonance.label && resonance.label !== 'mixed' && resonanceFactors.length) {
    const primaryFactor = resonanceFactors[0];
    const clusterFactors = Array.from(new Set(resonanceFactors))
      .slice(0, 3)
      .map((name) => formatFactorName(name))
      .join('、');
    const severity =
      resonance.label === 'reversal_cluster'
        ? 'high'
        : resonance.label === 'precursor_cluster' || resonance.label === 'fading_cluster'
          ? 'medium'
          : 'high';

    alerts.push({
      key: `resonance-${resonance.label}`,
      title: `宏观因子共振 ${resonance.label}`,
      severity,
      description: `${resonance.reason} · ${clusterFactors}`,
      action: buildCrossMarketAction(
        FACTOR_TEMPLATE_MAP[primaryFactor],
        'alert_hunter',
        `${clusterFactors} 正在形成宏观共振，建议打开跨市场剧本复核当前模板。`
      ),
    });
  }

  alerts.push(...buildNarrativeShiftAlerts(researchTasks));

  const refreshSignals = buildResearchTaskRefreshSignals({ researchTasks, overview, snapshot });
  const taskById = Object.fromEntries((researchTasks || []).map((task) => [task.id, task]));

  const buildRefreshAction = (item) => {
    const task = taskById[item.taskId] || {};
    const title = item.title || formatTemplateName(item.templateId);
    const workbenchType = task?.type || 'cross_market';
    const peopleNote = item.peopleLayerDriven
      ? item.peopleLayerShift?.actionHint
        || item.peopleLayerShift?.currentSummary
        || '人的维度较保存时明显走弱，建议优先确认组织结构变化。'
      : '';
    const thesisNote = item.tradeThesisDriven
      ? item.tradeThesisShift?.actionHint
        || item.tradeThesisShift?.currentSummary
        || '交易 Thesis 相对保存时已漂移，建议优先确认主逻辑和组合腿是否仍然成立。'
      : '';
    const departmentChaosNote = item.departmentChaosDriven
      ? item.departmentChaosShift?.actionHint
        || item.departmentChaosShift?.currentSummary
        || item.departmentChaosShift?.lead
        || '部门级政策混乱较保存时明显恶化，建议确认政策执行主体是否已经改变组合风险。'
      : '';
    const structuralRadarNote = item.structuralDecayRadarDriven
      ? item.structuralDecayRadarShift?.actionHint
        || item.structuralDecayRadarShift?.currentSummary
        || item.structuralDecayRadarShift?.lead
        || '系统级结构衰败雷达较保存时继续升温，建议优先确认组合是否需要切到更强的防御构造。'
      : '';
    if (item.severity === 'high') {
      return buildWorkbenchAction(
        item.taskId,
        'alert_hunter',
        item.selectionQualityRunState?.active
          ? `${title} 当前结果已在降级强度下运行，更适合直接打开对应任务优先重看。`
          : item.structuralDecayRadarDriven && structuralRadarNote
            ? `${title} ${structuralRadarNote}`
          : item.structuralDecayDriven && item.structuralDecayShift?.actionHint
            ? `${title} ${item.structuralDecayShift.actionHint}`
            : item.tradeThesisDriven && thesisNote
              ? `${title} ${thesisNote}`
            : item.departmentChaosDriven && departmentChaosNote
              ? `${title} ${departmentChaosNote}`
          : item.reviewContextDriven && item.reviewContextShift?.actionHint
            ? `${title} ${item.reviewContextShift.actionHint}`
            : item.inputReliabilityDriven && item.inputReliabilityShift?.actionHint
              ? `${title} ${item.inputReliabilityShift.actionHint}`
              : item.peopleLayerDriven && peopleNote
                ? `${title} ${peopleNote}`
                : item.inputReliabilityDriven && item.inputReliabilityShift?.currentLead
                  ? `${title} ${item.inputReliabilityShift.currentLead}`
                  : `${title} 当前研究输入已经变化，建议直接打开对应任务更新判断。`,
        item.priorityReason || '',
        item.selectionQualityRunState?.active
          ? '优先重看任务'
          : item.structuralDecayRadarDriven
            ? '优先复核系统衰败雷达'
          : item.structuralDecayDriven
            ? '优先复核衰败判断'
          : item.tradeThesisDriven
            ? '优先复核交易 Thesis'
            : item.departmentChaosDriven
              ? '优先复核部门混乱'
          : item.reviewContextDriven
            ? getReviewContextActionLabel(item.reviewContextShift)
          : item.inputReliabilityDriven
              ? getInputReliabilityActionLabel(item.inputReliabilityShift)
              : item.peopleLayerDriven
                ? '优先复核人的维度'
                : '打开任务',
        workbenchType
      );
    }

    if (task?.type === 'trade_thesis') {
      return buildWorkbenchAction(
        item.taskId,
        'alert_hunter',
        item.tradeThesisDriven && thesisNote
          ? `${title} ${thesisNote}`
          : item.structuralDecayRadarDriven && structuralRadarNote
            ? `${title} ${structuralRadarNote}`
          : item.structuralDecayDriven && item.structuralDecayShift?.actionHint
            ? `${title} ${item.structuralDecayShift.actionHint}`
            : departmentChaosNote
              ? `${title} ${departmentChaosNote}`
            : peopleNote
              ? `${title} ${peopleNote}`
              : `${title} 当前交易 Thesis 已与最新定价证据出现漂移，建议直接打开任务复核。`,
        item.priorityReason || '',
        item.tradeThesisDriven
          ? '优先复核交易 Thesis'
          : item.structuralDecayRadarDriven
            ? '优先复核系统衰败雷达'
          : item.structuralDecayDriven
            ? '优先复核衰败判断'
          : item.departmentChaosDriven
              ? '优先复核部门混乱'
            : item.peopleLayerDriven
              ? '优先复核人的维度'
              : '打开交易 Thesis',
        'trade_thesis'
      );
    }

    if (task?.type === 'pricing') {
      return buildPricingAction(
        task?.symbol || '',
        'alert_hunter',
        peopleNote
          ? `${title} ${peopleNote}`
          : `${title} 当前人的维度或研究输入已变化，建议重新打开定价研究确认结论。`
      );
    }

    if (task?.type === 'macro_mispricing') {
      return buildWorkbenchAction(
        item.taskId,
        'alert_hunter',
        item.structuralDecayRadarDriven && structuralRadarNote
          ? `${title} ${structuralRadarNote}`
          : item.structuralDecayDriven && item.structuralDecayShift?.actionHint
            ? `${title} ${item.structuralDecayShift.actionHint}`
          : peopleNote
            ? `${title} ${peopleNote}`
            : `${title} 当前结构性衰败判断已经变化，建议直接打开衰败任务延续跟踪。`,
        item.priorityReason || '',
        item.structuralDecayRadarDriven
          ? '优先复核系统衰败雷达'
          : item.structuralDecayDriven
          ? '优先复核衰败判断'
          : item.peopleLayerDriven
            ? '优先复核人的维度'
            : '打开衰败任务',
        'macro_mispricing'
      );
    }

    return buildCrossMarketAction(
      item.templateId,
      'alert_hunter',
        item.selectionQualityRunState?.active
        ? `${title} 当前结果已在降级强度下运行，建议重新打开跨市场剧本优先重看。`
        : item.structuralDecayRadarDriven && structuralRadarNote
          ? `${title} ${structuralRadarNote}`
        : item.departmentChaosDriven && departmentChaosNote
          ? `${title} ${departmentChaosNote}`
        : item.reviewContextDriven && item.reviewContextShift?.actionHint
          ? `${title} ${item.reviewContextShift.actionHint}`
          : item.inputReliabilityDriven && item.inputReliabilityShift?.actionHint
            ? `${title} ${item.inputReliabilityShift.actionHint}`
            : item.peopleLayerDriven && peopleNote
              ? `${title} ${peopleNote}`
              : item.inputReliabilityDriven && item.inputReliabilityShift?.currentLead
                ? `${title} ${item.inputReliabilityShift.currentLead}`
                : `${title} 当前研究输入已经变化，建议重新打开跨市场剧本更新判断。`
    );
  };

  refreshSignals.prioritized
    .filter((item) => item.severity !== 'low')
    .slice(0, 3)
    .forEach((item) => {
      const recentComparisonLead = extractRecentComparisonLead(taskById[item.taskId]);
      const runStateSummary =
        item.selectionQualityRunState?.active && item.selectionQualityRunState?.label
          ? `降级运行 ${item.selectionQualityRunState.label}${
              item.selectionQualityRunState.reason ? `，${item.selectionQualityRunState.reason}` : ''
            }`
          : '';
      alerts.push({
        key: `refresh-${item.taskId}`,
        title: `${item.title || formatTemplateName(item.templateId)} ${item.refreshLabel}`,
        severity: item.severity,
        description: [
          item.summary,
          recentComparisonLead ? `最近两版：${recentComparisonLead}` : '',
          item.reviewContextDriven && item.reviewContextShift?.lead ? item.reviewContextShift.lead : '',
          item.inputReliabilityDriven && item.inputReliabilityShift?.currentLead
            ? `输入可靠度 ${item.inputReliabilityShift.savedLabel}→${item.inputReliabilityShift.currentLabel}，${item.inputReliabilityShift.currentLead}`
            : '',
          item.peopleLayerDriven && item.peopleLayerShift?.lead
            ? item.peopleLayerShift.lead
            : '',
          item.peopleLayerDriven && item.peopleLayerShift?.evidenceSummary
            ? `人事证据 ${item.peopleLayerShift.evidenceSummary}`
            : '',
          item.peopleLayerDriven && item.peopleLayerShift?.currentSummary
            ? item.peopleLayerShift.currentSummary
            : '',
          item.structuralDecayDriven && item.structuralDecayShift?.lead
            ? item.structuralDecayShift.lead
            : '',
          item.structuralDecayDriven && item.structuralDecayShift?.evidenceSummary
            ? `衰败证据 ${item.structuralDecayShift.evidenceSummary}`
            : '',
          item.structuralDecayDriven && item.structuralDecayShift?.currentSummary
            ? item.structuralDecayShift.currentSummary
            : '',
          item.structuralDecayRadarDriven && item.structuralDecayRadarShift?.lead
            ? item.structuralDecayRadarShift.lead
            : '',
          item.structuralDecayRadarDriven && item.structuralDecayRadarShift?.topSignalSummary
            ? `雷达焦点 ${item.structuralDecayRadarShift.topSignalSummary}`
            : '',
          item.structuralDecayRadarDriven && item.structuralDecayRadarShift?.currentSummary
            ? item.structuralDecayRadarShift.currentSummary
            : '',
          item.tradeThesisDriven && item.tradeThesisShift?.lead
            ? item.tradeThesisShift.lead
            : '',
          item.tradeThesisDriven && item.tradeThesisShift?.evidenceSummary
            ? `Thesis 证据 ${item.tradeThesisShift.evidenceSummary}`
            : '',
          item.departmentChaosDriven && item.departmentChaosShift?.lead
            ? item.departmentChaosShift.lead
            : '',
          item.departmentChaosDriven && item.departmentChaosShift?.currentSummary
            ? item.departmentChaosShift.currentSummary
            : '',
          item.departmentChaosDriven && item.departmentChaosShift?.topDepartmentLabel
            ? `部门焦点 ${item.departmentChaosShift.topDepartmentLabel}${
                item.departmentChaosShift.topDepartmentReason ? `，${item.departmentChaosShift.topDepartmentReason}` : ''
              }`
            : '',
          runStateSummary
            ? `${runStateSummary}，当前结果已在降级强度下运行，应优先重看`
            : '',
          item.selectionQualityDriven && item.selectionQualityShift?.currentLabel
            ? `自动降级 ${item.selectionQualityShift.currentLabel}`
            : '',
          item.biasCompressionDriven && item.biasCompressionShift?.topCompressedAsset
            ? `压缩焦点 ${item.biasCompressionShift.topCompressedAsset}`
            : '',
        ].filter(Boolean).join(' · '),
        action: buildRefreshAction(item),
      });
    });

  alerts.sort((a, b) => {
    const priority = { high: 0, medium: 1, low: 2 };
    return priority[a.severity] - priority[b.severity];
  });

  return alerts.slice(0, 8);
};

export const buildDecayWatchModel = (researchTasks = []) => {
  const existingMacroTasksBySymbol = Object.fromEntries(
    (researchTasks || [])
      .filter((task) => task?.type === 'macro_mispricing' && task?.status !== 'archived')
      .map((task) => [String(task?.symbol || '').trim().toUpperCase(), task])
      .filter(([symbol]) => Boolean(symbol))
  );

  return (researchTasks || [])
    .filter((task) => task?.type === 'pricing' && task?.status !== 'archived')
    .map((task) => {
      const payload =
        task?.snapshot?.payload
        || task?.snapshot_history?.[0]?.payload
        || {};
      const structuralDecay = payload?.structural_decay || payload?.implications?.structural_decay || {};
      const macroMispricingThesis = payload?.macro_mispricing_thesis || payload?.implications?.macro_mispricing_thesis || {};
      const peopleLayer = payload?.people_layer || {};
      const implications = payload?.implications || {};
      const gap = payload?.gap_analysis || {};
      const score = Number(structuralDecay?.score || 0);
      if (!score) {
        return null;
      }

      const symbol = String(task?.symbol || '').trim().toUpperCase();
      const existingMacroTask = existingMacroTasksBySymbol[symbol] || null;
      return {
        key: `decay-${task.id}`,
        taskId: task.id,
        macroTaskId: existingMacroTask?.id || '',
        symbol,
        title: task.title || symbol || 'Pricing task',
        label: structuralDecay.label || '待确认',
        actionLabel: structuralDecay.action || 'watch',
        score,
        summary: structuralDecay.summary || peopleLayer.summary || task?.snapshot?.summary || '',
        evidence: structuralDecay.evidence || [],
        dominantFailureLabel: structuralDecay.dominant_failure_label || '',
        peopleRisk: peopleLayer.risk_level || implications.people_risk || '',
        primaryView: implications.primary_view || gap.direction || '',
        peopleLayer,
        structuralDecay,
        macroMispricingThesis: {
          ...macroMispricingThesis,
          trade_legs: macroMispricingThesis?.trade_legs || [],
        },
        implications,
        gapAnalysis: gap,
        sourceTaskTitle: task.title || symbol || 'Pricing task',
        refreshLabel: score >= 0.72 ? '优先重看' : score >= 0.5 ? '重点观察' : '继续观察',
        action: existingMacroTask
          ? buildWorkbenchAction(
              existingMacroTask.id,
              'godeye_decay_watch',
              `${task.title || symbol} 已存在结构性衰败观察任务，建议直接打开工作台延续跟踪。`,
              peopleLayer.risk_level === 'high' ? 'people_layer' : '',
              '打开衰败任务',
              'macro_mispricing'
            )
          : buildWorkbenchAction(
              task.id,
              'godeye_decay_watch',
              `${task.title || symbol} 当前出现${structuralDecay.label || '结构性走弱'}迹象，建议打开任务复核长期判断。`,
              peopleLayer.risk_level === 'high' ? 'people_layer' : '',
              score >= 0.72 ? '优先重看任务' : '打开任务',
              'pricing'
            ),
      };
    })
    .filter(Boolean)
    .sort((left, right) => {
      if (right.score !== left.score) {
        return right.score - left.score;
      }
      return String(right.title || '').localeCompare(String(left.title || ''));
    })
    .slice(0, 5);
};

export const buildTradeThesisWatchModel = (researchTasks = [], refreshSignals = []) => {
  const refreshByTaskId = Object.fromEntries((refreshSignals || []).map((item) => [item.taskId, item]));

  return (researchTasks || [])
    .filter((task) => task?.type === 'trade_thesis' && task?.status !== 'archived')
    .map((task) => {
      const payload =
        task?.snapshot?.payload
        || task?.snapshot_history?.[0]?.payload
        || {};
      const thesisPayload = payload?.trade_thesis || {};
      const thesis = thesisPayload?.thesis || {};
      const structuralDecay =
        thesisPayload?.structural_decay
        || payload?.structural_decay
        || {};
      const peopleLayer =
        thesisPayload?.people_layer
        || payload?.people_layer
        || {};
      const resultsSummary = thesisPayload?.results_summary || {};
      const refresh = refreshByTaskId[task.id] || null;
      const leadLeg =
        thesis?.primary_leg?.symbol
        || thesis?.trade_legs?.[0]?.symbol
        || thesisPayload?.assets?.[0]?.symbol
        || String(task?.symbol || '').trim().toUpperCase();
      const symbol = String(leadLeg || task?.symbol || '').trim().toUpperCase();
      const score = Number(structuralDecay?.score || peopleLayer?.people_fragility_score || 0);
      const severityRank = refresh?.severity === 'high' ? 3 : refresh?.severity === 'medium' ? 2 : 1;

      return {
        key: `thesis-watch-${task.id}`,
        taskId: task.id,
        symbol,
        title: task.title || symbol || 'Trade Thesis',
        stance: thesis?.stance || thesisPayload?.stance || '',
        horizon: thesis?.expected_horizon || thesis?.horizon || resultsSummary?.horizon || '',
        leadLeg,
        tradeLegs: thesis?.trade_legs || [],
        summary: thesis?.summary || resultsSummary?.summary || task?.snapshot?.summary || '',
        resultsSummary,
        structuralDecay,
        peopleLayer,
        refreshLabel: refresh?.refreshLabel || '保持观察',
        refreshSeverity: refresh?.severity || 'low',
        driftLead: refresh?.tradeThesisShift?.lead || refresh?.summary || '',
        driftEvidence: refresh?.tradeThesisShift?.evidenceSummary || '',
        action: buildWorkbenchAction(
          task.id,
          'godeye_thesis_watch',
          refresh?.tradeThesisDriven && refresh?.tradeThesisShift?.actionHint
            ? `${task.title || symbol} ${refresh.tradeThesisShift.actionHint}`
            : `${task.title || symbol} 当前交易 Thesis 进入重点观察区，建议打开任务确认组合腿和执行条件。`,
          refresh?.priorityReason || '',
          refresh?.tradeThesisDriven ? '优先复核交易 Thesis' : '打开交易 Thesis',
          'trade_thesis'
        ),
        score,
        severityRank,
      };
    })
    .filter((item) => item.symbol || item.title)
    .sort((left, right) => {
      if (right.severityRank !== left.severityRank) {
        return right.severityRank - left.severityRank;
      }
      if (right.score !== left.score) {
        return right.score - left.score;
      }
      return String(left.title || '').localeCompare(String(right.title || ''));
    })
    .slice(0, 5);
};

export const buildMacroMispricingWorkbenchPayload = (item) => {
  const symbol = String(item?.symbol || '').trim().toUpperCase();
  const structuralDecay = item?.structuralDecay || {};
  const macroMispricingThesis = item?.macroMispricingThesis || {};
  const peopleLayer = item?.peopleLayer || {};
  const implications = item?.implications || {};
  const gapAnalysis = item?.gapAnalysis || {};
  const title = `[MacroMispricing] ${symbol || item?.title || 'Decay Watch'} 结构性衰败观察`;
  const highlights = [
    structuralDecay?.summary || '',
    peopleLayer?.summary || '',
    structuralDecay?.dominant_failure_label ? `主导失效模式 ${structuralDecay.dominant_failure_label}` : '',
    gapAnalysis?.direction ? `定价方向 ${gapAnalysis.direction}` : '',
  ].filter(Boolean);

  const payload = {
    type: 'macro_mispricing',
    title,
    source: 'godeye_decay_watch',
    symbol,
    note: `${symbol || item?.title || '该标的'} 已进入结构性衰败观察名单，建议按长期错价任务持续跟踪。`,
    context: {
      view: 'godsEye',
      source: 'godeye_decay_watch',
      symbol,
      stage: '结构性衰败观察',
      pricing_task_id: item?.taskId || '',
    },
    snapshot: {
      headline: `${symbol || item?.title || '目标'} 结构性衰败观察`,
      summary: structuralDecay?.summary
        || peopleLayer?.summary
        || `${symbol || item?.title || '该标的'} 出现人的维度与长期定价证据同时走弱的迹象。`,
      highlights: highlights.slice(0, 4),
      payload: {
        structural_decay: structuralDecay,
        macro_mispricing_thesis: macroMispricingThesis,
        people_layer: peopleLayer,
        implications,
        gap_analysis: gapAnalysis,
        source_task_id: item?.taskId || '',
        source_task_title: item?.sourceTaskTitle || item?.title || '',
        source_task_type: 'pricing',
      },
    },
  };
  const refreshPriorityEvent = buildMacroMispricingRefreshPriorityEvent(item);
  return refreshPriorityEvent
    ? { ...payload, refresh_priority_event: refreshPriorityEvent }
    : payload;
};

export const buildCrossMarketCards = (
  payload = {},
  overview = {},
  snapshot = {},
  researchTasks = [],
) => {
  const trendLookup = buildNarrativeTrendLookup(researchTasks);
  const refreshLookup = buildResearchTaskRefreshSignals({ researchTasks, overview, snapshot }).byTemplateId;
  const taskLookup = Object.fromEntries(
    (researchTasks || [])
      .filter((task) => task?.type === 'cross_market' && task?.status !== 'archived')
      .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')))
      .map((task) => [extractTemplateIdentity(task, extractTemplateMeta(task)), task])
      .filter(([templateId]) => Boolean(templateId))
  );

  return buildScoredCrossMarketCards(
    payload,
    overview,
    snapshot,
    (templateId, note) => buildCrossMarketAction(templateId, 'cross_market_overview', note)
  )
    .map((card) => {
      const trendMeta = trendLookup[card.id] || {};
      const refreshMeta = refreshLookup[card.id] || null;
      const recentComparisonLead = extractRecentComparisonLead(taskLookup[card.id]);
      const rankingPenalty = refreshMeta?.biasCompressionShift?.coreLegAffected
        ? 0.45
        : refreshMeta?.selectionQualityRunState?.active
          ? 0.3
          : refreshMeta?.reviewContextDriven
            ? 0.24
            : refreshMeta?.departmentChaosDriven
              ? 0.18
            : refreshMeta?.inputReliabilityDriven
              ? 0.16
              : refreshMeta?.selectionQualityDriven
                ? 0.2
                : 0;
      const adjustedScore = Number(Math.max(0, Number(card.recommendationScore || 0) - rankingPenalty).toFixed(2));

      return {
        ...card,
        baseRecommendationScore: card.recommendationScore,
        baseRecommendationTier: card.recommendationTier,
        rankingPenalty,
        rankingPenaltyReason: rankingPenalty
          ? refreshMeta?.biasCompressionShift?.coreLegAffected
            ? `核心腿 ${refreshMeta?.biasCompressionShift?.topCompressedAsset || ''} 已进入偏置收缩焦点，模板排序自动降级`
            : refreshMeta?.selectionQualityRunState?.active
                ? `当前结果已按 ${refreshMeta?.selectionQualityRunState?.label || 'degraded'} 强度运行，模板排序进一步下调`
              : refreshMeta?.reviewContextDriven
                ? `复核语境切换：${refreshMeta?.reviewContextShift?.lead || '最近两版已发生复核语境切换，模板排序谨慎下调'}`
                : refreshMeta?.departmentChaosDriven
                  ? `部门混乱变化：${refreshMeta?.departmentChaosShift?.lead || refreshMeta?.departmentChaosShift?.currentSummary || '部门级政策混乱恶化，模板排序谨慎下调'}`
                : refreshMeta?.inputReliabilityDriven
                  ? `输入可靠度变化：${refreshMeta?.inputReliabilityShift?.currentLead || '整体输入可靠度下降，模板排序适度下调'}`
                  : `当前主题已进入自动降级处理，模板排序谨慎下调`
          : '',
        recommendationScore: adjustedScore,
        recommendationTier: buildDisplayTier(adjustedScore),
        recommendationTone: buildDisplayTone(adjustedScore),
        ...trendMeta,
        ...(refreshMeta
          ? {
              taskRefreshTaskId: refreshMeta.taskId,
              taskRefreshSeverity: refreshMeta.severity,
              taskRefreshLabel: refreshMeta.refreshLabel,
              taskRefreshTone: refreshMeta.refreshTone,
              taskRefreshSummary: refreshMeta.summary,
              taskRefreshResonanceDriven: refreshMeta.resonanceDriven,
              taskRefreshPolicySourceDriven: refreshMeta.policySourceDriven,
              taskRefreshDepartmentChaosDriven: refreshMeta.departmentChaosDriven,
              taskRefreshInputReliabilityDriven: refreshMeta.inputReliabilityDriven,
              taskRefreshBiasCompressionDriven: refreshMeta.biasCompressionDriven,
              taskRefreshSelectionQualityDriven: refreshMeta.selectionQualityDriven,
              taskRefreshSelectionQualityShift: refreshMeta.selectionQualityShift,
              taskRefreshSelectionQualityRunState: refreshMeta.selectionQualityRunState,
              taskRefreshSelectionQualityActive: refreshMeta.selectionQualityRunState?.active || false,
              taskRefreshReviewContextDriven: refreshMeta.reviewContextDriven,
              taskRefreshReviewContextShift: refreshMeta.reviewContextShift,
              taskRefreshTradeThesisDriven: refreshMeta.tradeThesisDriven,
              taskRefreshTradeThesisShift: refreshMeta.tradeThesisShift,
              taskRefreshBiasCompressionShift: refreshMeta.biasCompressionShift,
              taskRefreshBiasCompressionCore: refreshMeta.biasCompressionShift?.coreLegAffected || false,
              taskRefreshTopCompressedAsset: refreshMeta.biasCompressionShift?.topCompressedAsset || '',
              taskRefreshPolicySourceShift: refreshMeta.policySourceShift,
              taskRefreshDepartmentChaosShift: refreshMeta.departmentChaosShift,
              taskRefreshInputReliabilityShift: refreshMeta.inputReliabilityShift,
              taskRecentComparisonLead: recentComparisonLead,
              taskAction:
                refreshMeta.severity === 'high'
                  ? buildWorkbenchAction(
                      refreshMeta.taskId,
                      'cross_market_overview',
                      refreshMeta.selectionQualityRunState?.active
                        ? `${card.name} 当前结果已在降级强度下运行，更适合直接打开对应任务优先重看。`
                        : refreshMeta.reviewContextDriven
                          ? `${card.name} 最近两版已发生复核语境切换，更适合直接打开对应任务优先重看。`
                          : refreshMeta.departmentChaosDriven && refreshMeta.departmentChaosShift?.actionHint
                            ? `${card.name} ${refreshMeta.departmentChaosShift.actionHint}`
                            : refreshMeta.departmentChaosDriven
                              ? `${card.name} 部门级政策混乱已经恶化，更适合直接打开对应任务优先复核。`
                          : refreshMeta.inputReliabilityDriven && refreshMeta.inputReliabilityShift?.actionHint
                            ? `${card.name} ${refreshMeta.inputReliabilityShift.actionHint}`
                            : refreshMeta.inputReliabilityDriven
                              ? `${card.name} 当前整体输入可靠度已经变化，更适合直接打开对应任务优先复核。`
                              : `${card.name} 当前更适合直接打开对应任务处理。`,
                      refreshMeta.priorityReason || '',
                      refreshMeta.selectionQualityRunState?.active
                        ? '优先重看任务'
                        : refreshMeta.reviewContextDriven
                          ? getReviewContextActionLabel(refreshMeta.reviewContextShift)
                          : refreshMeta.departmentChaosDriven
                            ? '优先复核部门混乱'
                          : refreshMeta.inputReliabilityDriven
                            ? getInputReliabilityActionLabel(refreshMeta.inputReliabilityShift)
                            : '打开任务'
                    )
                  : null,
            }
          : {}),
      };
    });
};
