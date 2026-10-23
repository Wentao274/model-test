# K. 客户问题复现测试

## 概述
收录来自客户反馈的真实问题，将客户提供的原始请求（通常是 curl 命令）还原为标准
模型请求进行复现与回归验证。

设计原则：
- **原样复现**：system/user 提示词、tools 定义、tool_choice、thinking、stream、
  stream_options、temperature、max_tokens 等全部字段与客户原始请求逐字段一致，
  不做任何"规范化"改写——保证复现的是客户遇到的确切请求形态。
- **全部 P0**：客户报障场景纳入每次回归的必验范围，任何失败都应阻断发布。
- **修复后转为回归**：问题修复后用例保留，作为该场景的长期回归用例。
- **参数豁免**：K 类用例加入 `RAW_SAMPLING_PARAM_TESTS` 豁免名单，全局
  `--sampling-params` 覆盖对其不生效，始终按客户原始采样参数执行。
- **环境注入（不硬编码）**：客户 curl 中的 **URL、API key、模型名不写入测试
  代码**——与其他测试类一致，由 Jenkinsfile 构建参数（`BASE_URL` / `API_KEY` /
  `MODEL`）透传至 pytest 的 `--base-url` / `--api-key` / `--model-name`，经
  conftest 的 `api_client` fixture 注入。curl 中的其余请求字段（messages、
  tools、采样参数、`user` 标识等）按原样保留在用例常量中。

新增客户问题的流程：
1. 在 `tests/test_k_customer_issue.py` 对应测试方法**内部**以 `K{n}_` 前缀
   定义该问题的常量（提示词、tools、tool_choice 等），内容与客户原始请求
   逐字段一致——每个用例自包含，常量与内部辅助函数均定义在用例方法内，
   不放模块顶部；
2. 新增测试方法 `test_xxx`，按客户原始参数原样调用
   `api_client.chat_completion` / `chat_completion_stream`
   （特殊协议/参数形态按 K3/K4 先例手工构造 payload 直发）；
3. 在文件头 docstring 与 `base/test_definitions.py` 的 `k_customer_issue` 类别中
   登记测试点（编号 K{n}，优先级 P0，func_name 与测试方法名一致）。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| K1 | Pydantic $defs/$ref Schema 工具调用 | 客户问题复现：thinking+stream+强制 tool_choice+Pydantic v2 Schema（$defs/$ref）请求报【$$不兼容】，验证服务端可正常处理并返回合法工具调用 | P0 |
| K2 | 同一请求循环执行5次返回信息异常 | 客户问题复现：同一 curl（logprobs+top_logprobs+n+thinking+stream+X-Cache-Buster）循环执行 5 次左右出现返回信息异常，原样复现并连续执行 5 次，验证每次响应与内容均正常 | P0 |
| K3 | Anthropic 协议 prompt cache 未创建 | 客户问题复现：Anthropic 协议（/anthropic/v1/messages）请求的 cache_creation_tokens 一直为 0（未创建缓存），构造带 cache_control 断点的唯一长前缀连发两次，验证第 1 次创建、第 2 次命中 | P0 |
| K4 | frequency_penalty=-2 不传 max_tokens 无返回 | 客户问题复现：fp=-2（合法极值）且不传 max_tokens 时退化重复导致无界生成、请求一直无返回；修复契约 fp<0 按 0 处理，输入保持 -2 连发 3 次（消息各异）、断言每次 fp=0 预期（预算内返回+自然结束+内容非空） | P0 |
| K5 | thinking.type=disabled 后思考未关闭 | 客户问题复现：disabled 后 reasoning_tokens 仍>0、reasoning_content 照常输出，关思考相关功能全部失效；官方端点实测 disabled 应完全关闭思考（rt 为空、无思考内容、正文正常），输入保持 disabled+temperature=0.6 连发 3 次（消息各异），断言每次均符合官方实测预期 | P0 |
| K6 | 关思考温度档未联动校验 | 官方契约（kimi-k3）：thinking 与 temperature 档位联动——disabled 仅允许 0.6（给 1 或 0 报 400 "only 0.6 is allowed for this model in non-thinking mode"）、enabled 仅允许 1（给 0.6 或 0 报 400 "only 1 is allowed for this model in thinking mode"）。对 6 个组合各发一次请求，断言合法组合 200+正文非空、非法组合 400+错误信息含官方文案 | P0 |
| K7 | 思考强度档位思考长度倒挂（官方 reasoning_effort） | 官方契约（kimi-k3 文档）：思考强度为顶层 reasoning_effort（K2.x thinking 配置已废弃）。只按官方格式传参（无回退）：low→high→max 比对后 max→high→low 再比对（正逆两轮，medium 不参与对比）；最后 medium 顶层 200 放行、嵌套 thinking.effort=medium 预期 400；倒挂/持平不判失败，仅告警 | P0 |

