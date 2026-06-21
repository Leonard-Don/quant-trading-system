# 设计:前端设计系统地基 + today 试点(阶段 0)

> Status: approved (design), pending implementation plan
> Date: 2026-06-21
> Goal owner: Leonard-Don (single-user A-share research tool)

## 背景与目标

前端(React 18 + Vite + Ant Design 5,~140 文件 / ~7.8 万行)视觉底子不错,品牌为
"午夜金融 / Midnight Fintech"(深石板蓝 `#0f172a` + sky-blue `#38bdf8` + 玻璃态)。
现状评估(本会话实测四个工作区 + 设计令牌通读)结论:**审美在线、体系成熟,但工程层面有美观隐患**:

- `src/index.css` 5737 行,内含 **200+ 个 `!important`** 在硬怼 antd 默认值,升级易回归。
- `src/components/realtime/realtimePanelStyles.js` 是 **1143 行 JS 内联 CSS 字符串**,无 HMR、断点与
  index.css 重复。
- `Inter` 在 `body` font-family 中被声明,但 `index.html` / `index.css` 头部**没有任何 `@font-face`
  或 webfont 引入**,大概率 fallback 到系统字体。
- 图表颜色硬编码(`#00b578` 涨 / `#ff3030` 跌),不读令牌。
- 行业热力树图小色块**文字裁切/重叠**(实测可见 bug):`HeatmapTreemap.jsx` 在密集 cell 未做内容降级。
- 全套**无视觉回归测试**,以上 polish 类问题 CI 拦不住。

**最终目标(用户选定)**:在**保留"午夜金融"品牌气质**的前提下,把工艺打磨到"高级"质感
(参见本会话的目标样张),并**重做底层样式架构**(消灭 CSS 技术债)。

**用户已定的关键决策**:

- 改造力度:**整体改版**(重塑视觉语言 + 重构样式系统)。
- 视觉方向:**沿用"午夜金融"深色 + 精修**(品牌不变)。
- 执行路线:**令牌单一来源 + Tailwind CSS v4,保留 Ant Design 5**(增量、不破坏现有 56 个测试)。
- 阶段 0 试点:**今日研究 today** 工作区,端到端验证。

## 为什么拆阶段

"整体改版"覆盖 6 个工作区 / ~140 组件,塞进一个 spec 会失控。故拆:

- **阶段 0(本 spec)**:设计系统地基(令牌层 + 基础组件 + 动效 + 字体 + 图表主题)+ **today 试点端到端** +
  树图裁切修复 + 质量护栏。产出可复用底座 + 一个达标范例。
- **阶段 1..n(后续,各自独立 plan)**:把基础组件**逐工作区**铺开(backtest / realtime / industry /
  paper / lowvol)。realtime 阶段负责删除 `realtimePanelStyles.js`。
- **收尾阶段**:浅色主题全面平权 + 全局微交互打磨。

后续阶段的规模/形态依赖阶段 0 落定的令牌与组件接口,故本 spec 不涵盖。

## 阶段 0 范围

### 令牌单一来源(核心架构)

一份 `src/design/tokens.js` 作为唯一真相源,向三个消费端分发,杜绝漂移:

```
src/design/tokens.js
   ├─► 运行时注入 :root / [data-theme='light'] 的 CSS 变量(src/design/applyTokens.js)
   ├─► Tailwind @theme:utility 名映射到 var(--token)(语义变量,主题切换自动翻转)
   └─► antd ConfigProvider theme:由 tokens 构建(src/design/antdTheme.js)
```

- **令牌分层**:
  - 原始标度(raw):色阶、间距阶(4/8 基)、圆角阶、字号/行高/字距阶、时长/缓动。
  - 语义令牌(semantic,组件只用这层):
    `color.bg.{base,surface,raised,inset}`、`color.text.{primary,secondary,muted,inverse}`、
    `color.accent`、`color.state.{up,down,warn,info,success,danger}`、
    `border.{hairline,strong,focus}`、`radius.{sm,md,lg,pill}`、`space.*`、
    `type.{size,leading,tracking}`、`elevation.*`、`motion.{dur.*,ease.*}`。
- **深浅主题**:语义令牌按主题解析;`[data-theme='light']` 覆写 CSS 变量;antd 切 algorithm +
  对应 token 集;Tailwind utility 因引用语义变量自动翻转。`ThemeContext` 保持现有 API(`isDarkMode`/
  `toggleTheme`),内部改为从 tokens 驱动。

### 基础组件(隔离单元,today 用其重写)

