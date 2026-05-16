# 贡献指南

感谢你对 `quant-trading-system` 的关注。

## 开发流程

1. Fork 本仓库并创建功能分支
2. 安装依赖并确认本地可以启动前后端
3. 完成修改后运行相关测试
4. 提交清晰的 commit message
5. 发起 Pull Request，并说明修改目的与验证方式

## 本地启动

```bash
pip install -r requirements-dev.txt
cd frontend && npm install
cd ..
./scripts/start_system.sh
```

## 提交建议

- 保持 PR 聚焦，避免混入无关改动
- 如果涉及 UI，请附上截图
- 如果涉及 API，请同步更新文档
- 新功能尽量补充测试

## CI 质量门槛

PR 必须通过这两道防回涨门槛，本地都能跑：

```bash
# Ruff 基线门——发现数不允许增长（首版基线 = scripts/ruff_baseline_count.txt）
python scripts/check_ruff_baseline.py

# Coverage 阈值——当前锁在 60%
pytest tests/unit tests/integration -m "not perf" \
  --cov=src --cov=backend --cov-fail-under=60 -q
```

如果你顺手清理了一批 lint 发现，请同步降低基线：
`python scripts/check_ruff_baseline.py --write-baseline`，
然后把 `scripts/ruff_baseline_count.txt` 一起提交。
完整 re-baseline 流程见 `docs/MAINTENANCE_GUIDE.md` 第 9 节。

## 问题反馈

欢迎通过 GitHub Issues 提交 Bug、改进建议或功能请求。
