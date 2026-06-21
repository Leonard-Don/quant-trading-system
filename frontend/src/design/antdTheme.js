import { theme as antdTheme } from 'antd';
import { antdTokenInputs, RADII, FONT_SANS } from './tokens';

export function buildAntdTheme(isDark) {
  const t = isDark ? antdTokenInputs.dark : antdTokenInputs.light;
  return {
    algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: t.colorPrimary,
      borderRadius: parseInt(RADII.md, 10),
      fontFamily: FONT_SANS,
      colorBgContainer: t.colorBgContainer,
      colorBgElevated: t.colorBgElevated,
      colorBgLayout: t.colorBgLayout,
      colorBorder: t.colorBorder,
      colorText: t.colorText,
      colorTextSecondary: t.colorTextSecondary,
    },
    components: {
      Layout: { headerBg: t.colorBgLayout, siderBg: t.colorBgLayout, bodyBg: t.colorBgLayout },
      Card: { colorBgContainer: t.colorBgContainer },
      Table: { colorBgContainer: 'transparent', headerBg: t.colorBgElevated },
      Input: { colorBgContainer: t.colorBgContainer },
      Select: { colorBgContainer: t.colorBgContainer },
    },
  };
}
