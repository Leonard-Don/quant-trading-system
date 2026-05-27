import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const cssPath = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'index.css');
const readAppCss = () => readFileSync(cssPath, 'utf8');

const extractCollapsedBodyRule = (css) => {
  const match = css.match(/\.app-main-shell>\.app-main-sider\.ant-layout-sider-collapsed~\.app-main-body\s*\{(?<body>[^}]+)\}/);
  return match?.groups?.body || '';
};

describe('app layout css contract', () => {
  test('desktop collapsed sider still reserves its fixed rail gutter', () => {
    const css = readAppCss();
    const collapsedBodyRule = extractCollapsedBodyRule(css);

    expect(css).toContain('--app-sider-collapsed-width: 64px;');
    expect(collapsedBodyRule).toContain('margin-left: var(--app-sider-collapsed-width);');
    expect(collapsedBodyRule).toContain('width: calc(100% - var(--app-sider-collapsed-width));');
  });

  test('mobile overlay layout overrides the desktop collapsed gutter', () => {
    const css = readAppCss();

    expect(css).toMatch(/@media\s*\(max-width:\s*992px\)[\s\S]*\.app-main-shell>\.app-main-sider\.ant-layout-sider-collapsed~\.app-main-body\s*\{[\s\S]*margin-left:\s*0;[\s\S]*width:\s*100%;/);
  });
});
