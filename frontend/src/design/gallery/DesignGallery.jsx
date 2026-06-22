import { PageHero, MetricGrid, StatCard, Panel, StatusPill, SectionHeader, Toolbar } from '../components';
import { FadeIn, AnimatedNumber } from '../motion';

export default function DesignGallery() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <PageHero
        eyebrow="BACKTEST · 策略回测"
        title="策略回测工作台"
        subtitle="从策略配置、执行到结果研判的一体化回测流。"
        metrics={
          <MetricGrid className="w-[280px]">
            <StatCard label="待处理" value={<AnimatedNumber value={10} />} />
            <StatCard label="回测快照" value={<AnimatedNumber value={24} />} accent />
            <StatCard label="实时记录" value="8" />
            <StatCard label="行业观察" value="10" />
          </MetricGrid>
        }
      />

      <Panel title="数据源健康" actions={<StatusPill tone="info">ths_primary</StatusPill>}>
        <Toolbar>
          <StatusPill tone="success">已连接</StatusPill>
          <StatusPill tone="warn">被拦截</StatusPill>
          <StatusPill tone="danger">失败</StatusPill>
        </Toolbar>
      </Panel>

      <FadeIn>
        <Panel>
          <SectionHeader eyebrow="SECTION" title="行业扫描与轮动" actions={<StatusPill tone="neutral">市值加权</StatusPill>} />
        </Panel>
      </FadeIn>
    </div>
  );
}
