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

find_cleanable() {
    find . \( \
        -path "./.git" -o \
        -path "./.venv" -o \
        -path "./venv" -o \
        -path "./env" -o \
        -path "./ENV" -o \
        -path "./frontend/node_modules" -o \
        -path "./node_modules" \
    \) -prune -o "$@"
}

# 1. 清理Python缓存
echo -e "\n${YELLOW}1. 清理Python缓存...${NC}"
find_cleanable -type d -name "__pycache__" -exec rm -rf {} \; 2>/dev/null || true
find_cleanable -type f -name "*.pyc" -delete 2>/dev/null || true
find_cleanable -type f -name "*.pyo" -delete 2>/dev/null || true
find_cleanable -type f -name "*.pyd" -delete 2>/dev/null || true
find_cleanable -type d -name "*.egg-info" -exec rm -rf {} \; 2>/dev/null || true
echo -e "${GREEN}✓ Python缓存已清理${NC}"

# 2. 清理测试/类型检查缓存
echo -e "\n${YELLOW}2. 清理测试/类型检查缓存...${NC}"
rm -rf .pytest_cache 2>/dev/null || true
rm -rf htmlcov 2>/dev/null || true
rm -rf .coverage 2>/dev/null || true
rm -rf .tox 2>/dev/null || true
rm -rf .nox 2>/dev/null || true
rm -rf .mypy_cache 2>/dev/null || true
rm -rf .ruff_cache 2>/dev/null || true
echo -e "${GREEN}✓ 测试/类型检查缓存已清理${NC}"

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
find_cleanable -name ".DS_Store" -delete 2>/dev/null || true
find_cleanable -name "Thumbs.db" -delete 2>/dev/null || true
echo -e "${GREEN}✓ 系统文件已清理${NC}"

# 5. 清理日志文件
echo -e "\n${YELLOW}5. 清理日志文件...${NC}"
if [ -d "logs" ]; then
    find logs -type f \( -name "*.log" -o -name "*.log.*" \) -delete 2>/dev/null || true
    find logs -type d -empty -delete 2>/dev/null || true
    echo -e "${GREEN}✓ 日志文件已清理${NC}"
else
    echo -e "${GREEN}✓ 无日志目录${NC}"
fi

# 6. 清理临时文件
echo -e "\n${YELLOW}6. 清理临时文件...${NC}"
find_cleanable -name "*.tmp" -delete 2>/dev/null || true
find_cleanable -name "*.bak" -delete 2>/dev/null || true
find_cleanable -name "*~" -delete 2>/dev/null || true
find_cleanable -name ".#*" -delete 2>/dev/null || true
echo -e "${GREEN}✓ 临时文件已清理${NC}"

# 7. 清理运行输出和验证残留
echo -e "\n${YELLOW}7. 清理运行输出和验证残留...${NC}"
rm -rf output outputs tmp 2>/dev/null || true
rm -rf .playwright-cli 2>/dev/null || true
rm -f verify_result.html tests/e2e/verify_result.html health_check_report.json 2>/dev/null || true
echo -e "${GREEN}✓ 运行输出和验证残留已清理${NC}"

# 8. 显示磁盘使用情况
echo -e "\n${YELLOW}8. 磁盘使用情况...${NC}"
du -sh . 2>/dev/null || true
echo -e "${GREEN}✓ 项目总大小已显示${NC}"

echo -e "\n================================"
echo -e "${GREEN}🎉 清理完成！${NC}"
echo ""
echo "提示："
echo "  - Python缓存: 已清理"
echo "  - 测试/类型检查缓存: 已清理"
echo "  - 临时文件: 已清理"
echo "  - 日志文件: 已清理"
echo "  - 运行输出和验证残留: 已清理"
echo ""
echo "保留的内容："
echo "  - .venv 和 frontend/node_modules"
echo "  - .env、.agents/、.claude/"
echo "  - data/、cache/ 和 metrics/ 目录"
echo ""
