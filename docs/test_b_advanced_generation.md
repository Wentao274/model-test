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
```

## 测试用例说明

### test_thinking_mode
测试模型的思考模式功能，开启后应返回reasoning_content。

### test_non_thinking_mode
测试思考模式关闭后，不应有任何thinking内容泄漏到响应中。

**不支持关闭思考的模型**：GLM-5.3 等 chat_template 不存在"关闭思考"分支的模型，
所有关闭策略均会检测到思考泄漏。此时用例改为 `record_warning("模型可能不支持关闭思考模式")`
并跳过断言，**不视为失败**。模型仍需给出正确答案 56088 才能通过。

### test_thinking_mode_switch
测试同一会话内切换thinking模式。第1轮开启思考（必须成功），第2轮关闭思考。

**第2轮关闭失败时**：同 B2 处理方式，`record_warning` 而非 `assert` 失败。

### test_single_tool_call
测试模型能否正确识别需要调用的工具并传参。

### test_multiple_tool_call
测试模型在多个工具定义下能选择正确的工具。

### test_parallel_tool_calls
测试单次响应中并行调用多个工具的能力。

### test_multi_step_tool_chain
测试多步工具链式调用，需要将工具返回结果作为下一步输入。

### test_json_mode
测试JSON模式输出，验证返回的是合法的JSON对象。

### test_structured_output
测试结构化输出，使用JSON Schema约束输出格式。

### test_prefix_suffix_constraint
测试输出前缀/后缀约束功能，验证模型能遵循指定的格式模板。

### test_reasoning_effort
测试 `reasoning_effort` 参数（GLM-5.3 等模型的核心思考控制参数）。

通过多种下发格式自动回退尝试 `low`/`high`/`max` 三档：
- `chat_template_kwargs: {reasoning_effort: "..."}`（vLLM/GLM5 标准）
- 顶层 `reasoning_effort: "..."`（OpenAI 兼容字段）

**不支持 reasoning_effort 的模型**：所有策略均请求异常时，
`record_warning("模型可能不支持 reasoning_effort 参数")` + `pytest.skip`，不视为失败。

**支持的模型**：对比 low vs high 的 `completion_tokens`，low 应 <= high；
反向或相等则 `record_warning`。弱断言至少一档给出正确答案 56088。

## 注意事项
- 工具调用测试需要模型支持function calling功能
- B2/B3：部分模型（如 GLM-5.3）固有强制思考，无法通过参数关闭，此时告警而非失败
- B11 为新增测试点，覆盖 reasoning_effort 参数，不支持的模型会 skip + 告警
- B10 为 P2 优先级