## 运行方式

```bash
# 运行所有客户问题复现测试
pytest tests/test_k_customer_issue.py -v

# 使用 marker 运行
pytest -m k_customer_issue -v

# 运行特定测试
pytest tests/test_k_customer_issue.py::TestCustomerIssue::test_pydantic_schema_tool_call_stream -v

# 运行 P0 优先级测试
pytest tests/test_k_customer_issue.py -m p0 -v
```

## 测试用例说明

### test_pydantic_schema_tool_call_stream (K1)

**客户问题**：glm-5.3 通过 `/v1/chat/completions` 发起流式请求报错【$$不兼容】。

**请求特征**（全部来自客户原始 curl）：
- `thinking={"type": "enabled"}`：开启思考模式
- `stream=true` + `stream_options={"include_usage": true}`：流式并要求 usage
- `tool_choice` 强制指定 `submit_d2_product` 函数
- `tools` 使用 Pydantic v2 自动生成的 JSON Schema，`parameters` 中含
  `$defs` 定义与 `$ref` 引用（【$$不兼容】问题的核心对象）
- `temperature=0.1`、`max_tokens=4096`
- 通话内容分析场景：从坐席-客户对话中提取产品与工作分类信息

**验证链**（对应客户问题修复后的预期行为）：
1. 服务端正常处理该请求并返回流式 chunks（原始报错【$$不兼容】时，
   HTTP 非 200 直接抛异常，用例失败）
2. `finish_reason` 合法（工具调用场景应为 `tool_calls`；思考模型 reasoning
   耗尽 max_tokens 时可能为 `length`，也接受 `stop`/`eos`/`ended`）
3. 强制 `tool_choice` 下必须返回指定的 `submit_d2_product` 工具调用（含 id）
4. 流式增量 `tool_calls` 片段按 index 聚合后，`function.arguments` 为合法 JSON
5. 工具参数满足 schema 必填项：`core_work_type` 非空字符串
6. `stream_options.include_usage` 的 usage 返回（软校验：缺失仅告警，
   部分部署不实现该参数）

**实现要点**：
- `collect_stream_tool_calls`（用例内嵌套函数）：OpenAI 流式协议中
  tool_calls 以增量片段下发（按 index 分片，`function.arguments` 逐段
  追加），需按 index 聚合成完整调用后才能做 JSON 合法性与必填项校验
- 客户原始 `temperature=0.1` 通过 `RAW_SAMPLING_PARAM_TESTS` 豁免保留，
  不被全局采样参数覆盖

### test_repeated_request_stability (K2)

**客户问题**：同一 curl 命令循环执行 5 次左右出现返回信息异常。

**请求特征**（全部来自客户原始 curl）：
- `thinking={"type": "enabled"}`：开启思考模式
- `stream=true` + `stream_options={"include_usage": true}`：流式并要求 usage
- `logprobs=true` + `top_logprobs=4`：返回 token 对数概率
- `n=1`、`frequency_penalty=0`、`presence_penalty=0`、`top_p=0.95`、`temperature=1`
- `user`：终端用户标识（32 位以上哈希串）
- `X-Cache-Buster` 请求头：`$(date +%s)` 防缓存，每次执行生成新值——
  用例在每次迭代前更新 `api_client.session.headers["X-Cache-Buster"]`
  （追加迭代序号保证快速执行间取值也唯一）
