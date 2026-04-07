# G. API 兼容性测试

## 概述
验证API的OpenAI兼容性，包括接口格式、参数支持、响应格式等。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| H1 | Chat Completions | /v1/chat/completions接口 | P0 |
| H2 | Completions | /v1/completions接口 | P1 |
| H3 | 模型列表 | /v1/models接口 | P1 |
| H4 | Usage统计 | usage字段准确性 | P0 |

## 运行方式

```bash
# 运行所有API兼容性测试
pytest tests/test_g_api_compatibility.py -v

# 运行特定测试
pytest tests/test_g_api_compatibility.py::TestAPICompatibility::test_chat_completions_api -v
```

## 测试用例说明

### test_chat_completions_api
测试Chat Completions接口，验证：
- 响应格式正确
- message包含role和content字段
- usage统计准确
- finish_reason正确

### test_completions_api
测试传统Completions接口（非流式）。

### test_models_list
测试模型列表接口，验证返回格式和数据结构。

### test_usage_statistics
测试usage统计的准确性，验证：
- prompt_tokens + completion_tokens = total_tokens
- token计数非负

### test_response_format_variants
测试不同参数组合的响应格式。

### test_stream_parameter
测试stream参数的正确性。

## 注意事项
- 需要模型支持OpenAI兼容接口
- 部分接口（如/v1/completions）可能不被所有模型支持