# 量化交易系统 - 项目结构说明

## 📁 项目目录结构

```
PythonProject/                          # 项目根目录
├── 📁 backend/                         # 后端服务
│   ├── main.py                         # FastAPI 主应用
│   └── app/                            # 后端模块
│       ├── api/                        # API 路由
│       │   └── v1/                     # v1 版本路由
│       ├── core/                       # 核心配置与错误处理
│       ├── schemas/                    # 请求/响应模型
│       └── websocket/                  # WebSocket 路由与连接管理
├── 📁 frontend/                        # 前端应用
│   ├── 📁 public/                      # 静态资源
│   ├── 📁 src/                         # 源代码
│   │   ├── App.js                      # 主应用组件
│   │   ├── index.js                    # 前端入口
│   │   ├── index.css                   # 全局样式
│   │   ├── 📁 components/              # React 组件
│   │   └── 📁 services/                # API 服务
│   ├── package.json                    # 前端依赖配置
│   └── 📁 build/                       # 构建输出
├── 📁 src/                             # 核心业务代码
│   ├── 📁 analytics/                   # 分析模块
│   ├── 📁 backtest/                    # 回测引擎
│   ├── 📁 core/                        # 核心组件与事件系统
│   ├── 📁 data/                        # 数据管理与提供器
│   │   └── 📁 providers/               # 多数据源适配
│   ├── 📁 reporting/                   # 报告导出与生成
│   ├── 📁 security/                    # 安全与输入校验
│   ├── 📁 strategy/                    # 交易策略
│   ├── 📁 trading/                     # 交易执行与管理
│   └── 📁 utils/                       # 通用工具
├── 📁 tests/                           # 测试代码
│   ├── 📁 unit/                        # 单元测试
│   ├── 📁 integration/                 # 集成测试
│   └── 📁 manual/                      # 手工/调试测试
├── 📁 scripts/                         # 脚本工具
│   ├── start_system.sh                 # 系统启动脚本
│   ├── stop_system.sh                  # 系统停止脚本
│   ├── start_backend.py                # 后端启动脚本
│   ├── start_frontend.sh               # 前端启动脚本
│   ├── run_tests.py                    # 测试入口
│   ├── dev_tools.py                    # 代码质量工具
│   ├── performance_test.py             # 性能测试
│   └── health_check.py                 # 健康检查脚本
├── 📁 docs/                            # 文档目录
│   ├── API_REFERENCE.md                # API 参考文档
│   ├── PERFORMANCE_OPTIMIZATION.md     # 性能优化指南
│   ├── PROJECT_STRUCTURE.md            # 项目结构说明
│   ├── TESTING_GUIDE.md                # 测试指南
│   └── DEPLOYMENT.md                   # 部署说明
├── 📁 logs/                            # 日志文件
├── 📁 cache/                           # 缓存文件
├── 📁 reports/                         # 报告输出
├── 📁 metrics/                         # 性能指标
├── requirements.txt                    # Python 依赖
├── requirements-dev.txt                # 开发依赖
├── .env.example                        # 配置模板
├── .env                                # 本地配置
├── .gitignore                          # Git 忽略文件
├── README.md                           # 项目说明
└── docs/PROJECT_STATUS.md              # 项目状态
```

## 🏗️ 架构说明

### 核心模块

#### 1. 数据层 (`src/data/`)
- **data_manager.py**: 历史数据获取和管理
- **realtime_manager.py**: 实时数据管理
- **providers/**: 数据源适配与故障转移

#### 2. 策略层 (`src/strategy/`)
- **strategies.py**: 基础技术指标策略
- **advanced_strategies.py**: 高级策略
- **advanced_technical.py**: 高级技术指标策略
- **ml_strategies.py**: 机器学习策略
- **momentum_strategy.py**: 动量策略
- **lstm_strategy.py**: LSTM 深度学习策略
- **pairs_trading.py**: 配对交易策略
- **portfolio_optimizer.py**: 投资组合优化
- **sentiment_strategy.py**: 情绪分析策略
- **strategy_validator.py**: 策略验证工具

#### 3. 回测引擎 (`src/backtest/`)
- **backtester.py**: 回测核心逻辑与指标计算

#### 4. 报告模块 (`src/reporting/`)
- **pdf_generator.py**: PDF 报告生成
- **data_exporter.py**: 数据导出

#### 5. 交易执行 (`src/trading/`)
- **trade_manager.py**: 交易执行与管理

#### 6. 工具层 (`src/utils/`)
- **cache.py**: 缓存管理
- **config.py**: 配置管理
- **error_handler.py**: 错误处理
- **performance.py**: 性能监控
- **validators.py**: 数据验证

### 服务层

#### 后端服务 (`backend/`)
- FastAPI 框架构建的 RESTful API
- 路由在 `backend/app/api/v1/endpoints/`
- 集成回测、策略、分析、数据获取与报告生成等核心模块

#### 前端应用 (`frontend/`)
- React + Ant Design 构建的现代化界面
- 实时数据展示与交互
- 响应式设计

## 🚀 快速开始

### 1. 环境准备
```bash
# 安装 Python 依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 安装前端依赖
cd frontend && npm install
```

### 2. 配置设置
```bash
# 复制配置模板
cp .env.example .env
# 根据需要修改配置
```

### 3. 启动系统
```bash
# 启动完整系统
./scripts/start_system.sh

# 或分别启动
python backend/main.py &
cd frontend && npm start
```

## 📊 功能模块

### 交易策略 (当前实现)
- 移动平均策略
- RSI 策略
- MACD 策略
- 布林带策略
- 均值回归策略
- VWAP 策略
- 动量策略
- 买入持有策略
- LSTM 深度学习策略
- 配对交易策略
- 情绪分析策略
- 投资组合优化

### 数据处理
- 多数据源支持（Yahoo Finance、Alpha Vantage、Twelve Data、AKShare）
- 实时数据流处理
- 缓存系统
- 数据验证与清洗

### 监控与健康检查
- 通过脚本与 API 进行健康检查与性能测试
- 日志位于 `logs/`

### 报告生成
- 专业回测报告
- 可视化图表
- 多格式导出（JSON/CSV/Excel）

## 🔧 开发指南

### 添加新策略
1. 在 `src/strategy/` 目录创建策略文件
2. 继承 `BaseStrategy` 类
3. 实现 `generate_signals()` 方法
4. 添加相应的测试用例

### 扩展 API 端点
1. 在 `backend/app/api/v1/endpoints/` 添加新的路由文件
2. 实现业务逻辑
3. 添加错误处理
4. 更新 API 文档

### 前端组件开发
1. 在 `frontend/src/components/` 创建组件
2. 遵循 Ant Design 设计规范
3. 实现响应式布局
4. 添加必要的状态管理

---

*项目结构说明最后更新: 2026年2月5日*