- system prompt 要求每次回答以"很高兴为您服务"开头

**断言策略**（按客户要求：五次响应和内容都正常即 PASS）：
每次迭代断言三项——
1. 流式 chunks 非空（HTTP 非 200 时 `chat_completion_stream` 直接抛异常）
2. `finish_reason` 合法（`stop`/`tool_calls`/`eos`/`ended`/`length`）
3. 正式回答内容非空

5 次全部正常才判定通过；任一次异常即失败，并报告**第几次**及异常详情
（客户反馈为"5 次左右"出现异常，定位到具体迭代次数有助于问题复现）。

**软观察**（记 warning 不判失败）：
- 回答未以"很高兴为您服务"开头（system prompt 要求，偏离供问题定位）
- `stream_options.include_usage` 未返回 usage（部分部署不实现）

**实现要点**：
- 相邻请求间隔 3s（`K2_REQUEST_INTERVAL_SECONDS`，末次后不等待），
  模拟客户循环执行 curl 的节奏，用例总时长增加约 12s
- 客户原始 `temperature=1` 等采样参数通过 `RAW_SAMPLING_PARAM_TESTS`
  豁免保留，不被全局采样参数覆盖

**关于 `user` 字段**（`"user": "a74685ef..."`）：
OpenAI Chat Completions 协议的标准可选字段——**终端用户唯一标识符**，供
服务端做监控、滥用检测与计量归属；**不参与模型生成，对输出内容无影响**。
客户传的是哈希串（不传明文身份是官方推荐做法）。

硬编码风险评估：
- vLLM/SGLang 等 OpenAI 兼容实现对该字段**接受但通常忽略**（或仅记日志），
  传任意字符串、甚至不传，请求都不会因此失败
- 该值不是凭证（非 API key），无泄露风险
- 极少数网关若对 `user` 做白名单/绑定校验，保留客户原值反而能如实暴露该
  部署行为——符合 K 类"原样复现"定位

结论：用例保留客户原始值（`K2_USER_ID`）是安全且忠实的做法。

### test_anthropic_prompt_cache_creation (K3)

**客户问题**：通过 Anthropic 协议发送带 prompt cache 的流式请求，服务端日志
`anthropic cache stats` 中 `cache_creation_tokens` 一直为 0（同时
`cache_read_tokens` 有值），说明 `cache_control` 断点未被落实、未创建缓存。

**请求构造**（客户提供的证据为服务端日志而非 curl，请求为按协议构造的
代表性复现）：
- 端点：`{base_url}/anthropic/v1/messages`（与客户网关布局一致，`base_url`
  由 Jenkins 参数透传，不硬编码）
- 头：`x-api-key`（透传 API_KEY）+ `anthropic-version: 2023-06-01`
  （长期 GA 版本，第三方兼容网关的事实标准；官方 SDK v2.1.0+ 虽已升级到
  `2026-10-21`，但对兼容网关而言旧版本兼容面最广且不会失效。prompt caching
  在 `2023-06-01` 上即为 GA，无需 `anthropic-beta` 头）
- `system` 为块列表，末块标记 `cache_control: {"type": "ephemeral"}`；
  前缀填充至约 19 万字符（约 11 万+ tokens）——**对齐客户场景规模**
  （客户 prompt_tokens=111283；若缺陷为规模相关，过短前缀无法复现），
  同时远超协议最小可缓存长度 1024 tokens
- 前缀最前方带**每次运行唯一的批次号**（时间戳+随机串），保证第 1 次请求
  不会命中历史运行遗留的缓存，避免跨运行误判
- `stream=true`（与客户场景一致），`max_tokens=512`（缓存断言只关心
  input 侧 usage）
- 超时保护：超长前缀 prefill 耗时显著，请求超时下限 1200s（参考 D 类
  用例模式，配置已大于该值时为 no-op）

