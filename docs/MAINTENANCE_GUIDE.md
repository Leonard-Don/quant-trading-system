# 维护指南

## 常用检查

```bash
# 基础健康检查
curl http://localhost:8000/health

# 如需查看旧版系统状态接口（已废弃）
curl http://localhost:8000/system/status
```

## 日志与排障

- 日志目录: `logs/`
- 后端日志默认写入 `logs/system.log`

## 常见问题

- **无法获取数据**: 检查网络与数据源可用性
- **前端请求失败**: 确认 `REACT_APP_API_URL` 与后端端口一致
- **接口报 429**: 触发限流（默认 100 次/分钟）

## 数据与缓存

- 缓存目录: `cache/`
- 如需清空缓存，可删除 `cache/*.json`

## 文档维护

- API 文档可运行 `scripts/generate_api_docs.py` 生成
- 文档索引在 `docs/README.md`

---

**最后更新**: 2026-03-26
