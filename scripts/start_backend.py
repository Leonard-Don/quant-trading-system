#!/usr/bin/env python3
"""
启动后端服务
"""

import uvicorn
import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.utils.config import get_config

config = get_config()

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=config["api_host"],
        port=config["api_port"],
        reload=config["api_reload"],
        log_level="info",
    )