**验证逻辑（两次请求法）**：
| 请求 | 前缀 | 断言 |
|------|------|------|
| 第 1 次 | 唯一新前缀（带 cache_control） | `cache_creation_input_tokens > 0`（创建缓存） |
| 第 2 次 | 相同前缀 | `cache_read_input_tokens > 0`（命中缓存） |

**字段名兼容**：Anthropic 协议 API 返回 `cache_creation_input_tokens` /
`cache_read_input_tokens`，客户日志的网关内部名为 `cache_creation_tokens` /
`cache_read_tokens`——断言两种拼写均兼容。

**判定**：
- 两个断言全过 → PASS（缓存创建与命中均正常，问题已修复）
- 第 1 次 `creation` 为 0 → FAIL（客户症状：cache_creation 一直为 0，
  未创建缓存；若部署仅实现隐式前缀缓存而无 cache_control 落实，也会在此暴露）
- 第 1 次创建成功但第 2 次 `read` 为 0 → FAIL（缓存创建后不可命中）

**注意事项**：
- 该用例依赖同一 `base_url` 下同时存在 OpenAI（`/v1/chat/completions`，
  conftest 连通性检查用）与 Anthropic（`/anthropic/v1/messages`）两套路径
  ——与客户网关部署布局一致
- `input_tokens < 1024` 时告警（前缀过短时 creation 为 0 属协议预期，
  需加大 `K3_PREFIX_TARGET_CHARS`）；`< 100000` 时提示低于客户场景规模
- 前缀规模与实际 tokens 的换算依赖部署的 tokenizer（中文约 1.3~1.7
  字符/token），实际值以响应的 `input_tokens` 为准

### test_negative_frequency_penalty_treated_as_zero (K4)

**客户问题**：`frequency_penalty=-2` 且不传 `max_tokens` 时，请求一直没有返回。

**机理**：`frequency_penalty` 取值范围 [-2, 2]（OpenAI 规范），-2 为合法极值。
fp<0 按出现次数**奖励**已出现 token，形成无饱和正反馈：循环 token 的 logit
随出现次数持续增长、压制 EOS，自然终止失效；不传 `max_tokens` 时输出上限
= 剩余上下文（可能十余万 tokens），生成耗时远超网关/客户端超时，观感即
"一直没有返回"（引擎层最终会以 finish_reason=length 停止，但远超任何合理
超时）。附带可用性风险：此类请求长时间占用调度槽与 KV cache。

**平台修复契约**：`frequency_penalty<0` 时按 0 处理（防御性钳制）。
因此用例设计为：**输入保持客户原值 -2、不传 max_tokens，断言按 fp=0 的
预期结果**。

**请求构造**：
- 仅 `model` / `messages` / `frequency_penalty=-2` / `stream=false`，不传
  `max_tokens`（客户原始请求形态）
- **连发 3 次，消息各异**（`K4_USER_PROMPTS` 三条不同开放问题）——仅一次
  调用可能无法严谨验证：钳制若未生效，单次请求也可能侥幸自然结束；
  不同消息降低偶然性，未钳制的退化重复更难在不同 prompt 下全部侥幸通过
- `chat_completion` 封装会强制注入默认 `max_tokens=2048` 与 `temperature`，
  破坏"不传 max_tokens"的前提——故按 K3 先例手工构造 payload 直发
- 客户原始 prompt 未提供，选用常规开放问题，验证正常生成即可

**断言**（fp=0 预期结果，每次请求独立断言）：
1. 响应时间预算内返回——专用预算客户端（F8 先例：`timeout=120` +
   `retry_times=0`，最坏耗时 = 单次预算而非预算×(重试+1)），超预算
   无响应即客户问题复现（FAIL）
2. `finish_reason` 为自然结束（`stop`/`eos`/`ended`）——未传 max_tokens
   时 `length` 表示生成跑满输出上限（=剩余上下文），即退化重复未被
   钳制的特征
3. 回答内容非空

3 次全部正常结束才判定通过；任一次异常即失败，并报告**第几次**及该次
消息（用例内嵌套函数 `run_request` 承载单次请求逻辑，失败归因到具体
迭代）。相邻请求
间隔 3s（`K4_REQUEST_INTERVAL_SECONDS`，末次后不等待），总时长额外
约 6s。

