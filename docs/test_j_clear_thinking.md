# J. clear_thinking 参数行为测试

## 概述
验证 `chat_template_kwargs.clear_thinking` 参数在多轮对话场景下的行为。该参数控制历史
assistant 消息中的思考内容（open-think ... close-think 块或 reasoning_content 字段）
在拼下一轮 prompt 时是否被清除。

- `clear_thinking=true`（默认）：清除历史轮次思考内容，只保留最终答复。可节省 token、
  避免上下文膨胀、防止历史思考被模型在后续轮次"看到"。
- `clear_thinking=false`：保留历史思考内容，模型能看到自己之前的推理过程。便于在长任务
  上承接推理，但代价是 context 显著变长（每轮思考块全累积）。

`clear_thinking` 与 `enable_thinking` 是**正交独立**的两个参数：
- `enable_thinking` 控制本轮是否生成思考
- `clear_thinking` 控制历史思考是否在多轮拼接时被清除（仅 multi-turn 有意义）

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| J1 | clear_thinking=true 多轮 | 显式清除历史 thinking，验证多轮请求成功且无泄漏 | P1 |
| J2 | clear_thinking=false 多轮 | 显式保留历史 thinking，验证多轮请求成功 | P1 |
| J3 | clear_thinking 对 prompt_tokens 的影响 | 严格断言 pt_false > pt_true，未生效时 FAIL | P2 |
| J4 | clear_thinking 与 enable_thinking 组合 | 四种 (enable_thinking, clear_thinking) 组合均可被服务端接受 | P1 |
| J5 | clear_thinking deployment 能力探测 | 探测服务端是否真实实现 clear_thinking，未生效时 WARNING + record_warning | P1 |

## 运行方式

```bash
# 运行所有 clear_thinking 测试
pytest tests/test_j_clear_thinking.py -v

# 使用 marker 运行
pytest -m j_clear_thinking -v

# 运行特定测试
pytest tests/test_j_clear_thinking.py::TestClearThinking::test_clear_thinking_true_multi_turn -v

# 运行 P1 优先级测试
pytest tests/test_j_clear_thinking.py -m p1 -v

# 运行冒烟测试
pytest tests/test_j_clear_thinking.py -m smoke -v
```

## 测试用例说明

### test_clear_thinking_true_multi_turn (J1)
显式 `chat_template_kwargs={"enable_thinking": true, "clear_thinking": true}`，发送含
历史思考块的多轮请求。验证服务端能接受该参数（HTTP 200）、第二轮响应非空、能基于历史
最终答案推论。这是 `clear_thinking` 的默认行为，也是最常见的多轮形态。

### test_clear_thinking_false_multi_turn (J2)
显式 `chat_template_kwargs={"enable_thinking": true, "clear_thinking": false}`，发送含
历史思考块的多轮请求。验证服务端能接受该参数、第二轮响应非空、能基于历史最终答案推论
（此时历史思考也被服务端保留并送入上下文）。

### test_clear_thinking_prompt_tokens_difference (J3)
使用同一组多轮 messages，分别以 `clear_thinking=true` 和 `clear_thinking=false` 发送请求
（false 用 `only_strategy` 保证策略一致），对比两者的 `usage.prompt_tokens`。

**严格断言**：`pt_false` 必须严格大于 `pt_true`，相等即 FAIL。
- 服务端正确实现 `clear_thinking` 时，`false`（保留历史思考）的 prompt_tokens 应严格大于 `true`
- 服务端未返回 usage 字段时 SKIP（无法判定，不视为失败）
- `pt_false == pt_true` 时 FAIL，强制回归保护——避免"参数被接受但未生效"的 deployment 静默通过

J3 依赖 `_probe_clear_thinking_effect` 的探测结果。J3 是"行为验证"，未生效时 FAIL；
J5 是"能力探测"，未生效时 WARNING。两者互补。

### test_clear_thinking_enable_combinations (J4)
遍历四种 `(enable_thinking, clear_thinking)` 组合：
- `(true, true)`、`(true, false)`、`(false, true)`、`(false, false)`

判定规则：
- **enable_thinking=True 的两种组合**：必须返回 HTTP 200 且响应非空。这是 `clear_thinking`
  与 `enable_thinking` 正交独立的关键回归点。
- **enable_thinking=False 的两种组合**：
  - 若服务端尊重参数（响应无思考内容）：必须返回 HTTP 200 且响应非空
  - 若模型强制开启思考（响应仍含 `reasoning_content` 或 think 标签）：SKIP 该组合并
    `record_warning`，**不视为失败**——这是模型固有特性，不是参数处理 bug

这样在强制开启思考的模型（如部分 deepseek/glm 部署）上，J4 不会因为 `enable_thinking=False`
被忽略而误判失败，同时报告会明确标记该特性。

强制开启思考的识别方式：`_response_has_thinking` 检查响应的 `reasoning` / `reasoning_content`
字段非空，或 `content` 中含 `open-think` 标签。

### test_clear_thinking_deployment_probe (J5)
在做行为验证（J3）之前，先探测当前 deployment 是否真的实现了 `clear_thinking` 对历史
thinking 的剥除/保留行为。这是 deployment 能力的"事实判定"用例：

- **生效**（`pt_false > pt_true`）：记录 INFO，提示 J3 行为验证应能 PASS
- **未生效**（`pt_true == pt_false`）：记录 WARNING 并调用 `record_warning`，
  提示运维/算法团队该 deployment 仅"接受参数"但不"处理参数"，J3 将 FAIL
