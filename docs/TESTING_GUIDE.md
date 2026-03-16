# 测试指南

## 测试结构

- `tests/unit/` 单元测试
- `tests/integration/` 集成测试
- `tests/e2e/` 浏览器端到端回归
- `tests/manual/` 手工/调试脚本

## 运行测试

```bash
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

## 注意事项

- 部分测试依赖网络或第三方数据源
- 运行前请确保后端依赖已安装
- 行业热度 E2E 需要本地服务已启动：

```bash
python scripts/start_backend.py
./scripts/start_frontend.sh
```

---

**最后更新**: 2026-03-13
