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

## 问题反馈

欢迎通过 GitHub Issues 提交 Bug、改进建议或功能请求。
