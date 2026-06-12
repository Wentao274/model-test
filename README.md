# 大模型推理能力测试框架

基于 checkpoints.md 文档设计的大模型推理能力测试框架，覆盖 9 大类共 96 个测试点。

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
| D. 长上下文处理 | 12 | 长文本、大海捞针、超长上下文验证 |
| E. 性能指标 | 12 | 延迟、吞吐、并发（已禁用） |
| F. 稳定性与边界 | 8 | 异常输入、OOM恢复 |
| G. API兼容性 | 8 | OpenAI 接口兼容 |
| H. Chat Completions API 质量评估与回答相关性 | 13 | Chat Completions API 生成质量、幻觉率、回答相关性、乱码检测 |
| I. Completions API 质量评估与回答相关性 | 13 | Completions API 生成质量、幻觉率、回答相关性、乱码检测 |

> 总计：96 个测试点

## 按分类运行

```bash
pytest -m a_basic -v        # 基础推理能力
pytest -m b_advanced -v     # 高级生成功能
pytest -m c_multimodal -v   # 多模态能力
pytest -m d_long_context -v # 长上下文处理
pytest -m f_stability -v    # 稳定性与边界
pytest -m g_api -v          # API兼容性
pytest -m h_quality_chat_completions -v  # Chat Completions API 质量评估
pytest -m i_quality_completions -v  # Completions API 质量评估
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
- [H类测试说明](docs/test_h_quality_chat_completions.md)
- [I类测试说明](docs/test_i_quality_completions.md)

## Jenkins Pipeline

项目提供了 `Jenkinsfile`，通过 SSH 在远程主机上执行测试，并将结果拉取回 Jenkins 发送邮件通知。

### 构建参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `TESTER` | string | `liwt` | 测试人员名称（必填） |
| `INFRA` | choice | `vllm` | 推理框架（vllm / sglang） |
| `PD` | choice | `agg` | PD分离模式（agg=非分离 / disagg=PD分离） |
| `CHIP` | string | `nvidia-h100` | 芯片平台名称 |
| `MODEL` | string | `kimi-k2.5` | 模型名称 |
| `BASE_URL` | string | `http://10.201.149.10:8080/v1` | API 地址（必填，需带 /v1 后缀） |
| `API_KEY` | password | 空 | API Key（可选） |
| `THINKING_MODE` | boolean | `true` | 启用思考模式 |
| `MARKER` | choice | `all` | 测试标记（p0/p1/smoke/h_quality_chat_completions/i_quality_completions 等，all=全部） |
| `RECIPIENTS` | text | `liwt@zetyun.com` | 邮件接收者（逗号分隔） |
| `WORK_DIR` | string | `/dingofs/data1/...` | 远程测试仓库目录 |

### Pipeline 阶段

| 阶段 | 说明 |
|------|------|
| 环境检查 | SSH 到远程主机，同步代码、创建虚拟环境、安装依赖 |
| 运行测试 | 执行 pytest，生成 Allure 数据和 Markdown 汇总报告 |
| 生成 Allure 报告 | 调用 `allure generate` 生成 HTML 报告 |
| 拉取报告到 Jenkins | 将 Markdown 报告、allure-results、Allure HTML 拉取到 Jenkins |
| 发送邮件 | 解析 Markdown 报告，生成 HTML 邮件发送通知 |
| 清理旧构建 | 保留最近 20 次构建记录，自动清理更早的 |

### 邮件通知

邮件正文包含以下信息，附件包含完整的 Markdown 测试报告：

1. **测试概要** — 构建编号、测试人员、芯片/模型/框架/模式等参数信息
2. **统计汇总** — 总测试点数、通过/未通过/部分通过/未测试数量及占比、通过率
3. **分类统计** — 按 8 大分类的通过率统计
4. **测试结论** — 根据分类关键等级自动判定（详见"测试结论判定"章节）

邮件主题格式：`[模型推理 - 功能测试报告] {芯片} - {模型} - 构建 #{编号} - {状态}`

### 远程构建输出

构建结果存储在远程主机的 `builds/{TESTER}/{BUILD_NUMBER}/` 目录下：

```
builds/{TESTER}/{BUILD_NUMBER}/
├── allure-results/          # Allure 原始数据
├── allure-report/           # Markdown 汇总报告
│   └── {chip}/{model}/
│       └── {model}_{ts}/
│           └── test_report_{model}_{ts}.md
└── allure-html/             # Allure HTML 报告
```

## 测试结论判定

测试报告的"分类统计"下方会自动生成**测试结论**，根据各分类的测试结果和分类关键等级综合评估。

### 分类关键等级

| 关键等级 | 分类 |
|---------|------|
| 关键 | A. 基础推理能力、H. Chat Completions API 质量评估与回答相关性 |
| 重要 | B. 高级生成功能、D. 长上下文处理、G. API兼容性、I. Completions API 质量评估 |
| 一般 | C. 多模态能力、E. 性能指标、F. 稳定性与边界 |

### 判定规则

按以下优先级依次判断，满足即返回结论：

| 结论 | 判定条件 | 含义 |
|------|---------|------|
| ❌ 不通过 | 关键分类存在未通过或部分通过用例 | 必须修复后重新测试 |
| ⚠️ 有条件通过 | 重要分类存在未通过或部分通过用例（关键分类全部通过） | 建议修复后重新测试 |
| ⚠️ 有条件通过 | 一般分类存在未通过或部分通过用例（关键+重要分类全部通过） | 可酌情接受，建议后续修复 |
| ⚠️ 有条件通过 | 全部通过但存在警告项 | 所有用例通过，但警告项需关注 |
| ✅ 通过 | 全部通过且无警告 | 测试结果可接受 |

### 结论展示内容

结论区域按优先级分层展示问题详情：

1. **关键分类问题** — 列出关键分类中未通过/部分通过的用例及原因
2. **重要分类问题** — 列出重要分类中未通过/部分通过的用例及原因
3. **一般分类问题** — 列出一般分类中未通过/部分通过的用例及原因
4. **警告项** — 列出通过但带有警告的用例及警告内容

## 注意事项

1. 确保模型服务已启动并可访问
2. 芯片名称自动转小写（NVIDIA-H100 → nvidia-h100）
3. thinking_mode 不指定时使用 config.yaml 配置
4. E 类性能测试已默认禁用