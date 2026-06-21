import { describe, test, expect } from 'vitest';
import { render } from '@testing-library/react';
import { PageHero, StatCard, Panel, SectionHeader, StatusPill } from '../design/components';

describe('design primitives avoid arbitrary-value (bracket) classes', () => {
  test('no rendered element uses a [..] class (they break jsdom+antd getByRole selectors)', () => {
    const { container } = render(
      <div>
        <PageHero eyebrow="E" title="T" subtitle="S" />
        <StatCard label="L" value="1" accent />
        <Panel title="P">body</Panel>
        <SectionHeader eyebrow="E" title="T" />
        <StatusPill tone="success">ok</StatusPill>
      </div>,
    );
    container.querySelectorAll('[class]').forEach((el) => {
      expect(el.getAttribute('class')).not.toMatch(/[[\]]/);
    });
  });
});