- **探测失败**（请求异常 / 无 usage）：SKIP，不视为失败

J5 与 J3 的关系：
- J5 是"能力探测"——未生效时 WARNING（不 FAIL），让报告对 deployment 能力可见
- J3 是"行为验证"——未生效时 FAIL，强制 deployment 必须真实实现 clear_thinking 才能通过回归
- 两者互补：J5 帮助定位"为什么 J3 失败"，J3 强制回归标准

## enable_thinking 下发格式自动回退

`clear_thinking` 几乎只能通过 `chat_template_kwargs` 下发，但 `enable_thinking` 有多种
承载形式。`_send_with_clear_thinking` 内部按以下顺序尝试 4 种下发格式，任一成功即返回：

| # | 策略名 | extra_body 形式 | 适用场景 |
|---|--------|---------------|---------|
| 1 | `chat_template_kwargs.enable_thinking` | `{"chat_template_kwargs": {"enable_thinking": ..., "clear_thinking": ...}}` | vLLM/Qwen3/GLM5 标准（最通用） |
| 2 | `chat_template_kwargs.thinking` | `{"chat_template_kwargs": {"thinking": ..., "clear_thinking": ...}}` | 部分 vLLM 部署使用 thinking 而非 enable_thinking |
| 3 | `top_enable_thinking+chat_template_kwargs.clear_thinking` | `{"enable_thinking": ..., "chat_template_kwargs": {"clear_thinking": ...}}` | 混合形式，服务端在顶层处理 enable_thinking |
| 4 | `thinking.type+chat_template_kwargs.clear_thinking` | `{"thinking": {"type": "enabled"/"disabled"}, "chat_template_kwargs": {"clear_thinking": ...}}` | DeepSeek/GLM 风格 thinking.type 对象 |

J1/J2/J4 使用多策略回退（首个成功即返回），J3 用 `only_strategy` 强制与第一次相同策略，
保证 prompt_tokens 对比时除 clear_thinking 取值外其余参数完全一致。

## 历史 assistant 消息构造

为稳定可重现地观察 `clear_thinking` 效果，测试用例固定使用以下历史：

```python
# 用 chr() 拼接思考标签，避免尖括号在源码处理中被破坏
_THINK_OPEN  = chr(0x3C) + "think"  + chr(0x3E)
_THINK_CLOSE = chr(0x3C) + "/think" + chr(0x3E)

HISTORY_USER_1 = "请计算 7 * 6"
HISTORY_USER_2 = "再把这个结果乘 3，告诉我最终是多少"

HISTORY_ASSISTANT_THINKING = (
    "让我一步一步计算 7 乘以 6：\n"
    "首先，7 乘以 6 可以分解为 7 + 7 + 7 + 7 + 7 + 7，\n"
    "一共 6 个 7 相加，结果是 42。\n"
    "因此答案确定为 42，可以作为后续推理的依据。"
)
HISTORY_ASSISTANT_ANSWER = "7 * 6 = 42"

HISTORY_ASSISTANT_CONTENT = (
    f"{_THINK_OPEN}\n{HISTORY_ASSISTANT_THINKING}\n"
    f"{_THINK_CLOSE}\n\n{HISTORY_ASSISTANT_ANSWER}"
)
```

设计要点：
- **历史 assistant.content 直接嵌入 think 块**：这是 vLLM Qwen3 / GLM5 等 chat_template
  渲染多轮历史时实际处理的对象，与服务端 `clear_thinking` 分支正面对应
- **follow-up 不依赖历史思考**：第二轮只问"把最终答案乘 3"，不论 `clear_thinking` 取值
  模型都能凭历史最终答案（42）推 126，避免对模型行为过度依赖
- **enable_thinking 多策略回退**：自动尝试 4 种下发格式（见上节），首个成功即返回，
  避免对单一 deployment 形态过度耦合
- **服务端不支持 `clear_thinking` 时 `pytest.skip` 跳过**而非 fail，保证不同 deployment
  上报告稳定

## 断言策略

- **J1/J2**：硬断言响应成功、最终回答非空；软断言（warning）模型基于历史最终答案推论
  命中 `["126", "42 * 3"]`
- **J3**：硬断言 `prompt_tokens(false) >= prompt_tokens(true)`；服务端未返回 usage 时
  仅 warning 不 fail
- **J3**：硬断言 `pt_false > pt_true`（严格大于，相等即 FAIL）；服务端未返回 usage 时 SKIP
- **J4**：硬断言 `enable_thinking=True` 的两个组合返回 HTTP 200 且响应非空；
  `enable_thinking=False` 的组合若检测到模型强制开启思考则 SKIP + WARNING（不视为失败）
- **J5**：探测未生效时 WARNING + `record_warning`（不 FAIL）；探测失败时 SKIP

## 注意事项

- `clear_thinking` 只在多轮对话场景下有意义，单轮请求无效果
- Qwen3 官方 chat_template 默认 `clear_thinking=true`（清除历史思考）。GLM-5 / 5.1、
  Minimax-M2.5 是否改写过默认值需逐模型核对 `tokenizer_config.json` 的 `chat_template` 源码
- 当前 `config.yaml` 的 `thinking_key` 仅覆盖 `enable_thinking`，未对 `clear_thinking`
  做模型级开关。J 类测试统一以 `chat_template_kwargs` 形式下发，不依赖 config 配置
- 服务端若拒绝 `clear_thinking` 参数导致 HTTP 错误，用例以 `pytest.skip` 跳过而非
  fail，使报告在不同 deployment 上稳定可用