**软观察**：单次耗时超过预算一半（60s）时告警——修复后正常应在数秒内返回。

**设计决策记录**：
- 连发 3 次（消息各异）：单次调用可能无法严谨验证问题，3 次全部正常
  结束才 PASS，任一次失败报告第几次
- 不进 smoke 集：未修复时最坏耗时约 3×`K4_RESPONSE_BUDGET_SECONDS`
  （360s），避免拖慢冒烟套件（K1-K3 均 smoke，K4 为首个非 smoke 的
  K 类用例）
- 对照场景（fp=0 不传 max_tokens）按决策跳过：修复契约明确后无需对照隔离，
  单一场景即可判定
- 若平台未来将契约改为 400 拒绝（而非钳制），本用例会在"请求失败
  HTTP 400"处 FAIL，需同步调整

**注意事项**：
- 修复方式为静默钳制（非 OpenAI 官方语义——官方允许 -2 并会放大重复），
  本用例编码的是平台契约；G 类 API 兼容性如需覆盖该语义差异另行评估
- fp=-2 的退化重复具有模型依赖性（若 EOS 始终占优则不退化）——但 K 类
  对同一部署回归，客户已在其模型上复现，风险可接受

### test_thinking_disabled_suppresses_reasoning (K5)

**客户问题**：`thinking.type=disabled` 后 `reasoning_tokens` 仍=100/75、
`reasoning_content` 照常输出——客户无法关闭思考，关思考相关功能（低延迟
模式、关思考温度档）全部失效。

**官方契约（以端点实测为准）**：官方 FAQ 与端点实际行为不符，以实测为准
——`thinking.type=disabled` 后思考完全关闭：
- `reasoning_tokens` 为空（0/缺失）
- 无 `reasoning_content`（思考内容不输出）
- 正文正常返回

客户网关对 `disabled` 不响应（rt 仍>0），与官方实测不一致。用例即按
官方实测预期断言。

**请求构造**：
- 仅 `model` / `messages` / `thinking={"type": "disabled"}` /
  `temperature=0.6`（官方关思考档唯一合法温度，契约见 K6——disabled 下
  给 1 或 0 会被 400 拒绝）/ `stream=false`，不传 `max_tokens`（手工构造
  payload 直发，K3/K4 先例，保持客户原始参数面）
- 连发 3 次（消息各异）+ 相邻间隔 3s（K4 模式，末次后不等待），
  任一次不符合即失败并报告**第几次**及该次消息
- 客户原始 prompt 未提供，选用常规开放问题

**断言**（官方实测预期，每次请求独立断言）：
1. 无思考内容——`reasoning_content` / `reasoning` 字段均为空
2. `reasoning_tokens` 为空（0/缺失）——兼容 `usage.reasoning_tokens`
   （Kimi/Zhipu 风格）与 `usage.completion_tokens_details.reasoning_tokens`
   （OpenAI 风格）两种拼写
3. 正文非空（官方实测正文正常返回）
4. `finish_reason` 自然结束（`stop`/`eos`/`ended`，未传 max_tokens）

**软观察**：响应未携带 usage 时告警（无法观测 reasoning_tokens，缺失视为
"为空"——与官方实测"rt 为空"一致）。

**实现要点**：
- 与 K1 的 `thinking={"type": "enabled"}` 为同一参数面（客户网关的
  thinking 对象）；与本框架 B2 类的 `enable_thinking` /
  `chat_template_kwargs` 参数面不同——B2 在后端直连部署上通过不代表网关
  此路径正确，故需独立复现
- 进 smoke 集：单次数秒内返回（无 K4 的长预算风险），与 K1-K3 一致

**注意事项**：
- 修复方向应为网关将 `thinking.type=disabled` 落实到后端思考开关；
  翻译层只实现 enabled 分支的不对称实现是常见根因（与 K1 的翻译层
  遗漏可能同源）
- 若后端仅支持其他关闭思考的参数面（如 `enable_thinking=false`），网关
  应做翻译；客户按 thinking 对象关闭的用法不应失效