| 组件 | 职责 | 备注 |
|---|---|---|
| `src/design/components/Surface.jsx` | 基础表面(flat/raised/inset 变体):背景/发丝边框/圆角 | 替代散装 Card 样式 |
| `src/design/components/Panel.jsx` | Surface + 可选头部(标题/图标/右侧操作)+ 内边距 | 工作区面板统一壳 |
| `src/design/components/PageHero.jsx` | 共享 hero:eyebrow + 标题 + 副标题 + KPI 槽 | 6 个工作区共用骨架 |
| `src/design/components/MetricGrid.jsx` + `StatCard.jsx` | 响应式 KPI 网格 + 指标卡(micro 标签 + tabular 数字 + 可选 delta/趋势) | 数字 `tabular-nums` |
| `src/design/components/SectionHeader.jsx` | eyebrow + 标题 + 操作行 | |
| `src/design/components/StatusPill.jsx` | 圆点 + 标签 + tone(success/warn/danger/info/neutral) | 替代满色块状态 |
| `src/design/components/Toolbar.jsx` | 过滤 / segmented 控件行的容器 | |

每个组件:单一职责、props 接口清晰、可独立测试;不依赖具体业务数据。

### 动效原语(framer-motion,克制)

| 原语 | 用途 |
|---|---|
| `src/design/motion/FadeIn.jsx` / `Stagger.jsx` | 卡片/面板入场 |
| `src/design/motion/AnimatedNumber.jsx` | KPI 数字滚动 |
| 路由 / 标签切换淡入 | 接到 App 视图切换与 antd Tabs |

统一从 `motion` 令牌取时长/缓动;`prefers-reduced-motion` 下降级为无动画。framer-motion 按需懒加载,
避免拖慢首屏。

### 字体 / 图表 / Tailwind 接入

- **字体**:`@fontsource/inter` 自托管 + `font-display: swap` + 预加载关键字重;数字启用 tabular-nums。
- **图表主题**:`src/design/chartTheme.js` 让 `recharts` / `lightweight-charts` 读同一套令牌,
  去掉硬编码涨跌色。阶段 0 仅接 today 命中的图表;全量接入随各工作区阶段。
- **Tailwind v4**:**关闭 preflight**(避免与 antd reset 冲突),仅启用 `@theme` + utilities,JIT 按需产出;
  通过 PostCSS 接入现有 Vite 构建。

### 顺带的高可见修复(独立小修)

- **树图文字裁切/重叠**:`src/components/industry/HeatmapTreemap.jsx`(配合
  `src/utils/squarifiedTreemap.js`)按 tile 可用面积做内容降级(小块隐藏龙头行/只数)+
  `text-overflow: ellipsis` 兜底。**不依赖 today 试点,可独立交付**。

### 阶段 0 的清理边界(不扩散)

- 只清理 **today 渲染路径命中的 `!important`** 与散装样式;其余文件的 `!important` 留给对应工作区阶段。
- **不**在阶段 0 删除 `realtimePanelStyles.js`(属 realtime,随 realtime 阶段删除)。

## 测试与质量护栏

- **保持现有 56 个 Vitest 全绿**;`src/__tests__/app-layout-css-contract.test.js` 按新令牌/类名更新。
- 新增基础组件单测(Surface/Panel/StatCard/StatusPill/PageHero 等的渲染与变体)。
- **视觉回归基线(Playwright,复用现有 E2E 设施)**:today(深 + 浅)+ 基础组件画廊截图基线。
- **stylelint**:禁止新增 `!important`、强制颜色/间距走令牌变量(防止技术债回流)。
- today 重构后:键盘可达性与对比度不回退(沿用现有可达性约定)。

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| Tailwind ↔ antd 优先级 / reset 冲突 | 关闭 preflight;限定 base 层;必要时给 Tailwind 容器作用域 |
| 字体 FOUC | 自托管 + `font-display: swap` + 预加载 |
| 测试改动面过大 | 试点只限 today;基础组件接口稳定后再铺开;契约测试同步更新 |
| 包体增大(Tailwind / framer-motion) | Tailwind JIT 仅产出用到的类;framer-motion 懒加载;构建后对比 chunk 体积 |
| 令牌三端漂移 | 单一来源 `tokens.js`,antd theme 与 CSS 变量均由其派生,禁止旁路硬编码(stylelint 守) |

## 成功标准

- today 在深 / 浅两套主题下达到目标样张质感(hero + KPI + 面板 + 状态胶囊)。
- 基础组件就位且有单测;App 其余工作区可零成本复用这些组件。
- 树图文字裁切消失。
- today 渲染路径 `!important` 清零。
- 视觉回归基线建立;全部 Vitest 测试绿;构建通过。

## 不在本阶段范围(Out of scope)

- 其余 5 个工作区(backtest / realtime / industry / paper / lowvol)的视觉改造。
- 浅色主题在全 app 的全面平权(阶段 0 仅 today)。
- 组件库替换(继续保留 antd 承载表格 / 表单 / 日期 / 弹窗等重型组件)。
- 删除 `realtimePanelStyles.js`(随 realtime 阶段)。
- 引入新图标库 / Storybook(可选增强,非阶段 0 必需)。
