# K. 客户问题复现测试

## 概述
收录来自客户反馈的真实问题，将客户提供的原始请求（通常是 curl 命令）还原为标准
模型请求进行复现与回归验证。

设计原则：
- **原样复现**：system/user 提示词、tools 定义、tool_choice、thinking、stream、
  stream_options、temperature、max_tokens 等全部字段与客户原始请求逐字段一致，
  不做任何"规范化"改写——保证复现的是客户遇到的确切请求形态。
- **P0 为主，按工单优先级**：客户报障场景纳入回归验证——K1-K7、K10-K30、
  K37-K39 为 P0 必测（任何失败应阻断发布），K8/K9/K31/K32/K35/K36/K40 按客户工单优先级为 P1，K33/K34 为 P2。
- **修复后转为回归**：问题修复后用例保留，作为该场景的长期回归用例。
- **参数豁免（test_k 整套件）**：所有 K 用例保持原始测试参数，不参与
  全局 `--sampling-params` 覆盖（`conftest.py` 模块级规则
  `RAW_SAMPLING_EXEMPT_FILES`——新增 K 用例自动适用，无需登记）：
  工单/原始请求含采样参数的原样保留（K1 temperature=0.1、K2
  temperature=1+top_p=0.95、K5-K9 思考档契约温度、K10/K11/K12 脚本
  temperature=0、K24 temperature=0.0、K32 temperature=0.5/1.5/2.0/
  2.5/-0.5——chat/msg 双协议），其余未含参数的用例一律不注入（无全局
  注入口）。
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
   登记测试点（编号 K{n}，优先级按客户工单 P0/P1，func_name 与测试方法名一致）。

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
| K8 | required+闲聊必须调用工具（客户工单级别） | 客户工单原始问题：required+闲聊（"Reply with exactly: OK"）不发起工具调用——tool_calls 缺失、finish=length、ct 恒吃满 max_tokens、正文仅 OK；预期 finish=tool_calls、关思考 ct 较小、开思考 rt<max_tokens | 关思考 mt=1000/3000、开思考 mt=3000（get_weather 工具），断言 tool_calls+get_weather+arguments 合法 JSON、finish=tool_calls、ct<max_tokens、开思考 rt<max_tokens | P1 |
| K9 | required+闲聊必须强制调用工具（按官方行为） | 官方实测：闲聊+required → finish=tool_calls、强制返回 get_weather（city 瞎猜不限定）、reasoning 仅 38；Alaya 同场景 finish=length、reasoning 吃满 256/2000 预算、tool_calls=None；有意图时两站一致正常 | 关/开思考 × mt=256/2000（与 K8 同场景不同级别），按官方行为断言 tool_calls 强制返回（get_weather、arguments 合法 JSON）、finish=tool_calls、ct<max_tokens、开思考 rt<max_tokens | P1 |
| K10 | GLM-5.3-Flash tool_choice 四种模式支持 | 客户问题（AGDC2-15）：上线前版本未指定模型专属工具调用格式解析器，tool_choice 语义不被支持；修复为 Worker 侧指定生成解释器、渲染字段至聊天模版；需支持 auto/required/named/none；同时适用 Kimi K3 | 四模式各一次（mt=2048、非流式、不传 thinking；采样参数豁免——原始脚本指定 temperature=0 原样保留，不受全局 SAMPLING_PARAMS 覆盖；top_p/seed 不注入；get_weather+get_current_time 两工具），断言 auto/required 必须发起工具调用（形状合法、finish=tool_calls）、named 必须调用指定工具（指定与天气意图不同向的 get_current_time）、none 禁止调用（无 tool_calls、正文非空、finish=stop） | P0 |
| K11 | GLM-5.3-Flash response_format 三种模式支持 | 客户问题（AGDC2-16）：DingoRouter 不支持结构化输出语义；修复为 Router 侧支持结构化生成语义并转发至引擎；需支持 json_object/json_schema/text | 三模式各一次（temperature=0、mt=2048、非流式、不传 thinking），断言 json_object 正文可解析为 JSON 对象、json_schema 正文可解析且 city 为字符串、temperature 为数值、键集合恰为 {city,temperature}（weather strict schema）、text 正文非空；每轮 finish=stop | P0 |
| K12 | GLM-5.3-Flash reasoning_effort 档位支持 | 客户问题（AGDC2-17）：字段为 reasoning_effort 且放在 chat_template_kwargs 里（GLM 聊天模版），而 OpenAI 协议/参考脚本将其放在顶层；Router 需在 OpenAI 协议外层捕获该字段并传给引擎；修复为 Router 侧支持语义转发；需支持 low/high/max/空（空=不发送该字段，默认档），且不管放在顶层还是嵌套在 chat_template_kwargs 里，请求都能被正常接受和处理并输出正常响应 | 两种放置（顶层/嵌套 chat_template_kwargs）× 四档各一次（temperature=0、mt=2048、非流式、不传 thinking、chat_template_kwargs={clear_thinking:true}；嵌套放置：reasoning_effort 放进 chat_template_kwargs），断言每轮 200+正文非空+finish=stop；档位对思考的实际影响（rt/reasoning 长度）仅日志留痕 | P0 |
| K13 | stop 序列遵循且被截断正文前置多余字符 | 客户问题：stop=["橘子"] 的流式请求，期望输出 "苹果、香蕉、"，实际输出 ">苹果、香蕉、"——被截断正文前面多输出了一个 ">" 符号；同时适用 KimiK3 | 按客户原始请求体还原（stream=true、stop=[橘子]、glm-5.3-flash 另传 thinking={type:enabled}+reasoning_effort=low；KimiK3 不传），断言 SSE 有正文增量、finish=stop、合并正文严格等于 "苹果、香蕉、"、不含 "橘子" | P0 |
| K14 | 孤儿 tool 消息应 HTTP 400 拒绝 | 客户问题：tool 角色消息前无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未定义任何 tools），属协议非法请求，网关应校验并返回 400 Bad Request；实际返回 200 放行；同时适用 GLM-5.3 与 GLM-5.3-Flash | 按客户原始请求体还原（user 后直接跟 tool tool_call_id=call_abc123、stream=true、无 tools/thinking/采样参数），断言 HTTP 400；若 200 放行（缺陷形态）取样 SSE 事件留证后 FAIL | P0 |
| K15 | 细粒度前缀匹配短输入缓存阈值 | 客户问题：短文本缓存命中率不达标，根因推理引擎默认前缀缓存分块撮合的最小可缓存块长过大（vLLM 默认 640 tok 量级），客户输入低于该块长（如 625 tok）完全不缓存；平台修复为细粒度前缀匹配（sglang prefix-match-unit=64）；同时适用 GLM-5.3 与 GLM-5.3-Flash | 两个测试点（OpenAI 协议非流式、不发送采样参数，cached_tokens 取 usage.prompt_tokens_details.cached_tokens 兼容 usage.cached_tokens）：1) 输入 64<N<640 相同请求连发两次，断言第 2 次 cached_tokens>0；2) 输入 N<64 相同请求连发两次，断言 cached_tokens==0；以服务端 prompt_tokens 校验规模前提 | P0 |
| K16 | 固定前缀/多轮上下文缓存命中率达标 | 客户问题：修复前固定前缀每轮 cached=7680/input=8693（88.35%）、多轮上下文 87.16%，均低于 90% 目标；根因 640 token 分块粒度将共享前缀截断（8192→12×640=7680，损失 512），细粒度匹配（64）后应 ≈94.2%≥90%；同时适用 GLM-5.3 与 GLM-5.3-Flash | 两模式（OpenAI 协议非流式、不发送采样参数，规模由原始信息推算：~12800 字符共享前缀 ≈8192 tok + ~780 字符/轮唯一问题 ≈501 tok）：1) 固定前缀 10 轮独立请求；2) 多轮上下文单会话逐轮追加（回复极短）；均排除第 1 轮预热实测 9 轮，断言各模式 Σcached/Σprompt_tokens ≥90%，任一 <90% 即 FAIL | P0 |
| K17 | stop 停止符（换行符）在推理阶段生效 | 客户契约：指定停止符为换行符 "\n" 并开启思考时，停止符同样作用于推理输出——推理里的第一个换行即触发停止，正文不会生成；反之若换行未触发停止、继续输出正文，则换行符未生效；适用 GLM-5.3 | 按场景构造流式请求（stream=true、stop=["\n"]、thinking={type:enabled}（K1 口径）、max_tokens=512 防御性预算、不发送采样参数），断言 SSE 有事件、合并正文为空（核心）、finish_reason==stop、合并 reasoning 不含换行（停止符不泄漏） | P0 |
| K18 | 模型输出 JSON 可回填为下次请求输入上下文 | 客户问题（AGDC2-28）：上次请求输出的 assistant JSON 作为下次请求的输入上下文提交即报错（missing field `name`）——助手历史 tool_calls 混有空占位调用（name=""、id=null）与真实 bash 调用（arguments 缺开头 "{"、非合法 JSON）；修复为移除空占位项再校验、缺 "{" 原样保留（不补）、兼容重复 reasoning 字段；后续问题（开发文档）：修复后新问题 tool_call_id 悬空引用（must reference an unanswered tool call）——根因为模型返回空 function（id=null），客户端以 missing_tool_call_id 回填后被协议拒绝，根上解决为模型不返回空 function；适用 GLM-5.3 | 按客户 agent 两步流程还原（用户指定测试逻辑）：第一个请求让模型输出技能周报数据 JSON 并落盘测试脚本同级目录下临时文件（第一步"输出 JSON 到 *.json 文件"）；第二个请求调用工具读取该临时 JSON 文件，将工单原始 assistant 返回数据（user→assistant(真实 bash 调用（arguments 缺 "{"）+reasoning 双字段——空占位调用已按用户指定移除)→tool(工具读取结果——协议必需的工具结果配对，实测缺失被 400 拒绝)→user 追问，带 bash 工具定义，非流式）回填为输入上下文；第三个请求（根因断言）复刻工单首个 user 回合（带 bash 工具定义）断言模型工具调用结构完整；测试完成后删除临时 JSON 文件（finally 兜底，断言失败同样清理）；断言：第一个请求 HTTP 200 且正文可提取合法 JSON 对象、临时文件回读一致、第二个请求 HTTP 200（核心）、choices 存在、message 结构存在、第三个请求模型发起工具调用且每条调用 name/id 非空、arguments 为合法 JSON 对象（根因断言：模型不得返回空 function）；采样参数不发送——test_k 保持原始测试参数（工单未指定，不注入） | P0 |
| K19 | 单次请求图片数超限（>16）应拒绝并返回恰当错误 | 客户问题：单次请求携带超过 16 张图片导致请求失败；根因服务端 serving-pool 显式配置 --limit-mm-per-prompt {"image":16,"video":1,"audio":0}（vLLM 多模态单项限额）；契约为超限请求应失败并返回恰当错误信息（参考 "At most 16 image(s) may be provided in one prompt"）；适用 GLM-5.3-Flash | 代码生成 17 张 32x32 纯色 PNG（base64 data URL，无外部依赖），单条 user 消息携带 17 个 image_url part 非流式提交（不发送采样参数——豁免），断言响应失败（非 200）且错误信息含 "at most 16 image"（大小写不敏感） | P0 |
| K20 | 1M 上下文请求应被正常支持 | 客户问题：请求报错 "Input length (918451 tokens) exceeds the maximum allowed length (781754 tokens). Use a shorter input or enable --allow-auto-truncate."（invalid_request_error——网关透传 serving 侧上下文长度校验拒绝；当时最大允许 781754，未按 1M 上下文契约配置）；契约：模型需支持 1M 上下文请求——1M 量级输入应正常响应；适用 GLM-5.3 | 1M=输入+输出（用户口径），总量略小于 1M：探针自校准（重复单元 ×2000 从 usage.prompt_tokens 精确计量）后按目标生成主请求：输入 960,000 tokens + 输出预算 max_tokens 覆盖思考+正文，两轮思考档位（用户指定补 max 场景）——low 轮（1024）常规、max 轮（4096）最大思考负载，输出侧同步压窗口（总消耗 ≈961K/964K，两种 1M 口径均满足），单条 user 消息非流式提交（采样参数不发送——用户指定：test_k 保持原始测试参数（工单原始请求未指定，不注入）；跑必冷仅 low 轮——用户加固：low 轮（含探针）材料头部置每次请求唯一 nonce（时间戳+uuid，可含中文），前缀必不命中 KV 缓存，真 1M 冷 prefill；max 轮取消唯一前缀——输出侧验证不受缓存影响，允许命中历史缓存加速），断言探针 200 且有 usage、每轮主请求 HTTP 200、choices/content 非空、每轮主响应 prompt_tokens（如有）>781,754（规模 sanity） | P0 |
| K21 | system 消息内嵌 tools 的非标请求结构应被接受 | 客户问题（kimi-k3 工单原始请求体）：messages[2] 为 role=system 且无 content 字段、代之以内嵌 tools 数组（Calculator 单工具），服务端反序列化报 400 invalid_request_error/json_parse_error（"messages[2]: data did not match any variant of untagged enum MessageContent"）——结构虽非 OpenAI 协议标准形态（tools 应为顶层参数），但客户业务实际在用；契约：宽容解析并正常响应（预期 200）；适用 Kimi-K3 | 按工单原始请求体原样重放（模型名由环境注入，其余字段不改动；采样参数不发送——test_k 保持原始测试参数（工单原始请求未指定，不注入）），单次请求（确定性行为，无需连发），断言 HTTP 200（核心——原始报错形态复现即 FAIL）、choices 存在、message 有效输出（content 或 tool_calls 非空）；模型真实响应（状态码/响应体全文）断言前打印；运行日志不含具体模型名（系统提示词正文含模型自我介绍，仅记字符数概要） | P0 |
| K22 | /v1/messages 缓存命中率应与 /v1/chat/completions 基本一致 | 客户问题：相同请求下 Anthropic 协议（/anthropic/v1/messages）前缀缓存命中率始终低于 chat 协议（"缓存始终上不去"）——根因：该链路 system 头部携带 x-anthropic-billing-header: 逐请求动态计费行（字符串/块数组两种 system 形态），前缀缓存要求从位置 0 连续匹配，头部逐请求变化导致整个前缀永不命中；chat 协议无此行、前缀稳定（K15/K16 已验证 ≥90%）；开发修复：入引擎前条件剥离——system 开头是 x-anthropic-billing-header: 行即去掉、其余内容原样保留；适用 GLM-5.3 | 测试要点（用户口径）：同轮等价请求逐轮交替发送两协议（同轮同问；前缀头部渠道标记行不同——用户指定：剥离计费行后两协议前缀仍从位置 0 分叉，互不命中对方缓存条目，各自建条目/各自命中，messages 冷轮为真冷），统计二者缓存命中率并逐轮比较——冷轮不参与比较（需热轮才能统计命中率），组级判定（用户指定）：单组失败不中断后续组，5 组中至少 4 组该组全部热轮差值 ≤3 个百分点（用户指定容差）即 PASS、不足 4 组 FAIL；热轮 messages 全量 miss（read=0 且 creation=0）时同轮重发一次鉴别（用户指定）：重发命中→WARN 留痕继续（偶发——疑似多实例路由/条目可见性问题）；仍 miss→该组不符合预期（剥离失效形态，判别力不变）；每请求在 system 头部构造逐请求变化的计费行；循环 5 次比对（用户口径：每次循环的请求消息尽量不一样）：2 组中文、2 组英文、1 组中英混合，整请求长度尽量超过 8k tokens；覆盖两条剥离代码路径（块数组断点挂 system 块——K3 口径；字符串断点挂 user 首块）；每次循环每协议 1 冷轮 + 2 热轮（用户口径；冷轮不参与比较），共 5 次循环 × 2 协议 × 3 轮 = 30 请求，组间间隔 3 秒（用户指定）；硬断言：①组级判定（用户指定）——单组失败不中断后续组，5 组中至少 4 组该组全部热轮差值 ≤3 个百分点即 PASS、不足 4 组 FAIL；②每请求 HTTP 200 且响应正常；缺陷形态 messages ≈0% vs chat ≈94%（五组全不符合→FAIL）、修复后两协议每热轮均 ≈94%（五组全符合→PASS）；热轮 cache_creation>0（剥离失效直接信号）与双低形态仅日志留痕；运行日志不含具体模型名 | P0 |
| K23 | 孤儿 tool 消息应对齐官方放行并正常消费 | 客户问题（新工单，官方对齐口径）：tool 角色消息前无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未定义任何 tools），平台返回 400（"Invalid parameter: messages with role 'tool' must be a response to a preceeding message with 'tool calls'."——type: alaya code error、code: invalid text request——网关层白加的校验）；智谱官方源对同一请求 HTTP 200 正常应答「北京今天天气晴朗，气温18℃」且模型在 reasoning 中实际引用 tool 数据（工具数据被正常消费）；新契约（客户指定）：预期结果同官方一致——此类消息序列不做校验、正常出结果；与 K14 关系：K14 为当时工单口径原始契约（保持不变——用户指令），二者输入同类预期相反，平台采纳官方对齐修复后 K14 将 FAIL、其保留/退役由用户决定；适用 GLM-5.3 | 按客户新工单原始请求体还原（messages=[user"查一下北京天气"、assistant"好的，我来为您查询北京天气数据。"（纯文本无 tool_calls——孤儿条件）、tool tool_call_id="call_weather_001" content={"city":"北京","temp_c":18,"condition":"晴"}、user"根据工具返回的数据，用一句话告诉我天气。"]、max_tokens=200、非流式、无 tools/thinking；采样参数不发送——test_k 保持原始测试参数），单次请求（确定性行为，无需连发），断言 HTTP 200（核心——原始 400 拦截形态复现即 FAIL）、响应合法 JSON 且 choices 非空、message 有效输出（content 或 tool_calls 非空——官方形态为正常答句；思考耗光无输出+finish=length 以 reasoning_effort=low 回退重发——K24/K25/K27 口径，双强度均未产出即 FAIL）；官方行为细节（输出/推理引用工具数据要素）软校验仅日志；模型真实响应（状态码/响应体全文）断言前打印 | P0 |
| K24 | 双请求正常响应（思考耗尽预算 low 强度回退） | 客户问题（新工单）：客户两个请求（中文同音词与言部汉字写作题、英文数学题），temperature=0.0、max_completion_tokens=32768（工单原始字段名）、非流式，期望均正常响应并返回正文；风险形态（用户指定）：默认 max 思考强度下思考可能耗光预算（正文空+finish=length）；适用 GLM-5.3 | 按工单原始请求体还原两请求直发（采样参数保持原始——用户指定：两请求体均显式 temperature=0.0，工单体为唯一口径（test_k 整套件不参与全局采样覆盖），top_p/seed 不注入）；第 1 轮默认 max 思考强度（不带 reasoning_effort），有正常正文即通过，断言 HTTP 200、响应合法 JSON 且 choices 非空、message 有效输出（content 或 tool_calls 非空）；耗光形态（正文空+finish=length）按用户指定契约转 reasoning_effort=low（GLM 顶层思考强度参数，K20 口径）重发且仅重测耗光请求（已通过不重测），断言相同；正文空且 finish≠length 直接 FAIL；low 回退仍无正文即 FAIL（双强度均未产出——留证交开发）；finish/usage 仅日志；模型真实响应（状态码/响应体全文）断言前打印 | P0 |
| K25 | assistant 历史重复 reasoning_content 字段应被兼容接受 | 客户问题（工单跟进）：多轮对话回填 assistant 历史时，同一条消息携带两个 reasoning_content 字段（两轮历史思考未去重地拼接成同键重复）与上一次请求的正文；客户原始工单还曾因思考内容含 They're/I'm/It's 等英文撇号导致 JSON 破损——正文与思考可能含单引号/双引号/换行等字符，须兼容处理、不影响请求格式（用户指定）；契约（用户指定）：预期不报错、正常响应，第一个 reasoning_content 被第二个覆盖（宽松解析保留最后一个值，K18 修复口径）；适用 GLM-5.3 | 共发三次请求（用户指定，JSON 链式回填——第 1/2 次响应 JSON 作为下一请求输入、思考随历史一并回填；提示词为测试自行设计，工单未携带具体提示词——用户口径仅要求结构）：第 1 次 user 单轮流式要求仅输出 JSON——采集第 1 段思考+第 1 次正文（JSON，作为第 2 次请求输入回填）；第 2 次流式回填第 1 次历史 messages=[assistant(content=第 1 次正文（JSON）, reasoning_content=第 1 次思考), user 追问]（单键经 dict 表达——K18 口径）并要求仅输出 JSON——采集第 2 段思考+第 2 次正文（JSON，作为第 3 次请求输入回填）；第 3 次流式回填 messages=[assistant(content=第 2 次正文（JSON）, reasoning_content=第 1 次思考, reasoning_content=第 2 次思考), user 追问]——重复键无法经 dict 表达，手工拼接 JSON 文本直发，动态值一律 json.dumps 全转义，发送前三重自检（合法 JSON、reasoning_content 键出现次数==2、转义回读值一致）；硬断言第 1/2 次思考与正文均非空（构造数据源）且正文为合法 JSON（JSON 链断裂即场景无法构造 FAIL；容忍 markdown 代码块围栏）、第 3 次 HTTP 200（核心——被拒绝即 FAIL）+ SSE 事件非空 + 合并正文非空 + finish_reason 合法；耗光回退（K24 口径）：max_tokens=8192 下默认 max 档思考可能耗尽预算（正文空+finish=length）——该形态以 reasoning_effort=low 仅重发耗光请求（第 3 次重发构造不变仅加顶层 reasoning_effort 字段——HTTP 200 核心契约首次请求已达成），断言相同，正文空且 finish≠length 直接 FAIL，low 回退仍无正文即 FAIL（双强度均未产出——留证交开发）；引号覆盖度软观察（三个回填值均无引号/换行字符时 record_warning，不判失败）；采样参数不发送（test_k 保持原始测试参数——工单未指定，不注入）；max_tokens=8192 工单口径三次一致；usage 仅日志；模型真实响应断言前打印 | P0 |
| K26 | 工具 schema 负向前瞻正则应被兼容放行 | 客户问题：工具参数 schema 的 pattern 包含 ^(?!...) 负向前瞻正则——后端编译为 structural_tag 生成约束时底层语法编译器不支持 lookahead：非流式报 400（Failed to compile structural_tag grammar——Lookahead is not supported yet，request id 2026102616110264231215776333070）、流式报 provider_unavailable（upstream_stream_error）；修复（frontend 预处理兼容，非编译器新增 lookahead 支持）：GLM-5.3+glm47 解析器+SGLang、tool_choice=auto、工具未显式 strict、schema 含 ^(?! 开头正则时命中——仅将生成约束工具副本置 strict=false 绕过强制编译，原始 schema/工具描述/格式约束保留；该路径不再由 grammar 强制保证参数满足完整 schema；适用 GLM-5.3 | 按触发形态构造：path 参数 pattern 以 ^(?! 开头（禁止路径穿越 ^(?!.*\.\.).+$）、不显式 strict、tool_choice=auto，user 消息自然诱导 write_workspace_file 调用，非流式+流式各发一次；断言：非流式 HTTP 200（核心——grammar 编译错误复现即 FAIL）+choices 非空+message 结构存在，流式 HTTP 200（核心——provider_unavailable 复现即 FAIL）+SSE 事件非空+至少一个含 choices 数据块；不断言工具被调用与参数满足 pattern（兼容绕过明确口径）、响应形态宽松留日志；采样参数不发送（用户指定；test_k 保持原始测试参数——工单未指定，不注入）；usage 仅日志 | P0 |
| K27 | 历史非法 JSON arguments 应被容忍 | 客户问题（AGDC2-19，codex 客户端 + MCP 工具场景）：模型输出的工具调用 arguments 本身非合法 JSON（两处括号错误——"refId": "A"}] 缺 }、40}}}] 处多 }，上游流式日志证实由模型产生）；客户端执行失败、回放全量历史，服务端校验历史 tool_calls 的 arguments 直接 400（Assistant tool call function.arguments must be valid JSON）——纯服务端问题，与 codex 客户端无本质关系；修复：历史无法解析的 arguments 按字符串保留、不再 400、让模型继续纠正；适用 GLM-5.3 | 复刻客户链路（user→assistant(畸形 arguments 调用，保真浓缩版——两处错误形态与关键结构原样、场景自检必非法)→tool(执行失败结果，协议配对必需)→user 追问修正重试，带 MCP 工具定义，非流式，max_tokens=16384（16k——覆盖默认档思考+大尺寸修正输出，low 兜底）），断言 HTTP 200（核心——报错复现即 FAIL）+choices 非空+message 结构存在+模型发起修正工具调用且每条调用 name/id 非空、arguments 为合法 JSON 对象（修正行为——修复目的"让模型继续纠正"）；不断言历史被改写/修复；采样参数不发送——test_k 保持原始测试参数（工单未指定，不注入）；usage 仅日志 | P0 |
| K28 | 模型输出字段核验（尾裸/回流/工具参数） | 客户问题（AGDC2-24，TR-20261016-02 九章云-模型输出字段核验）：客户探针报告三项判据——T1 content 尾部裸 </think> 残留（0 次为通过，被测平台曾 2/15 不通过）、T2 字段回流（content→reasoning，0 次为通过）、T3 工具参数完整性（arguments 合法完整 JSON 且 reasoning 无 <arg_key>/<arg_value>/</tool_call> 原生标记，100% 为通过）；length 截断只记录不判定；适用 GLM-5.3 | 客户探针（scripts/probe_think_tag.py）+ 数据集（requests/AGDC2-24，工单原始参数 stream=true、max_tokens=8192、reasoning_effort=max 原样保留）纳入框架：3 用例×5 次（--runs 硬编码 5，用户指定）流式请求，只评被测平台（不跑对照），逐条留存 raw 并统计三项；raw 目录：Jenkins→builds/<TESTER>/<BUILD_NUMBER>/origin_raw/AGDC2-24/<model>/（与 allure-report 同级），手动→origin_raw/AGDC2-24/<model>/<timestamp>/；断言：全部 HTTP 200 且响应体可解析 SSE（空体/非流式结构即无法核验）、T1=0、T2=0、T3=100%——任一不符合即 FAIL；模型名由环境注入；请求体不含 temperature/top_p/seed——按用户指定保持工单原始请求体不变、不注入采样参数；usage 仅日志 | P0 |
| K29 | 双协议零增量响应与工具调用核验 | 客户问题（AGDC2-25，九章云 Alaya GLM-5.3 网关）：同一段业务会话报文（195 条消息/19 个工具/stream=true/max_tokens=4096）分别请求 /v1/chat/completions 与 /anthropic/v1/messages——OpenAI 协议 13 次中 5 次零增量响应（HTTP 200、SSE 结构完整但 delta.content/reasoning_content/tool_calls 三类增量均空、usage.completion_tokens>0），工具调用仅 4/13；Anthropic 协议 8/8 返回工具调用、零增量 0/8；适用 GLM-5.3 | 客户探针（scripts/probe_alaya.py）+ 数据集（requests/AGDC2-25 两份协议请求体）纳入框架：两种协议各发 --n 硬编码 10 次（用户指定）流式请求，逐条留存 raw 并统计三项判据——有效请求==10、零增量==0、返回工具调用==100%（10/10），任一不符合即 FAIL；每协议追加 1 次强制工具调用（tool_choice required/any，仅观察不计入）；raw 目录：Jenkins→builds/<TESTER>/<BUILD_NUMBER>/origin_raw/AGDC2-25/<model>/（与 allure-report 同级），手动→origin_raw/AGDC2-25/<model>/<timestamp>/；模型名由环境注入；stream/max_tokens=4096 按脚本口径覆盖；temperature/top_p 原始未指定——保持不指定（不注入）；usage 仅日志 | P0 |
| K30 | /v1/responses 校验码输出与 token 计数核验 | 客户问题（合成短文本 Token 对照测试，/v1/responses 接口）：probe 三项断言未通过——请求明确要求只输出 SYNTHETIC_SHORT_TEXT_MARKER 实际正文输出 '4b69a88e6b'（模型未遵守指令）；input_tokens=52 超基准 43 ±3%（区间 41.71-44.29——整数取值 42/43/44）；output_tokens 报告 295 而实际可见输出仅 10 字符且 reasoning_tokens=0（计数与实际文本量明显不成比例，存在统计口径或隐藏推理未计入疑点）；适用 GLM-5.3 | 按客户原始 curl 还原：POST {base}/v1/responses（Responses API），input 两消息（content 均 input_text 类型）、stream=true、max_output_tokens=1024 原样，模型名由环境注入，采样参数原始未指定——保持不注入；断言（任一失败即整体失败）：HTTP 200 且流式结构完整（output_text 增量+usage）、终态事件 status == completed（failed/incomplete/cancelled 或无终态事件即失败）、合并正文严格等于校验码（多一个字符即失败）、usage.input_tokens∈[42,44]（基准 43 ±3%）、output_tokens 满足 reasoning_tokens ≤ output ≤ reasoning + len(正文)（总计=思考+正文，1 token/字符宽松上界——缺陷形态 295 tok vs 10 字符远超） | P0 |
| K31 | json_object 嵌套结构完整输出与预算回退核验（256→512，chat+msg 双协议） | 客户问题（工单 P1 R-01+A-07a/A-07b，结构化输出）：官方行为 HTTP 200、content 为合法 JSON（嵌套对象/数组均可解析）；贵方实测 finish_reason=length、content 为空字符串、思考内容占满 max_tokens=256——A-07a（嵌套对象 user.name/user.age/address.city）与 A-07b（数组 3 个 id+title 对象）两种请求各 3 发全部该形态（3 采样 0 过，2026-11-03）；用户确认：思考消耗配额致空正文/截断在官方与被测均有一定概率发生——验收口径调整为预算回退链（用户指定）：核心需求为在 max_tokens 内能返回完整合法 JSON；适用 GLM-5.3 | chat+msg 双协议（msg 无 json_object 参数语义——同一 prompt 引导、max_tokens 协议必需字段）× 工单两形态（A-07a/A-07b 提示词与请求体工单原样——chat 字段序 model/messages/max_tokens/response_format、无 stream 字段）× 预算回退链：轮一 max_tokens=256（工单原值）→ HTTP 200+正文非空+json.loads 成功+嵌套结构齐备（递归宽容：含 name+age 的 user 对象与含 city 的 address 对象 / 对象数组每元素含 id+title，裸数组或对象包裹均认可，数量=3 与类型留观察）→ 直接达标；不满足（空正文/json 截断或非法/结构不齐）→ 回退 max_tokens=512 同请求重验——满足 → 测试通过+警告留痕（警告显示 256 输出空正文或 json 截断及 finish 状态）；两轮均不满足 → FAIL（输出两轮各自形态）；HTTP 非 200 直接 FAIL（回退链仅针对正文形态）；模型名由环境注入，采样参数原始未指定——保持不注入；历史记录：初版三接口 chat/responses/msg × 各 2 次，A-07 证据后重构聚焦双协议（用户指定"覆盖两种协议"），/v1/responses 轮移除 | P1 |
| K32 | temperature 原厂区间 [0, 2] 放行与越界校验（chat+msg 双协议） | 客户问题（工单 P1 R-02+A-03，参数校验）：官方行为 HTTP 200（原厂取值区间 [0, 2]，1.5 合法）；贵方最新实测（A-03，2026-11-03）chat 三发 temperature=1.5 全部 HTTP 400、错误体「temperature 超出范围 [0, 1]」——本地收紧到 [0, 1]（历史 R-02：6 发通用「模型服务调用失败」upstream_error）；整改建议（即预期结果，用户指定）：放开 temperature 到原厂 [0, 2] 区间（原 [0, 2) 调整为 [0, 2]——上界端点 2.0 移入放行），或原样透传不做本地收紧；保留非法参数校验（越界 400 指明参数名与区间）；适用 GLM-5.3 | 双协议覆盖：chat 协议（原厂区间 [0, 2] 含端点）——工单 A-03 三发复现 temperature=1.5（content="只回复:好"、max_tokens=32，请求体工单原样无 stream 字段）→ 200+choices 非空（正文/finish_reason 留观察——小配额+默认思考计入易 length，K31 域形态非判据），边界轮 2.0（上界端点移入放行；请求对齐 A-03 短形态——content="只回复:好"+max_tokens=32+无 stream 字段，用户指定 2026-11-09）→ 200+choices 非空（正文/finish_reason 留观察，K31 域形态非判据——主判据=2.0 被接受 200），左边界轮 0.0（下界端点——[0, 2] 含 0.0，用户指定 2026-11-09 新增验证，此前下界仅由 -0.5 越界轮间接验证；长形态 content="请用一句话介绍你自己。"+max_tokens=1024）→ 200+choices 非空（正文/finish_reason 留观察——主判据=0.0 被接受 200），越界轮 2.5 与 -0.5（max_tokens=1024——所有轮均须 max_tokens 限制，用户指定 2026-11-09）→ 400+错误体指明参数名 temperature（大小写不敏感）+含上界数字 2（区间痕迹辅助下限口径）；msg 协议（/anthropic/v1/messages，Anthropic 官方区间 [0, 1] 分别校验——A-03 未涉及 msg 维持原口径）——放行轮 temperature=0.5（工单原值 1.5 在该协议官方语义下越界，不可作放行点）与 0.0（下界端点——用户指定 2026-11-09 新增验证，双协议口径一致）→ 200+正文非空+stop_reason 自然结束，越界轮 1.5（工单原值，与 chat 侧同值不同判——验证网关按协议语义分别校验而非一刀切）、2.0 与 -0.5 → 400+错误体指明参数名+含上界数字 1；chat 放行点按 A-03 三发依序复现，其余组合每组合 1 次（K6 先例）；工单原始值原样保留并豁免全局采样覆盖，top_p/seed 未指定不注入，A-03 轮与 chat 2.0 边界轮同形态（max_tokens=32——边界轮用户指定 2026-11-09 对齐，原不传致 2.0 无界生成长尾超时，curl 复核服务端正常），chat 0.0 左边界轮/越界轮长形态 max_tokens=1024（所有轮均须 max_tokens 限制——用户指定 2026-11-09，当前无限制的取 1024），thinking 不传，msg max_tokens 为协议必需字段；每发 60s 硬超时（K32_HARD_TIMEOUT 用例内自定覆盖全局 timeout——小请求正常返回毫秒级-秒级，挂起/严重延迟快速失败：超时即 FAIL 留痕，仅本用例生效不影响他例） | P1 |
| K33 | top_logprobs=5 放行核验（未开 logprobs 也接受，chat+msg 双协议） | 客户问题（工单 P2 A-04，参数校验）：官方行为不变——top_logprobs=5 官方 HTTP 200 接受（未开 logprobs 时也接受）；贵方最新实测（A-04，2026-11-03）chat 三发 top_logprobs=5 单独出现（无 logprobs）全部 400、错误体「top_logprobs is only allowed when logprobs is enabled」（对未开 logprobs 的 top_logprobs 额外拒绝）；整改建议（即预期结果）：按官方行为处理 top_logprobs（未开 logprobs 时也接受）不额外拒绝，若上游确实不支持，错误体应说明能力缺失而非参数非法；用户判定口径（2026-11-06）：top_logprobs=5 不拒绝、按官方 HTTP 200 即可、正文为空不判定失败（R-03 轮移除，仅保留 A-04 请求——用户指定）；适用 GLM-5.3 | 双协议覆盖：chat 协议——A-04 三发复现（top_logprobs=5 单独出现、content="只回复:好"、max_tokens=32，请求体工单原样无 stream 字段）→ 200+choices 非空（正文/finish_reason/logprobs 结构留观察——小配额+默认思考计入易 length，K31 域形态非判据）；msg 协议（/anthropic/v1/messages）无 logprobs 参数语义——A-04 镜像 3 发（top_logprobs 单独出现、content 工单原样、max_tokens=512 套件必需字段值）硬断言统一行为：全部 400 且错误体指明字段（含 'logprobs'，top_logprobs 子串覆盖，能力缺失说明口径——整改建议两分支之一）或全部 200（正文为空不判定失败——用户口径：top_logprobs=5 不拒绝、官方 200 即可，空正文留观察，用户指定 2026-11-06），混现即 FAIL——额外拒绝与行为不统一在两协议均不得复现；A-04 工单三发采集间隔 1s（节奏非判据），复现按套件相邻间隔 3s；max_tokens/thinking/采样参数未指定不传不注入（A-04 复现轮 max_tokens=32 工单原值；msg max_tokens 协议必需） | P2 |
| K34 | 多模态媒体块该拒未拒（msg 侧静默丢弃返回 200）应 400 明确拒绝（chat+msg 双协议） | 客户问题（工单 P2 R-04 补充证据 A-01，多模态）：官方行为 glm-5.3 为非多模态模型——请求携带图片/音频/视频/文档（base64 与 URL 两种载体）必须返回 400，返回 2xx 即不合格；原始问题：msg 协议下返回 200 该拒未拒，媒体块被静默丢弃——prompt_tokens 仅 17-43（媒体未进入分词器）、正文自述『没有收到视频/音频/文档』；同一素材在 chat 协议下渠道返回 400（同一渠道、同一文件、两种协议两种结果）；整改建议（客户给出）：在 /v1/messages → OpenAI 转换层对 media block（video/audio/document）做前置校验，返回 400 并给出明确文案；不得剥离媒体块后继续转发；URL 载体（http/https 媒体链接）同样必须返回 400，不得自行抓取、转文字或降级为纯文本；另外 chat 协议也应该相同的处理；适用 GLM-5.3 | 双协议各 5 发共 10 发（用户指定：message 协议和 chat 协议都要 5 轮请求）：msg 5 发按客户原始记录依序复现（缺陷复现轮）——document×base64（application/pdf）+『文档中的文字是什么?简答。』（媒体块在前——工单原序）、text+audio×base64（audio/wav）『这段音频是什么类型的声音?简答。』（文本块在前——工单原序）、video×base64（video/mp4）+『简要描述视频内容。』、video×url +『简要描述视频内容。』（沿用本仓现有 MDN flower.mp4 地址——工单原 test-videos.co.uk 不复用，用户指定保留现有 URL）、video×base64 +『这段视频前半段的底色和中间显示的数字是什么？后半段的底色和中间显示的数字是什么？按先后顺序一句话回答。』（工单第 5 采集提问原样）；chat 5 发为同素材/同提示词/同块序镜像（整改『chat 协议也应相同处理』一致性核验轮；part 映射：document→file part（file_data data URL）、audio→input_audio、video→video_url（base64 发用 data URL））；媒体数据工单未提供完整 data——代码生成有效 base64（最小 PDF/WAV/MP4 容器，内存生成、不落临时文件；拒绝校验在媒体块类型层不依赖可解码内容；双协议第 3/5 发共用同一生成 MP4）；max_tokens=1024 工单原值（10 发同值镜像豁免注入）；请求体不含 stream 字段（工单原始格式，两协议默认非流式）；硬断言每发：①HTTP 400（200=静默丢弃缺陷复现——A-01 形态留证；2xx 同判；500 等=非合规拒绝）②错误体含对应媒体类型关键词（中英任一命中：document/文档/pdf、audio/音频/语音、video/视频，大小写不敏感——20261104 实测整改错误体为中文，双语匹配（用户指定）；排除通用『模型服务调用失败』缺陷形态）；'text' 痕迹留观察日志；thinking/采样参数未含不注入；相邻间隔 3s | P2 |
| K35 | 关闭思考应按原厂 400 拒绝（enable_thinking=false 与 thinking.type=disabled 双路径，chat+msg 双协议） | 客户问题（工单 P1 R-07 补充证据 A-02 · chat/msg 协议关闭思考的请求被放行，接口协议）：官方行为原厂对关闭思考返回 400（原厂 HTTP 400）；贵方实测（A-02，2026-11-03 采集，2 发均 HTTP 200）：渠道返回 200 并正常出文——chat 发 enable_thinking=false 放行且响应带 reasoning_content（思考仍开启，reasoning_tokens=91）、msg 发 thinking.type=disabled 放行且 content 带 thinking 块（思考仍开启），对照记为 http_status 400→200（HTTP 状态语义）；预期行为（整改）：统一关闭思考的拒绝口径——enable_thinking=false 与 thinking.type=disabled 两条路径均按原厂返回 400，不得一条拒一条放；适用 GLM-5.3 | 按工单 A-02 原始请求 2 发依序复现（双协议两路径——用户指定：两条路径都要按官方行为返回 400，覆盖两种协议）：路径1 chat（/v1/chat/completions 非流式）enable_thinking=false（工单原样：content="23+19 等于多少？" 字符串、max_tokens=512、请求体不含 stream 字段）；路径2 msg（/anthropic/v1/messages，x-api-key + anthropic-version 头——K3 先例）thinking={"type": "disabled"}（工单原样：content="23+19=?" 字符串、max_tokens=512、stream=false 显式携带）；硬断言每路径：HTTP 400（200=放行缺陷复现——A-02 形态：200 且正常出文（思考仍开启）；500 等=非合规拒绝）；错误体参数名痕迹（路径1 enable_thinking/路径2 thinking）留观察不计判据；max_tokens=512 工单 2 发同值（豁免注入）；采样参数未含不注入；相邻间隔 3s | P1 |
| K36 | finish_reason 判定对齐官方（stop 语义——流式/多段/结构化 × 双协议） | 客户问题（工单 P1 R-06，接口协议）：官方行为 finish_reason=stop（20_chat_stream_002 / 20_chat_ms_001 / 20_chat_structured_002 三例）；贵方实测同一请求渠道返回 finish_reason=length，官方返回 stop（三例一致复现）；整改建议：对齐 finish_reason 判定——思考 token 不应把正常结束的请求判成 length 截断；按官方行为进行预期断言（用户指定）；适用 GLM-5.3 | 流式（SSE 收集终止字段与正文增量）、多段（单条 user 消息 content 数组多段文本）、结构化（chat response_format=json_object / msg 无该参数按 K31 先例 prompt 引导）三种请求形态 × chat+msg 双协议各 1 发（共 6 发）；硬断言每形态 × 每协议：终止语义对齐官方——chat finish_reason=='stop' / msg stop_reason=='end_turn'（Anthropic 协议自然结束语义——msg 侧的 stop 等价；length/max_tokens=缺陷复现：思考 token 计入判定把正常结束的请求误判截断）+ 正文非空（正常结束的佐证；正文空+length 为 K31 思考耗光形态，非本例口径）；max_tokens=512（工单未附原始 payload——适中值：正文远低于配额而计入思考的实现易触顶误判，对判定语义敏感且不致正文真实截断）；thinking/采样参数未指定不传不注入；相邻间隔 3s | P1 |
| K37 | n=2 请求应 400 拒绝且不挂死（返回提示信息） | 客户问题（工单 P0，n=2 请求挂死）：贵方实测无响应直至超时——参数电池 3/3 轮 TimeoutError（已重试 1 次仍超时）、协议电池 2 例 ReadTimeout、直连 300s 超时，挂死同时导致模块 4 的 n=2 探针被记为『无效』而未计失败；官方行为原厂 n=2 HTTP 200（返回 1 个 choice）；客户明确需求（2026-11-06，契约口径）：当 n=2 时 400 拒绝，并返回相应的提示信息，但不能卡死（示例响应：HTTP 400 {"code":1210,"message":"参数有误：glm-5.3 仅支持 n=1，收到 n=2 (request id: ...)"}）——客户明确需求优先于官方对齐（用户指定按新契约断言，替代原官方 200+单 choice 口径）；适用 GLM-5.3 | chat 单协议 2 发对齐工单口径（055/056 两次独立采集，非重试；n 为 OpenAI 协议参数、msg 无 n 语义——工单证据仅 chat，msg 未知参数行为由 K33/K35 覆盖）；单发直发不重试（重试掩盖挂死证据且超时等待翻倍），requests timeout=30s 硬超时；硬断言每发：①30s 内返回（超时即 FAIL 挂死复现——纠正『无效不计失败』漏报形态）②HTTP 400（200 放行=未按客户契约拒绝；500 等=非合规拒绝）③提示信息指明 n 参数限制（响应体合法 JSON、message 非空且含 "n=1"/"n=2" 子串，大小写不敏感——客户示例：参数有误：glm-5.3 仅支持 n=1，收到 n=2）；工单原值原样保留（"说一句话。"/max_tokens=16/n=2——豁免注入）；错误码 code（如 1210——平台错误码口径不硬绑）/request id/elapsed 留观察（字节缓流形态人工分派）；thinking/采样参数未含不注入；相邻间隔 3s | P0 |
| K38 | max_completion_tokens 别名单 token 请求不挂起（与 tokens 主路径同延迟水平）（暂挂 SKIP：官方复测亦超时——判定基线失效待口径澄清，用户指定 2026-11-06） | 客户问题（工单 A-A01，异常）：官方判定通过——max_completion_tokens 别名为单 token 请求，被接受并按 max_tokens 语义立即截断返回；贵方实测客户原始请求 1 发即挂起——180s 请求超时、无响应（HTTP 0，采集未落盘）；预期行为（整改）：不得触发 180s 级挂起；需与 tokens 主路径同延迟水平；适用 GLM-5.3 | chat 单协议 2 发（别名轮工单原样 1 发对齐工单口径 + 主路径轮同 prompt max_tokens=1 对照基线 1 发；max_completion_tokens 为 OpenAI 别名字段、Anthropic /v1/messages 无该字段——max_tokens 即协议必需主路径字段，msg 未知参数行为由 K33/K35 覆盖）；别名轮请求体工单原样（单 user "Write a long essay about turbines."、max_completion_tokens=1，字段序 model/messages/max_completion_tokens，无 stream 字段），模型名由环境注入，采样参数原始未指定——保持不注入；单发直发不重试（重试掩盖挂起证据且超时等待翻倍），requests timeout=30s 硬超时；硬断言：别名轮 30s 内返回（超时即 FAIL 挂起复现——工单 180s 无响应形态）+ HTTP 200（官方判定通过）+ 响应体合法 + usage.completion_tokens<=2（别名生效——单 token 截断；字段被丢弃则长文数百 token，usage 未携带时判据降级为延迟判据留观察）；主路径轮 30s 内返回 + 200；同延迟水平判据：别名 elapsed <= 主路径 elapsed×3+10s（容网络抖动）；finish_reason/正文留观察（1 配额默认思考计入易空正文+length——K31 域形态非本例判据）；字节缓流形态留观察人工分派（K37 口径）；相邻间隔 3s | P0 |
| K39 | 历史 assistant 消息 reasoning/reasoning_content 双字段共存兼容核验（同值/异值 × 两字段序） | 客户问题（工单 AGDC2-47，接口协议）：官方行为（AGDC2-47 测试资料·官方 API 验证结论，2026-11-05 Kimi K3 官方端点）——同一历史 assistant 消息同时包含 reasoning 与 reasoning_content，无论内容相同或不同、哪个字段在前均接受，14 组合（字段变体 × 默认/关闭思考）全部 HTTP 200、finish_reason=stop、回答 3；贵方实测：双字段共存即 HTTP 400、错误码 json_parse_error、提示 duplicate field reasoning_content——两字段值相同或不同均报错，单字段（仅 reasoning 或仅 reasoning_content）调用成功，客户生产调用产生较多报错；预期行为（整改）：双字段共存无论值相同或不同、字段顺序如何均不得 400，应正常请求成功；适用 GLM-5.3 与 Kimi K3（双 marker GLM53+KimiK3，用户指定双模型覆盖） | chat 单协议 4 发（相邻间隔 3s；用户指定：只测双字段共存场景——单字段/无字段场景不测；调整两字段顺序 × 覆盖同值/异值），同一三消息结构（AGDC2-47 官方验证请求原样：user "What is 1 + 1? Reply with only the number." / assistant content="2"+双思考字段 / user "Add 1 to the previous answer. Reply with only the number."），请求体官方验证原样（字段序 model/stream/max_tokens=512/messages，stream=false，thinking 默认模式不传），模型名由环境注入，采样参数官方验证请求未含——保持不注入；场景：同值/reasoning 在前、同值/reasoning_content 在前（两字段均 "1 + 1 = 2."）、异值/reasoning 在前、异值/reasoning_content 在前（reasoning="Compute the sum."、reasoning_content="The answer is two."）；硬断言每发（任一失败即 FAIL 报告场景序）：HTTP 200（400 json_parse_error/duplicate field reasoning_content=缺陷复现——同条消息两思考字段被解析层视为同字段别名而拒绝）+ 响应体合法 JSON + choices 非空 + 正文非空（空正文+finish=length 留观察——512 预算默认思考计入耗尽属 K31 域形态；空正文且 finish≠length 即 FAIL）；finish_reason/回答含 3（官方验证回答为 3——生成质量非本例判据）/正文长度留观察；关闭思考模式不测（官方双模式均 200 证明字段兼容性与模式正交；K35 已确立网关对关闭思考 400 拒绝口径——另一缺陷域）；chat 单协议（Anthropic /v1/messages 无 reasoning 字段形态——思考经 thinking content block 承载，msg 未知参数行为由 K33/K35 覆盖） | P0 |

