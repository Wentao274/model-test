# 大模型推理能力测试框架

基于 checkpoints.md 文档设计的大模型推理能力测试框架，覆盖 9 大类共 96 个测试点，用于评估大模型推理服务（OpenAI 兼容 API）的功能完备性与生成质量。

测试可通过 **本地手动执行** 或 **Jenkins 流水线触发** 两种方式运行，自动生成 Allure HTML 报告与 Markdown 汇总报告，并按用例优先级（P0/P1/P2）给出测试结论。

---

## 目录

- [测试分类](#测试分类)
- [环境准备](#环境准备)
- [手动执行测试](#手动执行测试)
- [报告生成](#报告生成)
- [通过 Jenkins 构建触发测试](#通过-jenkins-构建触发测试)
- [测试结论判定](#测试结论判定)
- [支持的模型](#支持的模型)
- [目录结构](#目录结构-1)
- [详细文档](#详细文档)
- [注意事项](#注意事项)

---

## 测试分类

| 分类 | Marker | 测试点数 | 说明 |
|------|--------|---------|------|
| A. 基础推理能力 | `a_basic` | 12 | 单轮/多轮对话、流式输出、参数控制 |
| B. 高级生成功能 | `b_advanced` | 10 | 思考模式、工具调用、JSON Mode |
| C. 多模态能力 | `c_multimodal` | 8 | 图片/视频理解、OCR |
| D. 长上下文处理 | `d_long_context` | 12 | 长文本、大海捞针、超长上下文验证 |
| E. 性能指标 | `e_performance` | 12 | 延迟、吞吐、并发（**已默认禁用**） |
| F. 稳定性与边界 | `f_stability` | 8 | 异常输入、OOM 恢复 |
| G. API 兼容性 | `g_api` | 8 | OpenAI 接口兼容 |
| H. Chat Completions API 质量评估 | `h_quality_chat_completions` | 13 | 生成质量、幻觉率、回答相关性、乱码检测 |
| I. Completions API 质量评估 | `i_quality_completions` | 13 | 生成质量、幻觉率、回答相关性、乱码检测 |

> 总计：96 个测试点（P0: 37 / P1: 48 / P2: 11）

---

## 环境准备

### 1. 前置条件

- **Python 3.8+**
- **[uv](https://github.com/astral-sh/uv)**（推荐，用于创建虚拟环境与安装依赖；也可使用 pip）
- **Allure 命令行工具**（仅生成 HTML 报告时需要，运行测试本身不依赖）
- **一个可访问的模型推理服务**（提供 OpenAI 兼容的 `/v1/chat/completions` 接口）

### 2. 安装 uv

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. 创建虚拟环境并安装依赖

```bash
# 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows (PowerShell: .venv\Scripts\Activate.ps1)

# 安装 Python 依赖
uv pip install -r requirements.txt
```

> `requirements.txt` 包含：pytest、allure-pytest、requests、pyyaml、pytest-xdist、sseclient-py、Pillow 等。

### 4. 安装 Allure 命令行工具

Allure CLI 用于把 `allure-results` 原始数据渲染为 HTML 报告。项目提供了自动安装脚本：

```bash
# 自动检测系统并安装（Ubuntu/Debian/macOS/Windows-scoop）
bash scripts/install_allure.sh
```

也可手动安装：

```bash
# Ubuntu/Debian
sudo apt-add-repository ppa:qameta/allure && sudo apt-get update && sudo apt-get install allure
# macOS
brew install allure
# Windows
scoop install allure
# 或从 https://github.com/allure-framework/allure2/releases 下载
```

验证：`allure --version`

### 5. 配置文件（可选）

编辑 `config.yaml` 可预置芯片平台与模型信息。命令行参数与环境变量会覆盖此配置（优先级见[手动执行测试](#手动执行测试)）。

```yaml
chips:
  hygon-bw1000:
    enabled: true
    base_url: http://10.212.16.23:8080

models:
  glm5:
    name: glm5
    display_name: GLM-5
    api_key: abc123
    enabled: true
    thinking_mode: true
    thinking_key: "enable_thinking"

default_model: minimax25
```

> 配置文件中 `${VAR}` 形式的值会自动从环境变量读取（如 `api_key: ${QWEN_API_KEY}`）。

---

## 手动执行测试

### 配置优先级

测试参数按以下优先级解析（高 → 低）：

**命令行参数 > 环境变量 > `config.yaml`**

### 方式一：命令行参数（推荐）

```bash
# 最简命令（仅必填参数）
pytest -v \
  --base-url http://10.201.149.10:8080 \
  --model-name kimi-k25 \
  --thinking-mode

# 完整参数
pytest -v \
  --base-url http://10.201.149.10:8080 \
  --api-key your-api-key \
  --model-name kimi-k25 \
  --chip nvidia-h100 \
  --engine vllm \
  --pd-mode agg \
  --tester yourname \
  --thinking-mode
```

> **关于 `--base-url`**：无需带 `/v1` 后缀，框架会自动拼接 `/v1/chat/completions`；若误带 `/v1` 也会被自动去除。
>
> **关于鉴权**：传入 `--api-key` 即携带 `Authorization: Bearer <key>` 头；传入 `--api-key ""`（空字符串）则不发送鉴权头。完全省略该参数时会使用占位 key。

### 方式二：环境变量

```bash
# Linux/macOS
export BASE_URL=http://10.201.149.10:8080
export API_KEY=your-api-key
export MODEL_NAME=kimi-k25
export CHIP=nvidia-h100
export THINKING_MODE=true
pytest -v

# Windows PowerShell
$env:BASE_URL="http://10.201.149.10:8080"
$env:MODEL_NAME="kimi-k25"
$env:THINKING_MODE="true"
pytest -v
```

### 方式三：修改 `config.yaml`

启用一个芯片和一个模型后直接运行：

```bash
pytest -v
```

### 一行命令运行测试并生成报告

```bash
# 运行 P0 测试 + 生成 Allure 报告（推荐）
pytest -v -m p0 \
  --base-url http://127.0.0.1:8080 \
  --api-key abc123 \
  --model-name minimax-m2.5 \
  --chip hygon-bw1000 \
  --thinking-mode \
  --alluredir=allure-results/local \
  --summary-report-dir=allure-report/local && \
allure generate allure-results/local -o allure-report/local --clean && \
allure open allure-report/local
```

### 运行指定测试

```bash
# 按分类运行
pytest -v -m a_basic --base-url http://10.201.149.10:8080 --model-name kimi-k25 --thinking-mode

# 按优先级运行（P0 冒烟测试）
pytest -v -m "p0 and smoke" --base-url http://10.201.149.10:8080 --model-name kimi-k25 --thinking-mode

# 运行单个测试文件
pytest -v tests/test_a_basic_reasoning.py --base-url http://10.201.149.10:8080 --model-name kimi-k25 --thinking-mode

# 运行单个测试用例
pytest -v tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_conversation \
  --base-url http://10.201.149.10:8080 --model-name kimi-k25 --thinking-mode

# 关闭思考模式
pytest -v -m a_basic --base-url http://10.201.149.10:8080 --model-name kimi-k25 --no-thinking-mode
```

可用 Marker 列表（`pytest -m <marker>`）：

```bash
pytest -m a_basic -v                        # 基础推理能力
pytest -m b_advanced -v                     # 高级生成功能
pytest -m c_multimodal -v                   # 多模态能力
pytest -m d_long_context -v                 # 长上下文处理
pytest -m f_stability -v                    # 稳定性与边界
pytest -m g_api -v                          # API 兼容性
pytest -m h_quality_chat_completions -v     # Chat Completions API 质量评估
pytest -m i_quality_completions -v          # Completions API 质量评估
pytest -m p0 -v                             # P0 优先级测试
pytest -m p1 -v                             # P1 优先级测试
pytest -m p2 -v                             # P2 优先级测试
pytest -m smoke -v                          # 冒烟测试（核心功能快速验证）
pytest -m slow -v                           # 慢速测试
```

> E 类（`e_performance`）测试已在 `conftest.py` 中自动标记为 skip，即使选中也不会执行。

### 参数说明

| 参数 | 环境变量 | 必填 | 说明 |
|------|---------|------|------|
| `--base-url` | `BASE_URL` | 是 | API 地址（无需带 `/v1`，框架自动拼接/去除） |
| `--model-name` | `MODEL_NAME` | 是 | 模型服务名称（如 `kimi-k25`、`glm5`、`minimax-m2.5`） |
| `--api-key` | `API_KEY` | 否 | API 密钥；传空字符串则不携带鉴权头 |
| `--chip` | `CHIP` | 否 | 芯片平台名称（自动转小写，用于日志/报告目录标识） |
| `--thinking-mode` | `THINKING_MODE=true` | 否 | 启用思考模式 |
| `--no-thinking-mode` | — | 否 | 显式关闭思考模式 |
| `--engine` | — | 否 | 推理框架（vllm / sglang，仅用于报告标识） |
| `--pd-mode` | — | 否 | PD 分离模式（agg / disagg，仅用于报告标识） |
| `--tester` | — | 否 | 测试人员名称（仅用于报告标识） |
| `--alluredir` | — | 否 | Allure 结果输出目录（不指定则按芯片/模型/时间戳自动生成） |
| `--summary-report-dir` | — | 否 | Markdown 汇总报告输出目录（默认 `allure-report`） |
| `--model` | — | 否 | 指定 `config.yaml` 中的模型配置名（如 `qwen35`、`glm5`） |

### 连通性检查

测试启动前，`conftest.py` 会自动向 `{base_url}/v1/chat/completions` 发送一个最小请求（`hello`，`max_tokens=10`）验证连通性：

- **通过**：继续执行用例
- **失败**：直接退出进程（exit code 2），不执行任何用例

`api_key` 为空时不携带 `Authorization` 头。Jenkins 构建中，失败原因会写入标记文件并在邮件中提示（详见 [Jenkins 章节](#连通性检查失败处理)）。

---

## 报告生成

测试结束后，`conftest.py` 会自动生成两类报告：

1. **Markdown 汇总报告**：含统计汇总、分类统计、测试结论，输出到 `--summary-report-dir`（默认 `allure-report/`）及 `test_reports/`
2. **Allure 原始数据**：输出到 `--alluredir`（未指定时按 `allure-results/{chip}/{model}/{timestamp}` 自动生成）

### 目录结构

```
allure-results/                     # Allure 原始数据
├── hygon-bw1000/minimax-m2.5/     # 按芯片/模型分离
└── nvidia-h100/qwen35/

allure-report/                      # Markdown 汇总报告 + Allure HTML
├── hygon-bw1000/minimax-m2.5/
│   ├── index.html                  # Allure HTML 报告首页（需手动 generate）
│   └── minimax-m2.5_xxx/test_report_xxx.md  # Markdown 汇总
└── nvidia-h100/qwen35/

test_reports/                       # Markdown 报告
├── hygon-bw1000/minimax-m2.5/
│   └── minimax-m2.5_xxx/test_report_xxx.md
└── nvidia-h100/qwen35/
```

### 生成 Allure HTML 报告

```bash
# 由 allure-results 生成 HTML 报告
allure generate allure-results/hygon-bw1000/minimax-m2.5 -o allure-report/hygon-bw1000/minimax-m2.5 --clean

# 打开报告
allure open allure-report/hygon-bw1000/minimax-m2.5

# 或实时查看（不落盘）
allure serve allure-results/hygon-bw1000/minimax-m2.5
```

### 其他报告格式

```bash
pytest --html=report.html           # HTML 报告（需 pytest-html）
pytest --junit-xml=report.xml       # JUnit XML
```

---

## 通过 Jenkins 构建触发测试

项目根目录的 `Jenkinsfile` 定义了完整的 CI 流水线：Jenkins master 节点通过 **SSH** 连接到远程测试主机（`10.201.132.50`），在远程仓库目录同步代码、执行 pytest，再将报告拉回 Jenkins 并发送邮件通知。

### 运行机制

- **Jenkins agent**：`master` 节点
- **远程主机**：`10.201.132.50`（用户 `root`），通过 SSH 凭证 `HOST_SSH_KEY` 免密登录
- **远程工作目录**：由 `WORK_DIR` 参数指定（默认 `/dingofs/data2/userdata/liwt/maas-image/model-test`）
- **构建产物目录**：远程 `builds/${TESTER}/${BUILD_NUMBER}/`，Jenkins 端 `reports/${BUILD_NUMBER}/`
- 代码同步通过 `git restore . && git pull` 完成（经内网代理 `100.64.1.68:1080`）

### 构建参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `TESTER` | string | `liwt` | 测试人员名称（必填，用于产物目录与报告标识） |
| `CHIP` | string | `nvidia-h100` | 芯片平台名称（必填） |
| `ENGINE` | choice | `vllm` | 推理框架：`vllm` / `sglang` |
| `PD` | choice | `agg` | PD 分离模式：`agg`（非分离）/ `disagg`（PD 分离） |
| `MODEL` | string | `kimi-k2.5` | 模型服务名称（必填） |
| `BASE_URL` | string | `http://10.201.149.10:8080` | API 地址（必填，**无需带 `/v1`**） |
| `API_KEY` | password | 空 | API Key（可选，留空则不携带鉴权头） |
| `THINKING_MODE` | boolean | `true` | 启用思考模式 |
| `MARKER` | choice | `all` | 测试标记，见下表 |
| `DESCRIPTION` | string | 空 | 模型服务的描述信息（展示在邮件概要中） |
| `RECIPIENTS` | text | `liwt@zetyun.com` | 测试报告邮件接收者（逗号分隔） |
| `WORK_DIR` | string | `/dingofs/data2/.../model-test` | 远程测试仓库目录（请勿改动） |

**`MARKER` 可选值**：

| 值 | 含义 |
|----|------|
| `all` | 全部测试（不传 `-m`） |
| `a_basic` ~ `i_quality_completions` | 按 A~I 分类运行 |
| `p0` / `p1` / `p2` | 按优先级运行 |
| `smoke` | 冒烟测试 |
| `slow` | 慢速测试 |

### Pipeline 阶段

| 阶段 | 说明 |
|------|------|
| 1. 打印测试参数 | 输出本次构建的所有参数信息 |
| 2. 环境检查 | SSH 到远程主机，`git pull` 同步代码；不存在则 `uv venv` 创建虚拟环境；`uv pip install -r requirements.txt` 安装依赖 |
| 3. 运行测试 | 执行 pytest，根据 `THINKING_MODE` 选择 `--thinking-mode` / `--no-thinking-mode`，根据 `MARKER` 决定是否加 `-m`；输出 Allure 数据与 Markdown 汇总到构建产物目录。该阶段失败仅将 stage 标记为 FAILURE，构建结果置为 UNSTABLE，不中断后续报告阶段 |
| 4. 生成 Allure 报告 | 远程调用 `allure generate` 生成 HTML 报告 |
| 5. 拉取报告到 Jenkins | 将 Markdown 报告、`allure-results`、`allure-html` 通过 `scp` + `tar` 拉取到 Jenkins 的 `reports/${BUILD_NUMBER}/` |
| 6. 发送邮件 | 解析 Markdown 报告，提取统计汇总/分类统计/测试结论，渲染为 HTML 邮件发送；附件为完整 Markdown 报告 |
| 7. 清理旧构建 | 远程保留最近 20 次构建记录，自动清理更早的 |

### 远程构建输出目录

构建结果存储在远程主机的 `builds/${TESTER}/${BUILD_NUMBER}/` 目录下：

```
builds/{TESTER}/{BUILD_NUMBER}/
├── allure-results/          # Allure 原始数据（pytest --alluredir）
├── allure-report/           # Markdown 汇总报告（--summary-report-dir）
│   └── {chip}/{model}/
│       └── {model}_{ts}/
│           └── test_report_{model}_{ts}.md
├── allure-html/             # Allure HTML 报告（allure generate 输出）
└── *.md                     # Markdown 报告副本（供邮件拉取）
```

### Jenkins 端产物

每次构建结束后，`post.always` 阶段会：

1. **归档产物**：`archiveArtifacts reports/${BUILD_NUMBER}/**`，可在 Jenkins UI 直接下载
2. **Allure 插件**：基于 `reports/${BUILD_NUMBER}/allure-results` 在 Jenkins 内生成 Allure 报告页面
3. **清理工作空间**：`cleanWs()` 清理 master 节点临时文件

### 邮件通知

邮件主题格式：`[模型推理 - 功能测试报告] {芯片} - {模型} - 构建 #{编号} - {状态}`

邮件正文包含：

1. **测试概要** — 构建编号、模型描述、测试人员、芯片/模型/框架/PD 模式/测试标记/思考模式、执行时间、构建状态
2. **统计汇总** — 总测试点数、通过/未通过/部分通过/未测试数量及占比、通过率
3. **分类统计** — 按 9 大分类的通过率统计
4. **测试结论** — 按用例优先级（P0/P1/P2）自动判定（详见[测试结论判定](#测试结论判定)）

附件包含完整的 Markdown 测试报告。模型名中的路径分隔符（如 `org/model`）会自动取最后一段作为展示名。

### 连通性检查失败处理

若 API 连通性检查失败，pytest 会将失败原因写入标记文件 `${BUILD_OUTPUT_DIR}/.connectivity_check_failed` 后退出。发送邮件阶段会读取该文件，在邮件正文顶部以红色提示框展示失败原因，此时不会有用例被执行，统计/分类/结论区域为空。

### 清理策略

每次构建的"清理旧构建"阶段会在远程 `builds/${TESTER}/` 目录下按时间倒序保留最近 **20** 次构建，更早的自动删除。

---

## 测试结论判定

测试报告的"测试结论"区域按**用例优先级（P0/P1/P2）**对未通过/部分通过的用例进行综合评估，分类关键等级不再作为判定依据。

### 用例优先级与级别映射

| 优先级 | 级别名 | 说明 |
|-------|-------|------|
| P0 | 关键 | 必保指标，失败必须修复 |
| P1 | 重要 | 推荐指标，失败建议修复 |
| P2 | 一般 | 增强指标，失败可酌情接受 |

每个测试用例的优先级在 `base/test_definitions.py` 中配置（合计 96 项）：P0 = 37，P1 = 48，P2 = 11。

### 判定规则

按以下优先级依次判断，满足即返回结论：

| 结论 | 判定条件 | 含义 |
|------|---------|------|
| ❌ 不通过 | 存在 P0 用例未通过或部分通过 | 必须修复后重新测试 |
| ⚠️ 有条件通过 | 存在 P1 用例未通过或部分通过（P0 全部通过或未运行） | 建议修复后重新测试 |
| ⚠️ 有条件通过 | 仅存在 P2 用例未通过或部分通过（P0/P1 全部通过或未运行） | 可酌情接受，建议后续修复 |
| ⚠️ 有条件通过 | 已运行用例全部通过但存在警告项 | 所有已运行用例通过，警告项需关注 |
| ✅ 通过 | 已运行用例全部通过且无警告 | 测试结果可接受 |

> **关于未运行（SKIPPED）用例**：未运行的用例**不参与**结论判定，既不计入失败，也不计入通过。在统计汇总中，`通过率 = 通过 / (通过 + 未通过)`，`未测试` 单独展示但不参与分母。

### 结论展示内容

结论区域按优先级分层展示问题详情：

1. **关键(P0)优先级问题** — 列出所有 P0 用例中未通过/部分通过的用例及原因
2. **重要(P1)优先级问题** — 列出所有 P1 用例中未通过/部分通过的用例及原因
3. **一般(P2)优先级问题** — 列出所有 P2 用例中未通过/部分通过的用例及原因
4. **警告项** — 列出通过但带有警告的用例及警告内容（标注所属分类与优先级）

每条问题项格式：`❌ {用例编号} {用例名}（{优先级}）：{详细原因}`。

---

## 支持的模型

以下模型已在 `config.yaml` 中预置（`thinking_via_chat_template=false` 时，思考参数以 `extra_body` 形式下发；`true` 时通过 `chat_template_kwargs` 下发）：

| 配置名 | 显示名 | API 模型名 | thinking_key | 默认思考模式 |
|--------|--------|-----------|--------------|-------------|
| `qwen35` | Qwen 3.5 | qwen3.5 | `enable_thinking` | true |
| `kimi_k25` | Kimi K2.5 | kimi-k25 | `thinking` | true |
| `glm5` | GLM-5 | glm5 | `enable_thinking` | true |
| `glm51` | GLM-5.1 | glm51 | `enable_thinking` | true |
| `minimax21` | Minimax 2.1 | minimax-m21 | — | false |
| `minimax25` | Minimax 2.5 | minimax-m2.5 | `enable_thinking` | true |

> 默认测试模型：`minimax25`。命令行 `--model-name` 指定的是 **API 模型名**，`--model` 指定的是 **config.yaml 中的配置名**。

---

## 目录结构

```
model-test/
├── config.yaml           # 配置文件（芯片/模型/测试参数）
├── requirements.txt      # Python 依赖
├── pytest.ini            # pytest 配置（marker、addopts）
├── conftest.py           # pytest 全局配置（命令行选项、连通性检查、报告生成）
├── Jenkinsfile           # Jenkins 流水线定义
├── checkpoints.md        # 测试点设计文档
├── base/                 # 基础模块（API 客户端、日志、报告生成、测试定义）
├── tests/                # 测试用例（test_a_ ~ test_i_）
├── fixtures/             # 测试 fixtures（图片/视频/代码/工具）
├── scripts/              # 工具脚本（install_allure.sh、quick_report.py、generate_report.py）
├── docs/                 # 详细文档
├── logs/                 # 日志（运行后生成，已 gitignore）
├── test_reports/         # Markdown 报告（运行后生成，已 gitignore）
├── allure-results/       # Allure 原始数据（运行后生成，已 gitignore）
├── allure-report/        # Allure HTML / Markdown 汇总（运行后生成，已 gitignore）
└── builds/               # Jenkins 远程构建产物（已 gitignore）
```

---

## 详细文档

- [测试文档导航](docs/README.md)
- [Allure 报告使用指南](docs/allure_report.md)
- [A 类测试说明](docs/test_a_basic_reasoning.md)
- [B 类测试说明](docs/test_b_advanced_generation.md)
- [C 类测试说明](docs/test_c_multimodal.md)
- [D 类测试说明](docs/test_d_long_context.md)
- [E 类测试说明](docs/test_e_performance.md)
- [F 类测试说明](docs/test_f_stability.md)
- [G 类测试说明](docs/test_g_api_compatibility.md)
- [H 类测试说明](docs/test_h_quality_chat_completions.md)
- [I 类测试说明](docs/test_i_quality_completions.md)

---

## 注意事项

1. 确保模型服务已启动并可访问，否则连通性检查会直接终止测试。
2. `--base-url` 无需带 `/v1` 后缀，框架会自动拼接；若误带也会自动去除。
3. 芯片名称自动转小写（如 `NVIDIA-H100` → `nvidia-h100`）。
4. `thinking_mode` 不指定时使用 `config.yaml` 中的模型配置；命令行 `--thinking-mode` / `--no-thinking-mode` 优先级最高。
5. E 类性能测试已默认禁用（`conftest.py` 中自动 skip）。
6. Jenkins 构建中"运行测试"阶段失败不会中断流水线，后续报告生成与邮件发送仍会执行（构建结果置为 UNSTABLE）。
7. Jenkins 远程构建保留最近 20 次产物，更早的自动清理。
