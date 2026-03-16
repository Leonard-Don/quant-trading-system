#!/bin/bash

# 项目清理脚本
# 用于清理临时文件、缓存和构建产物

set -e

echo "🧹 开始清理项目..."
echo "================================"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 1. 清理Python缓存
echo -e "\n${YELLOW}1. 清理Python缓存...${NC}"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type f -name "*.pyd" -delete 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
echo -e "${GREEN}✓ Python缓存已清理${NC}"

# 2. 清理pytest缓存
echo -e "\n${YELLOW}2. 清理测试缓存...${NC}"
rm -rf .pytest_cache 2>/dev/null || true
rm -rf htmlcov 2>/dev/null || true
rm -rf .coverage 2>/dev/null || true
rm -rf .tox 2>/dev/null || true
rm -rf .nox 2>/dev/null || true
echo -e "${GREEN}✓ 测试缓存已清理${NC}"

# 3. 清理前端缓存和构建
echo -e "\n${YELLOW}3. 清理前端缓存...${NC}"
if [ -d "frontend" ]; then
    rm -rf frontend/build 2>/dev/null || true
    rm -rf frontend/.cache 2>/dev/null || true
    rm -rf frontend/node_modules/.cache 2>/dev/null || true
    echo -e "${GREEN}✓ 前端缓存已清理${NC}"
else
    echo -e "${GREEN}✓ 无前端目录${NC}"
fi

# 4. 清理macOS系统文件
echo -e "\n${YELLOW}4. 清理系统文件...${NC}"
find . -name ".DS_Store" -delete 2>/dev/null || true
find . -name "Thumbs.db" -delete 2>/dev/null || true
echo -e "${GREEN}✓ 系统文件已清理${NC}"

# 5. 清理日志文件（可选）
echo -e "\n${YELLOW}5. 清理旧日志...${NC}"
if [ -d "logs" ]; then
    find logs -name "*.log" -mtime +7 -delete 2>/dev/null || true
    echo -e "${GREEN}✓ 7天前的日志已清理${NC}"
fi

# 6. 清理临时文件
echo -e "\n${YELLOW}6. 清理临时文件...${NC}"
find . -name "*.tmp" -delete 2>/dev/null || true
find . -name "*.bak" -delete 2>/dev/null || true
find . -name "*~" -delete 2>/dev/null || true
find . -name ".#*" -delete 2>/dev/null || true
echo -e "${GREEN}✓ 临时文件已清理${NC}"

# 7. 清理Docker（可选）
if command -v docker &> /dev/null; then
    echo -e "\n${YELLOW}7. 清理Docker缓存（可选）...${NC}"
    read -p "是否清理Docker悬空镜像？(y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker system prune -f
        echo -e "${GREEN}✓ Docker缓存已清理${NC}"
    else
        echo -e "${GREEN}✓ 跳过Docker清理${NC}"
    fi
fi

# 8. 显示磁盘使用情况
echo -e "\n${YELLOW}8. 磁盘使用情况...${NC}"
du -sh . 2>/dev/null || true
echo -e "${GREEN}✓ 项目总大小已显示${NC}"

echo -e "\n================================"
echo -e "${GREEN}🎉 清理完成！${NC}"
echo ""
echo "提示："
echo "  - Python缓存: 已清理"
echo "  - 测试缓存: 已清理"
echo "  - 临时文件: 已清理"
echo "  - 7天前日志: 已清理"
echo ""
echo "保留的内容："
echo "  - node_modules (运行 'cd frontend && npm ci' 重新安装)"
echo "  - 最近7天的日志"
echo "  - cache/ 和 metrics/ 目录"
echo ""