| K40 | thinking enabled 响应 reasoning_content 字段稳定性核验（三轮 × 每轮 10 并发统一携带） | 客户问题（新工单，响应字段稳定性）：请求体 max_tokens=16000 + 单 user 消息「证明：对于任意正整数n，n^3-n能被6整除」+ thinking={"type": "enabled"}（客户环境模型 GLM-5.3-jy-b）——响应有时带、有时不带 reasoning_content 字段，不稳定，客户生产调用产生较多困扰；预期行为（整改）：所有请求统一携带 reasoning_content | 三轮 × 每轮 10 并发（轮内 ThreadPoolExecutor 10 workers 同拍齐发——E5 并发稳定性先例；轮间串行——每轮收齐后再开下一轮；用户指定 2026-11-09：测试分为三轮、每轮 10 并发，所有轮的所有请求 reasoning_content 统一才算通过；同日调整确认：每轮结束收集一次，任一轮次不一致即失败中止——避免后续轮次浪费）验证统一性，请求体工单原样（max_tokens=16000、thinking.type=enabled、单 user 消息；stream 工单未含——不传，非流式默认；采样参数未含——不注入；模型名由环境注入，用户确认——GLM-5.3-jy-b 为客户内部档位名）；逐轮判定（每轮收齐即断言该轮，任一轮次失败即用例失败并中止后续轮次——用户指定：避免无效轮次消耗）：断言1 该轮 10/10 HTTP 200（非 200/发送异常全量列出）；断言2 该轮 10/10 响应体合法 JSON+choices 非空；断言3 该轮 10/10 choices[0].message.reasoning_content 存在且非空（「统一」口径=字段层面全部携带，用户确认——空字符串同样属「没有」，内容逐字一致不作要求；缺失/空串清单全量输出=缺陷复现证据，如「第 2 轮 8/10 携带，缺失 #R2-3/#R2-7」）；观察（不计判据）：逐轮+整体 finish_reason/正文长度/思考长度分布/耗时；超时沿用全局（工单未涉及超时语义）；chat 单协议（客户请求为 chat 形态，缺陷为 chat 响应字段——Anthropic msg 思考经 thinking content block 承载，无 reasoning_content 字段形态）；GLM-5.3 专用（工单模型 GLM-5.3-jy-b 为 GLM-5.3 档位变体，缺陷为响应字段生成逻辑，无模型分支） | P1 |

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
- 工单原始请求含 `temperature=0.1`——原样保留（test_k 整套件保持
  原始测试参数，不参与全局采样覆盖；top_p/seed 工单未指定，
  不注入）
- 不进 smoke 集（K 类用例均不进——用户指定）

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
- 工单原始请求含 `temperature=1`、`top_p=0.95`——原样保留
  （test_k 整套件保持原始测试参数，不参与全局采样覆盖；
  seed 工单未指定，不注入）
- 不进 smoke 集（K 类用例均不进——用户指定）

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
- 不进 smoke 集（K 类用例均不进——用户指定）

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
- `chat_completion` 封装会固定附带默认 `max_tokens=2048`（无法省略），
  破坏"不传 max_tokens"的前提——故按 K3 先例手工构造 payload 直发
- 客户原始 prompt 未提供，选用常规开放问题，验证正常生成即可

**断言**（fp=0 预期结果，每次请求独立断言）：
1. 响应时间预算内返回——专用预算客户端（E8 先例：`timeout=120` +
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
  （360s），避免拖慢冒烟套件（K 类用例均不进 smoke 集——用户指
  定）
- 对照场景（fp=0 不传 max_tokens）按决策跳过：修复契约明确后无需对照隔离，
  单一场景即可判定
- 若平台未来将契约改为 400 拒绝（而非钳制），本用例会在"请求失败
  HTTP 400"处 FAIL，需同步调整

**注意事项**：
- 修复方式为静默钳制（非 OpenAI 官方语义——官方允许 -2 并会放大重复），
  本用例编码的是平台契约；F 类 API 兼容性如需覆盖该语义差异另行评估
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
- 不进 smoke 集（K 类用例均不进——用户指定；单次数秒内返回，
  无 K4 的长预算风险）

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
- **不进 smoke 集**（K 类用例均不进——用户指定；4 次请求均为数
  秒级（2 次生成 + 2 次快速 400），无 K4 的长预算风险）

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
  test_k 整套件保持原始测试参数——全局 `--sampling-params` 温度
  覆盖对 K 用例不生效，档位对比前提不受影响
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

### test_required_chitchat_calls_tool (K8)

**背景**：客户工单原始问题：`tool_choice=required` + 闲聊
"Reply with exactly: OK"（无工具意图）下不发起工具调用——
tool_calls 键缺失、finish=length、completion_tokens 恒被吃满
max_tokens（关思考 1000/3000 级别均如此）、正文仅 "OK"、耗时
~15.6s（正常 ~1.5s，双峰）；开思考下 reasoning 消耗远小于预算
但整体仍被吃满（mt=3000 仍不调）。预期（工单）：finish 应为
tool_calls 而非 length、关思考 ct 应较小、开思考 rt 应 <
max_tokens、正文应正常收到调用工具的响应信息。

**请求构造**：
- tools=[get_weather(city)]（获取北京天气的工具）+
  `tool_choice="required"`，user 提示词 "Reply with exactly: OK"
  （客户原始口径，无工具意图——缺陷触发条件）
- 轮次（客户实测级别）：关思考 mt=1000、关思考 mt=3000、开思
  考 mt=3000
- temperature 按网关档位联动约束：disabled→0.6、enabled→1（非
  该值被 400 拒绝，无法构建场景）
- 非流式手工 payload 直发（需 tools/tool_choice/max_tokens/档位
  温度——精确控制请求字段集，wrapper 会固定附带 max_tokens/stream
  等默认字段）

**断言**（硬）：
1. 每轮 HTTP 200 + choices + usage 存在（ct 判定数据源）
2. tool_calls 存在且为 get_weather 函数调用（type=function、
   name=get_weather）、arguments 为合法 JSON（city 值不限定）
3. `finish_reason == "tool_calls"`（而非 length——length 即 token
   预算被消耗殆尽的缺陷形态，关/开思考均不允许）
4. `ct < max_tokens`（关思考下应较小；缺陷形态为 ct 恒吃满预算）
5. 开思考：`rt < max_tokens`（思考不吃完预算；rt 双拼写兼容）

**判定矩阵**：
- 任一轮非 200 / 缺 choices / 缺 usage / 缺 completion_tokens →
  FAIL（判定数据源被破坏）
- 任一轮 tool_calls 缺失 / finish≠tool_calls / ct≥max_tokens /
  （开思考）rt≥max_tokens 或 rt 未上报 → FAIL（缺陷形态）
- 全部轮满足 → PASS

**设计决策记录**：
- **P1（按客户工单）**
- **mt 级别**：关思考 1000/3000、开思考 3000——客户工单实测
  级别（官方行为对照级别 256/2000 由 K9 验证，两用例同场景不
  同级别）
- **耗时不断言**：缺陷轮 15.6s 级 vs 正常 1.5s 级双峰仅日志留
  痕——finish 断言已覆盖其缺陷形态，绝对耗时受网络抖动影响易
  误报
- **不进 smoke 集**：缺陷轮 15.6s 级长耗时 + 缺陷概率性

**注意事项**：
- 修复方向为上游 required 强制调用；K8/K9 同场景不同级别互补，
  上游只修部分级别时另一用例仍可拦截

### test_required_chitchat_official_behavior (K9)

**背景**：官方 api.moonshot.cn/kimi-k3 实测：闲聊 "Reply with
exactly: OK" + required → finish=tool_calls、强制返回 get_weather
调用（city 瞎猜 London/UNKNOWN——值不限定）、reasoning 仅 38
token——符合 [OI] required「必须发起至少一次工具调用」规范。
Alaya 同场景缺陷：finish=length、reasoning 吃满 256/2000 预算、
tool_calls=None；有工具意图时（北京天气）两站一致正常。

**请求构造**：
- tools=[get_weather(city)]、`tool_choice="required"`、user 提示
  词 "Reply with exactly: OK"（客户原始口径，无工具意图）
- 轮次（镜像 Alaya 缺陷实测级别）：关思考 mt=256、关思考
  mt=2000、开思考 mt=256、开思考 mt=2000
- temperature 按网关档位联动约束：disabled→0.6、enabled→1
- 非流式手工 payload 直发（同 K8）

**断言**（硬）：
1. 每轮 HTTP 200 + choices + usage 存在
2. tool_calls 强制返回且为 get_weather 函数调用、arguments 为合
   法 JSON（city 值不限定——官方亦瞎猜）
3. `finish_reason == "tool_calls"`（官方行为；而非 length）
4. `ct < max_tokens`（预算不被吃满）
5. 开思考：`rt < max_tokens`（官方同场景 reasoning 仅 38；缺陷
   形态为吃满预算；rt 双拼写兼容）

**判定矩阵**：
- 任一轮 tool_calls 缺失 / finish≠tool_calls / ct≥max_tokens /
  （开思考）rt≥max_tokens 或 rt 未上报 → FAIL（Alaya 缺陷形态：
  finish=length、reasoning 吃满预算、tool_calls=None）
- 全部轮满足 → PASS（对齐官方行为）

**设计决策记录**：
- **P1（按客户工单）**
- **以官方行为为预期**：required「必须发起至少一次工具调用」，
  官方闲聊场景亦强制返回 get_weather（city 瞎猜不限定）
- **mt 级别 256/2000**：镜像 Alaya 缺陷实测级别（与 K8 客户工单
  级别 1000/3000 同场景互补——上游只修部分级别时另一用例仍可
  拦截）
- **耗时不断言**：同 K8 理由（finish 断言已覆盖缺陷形态）
- **不进 smoke 集**：缺陷轮 15.6s 级长耗时 + 缺陷概率性

### test_tool_choice_four_modes_support (K10)

**背景**：客户问题（AGDC2-15）：OpenAI 协议 tool_choice 让模型
在准备工具调用时按请求指定的类型/模式生成调用（Agent 自定义
工具场景）；上线前版本未指定模型专属的工具调用格式解析器，
GLM-5.3-Flash 不支持该语义。修复：Worker 侧指定生成解释器，
支持渲染字段至模型聊天模版（zai-org/GLM-5.3-Flash 的
chat_template.jinja）。需支持四种模式：auto（模型自主决定）、
required（必须调用工具）、named（必须调用指定工具）、none
（禁止调用工具）。

**请求构造**：
- 原始验证脚本口径（glm53_flash_suite 的 tool_auto/tool_
  required/tool_named/tool_none.sh）：max_tokens=2048、非流式、
  不传 thinking（GLM-5.3-Flash 默认思考，参考结果含
  reasoning_content，不做思考断言）
- 采样参数豁免（用户口径）——原始脚本指定 temperature=0，原样
  保留，不受全局 SAMPLING_PARAMS（Jenkinsfile，经
  `--sampling-params`）覆盖；top_p/seed 脚本未指定，不注入；
  reasoning_effort 不在此列，保持原始口径不传
