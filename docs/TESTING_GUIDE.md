# 测试指南

## 测试结构

- `tests/unit/` 单元测试
- `tests/integration/` 集成测试
- `tests/e2e/` 浏览器端到端回归
- `tests/manual/` 手工/调试脚本

## 运行测试

```bash
# 默认运行 unit / integration / system
python scripts/run_tests.py

# 单元测试
python scripts/run_tests.py --unit

# 集成测试
python scripts/run_tests.py --integration

# 行业热度 E2E 回归
python scripts/run_tests.py --e2e-industry

# 覆盖率报告
python scripts/run_tests.py --coverage
```

也可以直接在 `tests/e2e/` 目录下运行：

```bash
npm run verify:industry
```

## 测试分层说明

- `unit`：纯 Python 单元测试，不依赖已启动服务
- `integration`：接口与模块集成测试，可能依赖第三方数据源
- `system`：系统级脚本检查
- `e2e-industry`：浏览器回归，要求本地前后端服务均已启动

## 注意事项

- 部分测试依赖网络或第三方数据源
- 运行前请确保后端依赖已安装
- 默认 `python scripts/run_tests.py` 会在未检测到本地服务时自动跳过 E2E
- 行业热度 E2E 需要本地服务已启动：

```bash
python scripts/start_backend.py
./scripts/start_frontend.sh
```

---

**最后更新**: 2026-03-20
