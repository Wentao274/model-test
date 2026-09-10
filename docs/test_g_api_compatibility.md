# G. API 兼容性测试

## 概述
验证API的OpenAI兼容性，包括接口格式、参数支持、响应格式等。

## 测试点列表

| ID  | 测试点 | 测试内容 | 验证要点 | 优先级 |
|-----|--------|---------|---------|--------|
| G1  | OpenAI Chat Completions | /v1/chat/completions 接口兼容 | 响应格式、字段完整性、finish_reason、usage | P0 |
| G2  | OpenAI Completions | /v1/completions 接口兼容 | 传统 completion 格式支持、finish_reason、max_tokens超限 | P1 |
| G3  | 模型列表 | /v1/models 返回可用模型 | 响应格式、当前模型在列表中、object字段 | P0 |
| G4  | Usage 统计 | 返回中 usage 字段准确 | prompt_tokens + completion_tokens 与 total_tokens 关系 | P0 |
| G5  | 错误码规范 | 401/400/404 错误码 | 符合 OpenAI 错误格式 | P1 |
| G6  | 客户端 SDK 兼容 | Python openai | 无需修改代码直接调用、finish_reason | P0 |

> **注意**：response_format（json_object/json_schema）测试见 B8/B9，stream 参数测试见 A4，此处不重复测试。

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
- 响应顶层含 id/object/model/created 字段（OpenAI 规范）
- object 字段值为 "chat.completion"
- choices[0].message 含 role=assistant 和 content 字段
- finish_reason 合法（stop/eos/ended/length）
- usage 字段含 prompt_tokens > 0 和 completion_tokens > 0
- 使用 temperature=0.0 确保确定性输出

### G2: test_completions_api
测试传统Completions接口（非 chat 格式）：
- 验证 choices[0].text 非空
- 验证 finish_reason 合法
- 验证 usage 字段（若存在）
- **max_tokens 超限子测试**：设置 max_tokens 超过模型最大上下文长度，验证服务端截断或返回超限错误
- 若 Completions API 不被支持，降级为软告警

### G3: test_models_list
测试模型列表接口，验证：
- 顶层 object == "list"
- data 为列表，每个元素含 id 和 object=="model"
- **当前配置的 model_name 必须在列表中**（关键验证项）
- 兼容简洁输出（sglang 等仅含 id/object/created/owned_by/context_window）
- 空列表降级为软告警

### G4: test_usage_statistics
测试usage统计的准确性，验证：
- prompt_tokens > 0
- completion_tokens > 0
- total_tokens >= prompt_tokens + completion_tokens
  （思考模型可能将 reasoning_tokens 计入 total 但不计入 completion，
  故使用 >= 而非 ==）
- total_tokens 缺失时记录软告警但不跳过核心验证
- 使用 temperature=0.0 确保确定性输出

### G5: test_error_codes
测试错误码规范，验证：
- 401 认证错误（无效 API key）
- 400 请求错误（空 content，被接受则验证响应合法）
- 404 接口不存在
- 错误关键词匹配缩窄，避免假阳性

### G6: test_client_sdk_compatibility
测试客户端 SDK 兼容性，验证：
- Python openai 库可以直接调用
- SDK 响应含 id/choices/content/role/finish_reason
- 思考模型 content 可能为空时兼容 reasoning
- ImportError（SDK 未安装）→ 软告警跳过
- SDK 调用失败（非 ImportError）→ 硬断言失败

## 辅助方法

> 以下方法均从 `BaseTest` 继承，各测试类（A/B/D/F/G）统一复用：

| 方法 | 说明 |
|------|------|
| `_get_formal_content` | 获取正式回复（排除 reasoning），空时回退到 content+reasoning |
| `_assert_finish_reason` | 断言非流式 finish_reason 合法 |
| `_is_over_limit_error` | 判断异常是否为超限/连接中断/服务端边界失败 |
| `_get_max_context_len` | 获取模型最大上下文长度（兼容 vLLM/sglang 等多种字段名），default=0 时若取不到则返回 0 |

## 注意事项
- 需要模型支持OpenAI兼容接口
- 部分接口（如/v1/completions）可能不被所有模型支持，会降级为软告警
- /v1/models 输出可能较简洁（如 sglang 仅含 context_window），属正常现象
- 思考模型的 total_tokens 可能包含 reasoning_tokens，故求和检查使用 >=
- response_format 测试见 B8/B9，stream 测试见 A4，不在此重复
