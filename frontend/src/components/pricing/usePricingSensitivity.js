import { useCallback, useEffect, useState } from 'react';

import { getValuationSensitivityAnalysis } from '../../services/api';
import { useSafeMessageApi } from '../../utils/messageApi';
import { resolveAnalysisSymbol } from '../../utils/pricingResearch';

export default function usePricingSensitivity({ data, researchContextSymbol, symbol }) {
  const message = useSafeMessageApi();
  const [sensitivity, setSensitivity] = useState(null);
  const [sensitivityLoading, setSensitivityLoading] = useState(false);
  const [sensitivityError, setSensitivityError] = useState(null);
  const [sensitivityControls, setSensitivityControls] = useState({
    wacc: 8.2,
    initialGrowth: 12,
    terminalGrowth: 2.5,
    fcfMargin: 80,
  });

  useEffect(() => {
    const anchor = data?.valuation?.dcf?.sensitivity_anchor;
    if (!anchor) return;
    setSensitivityControls({
      wacc: Number((anchor.wacc || 0) * 100).toFixed(1) * 1,
      initialGrowth: Number((anchor.initial_growth || 0) * 100).toFixed(1) * 1,
      terminalGrowth: Number((anchor.terminal_growth || 0) * 100).toFixed(1) * 1,
      fcfMargin: Number((anchor.fcf_margin || 0) * 100).toFixed(0) * 1,
    });
  }, [data]);

  const handleRunSensitivity = useCallback(async () => {
    const targetSymbol = resolveAnalysisSymbol(symbol, researchContextSymbol || '');
    if (!targetSymbol) {
      message.warning('请先选择一个标的再做敏感性分析');
      return;
    }

    setSensitivityLoading(true);
    setSensitivityError(null);
    try {
      const payload = await getValuationSensitivityAnalysis({
        symbol: targetSymbol,
        wacc: Number(sensitivityControls.wacc) / 100,
        initial_growth: Number(sensitivityControls.initialGrowth) / 100,
        terminal_growth: Number(sensitivityControls.terminalGrowth) / 100,
        fcf_margin: Number(sensitivityControls.fcfMargin) / 100,
        dcf_weight: data?.valuation?.fair_value?.dcf_weight,
        comparable_weight: data?.valuation?.fair_value?.comparable_weight,
      });
      setSensitivity(payload);
    } catch (err) {
      setSensitivityError(err.userMessage || err.message || '敏感性分析失败');
      setSensitivity(null);
    } finally {
      setSensitivityLoading(false);
    }
  }, [
    data?.valuation?.fair_value?.comparable_weight,
    data?.valuation?.fair_value?.dcf_weight,
    message,
    researchContextSymbol,
    sensitivityControls,
    symbol,
  ]);

  return {
    handleRunSensitivity,
    sensitivity,
    sensitivityControls,
    sensitivityError,
    sensitivityLoading,
    setSensitivityControls,
  };
}
