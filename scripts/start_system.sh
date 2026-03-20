#!/bin/bash

# 量化交易系统统一启动脚本
# 前后端一键启动

echo "🚀 正在启动量化交易系统..."
echo "=================================="

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，请先安装Python3"
    exit 1
fi

# 检查Node.js环境
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 未安装，请先安装Node.js"
    exit 1
fi

# 检查npm环境
if ! command -v npm &> /dev/null; then
    echo "❌ npm 未安装，请先安装npm"
    exit 1
fi

# 安装Python依赖
echo "📦 检查Python依赖..."
if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "✅ Python依赖安装完成"
    else
        echo "⚠️  Python依赖安装可能有问题，继续启动..."
    fi
else
    echo "⚠️  requirements.txt 文件未找到"
fi

# 安装前端依赖
echo "📦 检查前端依赖..."
if [ -d "frontend" ]; then
    cd frontend
    if [ ! -d "node_modules" ]; then
        echo "正在安装前端依赖..."
        npm install > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "✅ 前端依赖安装完成"
        else
            echo "❌ 前端依赖安装失败"
            exit 1
        fi
    else
        echo "✅ 前端依赖已存在"
    fi
    cd ..
else
    echo "❌ frontend 目录不存在"
    exit 1
fi

# 创建日志目录
mkdir -p logs

# 启动后端服务
echo "🔧 启动后端服务..."
python3 scripts/start_backend.py > logs/backend.log 2>&1 &
BACKEND_PID=$!

# 等待后端启动
echo "⏳ 等待后端服务启动..."
sleep 3

# 检查后端是否启动成功
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ 后端服务启动成功 (PID: $BACKEND_PID)"
    echo "   - API地址: http://localhost:8000"
    echo "   - API文档: http://localhost:8000/docs"
else
    echo "❌ 后端服务启动失败，请检查日志: logs/backend.log"
    kill $BACKEND_PID 2>/dev/null
    exit 1
fi

# 检查并释放端口 3000
echo "🔍 检查端口 3000 是否被占用..."
PORT_PID=$(lsof -ti :3000 2>/dev/null)
if [ -n "$PORT_PID" ]; then
    echo "⚠️  端口 3000 被进程 $PORT_PID 占用，正在释放..."
    kill -9 $PORT_PID 2>/dev/null
    sleep 1
    echo "✅ 端口 3000 已释放"
else
    echo "✅ 端口 3000 可用"
fi

# 启动前端服务
echo "🎨 启动前端服务..."
cd frontend
npm start > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

# 等待前端启动
echo "⏳ 等待前端服务启动..."
sleep 5

echo "=================================="
echo "🎉 系统启动完成！"
echo ""
echo "📊 服务信息:"
echo "   - 前端地址: http://localhost:3000"
echo "   - 后端地址: http://localhost:8000"
echo "   - API文档:  http://localhost:8000/docs"
echo ""
echo "📝 进程信息:"
echo "   - 后端进程 PID: $BACKEND_PID"
echo "   - 前端进程 PID: $FRONTEND_PID"
echo ""
echo "📋 日志文件:"
echo "   - 后端日志: logs/backend.log"
echo "   - 前端日志: logs/frontend.log"
echo ""
echo "🛑 停止系统: 按 Ctrl+C 或运行 ./stop_system.sh"
echo "=================================="

# 保存PID到文件
echo $BACKEND_PID > logs/backend.pid
echo $FRONTEND_PID > logs/frontend.pid

# 等待用户中断
trap 'echo ""; echo "🛑 正在停止系统..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo "✅ 系统已停止"; exit 0' INT

# 持续监控服务状态
while true; do
    sleep 10
    # 使用HTTP健康检查监控后端（reload模式下PID可能变化）
    if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "❌ 后端服务意外停止（无法连接到健康检查端点）"
        kill $FRONTEND_PID 2>/dev/null
        exit 1
    fi
    # 检查前端是否还在运行
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "❌ 前端服务意外停止"
        # 终止所有后端相关进程
        pkill -f "uvicorn.*backend" 2>/dev/null
        exit 1
    fi
done
