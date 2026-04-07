# 大模型推理能力测试框架

基于 checkpoints.md 文档设计的大模型推理能力测试框架，覆盖 9 大类共 62 个测试点。

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

编辑 `config.yaml`，配置模型的 base_url 和端口：

```yaml
models:
  qwen35:
    base_url: http://localhost:8000/v1
    enabled: true
```

### 5. 运行测试

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

# 指定模型运行
pytest --model=qwen35 -v
```

## 测试分类概览

| 分类 | 测试点数 | 测试文件 | 说明 |
|------|---------|---------|------|
| A. 基础推理能力 | 8 | test_a_basic_reasoning.py | 单轮/多轮对话、流式输出、多语言 |
| B. 高级生成功能 | 9 | test_b_advanced_generation.py | 思考模式、工具调用、JSON Mode |
| C. 多模态能力 | 8 | test_c_multimodal.py | 图片理解、视频理解、OCR |
| D. 长上下文处理 | 8 | test_d_long_context.py | 短/中/长上下文、大海捞针、边界 |
| E. 性能指标 | 12 | test_e_performance.py | TTFT、TPOT、吞吐量、并发 |
| F. 稳定性与边界 | 8 | test_f_stability.py | 异常输入、OOM恢复、并发稳定性 |
| G. API兼容性 | 4 | test_g_api_compatibility.py | OpenAI兼容、Usage统计 |
| H. 质量评估 | 4 | test_h_quality.py | 生成质量、一致性、幻觉率、指令遵循 |
| I. 单项超长上下文验证 | 1 | test_i_long_context.py | 超长上下文脚本验证 |

## 配置文件说明

`config.yaml` 是测试框架的主配置文件：

```yaml
# 全局配置
global:
  timeout: 120          # 请求超时（秒）
  retry_times: 3        # 重试次数
  log_level: INFO       # 日志级别
  output_dir: ./test_results

# 模型配置
models:
  qwen35:
    name: qwen35
    api_key: ${QWEN_API_KEY}
    base_url: http://localhost:8000/v1
    enabled: true

# 默认测试模型
default_model: qwen35
```

配置支持环境变量：`${ENV_VAR}` 格式会自动读取环境变量值。

## 支持的模型

| 模型 | 配置名 | 说明 |
|------|--------|------|
| Qwen 3.5 | qwen35 | 阿里Qwen系列 |
| Kimi K2.5 | kimi_k25 | 月之暗面Kimi |
| GLM-5 | glm5 | 智谱GLM系列 |
| Minimax 2.1 | minimax21 | Minimax系列（默认关闭） |
| Minimax 2.5 | minimax25 | Minimax系列 |

## 目录结构

```
model-test/
├── config.yaml           # 配置文件
├── requirements.txt      # Python依赖
├── pytest.ini           # pytest配置
├── conftest.py          # pytest全局配置
├── base/                # 基础模块
│   ├── api_client.py    # API客户端
│   └── base_test.py     # 基础测试类
├── tests/               # 测试用例
│   ├── test_a_*.py      # A类测试
│   ├── test_b_*.py      # B类测试
│   └── ...
├── docs/                # 测试文档
│   ├── test_a_*.md      # A类测试说明
│   └── ...
└── fixtures/            # 测试素材（需创建）
    └── images/
```

## 运行选项

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

```bash
pytest --html=report.html
pytest --junit-xml=report.xml
```

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

## 注意事项

1. 确保模型服务已启动并可访问
2. 根据实际模型支持情况调整配置
3. 性能测试结果受网络和服务器负载影响
4. 部分测试需要GPU环境（如显存测试）

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