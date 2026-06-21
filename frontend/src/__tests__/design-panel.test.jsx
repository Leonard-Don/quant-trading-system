import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Panel from '../design/components/Panel';

describe('Panel', () => {
  test('renders title, actions and body', () => {
    render(<Panel title="数据源健康" actions={<button>刷新</button>}>body content</Panel>);
    expect(screen.getByText('数据源健康')).toBeTruthy();
    expect(screen.getByRole('button', { name: '刷新' })).toBeTruthy();
    expect(screen.getByText('body content')).toBeTruthy();
  });

  test('omits the header when no title/actions', () => {
    render(<Panel>only body</Panel>);
    expect(screen.queryByTestId('panel-header')).toBeNull();
    expect(screen.getByText('only body')).toBeTruthy();
  });
});
