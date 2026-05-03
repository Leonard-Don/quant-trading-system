# Batch A — Repo Hygiene (设计文档)

- 日期: 2026-05-03
- 范围: `quant-trading-system` 项目评估总结中"轻量改进建议"里的仓库卫生类条目
- 状态: 已与用户确认 (A3 选方案 ii — Dependabot 安全更新模式)

## 背景

5 月 3 日的项目评估指出 3 条仓库卫生层面的债务：

1. `verify_result.html` (1.3 MB) 留在工作区根目录，虽已 gitignore 但占空间且容易引起误会。
2. `scripts/health_check.py` 运行后会在仓库根生成 `health_check_report.json`，但该文件未被 gitignore，每次执行都会污染 `git status`。
3. 仓库无任何依赖巡检机制，`requirements.txt` 用 `==` 严格 pin、前端用 `^` 范围锁，缺少对 CVE 的主动监控。

整体评估结论是这些都属于"30 分钟成本、低风险"项，应优先清理掉以让后续重构批次起跑姿势更干净。

## 子任务

### A1. 删除 `verify_result.html`

- 该文件为 Playwright E2E 测试运行后生成的 HTML 快照（dark-theme React DOM dump）。
- 已确认：`.gitignore:116` 含 `verify_result.html`、`.gitignore:117` 含 `tests/e2e/verify_result.html`，文件从未进入版本历史。
- E2E 跑一次就会重新生成，删除安全。
- 操作：`rm verify_result.html`（仅删根目录这份，不动 `tests/e2e/` 路径下的预期产出位置）。

### A2. `health_check_report.json` 加入 gitignore

- 文件由 `scripts/health_check.py` 写入仓库根。
- 操作：在 `.gitignore` 第 116 行 `verify_result.html` 附近追加：
  ```
  health_check_report.json
  ```
- 同时清理工作区现存的 `health_check_report.json`（该文件未跟踪，删除即可）。

### A3. 月度依赖安全巡检 — Dependabot security-only

- 新增 `.github/dependabot.yml`，配置 `pip` + `npm` 两个生态，月度扫描。
- 关键策略：仅当存在已知 CVE 时开启 PR，避免常规版本升级产生的噪音（项目当前 `==` pin 极严，全量升级会一次开一大批 PR）。
- 配置示例：

  ```yaml
  version: 2
  updates:
    - package-ecosystem: "pip"
      directory: "/"
      schedule:
        interval: "monthly"
      open-pull-requests-limit: 5
      labels: ["dependencies", "security"]
      # 仅安全更新：不指定 allow，但通过 ignore 把所有 update-type 屏蔽掉，
      # 这样 Dependabot 只会开 security PR
      ignore:
        - dependency-name: "*"
          update-types:
            - "version-update:semver-patch"
            - "version-update:semver-minor"
            - "version-update:semver-major"

    - package-ecosystem: "npm"
      directory: "/frontend"
      schedule:
        interval: "monthly"
      open-pull-requests-limit: 5
      labels: ["dependencies", "security"]
      ignore:
        - dependency-name: "*"
          update-types:
            - "version-update:semver-patch"
            - "version-update:semver-minor"
            - "version-update:semver-major"
  ```

- 后续如需"全量版本升级"模式，把 `ignore` 块去掉即可，无需重新设计配置。
- **前置依赖**：要让"security PR"真正出现，还需要在 GitHub 仓库 `Settings → Code security and analysis` 中开启 **Dependabot security updates** 与 **Dependency graph** 两个开关。这一步无法通过仓库内文件配置完成，需要由仓库管理员手动在 Web UI 切换。如果当前未开，本批 PR 合入后实际只会"屏蔽所有版本升级 PR"，要等到上述开关开启后才会收到 CVE 告警 PR。`dependabot.yml` 入仓本身不会引入回归。

### 不在范围内（明确排除）

- 不动 `tests/e2e/verify_result.html` 这条 ignore 规则；
- 不修改 `scripts/health_check.py` 的输出路径或行为；
- 不引入 `pip-audit` / `npm audit` 的 CI workflow（如未来想"主动扫描型"再单独立项）；
- 不调整 `requirements.txt` 的 pin 策略；
- 不为 GitHub Actions ecosystem 配 dependabot（CI 配置稳定，暂无需求）。

## 验证标准

| 编号 | 条件 |
|------|------|
| A1 | 工作区根目录无 `verify_result.html`；`tests/e2e/verify_result.html` 路径策略不变；E2E 跑一次能正常生成新文件 |
| A2 | 工作区根目录无 `health_check_report.json`；运行 `python3 scripts/health_check.py` 后 `git status` 不再出现该文件 |
| A3 | `.github/dependabot.yml` 存在且 YAML 解析无误（`python -c "import yaml; yaml.safe_load(open('.github/dependabot.yml'))"`）；提交后 GitHub `Insights → Dependency graph → Dependabot` 页面识别到配置；仓库 `Settings → Code security and analysis` 中已开启 **Dependabot security updates**（人工核对项） |

## 风险

- A1: 极低。文件可重新生成。
- A2: 极低。纯配置追加。
- A3: 低。Dependabot 配置错误最坏的后果是 GitHub 给一个解析失败的告警，不会破坏 CI。

## 实施顺序

A1 → A2 → A3，全部放到一个 commit（"chore: tidy repo hygiene + dependabot security audits"）。三件事都属于配置/清理，没有相互依赖，但放一起便于回滚。