- 工具两个：get_weather(city) + get_current_time(timezone)
  （两个工具使 named 模式可判定）
- 轮次：auto/required/none 用工具意图提示词 "Call get_weather
  for Beijing and report the temperature."；named 指定 get_
  current_time 且提示词保持原始口径的天气意图 "Look up Beijing
  weather."——named 与提示词自然意图不同向，若 named 语义未
  生效（被忽略按 auto 处理）模型会按意图调 get_weather，从而
  检出「指定工具未被强制」

**断言**（硬）：
1. 每轮 HTTP 200 + choices 存在（该模式不被支持即非 200）
2. auto/required：tool_calls 存在且形状合法（type=function、
   arguments 合法 JSON）、finish_reason=="tool_calls"
3. named：tool_calls 存在且 function.name==指定工具
   （get_current_time）、finish_reason=="tool_calls"
4. none：tool_calls 缺失、content 非空、finish_reason=="stop"

**判定矩阵**：
- 任一轮非 200 / 缺 choices → FAIL（该模式不被支持）
- auto/required/named 轮 tool_calls 缺失 / 形状异常 / finish≠
  tool_calls → FAIL（模式语义未生效）
- named 轮调用的不是指定工具 → FAIL（named 强制语义未生效）
- none 轮出现 tool_calls / 正文为空 / finish≠stop → FAIL（none
  语义未生效）
- 全部轮满足 → PASS

**设计决策记录**：
- **P0（按客户工单，AGDC2-15）**
- **采样参数豁免（用户口径）**：test_k 整套件保持原始测试参数
  （`conftest.py` 模块级规则 `RAW_SAMPLING_EXEMPT_FILES`）——
  原始脚本指定 temperature=0，原样保留，不受全局
  SAMPLING_PARAMS 覆盖；top_p/seed 脚本未指定，不注入；
  reasoning_effort 不在 SAMPLING_PARAMS 内，保持原始口径不传
- **named 判定设计**：指定与提示词意图不同的工具（提示词为天
  气意图、named 指定 get_current_time）——原始脚本 named 与意
  图同向（named=get_weather+天气提示词），无法区分「named 生
  效」与「named 被忽略后按意图调用」；不同向设计使 named 未
  生效时直接被检出
- **auto 断言依据**：提示词为明确的工具意图（原始脚本同款），
  auto 下模型应发起调用；参考结果（results/tool_auto.json）
  亦为 tool_calls
- **usage 仅日志**：原始脚本未做预算断言，本用例测模式支持，
  不引入无关断言
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 修复方向为 Worker 侧生成解释器；四模式任一不支持即 FAIL
- Kimi K3 基线：2026-10-26 staging（nvidia-B300）实测 required 轮
  HTTP 500 `prefill_internal_error`（"Kimi K3 required tool call
  is missing or incomplete"）——该 FAIL 为 kimi-k3 待修复基线；
  auto 轮通过（默认思考、响应含 reasoning_content，不做思考断
  言）
- marker：`GLM53FLASH` + `KimiK3`（K 套件按模型分组标记）

### test_response_format_three_modes_support (K11)

**背景**：客户问题（AGDC2-16）：OpenAI 协议 response_format 让
模型按指定格式输出（Agent 场景）；DingoRouter 不支持该结构化输
出语义。修复：Router 侧支持结构化生成语义并实现语义转发至引
擎。需支持三种模式：json_object（输出为合法 JSON 对象）、
json_schema（输出符合指定 JSON Schema）、text（纯文本，协议默
认）。

**请求构造**：
- 原始验证脚本口径（glm53_flash_suite 的 response_json_object/
  response_json_schema.sh）：temperature=0、max_tokens=2048、
  非流式、不传 thinking；采样参数豁免——原始脚本指定
  temperature=0 原样保留，top_p/seed 未指定不注入
- json_object 轮：`response_format={"type":"json_object"}`，提
  示词 "Output a JSON object with fields city=Beijing and
  value=17. No markdown."
- json_schema 轮：`response_format={"type":"json_schema",
  json_schema:{name:"weather", strict:true, schema:{city:
  string, temperature:number, required, additionalProperties:
  false}}}`，提示词 "Give estimated temperature for Beijing
  as a JSON object matching schema."
- text 轮：`response_format={"type":"text"}`（协议默认模式，
  原始脚本未单测，按需补齐）

**断言**（硬）：
1. 每轮 HTTP 200 + choices 存在（该模式不被支持即非 200）
2. 正文非空、finish_reason=="stop"（参考结果均自然结束）
3. json_object：json.loads(正文) 为 dict（对齐原始脚本 jq 校验
   `fromjson | type=="object"`）
4. json_schema：json.loads(正文) 为 dict 且 city 为字符串、
   temperature 为数值（非 bool）、键集合恰为 {city, temperature}
   （对齐原始脚本 jq 校验）
5. text：正文非空（纯文本语义，不强制 JSON）

**判定矩阵**：
- 任一轮非 200 / 缺 choices → FAIL（该模式不被支持）
- 任一轮正文为空 / finish≠stop → FAIL
- json_object/json_schema 轮正文不可解析为 JSON 对象 → FAIL
  （结构化输出语义未生效）
- json_schema 轮键集合/字段类型不符 schema → FAIL（schema 约束
  未生效）
- 全部轮满足 → PASS

**设计决策记录**：
- **P0（按客户工单，AGDC2-16）**
- **口径对齐原始脚本**：json_object/json_schema 轮的提示词、
  response_format、jq 校验逻辑均按 response_json_object.sh /
  response_json_schema.sh 原样还原
- **text 轮补齐**：原始脚本未单测 text（协议默认模式），按用户
  要求补齐支持验证——断言保持宽松（正文非空+自然结束），不强
  制「非 JSON」反向断言（模型输出什么纯文本均合法）
- **usage 仅日志**：原始脚本无预算断言，不引入无关断言
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 修复方向为 Router 侧结构化生成语义转发；三模式任一不支持即
  FAIL
- marker：`GLM53FLASH`（K 套件按模型分组标记）

### test_reasoning_effort_levels_support (K12)

**背景**：客户问题（AGDC2-17）：GLM-5.3-Flash 使用 GLM 自己的聊
天模版，字段为 reasoning_effort 且放在 chat_template_kwargs 里；
而 OpenAI 协议/参考脚本将其放在顶层。Router 需要在 OpenAI 协议
外层捕获该字段并传给引擎。修复：Router 侧支持语义转发。需支持：
low/high/max/空（空=不发送该字段，默认档），且不管
reasoning_effort 放在顶层还是嵌套在 chat_template_kwargs 里，
请求都能被正常接受和处理并输出正常响应，否则用例失败。

**请求构造**：
- 原始验证脚本口径（glm53_flash_suite 的 reasoning_low/
  reasoning_high/reasoning_max.sh）：temperature=0、
  max_tokens=2048、非流式、不传 thinking、顶层
  `reasoning_effort`、`chat_template_kwargs={"clear_thinking":
  true}`（原始脚本原样保留）；采样参数豁免——原始脚本指定
  temperature=0 原样保留，top_p/seed 未指定不注入
- 嵌套放置（GLM 聊天模版原生口径）：`reasoning_effort` 放进
  `chat_template_kwargs`（与 clear_thinking 并列），不发送顶层
  reasoning_effort
- 提示词 "Explain why 17*19=323 with intermediate reasoning if
  available."（原始脚本口径，各轮相同——放置与档位为唯一变量）
- 空档：不发送 reasoning_effort 字段（原始脚本无对应档，按需补
  齐；两种放置口径下同构）

**轮次矩阵**（2 放置 × 4 档 = 8 轮）：

| # | 放置 | reasoning_effort |
|---|------|------------------|
| 1-4 | 顶层 | low / high / max / 空 |
| 5-8 | 嵌套 chat_template_kwargs | low / high / max / 空 |

**断言**（硬）：
1. 每轮 HTTP 200 + choices 存在（该放置/档位不被支持即非 200）
2. 正文非空、finish_reason=="stop"（参考结果均自然结束）

**判定矩阵**：
- 任一轮非 200 / 缺 choices → FAIL（该放置/档位不被支持）
- 任一轮正文为空 / finish≠stop → FAIL
- 全部轮满足 → PASS

**设计决策记录**：
- **P0（按客户工单，AGDC2-17）**
- **双放置覆盖**：原始问题即"GLM 模版将 reasoning_effort 放在
  chat_template_kwargs 里，而参考脚本放在顶层"——两种口径都需
  被正常接受和处理，缺一即 FAIL
- **档位效果仅观测**：档位对思考的实际影响（rt/reasoning 长度）
  仅日志留痕——参考脚本未做档位间断言，思考长度为模型行为质量
  （非确定性行为），不做硬断言
- **空档补齐**：原始脚本仅覆盖 low/high/max，空档（不发送该字
  段，默认行为）按用户要求补齐
- **usage 仅日志**：原始脚本无预算断言，不引入无关断言
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 修复方向为 Router 侧语义转发；任一放置/档位不支持（400/500）
  即 FAIL
- Router 若静默剥离该字段（请求仍 200），响应侧不可观测区分——
  各轮 rt/reasoning 长度日志可作人工核查线索
- marker：`GLM53FLASH`（K 套件按模型分组标记）

### test_stop_sequence_prefix_leak (K13)

**背景**：客户问题：stop=["橘子"] 的流式请求，期望输出 "苹果、香
蕉、"（正文在停止词处截断、不含停止词），实际输出 ">苹果、香蕉、"
——被截断正文前面多输出了一个 ">" 符号（stop 截断逻辑把停止词
的某个字符/片段泄漏到了正文开头）。缺陷为通用 stop 截断逻辑，
同时适用于 GLM-5.3-Flash 与 KimiK3。

**请求构造**（按客户原始请求体还原）：
- 提示词 "请依次说出：苹果、香蕉、橘子、西瓜、葡萄。每个水果之
  间用顿号分隔，不要省略。"
- `stop=["橘子"]`、`stream=true`
- glm-5.3-flash（模型名含 flash）：另传 `thinking={"type":
  "enabled"}`、`reasoning_effort="low"`（客户原始请求体口径）
- KimiK3：不传 thinking/reasoning_effort（按 K5 口径：网关对
  thinking 参数兼容性未知，缺陷本身与其无关）
- 其余采样参数（temperature/top_p/seed）不发送（客户原始请求体
  即如此；test_k 整套件保持原始测试参数——无全局注入口；
  手工 payload 直发）

**断言**（硬）：
1. SSE 解析成功且有正文增量（收到 content delta）
2. finish_reason == "stop"（stop 序列触发，非 length）
3. 合并正文严格等于 "苹果、香蕉、"（多余前缀如 ">"、停止词泄
   漏、未截断均 FAIL）
4. 正文不含停止词 "橘子"（遵循 stop 语义）

**判定矩阵**：
- 无 SSE 事件 / 无正文增量 → FAIL
- finish ≠ stop → FAIL（stop 序列未触发）
- content ≠ "苹果、香蕉、" → FAIL（核心缺陷检出：多余前缀/停
  止词泄漏/未截断）
- content 含 "橘子" → FAIL
- 全部满足 → PASS（修复后预期）

**设计决策记录**：
- **P0**（客户报障，逐字符契约明确）
- **双标记**：`GLM53FLASH` + `KimiK3`（缺陷为通用 stop 截断逻
  辑，两个环境均需回归）
- **严格相等断言**：客户期望输出完全确定（">苹果、香蕉、" 对
  "苹果、香蕉、"），逐字符比对最敏感；温度未固定（客户原始请
  请求体不发送采样参数），水果列表+顿号结构在正常采样下稳定
  截断于停止词前
- **thinking 参数差异化**：glm-5.3-flash 按客户原始请求体传
  thinking+reasoning_effort；KimiK3 按既有 K5 口径不传
- **usage 仅日志**：客户问题与预算无关
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 若 FAIL 形态为 "苹果、香蕉、橘子、..."（未截断）说明 stop 未
  生效（另一种缺陷形态，同样 FAIL）
- 若 FAIL 形态为多余前缀（如 ">"），即客户原始缺陷
- marker：`GLM53FLASH` + `KimiK3`（K 套件按模型分组标记）

### test_orphan_tool_message_rejected (K14)

**背景**：客户问题：messages 中 tool 角色消息前无带 tool_calls 的
assistant 消息（孤儿 tool 消息，且请求未定义任何 tools），属协议
非法请求，网关应做校验并返回 400 Bad Request；实际返回 200 放行，
模型把孤儿 tool 消息当普通上下文推理（流式输出 reasoning_content/
正文）。

**请求构造**（按客户原始请求体还原）：
- messages：user "今天天气怎么样？" 后直接跟 tool 消息
  （`tool_call_id="call_abc123"`、`content="{\"weather\":\"晴\"}"`），
  中间无 assistant tool_calls
- `stream=true`；不定义 `tools`；不传 thinking/采样参数（客户原
  始请求体即如此；test_k 整套件保持原始测试参数——无全局注入
  口；手工 payload 直发）
- GLM-5.3 与 GLM-5.3-Flash 请求完全一致（原始请求体无模型专属字
  段，仅 model 名不同）

**断言**（硬）：
1. HTTP 400（Bad Request——协议非法请求必须被拒绝）

**判定矩阵**：
- HTTP 400 → PASS（修复后预期）
- HTTP 200（放行并生成）→ FAIL（核心缺陷检出；测试取样至多 8 个
  SSE 事件留证 reasoning/正文预览后失败）
- 其他状态码 → FAIL（非预期拒绝形态）

**设计决策记录**：
- **P0**（协议校验缺失，客户报障）
- **双标记**：`GLM53FLASH` + `GLM53`（缺陷为通用消息校验逻辑，
  两个环境均需回归）
- **严格 400**：客户口径 "期望 HTTP 400"；422 等其他 4xx 属不同
  修复实现，如网关改用其他状态码需同步调整本断言
- **取证设计**：缺陷形态（200 放行）下先取样 SSE 事件再 FAIL，
  失败信息中直接携带模型"把孤儿 tool 消息当上下文推理"的证据
  （对齐客户原始日志中 reasoning_content 逐段推理的现象）
- **usage 仅日志**：客户问题与预算无关
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 修复方向为网关/引擎侧消息协议校验（tool 消息必须跟随带
  tool_calls 的 assistant 消息）
- marker：`GLM53FLASH` + `GLM53`（K 套件按模型分组标记）

### test_short_input_prefix_cache_threshold (K15)

**背景**：客户问题（平台原始验证信息）：短文本缓存命中率不达标，根
因推理引擎默认前缀缓存分块撮合的最小可缓存块长过大（vLLM 默认 640
token 量级），客户输入低于该块长（如 625 token）时完全不缓存，命中
率远低于目标；平台修复为细粒度前缀匹配（sglang `--prefix-match-
unit 64` / vLLM 对应参数调小，单一缓存块内补充更细粒度的缓存点）。

**请求构造**（OpenAI 协议 `/v1/chat/completions`，非流式）：
- 测试点1 内容：K15_MID_UNIT（"本知识库涵盖产品规格、接口说明与
  常见问题处理流程。"）× 20 ≈ 480 中文字符（≈280-320 tok，落于
  64 < N < 640 区间中部，两侧留裕量）
- 测试点2 内容：K15_SHORT_CONTENT（"请简要介绍北京的历史文化背景
  与著名景点。"）≈ 21 字符（含对话模板开销 < 64 tok）
- `max_tokens=16`；不发送采样参数（test_k 整套件保持原始测试参
  数——无全局注入口；手工 payload 直发）
- 每个测试点相同请求连发两次（第 1 次建缓存、第 2 次测命中）

**断言**（硬）：
1. 前提自检：服务端 `usage.prompt_tokens` 落在对应区间（64 < pt1 <
   640、pt2 < 64）——内容长度估算漂移导致前提失效时 FAIL 并提示
   调整常量
2. 测试点1：第 2 次请求 `cached_tokens > 0`（修复后应正常缓存；
   修复前 640 粒度下为 0——即客户 625 tok 不缓存场景）
3. 测试点2：第 2 次请求 `cached_tokens == 0`（低于最细匹配粒度
   64 tok 不可缓存）

**取值约定**：cached_tokens 取 `usage.prompt_tokens_details.
cached_tokens`（OpenAI 标准位置），兼容 `usage.cached_tokens` 拼
写；GLM-5.3 与 GLM-5.3-Flash 请求完全一致（仅 model 名不同）。

**设计决策记录**：
- **P0**（缓存核心功能失效，客户报障）
- **双标记**：`GLM53` + `GLM53FLASH`（前缀缓存为引擎/推理平台通
  用能力，两个环境均需回归）
- **协议选择**：原始验证信息来自 /v1/messages 与 /v1/responses
  协议的 usage 统计，本用例统一走 OpenAI /v1/chat/completions 并
  取 prompt_tokens_details.cached_tokens（框架主协议，便于 CI 全
  量回归）
- **双向断言**：既验证修复（短输入应缓存）也验证粒度下限（<64 不
  缓存），避免"全部 cached=pt"的过拟合假实现
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 修复前 640 粒度下测试点1 即 FAIL（cached=0），测试点2 恒 PASS
- 若实际 prompt_tokens 接近区间边界（640 或 64），优先调整内容
  常量而非放宽断言
- marker：`GLM53` + `GLM53FLASH`（K 套件按模型分组标记）

### test_prefix_cache_hit_rate_threshold (K16)

**背景**：客户问题（平台原始验证信息）：短文本缓存命中率不达标——
修复前固定前缀每轮 cached=7680/input=8693（88.35%）、多轮上下文
87.16%，均低于 90% 目标；根因 640 token 分块粒度将共享前缀截断
（8192 → 12×640=7680，损失 512），细粒度匹配（64）后固定前缀命中
率应 ≈8192/8693≈94.2% ≥ 90%。

**请求规模推算**（由原始信息反推，对齐客户场景）：
- 共享前缀 ≈8192 tok → K16_PREFIX_TEXT ≈12800 中文字符
  （K16_PREFIX_FILLER_UNIT 41 字符 × 313 = 12833 字符，中文 ~1.55 字符/tok）
- 每轮新增问题 ≈501 tok（input 8693 − 前缀 8192）→ 每轮
  ~780 字符（问题开头 ~60 字符 + K16_QUESTION_FILLER 64 字符 × 11）
- 轮次：10 轮，排除第 1 轮预热，实测 9 轮（对齐原始验证口径）

**请求构造**（OpenAI 协议 `/v1/chat/completions`，非流式）：
- 模式1 固定前缀：10 轮独立请求 `[system K16_PREFIX_TEXT,
  user question_for(k)]`——每轮问题以轮次号开头保证前缀在问题
  开头处分叉，user 内容每轮唯一
- 模式2 多轮上下文：单会话 history 逐轮追加（system 前缀 + 历史
  问答 + 新问题），问题带 "本轮请仅回复：收到。"（控制 assistant
  回复极短、不放大每轮新增 token），assistant 回复取实际响应
  content
- `max_tokens=16`；不发送采样参数（test_k 整套件保持原始测试参
  数——无全局注入口；手工 payload 直发）

**断言**（硬）：
1. 固定前缀模式：Σcached_tokens / Σprompt_tokens（实测 9 轮）
   ≥ 90%，FAIL 信息携带对照原始验证 88.35%<90%
2. 多轮上下文模式：Σcached_tokens / Σprompt_tokens（实测 9 轮）
   ≥ 90%，FAIL 信息携带对照原始验证 87.16%<90%

**取值约定**：同 K15——`usage.prompt_tokens_details.cached_tokens`
优先，兼容 `usage.cached_tokens`；zero_cache_rounds（零命中轮次）
仅日志留痕；usage 其余字段仅日志。

**设计决策记录**：
- **P0**（缓存命中率低于承诺目标，客户报障）
- **双标记**：`GLM53` + `GLM53FLASH`（同 K15，两个环境均需回归）
- **推算口径**：640 粒度下每轮命中 7680 = 12×640 反推前缀为
  8192 tok（截断损失 512）——由此构造 ~12800 字符前缀，使修复
  前后命中率分别落在 90% 阈值两侧（88.35% vs 94.2%），确保断言
  有检出力
- **两种模式**：固定前缀（Agent 场景：同一 system prompt 反复使
  用）与多轮上下文（对话场景：会话内历史增长），对齐原始验证的
  两个维度
- **预热排除**：第 1 轮为首建缓存（cached 必为 0），排除后实测
  9 轮，与原始验证口径一致
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 模式2 多轮上下文修复前 ≈92-93%（7680 截断 + 历史追加稀释），
  固定前缀模式（≈87-88%）为主要检出点
- 实际模型回复若超短（"收到。"）以外内容过多，会稀释命中率——
  问题已带 "本轮请仅回复：收到。" 约束
- marker：`GLM53` + `GLM53FLASH`（K 套件按模型分组标记）

### test_stop_newline_in_reasoning (K17)

**背景**：客户契约：指定停止符为换行符 `"\n"` 并开启思考时，停止
符同样作用于推理（reasoning）输出——推理里出现的第一个换行即触
发停止，正文（content）不会生成；反之若换行未触发停止、继续输
出正文，则换行符未生效。

**请求构造**（按场景构造，OpenAI 协议 `/v1/chat/completions` 流式）：
- messages：单条 user "请简要介绍量子计算的基本概念与应用前景。"
  （思考开启下推理输出自然含换行——第一个换行即应触发停止）
- `stop=["\n"]`、`stream=true`
- `thinking={"type":"enabled"}` 显式开启思考（K1 口径）
- `max_tokens=512` 防御性预算（正常应在推理早期几十个 token 内触
  发停止，仅防缺陷形态下无界生成）
- 不发送采样参数（test_k 整套件保持原始测试参数——无全局注入
  口；手工 payload 直发）

**断言**（硬）：
1. SSE 解析成功（收到事件）
2. 合并正文为空（核心——stop 在推理阶段触发，正文未生成；收到
   正文即换行符未生效）
3. `finish_reason == "stop"`（停止符触发，非 length）
4. 合并 reasoning 不含 `"\n"`（stop 语义：输出在停止符前截断、
   停止符不泄漏到输出）

**判定矩阵**：
- 推理中第一个换行触发停止、无正文、finish=stop、reasoning 无
  换行 → PASS（契约行为）
- 换行未触发停止、推理带换行继续并输出正文 → FAIL（核心缺陷检
  出：正文断言/换行泄漏断言任一命中）
- 思考被忽略直接输出正文 → FAIL（正文非空，同样命中核心断言）
- finish=length 且正文为空（换行未生效且思考吃满预算）→ FAIL
  （finish 断言命中）

**设计决策记录**：
- **P0**（stop 核心语义在推理阶段失效，客户报障）
- **单标记**：仅 `GLM53`（用户指定，本用例仅在 GLM-5.3 环境回
  归，不进 GLM53FLASH 集）
- **测试技术**："将 stop 用到推理上"——思考输出几乎必然在早期出
  现换行，因此无需构造特殊提示词即可确定性验证停止符是否作用于
  推理阶段；正文是否生成即判定分水岭
- **max_tokens=512 防御性预算**：无客户原始 curl，设预算仅防缺陷
  形态下无界生成；契约行为下远用不到
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 若引擎将 stop 仅作用于正文（不作用于推理）：推理完整输出（含
  换行）、正文在第一个正文换行处截断——正文非空 + reasoning 含
  换行，断言 2/4 双重检出
- **模型真实响应打印**（用户要求）：合并正文/思考全文、finish、
  usage 在断言前打印到日志——失败时日志中同样可见，便于诊断
- usage 仅日志（流式下客户场景未带 stream_options.include_usage，
  usage 可能为空）
- marker：仅 `GLM53`（K 套件按模型分组标记；用户指定不含
  GLM53FLASH）

### test_output_json_as_input_context (K18)

**背景**：客户问题（AGDC2-28）：上次请求输出的 assistant JSON
作为下次请求的输入上下文提交即报错——`Failed to deserialize
the JSON body into the target type: missing field 'name'`。触发
形态：助手历史 tool_calls 列表混有
1. 空占位调用：`function.name=""`、`id=null`、`arguments="{}"`
   （报错 missing field `name` 即指向它）——模型侧修复已明确
   任何情况下不返回空 function，本用例按用户指定不再保留该空
   function 场景（回放数据中已移除）；
2. 真实 bash 调用：`name="bash"`、`id="call_8af1ab36a4154c25"`，
   arguments 为 `'"command":"cd ... ", "description": "..."}'`
   ——缺开头 `{`、非合法 JSON（内部 `data,json`、`SKlLL` 等怪
   字符均为工单原文，原样保留）。
（按客户 agent 两步流程解读：第一个 tool 调用即第一步"输出
JSON 到 *.json 文件"——其 name/id 在返回数据中丢失；bash 调
用即第二步，读取/复制第一步输出的 skill_weekly.json）
修复逻辑（开发回复）：
1. 先按原有逻辑解析、校验请求，正常请求直接通过；
2. 解析失败后，识别 assistant 历史中的空占位调用；同一列表还有
   其他真实调用时，移除空占位项、保留真实调用，再重新校验（只有
   空占位项时不直接删除）；
3. 真实 bash 调用的 arguments 即使缺少开头 `{`，仍作为字符串保
   留，不补 `{`（请求能通过 router 不代表该字符串成为合法工具
   参数 JSON）；
4. 兼容 assistant 历史里重复的 reasoning_content /
   reasoning_context，保留最后一个值。

注：模型侧根上解决（任何情况下不返回空 function）生效后，空
占位场景不再产生——本用例按用户指定不再保留空 function 场
景，回放历史仅保留真实 bash 调用（缺 `{` arguments 原样）+
reasoning 双字段，验证剩余契约：含真实工具调用的上次输出可回
填为下次请求输入上下文。

后续问题（开发文档：glm5.3 返回 messages[141].tool_call_id
must reference an unanswered tool call 问题——SMG 1.13.0 修复
上线后引出）：不再报 missing field `name`，但出现新问题——
`messages[141].tool_call_id must reference an unanswered tool
call in the preceding assistant message`。完整根因链（开发确
认）：
1. 模型返回了一个空的 function（id=null）——根本原因；
2. 客户端工具执行后回填错误结果：真实调用因 arguments 缺 `{`
   无法执行（`[Tool call could not be executed because its
   arguments were invalid.]`，以其真实 id 回填）；空 function
   因 id=null，客户端构造 ToolMessage 校验失败
   （ValidationError: tool_call_id Input should be valid
   string, input_value=None），遂以
   `tool_call_id="missing_tool_call_id"` 回填错误说明；
3. 再次请求时该悬空 tool_call_id 不指向任何未应答调用，被协
   议校验拒绝（messages[141] 报错）。
根上解决（开发建议）：模型不要返回空的 function——不同客户端
工具处理结果的方式不同。

**请求构造**（按客户 agent 两步流程还原+根因断言请求，OpenAI
协议 `/v1/chat/completions` 非流式，手工 payload 直发）：
- **第一个请求**（第一步"输出 JSON 到 *.json 文件"）：user 单轮
  要求直接输出技能周报数据 JSON 对象（3-5 条示例记录，明确无需
  真实数据——防御模型因"无工作区数据"拒绝虚构而输出 error
  JSON；不带工具定义——直接输出 JSON 才可确定性落盘）；
  max_tokens=2048（留足
  思考预算余量，防御正文被思考耗光）；测试代为执行"输出 JSON
  到 *.json 文件"——从正文提取最外层 `{...}`（容忍 markdown
  代码块围栏/前后杂文）、json.loads 校验后写入测试脚本同级目录
  下临时文件 `tests/k18_temp_skill_weekly.json`（对应工单中的
  skill_weekly.json）
- **工具读取**：测试代为执行第二个请求上下文中 bash 工具调用的
  读取语义——读取第一个请求输出的临时 JSON 文件，回读 json 与
  第一个请求输出一致
- **第二个请求**（核心）：user（"请分析工作区数据并生成技能周
  报图表。"）→ assistant（content=null、reasoning_content +
  reasoning_context 双字段并存、tool_calls=[真实 bash 调用
  （arguments 缺 `{`、非合法 JSON，工单原样保留）]——空占位
  调用已按用户指定移除）→ tool（role=tool，
  tool_call_id=call_8af1ab36a4154c25，content=工具读取到的临
  时 JSON 文件内容，防御性截断上限 3000 字符——协议必需：
  assistant 带 tool_calls 后必须紧跟匹配工具结果消息，实测缺
  失被 400 拒绝 messages[2] missing tool results）→ user 追问
  （"请继续完成任务。"）；tools：bash 工具定义（agent 场景——
  模型输出调用了 bash，请求必然定义了该工具）；max_tokens=512
  （工单口径）
- **第三个请求**（根因断言）：复刻工单首个 user 回合——user
  单轮 "请分析工作区数据并生成技能周报图表。"（与第二个请求
  历史第 0 条同一消息，常量 K18_CHART_PROMPT 单一来源复用），
  带 bash 工具定义，max_tokens=2048（同第一个请求防御口径——
  留足思考预算余量）；工单中模型在该回合输出了空占位调用与畸
  形 bash arguments（根因行为），本请求断言本次输出结构完整
- 采样参数不发送（用户指令）——三个请求一致：test_k 保持原始
  测试参数（工单原始请求未指定，不注入）
- **测试完成后删除生成的临时 JSON 文件**（finally 兜底，断言失
  败同样清理）

**断言**（硬）：
1. 第一个请求 HTTP 200 且正文可提取合法 JSON 对象（第一步契约：
   输出 JSON 到文件）
2. 工具读取临时 JSON 文件成功（回读 json 与输出一致）
3. 第二个请求 HTTP 200（核心——上次输出 JSON 必须可作为下次请
   求的输入上下文，报错复现即 FAIL）
4. 第二个请求 choices 存在且非空 + message 结构存在（响应可正
   常生成）
5. 第三个请求 HTTP 200 且模型发起工具调用（生成图表必须执行
   绘图脚本——工单场景中模型对该消息即发起 bash 调用；纯文本
   回答无法覆盖根因），每条调用 name 非空、id 非空、arguments
   为合法 JSON 对象（根因断言：模型不得返回空 function；同时
   覆盖工单同款畸形 arguments 缺 `{` 的模型输出缺陷）

