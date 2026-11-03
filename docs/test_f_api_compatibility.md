# F. API 兼容性测试

## 概述
验证API的OpenAI兼容性，包括接口格式、参数支持、响应格式等。

## 测试点列表

| ID  | 测试点 | 测试内容 | 验证要点 | 优先级 |
|-----|--------|---------|---------|--------|
| F1  | OpenAI Chat Completions | /v1/chat/completions 接口兼容 | 响应格式、字段完整性、finish_reason、usage | P0 |
| F2  | OpenAI Completions | /v1/completions 接口兼容 | 传统 completion 格式支持、finish_reason、usage | P1 |
| F3  | 模型列表 | /v1/models 返回可用模型 | 响应格式、当前模型在列表中、object字段 | P0 |
| F4  | Usage 统计 | 返回中 usage 字段准确 | prompt_tokens + completion_tokens 与 total_tokens 关系 | P0 |
| F5  | 错误码规范 | 401/400/404 错误码 | 符合 OpenAI 错误格式 | P1 |
| F6  | 客户端 SDK 兼容 | Python openai | 无需修改代码直接调用、finish_reason | P0 |
| F7  | OpenAI Responses API | /v1/responses 新一代接口兼容 | object=="response"、status、output/output_text 结构、input_tokens/output_tokens 字段名 | P0 |

> **注意**：response_format（json_object/json_schema）测试见 B8/B9，stream 参数测试见 A4，此处不重复测试。

## 运行方式

```bash
# 运行所有API兼容性测试
pytest tests/test_f_api_compatibility.py -v

# 运行特定测试
pytest tests/test_f_api_compatibility.py::TestAPICompatibility::test_chat_completions_api -v
```

## 测试用例说明

### F1: test_chat_completions_api
测试Chat Completions接口，验证：
- 响应顶层含 id/object/model/created 字段（OpenAI 规范）
- object 字段值为 "chat.completion"
- choices[0].message 含 role=assistant 和 content 字段
- finish_reason 合法（stop/eos/ended/length）
- usage 字段含 prompt_tokens > 0 和 completion_tokens > 0
- 使用 temperature=0.0 确保确定性输出

### F2: test_completions_api
测试传统Completions接口（非 chat 格式）：
- 验证 choices[0].text 非空
- 验证 finish_reason 合法
- 验证 usage 字段（若存在）
- 仅验证 /v1/completions 接口兼容性，max_tokens 超限行为由 D/E 测试套件覆盖
- 若 Completions API 不被支持，降级为软告警

### F3: test_models_list
测试模型列表接口，验证：
- 顶层 object == "list"
- data 为列表，每个元素含 id 和 object=="model"
- **当前配置的 model_name 必须在列表中**（关键验证项）
- 兼容简洁输出（sglang 等仅含 id/object/created/owned_by/context_window）
- 空列表降级为软告警

### F4: test_usage_statistics
测试usage统计的准确性，验证：
- prompt_tokens > 0
- completion_tokens > 0
- total_tokens >= prompt_tokens + completion_tokens
  （思考模型可能将 reasoning_tokens 计入 total 但不计入 completion，
  故使用 >= 而非 ==）
- total_tokens 缺失时记录软告警但不跳过核心验证
- 使用 temperature=0.0 确保确定性输出

### F5: test_error_codes
测试错误码规范，验证：
- 401 认证错误（无效 API key）
- 400 请求错误（空 content，被接受则验证响应合法）
- 404 接口不存在
- 错误关键词匹配缩窄，避免假阳性

### F6: test_client_sdk_compatibility
测试客户端 SDK 兼容性，验证：
- Python openai 库可以直接调用
- SDK 响应含 id/choices/content/role/finish_reason
- 思考模型 content 可能为空时兼容 reasoning
- ImportError（SDK 未安装）→ 软告警跳过
- SDK 调用失败（非 ImportError）→ 硬断言失败

### F7: test_responses_api
测试 OpenAI Responses API（/v1/responses）接口兼容性。

**背景**：/v1/responses 是 OpenAI 2025 年 3 月推出的新一代大模型响应生成接口，作为 Chat Completions 的超集（stateful 对话、内置工具、多模态输入、structured outputs），是构建 AI Agent 的核心 API 原语，已成为 2026 年 AI 开发生态的主流标准接口。

**请求构造**：
- `POST {base_url}/v1/responses`，经手工 payload 直发（与 K30 同模式，不经 wrapper 注入，不指定 temperature/top_p/seed）
- `input` 采用字符串最简形式（区别于 K30 的消息数组形式，互补覆盖两种规范形态）
- `max_output_tokens=2048`（Responses API 字段名，区别于 Chat Completions 的 max_tokens——本身即为断言点）

**断言**（端点已部署时全部硬断言）：
- 顶层 `object == "response"`、`id` 非空、`status == "completed"`
- `output` 为非空数组，含 `type=="message"` 项，其 `content` 含 `type=="output_text"` 项
- 提取文本非空
- `usage.input_tokens > 0`、`usage.output_tokens > 0`（Responses API 字段名，区别于 prompt_tokens/completion_tokens）
- `total_tokens` 若存在则 `>= input_tokens + output_tokens`（思考模型 reasoning_tokens 计入 total 但可能单列，同 F4 的 `>=` 口径）
- `id` 前缀 `resp_` 为实现细节，缺失仅记录不硬断言

**判定矩阵**：
| 场景 | 判定 |
|------|------|
| HTTP 200 且全部字段符合规范 | PASS |
| HTTP 404/405/501（端点未实现） | record_warning 软告警（接口未部署，报告可追溯） |
| 请求发送异常（连接拒绝/超时） | record_warning 软告警 |
| HTTP 200 但 object/status/output 结构不符 | FAIL（硬断言） |
| 其他非 200（400/500 等，端点已部署但出错） | FAIL（硬断言） |

**设计决策记录**：
- 端点未实现软告警而非 FAIL：与 F2（Completions API 不支持 → 软告警）框架哲学一致——"不支持的功能软告警，支持了就必须符合规范"；WARNING 在报告中可追溯，运维可据此推动部署升级
- `input` 用字符串形式：与 K30（消息数组 + input_text 类型）互补，一次请求覆盖另一种规范形态，不重复测试
- 非流式：K30 已覆盖流式 SSE 事件解析（output_text.delta/response.completed），F7 覆盖非流式 JSON 响应格式
- 与 K30 分工：K30 是客户报障复现（校验码原样输出、input_tokens 基准 ±3%、output 计数核验），F7 是接口兼容性基线（结构规范、字段名语义）
- P0 定位：2026 主流标准接口的兼容基线，已部署环境必须符合 OpenAI 规范
- 不进 smoke 集：新用例首跑观察期（同 K30 口径）

**后续扩展方向**（依赖服务端实现程度，vLLM 兼容层尚参差不齐，暂不纳入基线）：
- `previous_response_id` 服务端对话状态（stateful 多轮）
- 内置工具（web_search/file_search/code_interpreter）
- `reasoning` 参数（`{"reasoning": {"effort": ...}}`）与 `store`、`text` 格式化参数

## 辅助方法

> 以下方法均从 `BaseTest` 继承，各测试类（A/B/D/E/F）统一复用：

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
- /v1/responses 端点未实现（404/405/501）时软告警不阻塞，已部署环境则全部硬断言；消息数组形式与流式解析由 K30 覆盖
