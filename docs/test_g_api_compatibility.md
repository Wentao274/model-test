# G. API 兼容性测试

## 概述
验证API的OpenAI兼容性，包括接口格式、参数支持、响应格式等。

## 测试点列表

| ID  | 测试点 | 测试内容 | 验证要点 | 优先级 |
|-----|--------|---------|---------|--------|
| G1  | OpenAI Chat Completions | /v1/chat/completions 接口兼容 | 请求格式、返回格式完全兼容 | P0 |
| G2  | OpenAI Completions | /v1/completions 接口兼容 | 传统 completion 格式支持 | P1 |
| G3  | 模型列表 | /v1/models 返回可用模型 | 正确返回模型 ID 和元信息 | P1 |
| G4  | Usage 统计 | 返回中 usage 字段准确 | prompt_tokens + completion_tokens 准确 | P0 |
| G5  | 错误码规范 | 400/401/404/429/500 错误码 | 符合 OpenAI 错误格式 | P1 |
| G6  | 客户端 SDK 兼容 | Python openai / JS @openai/sdk | 无需修改代码直接调用 | P0 |
| G7  | 响应格式变体 | 响应格式变体 | 测试不同参数组合，temperature, max_tokens | P2 |
| G8  | Stream参数 | Stream参数 | 测试流式请求 | P2 |

## 运行方式

```bash
# 运行所有API兼容性测试
pytest tests/test_g_api_compatibility.py -v

# 运行特定测试
pytest tests/test_g_api_compatibility.py::TestAPICompatibility::test_chat_completions_api -v
```

## 测试用例说明

### G1: test_chat_completions_api
测试Chat Completions接口，验证：
- 响应格式正确
- message包含role和content字段
- usage统计准确
- finish_reason正确

### G2: test_completions_api
测试传统Completions接口（非流式）。

### G3: test_models_list
测试模型列表接口，验证返回格式和数据结构。

### G4: test_usage_statistics
测试usage统计的准确性，验证：
- prompt_tokens + completion_tokens = total_tokens
- token计数非负

### G5: test_error_codes
测试错误码规范，验证：
- 400 错误码格式
- 401 认证错误
- 404 接口不存在
- 429 限流错误
- 500 服务端错误
- 错误格式符合 OpenAI 规范

### G6: test_client_sdk_compatibility
测试客户端 SDK 兼容性，验证：
- Python openai 库可以直接调用
- 无需修改代码即可使用

### G7: test_response_format_variants
测试不同参数组合的响应格式。

### G8: test_stream_parameter
测试stream参数的正确性。

## 注意事项
- 需要模型支持OpenAI兼容接口
- 部分接口（如/v1/completions）可能不被所有模型支持