**判定矩阵**：
- 第一个请求未输出合法 JSON 对象（正文空/无 `{...}`/解析失败）
  → FAIL（第一步"输出 JSON 到文件"契约未达成）
- 临时 JSON 文件回读失败或与第一个请求输出不一致 → FAIL（工具
  读取链路破损）
- 第二个请求被接受（200）且正常生成 → PASS（上下文回填成功）
- 第二个请求非 200 → FAIL（含真实工具调用（缺 `{` arguments）
  +reasoning 双字段的上次输出未被接受为输入上下文）
- 200 但无 choices / 无 message 结构 → FAIL（上下文被接受但未
  正常生成）
- 第三个请求模型未发起工具调用 → FAIL（无法验证根因断言——
  工单场景中该回合必然发起工具调用）
- 第三个请求任一工具调用 name 为空 / id 为空 → FAIL（根因复
  现：模型返回空 function——客户端将以 missing_tool_call_id
  回填，后续请求被协议校验拒绝）
- 第三个请求任一工具调用 arguments 非合法 JSON 对象 → FAIL
  （工单同款畸形 arguments 模型输出缺陷复现）

**设计决策记录**：
- **P0**（按客户工单，AGDC2-28）
- **明确不断言**：arguments 被补 `{`（修复明确不补——通过
  router 不代表该字符串成为合法参数 JSON）
- **空 function 场景移除（用户指定）**：模型侧修复已明确任何
  情况下不返回空 function——回放历史不再保留空占位调用；
  K18 聚焦剩余契约（真实工具调用缺 `{` arguments 原样+
  reasoning 双字段+回填接受），空 function 的模型侧保证由本
  用例第三个请求（根因断言）验证（原 K27 已按用户决定合并回
  K18）
- **响应形态宽松**：只测"上下文被接受"——正文或继续调用工具
  均可（历史是工具调用场景且提供了 bash 工具），content/
  tool_calls 仅日志
- **role 拼写**：docx 中为 `"assitant"`——报错与修复逻辑均不涉
  及 role，判定为文档笔误，按标准 `assistant` 还原
- **reasoning 重复字段覆盖方式**：dict 无法表达同键字面重复，
  以 reasoning_content + reasoning_context 两拼写并存覆盖兼容
  路径（"保留最后一个值"为 router 内部合并行为，响应不可见，
  不断言）
- **采样参数不发送（用户指令）**：对齐 K10 口径——test_k 保持
  原始测试参数（工单原始请求未指定，不注入）
- **两步流程还原（用户指定测试逻辑）**：第一个请求输出临时
  JSON 文件、第二个请求调用工具读取后回填——对应客户 agent
  场景中两个 tool 调用（输出 JSON 到文件 + bash 读取该文件）；
  临时文件落盘测试脚本同级目录（tests/），测试完成后 finally
  兜底删除（断言失败同样清理）
- **第一个请求不带工具定义**：直接输出 JSON 才可确定性落盘
  （带工具定义时模型可能改为发起工具调用，正文无 JSON 可写盘）
- **第一个请求明确生成示例记录**：测试无真实工作区数据，首跑
  曾因模型"无数据拒绝虚构"输出 error:no_workspace_data——
  提示词明确无需真实数据，保证第一步确定性产出数据记录
- **第三个请求复刻工单首个 user 回合**：根因行为（空占位调用
  +畸形 bash arguments）发生在模型对该消息的响应中——同一消
  息复现条件最贴近；与第二个请求历史第 0 条共用常量
  K18_CHART_PROMPT（单一来源）
- **tool_calls 非空硬断言**：生成图表必须执行绘图脚本，工单场
  景中模型对该消息即发起 bash 调用——纯文本回答时根因断言
  无从谈起（vacuous pass），故硬断言；行为假设失败时 FAIL 信
  息明确
- **arguments 合法 JSON 对象断言**：覆盖工单同款畸形
  arguments（缺 `{`）模型输出缺陷——根因文档仅点名空
  function，但畸形 arguments 同样源自模型输出，一并纳入结构
  完整性断言
- **不断言 missing_tool_call_id 悬空引用被放行**：该形态为客
  户端产物（协议上 tool 结果必须引用未应答调用，拒绝是正确行
  为），根因修复在模型侧——不做服务端放行断言
- **工具结果配对为协议必需（实测修正）**：第二个请求
  user→assistant(工单输出)→tool(工具读取结果)→user 追问——
  assistant 带 tool_calls 后必须紧跟匹配 tool_call_id 的
  role=tool 结果消息：原"user 追问携带文件内容"方案被服务端
  400 拒绝（messages[2]: missing tool results for preceding
  assistant tool_calls，prefill_bad_request）；文件内容改经
  tool 消息携带（协议原生位置）；该 400 亦证空 name 反序列化
  层已通过（空占位移除生效——缺陷触发源消除后暴露下一层校
  验）
- **临时文件内容截断上限 3000 字符**：防御模型输出超长 JSON
  撑大第二个请求上下文
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 空占位相关 router 兼容分支（移除空占位项、仅有空占位项时不
  直接删除）不在本用例覆盖范围——模型侧修复后空 function 不
  再产生，回放场景已按用户指定移除空占位调用
- 临时 JSON 文件（`tests/k18_temp_skill_weekly.json`）为运行期
  产物，测试结束（无论成败）即被 finally 删除，不入库
- usage 仅日志
- marker：仅 `GLM53`（用户指定）

### test_over_image_limit_rejected (K19)

**背景**：客户问题：单次请求携带超过 16 张图片导致请求失败。
根因：服务端 serving-pool 启动参数显式配置
`--limit-mm-per-prompt {"image":16,"video":1,"audio":0}`（vLLM
多模态单项限额）。契约：超限请求应失败并返回恰当的错误信息
（参考 `"At most 16 image(s) may be provided in one prompt"`）。

**请求构造**（GLM-5.3-Flash 专用，OpenAI 协议
`/v1/chat/completions` 非流式，手工 payload 直发）：
- 代码生成 17 张 32x32 纯色 PNG（IHDR+IDAT+IEND 手工构造，
  base64 data URL，各图颜色不同，无外部依赖）
- 单条 user 消息 content 数组：1 个 text part + 17 个
  `image_url` part（单次请求/单次会话超过 16 图）
- `max_tokens=32` 防御性预算（应在生成前被拒绝）
- 不发送采样参数（test_k 整套件保持原始测试参数——无全局注入
  口；手工 payload 直发）

**断言**（硬）：
1. 响应失败（HTTP 非 200——超限应被拒绝；200 放行即限额未生
   效）
2. 错误信息含 `"at most 16 image"`（大小写不敏感——覆盖
   "At most 16 image(s) may be provided in one prompt" 及网关
   等价表述；信息不恰当即 FAIL）

**判定矩阵**：
- 非 200 且信息含该模式 → PASS（超限被正确拒绝且信息恰当）
- HTTP 200 放行 → FAIL（限额未生效）
- 非 200 但信息不含该模式 → FAIL（失败信息不恰当——如裸
  500/internal error 无超限说明）

**设计决策记录**：
- **P0**（客户报障场景）
- **图片代码生成**：手工构造 PNG 字节（struct/zlib/base64），
  17 张各色不同——自包含、确定性、无外部 URL 依赖；32x32 尺寸
  兼顾视觉编码器的最小尺寸要求
- **恰好 16 张正向对照未纳入**：用户测试要点仅两条（17 张生成
  + 超限失败断言），且避免回归中重度视觉计算
- **断言口径**：原始失败详情截图未收到，以用户给定的参考信息
  "At most 16 image(s) may be provided in one prompt" 为准，
  匹配取大小写不敏感子串（网关可能等价改写措辞）
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 若网关/引擎对超限返回 500 而非 400 但信息恰当，断言 1（非
  200）+ 断言 2（信息）均满足 → PASS（用户测试要点为"响应应
  该失败 + 恰当失败信息"，不限定具体状态码）
- **模型真实响应打印**（用户要求）：状态码与响应体全文在断言
  前打印到日志——失败时同样可见，便于诊断
- usage/响应体仅日志
- marker：`GLM53FLASH`（K 套件按模型分组标记；采样参数豁免）

### test_1m_context_request_supported (K20)

**背景**：客户问题：请求报错 `"Input length (918451 tokens)
exceeds the maximum allowed length (781754 tokens). Use a shorter
input or enable --allow-auto-truncate."`（type:
invalid_request_error、code: invalid_request、
metadata.provider_code: bad_response_status_code——网关透传
serving 侧上下文长度校验拒绝）。根因：serving 侧未按 1M 上下文
契约配置（当时最大允许 781754）。契约：模型需支持 1M 上下文请
求——1M 量级输入应正常响应。

**请求构造**（GLM-5.3 适用，OpenAI 协议
`/v1/chat/completions` 非流式，手工 payload 直发）：
- **两阶段：探针自校准 + 主请求**（1M = 输入+输出，总量略小于
  1M——用户口径，余量留给推理框架额外补充的长度）
- **阶段1 探针自校准**：英文重复单元（"Long context
  verification material. ..."）× 2000（约 276K 字符），max_tokens=1，
  从响应 usage.prompt_tokens 精确得出每单元 token 数——客户端
  无分词器，chars/token 启发式误差大（真实环境实测该单元 6.28
  字符/token，chars/4 高估 57%——估算偏低会造成实际输入低于
  旧限 781,754 → 假阳性），规模必须可靠计量
- **阶段2 主请求（两轮）**：按自校准结果重复至输入目标
  960,000 tokens + 尾部简短指令（"以上为背景材料。请直接回复一
  句话，确认已完整收到全部材料。"）；输出预算 max_tokens 覆盖思
  考+正文（计入总量），两轮思考档位（**GLM-5.3 不支持禁用思考、
  仅支持 reasoning_effort 档位**——用户口径；用户指定补 max 场
  景）：
  - ①low 轮 `reasoning_effort="low"` + `max_tokens=1024`——常
    规（真实环境实测默认档思考耗尽 32 预算：reasoning_tokens==
    max_tokens、finish_reason=length、content 为空——预算必须
    覆盖思考+正文的教训）
  - ②max 轮 `reasoning_effort="max"` + `max_tokens=4096`——
    最大思考负载，输出侧同步压窗口（max 档思考显著更长，预算
    放大至 4096）
  → 总消耗 ≈961K/964K tokens
- 单条 user 消息（超长单字符串 content）
- **采样参数不发送**（用户指定）：test_k 保持原始测试参数——工单
  原始请求未指定，不注入（探针与两轮主请求共用同一构造）
- **跑必冷——nonce 前缀绕过 KV 缓存（仅 low 轮，用户加固）**：
  材料头部置每次请求唯一 nonce（时间戳+uuid，可含中文，几十字
  符；探针与 low 轮各自唯一）——前缀必不命中 KV 缓存，真 1M
  冷 prefill。缓存命中只省 prefill 重算，**不绕过准入长度校
  验、不省 KV 内存驻留与 decode 全窗注意力——核心契约验证本
  不受缓存影响**，此为 prefill 侧压测加固；nonce 为常数级几
  十 tokens，对探针计量/1M 总量口径影响可忽略。
  **max 轮取消唯一前缀**（用户口径：输出侧验证——最大思考负
  载 + 非空正文 + 1M 窗口总消耗——不受缓存影响，允许命中历
  史缓存加速）
- **超时处理**：1M token prefill 耗时长，临时将客户端超时上
  调至 900s（finally 恢复；ReadTimeout 不重试——框架约定）

**断言**（硬，每轮）：
1. 探针 200 且返回 usage.prompt_tokens（计量前提）
2. 每轮主请求 HTTP 200（未被拒绝——1M 量级输入应被接受）
3. 每轮 choices 非空且 content 非空（可正常响应）
4. 每轮主响应 usage.prompt_tokens（如有）> 781,754——规模
   sanity（确保真正压过原始故障点，防计量偏差）

**判定矩阵**：
- 探针 200 + 两轮主请求均 200 + content 非空 + prompt_tokens
  > 781,754 → PASS（1M 量级输入在两种思考负载下均正常响应）
- 探针失败/缺 usage → FAIL（断言 1——无法计量规模）
- 任一轮主请求非 200（如原始报错形态 Input length...exceeds...
  ）→ FAIL（断言 2——上下文未按 1M 契约支持）
- 任一轮主请求 200 但 content 为空 → FAIL（断言 3——未正常
  响应）
- 任一轮 prompt_tokens ≤ 781,754 → FAIL（断言 4——用例未真正
  压过故障点）

**设计决策记录**：
- **P0**（客户报障场景）
- **1M = 输入+输出，总量略小于 1M**（用户口径）：输入目标
  960,000 + 输出预算（low 轮 1024 / max 轮 4096）→ 总消耗
  ≈961K/964K——两种 1M 口径（1,000,000 / 1,048,576）下均略
  小于 1M（余量 36K/84K tokens 留给推理框架额外补充的长度；
  prompt_tokens 本身已含聊天模板等框架开销）
- **探针自校准**：客户端无分词器、估算不可靠——先小规模实测
  每单元 token 数再精确生成主请求（真实环境实测：6.28 字符/
  token，探针自动适配任意比率）；高于原始故障上限 781,754 约
  178K（缺陷可复现）
- **禁用思考改为 reasoning_effort 档位 + 预算覆盖思考**：
  GLM-5.3 不支持禁用思考、仅支持 reasoning_effort 档位（用户
  口径）——low 轮（1024）常规；max 轮（4096）最大思考负载、输
  出侧同步压窗口（用户指定补 max 场景；真实环境首轮实测默认
  档思考对该指令约 40 tokens 即将收尾，max 档显著更长故预算
  放大）；探针用 low 档（计量不受生成影响）
- **采样参数不发送**（用户指定）：test_k 保持原始测试参数——
  工单原始请求未指定，不注入
- **跑必冷——nonce 前缀绕过 KV 缓存（仅 low 轮）**（用户加
  固）：真实环境实测同内容重跑会命中 KV 缓存（cached_tokens
  959,744/959,758 ≈ 全量，elapsed 3.0s vs 冷跑 155.1s）——
  low 轮（含探针）材料头部置每次请求唯一 nonce 后真 1M 冷
  prefill；缓存不绕过准入长度校验（原始缺陷形态），核心契约
  验证本不受影响。**max 轮取消唯一前缀**（用户口径：输出侧
  验证不受缓存影响，允许命中历史缓存加速）
- **超时 900s 临时上调**：1M prefill 耗时长于默认 120s（真实
  环境 585K tokens 实测 73.2s、916K 冷 prefill 155.1s；low
  轮必冷 ~2.5-3 分钟，max 轮视缓存命中秒级至 ~3 分钟）；finally
  恢复不影响其他用例
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 真实环境耗时：探针 ~1s + low 轮 1M 冷 prefill ~2.5-3 分钟
  （实测 916K 冷 prefill 155.1s；nonce 保证必冷）+ max 轮视缓
  存命中秒级至 ~3 分钟（无唯一前缀，允许命中历史缓存）——总
  耗时预期 3-6 分钟
- **模型真实响应打印**（用户要求）：状态码与响应体全文在断言
  前每轮打印到日志——失败时同样可见，便于诊断
- usage 仅日志（主响应 prompt_tokens 为实际输入 token 数）
- marker：`GLM53`（K 套件按模型分组标记）

### test_system_message_embedded_tools_accepted (K21)

**背景**：客户问题（kimi-k3 工单原始请求体）：messages[2] 为
role=system 且无 content 字段、代之以内嵌 tools 数组（Calculator
单工具——"计算器，只支持单个算术表达式的求值"），服务端反序
列化直接报 400 invalid_request_error / json_parse_error：`"messages[2]:
data did not match any variant of untagged enum MessageContent"`。
该结构虽非 OpenAI 协议标准形态（tools 应为顶层参数），但客户业务
实际在用——契约：服务端应宽容解析该非标结构并正常响应（预期
200）。

**请求构造**（Kimi-K3 适用，OpenAI 协议
`/v1/chat/completions` 非流式，手工 payload 直发）：
- **工单原始请求体原样重放**：三条消息（①role=system 长系统提
  示词；②role=user "Calculate fuel consumption."；③role=system
  无 content 字段、tools 内嵌——缺陷触发点，不修复）+
  stream=false；模型名按框架约定由环境注入，其余字段不改动
- **采样参数不发送**：test_k 保持原始测试参数——工单原始请求
  未指定，不注入
- 单次请求（结构解析为确定性行为，无需多次连发）

**断言**（硬）：
1. HTTP 200（核心——原始报错形态 400 json_parse_error 复现即
   FAIL）
2. 响应为合法 JSON 且 choices 存在
3. message 有效输出：content 非空或 tool_calls 非空（宽容解析后
   无论按"忽略内嵌 tools 文本作答"或"按工具调用响应"均为有效
   成功形态；两者皆空即未正常响应）

**判定矩阵**：
- 200 + choices + 有效输出 → PASS（非标结构被宽容接受并正常响
  应）
- 400（原始报错形态）/其他非 200 → FAIL（断言 1——未宽容解析）
- 200 但 content 与 tool_calls 均为空 → FAIL（断言 3——未正常
  响应）

**设计决策记录**：
- **P0**（客户报障场景）
- **工单原始请求体唯一口径**：非标结构原样重放不修复（缺陷触发
  点），模型名由环境注入（框架约定——客户 curl 中的模型名仅用于
  当时定位，不写入测试）
- **有效输出断言取 content 或 tool_calls**：宽容解析的合理修复
  形态不止一种（忽略内嵌 tools 文本作答 / 按工具调用响应），两
  者均为成功形态——仅断言"200 + 有有效输出"，不为服务端选择
  的实现方式设限
- **单次请求**：结构解析为确定性行为（K6 先例——参数校验无概
  率性），无需连发
- **采样参数不发送**：test_k 保持原始测试参数——工单原始请求
  未指定，不注入
- **打印口径**（用户指令）：运行日志不出现具体模型名——系统提
  示词正文含模型自我介绍，日志仅记字符数概要（原文见用例常量/
  工单）
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 模型真实响应打印（用户要求）：状态码与响应体全文在断言前打
  印到日志——失败时同样可见，便于诊断
- usage 仅日志
- marker：`KimiK3`（K 套件按模型分组标记）

### test_cross_protocol_prefix_cache_parity (K22)

**背景**：客户问题：相同请求下，Anthropic 协议
（/anthropic/v1/messages）的前缀缓存命中率始终低于
/v1/chat/completions（"缓存始终上不去"）。根因：该链路 system
头部携带 `x-anthropic-billing-header: <逐请求动态值>` 计费行
（字符串/块数组两种 system 形态均涉及），而前缀缓存要求从位置 0
连续匹配——头部逐请求变化导致整个前缀永不命中；chat 协议无此行、
前缀稳定，命中率正常（K15/K16 已验证 ≥90%）。

**修复**（开发）：入引擎前条件剥离——system（字符串或块数组）开头
是 `x-anthropic-billing-header:` 行即去掉，其余内容原样保留。

**测试要点**（用户口径）：
- **同轮等价请求双协议逐轮对比**：同轮同问逐轮交替发送
  /v1/chat/completions 与 /anthropic/v1/messages，前缀头部渠道标
  记行不同（用户指定：剥离计费行后两协议前缀仍从位置 0 分叉——
  互不命中对方缓存条目，各自建条目/各自命中，messages 冷轮为真
  冷；标记差异仅数字符，对命中率影响可忽略），统计二者缓存命中
  率并逐轮比较
- **冷轮不参与比较**：第一次请求为冷轮，两协议均无缓存可命中
  （用户口径：需热轮才能统计命中率）；热轮（第 2 轮起）逐轮比较
- **循环 5 次比对**（用户口径：每次循环的请求消息尽量不一样）：
  2 组中文、2 组英文、1 组中英混合；每组前缀 ~8400-12000 tok +
  每轮唯一问题 ~330-550 tok，整请求长度尽量超过 8k tokens；组间
  前缀内容互不相同，组内批次号防跨运行污染
- **每次循环每协议 1 冷轮 + 2 热轮**（用户口径），共 5 次循环 ×
  2 协议 × 3 轮 = 30 请求，组间间隔 3 秒（用户指定——降低组间背
  靠背请求的调度/缓存抖动）
- **热轮全量 miss 重发加固**（用户指定）：messages 热轮 read=0
  且 creation=0 时同轮重发一次（新计费行、同前缀同问）——重发
  命中→WARN 留痕并按重发结果继续比较（偶发 miss，疑似多实例路
  由/条目可见性问题，交开发排查）；重发仍全量 miss→该组不符合
  预期（剥离失效形态——剥离失效时重发同样 miss，判别力不变）
- **组级判定与 4/5 阈值**（用户指定）：单组失败不中断后续组（五
  组全部执行）；每组判定=该组全部热轮差值 ≤3 个百分点；最终 5
  组中至少 4 组符合预期即 PASS，不足 4 组 FAIL（报文汇总各组判
  定与失败轮细节）
- **计费行**：每请求在 system 头部构造逐请求变化的计费行
  （request_id + 时间戳）——值必须变化：静态值修复前前缀也相同、
  缺陷无法复现=假阴性
- **双 system 形态**：覆盖开发修复的两条剥离代码路径——块数组
  形态断点挂 system 块（K3 口径）、字符串形态断点挂 user 首块
  （内容固定断点前缀逐轮恒定，每轮唯一问题置于断点外）
- messages 请求按开发示例口径：非流式、x-api-key +
  anthropic-version: 2023-06-01 头
- 命中率口径：chat = cached_tokens/prompt_tokens（该轮，K16 字段
  口径）；messages = cache_read/分母（分母按 input_tokens 口径
  自适应——以同轮 chat prompt_tokens 为参照判别官方语义/总量
  语义）

**断言**（硬）：
1. 组级判定（用户指定）：每组判定=该组全部热轮差值 ≤3 个百分点
   （messages 热轮全量 miss 时先同轮重发一次鉴别——见测试要点
   重发加固）；单组失败不中断后续组；最终 5 组中至少 4 组符合预
   期即 PASS，不足 4 组 FAIL，报文汇总各组判定与失败组/轮两侧
   命中率与 usage 细节
2. 每请求 HTTP 200 且响应正常（chat：choices；messages：
   usage+content）

**判定矩阵**（组级判定，≥4/5 组符合预期才 PASS）：
- 修复前（计费行未剥离）：messages 热轮 ≈0% vs chat ≈94% → 差
  ≈90pp > 3pp → 五组全部不符合预期 → FAIL
- 修复后：两协议每热轮均 ≈94% → 差 <3pp → 五组全符合 → PASS
- 偶发单组 miss（重发仍 miss，疑似多实例路由/条目可见性）：该
  组不符合预期、其余组符合 → 4/5 → PASS（error/WARN 留证交开
  发）

**设计决策记录**：
- **P0**（客户报障场景）
- **测试自带计费行**（用户口径）：不区分计费行来自客户请求还是
  平台注入——测试尽量模拟带有 x-anthropic-billing-header 开头的
  请求，以验证开发修复确实正常处理了这样开头的请求消息
- **计费行值逐请求变化**：静态值修复前前缀也相同、缺陷无法复现
  （假阴性）——动态值才是缺陷的触发条件
- **容差 3 个百分点**（用户指定）："基本一致"的量化；缺陷形态差
  ≈90pp，判别度充足；修复后两协议前缀仅差渠道标记行、粒度效应
  相同，差异远小于 3pp
- **冷轮排除**（用户口径）：第一次请求为冷轮——渠道标记行隔离后
  两协议互不命中对方条目（真冷），不参与差值比较（需热轮才能统
  计命中率）
- **渠道标记行隔离**（用户指定）：引擎跨协议共享 KV 时，相同前缀
  会使 messages 冷轮直接命中 chat 刚建的条目（"冷轮即热"）——前
  缀头部渠道标记行（渠道 chat / 渠道 anthropic）使两协议前缀从
  位置 0 分叉，各自建条目/各自命中；标记差异仅数字符，对命中率
  影响可忽略；缺陷判别力不变（剥离失效时 messages 热轮仍全
  miss）
- **重发而非直接 FAIL**（用户指定）：真实环境三轮运行各出现一次
  anthropic 热轮全量 miss（chat 侧三轮零 miss、miss 跨运行游走、
  失败轮曾现 61.4s 长尾）——判定为平台多实例路由/条目可见性偶发
  问题而非剥离缺陷；测试聚焦剥离缺陷回归门禁，偶发 miss 以 WARN
  日志留证交开发，重发命中后继续全程（第 5 组因此恢复覆盖）
- **组级 4/5 阈值**（用户指定）：单组偶发 miss（重发仍 miss）不
  应拦截回归门禁——允许至多 1 组不符合预期；确定性缺陷必然不足
  4 组仍被拦截（剥离失效=五组全挂；单形态缺陷=该形态两组同挂）；
  失败组以 error 日志+最终断言报文留证
- **双 system 形态**：修复方案明确覆盖字符串/块数组两条剥离代码
  路径；字符串形态断点挂 user 首块（Anthropic 标准语义——断点
  前缀含 system）
- **采样参数不发送**（test_k 保持原始测试参数）：手工 payload
  不携带采样字段，缓存命中与采样无关
- **打印口径**（用户指令）：运行日志不出现具体模型名——前缀/问题
  均按字符数概要打印
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 热轮 cache_creation>0（前缀逐请求重建）= 剥离失效的直接信号，
  仅日志留痕（差值断言已覆盖该形态）
- 双低形态（两协议命中率均异常低——疑似全局缓存异常，chat 侧由
  K15/K16 覆盖）仅日志留痕——本用例按用户口径仅判定协议间差值
- usage 全量日志留痕（含 input_tokens/cache_read/cache_creation）
- marker：`GLM53`（K 套件按模型分组标记）

### test_orphan_tool_message_accepted (K23)

**背景**：客户问题（新工单，官方对齐口径）：messages 中 tool 角色
消息前无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未
定义任何 tools），平台返回 400
（`"Invalid parameter: messages with role 'tool' must be a
response to a preceeding message with 'tool calls'."`——type:
alaya code error、code: invalid text request——客户定位为网关层
白加的校验）；而智谱官方源对同一请求 HTTP 200 正常应答
「北京今天天气晴朗，气温18℃」，且模型在 reasoning 中实际引用了
tool 消息里的数据（工具数据被模型正常消费）。

**新契约**（客户指定）：预期结果同官方一致——此类消息序列不做
校验、正常出结果。

**与 K14 的关系**：K14（test_orphan_tool_message_rejected）为当
时工单口径的原始契约（网关校验拒绝 400），按用户指令保持不变；
本用例记录新客户需求（官方对齐契约：接受并正常消费）。二者输入
同类、预期相反——平台采纳官方对齐修复后 K14 将 FAIL，其保留/退
役由用户决定（本用例不改动 K14）。

**请求**（客户新工单原始请求体原样还原）：
- messages：
  1. `{"role": "user", "content": "查一下北京天气"}`
  2. `{"role": "assistant", "content": "好的，我来为您查询北京天
     气数据。"}`（纯文本、无 tool_calls——孤儿条件）
  3. `{"role": "tool", "tool_call_id": "call_weather_001",
     "content": "{\"city\": \"北京\", \"temp_c\": 18,
     \"condition\": \"晴\"}"}`
  4. `{"role": "user", "content": "根据工具返回的数据，用一句话告
     诉我天气。"}`
- `max_tokens=200`（工单原始值；官方同参数下正常答句）；非流式；
  无 tools/thinking
- 采样参数不发送（test_k 保持原始测试参数——工单原始请求未指
  定，不注入）
- 单次请求（确定性行为，无需连发）

**断言**（硬）：
1. HTTP 200（核心——原始 400 拦截形态复现即 FAIL，报文引用原始
   报错文案）
2. 响应合法 JSON 且 choices 非空
3. message 有效输出（content 或 tool_calls 非空——官方形态为正
   常答句，工具调用响应亦为成功形态）

**耗光回退**（K24/K25/K27 口径）：无输出+finish=length 为
max_tokens=200 预算被思考耗尽形态（GLM-5.3 恒开思考）——非契
约违约（HTTP 200 已达成）；以 `reasoning_effort=low` 重发（构
造不变仅加顶层字段，首次请求预算保持工单值 200 不偏离），断
言相同；双强度均未产出即 FAIL（留证交开发）。

**判定矩阵**：
- 修复前（网关白加校验拦截）：400 → FAIL（断言 1，报文标注缺陷
  形态精确复现）
- 无输出+finish=length（思考耗光）→ low 回退重发，断言相同；
  回退后仍无产出 → FAIL（双强度均未产出——留证交开发）
- 修复后（官方对齐）：200 + 有效输出 → PASS

**设计决策记录**：
- **P0**（客户报障场景）
- **K14 保持不变**（用户指令）：K14 为当时工单口径的原始契约，
  不因新需求改动；二者预期相反，平台采纳官方对齐修复后 K14 将
  FAIL——其保留/退役由用户决定
- **工单原始请求体原样重放**：assistant 纯文本消息 + tool 消息
  （无 tool_calls 关联）+ 未定义 tools——孤儿条件最小充分；模型
  名由环境注入
- **max_tokens=200 保持工单值**：官方同参数下正常答句；首次请
  求预算保持工单值不偏离，思考耗尽（finish=length 空正文）形
  态以 reasoning_effort=low 回退重发（K24/K25/K27 口径，构造不
  变仅加顶层字段）——与 400 拦截形态区分
- **官方行为细节软校验**：输出/推理引用工具数据要素（北京/18/
  晴）= 工具数据被模型正常消费的信号——生成措辞自由，仅日志，
  不作硬断言
- **采样参数不发送**（test_k 保持原始测试参数——工单未指定，不注入）
- **打印口径**：模型真实响应（状态码/响应体全文）断言前打印；
  运行日志不含具体模型名（请求侧）
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- finish/usage 仅日志留痕
- marker：`GLM53`（K 套件按模型分组标记；工单模型 glm-5.3）

### test_dual_request_response_with_effort_fallback (K24)

