#!/usr/bin/env python3
"""
系统健康检查脚本
"""
import sys
import os
import subprocess
import importlib
from pathlib import Path
import json
from datetime import datetime
import shlex

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class HealthChecker:
    """系统健康检查器"""

    def __init__(self):
        self.issues = []
        self.warnings = []
        self.successes = []

    def log_issue(self, message: str):
        """记录问题"""
        self.issues.append(message)
        print(f"❌ {message}")

    def log_warning(self, message: str):
        """记录警告"""
        self.warnings.append(message)
        print(f"⚠️  {message}")

    def log_success(self, message: str):
        """记录成功"""
        self.successes.append(message)
        print(f"✅ {message}")

    def check_python_version(self):
        """检查Python版本"""
        print("\n🐍 检查Python环境...")

        if sys.version_info < (3, 8):
            self.log_issue(f"Python版本过低: {sys.version}，需要3.8+")
        else:
            self.log_success(f"Python版本正常: {sys.version}")

    def check_required_packages(self):
        """检查必需的包"""
        print("\n📦 检查必需包...")

        required_packages = [
            "fastapi",
            "uvicorn",
            "pandas",
            "numpy",
            "yfinance",
            "pydantic",
            "requests",
            "psutil",
            "scipy",
            "sklearn",
        ]

        for package in required_packages:
            try:
                importlib.import_module(package)
                self.log_success(f"包 {package} 已安装")
            except ImportError:
                self.log_issue(f"缺少必需包: {package}")

    def check_project_structure(self):
        """检查项目结构"""
        print("\n📁 检查项目结构...")

        required_dirs = ["src", "backend", "frontend", "tests", "scripts", "docs"]

        for dir_name in required_dirs:
            dir_path = project_root / dir_name
            if dir_path.exists():
                self.log_success(f"目录 {dir_name} 存在")
            else:
                self.log_issue(f"缺少目录: {dir_name}")

        # 检查关键文件
        required_files = ["requirements.txt", "README.md", "scripts/start_system.sh", "scripts/stop_system.sh"]

        for file_name in required_files:
            file_path = project_root / file_name
            if file_path.exists():
                self.log_success(f"文件 {file_name} 存在")
            else:
                self.log_issue(f"缺少文件: {file_name}")

    def check_module_imports(self):
        """检查模块导入"""
        print("\n🔗 检查模块导入...")

        modules_to_check = [
            ("src.data.data_manager", "DataManager"),
            ("src.strategy.strategies", "MovingAverageCrossover"),
            ("src.backtest.backtester", "Backtester"),
            ("src.analytics.dashboard", "PerformanceAnalyzer"),
            ("src.utils.cache", "cache_manager"),
            ("src.core.base", "BaseComponent"),
            ("src.security.validation", "security_validator"),
            ("backend.main", "app"),
        ]

        for module_path, class_name in modules_to_check:
            try:
                module = importlib.import_module(module_path)
                if hasattr(module, class_name):
                    self.log_success(f"模块 {module_path}.{class_name} 导入成功")
                else:
                    self.log_warning(f"模块 {module_path} 中缺少 {class_name}")
            except Exception as e:
                self.log_issue(f"模块 {module_path} 导入失败: {e}")

    def check_frontend_dependencies(self):
        """检查前端依赖"""
        print("\n⚛️  检查前端依赖...")

        frontend_dir = project_root / "frontend"
        package_json = frontend_dir / "package.json"
        node_modules = frontend_dir / "node_modules"

        if not package_json.exists():
            self.log_issue("前端 package.json 不存在")
            return

        if not node_modules.exists():
            self.log_warning("前端依赖未安装 (node_modules 不存在)")
        else:
            self.log_success("前端依赖已安装")

        # 检查Node.js
        try:
            result = subprocess.run(
                ["node", "--version"], capture_output=True, text=True
            )
            if result.returncode == 0:
                self.log_success(f"Node.js 版本: {result.stdout.strip()}")
            else:
                self.log_issue("Node.js 未安装或不可用")
        except FileNotFoundError:
            self.log_issue("Node.js 未安装")

    def _load_env_file(self, env_path: Path):
        values = {}
        if not env_path.exists():
            return values
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            parsed = shlex.split(value.strip()) if value.strip() else []
            values[key.strip()] = parsed[0] if parsed else value.strip().strip('"').strip("'")
        return values

    def check_local_infrastructure_stack(self):
        """检查本地 Docker infra stack 入口"""
        print("\n🐳 检查本地基础设施栈...")

        compose_file = project_root / "docker-compose.quant-infra.yml"
        start_script = project_root / "scripts/start_infra_stack.sh"
        stop_script = project_root / "scripts/stop_infra_stack.sh"
        migration_script = project_root / "scripts/migrate_infra_store.py"
        runtime_env_file = project_root / "logs/infra-stack.env"
        env_file = project_root / ".env"
        env_values = self._load_env_file(env_file)

        if compose_file.exists():
            self.log_success("docker-compose.quant-infra.yml 存在")
        else:
            self.log_issue("缺少 docker-compose.quant-infra.yml")

        for script_path in [start_script, stop_script, migration_script]:
            if script_path.exists():
                if script_path.suffix == ".py" or os.access(script_path, os.X_OK):
                    self.log_success(f"{script_path.relative_to(project_root)} 可执行")
                else:
                    self.log_warning(f"{script_path.relative_to(project_root)} 存在但缺少执行权限")
            else:
                self.log_issue(f"缺少脚本: {script_path.relative_to(project_root)}")

        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                self.log_success(result.stdout.strip())
            else:
                self.log_warning("Docker 已安装但无法正常执行")
        except FileNotFoundError:
            self.log_warning("Docker 未安装，本地 infra stack 将无法直接启动")

        try:
            result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
            if result.returncode == 0:
                self.log_success(result.stdout.strip())
            else:
                self.log_warning("docker compose 不可用，可尝试安装 Docker Desktop")
        except FileNotFoundError:
            self.log_warning("docker compose 不可用")

        if env_values.get("DATABASE_URL"):
            self.log_success("`.env` 已配置 DATABASE_URL")
        else:
            self.log_warning("`.env` 未配置 DATABASE_URL，可使用 start_infra_stack.sh 运行时自动注入")

        if env_values.get("REDIS_URL"):
            self.log_success("`.env` 已配置 REDIS_URL")
        else:
            self.log_warning("`.env` 未配置 REDIS_URL，可使用 start_infra_stack.sh 运行时自动注入")

        if env_values.get("CELERY_BROKER_URL") or env_values.get("REDIS_URL"):
            self.log_success("任务队列 broker 入口已配置或可由 Redis 派生")
        else:
            self.log_warning("`.env` 未配置 CELERY_BROKER_URL，异步任务将回退为本地执行器")

        if runtime_env_file.exists():
            self.log_success("发现运行时 infra 环境文件 logs/infra-stack.env")
        else:
            self.log_warning("尚未发现 logs/infra-stack.env，可先运行 ./scripts/start_infra_stack.sh")

    def check_celery_worker_runtime(self):
        """检查 Celery worker 启停链路"""
        print("\n🧵 检查 Celery worker 运行时...")

        start_script = project_root / "scripts/start_celery_worker.sh"
        stop_script = project_root / "scripts/stop_celery_worker.sh"
        pid_file = project_root / "logs/celery-worker.pid"
        log_file = project_root / "logs/celery-worker.log"

        for script_path in [start_script, stop_script]:
            if script_path.exists():
                if os.access(script_path, os.X_OK):
                    self.log_success(f"{script_path.relative_to(project_root)} 可执行")
                else:
                    self.log_warning(f"{script_path.relative_to(project_root)} 存在但缺少执行权限")
            else:
                self.log_issue(f"缺少脚本: {script_path.relative_to(project_root)}")

        try:
            importlib.import_module("celery")
            self.log_success("Python celery 模块已安装")
        except ImportError:
            self.log_warning("Python celery 模块未安装，worker 暂时无法启动")

        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                os.kill(pid, 0)
                self.log_success(f"检测到 Celery worker 进程运行中 (PID: {pid})")
            except Exception:
                self.log_warning("检测到 celery-worker.pid，但进程已不在运行")
        else:
            self.log_warning("尚未发现 celery-worker.pid，可用 ./scripts/start_celery_worker.sh 启动")

        if log_file.exists():
            self.log_success("发现 Celery worker 日志文件 logs/celery-worker.log")
        else:
            self.log_warning("尚未发现 Celery worker 日志文件")

    def check_permissions(self):
        """检查文件权限"""
        print("\n🔐 检查文件权限...")

        executable_files = [
            "scripts/start_system.sh",
            "scripts/stop_system.sh",
            "scripts/run_tests.py",
            "scripts/dev_tools.py",
            "scripts/start_system.sh",
        ]

        for file_name in executable_files:
            file_path = project_root / file_name
            if file_path.exists():
                if os.access(file_path, os.X_OK):
                    self.log_success(f"文件 {file_name} 有执行权限")
                else:
                    self.log_warning(f"文件 {file_name} 缺少执行权限")
            else:
                self.log_warning(f"文件 {file_name} 不存在")

    def check_configuration(self):
        """检查配置"""
        print("\n⚙️  检查配置...")

        try:
            from src.utils.config import get_config

            config = get_config()
            self.log_success("配置文件加载成功")

            # 检查关键配置项
            if "project_root" in config:
                self.log_success("项目根路径配置正常")
            else:
                self.log_warning("缺少项目根路径配置")

        except Exception as e:
            self.log_issue(f"配置加载失败: {e}")

    def check_test_environment(self):
        """检查测试环境"""
        print("\n🧪 检查测试环境...")

        test_packages = ["pytest", "pytest-asyncio", "pytest-cov"]

        for package in test_packages:
            try:
                importlib.import_module(package.replace("-", "_"))
                self.log_success(f"测试包 {package} 已安装")
            except ImportError:
                self.log_warning(f"测试包 {package} 未安装")

        # 检查测试目录
        tests_dir = project_root / "tests"
        if tests_dir.exists():
            test_files = list(tests_dir.rglob("test_*.py"))
            if test_files:
                self.log_success(f"发现 {len(test_files)} 个测试文件")
            else:
                self.log_warning("tests目录存在但没有测试文件")
        else:
            self.log_warning("tests目录不存在")

    def check_logs_directory(self):
        """检查日志目录"""
        print("\n📋 检查日志目录...")

        logs_dir = project_root / "logs"
        if logs_dir.exists():
            self.log_success("logs目录存在")

            # 检查日志文件
            log_files = list(logs_dir.glob("*.log"))
            if log_files:
                self.log_success(f"发现 {len(log_files)} 个日志文件")
            else:
                self.log_success("logs目录为空 (正常)")
        else:
            self.log_warning("logs目录不存在，将在首次运行时创建")

    def run_all_checks(self):
        """运行所有检查"""
        print("🔍 开始系统健康检查...")
        print("=" * 60)

        self.check_python_version()
        self.check_required_packages()
        self.check_project_structure()
        self.check_module_imports()
        self.check_frontend_dependencies()
        self.check_local_infrastructure_stack()
        self.check_celery_worker_runtime()
        self.check_permissions()
        self.check_configuration()
        self.check_test_environment()
        self.check_logs_directory()

        # 汇总结果
        print("\n" + "=" * 60)
        print("📊 健康检查结果汇总:")
        print(f"   ✅ 成功: {len(self.successes)}")
        print(f"   ⚠️  警告: {len(self.warnings)}")
        print(f"   ❌ 问题: {len(self.issues)}")

        if self.issues:
            print("\n🚨 发现的问题:")
            for issue in self.issues:
                print(f"   • {issue}")

        if self.warnings:
            print("\n⚠️  警告信息:")
            for warning in self.warnings:
                print(f"   • {warning}")

        # 给出建议
        if self.issues:
            print("\n💡 建议:")
            if any("缺少必需包" in issue for issue in self.issues):
                print("   • 运行: pip install -r requirements.txt")
            if any("Node.js" in issue for issue in self.issues):
                print("   • 安装 Node.js: https://nodejs.org/")
            if any("前端依赖" in warning for warning in self.warnings):
                print("   • 运行: cd frontend && npm install")
            if any("执行权限" in warning for warning in self.warnings):
                print("   • 运行: chmod +x start.sh stop.sh scripts/*.py")

        # 返回状态
        if self.issues:
            print("\n❌ 系统存在问题，需要修复后才能正常运行")
            return 1
        elif self.warnings:
            print("\n⚠️  系统基本正常，但有一些警告需要注意")
            return 0
        else:
            print("\n🎉 系统健康状况良好！")
            return 0

    def generate_report(self):
        """生成详细报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "successes": len(self.successes),
                "warnings": len(self.warnings),
                "issues": len(self.issues),
            },
            "details": {
                "successes": self.successes,
                "warnings": self.warnings,
                "issues": self.issues,
            },
        }

        report_file = project_root / "health_check_report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"📄 详细报告已保存到: {report_file}")


def main():
    """主函数"""
    checker = HealthChecker()
    exit_code = checker.run_all_checks()

    # 生成报告
    try:
        checker.generate_report()
    except Exception as e:
        print(f"报告生成失败: {e}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
