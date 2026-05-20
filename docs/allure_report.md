# Allure 报告使用指南

## 概述

测试框架集成了 Allure 报告功能，提供更丰富的测试结果展示和分析能力。

## 安装依赖

```bash
# 安装 allure-pytest 插件
pip install allure-pytest

# 或使用 uv
uv pip install allure-pytest
```

## 安装 Allure 命令行工具

### 自动安装（推荐）

```bash
# 运行安装脚本
chmod +x scripts/install_allure.sh
./scripts/install_allure.sh
```

### 手动安装

### Linux/macOS
```bash
# macOS
brew install allure

# Ubuntu/Debian
sudo apt-add-repository ppa:qameta/allure
sudo apt-get update
sudo apt-get install allure

# 或使用 SDKMAN
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"
sdk install allure
```

### Windows
```bash
# 使用 Scoop
scoop install allure

# 或从 GitHub 下载
# https://github.com/allure-framework/allure2/releases
```

## 使用方式

### 1. 生成 Allure 数据

```bash
# 运行测试并生成 Allure 数据
pytest -v --alluredir=allure-results

# 或使用配置文件中已配置的默认路径
pytest -v
```

### 2. 生成 HTML 报告

```bash
# 生成 HTML 报告
allure generate allure-results -o allure-report --clean

# 打开报告
allure open allure-report
```

### 3. 实时查看报告

```bash
# 启动本地服务器实时查看
allure serve allure-results
```

## 报告内容

### 自动生成的内容

1. **测试用例结果**
   - 每个测试用例的执行状态（通过/失败/跳过）
   - 执行时间和持续时间
   - 失败详情和错误堆栈

2. **测试日志**
   - 自动附加每个测试类的日志文件
   - 请求和响应详情
   - 测试过程中的关键信息

3. **汇总报告**
   - Markdown 格式汇总（`allure-report/summary.md`）
   - 统计信息：总数、通过、失败、跳过
   - 分类统计

## 报告结构

每次测试会根据芯片和模型名称创建独立的目录，多次测试不会互相覆盖：

```
allure-results/                     # Allure 原始数据（按芯片/模型分离）
├── hygon-bw1000/
│   ├── minimax-m2.5/
│   │   └── *.json
│   └── glm5/
│       └── *.json
├── nvidia-h100/
│   └── qwen35/
│       └── *.json
└── ...

allure-report/                      # 生成的报告（按芯片/模型分离）
├── hygon-bw1000/
│   ├── minimax-m2.5/
│   │   ├── index.html             # HTML 报告
│   │   ├── data/
│   │   ├── widgets/
│   │   └── minimax-m2.5_20260520120000/
│   │       └── test_report_minimax-m2.5_20260520120000.md  # Markdown 汇总
│   └── glm5/
│       └── ...
├── nvidia-h100/
│   └── qwen35/
│       └── ...
└── ...
```

**优势：**
- 不同芯片/模型的测试结果完全隔离
- 多次测试不会覆盖之前的结果
- 每个芯片/模型有独立的 HTML 报告

## 配置选项

### pytest.ini 配置

```ini
[pytest]
addopts = --alluredir=allure-results
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--alluredir=DIR` | 指定 Allure 结果目录 |
| `--clean-alluredir` | 运行前清理结果目录 |

## 示例

### 完整流程

```bash
# 1. 运行测试（指定所有参数）
pytest -v -m p0 \
  --base-url http://127.0.0.1:8080/v1 \
  --api-key abc123 \
  --model-name minimax-m2.5 \
  --chip hygon-bw1000 \
  --thinking-mode

# 2. 生成报告
allure generate allure-results -o allure-report --clean

# 3. 打开报告
allure open allure-report
```

### 一行命令（推荐）

```bash
# 运行测试并生成 Allure 报告
pytest -v -m p0 \
  --base-url http://127.0.0.1:8080/v1 \
  --api-key abc123 \
  --model-name minimax-m2.5 \
  --chip hygon-bw1000 \
  --alluredir=allure-results && \
allure generate allure-results -o allure-report --clean && \
allure open allure-report
```

### CI/CD 集成

```yaml
# GitHub Actions 示例
- name: Run tests
  run: pytest -v --alluredir=allure-results

- name: Generate Allure Report
  run: allure generate allure-results -o allure-report --clean

- name: Upload Allure Report
  uses: actions/upload-artifact@v3
  with:
    name: allure-report
    path: allure-report/
```

## 注意事项

1. 确保 `allure` 命令行工具已安装
2. 报告会自动附加测试日志
3. Markdown 汇总报告与原有报告格式一致
4. 每次运行会清理旧的 Allure 结果