**背景**：客户问题（新工单）：客户的两个请求（中文"同音词+言部汉
字"写作题、英文数学题），期望均能正常响应并返回正文。两个请求体
均为 glm-5.3、temperature=0.0、max_completion_tokens=32768（工单
原始字段名，非 max_tokens）、非流式。

**风险形态**（用户指定）：默认（max）思考强度下，思考内容可能耗
光 max_completion_tokens 预算——正文为空、finish=length。

**回退契约**（用户指定）：
- 第 1 轮按工单原始请求体直发（不带 reasoning_effort——默认强
  度即 max）；有正常正文即该请求通过并退出
- 思考耗光预算（正文空+finish=length）的请求以
  reasoning_effort="low"（GLM 顶层思考强度参数，K20 口径）重发，
  断言相同
- 第 2 轮只重测第 1 轮耗光的请求（已通过的不重测——用户指定）

**请求**（工单原始请求体原样还原）：
- 请求一：user 单轮中文写作题——文段中找读音相同的二字词语
  （≥4 个入文）、[言部]汉字（≥7 个入文）、800 字上下浮动 10%、
  关键词"月光""这""意义"各限用 ≤2 次（文段与要求按工单原文，
  要求条目间换行、关键词双引号包裹均为工单原文形态）
- 请求二：user 单轮英文数学题——三个正实数 k 使
  f(x)=((x-18)(x-72)(x-98)(x-k))/x 在正实数上恰于两点取最小，
  求 k 之和
- 公共：temperature=0.0（显式）、max_completion_tokens=32768、
  stream=false

**采样参数保持原始**（用户指定）：两个请求体均显式指定 temperature=
0.0——工单原始请求体为唯一口径（test_k 整套件不参与全局
`--sampling-params` 覆盖），top_p/seed 亦不注入。

**断言**（硬，每轮每请求）：
1. HTTP 200
2. 响应合法 JSON 且 choices 非空
3. message 有效输出（content 或 tool_calls 非空）

**判定矩阵**：
- 默认 max 强度两请求均有正文 → 无需回退轮 → PASS
- 一通过一耗光 → 回退轮仅测耗光者，low 有正文 → PASS
- low 回退仍无正文（双强度均未产出）→ FAIL（报文留证交开发）
- 正文空且 finish≠length（非耗光形态的异常空响应）→ FAIL

**设计决策记录**：
- **P0**（客户报障场景）
- **max_completion_tokens 保持工单字段名**（非 max_tokens）：工
  单原始请求体为唯一口径，原样重放
- **默认强度 = 不传 reasoning_effort**（工单体即如此——默认强度
  按 max 计，用户口径）；low 回退用 GLM 顶层 reasoning_effort
  （K20 口径）
- **只重测耗光请求**（用户指定）：已通过的不重测，减少长耗时请
  求重复
- **耗光形态转回退而非直接 FAIL**（用户指定）：耗光是强度×预
  算的组合结果而非响应异常，回退轮保底客户"正常出结果"的诉
  求；双强度均无产出才 FAIL 留证交开发
- **采样参数豁免**（用户指定：工单体显式 temperature=0.0——唯
  一口径，全局覆盖不得改写请求体）
- **打印口径**：模型真实响应（状态码/响应体全文）断言前打印；
  运行日志不含具体模型名（请求侧）
- **超时保护**：max 思考 + 32768 预算耗光耗时显著——单请求超时
  下限 1800s（配置已 ≥ 该值时 no-op）
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- finish/usage 仅日志留痕
- marker：`GLM53`（K 套件按模型分组标记；工单模型 glm-5.3）

### test_duplicate_reasoning_content_history_accepted (K25)

**背景**：客户问题（工单跟进）：多轮对话回填 assistant 历史时，同一条
assistant 消息携带**两个 reasoning_content 字段**（两轮历史思考未去重
地拼接成同键重复）与上一次请求的正文，预期不报错、正常响应。客户原始
工单还曾因思考内容含 They're/I'm/It's 等英文撇号导致 JSON 破损——
**正文与思考内容可能含单引号/双引号/换行等字符，须兼容处理、不影响
正常的请求格式**（用户指定）。

**契约**（用户指定）：
- 预期不报错、正常响应
- 第一个 reasoning_content 被**第二个覆盖**（宽松解析保留最后一个值，
  K18 修复口径——兼容 assistant 历史重复的 reasoning 字段）

**请求构造**（共三次请求——JSON 链式回填，用户指定；提示词为测试
自行设计，工单未携带具体提示词——用户口径仅要求结构：JSON 链+
两个 reasoning_content）：

| 请求 | messages | 目的 |
|------|----------|------|
| 第 1 次 | [user: 问平方根，要求仅输出 JSON（格式 {"answer": "<你的回答>"}）] | 流式采集第 1 段思考 + 第 1 次正文（JSON——作为第 2 次请求输入回填） |
| 第 2 次 | [assistant(content=第 1 次正文 JSON, reasoning_content=第 1 次思考), user: "继续，2的平方等于几"+要求仅输出 JSON] | 回填第 1 次历史（单键经 dict 表达——K18 口径），流式采集第 2 段思考 + 第 2 次正文（JSON——作为第 3 次请求输入回填） |
| 第 3 次（核心） | [assistant(content=第 2 次正文 JSON, reasoning_content=第 1 次思考, reasoning_content=第 2 次思考), user: "继续，3的平方等于几"] | 重复键回填——预期 HTTP 200 正常响应 |

- `max_tokens=8192`（客户工单原始口径，三次请求一致）、`stream=true`
- 第 3 次请求形态与用户示例一致：messages 以 assistant 历史开头，
  content 为上一次的回复，两个 reasoning_content 分别为前两次请求的
  思考内容

**重复键的表达**（实现要点）：
- 同键字面重复**无法经 dict 表达**（Python dict 自动去重、requests 的
  `json=` 也会丢失重复键）——手工拼接 JSON 文本，以
  `session.post(data=raw)` 直发（Content-Type/Authorization 由
  session 既有头携带）
- **引号兼容（用户指定）**：所有动态值（正文/思考）一律经
  `json.dumps` 序列化后拼接——单/双引号、换行、反斜杠全转义，
  模型回复含任意字符时 JSON 格式均不破损

**发送前三重自检**：
1. raw body 可被 `json.loads` 解析（动态值含特殊字符时转义正确——
   客户原始 JSON 破损形态在此拦截）
2. `"reasoning_content"` 键在 raw body 中出现且仅出现 2 次（重复键
   真实上送，不被 dict 去重）
3. 转义回读一致：`json.loads` 保留最后一个重复键（与服务端宽松解析
   "第一个被第二个覆盖"契约一致），content 与第 2 次正文逐字一致

**断言**（硬）：
1. 第 1/2 次请求：思考与正文均非空（第 3 次请求的构造数据源——被测
   环境应开思考，GLM-5.3 默认开思考，无思考即环境异常 FAIL 留证）、
   正文为合法 JSON（JSON 链——作为下一请求输入回填，断裂即场景无法
   构造 FAIL；容忍 markdown 代码块围栏，如 json 围栏块）、
   finish_reason 合法
2. 第 3 次请求：HTTP 200（核心——报错/4xx 复现即 FAIL）、SSE 事件
   非空、合并正文非空、finish_reason 合法

**耗光回退（K24 口径）**：三次请求均 `max_tokens=8192`，默认 max 档
思考可能耗尽预算（正文空+`finish=length`，K24 实测 32768 预算亦可被
耗光）——该形态不判失败，以 `reasoning_effort=low`（GLM 顶层思考强
度参数，K20 口径）**仅重发耗光请求**（第 3 次重发构造不变，仅加顶层
`reasoning_effort` 字段——HTTP 200 核心契约首次请求已达成，重复键历
史被接受不以正文是否为空转移），断言相同；正文空且 finish≠length 直
接 FAIL；low 回退仍无正文即 FAIL（默认 max 与 low 双强度均未产出——
留证交开发）。

**软观察**：
- 引号覆盖度：三个回填值（第 2 次正文/两次思考）均不含引号/换行字符
  时 `record_warning` 留痕——引号兼容路径本次未被实际覆盖（构造本身
  已保证安全，不判失败）；含则 INFO 留痕路径被真实覆盖
- usage 仅日志（三次请求均未要求 include_usage）

**判定矩阵**：
- 第 3 次请求 200 且正文非空 → PASS（宽松解析契约生效）
- 第 3 次请求 4xx/5xx（严格解析拒绝重复键）→ FAIL（客户问题形态复现）
- raw body 自检失败（转义/重复键丢失）→ FAIL（测试构造缺陷，发送前
  拦截）
- 第 1/2 次请求无思考内容 → FAIL（环境未开思考，无法构造场景，留证）
- 第 1/2 次响应正文非合法 JSON → FAIL（JSON 链断裂——无法构造下一
  请求输入回填，留证）
- 任一请求正文空+finish=length（思考耗光预算）→ 以
  reasoning_effort=low 仅重发该请求（构造不变，仅加顶层
  reasoning_effort 字段），断言相同
- low 回退重发后仍无正文（finish=length）→ FAIL（双强度均未产出
  ——留证交开发）
- 任一请求正文空且 finish≠length → 直接 FAIL（非耗光形态的空响应
  为异常形态）

**设计决策记录**：
- **P0**（客户报障场景）
- **三次请求 JSON 链采集真实思考**：用户指定——第 1/2 次响应 JSON
  作为下一请求输入回填、思考随历史一并回填，用模型真实产生的思考/正
  文回填而非合成占位文本，忠实还原客户逐轮 JSON 输入回填+历史思考未
  去重拼接的实际形态；提示词为测试自行设计（工单未携带具体提示词
  ——用户口径仅要求结构：JSON 链+两个 reasoning_content）
- **手工拼接 raw JSON 直发**：dict 无法表达重复键（K18 曾以
  reasoning_content + reasoning_context 两拼写并存近似覆盖，本用例
  按用户示例要求同键字面重复——上送报文中真实出现两次）
- **动态值全转义 + 发送前自检**：客户原始工单的 JSON 破损（思考含英
  文撇号）即引号兼容问题的直接来源——构造安全由 json.dumps 保证，
  自检验证转义回读一致
- **采样参数不发送**（test_k 保持原始测试参数——工单原始请求未
  指定，不注入）
- **耗光回退对齐 K24**：max_tokens=8192 下默认 max 档思考可能耗光
  预算（K24 实测 32768 预算亦可被耗光）——耗光为环境/参数风险形态
  而非契约违约；处理口径与 K24 用户指定契约一致（low 仅重发耗光请
  求、非耗光空响应直接 FAIL、双强度未产出留证 FAIL）
- **打印口径**：模型真实响应（状态码/合并正文/思考全文）断言前打印
  （失败时同样可见）
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 第 3 次请求以 assistant 消息开头（无前置 user）——与用户示例一致，
  部分严格实现要求首轮为 user，若被拒为该类校验触发，报错形态会如实
  暴露该部署行为
- marker：`GLM53`（K 套件按模型分组标记；工单模型 glm-5.3）

### test_negative_lookahead_tool_pattern_accepted (K26)

**背景**：客户问题：流式请求报错 `The upstream provider is
unavailable. Please retry later.`（api_error /
provider_unavailable / upstream_stream_error）；非流式请求报错
`Failed to compile structural_tag grammar: .../regex_converter.cc:83:
Regex parsing error at position 4: Lookahead is not supported yet.`
（request id 2026102616110264231215776333070）。
问题原因（开发分析）：工具参数 schema 的 pattern 包含 `^(?!...)`
这类负向前瞻正则——后端将其编译为 structural_tag 生成约束时，
底层语法编译器不支持 lookahead，导致请求失败。
修复（frontend 请求预处理兼容，非底层编译器新增 lookahead 支持）
——仅当以下条件同时命中：
1. GLM-5.3、glm47 工具解析器、SGLang 后端；
2. `tool_choice=auto`、structural-tag schema 模式为 auto；
3. 工具没有显式设置 `strict`；
4. schema 中包含以 `^(?!` 开头的正则。
命中后只把用于生成约束的工具副本设为 `strict=false`，避免强制编
译该 schema；模型提示词里的原始 schema、工具描述及工具调用格式
约束保留。属兼容绕过：该路径不再由 grammar 强制保证参数满足完整
schema。

**请求构造**（OpenAI 协议 `/v1/chat/completions`，非流式+流式各
发一次）：
- 工具定义 `write_workspace_file`：`path` 参数 pattern 以 `^(?!`
  开头（负向前瞻——禁止路径穿越：`^(?!.*\.\.).+$`）；不显式
  `strict`（触发条件 3）；`content` 参数无约束；
  `required=[path, content]`
- `tool_choice="auto"`（显式——对齐触发条件 2，亦是客户请求的
  默认解析值）
- user 单轮自然诱导工具调用（保存技能周报数据到
  `reports/skill_weekly.json`——path 取值合法，不触碰负向前瞻
  拒绝域）
- `max_tokens=2048`（K18 口径——留足思考预算余量，防御正文/调
  用被思考耗光）
- 采样参数不发送（用户指定；test_k 保持原始测试参数——工单原始
  请求未指定，不注入），两个请求一致

**断言**（硬）：
1. 非流式 HTTP 200（核心——修复前 400 grammar 编译错误，报错
   复现即 FAIL）
2. 非流式 choices 存在且非空 + message 结构存在
3. 流式 HTTP 200（核心——修复前 provider_unavailable，报错复
   现即 FAIL）
4. 流式 SSE 事件非空 + 至少一个含 choices 的数据块

**判定矩阵**：
- 非流式 HTTP 400 报 Failed to compile structural_tag grammar
  （或同型 Lookahead 编译错误）→ FAIL（客户缺陷复现——兼容绕
  过未生效）
- 流式非 200（provider_unavailable / upstream_stream_error）
  → FAIL（同一 grammar 编译根因复现）
- 200 但无 choices / 无 message 结构（非流式）→ FAIL（请求被接
  受但未正常生成）
- 流式 200 但无 SSE 事件 / 无含 choices 数据块 → FAIL（流式通
  道异常）
- 两个请求均被接受且正常生成 → PASS（兼容绕过生效）

**设计决策记录**：
- **P0**（按客户工单——请求级阻断缺陷）
- **触发条件全量对齐**：pattern 以 `^(?!` 开头、不显式 strict、
  `tool_choice=auto`、GLM-5.3——逐条对齐开发修复的命中条件，
  确保用例落在兼容路径内（修复未生效则复现报错）
- **明确不断言**：工具被调用（tool_choice=auto 下模型可自主选择
  正文回答——测试要点是请求被兼容放行而非调用行为）；调用参数
  满足 pattern（兼容绕过路径不再由 grammar 强制保证——开发明确
  口径）；响应形态宽松留日志（正文或工具调用增量均可）
- **pattern 选型**：`^(?!.*\.\.).+$`（禁止路径穿越）——agent 文
  件工具的真实校验形态，且以 `^(?!` 开头精确命中触发条件
- **显式 tool_choice=auto**：与触发条件字面对齐（缺省解析值同为
  auto，显式消除歧义）
- **非流式先行**：非流式错误信息含完整 grammar 编译细节（排障信
  息量最大），流式错误为包装后的 provider_unavailable——核心断
  言信息密度高的先行
- **采样参数不发送（用户指定）**：对齐 K18/K25 口径——test_k
  保持原始测试参数（工单原始请求未指定，不注入），两个请求一致
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- usage 仅日志
- marker：`GLM53`（K 套件按模型分组标记；工单模型 glm-5.3）
- 本用例不覆盖"pattern 非 ^(?! 开头/工具显式 strict/tool_choice
  非 auto"等非命中分支（修复明确仅兼容命中形态，非命中分支行为
  不在修复契约内）

### test_invalid_arguments_history_tolerated (K27)

**背景**：客户问题（AGDC2-19，codex 客户端 + MCP 工具场景）：
1. codex 向模型发请求，模型返回 assistant 消息调用 MCP 工具
   `mcp__grafana__update_dashboard`（arguments 为嵌套 Grafana
   dashboard JSON）；
2. **模型输出的 arguments 本身不是合法 JSON**——两处括号错误：
   `"refId": "A"}]`（缺一个 `}`，应为 `"refId": "A"}}]`）与
   `40}}}]` 处（多一个 `}`）；PDF 第 8-10 页上游流式日志
   （upstreamResponseChunk）逐 chunk 证实错误内容由上游模型产
   生；
3. codex 执行 MCP 工具失败（无法解析），拼接失败结果并回放全
   量历史继续请求；
4. 服务端校验历史消息 tool_calls[].function.arguments，发现非
   合法 JSON → 400 `Assistant tool call function.arguments
   must be valid JSON`。
问题定位分析：**纯服务端问题，与 codex 客户端无本质关系**——
畸形源头为模型输出（上游日志证实）、报错点为服务端校验层（自
家校验拒绝自家模型的历史输出）、客户端行为为标准 agent 回放
（arguments 对客户端是不透明字符串，换任何客户端同路径复
现）、修复落在服务端。codex 唯一相关性是 MCP 场景+巨型嵌套
arguments 更易诱发模型 JSON 括号错误（触发概率差异）。
修复（开发方案）：历史里无法解析的 arguments 按字符串保留，
让模型继续纠正，不再直接 400 拒绝。

**请求构造**（OpenAI 协议 `/v1/chat/completions` 非流式单次请
求）：
- `user`："请通过 Grafana 工具更新 SLA 状态面板。"
- `assistant`：`content=null`，`tool_calls=[{id=
  "call_37835f057d824692ad063945"（工单截图原值），name=
  "mcp__grafana__update_dashboard"，arguments=畸形 JSON}]`——
  arguments 采用**保真浓缩版**（~2.2KB）：完整保留工单两处括
  号错误形态与关键结构（dataset/rawSql/title/uid/操作路径）；
  PDF 换行提取无法保证 3KB 原文字节级保真，浓缩版在两处错误之
  外结构合法（修正该两处即可解析，构造时已程序化验证）；场景
  自检：常量经 json.loads 解析必须失败
- `tool`：`tool_call_id` 匹配，`content`=执行失败结果
  （arguments 非合法 JSON——客户"失败结果"回填形态；role=tool
  为协议配对必需，K18 实测缺失被 400 拒绝）
- `user` 追问："工具执行失败：arguments 不是合法 JSON。请修正
  参数后重新调用工具完成任务。"（修正行为契约的确定性前提）
- `tools`：`mcp__grafana__update_dashboard` 工具定义
  （parameters 保留顶层结构——历史校验针对 arguments 字符串，
  无需复刻完整 Grafana schema）
- `max_tokens=16384`（16k——覆盖默认档思考+大尺寸修正
  arguments 输出；工单未载 max_tokens，首跑 2048 预算曾被思考
  全耗，上调至 16k 并以 low 兜底）
- 耗光回退（K24/K25 口径）：默认档思考仍可能耗尽预算（无正文
  无调用+finish=length——首跑实测 2048 预算
  reasoning_tokens 全耗）——该形态以
  `reasoning_effort=low`（GLM 顶层思考强度参数）重发（构造不变
  仅加顶层 reasoning_effort 字段；HTTP 200 核心契约首次请求已
  达成），断言相同
- 采样参数不发送——test_k 保持原始测试参数（工单未指定，不注入）

**断言**（硬）：
1. HTTP 200（核心——修复前 400 must be valid JSON，报错复现
   即 FAIL）
2. choices 存在且非空 + message 结构存在
3. 修正行为（修复目的"让模型继续纠正"）：模型发起工具调用
   （追问明确要求修正后重新调用——纯文本回答无法证明纠正），
   每条调用 name 非空、id 非空、arguments 为合法 JSON 对象

**判定矩阵**：
- HTTP 400 报 must be valid JSON（或同型历史 arguments 校验错
  误）→ FAIL（客户缺陷复现——历史未被容忍）
- 200 但无 choices / 无 message 结构 → FAIL（请求被接受但未正
  常生成）
- 模型未发起工具调用 → FAIL（无法验证修复目的"让模型继续纠
  正"）
- 修正调用任一 arguments 非合法 JSON 对象 → FAIL（模型未纠正
  参数——修复目的未达成）
- 无正文无调用+finish=length（思考耗光）→ low 回退重发，断言
  相同；回退后仍无产出 → FAIL（双强度均未产出——留证交开
  发）
- 200 且模型发起修正调用、arguments 合法 → PASS（容忍+自我纠
  正全链路生效）

**设计决策记录**：
- **P0**（按客户工单，AGDC2-19）
- **畸形 arguments 保真浓缩版**：完整保留工单两处括号错误形
  态（文档点名的 `"refId": "A"}]` 缺 `}` 与 `40}}}]` 多 `}`）
  与关键结构（dataset/rawSql/title/uid/操作路径）——PDF 换行
  提取无法保证 3KB 原文字节级保真（损坏的"原文"更糟）；浓缩
  版经程序化验证"恰因两处错误非法、修正两处即合法"
- **场景自检硬编码**：json.loads(常量) 必须失败——防止后续维
  护误改正常量致用例失去缺陷触发能力
- **修正行为硬断言**：开发修复目的即"让模型继续纠正"——追问
  明确要求重新调用工具（行为契约，同 K18 第三个请求口径）；
  修正调用的 arguments 必须为合法 JSON 对象（纠正的直接证据）
- **role=tool 不可少**：assistant 带 tool_calls 后必须紧跟匹配
  工具结果消息（K18 实测配对校验 400）——客户链路本就有工具
  结果回填
- **明确不断言**：历史畸形 arguments 被改写/修复为合法 JSON
  （修复是按字符串保留，不改写历史）
- **耗光回退对齐 K24/K25 口径**：耗光为环境/参数风险形态而非
  契约违约（真实环境首跑实测：修正任务思考量大，2048 预算全被
  reasoning_tokens 耗光、正文与调用均未产出）；预算上调 16k
  （max_tokens=16384——覆盖默认档思考+大尺寸修正输出，工单未
  载 max_tokens）并以 low 兜底，处理口径与 K24/K25 用户指定契
  约一致（low 仅重发耗光请求、构造不变仅加顶层
  reasoning_effort 字段、双强度未产出留证 FAIL）
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- usage 仅日志
- marker：`GLM53`（K 套件按模型分组标记；工单模型 glm-5.3）
- 与 K18 的关系：K18 覆盖"缺 `{` arguments 原样保留不补"
  （router 层容忍）；K27 覆盖 serving 层 must-be-valid-JSON 校
  验容忍 + 模型自我纠正行为——畸形形态互补（K18 缺 `{` vs K27
  缺 `}`/多 `}`），验证层级不同
- K18 第二个请求的 bash arguments 亦为非合法 JSON（缺 `{`）—
  —若 serving 层该校验在配对校验之后生效，K18 可能同路径触发
  本用例覆盖的报错形态（两次运行的先后顺序可揭示校验层级）

### test_output_fields_think_tag_probe (K28)

**背景**：客户问题（AGDC2-24，TR-20261016-02 九章云-模型输出字
段核验）：客户探针报告对被测平台与对照平台（智谱官方）各 3 用
例×5 次流式请求做输出字段核验，三项判据均取自实测报告已给出
判定的标注项：

| # | 测试项 | 判据 | 对应报告标注 |
|---|--------|------|--------------|
| T1 | `content` 尾部裸标记残留 | `content` 是否以裸 `</think>` 结尾；**0 次为通过**（被测平台曾 2/15 不通过） | `trailing_closing_marker_candidate` |
| T2 | 字段回流 | 字段切换序列中是否出现 `content → reasoning`；**0 次为通过** | `reasoning_reentry_candidate` |
| T3 | 工具参数完整性 | `arguments` 合法完整 JSON，且 `reasoning` 内无 `<arg_key>/<arg_value>/</tool_call>`；**100% 为通过** | `tool_parameter_error` |
| 观察 | `length` 截断 | 只记录，不判定 | `length_limited` |

工单原始参数：`stream: true`、`max_tokens 8192`、
`reasoning_effort: max`。

**请求构造**（OpenAI 协议 `/v1/chat/completions` 流式）：
- 数据集 `requests/AGDC2-24/` 三个用例请求体原样加载
  （`artifact_python_target` / `minimal_template_escaped` /
  `PTB-0083_seq406`），工单原始参数 `stream=true`、
  `max_tokens=8192`、`reasoning_effort=max`、`stream_options.
  include_usage` 原样保留
- 模型名由环境注入（覆盖请求体 `model` 字段原值）
- 请求体不含 temperature/top_p/seed（三个用例顶层字段已逐一核
  验：model/messages/tools/reasoning_effort/max_tokens/stream/
  stream_options）——按用户指定保持工单原始请求体不变，不注入
  采样参数（豁免机制针对 wrapper 注入，本用例经探针直发不涉
  及；仅 model 字段按框架约定由环境覆盖）
- 每用例 5 次（`--runs` 硬编码 5，用户指定），共 15 次
- 只评被测平台（用户指定——不设置 CONTROL_BASE/CONTROL_KEY，
  不跑对照平台）
- 探针：`scripts/probe_think_tag.py`（客户单文件探针引入，用例
  仅调用其 `call`/`analyse`/`CASES` 并传递参数）
- raw 输出目录（用户指定规则）：Jenkins 构建（BUILD_NUMBER 存
  在）→ `builds/<TESTER>/<BUILD_NUMBER>/origin_raw/AGDC2-24/
  <model>/`（与 allure-report 同级）；手动执行 →
  `origin_raw/AGDC2-24/<model>/<timestamp>/`（`%Y%m%d_%H%M%S`）
- 除 raw 文件外不输出其他额外文件

**断言**（硬——任一不符合即 FAIL）：
1. 全部请求 HTTP 200 且响应体为可解析 SSE（空体/非流式结构时
   analyse 返回全零值，T1/T2/T3 会被误判全部通过——无法核验即
   FAIL）
2. T1 尾裸出现次数 == 0
3. T2 字段回流出现次数 == 0（字段切换序列含 content→reasoning
   即命中）
4. T3 工具参数完整性 100%（每次 arguments 合法 JSON 且
   reasoning 无原生标记）

**判定矩阵**：
- 任一请求非 200 或响应体非可解析 SSE → FAIL（探针无法完整核
  验——空体/非流式结构时 analyse 返回全零值，T1/T2/T3 会被误
  判全部通过）
- T1 ≥ 1 → FAIL（content 尾部裸标记残留——原始报告缺陷形态复
  现）
- T2 ≥ 1 → FAIL（字段回流——content→reasoning 切换异常）
- T3 < 100% → FAIL（arguments 非法 JSON 或 reasoning 含原生标
  记）
- 三项全部符合 → PASS

**设计决策记录**：
- **P0**（按客户工单，AGDC2-24）
- **客户探针单文件引入**：`scripts/probe_think_tag.py` 与原始
  探针逻辑一致（仅请求体目录指向仓库 requests/AGDC2-24，可用
  `PROBE_REQ_DIR` 覆盖）；用例调用其 `call`/`analyse`/`CASES`
  并传递参数（用户指定集成方式）——核验口径与客户报告完全一
  致
- **只评被测平台**：不设置 CONTROL_BASE/CONTROL_KEY（探针原生
  机制——不设则跳过对照），用例不跑对照平台（用户指定）
- **请求体原样不注入采样参数（用户指定）**：三个用例顶层均不
  含 temperature/top_p/seed——保持工单原始请求体不变（仅
  model 字段按框架约定由环境覆盖）；test_k 整套件不参与全局采样
  覆盖（conftest 模块级规则），本用例经探针直发亦无注入口
- **`--runs` 硬编码 5**：对齐客户报告口径（每用例 5 次，共 15
  条——T1 曾 2/15 命中的样本量）
- **raw 目录双规则**：Jenkins 以 BUILD_NUMBER 判定并落
  builds/<TESTER>/<BUILD_NUMBER>/origin_raw/AGDC2-24/<model>/
  （与 allure-report 同级——BUILD_OUTPUT_DIR 下）；手动落
  origin_raw/AGDC2-24/<model>/<timestamp>/（用户指定）
- **可核验门槛（200+可解析 SSE 双要素）**：analyse 对非 SSE 响
  应体返回全零值（bare=False、seq=""、args_ok=True、native=0）
  ——仅判 HTTP 200 会让"200 空流/非流式结构"缺陷形态误判
  T1/T2/T3 全部通过；故与非 200 一并计入无法核验（K29 同款门
  槛对齐）
- **T2 判定口径**：字段切换序列（delta 侧 content/reasoning
  出现顺序压缩）含 `C→R`（content 后再次 reasoning）即命中—
  —对齐报告 `reasoning_reentry_candidate` 判据
- **T3 双要素**：arguments 串拼接后 json.loads 合法 **且**
  reasoning 不含 `<arg_key>`/`<arg_value>`/`</tool_call>` 原生
  标记（二者任一不满足即该次不完整）——对齐报告判据
- **length 截断只记录**：finish=length 不影响三项判据（报告明
  确只观察不判定）
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 探针 `call()` 逐条落盘 raw（含错误响应体）——原始响应逐字
  节留存对齐客户报告 `origin_raw/` 口径
- marker：`GLM53`（K 套件按模型分组标记；工单模型 glm-5.3）
- 探针的 `run_base`/`replay` 函数本用例未使用（保留供命令行
  独立运行/离线复算）

### test_dual_protocol_zero_delta_tool_call (K29)

**背景**：客户问题（AGDC2-25，九章云 Alaya GLM-5.3 网关）：客户
报告用**同一段业务会话报文**（195 条消息/19 个工具/
`stream: true`/`max_tokens: 4096`）分别请求两种接口：
- `/v1/chat/completions`（OpenAI 协议）：13 次中 **5 次零增量响
  应**——HTTP 200、SSE 结构完整（含 `finish_reason`/`usage`/
  `[DONE]`），但 `delta.content`、`delta.reasoning_content`、
  `delta.tool_calls` **三类增量均为空**，且
  `usage.completion_tokens>0`（整条流仅 1 个空 delta chunk，
  reasoning_tokens 占 completion_tokens 约 99%）；返回工具调用
  仅 4/13
- `/anthropic/v1/messages`（Anthropic 协议）：8/8 返回工具调
  用、零增量 0/8

