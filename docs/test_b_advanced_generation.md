# B. 高级生成功能测试

## 概述
验证模型的思考模式、工具调用、结构化输出等高级功能。

## 测试点列表

| ID  | 测试点              | 测试内容                                    | 优先级 |
|-----|-------------------|-----------------------------------------|-----|
| B1  | 思考模式（Thinking） | 开启thinking mode，验证返回思考链+最终答案        | P0  |
| B2  | 非思考模式（Instant） | 关闭thinking，无泄漏；不支持关闭则告警（不视为失败）       | P1  |
| B3  | 思考模式切换         | 同一会话内thinking↔non-thinking切换；关闭不支持则告警   | P1  |
| B4  | 工具调用-单工具       | 定义单个function，验证模型正确调用并传参           | P0  |
| B5  | 工具调用-多工具       | 定义多个function，验证模型选择正确的工具           | P1  |
| B6  | 工具调用-并行调用      | 单次回复中并行调用多个工具                      | P2  |
| B7  | 工具调用-多步链式      | 工具结果作为下一步输入，验证3+步链式执行            | P1  |
| B8  | JSON Mode         | response_format=json_object，验证输出合法JSON  | P0  |
| B9  | 结构化输出           | JSON Schema约束输出格式，验证字段完整性          | P0  |
| B10 | Prefix/Suffix约束  | 指定输出前缀或格式模板，验证遵循度                 | P2  |
| B11 | reasoning_effort 参数 | low/high/max 三档思考强度，不支持的模型告警并跳过   | P1  |

## 运行方式

```bash
# 运行所有高级生成功能测试
pytest tests/test_b_advanced_generation.py -v

# 运行特定测试
pytest tests/test_b_advanced_generation.py::TestAdvancedGeneration::test_thinking_mode -v

# 只运行P0优先级测试
pytest tests/test_b_advanced_generation.py -m p0 -v

# 指定模型运行
pytest tests/test_b_advanced_generation.py --model=qwen35 -v
```

## 测试用例说明

### test_thinking_mode
测试模型的思考模式功能。不依赖 config.yaml 配置，自动按多种策略顺序尝试开启思考：
`default` → `enable_thinking=true` → `chat_template_kwargs.thinking=true` →
`chat_template_kwargs.enable_thinking=true` → `thinking.type=enabled` →
`chat_template_kwargs.thinking=true + reasoning_effort=high`。

任一策略获取到思考内容即视为成功（硬断言）；所有策略均未获取到思考内容则断言失败。
正式回复通过 `_get_formal_content` 提取（剥离 reasoning 与 think 标签，content 为空时
回退到 content+reasoning），并验证 finish_reason 合法、答案为 56088。

思考格式由 `strip_thinking_content` 统一解析，兼容 reasoning_content 字段与 content 内嵌的
多种格式：`<think>...</think>` 完整标签、仅 `</think>` 结束标签（MiniMax M2 风格）、
`<|im_start|>assistant` 前缀、kimi-k3 的 `<|close|>think[<|sep|>]` 分隔。

### test_non_thinking_mode
测试思考模式关闭后不应有任何 thinking 内容泄漏到响应中。自动按多种策略顺序尝试关闭思考：
`no_params` → `enable_thinking=false` → `chat_template_kwargs.thinking=false` →
`chat_template_kwargs.enable_thinking=false` → `thinking.type=disabled`。

**不支持关闭思考的模型**：GLM-5.3 等 chat_template 不存在"关闭思考"分支的模型，所有关闭策略
均会检测到思考泄漏。此时用例改为 `record_warning("模型可能不支持关闭思考模式")` 并跳过断言，
**不视为失败**。模型仍须给出正确答案 56088 才能通过（通过 `_get_formal_content` 提取正式回复）。

### test_thinking_mode_switch
测试同一会话内切换 thinking 模式。第1轮开启思考（必须成功，硬断言），第2轮关闭思考。

**第2轮关闭失败时**：同 B2 处理方式，`record_warning` 而非 `assert` 失败。两轮均须给出正确答案
56088 且 finish_reason 合法。

### test_single_tool_call
测试模型能否正确识别需要调用的工具并传参。使用 `temperature=0.0` 保证确定性。

验证项：
- 模型返回 tool_calls 列表且包含工具调用 id
- 工具名为 `get_weather`，参数包含非空 `city`
- finish_reason 为 `tool_calls` 或 `length`
- 工具执行后的最终响应 finish_reason 合法且内容非空

### test_multiple_tool_call
测试模型在 5 个工具定义下能选择正确的工具（天气、股票、新闻、计算、翻译）。每个子用例使用
`temperature=0.0`，验证工具名、参数、id、finish_reason，以及工具执行后的最终响应。

### test_parallel_tool_calls
测试单次响应中并行调用多个工具的能力。使用 `temperature=0.0`。

**并行调用软告警**：若模型仅调用 1 个工具（未实现并行调用），`record_warning` 而非硬断言失败，
作为诊断工具评估并行调用支持情况。验证 finish_reason 合法、最终响应非空。

### test_multi_step_tool_chain
测试多步工具链式调用（get_weather → calculate → send_email）。使用 `temperature=0.0`。

验证项：
- 至少调用 2 个不同工具（硬断言）
- get_weather 必须被调用（硬断言）
- 每步 finish_reason 为 `tool_calls` 或 `length`
- 最终停止调用工具时 finish_reason 合法