### test_thinking_temperature_tier (K6)

**背景**：客户问题中"关思考相关功能（低延迟模式、**关思考温度档**）全部
失效"——K5 验证关思考本身，本用例验证温度档联动校验。

**官方契约**（kimi-k3 官方说明，thinking 模式 × temperature 档位联动）：

| thinking | temperature | 官方行为 |
|---|---|---|
| disabled | 0.6 | 合法：200 正常返回 |
| disabled | 1 | 400 拒绝，报 `only 0.6 is allowed for this model in non-thinking mode` |
| disabled | 0 | 400 拒绝，报 `only 0.6 is allowed for this model in non-thinking mode` |
| enabled | 1 | 合法：200 正常返回 |
| enabled | 0.6 | 400 拒绝，报 `only 1 is allowed for this model in thinking mode` |
| enabled | 0 | 400 拒绝，报 `only 1 is allowed for this model in thinking mode` |

**请求构造**：
- 6 个场景复用同一提示词（`K6_USER_PROMPT`），仅 `thinking` 与
  `temperature` 变化——被测参数是场景唯一变量
- payload 仅 `model` / `messages` / `thinking` / `temperature` /
  `stream=false`，不传 `max_tokens`（手工构造 payload 直发，K3-K5 先例）

**断言**：
1. 合法组合：HTTP 200 + `choices[0].message.content` 非空（enabled 场景
   可能含 `reasoning_content`，属正常思考输出，**不在本用例断言范围**
   ——关思考本身由 K5 验证，本用例专注温度档联动契约）
2. 非法组合：HTTP 400 + 错误信息包含官方文案（**忽略大小写的子串匹配**，
   对错误体 JSON 结构不敏感——官方文案可能嵌在 `error.message` 等不同
   位置）

**判定矩阵**：
- 网关未实现联动校验（非法组合也 200）→ FAIL（客户症状：关思考温度档
  失效）
- 校验过严（合法组合也 400）→ FAIL（过度修复）
- 400 但错误文案与官方不一致 → FAIL（对客户的错误提示偏离官方）
- 六组合全部符合官方契约 → PASS

**设计决策记录**：
- **每场景单次请求**：与 K4/K5 的多次连发不同——参数合法性校验是
  确定性行为（要么 400 要么不 400），不存在"时好时坏"的偶然性，无需
  重复验证；K4/K5 的多次连发针对的是非确定性的生成行为
- **错误文案采用子串匹配而非全等**：官方文案可能随版本微调前后缀，
  核心语义（`only 0.6 is allowed` / `only 1 is allowed`）稳定；忽略
  大小写避免大小写风格差异误报
- **进 smoke 集**：4 次请求均为数秒级（2 次生成 + 2 次快速 400），无
  K4 的长预算风险

### test_thinking_effort_reasoning_length (K7)

**背景**：kimi-k3 官方思考强度参数为顶层 `reasoning_effort`（官方文档
use-reasoning-effort / kimi-k3-quickstart），K3 恒开思考；K2.x 的
`thinking` 配置在 K3 已废弃（官方迁移指引：移除 thinking 改用
reasoning_effort）。官方预期思考长度（reasoning_tokens）随档位递增。
若档位倒挂，说明网关对思考强度的翻译/映射存在缺陷（如各档映射到
同一后端参数）。

**请求构造**：
- **只按官方格式传参（无回退）**：顶层 `reasoning_effort`，不带
  thinking 对象（官方迁移指引：K2.x thinking 配置在 K3 废弃）
- **请求顺序（客户指定）**：升序轮 low → high → max 发送后比对
  思考长度，降序轮 max → high → low 逆向重发后再比对——正逆两轮
  排除请求顺序相关干扰（缓存/预热），两轮各自按 low < high < max
  三档软对比（medium 不参与对比）
- 最后依次验证：medium 顶层（合法档位，按官方预期 200 放行，
  不参与对比）→ medium 嵌套 `thinking={"type": "enabled",
  "effort": "medium"}` 预期 400——废弃的 K2.x thinking 配置下
  medium 为非法档位（客户指定契约）
