#!/bin/bash

# 量化交易系统停止脚本

echo "🛑 正在停止量化交易系统..."

# 从PID文件读取进程ID并停止
if [ -f "logs/backend.pid" ]; then
    BACKEND_PID=$(cat logs/backend.pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID
        echo "✅ 后端服务已停止 (PID: $BACKEND_PID)"
    else
        echo "⚠️  后端服务已经停止"
    fi
    rm -f logs/backend.pid
fi

if [ -f "logs/frontend.pid" ]; then
    FRONTEND_PID=$(cat logs/frontend.pid)
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID
        echo "✅ 前端服务已停止 (PID: $FRONTEND_PID)"
    else
        echo "⚠️  前端服务已经停止"
    fi
    rm -f logs/frontend.pid
fi

# 强制杀死可能残留的进程
pkill -f "uvicorn.*backend.main:app" 2>/dev/null
pkill -f "react-scripts start" 2>/dev/null
pkill -f "node.*react-scripts" 2>/dev/null

echo "🏁 系统已完全停止"