**判据（用户指定）**：两种协议各自——有效请求 == 10（HTTP 200
且响应可解析）、零增量响应 == 0、返回工具调用 == 100%
（10/10）；任一不符合即 FAIL。

**请求构造**（双协议流式）：
- 数据集 `requests/AGDC2-25/`：`openai_request.json`（OpenAI 协
  议，195 条消息/19 工具）与 `anthropic_request.json`（Anthropic
  协议，同段会话）——脚本口径 `stream=true`、`max_tokens=4096`
  覆盖请求体原值（请求体原值为 128000，探针 `run()` 固定为
  4096，与报告"参数：stream: true、max_tokens: 4096"一致）
- 模型名由环境注入（覆盖请求体 `model` 字段原值）
- temperature/top_p：原始请求未指定——按用户指定**保持不指定**
  （不注入；豁免机制针对 wrapper 注入，本用例经探针直发不涉
  及）
- 每协议 `--n` 硬编码 10 次（用户指定），共 20 次
- 每协议追加 1 次强制工具调用（OpenAI：`tool_choice="required"`；
  Anthropic：`tool_choice={"type":"any"}`——与脚本一致的追加用
  例，**仅观察留日志、不计入判据**）
- 探针：`scripts/probe_alaya.py`（客户单文件探针引入，用例仅调
  用其 `post`/`parse` 并传递参数；`BASE`/`KEY` 由 api_client 注
  入指向被测网关）
- raw 输出目录（用户指定规则，同 K28 口径）：Jenkins 构建
  （BUILD_NUMBER 存在）→ `builds/<TESTER>/<BUILD_NUMBER>/
  origin_raw/AGDC2-25/<model>/`（与 allure-report 同级）；手动执
  行 → `origin_raw/AGDC2-25/<model>/<timestamp>/`
  （`%Y%m%d_%H%M%S`）；其他需要输出的文件与 raw 同级（本用例无
  其他输出）

**断言**（硬——按协议逐一判定，任一不符合即 FAIL）：
1. 有效请求 == 10（HTTP 200 且响应可解析——协议错误或非标
   200 即不计入有效）
2. 零增量响应 == 0（三类增量均空且 usage.completion_tokens>0
   即零增量——客户缺陷形态复现即 FAIL）
3. 返回工具调用 == 10（100%）

**判定矩阵**：
- 有效请求 < 10 → FAIL（协议错误/非标 200——探针无法完整核
  验）
- 零增量 ≥ 1 → FAIL（客户缺陷形态复现）
- 返回工具调用 < 10 → FAIL（未达 100%）
- 三项全部符合 → PASS

**设计决策记录**：
- **P0**（按客户工单，AGDC2-25）
- **客户探针单文件引入**：`scripts/probe_alaya.py` 与原始探针逻
  辑一致（仅 payload 目录指向仓库 requests/AGDC2-25，可用
  `PROBE_REQ_DIR` 覆盖）；用例调用其 `post`/`parse` 并传递参数
  （用户指定集成方式）——零增量判定口径与客户报告完全一致
- **有效请求口径**：HTTP 200 且响应可解析（无 err）——探针
  `parse()` 对非 SSE 非 JSON 体判 err；HTTP 状态与 err 双要素
- **零增量判定口径**：`delta.content`/`reasoning_content`/
  `tool_calls`（Anthropic 侧 `text_delta`/`thinking_delta`/
  `tool_use`）三类增量均为空——对齐报告术语定义
- **强制调用仅观察**：网关工具调用能力的 sanity 信号（报告"变
  量控制"一节即以此佐证网关能力正常），不计入三项判据（用户
  指定判据仅覆盖常规请求）
- **`--n` 硬编码 10**：用户指定；对齐脚本默认值
- **max_tokens=4096 覆盖**：与探针 `run()` 行为一致（请求体原
  值 128000 按脚本口径覆盖；零增量响应实际仅用 625~628，未触
  顶）
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- usage 仅日志
- marker：`GLM53`（K 套件按模型分组标记；工单模型 glm-5.3）
- 探针的 `run`/`replay` 函数本用例未使用（保留供命令行独立运
  行/离线复算）
- 零增量响应与 reasoning_tokens 高占用的相关性为报告观察现
  象，报告未对因果作结论；本用例按用户指定判据判定（零增量
  ==0），不扩展因果断言

### test_responses_api_marker_output_usage (K30)

**背景**：客户问题（合成短文本 Token 对照测试，`/v1/responses`
接口——Responses API，非 chat/completions）：probe 三项断言未
通过：
1. **严重**：请求明确要求只输出 `SYNTHETIC_SHORT_TEXT_MARKER`，
   实际正文输出 `'4b69a88e6b'`（与要求完全无关——模型侧未遵守
   指令，contains 断言失败）
2. **中等**：`input_tokens=52`，超出基准 43 的 ±3% 区间（约
   41.7-44.3）——可能为分词器或消息包装差异
3. **轻微**：`output_tokens` 报告 295，而实际可见输出文本仅 10
   个字符，且 `output_tokens_details.reasoning_tokens` 为 0——
   计数与实际文本量明显不成比例，存在统计口径或隐藏推理未计入
   的疑点

**测试断言点（用户指定——任一失败即整体失败）**：
1. 按请求明确要求的输出原样输出指定内容（无任何额外解释）
2. `input_tokens` 以 43 为基准，超 ±3% 即失败
3. 输出正文和思考消耗的 tokens 要计算正确——总输出 tokens ≈
   正文 + 思考

**请求构造**（按客户原始 curl 还原，Responses API 流式）：
- 端点：`{api_prefix}/responses`（`/v1/responses`，版本感知前
  缀）
- `input` 两条消息：`system`（"只输出指定校验码，不要解
  释。"）+ `user`（"这是 合成短文本 Token 对照测试。请只输出
  SYNTHETIC_SHORT_TEXT_MARKER。"）——`content` 均为
  `input_text` 类型（Responses API 消息结构）
- `stream=true`、`max_output_tokens=1024`（原样）
- 模型名由环境注入（覆盖原值 glm-5.3）
- 采样参数：原始请求未指定 temperature/top_p/seed——保持不指
  定（不注入）
- 流式解析：`response.output_text.delta` 事件合并正文、
  `response.completed` 事件取 usage（兼容事件级 usage 兜底）

**断言**（硬）：
1. HTTP 200 且流式结构完整（含 output_text 增量与 usage）
2. 终态事件 `status == "completed"`（failed/incomplete/cancelled
   或无终态事件均为非正常结束，即失败）
3. 合并正文严格等于 `SYNTHETIC_SHORT_TEXT_MARKER`（校验码原样
   输出，多一个字符即失败——客户缺陷形态：实际输出
   `'4b69a88e6b'`）
4. `usage.input_tokens ∈ [42, 44]`（基准 43 ±3%——区间
   41.71-44.29 的整数取值）
5. `usage.output_tokens` 满足 `reasoning_tokens ≤ output_tokens
   ≤ reasoning_tokens + len(正文)`（总计=思考+正文——
   1 token/字符为宽松上界，正常文本 2-6 字符/token；缺陷形态
   295 tok vs 10 字符远超此界）

**判定矩阵**：
- 非 200 → FAIL（端点不可用/请求被拒）
- 无 output_text 增量或无 usage → FAIL（流式结构不完整，无法核
  验）
- 终态 status ≠ completed（failed/incomplete/cancelled/无终态事
  件）→ FAIL（非正常结束）
- 正文 ≠ 校验码 → FAIL（模型侧未遵守指令——客户缺陷形态复
  现）
- input_tokens ∉ [42,44] → FAIL（超基准 ±3%）
- output_tokens < reasoning_tokens 或 > reasoning + len(正文)
  → FAIL（计数异常——统计口径或隐藏推理未计入疑点）
- 四项全部符合 → PASS

**设计决策记录**：
- **P0**（按客户 probe 三项断言失败）
- **Responses API 事件解析**：`response.output_text.delta` 合并
  正文、终态事件（`response.completed`/`failed`/`incomplete`/
  `cancelled`）取结束状态与 usage（兼容事件级 usage 兜底，适配
  不同实现的事件排布）；`decode errors="replace"` 防坏字节
- **结束状态硬断言**：终态事件 `status` 必须为 `completed`——
  `failed`/`incomplete`/`cancelled` 均为非正常结束；无终态事件
  （流被截断）时 `end_status=None` 同样判失败；usage 存在不等于
  正常结束（usage 可得与结束状态独立判定）
- **正文严格等值**：请求明确"只输出校验码，不要解释"——任何
  多余字符（解释/前后缀/其他内容）均判失败，与客户 contains 断
  言同语义且更强（contains 允许前后杂质，本用例按"只输出"语
  义严格等值）
- **input_tokens 容差换算**：43±3% → [41.71, 44.29] → 整数取
  值 {42, 43, 44}（避免浮点边界歧义）
- **输出计数可执行口径**：客户端无分词器，采用
  `reasoning_tokens ≤ output_tokens ≤ reasoning_tokens +
  len(正文)`——非思考部分不超过 1 token/字符（对 CJK/英文均宽
  松，正常文本 2-6 字符/token 不会误判）；客户缺陷形态（295
  tok vs 10 字符）远超此界，判别力充足；`output_tokens ≥
  reasoning_tokens` 为结构 sanity（总输出不得小于思考部分）
- **采样参数不注入**：原始 curl 未指定——豁免机制针对 wrapper
  注入，本用例手工 payload 直发不涉及
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- usage 同时是断言对象（断言 3/4）与日志对象，全量打印
- marker：`GLM53`（K 套件按模型分组标记；原始请求模型 glm-5.3）
- 若被测网关未实现 `/v1/responses` 端点，断言 1（HTTP 200）将
  如实暴露（404/405）

### test_json_object_nested_empty_content (K31)

**背景**：客户问题（工单 P1 R-01+A-07a/A-07b · json_object 嵌套对象/数组返回空正文，结构化输出）：
- **官方行为**：HTTP 200，content 为合法 JSON（嵌套对象/数组均可解析）
- **贵方实测（R-01）**：HTTP 200、finish_reason=length、content 为空字符串、思考内容占满 max_tokens=256
- **最新实测（A-07a/A-07b，2026-11-03）**：两种请求各 3 发全部该形态（3 采样 0 过）——A-07a 嵌套对象（user.name/user.age/address.city，021-023.json）与 A-07b 数组（3 个 id+title 对象，024-026.json）：空正文、finish_reason=length、reasoning_tokens=256/256（思考占满配额）、prompt_tokens=36/40
- **用户确认（验收口径调整）**：思考消耗配额致空正文/截断在官方与被测均有一定概率发生——核心需求为在 max_tokens 内能返回完整合法 JSON；验收采用预算回退链（用户指定）
- **历史记录**：初版按 R-01 设计（三接口 chat/responses/msg × 两形态 × 各 2 次，断言 256 内正文非空——整改建议口径"思考预算与可见输出分别配额"）；A-07a/A-07b 证据后重构为预算回退链并聚焦 chat+msg 双协议（用户指定"覆盖两种协议"），/v1/responses 轮移除

**测试断言点（预算回退链，任一失败即 FAIL）**：
1. 每链先按工单原值 max_tokens=256 发起（chat 携 response_format=json_object 工单原样）
2. 256 轮 HTTP 200 + 正文非空 + json.loads 成功 + 嵌套结构齐备 → 链直接达标
3. 256 轮不满足（空正文/json 截断或非法/结构不齐）→ 回退 max_tokens=512 同请求重验
4. 512 轮满足 → 测试通过 + 警告留痕（警告显示 256 输出空正文或 json 截断及 finish 状态）
5. 256 与 512 均不满足 → FAIL（输出两轮各自不满足形态）
6. HTTP 非 200 → 直接 FAIL（回退链仅针对正文形态，不覆盖请求层失败）

**请求构造**（chat+msg 双协议 × 工单两形态 × 预算回退链；K31 起用例须验证双协议，用户指定）：
- chat 端点：`{api_prefix}/chat/completions`——`response_format={"type": "json_object"}`、非流式、请求体工单原样（字段序 model/messages/max_tokens/response_format，无 stream 字段）
- msg 端点：`{base_url}/anthropic/v1/messages`（K3 先例——`x-api-key` + `anthropic-version: 2023-06-01` 头）——该协议无 json_object 参数语义，同一 prompt 引导嵌套 JSON、`max_tokens` 为协议必需字段
- 形态 A-07a（嵌套对象）：工单原样提示词「返回一个 JSON 对象,含 user.name、user.age 和 address.city(嵌套结构)。只输出 JSON。」
- 形态 A-07b（数组）：工单原样提示词「返回一个 JSON 数组,含 3 个对象,每个对象有 id(数字)和 title(字符串)。只输出 JSON。」
- 预算回退链：每（协议 × 形态）一链——轮一 256（工单原值）→ 条件回退 512；每链 1-2 请求，双协议 × 两形态共 4 链
- 模型名由环境注入；采样参数/thinking/stream 工单原始未指定——保持不指定（不注入/不传）；相邻请求间隔 3s

**结构校验**（嵌套层级不定——递归宽容，避免对生成细节过严误报）：
- A-07a：输出为 JSON 对象（dict）；递归存在含 `name`+`age` 的 user 嵌套对象与含 `city` 的 address 嵌套对象（顶层或 user 内嵌均认可）
- A-07b：递归找到对象数组（顶层裸数组或 dict 单层包裹——json_object 约束下模型可能以对象包裹数组）且每元素含 `id`+`title`；数量=3 与 id 数字类型留观察不判据

**判定矩阵**：
- 256 轮正文非空+合法 JSON+结构齐备 → 链 PASS（无回退）
- 256 轮空正文/json.loads 失败（截断或非法）/结构不齐 → 触发 512 回退
- 512 轮正文非空+合法 JSON+结构齐备 → 链 PASS + 警告留痕（警告显示 256 输出空正文或 json 截断及 finish 状态——思考消耗配额属官方/被测共有随机形态）
- 256 与 512 均不满足 → FAIL（输出两轮各自不满足形态与正文头）
- HTTP 非 200（任一轮）→ 直接 FAIL（回退链仅针对正文形态）
- finish_reason=length / stop_reason=max_tokens 且正文完整合法 → 不判失败，观察留痕

**设计决策记录**：
- **P1**（按客户工单 P1 R-01+A-07a/A-07b）
- **预算回退链替代"256 内必须非空"硬口径（用户指定）**：思考
  消耗配额致空正文/截断在官方与被测均有概率发生（A-07 两请求
  3 采样 0 过），单点预算硬断言必然随机失败；回退链验证核心需
  求"在 max_tokens 内能返回完整合法 JSON"——256 达标最优，512
  达标为通过+警告留痕，两轮均失败才判 FAIL
- **警告走 test_logger.warning**：512 达标时警告显示 256 输出空
  正文或 json 截断及 finish 状态——报告可见，非判据
- **HTTP 非 200 不回退直接 FAIL**：回退链针对正文形态（空/截
  断），请求层失败（400/5xx）属另一缺陷域，回退会掩盖该形态
- **工单原样请求**：A-07a/A-07b 提示词与请求体原样（chat 字段
  序 model/messages/max_tokens/response_format、无 stream 字
  段——A-03/A-04 先例）；msg 镜像被测维度（prompt+预算回
  退），协议无 json_object 语义不传 response_format
- **结构校验递归宽容**：A-07a 提示词"嵌套结构"未限定层级
  （user/address 顶层或内嵌均认可——递归查找）；A-07b
  json_object 约束下可能裸数组或对象包裹——两形态均认可；数
  量=3 与 id 数字类型留观察（模型生成细节随机，验证"完整合
  法"而非逐字段等值）
- **每链单发不重复（原各 2 次移除）**：原重复 2 次为降低思考
  长度随机性逃逸；新口径下 256 失败本身合法（回退处理），随
  机性由回退链覆盖，重复无判定增益
- **/v1/responses 轮移除（用户指定"覆盖两种协议"）**：初版三
  接口覆盖 responses 的 text.format 语义；A-07 重构聚焦
  chat+msg 双协议（与 K31 起双协议要求一致）；responses
  json_object 语义如需恢复须另行确认
- **send/链分离**：send_chat/send_msg 仅采集（HTTP 200 断言+
  观察留痕），正文判定统一由 run_budget_chain 执行——回退逻
  辑单点维护
- **chat 协议用 _post_with_retry、msg 协议用 session.post**
  （对齐 K11/K30/K3 先例）；msg 正文聚合 content 数组中
  type=="text" 项的 text 字段

**观察记录（不计判据，留日志）**：每轮 finish_reason/stop_reason、正文与 reasoning 长度、completion_tokens/reasoning_tokens（A-07 形态=空正文+reasoning_tokens=256 留痕）、usage（msg）、数组数量 vs 3、耗时；收尾统计 4 链中直接达标/经回退达标计数

**注意事项**：
- 4 链 × 1-2 请求（共 4-8 请求）× 思考模型单发 10-30s，总耗时约 1-4 分钟
- 警告≠失败：经回退达标的链为 PASS，阅读报告时警告仅提示 256 预算下的配额消耗形态
- 512 轮同样可能空正文（思考更长）——属 FAIL 判据（两轮均不满足）
- msg 侧依赖模型按 prompt 引导输出 JSON——引导失败（非法 JSON/结构不齐）同链判定
- marker：`GLM53`（K 套件按模型分组标记；工单未指定模型，按新用例惯例归 GLM-5.3）
- 不进 smoke 集：新用例首跑观察期

### test_temperature_range_validation (K32)

**背景**：客户问题（工单 P1 R-02+A-03 · temperature=1.5 被拒绝（原
厂接受），参数校验）：
- **官方行为**：HTTP 200（原厂取值区间 [0, 2]，1.5 合法）
- **贵方最新实测（A-03，2026-11-03）**：chat 三发 temperature=1.5
  全部 HTTP 400，错误体「temperature 超出范围 [0, 1]」
  (bad_response_status_code)——本地收紧到 [0, 1]
- **历史形态（R-02）**：6 发全部 HTTP 400，错误体为通用「模型服
  务调用失败」(upstream_error)
- **整改建议（即预期结果，用户指定）**：放开 temperature 到原厂
  支持的 [0, 2] 区间（原合法区间 [0, 2) 调整为 [0, 2]——上界端
  点 2.0 移入放行），或按原厂取值原样透传，不做本地收紧；同时保
  留非法参数校验（越界 400 并指明参数名与合法区间）
- **历史记录**：初版按 R-02 设计（chat [0, 2) 半开区间、越界点含
  2.0、单发放行轮）；2026-11-03 A-03 证据后调整为 [0, 2] 含端
  点、越界点改 2.5、工单三发复现替换原单发放行轮；2026-11-09
  首跑边界轮 60s 超时（无 max_tokens 无界生成长尾）后按用户指
  定调整：边界轮请求对齐 A-03 短形态、断言对齐状态语义口径；
  同日二次按用户指定：新增 0.0 左边界双协议放行轮、chat 越界
  轮补 max_tokens=1024（所有轮均须 max_tokens 限制）

**测试断言点（按整改建议设计，任一失败即 FAIL）**：
1. chat A-03 复现轮（三发）：temperature=1.5 → HTTP 200 + 响应
   体合法 JSON 且 choices 非空（正文/finish_reason 留观察）
2. chat 边界轮：temperature=2.0 → HTTP 200 + 响应体合法 JSON 且
   choices 非空（正文/finish_reason 留观察——对齐 A-03 轮口径，
   用户指定 2026-11-09：主判据=2.0 被接受 200）
3. chat 左边界轮：temperature=0.0 → HTTP 200 + 响应体合法 JSON
   且 choices 非空（正文/finish_reason 留观察——口径同 2.0 边
   界轮，用户指定 2026-11-09 新增：主判据=0.0 被接受 200）
4. chat 越界轮：temperature=2.5 / -0.5 → HTTP 400 + 错误体指明
   参数名与合法区间（上界数字 2）
5. msg 放行轮：temperature=0.5 / 0.0 → HTTP 200 + 正文非空 +
   stop_reason 自然结束（0.0 为下界端点，用户指定 2026-11-09
   新增，口径同 0.5）
6. msg 越界轮：temperature=1.5 / 2.0 / -0.5 → HTTP 400 + 错误
   体指明参数名与合法区间（上界数字 1）
7. 每发 60s 硬超时：超时即 FAIL（挂起/严重延迟异常信号留
   痕——本例小请求正常返回毫秒级-秒级）

**请求构造**（双协议覆盖——K31 起用例须验证 chat 与 msg 双协议，
用户指定；chat 放行点按工单 A-03 三发依序复现，其余组合每组合
1 次——K6 先例）：
- chat 端点：`{api_prefix}/chat/completions`（非流式直发
  `_post_with_retry`，每发 60s 硬超时——`timeout=K32_HARD_TIMEOUT`
  用例内自定覆盖全局 timeout，仅本用例生效不影响他例）
  - A-03 复现轮（三发）：工单原样请求体——content="只回复:好"
    （字符串）、max_tokens=32、temperature=1.5，字段序
    model/messages/max_tokens/temperature，**无 stream 字段**
    （工单未带——不传）；工单三发采集间隔 1s，复现按套件相邻
    3s（节奏非判据）
  - 边界轮（测试自构造，用户指定 2026-11-09 对齐 A-03 短形
    态）：content="只回复:好"、max_tokens=32、无 stream 字
    段——与 A-03 复现轮同形态（本例主目的为验证 temperature
    支持范围，短请求短响应即可；原长 prompt+不传 max_tokens
    在 2.0 极端温度下思考乱码无界生成长尾，首跑 60s 超时，
    curl 复核服务端 200 正常放行——非服务端缺陷）
  - 左边界轮（测试自构造，用户指定 2026-11-09 新增）：
    temperature=0.0、长形态——单 user 闲聊（"请用一句话介绍
    你自己。"）+ max_tokens=1024 + stream=False（[0, 2] 含下
    界端点，此前下界仅由 -0.5 越界轮间接验证）
  - 越界轮（测试自构造）：单 user 闲聊（"请用一句话介绍
    你自己。"）；temperature=2.5/-0.5——直进 payload，原
    样保留并豁免全局采样覆盖（top_p/seed/thinking 工单未
    指定，不注入；max_tokens=1024——所有轮均须 max_tokens
    限制，用户指定 2026-11-09，防网关错误放行时无界生成长
    尾；stream=False）
- msg 端点：`{base_url}/anthropic/v1/messages`（K3 先例——
  `x-api-key` + `anthropic-version: 2023-06-01` 头，session.post
  直发，同样 60s 硬超时 `timeout=K32_HARD_TIMEOUT`）；放行点
  0.5（工单原值 1.5 在 Anthropic 官方区间 [0, 1] 语义下越界，
  不可作放行点）与 0.0（下界端点，用户指定 2026-11-09 新增
  ——双协议口径一致）；越界点 1.5（工单原值——与 chat 侧同
  值不同判）、2.0、-0.5；`max_tokens=1024` 为协议必需字段
- 模型名由环境注入

**断言（硬）**：
1. chat A-03 三发均 HTTP 200（缺陷形态：三发全部 400
   「temperature 超出范围 [0, 1]」——本地收紧；历史形态：6 发
   通用 upstream_error）
2. chat A-03 三发响应体合法 JSON 且 choices 非空（200 须为有效
   补全结构）
3. chat 边界轮 HTTP 200（[0, 2] 含上界端点——用户指定口径调整）
4. chat 边界轮响应体合法 JSON 且 choices 非空（200 须为有效补
   全结构；正文/finish_reason 留观察——对齐 A-03 轮口径，用户
   指定 2026-11-09）
5. chat 左边界轮 HTTP 200（[0, 2] 含下界端点 0.0——用户指定
   2026-11-09 新增验证）
6. chat 左边界轮响应体合法 JSON 且 choices 非空（200 须为有效
   补全结构；正文/finish_reason 留观察——口径同 2.0 边界轮）
7. chat 越界轮 HTTP 400（[0, 2] 闭区间不含 2.5/-0.5——越界被静
   默放行/其他状态均为整改未达标）
8. chat 越界轮错误体含参数名 `temperature`（大小写不敏感）
9. chat 越界轮错误体含上界数字 `2`（合法区间痕迹——辅助下限口
   径，见注意事项）
10. msg 放行轮（0.5 与 0.0）HTTP 200 且正文非空、`stop_reason`
    存在且非 "max_tokens"（自然结束——Anthropic 枚举含
    end_turn/stop_sequence 等形态，宽松口径；0.0 为下界端点，
    用户指定 2026-11-09 新增，口径同 0.5）
11. msg 越界轮 HTTP 400
12. msg 越界轮错误体含参数名 `temperature`（大小写不敏感）
13. msg 越界轮错误体含上界数字 `1`（该协议合法区间痕迹）

**观察记录（不计判据）**：A-03 三发与 2.0/0.0 边界轮每发正文长
度、finish_reason、耗时——max_tokens=32 小配额下默认思考计入
共享配额（R-01 未整改）易 length/空正文（2.0 极端温度下思考乱
码更易耗尽配额；0.0 长形态 1024 配额贪心解码通常正文非空+
stop），属 K31 域形态；A-03 与 2.0/0.0 边界轮判据均为 HTTP 状
态语义（1.5/2.0/0.0 被接受=200）

**判定矩阵**：
- chat A-03 三发任一发非 200 → FAIL（缺陷复现——原厂区间内合
  法值被拒/本地收紧）
- chat 边界 2.0/0.0 非 200 → FAIL（区间端点未放行——口径 [0, 2]
  含上/下界端点未生效，0.0 为用户指定 2026-11-09 新增）；边界
  轮正文/finish_reason 留观察不计判据（对齐 A-03 轮口径，用户
  指定 2026-11-09——空正文+length 属 K31 域形态，非本例判据）
- chat 越界点非 400 → FAIL（越界未被拒绝——静默放行同样未达标）
- 400 但错误体不含 "temperature" → FAIL（缺陷形态复现——通用
  「模型服务调用失败」不含参数名，整改未达标）
- chat 400 且含参数名但不含数字 2 / msg 400 且含参数名但不含数
  字 1 → FAIL（未指明对应协议合法区间）
- msg 放行 0.5/0.0 非 200 → FAIL（Anthropic 官方区间内合法值/
  下界端点被拒——0.0 为用户指定 2026-11-09 新增）
- msg 越界 1.5 非 400 → FAIL（msg 语义下越界被静默放行——若网
  关一刀切按 chat 区间 [0, 2] 放行 1.5，将在此如实暴露）
- 三发 1.5→200+choices 非空、2.0/0.0→200+choices 非空（正
  文/finish 留观察）、2.5/-0.5→400+参数名+区间（chat）；0.5/
  0.0→200+自然结束（msg）/1.5、2.0、-0.5→400+参数名+区间
  （msg）→ PASS
- 任一发 60s 硬超时内无响应 → FAIL（挂起/严重延迟异常信号
  留痕——本例小请求正常返回毫秒级-秒级）

**设计决策记录**：
- **P1**（按客户工单 P1 R-02+A-03）
- **区间口径调整（用户指定）**：原 chat 合法区间 [0, 2) 调整为
  [0, 2]（含上界端点）——2.0 由越界点移入放行，越界点改取 2.5
  （上界外）；整改预期「放开到原厂 [0, 2] 或原样透传不做本地收
  紧」，端点行为以 2.0 放行核验
- **chat 放行点按工单 A-03 三发依序复现**：工单原样请求体
  （content="只回复:好"、max_tokens=32、字段序、无 stream 字
  段）——三发为工单采集口径，替换原单发放行轮；间隔按套件 3s
  （工单采集 1s，节奏非判据）
- **A-03 复现轮断言收缩为状态语义**：硬断言 200+choices 非空；
  正文/finish_reason 留观察——max_tokens=32 小配额下默认思考计
  入共享配额（R-01 未整改）易 length/空正文（K31 域形态），若强
  断言正文非空会把「temperature 已正确放行」误判为失败；与 K35
  断言收缩同理（客户预期仅定义状态语义）
- **msg 侧维持 Anthropic [0, 1] 口径**：A-03 证据与整改预期均未
  涉及 msg——msg 按协议官方语义分别校验（原设计）；若整改将透
  传范围扩至 msg 协议，须另行确认口径再调整
- **双协议同值不同判保留**：1.5 chat 放行/msg 拒绝、2.0 chat 放
  行/msg 拒绝——验证网关按协议语义分别校验而非一刀切；若一刀
  切复用 chat 区间，msg 越界轮将以 200 放行 FAIL 如实暴露
- **msg 放行点取 0.5 而非工单原值 1.5**：1.5 在 Anthropic 官方
  [0, 1] 语义下越界，不可作放行点；取 [0, 1] 内合法中位点验证
  msg 侧放行能力
- **越界点取双向边界**：2.5（上界外——[0, 2] 闭区间不含）与
  -0.5（负向——下界 0 含、负数不含）
- **区间痕迹断言口径（chat 含数字 2/msg 含数字 1）为下限设计**：
  错误文案形态多样（"[0, 2]" / "0 to 2"……），逐文案精确匹配会
  误报；含 "temperature" + 对应上界数字已可完全区分历史缺陷形
  态（通用「模型服务调用失败」两者皆不含）
- **每组合 1 次（A-03 三发除外）**：参数校验为确定性行为（K6 先
  例）；A-03 三发为工单复现口径（工单采集 3 发——一致性复现），
  其余组合无需重复
- **thinking 不传（chat 全轮）**：thinking 工单未指定——不注
  入；max_tokens 限制为全轮必须（见「左边界 0.0 新增验证 + 全
  轮 max_tokens 限制」条）；A-03 复现轮 max_tokens=32 为工单
  原值必须保留；msg 侧 max_tokens 为协议必需字段（1024 单句
  闲聊合理值）
