# 大模型推理能力测试框架

基于 checkpoints.md 文档设计的大模型推理能力测试框架，覆盖 10 大类共 83 个测试点。

## 快速开始

### 1. 创建并激活虚拟环境（推荐使用 uv）

本项目推荐使用 [uv](https://github.com/astral-sh/uv) 来管理 Python 环境，uv 是一个极快的 Python 包管理工具。

```bash
# 安装 uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或者使用 pip 安装
pip install uv
```

### 2. 使用 uv 创建虚拟环境并安装依赖

```bash
# 创建虚拟环境
uv venv

# 激活虚拟环境
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

# 安装依赖
uv pip install -r requirements.txt
```

### 3. 配置环境变量

创建或设置以下环境变量：

```bash
# 至少需要配置一个模型的API Key
# Linux/macOS
export QWEN_API_KEY="your-qwen-api-key"
export KIMI_API_KEY="your-kimi-api-key"
export GLM_API_KEY="your-glm-api-key"
export MINIMAX_API_KEY="your-minimax-api-key"

# Windows (PowerShell)
$env:QWEN_API_KEY="your-qwen-api-key"
$env:KIMI_API_KEY="your-kimi-api-key"
$env:GLM_API_KEY="your-glm-api-key"
$env:MINIMAX_API_KEY="your-minimax-api-key"
```

### 4. 修改配置文件

编辑 `config.yaml`，配置芯片平台和模型：

```yaml
# 芯片平台配置（base_url 在这里配置）
chips:
  metax-c550:
    enabled: false
    base_url: http://10.130.70.1:8000/v1
  nvidia-h100:
    enabled: true
    base_url: http://127.0.0.1:8080/v1
  hygon-bw1000:
    enabled: false
    base_url: http://10.212.16.21:8080/v1

# 模型配置
models:
  minimax25:
    name: minimax-m2.5
    api_key: abc123
    enabled: true
    thinking_mode: true
```

> 注意：`base_url` 现在配置在 `chips` 下，而不是 `models` 下，这样可以支持同一模型在不同芯片平台上的不同地址。

### 5. 运行测试

#### 方式一：使用 config.yaml 配置

```bash
# 运行所有测试
pytest

# 运行特定分类
pytest -m a_basic -v        # 基础推理能力
pytest -m b_advanced -v     # 高级生成功能
pytest -m c_multimodal -v   # 多模态能力
pytest -m d_long_context -v # 长上下文处理
pytest -m e_performance -v  # 性能指标
pytest -m f_stability -v    # 稳定性与边界
pytest -m g_api -v          # API兼容性
pytest -m h_quality -v      # 质量评估
pytest -m i_long_context -v # 超长上下文验证
pytest -m j_quality -v      # 回答质量与相关性

# 运行多个分类
pytest -m "a_basic or b_advanced" -v

# 运行 P0 优先级测试
pytest -m p0 -v

# 指定模型运行
pytest --model=qwen35 -v
```

#### 方式二：使用命令行参数

优先级：命令行参数 > 环境变量 > config.yaml

```bash
# 指定 API 地址、密钥、模型、芯片
pytest -v \
  --base-url http://127.0.0.1:8080/v1 \
  --api-key abc123 \
  --model-name minimax-m2.5 \
  --chip hygon-bw1000

# 启用思考模式
pytest -v \
  --base-url http://127.0.0.1:8080/v1 \
  --api-key abc123 \
  --model-name minimax-m2.5 \
  --thinking-mode

# 完整示例：指定所有参数并生成 Allure 报告
pytest -v -m p0 \
  --base-url http://127.0.0.1:8080/v1 \
  --api-key abc123 \
  --model-name minimax-m2.5 \
  --chip hygon-bw1000 \
  --thinking-mode

# 生成 Allure HTML 报告（自动按芯片/模型分目录）
# 报告位置: allure-report/hygon-bw1000/minimax-m2.5/
allure generate allure-results/hygon-bw1000/minimax-m2.5 -o allure-report/hygon-bw1000/minimax-m2.5 --clean

# 打开报告
allure open allure-report/hygon-bw1000/minimax-m2.5

# 运行特定测试
pytest -v tests/test_a_basic_reasoning.py -m p0 \
  --base-url http://127.0.0.1:8080/v1 \
  --api-key abc123 \
  --model-name minimax-m2.5
```

#### 方式三：使用环境变量

```bash
# 设置环境变量
export BASE_URL=http://127.0.0.1:8080/v1
export API_KEY=abc123
export MODEL_NAME=minimax-m2.5
export CHIP=hygon-bw1000
export THINKING_MODE=true

# 运行测试
pytest -v
```

#### 参数说明

| 参数 | 环境变量 | 说明 |
|------|---------|------|
| `--base-url` | `BASE_URL` | API 基础地址 |
| `--api-key` | `API_KEY` | API 密钥 |
| `--model-name` | `MODEL_NAME` | 模型名称 |
| `--chip` | `CHIP` | 芯片平台名称（用于日志目录，自动转小写） |
| `--thinking-mode` | `THINKING_MODE` | 启用思考模式（不指定则使用 config.yaml 配置） |
| `--model` | - | 指定 config.yaml 中的模型配置名 |

**thinking_mode 优先级**：命令行参数 > 环境变量 > config.yaml

## 测试分类概览

| 分类         | 测试点数 | 测试文件                          | 说明                                                                                           |
|------------|------|-------------------------------|----------------------------------------------------------------------------------------------|
| A. 基础推理能力  | 12   | test_a_basic_reasoning.py     | 单轮/多轮对话、System Prompt、流式输出、Temperature/Top-p控制、Max Tokens、Stop Sequences、Seed可复现、多语言、特殊Token |
| B. 高级生成功能  | 10   | test_b_advanced_generation.py | 思考模式、思考模式切换、工具调用（单/多/并行/多步链式）、JSON Mode、结构化输出、Prefix/Suffix约束                                |
| C. 多模态能力   | 8    | test_c_multimodal.py          | 单图/多图理解、高分辨率图片、图表OCR、视频理解、代码截图、多模态工具调用、图片格式兼容                                                |
| D. 长上下文处理  | 8    | test_d_long_context.py        | 短/中/长上下文、超长上下文、大海捞针、上下文边界、超出截断、长输出生成                                                         |
| E. 性能指标    | 12   | test_e_performance.py         | TTFT、TPOT、ITL分位数、端到端延迟、吞吐/请求吞吐、并发扩展性、显存占用、GPU利用率、预热时间、Prefill速度、突发流量恢复                       |
| F. 稳定性与边界  | 8    | test_f_stability.py           | 空输入、超大输入、非法参数、特殊字符注入、并发稳定性、OOM恢复、长时间运行、请求超时处理                                                |
| G. API兼容性  | 8    | test_g_api_compatibility.py   | OpenAI Chat/Completions接口、模型列表、Usage统计                                                       |
| H. 质量评估    | 5    | test_h_quality.py             | 生成质量、生成一致性、幻觉率、指令遵循度                                                                         |
| I. 超长上下文验证 | 4    | test_i_long_context.py        | 超长上下文脚本验证                                                                                    |
| J. 回答质量与相关性 | 8    | test_j_response_quality.py    | 回答相关性（编程/数学/科学领域）、乱码检测、无意义回答检测、跨领域相关性、上下文一致性、回答具体性                                |

> 总计：83 个测试点

## 配置文件说明

`config.yaml` 是测试框架的主配置文件：

```yaml
# 全局配置
global:
  timeout: 120          # 请求超时（秒）
  retry_times: 3        # 重试次数
  log_level: INFO       # 日志级别
  output_dir: ./test_results

# 芯片平台配置（支持多芯片部署）
chips:
  MetaX-C550:           # 芯片平台名称
    enabled: false      # 是否启用
    base_url: http://10.130.70.1:8000/v1  # API地址
  NVIDIA-H100:
    enabled: true
    base_url: http://127.0.0.1:8080/v1
  Hygon-BW1000:
    enabled: false
    base_url: http://10.212.16.21:8080/v1

# 模型配置
models:
  minimax25:
    name: minimax-m2.5
    api_key: ${MINIMAX_API_KEY}
    enabled: true
    thinking_mode: true
    thinking_key: "enable_thinking"

# 默认测试模型
default_model: minimax25
```

配置支持环境变量：`${ENV_VAR}` 格式会自动读取环境变量值。

### 芯片平台说明

不同芯片平台可能运行不同的模型服务，通过 `chips` 配置：
- 同一芯片平台下可以测试多个模型
- 同一模型也可以在不同芯片平台上测试
- `enabled: true` 的芯片会被使用（只启用一个）

### 模型思考模式配置

```yaml
models:
  minimax25:
    thinking_mode: true           # 默认是否开启思考模式
    thinking_key: "enable_thinking"  # 参数名（不同模型可能不同）
    thinking_via_chat_template: false  # 是否通过chat_template传递
```

## 支持的模型

| 模型          | 配置名       | 思考模式参数 | 说明              |
|-------------|-----------|----------|-----------------|
| Qwen 3.5    | qwen35    | enable_thinking | 阿里Qwen系列        |
| Kimi K2.5   | kimi_k25  | thinking  | 月之暗面Kimi        |
| GLM-5       | glm5      | enable_thinking | 智谱GLM系列         |
| Minimax 2.1 | minimax21 | -        | Minimax系列（默认关闭） |
| Minimax 2.5 | minimax25 | enable_thinking | Minimax系列       |

> 不同模型的思考模式参数名可能不同（`thinking` 或 `enable_thinking`），通过 `thinking_key` 配置。

## 目录结构

```
model-test/
├── config.yaml           # 配置文件
├── requirements.txt      # Python依赖
├── pytest.ini           # pytest配置
├── conftest.py          # pytest全局配置
├── base/                # 基础模块
│   ├── api_client.py    # API客户端
│   ├── base_test.py     # 基础测试类
│   ├── logger.py        # 日志管理
│   └── report_generator.py  # 报告生成
├── tests/               # 测试用例
│   ├── test_a_basic_reasoning.py      # A类测试：基础推理能力
│   ├── test_b_advanced_generation.py  # B类测试：高级生成功能
│   ├── test_c_multimodal.py            # C类测试：多模态能力
│   ├── test_d_long_context.py          # D类测试：长上下文处理
│   ├── test_e_performance.py           # E类测试：性能指标
│   ├── test_f_stability.py             # F类测试：稳定性与边界
│   ├── test_g_api_compatibility.py     # G类测试：API兼容性
│   ├── test_h_quality.py               # H类测试：质量评估
│   ├── test_i_long_context.py          # I类测试：超长上下文验证
│   └── test_j_response_quality.py      # J类测试：回答质量与相关性
├── logs/                # 日志目录（运行后生成，按芯片/模型/测试类组织）
│   └── {chip_name}/
│       └── {model_name}/
│           └── {TestClass}/
│               └── {TestClass}_{timestamp}.log
├── test_reports/        # 测试报告（运行后生成，按芯片/模型组织）
│   └── {chip_name}/
│       └── {model_name}/
│           └── {model_name}_{timestamp}/
│               └── test_report_{model_name}_{timestamp}.md
├── scripts/             # 工具脚本
│   ├── generate_report.py  # 生成测试报告
│   └── quick_report.py  # 快速报告生成
└── test_results/        # 测试结果（运行后生成）
```

## 运行选项

### 冒烟测试

运行核心功能用例，快速验证模型基础能力：

```bash
# 运行所有冒烟测试用例
pytest -m smoke -v

# 冒烟测试 + 指定模型
pytest -m smoke --model=minimax25 -v

# 冒烟测试 + 生成报告
pytest -m smoke --model=minimax25 -v --html=smoke_report.html
```

冒烟测试覆盖以下核心用例：
- A类: 单轮对话、多轮对话、流式输出、多语言能力
- B类: 思考模式、非思考模式、思考模式切换、工具调用（单/多工具）
- C类: 单图理解
- D类: 短上下文基线、超长上下文
- G类: Chat Completions API、Completions API、模型列表

### 按优先级运行

```bash
pytest -m p0 -v    # 只运行P0优先级测试
pytest -m p1 -v    # 只运行P1优先级测试
```

### 排除慢速测试

```bash
pytest -m "not slow" -v
```

### 生成报告

#### Markdown 报告（自动生成）

```bash
# 运行测试后自动生成 Markdown 报告
pytest -v

# 报告位置: test_reports/{chip}/{model}/{model}_{timestamp}/test_report_{model}_{timestamp}.md
```

#### Allure 报告

```bash
# 运行测试并生成 Allure 数据
pytest -v --alluredir=allure-results

# 生成 HTML 报告
allure generate allure-results -o allure-report --clean

# 打开报告
allure open allure-report
```

Allure 报告特性：
- 每个测试用例的详细结果
- 测试日志自动附加到报告中
- 失败详情自动记录
- 汇总报告 (allure-report/summary.md)

#### 其他格式

```bash
# HTML 报告
pytest --html=report.html

# JUnit XML
pytest --junit-xml=report.xml
```

### 日志说明

测试框架为每个测试类生成独立的日志文件，按芯片平台和模型组织目录：

```
logs/
└── {chip_name}/              # 芯片平台目录
    └── {model_name}/         # 模型目录
        └── {TestClass}/      # 测试类目录
            └── {TestClass}_{timestamp}.log
```

示例：
```
logs/
└── nvidia-h100/
    └── minimax25/
        ├── TestBasicReasoning/
        │   └── TestBasicReasoning_20260504112030.log
        └── TestAdvancedGeneration/
            └── TestAdvancedGeneration_20260504112045.log
```

日志内容包括：
- API 请求消息（messages）
- 请求参数（temperature、max_tokens、thinking 参数等）
- API 响应内容（content、reasoning_content）
- 测试执行过程和结果

控制台输出 INFO 级别，详细日志保存到文件（DEBUG 级别）。

每个测试类共享一个日志文件，同一测试类的多个测试方法之间用分隔符分隔。

## 详细文档

- [测试文档导航](docs/README.md)
- [A类测试说明](docs/test_a_basic_reasoning.md)
- [B类测试说明](docs/test_b_advanced_generation.md)
- [C类测试说明](docs/test_c_multimodal.md)
- [D类测试说明](docs/test_d_long_context.md)
- [E类测试说明](docs/test_e_performance.md)
- [F类测试说明](docs/test_f_stability.md)
- [G类测试说明](docs/test_g_api_compatibility.md)
- [H类测试说明](docs/test_h_quality.md)
- [I类测试说明](docs/test_i_long_context.md)
- [J类测试说明](docs/test_j_response_quality.md)

## 注意事项

1. 确保模型服务已启动并可访问
2. 根据实际模型支持情况调整配置
3. 性能测试结果受网络和服务器负载影响
4. 部分测试需要GPU环境（如显存测试）

## 生成测试报告

### 报告生成方式

测试报告支持三种生成方式：

| 方式 | 命令 | 说明 |
|------|------|------|
| **自动生成** | `pytest` | pytest测试完成后自动生成报告 |
| **快速测试** | `python scripts/quick_report.py` | 运行P0测试并生成报告 |
| **手动生成** | `python scripts/generate_report.py -j results.json` | 基于已有pytest结果JSON生成报告 |

### 1. 自动生成（推荐）

运行pytest测试后会自动生成报告（通过conftest.py的hook）：

```bash
# 运行测试
pytest -v

# 测试完成后报告自动生成在 test_reports/{模型名}_{时间}/
```

### 2. 快速测试报告

运行P0级别的核心测试并生成报告：

```bash
python scripts/quick_report.py
```

### 3. 手动生成报告

基于已有的pytest JSON结果重新生成或定制报告：

```bash
# 基于pytest JSON结果生成
python scripts/generate_report.py -j test_results/test_output.json

# 指定模型生成
python scripts/generate_report.py -j test_results/test_output.json -m minimax25

# 指定输出目录
python scripts/generate_report.py -o my_reports
```

### 报告目录结构

```
test_reports/
└── {chip_name}/              # 芯片平台目录
    └── {model_name}/         # 模型目录
        └── {model_name}_{timestamp}/
            └── test_report_{model_name}_{timestamp}.md
```

示例：
```
test_reports/
└── nvidia-h100/
    └── minimax25/
        └── minimax25_20260504172556/
            └── test_report_minimax25_20260504172556.md
```

### 报告格式

报告包含：
- 各测试分类的测试点表格（状态：✅通过 ❌未通过 ⏳未测试）
- 统计汇总表格（通过率统计）

## uv 虚拟环境使用指南

### 什么是 uv？

[uv](https://github.com/astral-sh/uv) 是 Astral 公司开发的 Python 包管理工具，比 pip 更快、更可靠。

### uv 常用命令

```bash
# 创建虚拟环境
uv venv

# 激活虚拟环境
# Linux/macOS
source .venv/bin/activate
# Windows CMD
.venv\Scripts\activate.bat
# Windows PowerShell
.venv\Scripts\Activate.ps1

# 安装依赖
uv pip install -r requirements.txt

# 安装特定包
uv pip install pytest requests pyyaml

# 升级包
uv pip install --upgrade pytest

# 查看已安装的包
uv pip list

# 退出虚拟环境
deactivate
```

### 在 IDE 中使用 uv 环境

如果使用 VS Code 或 PyCharm，需要将 IDE 的 Python 解释器路径设置为虚拟环境路径：

```bash
# Linux/macOS
.venv/bin/python

# Windows
.venv\Scripts\python.exe
```

### uv 环境下的测试运行

```bash
# 激活环境后直接运行
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows

# 运行测试
pytest -v

# 或使用 uv run（不需要手动激活）
uv run pytest -v
```