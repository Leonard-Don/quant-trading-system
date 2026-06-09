import { Tabs } from 'antd';

import LowVolatilityScreen from './LowVolatilityScreen';
import LowVolPortfolioPanel from './LowVolPortfolioPanel';

// 低波动 view = the validated signal surfaced two ways:
//   选股   — point-in-time low-vol ranking (the screen)
//   策略回测 — net-of-cost low-vol basket backtest vs equal-weight
// Default Tabs keep a pane mounted after first activation (the screen fetches
// once on mount; the backtest pane waits for an explicit "运行回测" click).
const LowVolatilityView = () => (
  <Tabs
    defaultActiveKey="screen"
    items={[
      { key: 'screen', label: '选股', children: <LowVolatilityScreen /> },
      { key: 'portfolio', label: '策略回测', children: <LowVolPortfolioPanel /> },
    ]}
  />
);

export default LowVolatilityView;