- **左边界 0.0 新增验证 + 全轮 max_tokens 限制（用户指定，
  2026-11-09）**：①需验证左边界 0.0——[0, 2] 闭区间含下界端
  点，原设计下界仅由 -0.5 越界轮间接验证；chat 与 msg 双协议
  同步新增（msg [0, 1] 下界端点同为 0.0，双协议口径一致）——
  chat 左边界轮长形态（K32_PROMPT+max_tokens=1024，与越界轮
  同族），判定对齐 2.0 边界轮口径（200+choices 非空，正文/
  finish 留观察——主判据=0.0 被接受 200）；msg 左边界放行轮
  口径同 0.5 放行轮（200+正文非空+stop_reason 自然结束——
  0.0 贪心解码正常生成可满足）。②所有轮均须 max_tokens 限制
  ——当前无限制的 chat 越界轮取 1024（防网关错误放行时无界
  生成长尾撞 60s 超时，FAIL 形态更干净）；A-03/2.0 轮 32、
  msg 轮 1024 维持
- **边界轮对齐 A-03 短形态（用户指定，2026-11-09）**：首跑（同
  日 Jenkins build 374）边界轮以长 prompt+不传 max_tokens 请求，
  60s 硬超时零响应 FAIL；用户 curl 复核（temperature=2.0、显式
  thinking、max_tokens=1024）服务端 200 正常放行、配额全耗于极
  端温度乱码 reasoning（finish=length、正文空）——服务端正常，
  属无 max_tokens 无界生成长尾，非服务端缺陷。按用户口径调整：
  本例主目的为验证模型服务支持的 temperature 取值范围（合法
  200/非法 400），无需长请求长响应——边界轮请求与 A-03 轮同形
  态（content="只回复:好"、max_tokens=32、无 stream 字段），
  断言对齐 A-03 轮口径（200+choices 非空，正文/finish_reason
  留观察——2.0+32 小配额+默认思考计入几乎必为空正文+length，
  强断言正文非空会把「2.0 已正确放行」误判为失败）；硬超时维
  持 60s 不变（短配额生成秒级返回）
- **直发 payload**：temperature 直进请求体（K 套件豁免机制下原
  样保留，无全局注入口）
- **每发 60s 硬超时（用户指定，2026-11-06）**：本例全部为小请
  求——越界轮 400 在参数校验层毫秒级返回、A-03 轮 max_tokens=32
  秒级、放行轮单句闲聊秒级，无需按全局 1200s（config.yaml
  global.timeout）等待——挂起/严重延迟时快速失败（超时即 FAIL
  留痕并报告超时值）；实现上经 `_post_with_retry` 新增的可选
  `timeout` 参数（默认 None=沿用全局值，不改全局、不影响其他
  用例）与 msg 直发 `timeout=K32_HARD_TIMEOUT` 传参，仅本用例
  生效；ReadTimeout 本就不重试（`_RETRYABLE_EXCEPTIONS` 仅
  ConnectionError），单发零字节挂死 60s 即断（connect 级挂死理
  论上可重试至 ~4×60s+退避，仍远优于原 1200s）

**注意事项**：
- 区间痕迹数字断言（"2"/"1"）为辅助下限口径：A-03 形态错误体含
  request id 数字串（如 "20261103…"），数字断言可能被 request id
  恒满足——本地收紧缺陷的主判据在放行轮（1.5/2.0/0.0 →
  200），越界轮断言未满足时仍如实 FAIL 交人工复核
- 若被测实现存在模型级温度档联动（如 thinking 档位契约），chat
  放行轮 FAIL 即按工单口径如实暴露（整改要求按 [0, 2] 放行，模
  型档位联动不得窄于原厂区间）
- 越界轮若返回 422/500 等非 400 状态：同样 FAIL（整改明确要求
  400）
- msg 越界轮 "1" 断言为下限口径：若错误体含其他数字组合（如
  HTTP 状态码字样）误含 "1"，按关键词组合 "temperature"+"1" 判
  定
- marker：`GLM53`（K 套件按模型分组标记；工单未指定模型，按新
  用例惯例归 GLM-5.3）
- 不进 smoke 集：新用例首跑观察期

### test_top_logprobs_stable_support (K33)

**背景**：客户问题（工单 P2 A-04 · top_logprobs=5 被拒，参数校
验）：
- **官方行为（不变）**：top_logprobs=5 官方 HTTP 200 接受（未开
  logprobs 时也接受）
- **贵方最新实测（A-04，2026-11-03）**：chat 三发 top_logprobs=5
  单独出现（无 logprobs）全部 HTTP 400，错误体「top_logprobs is
  only allowed when logprobs is enabled」
  (top_logprobs_requires_logprobs)——对未开 logprobs 的
  top_logprobs 额外拒绝
- **整改建议（即预期结果）**：按官方行为处理 top_logprobs（未开
  logprobs 时也接受），不额外拒绝；若上游确实不支持，错误体应
  说明能力缺失而非参数非法，避免客户端反复重试
- **用户判定口径（2026-11-06）**：top_logprobs=5 不要拒绝、按官
  方 HTTP 200 即可；正文为空不判定失败
- **历史记录**：初版按 R-03 设计（成对双协议 12 发稳定性核
  验）；2026-11-03 A-04 证据后新增 chat 工单三发复现轮（top_
  logprobs 单独出现）与 msg A-04 镜像轮；2026-11-06 用户明确判
  定口径（200 即可、正文为空不判定失败）并将"正文非空"断言放
  宽为留观察；同日 R-03 两轮移除、仅保留 A-04 请求（用户指定）

**测试断言点（任一失败即 FAIL）**：
1. chat A-04 复现轮（三发）：top_logprobs=5 单独出现（无
   logprobs）→ HTTP 200 + 响应体合法 JSON 且 choices 非空（正文/
   finish_reason/logprobs 结构留观察）
2. msg A-04 镜像轮（3 发）：状态码完全一致——全 400 且错误体指
   明字段（含 `logprobs`）或全 200；正文为空不判定失败（留观
   察）；混现即 FAIL

**请求构造**（双协议覆盖——K31 起用例须验证 chat 与 msg 双协议，
用户指定）：
- chat 端点：`{api_prefix}/chat/completions`（非流式直发
  `_post_with_retry`）
  - A-04 复现轮（三发）：工单原样请求体——top_logprobs=5 单独出
    现（**无 logprobs 字段**——A-04 缺陷形态即"未开 logprobs 也
    应接受"）、content="只回复:好"（字符串）、max_tokens=32，
    字段序 model/messages/max_tokens/top_logprobs，**无 stream 字
    段**（工单未带——不传）；工单三发采集间隔 1s，复现按套件相
    邻 3s（节奏非判据）
- msg 端点：`{base_url}/anthropic/v1/messages`（K3 先例——
  `x-api-key` + `anthropic-version: 2023-06-01` 头，session.post
  直发）
  - A-04 镜像轮（3 发）：top_logprobs=5 单独出现（无 logprobs）、
    content="只回复:好"（字符串——工单原样）、max_tokens=512
     （协议必需字段套件值——工单 32 为 chat 小配额口径，取 512
     避免 200 分支空正文误判）
- 模型名由环境注入

**断言（硬）**：
1. chat A-04 三发均 HTTP 200（缺陷形态：三发全部 400
   「top_logprobs is only allowed when logprobs is enabled」
   top_logprobs_requires_logprobs——额外拒绝）
2. chat A-04 三发响应体合法 JSON 且 choices 非空
3. msg A-04 镜像 3 发状态码集合大小为 1（统一行为）
4. msg A-04 全 400 → 每发错误体含 `logprobs`（top_logprobs 子串
   覆盖，大小写不敏感）；全 200 → 状态统一即达标，正文为空不
   判定失败（留观察）

**观察记录（不计判据）**：A-04 复现轮每发正文长度、finish_
reason、logprobs 有无、耗时——max_tokens=32 小配额下默认思考计入
共享配额（R-01 未整改）易 length/空正文（K31 域形态）；logprobs
未开时官方 200 响应结构形态未采集（客户预期仅定义接受语义）；msg
A-04 镜像 200 分支正文为空的发逐发 warning 留痕

**判定矩阵**：
- chat A-04 三发任一发非 200 → FAIL（缺陷复现——未开 logprobs
  的 top_logprobs 被额外拒绝，A-04 形态留证）
- msg A-04 镜像 200/400 混现 → FAIL（行为不统一缺陷在 msg 协议
  复现——整改要求统一行为）
- msg 全 400 但错误体不含 "logprobs" → FAIL（能力缺失未指明字
  段——整改建议："错误体应说明能力缺失"便于客户端停止重试）
- msg 全 200 但任一发正文空 → 留观察不计判据（用户口径：
  top_logprobs=5 不拒绝、官方 200 即可——正文为空不判定失
  败，用户指定 2026-11-06；空作答形态留 warning 供人工分析）
- A-04 三发均 200；msg A-04 镜像统一（全 400 指明字段或全
  200）→ PASS（额外拒绝与行为不统一缺陷在两协议均未复现）

**设计决策记录**：
- **P2**（按客户工单 P2 A-04）
- **A-04 复现轮断言收缩为状态语义**：硬断言 200+choices 非空；
  正文/finish_reason/logprobs 结构留观察——max_tokens=32 小配额
  下默认思考计入共享配额（R-01 未整改）易 length/空正文（K31 域
  形态），且 logprobs 未开时官方 200 响应结构形态未采集（客户
  预期仅定义接受语义"未开 logprobs 时也接受，不额外拒绝"）——
  与 K32/K35 断言收缩同理
- **R-03 轮移除（用户指定 2026-11-06）**：用户明确 K33 判定口
  径为 top_logprobs=5 不拒绝、按官方 HTTP 200 即可、正文为空不
  判定失败——仅保留 A-04 请求（chat 三发复现 + msg 镜像 3 发）；
  原 R-03 成对双协议 12 发稳定性轮与 logprobs 结构核验整体移
  除，判据聚焦参数放行与统一行为
- **msg A-04 镜像轮（3 发）**：A-04 工单证据仅 chat，msg 侧镜像
  被测维度（top_logprobs 单独出现）——验证 msg 协议对该形态的
  处理是否统一（K31 起双协议要求，用户指定"覆盖两种协议"）
- **msg 镜像 max_tokens 取 512 而非工单 32**：工单 32 为 chat 小
  配额口径；msg 200 分支正文为空不判定失败（用户口径），512 降
  低空正文观察噪音；被测维度 top_logprobs 单独出现已镜像，协议
  必需字段取套件合理值
- **正文为空不判定失败（用户口径，2026-11-06）**：用户明确
  K33 判定口径——top_logprobs=5 不要拒绝、按官方 HTTP 200 即
  可；正文为空不判定失败。chat A-04 复现轮与 msg A-04 镜像轮
  分支 B 原有的"正文非空"硬断言全部放宽为留观察（空正文逐发
  warning 留痕，人工可查）；判据聚焦参数放行与统一行为，不判
  生成形态
- **msg 断统一性而非 200**：Anthropic 协议无 logprobs 参数语义
  （官方对未知字段应 400 拒绝）——按官方 200 预期会与"网关忽略
  未知参数统一作答"的现实实现冲突；msg 侧以整改建议的两分支
  （统一能力缺失说明/统一放行）为达标口径，混现即 FAIL——两协
  议判据不同但核心一致（行为统一）

**注意事项**：
- 双协议 6 发 × 思考模型单发 10-30s，总耗时约 1-3 分钟——P2
  选测可接受，不进 smoke 集
- msg 统一性判定需收满同一轮全部发数后判（单发无法判定不稳
  定）——失败时逐发状态码全量进断言消息
- 正文为空不判定失败（用户口径）——空正文发逐发 warning 留
  痕（含 tag/body 前 300 字符），人工可查
- A-04 复现轮若 200 且响应含 logprobs.top_logprobs（未开
  logprobs 也返回结构）——观察留痕不计判据，人工评估口径
- marker：`GLM53`（K 套件按模型分组标记；工单未指定模型，按新
  用例惯例归 GLM-5.3）
- 不进 smoke 集：新用例首跑观察期；P2 选测

### test_multimodal_rejection_error_detail (K34)

**背景**：客户问题（工单 P2 R-04 补充证据 · A-01 msg 协议多模
态静默丢弃，多模态）：
- **官方行为**：glm-5.3 为非多模态模型——请求携带图片/音频/
  视频/文档（base64 与 URL 两种载体）必须返回 400；返回 2xx
  即不合格
- **原始问题（贵方实测 A-01，2026-11-03 采集，5 发全 msg 协
  议）**：HTTP 200——该拒未拒，媒体块被静默丢弃：prompt_tokens
  仅 17-43（媒体未进入分词器），正文自述『没有收到视频/音频/
  文档』；同一素材在 chat 协议下渠道返回 400——同一渠道、同
  一文件、两种协议两种结果
- **整改建议（客户给出）**：在 /v1/messages → OpenAI 转换层对
  media block（video/audio/document）做前置校验，返回 400 并
  给出明确文案；不得剥离媒体块后继续转发；URL 载体（http/
  https 媒体链接）同样必须返回 400，不得自行抓取、转文字或降
  级为纯文本；另外 chat 协议也应该相同的处理
- **历史记录**：工单初版口径为 chat 与 msg 双协议 8 发均通用
  「模型服务调用失败」(upstream_error)（20261104 Jenkins 首跑
  chat 侧实测整改错误体为中文「该模型不支持图片输入」code
  1210——类型维度已指明）；客户新证据 A-01 明确缺陷形态为
  msg 侧静默丢弃返回 200，本用例按工单原始记录复现并做双协
  议一致性核验（用户指定：message 协议和 chat 协议都要 5 轮
  请求——msg 5 发缺陷复现轮 + chat 5 发同素材同序镜像核验
  轮，共 10 发）

**测试断言点（每发任一失败即 FAIL 并报告轮标签）**：
1. HTTP 400（官方要求：非多模态模型收到媒体块——base64 与
   URL 两种载体——必须 400，返回 2xx 即不合格）
2. 错误体指明该发媒体类型——含对应关键词，中英任一命中
   （`document`/文档/pdf、`audio`/音频/语音、`video`/视频；
   大小写不敏感）

**请求构造**（双协议各 5 发共 10 发；用户指定：message 协议
和 chat 协议都要 5 轮请求——msg 侧按工单 A-01 原始记录依序
复现（缺陷复现轮），chat 侧同素材/同提示词/同块序镜像（整
改『chat 协议也应该相同的处理』——一致性核验轮））：
- msg 协议与头：`{base_url}/anthropic/v1/messages`（K3 先
  例——`x-api-key` + `anthropic-version: 2023-06-01` 头，
  session.post 直发），5 发（媒体块与文本块顺序按工单原样）：
  1. `document` × base64（`media_type=application/pdf`、
     `data=<最小 PDF base64>`）+ text『文档中的文字是什么?
     简答。』（媒体块在前）
  2. text『这段音频是什么类型的声音?简答。』+ `audio` ×
     base64（`media_type=audio/wav`、`data=<最小 WAV
     base64>`）（文本块在前）
  3. `video` × base64（`media_type=video/mp4`、`data=<最小
     MP4 base64>`）+ text『简要描述视频内容。』
  4. `video` × URL（`source.type=url`、沿用本仓现有公网视频地
     址 `https://interactive-examples.mdn.mozilla.net/media/
     cc0-videos/flower.mp4`——test_c 视频理解 C5 同款；工单
     原 test-videos.co.uk 地址不复用，用户指定保留现有 URL）
     + text『简要描述视频内容。』
  5. `video` × base64（同第 3 发生成数据）+ text『这段视频前
     半段的底色和中间显示的数字是什么？后半段的底色和中间
     显示的数字是什么？按先后顺序一句话回答。』（工单第 5
     采集提问原样）
- chat 协议：`{api_prefix}/chat/completions`（`_post_with_
  retry` 非流式直发），5 发（同素材、同提示词、同块序镜像；
  part 映射——document → file part、audio → input_audio、
  video → video_url）：
  1. `file` part × base64（`file_data=data:application/pdf;
     base64,<最小 PDF base64>`——OpenAI chat 协议文档输入标
     准形态）+ text part『文档中的文字是什么?简答。』（媒体
     part 在前）
  2. text part『这段音频是什么类型的声音?简答。』+
     `input_audio`（`data=<最小 WAV base64>`、`format=wav`）
     （文本 part 在前）
  3. `video_url` × data URL（`data:video/mp4;base64,<最小
     MP4 base64>`）+ text part『简要描述视频内容。』
  4. `video_url` × URL（`K34_VIDEO_URL`——同 msg 第 4 发
     MDN flower.mp4）+ text part『简要描述视频内容。』
  5. `video_url` × data URL（同第 3 发）+ text part『这段视
     频前半段的底色和中间显示的数字是什么？后半段的底色和
     中间显示的数字是什么？按先后顺序一句话回答。』
- 请求体为工单原始格式（双协议同形）：`max_tokens=1024`
  （msg/chat 10 发同值工单原值，msg 协议必需字段，豁免注
  入）/messages/model，不含 stream 字段（两协议默认均非流
  式）；thinking/采样参数工单未含——不传（不注入）；模型
  名由环境注入；相邻间隔 3s

**断言**（硬，每发）：
1. HTTP 400（200=媒体被静默丢弃后纯文本作答——工单 A-01 缺
   陷形态，留 body 全文证；2xx 同判；500 等=非合规拒绝）
2. 错误体含该发媒体类型关键词，中英任一命中（经
   `K34_MEDIA_KEYWORDS` 展开：document=（document/文档/
   pdf）、audio=（audio/音频/语音）、video=（video/视频）；
   大小写不敏感——英文 lower 匹配、中文原样匹配不受 lower
   影响；URL 载体与 base64 载体判据相同——整改明令"URL 载
   体同样必须返回 400"）

**判定矩阵**：
- 任一发非 400 → FAIL（200=媒体块被静默丢弃后纯文本作答——
  工单 A-01 缺陷形态：prompt_tokens 仅 17-43、正文自述未收
  到媒体，留 body 全文证；500 等=非合规拒绝）
- 400 但错误体不含该发关键词（中英均未命中）→ FAIL（缺陷复
  现——通用「模型服务调用失败」upstream_error 未指明媒体类
  型与字段，客户端无法定位）
- 10 发（双协议各 5 发）全部 400 且错误体含对应关键词（中英
  任一命中）→ PASS（拒绝合规 + 媒体类型可定位 + 覆盖工单
  A-01 全部 5 发（msg 侧）与 chat 侧镜像：文档/音频/视频
  base64 + 视频 URL 载体 × 双协议）
- 错误体是否含 `text`（取值范围 `['text']` 痕迹）→ 观察日
  志，不计判据

**设计决策记录**：
- **P2**（按客户工单 P2 R-04）
- **按工单原始记录 5 发依序复现 + chat 镜像（用户指定）**：
  客户新证据 A-01 提供了 5 发完整请求/响应原始记录——msg 侧
  5 发请求参数与类型按客户原始请求依序（document×base64 →
  audio×base64 → video×base64 → video×url → video×
  base64），媒体块与文本块顺序按工单原样（第 1 发媒体块在
  前、第 2 发文本块在前）；提示词逐字保留（含半角/全角问号
  差异——工单原样）
- **双协议各 5 发（用户指定）**：A-01 5 发全 msg 协议——缺陷
  在 msg 侧（msg 5 发为缺陷复现轮）；整改要求『chat 协议也
  应该相同的处理』——chat 5 发为同素材/同提示词/同块序镜像
  的一致性核验轮（chat 侧 20261104 首跑实测亦已返回 400 且
  文案指明媒体类型——「该模型不支持图片输入」）
- **chat part 映射**：document → `file` part（`file_data`
  data URL——OpenAI chat 协议文档输入标准形态，内含
  application/pdf）、audio → `input_audio`（format=wav）、
  video → `video_url`（base64 发用 data URL、URL 发用公网
  地址——test_c 视频理解 C5 同款形态）——各协议按其字段语
  义覆盖，同素材同序镜像
- **媒体数据代码生成（用户指定）**：工单记录中 data 字段被
  截断（未提供完整数据）——以代码生成有效 base64 数据（最小
  PDF/WAV/MP4 容器），内存生成、不落临时文件（无需临时文件
  即可满足测试）；拒绝校验发生在转换层媒体块类型层（整改建
  议原文——前置校验），不依赖可解码的媒体内容
- **MP4 最小容器骨架**：ftyp(isom 兼容 iso2/mp41) + free +
  mdat——结构合法的 MP4 容器签名；msg/chat 双协议第 3/5 发
  共用同一生成数据（工单两采集为不同视频，但拒绝判定在媒
  体块类型层，内容差异不影响拒绝行为——不硬凑两份视频数
  据）
- **视频 URL 沿用本仓现有地址（用户指定）**：MDN flower.mp4
  （test_c 视频理解 C5 同款）——工单原 test-videos.co.uk 地
  址不复用；URL 载体判据与 base64 载体相同（整改明令"URL 载
  体同样必须返回 400，不得自行抓取、转文字或降级为纯文本"）
- **断言口径为"含该发媒体关键词"下限设计**：错误体文案形态
  多样，逐文案精确匹配会误报；含关键词已可完全区分缺陷形态
  （通用「模型服务调用失败」upstream_error 不含任何媒体类
  型与字段名）
- **媒体类型关键词中英双语匹配（20261104 Jenkins 首跑后扩
  展，用户指定）**：首跑实测整改错误体为中文——
  `{"code":1210,"message":"该模型不支持图片输入"}`——类型维
  度已明确指明（整改实质达标），但原断言只认英文关键词误判
  FAIL；断言 2 扩展为 `K34_MEDIA_KEYWORDS` 中英关键词组任一
  命中，下限设计原则不变；工单 A-01 5 发覆盖 document/
  audio/video——image 关键词组移除（无图片轮）
- **取值范围痕迹（'text'）留观察不计判据**：官方行为含取值
  范围 `['text']`，但整改核心要求是"给出明确文案"（指明媒
  体类型）——允许值列表为增强信息，不作硬断言避免对文案形
  态过严
- **每发 1 次不重发**：错误体来自固定代码路径（确定性校验
  行为，K6/K32 先例）；msg 5 发对齐工单 A-01 采集口径，chat 5
  发为镜像核验

**注意事项**：
- 本用例针对非多模态模型（GLM-5.3）的多模态拒绝场景；若被测
  部署实为多模态模型（支持媒体输入），断言 1 将以"200 媒体
  被接受"FAIL——如实暴露环境与整改口径不符，须人工确认部
  署口径
- 若网关在转换层即拒绝（未达模型），错误体通常由网关生成
  ——断言口径同样适用（网关文案同样须指明媒体类型）
- 20261104 Jenkins 首跑实测贵方整改错误体为中文文案（「该
  模型不支持图片输入」，code 1210）——断言 2 关键词组已扩
  展中英双语；若后续文案改用其他表达使中英均未命中，FAIL 后
  须人工确认是否为"已指明类型"的等价表达（如纯格式名形态
  document 轮已含 pdf）
- 工单初版 8 发双协议口径（chat 4 + msg 4 矩阵）已按 A-01
  补充证据重构为双协议各 5 发（msg 按工单原始记录依序复现
  + chat 同素材同序镜像——用户指定）
- chat 文档轮以 OpenAI `file` part（file_data data URL）构
  造——若网关对未知 part 类型仅回 part 类型名（不含
  document/文档/pdf 关键词），将如实 FAIL，须人工判定文案是
  否等价指明媒体类型
- marker：`GLM53`（K 套件按模型分组标记；工单未指定模型，按
  新用例惯例归 GLM-5.3）
- 不进 smoke 集：新用例首跑观察期；P2 选测

### test_enable_thinking_param_rejection (K35)

**背景**：客户问题（工单 P1 R-07 补充证据 A-02 · chat/msg 协
议关闭思考的请求被放行，接口协议）：
- **官方行为**：原厂对关闭思考返回 400（原厂 HTTP 400）
- **贵方实测（A-02，2026-11-03 采集，2 发均 HTTP 200）**：
  渠道返回 200 并正常出文——chat 发 enable_thinking=false 放
  行且响应带 reasoning_content（思考仍开启，reasoning_
  tokens=91）；msg 发 thinking.type=disabled 放行且 content
  带 thinking 块（思考仍开启）；对照记为 http_status
  400→200（HTTP 状态语义）
- **预期行为（整改）**：统一关闭思考的拒绝口径——
  enable_thinking=false 与 thinking.type=disabled 两条路径均
  按原厂返回 400；不得一条拒一条放
- **历史记录**：工单初版口径为 enable_thinking=true 未知参数
  拒绝（工单未附请求样例）；A-02 补充证据明确缺陷形态为"关
  闭思考被放行"——按工单原始请求复现重构为双路径 2 发

**测试断言点（每路径任一失败即 FAIL 并报告协议与路径——不
得一条拒一条放）**：
1. HTTP 400（官方：原厂对关闭思考返回 400）

**请求构造**（按工单 A-02 原始请求 2 发依序复现，双协议两路
径——用户指定：两条路径都要按官方行为返回 400，覆盖两种协
议）：
- 路径1 chat 协议：`{api_prefix}/chat/completions`（非流式
  直发 `_post_with_retry`），工单 A-02 第 1 发原样：
  `messages=[{"role":"user","content":"23+19 等于多少？"}]`
  （字符串 content）、`max_tokens=512`、`enable_thinking=false`、
  model；请求体不含 stream 字段（工单原始格式）
- 路径2 msg 协议：`{base_url}/anthropic/v1/messages`（K3 先
  例——`x-api-key` + `anthropic-version: 2023-06-01` 头，
  session.post 直发），工单 A-02 第 2 发原样：
  `messages=[{"role":"user","content":"23+19=?"}]`（字符串
  content）、`max_tokens=512`、`thinking={"type": "disabled"}`、
  model、`stream=false`（工单原始格式显式携带）
- max_tokens=512 工单 2 发同值（豁免注入）；两发提示词不同
  ——工单原样逐字保留；采样参数工单未含——不传（不注入）；
  模型名由环境注入；相邻间隔 3s

**断言**（硬，每路径）：
1. HTTP 400（200=放行缺陷复现——A-02 形态：200 且正常出文
  （思考仍开启——reasoning_content/thinking 块）；500 等=
  非合规拒绝）

**判定矩阵**：
- 任一路径 200 → FAIL（放行缺陷复现——A-02 形态：200 且正常
  出文、思考仍开启（chat 响应带 reasoning_content、msg 响应
  带 thinking 块）；"不得一条拒一条放"——一条拒一条放同样
  FAIL）
- 500 等 → FAIL（非合规拒绝——整改要求"按原厂返回 400"）
- 两路径均 400 → PASS（统一关闭思考拒绝口径落地）

**观察记录（不计判据）**：
- 错误体是否含参数名（路径1 `enable_thinking` / 路径2
  `thinking`——官方拒绝文案常含参数名，客户端可据此定位；
  通用「模型服务调用失败」不含参数名）
- 完整错误体留痕

**设计决策记录**：
- **P1**（按客户工单 P1 R-07）
- **按客户原始请求复现（用户指定）**：A-02 提供两发完整请求/
  响应原始记录——两条关闭路径各 1 发按工单原样（含字符串
  content、max_tokens=512、chat 无 stream 字段/msg 显式
  stream=false、两发提示词不同）
- **两条路径各 1 发（用户指定）**：enable_thinking=false（chat
  路径）与 thinking.type=disabled（msg 路径）为关闭思考的两
  种协议表达——覆盖两种协议且任一路径放行即缺陷复现（"不得
  一条拒一条放"）
- **断言口径收缩为 HTTP 400**：客户预期行为仅定义状态语义
  （http_status 400→200）——错误体文案未作要求；参数名痕迹
  由硬断言降为观察记录（官方对"关闭思考"的拒绝文案形态未采
  集——不下限断言避免对文案过严，20261104 K34 教训：文案口
  径过严致误判）
- **max_tokens=512 工单原值**：2 发同值原样保留（chat 侧工单
  原样携带、msg 侧协议必需字段——豁免注入）
- **msg 侧 content 为字符串**：工单原始格式——Anthropic 协议
  允许字符串 content，原样保留不复刻为块数组

**注意事项**：
- 官方行为为"原厂对关闭思考返回 400"——若被测网关整改为放
  行关闭思考（文档声明支持关闭语义），本用例将按官方分支如
  实 FAIL——须人工确认口径
- 若网关在转换层即拒绝（未达模型），断言口径同样适用
- marker：`GLM53`（K 套件按模型分组标记；工单未指定模型，按
  新用例惯例归 GLM-5.3）
- 不进 smoke 集：新用例首跑观察期

### test_finish_reason_stop_semantics (K36)

**背景**：客户问题（工单 P1 R-06 · finish_reason 语义与官方不
一致，接口协议）：
- **官方行为**：finish_reason=stop（20_chat_stream_002 /
  20_chat_ms_001 / 20_chat_structured_002 三例）
- **贵方实测**：同一请求渠道返回 finish_reason=length，官方返
  回 stop（三例一致复现）
- **整改建议**：对齐 finish_reason 判定——思考 token 不应把正
  常结束的请求判成 length 截断
- **本用例口径**：按官方行为进行预期断言（用户指定），覆盖工单
  三例对应的三种请求形态

**测试断言点（按官方行为设计，每形态 × 每协议任一失败即 FAIL）**：
1. 终止语义对齐官方：chat `finish_reason == "stop"` / msg
   `stop_reason == "end_turn"`（Anthropic 协议的自然结束语义——
   msg 侧的 stop 等价；length/max_tokens=缺陷复现：思考 token
   计入判定把正常结束的请求误判截断——工单三例一致形态）
2. 正文非空（正常结束的佐证）

**请求构造**（三种请求形态 × chat+msg 双协议 = 6 发，相邻间隔
3s；thinking/采样参数工单未指定——不传不注入）：
- **流式**（对齐工单 20_chat_stream_002 形态）：chat
  `/v1/chat/completions` SSE（收集 `choices[].finish_reason` 与
  `delta.content` 增量，K24 流式消费先例）；msg
  `/anthropic/v1/messages` SSE（收集
  `message_delta.delta.stop_reason` 与
  `content_block_delta` 正文增量，K3 流式消费先例）
- **多段**（对齐工单 20_chat_ms_001 形态）：单条 user 消息
  content 数组多段文本（3 段——姓名/年龄/复述引导），非流式
