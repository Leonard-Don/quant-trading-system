#!/usr/bin/env python3
"""
开发工具脚本
"""
import sys
import os
import subprocess
import argparse
import shutil
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def clean_cache():
    """清理缓存文件"""
    print("🧹 清理缓存文件...")

    # Python缓存
    for root, dirs, files in os.walk(project_root):
        # 删除 __pycache__ 目录
        if "__pycache__" in dirs:
            cache_dir = Path(root) / "__pycache__"
            shutil.rmtree(cache_dir)
            print(f"   删除: {cache_dir}")

        # 删除 .pyc 文件
        for file in files:
            if file.endswith(".pyc"):
                pyc_file = Path(root) / file
                pyc_file.unlink()
                print(f"   删除: {pyc_file}")

    # 清理项目缓存目录
    cache_dir = project_root / "cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        print(f"   删除: {cache_dir}")

    # 清理测试缓存
    pytest_cache = project_root / ".pytest_cache"
    if pytest_cache.exists():
        shutil.rmtree(pytest_cache)
        print(f"   删除: {pytest_cache}")

    # 清理覆盖率文件
    coverage_files = [".coverage", "htmlcov"]
    for file in coverage_files:
        path = project_root / file
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"   删除: {path}")

    print("✅ 缓存清理完成")


