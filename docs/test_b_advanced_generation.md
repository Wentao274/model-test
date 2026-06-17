# B. 高级生成功能测试

## 概述
验证模型的思考模式、工具调用、结构化输出等高级功能。

## 测试点列表

| ID  | 测试点              | 测试内容                                    | 优先级 |
|-----|-------------------|-----------------------------------------|-----|
| B1  | 思考模式（Thinking） | 开启thinking mode，验证返回思考链+最终答案        | P0  |
| B2  | 非思考模式（Instant） | 关闭thinking，验证无hidden thinking泄漏       | P1  |
| B3  | 思考模式切换         | 同一会话内thinking↔non-thinking切换          | P1  |
| B4  | 工具调用-单工具       | 定义单个function，验证模型正确调用并传参           | P0  |
| B5  | 工具调用-多工具       | 定义多个function，验证模型选择正确的工具           | P1  |
| B6  | 工具调用-并行调用      | 单次回复中并行调用多个工具                      | P2  |
| B7  | 工具调用-多步链式      | 工具结果作为下一步输入，验证3+步链式执行            | P1  |
| B8  | JSON Mode         | response_format=json_object，验证输出合法JSON  | P0  |
| B9  | 结构化输出           | JSON Schema约束输出格式，验证字段完整性          | P0  |
| B10 | Prefix/Suffix约束  | 指定输出前缀或格式模板，验证遵循度                 | P2  |

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

### test_thinking_mode_switch
测试同一会话内切换thinking模式。

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

## 注意事项
- 工具调用测试需要模型支持function calling功能
- 部分模型可能不支持思考模式切换
- B10 为新增测试点，属于 P2 优先级