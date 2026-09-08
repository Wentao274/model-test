# D. 长上下文处理测试

## 概述
验证模型处理长文本输入输出的能力，包括上下文边界行为、NIAH（大海捞针）测试，以及超长上下文下的非流式/流式输出和思考模式验证。

## 测试点列表

| ID  | 测试点              | 测试内容                                    | 优先级 |
|-----|-------------------|-----------------------------------------|-----|
| D1  | 短上下文基线            | input ~1K tokens，验证正常推理                  | P0  |
| D2  | 中等上下文              | input 8K-16K tokens，验证质量不降               | P1  |
| D3  | 长上下文               | input 32K-64K tokens，验证召回和推理              | P1  |
| D4  | 超长上下文              | input 128K+ tokens，验证不OOM且可用              | P0  |
| D5  | 大海捞针（NIAH）        | 长文本中插入特定信息，验证召回率                        | P0  |
| D6  | 上下文边界行为            | 输入接近 max_model_len，验证流式响应                | P1  |
| D7  | 超出上下文截断            | 输入超过模型限制，验证截断/拒绝策略                      | P1  |
| D8  | 长输出生成              | 要求生成4K-8K tokens的长文本                     | P1  |
| D9  | 超长上下文（非流式）         | 验证超长上下文请求的非流式输出                         | P1  |
| D10 | 超长上下文（流式）          | 验证超长上下文请求的流式输出                          | P1  |
| D11 | 超长上下文（边界验证）        | 使用探进+二分法逼近模型最大上下文长度                      | P1  |
| D12 | 超长上下文（思考模式）        | 验证超长上下文下 reasoning_content 的可用性           | P0  |

## 运行方式

```bash
# 运行所有长上下文测试
pytest tests/test_d_long_context.py -v

# 排除慢速测试
pytest tests/test_d_long_context.py -m "not slow" -v

# 运行特定测试
pytest tests/test_d_long_context.py::TestLongContext::test_short_context_baseline -v

# 只运行P0优先级测试
pytest tests/test_d_long_context.py -m p0 -v
```

## 辅助方法与常量

> 本测试类从 `BaseTest` 继承以下共享常量与方法，各测试类（A/B/D/F/G）统一复用，
> 不再在子类中重复定义：

- `VALID_FINISH_REASONS = ("stop", "eos", "ended", "length")`：非流式合法 finish_reason
- `VALID_STREAM_FINISH_REASONS = ("stop", "eos", "ended", "length", None)`：流式最后 chunk 合法 finish_reason（中间 chunk 可为 None）
- `_get_formal_content(response, test_logger, context)`：提取正式回复内容（剥离 reasoning_content 字段与 think 标签），空时回退到 content + reasoning_content
- `_assert_finish_reason(response, allow_none=False)`：断言非流式响应 finish_reason 合法并返回其值
- `_assert_stream_finish_reason(result)`：断言流式响应最后 chunk 的 finish_reason 合法并返回其值
- `_check_has_thinking(response, test_logger)`：检查响应中是否包含思考内容（reasoning 字段或 content 中的思考标签），标签检测复用 `strip_thinking_content`（兼容 MiniMax M2 / kimi-k3 等格式），并检测 `finish_reason=length` 下的被截断思考
- `_chat_with_thinking_fallback(api_client, messages, test_logger, max_tokens=None)`：自动尝试 6 种思考参数格式 + no_params_fallback
- `_chat_without_thinking_fallback(api_client, messages, test_logger, max_tokens=None)`：自动尝试 5 种关闭思考参数格式 + no_params_fallback
- `_get_max_context_len(default=202752)`：获取模型最大上下文长度（兼容 vLLM/sglang/context_window）
- `_is_over_limit_error(e)`：判断异常是否表示上下文超限/连接中断/服务端边界失败

### 本类特有方法