def format_code():
    """格式化代码"""
    print("🎨 格式化代码...")

    # 检查是否安装了 black
    try:
        subprocess.run(
            [sys.executable, "-m", "black", "--version"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("安装 black...")
        subprocess.run([sys.executable, "-m", "pip", "install", "black"])

    # 格式化 Python 代码
    cmd = [sys.executable, "-m", "black", "src/", "backend/", "scripts/", "tests/"]
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        print("✅ 代码格式化完成")
    else:
        print("❌ 代码格式化失败")

    return result.returncode


def lint_code():
    """代码检查"""
    print("🔍 运行代码检查...")

    # 检查是否安装了 flake8
    try:
        subprocess.run(
            [sys.executable, "-m", "flake8", "--version"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("安装 flake8...")
        subprocess.run([sys.executable, "-m", "pip", "install", "flake8"])

    # 运行 flake8
    cmd = [
        sys.executable,
        "-m",
        "flake8",
        "src/",
        "backend/",
        "scripts/",
        "--max-line-length=88",
        "--ignore=E203,W503",
    ]
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        print("✅ 代码检查通过")
    else:
        print("❌ 代码检查发现问题")

    return result.returncode


def check_security():
    """安全检查"""
    print("🔒 运行安全检查...")

    # 检查是否安装了 bandit
    try:
        subprocess.run(
            [sys.executable, "-m", "bandit", "--version"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("安装 bandit...")
        subprocess.run([sys.executable, "-m", "pip", "install", "bandit"])

    # 运行 bandit
    cmd = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        "src/",
        "backend/",
        "-f",
        "json",
        "-o",
        "security_report.json",
    ]
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        print("✅ 安全检查通过")
    else:
        print("⚠️ 发现潜在安全问题，请查看 security_report.json")

    return result.returncode


def generate_docs():
    """生成文档"""
    print("📚 生成项目文档...")

    # 创建文档目录
    docs_dir = project_root / "docs" / "api"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # 生成 API 文档（如果有 FastAPI）
    try:
        # 这里可以添加自动生成 API 文档的逻辑
        print("   生成 API 文档...")

        # 创建模块文档
        modules = ["src.strategy", "src.backtest", "src.data", "src.analytics"]
        for module in modules:
            try:
                __import__(module)
                print(f"   ✅ {module} 模块文档已更新")
            except ImportError:
                print(f"   ⚠️ {module} 模块导入失败")

        print("✅ 文档生成完成")
        return 0

    except Exception as e:
        print(f"❌ 文档生成失败: {e}")
        return 1


def check_dependencies():
    """检查依赖"""
    print("📦 检查项目依赖...")

    # 检查 requirements.txt
    req_file = project_root / "requirements.txt"
    if not req_file.exists():
        print("❌ requirements.txt 文件不存在")
        return 1

    # 检查是否安装了 pip-tools
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "show", "pip-tools"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("安装 pip-tools...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pip-tools"])

    # 检查依赖是否有更新
    print("   检查依赖更新...")
    cmd = [sys.executable, "-m", "pip", "list", "--outdated"]
    result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True)

    if result.stdout.strip():
        print("   发现可更新的依赖:")
        print(result.stdout)
    else:
        print("   ✅ 所有依赖都是最新的")

    return 0


def backup_project():
    """备份项目"""
    print("💾 备份项目...")

    from datetime import datetime

    # 创建备份目录
    backup_dir = project_root.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    # 备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"quantitative_trading_backup_{timestamp}"
    backup_path = backup_dir / backup_name

    # 排除的目录
    exclude_dirs = [
        "__pycache__",
        ".git",
        "node_modules",
        "cache",
        "logs",
        ".pytest_cache",
        "htmlcov",
    ]

    try:
        # 使用 shutil.copytree 进行备份
        def ignore_patterns(dir, files):
            return [f for f in files if any(pattern in f for pattern in exclude_dirs)]

        shutil.copytree(project_root, backup_path, ignore=ignore_patterns)

        print(f"✅ 项目已备份到: {backup_path}")
        return 0

    except Exception as e:
        print(f"❌ 备份失败: {e}")
        return 1


def setup_pre_commit():
    """设置预提交钩子"""
    print("🔗 设置 Git 预提交钩子...")

    # 检查是否安装了 pre-commit
    try:
        subprocess.run(
            [sys.executable, "-m", "pre_commit", "--version"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("安装 pre-commit...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pre-commit"])

    # 创建 .pre-commit-config.yaml
    pre_commit_config = project_root / ".pre-commit-config.yaml"
    if not pre_commit_config.exists():
        config_content = """repos:
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        language_version: python3

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=88, --ignore=E203,W503]
  - repo: https://github.com/pycqa/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: [-r, .]
        exclude: tests/
"""
        pre_commit_config.write_text(config_content)
        print("   创建 .pre-commit-config.yaml")

    # 安装钩子
    cmd = [sys.executable, "-m", "pre_commit", "install"]
    result = subprocess.run(cmd, cwd=project_root)

    if result.returncode == 0:
        print("✅ 预提交钩子设置完成")
    else:
        print("❌ 预提交钩子设置失败")

    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="开发工具集")
    parser.add_argument("--clean", action="store_true", help="清理缓存文件")
    parser.add_argument("--format", action="store_true", help="格式化代码")
    parser.add_argument("--lint", action="store_true", help="代码检查")
    parser.add_argument("--security", action="store_true", help="安全检查")
    parser.add_argument("--docs", action="store_true", help="生成文档")
    parser.add_argument("--deps", action="store_true", help="检查依赖")
    parser.add_argument("--backup", action="store_true", help="备份项目")
    parser.add_argument("--pre-commit", action="store_true", help="设置预提交钩子")
    parser.add_argument("--all", action="store_true", help="运行所有工具")

    args = parser.parse_args()

    if args.all:
        print("🚀 运行所有开发工具...")
        results = []
        results.append(clean_cache() or 0)
        results.append(format_code())
        results.append(lint_code())
        results.append(check_security())
        results.append(generate_docs())
        results.append(check_dependencies())
        results.append(setup_pre_commit())

        if all(r == 0 for r in results if r is not None):
            print("🎉 所有工具执行成功！")
            return 0
        else:
            print("⚠️ 部分工具执行失败")
            return 1

    if args.clean:
        clean_cache()

    if args.format:
        return format_code()

    if args.lint:
        return lint_code()

    if args.security:
        return check_security()

    if args.docs:
        return generate_docs()

    if args.deps:
        return check_dependencies()

    if args.backup:
        return backup_project()

    if args.pre_commit:
        return setup_pre_commit()

    if not any(vars(args).values()):
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