- 各档请求内容与 `temperature=1` 完全相同（开思考档契约温度，
  见 K6），相邻间隔 3s，不传 `max_tokens`（观察思考自然长度，
  K4/K5 先例；手工构造 payload 直发）
- 提示词选用需要逐步推理的问题（鸡兔同笼），使档位间思考长度差异
  可观测

**断言**（硬——请求基本健康，否则长度对比无意义）：
1. 每次官方档请求（升序轮 3 + 降序轮 3 + medium 顶层 1）HTTP 200 +
   正文非空 + `finish_reason` 自然结束（`stop`/`eos`/`ended`，
   未传 max_tokens）
2. 嵌套 thinking.effort=medium 预期 HTTP 400

**对比**（软——**倒挂不判失败，仅告警**，按客户要求）：
- 升序轮与降序轮各自独立比对 low < high < max（round 前缀区分
  "升序轮/降序轮"）；low 与 high、high 与 max 的
  `reasoning_tokens` 应严格递增；任一对倒挂/持平（低档 ≥ 高档）→
  `test_logger` 警告 + `record_warning` 记入报告，用例**仍通过**
- 任一轮对比三档均为 0 → 告警思考强度参数可能未生效或服务端未
  上报思考 tokens，跳过该轮档位对比
- `reasoning_tokens` 兼容 `usage.reasoning_tokens`（Kimi/Zhipu 风格）
  与 `usage.completion_tokens_details.reasoning_tokens`（OpenAI 风格）
  两种拼写（K5 先例）；单次响应缺 usage 时软告警（K5 先例）

**判定矩阵**：
- 任一官方档请求失败（非 200/空正文/非自然结束）→ FAIL（对比前提
  被破坏）
- 嵌套 thinking.effort=medium 未按预期 400 → FAIL（废弃配置下非法
  档位校验缺失）
- 两轮均递增（low < high < max）→ PASS（无警告）
- 任一轮档位倒挂/持平 → **PASS + 警告**（行为质量偏离而非服务
  故障，按约定不判失败，报告留痕供定位档位映射问题）

**设计决策记录**：
- **纯官方格式（无回退）**：按客户要求只按官方顶层 reasoning_effort
  传参，不做 thinking.effort 回退——官方迁移指引明确"移除 K2.x
  thinking 配置"，网关应支持官方参数面
- **medium 档顶层 200 放行、嵌套 400**：按客户契约，顶层
  reasoning_effort=medium 为合法档位（200 放行，但不参与思考长度
  对比）；嵌套 thinking.effort=medium 在废弃的 K2.x 配置下为非法
  档位，预期 400
- **temperature=1 显式传递**：官方文档说明 K3 temperature 固定 1.0
  （建议省略）；本网关按 K6 契约显式传 1（开思考档唯一合法温度），
  且已加入采样豁免名单——若被 Jenkinsfile `--sampling-params` 全局
  温度覆盖，各档请求会因非法温度被 400 拒绝，破坏档位对比前提
- **正逆两轮请求顺序**：按客户指定顺序 low→high→max 比对后
  max→high→low 再比对——逆向重发可排除请求顺序相关干扰（前缀
  缓存命中/推理预热使后发请求思考变长等），两轮独立软对比，任一
  轮倒挂均告警留痕
- **倒挂为软判定**：档位倒挂属思考预算映射的行为质量偏离，服务
   本身仍正常响应——按客户要求不判失败，`record_warning`（报告
   可见）+ `test_logger` 警告（日志可见）双通道留痕
- **不进 smoke 集**：max 档思考生成为长耗时请求（数十秒级），
  避免拖慢冒烟套件（同 K4 理由）

**注意事项**：
- 修复方向应为网关完整支持官方顶层 `reasoning_effort` 参数
  （含 medium 档放行）并对废弃 thinking 配置的非法档位做校验
- 思考长度本身有随机性（temperature=1 采样），轻微倒挂可能偶发
  ——警告定位用；若稳定倒挂则为档位映射缺陷（如各档映射到同一
  后端思考预算参数）