### `_run_context_test(api_client, test_logger, label, context_tokens, prompt_suffix, min_prompt_tokens, max_tokens=2000)`
执行单个上下文长度测试的公共流程：生成指定 token 数的混合内容 → 发送请求 →
日志记录 → 断言响应成功/content 非空/finish_reason 合法 → 正式回复长度 > 50 →
prompt_tokens 超过阈值 → completion_tokens > 0。D1/D2/D3 共用此方法。

## 测试用例说明

### test_short_context_baseline（D1）
基线测试，验证短文本输入（~800 tokens）的正常处理。

验证项：
- 响应成功、content 非空
- finish_reason 合法（`_assert_finish_reason`）
- 正式回复通过 `_get_formal_content` 提取，长度 > 50 字符
- `prompt_tokens > 400`（短上下文 ~800 tokens 输入应产生足够的 prompt_tokens）
- `completion_tokens > 0`

### test_medium_context（D2）
测试中等长度上下文（~12K tokens）的处理能力。

验证项：
- 响应成功、content 非空、finish_reason 合法
- 正式回复通过 `_get_formal_content` 提取，长度 > 50 字符
- `prompt_tokens > 4000`（中等上下文应产生大量 prompt_tokens）

### test_long_context（D3）
测试长上下文（~50K tokens）的召回和推理能力。

验证项：
- 响应成功、content 非空、finish_reason 合法
- 正式回复通过 `_get_formal_content` 提取，长度 > 50 字符
- `prompt_tokens > 15000`（长上下文应产生大量 prompt_tokens）

### test_super_long_context（D4）
测试超长上下文（~128K tokens），验证模型不会 OOM 且可用。

验证项：
- 响应成功、content 非空、finish_reason 合法
- 正式回复通过 `_get_formal_content` 提取，长度 > 50 字符
- `prompt_tokens > 50000`（超长上下文应产生大量 prompt_tokens）
- `completion_tokens > 0`

**异常处理**：模型/proxy 不支持该上下文长度时，通过 `_is_over_limit_error` 统一判定后 skip。

### test_niah_needle_in_a_haystack（D5）
测试大海捞针（NIAH）能力，在长文本中插入特定信息并验证能否正确召回。
包含两个场景：
- 场景1（8K tokens）：基线大海捞针，必须通过
- 场景2（512K tokens）：超长上下文大海捞针，模型不支持时 record_warning 跳过

**Needle 设计**：使用高区分度组合 `项目Phoenix-37号的实验结果为8742`，
避免常见数字（如42）在 reasoning_content 中被讨论导致假阳性。

**关键修复**：通过 `_get_formal_content` 提取正式回复进行 needle 关键词匹配，
排除 reasoning_content。思考模型的 reasoning 中可能讨论 needle 关键词（如
"8742"、"Phoenix"），若用 `get_message_content`（含 reasoning）会假阳性通过。

验证项：
- 响应成功、finish_reason 合法
- `prompt_tokens > 0`
- 响应非乱码（garbled 检测）
- Core needle 关键词（8742、Phoenix）全部命中（硬断言）
- Secondary needle 关键词（特殊标记、37、实验结果）至少命中 1 个

### test_context_boundary_behavior（D6）
测试上下文边界行为，输入接近模型最大限制（max_len - 2000），验证流式响应。

验证项：
- 流式 chunks 数 > 0
- content 或 reasoning 非空
- 流式 finish_reason 合法（`_assert_stream_finish_reason`）

**异常处理**：模型/proxy 不支持该长度或超时时，通过 `_is_over_limit_error` +
timeout 关键词判定后 skip。

### test_context_truncation（D7）
测试超过上下文限制时的截断或拒绝策略。输入超过 max_len + 4000 tokens。

验证项（成功路径）：
- 流式 chunks 数 > 0
- content 或 reasoning 非空
- 流式 finish_reason 合法

**异常处理**：超限时通过 `_is_over_limit_error` 统一判定，为预期行为。

### test_long_output_generation（D8）
测试长文本生成能力，要求生成 4K-8K tokens 的长文章（不少于 4000 字）。

**思考模型回退**：流式 content 为空时（思考模型可能被 reasoning 消耗完 max_tokens），
回退到 content + reasoning，避免假阳性失败。

