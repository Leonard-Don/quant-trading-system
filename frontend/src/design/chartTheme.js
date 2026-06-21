import { chartPalette } from './tokens';

// Single place charts read their colors from, so recharts / lightweight-charts
// stop hardcoding #00b578 / #ff3030 and follow the active theme instead.
export function getChartTheme(isDark) {
  const p = isDark ? chartPalette.dark : chartPalette.light;
  return {
    up: p.up,
    down: p.down,
    accent: p.accent,
    grid: p.grid,
    axis: p.axis,
    series: [p.accent, '#818cf8', p.up, '#fbbf24', p.down],
  };
}
