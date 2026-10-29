# K. 客户问题复现测试

## 概述
收录来自客户反馈的真实问题，将客户提供的原始请求（通常是 curl 命令）还原为标准
模型请求进行复现与回归验证。

设计原则：
- **原样复现**：system/user 提示词、tools 定义、tool_choice、thinking、stream、
  stream_options、temperature、max_tokens 等全部字段与客户原始请求逐字段一致，
  不做任何"规范化"改写——保证复现的是客户遇到的确切请求形态。
- **P0 为主，按工单优先级**：客户报障场景纳入回归验证——K1-K7、K10-K25 为
  P0 必测（任何失败应阻断发布），K8/K9 按客户工单优先级为 P1。
- **修复后转为回归**：问题修复后用例保留，作为该场景的长期回归用例。
- **参数豁免**：`RAW_SAMPLING_PARAM_TESTS` 豁免名单默认规则（用户口径）：
  未明确指定加入豁免的用例一律不豁免——采样参数由全局 `--sampling-params`
  覆盖（temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入）。
  现仅 K5-K9、K24 保留豁免：K5-K9 测试逻辑依赖 temperature/top_p/seed
  （关思考温度档契约等），全局覆盖会破坏契约验证；K24 工单原始请求体
  显式指定 temperature=0.0（工单体为唯一口径，用户指定豁免）——均须
  始终按原始采样参数执行。
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
| K10 | GLM-5.3-Flash tool_choice 四种模式支持 | 客户问题（AGDC2-15）：上线前版本未指定模型专属工具调用格式解析器，tool_choice 语义不被支持；修复为 Worker 侧指定生成解释器、渲染字段至聊天模版；需支持 auto/required/named/none；同时适用 Kimi K3 | 四模式各一次（mt=2048、非流式、不传 thinking；采样参数不豁免——由全局 SAMPLING_PARAMS（Jenkinsfile）覆盖，temperature=0 为无覆盖时回退值；get_weather+get_current_time 两工具），断言 auto/required 必须发起工具调用（形状合法、finish=tool_calls）、named 必须调用指定工具（指定与天气意图不同向的 get_current_time）、none 禁止调用（无 tool_calls、正文非空、finish=stop） | P0 |
| K11 | GLM-5.3-Flash response_format 三种模式支持 | 客户问题（AGDC2-16）：DingoRouter 不支持结构化输出语义；修复为 Router 侧支持结构化生成语义并转发至引擎；需支持 json_object/json_schema/text | 三模式各一次（temperature=0、mt=2048、非流式、不传 thinking），断言 json_object 正文可解析为 JSON 对象、json_schema 正文可解析且 city 为字符串、temperature 为数值、键集合恰为 {city,temperature}（weather strict schema）、text 正文非空；每轮 finish=stop | P0 |
| K12 | GLM-5.3-Flash reasoning_effort 档位支持 | 客户问题（AGDC2-17）：字段为 reasoning_effort 且放在 chat_template_kwargs 里（GLM 聊天模版），而 OpenAI 协议/参考脚本将其放在顶层；Router 需在 OpenAI 协议外层捕获该字段并传给引擎；修复为 Router 侧支持语义转发；需支持 low/high/max/空（空=不发送该字段，默认档），且不管放在顶层还是嵌套在 chat_template_kwargs 里，请求都能被正常接受和处理并输出正常响应 | 两种放置（顶层/嵌套 chat_template_kwargs）× 四档各一次（temperature=0、mt=2048、非流式、不传 thinking、chat_template_kwargs={clear_thinking:true}；嵌套放置：reasoning_effort 放进 chat_template_kwargs），断言每轮 200+正文非空+finish=stop；档位对思考的实际影响（rt/reasoning 长度）仅日志留痕 | P0 |
| K13 | stop 序列遵循且被截断正文前置多余字符 | 客户问题：stop=["橘子"] 的流式请求，期望输出 "苹果、香蕉、"，实际输出 ">苹果、香蕉、"——被截断正文前面多输出了一个 ">" 符号；同时适用 KimiK3 | 按客户原始请求体还原（stream=true、stop=[橘子]、glm-5.3-flash 另传 thinking={type:enabled}+reasoning_effort=low；KimiK3 不传），断言 SSE 有正文增量、finish=stop、合并正文严格等于 "苹果、香蕉、"、不含 "橘子" | P0 |
| K14 | 孤儿 tool 消息应 HTTP 400 拒绝 | 客户问题：tool 角色消息前无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未定义任何 tools），属协议非法请求，网关应校验并返回 400 Bad Request；实际返回 200 放行；同时适用 GLM-5.3 与 GLM-5.3-Flash | 按客户原始请求体还原（user 后直接跟 tool tool_call_id=call_abc123、stream=true、无 tools/thinking/采样参数），断言 HTTP 400；若 200 放行（缺陷形态）取样 SSE 事件留证后 FAIL | P0 |
| K15 | 细粒度前缀匹配短输入缓存阈值 | 客户问题：短文本缓存命中率不达标，根因推理引擎默认前缀缓存分块撮合的最小可缓存块长过大（vLLM 默认 640 tok 量级），客户输入低于该块长（如 625 tok）完全不缓存；平台修复为细粒度前缀匹配（sglang prefix-match-unit=64）；同时适用 GLM-5.3 与 GLM-5.3-Flash | 两个测试点（OpenAI 协议非流式、不发送采样参数，cached_tokens 取 usage.prompt_tokens_details.cached_tokens 兼容 usage.cached_tokens）：1) 输入 64<N<640 相同请求连发两次，断言第 2 次 cached_tokens>0；2) 输入 N<64 相同请求连发两次，断言 cached_tokens==0；以服务端 prompt_tokens 校验规模前提 | P0 |
| K16 | 固定前缀/多轮上下文缓存命中率达标 | 客户问题：修复前固定前缀每轮 cached=7680/input=8693（88.35%）、多轮上下文 87.16%，均低于 90% 目标；根因 640 token 分块粒度将共享前缀截断（8192→12×640=7680，损失 512），细粒度匹配（64）后应 ≈94.2%≥90%；同时适用 GLM-5.3 与 GLM-5.3-Flash | 两模式（OpenAI 协议非流式、不发送采样参数，规模由原始信息推算：~12800 字符共享前缀 ≈8192 tok + ~780 字符/轮唯一问题 ≈501 tok）：1) 固定前缀 10 轮独立请求；2) 多轮上下文单会话逐轮追加（回复极短）；均排除第 1 轮预热实测 9 轮，断言各模式 Σcached/Σprompt_tokens ≥90%，任一 <90% 即 FAIL | P0 |
| K17 | stop 停止符（换行符）在推理阶段生效 | 客户契约：指定停止符为换行符 "\n" 并开启思考时，停止符同样作用于推理输出——推理里的第一个换行即触发停止，正文不会生成；反之若换行未触发停止、继续输出正文，则换行符未生效；适用 GLM-5.3 | 按场景构造流式请求（stream=true、stop=["\n"]、thinking={type:enabled}（K1 口径）、max_tokens=512 防御性预算、不发送采样参数），断言 SSE 有事件、合并正文为空（核心）、finish_reason==stop、合并 reasoning 不含换行（停止符不泄漏） | P0 |
| K18 | 模型输出 JSON 可回填为下次请求输入上下文 | 客户问题（AGDC2-28）：上次请求输出的 assistant JSON 作为下次请求的输入上下文提交即报错（missing field `name`）——助手历史 tool_calls 混有空占位调用（name=""、id=null）与真实 bash 调用（arguments 缺开头 "{"、非合法 JSON）；修复为移除空占位项再校验、缺 "{" 原样保留（不补）、兼容重复 reasoning 字段；后续问题（开发文档）：修复后新问题 tool_call_id 悬空引用（must reference an unanswered tool call）——根因为模型返回空 function（id=null），客户端以 missing_tool_call_id 回填后被协议拒绝，根上解决为模型不返回空 function；适用 GLM-5.3 | 按客户 agent 两步流程还原（用户指定测试逻辑）：第一个请求让模型输出技能周报数据 JSON 并落盘测试脚本同级目录下临时文件（第一步"输出 JSON 到 *.json 文件"）；第二个请求调用工具读取该临时 JSON 文件，将工单原始 assistant 返回数据（user→assistant(空占位+bash 调用+reasoning 双字段)→user 追问携带文件内容，带 bash 工具定义，非流式）回填为输入上下文；第三个请求（根因断言）复刻工单首个 user 回合（带 bash 工具定义）断言模型工具调用结构完整；测试完成后删除临时 JSON 文件（finally 兜底，断言失败同样清理）；断言：第一个请求 HTTP 200 且正文可提取合法 JSON 对象、临时文件回读一致、第二个请求 HTTP 200（核心）、choices 存在、message 结构存在、第三个请求模型发起工具调用且每条调用 name/id 非空、arguments 为合法 JSON 对象（根因断言：模型不得返回空 function）；采样参数不豁免——由全局 SAMPLING_PARAMS 覆盖 | P0 |
| K19 | 单次请求图片数超限（>16）应拒绝并返回恰当错误 | 客户问题：单次请求携带超过 16 张图片导致请求失败；根因服务端 serving-pool 显式配置 --limit-mm-per-prompt {"image":16,"video":1,"audio":0}（vLLM 多模态单项限额）；契约为超限请求应失败并返回恰当错误信息（参考 "At most 16 image(s) may be provided in one prompt"）；适用 GLM-5.3-Flash | 代码生成 17 张 32x32 纯色 PNG（base64 data URL，无外部依赖），单条 user 消息携带 17 个 image_url part 非流式提交（不发送采样参数——豁免），断言响应失败（非 200）且错误信息含 "at most 16 image"（大小写不敏感） | P0 |
| K20 | 1M 上下文请求应被正常支持 | 客户问题：请求报错 "Input length (918451 tokens) exceeds the maximum allowed length (781754 tokens). Use a shorter input or enable --allow-auto-truncate."（invalid_request_error——网关透传 serving 侧上下文长度校验拒绝；当时最大允许 781754，未按 1M 上下文契约配置）；契约：模型需支持 1M 上下文请求——1M 量级输入应正常响应；适用 GLM-5.3 | 1M=输入+输出（用户口径），总量略小于 1M：探针自校准（重复单元 ×2000 从 usage.prompt_tokens 精确计量）后按目标生成主请求：输入 960,000 tokens + 输出预算 max_tokens 覆盖思考+正文，两轮思考档位（用户指定补 max 场景）——low 轮（1024）常规、max 轮（4096）最大思考负载，输出侧同步压窗口（总消耗 ≈961K/964K，两种 1M 口径均满足），单条 user 消息非流式提交（采样参数不豁免——用户指定：全局 SAMPLING_PARAMS 覆盖，temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入；跑必冷仅 low 轮——用户加固：low 轮（含探针）材料头部置每次请求唯一 nonce（时间戳+uuid，可含中文），前缀必不命中 KV 缓存，真 1M 冷 prefill；max 轮取消唯一前缀——输出侧验证不受缓存影响，允许命中历史缓存加速），断言探针 200 且有 usage、每轮主请求 HTTP 200、choices/content 非空、每轮主响应 prompt_tokens（如有）>781,754（规模 sanity） | P0 |
| K21 | system 消息内嵌 tools 的非标请求结构应被接受 | 客户问题（kimi-k3 工单原始请求体）：messages[2] 为 role=system 且无 content 字段、代之以内嵌 tools 数组（Calculator 单工具），服务端反序列化报 400 invalid_request_error/json_parse_error（"messages[2]: data did not match any variant of untagged enum MessageContent"）——结构虽非 OpenAI 协议标准形态（tools 应为顶层参数），但客户业务实际在用；契约：宽容解析并正常响应（预期 200）；适用 Kimi-K3 | 按工单原始请求体原样重放（模型名由环境注入，其余字段不改动；采样参数不豁免——默认口径：全局 SAMPLING_PARAMS 覆盖，temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入），单次请求（确定性行为，无需连发），断言 HTTP 200（核心——原始报错形态复现即 FAIL）、choices 存在、message 有效输出（content 或 tool_calls 非空）；模型真实响应（状态码/响应体全文）断言前打印；运行日志不含具体模型名（系统提示词正文含模型自我介绍，仅记字符数概要） | P0 |
| K22 | /v1/messages 缓存命中率应与 /v1/chat/completions 基本一致 | 客户问题：相同请求下 Anthropic 协议（/anthropic/v1/messages）前缀缓存命中率始终低于 chat 协议（"缓存始终上不去"）——根因：该链路 system 头部携带 x-anthropic-billing-header: 逐请求动态计费行（字符串/块数组两种 system 形态），前缀缓存要求从位置 0 连续匹配，头部逐请求变化导致整个前缀永不命中；chat 协议无此行、前缀稳定（K15/K16 已验证 ≥90%）；开发修复：入引擎前条件剥离——system 开头是 x-anthropic-billing-header: 行即去掉、其余内容原样保留；适用 GLM-5.3 | 测试要点（用户口径）：同轮等价请求逐轮交替发送两协议（同轮同问；前缀头部渠道标记行不同——用户指定：剥离计费行后两协议前缀仍从位置 0 分叉，互不命中对方缓存条目，各自建条目/各自命中，messages 冷轮为真冷），统计二者缓存命中率并逐轮比较——冷轮不参与比较（需热轮才能统计命中率），组级判定（用户指定）：单组失败不中断后续组，5 组中至少 4 组该组全部热轮差值 ≤3 个百分点（用户指定容差）即 PASS、不足 4 组 FAIL；热轮 messages 全量 miss（read=0 且 creation=0）时同轮重发一次鉴别（用户指定）：重发命中→WARN 留痕继续（偶发——疑似多实例路由/条目可见性问题）；仍 miss→该组不符合预期（剥离失效形态，判别力不变）；每请求在 system 头部构造逐请求变化的计费行；循环 5 次比对（用户口径：每次循环的请求消息尽量不一样）：2 组中文、2 组英文、1 组中英混合，整请求长度尽量超过 8k tokens；覆盖两条剥离代码路径（块数组断点挂 system 块——K3 口径；字符串断点挂 user 首块）；每次循环每协议 1 冷轮 + 2 热轮（用户口径；冷轮不参与比较），共 5 次循环 × 2 协议 × 3 轮 = 30 请求，组间间隔 3 秒（用户指定）；硬断言：①组级判定（用户指定）——单组失败不中断后续组，5 组中至少 4 组该组全部热轮差值 ≤3 个百分点即 PASS、不足 4 组 FAIL；②每请求 HTTP 200 且响应正常；缺陷形态 messages ≈0% vs chat ≈94%（五组全不符合→FAIL）、修复后两协议每热轮均 ≈94%（五组全符合→PASS）；热轮 cache_creation>0（剥离失效直接信号）与双低形态仅日志留痕；运行日志不含具体模型名 | P0 |
| K23 | 孤儿 tool 消息应对齐官方放行并正常消费 | 客户问题（新工单，官方对齐口径）：tool 角色消息前无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未定义任何 tools），平台返回 400（"Invalid parameter: messages with role 'tool' must be a response to a preceeding message with 'tool calls'."——type: alaya code error、code: invalid text request——网关层白加的校验）；智谱官方源对同一请求 HTTP 200 正常应答「北京今天天气晴朗，气温18℃」且模型在 reasoning 中实际引用 tool 数据（工具数据被正常消费）；新契约（客户指定）：预期结果同官方一致——此类消息序列不做校验、正常出结果；与 K14 关系：K14 为当时工单口径原始契约（保持不变——用户指令），二者输入同类预期相反，平台采纳官方对齐修复后 K14 将 FAIL、其保留/退役由用户决定；适用 GLM-5.3 | 按客户新工单原始请求体还原（messages=[user"查一下北京天气"、assistant"好的，我来为您查询北京天气数据。"（纯文本无 tool_calls——孤儿条件）、tool tool_call_id="call_weather_001" content={"city":"北京","temp_c":18,"condition":"晴"}、user"根据工具返回的数据，用一句话告诉我天气。"]、max_tokens=200、非流式、无 tools/thinking；采样参数不豁免——默认口径：全局 SAMPLING_PARAMS 覆盖），单次请求（确定性行为，无需连发），断言 HTTP 200（核心——原始 400 拦截形态复现即 FAIL）、响应合法 JSON 且 choices 非空、message 有效输出（content 或 tool_calls 非空——官方形态为正常答句）；官方行为细节（输出/推理引用工具数据要素）软校验仅日志；模型真实响应（状态码/响应体全文）断言前打印 | P0 |
| K24 | 双请求正常响应（思考耗尽预算 low 强度回退） | 客户问题（新工单）：客户两个请求（中文同音词与言部汉字写作题、英文数学题），temperature=0.0、max_completion_tokens=32768（工单原始字段名）、非流式，期望均正常响应并返回正文；风险形态（用户指定）：默认 max 思考强度下思考可能耗光预算（正文空+finish=length）；适用 GLM-5.3 | 按工单原始请求体还原两请求直发（采样参数豁免——用户指定：两请求体均显式 temperature=0.0，工单体为唯一口径，通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖，top_p/seed 不注入）；第 1 轮默认 max 思考强度（不带 reasoning_effort），有正常正文即通过，断言 HTTP 200、响应合法 JSON 且 choices 非空、message 有效输出（content 或 tool_calls 非空）；耗光形态（正文空+finish=length）按用户指定契约转 reasoning_effort=low（GLM 顶层思考强度参数，K20 口径）重发且仅重测耗光请求（已通过不重测），断言相同；正文空且 finish≠length 直接 FAIL；low 回退仍无正文即 FAIL（双强度均未产出——留证交开发）；finish/usage 仅日志；模型真实响应（状态码/响应体全文）断言前打印 | P0 |
| K25 | assistant 历史重复 reasoning_content 字段应被兼容接受 | 客户问题（工单跟进）：多轮对话回填 assistant 历史时，同一条消息携带两个 reasoning_content 字段（两轮历史思考未去重地拼接成同键重复）与上一次请求的正文；客户原始工单还曾因思考内容含 They're/I'm/It's 等英文撇号导致 JSON 破损——正文与思考可能含单引号/双引号/换行等字符，须兼容处理、不影响请求格式（用户指定）；契约（用户指定）：预期不报错、正常响应，第一个 reasoning_content 被第二个覆盖（宽松解析保留最后一个值，K18 修复口径）；适用 GLM-5.3 | 共发三次请求（用户指定，JSON 链式回填——第 1/2 次响应 JSON 作为下一请求输入、思考随历史一并回填；提示词为测试自行设计，工单未携带具体提示词——用户口径仅要求结构）：第 1 次 user 单轮流式要求仅输出 JSON——采集第 1 段思考+第 1 次正文（JSON，作为第 2 次请求输入回填）；第 2 次流式回填第 1 次历史 messages=[assistant(content=第 1 次正文（JSON）, reasoning_content=第 1 次思考), user 追问]（单键经 dict 表达——K18 口径）并要求仅输出 JSON——采集第 2 段思考+第 2 次正文（JSON，作为第 3 次请求输入回填）；第 3 次流式回填 messages=[assistant(content=第 2 次正文（JSON）, reasoning_content=第 1 次思考, reasoning_content=第 2 次思考), user 追问]——重复键无法经 dict 表达，手工拼接 JSON 文本直发，动态值一律 json.dumps 全转义，发送前三重自检（合法 JSON、reasoning_content 键出现次数==2、转义回读值一致）；硬断言第 1/2 次思考与正文均非空（构造数据源）且正文为合法 JSON（JSON 链断裂即场景无法构造 FAIL；容忍 markdown 代码块围栏）、第 3 次 HTTP 200（核心——被拒绝即 FAIL）+ SSE 事件非空 + 合并正文非空 + finish_reason 合法；耗光回退（K24 口径）：max_tokens=8192 下默认 max 档思考可能耗尽预算（正文空+finish=length）——该形态以 reasoning_effort=low 仅重发耗光请求（第 3 次重发构造不变仅加顶层 reasoning_effort 字段——HTTP 200 核心契约首次请求已达成），断言相同，正文空且 finish≠length 直接 FAIL，low 回退仍无正文即 FAIL（双强度均未产出——留证交开发）；引号覆盖度软观察（三个回填值均无引号/换行字符时 record_warning，不判失败）；采样参数不豁免（默认口径：全局 SAMPLING_PARAMS 覆盖，temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入）；max_tokens=8192 工单口径三次一致；usage 仅日志；模型真实响应断言前打印 | P0 |

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
  温度，chat_completion 封装会强制覆盖 max_tokens/temperature）

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
- 采样参数不豁免（用户指令）——由全局 SAMPLING_PARAMS
  （Jenkinsfile，经 `--sampling-params` 注入）覆盖：temperature
  全局值优先（原始脚本口径 0 为无覆盖时的回退值），top_p/seed
  未显式指定时注入；reasoning_effort 不在此列，保持原始口径不传
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
- **采样参数不豁免（用户指令）**：本用例已从
  `RAW_SAMPLING_PARAM_TESTS` 豁免名单移除——采样参数由全局
  SAMPLING_PARAMS（Jenkinsfile，默认
  `{"temperature": 1.0, "top_p": 0.95, "seed": ""}`）覆盖：
  temperature 全局值优先（原始脚本口径 0 为无覆盖时回退值，
  SAMPLING_PARAMS 留空即框架原有行为）、top_p=0.95 注入、seed
  空（不发送）；reasoning_effort 不在 SAMPLING_PARAMS 内，保持
  原始口径不传
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
  非流式、不传 thinking
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
  true}`（原始脚本原样保留）
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
  即如此；通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）

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
  始请求体即如此；通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）
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
- `max_tokens=16`；不发送采样参数（通过 RAW_SAMPLING_PARAM_TESTS
  豁免全局覆盖）
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
- `max_tokens=16`；不发送采样参数（通过 RAW_SAMPLING_PARAM_TESTS
  豁免全局覆盖）

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
- 不发送采样参数（通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）

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
   （报错 missing field `name` 即指向它）；
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
  报图表。"）→ assistant（工单原样还原：content=null、
  reasoning_content + reasoning_context 双字段并存、
  tool_calls=[空占位调用, 真实 bash 调用（arguments 缺 `{`）]）
  → user 追问（携带工具读取到的临时 JSON 文件内容，防御性截断
  上限 3000 字符）；tools：bash 工具定义（agent 场景——模型输
  出调用了 bash，请求必然定义了该工具）；max_tokens=512（工单
  口径）
- **第三个请求**（根因断言）：复刻工单首个 user 回合——user
  单轮 "请分析工作区数据并生成技能周报图表。"（与第二个请求
  历史第 0 条同一消息，常量 K18_CHART_PROMPT 单一来源复用），
  带 bash 工具定义，max_tokens=2048（同第一个请求防御口径——
  留足思考预算余量）；工单中模型在该回合输出了空占位调用与畸
  形 bash arguments（根因行为），本请求断言本次输出结构完整
- 采样参数不豁免（用户指令）——三个请求一致，由全局
  SAMPLING_PARAMS（Jenkinsfile，经 `--sampling-params` 注入）
  覆盖：temperature 全局值优先（无覆盖时回退 0.7），top_p/seed
  未显式指定时注入
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
- 第二个请求 HTTP 400 报 missing field `name`（或同型反序列化
  错误）→ FAIL（工单缺陷复现——空占位调用未被容忍）
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
  router 不代表该字符串成为合法参数 JSON）；空占位被移除
  （router 内部行为，响应不可见）
- **响应形态宽松**：只测"上下文被接受"——正文或继续调用工具
  均可（历史是工具调用场景且提供了 bash 工具），content/
  tool_calls 仅日志
- **role 拼写**：docx 中为 `"assitant"`——报错与修复逻辑均不涉
  及 role，判定为文档笔误，按标准 `assistant` 还原
- **reasoning 重复字段覆盖方式**：dict 无法表达同键字面重复，
  以 reasoning_content + reasoning_context 两拼写并存覆盖兼容
  路径（"保留最后一个值"为 router 内部合并行为，响应不可见，
  不断言）
- **采样参数不豁免（用户指令）**：对齐 K10 新口径——由全局
  SAMPLING_PARAMS 覆盖（默认 temperature=1.0、top_p=0.95、seed
  不发送；SAMPLING_PARAMS 留空即无覆盖回退 temperature=0.7）
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
- **多轮最小还原**：第二个请求 user→assistant(工单输出)→user
  追问——工单核心是"输出回填为上下文"，不额外自造 tool 响应
  消息；工具读取到的文件内容经 user 追问带入（role=tool 消息
  可能引入额外服务端校验路径，偏离工单报错形态，不采用）
- **临时文件内容截断上限 3000 字符**：防御模型输出超长 JSON
  撑大第二个请求上下文
- **不进 smoke 集**：新用例首跑观察期

**注意事项**：
- 修复逻辑第 2 条的"只有空占位项时不直接删除"分支不在本用例
  覆盖范围（工单报错场景为占位+真实调用并存）
- 临时 JSON 文件（`tests/k18_temp_skill_weekly.json`）为运行期
  产物，测试结束（无论成败）即被 finally 删除，不入库
- usage 仅日志
- marker：仅 `GLM53`（用户指定；采样参数不豁免）

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
- 不发送采样参数（通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）

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
- **采样参数不豁免**（用户指定）：由全局 SAMPLING_PARAMS
  （Jenkinsfile）覆盖——temperature 无覆盖时回退 0.7、top_p/seed
  显式指定时注入（K10/K18 口径；探针与两轮主请求共用同一构造）
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
- **采样参数不豁免**（用户指定）：由全局 SAMPLING_PARAMS
  （Jenkinsfile）覆盖——temperature 无覆盖时回退 0.7、top_p/
  seed 显式指定时注入（K10/K18 口径）
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
- marker：`GLM53`（K 套件按模型分组标记；采样参数不豁免——用
  户指定）

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
- **采样参数不豁免**（默认口径——未明确指定加入豁免名单）：
  由全局 SAMPLING_PARAMS（Jenkinsfile）覆盖——temperature 无
  覆盖时回退 0.7、top_p/seed 显式指定时注入（K10/K18/K20 口
  径）
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
- **采样参数不豁免**（默认口径——未明确指定加入豁免名单）：由
  全局 SAMPLING_PARAMS 覆盖——temperature 无覆盖时回退 0.7、
  top_p/seed 显式指定时注入（K10/K18/K20 口径；conftest 豁免
  名单默认规则：未明确指定加入的用例一律不豁免）
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
- **采样参数不豁免**（默认口径——未明确指定加入豁免名单）：手工
  payload 不携带采样字段，缓存命中与采样无关
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
- 采样参数不豁免（默认口径——未明确指定加入豁免名单）：由全局
  `--sampling-params` 覆盖（temperature 无覆盖时回退 0.7、
  top_p/seed 显式指定时注入）
- 单次请求（确定性行为，无需连发）

**断言**（硬）：
1. HTTP 200（核心——原始 400 拦截形态复现即 FAIL，报文引用原始
   报错文案）
2. 响应合法 JSON 且 choices 非空
3. message 有效输出（content 或 tool_calls 非空——官方形态为正
   常答句，工具调用响应亦为成功形态）

**判定矩阵**：
- 修复前（网关白加校验拦截）：400 → FAIL（断言 1，报文标注缺陷
  形态精确复现）
- 修复后（官方对齐）：200 + 有效输出 → PASS

**设计决策记录**：
- **P0**（客户报障场景）
- **K14 保持不变**（用户指令）：K14 为当时工单口径的原始契约，
  不因新需求改动；二者预期相反，平台采纳官方对齐修复后 K14 将
  FAIL——其保留/退役由用户决定
- **工单原始请求体原样重放**：assistant 纯文本消息 + tool 消息
  （无 tool_calls 关联）+ 未定义 tools——孤儿条件最小充分；模型
  名由环境注入
- **max_tokens=200 保持工单值**：官方同参数下正常答句；若平台出
  现 finish=length 空正文（思考耗尽预算），与 400 拦截形态区分
  并在报文提示评估预算口径——不自行改预算偏离工单
- **官方行为细节软校验**：输出/推理引用工具数据要素（北京/18/
  晴）= 工具数据被模型正常消费的信号——生成措辞自由，仅日志，
  不作硬断言
- **采样参数不豁免**（默认口径——未明确指定加入豁免名单）
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

**采样参数豁免**（用户指定）：两个请求体均显式指定 temperature=
0.0——工单原始请求体为唯一口径，通过 `RAW_SAMPLING_PARAM_TESTS`
豁免全局 `--sampling-params` 覆盖，top_p/seed 亦不注入。

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
- **采样参数不豁免**（默认口径）：由全局 SAMPLING_PARAMS 覆盖
  （temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入，K10/
  K18/K20 口径）
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