验证项：
- 流式 chunks 数 > 0
- 流式 finish_reason 合法
- 输出长度 >= 2000 字符（~4K tokens）

**异常处理**：超时时 skip。

### test_super_long_context_create（D9）
超长上下文非流式验证，发送 ~128K tokens 输入。

验证项：
- 响应成功、content 非空、finish_reason 合法
- 正式回复通过 `_get_formal_content` 提取
- `prompt_tokens > 50000`
- `completion_tokens > 0`

**异常处理**：通过 `_is_over_limit_error` + timeout 关键词统一判定后 skip。

### test_super_long_context_stream（D10）
超长上下文流式验证，发送 ~128K tokens 输入。

验证项：
- 流式 chunks 数 > 0
- content 或 reasoning 非空
- 流式 finish_reason 合法
- **缓冲流式检测**：通过 `detect_buffered_streaming` 检测 proxy 是否积攒后
  一次性返回（软告警，`log_buffered_streaming_warning`）

**异常处理**：通过 `_is_over_limit_error` + timeout 关键词统一判定后 skip。

### test_context_boundary_exact_limit（D11）
上下文边界精确验证，使用探进+二分法逼近模型最大上下文长度。

**算法**：
- 阶段1（探进法）：指数倍增建立 [low, high] 区间，从小基数开始
- 阶段2（二分逼近）：仅在区间内二分，收敛容差按 max_len 缩放
- 通过阈值 80%（`PASS_RATIO`），达到即提前结束
- 总体墙钟预算保护，超时以已得最大成功值判定

验证项（每次探测）：
- 流式 chunks 数 > 0、content 或 reasoning 非空
- 流式 finish_reason 合法（`_assert_stream_finish_reason`）

**最终断言**：`ratio >= PASS_RATIO`（实际成功长度 / 模型声明 max_len >= 80%）。

### test_reasoning_content_in_long_context（D12）
超长上下文下的思考内容验证。在 ~50K tokens 上下文下开启 thinking 模式。

**策略**：通过 `_chat_with_thinking_fallback` 自动尝试 6 种思考参数格式 +
no_params_fallback，与 test_b 策略对齐。

验证项：
- 响应成功、content 非空、finish_reason 合法
- 正式回复通过 `_get_formal_content` 提取
- `has_thinking` 为 True（必须获取到思考内容，硬断言）
- `prompt_tokens > 10000`
- `completion_tokens > 0`

## 注意事项
- 标记为 slow 的测试耗时较长
- 超长上下文测试可能因模型限制而跳过（通过 `_is_over_limit_error` 统一判定）
- D9-D12 原属 I 类测试，已合并至 D 类统一管理
- 思考模型可能将 max_tokens 全部消耗于 reasoning，导致 formal content 为空。
  所有 content 断言均通过 `_get_formal_content` 提取（回退到 content+reasoning），
  流式测试同理（D8/D10/D11）
- D5 NIAH 测试的 needle 使用高区分度关键词（Phoenix-37/8742），避免在
  reasoning_content 中被讨论导致假阳性

## 预期结果
- **P0 测试必须全部通过**（D1 短上下文基线、D4 超长上下文、D5 NIAH、D12 长上下文+思考）
- **P1 测试中核心功能为硬断言**：
  - D2/D3：prompt_tokens 下限、content 长度、finish_reason
  - D6/D7/D8/D10：流式 chunks 非空、finish_reason 合法
  - D9：prompt_tokens > 50000、finish_reason 合法
  - D11：实际成功率 >= 80%
- **以下为诊断型软告警，不作为硬性失败条件**：
  - D5 512K 场景：模型最大上下文 < 512K 或不支持 512K 时 record_warning 跳过
  - D10 缓冲流式：proxy 积攒后一次性返回时 `log_buffered_streaming_warning`
  - D11 探测失败：超限/响应为空时 record_warning，不视为失败
- 软告警信息会记录在测试报告中，用于评估模型对该特性的支持情况
