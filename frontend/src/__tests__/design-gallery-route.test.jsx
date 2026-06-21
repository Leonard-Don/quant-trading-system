import { describe, test, expect } from 'vitest';
import { readViewStateFromLocation } from '../App';

describe('readViewStateFromLocation', () => {
  test('resolves the dev-only __gallery view', () => {
    expect(readViewStateFromLocation('?view=__gallery').currentView).toBe('__gallery');
  });

  test('coerces unknown views to the backtest default', () => {
    expect(readViewStateFromLocation('?view=nope').currentView).toBe('backtest');
  });

  test('keeps a real public view', () => {
    expect(readViewStateFromLocation('?view=realtime').currentView).toBe('realtime');
  });

  test('maps the alerts alias to realtime with an aux intent', () => {
    const s = readViewStateFromLocation('?view=alerts', 3);
    expect(s.currentView).toBe('realtime');
    expect(s.realtimeAuxIntent).toBe('alerts:3');
  });
});