**3步链不完整时**：若缺少 send_email，`record_warning` 而非硬断言失败。
**上下文隔离**：assistant 消息在 append 时剥离 `reasoning_content` 字段，避免将思考内容
回传给模型污染上下文。

### test_json_mode
测试 JSON 模式输出（`response_format={"type": "json_object"}`），验证返回的是合法的 JSON 对象。

正式回复通过 `_get_formal_content` 提取（避免 reasoning 中包含 JSON 干扰），content 为空时回退到
reasoning 提取 JSON。验证：
- JSON 为非空 dict
- 包含 name 相关字段（name/姓名/名字）和 age 相关字段（age/年龄/岁数）
- age 字段为数字且**排除 bool**（`True`/`False` 不是合法年龄）
- finish_reason 合法

### test_structured_output
测试结构化输出，使用 JSON Schema 约束输出格式。

**response_format 回退**：优先尝试 `json_schema` 格式（OpenAI 标准，
`{"type": "json_schema", "json_schema": {"name": "person_info", "schema": schema}}`），
不支持时回退到 `{"type": "json_object"}`。

正式回复通过 `_get_formal_content` 提取，content 提取失败时 `record_warning` 并回退到
reasoning 提取（亦告警）。验证：
- JSON 为 dict，包含 name/age 字段
- age 为数字且**排除 bool**，float 时须为整数（`25.0` 可接受，`25.5` 不接受）
- name 为非空字符串
- finish_reason 合法

### test_prefix_suffix_constraint
测试输出前缀/后缀约束功能，验证模型能遵循指定的格式模板。

- **Prefix 测试**：请求 `prefix="答案是："`，验证回答是否以"答案是："开头
- **Suffix 测试**：请求 `suffix="完毕。"`，验证回答是否以"完毕。"结尾

两个子测试均使用 `_get_formal_content` 提取正式回复（避免 reasoning 干扰），验证 finish_reason
合法。约束未遵循时 `record_warning`（软告警，模型可能不支持 prefix/suffix 参数）。

### test_reasoning_effort
测试 `reasoning_effort` 参数（GLM-5.3 等模型的核心思考控制参数）。

通过多种下发格式自动回退尝试 `low`/`high`/`max` 三档：
- `chat_template_kwargs: {reasoning_effort: "..."}`（vLLM/GLM5 标准）
- 顶层 `reasoning_effort: "..."`（OpenAI 兼容字段）

所有响应均验证 finish_reason 合法，正式回复通过 `_get_formal_content` 提取。

**不支持 reasoning_effort 的模型**：所有策略均请求异常时，
`record_warning("模型可能不支持 reasoning_effort 参数")` + `pytest.skip`，不视为失败。

**支持的模型**：对比 low vs high 的 `completion_tokens`，low 应 <= high；
反向或相等则 `record_warning`（软告警，可能为采样波动）。弱断言至少一档给出正确答案 56088。

## 工具安全说明
B5/B7 的 `calculate` 工具使用 `_safe_eval_math` 基于 AST 的安全数学表达式求值器，
仅允许数字与算术运算符（`+ - * / // % **` 及一元正负），拒绝函数调用、变量名等危险节点，
替代了原先的 `eval()` 调用，避免代码注入风险。

## 工具调用辅助方法

> 以下方法为本类特有，用于 B4-B7 工具调用测试的公共断言逻辑：

- `_assert_tool_finish_reason(response, label)`：断言工具调用步骤的 finish_reason 为
  `tool_calls` 或 `length`，统一 B4/B5/B6/B7 各步的 finish_reason 校验。
- `_parse_tool_args(tool_call, expected_keys, label)`：安全解析工具调用的 JSON 参数，
  解析失败时 `pytest.fail`，返回参数 dict 供后续字段断言。替代各处内联的 `json.loads`。

## 思考模式辅助方法

> 以下方法从 `BaseTest` 继承，B1/B2/B3 使用：

- `_check_has_thinking(response, test_logger)`：检测思考内容（reasoning 字段或 content 内思考标签）
- `_chat_with_thinking_fallback(api_client, messages, test_logger, max_tokens=None)`：6 种开启思考策略 + no_params_fallback
- `_chat_without_thinking_fallback(api_client, messages, test_logger, max_tokens=None)`：5 种关闭思考策略 + no_params_fallback

## 预期结果
- **P0 测试必须全部通过**（B1 思考模式、B4 单工具调用、B8 JSON Mode、B9 结构化输出）
- **P1 测试中核心功能为硬断言**：
  - B2 非思考模式：必须给出正确答案 56088（思考泄漏为软告警）
  - B3 思考模式切换：第1轮必须有思考内容、两轮均须给出正确答案
  - B5 多工具调用：工具选择、参数、finish_reason 均为硬断言
  - B7 多步链式：至少 2 个不同工具且 get_weather 被调用为硬断言
  - B11 reasoning_effort：响应非空、finish_reason 合法为硬断言
- **以下为诊断型软告警，不作为硬性失败条件**：
  - B2/B3 思考泄漏：部分模型（如 GLM-5.3）固有强制思考，无法通过参数关闭
  - B6 并行调用：模型可能仅调用 1 个工具，未实现并行调用
  - B9 JSON 提取失败：content 或 reasoning 中 JSON 提取失败时告警
  - B10 Prefix/Suffix 未遵循：模型可能不支持 prefix/suffix 参数
  - B11 reasoning_effort：所有策略均请求异常时 skip + 告警；completion_tokens 反向时告警；
    所有策略均未给出正确答案时告警
- 软告警信息会记录在测试报告中，用于评估模型对该特性的支持情况
