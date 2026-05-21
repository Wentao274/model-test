# 大模型推理能力测试框架

基于 checkpoints.md 文档设计的大模型推理能力测试框架，覆盖 10 大类共 83 个测试点。

## 快速开始

### 1. 安装依赖

```bash
# 安装 uv（推荐）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境并安装依赖
uv venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
uv pip install -r requirements.txt

# 安装 Allure 命令行工具（用于生成 HTML 报告）
# Ubuntu/Debian: sudo apt-add-repository ppa:qameta/allure && sudo apt-get update && sudo apt-get install allure
# macOS: brew install allure
```

### 2. 一行命令运行测试并生成报告

```bash
# 运行 P0 测试 + 生成 Allure 报告（推荐）
pytest -v -m p0 \
  --base-url http://127.0.0.1:8080/v1 \
  --api-key abc123 \
  --model-name minimax-m2.5 \
  --chip hygon-bw1000 && \
allure generate allure-results/hygon-bw1000/minimax-m2.5 -o allure-report/hygon-bw1000/minimax-m2.5 --clean && \
allure open allure-report/hygon-bw1000/minimax-m2.5
```

### 3. 基础运行命令

```bash
# 使用 config.yaml 配置运行
pytest -v

# 使用命令行参数运行
pytest -v \
  --base-url http://127.0.0.1:8080/v1 \
  --api-key abc123 \
  --model-name minimax-m2.5 \
  --chip hygon-bw1000

# 使用环境变量运行
export BASE_URL=http://127.0.0.1:8080/v1
export API_KEY=abc123
export MODEL_NAME=minimax-m2.5
export CHIP=hygon-bw1000
pytest -v
```

### 4. 参数说明

| 参数 | 环境变量 | 说明 |
|------|---------|------|
| `--base-url` | `BASE_URL` | API 基础地址 |
| `--api-key` | `API_KEY` | API 密钥 |
| `--model-name` | `MODEL_NAME` | 模型名称 |
| `--chip` | `CHIP` | 芯片平台名称（自动转小写，用于日志/报告目录） |
| `--thinking-mode` | `THINKING_MODE` | 启用思考模式（不指定则使用 config.yaml 配置） |

**优先级**：命令行参数 > 环境变量 > config.yaml

## 测试分类

| 分类 | 测试点数 | 说明 |
|------|---------|------|
| A. 基础推理能力 | 12 | 单轮/多轮对话、流式输出、参数控制 |
| B. 高级生成功能 | 10 | 思考模式、工具调用、JSON Mode |
| C. 多模态能力 | 8 | 图片/视频理解、OCR |
| D. 长上下文处理 | 8 | 长文本、大海捞针 |
| E. 性能指标 | 12 | 延迟、吞吐、并发（已禁用） |
| F. 稳定性与边界 | 8 | 异常输入、OOM恢复 |
| G. API兼容性 | 8 | OpenAI 接口兼容 |
| H. 质量评估 | 5 | 生成质量、幻觉率 |
| I. 超长上下文验证 | 4 | 超长上下文脚本验证 |
| J. 回答质量与相关性 | 8 | 相关性、乱码检测 |

> 总计：83 个测试点

## 按分类运行

```bash
pytest -m a_basic -v        # 基础推理能力
pytest -m b_advanced -v     # 高级生成功能
pytest -m c_multimodal -v   # 多模态能力
pytest -m d_long_context -v # 长上下文处理
pytest -m f_stability -v    # 稳定性与边界
pytest -m g_api -v          # API兼容性
pytest -m h_quality -v      # 质量评估
pytest -m i_long_context -v # 超长上下文验证
pytest -m j_response_quality -v  # 回答质量与相关性
pytest -m p0 -v             # P0 优先级测试
pytest -m smoke -v          # 冒烟测试
```

## 报告生成

### 目录结构

```
allure-results/                     # Allure 原始数据
├── hygon-bw1000/minimax-m2.5/     # 按芯片/模型分离
└── nvidia-h100/qwen35/

allure-report/                      # HTML 报告
├── hygon-bw1000/minimax-m2.5/
│   ├── index.html                  # HTML 报告首页
│   └── minimax-m2.5_xxx/test_report_xxx.md  # Markdown 汇总
└── nvidia-h100/qwen35/

test_reports/                       # Markdown 报告
├── hygon-bw1000/minimax-m2.5/
│   └── minimax-m2.5_xxx/test_report_xxx.md
└── nvidia-h100/qwen35/
```

### 生成 Allure 报告

```bash
# 测试完成后生成 HTML 报告
allure generate allure-results/hygon-bw1000/minimax-m2.5 -o allure-report/hygon-bw1000/minimax-m2.5 --clean

# 打开报告
allure open allure-report/hygon-bw1000/minimax-m2.5

# 或实时查看
allure serve allure-results/hygon-bw1000/minimax-m2.5
```

### 其他报告格式

```bash
pytest --html=report.html           # HTML 报告
pytest --junit-xml=report.xml       # JUnit XML
```

## 配置文件

编辑 `config.yaml`：

```yaml
# 芯片平台配置
chips:
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
    thinking_mode: true           # 思考模式

default_model: minimax25
```

## 支持的模型

| 模型 | 配置名 | 思考模式参数 |
|------|--------|-------------|
| Qwen 3.5 | qwen35 | enable_thinking |
| Kimi K2.5 | kimi_k25 | thinking |
| GLM-5 | glm5 | enable_thinking |
| Minimax 2.5 | minimax25 | enable_thinking |

## 目录结构

```
model-test/
├── config.yaml           # 配置文件
├── requirements.txt      # Python 依赖
├── conftest.py           # pytest 配置
├── base/                 # 基础模块
├── tests/                # 测试用例
├── scripts/              # 工具脚本
├── logs/                 # 日志（运行后生成）
├── test_reports/         # Markdown 报告
└── allure-results/       # Allure 原始数据
```

## 详细文档

- [测试文档导航](docs/README.md)
- [Allure 报告使用指南](docs/allure_report.md)
- [A类测试说明](docs/test_a_basic_reasoning.md)
- [B类测试说明](docs/test_b_advanced_generation.md)
- [J类测试说明](docs/test_j_response_quality.md)

## Jenkins Pipeline

项目提供了 `Jenkinsfile`，支持参数化构建：

```bash
# 构建参数
CHIP=hygon-bw1000        # 芯片平台
MODEL=minimax-m2.5        # 模型名称
BASE_URL=http://...        # API 地址
API_KEY=xxx                # API 密钥
THINKING_MODE=false        # 思考模式
MARKER=p0                  # 测试标记
```

**输出**：
- `reports/{BUILD_NUMBER}.tar.gz` - 包含 Markdown 报告、日志、Allure HTML
- Jenkins Allure 插件自动展示报告趋势

## 注意事项

1. 确保模型服务已启动并可访问
2. 芯片名称自动转小写（NVIDIA-H100 → nvidia-h100）
3. thinking_mode 不指定时使用 config.yaml 配置
4. E 类性能测试已默认禁用