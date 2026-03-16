# 性能优化指南

本项目已具备基础的缓存与并发能力，以下为当前实现与可优化方向。

## 当前实现

- `src/utils/cache.py` 提供内存/磁盘缓存
- `src/data/data_manager.py` 使用线程池并发获取数据
- 回测与分析模块使用向量化计算

## 可优化方向

- **数据源调用**: 将 `DataManager` 全面切换到 `providers` 工厂以便自动故障转移
- **缓存策略**: 为大体量回测结果增加 TTL 与缓存清理策略
- **异步 IO**: 对耗时数据请求统一使用 `run_in_executor`
- **批量接口**: 增加批量获取历史数据接口以减少多次请求

## 性能测试

```bash
python scripts/performance_test.py
```

---

**最后更新**: 2026-02-05
