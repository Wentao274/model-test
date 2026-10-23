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
1. 在 `tests/test_k_customer_issue.py` 中以 `K{n}_` 前缀定义该问题的常量
   （提示词、tools、tool_choice 等），内容与客户原始请求逐字段一致；
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
- `_collect_stream_tool_calls`：OpenAI 流式协议中 tool_calls 以增量片段下发
  （按 index 分片，`function.arguments` 逐段追加），需按 index 聚合成完整调用
  后才能做 JSON 合法性与必填项校验
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
消息（`_run_k4_request` 单次请求逻辑，失败归因到具体迭代）。相邻请求
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
