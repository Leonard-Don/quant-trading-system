#!/usr/bin/env python3
"""
测试运行脚本
"""
import sys
import subprocess
import argparse
import shutil
from urllib.error import URLError, HTTPError
from urllib.request import urlopen
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def run_unit_tests():
    """运行单元测试"""
    print("🧪 运行单元测试...")
    cmd = [sys.executable, "-m", "pytest", "tests/unit/", "-v", "--tb=short"]
    return subprocess.run(cmd, cwd=project_root).returncode


def run_integration_tests():
    """运行集成测试"""
    print("🔗 运行集成测试...")
    cmd = [sys.executable, "-m", "pytest", "tests/integration/", "-v", "--tb=short"]
    return subprocess.run(cmd, cwd=project_root).returncode


def run_system_tests():
    """运行系统测试"""
    print("🚀 运行系统测试...")
    cmd = [sys.executable, "scripts/test_system.py"]
    return subprocess.run(cmd, cwd=project_root).returncode


def _check_local_service(url: str) -> bool:
    try:
        with urlopen(url, timeout=5) as response:
            return 200 <= getattr(response, "status", 200) < 500
    except HTTPError as exc:
        return 200 <= exc.code < 500
    except URLError:
        return False


def run_industry_e2e_tests():
    """运行行业热度 E2E 回归测试"""
    print("🌐 运行行业热度 E2E 回归...")

    if shutil.which("node") is None:
        print("❌ 未找到 node，请先安装 Node.js")
        return 1

    frontend_ok = _check_local_service("http://localhost:3000")
    backend_ok = _check_local_service("http://localhost:8000/health")
    if not frontend_ok or not backend_ok:
        print("❌ 行业 E2E 需要本地前后端服务已启动")
        print(f"   frontend http://localhost:3000: {'OK' if frontend_ok else 'UNAVAILABLE'}")
        print(f"   backend  http://localhost:8000/health: {'OK' if backend_ok else 'UNAVAILABLE'}")
        print("   可先运行: python scripts/start_backend.py")
        print("   可先运行: ./scripts/start_frontend.sh")
        return 1

    cmd = ["node", "verify_industry_features.js"]
    return subprocess.run(cmd, cwd=project_root / "tests" / "e2e").returncode


def run_all_tests():
    """运行所有测试"""
    print("🎯 运行完整测试套件...")

    results = {}

    # 单元测试
    results["unit"] = run_unit_tests()

    # 集成测试
    results["integration"] = run_integration_tests()

    # 系统测试
    results["system"] = run_system_tests()

    # E2E 回归（仅在本地服务已启动时建议执行，默认纳入总入口）
    results["industry_e2e"] = run_industry_e2e_tests()

    # 汇总结果
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")

    all_passed = True
    for test_type, result in results.items():
        status = "✅ 通过" if result == 0 else "❌ 失败"
        print(f"   {test_type.capitalize()}: {status}")
        if result != 0:
            all_passed = False

    print("\n🎉 所有测试通过！" if all_passed else "\n⚠️ 部分测试失败")
    return 0 if all_passed else 1


def install_test_dependencies():
    """安装测试依赖"""
    print("📦 安装测试依赖...")
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
    ]
    return subprocess.run(cmd).returncode


def main():
    parser = argparse.ArgumentParser(description="运行测试套件")
    parser.add_argument("--unit", action="store_true", help="只运行单元测试")
    parser.add_argument("--integration", action="store_true", help="只运行集成测试")
    parser.add_argument("--system", action="store_true", help="只运行系统测试")
    parser.add_argument("--e2e-industry", action="store_true", help="只运行行业热度 E2E 回归（要求本地前后端已启动）")
    parser.add_argument("--install-deps", action="store_true", help="安装测试依赖")
    parser.add_argument("--coverage", action="store_true", help="生成覆盖率报告")

    args = parser.parse_args()

    if args.install_deps:
        return install_test_dependencies()

    if args.coverage:
        print("📈 生成覆盖率报告...")
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--cov=src",
            "--cov-report=html",
        ]
        return subprocess.run(cmd, cwd=project_root).returncode

    if args.unit:
        return run_unit_tests()
    elif args.integration:
        return run_integration_tests()
    elif args.system:
        return run_system_tests()
    elif args.e2e_industry:
        return run_industry_e2e_tests()
    else:
        return run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
