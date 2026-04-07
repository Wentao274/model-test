# A. 基础推理能力测试

## 概述
验证模型的基础文本生成和对话能力。

## 测试点列表

| ID  | 测试点           | 测试内容                            | 优先级 |
|-----|---------------|---------------------------------|-----|
| A1  | 单轮对话          | 发送单条prompt，验证正常生成               | P0  |
| A2  | 多轮对话          | 3-5轮对话，验证上下文保持和连贯性              | P0  |
| A3  | System Prompt | 设置系统角色，验证模型遵循程度                 | P0  |
| A4  | 流式输出          | stream=true，验证SSE逐token返回       | P0  |
| A5  | 非流式输出         | stream=false，验证完整返回             | P0  |
| A6  | Max Tokens限制  | 设置max_tokens=50/100/500，验证输出不超限 | P0  |
| A7  | 多语言能力         | 中/英/日/韩/法等多语言输入输出               | P1  |
| A8  | 特殊Token处理     | 含emoji、代码块、数学符号、HTML标签的输入       | P1  |

## 运行方式

```bash
# 运行所有基础推理测试
pytest tests/test_a_basic_reasoning.py -v

# 运行特定测试
pytest tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_conversation -v

# 只运行P0优先级测试
pytest tests/test_a_basic_reasoning.py -m p0 -v

# 指定模型运行
pytest tests/test_a_basic_reasoning.py --model=qwen35 -v
```

## 测试用例说明

### test_single_turn_conversation
验证模型能正确响应单条用户消息，返回有效的文本内容。

### test_multi_turn_conversation
验证模型能在多轮对话中保持上下文连贯性，能记住之前对话中提到的信息。

### test_system_prompt
验证模型能正确遵循system prompt设置的角色定位。

### test_streaming_output
验证流式输出（stream=true）能正确返回SSE格式的增量响应。

### test_non_streaming_output
验证非流式输出（stream=false）能一次性返回完整响应。

### test_max_tokens_limit
参数化测试不同max_tokens值（50, 100, 500），验证输出token数不超过限制。

### test_multilingual_capability
参数化测试多语言（中文、英文、日文、韩文、法文）输入输出能力。

### test_special_tokens_handling
测试特殊token（emoji、代码块、数学符号、HTML标签）的处理能力。

## 预期结果
- P0测试必须全部通过
- P1测试根据模型能力选择性通过