#!/bin/bash
# =============================================================================
# 安装 Allure 命令行工具
# =============================================================================

set -e

echo "=== 安装 Allure 命令行工具 ==="
echo ""

# 检测操作系统
OS="$(uname -s)"
case "${OS}" in
    Linux*)     
        if command -v apt-get &> /dev/null; then
            echo "检测到 Ubuntu/Debian 系统"
            echo "执行: sudo apt-add-repository ppa:qameta/allure && sudo apt-get update && sudo apt-get install -y allure"
            sudo apt-add-repository -y ppa:qameta/allure
            sudo apt-get update
            sudo apt-get install -y allure
        elif command -v yum &> /dev/null; then
            echo "检测到 RHEL/CentOS 系统"
            echo "请手动安装: https://docs.qameta.io/allure/#_linux"
            exit 1
        else
            echo "未知的 Linux 发行版，请手动安装"
            echo "参考: https://docs.qameta.io/allure/#_linux"
            exit 1
        fi
        ;;
    Darwin*)    
        echo "检测到 macOS 系统"
        if command -v brew &> /dev/null; then
            echo "执行: brew install allure"
            brew install allure
        else
            echo "未检测到 Homebrew，请先安装: https://brew.sh/"
            exit 1
        fi
        ;;
    CYGWIN*|MINGW*|MSYS*)
        echo "检测到 Windows 系统"
        if command -v scoop &> /dev/null; then
            echo "执行: scoop install allure"
            scoop install allure
        else
            echo "未检测到 Scoop，请手动安装"
            echo "下载: https://github.com/allure-framework/allure2/releases"
            exit 1
        fi
        ;;
    *)
        echo "未知操作系统: ${OS}"
        echo "请手动安装: https://docs.qameta.io/allure/#_installing_a_commandline"
        exit 1
        ;;
esac

echo ""
echo "=== 验证安装 ==="
if command -v allure &> /dev/null; then
    allure --version
    echo ""
    echo "✓ Allure 安装成功!"
else
    echo "✗ Allure 安装失败"
    exit 1
fi