- **结构化**（对齐工单 20_chat_structured_002 形态）：chat 侧
  `response_format={"type": "json_object"}` + JSON 对象任务；
  msg 侧无该参数按 K31 先例 prompt 引导 JSON，非流式
- msg 协议头：`x-api-key` + `anthropic-version: 2023-06-01`
  （K3 先例）；max_tokens 两协议同为 512（msg 协议必需字段）

**断言**（硬，每形态 × 每协议）：
1. chat `finish_reason == "stop"` / msg `stop_reason ==
   "end_turn"`
2. 正文非空（流式侧为合并增量，非流式侧为
   `message.content` / `content[].text`）

**判定矩阵**：
- chat `length` / msg `max_tokens`（正文已正常产出）→ FAIL
  （缺陷复现——思考 token 计入判定把正常结束的请求误判截断，
  贵方实测三例一致形态）
- 正文为空（任意终止字段）→ FAIL（思考耗光配额的 K31 形态混
  入——正常结束无从谈起，属配额缺陷而非误判，但本例判据要求
  "正常结束"，如实 FAIL 交人工分派）
- `stop` / `end_turn` 且正文非空 → PASS（与官方一致）

**设计决策记录**：
- **P1**（按客户工单 P1 R-06）
- **按官方行为断言（用户指定）**：工单实测为官方 stop / 贵方
  length 的对照——本用例对齐官方预期 stop 为唯一合法终止语义
- **三种请求形态（工单三例映射）**：流式 / 多段 / 结构化各 1
  发——工单三例一致复现说明缺陷在判定层而非特定请求形态，但
  按工单原始覆盖面逐一验证
- **双协议覆盖**（K31 起用例须验证 chat 与 msg 双协议，用户指
  定）：msg 侧终止字段为 Anthropic 语义 `stop_reason`
  （自然结束=`end_turn`，截断=`max_tokens`）——与 chat 侧
  `finish_reason`（stop/length）一一对应，同一判定缺陷的双协
  议映射
- **max_tokens=512（工单三例未附原始 payload——设计取值）**：
  单句/短 JSON 正文（数十 token 量级）远低于配额（官方自然结
  束 stop），默认档思考 token 常达数百——计入判定的实现易触顶
  误判 length（贵方缺陷形态），对判定语义敏感且不致正文真实
  截断（真实截断时 length 反而正确，测试将失去判别力）
- **正文非空断言为佐证性设计**：把"正常结束"钉死——正文空+
  length 形态属 K31（思考耗光配额）域，混入时先行 FAIL 交人工
  分派
- **不传 thinking/采样参数**：工单未指定——缺陷正出在默认思考
  的 token 计入判定，注入思考参数反而引入无关变量

**注意事项**：
- 观察项：finish=length 但正文完整（真实自然结束而仅标签错）
  亦判 FAIL——判定语义必须整体对齐官方，标签错误同样违约
- msg 流式侧 `stop_reason` 取自 `message_delta` 事件（Anthropic
  SSE 协议位置）；chat 流式侧 `finish_reason` 取自末个带该字段
  的 chunk
- marker：`GLM53`（K 套件按模型分组标记；工单未指定模型，按新
  用例惯例归 GLM-5.3）
- 不进 smoke 集：新用例首跑观察期

### test_n2_request_hang_timeout (K37)

**背景**：
- 客户问题（工单 P0 · n=2 请求挂死：无响应直至超时，异常）：
  - 原始问题：n=2 请求无响应直至超时——参数电池 3/3 轮
    TimeoutError（已重试 1 次仍超时）；协议电池 2 例 ReadTimeout，
    直连 300s 超时；该挂死同时导致模块 4 的 n=2 探针被记为
    『无效』而未计失败
  - 官方行为：原厂 n=2 HTTP 200（返回 1 个 choice）
  - 客户明确需求（2026-11-06，契约口径）：当 n=2 时 400 拒绝，
    并返回相应的提示信息，但不能卡死；客户示例响应：HTTP 400
    `{"code":1210,"message":"参数有误：glm-5.3 仅支持 n=1，`
    `收到 n=2 (request id: ...)"}`
- 原始请求（工单 055/056 两采集同形态）：
  `{"messages":[{"role":"user","content":"说一句话。"}],"max_tokens":16,"n":2,"model":"glm-5.3"}`，
  响应 null（ReadTimeout 300s）
- 适用模型：GLM-5.3（marker `GLM53`）

**测试断言点**：
1. 30s 硬超时：每发在 30s 内返回，超时即 FAIL——挂死缺陷复现
   （『不能卡死』违反；工单『探针被记为无效而未计失败』的漏报
   形态纠正为显式失败）
2. HTTP 400：客户新契约——n=2 明确拒绝（200 放行=未按客户契
   约拒绝；500 等=非合规拒绝）
3. 提示信息：响应体合法 JSON、message 非空且指明 n 参数限制
   （含 "n=1"/"n=2" 子串，大小写不敏感）

**请求构造**：
- chat 单协议 2 发对齐工单口径（055/056 两次独立采集，非重试；
  相邻间隔 3s）；n 为 OpenAI 协议参数、/anthropic/v1/messages 无
  n 参数语义——工单证据仅 chat，msg 侧对未知参数的行为已由 K33
  分支 B（统一忽略）与 K35（enable_thinking 拒绝域）覆盖，补 msg
  轮并入他例域、不构成 n>1 路径挂死的判定证据
- 工单原值原样保留：messages="说一句话。"、max_tokens=16、n=2
  （豁免注入，无全局注入口）
- 单发直发不重试：不经 `_post_with_retry`——重试掩盖单发挂死
  证据、使超时等待翻倍（30s×2）；`requests` timeout=30s 硬超时
  即客户端侧硬超时（客户新契约『不能卡死』）
- thinking/采样参数工单未含——不传（不注入）；模型名由环境注入

**断言**：
- 每发硬断言：
  1. 30s 硬超时（`requests.exceptions.Timeout` →
     `pytest.fail`——挂死缺陷复现，报告超时与工单形态）
  2. HTTP 400（`assert response.status_code == 400`——200 放行
     即 FAIL：未按客户契约拒绝；500 等非合规拒绝同判）
  3. 提示信息（响应体合法 JSON、message 非空且含 "n=1"/"n=2"
     子串，大小写不敏感——客户示例：参数有误：glm-5.3 仅支持
     n=1，收到 n=2；兼容 error.message 嵌套形态；body 非 JSON
     时退回原文匹配，既无 JSON 又无提示即 FAIL）
- 观察记录（不计判据）：
  - 错误码 code（如 1210——平台错误码口径，不硬绑）
  - request id 痕迹（如有）
  - elapsed——requests 读超时按字节间隔计时（非总时长），已返回
    但总时长超 30s 的字节缓流形态留观察人工分派，不作硬断言
    避免边界抖动误报

**判定矩阵**：
| 形态 | 判定 |
|------|------|
| 30s 内无响应（requests 超时） | FAIL——挂死缺陷复现（工单形态；『不能卡死』违反） |
| HTTP 200（任意 choices 数） | FAIL——未按客户契约拒绝（200 放行形态） |
| HTTP 400 + 提示信息含 n=1/n=2 | PASS——客户新契约达成 |
| HTTP 400 + 提示信息为空或不含 n=1/n=2 | FAIL——未返回相应的提示信息 |
| 其它状态码（500 等，30s 内） | FAIL——非合规拒绝 |
| 已返回但总时长 > 30s（字节缓流） | 观察留痕（warning）人工分派——requests 读超时按字节间隔计时未触发 |
| 发送异常（连接错误等） | FAIL |

**设计决策记录**：
- **按客户新契约断言（用户指定，2026-11-06）**：客户明确需求
  ——n=2 400 拒绝 + 相应提示信息、不能卡死；官方行为虽为
  200+1 choice，客户明确需求优先于官方对齐（替代原官方
  200+单 choice 口径；K35 官方一致分支口径不再适用本例）
- **超时即 FAIL（用户指定：须有超时机制）**：工单原客户端 300s
  超时拖死整轮的形态不得复现；超时显式计入失败——纠正工单所述
  探针被记为『无效』而未计失败的漏报形态（漏报使整改验证失真）
- **单发直发不重试**：`_post_with_retry` 的重试会掩盖单发挂死
  证据（首试超时、重试偶发成功的形态不可判）并使超时等待翻倍
  （30s×2）——挂死证据必须单发原样呈现
- **30s 硬超时取值**：客户新契约『不能卡死』——30s 为挂死判
  定口径（远低于工单原客户端的 300s）；400 拒绝应在参数校验层
  毫秒级返回
- **chat 单协议**：n 为 OpenAI 协议参数，Anthropic /v1/messages
  无 n 参数语义——msg 侧对未知参数的行为已由 K33 分支 B（统一
  忽略）与 K35（enable_thinking 拒绝域）覆盖，补 msg 轮并入他
  例域、不构成 n>1 路径挂死的判定证据
- **2 发口径（055/056）**：工单两次独立采集（非重试）——挂死为
  确定性路径阻塞形态（非概率抖动），2 发对齐采集口径足够呈现
- **max_tokens=16 工单原值原样保留**：不调大——工单原值豁免注
  入；400 拒绝在参数校验层发生，配额不参与判据（原 K31 域空正
  文观察随 200 判据一并退役）
- **elapsed 不作硬断言**：requests 读超时按字节间隔计时（收到
  任意字节即重置计时窗口），已返回但总时长超 30s 的字节缓流形
  态不会触发超时——该形态留观察（warning）人工分派，不作硬断
  言避免边界抖动误报

**注意事项**：
- 挂死缺陷的回归判据是『30s 内有响应（HTTP 400 + 提示信息指明
  n 参数限制）』；200 放行即 FAIL（未按客户契约拒绝）
- 模块 4 的 n=2 探针曾因挂死被记『无效』未计失败——本用例超时
  显式 FAIL，回归中不得再出现该漏报形态
- marker：`GLM53`（K 套件按模型分组标记；工单未指定模型，按新
  用例惯例归 GLM-5.3）
- 不进 smoke 集：新用例首跑观察期

### test_max_completion_tokens_alias_single_token (K38)

**状态：暂挂 SKIP**（用户指定 2026-11-06）——官方环境复测同形请求亦超时，工单『官方判定通过（别名按 max_tokens 语义立即截断返回）』基线失效；用例已打 `@pytest.mark.skip`，判定口径待澄清后恢复执行（恢复条件：去除 skip 装饰器并复核判据）。

**背景**：
- 客户问题（工单 A-A01 · tokens.maxcompletion_alias · max_completion_tokens 别名单 token 请求挂起，异常）：
  - 官方判定通过：max_completion_tokens 别名为单 token 请求——被接受并按 max_tokens 语义立即截断返回
  - 贵方实测：客户原始请求 1 发即挂起——180s 请求超时、无响应（HTTP 0，采集未落盘）
  - 预期行为（整改）：不得触发 180s 级挂起；需与 tokens 主路径同延迟水平
- 原始请求（工单 A-A01，1 发）：
  `{"model":"test-model","messages":[{"role":"user","content":"Write a long essay about turbines."}],"max_completion_tokens":1}`，
  响应 null（180s 超时，无响应）
- 适用模型：GLM-5.3（marker `GLM53`）

**测试断言点**：
1. 别名轮 30s 硬超时：在 30s 内返回，超时即 FAIL——挂起缺陷复现（工单 180s 无响应形态；对齐 K37 先例）
2. 别名轮 HTTP 200：官方判定通过——别名单 token 请求被接受（4xx=别名被拒，与官方口径不一致）
3. 别名轮 usage.completion_tokens <= 2：别名生效——单 token 截断（字段被丢弃则长文数百 token）
4. 主路径轮（对照基线）30s 内返回 + HTTP 200
5. 同延迟水平：别名 elapsed <= 主路径 elapsed×3+10s（客户预期"与 tokens 主路径同延迟水平"，3 倍+10s 容网络抖动）

**请求构造**（chat 单协议 2 发，相邻间隔 3s）：
- 轮一别名轮（工单原样，1 发对齐工单口径）：`{api_prefix}/chat/completions`——单 user "Write a long essay about turbines."、`max_completion_tokens=1`，字段序 model/messages/max_completion_tokens、无 stream 字段（工单原始格式）
- 轮二主路径轮（延迟对照基线）：同 prompt、`max_tokens=1`（同预算主路径字段）——预期行为"与 tokens 主路径同延迟水平"的基线测量；与轮一唯一差异即 token 字段名
- 单发直发不重试：不经 `_post_with_retry`——重试掩盖挂死证据、使超时等待翻倍（30s×2，K37 口径）；`requests` timeout=30s 硬超时即客户端侧硬超时
- max_completion_tokens 为 OpenAI Chat Completions 别名字段，Anthropic /v1/messages 无该字段（max_tokens 即协议必需主路径字段）——chat 单协议（K37 同理口径；msg 侧未知参数行为已由 K33 分支 B 与 K35 覆盖）
- 模型名由环境注入；thinking/采样参数工单未含——不传（不注入）

**断言**：
- 别名轮：超时（`requests.exceptions.Timeout`）→ `pytest.fail` 挂起缺陷复现（报告超时与工单形态）；HTTP 200；响应体合法 JSON 且 choices 非空；`usage.completion_tokens <= 2`（usage 未携带/非数值时该判据降级为延迟判据并留观察，不因缺 usage 误报）
- 主路径轮：超时 → FAIL；HTTP 200
- 同延迟水平：`alias_elapsed <= main_elapsed * 3 + 10`

**判定矩阵**：
| 形态 | 判定 |
|------|------|
| 别名轮 30s 内无响应（requests 超时） | FAIL——挂起缺陷复现（工单 A-A01 形态：180s 超时无响应、HTTP 0） |
| 别名轮 4xx（30s 内） | FAIL——别名被拒，与官方判定通过（200）不一致，交人工分派 |
| 别名轮 200 + completion_tokens > 2 | FAIL——别名未生效（疑似字段被丢弃后长文输出） |
| 别名轮 200 + 单 token 截断 + 主路径轮 200 + 同延迟水平 | PASS——别名被接受且与主路径同延迟水平 |
| 别名轮 elapsed > 主路径×3+10s（均在 30s 内返回） | FAIL——延迟未达"与 tokens 主路径同延迟水平" |
| 正文空 + finish=length | 观察留痕不判失败——1 配额默认思考计入的 K31 域形态，非本例判据 |
| 已返回但总时长 > 30s（字节缓流） | 观察留痕（warning）人工分派——requests 读超时按字节间隔计时未触发（K37 口径） |
| 发送异常（连接错误等） | FAIL |

**设计决策记录**：
- **P0**（挂起类可用性缺陷，对齐 K37 先例——单请求 180s 无响
  应属服务不可用级）
- **30s 硬超时（对齐 K37 先例）**：工单挂起形态为 180s 超时
  无响应——30s 客户端硬超时远低于该水平即判挂起复现；单发
  直发不重试（重试掩盖挂死证据且超时等待翻倍，K37 口径）
- **主路径对照轮（预期行为要求）**：客户预期"需与 tokens 主
  路径同延迟水平"——同 prompt、同预算（max_tokens=1）主路径
  发作为基线；与别名轮唯一差异即 token 字段名，延迟差即别
  名路径的开销
- **同延迟水平判据 3×+10s**：单 token 请求正常延迟秒级且两轮
  同路径——3 倍+10s 容网络抖动，超线即别名路径病态拖慢；挂
  起形态由 30s 硬超时兜底，两判据互补
- **completion_tokens<=2 判据**：官方口径"别名为单 token 请
  求"——别名被接受且按 max_tokens 语义截断的直接证据；容忍
  ≤2（计数边界），字段被丢弃则长文数百 token 必远超线；
  usage 未携带/非数值时降级为延迟判据并留观察（不因缺 usage
  误报）
- **chat 单协议**：max_completion_tokens 为 OpenAI Chat
  Completions 别名字段，Anthropic /v1/messages 协议无该字段
  （max_tokens 即协议必需主路径字段）——msg 侧未知参数行为已
  由 K33 分支 B（统一忽略）与 K35（拒绝域）覆盖（K37 同理
  口径）
- **1 发对齐工单口径**：工单采集为 1 发（确定性路径阻塞形
  态，非概率抖动）；别名轮不重复——挂起由硬超时判定、延迟
  由对照轮判定，重复无判定增益
- **finish_reason/正文留观察**：1 配额默认思考计入易空正文+
  length（K31 域形态），不与本例『挂起/延迟』判据混淆
- **elapsed 总时长维度不作硬断言**：字节缓流形态（已返回但
  总时长超 30s）留观察人工分派（K37 口径）；同延迟水平判据
  只比较两轮 elapsed 差
- **暂挂 SKIP（用户指定 2026-11-06）**：官方环境复测同形请
  求亦超时——工单『官方判定通过（别名按 max_tokens 语义立
  即截断返回）』基线失效，『30s 硬超时即判挂起复现』判定口
  径随之失效（官方同形亦超时，无法区分缺陷与正常行为）；
  用例经 `@pytest.mark.skip` 跳过，判定口径澄清后恢复执行
  （恢复条件：去除 skip 装饰器并复核判据）；P0 注册、
  pytest.ini 枚举与 Jenkinsfile 条目保留不动

**观察记录（不计判据，留日志）**：两轮真实响应体前 800 字符、elapsed、finish_reason、正文字数、completion_tokens、字节缓流 warning

**注意事项**：
- 挂起缺陷的回归判据是『30s 内有响应 + 别名截断生效 + 与主路
  径同延迟水平』，正文质量不判（K31 域另测）
- marker：`GLM53`（K 套件按模型分组标记；工单未指定模型，按新
  用例惯例归 GLM-5.3）
- 不进 smoke 集：新用例首跑观察期

### test_reasoning_dual_field_history_accepted (K39)

**背景**：
- 客户问题（工单 AGDC2-47 · 历史 assistant 消息 reasoning/reasoning_content 双字段共存 400，接口协议）：
  - 官方行为（AGDC2-47 测试资料·官方 API 验证结论，2026-11-05 Kimi K3 官方端点）：同一历史 assistant 消息同时包含 `reasoning` 与 `reasoning_content`，无论内容相同或不同、哪个字段在前，官方 API 均接受——14 组合（字段变体 × 默认/关闭思考）全部 HTTP 200、`finish_reason=stop`、回答 3，无 400/`json_parse_error`/`duplicate field`
  - 贵方实测：双字段共存即 HTTP 400、错误码 `json_parse_error`、提示 `duplicate field reasoning_content`——两字段值相同或不同均报错；仅 reasoning 或仅 reasoning_content 单字段调用成功；客户生产调用产生较多报错
  - 预期行为（整改）：历史消息同时存在 reasoning 与 reasoning_content，无论两字段值相同或不同，均不得 400 响应，应正常请求成功
- 原始请求形态（AGDC2-47 官方验证请求原样）：
  `{"model":"...","stream":false,"max_tokens":512,"messages":[{"role":"user","content":"What is 1 + 1? Reply with only the number."},{"role":"assistant","content":"2","reasoning":"...","reasoning_content":"..."},{"role":"user","content":"Add 1 to the previous answer. Reply with only the number."}]}`
- 适用模型：GLM-5.3 与 Kimi K3（双 marker `GLM53` + `KimiK3`，用户指定双模型覆盖——工单缺陷经 Kimi K3 官方端点验证，字段解析为接口层通用逻辑，请求同构无模型分支）

**测试断言点**（每发，任一失败即 FAIL 并报告场景序）：
1. HTTP 200：双字段共存历史被正常接受（400 `json_parse_error`/`duplicate field reasoning_content` = 缺陷复现）
2. 响应体合法 JSON 且 choices 非空
3. 正文非空（空正文 + finish=length 留观察——K31 域豁免；空正文且 finish≠length 即 FAIL）

**请求构造**（chat 单协议 4 发，相邻间隔 3s；用户指定：只测双字段共存场景——单字段/无字段场景不测；调整两字段顺序 × 覆盖两字段值相同和不同）：
- 端点：`{api_prefix}/chat/completions`，非流式（`stream=false`）
- 同一三消息结构（官方验证请求原样）：user "What is 1 + 1? Reply with only the number." / assistant `content="2"` 携双思考字段 / user "Add 1 to the previous answer. Reply with only the number."
- 请求体字段序官方验证原样：model/stream/max_tokens=512/messages；模型名由环境注入；thinking 默认模式不传；采样参数未含——不注入
- 场景矩阵（assistant 消息内双思考字段键序按场景——dict 插入序即 JSON 上送序）：
  | 场景 | reasoning | reasoning_content | 键序 |
  |------|-----------|-------------------|------|
  | 1 同值/reasoning 在前 | "1 + 1 = 2." | "1 + 1 = 2." | reasoning 先 |
  | 2 同值/reasoning_content 在前 | "1 + 1 = 2." | "1 + 1 = 2." | reasoning_content 先 |
  | 3 异值/reasoning 在前 | "Compute the sum." | "The answer is two." | reasoning 先 |
  | 4 异值/reasoning_content 在前 | "Compute the sum." | "The answer is two." | reasoning_content 先 |

**判定矩阵**：
| 形态 | 判定 |
|------|------|
| HTTP 400（json_parse_error/duplicate field reasoning_content） | FAIL——缺陷复现（工单 AGDC2-47 形态） |
| 其他非 200 | FAIL |
| HTTP 200 + choices 非空 + 正文非空 | PASS——双字段共存被兼容接受 |
| HTTP 200 + 正文空 + finish=length | 观察留痕（warning）——512 预算思考计入耗尽的 K31 域形态，非本例判据 |
| HTTP 200 + 正文空 + finish≠length | FAIL——非截断的空正文为异常形态 |
| 回答不含 3 | 观察留痕——生成质量非本例判据 |
| 发送异常（连接错误等） | FAIL |

**设计决策记录**：
- **P0**（K25 同域先例——历史思考字段兼容；客户生产大量报错）
- **双 marker `GLM53` + `KimiK3`（用户指定双模型覆盖）**：工
  单缺陷经 Kimi K3 官方端点验证——字段解析为接口层通用逻辑
  （与模型无关），同时适用 GLM-5.3 与 Kimi K3；请求同构（模
  型名由环境注入），无模型分支（对照 K13 双标记先例）；
  pytest.ini KimiK3 枚举同步收录 K39
- **只测双字段共存场景（用户指定）**：单字段（仅 reasoning/仅
  reasoning_content）客户实测已成功、官方亦 200——无缺陷维度，
  不重复验证；无字段场景同理由不测
- **字段顺序 × 同值/异值全矩阵 4 发**：客户报错与值异同无关
  （同/异值均 400），但字段序与值异同为解析层别名处理的两个
  潜在分支——官方验证对四组合全 200，回归须全覆盖；键序经
  dict 插入序控制（reasoning 在前/reasoning_content 在前）
- **请求体官方验证原样**（三消息结构/stream=false/max_tokens=
  512/字段序）——与 AGDC2-47 测试资料保存的请求逐字段一致，
  便于对客户实际端点对照复现
- **关闭思考模式不测**：官方验证双模式（默认/关闭）均 200 证
  明字段兼容性与思考模式正交；K35 已确立本网关对关闭思考
  400 拒绝口径——该模式属另一缺陷域，混入将判据冲突
- **chat 单协议**：reasoning/reasoning_content 为 chat 历史
  消息字段，Anthropic /v1/messages 协议无该字段形态（思考经
  thinking content block 承载）——msg 未知参数行为由 K33 分支
  B 与 K35 覆盖（K37/K38 同理口径）
- **正文非空判据带 K31 域豁免**：512 预算默认思考计入可能耗
  尽（空正文+length）——该形态 warning 留观交人工分派，不判
  失败；非 length 的空正文（200 无截断却无正文）属异常如实
  FAIL
- **回答含 3 留观察**：官方验证回答为 3，但生成质量非本例
  判据（K37/K25 域分离先例）——多轮上下文是否被真实处理由
  200+正文非空保障

**观察记录（不计判据，留日志）**：每发真实响应体前 800 字符、
elapsed、finish_reason、正文长度、回答是否含 3、K31 域空正文
warning

**注意事项**：
- 双字段共存是 JSON 合法形态（两个不同键各出现一次），非同名
  键重复——与 K25（同名键字面重复）为相邻但不同的缺陷维度
- marker：`GLM53` + `KimiK3`（K 套件按模型分组标记；用户指定
  双模型覆盖——工单缺陷经 Kimi K3 官方端点验证，同时适用
  GLM-5.3 与 Kimi K3，请求同构无模型分支）
- 不进 smoke 集：新用例首跑观察期

### test_thinking_enabled_reasoning_content_stable (K40)

**背景**：（新工单，响应字段稳定性）客户请求体 max_tokens=16000 +
单 user 消息「证明：对于任意正整数n，n^3-n能被6整除」+
thinking={"type": "enabled"}（客户环境模型 GLM-5.3-jy-b）——响应
有时带、有时不带 reasoning_content 字段，不稳定，客户生产调用产
生较多困扰。预期行为（整改）：thinking enabled 请求的响应须稳定
携带 reasoning_content——所有请求统一携带。

**请求构造**：
- chat 端点：`{base_url}/v1/chat/completions`，`_post_with_retry`
  直发（超时沿用全局——工单未涉及超时语义，thinking+16000 预算
  单发通常 10-60s；三轮串行总时长约 1-3min）
- 请求体工单原样：字段序 model/messages/max_tokens/thinking；
  max_tokens=16000、单 user 消息、thinking={"type": "enabled"}
  （对象形态）；stream 工单未含——不传（非流式默认）；采样参
  数（temperature/top_p/seed）工单未含——不注入；模型名由环境
  注入（用户确认——staging 端点为 glm-5.3，GLM-5.3-jy-b 为客户
  内部档位名）
- 三轮 × 每轮 10 并发：轮内 ThreadPoolExecutor(max_workers=10)
  同拍齐发（E5 并发稳定性先例），轮间串行——每轮收齐后再开下
  一轮（用户指定 2026-11-09：测试分为三轮、每轮 10 并发，所
  有轮的所有请求 reasoning_content 统一才算通过；同日调整确
  认：每轮结束收集一次，任一轮次不一致即失败中止——避免后
  续轮次浪费）——不稳定缺陷以多轮并发批次探测，请求标识
  #R{轮}-{序} 跨轮定位

**断言（硬，逐轮判定——每轮收齐即断言该轮，任一轮次失败即用
例失败并中止后续轮次，用户指定 2026-11-09：避免无效轮次消
耗）**：
1. 该轮 10/10 HTTP 200（非 200/发送异常全量列出——请求层失败
   同样破坏统一性验证；失败即中止后续轮次）
2. 该轮 10/10 响应体合法 JSON 且 choices 非空
3. 该轮 10/10 choices[0].message.reasoning_content 存在且非空
   （「统一」口径=字段层面全部携带，用户确认——空字符串同样
   属「没有」，内容逐字一致不作要求——思考文本天然因请求而
   异；缺失/空串清单全量输出=缺陷复现证据，如「第 2 轮 8/10
   携带，缺失 #R2-3/#R2-7」，含缺失发响应留痕 finish/正文/
   reasoning_content 实值）

**判定矩阵**（任一 FAIL 条件触发即中止后续轮次）：
- 任一轮内任一发非 200/发送异常 → FAIL（请求层失败破坏统一性
  验证）
- 任一轮内任一发响应体非法 JSON/choices 空 → FAIL（响应结构异
  常）
- 任一轮内任一发 reasoning_content 缺失或为空串 → FAIL（缺陷
  复现——工单形态「有时带/有时不带」不稳定直接判据）
- 三轮全部 10/10 HTTP 200 + reasoning_content 全部存在且非空
  → PASS（所有轮的所有请求统一携带达标，缺陷未复现）

**观察记录（不计判据，留日志）**：每发真实响应（HTTP/elapsed/
reasoning_content 长度/正文长度/finish_reason）按 idx 序全量输
出（标识 #R{轮}-{序} 跨轮定位）；每轮通过时输出本轮摘要，三
轮全通过后输出整体汇总（思考长度 min/avg/max、耗时 min/avg/
max、finish_reason 分布）

**设计决策记录**：
- **三轮 × 每轮 10 并发（用户指定）**：不稳定缺陷单发难复现
  ——多轮并发批次探测批次间+批次内差异；轮内 ThreadPoolExec-
  utor 同拍齐发（E5 并发稳定性先例）；轮间串行——轮次语义清
  晰；api_client._post_with_retry 共享 session（urllib3 连接池
  线程安全，无 cookie 状态突变）
- **逐轮判定、失败即中止（用户指定）**：每轮结束收集一次，任
  一轮次不一致（非 200/响应异常/reasoning_content 缺失或空）
  即失败——后续轮次不再执行，避免无效轮次消耗
- **存在且非空口径（用户确认）**：空字符串同样属「没有」——缺
  失与空串同列缺陷形态
- **模型名环境注入（用户确认）**：staging 端点为 glm-5.3，
  GLM-5.3-jy-b 为客户内部档位名；缺陷为响应字段生成逻辑（与模
  型档位命名无关），模型名由环境注入即可复现验证
- **stream 不传**：工单请求体未含 stream 字段——不注入（独立
  性规则），requests 默认非流式
- **超时沿用全局**：工单未涉及超时语义；thinking+16000 预算单
  发通常 10-60s，全局超时充足，不自定覆盖（对照 K32/K37/K38 自
  定义超时先例——本例无短超时语义需求）
- **chat 单协议**：客户请求为 chat 形态，缺陷为 chat 响应字段
  ——Anthropic msg 思考经 thinking content block 承载，无
  reasoning_content 字段形态（K39 同款排除理由）

**注意事项**：
- reasoning_content 为思考输出字段（默认思考计入共享配额——
  K31 域）；16000 预算下 length 截断不预期，若出现留观察（非预
  期形态，交人工分派）
- marker：仅 `GLM53`（K 套件按模型分组标记；工单模型
  GLM-5.3-jy-b 为 GLM-5.3 档位变体——缺陷为响应字段生成逻辑，
  无模型分支）
- 不进 smoke 集：新用例首跑观察期
