"""
K. 客户问题复现测试

本测试类专门收录来自客户反馈的真实问题，将客户提供的 curl 命令还原为
标准模型请求进行复现与回归验证。优先级按客户工单标定：K1-K7、K10-K30、
 K37-K39 为 P0（任何失败应阻断发布），K8/K9/K31/K32/K35/K36/K40/K41/K42/K43/K44 为 P1，K33/K34 为 P2。

环境注入约定：客户 curl 中的 URL、API key、模型名仅用于当时的问题定位，
不写入测试代码。与其他测试类一致，目标服务地址与凭证由 Jenkinsfile 构建
参数（BASE_URL / API_KEY / MODEL）透传至 pytest 的 --base-url / --api-key /
--model-name，经 conftest 的 api_client fixture 注入；curl 中的其余请求字段
（messages、tools、采样参数、user 等）按原样保留。

用例自包含约定：每个用例的常量（提示词、tools、参数等）与内部辅助函数
均定义在用例方法内部，不集中放在模块顶部——单个用例的全部信息可在
一处读完，用例之间互不干扰。

测试点：
- K1: Pydantic $defs/$ref Schema 工具调用（流式+思考+强制tool_choice） [P0]
  客户问题：glm-5.3 通过 /v1/chat/completions 发起流式请求报错【$$不兼容】。
  请求特征：thinking.type=enabled + stream + stream_options.include_usage +
  tool_choice 强制指定 function + tools 使用 Pydantic v2 生成的 JSON Schema
  （含 $defs/$ref 引用）。本用例按客户原始 curl 原样复现请求，验证服务端
  可正常接受该 Schema 并返回合法的强制工具调用结果。工单原始请求含
  temperature=0.1——原样保留并豁免全局采样覆盖（top_p/seed 工单
  未指定，不注入）。
- K2: 同一请求循环执行5次返回信息异常 [P0]
  客户问题：同一 curl 命令循环执行 5 次左右出现返回信息异常。
  请求特征：logprobs+top_logprobs+n+thinking+stream+stream_options+
  frequency_penalty/presence_penalty+user 字段 + X-Cache-Buster 防缓存请求头。
  本用例按客户原始 curl 原样复现并连续执行 5 次（相邻间隔 3s），断言每次的响应与内容均正常。工单原始请求含 temperature=1、top_p=0.95——原样保留并豁免全局采样覆盖（seed 工单未指定，不注入）。
- K3: Anthropic 协议 prompt cache 未创建 [P0]
  客户问题：通过 Anthropic 协议（/anthropic/v1/messages，stream=true）发送带
  prompt cache 的请求，服务端日志 anthropic cache stats 中 cache_creation_tokens
  一直为 0（同时 cache_read_tokens 有值），说明 cache_control 断点未被落实、
  未创建缓存。本用例构造带 cache_control 断点的唯一长前缀，连续发送两次
  请求，断言第 1 次创建缓存（creation > 0）、第 2 次命中缓存（read > 0）。
- K4: frequency_penalty=-2 且不传 max_tokens 请求一直无返回 [P0]
  客户问题：fp=-2（OpenAI 规范 [-2,2] 的合法极值）且不传 max_tokens 时
  请求一直没有返回——fp<0 按出现次数奖励已出现 token，形成无饱和正反馈，
  循环 token 的 logit 压制 EOS 导致自然终止失效，输出只能跑到上下文
  上限，远超网关/客户端超时。平台修复契约：fp<0 按 0 处理（防御性
  钳制）。本用例输入保持 -2、不传 max_tokens，连发 3 次（消息各异、
  相邻间隔 3s——仅一次调用可能无法严谨验证），断言每次都按 fp=0 预期：
  预算时间内返回 + finish_reason 自然结束 + 内容非空，任一次失败报告
  第几次（不进 smoke 集）。
- K5: thinking.type=disabled 后思考未关闭 [P0]
  客户问题：thinking.type=disabled 后 reasoning_tokens 仍=100/75、
  reasoning_content 照常输出（官方端点实测应 rt 为空、无思考内容、正文
  正常返回；官方 FAQ 与实测不符，以实测为准），关思考相关功能（低延迟
  模式、关思考温度档）全部失效。本用例输入保持客户原值 disabled、显式
  temperature=0.6（官方关思考档唯一合法温度，契约见 K6）、不传
  max_tokens，连发 3 次（消息各异、相邻间隔 3s），断言每次均按官方实测
  预期：无思考内容（reasoning_content/reasoning）+ reasoning_tokens
  为空（0/缺失，兼容两种字段拼写）+ 正文正常返回且自然结束，任一次
  失败报告第几次。
- K6: 关思考温度档未联动校验 [P0]
  官方契约（kimi-k3 官方说明）：thinking 模式与 temperature 档位联动
  ——disabled 下仅允许 0.6（给 1 或 0 会 400 并报 "only 0.6 is allowed
  for this model in non-thinking mode"）、enabled 下仅允许 1（给 0.6
  或 0 会 400 并报 "only 1 is allowed for this model in thinking
  mode"）。客户影响：关思考相关功能（关思考温度档）失效。本用例对
  6 个组合各发一次请求（参数校验为确定性行为，无需多次连发），断言
  合法组合 200+正文非空、非法组合 400+错误信息含官方文案（忽略大小写
  子串匹配）。
- K7: 思考强度档位思考长度倒挂（官方 reasoning_effort） [P0]
  官方契约（kimi-k3 官方文档 use-reasoning-effort/kimi-k3-quickstart）：
  思考强度为顶层 reasoning_effort 参数（K2.x 的 thinking 配置在 K3
  已废弃，官方迁移指引为移除 thinking 改用 reasoning_effort），K3
  恒开思考；官方预期思考长度（reasoning_tokens）随档位递增。本用例
  只按官方格式传参（顶层 reasoning_effort，无回退），请求顺序（客户
  指定）：low → high → max 后比对思考长度，再按 max → high → low
  逆向重发并再次比对（正逆两轮排除请求顺序相关干扰，均按 low <
  high < max 三档软对比，medium 不参与对比）；最后依次验证 medium
  顶层（按官方 200 放行）与 medium 嵌套（thinking.effort=medium
  预期 400——废弃的 K2.x thinking 配置下 medium 为非法档位，客户
  指定契约）。请求内容与温度完全相同（temperature=1，开思考档契约
  温度，见 K6），相邻间隔 3s。硬断言：每次官方档请求（升序轮+降序轮+
  medium 顶层）200+正文非空+自然结束；嵌套 thinking.effort=medium
  400。档位倒挂/持平不判失败，仅告警记入报告（行为质量偏离而非
  服务故障）（不进 smoke 集：max 档思考生成为长耗时请求，同 K4
  理由）。
- K8: required+闲聊必须调用工具（客户工单级别） [P1]
  客户工单原始问题：tool_choice=required + 闲聊 "Reply with
  exactly: OK"（无工具意图）下不发起工具调用——tool_calls 键缺
  失、finish=length、completion_tokens 恒被吃满 max_tokens（关
  思考 1000/3000 级别均如此）、正文仅 "OK"、耗时 ~15.6s（正常
  ~1.5s，双峰）；开思考下 reasoning 消耗远小于预算但整体仍被
  吃满（mt=3000 仍不调）。预期（工单）：required 必须发起工具
  调用——finish 应为 tool_calls 而非 length、关思考 ct 应较
  小、开思考 rt 应 < max_tokens、正文应正常收到调用工具的响应
  信息。轮次（客户实测级别）：关思考 mt=1000、关思考 mt=3000、
  开思考 mt=3000（get_weather 工具）。硬断言：每轮 200+choices+
  usage 存在；tool_calls 存在且为 get_weather 调用（arguments
  合法 JSON，city 值不限定）；finish_reason=="tool_calls"（而非
  length，关/开思考均不允许）；ct < max_tokens（关思考下应较
  小）；开思考 rt < max_tokens（rt 双拼写兼容）。temperature 按
  网关档位联动取 0.6/1（非该值被 400 拒绝）。耗时双峰仅日志留
  痕。（不进 smoke 集：缺陷轮 15.6s 级长耗时+缺陷概率性）
- K9: required+闲聊必须强制调用工具（按官方行为） [P1]
  官方 api.moonshot.cn/kimi-k3 实测：闲聊 "Reply with exactly:
  OK" + required → finish=tool_calls、强制返回 get_weather 调用
  （city 瞎猜 London/UNKNOWN，值不限定）、reasoning 仅 38 token
  ——符合 [OI] required「必须发起至少一次工具调用」规范；Alaya
  同场景缺陷：finish=length、reasoning 吃满 256/2000 预算、
  tool_calls=None；有工具意图时（北京天气）两站一致正常。
  本用例按官方行为为预期（与 K8 同场景不同级别：K8 为客户工单
  级别，本用例镜像 Alaya 缺陷实测级别）：关/开思考 × mt=256/
  2000。硬断言：每轮 200+choices+usage 存在；tool_calls 强制
  返回（get_weather、arguments 合法 JSON，city 值不限定）；
  finish_reason=="tool_calls"；ct < max_tokens；开思考 rt <
  max_tokens（rt 双拼写兼容）。temperature 按网关档位联动取
  0.6/1。耗时双峰仅日志留痕。（不进 smoke 集：缺陷轮 15.6s 级
  长耗时+缺陷概率性）
- K10: GLM-5.3-Flash tool_choice 四种模式支持（auto/required/
  named/none） [P0]
  客户问题（AGDC2-15）：OpenAI 协议 tool_choice 让模型按请求指定
  的类型/模式生成工具调用（Agent 自定义工具场景）；上线前版本未
  指定模型专属的工具调用格式解析器，GLM-5.3-Flash 不支持该语义。
  修复：Worker 侧指定生成解释器，支持渲染字段至模型聊天模版
  （chat_template.jinja）。本用例对四种模式各发一次请求（原始
  验证脚本 glm53_flash_suite 的 tool_auto/tool_required/tool_
  named/tool_none.sh 口径：max_tokens=2048、非流式、不传
  thinking——GLM-5.3-Flash 默认思考，不做思考断言；采样参数豁
  免（用户口径：原始脚本指定 temperature=0——原样保留，不受全
  局 SAMPLING_PARAMS 覆盖；top_p/seed 脚本未指定，不注入）。
  同时适用 Kimi K3（OpenAI 协议 tool_choice 通用语义，默认思考
  不做断言；2026-10-26 staging 实测 kimi-k3 required 轮 500
  prefill_internal_error，该 FAIL 即为其待修复基线）。
  工具两个：get_weather(city)+get_current_time(timezone)。
  auto/required/none 用工具意图提示词（原始脚本口径）；named 指
  定 get_current_time 且提示词保持原始口径的天气意图——named 与
  提示词自然意图不同向，若 named 语义未生效（被忽略按 auto 处
  理）模型会按意图调 get_weather，从而检出「指定工具未被强制」。
  每轮硬断言：HTTP 200+choices 存在；auto/required：tool_calls
  存在且形状合法（type=function、arguments 合法 JSON）、finish=
  tool_calls；named：tool_calls 存在且 function.name==指定工具、
  finish=tool_calls；none：tool_calls 缺失、content 非空、
  finish=stop。usage 仅日志留痕（原始脚本无预算断言）。（不进
  smoke 集：新用例首跑观察期）
- K11: GLM-5.3-Flash response_format 三种模式支持（json_object/
  json_schema/text） [P0]
  客户问题（AGDC2-16）：OpenAI 协议 response_format 让模型按指定
  格式输出（Agent 场景）；DingoRouter 不支持该结构化输出语义。修
  复：Router 侧支持结构化生成语义并实现语义转发至引擎。本用例对
  三种模式各发一次请求（原始验证脚本 glm53_flash_suite 的
  response_json_object/response_json_schema.sh 口径：temperature=
  0、max_tokens=2048、非流式、不传 thinking；采样参数豁免——原
  始脚本指定 temperature=0 原样保留，top_p/seed 未指定不注入）。
  json_object 轮按
  原始脚本提示词与 jq 校验（正文可解析为 JSON 对象）；json_
  schema 轮按原始脚本 schema（name=weather、strict=true、city:
  string+temperature:number、required、additionalProperties=
  false）与 jq 校验（正文可解析、city 为字符串、temperature 为
  数值、键集合恰为 {city,temperature}）；text 轮为协议默认模式
  （原始脚本未单测，按需补齐）：正文非空即可。每轮硬断言：HTTP
  200+choices 存在；正文非空；finish=stop（参考结果均自然结
  束）；json_object：json.loads(正文) 为 dict；json_schema：另
  加键集合与字段类型校验。usage 仅日志留痕。（不进 smoke 集：
  新用例首跑观察期）
- K12: GLM-5.3-Flash reasoning_effort 档位支持（顶层/嵌套 ×
  low/high/max/空） [P0]
  客户问题（AGDC2-17）：GLM-5.3-Flash 使用 GLM 自己的聊天模版，
  字段为 reasoning_effort 且放在 chat_template_kwargs 里；而
  OpenAI 协议/参考脚本将其放在顶层。Router 需要在 OpenAI 协议
  外层捕获该字段并传给引擎（修复：Router 侧支持语义转发）。需
  支持：low/high/max/空（空=不发送该字段，默认档），且不管
  reasoning_effort 放在顶层还是嵌套在 chat_template_kwargs 里，
  请求都能被正常接受和处理并输出正常响应，否则用例失败。本用
  例对两种放置 × 四档各发一次请求（原始验证脚本 glm53_flash_
  suite 的 reasoning_low/reasoning_high/reasoning_max.sh 口径：
  temperature=0、max_tokens=2048、非流式、不传 thinking；采样参
  数豁免——原始脚本指定 temperature=0 原样保留，top_p/seed 未
  指定不注入；顶层
  放置：reasoning_effort 在顶层 + chat_template_kwargs=
  {"clear_thinking": true} 为原始脚本原样保留；嵌套放置：
  reasoning_effort 放进 chat_template_kwargs（GLM 聊天模版原
  生口径）；空档无对应脚本，按需补齐为不发送该字段）。提示词
  "Explain why 17*19=323 with intermediate reasoning if
  available."（原始脚本口径）。每轮硬断言：HTTP 200+choices 存
  在；正文非空；finish=stop（参考结果均自然结束）。档位对思考的
  实际影响（reasoning_tokens、reasoning_content 长度）仅日志留
  痕——参考脚本未做档位间断言，思考长度为模型行为质量。（不进
  smoke 集：新用例首跑观察期）
- K13: stop 序列遵循且被截断正文前置多余字符 [P0]
  客户问题：stop=["橘子"] 的流式请求，期望输出 "苹果、香蕉、"（正
  文在停止词处截断、不含停止词），实际输出 ">苹果、香蕉、"——被截
  断正文前面多输出了一个 ">" 符号。原始请求体（glm-5.3-flash）：
  stream=true、thinking={"type": "enabled"}、reasoning_effort=
   "low"、stop=["橘子"]、其余采样参数不发送（test_k 保持原始测试
   参数——工单原始请求未指定，不发送）；KimiK3 环境不传 thinking/
  reasoning_effort（按 K5 口径），断言完全一致。硬断言：SSE 解析
  成功且有正文增量；finish_reason=="stop"；合并正文严格等于
  "苹果、香蕉、"（多余前缀/停止词泄漏/未截断均 FAIL）；正文不含
  "橘子"。usage 仅日志。（不进 smoke 集：新用例首跑观察期）
- K14: 孤儿 tool 消息应 HTTP 400 拒绝 [P0]
  客户问题：messages 中 tool 角色消息前无带 tool_calls 的 assistant
  消息（孤儿 tool 消息，且请求未定义任何 tools），属协议非法请求，
  网关应校验并返回 400 Bad Request；实际返回 200 放行，模型把孤儿
  tool 消息当普通上下文推理。按客户原始请求体还原（user "今天天
  气怎么样？" 后直接跟 tool tool_call_id="call_abc123" content=
   "{\"weather\":\"晴\"}\"，stream=true，无 tools/thinking/采样参
   数——test_k 保持原始测试参数（工单原始请求未指定，不发送）。
   硬断言：
  HTTP 400；若 200 放行（缺陷形态）：取样若干 SSE 事件留证后
  FAIL。GLM-5.3 与 GLM-5.3-Flash 断言完全一致。响应体与 usage
  仅日志。（不进 smoke 集：新用例首跑观察期）
- K15: 细粒度前缀匹配短输入缓存阈值 [P0]
  客户问题（平台原始验证信息）：短文本缓存命中率不达标，根因推理
  引擎默认前缀缓存分块撮合的最小可缓存块长过大（vLLM 默认 640
  token 量级），客户输入低于该块长（如 625 token）时完全不缓存，
  命中率远低于目标；平台修复为细粒度前缀匹配（sglang prefix-
  match-unit=64 / vLLM 对应参数调小）。本用例覆盖短输入两个方向：
  1) 输入长度 64<N<640 的相同请求连发两次，断言第 2 次
  cached_tokens>0（修复后应正常缓存，修复前不缓存即为缺陷）；
  2) 输入长度 N<64 的相同请求连发两次，断言 cached_tokens==0
  （低于最小粒度不应缓存）。cached_tokens 取 usage.
  prompt_tokens_details.cached_tokens（兼容 usage.cached_tokens）。
   GLM-5.3 与 GLM-5.3-Flash 断言一致，非流式、不发送采样参数
   （test_k 保持原始测试参数——工单原始请求未指定，不发送）。
   （不进 smoke 集：新用例首跑
  观察期）
- K16: 固定前缀/多轮上下文缓存命中率达标 [P0]
  客户问题（平台原始验证信息）：短文本缓存命中率不达标——修复前
  每轮固定前缀缓存命中 7680/输入 8693（88.35%）、多轮上下文
  87.16%，均低于 90% 目标；根因 640 token 分块粒度将共享前缀截断
  （8192 → 12×640=7680，损失 512），细粒度匹配（64）后固定前缀
  命中率应 ≈8192/8693≈94.2%≥90%。本用例按 OpenAI /v1/chat/
  completions 协议构造两个模式验证：模式1 固定前缀——10 轮独立
  请求 [system 共享长前缀(~8192 token)，user 每轮唯一问题
  (~501 token)]；模式2 多轮上下文——单会话 history 逐轮追加，
  共享前缀随轮增长。两模式均排除第 1 轮预热、实测 9 轮，断言
  cached_tokens 总和/prompt_tokens 总和 ≥90%。  GLM-5.3 与
   GLM-5.3-Flash 断言  一致，非流式、不发送采样参数（test_k 保
   持原始测试参数——工单原始请求未指定，不发送）。（不进 smoke 集：新用例首跑观察期）
- K17: stop 停止符（换行符）在推理阶段生效 [P0]
  客户契约：指定停止符为换行符 "\n" 并开启思考时，停止符同样作用
  于推理（reasoning）输出——推理里出现的第一个换行即触发停止，
  正文（content）不会生成；反之若换行未触发停止、继续输出正文，
  则换行符未生效。本用例按该场景构造（GLM-5.3：
  thinking={"type":"enabled"} 显式开启思考（K1 口径）；
  stream=true、stop=["\n"]、
  max_tokens=512 仅作防御性预算（正常应在推理早期触发停止）、其余
   采样参数不发送——test_k 保持原始测试参数（工单原始请求未指
   定，不发送）。
  硬断言：SSE 解析成功有事件；合并正文为空（stop 在推理阶段触
  发、正文未生成——核心断言）；finish_reason=="stop"；合并
  reasoning 不含 "\n"（stop 语义：输出在停止符前截断、停止符不泄
  漏）。模型真实响应（合并正文/思考全文）断言前打印到日志（失败时
  同样可见）；usage 仅日志。（不进 smoke 集：新用例首跑观察期）
- K18: 模型输出 JSON 可回填为下次请求输入上下文 [P0]
  客户问题（AGDC2-28）：上次请求输出的 assistant JSON 作为下次请
  求的输入上下文提交即报错——"Failed to deserialize the JSON
  body into the target type: missing field `name`"。触发形态：助
  手历史 tool_calls 列表混有空占位调用（name=""、id=null、
  arguments="{}"）与真实 bash 调用（arguments 缺开头 "{"、非合法
  JSON，按工单原样保留）；模型侧修复已明确任何情况下不返回空
  function——本用例按用户指定不再保留空 function 场景（回放数
  据中已移除空占位调用）。修复：解析失败后同列表有真实调用时
  移除空占位项再重新校验；缺 "{" 的 arguments 原样保留（不
  补）；兼容 assistant 历史重复的 reasoning_content/
  reasoning_context（保留最后一个值）。后续问题（开发文档）：
  修复上线后新问题 tool_call_id 悬空引用（must reference an
  unanswered tool call）——根因为模型返回空 function
  （id=null），客户端以 missing_tool_call_id 回填错误结果后被
  协议校验拒绝；根上解决为模型不返回空 function。本用例按客户
  agent 两步流程还原（用户指定测试逻辑）：第一个请求让模型输
  出技能周报数据 JSON（示例记录，无需真实数据）并落盘测试脚本
  同级目录下临时文件（第一步"输出 JSON 到 *.json 文件"）；第
  二个请求调用工具读取该临时 JSON 文件，将工单原始 assistant
  返回数据（user→assistant(真实 bash 调用（arguments 缺
  "{"）+reasoning 双字段)→tool(工具读取结果——协议必需：
  assistant 带 tool_calls 后必须紧跟匹配 tool_call_id 的工具结
  果消息，实测缺失被 400 拒绝)→user 追问，带 bash 工具定义，
  非流式）回填为输入上下文；第三个请求（根因断言）复刻
  工单首个 user 回合（带 bash 工具定义）断言模型输出的工具调
  用结构完整；测试完成后删除临时 JSON 文件（finally 兜底）。
  硬断言：第一个请求 HTTP 200 且正文可提取合法 JSON 对象、临
  时文件回读一致、第二个请求 HTTP 200+choices 存在+message 结
  构存在——上次输出 JSON 必须可作为下次输入上下文，报错复现
  即 FAIL；第三个请求模型发起工具调用且每条调用 name/id 非
  空、arguments 为合法 JSON 对象（模型不得返回空 function）。
   不断言 arguments 被补 "{"（修复明确不补——通过 router 不代
   表该字符串成为合法参数 JSON）。GLM-5.3 专用；采样参数不发送
   ——test_k 保持原始测试参数（工单原始请求未指定，不注入），
   三个请求一致。docx 中 role 拼写
  "assitant" 判定为笔误（报错与修复均不涉及 role），按标准
  assistant 还原。usage 仅日志。（不进 smoke 集：新用例首跑观
  察期）
- K19: 单次请求图片数超限（>16）应拒绝并返回恰当错误 [P0]
  客户问题：单次请求携带超过 16 张图片导致请求失败。根因：服务端
  serving-pool 启动参数显式配置 --limit-mm-per-prompt
  {"image":16,"video":1,"audio":0}（vLLM 多模态单项限额）。契
  约：超限请求应失败并返回恰当的错误信息（参考 "At most 16
  image(s) may be provided in one prompt"）。本用例代码生成 17
  张 32x32 纯色 PNG（base64 data URL，无外部依赖），单条 user
  消息携带 17 个 image_url part 发起请求，硬断言：响应失败（非
  200）；错误信息含 "at most 16 image"（大小写不敏感）——超限
  被正确拒绝且信息恰当则 PASS；200 放行（限额未生效）或错误信
   信息不含该模式（信息不恰当）均 FAIL。GLM-5.3-Flash 专用；不发
   送采样参数（test_k 保持原始测试参数——工单原始请求未指定，
   不发送）。
  原始失败详情截图未收到，断言口径以用户给定的参考信息为准；
  恰好 16 张的正向对照轮未纳入（用户测试要点仅两条，且避免回
  归中重度视觉计算）。模型真实响应（状态码/响应体全文）断言前
  打印到日志（失败时同样可见）；usage 仅日志。（不进 smoke 集：
  新用例首跑观察期）
- K20: 1M 上下文请求应被正常支持 [P0]
  客户问题：请求报错 "Input length (918451 tokens) exceeds the
  maximum allowed length (781754 tokens). Use a shorter input or
  enable --allow-auto-truncate."（type: invalid_request_error、
  code: invalid_request、metadata.provider_code:
  bad_response_status_code——网关透传 serving 侧上下文长度校验拒
  绝）。根因：serving 侧未按 1M 上下文契约配置（当时最大允许
  781754）。契约：模型需支持 1M 上下文请求——1M 量级输入应正常
  响应。本用例（用户口径：1M = 输入+输出，总量略小于 1M——余量
  留给推理框架额外补充的长度）探针自校准（重复单元 ×2000 从
  usage.prompt_tokens 精确计量每单元 token 数——客户端无分词
  器，chars/token 启发式误差大：真实环境实测该单元 6.28 字符/
  token，chars/4 高估 57%）后按目标生成主请求：输入 960,000
  tokens（自校准计量）+ 输出预算 max_tokens 覆盖思考+正文，两轮
  思考档位（用户口径：GLM-5.3 不支持禁用思考、仅支持
  reasoning_effort 档位；用户指定补 max 场景）——①low 轮（预算
  1024）常规；②max 轮（预算 4096）最大思考负载，输出侧同步压
  窗口（真实环境实测默认档思考耗尽 32 预算致 content 为空——预
  算必须覆盖思考+正文的教训）
  → 总消耗 ≈961K/964K，两种 1M 口径（1,000,000/1,048,576）下
  均略小于 1M，且高于原始故障上限 781,754 约 178K（缺陷可复现），
  单条 user 消息非流式提交，硬断言：探针 200 且返回 usage；每轮
  主请求 HTTP 200（未被拒绝）；choices 非空且 content 非空（可
  正常响应）；每轮主响应 usage.prompt_tokens（如有）> 781,754
  （规模 sanity——确保真正压过原始故障点）——两轮均 1M 量级输
  入正常响应则 PASS，任一轮被拒（原始报错形态）或空响应均
  FAIL。1M token prefill 耗时长，临时将客户端超时上调至 900s
  （finally 恢复；ReadTimeout 不重试——框架约定）。请求提示词由
  程序生成（无外部文件）。跑必冷（用户加固，仅 low 轮）：low 轮
  （含探针）材料头部置每次请求唯一 nonce（时间戳+uuid，可含中
  文）——前缀必不命中 KV 缓存，真 1M 冷 prefill（缓存只省
  prefill 重算，不绕过准入长度校验/不省 KV 内存驻留与 decode
  全窗注意力——核心契约验证本不受缓存影响，此为 prefill 侧压
  测）；max 轮取消唯一前缀（用户口径：输出侧验证不受缓存影响，
   允许命中历史缓存加速）。采样参数不发送——test_k 保持原始测
   试参数（工单原始请求未指定，不注入）。模型真实响应（状态码/响应体全文）断言前每
  轮打印（失败时同样可见）；usage 仅日志。  （不进 smoke 集：
  新用例首跑观察期）
- K21: system 消息内嵌 tools 的非标请求结构应被接受 [P0]
  客户问题（kimi-k3 工单原始请求体）：messages[2] 为 role=system
  且无 content 字段、代之以内嵌 tools 数组（Calculator 单工具
  ——算术表达式求值），服务端反序列化直接报 400
  invalid_request_error/json_parse_error："messages[2]: data did
  not match any variant of untagged enum MessageContent"。该结
  构虽非 OpenAI 协议标准形态（tools 应为顶层参数），但客户业务
  实际在用——契约：应宽容解析该非标结构并正常响应（预期 200）。
  本用例按工单原始请求体原样重放（模型名按框架约定由环境注入，
  其余字段——系统提示词/用户问题/内嵌 tools 结构——均不改动），
  单次请求（结构解析为确定性行为，无需连发），硬断言：HTTP 200
  （核心——原始报错形态复现即 FAIL）；响应合法 JSON 且 choices
  存在；message 有效输出——content 非空或 tool_calls 非空（宽容
  解析后文本作答/工具调用响应均为成功形态）。模型真实响应（状
  态码/响应体全文）断言前打印（失败时同样可见）；usage 仅日志；
    采样参数不发送——test_k 保持原始测试参数（工单原始请求未指
    定，不注入）。打印
  口径（用户指令）：运行日志不出现具体模型名——系统提示词正文含
  模型自我介绍，日志仅记字符数概要，原文见本 docstring 与用例
  常量。
  （不进 smoke 集：新用例首跑观察期）
- K22: /v1/messages 缓存命中率应与 /v1/chat/completions 基本一致 [P0]
  客户问题：相同请求下，Anthropic 协议（/anthropic/v1/messages）
  的前缀缓存命中率始终低于 chat 协议（"缓存始终上不去"）。根因：
  该链路 system 头部携带 x-anthropic-billing-header: 逐请求动态
  计费行（字符串/块数组两种 system 形态），而前缀缓存要求从位置
  0 连续匹配——头部逐请求变化导致整个前缀永不命中；chat 协议无
  此行、前缀稳定（K15/K16 已验证 ≥90%）。开发修复：入引擎前条
  件剥离——system 开头是 x-anthropic-billing-header: 行即去掉、
  其余内容原样保留。本用例按用户口径模拟客户请求形态：每请求在
  system 头部构造逐请求变化的计费行（值必须变化——静态值修复前
  前缀也相同、缺陷无法复现=假阴性），同轮同问逐轮交替发送两协议
  （前缀头部渠道标记行不同——用户指定：剥离计费行后两协议前缀
  仍从位置 0 分叉，互不命中对方缓存条目，各自建条目/各自命中），
  统计二者缓存命中率并逐轮比较。热轮 messages 全量 miss（read=0
  且 creation=0）时同轮重发一次鉴别（用户指定）：重发命中→WARN
  留痕继续（判定偶发——疑似多实例路由/条目可见性问题，非剥离缺
  陷）；仍 miss→该组不符合预期（剥离失效形态，判别力不变）。
  组级判定（用户指定）：单组失败不中断后续组，5 组中至少 4 组
  符合预期（该组全部热轮差值 ≤3 个百分点）即 PASS、不足 4 组
  FAIL。循环 5 次比对
  （用
  户口径：每次循环的请求消息尽量不一样）：2 组中文、2 组英文、1
  组中英混合，每组前缀 ~8400-12000 tok + 每轮唯一问题
  ~330-550 tok——整请求长度尽量超过 8k tokens；同时覆盖开发修
  复的两条剥离代码路径——块数组形态（断点挂 system 块，K3 口
  径）与字符串形态（断点挂 user 首块，每轮唯一问题置于断点外）。
  每次循环每协议 1 冷轮 + 2 热轮（用户口径；冷轮两协议均无缓存
  可命中，不参与比较——需热轮才能统计命中率；第 2-3 轮热轮逐轮
  比较），共 5 次循环 × 2 协议 × 3 轮 = 30 请求，组间间隔 3 秒
  （用户指定）。
  命中率口径：chat=cached_tokens/prompt_tokens（该轮，K16 字段口
  径）；messages=cache_read/分母（分母按 input_tokens 口径自适应
  ——以同轮 chat prompt_tokens 为参照）。硬断言：①每热轮两协议
  命中率差值 ≤3 个百分点（用户指定容差，任意一轮超差即 FAIL——
  缺陷形态 messages ≈0% vs chat ≈94%，差 ≈90pp）；②每请求
  HTTP 200 且响应正常（chat：choices；messages：usage+content）。
  热轮 cache_creation>0（前缀逐请求重建=剥离失效直接信号）与双
  低形态仅日志留痕。运行日志不含具体模型名。
  （不进 smoke 集：新用例首跑观察期）
- K23: 孤儿 tool 消息应对齐官方放行并正常消费 [P0]
  客户问题（新工单，官方对齐口径）：messages 中 tool 角色消息前
  无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未定
  义任何 tools），平台返回 400（"Invalid parameter: messages
  with role 'tool' must be a response to a preceeding message
  with 'tool calls'."——type: alaya code error、code:
  invalid text request——网关层白加的校验）；而智谱官方源对同
  一请求 HTTP 200 正常应答，且模型在 reasoning 中实际引用了
  tool 消息里的数据（工具数据被模型正常消费）。新契约（客户指
  定）：预期结果同官方一致——此类消息序列不做校验、正常出结果。
  与 K14 的关系：K14 为当时工单口径的原始契约（网关校验拒绝
  400，保持不变——用户指令）；本用例记录新客户需求（官方对齐契
  约）——二者输入同类、预期相反，平台采纳官方对齐修复后 K14 将
  FAIL，其保留/退役由用户决定（本用例不改动 K14）。本用例按客
  户新工单原始请求体还原（messages=[user"查一下北京天气"、
  assistant"好的，我来为您查询北京天气数据。"（纯文本无
  tool_calls——孤儿条件）、tool tool_call_id="call_weather_001"
  content={"city":"北京","temp_c":18,"condition":"晴"}、
  user"根据工具返回的数据，用一句话告诉我天气。"]、
  max_tokens=200、非流式、无 tools/thinking）。硬断言：①HTTP 200
  （核心——原始 400 拦截形态复现即 FAIL）；②响应合法 JSON 且
  choices 非空；③message 有效输出（content 或 tool_calls 非空；
  思考耗光无输出+finish=length 以 reasoning_effort=low 回退重发
  ——K24/K25/K27 口径，双强度均未产出即 FAIL）。
  官方行为细节（输出/推理引用工具数据要素）软校验仅日志；
    finish/usage 仅日志。采样参数不发送——test_k 保持原始测试参数
    （工单原始请求未指定，不注入）。模型
  真实响应（状态码/响应体全文）断言前打印。（不进 smoke 集：新
  用例首跑观察期）
- K24: 双请求正常响应（思考耗尽预算 low 强度回退） [P0]
  客户问题（新工单）：客户两个请求（中文同音词与言部汉字写作题、
  英文数学题）——temperature=0.0、max_completion_tokens=32768
  （工单原始字段名）、非流式，期望均正常响应并返回正文。风险形
  态（用户指定）：默认 max 思考强度下思考可能耗光预算——正文空、
  finish=length。回退契约（用户指定）：第 1 轮按工单原始请求体
  直发（不带 reasoning_effort）；有正常正文即通过；耗光的请求
  以 reasoning_effort=low（GLM 顶层参数，K20 口径）重发，断言相
   同；第 2 轮只重测耗光的（已通过不重测）。采样参数保持原始
   （用户指定）：两请求体均显式 temperature=0.0——工单体为唯一
   口径，test_k 整套件不参与全局采样覆盖（原样保留）。硬
  断言（每轮每请求）：①HTTP 200；②合法 JSON 且 choices 非空；
  ③message 有效输出（content 或 tool_calls 非空）；第 1 轮耗光
  形态转 low 回退不直接 FAIL，low 回退仍无正文即 FAIL（双强度
  均未产出——留证交开发）。finish/usage 仅日志；模型真实响应断
  言前打印；运行日志不含具体模型名。（不进 smoke 集：新用例首跑
  观察期）
- K25: assistant 历史重复 reasoning_content 字段应被兼容接受 [P0]
  客户问题（工单跟进）：多轮对话回填 assistant 历史时，同一条消
  息携带两个 reasoning_content 字段（两轮历史思考未去重地拼接成
  同键重复）与上一次请求的正文；客户原始工单还曾因思考内容含
  They're/I'm/It's 等英文撇号导致 JSON 破损。契约（用户指定）：
  预期不报错、正常响应；第一个 reasoning_content 被第二个覆盖
  （宽松解析保留最后一个值，K18 修复口径）。因需两段真实思考，
  共发三次请求（用户指定，JSON 链式回填——第 1/2 次响应 JSON 作
  为下一请求输入、思考随历史一并回填；提示词为测试自行设计，工单
  未携带具体提示词）：第 1 次 user 单轮要求仅输出 JSON（响应用于
  第 2 次请求输入回填）；第 2 次 messages=[assistant(content=第 1
  次正文（JSON）, reasoning_content=第 1 次思考), user 追问]（回填
  第 1 次历史，要求仅输出 JSON——响应用于第 3 次请求输入回填）；
  第 3 次 messages=[assistant(content=第 2 次正文（JSON）,
  reasoning_content=第 1 次思考, reasoning_content=第 2 次思考),
  user 追问]，流式。重复键无法经 dict 表达——手工拼接 JSON 文本
  直发；正文/思考可能含单引号/双引号/换行（用户指定兼容要求），
  动态值一律 json.dumps 全转义后拼接，发送前三重自检（raw body
  可被 json.loads 解析、"reasoning_content" 键出现次数==2、转
  义回读值一致——回读保留最后一个重复键，模拟服务端宽松解析）。
  硬断言：第 1/2 次请求思考与正文均非空（构造数据源——被测环境
  应开思考，GLM-5.3 默认开思考）、正文为合法 JSON（JSON 链——作
  为下一请求输入回填，断裂即场景无法构造 FAIL；容忍 markdown 代
  码块围栏）；第 3 次请求 HTTP 200（核心——
  报错/4xx 复现即 FAIL）+ SSE 事件非空 + 合并正文非空 +
  finish_reason 合法。耗光回退（K24 口径）：max_tokens=8192 下默认
  max 档思考可能耗尽预算（正文空+finish=length）——该形态以
  reasoning_effort=low（GLM 顶层思考强度参数，K20 口径）仅重发耗
  光请求（第 3 次重发构造不变仅加顶层 reasoning_effort 字段——
  HTTP 200 核心契约首次请求已达成，重复键历史被接受不以正文是否
  为空转移），断言相同；正文空且 finish≠length 直接 FAIL；low 回
  退仍无正文即 FAIL（双强度均未产出——留证交开发）。引号覆盖度软观察：三个回填值均不含引号/换
  行字符时 record_warning 留痕（引号兼容路径本次未被实际覆盖，构
   造本身已保证安全，不判失败）。采样参数不发送——test_k 保持原
   始测试参数（工单原始请求未指定，不注入）。
  usage 仅日志；
  模型真实响应（状态码/合并正文/思考）断言前打印（失败时同样可
  见）。（不进 smoke 集：新用例首跑观察期）
- K26: 工具 schema 负向前瞻正则应被兼容放行 [P0]
  客户问题：工具参数 schema 的 pattern 包含 ^(?!...) 负向前瞻正
  则——后端编译为 structural_tag 生成约束时，底层语法编译器不支
  持 lookahead：非流式报 400（Failed to compile structural_tag
  grammar——Lookahead is not supported yet）、流式报
  provider_unavailable（upstream_stream_error）。修复（frontend
  请求预处理兼容，非底层编译器新增 lookahead 支持）：GLM-5.3+
  glm47 工具解析器+SGLang 后端、tool_choice=auto（structural-tag
  schema 模式 auto）、工具未显式 strict、schema 含 ^(?! 开头正则
  时命中——仅将生成约束用的工具副本置 strict=false 绕过强制编
  译，原始 schema/工具描述/工具调用格式约束保留；属兼容绕过，
  该路径不再由 grammar 强制保证参数满足完整 schema。按触发形态
  构造：path 参数 pattern 以 ^(?! 开头（禁止路径穿越）、不显式
  strict、tool_choice=auto，非流式+流式各发一次。硬断言：非流式
  HTTP 200+choices 非空+message 结构存在；流式 HTTP 200+SSE 事件
  非空+至少一个含 choices 数据块——报错复现即 FAIL；不断言工具
  被调用与参数满足 pattern（兼容绕过明确口径）。GLM-5.3 专用；
    采样参数不发送——test_k 保持原始测试参数（工单原始请求未指
    定，不注入），两个请求一致。usage 仅日志。（不进 smoke 集：新用例首
  跑观察期）
- K27: 历史非法 JSON arguments 应被容忍 [P0]
  客户问题（AGDC2-19，codex 客户端 + MCP 工具场景）：模型输出的
  工具调用 arguments 本身非合法 JSON（两处括号错误——"refId":
  "A"}] 缺 }、40}}}] 处多 }，上游流式日志证实由模型产生）；客户
  端执行失败、回放全量历史，服务端校验历史 tool_calls 的
  arguments 直接 400（Assistant tool call function.arguments
  must be valid JSON）——纯服务端问题，与 codex 客户端无本质关
  系。修复：历史无法解析的 arguments 按字符串保留、不再 400、
  让模型继续纠正。复刻客户链路（user→assistant(畸形 arguments
  调用，保真浓缩版——两处错误形态与关键结构原样、场景自检必
  非法)→tool(执行失败结果，协议配对必需)→user 追问修正重试，
  带 MCP 工具定义，非流式），断言 HTTP 200（核心——报错复现即
  FAIL）+choices 存在+message 结构存在+模型发起修正工具调用且
  每条调用 name/id 非空、arguments 为合法 JSON 对象（修正行为
  ——修复目的"让模型继续纠正"）；不断言历史被改写/修复。耗光回
  退（K24/K25 口径）：预算 16k（max_tokens=16384，工单未载），
  默认档思考仍可能耗尽预算（无正文无调用+finish=length——首跑
  实测 2048 预算 reasoning_tokens 全耗），该形态以
  reasoning_effort=low 重发（构造不变仅加顶层 reasoning_effort
  字段——HTTP 200 核心契约首次请求已达成），断言相同；双强度
    均未产出即 FAIL（留证交开发）。GLM-5.3 专用；采样参数不发送
    ——test_k 保持原始测试参数（工单原始请求未指定，不注入）。
    usage 仅日志。（不进 smoke 集：新用例
- K28: 模型输出字段核验（尾裸/回流/工具参数） [P0]
  客户问题（AGDC2-24，TR-20261016-02 九章云-模型输出字段核验）：
  客户探针报告三项判据——T1 content 尾部裸 </think> 残留（0 次
  为通过，被测平台曾 2/15 不通过）、T2 字段回流（content→
  reasoning，0 次为通过）、T3 工具参数完整性（arguments 合法完
  整 JSON 且 reasoning 无 <arg_key>/<arg_value>/</tool_call> 原生
  标记，100% 为通过）；length 截断只记录不判定。将客户探针
  （scripts/probe_think_tag.py）与数据集（requests/AGDC2-24，工
  单原始参数 stream=true、max_tokens=8192、reasoning_effort=max
  原样保留）纳入框架：3 用例×5 次（--runs 硬编码 5，用户指定）
  流式请求，只评被测平台（不跑对照），逐条留存 raw 并统计三
  项；raw 目录：Jenkins→builds/<TESTER>/<BUILD_NUMBER>/
  origin_raw/AGDC2-24/<model>/（与 allure-report 同级），手动→
  origin_raw/AGDC2-24/<model>/<timestamp>/。硬断言：
  全部 HTTP 200、T1=0、T2=0、T3=100%——任一不符合即 FAIL。模型
  名由环境注入；请求体不含 temperature/top_p/seed——按用户指定
  保持工单原始请求体不变、不注入采样参数。GLM-5.3 专用。（不
  进 smoke 集：新用例首跑观察期）
- K29: 双协议零增量响应与工具调用核验 [P0]
  客户问题（AGDC2-25，九章云 Alaya GLM-5.3 网关）：同一段业务会
  话报文（195 条消息/19 个工具/stream=true/max_tokens=4096）分
  别请求 /v1/chat/completions 与 /anthropic/v1/messages——OpenAI
  协议 13 次中 5 次零增量响应（HTTP 200、SSE 结构完整但
  delta.content/reasoning_content/tool_calls 三类增量均空、
  usage.completion_tokens>0，整条流仅 1 个空 delta chunk），工
  具调用仅 4/13；Anthropic 协议 8/8 返回工具调用、零增量 0/8。
  客户探针（scripts/probe_alaya.py）+ 数据集（requests/AGDC2-25
  两份协议请求体）纳入框架：两种协议各发 --n 硬编码 10 次（用
  户指定）流式请求，逐条留存 raw 并统计三项判据——有效请求
  ==10、零增量==0、返回工具调用==100%（10/10），任一不符合即
  FAIL；每协议追加 1 次强制工具调用（tool_choice required/
  any，仅观察不计入）。raw 目录：Jenkins→builds/<TESTER>/
  <BUILD_NUMBER>/origin_raw/AGDC2-25/<model>/（与 allure-report
  同级），手动→origin_raw/AGDC2-25/<model>/<timestamp>/。模型
  名由环境注入；stream/max_tokens=4096 按脚本口径覆盖；
  temperature/top_p 原始未指定——按用户指定保持不指定（不注
  入）。GLM-5.3 专用。（不进 smoke 集：新用例首跑观察期）
- K30: /v1/responses 校验码输出与 token 计数核验 [P0]
  客户问题（合成短文本 Token 对照测试，/v1/responses 接口）：
  probe 三项断言未通过——请求明确要求只输出
  SYNTHETIC_SHORT_TEXT_MARKER 实际正文输出 '4b69a88e6b'（模型
  未遵守指令）；input_tokens=52 超基准 43 ±3%（区间
  41.71-44.29——整数取值 42/43/44）；output_tokens 报告 295 而
  实际可见输出仅 10 字符且 reasoning_tokens=0（计数与实际文本
  量明显不成比例）。按客户原始 curl 还原：POST {base}/
  v1/responses（Responses API），input 两消息（content 均
  input_text 类型）、stream=true、max_output_tokens=1024 原样，
  模型名由环境注入，采样参数原始未指定——保持不注入。硬断言
  （任一失败即整体失败）：HTTP 200 且流式结构完整；终态事件
  status == completed（failed/incomplete/cancelled 或无终态事
  件即失败）；合并正文严格等于校验码；usage.input_tokens∈
  [42,44]；output_tokens 满足 reasoning_tokens ≤ output ≤
  reasoning + len(正文)（总计=思考+正文，1 token/字符宽松上
  界——缺陷形态 295 tok vs 10 字符远超）。GLM-5.3 专用。（不
  进 smoke 集：新用例首跑观察期）
- K31: json_object 嵌套结构完整输出与预算回退核验（256→512，chat+msg 双协议） [P1]
  客户问题（工单 P1 R-01+A-07a/A-07b，结构化输出）：官方行为
  HTTP 200、content 为合法 JSON（嵌套对象/数组均可解析）；贵
  方实测 finish_reason=length、content 为空字符串、思考内容占
  满 max_tokens=256——A-07a（嵌套对象 user.name/user.age/
  address.city，021-023.json）与 A-07b（数组 3 个 id+title 对
  象，024-026.json）两种请求各 3 发全部该形态（3 采样 0 过，
  2026-11-03），reasoning_tokens=256/256。用户确认：思考消
  耗配额致空正文/截断在官方与被测均有一定概率发生——验收口
  径调整为预算回退链（用户指定）：核心需求为在 max_tokens 内
  能返回完整合法 JSON。chat+msg 双协议（msg 无 json_object 参
  数语义——同一 prompt 引导、max_tokens 协议必需字段）× 工单
  两形态（提示词/请求体工单原样，chat 字段序 model/messages/
  max_tokens/response_format、无 stream 字段）× 预算回退链：
  轮一 max_tokens=256（工单原值）——HTTP 200+正文非空+
  json.loads 成功+嵌套结构齐备（递归宽容：含 name+age 的
  user 对象与含 city 的 address 对象 / 对象数组每元素含
  id+title，裸数组或对象包裹均认可，数量=3 与类型留观察）→
  直接达标；不满足（空正文/json 截断或非法/结构不齐）→ 回
  退 max_tokens=512 同请求重验——满足→测试通过+警告留痕（警
  告显示 256 输出空正文或 json 截断及 finish 状态）；两轮均
  不满足→FAIL（输出两轮各自形态）。HTTP 非 200 直接 FAIL（回
  退链仅针对正文形态）。finish_reason/stop_reason=length/
  max_tokens 且正文完整合法不判失败留观察；A-07 形态（空正文+
  reasoning_tokens=256）留痕。历史记录：初版按 R-01 设计（三
  接口 chat/responses/msg × 两形态 × 各 2 次，断言 256 内正
  文非空）；A-07a/A-07b 证据后重构为预算回退链并聚焦双协议
  （用户指定"覆盖两种协议"），/v1/responses 轮移除。模型名由
  环境注入；采样参数/thinking/stream 工单未指定——不注入。
  GLM-5.3 专用。（不进 smoke 集：新用例首跑观察期；双协议 ×
  两形态 4 链 × 每链 1-2 发）
- K32: temperature 原厂区间 [0, 2] 放行与越界校验（chat+msg
  双协议） [P1]
  客户问题（工单 P1 R-02+A-03，参数校验）：官方行为 HTTP 200
  （原厂取值区间 [0, 2]，1.5 合法）；贵方最新实测（A-03，
  2026-11-03）chat 三发 temperature=1.5 全部 HTTP 400，错误体
  「temperature 超出范围 [0, 1]」(bad_response_status_code)
  ——本地收紧到 [0, 1]；历史形态（R-02）6 发全部 400 通用
  「模型服务调用失败」(upstream_error)。整改建议（即预期结
  果，用户指定）：放开 temperature 到原厂支持的 [0, 2] 区间
  （原合法区间 [0, 2) 调整为 [0, 2]——上界端点 2.0 移入放
  行），或按原厂取值原样透传，不做本地收紧；保留非法参数
  校验（越界 400 并指明参数名与区间）。本用例双向验收（chat
  放行点按工单 A-03 三发依序复现，其余组合每组合 1 次——K6
  先例）双协议覆盖（chat + msg——K31 起用例须验证
  /v1/chat/completions 与 /v1/messages 双协议，用户指定）：
  chat 协议按原厂区间 [0, 2]——工单 A-03 三发复现
  temperature=1.5、content="只回复:好"、max_tokens=32（请求
  体工单原样：字段序 model/messages/max_tokens/temperature、
  无 stream 字段）→ 200+choices 非空（正文/finish_reason 留
  观察不计判据——max_tokens=32 小配额下默认思考计入共享配额
  易 length/空正文，K31 域形态非本例判据；A-03 判据为 HTTP
   状态语义）；边界轮 2.0（上界端点移入放行，测试自构造轮；
   请求对齐 A-03 短形态 content="只回复:好"+max_tokens=32+
   无 stream 字段，断言对齐 A-03 轮口径：200+choices 非空、
   正文/finish 留观察（K31 域形态非判据——主判据=2.0 被接
   受 200）——用户指定 2026-11-09）；左边界轮 0.0（下界端
   点，用户指定 2026-11-09 新增；长形态 max_tokens=1024）
   → 200+choices 非空（正文/finish 留观察——主判据=0.0 被
   接受 200）；越界轮 2.5 与 -0.5（max_tokens=1024——所有
   轮均须 max_tokens 限制，用户指定 2026-11-09）→
   400+错误体
  指明参数名 temperature（大小写不敏感）+含上界数字 2（区
  间痕迹辅助下限口径——A-03 形态错误体含 request id 数字串
  可能恒满足，本地收紧主判据在放行轮 200）。msg 协议
  （/anthropic/v1/messages）按 Anthropic 官方区间 [0, 1] 分
  别校验（A-03 未涉及 msg，维持原口径）——放行轮
  temperature=0.5（工单原值 1.5 在该协议官方语义下越界，不
  可作放行点）与 0.0（下界端点，用户指定 2026-11-09 新增
  ——双协议口径一致）→ 200+正文非空+stop_reason 自然结
  束；越界轮
  1.5（工单原值，[0, 1] 越界——与 chat 侧同值不同判，验证
  网关按协议语义分别校验而非一刀切）与 2.0、-0.5 → 400+错
  误体指明参数名 temperature+含上界数字 1（区间痕迹）。非流
  式直发，每发 60s 硬超时（K32_HARD_TIMEOUT 用例内自定覆盖全
  局 timeout——小请求正常返回毫秒级-秒级，挂起/严重延迟快
  速失败：超时即 FAIL 留痕，仅本用例生效、不影响他例）；工
  单原始值 temperature/max_tokens 原样保留并豁免全局采样覆
  盖；top_p/seed/thinking 工单未指定，不注入；所有轮均传
  max_tokens（32/1024——用户指定 2026-11-09，当前无限制的
  取 1024）；msg 协议 max_tokens 为必需字段；A-03 工单三发
  采集间隔 1s（节奏非判据），复现按
  套件相邻 3s。GLM-5.3 专用。（不进 smoke 集：新用例首跑观
  察期）
- K33: top_logprobs=5 放行核验（未开 logprobs 也接受，chat+msg
  双协议） [P2]
  客户问题（工单 P2 A-04，参数校验）：官方行为不变——
  top_logprobs=5 官方 HTTP 200 接受（未开 logprobs 时也接
  受）；贵方最新实测（A-04，2026-11-03）chat 三发
  top_logprobs=5 单独出现（无 logprobs）全部 HTTP 400，错误体
  「top_logprobs is only allowed when logprobs is enabled」
  (top_logprobs_requires_logprobs)——对未开 logprobs 的
  top_logprobs 额外拒绝。整改建议（即预期结果）：按官方行为
  处理 top_logprobs（未开 logprobs 时也接受），不额外拒绝；
  若上游确实不支持，错误体应说明能力缺失而非参数非法，避免
  客户端反复重试。用户判定口径（2026-11-06）：top_logprobs=5
  不要拒绝、按官方 HTTP 200 即可；正文为空不判定失败（R-03
  轮移除，仅保留 A-04 请求——用户指定 2026-11-06）。双协议
  覆盖（chat + msg——K31 起用例须验证双协议，用户指定）：chat
  协议——A-04 三发复现 top_logprobs=5 单独出现（无 logprobs
  字段）、content="只回复:好"、max_tokens=32（请求体工单原
  样：字段序 model/messages/max_tokens/top_logprobs、无
  stream 字段）→ 200+choices 非空（正文/finish_reason/
  logprobs 结构留观察不计判据——小配额+默认思考计入易
  length，K31 域形态；客户预期仅定义接受语义，与 K32/K35
  断言收缩同理）；msg 协议
  （/anthropic/v1/messages）无 logprobs 参数语义（Anthropic
  官方未知字段应 400 拒绝）——A-04 镜像 3 发（top_logprobs
  单独出现、content 工单原样字符串、max_tokens=512 套件必
  需字段值——工单 32 为 chat 小配额口径）硬断言统一行为：
  要么全部 400 且错误体指明字段（含
  "logprobs"，top_logprobs 子串覆盖，能力缺失说明口径——整
  改建议两分支之一），要么全部 200（网关忽略该参数统一作
  答）；正文为空不判定失败（用户口径：top_logprobs=5 不拒
  绝、官方 200 即可——空正文留观察，用户指定 2026-11-06）；
   混现（时拒时放）即 FAIL——额外拒绝与行
  为不统一缺陷在两协议均不得复现；msg 协议 max_tokens 为必需
  字段。max_tokens/thinking/采样参数工单未指定——不传（不注
  入）；A-04 工单三发采集间隔 1s（节奏非判据），复现按套件
  相邻 3s。GLM-5.3 专用。（不进 smoke 集：新用例首跑观察期；
  P2 选测——双协议 6 发）
- K34: 多模态媒体块该拒未拒（msg 侧静默丢弃返回 200）应 400
  明确拒绝（chat+msg 双协议） [P2]
  客户问题（工单 P2 R-04 补充证据 A-01，多模态）：官方行为
  glm-5.3 为非多模态模型——请求携带图片/音频/视频/文档
  （base64 与 URL 两种载体）必须返回 400，返回 2xx 即不合格；
  原始问题：msg 协议下返回 200 该拒未拒——媒体块被静默丢弃：
  prompt_tokens 仅 17-43（媒体未进入分词器）、正文自述『没有
  收到视频/音频/文档』，同一素材 chat 协议渠道返回 400（同一
  渠道、同一文件、两种协议两种结果）；整改建议（客户给出）：
  /v1/messages → OpenAI 转换层对 media block（video/audio/
  document）前置校验返回 400 并给出明确文案，不得剥离媒体块后
  继续转发，URL 载体同样必须 400、不得自行抓取/转文字/降级纯
  文本，chat 协议也应相同处理。本用例双协议各 5 发共 10 发
  （用户指定：message 协议和 chat 协议都要 5 轮请求）：msg 5
  发按工单原始记录依序复现（缺陷复现轮）——document×
  base64、text+audio×base64（文本块在前——工单原序）、
  video×base64、video×url（沿用本仓现有 MDN flower.mp4 地址
  ——工单原 test-videos.co.uk 不复用，用户指定保留现有
  URL）、video×base64（工单第 5 采集提问原样）；chat 5 发为
  同素材/同提示词/同块序镜像（整改『chat 协议也应相同处理』
  ——一致性核验轮；part 映射：document→file part（file_data
  data URL）、audio→input_audio、video→video_url（base64 发
  data URL））；媒体数据工单未提供完整 data——代码生成有效
  base64（最小 PDF/WAV/MP4 容器，内存生成不落临时文件；拒绝
  校验在媒体块类型层不依赖可解码内容；双协议第 3/5 发共用同
  一生成 MP4——判定在类型层）；max_tokens=1024 工单原值（10
  发同值镜像，豁免注入）；请求体不含 stream 字段（工单原始格
  式，两协议默认非流式）；thinking/采样参数未含——不注入；
  相邻间隔 3s。硬断言每发：HTTP 400（200=静默丢弃缺陷复现
  ——A-01 形态（prompt_tokens 仅 17-43+正文自述未收到）留
  证）+ 错误体含对应媒体类型关键词（中英任一命中：document/
  文档/pdf、audio/音频/语音、video/视频——20261104 实测整改
  错误体为中文，双语匹配（用户指定）；排除通用『模型服务调
  用失败』缺陷形态）；'text' 痕迹留观察。GLM-5.3 专用。（不
  进 smoke 集：新用例首跑观察期）
- K35: 关闭思考应按原厂 400 拒绝（enable_thinking=false 与
  thinking.type=disabled 双路径，chat+msg 双协议） [P1]
  客户问题（工单 P1 R-07 补充证据 A-02 · chat/msg 协议关闭思考
  的请求被放行，接口协议）：官方行为：原厂对关闭思考返回 400
  （原厂 HTTP 400）；贵方实测（A-02，2026-11-03 采集，2 发均
  HTTP 200）：渠道返回 200 并正常出文——chat 发
  enable_thinking=false 放行且响应带 reasoning_content（思考仍
  开启，reasoning_tokens=91）、msg 发 thinking.type=disabled 放
  行且 content 带 thinking 块（思考仍开启），对照记为
  http_status 400→200（HTTP 状态语义）；预期行为（整改）：统
  一关闭思考的拒绝口径——enable_thinking=false 与
  thinking.type=disabled 两条路径均按原厂返回 400，不得一条拒
  一条放。本用例按客户原始请求 A-02 依序复现（用户指定——两
  条路径都要按官方行为返回 400，覆盖两种协议）：路径1 chat 协
  议（/v1/chat/completions）enable_thinking=false（工单原样：
  content="23+19 等于多少？"、max_tokens=512、不含 stream 字
  段）；路径2 msg 协议（/anthropic/v1/messages，x-api-key +
  anthropic-version 头——K3 先例）thinking={"type": "disabled"}
  （工单原样：content="23+19=?" 为字符串、max_tokens=512、
  stream=false 显式携带）；硬断言每路径：HTTP 400（200=放行
  缺陷复现——A-02 形态：200 且正常出文（思考仍开启）；
  500 等=非合规拒绝）；错误体参数名痕迹（路径1 enable_thinking/
  路径2 thinking）留观察不计判据（官方拒绝文案常含参数名；
  排除通用『模型服务调用失败』不含参数名缺陷形态）；max_
  tokens=512 工单 2 发同值（豁免注入）；采样参数未含——不注
  入；相邻间隔 3s。GLM-5.3 专用。（不进 smoke 集：新用例首
  跑观察期）
- K36: finish_reason 判定对齐官方（stop 语义——流式/多段/结构化 × 双协议） [P1]
  客户问题（工单 P1 R-06，接口协议）：官方行为 finish_reason=
  stop（20_chat_stream_002 / 20_chat_ms_001 /
  20_chat_structured_002 三例）；贵方实测同一请求渠道返回
  finish_reason=length，官方返回 stop（三例一致复现）。整改建议：
  对齐 finish_reason 判定——思考 token 不应把正常结束的请求判
  成 length 截断。本用例按官方行为进行预期断言（用户指定），覆
  盖三种请求形态（工单三例）× 双协议（chat + msg——K31 起用例
  须验证双协议）：1. 流式（chat SSE/msg SSE，收集终止字段与正
  文增量）；2. 多段（单条 user 消息 content 数组多段文本）；
  3. 结构化（chat response_format=json_object；msg 无该参数按
  K31 先例 prompt 引导）。硬断言（每形态 × 每协议）：终止语义
  对齐官方——chat finish_reason == "stop" / msg stop_reason ==
  "end_turn"（Anthropic 协议自然结束语义——msg 侧的 stop 等价；
  length/max_tokens=缺陷复现：思考 token 计入判定把正常结束的
  请求误判截断）+ 正文非空（正常结束的佐证；正文空+length 为
  思考耗光配额的 K31 形态，非本例"正常结束误判"口径）。
  max_tokens=512（工单三例未附原始 payload——取适中值：单句/短
  JSON 正文远低于配额（官方自然结束 stop），默认档思考 token 常
  达数百，计入判定的实现易触顶误判 length，对判定语义敏感且不
  致正文真实截断）；thinking/采样参数工单未指定——不传（不注
  入）；相邻间隔 3s。GLM-5.3 专用。（不进 smoke 集：新用例首跑
  观察期）
- K37: n=2 请求应 400 拒绝且不挂死（返回提示信息） [P0]
  客户问题（工单 P0，异常）：贵方实测 n=2 请求无响应直至超时——
  参数电池 3/3 轮 TimeoutError（已重试 1 次仍超时）、协议电池
  2 例 ReadTimeout、直连 300s 超时，挂死同时导致模块 4 的 n=2
  探针被记为『无效』而未计失败；官方行为为 200+1 choice。客户
  明确需求（2026-11-06，契约口径）：当 n=2 时 400 拒绝，并返
  回相应的提示信息，但不能卡死（示例响应：HTTP 400
  {"code":1210,"message":"参数有误：glm-5.3 仅支持 n=1，收到
  n=2 (request id: ...)"}）——客户明确需求优先于官方对齐（用
  户指定按新契约断言，替代原官方 200+单 choice 口径）。本用例
  chat 2 发对齐工单 055/056 口径，工单原值原样保留（"说一句
  话。"/max_tokens=16/n=2），单发直发不重试，requests
  timeout=30s 硬超时——超时即 FAIL 挂死复现（纠正『无效不
  计失败』漏报形态）；硬断言每发：30s 内返回 + HTTP 400（200
  放行=未按客户契约拒绝；500 等=非合规拒绝）+ 提示信息指明
  n 参数限制（响应体合法 JSON、message 非空且含 "n=1"/
  "n=2" 子串，大小写不敏感——客户示例：参数有误：glm-5.3 仅
  支持 n=1，收到 n=2）；错误码 code（如 1210——平台错误码口
  径不硬绑）/request id/elapsed 留观察；chat 单协议（n 为
  OpenAI 参数、msg 无该语义——msg 未知参数行为由 K33/K35 覆
  盖）；thinking/采样参数未含——不传（不注入）；相邻间隔 3s。
  GLM-5.3 专用。（不进 smoke 集：新用例首跑观察期）
- K38: max_completion_tokens 别名单 token 请求不挂起（与 tokens 主路径同延迟水平） [P0]
  客户问题（工单 A-A01，异常）：官方判定通过——max_completion_
  tokens 别名为单 token 请求，被接受并按 max_tokens 语义立即截
  断返回；贵方实测客户原始请求 1 发即挂起——180s 请求超时、无
  响应（HTTP 0，采集未落盘）。预期行为（整改）：不得触发 180s
  级挂起；需与 tokens 主路径同延迟水平。本用例按原始请求与预
  期行为验收（用户指定），chat 单协议 2 发：别名轮工单原样
  （单 user "Write a long essay about turbines." +
  max_completion_tokens=1，字段序 model/messages/max_
  completion_tokens，无 stream 字段）1 发对齐工单口径；主路
  径轮同 prompt max_tokens=1 对照基线 1 发。硬断言：别名轮
  30s 硬超时（requests timeout=30s——对齐 K37 先例，远低于工
  单 180s 挂起水平；单发直发不重试——重试掩盖挂起证据且超
  时等待翻倍）内返回、HTTP 200（官方判定通过）+ 响应体合法
  + usage.completion_tokens<=2（别名生效——单 token 截断；
  字段被丢弃则长文数百 token）；主路径轮 30s 内返回 + 200；
  同延迟水平判据：别名 elapsed<=主路径 elapsed*3+10s（容网
  络抖动）。超时即 FAIL 挂起复现（工单 180s 无响应形态）；字
  节缓流形态留观察人工分派（K37 口径）；finish_reason/正文
  留观察（1 配额默认思考计入易空正文+length——K31 域形态非
  本例判据）。chat 单协议（max_completion_tokens 为 OpenAI
  别名字段、Anthropic /v1/messages 无该字段——max_tokens 即
  协议必需主路径字段，msg 未知参数行为由 K33/K35 覆盖）；模
  型名由环境注入；thinking/采样参数工单未含——不传（不注
  入）；相邻间隔 3s。GLM-5.3 专用。（不进 smoke 集：新用例
  首跑观察期）。暂挂 SKIP（用户指定 2026-11-06）：官方环境复
  测同形请求亦超时——官方判定基线（别名立即截断返回）失效，
  判定口径待澄清后恢复执行
- K39: 历史 assistant 消息 reasoning/reasoning_content 双字段共存兼容核验（同值/异值 × 两字段序） [P0]
  客户问题（工单 AGDC2-47，接口协议）：多轮对话历史 assistant
  消息同时携带 reasoning 与 reasoning_content（合法 JSON 两个
  不同键——部分客户端/上游分别使用两字段名，历史拼接时共
  存）即 HTTP 400、错误码 json_parse_error、提示 duplicate
  field reasoning_content——两字段值相同或不同均报错；单字
  段（仅 reasoning 或仅 reasoning_content）调用成功；客户生
  产调用大量报错。官方 API 验证结论（AGDC2-47 测试资料，
  2026-11-05 Kimi K3 官方端点）：同一请求形态 14 组合（字段
  变体 × 默认/关闭思考）全部 HTTP 200、finish_reason=stop、
  回答 3——双字段共存不必然导致错误（含双字段同值/异值 ×
  两字段序全部 200）。预期行为（整改）：历史消息同时存在
  reasoning 与 reasoning_content，无论两字段值相同或不同、
  哪个字段在前，均不得 400，应正常请求成功。本用例按官方验
  证请求原样复现（用户指定：只测双字段共存场景，不测单字段/
  无字段；调整两字段顺序 × 覆盖同值/异值），chat 单协议 4
  发（相邻间隔 3s），同一三消息结构（user "What is 1 + 1?
  Reply with only the number." / assistant content="2"+双
  思考字段 / user "Add 1 to the previous answer. Reply with
  only the number."），请求体官方验证原样（字段序 model/
  stream/max_tokens=512/messages，stream=false，thinking 默
  认模式不传）：同值/reasoning 在前、同值/reasoning_content
  在前（两字段均 "1 + 1 = 2."）、异值/reasoning 在前、异值/
  reasoning_content 在前（reasoning="Compute the sum."、
  reasoning_content="The answer is two."）。硬断言每发：HTTP
  200（400 json_parse_error/duplicate field reasoning_
  content=缺陷复现）+ 响应体合法 + choices 非空 + 正文非空
  （空正文+finish=length 留观察——512 预算默认思考计入耗尽
  属 K31 域形态；空正文且 finish≠length 即 FAIL）。finish_
  reason/回答含 3（官方验证回答为 3——生成质量非本例判据）/
  正文长度留观察。显式关闭思考模式不测（官方双模式均 200 证
  明字段兼容性与模式正交；K35 已确立网关对关闭思考 400 拒
  绝口径——另一缺陷域）；chat 单协议（reasoning/
  reasoning_content 为 chat 历史消息字段，Anthropic
  /v1/messages 无该字段形态——思考经 thinking content block
  承载，msg 未知参数行为由 K33/K35 覆盖）；模型名由环境注
  入；thinking/采样参数官方验证请求未含——不传（不注入）；
  相邻间隔 3s。双 marker GLM53 + KimiK3——工单缺陷经 Kimi
  K3 官方端点验证，字段解析为接口层通用逻辑（与模型无关），
  同时适用 GLM-5.3 与 Kimi K3（请求同构，模型名由环境注入，
  无模型分支）。（不进 smoke 集：新用例首跑观察期；4 请求）
- K40: thinking enabled 响应 reasoning_content 字段稳定性核验（三
  轮 × 每轮 10 并发统一携带） [P1]
  客户问题（新工单，响应字段稳定性）：请求体 max_tokens=
  16000 + 单 user 消息「证明：对于任意正整数n，n^3-n能被6
  整除」+ thinking={"type": "enabled"}（客户环境模型 GLM-
  5.3-jy-b）——响应有时带、有时不带 reasoning_content 字段，
  不稳定，客户生产调用产生较多困扰；预期所有请求统一携带
  reasoning_content。本用例分三轮、每轮 10 并发（轮内
  ThreadPoolExecutor 10 workers 同拍齐发——E5 并发稳定性先
  例；轮间串行——每轮收齐后再开下一轮；用户指定
  2026-11-09：测试分为三轮、每轮 10 并发，所有轮的所有请求
  reasoning_content 统一才算通过；同日调整确认：每轮结束收
  集一次，任一轮次不一致即失败中止——避免后续轮次浪费）验
  证统一性，请求体工单原样（max_tokens=16000、thinking.
  type=enabled、单 user 消息；stream 工单未含——不传，非流
  式默认；采样参数未含——不注入；模型名由环境注入，用户确
  认——GLM-5.3-jy-b 为客户内部档位名）。逐轮判定（每轮收
  齐即断言该轮，任一轮失败即用例失败并中止后续轮次——用户
  指定：避免无效轮次消耗）：断言1 该轮 10/10 HTTP 200；断言
  2 该轮 10/10 响应体合法 JSON+choices 非空；断言3 该轮
  10/10 choices[0].message.reasoning_content 存在且非空（「统
  一」口径=字段层面全部携带，用户确认——空字符串同样属「没
  有」，内容逐字一致不作要求——思考文本天然因请求而异；缺
  失/空串清单全量输出=缺陷复现证据，如「第 2 轮 8/10 携带，
  缺失 #R2-3/#R2-7」）。三轮全通过才 PASS。观察（不计判
  据）：逐轮+整体 finish_reason/正文长度/思考长度分布/耗
  时。超时沿用全局（工单未涉及超时语义）。chat 单协议（客
  户请求为 chat 形态，缺陷为 chat 响应字段——Anthropic msg
  思考经 thinking content block 承载，无 reasoning_content 字
  段形态）。GLM-5.3 专用（工单模型 GLM-5.3-jy-b 为 GLM-5.3
  档位变体，缺陷为响应字段生成逻辑，无模型分支）。（不进
  smoke 集：新用例首跑观察期；三轮 × 每轮 10 请求）
- K41: stop 空数组应正常响应核验（400 拒绝缺陷，chat 单协议） [P1]
  客户问题（新工单，参数校验）：请求带 stop=[]（空数组）时平台
  400 拒绝，两种错误形态（两个 request id）——上游校验错透传
  {"error": {"message": "Validation: Stop sequences array cannot
  be empty (...)", "type": "upstream_error", "param": "400",
  "code": "bad_response_status_code"}} 与平台参数错 {"code":
  1210, "message": "max_tokens 超出范围 [1, 131072] (...)"};
  预期（整改）：正常响应、正常结束（finish=stop），不应触发模
  型服务的最大输出上限 128k。本用例单发 stop=[] 请求（参数处理
  确定性，K6/K23 先例），请求体最小构造（stop=[] 工单唯一原样
  参数+自拟最小 user 消息——工单未携带消息内容；max_tokens 不
  传——用户确认 2026-11-09：工单未提供不注入，且缺省填充上限
  缺陷路径恰好由不传覆盖；stream/thinking/采样参数未含——不
  传不注入；模型名由环境注入——工单无模型线索）。断言：1)
  HTTP 200（400=缺陷复现——两种工单错误文案归类留证）；2) 合
  法 JSON+choices 非空；3) finish_reason=="stop"（正常结束——
  工单原话；length=触发输出上限 128k 形态）；4) 正文非空。观
  察（不计判据）：400 时错误体归类（Stop sequences array
  cannot be empty→上游校验错形态/max_tokens 超出范围+code
  1210→平台参数错形态）；200 时 usage.completion_tokens 异常
  大（撞 128k 上限痕迹）留痕。超时沿用全局（工单未涉及挂死/
  超时语义）。chat 单协议（错误体为 chat 形态响应；msg 未知参
  数行为由 K33/K35 覆盖）。GLM-5.3 专用（工单无模型线索，缺
  陷为平台/引擎层 stop 校验与 max_tokens 上限路径，无模型分
  支）。（不进 smoke 集：新用例首跑观察期；1 请求）
- K42: Kimi-K3 工具调用长参数流式停流核验（间隔<30s+正常终止，chat 单协议） [P1]
  客户问题（工单 AGDC2-45 · Kimi-K3 流式中途停流）：kimi-k3 流
  式请求正常出流（~70 chunk/s、已出 1480 tokens）后正文结束，连
  续 30s 无任何字节——无 finish_reason/tool_calls/[DONE]，连接
  未断，客户端按 30s 无数据取消策略断开（网关日志「客户端已断
  开，已中断渠道 #20 上游请求」）；多条历史请求同形态（中断、
  finish_reason 为空）。根因（排障报告确认）：SGLang 0.5.21
  kimik3_detector 工具调用解析器按完整 call 整包输出、不增量
  发工具参数——正文/思考可先结束，长参数生成阶段参数全部缓存
  在解析器内，SSE 无新数据无心跳（serving_chat.py 空时不
  yield）；线上抓包 3 样本空窗 71.697/89.010/116.724s（恢复时
  一次性返回 7952/12831/12044 字符参数），均超客户 30s 取消阈
  值。本用例单发原样回放抓包请求 tests/data/k42_request_
  original.json（231,432 字节，sha256 371b1753...；78 messages/
  25 tools/31 历史工具调用，agentic 工作流场景——报告方法 C 口
  径：单并发、读空闲 180s、总时限 600s）。请求构造：messages/
  tools/temperature=1/max_completion_tokens=131072/stream=true/
  stream_options={"include_usage": true}/reasoning_effort="high"
  全部原样（抓包原样参数）；stop/tool_choice/seed/采样参数未
  含——不注入；model 由环境注入（用户确认 2026-11-09——与既有
  K 用例一致，运行环境指向 Kimi-K3 实例）。判定（单发，四断
  言）：1) HTTP 200 + SSE 事件流；2) 正常终止——收到非空
  finish_reason 且收到 [DONE]（缺陷形态=两者皆无直至客户端断
  开）；3) 全程任意相邻 SSE 事件间隔 < 30s（客户取消阈值；缺
  陷实测 71.7-116.7s 空窗；TTFT 不计入——首 token 问题报告声明
  另行排查）；4) finish=tool_calls 时逐 tool index 拼接
  arguments 为完整 JSON 且工具名非空（报告修复验证标准 4）。
  观察（不计判据）：TTFT（历史实测 22.6/44.2s）、事件数、最大
  事件间隔及位置、工具参数增量事件数（修复标准 2 证据——长参
  数阶段应有多段 delta 而非整包）、参数字符数、usage、请求文
  件 sha256 留痕。超时：读空闲上限 180s（requests 读超时按字节
  间隔计——K37/K38 先例；永久停流触发 ReadTimeout=缺陷形态
  FAIL）；总时限 600s 墙钟检查。chat 单协议（工单为 chat SSE
  流式）。仅 KimiK3（工单模型 Kimi-K3，缺陷为 SGLang K3 工具
  解析器层，无其他模型分支）。（不进 smoke 集：新用例首跑观察
  期；单发大上下文 prefill+131072 上限，耗时约 1.5-4 分钟）
- K43: responses 端点空 input 400 拒绝核验（对齐官方，responses 单协议） [P1]
  客户问题（工单 AGDC2-55 · alayanew vs 智谱官方未对齐 #48）：相
  同请求 POST /v1/responses {"model": "glm-5.3", "input": [{"role":
  "user", "content": [{"type": "input_text", "text": ""}]}],
  "max_output_tokens": 32}，alayanew 返回 200（错误——空 input 文本
  被接受并生成 reasoning 内容，status=incomplete/
  incomplete_details.reason=max_output_tokens，usage output_
  tokens=32），智谱官方返回 400 {"error": {"code":
  "invalid_request", "message": "输入不能为空", "type":
  "invalid_request"}}。预期（对齐官方）：400 拒绝，错误体
  code=invalid_request、message 含「输入不能为空」。本用例单发非
  流式原样请求（请求体全部工单原样，仅 model 环境注入；responses
  端点 staging 网关已有——报文实证）。断言：1) HTTP 400（200=缺
  陷复现——空输入被接受，响应结构 status/incomplete_details/
  output/usage 留证）；2) 错误体 code=="invalid_request"；3)
  message 含「输入不能为空」（对齐官方原文）。观察（不计判
  据）：400 时错误体全文；200 时缺陷响应结构留证。超时沿用全局
  （工单未涉及挂死/超时语义）。responses 单协议（缺陷为
  responses 端点空输入校验缺失；chat 端点无关）。GLM-5.3 专用
  （工单模型 glm-5.3）。无新增数据文件（请求短小完整内联）。
  （不进 smoke 集：新用例首跑观察期；1 请求）
- K44: reasoning_effort="none" 应被接受核验（对齐官方，chat 单协议） [P1]
  客户问题（工单 AGDC2-55 · alayanew vs 智谱官方未对齐 #10）：相
  同请求 POST /v1/chat/completions（确认参数 max_completion_
  tokens=128 + reasoning_effort="none"——标题与 alayanew 错误文
  案双重佐证；原始消息 349,732 字符被截断不可得，缺陷为参数校验
  层与消息内容无关），alayanew 返回 400 {"code": 1210, "message":
  "reasoning_effort 取值非法: none（glm-5.3 仅支持 low / high /
  max）"}，智谱官方返回 200（finish=stop，正文非空，reasoning_
  content 非空 18 tokens——官方接受 none 并正常生成）。预期（对
  齐官方）：200 正常响应。本用例单发非流式：请求体 = 工单确认参
  数 max_completion_tokens=128 + reasoning_effort="none" 原样 +
  自拟最小 user 消息（工单消息不可得且不影响缺陷路径）；模型名
  由环境注入；两侧工单响应均非流式形态——stream 不传（不注
  入）。断言：1) HTTP 200（400=缺陷复现——1210「reasoning_
  effort 取值非法: none（glm-5.3 仅支持 low / high / max）」文案
  留证）；2) 合法 JSON+choices 非空；3) finish_reason 非空（对齐
  官方 stop 形态）；4) 正文非空。观察（不计判据）：reasoning_
  content 存在性/reasoning_tokens（官方 none 仍返回 18 reasoning
  tokens 的形态留痕——none 语义为不声明思考努力档位，官方仍产
  出思考）；400 时错误全文留证。超时沿用全局。chat 单协议（缺
  陷为 chat 参数校验过度严格）。GLM-5.3 专用（工单模型 glm-
  5.3）。无新增数据文件。（不进 smoke 集：新用例首跑观察期；
  1 请求）
"""

import base64
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import os
import struct
import time
import uuid
import zlib
from datetime import datetime
import pytest
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestCustomerIssue(BaseTest, StreamingTestMixin):
    """客户问题复现测试类

    每个用例自包含：该用例的常量与内部辅助函数均定义在用例方法内部
    （见模块 docstring 的"用例自包含约定"）。
    """

    def get_test_category(self) -> str:
        return "K. 客户问题复现"

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_pydantic_schema_tool_call_stream(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K1 [P0]: 客户问题 - Pydantic $defs/$ref Schema 工具调用报【$$不兼容】

        客户使用 glm-5.3 发起 thinking+stream+强制 tool_choice 的通话分析请求，
        tools 的 parameters 为 Pydantic v2 自动生成的 JSON Schema（含
        $defs/$ref 引用），服务端报错【$$不兼容】。本用例按客户原始 curl
        原样复现请求，验证：
        - 服务端正常处理该请求并返回流式 chunks（不报 $$ 相关错误）
        - 返回强制指定的 submit_d2_product 工具调用（含 id）
        - 工具参数为合法 JSON 且满足 schema 必填项（core_work_type）
        - stream_options.include_usage 的 usage 返回（缺失仅告警）
        """
        # K1: 客户原始请求的 system 提示词（与 curl 完全一致）
        K1_SYSTEM_PROMPT = (
            "你是通话内容分析师。请根据通话内容完成指定维度的结构化提取。只提取客观事实。"
        )

        # K1: 客户原始请求的 user 消息（与 curl 完全一致）
        K1_USER_PROMPT = (
            "请从以下通话中提取产品与工作分类信息。\n"
            "核心工作类型：产品售卖|大搜解搁|充值续费|账户优化|流程处理|客情维护|"
            "活动通知|操作指引\n"
            "\n"
            "## 通话内容\n"
            "\n"
            "坐席：'喂你好百度，'\n"
            "客户：'您说，'\n"
            "坐席：'嗯是这样的我们那个vip神经元这个账户的话是已经分到我这边了，"
            "然后跟您说一下，后续的账户负责是通过我这边给您去做维护，'"
            "'然后后续的话我让这个咱们的开户销售拉个群到时候我们有什么问题"
            "直接在群里沟通好吧，'\n"
            "客户：'嗯可以啊，''就是我没用过咱们这平台有培训吗？'\n"
            "坐席：'培训的话我这边可以教您一些比较基础的，然后详细的话它百度这边"
            "好像是没有可以外发的，到时候我看一下有什么渠道让您去学习一下看一下，'\n"
            "客户：'嗯，'\n"
            "坐席：'嗯好的好的，拜拜拜，'\n"
            "客户：'四分，'"
        )

        # K1: 客户原始请求的 tools 定义 —— Pydantic v2 自动生成的 JSON
        # Schema，parameters 中含 $defs 定义与 $ref 引用（【$$不兼容】问题
        # 的核心对象）
        K1_TOOLS_SUBMIT_D2_PRODUCT = [
            {
                "type": "function",
                "function": {
                    "name": "submit_d2_product",
                    "description": "提交产品与工作分类分析结果",
                    "parameters": {
                        "$defs": {
                            "ProductDetail": {
                                "additionalProperties": True,
                                "properties": {
                                    "customer_response": {
                                        "default": "",
                                        "title": "Customer Response",
                                        "type": "string",
                                    },
                                    "depth": {
                                        "default": "",
                                        "title": "Depth",
                                        "type": "string",
                                    },
                                    "evidence": {
                                        "default": "",
                                        "title": "Evidence",
                                        "type": "string",
                                    },
                                    "mention_type": {
                                        "default": "",
                                        "title": "Mention Type",
                                        "type": "string",
                                    },
                                    "outcome": {
                                        "default": "",
                                        "title": "Outcome",
                                        "type": "string",
                                    },
                                    "product": {
                                        "default": "",
                                        "title": "Product",
                                        "type": "string",
                                    },
                                },
                                "title": "ProductDetail",
                                "type": "object",
                            },
                            "SaleSignals": {
                                "additionalProperties": True,
                                "properties": {
                                    "has_signal": {
                                        "default": False,
                                        "title": "Has Signal",
                                        "type": "boolean",
                                    },
                                    "signal_strength": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}],
                                        "default": None,
                                        "title": "Signal Strength",
                                    },
                                    "signal_type": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}],
                                        "default": None,
                                        "title": "Signal Type",
                                    },
                                },
                                "title": "SaleSignals",
                                "type": "object",
                            },
                        },
                        "properties": {
                            "biz_scenario": {
                                "default": "",
                                "title": "Biz Scenario",
                                "type": "string",
                            },
                            "core_work_type": {
                                "title": "Core Work Type",
                                "type": "string",
                            },
                            "product_details": {
                                "items": {"$ref": "#/$defs/ProductDetail"},
                                "title": "Product Details",
                                "type": "array",
                            },
                            "product_tags": {
                                "items": {"type": "string"},
                                "title": "Product Tags",
                                "type": "array",
                            },
                            "sale_signals": {"$ref": "#/$defs/SaleSignals"},
                        },
                        "required": ["core_work_type"],
                        "title": "ProductSchema",
                        "type": "object",
                    },
                },
            }
        ]

        # K1: 客户原始请求的 tool_choice —— 强制调用 submit_d2_product
        K1_TOOL_CHOICE = {"type": "function", "function": {"name": "submit_d2_product"}}

        def collect_stream_tool_calls(
            result: Dict[str, Any],
        ) -> List[Dict[str, Any]]:
            """从流式 chunks 中聚合 tool_calls 增量片段

            OpenAI 流式协议中 tool_calls 以增量片段下发（按 index 分片，
            function.arguments 逐段追加），需按 index 聚合才是完整调用。
            """
            aggregated: Dict[int, Dict[str, Any]] = {}
            for chunk in result.get("chunks", []):
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {}) or {}
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    entry = aggregated.setdefault(
                        idx, {"id": None, "name": "", "arguments": ""}
                    )
                    if tc.get("id"):
                        entry["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        entry["name"] += fn["name"]
                    if fn.get("arguments"):
                        entry["arguments"] += fn["arguments"]
            return [aggregated[k] for k in sorted(aggregated)]

        test_logger.info(
            "=== 测试开始: 客户问题 - Pydantic $defs/$ref Schema 工具调用 ==="
        )

        messages = [
            {"role": "system", "content": K1_SYSTEM_PROMPT},
            {"role": "user", "content": K1_USER_PROMPT},
        ]
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "max_tokens": 4096,
                "temperature": 0.1,
                "thinking": {"type": "enabled"},
                "tools": "submit_d2_product ($defs/$ref schema)",
                "tool_choice": "forced submit_d2_product",
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        )

        # 按客户原始 curl 原样下发：thinking + stream + 强制 tool_choice +
        # Pydantic $defs/$ref Schema + stream_options.include_usage
        response_iter = api_client.chat_completion_stream(
            messages,
            temperature=0.1,
            max_tokens=4096,
            thinking={"type": "enabled"},
            tools=K1_TOOLS_SUBMIT_D2_PRODUCT,
            tool_choice=K1_TOOL_CHOICE,
            stream_options={"include_usage": True},
        )
        result = self.collect_stream_chunks(response_iter)
        tool_calls = collect_stream_tool_calls(result)

        self.log_full_response(
            test_logger,
            {
                "chunks_count": len(result["chunks"]),
                "content": result["content"][:2000],
                "reasoning": (
                    result["reasoning"][:2000] if result["reasoning"] else ""
                ),
                "tool_calls": tool_calls,
            },
            "K1-客户问题复现($defs/$ref Schema)",
        )

        # 核心验证：含 $defs/$ref Schema 的请求可被正常处理
        assert len(result["chunks"]) > 0, (
            "No streaming chunks received — 客户问题复现失败：服务端未能处理"
            "含 $defs/$ref Schema 的工具调用请求（原始报错【$$不兼容】）"
        )

        # 工具调用场景 finish_reason 应为 tool_calls；
        # 思考模型在 reasoning 耗尽 max_tokens 时可能为 length
        finish_reason = None
        for chunk in reversed(result["chunks"]):
            if chunk.get("choices"):
                finish_reason = chunk["choices"][0].get("finish_reason")
                break
        assert finish_reason in ("tool_calls", "stop", "eos", "ended", "length"), (
            f"finish_reason should be 'tool_calls' (or stop/eos/ended/length), "
            f"got '{finish_reason}'"
        )
        test_logger.info(f"finish_reason: {finish_reason}")

        # 强制 tool_choice 下必须返回指定的工具调用
        assert len(tool_calls) > 0, (
            "tool_choice 强制指定 submit_d2_product，"
            "但流式响应中未聚合到任何 tool_calls"
        )
        first_call = tool_calls[0]
        assert first_call["name"] == "submit_d2_product", (
            f"Expected forced tool 'submit_d2_product', got '{first_call['name']}'"
        )
        assert first_call.get("id"), "Tool call should have non-empty 'id'"

        # 工具参数必须是合法 JSON（流式增量聚合后）
        args_raw = first_call["arguments"]
        try:
            args = json.loads(args_raw) if args_raw.strip() else {}
        except json.JSONDecodeError as e:
            test_logger.error(
                f"工具调用 arguments 非法 JSON，原始 arguments: "
                f"{args_raw[:2000]!r}"
            )
            pytest.fail(
                f"Tool call arguments is not valid JSON: error: {e}"
                f"（原始 arguments 已记录于测试日志）"
            )

        # schema 必填项校验：required = ["core_work_type"]
        if "core_work_type" not in args:
            test_logger.error(
                f"工具调用 arguments 缺少必填项 core_work_type，完整 "
                f"arguments: {json.dumps(args, ensure_ascii=False)[:2000]}"
            )
        assert "core_work_type" in args, (
            "Tool arguments missing required field 'core_work_type' "
            "(args logged in test log)"
        )
        core_work_type = args["core_work_type"]
        assert (
            isinstance(core_work_type, str) and core_work_type.strip()
        ), f"'core_work_type' should be a non-empty string, got: {core_work_type!r}"

        # stream_options.include_usage 软校验：usage 缺失仅告警（部分部署不实现）
        usage = next(
            (c.get("usage") for c in reversed(result["chunks"]) if c.get("usage")),
            None,
        )
        if not usage:
            test_logger.warning(
                "stream_options.include_usage=true 但流式响应中未携带 usage，"
                "当前部署可能未实现该参数"
            )

        test_logger.info(
            f"客户问题复现通过: tool={first_call['name']}, "
            f"core_work_type={core_work_type}, "
            f"reasoning_len={len(result['reasoning'])}, "
            f"chunks={len(result['chunks'])}"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_repeated_request_stability(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K2 [P0]: 客户问题 - 同一请求循环执行5次返回信息异常

        客户循环执行同一 curl 命令（thinking+stream+logprobs+top_logprobs+n+
        frequency_penalty/presence_penalty+user 字段+X-Cache-Buster 防缓存头）
        5 次左右出现返回信息异常。本用例按客户原始 curl 原样复现并连续执行
        5 次（相邻请求间隔 3s），验证：
        - 每次请求均被服务端正常处理并返回流式 chunks
        - 每次 finish_reason 合法
        - 每次正式回答内容非空
        5 次全部正常才判定通过；任一次异常即失败，并报告第几次及异常详情。
        """
        # K2: 客户原始请求的 system 提示词（与 curl 完全一致）
        K2_SYSTEM_PROMPT = "无论什么问题，你每次回答都必须以“很高兴为您服务”开头"

        # K2: 客户原始请求的 user 消息（与 curl 完全一致）
        K2_USER_PROMPT = "介绍一下，RPG游戏，40字🤔"

        # K2: 客户原始请求的 user 字段——终端用户标识（与 curl 完全一致）
        K2_USER_ID = "a74685ef7268c396f0b842750bd7ab3252b37e7e3619ab33126946ee63d867e0"

        # K2: 循环执行次数（客户反馈"请求5次左右返回信息异常"）
        K2_REPEAT_TIMES = 5

        # K2: 相邻两次请求的间隔（秒）——第 1~4 次完成后间隔 3s 再发起下一次
        # （末次后不等待），模拟客户循环执行 curl 的节奏
        K2_REQUEST_INTERVAL_SECONDS = 3

        test_logger.info(
            "=== 测试开始: 客户问题 - 同一请求循环执行 %d 次返回信息异常 ==="
            % K2_REPEAT_TIMES
        )

        messages = [
            {"role": "system", "content": K2_SYSTEM_PROMPT},
            {"role": "user", "content": K2_USER_PROMPT},
        ]
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "max_tokens": 2048,
                "temperature": 1,
                "thinking": {"type": "enabled"},
                "logprobs": True,
                "top_logprobs": 4,
                "n": 1,
                "frequency_penalty": 0,
                "presence_penalty": 0,
                "top_p": 0.95,
                "user": K2_USER_ID,
                "stream": True,
                "stream_options": {"include_usage": True},
                "X-Cache-Buster": "每次迭代更新（$(date +%s)）",
            },
        )

        for i in range(1, K2_REPEAT_TIMES + 1):
            # 客户 curl 通过 -H "X-Cache-Buster: $(date +%s)" 防缓存，
            # 每次执行生成新值；此处同样在每次迭代前更新该请求头
            # （追加迭代序号保证 5 次快速执行间取值也唯一）
            api_client.session.headers["X-Cache-Buster"] = (
                f"{int(time.time())}_{i}"
            )

            # 按客户原始 curl 原样下发全部参数
            try:
                response_iter = api_client.chat_completion_stream(
                    messages,
                    temperature=1,
                    max_tokens=2048,
                    logprobs=True,
                    n=1,
                    thinking={"type": "enabled"},
                    user=K2_USER_ID,
                    frequency_penalty=0,
                    presence_penalty=0,
                    stream_options={"include_usage": True},
                    top_logprobs=4,
                    top_p=0.95,
                )
                result = self.collect_stream_chunks(response_iter)
            except Exception as e:
                pytest.fail(
                    f"第 {i}/{K2_REPEAT_TIMES} 次请求异常"
                    f"——客户问题复现失败：{e}"
                )

            # 响应正常：流式 chunks 非空（HTTP 非 200 时 chat_completion_stream
            # 已直接抛异常，走到这里说明请求本身成功）
            assert len(result["chunks"]) > 0, (
                f"第 {i}/{K2_REPEAT_TIMES} 次请求未返回任何 SSE chunk"
                "——客户问题复现失败：循环执行出现返回信息异常"
            )

            # 响应正常：finish_reason 合法
            finish_reason = None
            for chunk in reversed(result["chunks"]):
                if chunk.get("choices"):
                    finish_reason = chunk["choices"][0].get("finish_reason")
                    break
            assert finish_reason in ("tool_calls", "stop", "eos", "ended", "length"), (
                f"第 {i}/{K2_REPEAT_TIMES} 次请求 finish_reason 异常: "
                f"'{finish_reason}'"
            )

            # 内容正常：正式回答非空
            content = result["content"].strip()
            assert content, (
                f"第 {i}/{K2_REPEAT_TIMES} 次请求返回内容为空"
                "——客户问题复现失败：循环执行出现返回信息异常"
            )

            # 软观察（不判失败）：system prompt 要求每次回答以
            # "很高兴为您服务"开头，偏离时记录告警供问题定位
            if not content.startswith("很高兴为您服务"):
                test_logger.warning(
                    f"第 {i}/{K2_REPEAT_TIMES} 次回答未以'很高兴为您服务'开头"
                    f"（system prompt 要求）: {content[:80]}"
                )

            # 软观察：stream_options.include_usage 的 usage 返回
            usage = next(
                (c.get("usage") for c in reversed(result["chunks"]) if c.get("usage")),
                None,
            )
            if not usage:
                test_logger.warning(
                    f"第 {i}/{K2_REPEAT_TIMES} 次请求 stream_options.include_usage=true "
                    "但流式响应中未携带 usage"
                )

            test_logger.info(
                f"第 {i}/{K2_REPEAT_TIMES} 次正常: finish_reason={finish_reason}, "
                f"content={content[:60]}, "
                f"reasoning_len={len(result['reasoning'])}, "
                f"chunks={len(result['chunks'])}, usage={'有' if usage else '无'}"
            )

            # 相邻请求间隔（末次后不等待）
            if i < K2_REPEAT_TIMES:
                time.sleep(K2_REQUEST_INTERVAL_SECONDS)

        test_logger.info(
            f"客户问题复现通过: 同一请求连续执行 {K2_REPEAT_TIMES} 次，"
            "响应与内容均正常"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM52
    @pytest.mark.p0
    def test_anthropic_prompt_cache_creation(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K3 [P0]: 客户问题 - Anthropic 协议请求 cache_creation_tokens 一直为 0

        客户通过 Anthropic 协议（/anthropic/v1/messages，stream=true）发送带
        prompt cache 的请求，服务端日志 anthropic cache stats 中
        cache_creation_tokens 一直为 0（同时 cache_read_tokens 有值），
        说明 cache_control 断点未被落实。本用例构造带 cache_control 断点的
        唯一长前缀（约 11 万 tokens，对齐客户 prompt_tokens=111283 的场景
        规模，同时远超 Anthropic 协议最小可缓存长度），连续发送两次请求：
        - 第 1 次（唯一新前缀）：cache_creation_input_tokens > 0（创建缓存）
        - 第 2 次（相同前缀）：cache_read_input_tokens > 0（命中缓存）
        字段名兼容 Anthropic 协议（cache_creation_input_tokens）与客户日志
        网关内部名（cache_creation_tokens）两种拼写。
        """
        # K3: Anthropic 协议版本头。2023-06-01 为长期 GA 版本（2023.6 起两年
        # 多内唯一主流版本，第三方兼容网关的事实标准）；官方 SDK v2.1.0+ 已
        # 升到 2026-10-21，但被测对象为客户的 Anthropic 兼容网关（非官方
        # API），新版本日期更可能被网关版本校验拒绝，故沿用兼容面最广的
        # 2023-06-01。Anthropic 版本头用于钉住协议行为，老版本不会过期失效；
        # K3 依赖的 prompt caching（cache_control）在 2023-06-01 上即为 GA。
        # 若目标网关升级要求新版本，改此常量即可。
        K3_ANTHROPIC_VERSION = "2023-06-01"

        # K3: 输出 token 上限——缓存断言只关心 input 侧 usage，输出无需过长
        K3_MAX_TOKENS = 512

        # K3: 可缓存前缀的填充文本。客户问题的 prompt_tokens=111283（超长
        # 上下文触发 prompt cache），按中文 ~1.3-1.7 字符/token 保守折算，
        # 需约 19 万字符才能保证达到 11 万 tokens 量级（同时远超 Anthropic
        # 协议最小可缓存长度 1024 tokens）。规模对齐客户场景的原因：若缺陷
        # 为规模相关（仅超长前缀的 cache_control 不落实），过短的测试前缀
        # 将无法复现。
        K3_PREFIX_FILLER_UNIT = (
            "本知识库涵盖产品规格、接口说明、计费策略、常见问题与处理流程，"
            "供客服助手检索引用。"
        )
        K3_PREFIX_TARGET_CHARS = 190000
        K3_PREFIX_FILLER = K3_PREFIX_FILLER_UNIT * (
            K3_PREFIX_TARGET_CHARS // len(K3_PREFIX_FILLER_UNIT) + 1
        )

        # K3: 超长前缀（~11 万 tokens）的 prefill 耗时显著，参考 D 类用例的
        # 超时保护模式，保证单次请求超时下限
        K3_MIN_REQUEST_TIMEOUT = 1200

        # K3: 用户消息（缓存断言不依赖回答内容）
        K3_USER_MESSAGE = "请回复：收到。"

        def anthropic_stream_request(
            payload: Dict[str, Any], label: str
        ) -> Dict[str, Any]:
            """通过 Anthropic 协议发送流式请求并解析 SSE，返回合并后的 usage

            端点为 {base_url}/anthropic/v1/messages（与客户网关布局一致），
            鉴权使用 x-api-key 头 + anthropic-version 协议头。
            usage 提取自 message_start（message.usage）与 message_delta
            （usage），后者覆盖前者（累计值）。
            """
            url = f"{api_client.base_url}/anthropic/v1/messages"
            headers = {"anthropic-version": K3_ANTHROPIC_VERSION}
            if api_client.api_key:
                headers["x-api-key"] = api_client.api_key
            try:
                response = api_client.session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=api_client.timeout,
                    stream=True,
                )
            except Exception as e:
                pytest.fail(f"{label} 发送失败（{url}）: {e}")

            if response.status_code != 200:
                pytest.fail(
                    f"{label} 请求失败 HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

            usage: Dict[str, Any] = {}
            events = 0
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                events += 1
                evt_usage = None
                if event.get("type") == "message_start":
                    evt_usage = (event.get("message") or {}).get("usage")
                elif event.get("type") == "message_delta":
                    evt_usage = event.get("usage")
                if evt_usage:
                    usage.update(evt_usage)
            if events == 0:
                pytest.fail(f"{label} 未返回任何 SSE 事件（{url}）")
            test_logger.info(f"{label} usage: {usage}")
            return usage

        def cache_usage_field(usage: Dict[str, Any], *names: str) -> int:
            """从 usage 中取缓存计数值，兼容协议字段名与网关内部字段名两种拼写"""
            for name in names:
                value = usage.get(name)
                if isinstance(value, (int, float)) and value > 0:
                    return int(value)
            return 0

        test_logger.info(
            "=== 测试开始: 客户问题 - Anthropic 协议 prompt cache 未创建 ==="
        )

        # 唯一批次号置于前缀最前：保证本次运行不会命中历史运行遗留的缓存
        run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        prefix_text = f"文档批次编号：{run_id}\n" + K3_PREFIX_FILLER

        # 超长前缀（~11 万 tokens）prefill 耗时显著，参考 D 类用例的
        # 超时保护模式：保证单次请求超时下限（配置已 >= 该值时为 no-op）
        original_timeout = api_client.timeout
        api_client.timeout = max(original_timeout, K3_MIN_REQUEST_TIMEOUT)
        try:
            payload = {
                "model": api_client.model_name,
                "max_tokens": K3_MAX_TOKENS,
                "system": [
                    {
                        "type": "text",
                        "text": prefix_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "messages": [{"role": "user", "content": K3_USER_MESSAGE}],
                "stream": True,
            }

            TestLogger.log_request(
                test_logger,
                [
                    {
                        "role": "system",
                        "content": (
                            f"[可缓存长前缀 {len(prefix_text)} 字符，批次 {run_id}]"
                        ),
                    },
                    {"role": "user", "content": K3_USER_MESSAGE},
                ],
                {
                    "protocol": "anthropic (/anthropic/v1/messages)",
                    "anthropic-version": K3_ANTHROPIC_VERSION,
                    "max_tokens": K3_MAX_TOKENS,
                    "stream": True,
                    "cache_control": "ephemeral（system 前缀断点）",
                },
            )

            # 第 1 次请求：唯一新前缀，期望触发缓存创建
            usage1 = anthropic_stream_request(payload, "第 1 次请求（唯一前缀）")
            creation1 = cache_usage_field(
                usage1, "cache_creation_input_tokens", "cache_creation_tokens"
            )
            read1 = cache_usage_field(
                usage1, "cache_read_input_tokens", "cache_read_tokens"
            )
            input1 = usage1.get("input_tokens", 0)
            test_logger.info(
                f"第 1 次请求（唯一前缀）: input_tokens={input1}, "
                f"cache_creation={creation1}, cache_read={read1}"
            )
            if input1 and input1 < 1024:
                test_logger.warning(
                    f"input_tokens={input1} 低于 Anthropic 协议最小可缓存长度"
                    "（1024 tokens），cache_creation 为 0 可能是前缀过短所致，"
                    "请加大 K3_PREFIX_TARGET_CHARS"
                )
            elif input1 and input1 < 100000:
                test_logger.info(
                    f"input_tokens={input1} 低于客户场景规模（111283），"
                    "如疑似规模相关问题请加大 K3_PREFIX_TARGET_CHARS"
                )

            # 第 2 次请求：相同前缀，期望命中缓存
            usage2 = anthropic_stream_request(payload, "第 2 次请求（相同前缀）")
            creation2 = cache_usage_field(
                usage2, "cache_creation_input_tokens", "cache_creation_tokens"
            )
            read2 = cache_usage_field(
                usage2, "cache_read_input_tokens", "cache_read_tokens"
            )
            test_logger.info(
                f"第 2 次请求（相同前缀）: cache_creation={creation2}, "
                f"cache_read={read2}"
            )

            # 核心断言 1：携带 cache_control 断点的新前缀必须创建缓存
            # （客户问题：cache_creation_tokens 一直为 0，未创建缓存）
            assert creation1 > 0, (
                f"客户问题复现失败：携带 cache_control 断点的新前缀请求 "
                f"cache_creation_tokens={creation1}（一直为 0，未创建缓存）。"
                f"input_tokens={input1}, usage={usage1}"
            )

            # 核心断言 2：相同前缀的第 2 次请求必须命中缓存
            assert read2 > 0, (
                f"相同前缀第 2 次请求未命中缓存: cache_read_tokens={read2}"
                f"（第 1 次已创建 {creation1}）, usage={usage2}"
            )

            test_logger.info(
                f"客户问题复现通过: 第 1 次创建 {creation1} tokens, "
                f"第 2 次命中 {read2} tokens"
            )
        finally:
            api_client.timeout = original_timeout

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_negative_frequency_penalty_treated_as_zero(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K4 [P0]: 客户问题 - frequency_penalty=-2 且不传 max_tokens 请求一直无返回

        客户问题：frequency_penalty=-2（OpenAI 规范 [-2,2] 的合法极值）且
        不传 max_tokens 时请求一直没有返回。机理：fp<0 按出现次数奖励已
        出现 token，形成无饱和正反馈，循环 token 的 logit 持续增长压制
        EOS，自然终止失效；输出上限=剩余上下文（可能十余万 tokens），
        生成耗时远超网关/客户端超时，观感即"一直没有返回"。
        平台修复契约：frequency_penalty<0 时按 0 处理（防御性钳制）。
        因此本用例输入保持客户原值 -2、不传 max_tokens，连发 3 次
        （消息各异、相邻间隔 3s——仅一次调用可能无法严谨验证问题），
        断言每次都按 fp=0 的预期结果：
        - 单次响应时间预算内返回（超预算无响应 = 客户问题复现）
        - finish_reason 为自然结束（stop/eos/ended，而非跑满上限的 length）
        - 回答内容非空
        3 次全部正常结束才判定通过；任一次异常即失败，并报告第几次。
        本用例不进 smoke 集：未修复时最坏耗时约
        3×K4_RESPONSE_BUDGET_SECONDS，避免拖慢冒烟套件
        （决策记录见 docs/test_k_customer_issue.md）。
        """
        # K4: 客户原始请求的 frequency_penalty 取值——OpenAI 规范允许
        # [-2, 2]，-2 为合法极值。fp<0 按出现次数奖励已出现 token（正
        # 反馈），是"放大重复"的文档化数学行为；客户问题出在不传
        # max_tokens 时无界生成无法终止。
        K4_FREQUENCY_PENALTY = -2

        # K4: 3 个不同的用户提示词（客户原始 prompt 未提供）。连发 3 次、
        # 消息各异：单次调用可能无法严谨验证——钳制若未生效，单次请求
        # 也可能侥幸自然结束；不同消息降低偶然性，未钳制的退化重复更
        # 难在不同 prompt 下全部侥幸通过
        K4_USER_PROMPTS = (
            "请用一段话介绍大语言模型的工作原理。",
            "请简要说明云计算能给企业带来的核心价值。",
            "请列举两种常见的排序算法，并各用一句话说明其特点。",
        )

        # K4: 相邻两次请求的间隔（秒）——第 1、2 次完成后间隔 3s 再发起
        # 下一次（末次后不等待），3 次总计额外约 6s
        K4_REQUEST_INTERVAL_SECONDS = 3

        # K4: 单次请求的响应时间预算（秒），按请求独立生效（3 次共享同一
        # 预算客户端，timeout 在每次请求上生效）。平台修复契约为 fp<0 按
        # 0 处理，修复后每次请求与普通请求无异、数秒内即应返回；未修复
        # 时退化重复会一直生成到上下文上限，远超任何网关/客户端超时。
        # 预算即挂起检测护栏：超预算无响应 = 客户问题复现。取 120s：
        # 远大于正常请求耗时，又控制在单用例可承受范围（3 次最坏 360s）。
        K4_RESPONSE_BUDGET_SECONDS = 120

        # K4: 修复契约下的自然结束原因——未传 max_tokens，正常生成应自然
        # 停止；length 表示生成跑满输出上限（=剩余上下文），即退化重复
        # 未被钳制的特征
        K4_NATURAL_FINISH_REASONS = ("stop", "eos", "ended")

        test_logger.info(
            "=== 测试开始: 客户问题 - frequency_penalty=-2 不传 max_tokens 无返回"
            f"（连发 {len(K4_USER_PROMPTS)} 次，消息各异）==="
        )

        # 专用预算客户端（E8 先例）：短超时 + retry_times=0，保证未修复时
        # 单次最坏耗时 = 单次预算而非预算×(重试+1)；构造时只透传鉴权与
        # 模型，不携带全局采样参数，保持客户原始参数面
        budget_client = ModelAPIClient(
            api_key=api_client.api_key,
            base_url=api_client.api_prefix,
            model_name=api_client.model_name,
            timeout=K4_RESPONSE_BUDGET_SECONDS,
            config=api_client.config,
            retry_times=0,
        )
        url = f"{budget_client.api_prefix}/chat/completions"

        def run_request(index: int, prompt: str) -> None:
            """K4 单次请求核心逻辑：fp=-2、不传 max_tokens，按 fp=0 预期断言

            任一步失败即判失败并报告第 {index}/{len(K4_USER_PROMPTS)} 次。
            """
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "frequency_penalty": K4_FREQUENCY_PENALTY,
                    "max_tokens": "未传（客户原始请求）",
                    "stream": False,
                    "request": f"第 {index}/{len(K4_USER_PROMPTS)} 次（消息各异）",
                },
            )

            # 客户请求形态：仅 model/messages/frequency_penalty，不带
            # max_tokens。chat_completion 封装会固定附带默认 max_tokens=2048（无法省略），破坏"不传 max_tokens"的前提，故按 K3 先例
            # 手工构造 payload 直发
            payload = {
                "model": budget_client.model_name,
                "messages": messages,
                "frequency_penalty": K4_FREQUENCY_PENALTY,
                "stream": False,
            }

            started = time.time()
            try:
                response = budget_client._post_with_retry(url, payload, stream=False)
            except requests.exceptions.Timeout as e:
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次请求客户问题复现失败："
                    f"frequency_penalty={K4_FREQUENCY_PENALTY} 且未传 max_tokens，"
                    f"{K4_RESPONSE_BUDGET_SECONDS}s 内无任何响应（fp<0 未按 0 处理，"
                    f"退化重复导致无界生成），耗时 {time.time() - started:.1f}s: {e}"
                )
            except Exception as e:
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次请求发送异常（{url}）: {e}"
                )
            elapsed = time.time() - started

            if response.status_code != 200:
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次请求失败 "
                    f"HTTP {response.status_code}: {response.text[:500]}"
                )

            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                test_logger.error(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次真实响应体: "
                    f"{response.text[:2000]!r}"
                )
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )

            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"第 {index}/{len(K4_USER_PROMPTS)} 次响应缺少 choices: "
                f"{list(result.keys())}"
            )
            choice = choices[0]
            message = choice.get("message") or {}
            content = (message.get("content") or "").strip()
            finish_reason = choice.get("finish_reason")

            # 核心断言 1：修复契约（fp<0 按 0 处理）下应自然结束——未传
            # max_tokens，正常生成自然停止；length 表示生成跑满输出上限
            # （=剩余上下文），即退化重复未被钳制的特征
            assert finish_reason in K4_NATURAL_FINISH_REASONS, (
                f"第 {index}/{len(K4_USER_PROMPTS)} 次客户问题复现失败："
                f"frequency_penalty={K4_FREQUENCY_PENALTY} 应按 0 处理（防御性"
                f"钳制），但 finish_reason='{finish_reason}'（期望自然结束 "
                f"{K4_NATURAL_FINISH_REASONS}；length 表示生成跑满输出上限，"
                f"即退化重复未被钳制），耗时 {elapsed:.1f}s，消息: {prompt[:30]}"
            )

            # 核心断言 2：回答内容非空
            assert content, (
                f"第 {index}/{len(K4_USER_PROMPTS)} 次客户问题复现失败："
                f"返回内容为空，finish_reason={finish_reason}，"
                f"耗时 {elapsed:.1f}s，消息: {prompt[:30]}"
            )

            # 软观察：耗时超过单次预算一半时告警（修复后正常应数秒内返回）
            if elapsed > K4_RESPONSE_BUDGET_SECONDS / 2:
                test_logger.warning(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次请求耗时 {elapsed:.1f}s，"
                    f"超过预算 {K4_RESPONSE_BUDGET_SECONDS}s 的一半（修复后正常应"
                    f"数秒内返回），请关注服务负载"
                )

            TestLogger.log_response(
                test_logger, result, f"K4-响应（第 {index} 次）"
            )
            test_logger.info(
                f"第 {index}/{len(K4_USER_PROMPTS)} 次正常（fp="
                f"{K4_FREQUENCY_PENALTY} 按 0 处理）: finish_reason={finish_reason}, "
                f"completion_tokens="
                f"{(result.get('usage') or {}).get('completion_tokens')}, "
                f"耗时 {elapsed:.1f}s, 消息: {prompt[:30]}"
            )

        try:
            for i, prompt in enumerate(K4_USER_PROMPTS, start=1):
                run_request(i, prompt)
                # 相邻请求间隔（末次后不等待）
                if i < len(K4_USER_PROMPTS):
                    time.sleep(K4_REQUEST_INTERVAL_SECONDS)
        finally:
            budget_client.close()

        test_logger.info(
            "客户问题复现通过: frequency_penalty=-2 已按 0 处理，未传 "
            f"max_tokens 连发 {len(K4_USER_PROMPTS)} 次（消息各异）"
            "均正常返回并自然结束"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.KimiK3
    @pytest.mark.p0
    def test_thinking_disabled_suppresses_reasoning(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K5 [P0]: 客户问题 - thinking.type=disabled 后思考未关闭

        客户问题：thinking.type=disabled 后 reasoning_tokens 仍=100/75、
        reasoning_content 照常输出，关思考相关功能（低延迟模式、关思考
        温度档）全部失效。官方端点实测（官方 FAQ 与实测不符，以实测
        为准）：disabled 后思考完全关闭——reasoning_tokens 为空、无
        reasoning_content、正文正常返回；客户网关对 disabled 不响应
        （rt 仍>0），与官方实测不一致。
        本用例输入保持客户原值 thinking={"type": "disabled"}、显式
        temperature=0.6（官方关思考档唯一合法温度，契约见 K6；不传
        max_tokens），连发 3 次（消息各异、相邻间隔 3s），断言每次均
        按官方实测预期：
        - 无思考内容（reasoning_content/reasoning 均为空）
        - reasoning_tokens 为空（0/缺失；兼容 usage.reasoning_tokens 与
          completion_tokens_details.reasoning_tokens 两种拼写）
        - 正文正常返回且 finish_reason 自然结束
        任一次不符合即失败，并报告第几次。
        """
        # K5: 客户原始请求的思考开关参数——thinking.type=disabled（与 K1
        # 的 enabled 为同一参数面）。官方端点实测（官方 FAQ 与实测不符，
        # 以实测为准）：disabled 后思考完全关闭——reasoning_tokens 为空
        # （0/缺失）、无 reasoning_content、正文正常返回。客户网关对
        # disabled 不响应（reasoning_tokens 仍 >0、reasoning_content 照常
        # 输出）。
        K5_THINKING_DISABLED = {"type": "disabled"}

        # K5: 官方关思考档唯一合法温度——disabled 下给 1 或 0 会被 400
        # 拒绝（"only 0.6 is allowed for this model in non-thinking mode"，
        # 官方契约见 K6），显式指定 0.6 与官方关思考用法对齐
        K5_TEMPERATURE = 0.6

        # K5: 3 个不同的用户提示词（客户原始 prompt 未提供；消息各异 +
        # 3s 间隔，沿用 K4 模式：3 次全部符合官方实测预期才通过，任一次
        # 失败报告第几次）
        K5_USER_PROMPTS = (
            "请用一句话解释什么是通货膨胀。",
            "请把'今天天气很好'翻译成英文。",
            "请列出三种常见的颜色，用顿号分隔。",
        )

        # K5: 相邻两次请求的间隔（秒）——第 1、2 次完成后间隔 3s 再发起
        # 下一次（末次后不等待）
        K5_REQUEST_INTERVAL_SECONDS = 3

        # K5: 官方实测预期下的自然结束原因（未传 max_tokens，正常生成
        # 自然停止）
        K5_NATURAL_FINISH_REASONS = ("stop", "eos", "ended")

        test_logger.info(
            "=== 测试开始: 客户问题 - thinking.type=disabled 后思考未关闭"
            f"（连发 {len(K5_USER_PROMPTS)} 次，消息各异）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def run_request(index: int, prompt: str) -> None:
            """K5 单次请求核心逻辑：thinking.type=disabled，按官方实测预期断言

            任一步失败即判失败并报告第 {index}/{len(K5_USER_PROMPTS)} 次。
            """
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "thinking": "disabled（客户原始请求参数）",
                    "temperature": "0.6（官方关思考档唯一合法温度）",
                    "max_tokens": "未传（客户原始请求）",
                    "stream": False,
                    "request": f"第 {index}/{len(K5_USER_PROMPTS)} 次（消息各异）",
                },
            )

            # 客户请求形态：model/messages/thinking(disabled)/temperature=0.6，
            # 不带 max_tokens。手工构造 payload 直发（K3/K4 先例），保持客户
            # 原始参数面
            payload = {
                "model": api_client.model_name,
                "messages": messages,
                "thinking": K5_THINKING_DISABLED,
                "temperature": K5_TEMPERATURE,
                "stream": False,
            }

            started = time.time()
            try:
                response = api_client._post_with_retry(url, payload, stream=False)
            except Exception as e:
                pytest.fail(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次请求发送异常"
                    f"（{url}）: {e}"
                )
            elapsed = time.time() - started

            if response.status_code != 200:
                pytest.fail(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次请求失败 "
                    f"HTTP {response.status_code}: {response.text[:500]}"
                )

            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                test_logger.error(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次真实响应体: "
                    f"{response.text[:2000]!r}"
                )
                pytest.fail(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )

            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次响应缺少 choices: "
                f"{list(result.keys())}"
            )
            choice = choices[0]
            message = choice.get("message") or {}
            content = (message.get("content") or "").strip()
            finish_reason = choice.get("finish_reason")
            usage = result.get("usage") or {}

            # 思考内容字段名兼容：reasoning_content（Kimi/Zhipu/DeepSeek
            # 风格）与 reasoning（部分网关）
            reasoning_text = ""
            for field in ("reasoning_content", "reasoning"):
                value = message.get(field)
                if isinstance(value, str):
                    reasoning_text += value

            # reasoning_tokens 字段名兼容：usage.reasoning_tokens（Kimi/
            # Zhipu 风格）与 usage.completion_tokens_details.reasoning_tokens
            # （OpenAI 风格）
            details = usage.get("completion_tokens_details") or {}
            reasoning_tokens = 0
            for value in (
                usage.get("reasoning_tokens"),
                details.get("reasoning_tokens"),
            ):
                if isinstance(value, (int, float)) and value > 0:
                    reasoning_tokens = int(value)
                    break

            # 核心断言 1：官方实测——disabled 后无思考内容
            if reasoning_text.strip():
                test_logger.error(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次思考内容"
                    f"（reasoning_content 全文）: {reasoning_text[:2000]!r}"
                )
            assert not reasoning_text.strip(), (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"thinking.type=disabled 后仍返回思考内容（官方实测应无 "
                f"reasoning_content），思考内容长度 {len(reasoning_text)}，"
                f"消息: {prompt[:30]}"
            )

            # 核心断言 2：官方实测——reasoning_tokens 为空（0/缺失）
            assert reasoning_tokens == 0, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"thinking.type=disabled 后 reasoning_tokens={reasoning_tokens}"
                f"（官方实测应为空/0），消息: {prompt[:30]}"
            )

            # 核心断言 3：官方实测——正文正常返回
            assert content, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"thinking.type=disabled 后返回正文为空（官方实测正文应正常"
                f"返回），finish_reason={finish_reason}，消息: {prompt[:30]}"
            )

            # 核心断言 4：自然结束（未传 max_tokens）
            assert finish_reason in K5_NATURAL_FINISH_REASONS, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"finish_reason='{finish_reason}'（期望自然结束 "
                f"{K5_NATURAL_FINISH_REASONS}），消息: {prompt[:30]}"
            )

            # 软观察：usage 缺失时告警（无法观测 reasoning_tokens）
            if not usage:
                test_logger.warning(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次响应未携带 usage，"
                    "无法观测 reasoning_tokens（缺失视为'为空'）"
                )

            TestLogger.log_response(
                test_logger, result, f"K5-响应（第 {index} 次）"
            )
            test_logger.info(
                f"第 {index}/{len(K5_USER_PROMPTS)} 次正常（thinking 已关闭）: "
                f"finish_reason={finish_reason}, reasoning_tokens="
                f"{reasoning_tokens}, 思考内容长度={len(reasoning_text)}, "
                f"completion_tokens={usage.get('completion_tokens')}, "
                f"耗时 {elapsed:.1f}s, 消息: {prompt[:30]}"
            )

        for i, prompt in enumerate(K5_USER_PROMPTS, start=1):
            run_request(i, prompt)
            # 相邻请求间隔（末次后不等待）
            if i < len(K5_USER_PROMPTS):
                time.sleep(K5_REQUEST_INTERVAL_SECONDS)

        test_logger.info(
            "客户问题复现通过: thinking.type=disabled 已生效，连发 "
            f"{len(K5_USER_PROMPTS)} 次（消息各异）均无思考内容、"
            "reasoning_tokens 为空、正文正常返回"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.KimiK3
    @pytest.mark.p0
    def test_thinking_temperature_tier(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K6 [P0]: 客户问题 - 关思考温度档未联动校验

        官方契约（kimi-k3 官方说明）：thinking 模式与 temperature 档位
        联动校验——
        - disabled + temperature=0.6：合法，200 正常返回
        - disabled + temperature=1 或 0：非法，400 拒绝并报
          "only 0.6 is allowed for this model in non-thinking mode"
        - enabled + temperature=1：合法，200 正常返回
        - enabled + temperature=0.6 或 0：非法，400 拒绝并报
          "only 1 is allowed for this model in thinking mode"
        客户影响：关思考相关功能（低延迟模式、关思考温度档）全部失效
        （K5 验证关思考本身，本用例验证温度档联动校验）。
        本用例对 6 个组合各发一次请求（参数校验为确定性行为，无需
        K4/K5 式多次连发），断言：
        - 合法组合：HTTP 200 + 正文非空
        - 非法组合：HTTP 400 + 错误信息包含官方文案（忽略大小写子串
          匹配，对错误体的 JSON 结构不敏感）
        任一组合不符合即失败，并报告具体场景。
        """
        # K6: 客户原始 user 提示词——6 个场景复用同一提示词，仅 thinking
        # 与 temperature 参数变化（参数联动校验与 prompt 内容无关，同一
        # prompt 使各场景唯一变量为被测参数）
        K6_USER_PROMPT = "请用一句话介绍你自己。"

        # K6: 关思考温度档——官方契约（kimi-k3 官方说明）：thinking 模式
        # 与 temperature 档位联动校验，合法组合 200 正常返回，非法组合
        # 400 拒绝并报对应错误信息：
        # - disabled + temperature=0.6：合法（关思考档唯一合法温度）
        # - disabled + temperature=1 或 0：400
        #   "only 0.6 is allowed for this model in non-thinking mode"
        # - enabled + temperature=1：合法（开思考档唯一合法温度）
        # - enabled + temperature=0.6 或 0：400
        #   "only 1 is allowed for this model in thinking mode"
        K6_SCENARIOS = (
            {
                "label": "disabled+temp=0.6（合法）",
                "thinking": {"type": "disabled"},
                "temperature": 0.6,
                "expect_ok": True,
                "error_substring": None,
            },
            {
                "label": "disabled+temp=1（非法）",
                "thinking": {"type": "disabled"},
                "temperature": 1,
                "expect_ok": False,
                "error_substring": (
                    "only 0.6 is allowed for this model in non-thinking mode"
                ),
            },
            {
                "label": "disabled+temp=0（非法）",
                "thinking": {"type": "disabled"},
                "temperature": 0,
                "expect_ok": False,
                "error_substring": (
                    "only 0.6 is allowed for this model in non-thinking mode"
                ),
            },
            {
                "label": "enabled+temp=1（合法）",
                "thinking": {"type": "enabled"},
                "temperature": 1,
                "expect_ok": True,
                "error_substring": None,
            },
            {
                "label": "enabled+temp=0.6（非法）",
                "thinking": {"type": "enabled"},
                "temperature": 0.6,
                "expect_ok": False,
                "error_substring": (
                    "only 1 is allowed for this model in thinking mode"
                ),
            },
            {
                "label": "enabled+temp=0（非法）",
                "thinking": {"type": "enabled"},
                "temperature": 0,
                "expect_ok": False,
                "error_substring": (
                    "only 1 is allowed for this model in thinking mode"
                ),
            },
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - 关思考温度档未联动校验"
            f"（{len(K6_SCENARIOS)} 个组合）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def run_scenario(scenario: Dict[str, Any]) -> None:
            """K6 单场景核心逻辑：thinking 模式 × temperature 档位联动校验

            合法组合断言 200+正文非空；非法组合断言 400+官方错误文案。
            """
            label = scenario["label"]
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K6_USER_PROMPT}],
                {
                    "thinking": scenario["thinking"]["type"],
                    "temperature": scenario["temperature"],
                    "max_tokens": "未传（契约校验与生成长度无关）",
                    "stream": False,
                    "scenario": label,
                },
            )

            # 官方契约校验场景：thinking 与 temperature 为被测参数，其余
            # 保持最小参数面（手工构造 payload 直发，K3/K4/K5 先例）
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": K6_USER_PROMPT}],
                "thinking": scenario["thinking"],
                "temperature": scenario["temperature"],
                "stream": False,
            }

            try:
                response = api_client._post_with_retry(url, payload, stream=False)
            except Exception as e:
                pytest.fail(f"场景[{label}] 请求发送异常（{url}）: {e}")

            if scenario["expect_ok"]:
                # 合法组合：官方契约应 200 正常返回
                assert response.status_code == 200, (
                    f"场景[{label}] 客户问题复现失败：官方契约为合法组合，"
                    f"应 200 正常返回，实际 HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )
                try:
                    result = response.json()
                except (json.JSONDecodeError, ValueError) as e:
                    test_logger.error(
                        f"场景[{label}] 真实响应体: "
                        f"{response.text[:2000]!r}"
                    )
                    pytest.fail(
                        f"场景[{label}] 响应不是合法 JSON: {e}. "
                        f"响应体已记录于测试日志"
                    )
                choices = result.get("choices") or []
                if not choices:
                    test_logger.error(
                        f"场景[{label}] 真实响应体: "
                        f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                    )
                assert choices, (
                    f"场景[{label}] 响应缺少 choices: {list(result.keys())}"
                )
                content = (
                    (choices[0].get("message") or {}).get("content") or ""
                ).strip()
                # 合法组合应正常生成正文（enabled 场景可能含
                # reasoning_content，属正常思考输出，不在本用例断言范围
                # ——关思考本身由 K5 验证）
                if not content:
                    test_logger.error(
                        f"场景[{label}] 真实响应体: "
                        f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                    )
                assert content, (
                    f"场景[{label}] 客户问题复现失败：合法组合应正常返回正文，"
                    f"实际正文为空"
                )
                TestLogger.log_response(
                    test_logger, result, f"K6-响应（{label}）"
                )
                test_logger.info(
                    f"场景[{label}] 正常: HTTP 200, 正文长度 {len(content)}, "
                    f"completion_tokens="
                    f"{(result.get('usage') or {}).get('completion_tokens')}"
                )
            else:
                # 非法组合：官方契约应 400 拒绝并报对应文案
                expected_msg = scenario["error_substring"]
                if response.status_code != 400:
                    test_logger.error(
                        f"场景[{label}] 真实响应体: "
                        f"{response.text[:2000]!r}"
                    )
                assert response.status_code == 400, (
                    f"场景[{label}] 客户问题复现失败：官方契约应 400 拒绝"
                    f"（错误信息含 '{expected_msg}'），实际 HTTP "
                    f"{response.status_code}（响应体已记录于测试日志）"
                )
                # 错误文案校验：忽略大小写的子串匹配（对错误体的 JSON 结构
                # 不敏感——官方文案可能嵌在 error.message 等不同位置）
                assert expected_msg.lower() in response.text.lower(), (
                    f"场景[{label}] 客户问题复现失败：400 错误信息与官方不一致，"
                    f"期望包含 '{expected_msg}'，实际: {response.text[:300]}"
                )
                test_logger.info(
                    f"场景[{label}] 正常拒绝: HTTP 400, 错误信息含官方文案 "
                    f"'{expected_msg}'"
                )

        for scenario in K6_SCENARIOS:
            run_scenario(scenario)

        test_logger.info(
            "客户问题复现通过: thinking 模式与温度档联动校验与官方契约一致"
            f"（{len(K6_SCENARIOS)} 个组合全部符合）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.KimiK3
    @pytest.mark.p0
    def test_thinking_effort_reasoning_length(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """K7 [P0]: 客户问题 - 思考强度档位思考长度倒挂（官方 reasoning_effort）

        官方契约（kimi-k3 官方文档 use-reasoning-effort /
        kimi-k3-quickstart）：思考强度为顶层 reasoning_effort 参数
        （K2.x 的 thinking 配置在 K3 已废弃，官方迁移指引为移除
        thinking 改用顶层 reasoning_effort），K3 恒开思考；官方预期
        思考长度（reasoning_tokens）随档位递增。
        本用例只按官方格式传参（顶层 reasoning_effort，无回退），
        请求顺序（客户指定）：low → high → max 后比对思考长度，
        再按 max → high → low 逆向重发并再次比对思考长度——正逆
        两轮排除请求顺序相关干扰（缓存/预热），均按 low < high <
        max 三档软对比（medium 不参与对比）；最后依次验证 medium
        顶层（按官方预期 200 放行）与 medium 嵌套
        （thinking.effort=medium 预期 400——废弃的 K2.x thinking
        配置下 medium 为非法档位，客户指定契约）。
        请求内容与 temperature 完全相同（temperature=1，开思考档
        契约温度，见 K6），相邻间隔 3s。
        断言（硬）——请求基本健康，否则长度对比无意义：
        - 每次官方档请求（升序轮+降序轮+medium 顶层）HTTP 200 +
          正文非空 + finish_reason 自然结束
        - 嵌套 thinking.effort=medium 预期 HTTP 400
        对比（软，按客户要求倒挂不判失败，仅告警）：
        - low 与 high、high 与 max 的 reasoning_tokens 应严格递增；
          任一对倒挂/持平 → 告警记入报告，用例仍通过（档位倒挂属
          行为质量偏离而非服务故障）
        - 三档均为 0 → 告警思考强度参数可能未生效
        reasoning_tokens 兼容两种字段拼写（K5 先例）；usage 缺失时
        逐次软告警（K5 先例）。
        """
        # K7: 升序轮发送顺序——low → high → max，发送后比对思考长度
        K7_ASCENDING_LEVELS = ("low", "high", "max")

        # K7: 降序轮发送顺序——max → high → low，逆向重发后再比对
        # 思考长度（正逆两轮排除请求顺序相关干扰：缓存/预热）
        K7_DESCENDING_LEVELS = ("max", "high", "low")

        # K7: 参与思考长度对比的档位（两轮共用）——medium 为合法
        # 档位但不参与对比（对比仍按 low < high < max 严格递增）
        K7_COMPARISON_LEVELS = ("low", "high", "max")

        # K7: 请求总数——升序轮 3 + 降序轮 3 + medium 顶层 1 +
        # medium 嵌套 1
        K7_TOTAL_REQUESTS = (
            len(K7_ASCENDING_LEVELS) + len(K7_DESCENDING_LEVELS) + 2
        )

        # K7: 嵌套 thinking.effort=medium——废弃的 K2.x thinking 配置
        # 下 medium 为非法档位，预期 400（客户指定契约）
        K7_NESTED_MEDIUM = {"type": "enabled", "effort": "medium"}

        # K7: 客户原始 user 提示词——需要逐步推理的问题，使各档思考
        # 长度差异可观测；各档请求内容完全相同（仅思考强度不同）
        K7_USER_PROMPT = (
            "一个笼子里有鸡和兔共 35 个头、94 只脚，请问鸡和兔各有多少只？"
            "请逐步推理后给出答案。"
        )

        # K7: 开思考档契约温度（K6；官方文档 K3 temperature 固定
        # 1.0），各档相同
        K7_TEMPERATURE = 1

        # K7: 相邻两次请求的间隔（秒）——K2/K4/K5 先例（末次后
        # 不等待）
        K7_REQUEST_INTERVAL_SECONDS = 3

        # K7: 自然结束原因（不传 max_tokens，观察思考自然长度，
        # K4/K5 先例）
        K7_NATURAL_FINISH_REASONS = ("stop", "eos", "ended")

        test_logger.info(
            "=== 测试开始: 客户问题 - 思考强度档位思考长度对比"
            "（官方顶层 reasoning_effort；low→high→max 比对后 "
            "max→high→low 再比对；最后 medium 顶层 200 放行、"
            "medium 嵌套 400；倒挂仅告警不判失败）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"
        messages = [{"role": "user", "content": K7_USER_PROMPT}]

        def run_official_request(index: int, effort: str) -> Dict[str, Any]:
            """K7 官方格式单次请求：顶层 reasoning_effort={effort}

            硬断言响应基本健康（200+正文非空+自然结束），返回观测到的
            reasoning_tokens（双拼写兼容，缺失按 0）与思考文本长度。
            """
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "reasoning_effort": effort,
                    "temperature": K7_TEMPERATURE,
                    "max_tokens": "未传（观察思考自然长度）",
                    "stream": False,
                    "round": f"第{index}次/{K7_TOTAL_REQUESTS}",
                },
            )

            # 思考强度为唯一被测参数，其余保持最小参数面（手工构造
            # payload 直发，K3-K6 先例）
            payload = {
                "model": api_client.model_name,
                "messages": messages,
                "reasoning_effort": effort,
                "temperature": K7_TEMPERATURE,
                "stream": False,
            }

            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(
                    f"第[{index}]次（reasoning_effort={effort}）请求发送"
                    f"异常（{url}）: {e}"
                )

            assert response.status_code == 200, (
                f"第[{index}]次（reasoning_effort={effort}）请求失败："
                f"应 200 正常返回，实际 HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                test_logger.error(
                    f"第[{index}]次（reasoning_effort={effort}）真实响应体: "
                    f"{response.text[:2000]!r}"
                )
                pytest.fail(
                    f"第[{index}]次（reasoning_effort={effort}）响应不是"
                    f"合法 JSON: {e}. 响应体已记录于测试日志"
                )
            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"第[{index}]次（reasoning_effort={effort}）真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"第[{index}]次（reasoning_effort={effort}）响应缺少 "
                f"choices: {list(result.keys())}"
            )
            message = choices[0].get("message") or {}
            content = (message.get("content") or "").strip()
            assert content, (
                f"第[{index}]次（reasoning_effort={effort}）正文为空"
            )
            finish_reason = (choices[0].get("finish_reason") or "").lower()
            assert finish_reason in K7_NATURAL_FINISH_REASONS, (
                f"第[{index}]次（reasoning_effort={effort}）finish_reason "
                f"异常: '{finish_reason}'（预期自然结束，未传 "
                f"max_tokens）"
            )

            # 思考长度观测（软指标，不参与硬断言）：reasoning_tokens
            # 双拼写兼容（K5 先例）
            usage = result.get("usage") or {}
            if not usage:
                # usage 缺失不影响请求健康判定，仅软告警（K5 先例）
                warn_msg = (
                    f"第[{index}]次（reasoning_effort={effort}）响应缺少 "
                    "usage，无法观测思考长度"
                )
                test_logger.warning(f"[K7-警告] {warn_msg}")
                record_warning(warn_msg)
            reasoning_tokens = usage.get("reasoning_tokens")
            if reasoning_tokens is None:
                details = usage.get("completion_tokens_details") or {}
                reasoning_tokens = details.get("reasoning_tokens")
            reasoning_tokens = reasoning_tokens or 0
            reasoning_text = (
                message.get("reasoning_content")
                or message.get("reasoning")
                or ""
            )

            TestLogger.log_response(
                test_logger,
                result,
                f"K7-响应（reasoning_effort={effort}）",
            )
            test_logger.info(
                f"第[{index}]次（reasoning_effort={effort}）正常: "
                f"HTTP 200, reasoning_tokens={reasoning_tokens}, "
                f"思考文本长度={len(reasoning_text)}, "
                f"completion_tokens={usage.get('completion_tokens')}, "
                f"正文长度={len(content)}, finish_reason={finish_reason}"
            )
            return {
                "effort": effort,
                "reasoning_tokens": reasoning_tokens,
                "reasoning_len": len(reasoning_text),
            }

        def run_nested_medium_reject(index: int) -> None:
            """K7 嵌套 thinking.effort=medium：预期 400

            废弃的 K2.x thinking 配置下 medium 为非法档位，按客户
            指定契约预期 400 拒绝。
            """
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "thinking": K7_NESTED_MEDIUM,
                    "temperature": K7_TEMPERATURE,
                    "max_tokens": "未传（契约校验与生成长度无关）",
                    "stream": False,
                    "round": f"第{index}次",
                    "expect": "reject",
                },
            )

            payload = {
                "model": api_client.model_name,
                "messages": messages,
                "thinking": K7_NESTED_MEDIUM,
                "temperature": K7_TEMPERATURE,
                "stream": False,
            }

            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(
                    f"第[{index}]次（嵌套 thinking.effort=medium）请求"
                    f"发送异常（{url}）: {e}"
                )

            if response.status_code != 400:
                test_logger.error(
                    f"第[{index}]次（嵌套 thinking.effort=medium）"
                    f"真实响应体: {response.text[:2000]!r}"
                )
            assert response.status_code == 400, (
                f"第[{index}]次（嵌套 thinking.effort=medium）预期 400 "
                f"拒绝（废弃的 K2.x thinking 配置下 medium 为非法"
                f"档位），实际 HTTP {response.status_code}"
                f"（响应体已记录于测试日志）"
            )
            test_logger.info(
                f"第[{index}]次（嵌套 thinking.effort=medium）按预期"
                f"拒绝: HTTP 400: {response.text[:200]}"
            )

        def compare_pass(
            pass_label: str, observations: Dict[str, Dict[str, Any]]
        ) -> str:
            """K7 单轮思考长度软对比（low < high < max）

            倒挂/持平仅告警不判失败（客户要求：行为质量偏离而非
            服务故障），返回本轮观测摘要。
            """
            rt = {
                level: observations[level]["reasoning_tokens"]
                for level in K7_COMPARISON_LEVELS
            }
            rt_low, rt_high, rt_max = rt["low"], rt["high"], rt["max"]
            summary = (
                f"{pass_label}思考长度观测: low={rt_low}, "
                f"high={rt_high}, max={rt_max}"
            )
            if rt_low == 0 and rt_high == 0 and rt_max == 0:
                # 全 0：无法区分"思考强度未生效/思考未开启"与"未上报
                # 思考 tokens"
                warn_msg = (
                    f"{summary}——对比三档均为 0，思考强度参数可能"
                    "未生效或服务端未上报思考 tokens，无法进行档位对比"
                )
                test_logger.warning(f"[K7-警告] {warn_msg}")
                record_warning(warn_msg)
            else:
                inversion_found = False
                if rt_low >= rt_high:
                    warn_msg = (
                        f"{summary}——档位倒挂/持平: low({rt_low}) 未小于 "
                        f"high({rt_high})，官方预期 low < high < max"
                    )
                    test_logger.warning(f"[K7-警告] {warn_msg}")
                    record_warning(warn_msg)
                    inversion_found = True
                if rt_high >= rt_max:
                    warn_msg = (
                        f"{summary}——档位倒挂/持平: high({rt_high}) 未小于 "
                        f"max({rt_max})，官方预期 low < high < max"
                    )
                    test_logger.warning(f"[K7-警告] {warn_msg}")
                    record_warning(warn_msg)
                    inversion_found = True
                if inversion_found:
                    test_logger.warning(
                        "[K7-警告] 检测到思考强度档位思考长度未严格递增"
                        "（按约定不判失败，请检查思考强度档位到后端思考"
                        "预算的映射）"
                    )
                else:
                    test_logger.info(
                        f"{summary}，档位严格递增，符合官方预期"
                    )
            return summary

        # === 升序轮：low → high → max，发送后比对思考长度 ===
        observations: Dict[str, Dict[str, Any]] = {}
        for index, effort in enumerate(K7_ASCENDING_LEVELS, start=1):
            observations[effort] = run_official_request(index, effort)
            if index < len(K7_ASCENDING_LEVELS):
                time.sleep(K7_REQUEST_INTERVAL_SECONDS)
        summary_asc = compare_pass("升序轮（low→high→max）", observations)

        time.sleep(K7_REQUEST_INTERVAL_SECONDS)

        # === 降序轮：max → high → low，逆向重发后再比对思考长度 ===
        observations_desc: Dict[str, Dict[str, Any]] = {}
        for index, effort in enumerate(
            K7_DESCENDING_LEVELS, start=len(K7_ASCENDING_LEVELS) + 1
        ):
            observations_desc[effort] = run_official_request(index, effort)
            if index < len(K7_ASCENDING_LEVELS) + len(K7_DESCENDING_LEVELS):
                time.sleep(K7_REQUEST_INTERVAL_SECONDS)
        summary_desc = compare_pass(
            "降序轮（max→high→low）", observations_desc
        )

        time.sleep(K7_REQUEST_INTERVAL_SECONDS)

        # === medium 顶层：合法档位，按官方预期 200 放行（不参与对比） ===
        medium_index = (
            len(K7_ASCENDING_LEVELS) + len(K7_DESCENDING_LEVELS) + 1
        )
        medium_observation = run_official_request(medium_index, "medium")

        time.sleep(K7_REQUEST_INTERVAL_SECONDS)

        # === 最后：medium 嵌套 thinking.effort=medium 预期 400
        # （客户指定契约） ===
        run_nested_medium_reject(medium_index + 1)

        test_logger.info(
            "客户问题复现通过: 升序/降序两轮思考强度请求均正常返回，"
            "medium 顶层按官方放行、medium 嵌套按预期拒绝"
            f"（思考长度对比仅告警不判失败；{summary_asc}；"
            f"{summary_desc}；medium 顶层 reasoning_tokens="
            f"{medium_observation['reasoning_tokens']}，"
            "合法档位不参与对比）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.KimiK3
    @pytest.mark.p1
    def test_required_chitchat_calls_tool(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K8 [P1]: 客户问题 - required+闲聊必须调用工具（客户工单级别，finish=tool_calls、预算不被吃满）

        客户工单原始问题：tool_choice=required + 闲聊
        "Reply with exactly: OK"（无工具意图）下不发起工具调用：
        tool_calls 键缺失、finish=length、completion_tokens 恒被
        吃满 max_tokens（关思考 1000/3000 级别均如此）、正文仅
        "OK"、耗时 ~15.6s（正常 ~1.5s，双峰）；开思考下
        reasoning 消耗远小于预算但整体仍被吃满（mt=3000 仍不调）。
        预期（工单）：required 必须发起工具调用——finish 应为
        tool_calls 而非 length；关思考 ct 应较小、耗时应较少；
        开思考 rt 应 < max_tokens；正文应正常收到调用工具的响应
        信息。
        轮次（客户实测级别）：关思考 mt=1000、关思考 mt=3000、
        开思考 mt=3000；工具定义 get_weather(city)（获取北京天气
        的工具，city 值不限定）。temperature 按网关档位联动约束
        取 disabled→0.6 / enabled→1（非该值被 400 拒绝，无法构
        建场景）。每轮硬断言：
        - HTTP 200 + choices + usage 存在（ct 判定数据源）
        - tool_calls 存在且为 get_weather 函数调用，arguments 为
          合法 JSON
        - finish_reason == "tool_calls"（而非 length——length 即
          token 预算被消耗殆尽的缺陷形态，关/开思考均不允许）
        - ct < max_tokens（关思考下应较小；缺陷形态为恒吃满）
        - 开思考：rt（reasoning tokens）< max_tokens（思考不吃完
          预算）；rt 双拼写兼容
        耗时双峰（缺陷 15.6s 级 vs 正常 1.5s 级）仅日志留痕——
        finish 断言已覆盖其缺陷形态，不对绝对耗时硬断言（网络抖
        动易误报）。官方行为对照级别（mt=256/2000）由 K9 验证。
        （不进 smoke 集：缺陷轮 15.6s 级长耗时+缺陷概率性）
        """
        # K8: 工具定义——获取北京天气（get_weather(city)，客户工单
        # 原始工具）
        K8_TOOLS = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }]

        # K8: 闲聊提示词（客户原始口径）——无工具意图 + required 即
        # 缺陷触发条件
        K8_USER_PROMPT = "Reply with exactly: OK"

        # K8: 轮次（标签, thinking, temperature, max_tokens）——按客户
        # 实测级别：关思考 mt=1000/3000、开思考 mt=3000；temperature
        # 按网关档位联动约束（disabled→0.6、enabled→1，非该值被
        # 400 拒绝、无法构建场景）
        K8_ROUNDS = (
            ("关思考 mt=1000", "disabled", 0.6, 1000),
            ("关思考 mt=3000", "disabled", 0.6, 3000),
            ("开思考 mt=3000", "enabled", 1, 3000),
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - required+闲聊必须调用工具"
            f"（{K8_USER_PROMPT}；关思考 mt=1000/3000、开思考 "
            "mt=3000；断言 tool_calls+finish=tool_calls+ct/rt 不被"
            "吃满；官方行为对照级别 256/2000 由 K9 验证）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def run_round(
            label: str, thinking_type: str, temperature: float,
            max_tokens: int,
        ) -> None:
            """K8 单轮：required+无工具意图闲聊，断言必须调用工具且预算不被吃满"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K8_USER_PROMPT}],
                {
                    "tools": [t["function"]["name"] for t in K8_TOOLS],
                    "tool_choice": "required",
                    "thinking": thinking_type,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                    "round": label,
                },
            )

            # 手工构造 payload 直发（需 tools/tool_choice/max_tokens/
            # 档位温度——精确控制请求字段集，wrapper 会固定附带
            # max_tokens/stream 等默认字段）
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": K8_USER_PROMPT}],
                "tools": K8_TOOLS,
                "tool_choice": "required",
                "thinking": {"type": thinking_type},
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }

            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started

            assert response.status_code == 200, (
                f"[{label}] 客户问题复现失败：应 200 正常返回，实际 "
                f"HTTP {response.status_code}: {response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                test_logger.error(
                    f"[{label}] 真实响应体: {response.text[:2000]!r}"
                )
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"[{label}] 响应缺少 choices: {list(result.keys())}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls")
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            # usage 为预算断言数据源，缺失即失败
            if not usage:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert usage, (
                f"[{label}] 客户问题复现失败：响应缺少 usage——预算"
                f"断言无从进行: {list(result.keys())}"
            )
            ct = usage.get("completion_tokens")
            assert isinstance(ct, int), (
                f"[{label}] 客户问题复现失败：usage 缺少有效 "
                f"completion_tokens: "
                f"{json.dumps(usage, ensure_ascii=False)[:300]}"
            )
            # rt 双拼写兼容；缺失按 None（关思考不强制上报）
            rt = usage.get("reasoning_tokens")
            if rt is None:
                details = usage.get("completion_tokens_details") or {}
                rt = details.get("reasoning_tokens")

            TestLogger.log_response(test_logger, result, f"K8-响应（{label}）")
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed={elapsed:.1f}s, ct={ct}, "
                f"rt={rt}, finish={finish}, "
                f"tool_calls={'有' if tool_calls else '无'}, "
                f"content_len={len(content)}"
            )

            # 断言1：required 必须发起工具调用（缺陷形态：tool_calls
            # 键缺失、正文仅 "OK"、ct 恒吃满预算、finish=length）
            if not tool_calls:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert tool_calls, (
                f"[{label}] 客户问题复现失败：required 下未发起工具"
                f"调用——tool_calls 键缺失（finish={finish}、ct={ct}/"
                f"{max_tokens}；缺陷形态：finish=length、completion_"
                f"tokens 恒吃满 max_tokens、正文仅 OK）"
            )
            first = tool_calls[0] or {}
            fn = first.get("function") or {}
            assert (
                first.get("type") == "function"
                and fn.get("name") == "get_weather"
            ), (
                f"[{label}] 客户问题复现失败：工具调用形状异常（应 "
                f"function/get_weather，实际 "
                f"type={first.get('type')}, name={fn.get('name')}）"
            )
            try:
                fn_args = json.loads(fn.get("arguments") or "")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                test_logger.error(
                    f"[{label}] 工具调用 arguments: "
                    f"{(fn.get('arguments') or '')[:2000]!r}"
                )
                pytest.fail(
                    f"[{label}] 客户问题复现失败：工具调用 arguments "
                    f"不是合法 JSON: {e}（已记录于测试日志）"
                )
            if not isinstance(fn_args, dict):
                test_logger.error(
                    f"[{label}] 工具调用 arguments: "
                    f"{(fn.get('arguments') or '')[:2000]!r}"
                )
            assert isinstance(fn_args, dict), (
                f"[{label}] 客户问题复现失败：工具调用 arguments 应为"
                f" JSON 对象"
            )

            # 断言2：finish 必须为 tool_calls（length 即 token 预算
            # 被消耗殆尽的缺陷形态——关/开思考均不允许，断言不分模式）
            if finish != "tool_calls":
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert finish == "tool_calls", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"tool_calls（required 必须调用工具），实际 {finish}"
                f"（ct={ct}/{max_tokens}、rt={rt}——token 被消耗殆尽"
                f"的缺陷形态）"
            )

            # 断言3：预算不被吃满（缺陷形态：ct 恒==max_tokens）
            assert ct < max_tokens, (
                f"[{label}] 客户问题复现失败：completion_tokens={ct} "
                f"吃满 max_tokens={max_tokens}——关思考下 ct 应较"
                f"小、不被吃满"
            )

            # 断言4（开思考）：思考消耗应小于 max_tokens
            if thinking_type == "enabled":
                assert isinstance(rt, int) and rt >= 0, (
                    f"[{label}] 客户问题复现失败：开思考下 usage 未上"
                    f"报有效 reasoning_tokens（rt={rt}），无法验证"
                    f"思考消耗 < max_tokens"
                )
                assert rt < max_tokens, (
                    f"[{label}] 客户问题复现失败：reasoning tokens="
                    f"{rt} 吃满/超出 max_tokens={max_tokens}——思考"
                    f"不应吃完预算"
                )

        for label, thinking_type, temperature, max_tokens in K8_ROUNDS:
            run_round(label, thinking_type, temperature, max_tokens)

        test_logger.info(
            "客户问题复现通过: required+闲聊 关思考 mt=1000/3000、"
            "开思考 mt=3000 全部正常发起 get_weather 调用"
            "（finish=tool_calls、ct/rt 均未吃满预算；官方行为对照"
            "级别由 K9 验证）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.KimiK3
    @pytest.mark.p1
    def test_required_chitchat_official_behavior(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K9 [P1]: 客户问题 - required+闲聊必须强制调用工具（按官方行为为预期）

        官方 api.moonshot.cn/kimi-k3 实测：闲聊 "Reply with exactly:
        OK" + required → finish=tool_calls、强制返回 get_weather 调用
        （city 瞎猜 London/UNKNOWN——值不限定）、reasoning 仅 38
        token——符合 [OI] required「必须发起至少一次工具调用」规范。
        Alaya 同场景缺陷：finish=length、reasoning 吃满 256/2000
        预算、tool_calls=None；有工具意图时（北京天气）两站一致
        正常。
        本用例按官方行为为预期（与 K8 同场景不同级别：K8 为客户
        工单级别 mt=1000/3000/3000 复现，本用例镜像 Alaya 缺陷实
        测级别）。轮次：关思考 mt=256、关思考 mt=2000、开思考
        mt=256、开思考 mt=2000。temperature 按网关档位联动约束取
        disabled→0.6 / enabled→1（非该值被 400 拒绝，无法构建场
        景）。每轮硬断言：
        - HTTP 200 + choices + usage 存在
        - tool_calls 强制返回且为 get_weather 函数调用、arguments
          为合法 JSON（city 值不限定——官方亦瞎猜）
        - finish_reason == "tool_calls"（而非 length）
        - ct < max_tokens（预算不被吃满）
        - 开思考：rt < max_tokens（官方 reasoning 仅 38；缺陷形态
          为吃满预算）；rt 双拼写兼容
        耗时双峰仅日志留痕（finish 断言已覆盖缺陷形态，同 K8 理
        由）。（不进 smoke 集：缺陷轮 15.6s 级长耗时 + 缺陷概率性）
        """
        # K9: 工具定义（get_weather(city)）——与 K8 相同的客户原始工
        # 具（各用例独立自包含，不共享常量）
        K9_TOOLS = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }]

        # K9: 闲聊提示词（客户原始口径，官方对照同款）——无工具意图
        # + required 即缺陷触发条件
        K9_USER_PROMPT = "Reply with exactly: OK"

        # K9: 轮次（标签, thinking, temperature, max_tokens）——镜像
        # Alaya 缺陷实测级别 256/2000 × 关/开思考；temperature 按网
        # 关档位联动约束
        K9_ROUNDS = (
            ("关思考 mt=256", "disabled", 0.6, 256),
            ("关思考 mt=2000", "disabled", 0.6, 2000),
            ("开思考 mt=256", "enabled", 1, 256),
            ("开思考 mt=2000", "enabled", 1, 2000),
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - required+闲聊必须强制调用"
            "工具（'Reply with exactly: OK'；关/开思考 × mt=256/"
            "2000；按官方行为为预期：finish=tool_calls+强制 "
            "get_weather+预算不被吃满；客户工单级别 mt=1000/3000 "
            "由 K8 验证）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def run_round(
            label: str, thinking_type: str, temperature: float,
            max_tokens: int,
        ) -> None:
            """K9 单轮：required+闲聊，断言必须强制调用工具且预算不被吃满"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K9_USER_PROMPT}],
                {
                    "tools": [t["function"]["name"] for t in K9_TOOLS],
                    "tool_choice": "required",
                    "thinking": thinking_type,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                    "round": label,
                },
            )

            # 手工构造 payload 直发（需 tools/tool_choice/max_tokens/
            # 档位温度——精确控制请求字段集，wrapper 会固定附带
            # max_tokens/stream 等默认字段）
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": K9_USER_PROMPT}],
                "tools": K9_TOOLS,
                "tool_choice": "required",
                "thinking": {"type": thinking_type},
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }

            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started

            assert response.status_code == 200, (
                f"[{label}] 客户问题复现失败：应 200 正常返回，实际 "
                f"HTTP {response.status_code}: {response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                test_logger.error(
                    f"[{label}] 真实响应体: {response.text[:2000]!r}"
                )
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"[{label}] 响应缺少 choices: {list(result.keys())}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls")
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            # usage 为预算断言数据源，缺失即失败
            if not usage:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert usage, (
                f"[{label}] 客户问题复现失败：响应缺少 usage——预算"
                f"断言无从进行: {list(result.keys())}"
            )
            ct = usage.get("completion_tokens")
            assert isinstance(ct, int), (
                f"[{label}] 客户问题复现失败：usage 缺少有效 "
                f"completion_tokens: "
                f"{json.dumps(usage, ensure_ascii=False)[:300]}"
            )
            # rt 双拼写兼容；缺失按 None（关思考不强制上报）
            rt = usage.get("reasoning_tokens")
            if rt is None:
                details = usage.get("completion_tokens_details") or {}
                rt = details.get("reasoning_tokens")

            TestLogger.log_response(test_logger, result, f"K9-响应（{label}）")
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed={elapsed:.1f}s, ct={ct}, "
                f"rt={rt}, finish={finish}, "
                f"tool_calls={'有' if tool_calls else '无'}, "
                f"content_len={len(content)}"
            )

            # 断言1：required 必须强制发起工具调用（官方行为：闲聊也
            # 强制返回 get_weather，city 瞎猜不限定；Alaya 缺陷形态：
            # tool_calls=None、finish=length、reasoning 吃满预算）
            if not tool_calls:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert tool_calls, (
                f"[{label}] 客户问题复现失败：required 下闲聊未强制"
                f"发起工具调用——tool_calls 键缺失（finish={finish}、"
                f"ct={ct}/{max_tokens}；官方行为为 finish=tool_calls"
                f" 强制返回 get_weather，Alaya 缺陷形态为 finish="
                f"length、reasoning 吃满预算、tool_calls=None）"
            )
            first = tool_calls[0] or {}
            fn = first.get("function") or {}
            assert (
                first.get("type") == "function"
                and fn.get("name") == "get_weather"
            ), (
                f"[{label}] 客户问题复现失败：工具调用形状异常（应 "
                f"function/get_weather，实际 "
                f"type={first.get('type')}, name={fn.get('name')}）"
            )
            try:
                fn_args = json.loads(fn.get("arguments") or "")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                test_logger.error(
                    f"[{label}] 工具调用 arguments: "
                    f"{(fn.get('arguments') or '')[:2000]!r}"
                )
                pytest.fail(
                    f"[{label}] 客户问题复现失败：工具调用 arguments "
                    f"不是合法 JSON: {e}（已记录于测试日志）"
                )
            if not isinstance(fn_args, dict):
                test_logger.error(
                    f"[{label}] 工具调用 arguments: "
                    f"{(fn.get('arguments') or '')[:2000]!r}"
                )
            assert isinstance(fn_args, dict), (
                f"[{label}] 客户问题复现失败：工具调用 arguments 应为"
                f" JSON 对象"
            )

            # 断言2：finish 必须为 tool_calls（官方行为；而非 length）
            if finish != "tool_calls":
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert finish == "tool_calls", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"tool_calls（required 必须调用工具），实际 {finish}"
                f"（ct={ct}/{max_tokens}、rt={rt}）"
            )

            # 断言3：预算不被吃满（Alaya 缺陷形态：ct 恒吃满预算）
            assert ct < max_tokens, (
                f"[{label}] 客户问题复现失败：completion_tokens={ct} "
                f"吃满 max_tokens={max_tokens}——预算不应被吃满"
            )

            # 断言4（开思考）：思考消耗应小于 max_tokens
            if thinking_type == "enabled":
                assert isinstance(rt, int) and rt >= 0, (
                    f"[{label}] 客户问题复现失败：开思考下 usage 未上"
                    f"报有效 reasoning_tokens（rt={rt}），无法验证"
                    f"思考消耗 < max_tokens"
                )
                assert rt < max_tokens, (
                    f"[{label}] 客户问题复现失败：reasoning tokens="
                    f"{rt} 吃满/超出 max_tokens={max_tokens}——思考"
                    f"不应吃完预算（官方同场景 reasoning 仅 38）"
                )

        for label, thinking_type, temperature, max_tokens in K9_ROUNDS:
            run_round(label, thinking_type, temperature, max_tokens)

        test_logger.info(
            "客户问题复现通过: required+闲聊 关/开思考 × mt=256/2000 "
            "全部按官方行为强制返回 get_weather 调用（finish="
            "tool_calls、ct/rt 均未吃满预算；客户工单级别由 K8 验证）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53FLASH
    @pytest.mark.KimiK3
    @pytest.mark.p0
    def test_tool_choice_four_modes_support(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K10 [P0]: 客户问题 - GLM-5.3-Flash tool_choice 四种模式支持

        客户问题（AGDC2-15）：OpenAI 协议 tool_choice 让模型在准备
        工具调用时按请求指定的类型/模式生成调用（Agent 自定义工具
        场景）；上线前版本未指定模型专属的工具调用格式解析器，
        GLM-5.3-Flash 不支持该语义。修复：Worker 侧指定生成解释
        器，支持渲染字段至模型聊天模版（chat_template.jinja）。
        需支持四种模式：auto（模型自主决定）、required（必须调用
        工具）、named（必须调用指定工具）、none（禁止调用工具）。
        本用例对四种模式各发一次请求（原始验证脚本 glm53_flash_
        suite 的 tool_auto/tool_required/tool_named/tool_none.sh
        口径：max_tokens=2048、非流式、不传 thinking——GLM-5.3-
        Flash 默认思考，参考结果含 reasoning_content，不做思考断
        言；采样参数豁免（用户口径：原始脚本指定 temperature=0
        ——原样保留，不受全局 SAMPLING_PARAMS 覆盖；top_p/seed
        脚本未指定，不注入）。工具两个：get_weather(city)+
        get_current_time(timezone)。auto/required/none 用工具意图
        提示词（原始脚本口径）；named 指定 get_current_time 且提
        示词保持原始口径的天气意图——named 与提示词自然意图不同
        向，若 named 语义未生效（被忽略按 auto 处理）模型会按意
        图调 get_weather，从而检出「指定工具未被强制」。同时适用
        Kimi K3（OpenAI 协议 tool_choice 通用语义；Kimi K3 默认思
        考、响应含 reasoning_content，同样不做思考断言；2026-10-26
        staging 实测 kimi-k3 required 轮 500 prefill_internal_error
        "Kimi K3 required tool call is missing or incomplete"，
        该 FAIL 即为其待修复基线）。每轮硬断言：
        - HTTP 200 + choices 存在（该模式不被支持即非 200）
        - auto/required：tool_calls 存在且形状合法（type=
          function、arguments 合法 JSON）、finish_reason==
          "tool_calls"
        - named：tool_calls 存在且 function.name==指定工具
          （get_current_time）、finish_reason=="tool_calls"
        - none：tool_calls 缺失、content 非空、finish_reason==
          "stop"
        usage 仅日志留痕（原始脚本无预算断言，本用例测模式支持，
        不引入无关断言）。（不进 smoke 集：新用例首跑观察期）
        """
        # K10: 工具定义——两个工具使 named 模式可判定（指定与提
        # 示词意图不同的工具，见 docstring；形状对齐原始脚本）
        K10_TOOLS = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a city",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "Get current time for a timezone",
                    "parameters": {
                        "type": "object",
                        "properties": {"timezone": {"type": "string"}},
                        "required": ["timezone"],
                    },
                },
            },
        ]

        # K10: 轮次（标签, tool_choice, 提示词, 期望）——期望：call_any
        # （必须发起调用，工具不限）/ call_named（必须为指定工具）/
        # no_call（禁止调用）。auto/required/none 提示词为原始脚本
        # 口径的工具意图；named 提示词保持原始脚本口径的天气意图，
        # 但指定 get_current_time（与意图不同向，named 未生效时模型
        # 会按意图调 get_weather 而被检出）
        K10_ROUNDS = (
            (
                "auto",
                "auto",
                "Call get_weather for Beijing and report the temperature.",
                "call_any",
            ),
            (
                "required",
                "required",
                "Call get_weather for Beijing and report the temperature.",
                "call_any",
            ),
            (
                "named(get_current_time)",
                {"type": "function", "function": {"name": "get_current_time"}},
                "Look up Beijing weather.",
                "call_named",
            ),
            (
                "none",
                "none",
                "Call get_weather for Beijing and report the temperature.",
                "no_call",
            ),
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - tool_choice 四种"
            "模式支持（auto/required/named/none；mt=2048、非流式、"
            "不传 thinking，按原始脚本口径；采样参数豁免——原始"
            "脚本指定 temperature=0 原样保留，不受全局 SAMPLING_"
            "PARAMS 覆盖；named 指定与天气意图不同向的 get_current_time "
            "以验证强制语义）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def run_round(
            label: str, tool_choice: Any, prompt: str, expect: str
        ) -> None:
            """K10 单轮：按 tool_choice 模式断言语义生效"""
            # 手工构造 payload 直发（需 tools/tool_choice 直进 payload）；
            # 采样参数豁免（用户口径）——原始脚本指定 temperature=0，
            # 原样保留；top_p/seed 脚本未指定，不注入
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "tools": K10_TOOLS,
                "tool_choice": tool_choice,
                "max_tokens": 2048,
                "temperature": 0,
                "stream": False,
            }

            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": prompt}],
                {
                    "tools": [t["function"]["name"] for t in K10_TOOLS],
                    "tool_choice": tool_choice,
                    "temperature": payload["temperature"],
                    "top_p": payload.get("top_p", "(不注入)"),
                    "seed": payload.get("seed", "(不注入)"),
                    "max_tokens": 2048,
                    "stream": False,
                    "round": label,
                },
            )

            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started

            # 断言0：该模式被支持（不支持通常表现为 400/500）
            assert response.status_code == 200, (
                f"[{label}] 客户问题复现失败：应 200 正常返回（该模"
                f"式不被支持），实际 HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                test_logger.error(
                    f"[{label}] 真实响应体: {response.text[:2000]!r}"
                )
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"[{label}] 响应缺少 choices: {list(result.keys())}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls")
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            TestLogger.log_response(test_logger, result, f"K10-响应（{label}）")
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed={elapsed:.1f}s, "
                f"finish={finish}, tool_calls="
                f"{'有' if tool_calls else '无'}, content_len="
                f"{len(content)}, usage="
                f"{json.dumps(usage, ensure_ascii=False)}"
            )

            def check_call_shape(tc: List[Dict[str, Any]]) -> str:
                """校验工具调用形状，返回被调用的函数名"""
                first = tc[0] or {}
                fn = first.get("function") or {}
                assert (
                    first.get("type") == "function" and fn.get("name")
                ), (
                    f"[{label}] 客户问题复现失败：工具调用形状异常（应 "
                    f"type=function 且带 name，实际 "
                    f"type={first.get('type')}, name={fn.get('name')}）"
                )
                try:
                    fn_args = json.loads(fn.get("arguments") or "")
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    test_logger.error(
                        f"[{label}] 工具调用 arguments: "
                        f"{(fn.get('arguments') or '')[:2000]!r}"
                    )
                    pytest.fail(
                        f"[{label}] 客户问题复现失败：工具调用 arguments "
                        f"不是合法 JSON: {e}（已记录于测试日志）"
                    )
                if not isinstance(fn_args, dict):
                    test_logger.error(
                        f"[{label}] 工具调用 arguments: "
                        f"{(fn.get('arguments') or '')[:2000]!r}"
                    )
                assert isinstance(fn_args, dict), (
                    f"[{label}] 客户问题复现失败：工具调用 arguments 应为"
                    f" JSON 对象"
                )
                return fn.get("name")

            if expect == "no_call":
                # 断言（none）：禁止调用工具，正文正常回复
                if tool_calls:
                    test_logger.error(
                        f"[{label}] 真实响应体: "
                        f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                    )
                assert not tool_calls, (
                    f"[{label}] 客户问题复现失败：tool_choice=none 下仍"
                    f"发起工具调用（none 语义未生效）"
                )
                if not content:
                    test_logger.error(
                        f"[{label}] 真实响应体: "
                        f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                    )
                assert content, (
                    f"[{label}] 客户问题复现失败：tool_choice=none 下"
                    f"正文为空（应正常文本回复）"
                )
                if finish != "stop":
                    test_logger.error(
                        f"[{label}] 真实响应体: "
                        f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                    )
                assert finish == "stop", (
                    f"[{label}] 客户问题复现失败：tool_choice=none 下"
                    f"finish_reason 应为 stop，实际 {finish}"
                )
            else:
                # 断言（auto/required/named）：必须发起工具调用
                if not tool_calls:
                    test_logger.error(
                        f"[{label}] 真实响应体: "
                        f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                    )
                assert tool_calls, (
                    f"[{label}] 客户问题复现失败：该模式下未发起工具"
                    f"调用（模式不被支持/语义未生效，finish="
                    f"{finish}）"
                )
                called = check_call_shape(tool_calls)
                if finish != "tool_calls":
                    test_logger.error(
                        f"[{label}] 真实响应体: "
                        f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                    )
                assert finish == "tool_calls", (
                    f"[{label}] 客户问题复现失败：finish_reason 应为 "
                    f"tool_calls，实际 {finish}"
                )
                if expect == "call_named":
                    # 断言（named）：必须调用指定工具（与提示词意图
                    # 不同向，named 未生效时模型按意图调 get_weather
                    # 即在此被检出）
                    named_name = tool_choice["function"]["name"]
                    if called != named_name:
                        test_logger.error(
                            f"[{label}] 真实响应体: "
                            f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                        )
                    assert called == named_name, (
                        f"[{label}] 客户问题复现失败：named 指定 "
                        f"{named_name} 但实际调用 {called}（named 强"
                        f"制语义未生效，按提示词意图选择了工具）"
                    )

        for label, tool_choice, prompt, expect in K10_ROUNDS:
            run_round(label, tool_choice, prompt, expect)

        test_logger.info(
            "客户问题复现通过: tool_choice 四种模式"
            "（auto/required/named/none）语义均生效（auto/required/"
            "named 发起工具调用且 named 强制指定工具、none 禁止调用"
            "且正文正常）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53FLASH
    @pytest.mark.p0
    def test_response_format_three_modes_support(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K11 [P0]: 客户问题 - GLM-5.3-Flash response_format 三种模式支持

        客户问题（AGDC2-16）：OpenAI 协议 response_format 让模型按
        指定格式输出（Agent 场景）；DingoRouter 不支持该结构化输出
        语义。修复：Router 侧支持结构化生成语义并实现语义转发至
        引擎。需支持三种模式：json_object（输出为合法 JSON 对
        象）、json_schema（输出符合指定 JSON Schema）、text（纯
        文本，协议默认）。
        本用例对三种模式各发一次请求（原始验证脚本 glm53_flash_
        suite 的 response_json_object/response_json_schema.sh 口
        径：temperature=0、max_tokens=2048、非流式、不传
        thinking）。json_object 轮与 json_schema 轮的提示词、
        response_format 均为原始脚本原样口径；text 轮为协议默认
        模式（原始脚本未单测，按需补齐）。每轮硬断言：
        - HTTP 200 + choices 存在（该模式不被支持即非 200）
        - 正文非空、finish_reason=="stop"（参考结果均自然结束）
        - json_object：json.loads(正文) 为 dict
        - json_schema：json.loads(正文) 为 dict 且 city 为字符
          串、temperature 为数值（非 bool）、键集合恰为
          {city, temperature}
        - text：正文非空（纯文本语义，不强制 JSON）
        usage 仅日志留痕（原始脚本无预算断言）。（不进 smoke 集：
        新用例首跑观察期）
        """
        # K11: 轮次（标签, response_format, 提示词, 期望）——json_
        # object/json_schema 轮为原始脚本原样口径；text 轮为协议默
        # 认模式（原始脚本未单测，按需补齐支持验证）
        K11_ROUNDS = (
            (
                "json_object",
                {"type": "json_object"},
                "Output a JSON object with fields city=Beijing and "
                "value=17. No markdown.",
                "json_object",
            ),
            (
                "json_schema",
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "weather",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string"},
                                "temperature": {"type": "number"},
                            },
                            "required": ["city", "temperature"],
                            "additionalProperties": False,
                        },
                    },
                },
                "Give estimated temperature for Beijing as a JSON "
                "object matching schema.",
                "json_schema",
            ),
            (
                "text",
                {"type": "text"},
                "Respond with a short plain text greeting.",
                "text",
            ),
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - response_format "
            "三种模式支持（json_object/json_schema/text；temperature="
            "0、mt=2048、非流式、不传 thinking，按原始脚本口径）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def run_round(
            label: str, response_format: Dict[str, Any],
            prompt: str, expect: str,
        ) -> None:
            """K11 单轮：按 response_format 模式断言语义生效"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": prompt}],
                {
                    "response_format": response_format,
                    "temperature": 0,
                    "max_tokens": 2048,
                    "stream": False,
                    "round": label,
                },
            )

            # 手工构造 payload 直发（需 response_format 直进 payload；
            # temperature=0 为工单原始脚本口径，原样保留——已豁免全局
            # 采样覆盖；top_p/seed 脚本未指定，不注入）
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": response_format,
                "max_tokens": 2048,
                "temperature": 0,
                "stream": False,
            }

            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started

            # 断言0：该模式被支持（不支持通常表现为 400/500）
            assert response.status_code == 200, (
                f"[{label}] 客户问题复现失败：应 200 正常返回（该模"
                f"式不被支持），实际 HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                test_logger.error(
                    f"[{label}] 真实响应体: {response.text[:2000]!r}"
                )
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"[{label}] 响应缺少 choices: {list(result.keys())}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            TestLogger.log_response(
                test_logger, result, f"K11-响应（{label}）"
            )
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed={elapsed:.1f}s, "
                f"finish={finish}, content_len={len(content)}, "
                f"usage={json.dumps(usage, ensure_ascii=False)}"
            )

            # 断言1：正文非空且自然结束（三种模式通用）
            assert content, (
                f"[{label}] 客户问题复现失败：正文为空"
            )
            assert finish == "stop", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"stop，实际 {finish}"
            )

            # 断言2：模式语义（json_object/json_schema 输出结构化
            # JSON；text 纯文本不强制 JSON）
            if expect in ("json_object", "json_schema"):
                try:
                    parsed = json.loads(content)
                except (json.JSONDecodeError, ValueError) as e:
                    pytest.fail(
                        f"[{label}] 客户问题复现失败：正文不是合法 "
                        f"JSON（结构化输出语义未生效，{e}）"
                    )
                assert isinstance(parsed, dict), (
                    f"[{label}] 客户问题复现失败：正文应为 JSON 对象"
                    f"（dict），实际 {type(parsed).__name__}"
                )
                if expect == "json_schema":
                    keys = set(parsed.keys())
                    assert keys == {"city", "temperature"}, (
                        f"[{label}] 客户问题复现失败：json_schema 正文"
                        f"键集合应为 {{city, temperature}}，实际 "
                        f"{sorted(keys)}"
                    )
                    city = parsed.get("city")
                    temperature = parsed.get("temperature")
                    assert isinstance(city, str), (
                        f"[{label}] 客户问题复现失败：city 应为字符"
                        f"串，实际 {city!r}"
                    )
                    assert (
                        isinstance(temperature, (int, float))
                        and not isinstance(temperature, bool)
                    ), (
                        f"[{label}] 客户问题复现失败：temperature 应"
                        f"为数值，实际 {temperature!r}"
                    )

        for label, response_format, prompt, expect in K11_ROUNDS:
            run_round(label, response_format, prompt, expect)

        test_logger.info(
            "客户问题复现通过: response_format 三种"
            "模式（json_object/json_schema/text）语义均生效（json_"
            "object 正文为合法 JSON 对象、json_schema 正文符合 "
            "weather schema、text 正文正常）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53FLASH
    @pytest.mark.p0
    def test_reasoning_effort_levels_support(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K12 [P0]: 客户问题 - GLM-5.3-Flash reasoning_effort 档位支持

        客户问题（AGDC2-17）：GLM-5.3-Flash 使用 GLM 自己的聊天
        模版，字段为 reasoning_effort 且放在 chat_template_kwargs
        里；而 OpenAI 协议/参考脚本将其放在顶层。Router 需要在
        OpenAI 协议外层捕获该字段并传给引擎（修复：Router 侧支持
        语义转发）。需支持：low/high/max/空（空=不发送该字段，
        默认档），且不管 reasoning_effort 放在顶层还是嵌套在
        chat_template_kwargs 里，请求都能被正常接受和处理并输出
        正常响应，否则用例失败。
        本用例对两种放置（顶层 / 嵌套 chat_template_kwargs）× 四
        档各发一次请求（原始验证脚本 glm53_flash_suite 的
        reasoning_low/reasoning_high/reasoning_max.sh 口径：
        temperature=0、max_tokens=2048、非流式、不传 thinking；
        顶层放置：reasoning_effort 在顶层 +
        chat_template_kwargs={"clear_thinking": true}（原始脚本
        原样保留）；嵌套放置：reasoning_effort 放进
        chat_template_kwargs（GLM 聊天模版原生口径）；空档无对应
        脚本，按需补齐为不发送该字段）。提示词 "Explain why
        17*19=323 with intermediate reasoning if available."
        （原始脚本口径）。每轮硬断言：
        - HTTP 200 + choices 存在（该放置/档位不被支持即非 200）
        - 正文非空、finish_reason=="stop"（参考结果均自然结束）
        档位对思考的实际影响（reasoning_tokens、reasoning_
        content 长度）仅日志留痕——参考脚本未做档位间断言，思考
        长度为模型行为质量，不做硬断言。usage 仅日志。（不进
        smoke 集：新用例首跑观察期）
        """
        # K12: 提示词（原始脚本口径，各轮相同——放置与档位为唯
        # 一变量）
        K12_PROMPT = (
            "Explain why 17*19=323 with intermediate reasoning "
            "if available."
        )

        # K12: 轮次（标签, 放置, reasoning_effort）——顶层为原始
        # 脚本口径；嵌套为 GLM 聊天模版原生口径（reasoning_
        # effort 放在 chat_template_kwargs 里）；空=不发送该字
        # 段（默认档，原始脚本无对应档，按需补齐；两种放置口径
        # 下同构）
        K12_ROUNDS = (
            ("顶层-low", "top", "low"),
            ("顶层-high", "top", "high"),
            ("顶层-max", "top", "max"),
            ("顶层-空（不发送该字段，默认档）", "top", None),
            ("嵌套-low", "nested", "low"),
            ("嵌套-high", "nested", "high"),
            ("嵌套-max", "nested", "max"),
            ("嵌套-空（不发送该字段，默认档）", "nested", None),
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - reasoning_"
            "effort 档位支持（顶层/嵌套 chat_template_kwargs 两种"
            "放置 × low/high/max/空 四档；temperature=0、mt=2048、"
            "非流式、不传 thinking、chat_template_kwargs="
            "{clear_thinking:true}，按原始脚本口径）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def run_round(label: str, placement: str, effort) -> None:
            """K12 单轮：按放置+档位断言请求被支持"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K12_PROMPT}],
                {
                    "placement": (
                        "顶层" if placement == "top"
                        else "嵌套 chat_template_kwargs"
                    ),
                    "reasoning_effort": effort if effort else "(空)",
                    "chat_template_kwargs": {"clear_thinking": True},
                    "temperature": 0,
                    "max_tokens": 2048,
                    "stream": False,
                    "round": label,
                },
            )

            # 手工构造 payload 直发（需按放置构造 reasoning_
            # effort/chat_template_kwargs；temperature=0 为工单原始
            # 脚本口径，原样保留——已豁免全局采样覆盖；空档不发送
            # reasoning_effort 字段）
            payload = {
                "model": api_client.model_name,
                "messages": [
                    {"role": "user", "content": K12_PROMPT}
                ],
                "max_tokens": 2048,
                "temperature": 0,
                "stream": False,
            }
            if placement == "top":
                # 顶层放置（原始脚本口径）
                payload["chat_template_kwargs"] = {
                    "clear_thinking": True
                }
                if effort is not None:
                    payload["reasoning_effort"] = effort
            else:
                # 嵌套放置（GLM 聊天模版原生口径）
                ctk = {"clear_thinking": True}
                if effort is not None:
                    ctk["reasoning_effort"] = effort
                payload["chat_template_kwargs"] = ctk

            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started

            # 断言0：该放置/档位被支持（不支持通常表现为 400/500）
            assert response.status_code == 200, (
                f"[{label}] 客户问题复现失败：应 200 正常返回（该"
                f"放置/档位不被支持），实际 HTTP "
                f"{response.status_code}: {response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                test_logger.error(
                    f"[{label}] 真实响应体: {response.text[:2000]!r}"
                )
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"[{label}] 响应缺少 choices: {list(result.keys())}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            reasoning = message.get("reasoning_content") or ""
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            # rt 双拼写兼容（仅日志观测，不硬断言）
            rt = usage.get("reasoning_tokens")
            if rt is None:
                details = usage.get("completion_tokens_details") or {}
                rt = details.get("reasoning_tokens")

            TestLogger.log_response(
                test_logger, result, f"K12-响应（{label}）"
            )
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed={elapsed:.1f}s, "
                f"finish={finish}, content_len={len(content)}, "
                f"reasoning_len={len(reasoning)}, rt={rt}, usage="
                f"{json.dumps(usage, ensure_ascii=False)}"
            )

            # 断言1：正文非空且自然结束
            assert content, (
                f"[{label}] 客户问题复现失败：正文为空"
            )
            assert finish == "stop", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"stop，实际 {finish}"
            )

        for label, placement, effort in K12_ROUNDS:
            run_round(label, placement, effort)

        test_logger.info(
            "客户问题复现通过: reasoning_effort 两种"
            "放置（顶层/嵌套 chat_template_kwargs）× 四档"
            "（low/high/max/空）均被正常接受和处理（200+正文正常+"
            "自然结束；各轮 rt/reasoning 长度见日志，档位实际效果"
            "仅观测不硬断言）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53FLASH
    @pytest.mark.KimiK3
    @pytest.mark.p0
    def test_stop_sequence_prefix_leak(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K13 [P0]: 客户问题 - stop 序列遵循且被截断正文前置多余字符

        客户问题：stop=["橘子"] 的流式请求，期望输出 "苹果、香蕉、"
        （正文在停止词处截断、不含停止词），实际输出 ">苹果、香蕉、"
        ——被截断正文前面多输出了一个 ">" 符号（stop 截断逻辑把停
        止词的某个字符/片段泄漏到了正文开头）。
        本用例按客户原始请求体还原（glm-5.3-flash：stream=true、
        thinking={"type": "enabled"}、reasoning_effort="low"、
        stop=["橘子"]、其余采样参数不发送——客户原始请求体即如此
        （test_k 保持原始测试参数，不发送）；KimiK3 环境
        不传 thinking/reasoning_effort/temperature（按 K5 口径），
        断言完全一致。硬断言：
        1. SSE 解析成功且有正文增量（收到 content delta）
        2. finish_reason == "stop"（stop 序列触发，非 length）
        3. 合并正文 == "苹果、香蕉、"（严格等于——多余前缀/停止
        词/未截断均 FAIL）
        4. 正文不含停止词 "橘子"（遵循 stop 语义）
        修复后应 PASS；缺陷存在时（多余 ">" 前缀等）FAIL。usage 仅
        日志。（不进 smoke 集：新用例首跑观察期）
        """
        # K13: 客户原始请求体口径（勿改——缺陷复现的最小充分条件）
        K13_PROMPT = (
            "请依次说出：苹果、香蕉、橘子、西瓜、葡萄。每个水果之间"
            "用顿号分隔，不要省略。"
        )
        K13_STOP = ["橘子"]
        K13_EXPECTED = "苹果、香蕉、"
        # K13: KimiK3 环境不传 thinking/reasoning_effort（按 K5 口径：
        # 网关对 thinking 参数兼容性未知，缺陷本身与其无关）
        K13_IS_GLM53FLASH = (
            "flash" in (api_client.model_name or "").lower()
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - stop 序列遵循且被截断正文前置"
            "多余字符（stop=[\"橘子\"]，期望 \"%s\"，缺陷形态为正文前"
            "多出 \">\" 等多余前缀）===" % K13_EXPECTED
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # 手工构造 payload 直发（需 stop/thinking/reasoning_effort 字
        # 段原样还原，chat_completion 封装不支持这些组合）
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": K13_PROMPT}],
            "stop": list(K13_STOP),
            "stream": True,
        }
        if K13_IS_GLM53FLASH:
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = "low"

        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K13_PROMPT}],
            {
                "stop": K13_STOP,
                "stream": True,
                "thinking": (
                    {"type": "enabled"} if K13_IS_GLM53FLASH else "(不传)"
                ),
                "reasoning_effort": (
                    "low" if K13_IS_GLM53FLASH else "(不传)"
                ),
                "temperature": "(不发送)",
            },
        )

        started = time.time()
        try:
            response = api_client.session.post(
                url,
                json=payload,
                timeout=api_client.timeout,
                stream=True,
            )
        except Exception as e:
            pytest.fail(f"请求发送异常（{url}）: {e}")
        elapsed = time.time() - started

        if response.status_code != 200:
            pytest.fail(
                f"请求失败 HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        # 解析 SSE：合并正文增量，提取 finish_reason 与 usage
        content = ""
        reasoning = ""
        finish = None
        usage: Dict[str, Any] = {}
        events = 0
        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            events += 1
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                content += delta["content"]
            if delta.get("reasoning_content"):
                reasoning += delta["reasoning_content"]
            if choices[0].get("finish_reason"):
                finish = choices[0].get("finish_reason")
            evt_usage = event.get("usage")
            if evt_usage:
                usage.update(evt_usage)

        # 断言0：SSE 解析成功且有正文
        assert events > 0, "未返回任何 SSE 事件"
        assert content, (
            f"流式响应未收到任何正文增量（content 为空），"
            f"reasoning_len={len(reasoning)}, finish={finish}"
        )

        test_logger.info(
            f"HTTP 200, elapsed={elapsed:.1f}s, finish={finish}, "
            f"content={content!r}, content_len={len(content)}, "
            f"reasoning_len={len(reasoning)}, events={events}, "
            f"usage={json.dumps(usage, ensure_ascii=False)}"
        )

        # 断言1：stop 序列触发（非 length/其他）
        assert finish == "stop", (
            f"客户问题复现失败：stop 序列应触发 finish_reason=stop，"
            f"实际 {finish}"
        )

        # 断言2（核心）：合并正文严格等于期望——多余前缀（如 ">"）、
        # 停止词泄漏、未截断均在此检出
        assert content == K13_EXPECTED, (
            f"客户问题复现失败：被截断正文应为 {K13_EXPECTED!r}，"
            f"实际不符（多余前缀/停止词泄漏/未截断）"
        )

        # 断言3：正文不含停止词（stop 语义遵循）
        assert "橘子" not in content, (
            f"客户问题复现失败：正文不应包含停止词 '橘子'"
        )

        test_logger.info(
            "客户问题复现通过: stop 序列遵循且被截断正文无多余前缀"
            "（content 严格等于期望值，finish=stop，不含停止词）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53FLASH
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_orphan_tool_message_rejected(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K14 [P0]: 客户问题 - 孤儿 tool 消息应 HTTP 400 拒绝

        客户问题：messages 中 tool 角色消息前无带 tool_calls 的
        assistant 消息（孤儿 tool 消息，且请求未定义任何 tools），
        属协议非法请求，网关应做校验并返回 400 Bad Request；实际
        返回 200 放行，模型把孤儿 tool 消息当普通上下文推理（流式
        输出 reasoning_content/正文）。
        本用例按客户原始请求体还原（glm-5.3-flash：messages=
        [user "今天天气怎么样？", tool tool_call_id="call_abc123"
        content="{\"weather\":\"晴\"}"]、stream=true、无 tools/
        thinking/采样参数——客户原始请求体即如此（test_k 保持原始
        测试参数，不发送采样参数）；GLM-5.3 与 GLM-5.3-Flash 断言完
        全一致）。硬断言：
        1. HTTP 400（Bad Request，拒绝协议非法请求）
        若 200 放行（缺陷形态）：取样若干 SSE 事件留证后 FAIL。
        修复后应 PASS。响应体与 usage 仅日志。（不进 smoke 集：
        新用例首跑观察期）
        """
        # K14: 客户原始请求体口径（勿改——孤儿 tool 消息的最小充
        # 分条件：user 后直接跟 tool，无前置 assistant tool_calls，
        # 且不定义任何 tools）
        K14_USER_MESSAGE = "今天天气怎么样？"
        K14_TOOL_CALL_ID = "call_abc123"
        K14_TOOL_CONTENT = "{\"weather\":\"晴\"}"
        # K14: 缺陷形态（200 放行）时的 SSE 取证上限（事件数）
        K14_PREVIEW_EVENTS = 8

        test_logger.info(
            "=== 测试开始: 客户问题 - 孤儿 tool 消息校验（tool 消息"
            "前无 assistant tool_calls 且未定义 tools，期望 HTTP 400"
            " 拒绝；缺陷形态为 200 放行并生成）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # 手工构造 payload 直发（含 tool 角色消息，chat_completion
        # 封装不支持；客户原始请求体不发送采样参数）
        payload = {
            "model": api_client.model_name,
            "messages": [
                {"role": "user", "content": K14_USER_MESSAGE},
                {
                    "role": "tool",
                    "tool_call_id": K14_TOOL_CALL_ID,
                    "content": K14_TOOL_CONTENT,
                },
            ],
            "stream": True,
        }

        TestLogger.log_request(
            test_logger,
            [
                {"role": "user", "content": K14_USER_MESSAGE},
                {
                    "role": "tool",
                    "tool_call_id": K14_TOOL_CALL_ID,
                    "content": K14_TOOL_CONTENT,
                },
            ],
            {
                "stream": True,
                "tools": "(未定义)",
                "thinking": "(不传，客户原始请求体口径)",
                "temperature": "(不发送)",
            },
        )

        started = time.time()
        try:
            response = api_client.session.post(
                url,
                json=payload,
                timeout=api_client.timeout,
                stream=True,
            )
        except Exception as e:
            pytest.fail(f"请求发送异常（{url}）: {e}")
        elapsed = time.time() - started

        if response.status_code == 200:
            # 缺陷形态：放行并开始流式生成——取样若干 SSE 事件留证
            preview = ""
            events = 0
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                events += 1
                choices = event.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    if delta.get("reasoning_content"):
                        preview += delta["reasoning_content"]
                    if delta.get("content"):
                        preview += delta["content"]
                if events >= K14_PREVIEW_EVENTS:
                    break
            response.close()
            test_logger.info(
                f"缺陷形态取证: HTTP 200, elapsed={elapsed:.1f}s, "
                f"events={events}, preview={preview[:200]!r}"
            )
            pytest.fail(
                f"客户问题复现失败：孤儿 tool 消息（tool 消息前无 "
                f"assistant tool_calls，且请求未定义 tools）应 HTTP "
                f"400 拒绝，实际 200 放行并生成（SSE 取证 "
                f"events={events}，reasoning/正文预览已记录于测试日志）"
            )

        # 断言（核心）：协议非法请求必须被 400 拒绝
        assert response.status_code == 400, (
            f"客户问题复现失败：孤儿 tool 消息应 HTTP 400（Bad "
            f"Request），实际 HTTP {response.status_code}: "
            f"{response.text[:300]}"
        )

        test_logger.info(
            f"HTTP 400, elapsed={elapsed:.1f}s, body="
            f"{response.text[:300]!r}"
        )
        test_logger.info(
            "客户问题复现通过: 孤儿 tool 消息被 HTTP 400 拒绝（tool "
            "消息前无 assistant tool_calls 的协议非法请求未放行）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.GLM53FLASH
    @pytest.mark.p0
    def test_short_input_prefix_cache_threshold(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K15 [P0]: 客户问题 - 细粒度前缀匹配短输入缓存阈值

        客户问题：vLLM 分块撮合后最小缓存块长 640 tok，用户输入
        625 tok 不被缓存（短输入缓存失效）。修复：开启细粒度前缀
        匹配，单一缓存块内补充更细粒度的缓存点（--prefix-match-
        unit 64）。
        本用例验证修复后的缓存粒度行为（两个测试点，OpenAI 协议
        非流式，cached_tokens 取自 usage.prompt_tokens_details.
        cached_tokens，兼容 usage.cached_tokens 拼写）：
        1. 用户输入 64 < N < 640：第二次相同请求应正常缓存
           （cached_tokens > 0；修复前 640 粒度下为 0——即客户
           625 tok 不缓存场景）
        2. 用户输入 N < 64：不缓存（cached_tokens == 0，低于最细
           匹配粒度 64 tok 不可缓存）
        前置自检（硬断言）：实际输入规模以服务端 usage.prompt_
        tokens 为准，须落在对应区间——内容长度估算漂移导致前提
        失效时 FAIL 并提示调整常量。usage 其余字段仅日志。（不进
        smoke 集：新用例首跑观察期）
        """
        # K15: 测试点1 内容（~480 中文字符 ≈ 280-320 tok，落于
        # 64 < N < 640 区间中部，两侧留裕量）
        K15_MID_UNIT = "本知识库涵盖产品规格、接口说明与常见问题处理流程。"
        K15_MID_CONTENT = K15_MID_UNIT * 20
        # K15: 测试点2 内容（~21 中文字符，含对话模板开销 < 64 tok）
        K15_SHORT_CONTENT = "请简要介绍北京的历史文化背景与著名景点。"

        test_logger.info(
            "=== 测试开始: 客户问题 - 细粒度前缀匹配短输入缓存阈值"
            "（--prefix-match-unit 64；测试点1: 64<N<640 应缓存，"
            "测试点2: N<64 应不缓存）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def usage_round(content: str, label: str) -> Dict[str, Any]:
            """K15 单轮：发送请求并返回 usage（OpenAI 协议非流式）"""
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": content}],
                "max_tokens": 16,
                "stream": False,
            }
            TestLogger.log_request(
                test_logger,
                [
                    {
                        "role": "user",
                        "content": f"[{len(content)} 字符] {content[:30]}…",
                    }
                ],
                {
                    "max_tokens": 16,
                    "stream": False,
                    "temperature": "(不发送)",
                    "round": label,
                },
            )
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            assert response.status_code == 200, (
                f"[{label}] 请求失败 HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(f"[{label}] 响应不是合法 JSON: {e}")
            usage = result.get("usage") or {}
            TestLogger.log_response(
                test_logger, result, f"K15-响应（{label}）"
            )
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed="
                f"{time.time() - started:.1f}s, usage="
                f"{json.dumps(usage, ensure_ascii=False)}"
            )
            return usage

        def cached_of(usage: Dict[str, Any]):
            """取缓存命中 tokens（prompt_tokens_details.cached_tokens
            优先，兼容 usage.cached_tokens 拼写）"""
            details = usage.get("prompt_tokens_details") or {}
            value = details.get("cached_tokens")
            if value is None:
                value = usage.get("cached_tokens")
            return value

        # ---- 测试点 1：64 < N < 640，第二次相同请求应正常缓存 ----
        usage_round(K15_MID_CONTENT, "测试点1-第1次（建缓存）")
        usage2 = usage_round(K15_MID_CONTENT, "测试点1-第2次（相同请求）")
        pt1 = usage2.get("prompt_tokens")
        assert isinstance(pt1, int) and 64 < pt1 < 640, (
            f"测试点1 前提失效：实际输入 {pt1} tok 不在 (64, 640) 区"
            f"间（内容长度估算漂移），请调整 K15_MID_CONTENT 重复次"
            f"数（当前 usage={usage2}）"
        )
        cached1 = cached_of(usage2) or 0
        assert cached1 > 0, (
            f"客户问题复现失败：用户输入 {pt1} tok（64<N<640）第二次"
            f"相同请求应正常缓存（--prefix-match-unit 64 细粒度前缀"
            f"匹配生效），实际 cached_tokens={cached1}（640 最小缓存"
            f"块长未修复——即客户 625 tok 不缓存场景，usage={usage2}）"
        )

        # ---- 测试点 2：N < 64，应不缓存 ----
        usage_round(K15_SHORT_CONTENT, "测试点2-第1次")
        usage4 = usage_round(K15_SHORT_CONTENT, "测试点2-第2次（相同请求）")
        pt2 = usage4.get("prompt_tokens")
        assert isinstance(pt2, int) and pt2 < 64, (
            f"测试点2 前提失效：实际输入 {pt2} tok 不小于 64（内容长"
            f"度估算漂移），请缩短 K15_SHORT_CONTENT（当前 "
            f"usage={usage4}）"
        )
        cached2 = cached_of(usage4) or 0
        assert cached2 == 0, (
            f"测试点2 断言失败：用户输入 {pt2} tok（<64，低于最细匹"
            f"配粒度）应不缓存，实际 cached_tokens={cached2}（"
            f"usage={usage4}）"
        )

        test_logger.info(
            f"客户问题复现通过: 细粒度前缀匹配生效（输入 {pt1} tok "
            f"缓存 {cached1} tok；输入 {pt2} tok 不缓存——低于最细"
            f"粒度 64 tok）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.GLM53FLASH
    @pytest.mark.p0
    def test_prefix_cache_hit_rate_threshold(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K16 [P0]: 客户问题 - 固定前缀/多轮上下文缓存命中率达标

        客户问题：短文本缓存命中率不达标（原始验证：固定前缀
        88.35%、多轮上下文 87.16%/87.14%，目标 90%）——根因同
        K15（vLLM 640 tok 最小缓存块长），修复（--prefix-match-
        unit 64）后命中率应达标。
        请求规模由原始信息推算（原始 fixed_prefix: 每轮 cached=
        7680、input=8693、实测 9 轮、排除 1 轮预热）：共享前缀
        ≈8192 tok（640 粒度截断为 12×640=7680，损失 512）+ 每轮
        新增问题 ≈501 tok——即 ~12800 中文字符前缀 + ~780 字符/
        轮问题。修复后预期固定前缀命中率 ≈8192/8693≈94.2%≥90%
        （修复前 7680/8693≈88.35%<90%）。
        两种模式（OpenAI 协议非流式，cached_tokens 取自 usage.
        prompt_tokens_details.cached_tokens，兼容 usage.cached_
        tokens 拼写）：
        1. 固定前缀：10 轮独立请求（同一 ~8192 tok 系统前缀 + 每
           轮唯一 ~501 tok 问题），第 1 轮为预热不计入
        2. 多轮上下文：同一会话逐轮追加（前缀 + 历史问答 + 新问
           题，回复极短），第 1 轮为预热不计入
        断言：两模式实测命中率 = Σcached_tokens / Σprompt_tokens
        （各 9 轮实测）均 ≥ 90%，任一 < 90% 即 FAIL。usage 其余
        字段仅日志；零命中轮次记录留痕（zero_cache_rounds）。
        （不进 smoke 集：新用例首跑观察期）
        """
        K16_TARGET_RATE = 0.9
        K16_ROUNDS = 10
        K16_WARMUP_ROUNDS = 1
        # K16: 共享前缀 ~8192 tok（由原始信息推算：640 粒度下每轮
        # 命中 7680 = 12×640，前缀 8192 截断损失 512）
        K16_PREFIX_FILLER_UNIT = (
            "本知识库涵盖产品规格、接口说明、计费策略、常见问题与"
            "处理流程，供客服助手检索引用。"
        )
        K16_PREFIX_TARGET_CHARS = 12800  # ≈8192 tok（中文 ~1.55 字符/tok）
        K16_PREFIX_TEXT = K16_PREFIX_FILLER_UNIT * (
            K16_PREFIX_TARGET_CHARS // len(K16_PREFIX_FILLER_UNIT) + 1
        )
        # K16: 每轮问题 ~501 tok（input 8693 - 前缀 8192）
        K16_QUESTION_FILLER = (
            "补充材料：客户在部署与验收阶段需核对接口说明、计费策略"
            "与规格参数，涉及多部门协作、流程审批与回归验证节点，请"
            "结合知识库内容作答。"
        ) * 11

        def question_for(k: int, brief_reply: bool) -> str:
            """每轮唯一问题（轮次号保证前缀在问题开头处分叉）"""
            text = (
                f"检索问题（第 {k} 轮）：请在上述知识库中定位与第 "
                f"{k} 号主题相关的条目，归纳其适用范围、注意事项与"
                f"处理流程，并给出要点摘要。" + K16_QUESTION_FILLER
            )
            if brief_reply:
                text += "本轮请仅回复：收到。"
            return text

        test_logger.info(
            "=== 测试开始: 客户问题 - 固定前缀/多轮上下文缓存命中率"
            "达标（目标 ≥90%；前缀 ~8192 tok + 每轮新增 ~501 tok，"
            "各 10 轮排除 1 轮预热实测 9 轮，由原始信息推算）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def cached_of(usage: Dict[str, Any]):
            """取缓存命中 tokens（prompt_tokens_details.cached_tokens
            优先，兼容 usage.cached_tokens 拼写）"""
            details = usage.get("prompt_tokens_details") or {}
            value = details.get("cached_tokens")
            if value is None:
                value = usage.get("cached_tokens")
            return value

        def completion_round(
            messages: List[Dict[str, Any]], label: str
        ) -> Dict[str, Any]:
            """K16 单轮：发送请求并返回完整响应（非流式）"""
            payload = {
                "model": api_client.model_name,
                "messages": messages,
                "max_tokens": 16,
                "stream": False,
            }
            logged = []
            for m in messages:
                content = m.get("content") or ""
                logged.append(
                    {
                        "role": m.get("role"),
                        "content": (
                            f"[{len(content)} 字符] {content[:30]}…"
                            if len(content) > 60
                            else content
                        ),
                    }
                )
            TestLogger.log_request(
                test_logger,
                logged,
                {
                    "max_tokens": 16,
                    "stream": False,
                    "temperature": "(不发送)",
                    "round": label,
                },
            )
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{label}] 请求发送异常（{url}）: {e}")
            assert response.status_code == 200, (
                f"[{label}] 请求失败 HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(f"[{label}] 响应不是合法 JSON: {e}")
            TestLogger.log_response(
                test_logger, result, f"K16-响应（{label}）"
            )
            usage = result.get("usage") or {}
            test_logger.info(
                f"[{label}]: HTTP 200, elapsed="
                f"{time.time() - started:.1f}s, pt="
                f"{usage.get('prompt_tokens')}, cached="
                f"{cached_of(usage)}"
            )
            return result

        # ---- 模式 1：固定前缀（10 轮独立请求，同一前缀 + 唯一问题） ----
        fixed_pt_sum = 0
        fixed_cached_sum = 0
        fixed_zero_rounds = []
        for k in range(1, K16_ROUNDS + 1):
            messages = [
                {"role": "system", "content": K16_PREFIX_TEXT},
                {"role": "user", "content": question_for(k, False)},
            ]
            usage = (
                completion_round(messages, f"固定前缀-第{k}轮").get(
                    "usage"
                )
                or {}
            )
            if k > K16_WARMUP_ROUNDS:
                fixed_pt_sum += usage.get("prompt_tokens") or 0
                fixed_cached_sum += cached_of(usage) or 0
                if not cached_of(usage):
                    fixed_zero_rounds.append(k)
        measured = K16_ROUNDS - K16_WARMUP_ROUNDS
        fixed_rate = (
            fixed_cached_sum / fixed_pt_sum if fixed_pt_sum else 0.0
        )
        test_logger.info(
            f"固定前缀: rate={fixed_rate:.4f}, Σcached="
            f"{fixed_cached_sum}, Σinput={fixed_pt_sum}, 实测 "
            f"{measured} 轮, zero_cache_rounds={fixed_zero_rounds}"
        )
        assert fixed_rate >= K16_TARGET_RATE, (
            f"客户问题复现失败：固定前缀缓存命中率 {fixed_rate:.2%} "
            f"未达标（目标 ≥90%；Σcached={fixed_cached_sum}, "
            f"Σinput={fixed_pt_sum}, 实测 {measured} 轮, "
            f"zero_cache_rounds={fixed_zero_rounds}；对照原始验证 "
            f"88.35%<90%——640 粒度截断未修复）"
        )

        # ---- 模式 2：多轮上下文（同一会话逐轮追加） ----
        history: List[Dict[str, Any]] = [
            {"role": "system", "content": K16_PREFIX_TEXT}
        ]
        mt_pt_sum = 0
        mt_cached_sum = 0
        mt_zero_rounds = []
        for k in range(1, K16_ROUNDS + 1):
            question = question_for(k, True)
            messages = history + [
                {"role": "user", "content": question}
            ]
            result = completion_round(messages, f"多轮上下文-第{k}轮")
            usage = result.get("usage") or {}
            choices = result.get("choices") or []
            reply = "收到。"
            if choices:
                reply = (
                    (choices[0].get("message") or {}).get("content")
                    or "收到。"
                )
            history = history + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": reply},
            ]
            if k > K16_WARMUP_ROUNDS:
                mt_pt_sum += usage.get("prompt_tokens") or 0
                mt_cached_sum += cached_of(usage) or 0
                if not cached_of(usage):
                    mt_zero_rounds.append(k)
        mt_rate = mt_cached_sum / mt_pt_sum if mt_pt_sum else 0.0
        test_logger.info(
            f"多轮上下文: rate={mt_rate:.4f}, Σcached="
            f"{mt_cached_sum}, Σinput={mt_pt_sum}, 实测 {measured} "
            f"轮, zero_cache_rounds={mt_zero_rounds}"
        )
        assert mt_rate >= K16_TARGET_RATE, (
            f"客户问题复现失败：多轮上下文缓存命中率 {mt_rate:.2%} "
            f"未达标（目标 ≥90%；Σcached={mt_cached_sum}, "
            f"Σinput={mt_pt_sum}, 实测 {measured} 轮, "
            f"zero_cache_rounds={mt_zero_rounds}；对照原始验证 "
            f"87.16%<90%——640 粒度截断未修复）"
        )

        test_logger.info(
            f"客户问题复现通过: 缓存命中率全部达标——固定前缀 "
            f"{fixed_rate:.2%}、多轮上下文 {mt_rate:.2%}（目标 90%，"
            f"Σcached/Σinput 各实测 {measured} 轮、排除 "
            f"{K16_WARMUP_ROUNDS} 轮预热）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_stop_newline_in_reasoning(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K17 [P0]: 客户问题 - stop 停止符（换行符）在推理阶段生效

        客户契约：指定停止符为换行符 "\n" 并开启思考时，停止符同样
        作用于推理（reasoning）输出——推理里出现的第一个换行即触发
        停止，正文（content）不会生成；反之若换行未触发停止、继续
        输出正文，则换行符未生效，用例 FAIL。
        本用例按该场景构造（GLM-5.3：thinking={"type":"enabled"}
        显式开启思考（K1 口径））：
        - stream=true、stop=["\n"]、max_tokens=512（防御性预算——
          正常应在推理早期几十个 token 内触发停止，仅防缺陷形态下
          无界生成）
        - 其余采样参数不发送（test_k 保持原始测试参数——工单原始
          请求未指定，不发送）
        硬断言：
        1. SSE 解析成功（收到事件）
        2. 合并正文为空（stop 在推理阶段触发，正文未生成——核心：
           若收到正文即换行符未生效）
        3. finish_reason == "stop"（停止符触发，非 length）
        4. 合并 reasoning 不含 "\n"（stop 语义：输出在停止符前截
           断、停止符不泄漏到输出）
        模型真实响应（合并正文/思考全文、finish、usage）在断言前打
        印到日志（失败时同样可见，便于诊断）。usage 仅日志。
        （不进 smoke 集：新用例首跑观察期）
        """
        # K17: 场景常量（思考开启下推理输出自然含换行——第一个换行
        # 即应触发停止，正文不生成）
        K17_PROMPT = "请简要介绍量子计算的基本概念与应用前景。"
        K17_STOP = ["\n"]
        K17_MAX_TOKENS = 512  # 防御性预算，见 docstring

        test_logger.info(
            "=== 测试开始: 客户问题 - stop 停止符（换行符）在推理阶段"
            "生效（stop=[\"\\n\"]，推理中第一个换行即触发停止、正文"
            "不生成；缺陷形态为换行未停止且继续输出正文）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # 手工构造 payload 直发（需 stop/thinking 字段原样还原，
        # chat_completion 封装不支持这些组合）
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": K17_PROMPT}],
            "stop": list(K17_STOP),
            "stream": True,
            "max_tokens": K17_MAX_TOKENS,
            "thinking": {"type": "enabled"},
        }

        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K17_PROMPT}],
            {
                "stop": K17_STOP,
                "stream": True,
                "max_tokens": K17_MAX_TOKENS,
                "thinking": {"type": "enabled"},
                "temperature": "(不发送)",
            },
        )

        started = time.time()
        try:
            response = api_client.session.post(
                url,
                json=payload,
                timeout=api_client.timeout,
                stream=True,
            )
        except Exception as e:
            pytest.fail(f"请求发送异常（{url}）: {e}")
        elapsed = time.time() - started

        if response.status_code != 200:
            pytest.fail(
                f"请求失败 HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )

        # 解析 SSE：合并正文/思考增量，提取 finish_reason 与 usage
        # （口径同 K13）
        content = ""
        reasoning = ""
        finish = None
        usage: Dict[str, Any] = {}
        events = 0
        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            events += 1
            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                content += delta["content"]
            if delta.get("reasoning_content"):
                reasoning += delta["reasoning_content"]
            if choices[0].get("finish_reason"):
                finish = choices[0].get("finish_reason")
            evt_usage = event.get("usage")
            if evt_usage:
                usage.update(evt_usage)

        # 模型真实响应信息（用户要求打印；置于断言前——失败时日志
        # 中同样可见，便于诊断）
        test_logger.info(
            f"K17 真实响应 - HTTP 200, elapsed={elapsed:.1f}s, "
            f"finish={finish}, events={events}, usage="
            f"{json.dumps(usage, ensure_ascii=False)}"
        )
        test_logger.info(
            f"K17 真实响应 - 合并正文({len(content)} 字符): {content!r}"
        )
        test_logger.info(
            f"K17 真实响应 - 合并思考({len(reasoning)} 字符): "
            f"{reasoning!r}"
        )

        # 断言0：SSE 解析成功
        assert events > 0, "未返回任何 SSE 事件"

        # 断言1（核心）：正文未生成——stop 应在推理阶段的第一个换行
        # 处触发，正文不应出现（收到正文即换行符未生效）
        assert content == "", (
            f"客户问题复现失败：stop=[\"\\n\"] 应在推理阶段的第一个"
            f"换行处触发停止、正文不应生成，实际收到正文"
            f"（长度 {len(content)}）——换行符未生效"
            f"（推理继续并输出了正文；reasoning_len={len(reasoning)}, "
            f"finish={finish}）"
        )

        # 断言2：stop 触发（非 length/其他）
        assert finish == "stop", (
            f"客户问题复现失败：换行停止符应触发 finish_reason=stop，"
            f"实际 {finish}（reasoning_len={len(reasoning)}）"
        )

        # 断言3：合并 reasoning 不含换行（停止符前截断、不泄漏）
        assert "\n" not in reasoning, (
            f"客户问题复现失败：stop=[\"\\n\"] 下输出应在第一个换行"
            f"前截断，合并 reasoning 中出现换行（{len(reasoning)} "
            f"字符）——推理中的换行"
            f"未触发停止（停止符泄漏/未作用于推理）"
        )

        test_logger.info(
            "客户问题复现通过: 换行停止符在推理阶段生效（推理中第一"
            "个换行触发停止，正文未生成，reasoning 中无换行泄漏）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_output_json_as_input_context(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K18 [P0]: 客户问题 - 模型输出 JSON 可回填为下次请求输入上下文

        客户问题（AGDC2-28）：上次请求输出的 assistant JSON 作为下次
        请求的输入上下文提交即报错——"Failed to deserialize the
        JSON body into the target type: missing field `name`"。触
        发形态（docx 原样还原）：助手历史 tool_calls 混有
        1) 空占位调用：function.name=""、id=null、arguments="{}"
           （报错 missing field `name` 即指向它；按客户 agent
           两步流程，该调用即第一步"输出 JSON 到 *.json 文件"，
           其 name/id 在返回数据中丢失）——模型侧修复已明确任
           何情况下不返回空 function，本用例按用户指定不再保留
           该空 function 场景（回放数据中已移除）；
        2) 真实 bash 调用：name="bash"、id="call_8af1ab36a4154c25"，
            arguments 为 '"command":"cd ... ", "description":
            "..."}'——缺开头 "{"、非合法 JSON（命令为运行绘图脚本
            并读取/复制第一步输出的 skill_weekly.json；内部
            data,json、SKlLL 等怪字符均为工单原文，原样保留）。
        修复逻辑（router 侧，SMG 1.13.0）：解析失败后，同列表还
        有其他真实调用时移除空占位项、保留真实调用再重新校验；
        缺 "{" 的 arguments 原样保留（不补 "{"——通过 router 不
        代表该字符串成为合法参数 JSON）；兼容 assistant 历史重复
        的 reasoning_content/reasoning_context（保留最后一个
        值）。注：模型侧根上解决（任何情况下不返回空 function）
        生效后，空占位场景不再产生——本用例回放历史仅保留真实
        bash 调用（缺 "{" arguments 原样）+ reasoning 双字段（用
        户指定），验证剩余契约：含真实工具调用的上次输出可回填
        为下次请求输入上下文。
        后续问题（开发文档，SMG 1.13.0 修复上线后引出）：不再报
        missing field `name`，但出现新问题——"messages[141].
        tool_call_id must reference an unanswered tool call in
        the preceding assistant message"。根本原因：模型返回了
        一个空的 function（id=null）——客户端工具执行后回填错
        误结果：真实调用因 arguments 缺 "{" 无法执行（错误结果
        以其真实 id 回填），空 function 因 id=null 被客户端以
        tool_call_id="missing_tool_call_id" 回填；再次请求时该
        悬空 tool_call_id 不指向任何未应答调用，被协议校验拒绝。
        根上解决（开发建议）：模型不要返回空的 function——不同
        客户端工具处理结果的方式不同。
        本用例按客户 agent 两步流程还原（用户指定测试逻辑），并
        追加根因断言请求：
        - 第一个请求：模型直接输出技能周报数据 JSON（示例记录，
          无需真实数据），测试代为执行"输出 JSON 到 *.json 文
          件"——写入测试脚本同级目录下的临时文件
          k18_temp_skill_weekly.json；
        - 第二个请求：测试代为执行 bash 工具读取该临时 JSON 文件
          （读取第一个请求输出的 json 文件），将工单原始 assistant
          返回数据（真实 bash 调用（arguments 缺 "{"）+reasoning
          双字段并存——空占位调用已按用户指定移除）与读到的文件
          内容一并回填为输入上下文：user → assistant(返回数据) →
          tool(工具读取结果——协议必需：assistant 带 tool_calls
          后必须紧跟匹配 tool_call_id 的工具结果消息，实测缺失被
          400 拒绝 messages[2] missing tool results) → user 追问，
          带 bash 工具定义，非流式；
        - 第三个请求（根因断言）：复刻工单首个 user 回合（同一消
          息、带 bash 工具定义）——工单中模型在该回合输出了空占
          位调用与畸形 bash arguments，断言本次模型输出的每条工
          具调用结构完整；
        - 测试完成后删除生成的临时 JSON 文件（finally 兜底，断言
          失败同样清理）。
        硬断言：
        1. 第一个请求 HTTP 200 且正文可提取合法 JSON 对象（第一
           步契约：输出 JSON 到文件）
        2. 工具读取临时 JSON 文件成功（回读 json 与输出一致）
        3. 第二个请求 HTTP 200（核心——上次输出 JSON 必须可作为
           下次请求的输入上下文，报错复现即 FAIL）
        4. choices 存在且非空 + message 结构存在（响应可正常生成）
        5. 第三个请求 HTTP 200 且模型发起工具调用（生成图表必须
           执行绘图脚本——工单场景中模型对该消息即发起 bash 调
           用；纯文本回答无法覆盖根因），每条调用 name 非空、id
           非空、arguments 为合法 JSON 对象（根因断言：模型不得
           返回空 function；同时覆盖工单同款畸形 arguments 缺
           "{" 的模型输出缺陷）
        明确不断言：arguments 被补 "{"（修复明确不补——通过
        router 不代表该字符串成为合法参数 JSON）。响应形态（正
        文/继续调用工具）宽松留日志——测试要点是上下文被接受。
        docx 中 role 拼写 "assitant" 判定为笔误（报错与修复均不涉
        及 role），按标准 assistant 还原。reasoning 同键字面重复
        无法经 dict 表达，以 reasoning_content + reasoning_context
        两拼写并存覆盖兼容路径。GLM-5.3 专用；采样参数不发送——
        test_k 保持原始测试参数（工单原始请求未指定，不注入），
        三个请求一致。usage 仅日志。
        （不进 smoke 集：新用例首跑观察期）
        """
        # K18: 工单原始 bash 调用 arguments（缺开头 "{"、非合法
        # JSON；内部 data,json/SKlLL 等怪字符均为工单原文，原样保留）
        K18_BASH_ARGS = (
            '"command":"cd /mnt/user-data/workspace/gb-audit && '
            'python3 plot_skill.py && cp skill_weekly.json '
            '/mnt/user-data/outputs/gammabull_skill_events_data,'
            'json && ls -la /mnt/user-data/outputs/", '
            '"description": "Render SKlLL chart and copy evidence '
            'data"}'
        )
        # K18: bash 工具定义（agent 场景——模型输出调用了 bash，请
        # 求必然定义了该工具）
        K18_TOOLS = [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": (
                        "Run a shell command in the workspace"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["command"],
                    },
                },
            }
        ]
        # K18: 按工单还原的 assistant 历史消息（上次请求的输出 JSON）
        # ——真实 bash 调用（arguments 缺 "{"、非合法 JSON，原样保
        # 留）+ reasoning 双拼写并存（重复 reasoning 字段兼容路
        # 径）；工单中的空占位调用（name=""、id=null）不再保留—
        # —模型侧修复已明确任何情况下不返回空 function（用户指
        # 定：不保留空 function 场景）
        K18_ASSISTANT = {
            "role": "assistant",
            "content": None,
            "reasoning_content": (
                "先分析工作区数据结构，再规划绘图步骤。"
            ),
            "reasoning_context": (
                "已确认数据文件位置，准备调用 bash 执行绘图脚本。"
            ),
            "tool_calls": [
                {
                    "function": {
                        "arguments": K18_BASH_ARGS,
                        "name": "bash",
                    },
                    "id": "call_8af1ab36a4154c25",
                    "type": "function",
                },
            ],
        }
        # K18: 第二个请求（返回数据回填上下文）预算——工单口径
        K18_MAX_TOKENS = 512
        # K18: 第一个请求提示词——按客户 agent 流程第一步"输出
        # JSON 到 *.json 文件"：让模型直接输出技能周报数据 JSON
        #（不带工具定义——直接输出 JSON 才可确定性落盘）；明确
        # 无需真实数据、构造示例记录——真实首跑曾因"无工作区数
        # 据"拒绝虚构，输出 error:no_workspace_data 致落盘内容
        # 语义不符且随模型版本不稳定
        K18_REQ1_PROMPT = (
            "请生成技能周报数据：无需基于真实数据，请直接构造 3-5 "
            "条示例技能记录并输出为一个 JSON 对象，每条含技能名称"
            "（skill）、本周事件数（events）、评分（score）字段；"
            '以 { 开头、以 } 结尾，不要使用 markdown 代码块，不要'
            "输出 JSON 以外的任何内容。"
        )
        # K18: 第一个请求预算——简单数据生成任务，2048 留足思考
        # 预算余量（防御正文被思考耗光）
        K18_REQ1_MAX_TOKENS = 2048
        # K18: 临时 JSON 文件名——第一个请求"输出 JSON 到 *.json
        # 文件"的落盘产物（测试脚本同级目录下，对应工单中的
        # skill_weekly.json），测试完成后删除
        K18_TEMP_FILE_NAME = "k18_temp_skill_weekly.json"
        # K18: 第二个请求工具结果消息携带文件内容的防御性截断上限
        K18_FILE_CONTEXT_LIMIT = 3000
        # K18: 工单首个 user 回合消息（工单原文）——第二个请求历
        # 史第 0 条与第三个请求（根因断言）复用同一消息
        K18_CHART_PROMPT = "请分析工作区数据并生成技能周报图表。"
        # K18: 第三个请求（根因断言）预算——工具调用生成任务，
        # 2048 留足思考预算余量（同第一个请求防御口径）
        K18_REQ3_MAX_TOKENS = 2048

        test_logger.info(
            "=== 测试开始: 客户问题 - 模型输出 JSON 回填为下次请求"
            "输入上下文（两步流程+根因断言：第一个请求输出临时 JSON "
            "文件 → 第二个请求调用工具读取后回填上下文 → 第三个请"
            "求断言模型不返回空 function；assistant 历史含缺 \"{\" "
            "的 bash arguments/reasoning 双字段（空占位调用已按用户"
            "指定移除——模型侧修复后不保留空 function 场景）；修复"
            "后应被接受，报错复现即 FAIL）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # 手工构造 payload 直发（需按工单原样还原 assistant 历史怪
        # 异结构，chat_completion 封装不支持）；采样参数不发送——
        # test_k 保持原始测试参数（工单原始请求未指定，不注入），
        # 三个请求一致

        temp_file = Path(__file__).with_name(K18_TEMP_FILE_NAME)
        try:
            # ---- 第一个请求：模型输出技能周报数据 JSON ----
            req1_payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [
                    {"role": "user", "content": K18_REQ1_PROMPT}
                ],
                "max_tokens": K18_REQ1_MAX_TOKENS,
                "stream": False,
            }
            TestLogger.log_request(
                test_logger,
                req1_payload["messages"],
                {
                    "max_tokens": K18_REQ1_MAX_TOKENS,
                    "temperature": "(不发送)",
                    "top_p": "(不发送)",
                    "seed": "(不发送)",
                    "stream": False,
                    "step": (
                        "第一个请求（输出技能周报数据 JSON，落盘临时"
                        "文件）"
                    ),
                },
            )
            started1 = time.time()
            try:
                response1 = api_client._post_with_retry(
                    url, req1_payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"第一个请求发送异常（{url}）: {e}")
            elapsed1 = time.time() - started1
            # 模型真实响应断言前打印（失败时同样可见）
            test_logger.info(
                f"第一个请求真实响应: HTTP {response1.status_code}, "
                f"elapsed={elapsed1:.1f}s, "
                f"body={response1.text[:800]!r}"
            )
            # 断言1a：第一个请求本身应成功（第一步：输出 JSON）
            assert response1.status_code == 200, (
                f"第一个请求失败：模型应输出技能周报数据 JSON，实际 "
                f"HTTP {response1.status_code}: {response1.text[:400]}"
            )
            try:
                result1 = response1.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"第一个请求响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices1 = result1.get("choices") or []
            assert choices1, (
                f"第一个请求响应缺少 choices: {list(result1.keys())}"
            )
            message1 = choices1[0].get("message")
            assert isinstance(message1, dict), (
                f"第一个请求响应 message 结构缺失: {list(result1.keys())}"
            )
            content1 = message1.get("content") or ""
            finish1 = choices1[0].get("finish_reason")
            TestLogger.log_response(
                test_logger, result1, "K18-第一个请求响应"
            )
            # 断言1b：正文非空且可提取合法 JSON 对象（容忍 markdown
            # 代码块围栏/前后杂文——提取最外层 {...}）
            assert content1.strip(), (
                f"第一个请求正文为空（finish={finish1}），无法输出 "
                f"JSON 到临时文件"
            )
            json_start = content1.find("{")
            json_end = content1.rfind("}")
            assert json_start != -1 and json_end > json_start, (
                "第一个请求正文中未找到 JSON 对象"
            )
            try:
                skill_data = json.loads(
                    content1[json_start : json_end + 1]
                )
            except json.JSONDecodeError as e:
                pytest.fail(
                    f"第一个请求输出的 JSON 对象解析失败: {e}. "
                    f"正文已记录于测试日志"
                )
            # 第一步落盘：输出 JSON 到测试脚本同级目录下的临时文件
            #（测试代为执行"输出 JSON 到 *.json 文件"的工具语义）
            temp_file.write_text(
                json.dumps(skill_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            test_logger.info(
                f"第一步完成: 第一个请求输出 JSON 已写入临时文件 "
                f"{temp_file}"
            )

            # ---- 工具读取：bash 读取第一个请求输出的 JSON 文件 ----
            #（测试代为执行第二个请求上下文中 bash 工具调用的读取
            # 语义——工单 bash 命令即读取/复制 skill_weekly.json）
            assert temp_file.exists(), (
                f"临时 JSON 文件未生成: {temp_file}"
            )
            try:
                file_text = temp_file.read_text(encoding="utf-8")
                file_data = json.loads(file_text)
            except (OSError, json.JSONDecodeError) as e:
                pytest.fail(
                    f"工具读取临时 JSON 文件失败（{temp_file}）: {e}"
                )
            # 断言2：临时 JSON 文件回读成功且与第一个请求输出一致
            if file_data != skill_data:
                test_logger.error(
                    f"临时 JSON 文件回读内容与第一个请求输出不一致，"
                    f"file_text: {file_text[:2000]!r}"
                )
            assert file_data == skill_data, (
                "临时 JSON 文件回读内容与第一个请求输出不一致"
                "（文件内容已记录于测试日志）"
            )
            test_logger.info(
                f"第二步完成: 工具已读取第一个请求输出的临时 JSON "
                f"文件 {temp_file}（{len(file_text)} 字符）: "
                f"{file_text[:400]!r}"
            )

            # ---- 第二个请求：返回数据回填为输入上下文（核心断言） ----
            # 协议必需：assistant 带 tool_calls 后必须紧跟匹配
            # tool_call_id 的 role=tool 工具结果消息——实测缺失被
            # 400 拒绝（messages[2]: missing tool results for
            # preceding assistant tool_calls）；工具读取到的文件内
            # 容经 tool 消息携带（协议原生位置——原 user 追问携带
            # 方案不满足工具结果配对约束，已被服务端拒绝证伪）
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": K18_CHART_PROMPT,
                    },
                    K18_ASSISTANT,
                    {
                        "role": "tool",
                        "tool_call_id": "call_8af1ab36a4154c25",
                        "content": file_text[:K18_FILE_CONTEXT_LIMIT],
                    },
                    {"role": "user", "content": "请继续完成任务。"},
                ],
                "tools": K18_TOOLS,
                "max_tokens": K18_MAX_TOKENS,
                "stream": False,
            }
            TestLogger.log_request(
                test_logger,
                payload["messages"],
                {
                    "tools": [t["function"]["name"] for t in K18_TOOLS],
                    "max_tokens": K18_MAX_TOKENS,
                    "temperature": "(不发送)",
                    "top_p": "(不发送)",
                    "seed": "(不发送)",
                    "stream": False,
                    "step": (
                        "第二个请求（工具读取 JSON 文件后回填上下文）"
                    ),
                    "assistant_history": (
                        "bash 调用(arguments 缺 \"{\") + reasoning "
                        "双字段（空占位调用已按用户指定移除）"
                    ),
                    "temp_file": str(temp_file),
                },
            )
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"第二个请求发送异常（{url}）: {e}")
            elapsed = time.time() - started
            # 模型真实响应断言前打印（失败时同样可见）
            test_logger.info(
                f"第二个请求真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, "
                f"body={response.text[:800]!r}"
            )
            # 断言3（核心）：上次输出 JSON 可作为下次请求输入上下文
            # ——历史含缺 "{" 的 bash arguments 与 reasoning 双字
            # 段（空占位调用已按用户指定移除），被拒绝即 FAIL
            assert response.status_code == 200, (
                f"客户问题复现失败：上次请求输出的 assistant JSON 应可"
                f"作为下次请求的输入上下文，实际 HTTP "
                f"{response.status_code}（历史含缺 \"{{\" 的 bash "
                f"arguments 与 reasoning 双字段；空占位调用已按用户"
                f"指定移除——模型侧修复后不保留空 function 场景）: "
                f"{response.text[:400]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"第二个请求响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            # 断言4：choices 存在（上下文被接受且正常生成）
            choices = result.get("choices") or []
            assert choices, (
                f"第二个请求响应缺少 choices: {list(result.keys())}"
            )
            message = choices[0].get("message")
            assert isinstance(message, dict), (
                f"第二个请求响应 message 结构缺失: {list(result.keys())}"
            )

            content = message.get("content") or ""
            tool_calls = message.get("tool_calls")
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            TestLogger.log_response(
                test_logger, result, "K18-第二个请求响应"
            )
            test_logger.info(
                f"HTTP 200, elapsed={elapsed:.1f}s, finish={finish}, "
                f"content_len={len(content)}, tool_calls="
                f"{'有' if tool_calls else '无'}, usage="
                f"{json.dumps(usage, ensure_ascii=False)}"
            )
            test_logger.info(
                "客户问题复现通过: 两步流程完成——第一个请求输出 JSON "
                "到临时文件、工具读取成功、上次输出 JSON（含缺 \"{\" "
                "的 bash arguments/reasoning 双字段的 assistant 历史"
                "——空占位调用已按用户指定移除）已被接受为下次请求的"
                "输入上下文，正常生成响应"
            )

            # ---- 第三个请求：根因断言——模型不得返回空 function ----
            # 复刻工单首个 user 回合（工单中模型在该回合输出了空占位
            # 调用与畸形 bash arguments——后续问题文档确认的根因行
            # 为），带 bash 工具定义，断言本次模型输出的每条工具调用
            # 结构完整
            req3_payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [
                    {"role": "user", "content": K18_CHART_PROMPT}
                ],
                "tools": K18_TOOLS,
                "max_tokens": K18_REQ3_MAX_TOKENS,
                "stream": False,
            }
            TestLogger.log_request(
                test_logger,
                req3_payload["messages"],
                {
                    "tools": [t["function"]["name"] for t in K18_TOOLS],
                    "max_tokens": K18_REQ3_MAX_TOKENS,
                    "temperature": "(不发送)",
                    "top_p": "(不发送)",
                    "seed": "(不发送)",
                    "stream": False,
                    "step": (
                        "第三个请求（根因断言：模型不得返回空 "
                        "function）"
                    ),
                },
            )
            started3 = time.time()
            try:
                response3 = api_client._post_with_retry(
                    url, req3_payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"第三个请求发送异常（{url}）: {e}")
            elapsed3 = time.time() - started3
            # 模型真实响应断言前打印（失败时同样可见）
            test_logger.info(
                f"第三个请求真实响应: HTTP {response3.status_code}, "
                f"elapsed={elapsed3:.1f}s, "
                f"body={response3.text[:800]!r}"
            )
            assert response3.status_code == 200, (
                f"第三个请求失败：根因断言请求应成功，实际 HTTP "
                f"{response3.status_code}: {response3.text[:400]}"
            )
            try:
                result3 = response3.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"第三个请求响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices3 = result3.get("choices") or []
            assert choices3, (
                f"第三个请求响应缺少 choices: {list(result3.keys())}"
            )
            message3 = choices3[0].get("message")
            assert isinstance(message3, dict), (
                f"第三个请求响应 message 结构缺失: {list(result3.keys())}"
            )
            TestLogger.log_response(
                test_logger, result3, "K18-第三个请求响应"
            )
            tool_calls3 = message3.get("tool_calls") or []
            # 断言5a：该回合模型应发起工具调用（生成图表必须执行绘
            # 图脚本——工单场景中模型对该消息即发起 bash 调用；纯
            # 文本回答无法覆盖"空 function"根因）
            assert tool_calls3, (
                f"第三个请求模型未发起工具调用（finish="
                f"{choices3[0].get('finish_reason')}），无法验证根因断言"
                f"（模型不得返回空 function，响应体已记录于测试日志）"
            )
            # 断言5b（根因）：每条工具调用结构完整——name 非空、
            # id 非空、arguments 为合法 JSON 对象（对应开发根因结
            # 论"模型不要返回空的 function"；同时覆盖工单同款畸形
            # arguments 缺 "{" 的模型输出缺陷）
            for i, tc in enumerate(tool_calls3):
                tc = tc if isinstance(tc, dict) else {}
                fn = tc.get("function") or {}
                name = fn.get("name")
                tc_id = tc.get("id")
                raw_args = fn.get("arguments")
                assert isinstance(name, str) and name.strip(), (
                    f"模型返回空 function：tool_calls[{i}].function."
                    f"name 为空（{name!r}）——客户问题根因（空占位调"
                    f"用致客户端回填 missing_tool_call_id 后被协议拒"
                    f"绝），模型不得返回空 function"
                )
                assert isinstance(tc_id, str) and tc_id.strip(), (
                    f"模型返回空 function：tool_calls[{i}].id 为空"
                    f"（{tc_id!r}）——客户端将以 missing_tool_call_id"
                    f" 回填，后续请求被协议校验拒绝"
                )
                args_obj = raw_args
                if isinstance(raw_args, str):
                    try:
                        args_obj = json.loads(raw_args)
                    except json.JSONDecodeError as e:
                        pytest.fail(
                            f"模型返回畸形 arguments：tool_calls[{i}]"
                            f".function.arguments 非合法 JSON（{e}）"
                            f"——工单同款模型输出缺陷（缺 \"{{\"）"
                            f"（原始 arguments 已记录于测试日志）"
                        )
                assert isinstance(args_obj, dict), (
                    f"模型返回畸形 arguments：tool_calls[{i}].function"
                    f".arguments 应为 JSON 对象，实际 "
                    f"{type(args_obj).__name__}（原始 arguments 已记录于测试日志）"
                )
            test_logger.info(
                f"根因断言通过: 模型返回 {len(tool_calls3)} 条结构完"
                f"整的工具调用（name/id 非空、arguments 均为合法 "
                f"JSON 对象），未返回空 function"
            )
        finally:
            # ---- 测试完成后删除生成的临时 JSON 文件（断言失败同样
            # 清理，finally 兜底）----
            try:
                if temp_file.exists():
                    temp_file.unlink()
                    test_logger.info(
                        f"清理完成: 已删除临时 JSON 文件 {temp_file}"
                    )
                else:
                    test_logger.info(
                        f"清理完成: 临时 JSON 文件不存在（无需删除）: "
                        f"{temp_file}"
                    )
            except OSError as e:
                test_logger.warning(
                    f"临时 JSON 文件删除失败: {temp_file} ({e})"
                )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53FLASH
    @pytest.mark.p0
    def test_over_image_limit_rejected(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K19 [P0]: 客户问题 - 单次请求图片数超限（>16）应拒绝并返回恰当错误

        客户问题：单次请求携带超过 16 张图片导致请求失败。根因：服务
        端 serving-pool 启动参数显式配置 --limit-mm-per-prompt
        {"image":16,"video":1,"audio":0}（vLLM 多模态单项限额）。
        契约：超限请求应失败并返回恰当的错误信息（参考 "At most
        16 image(s) may be provided in one prompt"）。
        本用例（GLM-5.3-Flash 专用）：
        - 代码生成 17 张 32x32 纯色 PNG（base64 data URL，无外部
          依赖，各图颜色不同）
        - 单条 user 消息携带 17 个 image_url part（单次请求/单次
          会话超过 16 图）发起非流式请求
        硬断言：
        1. 响应失败（HTTP 非 200——超限应被拒绝）
        2. 错误信息含 "at most 16 image"（大小写不敏感，覆盖
           "At most 16 image(s) may be provided in one prompt"
           及网关等价表述）——恰当的失败信息
        PASS：超限被正确拒绝且信息恰当；FAIL：200 放行（限额未生
        效）或错误信息不含该模式（信息不恰当）。
        原始失败详情截图未收到，断言口径以用户给定的参考信息为准。
        恰好 16 张的正向对照轮未纳入（用户测试要点仅两条，且避免回
        归中重度视觉计算）。max_tokens=32 防御性预算（应在生成前
        被拒绝）。不发送采样参数（test_k 保持原始测试参数——工单
        原始请求未指定，不发送）。
        模型真实响应（状态码/响应体全文）在断言前
        打印到日志（失败时同样可见，便于诊断）。usage/响应体仅日
        志。（不进 smoke 集：新用例首跑观察期）
        """
        # K19: 场景常量——17 张图（超过 serving 限额 16）
        K19_IMAGE_COUNT = 17
        K19_IMAGE_LIMIT = 16
        K19_TEXT = "请逐一描述以下图片的内容。"
        K19_MAX_TOKENS = 32  # 防御性预算（应在生成前被拒绝）
        K19_MSG_NEEDLE = "at most 16 image"  # 大小写不敏感匹配

        def make_png_data_url(index: int) -> str:
            """生成 32x32 纯色 PNG 的 data URL（代码生成图片，无外部依赖）"""
            width = height = 32
            color = (
                (index * 15) % 256,
                (index * 7 + 30) % 256,
                (K19_IMAGE_COUNT - index) * 15 % 256,
            )

            def chunk(ctype: bytes, data: bytes) -> bytes:
                return (
                    struct.pack(">I", len(data))
                    + ctype
                    + data
                    + struct.pack(
                        ">I", zlib.crc32(ctype + data) & 0xFFFFFFFF
                    )
                )

            ihdr = chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
            )
            row = b"\x00" + bytes(color) * width
            idat = chunk(b"IDAT", zlib.compress(row * height))
            iend = chunk(b"IEND", b"")
            png = b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend
            return (
                "data:image/png;base64,"
                + base64.b64encode(png).decode("ascii")
            )

        test_logger.info(
            "=== 测试开始: 客户问题 - 单次请求图片数超限（>16）应"
            "拒绝并返回恰当错误（serving --limit-mm-per-prompt "
            "{\"image\":16}；17 张代码生成 PNG 单会话提交；期望非 "
            "200 + \"At most 16 image(s)...\" 类信息）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # 手工构造 payload 直发（多模态 image_url part 形态，封
        # 装不支持）；不发送采样参数（test_k 保持原始测试参数）
        content_parts: List[Dict[str, Any]] = [
            {"type": "text", "text": K19_TEXT}
        ]
        for i in range(K19_IMAGE_COUNT):
            content_parts.append(
                {"type": "image_url", "image_url": {"url": make_png_data_url(i)}}
            )
        payload = {
            "model": api_client.model_name,
            "messages": [
                {"role": "user", "content": content_parts}
            ],
            "max_tokens": K19_MAX_TOKENS,
            "stream": False,
        }

        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": f"[{K19_TEXT} + {K19_IMAGE_COUNT} 张图]"}],
            {
                "image_parts": K19_IMAGE_COUNT,
                "image_limit": K19_IMAGE_LIMIT,
                "max_tokens": K19_MAX_TOKENS,
                "stream": False,
                "temperature": "(不发送)",
            },
        )

        started = time.time()
        try:
            response = api_client._post_with_retry(
                url, payload, stream=False
            )
        except Exception as e:
            pytest.fail(f"请求发送异常（{url}）: {e}")
        elapsed = time.time() - started

        # 模型真实响应信息（用户要求打印；置于断言前——失败时日志
        # 中同样可见，便于诊断）
        test_logger.info(
            f"K19 真实响应 - HTTP {response.status_code}, "
            f"elapsed={elapsed:.1f}s"
        )
        test_logger.info(
            f"K19 真实响应 - 响应体({len(response.text)} 字符): "
            f"{response.text!r}"
        )

        # 断言1（核心之一）：响应失败——超限应被拒绝
        if response.status_code == 200:
            test_logger.error(
                f"超限放行时的真实响应体: {response.text[:2000]!r}"
            )
        assert response.status_code != 200, (
            f"客户问题复现失败：单次请求携带 {K19_IMAGE_COUNT} 张图"
            f"（超过 serving 限额 {K19_IMAGE_LIMIT}）应被拒绝，实际"
            f" HTTP 200 放行（限额未生效，响应体已记录于测试日志）"
        )

        # 断言2（核心之二）：恰当的失败信息——含 "at most 16 image"
        # （大小写不敏感，覆盖 "At most 16 image(s) may be provided
        # in one prompt" 及网关等价表述）
        assert K19_MSG_NEEDLE in response.text.lower(), (
            f"客户问题复现失败：超限请求已失败（HTTP "
            f"{response.status_code}）但错误信息不恰当——应含类似 "
            f"\"At most 16 image(s) may be provided in one prompt\" "
            f"的信息（匹配 \"/{K19_MSG_NEEDLE}/i\"），实际: "
            f"{response.text[:400]}"
        )

        test_logger.info(
            "客户问题复现通过: 单次请求 17 张图被正确拒绝（HTTP "
            f"{response.status_code}）且返回恰当的超限错误信息"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_1m_context_request_supported(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K20 [P0]: 客户问题 - 1M 上下文请求应被正常支持

        客户问题：请求报错 "Input length (918451 tokens) exceeds
        the maximum allowed length (781754 tokens). Use a shorter
        input or enable --allow-auto-truncate."（type:
        invalid_request_error、code: invalid_request、
        metadata.provider_code: bad_response_status_code——网关透传
        serving 侧上下文长度校验拒绝）。根因：serving 侧未按 1M
        上下文契约配置（当时最大允许 781754）。
        契约：模型需支持 1M 上下文请求——1M 量级输入应正常响应。
        本用例（用户口径：1M = 输入+输出，总量略小于 1M——余量留
        给推理框架额外补充的长度）：
        - 探针自校准：先发小规模探针（重复单元 ×2000，约 276K 字
          符），从 usage.prompt_tokens 精确得出每单元 token 数
          （客户端无分词器，chars/token 启发式误差大——真实环境
          实测该单元 6.28 字符/token，chars/4 高估 57%，1M 契约
          判定的前提是主请求规模可靠）
        - 按目标生成主请求：输入目标 960,000 tokens（自校准计量）
          + 输出预算 max_tokens 覆盖思考+正文 → 总消耗 ≈961K/964K，
          两种 1M 口径（1,000,000 / 1,048,576）下均略小于 1M
          （余量 36K/84K tokens；prompt_tokens 已含聊天模板等框
          架开销），且高于原始故障上限 781,754 约 178K（缺陷可复
          现）
        - 两轮思考档位（用户口径：GLM-5.3 不支持禁用思考、仅支持
          reasoning_effort 档位；用户指定补 max 场景）：①low 轮
          （预算 1024）——常规；②max 轮（预算 4096）——最大思考
          负载，输出侧同步压窗口（真实环境实测默认档思考耗尽 32
          预算致 content 为空——预算必须覆盖思考+正文的教训；
          max 档思考显著更长，预算放大至 4096）
        - 采样参数不发送：test_k 保持原始测试参数（工单原始请求未
          指定，不注入）
        - 跑必冷（用户加固，仅 low 轮）：low 轮（含探针）材料头
          部置每次请求唯一 nonce（时间戳+uuid，可含中文，几十字
          符）——前缀必不命中 KV 缓存，真 1M 冷 prefill（缓存
          命中只省 prefill 重算，不绕过准入长度校验、不省 KV 内
          存驻留与 decode 全窗注意力——核心契约验证本不受缓存
          影响，此为 prefill 侧压测加固）；max 轮取消唯一前缀
          （用户口径：输出侧验证不受缓存影响，允许命中历史缓存
          加速）；nonce 为常数级几十 tokens，对计量影响可忽略
        - 单条 user 消息非流式提交（程序生成，无外部文件）
        硬断言：
        1. 探针 200 且返回 usage.prompt_tokens（计量前提）
        2. 每轮主请求 HTTP 200（未被拒绝——1M 量级输入应被接受）
        3. 每轮 choices 非空且 content 非空（可正常响应）
        4. 每轮主响应 usage.prompt_tokens（如有）> 781,754——
           规模 sanity（确保真正压过原始故障点，防计量偏差）
        PASS：两轮均 1M 量级输入正常响应；FAIL：任一轮被拒（原
        始报错形态）或空响应。
        超时处理：1M token prefill 耗时长，临时将客户端超时上调
        至 900s（finally 恢复；ReadTimeout 不重试——框架约定）。
        请求提示词由程序生成（无外部文件）。模型真实响应（状态码/
        响应体全文）断言前每轮打印（失败时同样可见，便于诊断）。
        usage/响应体仅日志。
        （不进 smoke 集：新用例首跑观察期）
        """
        # K20: 场景常量——1M = 输入+输出（用户口径），总量略小于 1M
        # （1,000,000 / 1,048,576 两种 1M 口径均满足；余量留给推理
        # 框架额外补充的长度——prompt_tokens 已含聊天模板等开销，
        # 输出预算计入总量）
        K20_TARGET_PROMPT_TOKENS = 960_000
        # 两轮思考档位（GLM-5.3 不支持禁用思考、仅支持档位——用户
        # 口径）：low 轮常规预算；max 轮最大思考负载（输出侧同步压
        # 窗口），预算放大覆盖更长思考。第三元素=是否跑必冷（用户
        # 口径：low 轮唯一 nonce 前缀强制冷 prefill——prefill 侧压
        # 测；max 轮取消唯一前缀——输出侧验证不受缓存影响，允许
        # 命中历史缓存加速）
        K20_EFFORT_ROUNDS = [("low", 1024, True), ("max", 4096, False)]
        K20_PROBE_UNITS = 2000  # 探针规模（约 276K 字符，精确自校准）
        K20_OLD_INPUT_LIMIT = 781_754  # 原始故障上限（规模 sanity 用）
        K20_TIMEOUT_SECONDS = 900  # 1M prefill 需长超时
        K20_UNIT = (
            "Long context verification material. The platform must "
            "accept very large document inputs and process them "
            "without truncation or rejection. "
        )
        K20_INSTRUCTION = (
            "\n\n以上为背景材料。请直接回复一句话，确认已完整收到"
            "全部材料。"
        )

        url = f"{api_client.api_prefix}/chat/completions"

        test_logger.info(
            "=== 测试开始: 客户问题 - 1M 上下文请求应被正常支持"
            f"（探针自校准精确计量；目标输入 {K20_TARGET_PROMPT_TOKENS} "
            f"tokens + 输出预算 low 轮 1024 / max 轮 4096——输入+输出 "
            f"略小于 1M；采样参数不发送——test_k 保持原始测试参数；"
            f"low 轮唯一 nonce 头部绕过 KV 缓存——跑必冷、"
            f"max 轮无唯一前缀（允许命中缓存）；"
            f"期望每轮 HTTP 200 + 非空正文）==="
        )

        # 采样参数不发送——test_k 保持原始测试参数（工单原始请求
        # 未指定，不注入）

        def make_nonce() -> str:
            """生成唯一 nonce（时间戳+uuid，可含中文，几十字符）——
            置于材料头部使前缀必不命中 KV 缓存（跑必冷，仅 low 轮及
            探针使用——用户口径；nonce 为常数级几十 tokens，对探针
            计量/1M 总量口径影响可忽略）"""
            return (
                f"【本次请求唯一标识 {time.strftime('%Y%m%d%H%M%S')}"
                f" {uuid.uuid4().hex[:8]}】"
            )

        def build_payload(
            text: str, effort: str, max_tokens: int, nonce: str = ""
        ) -> Dict[str, Any]:
            """构造 K20 请求体（探针/两轮共用）"""
            return {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": nonce + text}],
                "max_tokens": max_tokens,
                "reasoning_effort": effort,
                "stream": False,
            }

        # ---- 阶段1：探针自校准（精确测量每单元 token 数）----
        # 客户端无分词器，chars/token 启发式误差可达 ±30%——先发小
        # 规模探针，从 usage.prompt_tokens 精确得出每单元 token 数
        # （1M 契约判定的前提，主请求规模必须可靠）
        probe_payload = build_payload(
            K20_UNIT * K20_PROBE_UNITS,
            K20_EFFORT_ROUNDS[0][0],
            1,
            nonce=make_nonce() if K20_EFFORT_ROUNDS[0][2] else "",
        )
        probe_content = probe_payload["messages"][0]["content"]
        TestLogger.log_request(
            test_logger,
            [
                {
                    "role": "user",
                    "content": (
                        f"[nonce+探针自校准材料 {K20_PROBE_UNITS} 单元"
                        f"（{len(probe_content)} 字符）]"
                    ),
                }
            ],
            {
                "max_tokens": 1,
                "reasoning_effort": K20_EFFORT_ROUNDS[0][0],
                "temperature": "(不发送)",
                "top_p": "(不发送)",
                "seed": "(不发送)",
                "cache": "nonce 前缀绕过（跑必冷）",
                "stream": False,
            },
        )
        try:
            probe_resp = api_client._post_with_retry(
                url, probe_payload, stream=False
            )
        except Exception as e:
            pytest.fail(f"探针请求发送异常（{url}）: {e}")
        assert probe_resp.status_code == 200, (
            f"探针请求失败（HTTP {probe_resp.status_code}）: "
            f"{probe_resp.text[:400]}"
        )
        try:
            probe_body = probe_resp.json()
        except ValueError as e:
            test_logger.error(
                f"探针响应体非合法 JSON，真实响应体: "
                f"{probe_resp.text[:2000]!r}"
            )
            pytest.fail(
                f"探针响应体非 JSON（{e}）（真实响应体已记录于测试日志）"
            )
        probe_prompt_tokens = (probe_body.get("usage") or {}).get(
            "prompt_tokens"
        )
        if not probe_prompt_tokens:
            test_logger.error(
                f"探针响应缺少 usage.prompt_tokens，真实响应体: "
                f"{probe_resp.text[:2000]!r}"
            )
        assert probe_prompt_tokens, (
            "探针响应缺少 usage.prompt_tokens，无法精确计量 1M 目标"
            "规模（真实响应体已记录于测试日志）"
        )
        tokens_per_unit = probe_prompt_tokens / K20_PROBE_UNITS
        test_logger.info(
            f"K20 探针自校准 - {K20_PROBE_UNITS} 单元"
            f"（{len(probe_content)} 字符）实测 prompt_tokens="
            f"{probe_prompt_tokens} → {tokens_per_unit:.3f} tokens/单元"
        )

        # ---- 阶段2：按目标规模生成主请求（输入+输出 略小于 1M）----
        main_units = math.ceil(K20_TARGET_PROMPT_TOKENS / tokens_per_unit)
        content = K20_UNIT * main_units + K20_INSTRUCTION
        predicted_tokens = round(main_units * tokens_per_unit)

        # 两轮（用户指定补 max 场景）：同一工单同一契约——1M 量级输
        # 入在不同思考负载下均应正常响应；探针校准共享，逐轮发送、
        # 逐轮断言（任一轮失败即用例 FAIL）
        for round_index, (effort, budget, cold) in enumerate(
            K20_EFFORT_ROUNDS, start=1
        ):
            payload = build_payload(
                content, effort, budget, nonce=make_nonce() if cold else ""
            )
            req_content = payload["messages"][0]["content"]

            TestLogger.log_request(
                test_logger,
                [
                    {
                        "role": "user",
                        "content": (
                            f"[{'nonce+' if cold else ''}程序生成背景材料 "
                            f"{len(req_content)} 字符"
                            f"（自校准预计 {predicted_tokens} tokens）"
                            f"+ 尾部指令]"
                        ),
                    }
                ],
                {
                    "round": (
                        f"{round_index}/{len(K20_EFFORT_ROUNDS)}"
                        f"（reasoning_effort={effort}）"
                    ),
                    "predicted_prompt_tokens": predicted_tokens,
                    "chars": len(req_content),
                    "unit_repeats": main_units,
                    "max_tokens": budget,
                    "reasoning_effort": (
                        f"{effort}"
                        "（不支持禁用思考、仅档位——用户口径）"
                    ),
                    "stream": False,
                    "temperature": "(不发送)",
                    "top_p": "(不发送)",
                    "seed": "(不发送)",
                    "cache": (
                        "nonce 前缀绕过（唯一——跑必冷）"
                        if cold
                        else "无唯一前缀（允许命中历史缓存）"
                    ),
                },
            )

            # 1M prefill 耗时长：临时上调客户端超时（finally 恢复，
            # 不影响其他用例；ReadTimeout 不在重试名单——框架约定）
            original_timeout = api_client.timeout
            api_client.timeout = K20_TIMEOUT_SECONDS
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(
                    f"第 {round_index} 轮（reasoning_effort={effort}）"
                    f"请求发送异常（{url}）: {e}"
                )
            finally:
                api_client.timeout = original_timeout
            elapsed = time.time() - started

            # 模型真实响应信息（用户要求打印；置于断言前——失败时
            # 日志中同样可见，便于诊断）
            test_logger.info(
                f"K20 第{round_index}轮（reasoning_effort={effort}）"
                f"真实响应 - HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s"
            )
            test_logger.info(
                f"K20 第{round_index}轮（reasoning_effort={effort}）"
                f"真实响应 - 响应体({len(response.text)} 字符): "
                f"{response.text!r}"
            )

            # 断言1（核心之一）：未被拒绝——1M 量级输入应被接受
            assert response.status_code == 200, (
                f"客户问题复现失败（第 {round_index} 轮 "
                f"reasoning_effort={effort}）：约 {predicted_tokens} "
                f"tokens（自校准）的 1M 量级输入应被支持，实际被拒绝"
                f"（HTTP {response.status_code}）: {response.text[:400]}"
            )

            # 断言2（核心之二）：可正常响应——choices/content 非空
            try:
                body = response.json()
            except ValueError as e:
                pytest.fail(
                    f"第 {round_index} 轮响应体非 JSON（{e}）"
                )
            choices = body.get("choices") or []
            assert choices, (
                f"第 {round_index} 轮 choices 为空（响应体已记录于测试日志）"
            )
            message = (choices[0] or {}).get("message") or {}
            content_out = (message.get("content") or "").strip()
            assert content_out, (
                f"客户问题复现失败（第 {round_index} 轮 "
                f"reasoning_effort={effort}）：1M 量级输入已接受"
                f"（HTTP 200）但响应正文为空（响应体已记录于测试日志）"
            )

            # usage 仅日志；prompt_tokens 附加规模 sanity 断言——必须
            # 高于原始故障上限 781754（确保用例真正压过故障点，防计
            # 量偏差）
            usage = body.get("usage") or {}
            actual_prompt_tokens = usage.get("prompt_tokens")
            if actual_prompt_tokens is None:
                test_logger.info(
                    f"K20 第{round_index}轮真实响应 - usage 缺 "
                    "prompt_tokens（跳过规模 sanity 断言）"
                )
            else:
                assert actual_prompt_tokens > K20_OLD_INPUT_LIMIT, (
                    f"规模 sanity 断言失败（第 {round_index} 轮）：实际 "
                    f"prompt_tokens={actual_prompt_tokens} 未超过原始"
                    f"故障上限 {K20_OLD_INPUT_LIMIT}——用例未真正压过"
                    f"故障点（探针自校准 {tokens_per_unit:.3f} "
                    f"tokens/单元，预计 {predicted_tokens}）"
                )
            test_logger.info(
                f"K20 第{round_index}轮（reasoning_effort={effort}）"
                f"真实响应 - usage: {json.dumps(usage, ensure_ascii=False)}"
            )
            test_logger.info(
                f"客户问题复现通过（第 {round_index} 轮 "
                f"reasoning_effort={effort}）: 1M 量级输入（自校准预计 "
                f"{predicted_tokens} tokens，实际 {actual_prompt_tokens}）"
                "被正常接受并返回非空响应（输入+输出 "
                f"{actual_prompt_tokens}+{budget} tokens，略小于 1M）"
            )

    @pytest.mark.k_customer_issue
    @pytest.mark.KimiK3
    @pytest.mark.p0
    def test_system_message_embedded_tools_accepted(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K21 [P0]: 客户问题 - system 消息内嵌 tools 的非标请求结构应被接受

        客户问题（kimi-k3 工单原始请求体，request id
        2026101517465272830754257355159）：messages[2] 为 role=system
        且无 content 字段、代之以内嵌 tools 数组（Calculator 单工具
        ——算术表达式求值），服务端反序列化直接报 400：
        {"error": {"message": "Invalid JSON data: Failed to
        deserialize the JSON body into the target type: messages[2]:
        data did not match any variant of untagged enum
        MessageContent at line 1 column 944 ...", "type":
        "invalid_request_error", "code": "json_parse_error"}}。
        该结构虽非 OpenAI 协议标准形态（tools 应为顶层参数），但客户
        业务实际在用——契约：服务端应宽容解析该非标结构并正常响应
        （预期 200）。
        本用例按工单原始请求体原样重放（模型名按框架约定由环境注入，
        其余字段——系统提示词/用户问题/内嵌 tools 结构——均不改动），
        单次请求（结构解析为确定性行为，无需多次连发），硬断言：
        1. HTTP 200（核心——原始报错形态 400 json_parse_error 复现
           即 FAIL）
        2. 响应为合法 JSON 且 choices 存在
        3. message 有效输出：content 非空或 tool_calls 非空（宽容解析
           后无论按"忽略内嵌 tools 文本作答"或"按工具调用响应"均为
           有效成功形态；两者皆空即未正常响应）
        模型真实响应（状态码/响应体全文）断言前打印（失败时同样可
        见）；usage 仅日志。采样参数不发送——test_k 保持原始测试参
        数（工单原始请求未指定，不注入）。打印口径
        （用户指令）：运行日志不出现具体模型名——系统提示词正文含
        模型自我介绍，日志仅记字符数概要，原文见本 docstring 与用
        例常量。
        （不进 smoke 集：新用例首跑观察期）
        """
        # K21: 工单原始 system 提示词（正文含模型自我介绍——按用户
        # 指令不进运行日志，原文仅保留于此）
        K21_SYSTEM_PROMPT = (
            "You are Kimi, an AI assistant developed by Moonshot AI.\n"
            "You are capable of a wide range of tasks, including:\n"
            "📝 Q&A & Explanation – Answer all kinds of questions, "
            "ranging from scientific knowledge to daily life matters\n"
            "✍️ Writing Assistance – Draft essays, emails and reports, "
            "or polish your written text\n"
            "💻 Coding Support – Write and debug code, and explain "
            "technical concepts\n"
            "🔍 Analysis & Summarization – Process lengthy documents, "
            "extract key points and analyze data\n"
            "🌍 Translation – Support mutual translation between "
            "multiple languages\n"
            "💡 Brainstorming – Help you expand ideas and generate "
            "creative inspirations\n"
            "You also accept extremely long context inputs, making you "
            "ideal for users who need analysis or summaries of lengthy "
            "documents."
        )

        # K21: 工单原始 user 提示词
        K21_USER_PROMPT = "Calculate fuel consumption."

        # K21: 工单原始非标第三条消息的 tools 数组（Calculator 单工
        # 具）——原样重放：role=system、无 content 字段、tools 内嵌
        # 于消息（缺陷触发点，不修复）
        K21_EMBEDDED_TOOLS = [
            {
                "type": "function",
                "function": {
                    "name": "Calculator",
                    "description": (
                        "计算器，只支持单个算术表达式的求值"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expr": {
                                "type": "string",
                                "description": (
                                    "算术表达式，支持四则运算、指数运"
                                    "算、对数函数、三角函数，使用 "
                                    "javascript 语法"
                                ),
                            }
                        },
                        "required": ["expr"],
                    },
                },
            }
        ]

        url = f"{api_client.api_prefix}/chat/completions"

        test_logger.info(
            "=== 测试开始: 客户问题 - system 消息内嵌 tools 的非标请"
            "求结构应被接受（工单原始请求体原样重放；期望 HTTP 200 "
            "正常响应——原始报错形态为 400 json_parse_error："
            "messages[2] data did not match any variant of untagged "
            "enum MessageContent）==="
        )

        # 工单原始 messages 原样重放（第三条为非标结构：role=system、
        # 无 content、tools 内嵌于消息——缺陷触发点）
        messages = [
            {"role": "system", "content": K21_SYSTEM_PROMPT},
            {"role": "user", "content": K21_USER_PROMPT},
            {"role": "system", "tools": K21_EMBEDDED_TOOLS},
        ]
        # 采样参数不发送——test_k 保持原始测试参数（工单原始请求
        # 未指定，不注入）
        payload = {
            "model": api_client.model_name,
            "messages": messages,
            "stream": False,
        }

        # 打印口径（用户指令）：运行日志不出现具体模型名——系统提
        # 示词正文含模型自我介绍，仅记字符数概要（原文见用例常量）
        TestLogger.log_request(
            test_logger,
            [
                {
                    "role": "system",
                    "content": (
                        f"[工单原始系统提示词（{len(K21_SYSTEM_PROMPT)} "
                        "字符，正文略——含模型自我介绍，不进运行日志）]"
                    ),
                },
                {"role": "user", "content": K21_USER_PROMPT},
                {
                    "role": "system",
                    "content": (
                        "[无 content 字段——非标结构：tools 数组内嵌于"
                        "消息（Calculator 单工具，工单原文）]"
                    ),
                },
            ],
            {
                "stream": False,
                "message[2]": (
                    "role=system + tools 内嵌（无 content 字段——非"
                    "标结构，工单原样重放）"
                ),
                "tools": ["Calculator"],
                "重放口径": "工单原始请求体（模型名由环境注入——框架约定）",
                "temperature": "(不发送)",
                "top_p": "(不发送)",
                "seed": "(不发送)",
            },
        )

        started = time.time()
        try:
            response = api_client._post_with_retry(
                url, payload, stream=False
            )
        except Exception as e:
            pytest.fail(f"请求发送异常（{url}）: {e}")
        elapsed = time.time() - started

        # 模型真实响应（用户要求打印；置于断言前——失败时日志中同
        # 样可见，便于诊断）
        test_logger.info(
            f"K21 真实响应 - HTTP {response.status_code}, "
            f"elapsed={elapsed:.1f}s"
        )
        test_logger.info(
            f"K21 真实响应 - 响应体({len(response.text)} 字符): "
            f"{response.text!r}"
        )

        # 断言1（核心）：未被拒绝——非标结构应被宽容解析并接受
        assert response.status_code == 200, (
            f"客户问题复现失败：system 消息内嵌 tools 的非标请求结构"
            f"应被宽容解析并正常响应，实际被拒绝（HTTP "
            f"{response.status_code}；原始报错形态为 400 "
            f"json_parse_error——messages[2] data did not match any "
            f"variant of untagged enum MessageContent）: "
            f"{response.text[:400]}"
        )

        # 断言2：可正常响应——合法 JSON 且 choices 存在
        try:
            result = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            pytest.fail(
                f"响应不是合法 JSON: {e}. 响应体已记录于测试日志"
            )
        choices = result.get("choices") or []
        assert choices, (
            f"响应缺少 choices: {list(result.keys())}"
        )

        # 断言3：有效输出——content 非空或 tool_calls 非空（宽容解析
        # 后文本作答/工具调用响应均为成功形态；两者皆空即未正常响应）
        message = (choices[0] or {}).get("message") or {}
        content_out = (message.get("content") or "").strip()
        tool_calls_out = message.get("tool_calls") or []
        assert content_out or tool_calls_out, (
            f"客户问题复现失败：请求已接受（HTTP 200）但响应无有效输"
            f"出（content 与 tool_calls 均为空，响应体已记录于测试日志）"
        )
        output_kind = "content 非空" if content_out else "tool_calls 非空"

        TestLogger.log_response(test_logger, result, "K21-响应")
        usage = result.get("usage") or {}
        test_logger.info(
            f"K21 真实响应 - usage: {json.dumps(usage, ensure_ascii=False)}"
        )
        test_logger.info(
            "客户问题复现通过: 非标请求结构（system 消息内嵌 tools、"
            f"无 content 字段）被正常接受（HTTP 200）并返回有效输出"
            f"（{output_kind}）——原始 400 json_parse_error 报错形态"
            "未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_cross_protocol_prefix_cache_parity(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K22 [P0]: 客户问题 - /v1/messages 缓存命中率应与
        /v1/chat/completions 基本一致（循环 5 次比对）

        客户问题：相同请求下，Anthropic 协议（/anthropic/v1/messages，
        端点与鉴权头见开发示例：x-api-key + anthropic-version）的前
        缓存命中率始终低于 /v1/chat/completions（"缓存始终上不去"）。
        根因：该链路 system 头部携带 x-anthropic-billing-header:
        <逐请求动态值> 计费行（字符串/块数组两种 system 形态均涉及），
        而前缀缓存要求从位置 0 连续匹配——头部逐请求变化导致整个前
        缀永不命中；chat 协议无此行、前缀稳定，命中率正常（K15/K16
        已验证 ≥90%）。
        开发修复：入引擎前条件剥离——system（字符串或块数组）开头是
        x-anthropic-billing-header: 行即去掉，其余内容原样保留。
        测试要点（用户口径）：同轮等价请求分别发送
        /v1/chat/completions 与 /anthropic/v1/messages 两协议（同
        轮同问；前缀头部渠道标记行不同——用户指定：剥离计费行后
        两协议前缀仍从位置 0 分叉，互不命中对方缓存条目，各自建
        条目/各自命中，messages 冷轮为真冷；标记差异仅数字符，
        对命中率影响可忽略），统计二者缓存命中率并逐轮比较——
        第一次请求为冷轮（两协议均无缓存可命中，不参与比较；用
        户口径：需热轮才能统计命中率），热轮（第 2 轮起）逐轮比
        较差值（用户指定容差 3 个百分点）。组级判定（用户指
        定）：单组失败不中断后续组（五组全部执行），每组判定=该
        组全部热轮差值 ≤3 个百分点，5 组中至少 4 组符合预期即用
        例 PASS、不足 4 组 FAIL。
        循环 5 次比对（用户口径：每次循环的请求消息尽量不一样）：
        2 组中文、2 组英文、1 组中英混合，每组前缀
        ~8400-12000 tok + 每轮唯一问题 ~330-550 tok——整请求长度
        尽量超过 8k tokens；同时覆盖开发修复的两条剥离代码路径：
        块数组形态（断点挂 system 块，K3 口径）与字符串形态（断
        点挂 user 首块——内容固定断点前缀逐轮恒定，每轮唯一问题
        置于断点之外）。每次循环每协议 1 冷轮 + 2 热轮（用户口
        径），逐轮交替发送两协议（同轮同问），共 5 次循环 × 2
        协议 × 3 轮 = 30 请求，组间间隔 3 秒（用户指定）。命中率口径：chat = cached_tokens/
        prompt_tokens（该轮，K16 字段口径）；messages = cache_
        read/分母（分母按 input_tokens 口径自适应——以同轮 chat
        prompt_tokens 为参照，已含命中总量时取其自身，否则加
        cache_read）。
        缺陷形态：计费行未剥离 → messages 前缀逐请求失配 → 热轮命
        中率 ≈0% vs chat ≈94% → 差 ≈90pp > 3pp → 五组全部不符合
        预期 → FAIL；修复后两协议每热轮均 ≈94% → 差 <3pp → 五组
        全符合 → PASS。热轮 cache_creation>0
        （前缀逐请求重建=剥离失效直接信号）与双低形态（两协议命中
        率均异常低——疑似全局缓存异常，chat 侧由 K15/K16 覆盖）
        仅日志留痕。硬断言：①组级判定（用户指定）——单组失败不
        中断后续组（五组全部执行），每组判定=该组全部热轮差值
        ≤3 个百分点（messages 热轮全量 miss 时先同轮重发一次鉴
        别），5 组中至少 4 组符合预期才 PASS（不足 4 组 FAIL，
        报文汇总各组判定与失败组/轮两侧命中率与 usage 细节）；
        ②每请求 HTTP 200 且响应正常（chat：choices；
        messages：usage+content）。热轮全量 miss 重发加固（用户
        指定）：messages 热轮 read=0 且 creation=0 时同轮重发
        一次（新计费行、同前缀同问）——重发命中→WARN 留痕并按
        重发结果继续比较（偶发 miss，疑似多实例路由/条目可见性
        问题，非剥离缺陷）；重发仍全量 miss→FAIL（剥离失效形
        态——剥离失效时重发同样 miss，判别力不变）。运行日志不
        含具体模型名。（不进 smoke 集：新用例首跑观察期）
        """
        # K22: Anthropic 协议版本头（K3 口径：2023-06-01 长期 GA
        # 版本，兼容网关事实标准；若目标网关升级要求新版本改此常量）
        K22_ANTHROPIC_VERSION = "2023-06-01"

        # K22: 计费行前缀——开发修复的剥离触发特征（system 开头为
        # 该行即剥离，值与剥离无关）
        K22_BILLING_LINE_PREFIX = "x-anthropic-billing-header:"

        # K22: 输出 token 上限——缓存断言只关心 input 侧 usage
        # （K3 口径）
        K22_MAX_TOKENS = 512

        # K22: 每次循环每协议轮次：1 冷轮（不参与比较）+ 2 热轮
        # （逐轮比较）——用户口径：每次每协议一冷轮 + 两热轮
        K22_ROUNDS = 3
        K22_COLD_ROUNDS = 1

        # K22: "基本一致"容差（3 个百分点，用户指定）
        K22_PARITY_TOLERANCE = 0.03

        # K22: 组级判定阈值（用户指定）——5 组中至少 4 组该组全
        # 部热轮差值 ≤容差才 PASS；单组失败不中断后续组
        K22_MIN_PASS_GROUPS = 4

        # K22: input_tokens 口径判别阈值——同轮 chat prompt_tokens
        # 为参照，input_tokens 超过其 80% 即认定"已含命中总量"
        K22_INPUT_TOTAL_SEMANTICS_RATIO = 0.8

        # K22: 8-10k tok prefill 耗时显著但远小于 K3 的 11 万——
        # 超时下限适度（K3 超时保护模式）
        K22_MIN_REQUEST_TIMEOUT = 600

        # K22: 字符串形态 user 首块（cache_control 断点挂此块——内
        # 容固定，断点前缀=system+本块逐轮恒定；每轮唯一问题在第二
        # 块、断点之外）
        K22_STRING_FORM_ACK_BLOCK = "请基于上述材料回答。"

        # K22: 五组不同请求消息——循环 5 次比对，每次循环的请求消
        # 息尽量不一样（用户口径；中英文兼备、长度尽量超过 8k
        # tokens）。每组=（组名, system 形态,
        # 语言, 前缀填充单元, 前缀目标字符数, 问题填充文本）；中文
        # ~1.55 字符/token、英文 ~4 字符/token 折算，前缀约
        # 8400-12000 tok，加每轮唯一问题后整请求 >8k tokens；组间
        # 前缀内容互不相同（不同主题措辞），组内批次号防跨运行污
        # 染；形态分配覆盖开发修复的两条剥离代码路径（块数组断点
        # 挂 system 块——K3 口径；字符串断点挂 user 首块）
        K22_GROUPS = [
            (
                "中文-客服知识库",
                "块数组",
                "中文",
                (
                    "本知识库收录产品规格说明、接口调用指南、计费"
                    "策略细则与常见问题处理流程，供客服助手检索引用。"
                ),
                13000,
                (
                    "补充材料：客户在部署与验收阶段需核对接口说明、"
                    "计费策略与规格参数，涉及多部门协作、流程审批与"
                    "回归验证节点，请结合知识库内容作答。"
                )
                * 11,
            ),
            (
                "英文-知识库",
                "字符串",
                "英文",
                (
                    "This knowledge base covers product "
                    "specifications, interface guidelines, billing "
                    "policies, frequently asked questions, and standard "
                    "resolution procedures for customer service "
                    "assistants."
                ),
                40000,
                (
                    "Supplementary material: customers must verify "
                    "interface descriptions, billing policies, and "
                    "specification parameters during deployment and "
                    "acceptance, involving multi-team collaboration, "
                    "approval workflows, and regression checkpoints."
                )
                * 10,
            ),
            (
                "中文-运维手册",
                "块数组",
                "中文",
                (
                    "本运维手册涵盖部署架构说明、容量规划建议、告"
                    "警分级处理、备份恢复步骤与故障排查流程，供值班"
                    "工程师日常查阅。"
                ),
                13000,
                (
                    "补充材料：运维值守需核对容量水位、告警级别与备"
                    "份状态，涉及值班交接、升级审批与演练复盘节点，"
                    "请结合手册内容作答。"
                )
                * 10,
            ),
            (
                "英文-技术文档",
                "字符串",
                "英文",
                (
                    "This technical documentation describes system "
                    "architecture, capacity planning, alert "
                    "management, disaster recovery procedures, and "
                    "troubleshooting workflows for operations "
                    "engineers."
                ),
                40000,
                (
                    "Supplementary material: on-call engineers must "
                    "verify capacity levels, alert severities, and "
                    "backup status, covering shift handover, "
                    "escalation approvals, and drill retrospectives "
                    "based on this documentation."
                )
                * 10,
            ),
            (
                "中英混合-双语知识库",
                "块数组",
                "中英混合",
                (
                    "本知识库同时收录中文与英文条目：产品规格、接"
                    "口说明与计费策略。The same repository also "
                    "includes English entries for deployment guides, "
                    "alert handling, and backup procedures."
                ),
                24000,
                (
                    "补充材料：双语检索需同时核对中文条目与 "
                    "English entries，涉及术语对照、流程审批与回归"
                    "验证节点，请结合知识库内容作答。"
                )
                * 10,
            ),
        ]

        def billing_line() -> str:
            """构造逐请求唯一计费行（值逐请求变化——静态值修复前
            前缀也相同、缺陷无法复现=假阴性）"""
            return (
                f"{K22_BILLING_LINE_PREFIX} "
                f'{{"request_id": "{uuid.uuid4().hex}", '
                f'"ts": {int(time.time() * 1000)}}}'
            )

        def question_for(lang: str, k: int, filler: str) -> str:
            """每轮唯一问题（轮次号在开头分叉——保证前缀在问题开
            头处分叉；同轮两协议同文——"相同请求"）"""
            if lang == "英文":
                return (
                    f"Question (Round {k}): Please summarize the "
                    "applicable scope, precautions, and handling "
                    "procedures based on the material above." + filler
                )
            return (
                f"检索问题（第 {k} 轮）：请依据上述材料归纳适用范"
                "围、注意事项与处理流程，并给出要点摘要。" + filler
            )

        def cache_usage_field(usage: Dict[str, Any], *names: str) -> int:
            """从 usage 中取缓存计数值，兼容协议字段名与网关内部
            字段名两种拼写（K3 口径）"""
            for name in names:
                value = usage.get(name)
                if isinstance(value, (int, float)) and value > 0:
                    return int(value)
            return 0

        def cached_of(usage: Dict[str, Any]):
            """取 chat 协议缓存命中 tokens（prompt_tokens_details.
            cached_tokens 优先，兼容 usage.cached_tokens 拼写——
            K16 口径）"""
            details = usage.get("prompt_tokens_details") or {}
            value = details.get("cached_tokens")
            if value is None:
                value = usage.get("cached_tokens")
            return value

        test_logger.info(
            "=== 测试开始: 客户问题 - /v1/messages 与 "
            "/v1/chat/completions 前缀缓存命中率对齐（循环 5 次比"
            "对，每次循环请求消息尽量不一样——2 组中文、2 组英文、"
            "1 组中英混合，整请求 >8k tokens；每次循环每协议 1 冷轮 "
            "+ 2 热轮，同轮两协议同问，组级判定 5 组中至少 4 组热轮"
            "差值 ≤3 个百分点）==="
        )

        # 全运行唯一批次号：置入各组前缀头部（K3 口径——避免命中
        # 历史运行遗留缓存）
        run_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"

        chat_url = f"{api_client.api_prefix}/chat/completions"
        messages_url = f"{api_client.base_url}/anthropic/v1/messages"

        def chat_round(
            g: int, gname: str, k: int, prefix_text: str, q: str
        ) -> Dict[str, Any]:
            """chat 协议单轮（K16 口径：非流式手工 payload，自动
            前缀缓存）"""
            label = f"第{g}组·{gname}-chat-第{k}轮"
            payload = {
                "model": api_client.model_name,
                "messages": [
                    {"role": "system", "content": prefix_text},
                    {"role": "user", "content": q},
                ],
                "max_tokens": 16,
                "stream": False,
            }
            TestLogger.log_request(
                test_logger,
                [
                    {
                        "role": "system",
                        "content": (
                            f"[可缓存长前缀 {len(prefix_text)} 字符，"
                            f"批次 {run_id} 第 {g} 组，渠道 chat]"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"[{len(q)} 字符] {q[:30]}…",
                    },
                ],
                {
                    "max_tokens": 16,
                    "stream": False,
                    "round": label,
                },
            )
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    chat_url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(
                    f"[{label}] 请求发送异常（{chat_url}）: {e}"
                )
            assert response.status_code == 200, (
                f"[{label}] 请求失败 HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(f"[{label}] 响应不是合法 JSON: {e}")
            choices = result.get("choices") or []
            if not choices:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert choices, (
                f"[{label}] 响应缺少 choices: {list(result.keys())}"
            )
            usage = result.get("usage") or {}
            test_logger.info(
                f"[{label}]: HTTP 200, "
                f"elapsed={time.time() - started:.1f}s, "
                f"pt={usage.get('prompt_tokens')}, "
                f"cached={cached_of(usage)}"
            )
            return usage

        def messages_round(
            g: int,
            gname: str,
            form: str,
            k: int,
            prefix_text: str,
            q: str,
            system_field,
            user_field,
            line: str,
            attempt: int = 1,
        ) -> Dict[str, Any]:
            """messages 协议单轮（开发示例口径：非流式单 JSON 响
            应，x-api-key + anthropic-version 头；attempt>1 时为
            全量 miss 后的同轮重发——label 标注重发序号）"""
            label = f"第{g}组·{gname}-{form}-第{k}轮"
            if attempt > 1:
                label += f"-重发{attempt}"
            payload = {
                "model": api_client.model_name,
                "max_tokens": K22_MAX_TOKENS,
                "system": system_field,
                "messages": [{"role": "user", "content": user_field}],
            }
            headers = {"anthropic-version": K22_ANTHROPIC_VERSION}
            if api_client.api_key:
                headers["x-api-key"] = api_client.api_key
            TestLogger.log_request(
                test_logger,
                [
                    {
                        "role": "system",
                        "content": (
                            f"[计费行 + 可缓存长前缀 "
                            f"{len(prefix_text)} 字符，批次 {run_id} "
                            f"第 {g} 组，渠道 anthropic]"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"[{len(q)} 字符] {q[:30]}…",
                    },
                ],
                {
                    "protocol": "anthropic (/anthropic/v1/messages)",
                    "anthropic-version": K22_ANTHROPIC_VERSION,
                    "max_tokens": K22_MAX_TOKENS,
                    "billing_line": line,
                    "cache_control": "ephemeral（块数组挂 system 块/"
                    "字符串挂 user 首块）",
                    "round": label,
                },
            )
            started = time.time()
            try:
                response = api_client.session.post(
                    messages_url,
                    json=payload,
                    headers=headers,
                    timeout=api_client.timeout,
                )
            except Exception as e:
                pytest.fail(
                    f"[{label}] 请求发送异常（{messages_url}）: {e}"
                )
            assert response.status_code == 200, (
                f"[{label}] 请求失败 HTTP {response.status_code}: "
                f"{response.text[:500]}"
            )
            try:
                result = response.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(f"[{label}] 响应不是合法 JSON: {e}")
            content_blocks = result.get("content") or []
            if not content_blocks:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert content_blocks, (
                f"[{label}] 响应缺少 content: {list(result.keys())}"
            )
            usage = result.get("usage") or {}
            if not usage:
                test_logger.error(
                    f"[{label}] 真实响应体: "
                    f"{json.dumps(result, ensure_ascii=False)[:2000]}"
                )
            assert usage, (
                f"[{label}] 响应缺少 usage: {list(result.keys())}"
            )
            test_logger.info(
                f"[{label}]: HTTP 200, "
                f"elapsed={time.time() - started:.1f}s, usage: "
                f"{json.dumps(usage, ensure_ascii=False)}"
            )
            return usage

        def build_request(
            form: str, line: str, prefix_text: str, q: str
        ):
            """按 system 形态构造 messages 协议请求字段（块数组：
            断点挂 system 块；字符串：断点挂 user 首块——内容固定
            断点前缀逐轮恒定，每轮唯一问题置于断点外）"""
            if form == "块数组":
                return (
                    [
                        {
                            "type": "text",
                            "text": f"{line}\n{prefix_text}",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    q,
                )
            return (
                f"{line}\n{prefix_text}",
                [
                    {
                        "type": "text",
                        "text": K22_STRING_FORM_ACK_BLOCK,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": q},
                ],
            )

        # 8-10k tok prefill 耗时显著——超时下限保护（K3 模式）
        original_timeout = api_client.timeout
        api_client.timeout = max(original_timeout, K22_MIN_REQUEST_TIMEOUT)
        try:
            group_summaries: List[str] = []
            group_verdicts: List[bool] = []
            group_fail_log: List[str] = []
            for g, group_cfg in enumerate(K22_GROUPS, 1):
                # 组间间隔 3 秒（用户指定）——降低组间背靠背请求的
                # 调度/缓存抖动
                if g > 1:
                    test_logger.info(
                        f"[第{g}组] 组间间隔 3 秒（用户指定）"
                    )
                    time.sleep(3)
                gname, form, lang, unit, target_chars, q_filler = (
                    group_cfg
                )
                # 渠道标记行（用户指定）：两协议前缀正文相同、头部
                # 标记不同——剥离计费行后仍从位置 0 分叉，互不命中
                # 对方缓存条目（跨协议共享 KV 时 messages 冷轮"即
                # 热"的问题随之消除——各自建条目/各自命中）；标记
                # 差异仅数字符，对命中率影响可忽略
                prefix_body = unit * (target_chars // len(unit) + 1)
                chat_prefix = (
                    f"批次编号 {run_id} 第 {g} 组 渠道 chat\n"
                    + prefix_body
                )
                msg_prefix = (
                    f"批次编号 {run_id} 第 {g} 组 渠道 anthropic\n"
                    + prefix_body
                )
                hot_compare: List[str] = []
                group_ok = True
                for k in range(1, K22_ROUNDS + 1):
                    q = question_for(lang, k, q_filler)
                    # 同轮交替发送两协议（同问；前缀头部渠道标记不
                    # 同——互不命中对方缓存条目）
                    chat_usage = chat_round(
                        g, gname, k, chat_prefix, q
                    )
                    line = billing_line()
                    system_field, user_field = build_request(
                        form, line, msg_prefix, q
                    )
                    msg_usage = messages_round(
                        g,
                        gname,
                        form,
                        k,
                        msg_prefix,
                        q,
                        system_field,
                        user_field,
                        line,
                    )
                    if k <= K22_COLD_ROUNDS:
                        # 冷轮：两协议均无缓存可命中，不参与比较（用
                        # 户口径：需热轮才能统计命中率）——仅做长度
                        # sanity 留痕
                        pt_cold = chat_usage.get("prompt_tokens") or 0
                        if pt_cold and pt_cold < 8000:
                            test_logger.warning(
                                f"[第{g}组·{gname}] 冷轮请求长度 "
                                f"{pt_cold} tokens 不足 8k——请加"
                                "大该组前缀目标字符数"
                            )
                        continue
                    # ---- 热轮：逐轮比较两协议命中率（用户口径） ----
                    pt = chat_usage.get("prompt_tokens") or 0
                    cached = cached_of(chat_usage) or 0
                    chat_rate = cached / pt if pt else 0.0
                    read = cache_usage_field(
                        msg_usage,
                        "cache_read_input_tokens",
                        "cache_read_tokens",
                    )
                    creation = cache_usage_field(
                        msg_usage,
                        "cache_creation_input_tokens",
                        "cache_creation_tokens",
                    )
                    input_tok = msg_usage.get("input_tokens") or 0
                    # ---- 热轮全量 miss 重发加固（用户指定）：
                    # read=0 且 creation=0 时同轮重发一次（新计费
                    # 行、同前缀同问）——重发命中=偶发 miss（疑似
                    # 多实例路由/条目可见性问题，WARN 留痕交开
                    # 发）；重发仍 miss=剥离失效形态（FAIL——剥离
                    # 失效时重发同样 miss，判别力不变）----
                    did_retry = False
                    if read == 0 and creation == 0:
                        did_retry = True
                        test_logger.warning(
                            f"[第{g}组·{gname}] 第{k}热轮 messages "
                            f"全量 miss（read=0, creation=0, "
                            f"input_tokens={input_tok}）——同轮重"
                            "发一次鉴别：重发命中=偶发 miss（疑似"
                            "多实例路由/条目可见性问题）；仍 miss="
                            "计费行剥离失效形态"
                        )
                        line = billing_line()
                        system_field, user_field = build_request(
                            form, line, msg_prefix, q
                        )
                        msg_usage = messages_round(
                            g,
                            gname,
                            form,
                            k,
                            msg_prefix,
                            q,
                            system_field,
                            user_field,
                            line,
                            attempt=2,
                        )
                        read = cache_usage_field(
                            msg_usage,
                            "cache_read_input_tokens",
                            "cache_read_tokens",
                        )
                        creation = cache_usage_field(
                            msg_usage,
                            "cache_creation_input_tokens",
                            "cache_creation_tokens",
                        )
                        input_tok = (
                            msg_usage.get("input_tokens") or 0
                        )
                        if read or creation:
                            test_logger.warning(
                                f"[第{g}组·{gname}] 第{k}热轮重发命"
                                f"中（read={read}, creation="
                                f"{creation}）——首次 miss 判定为偶"
                                "发（重发即中，非计费行剥离缺陷—"
                                "—剥离失效时重发同样 miss），留痕"
                                "交开发排查"
                            )
                    # 分母口径自适应（同轮 chat prompt_tokens 为参
                    # 照）：input_tokens 已含命中总量（超过参照
                    # 80%）时直接作分母；否则（官方语义——仅计未命
                    # 中输入）加 read
                    if (
                        pt
                        and input_tok
                        > pt * K22_INPUT_TOTAL_SEMANTICS_RATIO
                    ):
                        denom = input_tok
                    else:
                        denom = input_tok + read
                    msg_rate = read / denom if denom else 0.0
                    gap = abs(chat_rate - msg_rate)
                    test_logger.info(
                        f"[第{g}组·{gname}] 第{k}轮（热轮）: chat="
                        f"{chat_rate:.2%}（cached={cached}/{pt}），"
                        f"messages={msg_rate:.2%}（read={read}/"
                        f"{denom}，input_tokens={input_tok}，"
                        f"creation={creation}），差值={gap:.2%}"
                        f"（容差 3 个百分点）"
                    )
                    if creation:
                        test_logger.warning(
                            f"[第{g}组·{gname}] 第{k}热轮 "
                            f"cache_creation={creation}——热轮仍在"
                            "重建缓存，前缀逐请求变化（剥离失效直"
                            "接信号）"
                        )
                    if chat_rate < 0.3 and msg_rate < 0.3:
                        test_logger.warning(
                            f"[第{g}组·{gname}] 第{k}热轮两协议命"
                            f"中率均异常低（chat={chat_rate:.2%}，"
                            f"messages={msg_rate:.2%}）——疑似全"
                            "局缓存异常（chat 侧由 K15/K16 覆盖），"
                            "本用例按用户口径仅判定协议间差值"
                        )
                    hot_compare.append(
                        f"第{k}轮 chat={chat_rate:.2%}/"
                        f"messages={msg_rate:.2%}/差值{gap:.2%}"
                        + ("（首次 miss 重发后）" if did_retry else "")
                        + (
                            "（超差）"
                            if gap > K22_PARITY_TOLERANCE
                            else ""
                        )
                    )
                    # ---- 组级判定（用户指定）：单组失败不中断
                    # 后续组——超差热轮仅记录该组不符合预期，五组
                    # 全部执行完按 ≥4/5 组符合预期最终判定 ----
                    if gap > K22_PARITY_TOLERANCE:
                        group_ok = False
                        fail_detail = (
                            f"差值 {gap:.2%} 超过容差 3 个百分点"
                            f"——chat={chat_rate:.2%}"
                            f"（cached={cached}/{pt}），messages="
                            f"{msg_rate:.2%}（read={read}/{denom}，"
                            f"input_tokens={input_tok}，creation="
                            f"{creation}）"
                            + (
                                "；已同轮重发鉴别：重发仍全量 "
                                "miss——计费行剥离失效或条目持续"
                                "不可见（多实例路由/可见性问题）"
                                if did_retry
                                else ""
                            )
                        )
                        group_fail_log.append(
                            f"第 {g} 组（{gname}，{form} 形态）"
                            f"第 {k} 热轮 {fail_detail}"
                        )
                        test_logger.error(
                            f"[第{g}组·{gname}] 第{k}热轮 "
                            f"{fail_detail}——该组判定为不符合预期"
                            "（不影响后续组，用户指定）"
                        )
                group_verdicts.append(group_ok)
                group_summaries.append(
                    f"第{g}组·{gname}（{form}）: "
                    + "，".join(hot_compare)
                    + (
                        " → 组判定: 符合预期"
                        if group_ok
                        else " → 组判定: 不符合预期"
                    )
                )
                test_logger.info(
                    f"[第{g}组·{gname}] 组内热轮比较完成: "
                    + "；".join(hot_compare)
                    + (
                        " → 组判定: 符合预期"
                        if group_ok
                        else " → 组判定: 不符合预期"
                    )
                )
            # ---- 最终判定（用户指定）：5 组中至少 4 组符合预期 ----
            ok_count = sum(1 for v in group_verdicts if v)
            test_logger.info(
                f"组级判定汇总: {ok_count}/{len(group_verdicts)} 组符"
                f"合预期（阈值 ≥{K22_MIN_PASS_GROUPS} 组，用户指"
                f"定）——{'；'.join(group_summaries)}"
            )
            assert ok_count >= K22_MIN_PASS_GROUPS, (
                f"客户问题复现失败：{len(group_verdicts)} 组中仅 "
                f"{ok_count} 组符合预期（阈值 ≥"
                f"{K22_MIN_PASS_GROUPS} 组，用户指定）——失败明细："
                + " || ".join(group_fail_log)
                + "。缺陷形态：计费行留在 system 头部、逐请求变化"
                "致前缀从位置 0 失配，messages 命中率应 ≈0%（该形"
                "态下五组全部不符合预期）；修复后两协议每热轮均应 "
                "≈94%（五组全符合预期）"
            )
            if ok_count < len(group_verdicts):
                test_logger.warning(
                    f"{len(group_verdicts) - ok_count} 组不符合预期"
                    f"但未达失败阈值（≥{K22_MIN_PASS_GROUPS} 组）"
                    "——留证交开发排查（多实例路由/条目可见性问题）"
                )
            test_logger.info(
                "客户问题复现通过: 组级判定 "
                f"{ok_count}/{len(group_verdicts)} 组符合预期（每次"
                "循环请求消息各异，中英文兼备）——"
                f"{'；'.join(group_summaries)}"
            )
        finally:
            api_client.timeout = original_timeout

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_orphan_tool_message_accepted(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K23 [P0]: 客户问题 - 孤儿 tool 消息应对齐官方放行并正常消费

        客户问题（新工单，官方对齐口径）：messages 中 tool 角色消息前
        无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未定
        义任何 tools），平台返回 400（"Invalid parameter: messages
        with role 'tool' must be a response to a preceeding message
        with 'tool calls'."——type: alaya code error、code:
        invalid text request——网关层白加的校验）；而智谱官方源对
        同一请求 HTTP 200 正常应答「北京今天天气晴朗，气温18℃」，
        且模型在 reasoning 中实际引用了 tool 消息里的数据（工具数
        据被模型正常消费）。
        新契约（客户指定）：预期结果同官方一致——此类消息序列不做
        校验、正常出结果。
        与 K14 的关系：K14（test_orphan_tool_message_rejected）为
        当时工单口径的原始契约（网关校验拒绝 400），按用户指令保
        持不变；本用例记录新客户需求（官方对齐契约：接受并正常消
        费）。二者输入同类、预期相反——平台采纳官方对齐修复后
        K14 将 FAIL，其保留/退役由用户决定（本用例不改动 K14）。
        本用例按客户新工单原始请求体还原（messages=[user"查一下北
        京天气"、assistant"好的，我来为您查询北京天气数据。"（纯文
        本、无 tool_calls——孤儿条件）、tool tool_call_id=
        "call_weather_001" content={"city":"北京","temp_c":18,
        "condition":"晴"}、user"根据工具返回的数据，用一句话告诉我
        天气。"]、max_tokens=200、非流式、无 tools/thinking）。
        硬断言：
        1. HTTP 200（核心——原始 400 拦截形态复现即 FAIL）
        2. 响应合法 JSON 且 choices 非空
        3. message 有效输出（content 或 tool_calls 非空——官方形
           态为正常答句，工具调用响应亦为成功形态）
        耗光回退（K24/K25/K27 口径）：无输出+finish=length 为
        max_tokens=200 预算被思考耗尽形态（GLM-5.3 恒开思考）——
        非契约违约（HTTP 200 已达成）；以 reasoning_effort=low 重
        发（构造不变仅加顶层字段），断言相同；双强度均未产出即
        FAIL（留证交开发）。
        官方行为细节（输出/推理引用工具数据要素）为软校验仅日志；
        finish/usage 仅日志。采样参数不发送——test_k 保持原始测试
        参数（工单原始请求未指定，不注入）。模型真实响应（状态码/响应体全文）断言前打印（失败
        时同样可见）。（不进 smoke 集：新用例首跑观察期）
        """
        # K23: 客户新工单原始请求体口径（勿改——孤儿 tool 消息的最
        # 小充分条件：assistant 纯文本消息后直接跟 tool 消息，无
        # tool_calls 关联，且请求不定义任何 tools）
        K23_MESSAGES = [
            {"role": "user", "content": "查一下北京天气"},
            {
                "role": "assistant",
                "content": "好的，我来为您查询北京天气数据。",
            },
            {
                "role": "tool",
                "tool_call_id": "call_weather_001",
                "content": (
                    "{\"city\": \"北京\", \"temp_c\": 18, "
                    "\"condition\": \"晴\"}"
                ),
            },
            {
                "role": "user",
                "content": "根据工具返回的数据，用一句话告诉我天气。",
            },
        ]
        # K23: 工单原始输出上限（官方同参数下正常答句）
        K23_MAX_TOKENS = 200
        # K23: 原始 400 报错关键文案（缺陷形态判别/报文引用）
        K23_ORPHAN_ERROR_TEXT = (
            "messages with role 'tool' must be a response to a "
            "preceeding message with 'tool calls'"
        )
        # K23: 官方答句应含的天气要素（软校验——工具数据被模型消费
        # 的信号；仅日志，不作硬断言——生成措辞自由）
        K23_TOOL_DATA_HINTS = ("北京", "18", "晴")

        test_logger.info(
            "=== 测试开始: 客户问题 - 孤儿 tool 消息官方对齐（前无 "
            "assistant tool_calls 且未定义 tools——官方 200 正常消"
            "费工具数据，平台 400 白加校验为缺陷形态；期望 200+有效"
            "输出）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # 采样参数不发送——test_k 保持原始测试参数（工单原始请求
        # 未指定，不注入）

        # 手工构造 payload 直发（含 tool 角色消息，chat_completion
        # 封装不支持；工单原始请求体为非流式——不传 stream；采样
        # 参数不发送——test_k 保持原始测试参数）
        payload = {
            "model": api_client.model_name,
            "messages": K23_MESSAGES,
            "max_tokens": K23_MAX_TOKENS,
        }

        TestLogger.log_request(
            test_logger,
            K23_MESSAGES,
            {
                "max_tokens": K23_MAX_TOKENS,
                "tools": "(未定义)",
                "thinking": "(不传，工单原始请求体口径)",
                "stream": "(不传——默认非流式)",
                "temperature": "(不发送)",
                "top_p": "(不发送)",
                "seed": "(不发送)",
            },
        )

        started = time.time()
        try:
            response = api_client._post_with_retry(
                url, payload, stream=False
            )
        except Exception as e:
            pytest.fail(f"请求发送异常（{url}）: {e}")
        elapsed = time.time() - started

        # 模型真实响应断言前打印（状态码/响应体全文——失败时同样可
        # 见，便于诊断）
        test_logger.info(
            f"真实响应: HTTP {response.status_code}, elapsed="
            f"{elapsed:.1f}s, body={response.text[:800]!r}"
        )

        # 断言1（核心）：官方对齐——应放行并正常响应（原始 400 拦截
        # 形态复现即 FAIL）
        defect_note = (
            "缺陷形态：网关层白加校验返回 400 "
            f"\"{K23_ORPHAN_ERROR_TEXT}\"（type: alaya code error、"
            "code: invalid text request）；官方源同一请求 200 正常"
            "应答「北京今天天气晴朗，气温18℃」，且模型在 reasoning "
            "中实际引用了 tool 消息里的数据"
        )
        if response.status_code == 400 and "role 'tool'" in response.text:
            defect_note = (
                "缺陷形态精确复现（网关白加校验拦截——原始 400 报错"
                f"形态）。{defect_note}"
            )
        assert response.status_code == 200, (
            f"客户问题复现失败：孤儿 tool 消息应按官方口径放行并正"
            f"常响应，实际 HTTP {response.status_code}——"
            f"{response.text[:400]!r}。{defect_note}"
        )

        # 断言2：响应合法 JSON 且 choices 非空
        try:
            body = response.json()
        except ValueError as e:
            pytest.fail(
                f"客户问题复现失败：响应应为合法 JSON，解析异常: {e}"
                f"（响应体已记录于测试日志）"
            )
        choices = body.get("choices") or []
        assert choices, (
            f"客户问题复现失败：choices 为空——响应体已记录于测试日志"
        )

        # 断言3：message 有效输出（官方形态为正常答句）
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []
        finish = choices[0].get("finish_reason")
        # 耗光回退（K24/K25/K27 口径）：无输出+finish=length 为
        # max_tokens=200 预算被思考耗尽形态（GLM-5.3 恒开思考）——
        # 非契约违约（接受性契约 HTTP 200 已达成）；以
        # reasoning_effort=low 重发（构造不变仅加顶层字段），断言相
        # 同；双强度均未产出即 FAIL（留证交开发）
        if not content and not tool_calls and finish == "length":
            test_logger.info(
                "第 1 次请求思考耗光预算（无输出 + finish=length——"
                "HTTP 200 核心契约已达成），按 K24/K25/K27 口径以 "
                "reasoning_effort=low 回退重发（构造不变仅加顶层 "
                "reasoning_effort 字段）"
            )
            retry_payload = {**payload, "reasoning_effort": "low"}
            TestLogger.log_request(
                test_logger,
                K23_MESSAGES,
                {
                    "max_tokens": K23_MAX_TOKENS,
                    "tools": "(未定义)",
                    "thinking": "(不传，工单原始请求体口径)",
                    "stream": "(不传——默认非流式)",
                    "temperature": "(不发送)",
                    "top_p": "(不发送)",
                    "seed": "(不发送)",
                    "reasoning_effort": "low",
                },
            )
            started_r = time.time()
            try:
                response_r = api_client._post_with_retry(
                    url, retry_payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"low 回退重发异常（{url}）: {e}")
            elapsed_r = time.time() - started_r
            test_logger.info(
                f"low 回退真实响应: HTTP {response_r.status_code}, "
                f"elapsed={elapsed_r:.1f}s, "
                f"body={response_r.text[:800]!r}"
            )
            assert response_r.status_code == 200, (
                f"low 回退重发失败：实际 HTTP "
                f"{response_r.status_code}: {response_r.text[:400]}"
            )
            try:
                body = response_r.json()
            except ValueError as e:
                pytest.fail(
                    f"low 回退响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices = body.get("choices") or []
            assert choices, (
                "low 回退响应 choices 为空——响应体已记录于测试日志"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls") or []
            finish = choices[0].get("finish_reason")
            if not content and not tool_calls and finish == "length":
                pytest.fail(
                    "low 回退重发后仍无产出（默认与 low 双强度思考均"
                    "耗光预算——留证交开发）"
                )
        budget_note = (
            "（finish=length：max_tokens=200 预算被思考耗尽的空正文"
            "形态——与 400 拦截形态区分，需评估官方对齐下的预算口"
            "径）"
            if finish == "length" and not (content or tool_calls)
            else ""
        )
        assert content or tool_calls, (
            f"客户问题复现失败：message 无有效输出（content 与 "
            f"tool_calls 均空，finish={finish}）——官方同参数下正常"
            f"应答{budget_note}（响应体已记录于测试日志）"
        )

        # 官方行为细节软校验（仅日志）：输出/推理引用工具数据要素
        # （北京/18/晴）= 工具数据被模型正常消费的信号
        reasoning = (
            message.get("reasoning_content")
            or message.get("reasoning")
            or ""
        )
        consumed = [
            h
            for h in K23_TOOL_DATA_HINTS
            if h in content or h in reasoning
        ]
        if consumed:
            test_logger.info(
                f"官方行为细节（软校验通过）: 输出/推理引用了工具数"
                f"据要素（{'、'.join(consumed)}）——工具数据被模型"
                "正常消费（官方对齐形态）"
            )
        else:
            test_logger.info(
                "官方行为细节（软校验未命中）: 输出/推理未引用工具数"
                "据要素（生成措辞自由，不作硬断言）"
            )
        test_logger.info(f"finish={finish}, usage={body.get('usage')}")

        test_logger.info(
            "客户问题复现通过: 孤儿 tool 消息按官方口径放行——HTTP "
            "200 且 message 有效输出（400 白加校验拦截形态未复现，"
            "与官方源行为对齐）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_dual_request_response_with_effort_fallback(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K24 [P0]: 客户问题 - 双请求正常响应（思考耗尽预算 low 强度回退）

        客户问题（新工单）：客户的两个请求——中文写作题（文段中找
        同音词与[言部]汉字并写 800 字左右荷塘月色文章，关键词月光/
        这/意义限用）与英文数学题（三个正实数 k 使 f(x)=((x-18)
        (x-72)(x-98)(x-k))/x 在正实数上恰于两点取最小，求 k 之和）
        ——两请求体均为 glm-5.3、temperature=0.0、
        max_completion_tokens=32768、非流式，期望均正常响应并返回
        正文。
        风险形态（用户指定）：默认（max）思考强度下，思考内容可能
        耗光 max_completion_tokens 预算——正文为空、finish=length。
        回退契约（用户指定）：第 1 轮按工单原始请求体直发（不带
        reasoning_effort——默认强度即 max）；有正常正文即该请求
        通过并退出；思考耗光的请求以 reasoning_effort="low"（GLM
        顶层思考强度参数，K20 口径）重发，断言相同；第 2 轮只重测
        第 1 轮耗光的请求（已通过的不重测）。
        采样参数保持原始（用户指定）：两个请求体均显式指定
        temperature=0.0——工单原始请求体为唯一口径，test_k 整套
        件不参与全局采样覆盖，top_p/seed 亦不注入。
        硬断言（每轮每请求）：①HTTP 200；②响应合法 JSON 且
        choices 非空；③message 有效输出（content 或 tool_calls 非
        空）。第 1 轮正文空且 finish=length 为耗光形态按契约转
        low 回退（不直接 FAIL）；正文空且 finish≠length 直接
        FAIL；low 回退轮仍无正文即 FAIL（双强度均未产出有效输出
        ——报文留证交开发）。finish/usage 仅日志。模型真实响应
        （状态码/响应体全文）断言前打印（失败时同样可见）。运行
        日志不含具体模型名。（不进 smoke 集：新用例首跑观察期）
        """
        # K24: 工单请求之一——中文写作题（文段与要求按工单原文还
        # 原：要求条目间换行、关键词以双引号包裹，均为工单原文形
        # 态）
        K24_CONTENT_ZH = (
            "请您选出以下内容中的同音词以及特定部首的字，并用这些"
            "词和字写一篇，描写荷塘月色的文章。【在晨曦初升的"
            "时刻，水面如镜，倒映着熠熠生辉的霞光，远处的山屿若隐"
            "若现。水鸟掠过，羽翼轻拂，仿佛在湖心写下意义深远的诗"
            "句。湖畔柳丝轻摆，仿佛在对这喧嚣尘世提出温和的异议。"
            "它用自己的方式诠释着时光——不是激烈的抗争，而是如意"
            "译般的转化，将内心的不安化作诗意的舞蹈，在风中低语着"
            "属于自然的哲学。微风拂过，令人思忖，悄然唤醒沉睡已久"
            "的情愫。远处雄峰屹立，山峦叠嶂，岚气舒卷，山色漫衍,如"
            "同岁月的画卷。每一寸光影都在诉说着生命的意义，而每一"
            "朵花的开放，都有它独特的意义。阳光透过云层，照亮了无"
            "数微小的欢愉。大地静默，万物各自用自己的方式诠释着时"
            "光的温柔，怡然生长，静静守候。万物的心志与自然的情感"
            "交融，在这静谧的清晨,人们心怀喜悦开启新的一天。】要求"
            "如下：1.从文段中找出读音相同的二字词语，发音包括声调"
            "完全相同，在你的文章中需要用到至少4个文段中这样的同"
            "音词。\n2.从文段中找出部首是[言部]的汉字，并在你的文"
            "章中至少用到7个。\n3.你的文章字数需要在800字左右，左"
            "右意味着允许上下浮动10%。\n"
            '4.关键词"月光","这","意义"在你的文章中使用不能超过'
            "2次。请你直接给出文章。"
        )
        # K24: 工单请求之二——英文数学题
        K24_CONTENT_MATH = (
            "There are exactly three positive real numbers k such "
            "that the function\n\n"
            "f(x) = ((x - 18)(x - 72)(x - 98)(x - k)) / x\n\n"
            "defined over the positive real numbers achieves its "
            "minimum value at exactly two positive real numbers "
            "x.\n\n"
            "Find the sum of these three values of k."
        )
        # K24: 工单两个请求（标签 + 原始 messages——均为 user 单轮）
        K24_REQUESTS = [
            (
                "请求一（中文：同音词与言部汉字写作）",
                [{"role": "user", "content": K24_CONTENT_ZH}],
            ),
            (
                "请求二（英文：数学题）",
                [{"role": "user", "content": K24_CONTENT_MATH}],
            ),
        ]
        # K24: 工单原始公共参数——max_completion_tokens 为工单原
        # 始字段名（非 max_tokens，勿改）；temperature 显式 0.0
        # （豁免全局覆盖——工单体为唯一口径）
        K24_MAX_COMPLETION_TOKENS = 32768
        K24_TEMPERATURE = 0.0
        # K24: 思考耗尽预算的回退强度——GLM 顶层 reasoning_effort
        # 参数取 low（K20 口径）
        K24_EFFORT_LOW = "low"
        # K24: max 思考 + 32768 大预算耗光耗时显著（非流式整包返
        # 回）——单请求超时下限（配置已 >= 该值时为 no-op）
        K24_MIN_REQUEST_TIMEOUT = 1800

        def send_and_judge(
            label: str,
            messages: List[Dict[str, Any]],
            effort_label: str,
            effort_value: Any,
            allow_exhausted: bool,
        ) -> Dict[str, Any]:
            """K24 单次请求发送与判定：工单口径 payload 直发，返
            回 {"passed": bool, "exhausted": bool}——硬失败直接
            断言/pytest.fail；第 1 轮耗光形态（allow_exhausted=
            True 时）标记回退由调用方重发"""
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": messages,
                "stream": False,
                "max_completion_tokens": K24_MAX_COMPLETION_TOKENS,
                "temperature": K24_TEMPERATURE,
            }
            if effort_value is not None:
                payload["reasoning_effort"] = effort_value
            TestLogger.log_request(
                test_logger,
                messages,
                {
                    "max_completion_tokens": K24_MAX_COMPLETION_TOKENS,
                    "temperature": "0.0（工单原始——豁免全局覆盖）",
                    "stream": False,
                    "reasoning_effort": effort_label,
                },
            )
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"{label} 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started
            # 模型真实响应断言前打印（状态码/响应体全文——失败时
            # 同样可见，便于诊断）
            test_logger.info(
                f"{label} 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, body={response.text[:800]!r}"
            )
            assert response.status_code == 200, (
                f"客户问题复现失败：{label} 应正常响应（HTTP 200），"
                f"实际 HTTP {response.status_code}——"
                f"{response.text[:400]!r}"
            )
            try:
                body = response.json()
            except ValueError as e:
                pytest.fail(
                    f"客户问题复现失败：{label} 响应应为合法 JSON，"
                    f"解析异常: {e}（响应体已记录于测试日志）"
                )
            choices = body.get("choices") or []
            assert choices, (
                f"客户问题复现失败：{label} choices 为空——"
                f"响应体已记录于测试日志"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls") or []
            finish = choices[0].get("finish_reason")
            test_logger.info(
                f"{label} finish={finish}, usage={body.get('usage')}"
            )
            if content or tool_calls:
                test_logger.info(
                    f"{label} 正文有效（content {len(content)} 字符"
                    "）——该请求通过"
                )
                return {"passed": True, "exhausted": False}
            if allow_exhausted:
                # 第 1 轮：仅思考耗光形态（正文空+finish=length）可
                # 转回退；其他空响应为异常形态直接 FAIL
                assert finish == "length", (
                    f"客户问题复现失败：{label} 无有效输出且非思考"
                    f"耗光形态（content 与 tool_calls 均空，"
                    f"finish={finish}；响应体已记录于测试日志）"
                )
                test_logger.info(
                    f"{label} 思考耗光预算（正文空 + finish="
                    "length，默认 max 思考强度）——按用户指定契约转"
                    " reasoning_effort=low 回退重发"
                )
                return {"passed": False, "exhausted": True}
            pytest.fail(
                f"客户问题复现失败：{label}（low 强度回退轮）仍无"
                f"有效输出（content 与 tool_calls 均空，finish="
                f"{finish}）——默认 max 与 low 双强度均未产出有效"
                f"输出，报文已留存于测试日志供开发排查"
            )

        test_logger.info(
            "=== 测试开始: 客户问题 - 双请求正常响应（默认 max 思考"
            "强度有正文即过；思考耗光预算按 reasoning_effort=low "
            "回退重发且仅测耗光请求——用户指定契约；temperature=0.0"
            " 工单口径豁免全局采样覆盖）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # 采样参数保持原始（用户指定）：两个请求体均显式
        # temperature=0.0——工单原始请求体为唯一口径（test_k 整
        # 套件不参与全局采样覆盖），top_p/seed 亦不注入——payload
        # 直用工单原值

        # 超时保护：max 思考 + 32768 预算耗光耗时显著——单请求超
        # 时下限（配置已 >= 该值时为 no-op）
        original_timeout = api_client.timeout
        api_client.timeout = max(
            original_timeout, K24_MIN_REQUEST_TIMEOUT
        )
        try:
            # ---- 第 1 轮：默认 max 思考强度（工单原始请求体，不带
            # reasoning_effort）----
            outcomes: Dict[int, str] = {}
            exhausted_specs: List[Any] = []
            for idx, (label, messages) in enumerate(K24_REQUESTS, 1):
                result = send_and_judge(
                    f"{label}（第 1 轮：默认 max 思考强度）",
                    messages,
                    effort_label=(
                        "（不传——默认 max 思考强度，工单原始请求体）"
                    ),
                    effort_value=None,
                    allow_exhausted=True,
                )
                if result["passed"]:
                    outcomes[idx] = "默认 max 强度通过"
                else:
                    exhausted_specs.append((idx, label, messages))

            # ---- 第 2 轮：思考耗光的请求按 low 强度回退重发（仅第
            # 1 轮耗光的——已通过的不重测，用户指定）----
            if not exhausted_specs:
                test_logger.info(
                    "两个请求在默认 max 思考强度下均返回正常正文"
                    "——无需 low 回退轮"
                )
            for idx, label, messages in exhausted_specs:
                send_and_judge(
                    f"{label}（第 2 轮：low 强度回退）",
                    messages,
                    effort_label=(
                        "low（思考耗光回退——GLM 顶层 "
                        "reasoning_effort，K20 口径）"
                    ),
                    effort_value=K24_EFFORT_LOW,
                    allow_exhausted=False,
                )
                outcomes[idx] = "low 强度回退通过"

            test_logger.info(
                "客户问题复现通过: 两个请求均正常响应并返回正文——"
                + "；".join(
                    f"请求{idx}（{outcomes[idx]}）"
                    for idx in sorted(outcomes)
                )
            )
        finally:
            api_client.timeout = original_timeout

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_duplicate_reasoning_content_history_accepted(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """K25 [P0]: 客户问题 - assistant 历史重复 reasoning_content
        字段应被兼容接受

        客户问题（工单跟进）：多轮对话回填 assistant 历史时，同一条
        消息携带两个 reasoning_content 字段（两轮历史思考未去重地拼
        接成同键重复）与上一次请求的正文。客户原始工单还曾因思考内
        容含 They're/I'm/It's 等英文撇号导致 JSON 破损——正文与思
        考内容可能含单引号/双引号/换行等字符，须兼容处理、不影响
        正常请求格式（用户指定）。
        契约（用户指定）：预期不报错、正常响应；第一个
        reasoning_content 被第二个覆盖（宽松解析保留最后一个值，
        K18 修复口径——兼容 assistant 历史重复的 reasoning 字段）。
        因需两段真实思考内容，共发三次请求（用户指定，JSON 链式回
        填——第 1/2 次响应 JSON 作为下一请求输入、思考随历史一并
        回填）：
        - 第 1 次请求（user 单轮，流式）：要求仅输出 JSON——采集第
          1 段思考+第 1 次正文（JSON，作为第 2 次请求输入回填）；
        - 第 2 次请求（流式）：messages=[assistant(content=第 1 次正
          文（JSON）, reasoning_content=第 1 次思考), user 追问]——回
          填第 1 次历史（单 reasoning_content 经 dict 表达，K18 口
          径），要求仅输出 JSON——采集第 2 段思考+第 2 次正文
          （JSON，作为第 3 次请求输入回填）；
        - 第 3 次请求（流式）：messages=[assistant(content=第 2 次正
          文（JSON）, reasoning_content=第 1 次思考,
          reasoning_content=第 2 次思考), user 追问]。
        提示词为测试自行设计（工单未携带具体提示词——用户口径仅要
        求结构：JSON 链式回填+两个 reasoning_content）。
        同键字面重复无法经 dict 表达——手工拼接 JSON 文本直发；所有
        动态值（正文/思考）一律经 json.dumps 全转义后拼接（单/双引
        号、换行、反斜杠全转义），发送前三重自检：
        1. raw body 可被 json.loads 解析（动态值含特殊字符时转义正
           确，客户原始 JSON 破损形态在此拦截）；
        2. "reasoning_content" 键在 raw body 中出现且仅出现 2 次
           （重复键真实上送，不被 dict 去重）；
        3. 转义回读一致——json.loads 保留最后一个重复键（与服务端
           宽松解析"第一个被第二个覆盖"契约一致），content 与第 2 次
           正文逐字一致。
        硬断言：第 1/2 次请求思考与正文均非空（第 3 次请求的构造数
        据源——被测环境应开思考，GLM-5.3 默认开思考，无思考即环境异
        常 FAIL 留证）、正文为合法 JSON（JSON 链——第 1/2 次响应作
        为下一请求输入回填，断裂即场景无法构造 FAIL；容忍 markdown
        代码块围栏）；第 3 次请求 HTTP 200（核心——重复
        reasoning_content 历史被拒绝即缺陷形态复现 FAIL）+ SSE 事
        件非空 + 合并正文非空 + finish_reason 合法。
        耗光回退（K24 口径）：max_tokens=8192 下默认 max 档思考可
        能耗尽预算（正文空+finish=length，K24 实测 32768 预算亦可
        被耗光）——该形态不判失败，以 reasoning_effort=low（GLM
        顶层思考强度参数，K20 口径）仅重发耗光请求（第 3 次重发
        构造不变，仅加顶层 reasoning_effort 字段——HTTP 200 核心
        契约首次请求已达成，重复键历史被接受不以正文是否为空转
        移），断言相同；正文空且 finish≠length 直接 FAIL；low 回
        退仍无正文即 FAIL（默认 max 与 low 双强度均未产出——留证
        交开发）。
        引号覆盖度软观察：三个回填值（第 2 次正文/两次思考）均不含
        引号/换行字符时 record_warning 留痕——引号兼容路径本次未被
        实际覆盖（构造本身已保证安全，不判失败）。
        采样参数不发送——test_k 保持原始测试参数（工单原始请求未
        指定，不注入）。max_tokens=8192 为客户工单原始口
        径，三次请求一致。usage 仅日志；模型真实响应（状态码/合并
        正文/思考）断言前打印（失败时同样可见）。（不进 smoke 集：
        新用例首跑观察期）
        """
        # K25: 第 1/2/3 次请求的用户消息（工单未携带具体提示词——
        # 测试自行设计；用户口径：第 1/2 次响应须为 JSON 作为下一
        # 请求输入回填，故第 1/2 次显式要求仅输出 JSON 对象；第 3
        # 次为 JSON 链终点追问，无 JSON 输出要求）
        K25_USER_Q1 = (
            "你好，请仅输出一个合法的 JSON 对象回答：2的平方根大约"
            '是多少？格式为 {"answer": "<你的回答>"}，除该 JSON 外'
            "不要输出任何其他文字。"
        )
        K25_USER_Q2 = (
            "继续，请仅输出一个合法的 JSON 对象回答：2的平方等于"
            '几？格式为 {"answer": "<你的回答>"}，除该 JSON 外不要'
            "输出任何其他文字。"
        )
        K25_USER_Q3 = "继续，3的平方等于几"

        # K25: 客户工单原始口径 max_tokens（三次请求一致）
        K25_MAX_TOKENS = 8192

        def as_json(text_value: str) -> Optional[Any]:
            """K25 JSON 解析（容忍 markdown 代码块围栏）：第 1/2 次
            响应正文须为合法 JSON——作为下一请求输入回填。"""
            stripped = text_value.strip()
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
            if stripped.startswith("```"):
                lines = stripped.splitlines()
                if len(lines) >= 2 and lines[-1].strip().endswith("```"):
                    inner = "\n".join(lines[1:-1]).strip()
                    try:
                        return json.loads(inner)
                    except json.JSONDecodeError:
                        return None
            return None

        def ask_and_collect(
            label: str,
            messages: List[Dict[str, Any]],
            require_json: bool = False,
        ) -> Dict[str, Any]:
            """K25 采集请求：流式获取一次思考+一次正文（JSON 链）

            第 1 次调用 messages=[user 单轮]；第 2 次调用回填第 1 次
            历史 [assistant(content=第 1 次正文 JSON,
            reasoning_content=第 1 次思考), user 追问]（单
            reasoning_content 经 dict 表达，K18 口径）。
            require_json=True 时断言响应正文为合法 JSON（用户口径：
            第 1/2 次响应作为下一请求输入回填——JSON 链条断裂即场
            景无法构造 FAIL）。
            采样参数不发送——test_k 保持原始测试参数（工单原始请
            求未指定，不注入）。
            耗光回退（K24 口径）：默认 max 档思考可能耗尽 8192 预
            算（正文空+finish=length），该形态以 reasoning_effort=
            low（GLM 顶层思考强度参数，K20 口径）仅重发本采集请求
            （断言相同）；正文空且 finish≠length 直接 FAIL；low 回
            退仍无正文即 FAIL（默认 max 与 low 双强度均未产出——留
            证交开发）。
            """

            def attempt(effort: Optional[str] = None) -> Dict[str, Any]:
                TestLogger.log_request(
                    test_logger,
                    messages,
                    {
                        "max_tokens": K25_MAX_TOKENS,
                        "stream": True,
                        "temperature": "(不发送)",
                        **(
                            {"reasoning_effort": effort}
                            if effort is not None
                            else {}
                        ),
                    },
                )
                request_kwargs: Dict[str, Any] = {
                    "max_tokens": K25_MAX_TOKENS
                }
                if effort is not None:
                    request_kwargs["reasoning_effort"] = effort
                response_iter = api_client.chat_completion_stream(
                    messages, **request_kwargs
                )
                result = self.collect_stream_chunks(response_iter)
                finish_reason = None
                for chunk in reversed(result["chunks"]):
                    if chunk.get("choices"):
                        finish_reason = chunk["choices"][0].get(
                            "finish_reason"
                        )
                        break
                # 模型真实响应（合并正文/思考全文）断言前打印（失败
                # 时同样可见）
                effort_tag = (
                    f"（reasoning_effort={effort}）" if effort else ""
                )
                test_logger.info(
                    f"{label} 真实响应{effort_tag}: "
                    f"chunks={len(result['chunks'])}, "
                    f"finish={finish_reason}, "
                    f"content={result['content'][:2000]!r}, "
                    f"reasoning={result['reasoning'][:2000]!r}"
                )
                return {
                    "reasoning": result["reasoning"],
                    "content": result["content"],
                    "finish": finish_reason,
                    "chunks_count": len(result["chunks"]),
                }

            collected = attempt()
            if (
                not collected["content"].strip()
                and collected["finish"] == "length"
            ):
                test_logger.info(
                    f"{label} 思考耗光预算（正文空 + finish=length，"
                    f"默认 max 思考强度，max_tokens={K25_MAX_TOKENS}）"
                    f"——按 K24 口径以 reasoning_effort=low 重发采集"
                    f"（仅重发耗光请求，断言相同）"
                )
                collected = attempt("low")
            assert collected["chunks_count"], (
                f"{label} 未返回任何流式 chunks"
            )
            assert collected["reasoning"].strip(), (
                f"{label} 未返回思考内容（reasoning 为空）——本用例需"
                f"两段真实思考构造重复 reasoning_content 历史回填，"
                f"被测环境应开启思考（GLM-5.3 默认开思考）"
            )
            if not collected["content"].strip():
                if collected["finish"] == "length":
                    pytest.fail(
                        f"客户问题复现失败：{label} low 回退重发后仍无"
                        f"正文（finish=length）——默认 max 与 low 双强"
                        f"度均未产出正文，留证交开发"
                    )
                pytest.fail(
                    f"{label} 未返回正文（content 为空）且非思考耗光形"
                    f"态（finish={collected['finish']!r}）"
                )
            assert (
                collected["finish"] in self.VALID_STREAM_FINISH_REASONS
            ), f"{label} finish_reason 非法: {collected['finish']!r}"
            if require_json:
                parsed_json = as_json(collected["content"])
                if parsed_json is None:
                    test_logger.error(
                        f"{label} 响应正文非合法 JSON，正文: "
                        f"{collected['content'][:2000]!r}"
                    )
                assert parsed_json is not None, (
                    f"{label} 响应正文非合法 JSON——第 1/2 次响应须"
                    f"作为下一请求输入回填（JSON 链条断裂，场景无法构"
                    f"造）（正文已记录于测试日志）"
                )
                test_logger.info(
                    f"{label} 响应为合法 JSON: "
                    + json.dumps(parsed_json, ensure_ascii=False)[:400]
                )
            return collected

        def dumps(value: Any) -> str:
            """K25 动态值序列化：json.dumps 全转义——单/双引号、换
            行、反斜杠等一律转义，正文/思考内容含任意字符时 JSON 格
            式不破损（客户原始工单即因思考含 They're/I'm 等撇号致
            JSON 破损）"""
            return json.dumps(value, ensure_ascii=False)

        test_logger.info(
            "=== 测试开始: 客户问题 - assistant 历史重复 "
            "reasoning_content 字段（两次思考回填，宽松解析保留最后"
            "一个值——第一个被第二个覆盖）——三次请求 JSON 链式回填"
            "（用户口径）：第 1 次 user 单轮要求仅输出 JSON（响应作"
            "为第 2 次输入）；第 2 次回填第 1 次历史（content=第 1 "
            "次 JSON+reasoning_content=第 1 次思考）并要求仅输出 "
            "JSON（响应作为第 3 次输入）；第 3 次回填 assistant("
            "content=第 2 次 JSON, reasoning_content=第 1 次思考, "
            "reasoning_content=第 2 次思考)+user 追问，预期不报错、"
            "正常响应；动态值全转义（引号/换行兼容）；默认 max 思考"
            "耗光预算（正文空+finish=length）时按 K24 口径以 "
            "reasoning_effort=low 仅重发耗光请求==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # ---- 第 1 次请求：采集第 1 段思考+JSON 正文（第 2 次请求
        # 的输入）----
        first = ask_and_collect(
            "第 1 次请求（user 单轮，采集第 1 段思考+JSON 正文）",
            [{"role": "user", "content": K25_USER_Q1}],
            require_json=True,
        )

        # ---- 第 2 次请求：回填第 1 次历史（content=第 1 次正文
        # JSON+reasoning_content=第 1 次思考——单键经 dict 表达，
        # K18 口径），采集第 2 段思考+JSON 正文（第 3 次请求的输
        # 入）----
        second = ask_and_collect(
            "第 2 次请求（回填第 1 次历史，采集第 2 段思考+JSON 正文）",
            [
                {
                    "role": "assistant",
                    "content": first["content"],
                    "reasoning_content": first["reasoning"],
                },
                {"role": "user", "content": K25_USER_Q2},
            ],
            require_json=True,
        )

        # 采样参数不发送——test_k 保持原始测试参数（工单原始请求
        # 未指定，不注入）

        # ---- 构造第 3 次请求：assistant 历史同键 reasoning_content
        # 字面重复（dict 无法表达重复键，手工拼接 JSON 文本；content=
        # 第 2 次请求正文 JSON——上一次的回复，第 2 次响应作为本请
        # 求输入（JSON 链终点），两个 reasoning_content 分别为第 1、
        # 2 次请求的思考内容）----
        def build_third_body(effort: Optional[str] = None) -> str:
            """第 3 次请求 raw body 构造器（重复键直发专用）。

            耗光回退重发时 effort="low"（GLM 顶层思考强度参数，
            K24/K20 口径）——构造不变，仅加顶层 reasoning_effort 字
            段；每次构造均执行三重自检（low 回退体同样必须满足）。
            """
            assistant_raw = (
                "{"
                '"role": "assistant", '
                f'"content": {dumps(second["content"])}, '
                f'"reasoning_content": {dumps(first["reasoning"])}, '
                f'"reasoning_content": {dumps(second["reasoning"])}'
                "}"
            )
            user_raw = dumps({"role": "user", "content": K25_USER_Q3})
            messages_raw = f"[{assistant_raw}, {user_raw}]"
            effort_fields = (
                f'"reasoning_effort": {dumps(effort)}, '
                if effort is not None
                else ""
            )
            raw_body = (
                "{"
                f'"model": {dumps(api_client.model_name)}, '
                '"stream": true, '
                f'"max_tokens": {K25_MAX_TOKENS}, '
                f"{effort_fields}"
                f'"messages": {messages_raw}'
                "}"
            )
            # ---- 三重自检（每次构造均执行——low 回退体同样必须满
            # 足）：转义正确性与重复键真实性 ----
            # 自检1：raw body 为合法 JSON——正文/思考含单双引号/换
            # 行等字符时全转义后必须仍可解析（客户原始 JSON 破损形
            # 态在此拦截）
            parsed_body = json.loads(raw_body)
            # 自检2：重复键真实上送（wire 上出现且仅出现两次，不被
            # 去重）
            dup_count = raw_body.count('"reasoning_content"')
            assert dup_count == 2, (
                f"构造自检失败：raw body 中 reasoning_content 键应出现 2"
                f" 次（字面重复），实际 {dup_count} 次"
            )
            # 自检3：转义回读一致——json.loads 保留最后一个重复键
            # （与服务端宽松解析契约一致：第一个 reasoning_content 被
            # 第二个覆盖），content 与第 2 次请求正文逐字一致
            parsed_assistant = parsed_body["messages"][0]
            assert (
                parsed_assistant["reasoning_content"] == second["reasoning"]
            ), "构造自检失败：回读的 reasoning_content 与第 2 次请求思考不一致"
            assert parsed_assistant["content"] == second["content"], (
                "构造自检失败：回读的 content 与第 2 次请求正文不一致"
            )
            effort_tag = (
                f"（reasoning_effort={effort}）" if effort else ""
            )
            test_logger.info(
                f"第 3 次请求构造自检通过{effort_tag}: "
                f"raw body 合法 JSON、reasoning_content 键出现 "
                f"{dup_count} 次、转义回读值一致（raw body "
                f"{len(raw_body)} 字符）"
            )
            return raw_body

        raw_body = build_third_body()

        TestLogger.log_request(
            test_logger,
            [
                {
                    "role": "assistant",
                    "content": (
                        f"[第 2 次请求正文 JSON（上一次的回复），"
                        f"{len(second['content'])} 字符]"
                    ),
                },
                {"role": "user", "content": K25_USER_Q3},
            ],
            {
                "max_tokens": K25_MAX_TOKENS,
                "stream": True,
                "assistant_history_reasoning": (
                    "reasoning_content 键字面重复两次：第 1 次思考"
                    f"（{len(first['reasoning'])} 字符）+ 第 2 次思考"
                    f"（{len(second['reasoning'])} 字符）"
                ),
                "request_form": (
                    "raw JSON 文本直发（dict 无法表达重复键；动态值经"
                    " json.dumps 全转义）"
                ),
            },
        )

        # ---- 引号覆盖度软观察：三个回填值实际是否含引号/换行字符
        # ——含则引号兼容路径被真实覆盖；均不含仅 record_warning 留
        # 痕（构造已保证安全，不判失败）----
        quote_chars = ("'", '"', "\n")
        embedded_values = [
            ("第 2 次正文", second["content"]),
            ("第 1 次思考", first["reasoning"]),
            ("第 2 次思考", second["reasoning"]),
        ]
        any_quote_hit = False
        for value_label, value in embedded_values:
            hits = [repr(ch) for ch in quote_chars if ch in value]
            if hits:
                any_quote_hit = True
                test_logger.info(
                    f"回填值含特殊字符（{value_label}）: {'、'.join(hits)}"
                    f"——已全转义嵌入，引号兼容路径被真实覆盖"
                )
        if not any_quote_hit:
            warn_msg = (
                "K25: 本次运行回填的正文/思考均不含单双引号/换行字符"
                "——引号兼容路径未被实际覆盖（构造已保证安全：动态值一"
                "律经 json.dumps 全转义，仅覆盖度观察）"
            )
            test_logger.warning(warn_msg)
            record_warning(warn_msg)

        def send_raw_stream(label: str, body: str) -> Dict[str, Any]:
            """K25 第 3 次请求：raw JSON 文本直发（重复键无法经
            dict/json= 表达），解析 OpenAI 流式 SSE，返回合并的
            {"chunks", "content", "reasoning", "finish"}。

            非 200 直接 FAIL——客户契约为预期不报错、正常响应，重复
            reasoning_content 历史被拒绝（400/5xx）即缺陷形态复现。
            """
            try:
                response = api_client.session.post(
                    url,
                    data=body.encode("utf-8"),
                    timeout=api_client.timeout,
                    stream=True,
                )
            except Exception as e:
                pytest.fail(f"{label} 发送异常（{url}）: {e}")
            # 模型真实响应（状态码/响应体全文）断言前打印（失败时同
            # 样可见）
            if response.status_code != 200:
                test_logger.error(
                    f"{label} 真实响应: HTTP {response.status_code}, "
                    f"body={response.text[:500]!r}"
                )
                pytest.fail(
                    f"客户问题复现失败：{label} 应正常响应（HTTP 200），"
                    f"实际 HTTP {response.status_code}——重复 "
                    f"reasoning_content 的 assistant 历史被拒绝（预期"
                    f"宽松解析：第一个被第二个覆盖后放行）: "
                    f"{response.text[:400]!r}"
                )
            chunks: List[Dict[str, Any]] = []
            content_parts: List[str] = []
            reasoning_parts: List[str] = []
            finish_reason = None
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                chunks.append(chunk)
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                if delta.get("content"):
                    content_parts.append(delta["content"])
                # 兼容 reasoning/reasoning_content 两种字段拼写
                # （collect_stream_chunks 同口径）
                reasoning = delta.get("reasoning") or delta.get(
                    "reasoning_content"
                )
                if reasoning:
                    reasoning_parts.append(reasoning)
                if choices[0].get("finish_reason"):
                    finish_reason = choices[0]["finish_reason"]
            # 模型真实响应（合并正文/思考全文）断言前打印
            test_logger.info(
                f"{label} 真实响应: HTTP 200, chunks={len(chunks)}, "
                f"finish={finish_reason}, "
                f"content={''.join(content_parts)[:2000]!r}, "
                f"reasoning={''.join(reasoning_parts)[:2000]!r}"
            )
            return {
                "chunks": chunks,
                "content": "".join(content_parts),
                "reasoning": "".join(reasoning_parts),
                "finish": finish_reason,
            }

        # ---- 第 3 次请求（核心）：重复 reasoning_content 历史回填 ----
        third = send_raw_stream(
            "第 3 次请求（assistant 历史重复 reasoning_content 回填）",
            raw_body,
        )

        # 耗光回退（K24 口径）：HTTP 200 核心契约（重复键历史被接
        # 受）首次请求已达成——正文空+finish=length 为思考耗光形态
        # （非契约违约），以 reasoning_effort=low 仅重发本请求（构
        # 造不变仅加顶层 reasoning_effort 字段，断言相同）
        if not third["content"].strip() and third["finish"] == "length":
            test_logger.info(
                "第 3 次请求思考耗光预算（正文空 + finish=length，"
                "默认 max 思考强度，max_tokens=8192）——HTTP 200 核心"
                "契约已达成（重复 reasoning_content 历史被接受），按 "
                "K24 口径以 reasoning_effort=low 回退重发（构造不变仅"
                "加顶层 reasoning_effort 字段，断言相同）"
            )
            third = send_raw_stream(
                "第 3 次请求（重复 reasoning_content 回填，"
                "reasoning_effort=low 回退重发）",
                build_third_body("low"),
            )

        # 硬断言（客户契约：不报错、正常响应）
        assert third["chunks"], (
            "客户问题复现失败：第 3 次请求 HTTP 200 但未返回任何 SSE "
            "事件"
        )
        assert third["content"].strip(), (
            f"客户问题复现失败：第 3 次请求未返回正文（content 为空，"
            f"finish={third['finish']}）——"
            + (
                "low 回退重发后仍无正文（默认 max 与 low 双强度均未产"
                "出正文——留证交开发）"
                if third["finish"] == "length"
                else "重复 reasoning_content 历史回填后未正常响应"
            )
        )
        assert (
            third["finish"] in self.VALID_STREAM_FINISH_REASONS
        ), f"第 3 次请求 finish_reason 非法: {third['finish']!r}"

        # usage 软观察：三次请求均未要求 include_usage，chunk 中出现
        # 的 usage 仅日志
        usage = next(
            (
                c.get("usage")
                for c in reversed(third["chunks"])
                if c.get("usage")
            ),
            None,
        )
        test_logger.info(
            "第 3 次请求 usage: "
            + (
                json.dumps(usage, ensure_ascii=False)
                if usage
                else "（未携带——未要求 include_usage）"
            )
        )

        test_logger.info(
            "客户问题复现通过: assistant 历史重复 reasoning_content 回"
            "填被兼容接受——第 3 次请求 HTTP 200 且正常生成正文（第一"
            "个 reasoning_content 被第二个覆盖后放行，宽松解析契约生"
            "效）；动态值全程经 json.dumps 全转义，正文/思考含引号/换"
            "行等字符不影响请求格式"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_negative_lookahead_tool_pattern_accepted(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K26 [P0]: 客户问题 - 工具 schema 负向前瞻正则应被兼容放行

        客户问题：工具参数 schema 的 pattern 包含 ^(?!...) 负向前
        瞻正则——后端将其编译为 structural_tag 生成约束时，底层语
        法编译器不支持 lookahead，请求失败：
        - 非流式报 400："Failed to compile structural_tag
          grammar: .../regex_converter.cc:83: Regex parsing error
          at position 4: Lookahead is not supported yet."（request
          id 2026102616110264231215776333070）；
        - 流式报："The upstream provider is unavailable. Please
          retry later."（provider_unavailable /
          upstream_stream_error）。
        修复（frontend 请求预处理兼容——非底层编译器新增
        lookahead 支持）：仅当 GLM-5.3、glm47 工具解析器、SGLang
        后端、tool_choice=auto（structural-tag schema 模式
        auto）、工具未显式设置 strict、schema 含以 ^(?! 开头的正
        则时命中——只把用于生成约束的工具副本设为 strict=false，
        避免强制编译该 schema；模型提示词里的原始 schema、工具描
        述及工具调用格式约束保留。属兼容绕过：该路径不再由
        grammar 强制保证参数满足完整 schema。
        本用例按触发形态构造请求：工具 path 参数 pattern 以 ^(?!
        开头（负向前瞻——禁止路径穿越：^(?!.*\\.\\.).+$）、不显
        式 strict、tool_choice=auto，user 消息自然诱导工具调用；
        非流式与流式各发一次。
        硬断言：
        1. 非流式 HTTP 200（核心——修复前 400 grammar 编译错
           误，报错复现即 FAIL）
        2. 非流式 choices 存在且非空 + message 结构存在
        3. 流式 HTTP 200（核心——修复前 provider_unavailable，
           报错复现即 FAIL）
        4. 流式 SSE 事件非空 + 至少一个含 choices 的数据块
        明确不断言：工具被调用、调用参数满足 pattern（兼容绕过
        路径不再由 grammar 强制保证——开发明确口径）、响应形态
        （正文或工具调用增量均可，宽松留日志）。GLM-5.3 专用；采样
        参数不发送——test_k 保持原始测试参数（工单原始请求未指
        定，不注入），两个请求一致。usage
        仅日志。（不进 smoke 集：新用例首跑观察期）
        """
        # K26: 工具定义——path 参数 pattern 以 ^(?! 开头（负向前
        # 瞻：禁止路径穿越 ..），不显式 strict（修复触发条件：工
        # 具未显式设置 strict）
        K26_TOOLS = [
            {
                "type": "function",
                "function": {
                    "name": "write_workspace_file",
                    "description": (
                        "Write content to a file in the workspace"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "pattern": "^(?!.*\\.\\.).+$",
                                "description": (
                                    "Workspace-relative file path; "
                                    "must not contain '..'"
                                ),
                            },
                            "content": {"type": "string"},
                        },
                        "required": ["path", "content"],
                    },
                },
            }
        ]
        # K26: user 消息——自然诱导 write_workspace_file 调用
        #（path 取值合法，不触碰负向前瞻拒绝域）
        K26_PROMPT = (
            "请把技能周报数据保存到工作区文件 reports/"
            "skill_weekly.json：调用 write_workspace_file 工具，"
            "path 为 reports/skill_weekly.json，content 为一个 "
            "JSON 对象字符串，包含 3-5 条示例技能记录，每条含技能"
            "名称（skill）、本周事件数（events）、评分（score）字"
            "段。"
        )
        # K26: 预算——工具调用生成任务，2048 留足思考预算余量
        #（K18 口径——防御正文/调用被思考耗光）
        K26_MAX_TOKENS = 2048

        test_logger.info(
            "=== 测试开始: 客户问题 - 工具 schema 负向前瞻正则兼容"
            "放行（pattern 以 ^(?! 开头 + 不显式 strict + "
            "tool_choice=auto；非流式+流式各发一次，grammar 编译错"
            "误/provider_unavailable 复现即 FAIL）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        # 采样参数不发送——test_k 保持原始测试参数（工单原始请求
        # 未指定，不注入），两个请求一致

        # ---- 非流式请求（核心断言：grammar 编译错误修复）----
        payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": K26_PROMPT}],
            "tools": K26_TOOLS,
            "tool_choice": "auto",
            "max_tokens": K26_MAX_TOKENS,
            "stream": False,
        }
        TestLogger.log_request(
            test_logger,
            payload["messages"],
            {
                "tools": [t["function"]["name"] for t in K26_TOOLS],
                "tool_choice": "auto",
                "max_tokens": K26_MAX_TOKENS,
                "temperature": "(不发送)",
                "top_p": "(不发送)",
                "seed": "(不发送)",
                "stream": False,
                "step": (
                    "非流式请求（负向前瞻 pattern 工具，grammar 编"
                    "译错误修复验证）"
                ),
            },
        )
        started = time.time()
        try:
            response = api_client._post_with_retry(
                url, payload, stream=False
            )
        except Exception as e:
            pytest.fail(f"非流式请求发送异常（{url}）: {e}")
        elapsed = time.time() - started
        # 模型真实响应断言前打印（失败时同样可见）
        test_logger.info(
            f"非流式真实响应: HTTP {response.status_code}, "
            f"elapsed={elapsed:.1f}s, body={response.text[:800]!r}"
        )
        # 断言1（核心）：负向前瞻 pattern 工具请求应被兼容放行——
        # 修复前报 400（Failed to compile structural_tag grammar:
        # Lookahead is not supported yet），报错复现即 FAIL
        assert response.status_code == 200, (
            f"客户问题复现失败：含负向前瞻 pattern 工具的非流式请求"
            f"应被兼容放行，实际 HTTP {response.status_code}（客户原"
            f"始报错：Failed to compile structural_tag grammar——"
            f"Regex parsing error: Lookahead is not supported yet；"
            f"修复应将生成约束工具副本置 strict=false 绕过强制编"
            f"译）: {response.text[:400]}"
        )
        try:
            result = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            pytest.fail(
                f"非流式响应不是合法 JSON: {e}. "
                f"响应体: {response.text[:300]}"
            )
        # 断言2：choices 存在且非空 + message 结构存在
        choices = result.get("choices") or []
        assert choices, (
            f"非流式响应缺少 choices: "
            f"{json.dumps(result, ensure_ascii=False)[:500]}"
        )
        message = choices[0].get("message")
        assert isinstance(message, dict), (
            f"非流式响应 message 结构缺失: "
            f"{json.dumps(result, ensure_ascii=False)[:500]}"
        )
        TestLogger.log_response(
            test_logger, result, "K26-非流式响应"
        )
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls")
        finish = choices[0].get("finish_reason")
        usage = result.get("usage") or {}
        test_logger.info(
            f"非流式 HTTP 200, elapsed={elapsed:.1f}s, "
            f"finish={finish}, content_len={len(content)}, "
            f"tool_calls={'有' if tool_calls else '无'}, usage="
            f"{json.dumps(usage, ensure_ascii=False)}"
        )

        # ---- 流式请求（核心断言：provider_unavailable 修复）----
        stream_payload = {**payload, "stream": True}
        TestLogger.log_request(
            test_logger,
            stream_payload["messages"],
            {
                "tools": [t["function"]["name"] for t in K26_TOOLS],
                "tool_choice": "auto",
                "max_tokens": K26_MAX_TOKENS,
                "temperature": "(不发送)",
                "top_p": "(不发送)",
                "seed": "(不发送)",
                "stream": True,
                "step": (
                    "流式请求（负向前瞻 pattern 工具，"
                    "provider_unavailable 修复验证）"
                ),
            },
        )
        started_s = time.time()
        try:
            response_s = api_client.session.post(
                url,
                json=stream_payload,
                timeout=api_client.timeout,
                stream=True,
            )
        except Exception as e:
            pytest.fail(f"流式请求发送异常（{url}）: {e}")
        elapsed_s = time.time() - started_s
        test_logger.info(
            f"流式真实响应: HTTP {response_s.status_code}, "
            f"elapsed={elapsed_s:.1f}s"
        )
        # 断言3（核心）：流式请求应被兼容放行——修复前报
        # provider_unavailable（upstream_stream_error；同一
        # grammar 编译根因），报错复现即 FAIL
        assert response_s.status_code == 200, (
            f"客户问题复现失败：含负向前瞻 pattern 工具的流式请求应"
            f"被兼容放行，实际 HTTP {response_s.status_code}（客户原"
            f"始报错：The upstream provider is unavailable——"
            f"upstream_stream_error；同一 grammar 编译根因）: "
            f"{response_s.text[:400]}"
        )
        # 解析 SSE：统计事件数/含 choices 事件数，合并正文增量与
        # 工具调用增量（响应形态宽松——正文或工具调用均可，留日志）
        events = 0
        choice_events = 0
        content_s = ""
        tool_call_events = 0
        finish_s = None
        usage_s: Dict[str, Any] = {}
        for line in response_s.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            events += 1
            evt_choices = event.get("choices") or []
            if not evt_choices:
                evt_usage = event.get("usage")
                if evt_usage:
                    usage_s.update(evt_usage)
                continue
            choice_events += 1
            delta = evt_choices[0].get("delta") or {}
            if delta.get("content"):
                content_s += delta["content"]
            if delta.get("tool_calls"):
                tool_call_events += 1
            if evt_choices[0].get("finish_reason"):
                finish_s = evt_choices[0].get("finish_reason")
            evt_usage = event.get("usage")
            if evt_usage:
                usage_s.update(evt_usage)
        # 断言4：SSE 事件非空且至少一个含 choices 的数据块
        assert events > 0, (
            "客户问题复现失败：流式请求 HTTP 200 但未返回任何 SSE "
            "事件"
        )
        assert choice_events > 0, (
            f"客户问题复现失败：流式请求 SSE 事件中无 choices 数据块"
            f"（events={events}）"
        )
        test_logger.info(
            f"流式 HTTP 200, elapsed={elapsed_s:.1f}s, events="
            f"{events}, choice_events={choice_events}, finish="
            f"{finish_s}, content_len={len(content_s)}, "
            f"tool_call_events={tool_call_events}, usage="
            f"{json.dumps(usage_s, ensure_ascii=False)}"
        )

        test_logger.info(
            "客户问题复现通过: 工具 schema 负向前瞻正则（^(?!...)）"
            "已被兼容放行——非流式 HTTP 200 且正常生成、流式 HTTP "
            "200 且 SSE 正常（生成约束工具副本置 strict=false 绕过"
            "强制编译，原始 schema/工具描述/格式约束保留）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_invalid_arguments_history_tolerated(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K27 [P0]: 客户问题 - 历史非法 JSON arguments 应被容忍

        客户问题（AGDC2-19，codex 客户端 + MCP 工具场景）：模型调
        用 mcp__grafana__update_dashboard 时输出的 arguments 本身
        不是合法 JSON（两处括号错误——"refId": "A"}] 缺一个 }、
        40}}}] 处多一个 }；PDF 上游流式日志证实错误由上游模型产
        生）；客户端执行 MCP 工具失败、拼接失败结果并回放全量历
        史继续请求，服务端校验历史消息 tool_calls[].function.
        arguments 发现非合法 JSON，直接 400——"Assistant tool
        call function.arguments must be valid JSON"。问题定位分
        析：纯服务端问题（畸形源头为模型输出、报错点为服务端校
        验、客户端行为为标准 agent 回放），与 codex 客户端无本质
        关系。
        修复（开发方案）：历史里无法解析的 arguments 按字符串保
        留，让模型继续纠正，不再直接 400 拒绝。
        本用例复刻客户链路（user → assistant(畸形 arguments 的工
        具调用) → tool(执行失败结果——协议配对必需) → user 追问
        要求修正重试），带 MCP 工具定义，非流式。畸形 arguments
        采用保真浓缩版（~2.2KB）：完整保留工单两处括号错误形态
        与关键结构（dataset/rawSql/title/uid/操作路径）——PDF 换
        行提取无法保证 3KB 原文字节级保真；场景自检：常量经
        json.loads 解析必须失败（恰因两处工单错误而非法，修正该
        两处即可解析，构造时已验证）。
        硬断言：
        1. HTTP 200（核心——修复前 400 must be valid JSON，报错
           复现即 FAIL）
        2. choices 存在且非空 + message 结构存在
        3. 修正行为（修复目的"让模型继续纠正"）：模型发起工具调
           用（追问明确要求修正后重新调用——行为契约），每条调
           用 name 非空、id 非空、arguments 为合法 JSON 对象（修
           正后的参数必须合法）
        明确不断言：历史畸形 arguments 被改写/修复为合法 JSON
        （修复是按字符串保留，不改写历史）。
        耗光回退（K24/K25 口径）：预算 16k（max_tokens=16384——覆
        盖默认档思考+大尺
        寸修正输出；工单未载 max_tokens），默认档思考仍可能耗尽
        预算（无正文无调用+finish=length——首跑实测 2048 预算
        reasoning_tokens 全耗）——该形态以
        reasoning_effort=low（GLM 顶层思考强度参数）重发（构造不
        变仅加顶层 reasoning_effort 字段；HTTP 200 核心契约首次请
        求已达成），断言相同；双强度均未产出即 FAIL（留证交开
        发）。GLM-5.3 专用；采样参数不发送——test_k 保持原始测试参
        数（工单原始请求未指定，不注入）。usage 仅日志。（不进 smoke 集：新用例
        首跑观察期）
        """
        # K27: 工单同款畸形 arguments（保真浓缩版）——恰因两处
        # 括号错误而非法："refId": "A"}]（缺一个 }）与 40}}}],
        # 处被注入多余 }（40}}}]},）；修正该两处即恢复合法
        K27_MALFORMED_ARGS = (
            '{"dashboard": {"timeSettings": {"from": "now-6h", "to": '
            '"now"}}, "operations": [{"op": "add", "path": "$.elements.'
            'panel-131", "value": {"kind": "Panel", "spec": {"data": '
            '{"kind": "QueryGroup", "spec": {"queries": [{"kind": '
            '"PanelQuery", "spec": {"hidden": false, "query": '
            '{"datasource": {"name": "${data_source}"}, "group": '
            '"mysql", "kind": "DataQuery", "spec": {"dataset": '
            '"tokenmarket_dw_prod", "editorMode": "code", "format": '
            '"time_series", "rawQuery": true, "rawSql": "SELECT\\n  '
            "CAST(FLOOR(a.request_finished_at / 300000) * 300000 AS "
            "BIGINT) AS time,\\n  a.model AS metric,\\n  CASE\\n    "
            "WHEN COUNT(1) = 0 THEN 100.0\\n    ELSE (1 - SUM(CASE "
            "WHEN a.rsp_code >= 500 THEN 1 ELSE 0 END) / COUNT(1)) * "
            "100\\n  END AS value\\nFROM gateway_request_logs_dwd AS "
            "a\\nWHERE a.request_finished_at BETWEEN $__from AND "
            "$__to\\n  AND a.channel_id IN (${channel_id:csv})\\n  AND "
            "a.model IN ($model_id)\\n  AND a.user_id = CASE WHEN "
            "'$user_id' = '' THEN a.user_id ELSE '$user_id' END\\n  "
            "AND a.api_key_name = CASE WHEN '$api_key_name' = '' THEN "
            "a.api_key_name ELSE '$api_key_name' END\\nGROUP BY time, "
            'metric\\nORDER BY time ASC", "sql": {"columns": '
            '[{"parameters": [], "type": "function"}], "groupBy": '
            '[{"property": {"type": "string"}, "type": "groupBy"}], '
            '"limit": 50}}, "version": "v0"}, "refId": "A"}], '
            '"queryOptions": {}, "transformations": []}}, '
            '"description": "按 5 分钟窗口计算各模型服务可用性；绿色 '
            '≥99.9%，蓝色 99.5%-99.9%，黄色 99%-99.5%，红色 <99%。", '
            '"id": 131, "links": [], "title": "模型 - SLA 状态时间轴", '
            '"vizConfig": {"group": "state-timeline", "kind": '
            '"VizConfig", "spec": {"fieldConfig": {"defaults": '
            '{"thresholds": {"mode": "absolute", "steps": [{"color": '
            '"red", "value": null}, {"color": "yellow", "value": 99}, '
            '{"color": "blue", "value": 99.5}, {"color": "green", '
            '"value": 99.9}]}}, "overrides": []}, "options": '
            '{"alignValue": "left", "legend": {"displayMode": "list", '
            '"placement": "bottom", "showLegend": false}, "tooltip": '
            '{"mode": "single", "sort": "none"}}, "version": "13.2.0"'
            '}}}}}, {"op": "add", "path": "$.layout.spec.tabs[0].spec.'
            'layout.spec.rows[0].spec.layout.spec.items/-", "value": '
            '{"kind": "GridLayoutItem", "spec": {"element": {"kind": '
            '"ElementReference", "name": "panel-131"}, "height": 8, '
            '"width": 12, "x": 12, "y": 40}}}]}, "uid": "ad7mst8"}'
        )
        # K27: 工单工具调用 id（工单截图原值）与 MCP 工具名
        K27_CALL_ID = "call_37835f057d824692ad063945"
        K27_TOOL_NAME = "mcp__grafana__update_dashboard"
        # K27: MCP 工具定义（parameters 保留顶层结构——历史校验针
        # 对 arguments 字符串，无需复刻完整 Grafana schema）
        K27_TOOLS = [
            {
                "type": "function",
                "function": {
                    "name": K27_TOOL_NAME,
                    "description": "Update a Grafana dashboard",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dashboard": {"type": "object"},
                            "uid": {"type": "string"},
                        },
                        "required": ["dashboard", "uid"],
                    },
                },
            }
        ]
        # K27: 按客户链路还原的 assistant 历史消息——模型输出的工
        # 具调用（arguments 即上述畸形 JSON，原样回放）
        K27_ASSISTANT = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": K27_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": K27_TOOL_NAME,
                        "arguments": K27_MALFORMED_ARGS,
                    },
                }
            ],
        }
        # K27: 客户端工具执行失败结果（arguments 非合法 JSON——客
        # 户"失败结果"回填形态；role=tool 为协议配对必需，K18 实
        # 测缺失被 400 拒绝）
        K27_TOOL_RESULT = (
            "Error: failed to parse arguments for tool "
            "mcp__grafana__update_dashboard: invalid JSON"
        )
        # K27: user 追问——明确要求修正后重新调用工具（修正行为契
        # 约的确定性前提）
        K27_FOLLOWUP = (
            "工具执行失败：arguments 不是合法 JSON。请修正参数后重"
            "新调用工具完成任务。"
        )
        # K27: 首个 user 消息（MCP 场景任务）
        K27_PROMPT = "请通过 Grafana 工具更新 SLA 状态面板。"
        # K27: 预算 16k——覆盖默认档思考+大尺寸修正 arguments 输
        # 出（工单未载 max_tokens；首跑 2048 预算曾被思考全耗，上
        # 调至 16k 并以 reasoning_effort=low 兜底）
        K27_MAX_TOKENS = 16384

        # 场景自检：畸形 arguments 常量必须恰为非合法 JSON（否则
        # 用例失去缺陷触发能力）
        try:
            json.loads(K27_MALFORMED_ARGS)
            pytest.fail(
                "场景构造失效：K27_MALFORMED_ARGS 竟可解析为合法 "
                "JSON——不再具备 must-be-valid-JSON 触发能力"
            )
        except json.JSONDecodeError:
            pass

        test_logger.info(
            "=== 测试开始: 客户问题 - 历史非法 JSON arguments 应被"
            "容忍（user→assistant(畸形 arguments 调用)→tool(执行失"
            "败)→user 追问修正重试；修复前 400 must be valid JSON，"
            "报错复现即 FAIL；修复后模型应发起修正调用且 arguments "
            "合法）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # 采样参数不发送——test_k 保持原始测试参数（工单原始请求
        # 未指定，不注入）

        payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "messages": [
                {"role": "user", "content": K27_PROMPT},
                K27_ASSISTANT,
                {
                    "role": "tool",
                    "tool_call_id": K27_CALL_ID,
                    "content": K27_TOOL_RESULT,
                },
                {"role": "user", "content": K27_FOLLOWUP},
            ],
            "tools": K27_TOOLS,
            "max_tokens": K27_MAX_TOKENS,
            "stream": False,
        }
        TestLogger.log_request(
            test_logger,
            payload["messages"],
            {
                "tools": [K27_TOOL_NAME],
                "max_tokens": K27_MAX_TOKENS,
                "temperature": "(不发送)",
                "top_p": "(不发送)",
                "seed": "(不发送)",
                "stream": False,
                "step": "历史非法 arguments 回放+修正重试",
                "assistant_history": (
                    'arguments 两处括号错误（"refId": "A"}] 缺 }、'
                    "40}}}] 处多 }）"
                ),
            },
        )
        started = time.time()
        try:
            response = api_client._post_with_retry(
                url, payload, stream=False
            )
        except Exception as e:
            pytest.fail(f"请求发送异常（{url}）: {e}")
        elapsed = time.time() - started
        # 模型真实响应断言前打印（失败时同样可见）
        test_logger.info(
            f"真实响应: HTTP {response.status_code}, "
            f"elapsed={elapsed:.1f}s, body={response.text[:800]!r}"
        )
        # 断言1（核心）：历史非法 arguments 应被容忍——修复前此请
        # 求报 400（Assistant tool call function.arguments must be
        # valid JSON），报错复现即 FAIL
        assert response.status_code == 200, (
            f"客户问题复现失败：历史含非法 JSON arguments 的请求应被"
            f"容忍（按字符串保留、模型继续纠正），实际 HTTP "
            f"{response.status_code}（客户原始报错：Assistant tool "
            f"call function.arguments must be valid JSON）: "
            f"{response.text[:400]}"
        )
        try:
            result = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            pytest.fail(f"响应不是合法 JSON: {e}. 响应体已记录于测试日志")
        # 断言2：choices 存在且非空 + message 结构存在
        choices = result.get("choices") or []
        assert choices, f"响应缺少 choices: {list(result.keys())}"
        message = choices[0].get("message")
        assert isinstance(message, dict), (
            f"响应 message 结构缺失: {list(result.keys())}"
        )
        TestLogger.log_response(test_logger, result, "K27-响应")

        tool_calls = message.get("tool_calls") or []
        content = message.get("content") or ""
        finish = choices[0].get("finish_reason")
        # 耗光回退（K24/K25 口径）：无正文无调用+finish=length 为
        # 思考耗尽预算形态（真实环境首跑实测：2048 预算曾全被思
        # 考耗光——reasoning_tokens=2048/2048；现预算已上调 16k，
        # low 兜底），非契约违约；以
        # reasoning_effort=low（GLM 顶层思考强度参数，K20 口径）重
        # 发（构造不变仅加顶层 reasoning_effort 字段——HTTP 200 核
        # 心契约首次请求已达成），断言相同
        if not tool_calls and not content.strip() and finish == "length":
            test_logger.info(
                "第 1 次请求思考耗光预算（无正文无调用 + "
                "finish=length——HTTP 200 核心契约已达成：历史非法 "
                "arguments 被容忍），按 K24/K25 口径以 "
                "reasoning_effort=low 回退重发（构造不变仅加顶层 "
                "reasoning_effort 字段）"
            )
            retry_payload = {**payload, "reasoning_effort": "low"}
            TestLogger.log_request(
                test_logger,
                retry_payload["messages"],
                {
                    "tools": [K27_TOOL_NAME],
                    "max_tokens": K27_MAX_TOKENS,
                    "temperature": "(不发送)",
                    "top_p": "(不发送)",
                    "seed": "(不发送)",
                    "stream": False,
                    "reasoning_effort": "low",
                    "step": "low 回退重发（思考耗光形态）",
                },
            )
            started_r = time.time()
            try:
                response_r = api_client._post_with_retry(
                    url, retry_payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"low 回退重发异常（{url}）: {e}")
            elapsed_r = time.time() - started_r
            test_logger.info(
                f"low 回退真实响应: HTTP {response_r.status_code}, "
                f"elapsed={elapsed_r:.1f}s, "
                f"body={response_r.text[:800]!r}"
            )
            assert response_r.status_code == 200, (
                f"low 回退重发失败：实际 HTTP "
                f"{response_r.status_code}: {response_r.text[:400]}"
            )
            try:
                result = response_r.json()
            except (json.JSONDecodeError, ValueError) as e:
                pytest.fail(
                    f"low 回退响应不是合法 JSON: {e}. "
                    f"响应体已记录于测试日志"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"low 回退响应缺少 choices: {list(result.keys())}"
            )
            message = choices[0].get("message")
            assert isinstance(message, dict), (
                f"low 回退响应 message 结构缺失: {list(result.keys())}"
            )
            TestLogger.log_response(
                test_logger, result, "K27-low 回退响应"
            )
            tool_calls = message.get("tool_calls") or []
            content = message.get("content") or ""
            finish = choices[0].get("finish_reason")
            if not tool_calls and not content.strip() and finish == "length":
                pytest.fail(
                    "low 回退重发后仍无产出（默认与 low 双强度思考均"
                    "耗光预算——留证交开发）"
                )
        # 断言3a（修正行为前提）：模型应发起工具调用——追问明确要
        # 求修正后重新调用工具（纯文本回答无法证明"继续纠正"）
        assert tool_calls, (
            f"模型未发起修正工具调用（finish="
            f"{choices[0].get('finish_reason')}）——无法验证修复目的"
            f"（让模型继续纠正，响应体已记录于测试日志）"
        )
        # 断言3b（修正行为）：每条调用结构完整且 arguments 为合法
        # JSON 对象——模型应以修正后的合法参数重新调用
        for i, tc in enumerate(tool_calls):
            tc = tc if isinstance(tc, dict) else {}
            fn = tc.get("function") or {}
            name = fn.get("name")
            tc_id = tc.get("id")
            raw_args = fn.get("arguments")
            assert isinstance(name, str) and name.strip(), (
                f"修正调用的 function.name 为空（{name!r}）: "
                f"{json.dumps(tc, ensure_ascii=False)[:300]}"
            )
            assert isinstance(tc_id, str) and tc_id.strip(), (
                f"修正调用的 id 为空（{tc_id!r}）: "
                f"{json.dumps(tc, ensure_ascii=False)[:300]}"
            )
            args_obj = raw_args
            if isinstance(raw_args, str):
                try:
                    args_obj = json.loads(raw_args)
                except json.JSONDecodeError as e:
                    pytest.fail(
                        f"模型未纠正参数：tool_calls[{i}].function."
                        f"arguments 仍非合法 JSON（{e}）——修复目的"
                        f"（让模型继续纠正）未达成（原始 arguments 已"
                        f"记录于测试日志）"
                    )
            assert isinstance(args_obj, dict), (
                f"修正调用的 arguments 应为 JSON 对象，实际 "
                f"{type(args_obj).__name__}（原始 arguments 已记录于"
                f"测试日志）"
            )
        usage = result.get("usage") or {}
        test_logger.info(
            f"客户问题复现通过: 历史非法 JSON arguments 已被容忍——"
            f"HTTP 200 且模型发起 {len(tool_calls)} 条修正工具调用"
            f"（arguments 均为合法 JSON 对象），elapsed="
            f"{elapsed:.1f}s, usage="
            f"{json.dumps(usage, ensure_ascii=False)}"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_output_fields_think_tag_probe(
        self, api_client: ModelAPIClient, test_logger, request
    ):
        """K28 [P0]: 客户问题 - 模型输出字段核验（尾裸/回流/工具参数）

        客户问题（AGDC2-24，TR-20261016-02 九章云-模型输出字段核
        验）：客户探针报告对被测平台与对照平台各 3 用例×5 次流式
        请求做输出字段核验，判据三项——T1 content 尾部裸 `</think>`
        标记残留（0 次为通过，被测平台曾 2/15 不通过）、T2 字段回
        流（字段切换序列出现 content→reasoning，0 次为通过）、T3
        工具参数完整性（arguments 合法完整 JSON 且 reasoning 内无
        <arg_key>/<arg_value>/</tool_call> 原生标记，100% 为通
        过）；length 截断只记录不判定。
        本用例将客户探针（scripts/probe_think_tag.py——单文件探
        针，仅调用其 call/analyse/CASES 并传递参数）与数据集
        （requests/AGDC2-24 三个用例请求体，工单原始参数
        stream=true、max_tokens=8192、reasoning_effort=max 原样保
        留）纳入框架：3 用例 × 5 次（--runs 硬编码 5，用户指定）
        流式请求，只评被测平台（用户指定——不跑对照平台），逐条
        留存 raw 响应并统计三项判据。raw 输出目录（用户指定）：
        Jenkins 构建（--build-number 经 Jenkinsfile 透传，或 BUILD_NUMBER 环境变量存在）→
        builds/<TESTER>/<BUILD_NUMBER>/origin_raw/AGDC2-24/
        <model>/（与 allure-report 同级）；手动执行 →
        <repo>/origin_raw/AGDC2-24/<model>/<timestamp>/（年月日_
        时分秒）。除 raw 文件外不输出其他额外文件。
        硬断言（任一不符合即 FAIL）：
        1. 全部请求 HTTP 200 且响应体为可解析 SSE（空体/非流式结
           构时 analyse 返回全零值会误判 T1/T2/T3 全通过——无法核
           验即 FAIL）
        2. T1 尾裸出现次数 == 0
        3. T2 字段回流出现次数 == 0（字段切换序列含 content→
           reasoning 即命中）
        4. T3 工具参数完整性 100%（每次 arguments 合法 JSON 且
           reasoning 无原生标记）
        模型名由环境注入（请求体 model 字段覆盖）；请求体不含
        temperature/top_p/seed——按用户指定保持工单原始请求体不
        变、不注入采样参数（豁免机制针对 wrapper 注入，本用例经探
        针直发不涉及）；reasoning_effort/max_tokens/stream 为工单
        场景参数原样保留。GLM-5.3 专用。（不进 smoke 集：新用例
        首跑观察期）
        """
        # K28: 加载客户探针（单文件，scripts/probe_think_tag.py）
        probe_path = (
            Path(__file__).parent.parent / "scripts" / "probe_think_tag.py"
        )
        spec = importlib.util.spec_from_file_location(
            "probe_think_tag", probe_path
        )
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)

        K28_RUNS = 5  # --runs 硬编码为 5（用户指定）
        K28_TICKET = "AGDC2-24"
        # K28: raw 输出目录（用户指定规则）
        repo_root = Path(__file__).parent.parent
        # --build-number 优先（远程机 shell 无 Jenkins BUILD_NUMBER
        # 环境变量，Jenkinsfile 经该选项透传），保留环境变量兜底
        build_number = (
            request.config.getoption("--build-number", default=None)
            or os.environ.get("BUILD_NUMBER", "")
        )
        tester = (
            request.config.getoption("--tester", default=None)
            or os.environ.get("TESTER")
            or "unknown"
        )
        if build_number:
            raw_dir = (
                repo_root / "builds" / tester / build_number
                / "origin_raw" / K28_TICKET / api_client.model_name
            )
        else:
            raw_dir = (
                repo_root / "origin_raw" / K28_TICKET
                / api_client.model_name
                / datetime.now().strftime("%Y%m%d_%H%M%S")
            )
        raw_dir.mkdir(parents=True, exist_ok=True)

        test_logger.info(
            f"=== 测试开始: 客户问题 - 模型输出字段核验（3 用例 × "
            f"{K28_RUNS} 次流式，判据：T1 尾裸=0 / T2 字段回流=0 / "
            f"T3 工具参数完整性=100%；只评被测平台；raw 目录: "
            f"{raw_dir}）==="
        )

        # 请求体不含 temperature/top_p/seed（三个用例顶层字段已逐
        # 一核验：model/messages/tools/reasoning_effort/max_tokens/
        # stream/stream_options）——按用户指定保持工单原始请求体不
        # 变，不注入采样参数（豁免机制针对 wrapper 注入，本用例经
        # 探针直发不涉及；仅 model 字段按框架约定由环境覆盖）
        t1_bare = t2_reentry = t3_bad = http_errors = total = 0
        for case in probe.CASES:
            case_file = Path(probe.REQ) / f"{case}.json"
            with open(case_file, encoding="utf-8") as f:
                payload = json.load(f)
            payload.pop("url", None)
            # 模型名由环境注入（覆盖请求体原值）；其余字段一律保
            # 持工单原始请求体不变（不注入 temperature/top_p/seed）
            payload["model"] = api_client.model_name
            for i in range(1, K28_RUNS + 1):
                raw_path = raw_dir / f"{case}_r{i}.raw"
                started = time.time()
                st, txt = probe.call(
                    api_client.base_url,
                    api_client.api_key,
                    payload,
                    str(raw_path),
                    "/v1/chat/completions",
                )
                elapsed = time.time() - started
                a = probe.analyse(txt)
                total += 1
                # 可核验门槛：非 200 或响应体非可解析 SSE（空体/非
                # 流式结构——analyse 对非 SSE 体返回全零值，T1/T2/T3
                # 会被误判为全部通过）均视为无法核验
                if st != 200 or "data: " not in txt:
                    http_errors += 1
                if a["bare"]:
                    t1_bare += 1
                if "C→R" in a["seq"]:
                    t2_reentry += 1
                if (not a["args_ok"]) or a["native"]:
                    t3_bad += 1
                test_logger.info(
                    f"{case} #{i}: HTTP {st}, content={a['c']} 字符, "
                    f"reasoning={a['r']} 字符, 字段切换="
                    f"{a['seq'] or '-'}, T1尾裸={'是' if a['bare'] else '否'}, "
                    f"工具调用={','.join(a['tools']) or '-'}, "
                    f"finish={a['finish']}, 参数JSON="
                    f"{'合法' if a['args_ok'] else '非法'}, 原生标记="
                    f"{a['native']}, elapsed={elapsed:.1f}s"
                )

        test_logger.info(
            f"K28 汇总: 共 {total} 次, T1 尾裸={t1_bare}（判据 0）, "
            f"T2 字段回流={t2_reentry}（判据 0）, T3 参数不完整="
            f"{t3_bad}（判据 100% 完整）, HTTP 错误={http_errors}"
        )
        # 硬断言：任一判据不符合即 FAIL
        assert http_errors == 0, (
            f"模型输出字段核验失败：{http_errors}/{total} 次请求非 "
            f"200 或响应体非可解析 SSE——探针无法核验（raw 目录: "
            f"{raw_dir}）"
        )
        assert t1_bare == 0, (
            f"T1 判据不符合：content 尾部裸 </think> 出现 "
            f"{t1_bare}/{total} 次（判据 0 次——被测平台原始报告即 "
            f"2/15 不通过，raw 目录: {raw_dir}）"
        )
        assert t2_reentry == 0, (
            f"T2 判据不符合：字段回流（content→reasoning）出现 "
            f"{t2_reentry}/{total} 次（判据 0 次，raw 目录: {raw_dir}）"
        )
        assert t3_bad == 0, (
            f"T3 判据不符合：工具参数不完整 {t3_bad}/{total} 次（判"
            f"据 100% 完整——arguments 非法 JSON 或 reasoning 含原生"
            f"标记，raw 目录: {raw_dir}）"
        )
        test_logger.info(
            f"客户问题复现通过: 模型输出字段核验三项判据全部符合——"
            f"T1 尾裸 0/{total}、T2 字段回流 0/{total}、T3 工具参数"
            f"完整性 {total}/{total}（100%），raw 目录: {raw_dir}"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_dual_protocol_zero_delta_tool_call(
        self, api_client: ModelAPIClient, test_logger, request
    ):
        """K29 [P0]: 客户问题 - 双协议零增量响应与工具调用核验

        客户问题（AGDC2-25，九章云 Alaya GLM-5.3 网关）：客户报告用
        同一段业务会话报文（195 条消息/19 个工具/stream=true/
        max_tokens=4096）分别请求 /v1/chat/completions（OpenAI 协
        议）与 /anthropic/v1/messages（Anthropic 协议）——OpenAI
        协议 13 次中 5 次出现零增量响应（HTTP 200、SSE 结构完整
        含 finish_reason/usage/[DONE]，但 delta.content、
        delta.reasoning_content、delta.tool_calls 三类增量均为空，
        且 usage.completion_tokens>0——整条流仅 1 个空 delta
        chunk），工具调用仅 4/13；Anthropic 协议 8/8 返回工具调
        用、零增量 0/8。
        本用例将客户探针（scripts/probe_alaya.py——单文件探针，仅
        调用其 post/parse 并传递参数）与数据集
        （requests/AGDC2-25 两份协议请求体）纳入框架：两种协议各
        发 --n 硬编码 10 次（用户指定）流式请求，逐条留存 raw 响
        应并统计三项判据（用户指定）——有效请求 == 10（HTTP 200
        且响应可解析）、零增量响应 == 0、返回工具调用 == 100%
        （10/10）；任一不符合即 FAIL。每协议追加 1 次强制工具调
        用（tool_choice required/any——与脚本一致的追加用例，仅观
        察留日志、不计入判据）。raw 输出目录（用户指定）：
        Jenkins 构建（--build-number 经 Jenkinsfile 透传，或 BUILD_NUMBER 环境变量存在）→ builds/<TESTER>/
        <BUILD_NUMBER>/origin_raw/AGDC2-25/<model>/（与
        allure-report 同级）；手动执行 →
        <repo>/origin_raw/AGDC2-25/<model>/<timestamp>/（年月日_
        时分秒）；其他需要输出的文件与 raw 同级（本用例无其他输
        出）。
        硬断言（按协议逐一判定，任一不符合即 FAIL）：
        1. 有效请求 == 10（HTTP 200 且响应可解析——协议错误或
           非 200 即 FAIL）
        2. 零增量响应 == 0（三类增量均空且 usage.completion_tokens
           >0 即零增量——客户缺陷形态复现即 FAIL）
        3. 返回工具调用 == 10（100%）
        请求体 model 字段由环境注入覆盖；脚本口径 stream=true、
        max_tokens=4096 覆盖请求体原值；temperature/top_p 原始请
        求未指定——按用户指定保持不指定（不注入）。GLM-5.3 专
        用。（不进 smoke 集：新用例首跑观察期）
        """
        # K29: 加载客户探针（单文件，scripts/probe_alaya.py）
        probe_path = (
            Path(__file__).parent.parent / "scripts" / "probe_alaya.py"
        )
        spec = importlib.util.spec_from_file_location(
            "probe_alaya", probe_path
        )
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        # 模型参数经 Jenkinsfile→pytest 注入（用户指定）：探针的
        # BASE/KEY 指向被测网关
        probe.BASE = api_client.base_url
        probe.KEY = api_client.api_key or ""

        K29_N = 10  # --n 硬编码为 10（用户指定）
        K29_TICKET = "AGDC2-25"
        # K29: raw 输出目录（用户指定规则，同 K28 口径）
        repo_root = Path(__file__).parent.parent
        # --build-number 优先（远程机 shell 无 Jenkins BUILD_NUMBER
        # 环境变量，Jenkinsfile 经该选项透传），保留环境变量兜底
        build_number = (
            request.config.getoption("--build-number", default=None)
            or os.environ.get("BUILD_NUMBER", "")
        )
        tester = (
            request.config.getoption("--tester", default=None)
            or os.environ.get("TESTER")
            or "unknown"
        )
        if build_number:
            raw_dir = (
                repo_root / "builds" / tester / build_number
                / "origin_raw" / K29_TICKET / api_client.model_name
            )
        else:
            raw_dir = (
                repo_root / "origin_raw" / K29_TICKET
                / api_client.model_name
                / datetime.now().strftime("%Y%m%d_%H%M%S")
            )
        raw_dir.mkdir(parents=True, exist_ok=True)

        test_logger.info(
            f"=== 测试开始: 客户问题 - 双协议零增量响应与工具调用核"
            f"验（/anthropic/v1/messages 与 /v1/chat/completions 各 "
            f"{K29_N} 次流式；判据：有效请求=={K29_N} / 零增量==0 / "
            f"返回工具调用==100%；raw 目录: {raw_dir}）==="
        )

        stats = {}
        for proto in ("anthropic", "openai"):
            path = (
                "/v1/chat/completions"
                if proto == "openai"
                else "/anthropic/v1/messages"
            )
            src = (
                probe.OAI_PAYLOAD if proto == "openai"
                else probe.ANT_PAYLOAD
            )
            with open(src, encoding="utf-8") as f:
                base_req = json.load(f)
            # 与探针 run() 一致：stream/max_tokens 由脚本口径固定
            base_req["stream"] = True
            base_req["max_tokens"] = 4096
            # 模型名由环境注入（覆盖请求体原值）；temperature/top_p
            # 原始请求未指定——按用户指定保持不指定（不注入）
            base_req["model"] = api_client.model_name
            auth = "bearer" if proto == "openai" else "x-api-key"
            valid = zero = tools_n = 0
            for i in range(1, K29_N + 1):
                raw_path = raw_dir / f"{proto}_{i:02d}.raw"
                started = time.time()
                st, txt = probe.post(path, base_req, str(raw_path), auth)
                elapsed = time.time() - started
                r = probe.parse(txt, proto)
                is_valid = (st == 200) and not r["err"]
                if is_valid:
                    valid += 1
                    if r["empty"]:
                        zero += 1
                    if r["tools"]:
                        tools_n += 1
                test_logger.info(
                    f"{proto} #{i}: HTTP {st}, chunks={r['chunks']}, "
                    f"正文={r['text']}, 思考={r['think']}, 输出tok="
                    f"{r['out']}, reasoning={r['reason']}, 工具调用="
                    f"{','.join(r['tools']) or '-'}, 判定={r.get('verdict')}"
                    + (f"（错误: {r['err']}）" if r["err"] else "")
                    + f", elapsed={elapsed:.1f}s"
                )
            # 强制工具调用（与脚本一致的追加用例——仅观察留日志，
            # 不计入判据）
            forced = json.loads(json.dumps(base_req))
            forced["tool_choice"] = (
                "required" if proto == "openai" else {"type": "any"}
            )
            st_f, txt_f = probe.post(
                path, forced, str(raw_dir / f"{proto}_forced.raw"), auth
            )
            rf = probe.parse(txt_f, proto)
            test_logger.info(
                f"{proto} 强制调用（观察）: HTTP {st_f}, 工具调用="
                f"{','.join(rf['tools']) or '-'}, 判定={rf.get('verdict')}"
            )
            stats[proto] = (valid, zero, tools_n)
            test_logger.info(
                f"{proto} 小计: 有效请求 {valid}/{K29_N}（判据 =="
                f"{K29_N}）, 零增量 {zero}（判据 0）, 返回工具调用 "
                f"{tools_n}/{K29_N}（判据 100%）"
            )

        # 硬断言（按协议逐一判定，任一不符合即 FAIL）
        for proto in ("anthropic", "openai"):
            valid, zero, tools_n = stats[proto]
            assert valid == K29_N, (
                f"{proto} 判据不符合：有效请求 {valid}/{K29_N}（判据 "
                f"=={K29_N}——存在协议错误或非标 200 响应，raw 目录: "
                f"{raw_dir}）"
            )
            assert zero == 0, (
                f"{proto} 判据不符合：零增量响应 {zero}/{K29_N}（判据 "
                f"0——客户缺陷形态复现：HTTP 200 且结构完整但三类增"
                f"量均空、usage.completion_tokens>0，raw 目录: "
                f"{raw_dir}）"
            )
            assert tools_n == K29_N, (
                f"{proto} 判据不符合：返回工具调用 "
                f"{tools_n}/{K29_N}（判据 100%，raw 目录: {raw_dir}）"
            )
        test_logger.info(
            f"客户问题复现通过: 双协议核验三项判据全部符合——两协议"
            f"有效请求均 {K29_N}/{K29_N}、零增量均 0、返回工具调用均"
            f" {K29_N}/{K29_N}（100%），raw 目录: {raw_dir}"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_responses_api_marker_output_usage(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K30 [P0]: 客户问题 - /v1/responses 校验码输出与 token 计数核验

        客户问题（合成短文本 Token 对照测试，/v1/responses 接口）：
        probe 三项断言未通过——①严重：请求明确要求只输出
        SYNTHETIC_SHORT_TEXT_MARKER，实际正文输出 '4b69a88e6b'（与
        要求完全无关，模型侧未遵守指令）；②中等：input_tokens=52，
        超出基准 43 的 ±3% 区间（约 41.7-44.3）——可能为分词器或
        消息包装差异；③轻微：output_tokens 报告 295，实际可见输出
        文本仅 10 个字符且 output_tokens_details.reasoning_tokens
        为 0——计数与实际文本量明显不成比例，存在统计口径或隐藏推
        理未计入的疑点。
        测试断言点（用户指定，任一失败即整体失败）：
        1. 按请求明确要求的输出原样输出指定内容（无任何额外解
           释——合并正文严格等于校验码）
        2. input_tokens 以 43 为基准，超 ±3% 即失败（区间
           41.71-44.29——整数取值 42/43/44）
        3. 输出正文和思考消耗的 tokens 要计算正确——总输出
           tokens ≈ 正文 + 思考（可执行口径：reasoning_tokens ≤
           output_tokens ≤ reasoning_tokens + len(正文)，1 token/
           字符为宽松上界——正常文本 2-6 字符/token，缺陷形态
           295 tok vs 10 字符远超此界）
        本用例按客户原始 curl 还原：POST {base}/v1/responses
        （Responses API，非 chat/completions），input 两条消息
        （system "只输出指定校验码，不要解释。" + user "这是 合成
        短文本 Token 对照测试。请只输出
        SYNTHETIC_SHORT_TEXT_MARKER。"——content 均 input_text 类
        型），stream=true、max_output_tokens=1024 原样；模型名由
        环境注入；原始请求未指定 temperature/top_p/seed——保持不
        指定（不注入）。流式解析 Responses API 事件：
        response.output_text.delta 合并正文、response.completed 取
        usage（兼容事件级 usage 兜底）。
        硬断言：
        1. HTTP 200 且流式结构完整（含 output_text 增量与 usage）
        2. 终态事件 status == completed（failed/incomplete/
           cancelled 或无终态事件均为非正常结束，即失败）
        3. 合并正文严格等于 "SYNTHETIC_SHORT_TEXT_MARKER"（校验
           码原样输出，多一个字符即失败）
        4. usage.input_tokens ∈ [42, 44]（基准 43 ±3%）
        5. usage.output_tokens 满足 reasoning_tokens ≤ output_tokens
           ≤ reasoning_tokens + len(正文)（总计=思考+正文；缺陷形
           态 output_tokens 远超正文+思考即失败）
        GLM-5.3 专用。（不进 smoke 集：新用例首跑观察期）
        """
        K30_MARKER = "SYNTHETIC_SHORT_TEXT_MARKER"
        # K30: 基准 input_tokens 与 ±3% 容差（41.71-44.29——整数取
        # 值 42/43/44）
        K30_INPUT_BASE = 43
        K30_INPUT_MIN = 42
        K30_INPUT_MAX = 44

        test_logger.info(
            "=== 测试开始: 客户问题 - /v1/responses 校验码输出与 "
            "token 计数核验（判据：正文严格等于校验码 / input_tokens"
            "∈[42,44] / output=思考+正文）==="
        )

        url = f"{api_client.api_prefix}/responses"
        # K30: 按客户原始 curl 还原请求体（input 两消息、stream、
        # max_output_tokens 原样；模型名由环境注入；原始请求未指定
        # 采样参数——保持不指定、不注入）
        payload: Dict[str, Any] = {
            "input": [
                {
                    "role": "system",
                    "type": "message",
                    "content": [
                        {
                            "text": "只输出指定校验码，不要解释。",
                            "type": "input_text",
                        }
                    ],
                },
                {
                    "role": "user",
                    "type": "message",
                    "content": [
                        {
                            "text": (
                                "这是 合成短文本 Token 对照测试。请只"
                                "输出 SYNTHETIC_SHORT_TEXT_MARKER。"
                            ),
                            "type": "input_text",
                        }
                    ],
                }
            ],
            "model": api_client.model_name,
            "stream": True,
            "max_output_tokens": 1024,
        }
        TestLogger.log_request(
            test_logger,
            [
                {
                    "role": "system",
                    "content": "只输出指定校验码，不要解释。",
                },
                {
                    "role": "user",
                    "content": (
                        "这是 合成短文本 Token 对照测试。请只输出 "
                        "SYNTHETIC_SHORT_TEXT_MARKER。"
                    ),
                },
            ],
            {
                "endpoint": "/v1/responses",
                "stream": True,
                "max_output_tokens": 1024,
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )

        started = time.time()
        try:
            response = api_client.session.post(
                url,
                json=payload,
                timeout=api_client.timeout,
                stream=True,
            )
        except Exception as e:
            pytest.fail(f"请求发送异常（{url}）: {e}")
        elapsed = time.time() - started
        # 模型真实响应断言前打印（失败时同样可见）
        test_logger.info(
            f"真实响应: HTTP {response.status_code}, "
            f"elapsed={elapsed:.1f}s, body={response.text[:800]!r}"
        )
        # 断言1a：请求应成功（/v1/responses 端点可用为前提）
        assert response.status_code == 200, (
            f"/v1/responses 请求失败：实际 HTTP "
            f"{response.status_code}: {response.text[:400]}"
        )

        # 解析 Responses API SSE 事件：output_text.delta 合并正文、
        # 终态事件（response.completed/failed/incomplete/cancelled）
        # 取结束状态与 usage（兼容事件级 usage 兜底）
        text_parts: List[str] = []
        usage: Dict[str, Any] = {}
        end_status = None
        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8", errors="replace")
            if not line.startswith("data: "):
                continue
            s = line[6:].strip()
            if s == "[DONE]":
                break
            try:
                event = json.loads(s)
            except json.JSONDecodeError:
                continue
            etype = event.get("type") or ""
            if etype.endswith("output_text.delta"):
                text_parts.append(event.get("delta") or "")
            if etype in (
                "response.completed",
                "response.failed",
                "response.incomplete",
                "response.cancelled",
            ):
                resp_obj = event.get("response") or {}
                end_status = (
                    resp_obj.get("status") or etype.split(".")[-1]
                )
                if not usage and resp_obj.get("usage"):
                    usage = resp_obj["usage"]
            if not usage and event.get("usage"):
                usage = event["usage"]
        text = "".join(text_parts).strip()
        test_logger.info(
            f"合并正文（{len(text)} 字符）: {text[:300]!r}；end_status="
            f"{end_status}, usage={json.dumps(usage, ensure_ascii=False)}"
        )
        # 断言1b：流式结构完整（含正文增量与 usage）
        assert text_parts, "流式响应未收到任何 output_text 增量"
        assert usage, "流式响应未收到 usage（response.completed 缺失）"
        # 断言2（结束状态）：终态事件 status 必须为 completed——
        # failed/incomplete/cancelled 或无终态事件均为非正常结束
        assert end_status == "completed", (
            f"结束状态异常：response.status={end_status!r}（期望 "
            f"'completed'；failed/incomplete/cancelled 或无终态事件均"
            f"为非正常结束）"
        )

        # 断言2（校验码原样输出）：合并正文严格等于指定校验码——请
        # 求明确要求只输出该校验码、不要任何额外解释（客户缺陷形
        # 态：实际输出 '4b69a88e6b' 与要求完全无关）
        assert text == K30_MARKER, (
            f"校验码原样输出失败：请求要求只输出 {K30_MARKER!r}，实际"
            f"合并正文 {text[:200]!r}（模型侧未遵守指令/含额外内容）"
        )

        # 断言3（input_tokens 基准）：43 ±3%（区间 41.71-44.29——
        # 整数取值 42/43/44；客户缺陷形态：input_tokens=52）
        input_tokens = usage.get("input_tokens")
        assert isinstance(input_tokens, int), (
            f"usage.input_tokens 缺失或非整数: {input_tokens!r}"
        )
        assert K30_INPUT_MIN <= input_tokens <= K30_INPUT_MAX, (
            f"input_tokens 超出基准区间：实际 {input_tokens}，基准 "
            f"{K30_INPUT_BASE} ±3%（{K30_INPUT_MIN}-{K30_INPUT_MAX}；"
            f"可能为分词器或消息包装差异）"
        )

        # 断言4（输出计数=思考+正文）：reasoning_tokens ≤
        # output_tokens ≤ reasoning_tokens + len(正文)——1 token/字
        # 符为宽松上界（正常文本 2-6 字符/token；客户缺陷形态：
        # output_tokens=295 vs 实际 10 字符且 reasoning=0，远超此
        # 界）
        output_tokens = usage.get("output_tokens")
        assert isinstance(output_tokens, int), (
            f"usage.output_tokens 缺失或非整数: {output_tokens!r}"
        )
        reasoning_tokens = (
            (usage.get("output_tokens_details") or {}).get(
                "reasoning_tokens"
            )
            or 0
        )
        assert output_tokens >= reasoning_tokens, (
            f"输出计数结构异常：output_tokens={output_tokens} < "
            f"reasoning_tokens={reasoning_tokens}（总输出不得小于思考"
            f"部分）"
        )
        bound = reasoning_tokens + max(len(text), 1)
        assert output_tokens <= bound, (
            f"输出计数与实际文本量不成比例：output_tokens="
            f"{output_tokens}，正文 {len(text)} 字符（≈{len(text)} "
            f"token 上界）+ reasoning_tokens={reasoning_tokens}，合计"
            f"上界 {bound}——总输出 tokens 应 ≈ 正文 + 思考（存在统"
            f"计口径或隐藏推理未计入疑点）"
        )
        test_logger.info(
            f"客户问题复现通过: 校验码原样输出（{K30_MARKER}）、"
            f"input_tokens={input_tokens}∈[{K30_INPUT_MIN},"
            f"{K30_INPUT_MAX}]、output_tokens={output_tokens} ≈ 正文"
            f"{len(text)} 字符+reasoning={reasoning_tokens}（计数正"
            f"确），elapsed={elapsed:.1f}s"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p1
    def test_json_object_nested_empty_content(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K31 [P1]: 客户问题 - json_object 嵌套结构完整输出与预
        算回退核验（256→512，chat+msg 双协议）

        客户问题（工单 P1 R-01+A-07a/A-07b · json_object 嵌套
        对象/数组返回空正文，结构化输出）：官方行为 HTTP 200、
        content 为合法 JSON（嵌套对象/数组均可解析）；贵方实测
        finish_reason=length、content 为空字符串、思考内容占满
        max_tokens=256——A-07a（嵌套对象 user.name/user.age/
        address.city，021-023.json）与 A-07b（数组 3 个 id+title
        对象，024-026.json）两种请求各 3 发全部该形态（3 采样
        0 过，2026-11-03），reasoning_tokens=256/256、
        prompt_tokens=36/40。用户确认：思考消耗配额致空正文/
        截断在官方与被测均有一定概率发生——验收口径调整为预算
        回退链（用户指定）：核心需求为在 max_tokens 内能返回完
        整合法 JSON。
        本用例覆盖 chat+msg 双协议 × 工单两种形态（A-07a/A-07b
        提示词与请求体工单原样——chat 字段序 model/messages/
        max_tokens/response_format、无 stream 字段；msg 无
        json_object 参数语义，同一 prompt 引导）× 预算回退链：
        1. 轮一 max_tokens=256（工单原值）：HTTP 200 + 正文非
           空 + json.loads 成功 + 嵌套结构齐备 → 链直接达标
        2. 轮一不满足（空正文/json 截断或非法/结构不齐）→ 回
           退 max_tokens=512 同请求重验
        3. 512 满足 → 测试通过 + 警告留痕（警告显示 256 输出
           空正文或 json 截断及 finish 状态——思考消耗配额属
           官方/被测共有随机形态）
        4. 256 与 512 均不满足 → FAIL（输出两轮各自不满足形态）
        HTTP 非 200 直接 FAIL（回退链仅针对正文形态）。
        结构校验（嵌套层级不定——递归宽容）：A-07a——含 name+
        age 的 user 嵌套对象与含 city 的 address 嵌套对象齐备
        （顶层或 user 内嵌均认可）；A-07b——对象数组且每元素
        含 id/title（json_object 约束下裸数组或对象包裹两形态
        均认可；数量=3 与 id 数字类型留观察不判据）。
        观察记录（不计判据，留日志）：每轮 finish_reason/
        stop_reason、正文与 reasoning 长度、completion_tokens/
        reasoning_tokens（A-07 形态=空正文+reasoning_tokens=
        256 留痕）、耗时；finish=length/max_tokens 且正文完整
        合法不判失败。
        模型名由环境注入；工单原始请求未指定采样参数/thinking/
        stream——保持不指定（不注入）；相邻请求间隔 3s。GLM-5.3
        专用。（不进 smoke 集：新用例首跑观察期；双协议 × 两形
        态 4 链 × 每链 1-2 发）
        """
        # K31: 工单原值——json_object 嵌套/数组两形态预算上限
        K31_MAX_TOKENS = 256
        # K31: 预算回退上限（用户指定——256 空正文/截断时重验；
        # 思考消耗配额致空正文/截断在官方/被测均有概率发生）
        K31_FALLBACK_MAX_TOKENS = 512
        # K31: 工单 A-07a 原样提示词（嵌套对象——user.name/
        # user.age/address.city 嵌套结构，021-023.json 三发）
        K31_A07A_PROMPT = (
            "返回一个 JSON 对象,含 user.name、user.age 和 "
            "address.city(嵌套结构)。只输出 JSON。"
        )
        # K31: 工单 A-07b 原样提示词（数组——3 个 id+title 对
        # 象，024-026.json 三发）
        K31_A07B_PROMPT = (
            "返回一个 JSON 数组,含 3 个对象,每个对象有 id(数字)"
            "和 title(字符串)。只输出 JSON。"
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - json_object 嵌套结构完整输"
            "出与预算回退核验（工单 P1 R-01+A-07a/A-07b：chat/msg "
            "双协议 × 嵌套对象/数组 × 预算回退链——256 工单原值优"
            "先，空正文/json 截断回退 512，512 达标警告通过，两轮"
            "均不达标 FAIL）==="
        )

        chat_url = f"{api_client.api_prefix}/chat/completions"
        msg_url = f"{api_client.base_url}/anthropic/v1/messages"

        def find_dict_with_keys(
            node: Any, required: tuple
        ) -> Optional[Dict[str, Any]]:
            """K31: 递归查找包含全部 required 键的 dict（A-07a 嵌
            套层级不定——user/address 顶层或内嵌均认可）"""
            if isinstance(node, dict):
                if all(k in node for k in required):
                    return node
                for value in node.values():
                    found = find_dict_with_keys(value, required)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = find_dict_with_keys(item, required)
                    if found is not None:
                        return found
            return None

        def check_a07a_object(tag: str, parsed: Any) -> None:
            """K31 A-07a 结构校验：JSON 对象，含 name+age 的 user
            嵌套对象与含 city 的 address 嵌套对象递归齐备"""
            assert isinstance(parsed, dict), (
                f"[{tag}] A-07a 应输出 JSON 对象（提示词要求嵌套"
                f"对象+json_object 语义），实际类型: "
                f"{type(parsed).__name__}（{str(parsed)[:150]}）"
            )
            user_obj = find_dict_with_keys(parsed, ("name", "age"))
            assert user_obj is not None, (
                f"[{tag}] A-07a 嵌套结构不齐：未找到含 name+age 的"
                f"user 嵌套对象，实际: {str(parsed)[:200]}"
            )
            addr_obj = find_dict_with_keys(parsed, ("city",))
            assert addr_obj is not None, (
                f"[{tag}] A-07a 嵌套结构不齐：未找到含 city 的 "
                f"address 嵌套对象，实际: {str(parsed)[:200]}"
            )

        def find_item_array(node: Any) -> Optional[List[Any]]:
            """K31: 查找对象数组（顶层裸数组或 dict 单层包裹——
            json_object 约束下模型可能以对象包裹数组，两形态均
            认可）"""
            if isinstance(node, list) and node and all(
                isinstance(x, dict) for x in node
            ):
                return node
            if isinstance(node, dict):
                for value in node.values():
                    if isinstance(value, list) and value and all(
                        isinstance(x, dict) for x in value
                    ):
                        return value
            return None

        def check_a07b_array(tag: str, parsed: Any) -> None:
            """K31 A-07b 结构校验：对象数组且每元素含 id+title
            （数量=3 与 id 数字类型留观察不判据——避免对生成细
            节过严误报）"""
            items = find_item_array(parsed)
            assert items is not None, (
                f"[{tag}] A-07b 嵌套结构不齐：未找到对象数组，实"
                f"际: {str(parsed)[:200]}"
            )
            for idx, item in enumerate(items):
                assert "id" in item and "title" in item, (
                    f"[{tag}] A-07b 数组第 {idx + 1} 个对象缺 "
                    f"id/title 键，实际: {item!r}"
                )
            if len(items) != 3:
                test_logger.info(
                    f"[{tag}] 观察: 数组含 {len(items)} 个对象"
                    f"（提示词要求 3——数量留观察不判据）"
                )

        def evaluate_output(
            tag: str, content: str, structure_check
        ) -> tuple:
            """K31: 单轮预算输出核验——返回（合格?, 不满足形态描
            述）（空正文/json 截断或非法/结构不齐三类形态供回退
            链警告与失败信息引用）"""
            if not content or not content.strip():
                return False, "空正文"
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                return False, f"json 截断/非法（{e}）"
            try:
                structure_check(tag, parsed)
            except AssertionError as e:
                return False, f"嵌套结构不齐（{str(e)[:200]}）"
            return True, ""

        def send_chat(
            tag: str, prompt: str, max_tokens: int
        ) -> Dict[str, Any]:
            """K31 chat 协议预算轮：json_object 非流式，返回轮结
            果（正文判定由预算回退链统一执行——send 仅采集）"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": prompt}],
                {
                    "endpoint": "/v1/chat/completions",
                    "response_format": {"type": "json_object"},
                    "max_tokens": max_tokens,
                    "stream": "(工单未带——不传)",
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K31: 工单 A-07 原样 payload 直发（字段序按工单
            # model/messages/max_tokens/response_format；response_
            # format 直进 payload——json_object 语义；max_tokens
            # 256 工单原值/512 回退值；stream/采样参数工单未带
            # ——不传）
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            }
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    chat_url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{tag}] 请求发送异常（{chat_url}）: {e}")
            elapsed = time.time() - started
            try:
                data = response.json()
            except ValueError:
                data = None
            # 模型真实响应断言前打印（失败时同样可见）
            test_logger.info(
                f"[{tag}] 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, "
                f"body={response.text[:800]!r}"
            )
            # 断言：HTTP 200（非 200 直接 FAIL——回退链仅针对正文
            # 形态，不覆盖请求层失败）
            assert response.status_code == 200, (
                f"[{tag}] 请求失败：实际 HTTP "
                f"{response.status_code}: {response.text[:400]}"
            )
            assert data, f"[{tag}] 响应体应为合法 JSON"
            choices = data.get("choices") or []
            assert choices, f"[{tag}] 响应缺少 choices: {data!r}"
            choice = choices[0] or {}
            message = choice.get("message") or {}
            content = message.get("content") or ""
            finish_reason = choice.get("finish_reason")
            usage = data.get("usage") or {}
            reasoning_tokens = (usage.get("completion_tokens_details") or {}).get(
                "reasoning_tokens"
            )
            # 观察记录：预算分配留痕（A-07 实测形态=空正文+
            # reasoning_tokens=256——思考占满配额）
            test_logger.info(
                f"[{tag}] finish_reason={finish_reason!r}, 正文 "
                f"{len(content)} 字符, reasoning "
                f"{len(message.get('reasoning_content') or '')} 字符"
                f", completion_tokens={usage.get('completion_tokens')}"
                f", reasoning_tokens={reasoning_tokens}"
            )
            if not content.strip() and reasoning_tokens:
                test_logger.info(
                    f"[{tag}] 观察: 空正文且 reasoning_tokens="
                    f"{reasoning_tokens}——思考占满配额（A-07 实测"
                    f"形态，留痕不判据）"
                )
            return {
                "content": content,
                "finish_reason": finish_reason,
                "elapsed": elapsed,
            }

        def send_msg(
            tag: str, prompt: str, max_tokens: int
        ) -> Dict[str, Any]:
            """K31 msg 协议预算轮（/anthropic/v1/messages——K3 先
            例构造；协议无 json_object 参数语义，同一 prompt 引
            导；max_tokens 为协议必需字段），返回轮结果"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": prompt}],
                {
                    "endpoint": "/anthropic/v1/messages",
                    "protocol": "anthropic（x-api-key + "
                                "anthropic-version 头）",
                    "response_format": "(协议无语义——不传)",
                    "max_tokens": max_tokens,
                    "stream": "(工单未带——不传)",
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K31: msg 镜像 payload（协议必需字段 max_tokens——
            # 256 工单原值/512 回退值；无 response_format 语义
            # ——不传；stream 工单未带——不传）
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "max_tokens": max_tokens,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}],
                    }
                ],
            }
            headers: Dict[str, Any] = {
                "anthropic-version": "2023-06-01"
            }
            if api_client.api_key:
                headers["x-api-key"] = api_client.api_key
            started = time.time()
            try:
                response = api_client.session.post(
                    msg_url,
                    json=payload,
                    headers=headers,
                    timeout=api_client.timeout,
                )
            except Exception as e:
                pytest.fail(f"[{tag}] 请求发送异常（{msg_url}）: {e}")
            elapsed = time.time() - started
            try:
                data = response.json()
            except ValueError:
                data = None
            test_logger.info(
                f"[{tag}] 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, body={response.text[:800]!r}"
            )
            # 断言：HTTP 200（非 200 直接 FAIL——同 chat 侧口径）
            assert response.status_code == 200, (
                f"[{tag}] msg 协议嵌套 JSON 引导请求（max_tokens="
                f"{max_tokens}）应放行 HTTP 200，实际 "
                f"{response.status_code}（body={response.text[:400]!r}）"
            )
            assert data, f"[{tag}] 200 响应体应为合法 JSON 对象"
            content_arr = data.get("content") or []
            text = "".join(
                c.get("text") or ""
                for c in content_arr
                if isinstance(c, dict) and c.get("type") == "text"
            ).strip()
            stop_reason = data.get("stop_reason")
            # 观察记录：stop_reason 与正文/usage 留痕（max_tokens
            # 即 chat 侧 length 的 msg 形态）
            test_logger.info(
                f"[{tag}] stop_reason={stop_reason!r}, 正文 "
                f"{len(text)} 字符, usage={data.get('usage')!r}"
            )
            return {
                "content": text,
                "finish_reason": stop_reason,
                "elapsed": elapsed,
            }

        def run_budget_chain(
            protocol: str,
            form_label: str,
            prompt: str,
            structure_check,
            send,
        ) -> bool:
            """K31: 预算回退链（用户指定口径）——256 工单原值优
            先；空正文/json 截断或非法/结构不齐则回退 512 重验；
            512 达标→警告+通过；两轮均不达标→FAIL；返回是否经
            回退达标"""
            tag_base = f"{protocol}/形态={form_label}"
            # ── 轮一：max_tokens=256（工单原值）──
            tag1 = f"{tag_base}/256轮"
            r1 = send(tag1, prompt, K31_MAX_TOKENS)
            ok1, desc1 = evaluate_output(
                tag1, r1["content"], structure_check
            )
            if ok1:
                test_logger.info(
                    f"[{tag1}] 通过: 工单预算 max_tokens="
                    f"{K31_MAX_TOKENS} 内正文完整合法、嵌套结构齐"
                    f"备（{len(r1['content'])} 字符），elapsed="
                    f"{r1['elapsed']:.1f}s"
                )
                return False
            test_logger.info(
                f"[{tag1}] 预算未满足: {desc1}（finish="
                f"{r1['finish_reason']!r}）——回退 max_tokens="
                f"{K31_FALLBACK_MAX_TOKENS} 重验"
            )
            time.sleep(3)
            # ── 轮二：max_tokens=512（预算回退）──
            tag2 = f"{tag_base}/512回退轮"
            r2 = send(tag2, prompt, K31_FALLBACK_MAX_TOKENS)
            ok2, desc2 = evaluate_output(
                tag2, r2["content"], structure_check
            )
            if ok2:
                # 用户指定：512 达标→测试通过+警告留痕（警告显示
                # 256 输出空正文或 json 截断及 finish 状态）
                test_logger.warning(
                    f"警告：[{tag_base}] 工单预算 max_tokens="
                    f"{K31_MAX_TOKENS} 输出{desc1}（finish="
                    f"{r1['finish_reason']!r}，正文 "
                    f"{len(r1['content'])} 字符）——预算回退 "
                    f"max_tokens={K31_FALLBACK_MAX_TOKENS} 后正文"
                    f"完整合法、嵌套结构齐备（{len(r2['content'])} "
                    f"字符，finish={r2['finish_reason']!r}），测试"
                    f"通过；256 预算下思考消耗配额属官方/被测共有"
                    f"随机形态，留痕观察"
                )
                return True
            # 用户指定：256 与 512 均不满足→用例失败（输出两轮各
            # 自不满足形态）
            pytest.fail(
                f"[{tag_base}] 预算回退链均未满足需求——256 轮: "
                f"{desc1}（finish={r1['finish_reason']!r}，正文头 "
                f"{r1['content'][:120]!r}）；512 回退轮: {desc2}"
                f"（finish={r2['finish_reason']!r}，正文头 "
                f"{r2['content'][:120]!r}）——在 max_tokens 内返回"
                f"完整合法 JSON 的需求未达成"
            )

        # K31: 主流程——chat+msg 双协议 × 工单两形态 × 预算回退
        # 链（每形态 chat → msg，相邻间隔 3s；经回退达标的链计
        # 数供收尾统计）
        forms = (
            ("嵌套对象", K31_A07A_PROMPT, check_a07a_object),
            ("数组", K31_A07B_PROMPT, check_a07b_array),
        )
        senders = (("chat", send_chat), ("msg", send_msg))
        total = 0
        fallback_count = 0
        for form_label, prompt, structure_check in forms:
            for protocol, send in senders:
                if total:
                    time.sleep(3)
                total += 1
                if run_budget_chain(
                    protocol, form_label, prompt, structure_check, send
                ):
                    fallback_count += 1
        if fallback_count:
            test_logger.info(
                f"客户问题整改验证通过（预算回退链）: chat/msg 双协"
                f"议 × 嵌套对象/数组 {total} 链——{fallback_count} 链"
                f"经 max_tokens={K31_FALLBACK_MAX_TOKENS} 回退达标"
                f"（警告留痕：256 预算输出空正文/json 截断），其余 "
                f"{total - fallback_count} 链 256 工单预算直接达标"
                f"——在 max_tokens 内返回完整合法 JSON 的需求已验证"
            )
        else:
            test_logger.info(
                f"客户问题整改验证通过（预算回退链）: chat/msg 双协"
                f"议 × 嵌套对象/数组 {total} 链全部 256 工单预算直接"
                f"达标（无回退触发）——在 max_tokens 内返回完整合法 "
                f"JSON 的需求已验证"
            )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p1
    def test_temperature_range_validation(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K32 [P1]: 客户问题 - temperature 原厂区间 [0, 2] 放
        行与越界校验（chat+msg 双协议）

        客户问题（工单 P1 R-02+A-03 · temperature=1.5 被拒绝（原
        厂接受），参数校验）：官方行为 HTTP 200（原厂取值区间
        [0, 2]，1.5 合法）；贵方最新实测（A-03，2026-11-03）chat
        三发 temperature=1.5 全部 HTTP 400，错误体「temperature
        超出范围 [0, 1]」(bad_response_status_code)——本地收紧
        到 [0, 1]；历史形态（R-02）6 发全部 400 通用「模型服务
        调用失败」(upstream_error)。整改建议（即预期结果，用户
        指定）：放开 temperature 到原厂支持的 [0, 2] 区间（原合
        法区间 [0, 2) 调整为 [0, 2]——上界端点 2.0 移入放行），
        或按原厂取值原样透传，不做本地收紧；保留非法参数校验
        （越界 400 并指明参数名与合法区间）。
        本用例按整改建议设计双向验收（参数校验为确定性行为；
        chat 放行点按工单 A-03 三发依序复现，其余组合每组合
        1 次——K6 先例）双协议覆盖（chat + msg——K31 起用例
        须验证 /v1/chat/completions 与 /v1/messages 双协议，
        用户指定）：
        1. chat 协议（原厂区间 [0, 2]，含上界端点）——
           a. 工单 A-03 三发复现（缺陷复现轮）：temperature=
              1.5、content="只回复:好"、max_tokens=32——请求
              体按工单原样（字段序 model/messages/max_tokens/
              temperature，工单未带 stream——不传）→ HTTP
              200（1.5 被接受，与原厂一致；400 即本地收紧缺
              陷复现——A-03 形态「temperature 超出范围
              [0, 1]」留证）+ 响应体为合法 JSON 且 choices
              非空；正文/finish_reason 留观察不计判据（max_
              tokens=32 小配额下默认思考计入共享配额（R-01
              未整改）易 length/空正文——K31 域形态，非本例
              判据）
            b. 边界放行轮：temperature=2.0（区间上界端点——原
               [0, 2) 口径越界点移入放行，测试自构造轮非工单
               原发；请求对齐 A-03 轮同形态——content="只回
               复:好"、max_tokens=32、无 stream 字段，短请求
               短响应，用户指定 2026-11-09：本例主目的为验
               证 temperature 支持范围，仅验证合法/非法值能
               否按预期响应）→ HTTP 200 + 响应体为合法 JSON
               且 choices 非空；正文/finish_reason 留观察不
               计判据（对齐 A-03 轮口径——主判据=2.0 被接
               受 200；max_tokens=32 小配额+默认思考计入共
               享配额在 2.0 极端温度下易 length/空正文，
               K31 域形态非本例判据）
            c. 左边界放行轮：temperature=0.0（区间下界端
               点——[0, 2] 含 0.0，用户指定 2026-11-09 新增验
               证，此前下界仅由 -0.5 越界轮间接验证；长形态
               content="请用一句话介绍你自己。"+max_tokens=
               1024——所有轮均须 max_tokens 限制；测试自构造
               轮非工单原发）→ HTTP 200 + 响应体为合法 JSON
               且 choices 非空；正文/finish_reason 留观察不
               计判据（对齐 2.0 边界轮口径——主判据=0.0 被
               接受 200；0.0 贪心解码+1024 配额通常正文非
               空+stop）
            d. 越界轮（保留非法校验，用户指定）：2.5（上界外）
               与 -0.5（负向，max_tokens=1024——所有轮均须
               max_tokens 限制，用户指定 2026-11-09）→ HTTP
               400 + 错误体指明参数名
               temperature（大小写不敏感）+ 含上界数字 2（区
               间痕迹断言口径；A-03 形态错误体含 request id
               数字串，数字断言可能恒满足——辅助下限口径，
               本地收紧主判据在放行轮 200）
        2. msg 协议（/anthropic/v1/messages，Anthropic 官方区
           间 [0, 1] 分别校验——A-03 未涉及 msg，维持原口径）
            ——放行轮 temperature=0.5（工单原值 1.5 在该协议
            官方语义下越界，不可作放行点）与 0.0（下界端点
            ——用户指定 2026-11-09 新增验证，双协议口径一
            致；0.0 贪心解码正常生成可满足）→ HTTP 200 + 正
            文非空 + stop_reason 自然结束；越界轮 1.5（工单原
            值，[0, 1] 越界——与 chat 侧同值不同判，验证网关
            按协议语义分别校验而非一刀切）、2.0 与 -0.5 →
            HTTP 400 + 错误体指明参数名 temperature + 含上界
            数字 1（该协议区间痕迹）
        请求：非流式、单 user 闲聊、手工 payload 直发
        （temperature 直进 payload——工单原值原样保留并豁免全
        局采样覆盖；top_p/seed 工单未指定，不注入；A-03 复现
        轮 max_tokens=32 工单原值；chat 2.0 边界轮与 A-03 轮
        同形态（max_tokens=32——用户指定 2026-11-09，短请求
        短响应，原不传 max_tokens 致 2.0 无界生成长尾超
        时）；chat 0.0 左边界轮/越界轮长形态 max_tokens=1024
        ——所有轮均须 max_tokens 限制（用户指定 2026-11-09，
        当前无限制的取 1024，防网关错误放行时无界生成长
        尾）；thinking 工单未指定，不传；msg 侧 max_tokens
        为协议必需字段）；每发 60s 硬超时（K32_HARD_TIMEOUT 用例内自定
        覆盖全局 timeout——本例小请求正常返回毫秒级-秒级，挂
        起/严重延迟快速失败：超时即 FAIL（异常信号留痕）并报
        告超时值，仅本用例生效、不影响他例）；相邻间隔 3s
        （A-03 工单三发采集间隔 1s，节奏非判据）。模型名由环
        境注入。GLM-5.3 专用。（不进 smoke 集：新用例首跑观察
        期）
        """
        # K32: chat 协议工单原值——原厂区间 [0, 2]（含上界端
        # 点）内合法点（A-03：原厂 HTTP 200 接受）
        K32_LEGAL_VALUE = 1.5
        # K32: 工单 A-03 复现轮——原样请求体（content/
        # max_tokens 工单原值；三发依序复现）
        K32_A03_PROMPT = "只回复:好"
        K32_A03_MAX_TOKENS = 32
        K32_A03_ROUNDS = 3
        # K32: chat 协议区间上界端点——[0, 2] 含 2.0（原
        # [0, 2) 口径越界点移入放行，测试自构造边界轮）
        K32_UPPER_BOUND = 2.0
        # K32: chat 协议区间下界端点——[0, 2] 含 0.0（左边界
        # 放行轮，用户指定 2026-11-09 新增验证；长形态
        # K32_PROMPT+max_tokens=1024，与越界轮同族）
        K32_LOWER_BOUND = 0.0
        # K32: chat 协议越界点（[0, 2] 闭区间外——上界外不
        # 含、负数不含；保留非法参数校验，用户指定）
        K32_OUT_OF_RANGE = (2.5, -0.5)
        # K32: chat 长形态轮（0.0 左边界轮/越界轮）max_tokens
        # ——所有轮均须 max_tokens 限制（用户指定 2026-11-09，
        # 当前无限制的取 1024；防网关错误放行时无界生成长尾）
        K32_LONG_FORM_MAX_TOKENS = 1024
        # K32: msg 协议（Anthropic 官方区间 [0, 1]）放行点——工
        # 单原值 1.5 在该协议官方语义下越界，取 [0, 1] 内合法
        # 中位点（A-03 未涉及 msg，维持原口径）
        K32_MSG_LEGAL_VALUE = 0.5
        # K32: msg 协议区间下界端点——[0, 1] 含 0.0（左边界放
        # 行轮，用户指定 2026-11-09 新增验证，双协议口径一致）
        K32_MSG_LOWER_BOUND = 0.0
        # K32: msg 协议越界点——工单原值 1.5（[0, 1] 越界，与
        # chat 侧同值不同判——验证网关按协议语义分别校验）+ 2.0
        # + -0.5
        K32_MSG_OUT_OF_RANGE = (1.5, 2.0, -0.5)
        # K32: msg 协议必需字段（Anthropic 无默认值）——单 user
        # 闲聊最小合理值
        K32_MSG_MAX_TOKENS = 1024
        # K32: chat 0.0 左边界轮/越界轮与 msg 侧单 user 闲聊
        # prompt（2.0 边界轮已对齐 A-03 短形态，用户指定
        # 2026-11-09）
        K32_PROMPT = "请用一句话介绍你自己。"
        # K32: 每发 60s 硬超时（用例内自定覆盖全局 timeout——本
        # 例全部为小请求：越界轮 400 参数校验层毫秒级、A-03 轮
        # max_tokens=32 秒级、2.0 边界轮短形态秒级、0.0 左边
        # 界轮 1024 配额秒级，无需按全局
        # 1200s 等待——挂起/严重延迟快速失败（超时即 FAIL 留
        # 痕）；仅本用例生效，不影响其他用例（_post_with_retry
        # 的 timeout 参数默认 None=沿用全局值））
        K32_HARD_TIMEOUT = 60

        test_logger.info(
            "=== 测试开始: 客户问题 - temperature 原厂区间 [0, 2] "
            "放行与越界校验（工单 P1 R-02+A-03：chat 侧工单三发复"
            "现 1.5（预期 200）+ 边界 2.0/0.0 放行 + 越界 2.5/"
            "-0.5；msg 按 Anthropic 区间 [0, 1]：放行 0.5/0.0 + "
            "越界 1.5/2.0/-0.5）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        def send_round(
            tag: str,
            temperature: float,
            prompt: str = K32_PROMPT,
            max_tokens: Optional[int] = None,
            with_stream: bool = True,
        ):
            """K32 chat 单轮：构造带指定 temperature 的请求直发
            （所有轮均传 max_tokens——A-03 复现轮/2.0 边界轮短
            形态 32、0.0 左边界轮/越界轮长形态 1024（用户指定
            2026-11-09：所有轮均须 max_tokens 限制）；stream
            ——A-03/2.0 轮不传，0.0/越界轮 stream=False）"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": prompt}],
                {
                    "endpoint": "/v1/chat/completions",
                    "temperature": temperature,
                    "max_tokens": (
                        max_tokens
                        if max_tokens is not None
                        else "(原始未指定——不传)"
                    ),
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K32: 手工构造 payload 直发（temperature 直进 payload
            # ——工单原值原样保留；top_p/seed 工单未指定——不注
            # 入；A-03 复现轮 max_tokens=32 工单原值、stream 工
            # 单未带不传，其余轮 max_tokens/thinking 不传、
            # stream=False 非流式直发）
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": prompt}],
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            payload["temperature"] = temperature
            if with_stream:
                payload["stream"] = False
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url,
                    payload,
                    stream=False,
                    timeout=K32_HARD_TIMEOUT,
                )
            except requests.exceptions.Timeout as e:
                # K32: 60s 硬超时——小请求正常返回毫秒级-秒级，
                # 零字节无响应即挂起/严重延迟异常信号，快速失败
                pytest.fail(
                    f"[{tag}] {K32_HARD_TIMEOUT}s 硬超时内无响应"
                    f"（requests 超时：{e}——异常信号：挂起或严重"
                    f"延迟；本例小请求正常返回为毫秒级-秒级）"
                )
            except Exception as e:
                pytest.fail(f"[{tag}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started
            # 模型真实响应断言前打印（失败时同样可见）
            test_logger.info(
                f"[{tag}] 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, "
                f"body={response.text[:800]!r}"
            )
            return response, elapsed

        # ── 工单 A-03 三发复现：temperature=1.5（缺陷复现轮
        # ——工单原样请求体，预期与原厂一致 HTTP 200）─────────
        # 断言口径（整改建议即预期结果）：A-03 判据为 HTTP 状态
        # 语义——1.5 被接受=200（400 即本地收紧缺陷复现）
        for i in range(1, K32_A03_ROUNDS + 1):
            if i > 1:
                time.sleep(3)
            tag = (
                f"复现{i}/{K32_A03_ROUNDS}/"
                f"temperature={K32_LEGAL_VALUE}"
            )
            response, elapsed = send_round(
                tag,
                K32_LEGAL_VALUE,
                prompt=K32_A03_PROMPT,
                max_tokens=K32_A03_MAX_TOKENS,
                with_stream=False,
            )
            # 断言1：合法值应 200 放行（A-03 缺陷形态：三发全部
            # 400「temperature 超出范围 [0, 1]」——本地收紧到
            # [0, 1]；整改预期：放开到原厂 [0, 2] 或原样透传）
            assert response.status_code == 200, (
                f"[{tag}] 缺陷复现：原厂区间 [0, 2] 内合法值被拒"
                f"——实际 HTTP {response.status_code}: "
                f"{response.text[:400]}（工单 A-03 形态：三发全部"
                f" 400「temperature 超出范围 [0, 1]」——本地收"
                f"紧；历史 R-02 形态：6 发通用『模型服务调用失"
                f"败』upstream_error）"
            )
            # 断言2：响应体为合法 JSON 且 choices 非空（200 须
            # 为有效补全结构）
            try:
                data = response.json()
            except ValueError:
                data = None
            assert data, f"[{tag}] 响应体应为合法 JSON"
            choices = data.get("choices") or []
            assert choices, f"[{tag}] 响应缺少 choices: {data!r}"
            choice = choices[0] or {}
            content = (choice.get("message") or {}).get("content") or ""
            finish_reason = choice.get("finish_reason")
            # 正文/finish_reason 留观察（不计判据）——max_
            # tokens=32 小配额下默认思考计入共享配额（R-01 未整
            # 改）易 length/空正文，属 K31 域形态；A-03 判据为
            # HTTP 状态语义（1.5 被接受=200）
            if content.strip():
                test_logger.info(
                    f"[{tag}] 观察: 正文 {len(content)} 字符、"
                    f"finish_reason={finish_reason!r}, "
                    f"elapsed={elapsed:.1f}s"
                )
            else:
                test_logger.warning(
                    f"[{tag}] 观察: 正文为空、finish_reason="
                    f"{finish_reason!r}（max_tokens=32 小配额+"
                    f"默认思考计入配额——K31 域形态，非本例判"
                    f"据）, elapsed={elapsed:.1f}s"
                )

        # ── 边界放行轮：temperature=2.0（区间上界端点——原
        # [0, 2) 口径越界点移入放行，用户指定 [0, 2] 含端点；
        # 测试自构造轮非工单原发；请求对齐 A-03 轮同形态
        # ——content="只回复:好"、max_tokens=32、无 stream 字
        # 段，短请求短响应（用户指定 2026-11-09：本例主目的
        # 为验证 temperature 支持范围，仅验证合法/非法值能否
        # 按预期响应；原长 prompt+无 max_tokens 在 2.0 极端
        # 温度下思考乱码无界生成长尾，首跑 60s 超时——curl
        # 复核服务端 200 正常放行，非服务端缺陷）──────────
        time.sleep(3)
        tag = f"边界/temperature={K32_UPPER_BOUND}"
        response, elapsed = send_round(
            tag,
            K32_UPPER_BOUND,
            prompt=K32_A03_PROMPT,
            max_tokens=K32_A03_MAX_TOKENS,
            with_stream=False,
        )
        # 断言1：区间端点应 200 放行（[0, 2] 闭区间含 2.0）
        assert response.status_code == 200, (
            f"[{tag}] 缺陷复现：原厂区间 [0, 2] 含上界端点，"
            f"2.0 应放行——实际 HTTP {response.status_code}: "
            f"{response.text[:400]}（用户指定口径：原合法区间 "
            f"[0, 2) 调整为 [0, 2]，不做本地收紧）"
        )
        try:
            data = response.json()
        except ValueError:
            data = None
        assert data, f"[{tag}] 响应体应为合法 JSON"
        choices = data.get("choices") or []
        assert choices, f"[{tag}] 响应缺少 choices: {data!r}"
        choice = choices[0] or {}
        content = (choice.get("message") or {}).get("content") or ""
        finish_reason = choice.get("finish_reason")
        # 正文/finish_reason 留观察不计判据（对齐 A-03 轮口
        # 径，用户指定 2026-11-09：主判据=2.0 被接受 200——
        # max_tokens=32 小配额+默认思考计入共享配额在 2.0 极
        # 端温度下思考乱码易耗尽配额→length/空正文，属 K31
        # 域形态非本例判据）
        if content.strip():
            test_logger.info(
                f"[{tag}] 观察: 正文 {len(content)} 字符、"
                f"finish_reason={finish_reason!r}, "
                f"elapsed={elapsed:.1f}s"
            )
        else:
            test_logger.warning(
                f"[{tag}] 观察: 正文为空、finish_reason="
                f"{finish_reason!r}（max_tokens=32 小配额+"
                f"默认思考计入配额——K31 域形态，非本例判"
                f"据）, elapsed={elapsed:.1f}s"
            )

        # ── 左边界放行轮：temperature=0.0（区间下界端点——
        # [0, 2] 含 0.0，用户指定 2026-11-09 新增验证；长形
        # 态 K32_PROMPT+max_tokens=1024，所有轮均须 max_
        # tokens 限制；测试自构造轮非工单原发）────────────
        time.sleep(3)
        tag = f"左边界/temperature={K32_LOWER_BOUND}"
        response, elapsed = send_round(
            tag,
            K32_LOWER_BOUND,
            max_tokens=K32_LONG_FORM_MAX_TOKENS,
        )
        # 断言1：区间下界端点应 200 放行（[0, 2] 闭区间含 0.0）
        assert response.status_code == 200, (
            f"[{tag}] 缺陷复现：原厂区间 [0, 2] 含下界端点，"
            f"0.0 应放行——实际 HTTP {response.status_code}: "
            f"{response.text[:400]}（用户指定口径：验证左边界 "
            f"0.0 放行——下界此前仅由 -0.5 越界轮间接验证）"
        )
        try:
            data = response.json()
        except ValueError:
            data = None
        assert data, f"[{tag}] 响应体应为合法 JSON"
        choices = data.get("choices") or []
        assert choices, f"[{tag}] 响应缺少 choices: {data!r}"
        choice = choices[0] or {}
        content = (choice.get("message") or {}).get("content") or ""
        finish_reason = choice.get("finish_reason")
        # 正文/finish_reason 留观察不计判据（对齐 2.0 边界轮口
        # 径——主判据=0.0 被接受 200；0.0 贪心解码+1024 配额通
        # 常正文非空+stop，思考计入共享配额的极端形态留观察）
        if content.strip():
            test_logger.info(
                f"[{tag}] 观察: 正文 {len(content)} 字符、"
                f"finish_reason={finish_reason!r}, "
                f"elapsed={elapsed:.1f}s"
            )
        else:
            test_logger.warning(
                f"[{tag}] 观察: 正文为空、finish_reason="
                f"{finish_reason!r}（思考计入共享配额——K31 域形"
                f"态观察，非本例判据）, elapsed={elapsed:.1f}s"
            )

        # ── 越界轮：2.5（上界外）/ -0.5（负向）——保留非法参
        # 数校验（用户指定）───────────────────────────────────
        # 断言口径（整改建议即预期结果）：越界回 400 + 错误体指明
        # 参数名与合法区间——通用「模型服务调用失败」(upstream_
        # error) 不含参数名与区间，属缺陷形态
        for value in K32_OUT_OF_RANGE:
            time.sleep(3)
            tag = f"越界/temperature={value}"
            # 所有轮均须 max_tokens 限制（用户指定 2026-11-09）
            # ——防网关错误放行时无界生成长尾撞 60s 超时
            response, elapsed = send_round(
                tag, value, max_tokens=K32_LONG_FORM_MAX_TOKENS
            )
            body = response.text
            # 断言1：越界值必须 400 拒绝（[0, 2] 闭区间不含该点）
            assert response.status_code == 400, (
                f"[{tag}] 越界值应 HTTP 400 拒绝（原厂区间 "
                f"[0, 2] 不含该点——越界被静默放行/其他状态均"
                f"为整改未达标），实际 HTTP {response.status_code}: "
                f"{body[:400]}"
            )
            # 断言2：错误体须指明参数名（大小写不敏感）
            assert "temperature" in body.lower(), (
                f"[{tag}] 错误体未指明参数名 temperature（整改要"
                f"求：指明参数名与合法区间；客户缺陷形态：通用『模"
                f"型服务调用失败』upstream_error 不含参数名）: "
                f"{body[:300]}"
            )
            # 断言3：错误体须含合法区间痕迹（上界数字 2——如
            # "[0, 2]" / "0 to 2" 等文案均满足；辅助下限口径：
            # A-03 形态错误体含 request id 数字串（2026…），数
            # 字断言可能恒满足——本地收紧（如 [0, 1] 文案）主
            # 判据在放行轮 200，此处如未满足仍如实 FAIL 复核）
            assert "2" in body, (
                f"[{tag}] 错误体未指明合法区间（整改要求：指明参数"
                f"名与合法区间 [0, 2]——断言口径为错误体含上界数字 "
                f"2）: {body[:300]}"
            )
            test_logger.info(
                f"[{tag}] 通过: 400 拒绝且错误体指明参数名与区间"
                f", elapsed={elapsed:.1f}s"
            )

        # ── msg 协议轮（/anthropic/v1/messages——K3 先例构造，
        # Anthropic 官方区间 [0, 1] 分别校验）──────────────────
        msg_url = f"{api_client.base_url}/anthropic/v1/messages"

        def send_msg_round(tag: str, temperature: float):
            """K32 msg 单轮：构造带指定 temperature 的
            Anthropic 协议请求直发"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K32_PROMPT}],
                {
                    "endpoint": "/anthropic/v1/messages",
                    "protocol": "anthropic（x-api-key + "
                                "anthropic-version 头）",
                    "temperature": temperature,
                    "max_tokens": K32_MSG_MAX_TOKENS,
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K32: msg 协议手工 payload 直发（temperature 直进
            # payload——工单原值原样保留；max_tokens 为协议必需
            # 字段；thinking/stream 工单未指定——不传）
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "max_tokens": K32_MSG_MAX_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": K32_PROMPT}
                        ],
                    }
                ],
                "temperature": temperature,
                "stream": False,
            }
            headers: Dict[str, Any] = {
                "anthropic-version": "2023-06-01"
            }
            if api_client.api_key:
                headers["x-api-key"] = api_client.api_key
            started = time.time()
            try:
                response = api_client.session.post(
                    msg_url,
                    json=payload,
                    headers=headers,
                    timeout=K32_HARD_TIMEOUT,
                )
            except requests.exceptions.Timeout as e:
                # K32: 60s 硬超时（与 chat 侧同口径）——小请求正
                # 常返回毫秒级-秒级，零字节无响应即挂起/严重延
                # 迟异常信号，快速失败
                pytest.fail(
                    f"[{tag}] {K32_HARD_TIMEOUT}s 硬超时内无响应"
                    f"（requests 超时：{e}——异常信号：挂起或严重"
                    f"延迟；本例小请求正常返回为毫秒级-秒级）"
                )
            except Exception as e:
                pytest.fail(
                    f"[{tag}] 请求发送异常（{msg_url}）: {e}"
                )
            elapsed = time.time() - started
            test_logger.info(
                f"[{tag}] 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, "
                f"body={response.text[:800]!r}"
            )
            return response, elapsed

        # msg 放行轮：temperature=0.5（[0, 1] 内合法点）
        time.sleep(3)
        tag = f"msg放行/temperature={K32_MSG_LEGAL_VALUE}"
        response, elapsed = send_msg_round(tag, K32_MSG_LEGAL_VALUE)
        # 断言1：Anthropic 官方区间 [0, 1] 内合法值应 200 放行
        assert response.status_code == 200, (
            f"[{tag}] 缺陷复现：Anthropic 官方区间 [0, 1] 内合"
            f"法值被拒——实际 HTTP {response.status_code}: "
            f"{response.text[:400]}"
        )
        try:
            data = response.json()
        except ValueError:
            data = None
        assert data, f"[{tag}] 响应体应为合法 JSON"
        content_arr = data.get("content") or []
        content = "".join(
            c.get("text") or ""
            for c in content_arr
            if isinstance(c, dict) and c.get("type") == "text"
        ).strip()
        stop_reason = data.get("stop_reason")
        # 断言2：正文非空
        assert content, (
            f"[{tag}] 正文为空（stop_reason={stop_reason!r}）"
        )
        # 断言3：自然结束（stop_reason 存在且非 max_tokens 截断
        # ——Anthropic 枚举含 end_turn/stop_sequence 等自然结束形
        # 态，宽松口径与 K31 msg 轮一致）
        assert stop_reason and stop_reason != "max_tokens", (
            f"[{tag}] 应自然结束，实际 stop_reason="
            f"{stop_reason!r}（合法 temperature 下的正常生成不应"
            f"触顶截断）"
        )
        test_logger.info(
            f"[{tag}] 通过: 正文 {len(content)} 字符、自然结束"
            f"（stop_reason={stop_reason!r}）, elapsed={elapsed:.1f}s"
        )

        # ── msg 左边界放行轮：temperature=0.0（[0, 1] 下界端
        # 点——用户指定 2026-11-09 新增验证，双协议口径一致；
        # msg 家族形态 K32_PROMPT+max_tokens=1024）──────────
        time.sleep(3)
        tag = f"msg左边界/temperature={K32_MSG_LOWER_BOUND}"
        response, elapsed = send_msg_round(
            tag, K32_MSG_LOWER_BOUND
        )
        # 断言1：Anthropic 官方区间 [0, 1] 含下界端点 0.0——
        # 应 200 放行（口径同 0.5 放行轮）
        assert response.status_code == 200, (
            f"[{tag}] 缺陷复现：Anthropic 官方区间 [0, 1] 含下"
            f"界端点 0.0，应放行——实际 HTTP "
            f"{response.status_code}: {response.text[:400]}"
        )
        try:
            data = response.json()
        except ValueError:
            data = None
        assert data, f"[{tag}] 响应体应为合法 JSON"
        content_arr = data.get("content") or []
        content = "".join(
            c.get("text") or ""
            for c in content_arr
            if isinstance(c, dict) and c.get("type") == "text"
        ).strip()
        stop_reason = data.get("stop_reason")
        # 断言2：正文非空（0.0 贪心解码正常生成可满足）
        assert content, (
            f"[{tag}] 正文为空（stop_reason={stop_reason!r}）"
        )
        # 断言3：自然结束（stop_reason 存在且非 max_tokens 截
        # 断——口径同 0.5 放行轮）
        assert stop_reason and stop_reason != "max_tokens", (
            f"[{tag}] 应自然结束，实际 stop_reason="
            f"{stop_reason!r}（合法 temperature 下的正常生成不应"
            f"触顶截断）"
        )
        test_logger.info(
            f"[{tag}] 通过: 正文 {len(content)} 字符、自然结束"
            f"（stop_reason={stop_reason!r}）, elapsed={elapsed:.1f}s"
        )

        # msg 越界轮：1.5（工单原值——[0, 1] 越界，与 chat 侧同
        # 值不同判）/ 2.0 / -0.5——错误体指明参数名与该协议区间
        # 痕迹（上界数字 1）
        for value in K32_MSG_OUT_OF_RANGE:
            time.sleep(3)
            tag = f"msg越界/temperature={value}"
            response, elapsed = send_msg_round(tag, value)
            body = response.text
            # 断言1：越界值必须 400 拒绝（[0, 1] 不含该点）
            assert response.status_code == 400, (
                f"[{tag}] msg 协议越界值应 HTTP 400 拒绝（"
                f"Anthropic 官方区间 [0, 1] 不含该点——越界被静"
                f"默放行/其他状态均为整改未达标），实际 HTTP "
                f"{response.status_code}: {body[:400]}"
            )
            # 断言2：错误体须指明参数名（大小写不敏感）
            assert "temperature" in body.lower(), (
                f"[{tag}] 错误体未指明参数名 temperature（整改"
                f"要求：指明参数名与合法区间；客户缺陷形态：通"
                f"用『模型服务调用失败』upstream_error 不含参数"
                f"名）: {body[:300]}"
            )
            # 断言3：错误体须含该协议合法区间痕迹（上界数字 1
            # ——如 "[0, 1]" / "0 to 1" 等文案均满足）
            assert "1" in body, (
                f"[{tag}] 错误体未指明 msg 协议合法区间（整改要"
                f"求：指明参数名与合法区间 [0, 1]——断言口径为"
                f"错误体含上界数字 1）: {body[:300]}"
            )
            test_logger.info(
                f"[{tag}] 通过: 400 拒绝且错误体指明参数名与区"
                f"间, elapsed={elapsed:.1f}s"
            )
        test_logger.info(
            f"客户问题整改验证通过（双协议）: chat 协议工单 A-03 "
            f"三发 temperature={K32_LEGAL_VALUE} 复现均 200（原厂 "
            f"[0, 2] 放行）、区间端点 {K32_UPPER_BOUND}/"
            f"{K32_LOWER_BOUND} 放行、越界点 "
            f"{K32_OUT_OF_RANGE[0]}/{K32_OUT_OF_RANGE[1]} 均 "
            f"400 且错误体指明参数名与区间；msg 协议 temperature="
            f"{K32_MSG_LEGAL_VALUE}/{K32_MSG_LOWER_BOUND} 按 "
            f"Anthropic 官方区间 [0, 1] 放行、越界点 "
            f"{K32_MSG_OUT_OF_RANGE[0]}/"
            f"{K32_MSG_OUT_OF_RANGE[1]}/{K32_MSG_OUT_OF_RANGE[2]} "
            f"均 400 且错误体指明参数名与区间——网关按协议语义分"
            f"别校验，参数校验整改达标"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p2
    def test_top_logprobs_stable_support(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K33 [P2]: 客户问题 - top_logprobs=5 放行核验
        （未开 logprobs 也接受，chat+msg 双协议）

        客户问题（工单 P2 A-04 · top_logprobs=5 被拒，参数校
        验）：官方行为不变——top_logprobs=5 官方 HTTP 200 接受
        （未开 logprobs 时也接受）；贵方最新实测（A-04，
        2026-11-03）chat 三发 top_logprobs=5 单独出现（无
        logprobs）全部 HTTP 400，错误体「top_logprobs is
        only allowed when logprobs is enabled」
        (top_logprobs_requires_logprobs)——对未开 logprobs 的
        top_logprobs 额外拒绝。整改建议（即预期结果）：按官方
        行为处理 top_logprobs（未开 logprobs 时也接受），不额
        外拒绝；若上游确实不支持，错误体应说明能力缺失而非参
        数非法，避免客户端反复重试。用户判定口径（2026-11-06）：
        top_logprobs=5 不要拒绝、按官方 HTTP 200 即可；正文为
        空不判定失败（R-03 轮移除，仅保留 A-04 请求——用户指
        定 2026-11-06）。
        双协议覆盖（chat + msg——K31 起用例须验证
        /v1/chat/completions 与 /v1/messages 双协议，用户指定）：
        1. chat 协议——
           a. 工单 A-04 三发复现（缺陷复现轮）：top_logprobs=5
              单独出现（无 logprobs 字段）、content="只回复:好"、
              max_tokens=32——请求体按工单原样（字段序
              model/messages/max_tokens/top_logprobs，工单未带
              stream——不传）→ HTTP 200（未开 logprobs 也接受，
              与官方一致；400 即额外拒绝缺陷复现——A-04 形态
              「top_logprobs is only allowed when logprobs is
              enabled」留证）+ 响应体合法 JSON 且 choices 非空；
              正文/finish_reason/logprobs 结构留观察不计判据
              （max_tokens=32 小配额下默认思考计入共享配额易
              length/空正文——K31 域形态；logprobs 未开时官方
              200 响应结构形态未采集——客户预期仅定义接受语
              义，与 K32/K35 断言收缩同理）
        2. msg 协议（/anthropic/v1/messages——该协议无 logprobs
            参数语义，Anthropic 官方未知字段应 400 拒绝）——
            a. A-04 镜像轮 3 发：top_logprobs=5 单独出现（无
               logprobs），content="只回复:好"（字符串——工单
               原样），max_tokens=512（协议必需字段套件值——工
               单 32 为 chat 小配额口径，取 512 避免 200 分支空
               正文误判）→ 硬断言统一行为：三发全 400 且错误体
               指明字段（含 "logprobs"——top_logprobs 子串覆
               盖，能力缺失/未知字段说明口径）或三发全 200；
               正文为空不判定失败（用户口径：top_logprobs=5
               不拒绝、官方 200 即可——空正文留观察，用户指
               定 2026-11-06）；混现即 FAIL
        观察记录（不计判据）：每发 finish_reason、logprobs 有
        无、usage、耗时。GLM-5.3 专用。（不进 smoke 集：新用例
        首跑观察期；P2 选测——双协议 6 发）
        """
        # K33: 工单原值——top_logprobs（A-04 轮单独出现，无
        # logprobs）
        K33_TOP_LOGPROBS = 5
        # K33: 工单 A-04 复现轮——top_logprobs 单独出现（无
        # logprobs），原样请求体（content/max_tokens 工单原值；
        # 三发依序复现）
        K33_A04_PROMPT = "只回复:好"
        K33_A04_MAX_TOKENS = 32
        K33_A04_ROUNDS = 3
        # K33: msg 协议必需字段（Anthropic 无默认值）——单 user
        # 闲聊最小合理值（A-04 镜像轮同值——工单 32 为 chat 小
        # 配额口径，取 512 避免 200 分支空正文误判）
        K33_MSG_MAX_TOKENS = 512

        test_logger.info(
            "=== 测试开始: 客户问题 - top_logprobs=5 放行核验"
            "（未开 logprobs 也接受）（工单 P2 A-04：chat 侧工单"
            "三发复现 top_logprobs=5 单独出现（无 logprobs，预期"
            "200）；msg 侧 A-04 镜像 3 发统一行为——混现即"
            " FAIL）==="
        )

        url = f"{api_client.api_prefix}/chat/completions"

        # ── 工单 A-04 三发复现（缺陷复现轮）：top_logprobs=5 单
        # 独出现（无 logprobs）——按官方行为应 200 接受，不额
        # 外拒绝 ─────────────────────────────────────────────────
        for i in range(1, K33_A04_ROUNDS + 1):
            if i > 1:
                time.sleep(3)
            tag = f"A04复现{i}/{K33_A04_ROUNDS}发"
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K33_A04_PROMPT}],
                {
                    "endpoint": "/v1/chat/completions",
                    "top_logprobs": K33_TOP_LOGPROBS,
                    "logprobs": "(A-04 工单未带——不传)",
                    "max_tokens": K33_A04_MAX_TOKENS,
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K33: 工单 A-04 原样 payload 直发（top_logprobs 单独
            # 直进 payload——工单原值原样保留；content/max_tokens
            # 工单原值；logprobs/stream 工单未带——不传）
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [
                    {"role": "user", "content": K33_A04_PROMPT}
                ],
                "max_tokens": K33_A04_MAX_TOKENS,
                "top_logprobs": K33_TOP_LOGPROBS,
            }
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{tag}] 请求发送异常（{url}）: {e}")
            elapsed = time.time() - started
            # 模型真实响应断言前打印（失败时同样可见）
            test_logger.info(
                f"[{tag}] 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, "
                f"body={response.text[:800]!r}"
            )
            # 断言1：HTTP 200（A-04 缺陷形态：三发全部 400
            # 「top_logprobs is only allowed when logprobs is
            # enabled」——对未开 logprobs 的 top_logprobs 额外
            # 拒绝；整改预期：未开 logprobs 时也接受，不额外
            # 拒绝）
            assert response.status_code == 200, (
                f"[{tag}] 缺陷复现：未开 logprobs 的 "
                f"top_logprobs={K33_TOP_LOGPROBS} 被额外拒绝——按"
                f"官方行为应 200 接受（未开 logprobs 时也接受，"
                f"不额外拒绝），实际 HTTP "
                f"{response.status_code}: {response.text[:400]}"
                f"（工单 A-04 形态：三发全部 400「top_logprobs "
                f"is only allowed when logprobs is enabled」"
                f"top_logprobs_requires_logprobs）"
            )
            # 断言2：响应体合法 JSON 且 choices 非空
            try:
                data = response.json()
            except ValueError:
                data = None
            assert data, f"[{tag}] 响应体应为合法 JSON"
            choices = data.get("choices") or []
            assert choices, f"[{tag}] 响应缺少 choices: {data!r}"
            choice = choices[0] or {}
            content = (choice.get("message") or {}).get("content") or ""
            finish_reason = choice.get("finish_reason")
            logprobs = choice.get("logprobs")
            # 正文/finish_reason/logprobs 结构留观察（不计判据）
            # ——max_tokens=32 小配额下默认思考计入共享配额
            # （R-01 未整改）易 length/空正文（K31 域形态）；
            # logprobs 未开时官方 200 响应结构形态未采集（客户
            # 预期仅定义接受语义——与 K32/K35 断言收缩同理）
            if content.strip():
                test_logger.info(
                    f"[{tag}] 观察: 正文 {len(content)} 字符、"
                    f"finish_reason={finish_reason!r}、logprobs="
                    f"{'有' if logprobs else '无'}"
                    f", elapsed={elapsed:.1f}s"
                )
            else:
                test_logger.warning(
                    f"[{tag}] 观察: 正文为空、finish_reason="
                    f"{finish_reason!r}（max_tokens=32 小配额+默"
                    f"认思考计入配额——K31 域形态，非本例判据）"
                    f", elapsed={elapsed:.1f}s"
                )
        test_logger.info(
            f"A-04 复现轮通过: {K33_A04_ROUNDS} 发 top_logprobs="
            f"{K33_TOP_LOGPROBS} 单独出现（无 logprobs）均 200——"
            f"未开 logprobs 也接受，额外拒绝缺陷未复现"
        )

        time.sleep(3)

        # ── msg 协议轮（/anthropic/v1/messages——K3 先例构造；
        # 该协议无 logprobs 参数语义，断言统一行为而非 200）──
        msg_url = f"{api_client.base_url}/anthropic/v1/messages"

        # ── msg A-04 镜像轮（3 发）：top_logprobs=5 单独出现（无
        # logprobs）——该协议无 logprobs 语义，断言统一行为（全
        # 400 指明字段或全 200——正文为空不判定失败，混现即
        # FAIL）──────────────────────────────────────────────
        a04_msg_results = []
        for i in range(1, K33_A04_ROUNDS + 1):
            if i > 1:
                time.sleep(3)
            tag = f"msgA04镜像{i}/{K33_A04_ROUNDS}发"
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K33_A04_PROMPT}],
                {
                    "endpoint": "/anthropic/v1/messages",
                    "protocol": "anthropic（x-api-key + "
                                "anthropic-version 头）",
                    "top_logprobs": K33_TOP_LOGPROBS,
                    "logprobs": "(A-04 镜像——不传)",
                    "max_tokens": K33_MSG_MAX_TOKENS,
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K33: msg A-04 镜像 payload（top_logprobs 单独直进
            # payload——被测维度与 chat A-04 一致；content 工单
            # 原样字符串；max_tokens 取套件必需字段值 512——工
            # 单 32 为 chat 小配额口径，取 512 避免 200 分支空
            # 正文误判；logprobs/stream 不传）
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "max_tokens": K33_MSG_MAX_TOKENS,
                "messages": [
                    {"role": "user", "content": K33_A04_PROMPT}
                ],
                "top_logprobs": K33_TOP_LOGPROBS,
            }
            headers: Dict[str, Any] = {
                "anthropic-version": "2023-06-01"
            }
            if api_client.api_key:
                headers["x-api-key"] = api_client.api_key
            started = time.time()
            try:
                response = api_client.session.post(
                    msg_url,
                    json=payload,
                    headers=headers,
                    timeout=api_client.timeout,
                )
            except Exception as e:
                pytest.fail(
                    f"[{tag}] 请求发送异常（{msg_url}）: {e}"
                )
            elapsed = time.time() - started
            test_logger.info(
                f"[{tag}] 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, "
                f"body={response.text[:800]!r}"
            )
            try:
                data = response.json()
            except ValueError:
                data = None
            content_arr = (data or {}).get("content") or []
            text = "".join(
                c.get("text") or ""
                for c in content_arr
                if isinstance(c, dict) and c.get("type") == "text"
            ).strip()
            a04_msg_results.append(
                (tag, response.status_code, response.text, text)
            )
        # A-04 镜像统一性断言：3 发状态码须完全一致（混现=行
        # 为不统一缺陷复现——整改要求统一行为）
        a04_statuses = {r[1] for r in a04_msg_results}
        assert len(a04_statuses) == 1, (
            f"msg 协议 A-04 镜像行为不统一: {K33_A04_ROUNDS} 发"
            f" top_logprobs 单独出现出现多种状态码 "
            f"{sorted(a04_statuses)}——整改要求统一行为；逐发: "
            f"{[(r[0], r[1]) for r in a04_msg_results]}"
        )
        if a04_msg_results[0][1] == 400:
            # 分支A：全部 400——错误体须指明字段（含 "logprobs"，
            # top_logprobs 子串覆盖——能力缺失/未知字段说明口径）
            for tag, status, body, _ in a04_msg_results:
                assert "logprobs" in body.lower(), (
                    f"[{tag}] msg 协议 A-04 镜像 400 错误体未指明"
                    f"字段 logprobs（整改建议：上游不支持时错误体"
                    f"应说明能力缺失/指明字段，避免客户端反复重"
                    f"试）: {body[:300]}"
                )
            test_logger.info(
                f"msg A-04 镜像轮通过: {K33_A04_ROUNDS} 发全部 "
                f"400 且错误体指明 logprobs 字段（能力缺失说明口"
                f"径）——统一行为达标"
            )
        else:
            # 分支B：全部 200——网关忽略该参数统一放行即达标；
            # 正文为空不判定失败（用户口径：top_logprobs=5 不
            # 拒绝、官方 200 即可——空正文留观察，用户指定
            # 2026-11-06）
            a04_empty_count = 0
            for tag, status, body, text in a04_msg_results:
                if not text:
                    a04_empty_count += 1
                    test_logger.warning(
                        f"[{tag}] 观察: 统一 200 作答但正文为空"
                        f"（不判定失败——用户口径，留观察）: "
                        f"{body[:300]}"
                    )
            test_logger.info(
                f"msg A-04 镜像轮通过: {K33_A04_ROUNDS} 发全部 "
                f"200 统一放行（其中 {a04_empty_count} 发正文为"
                f"空留观察）——统一行为达标"
            )

        test_logger.info(
            f"客户问题整改验证通过（双协议）: chat A-04 复现 "
            f"{K33_A04_ROUNDS} 发（top_logprobs 单独出现）均 200"
            f"——未开 logprobs 也接受、额外拒绝缺陷未复现；msg "
            f"A-04 镜像 {K33_A04_ROUNDS} 发统一 HTTP "
            f"{a04_msg_results[0][1]}——top_logprobs=5 不拒绝、正"
            f"文为空不判定失败（用户口径，2026-11-06）"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p2
    def test_multimodal_rejection_error_detail(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K34 [P2]: 客户问题 - 多模态媒体块该拒未拒（msg 侧静
        默丢弃返回 200）——须 400 明确拒绝（chat+msg 双协议）

        客户问题（工单 P2 R-04 补充证据 · A-01 msg 协议多模态
        静默丢弃，多模态）：
        - 官方行为：glm-5.3 为非多模态模型——请求携带图片/音
          频/视频/文档（base64 与 URL 两种载体）必须返回 400；
          返回 2xx 即不合格
        - 原始问题（贵方实测 A-01，2026-11-03 采集，5 发全
          msg 协议）：HTTP 200——该拒未拒，媒体块被静默丢弃：
          prompt_tokens 仅 17-43（媒体未进入分词器），正文自述
          『没有收到视频/音频/文档』；同一素材在 chat 协议下
          渠道返回 400——同一渠道、同一文件、两种协议两种结
          果
        - 整改建议（客户给出）：在 /v1/messages → OpenAI 转换
          层对 media block（video/audio/document）做前置校验，
          返回 400 并给出明确文案；不得剥离媒体块后继续转发；
          URL 载体（http/https 媒体链接）同样必须返回 400，
          不得自行抓取、转文字或降级为纯文本；另外 chat 协议
          也应该相同的处理
        本用例双协议各 5 发共 10 发（用户指定：message 协议和
        chat 协议都要 5 轮请求）：msg 侧 5 发请求参数与类型依
        客户原始请求依序（工单证据 A-01 全 msg——缺陷复现
        轮）；chat 侧 5 发为同素材、同提示词、同块序镜像（整
        改『chat 协议也应该相同的处理』——一致性核验轮）：
        1. document×base64（application/pdf）+『文档中的文字
           是什么?简答。』（媒体块在前——工单原序）
        2. text + audio×base64（audio/wav）『这段音频是什么
           类型的声音?简答。』（文本块在前——工单原序）
        3. video×base64（video/mp4）+『简要描述视频内容。』
        4. video×url +『简要描述视频内容。』（沿用本仓现有公
           网视频地址——MDN flower.mp4；工单原 test-videos.
           co.uk 地址不复用，用户指定保留现有 URL）
        5. video×base64（video/mp4）+『这段视频前半段的底色
           和中间显示的数字是什么？后半段的底色和中间显示的
           数字是什么？按先后顺序一句话回答。』
        chat part 映射（同素材同序镜像）：document → file part
        （file_data data URL——OpenAI chat 协议文档输入标准
        形态，内含 application/pdf）、audio → input_audio
        （format=wav）、video → video_url（base64 发用 data
        URL、URL 发用公网地址）。
        媒体数据（用户指定）：工单未提供完整 data——以代码生
        成有效 base64 数据（最小 PDF/WAV/MP4 容器，内存生成、
        不落临时文件；拒绝校验发生在媒体块类型层，不依赖可解
        码内容；msg/chat 双协议第 3/5 发共用同一生成 MP4——
        判定在类型层，内容差异不影响拒绝行为）。
        max_tokens=1024 工单原值（msg/chat 10 发同值镜像工单请
        求，豁免注入）；请求体不含 stream 字段（工单原始格
        式，两协议默认均非流式）；模型名由环境注入；thinking/
        采样参数工单未含——不传（不注入）；相邻间隔 3s。
        硬断言（每发，任一失败即 FAIL 并报告轮标签）：
        1. HTTP 400（200=媒体被静默丢弃后纯文本作答——工单
           A-01 缺陷形态（prompt_tokens 仅 17-43+正文自述未
           收到），留 body 全文证；2xx 同判；500 等=非合规拒
           绝）
        2. 错误体指明该发媒体类型——对应关键词中英任一命中
           （document/文档/pdf、audio/音频/语音、video/视频；
           大小写不敏感——20261104 Jenkins 实测整改错误体为
           中文「该模型不支持图片输入」，原纯英文关键词口径
           误判，扩展中英双语匹配（用户指定）；排除通用「模
           型服务调用失败」upstream_error 不含任何媒体类型的
           缺陷形态）
        观察记录（不计判据，留日志）：错误体是否含 "text"（官
        方行为口径——取值范围 ['text'] 痕迹）、完整错误体留
        痕。GLM-5.3 专用。（不进 smoke 集：新用例首跑观察期）
        """
        K34_ANTHROPIC_VERSION = "2023-06-01"
        # K34: max_tokens=1024——工单原始 5 发同值（msg 协议必
        # 需字段，原值原样保留豁免注入）
        K34_MAX_TOKENS = 1024
        # K34: 视频轮远端 URL——沿用本仓现有公网视频地址（test_c
        # 视频理解 C5 同款 MDN flower.mp4；用户指定保留现有
        # URL——工单原 test-videos.co.uk 地址不复用）
        K34_VIDEO_URL = (
            "https://interactive-examples.mdn.mozilla.net"
            "/media/cc0-videos/flower.mp4"
        )
        # K34: 媒体类型中英关键词组（断言2 判定口径）——任一命
        # 中即视为指明类型；20261104 Jenkins 实测贵方整改错误体
        # 为中文（「该模型不支持图片输入」），原纯英文关键词口
        # 径误判，扩展中英双语匹配（用户指定）；工单 A-01 5 发
        # 覆盖 document/audio/video——无图片轮，image 关键词组
        # 移除
        K34_MEDIA_KEYWORDS = {
            "audio": ("audio", "音频", "语音"),
            "video": ("video", "视频"),
            "document": ("document", "文档", "pdf"),
        }

        test_logger.info(
            "=== 测试开始: 客户问题 - 多模态媒体块该拒未拒应 400 "
            "明确拒绝（chat+msg 双协议各 5 发——用户指定；工单 "
            "P2 R-04 补充证据 A-01：官方要求图/音/视/文档 × "
            "base64/URL 载体必须 400，返回 2xx 即不合格；贵方 5 "
            "发全 msg 均 200——prompt_tokens 仅 17-43、正文自述"
            "未收到媒体；整改要求 chat 协议也应相同处理；msg 5 "
            "发按工单原始记录依序复现 + chat 5 发同素材同序镜像"
            "核验，媒体数据代码生成（内存生成、不落临时文件））"
            "==="
        )

        def make_mp4_b64() -> str:
            """生成最小 MP4 容器 base64——代码生成视频，无外部
            依赖（K34 双协议视频轮，工单 A-01 第 3/5 发素材；拒
            绝校验发生在媒体块类型层，不依赖可解码的视频内容；
            工单原始 data 未提供完整数据——按用户指定以代码生
            成有效 base64 数据，内存生成、不落临时文件；ftyp
            (ftyp isom 兼容 iso2/mp41)+free+mdat 最小容器骨
            架）"""
            ftyp = (
                b"\x00\x00\x00\x18ftyp"
                b"isom\x00\x00\x02\x00isomiso2mp41"
            )
            free = b"\x00\x00\x00\x08free"
            payload = bytes(range(256)) * 4
            mdat = (
                struct.pack(">I", 8 + len(payload)) + b"mdat" + payload
            )
            return base64.b64encode(ftyp + free + mdat).decode("ascii")

        def make_wav_b64() -> str:
            """生成最小 WAV（8kHz 16bit 单声道 20ms 静音段）
            base64——代码生成音频，无外部依赖（K34 音频轮）"""
            sample_rate = 8000
            num_samples = 160
            data = b"\x00\x00" * num_samples
            hdr = b"RIFF" + struct.pack(
                "<I", 36 + len(data)
            ) + b"WAVE"
            fmt = (
                b"fmt "
                + struct.pack(
                    "<IHHIIHH",
                    16,
                    1,
                    1,
                    sample_rate,
                    sample_rate * 2,
                    2,
                    16,
                )
            )
            dat = b"data" + struct.pack("<I", len(data)) + data
            return base64.b64encode(hdr + fmt + dat).decode("ascii")

        def make_pdf_b64() -> str:
            """生成最小 PDF 文档 base64——代码生成文档，无外部
            依赖（K34 msg 文档轮；类型校验在 media_type 字段
            层，不依赖可完整解析的文档内容）"""
            pdf = (
                b"%PDF-1.4\n"
                b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                b"2 0 obj<</Type/Pages/Kids[3 0 R]>>endobj\n"
                b"3 0 obj<</Type/Page/Parent 2 0 R>>endobj\n"
                b"trailer<</Root 1 0 R>>\n%%EOF\n"
            )
            return base64.b64encode(pdf).decode("ascii")

        wav_b64 = make_wav_b64()
        pdf_b64 = make_pdf_b64()
        # K34: 双协议第 3/5 发共用同一生成 MP4——拒绝判定在媒
        # 体块类型层，工单两采集数据内容差异不影响拒绝行为
        mp4_b64 = make_mp4_b64()

        def check_rejection(
            proto_tag: str,
            media_keyword: str,
            response,
            elapsed: float,
        ) -> None:
            """K34 拒绝合规性与错误体质量断言（chat+msg 双协议
            各发共用——media_keyword 为该发媒体类型，经
            K34_MEDIA_KEYWORDS 展开中英关键词组，任一命中即视
            为指明类型）"""
            body = response.text
            test_logger.info(
                f"[{proto_tag}] 真实响应: HTTP "
                f"{response.status_code}, elapsed={elapsed:.1f}s, "
                f"body={body[:800]!r}"
            )
            # 断言1：拒绝合规——HTTP 400（官方要求：非多模态模型
            # 收到媒体块（base64/URL 两种载体）必须 400，返回
            # 2xx 即不合格；200=媒体被静默丢弃后纯文本作答——工
            # 单 A-01 缺陷形态，500 等=非合规拒绝）
            assert response.status_code == 400, (
                f"[{proto_tag}] 非多模态模型对媒体块请求应 400 明"
                f"确拒绝（base64 与 URL 两种载体——官方要求返回 "
                f"2xx 即不合格），实际 HTTP "
                f"{response.status_code}: {body[:400]}"
                f"（200=媒体被静默丢弃后纯文本作答——工单 A-01 缺"
                f"陷形态：prompt_tokens 仅 17-43、正文自述未收到媒"
                f"体；500 等=非合规拒绝）"
            )
            # 断言2：错误体指明媒体类型（该轮中英关键词组任一命
            # 中，大小写不敏感——英文 lower 匹配、中文原样匹配
            # 不受 lower 影响；缺陷形态：通用「模型服务调用失
            # 败」upstream_error 不含任何媒体类型与字段）
            keywords = K34_MEDIA_KEYWORDS[media_keyword]
            assert any(k in body.lower() for k in keywords), (
                f"[{proto_tag}] 错误体未指明不支持的媒体类型与字段"
                f"（整改要求：转换层前置校验并给出明确文案，便于"
                f"客户端定位；预期关键词组 {keywords!r}——中英任"
                f"一命中即达标；缺陷形态：通用『模型服务调用失"
                f"败』upstream_error）: "
                f"{body[:300]}"
            )
            # 观察记录：官方行为口径的取值范围痕迹（['text']）
            if "text" in body.lower():
                test_logger.info(
                    f"[{proto_tag}] 错误体含取值范围痕迹 'text'（官方"
                    f"行为口径 ['text']——增强信息）"
                )
            else:
                test_logger.warning(
                    f"[{proto_tag}] 错误体未含取值范围痕迹 'text'（官"
                    f"方行为口径——观察记录，不计判据）"
                )

        msg_url = f"{api_client.base_url}/anthropic/v1/messages"
        msg_headers: Dict[str, Any] = {
            "anthropic-version": K34_ANTHROPIC_VERSION
        }
        if api_client.api_key:
            msg_headers["x-api-key"] = api_client.api_key

        def send_msg(tag: str, payload: Dict[str, Any]):
            """K34 msg 协议单发直发（Anthropic 头——K3 先例；工
            单原始请求格式：max_tokens/messages/model，不含
            stream 字段——msg 协议默认非流式）"""
            TestLogger.log_request(
                test_logger,
                [
                    {
                        "role": "user",
                        "content": f"[媒体块 + 文本]（{tag}）",
                    }
                ],
                {
                    "endpoint": "/anthropic/v1/messages",
                    "protocol": "anthropic（x-api-key + "
                                "anthropic-version 头）",
                    "round": tag,
                    "max_tokens": K34_MAX_TOKENS,
                    "stream": "(工单原始未含 stream 字段——非流式)",
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            started = time.time()
            try:
                response = api_client.session.post(
                    msg_url,
                    json=payload,
                    headers=msg_headers,
                    timeout=api_client.timeout,
                )
            except Exception as e:
                pytest.fail(
                    f"[{tag}] 请求发送异常（{msg_url}）: {e}"
                )
            return response, time.time() - started

        chat_url = f"{api_client.api_prefix}/chat/completions"

        def send_chat(tag: str, payload: Dict[str, Any]):
            """K34 chat 协议单发直发（工单请求的 chat 协议镜像
            ——整改要求 chat 协议也应相同处理，一致性核验轮；
            镜像工单请求格式：不含 stream 字段——chat 协议默认
            非流式）"""
            TestLogger.log_request(
                test_logger,
                [
                    {
                        "role": "user",
                        "content": f"[媒体 part + 文本]（{tag}）",
                    }
                ],
                {
                    "endpoint": "/v1/chat/completions",
                    "round": tag,
                    "max_tokens": K34_MAX_TOKENS,
                    "stream": "(工单原始未含 stream 字段——非流式)",
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    chat_url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(
                    f"[{tag}] 请求发送异常（{chat_url}）: {e}"
                )
            return response, time.time() - started

        def text_block(text: str) -> Dict[str, Any]:
            """工单各发原文本块（msg 文本块/chat text part 同形
            ——提示词原样保留）"""
            return {"type": "text", "text": text}

        # K34: 工单 A-01 原始记录 5 发依序复现（全 msg 协议；用
        # 户指定——5 发请求参数与类型按客户原始请求依序，媒体块
        # 与文本块顺序按工单原样：第 1 发媒体块在前、第 2 发文
        # 本块在前）；每发 = （轮标签, 媒体类型键
        # （K34_MEDIA_KEYWORDS 映射键）, payload——工单原始格
        # 式：max_tokens/messages/model，不含 stream 字段）
        msg_rounds = [
            (
                "msg/document×base64",
                "document",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": (
                                            "application/pdf"
                                        ),
                                        "data": pdf_b64,
                                    },
                                },
                                text_block(
                                    "文档中的文字是什么?简答。"
                                ),
                            ],
                        }
                    ],
                },
            ),
            (
                "msg/audio×base64",
                "audio",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                text_block(
                                    "这段音频是什么类型的声音?简答。"
                                ),
                                {
                                    "type": "audio",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "audio/wav",
                                        "data": wav_b64,
                                    },
                                },
                            ],
                        }
                    ],
                },
            ),
            (
                "msg/video×base64",
                "video",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "video",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "video/mp4",
                                        "data": mp4_b64,
                                    },
                                },
                                text_block("简要描述视频内容。"),
                            ],
                        }
                    ],
                },
            ),
            (
                "msg/video×url",
                "video",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "video",
                                    "source": {
                                        "type": "url",
                                        "url": K34_VIDEO_URL,
                                    },
                                },
                                text_block("简要描述视频内容。"),
                            ],
                        }
                    ],
                },
            ),
            (
                "msg/video×base64(2)",
                "video",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "video",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "video/mp4",
                                        "data": mp4_b64,
                                    },
                                },
                                text_block(
                                    "这段视频前半段的底色和中间显示的"
                                    "数字是什么？后半段的底色和中间显示"
                                    "的数字是什么？按先后顺序一句话回"
                                    "答。"
                                ),
                            ],
                        }
                    ],
                },
            ),
        ]

        # K34: chat 协议 5 发——同素材、同提示词、同块序的工单
        # 镜像（整改『chat 协议也应该相同的处理』——一致性核
        # 验轮；用户指定：message 协议和 chat 协议都要 5 轮请
        # 求）；part 映射：document → file part（file_data data
        # URL——OpenAI chat 协议文档输入标准形态，内含
        # application/pdf）、audio → input_audio（format=wav）、
        # video → video_url（base64 发用 data URL、URL 发用公
        # 网地址）；每发 = （轮标签, 媒体类型键（K34_MEDIA_
        # KEYWORDS 映射键）, payload——镜像工单请求格式：
        # max_tokens/messages/model，不含 stream 字段）
        chat_rounds = [
            (
                "chat/document×base64",
                "document",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "file",
                                    "file": {
                                        "file_data": (
                                            "data:application/pdf"
                                            f";base64,{pdf_b64}"
                                        ),
                                    },
                                },
                                text_block(
                                    "文档中的文字是什么?简答。"
                                ),
                            ],
                        }
                    ],
                },
            ),
            (
                "chat/audio×base64",
                "audio",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                text_block(
                                    "这段音频是什么类型的声音?简答。"
                                ),
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": wav_b64,
                                        "format": "wav",
                                    },
                                },
                            ],
                        }
                    ],
                },
            ),
            (
                "chat/video×base64",
                "video",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "video_url",
                                    "video_url": {
                                        "url": (
                                            "data:video/mp4"
                                            f";base64,{mp4_b64}"
                                        ),
                                    },
                                },
                                text_block("简要描述视频内容。"),
                            ],
                        }
                    ],
                },
            ),
            (
                "chat/video×url",
                "video",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "video_url",
                                    "video_url": {
                                        "url": K34_VIDEO_URL
                                    },
                                },
                                text_block("简要描述视频内容。"),
                            ],
                        }
                    ],
                },
            ),
            (
                "chat/video×base64(2)",
                "video",
                {
                    "model": api_client.model_name,
                    "max_tokens": K34_MAX_TOKENS,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "video_url",
                                    "video_url": {
                                        "url": (
                                            "data:video/mp4"
                                            f";base64,{mp4_b64}"
                                        ),
                                    },
                                },
                                text_block(
                                    "这段视频前半段的底色和中间显示的"
                                    "数字是什么？后半段的底色和中间显示"
                                    "的数字是什么？按先后顺序一句话回"
                                    "答。"
                                ),
                            ],
                        }
                    ],
                },
            ),
        ]
        total_rounds = len(msg_rounds) + len(chat_rounds)

        total = 0
        for label, keyword, payload in msg_rounds:
            if total:
                time.sleep(3)
            total += 1
            round_tag = f"{label} 第{total}/{total_rounds} 发"
            response, elapsed = send_msg(round_tag, payload)
            check_rejection(round_tag, keyword, response, elapsed)
        for label, keyword, payload in chat_rounds:
            if total:
                time.sleep(3)
            total += 1
            round_tag = f"{label} 第{total}/{total_rounds} 发"
            response, elapsed = send_chat(round_tag, payload)
            check_rejection(round_tag, keyword, response, elapsed)
        test_logger.info(
            f"客户问题整改验证通过: {total} 发（msg 5 发按工单 "
            f"A-01 原始口径依序复现 + chat 5 发同素材同序镜像——"
            f"双协议一致性核验，用户指定双协议各 5 发）全部 HTTP "
            f"400 合规拒绝，且错误体均指明对应媒体类型（中英关键"
            f"词任一命中）——媒体块静默丢弃（200 + prompt_tokens "
            f"仅 17-43）缺陷未复现，转换层前置校验整改双协议达标"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p1
    def test_enable_thinking_param_rejection(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K35 [P1]: 客户问题 - 关闭思考应按原厂 400 拒绝
        （enable_thinking=false 与 thinking.type=disabled 双路径，
        chat+msg 双协议）

        客户问题（工单 P1 R-07 补充证据 A-02 · chat/msg 协议关
        闭思考的请求被放行，接口协议）：
        - 官方行为：原厂对关闭思考返回 400（原厂 HTTP 400）
        - 贵方实测（A-02，2026-11-03 采集，2 发均 HTTP 200）：
          渠道返回 200 并正常出文——chat 发 enable_thinking=
          false 放行且响应带 reasoning_content（思考仍开启，
          reasoning_tokens=91）；msg 发 thinking.type=disabled
          放行且 content 带 thinking 块（思考仍开启）；对照记
          为 http_status 400→200（HTTP 状态语义）
        - 预期行为（整改）：统一关闭思考的拒绝口径——
          enable_thinking=false 与 thinking.type=disabled 两条
          路径均按原厂返回 400；不得一条拒一条放
        本用例按客户原始请求 A-02 依序复现（用户指定——两条
        路径都要按官方行为返回 400，覆盖两种协议）：
        1. 路径1 chat 协议：/v1/chat/completions 非流式请求带
           enable_thinking=false（工单原样：content="23+19 等
           于多少？"、max_tokens=512、请求体不含 stream 字
           段）→ 应 HTTP 400
        2. 路径2 msg 协议：/anthropic/v1/messages（x-api-key +
           anthropic-version 头，K3 先例）非流式请求带
           thinking={"type": "disabled"}（工单原样：
           content="23+19=?"、max_tokens=512、stream=false 显
           式携带——工单原始格式）→ 应 HTTP 400
        硬断言（每路径，任一失败即 FAIL 并报告协议与路径——
        不得一条拒一条放）：
        1. HTTP 400（200=放行缺陷复现——A-02 形态：200 且正
           常出文（思考仍开启——reasoning_content/thinking
           块）；500 等=非合规拒绝）
        观察记录（不计判据，留日志）：错误体是否含参数名（路
        径1 enable_thinking / 路径2 thinking——官方拒绝文案常
        含参数名，客户端可据此定位；通用「模型服务调用失
        败」不含参数名）、完整错误体留痕。
        max_tokens=512 工单 2 发同值（豁免注入）；提示词与请
        求体按工单原样（msg 侧 content 为字符串——工单原始格
        式；两发提示词不同——工单原样）；采样参数工单未含
        ——不传（不注入）；相邻间隔 3s。模型名由环境注入。
        GLM-5.3 专用。（不进 smoke 集：新用例首跑观察期）
        """
        # K35: 工单 A-02 两发同值 max_tokens=512（原值原样保留
        # 豁免注入；chat 侧工单原样携带，msg 侧协议必需字段）
        K35_MAX_TOKENS = 512
        # K35: 工单 A-02 原始提示词（两发不同——工单原样逐字保
        # 留，含 chat 发全角问号/msg 发 ASCII 形态）
        K35_CHAT_PROMPT = "23+19 等于多少？"
        K35_MSG_PROMPT = "23+19=?"

        test_logger.info(
            "=== 测试开始: 客户问题 - 关闭思考应按原厂 400 拒绝"
            "（工单 P1 R-07 补充证据 A-02：官方原厂对关闭思考返回 "
            "400；贵方实测 chat enable_thinking=false 与 msg "
            "thinking.type=disabled 两发均 200 正常出文——http_"
            "status 400→200；统一关闭思考拒绝口径，不得一条拒一条"
            "放；chat + msg 双协议各 1 发按工单原始请求复现；判据："
            "每路径 HTTP 400）==="
        )

        def check_rejection(
            proto_tag: str, param_name: str, response, elapsed: float
        ) -> None:
            """K35 关闭思考拒绝一致性断言（双协议两路径共用——
            param_name 为该路径参数名，仅作错误体观察痕迹）"""
            body = response.text
            test_logger.info(
                f"[{proto_tag}] 真实响应: HTTP "
                f"{response.status_code}, elapsed={elapsed:.1f}s, "
                f"body={body[:800]!r}"
            )
            # 断言1：统一关闭思考拒绝口径——HTTP 400（官方：原
            # 厂对关闭思考返回 400；200=放行缺陷复现——A-02 形
            # 态：200 且正常出文（思考仍开启——reasoning_
            # content/thinking 块）；500 等=非合规拒绝；不得一
            # 条拒一条放）
            assert response.status_code == 400, (
                f"[{proto_tag}] 官方（原厂）对关闭思考返回 400——"
                f"统一关闭思考拒绝口径（不得一条拒一条放），实际 "
                f"HTTP {response.status_code}: {body[:400]}"
                f"（200=放行缺陷复现——工单 A-02 形态：200 且正常"
                f"出文、思考仍开启（reasoning_content/thinking 块）"
                f"；500 等=非合规拒绝）"
            )
            # 观察记录：错误体参数名痕迹（官方拒绝文案常含参数
            # 名——客户端可据此定位；通用「模型服务调用失败」
            # upstream_error 不含参数名；不计判据）
            if param_name in body.lower():
                test_logger.info(
                    f"[{proto_tag}] 错误体含参数名痕迹 "
                    f"'{param_name}'（增强信息，不计判据）"
                )
            else:
                test_logger.warning(
                    f"[{proto_tag}] 错误体未含参数名痕迹 "
                    f"'{param_name}'（观察记录，不计判据）"
                )

        # ── 路径1 chat 协议：/v1/chat/completions +
        # enable_thinking=false（工单 A-02 第 1 发原样）──
        chat_url = f"{api_client.api_prefix}/chat/completions"
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K35_CHAT_PROMPT}],
            {
                "endpoint": "/v1/chat/completions",
                "enable_thinking": False,
                "max_tokens": K35_MAX_TOKENS,
                "stream": "(工单原始未含 stream 字段——非流式)",
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )
        # K35: 手工 payload 直发（工单 A-02 原始格式：messages/
        # max_tokens/enable_thinking/model，不含 stream 字段——
        # 工单原样；采样参数未含——不传不注入）
        chat_payload: Dict[str, Any] = {
            "messages": [
                {"role": "user", "content": K35_CHAT_PROMPT}
            ],
            "max_tokens": K35_MAX_TOKENS,
            "enable_thinking": False,
            "model": api_client.model_name,
        }
        started = time.time()
        try:
            response = api_client._post_with_retry(
                chat_url, chat_payload, stream=False
            )
        except Exception as e:
            pytest.fail(
                f"[chat] 请求发送异常（{chat_url}）: {e}"
            )
        check_rejection(
            "chat·enable_thinking=false",
            "enable_thinking",
            response,
            time.time() - started,
        )

        time.sleep(3)

        # ── 路径2 msg 协议：/anthropic/v1/messages +
        # thinking.type=disabled（工单 A-02 第 2 发原样）──
        msg_url = f"{api_client.base_url}/anthropic/v1/messages"
        msg_headers: Dict[str, Any] = {
            "anthropic-version": "2023-06-01"
        }
        if api_client.api_key:
            msg_headers["x-api-key"] = api_client.api_key
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K35_MSG_PROMPT}],
            {
                "endpoint": "/anthropic/v1/messages",
                "protocol": "anthropic（x-api-key + "
                            "anthropic-version 头）",
                "thinking.type": "disabled",
                "max_tokens": K35_MAX_TOKENS,
                "stream": False,
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )
        # K35: msg 协议手工 payload 直发（工单 A-02 原始格式：
        # messages/max_tokens/thinking/model/stream——content 为
        # 字符串、stream=false 显式携带，均工单原样）
        msg_payload: Dict[str, Any] = {
            "messages": [
                {"role": "user", "content": K35_MSG_PROMPT}
            ],
            "max_tokens": K35_MAX_TOKENS,
            "thinking": {"type": "disabled"},
            "model": api_client.model_name,
            "stream": False,
        }
        started = time.time()
        try:
            response = api_client.session.post(
                msg_url,
                json=msg_payload,
                headers=msg_headers,
                timeout=api_client.timeout,
            )
        except Exception as e:
            pytest.fail(
                f"[msg] 请求发送异常（{msg_url}）: {e}"
            )
        check_rejection(
            "msg·thinking.type=disabled",
            "thinking",
            response,
            time.time() - started,
        )
        test_logger.info(
            "客户问题整改验证通过: chat（enable_thinking=false）与 "
            "msg（thinking.type=disabled）两路径均按原厂 HTTP 400 拒"
            "绝——统一关闭思考拒绝口径落地（不得一条拒一条放），放"
            "行（200 正常出文）缺陷未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p1
    def test_finish_reason_stop_semantics(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K36 [P1]: 客户问题 - finish_reason 判定对齐官方（stop
        语义——流式/多段/结构化）

        客户问题（工单 P1 R-06 · finish_reason 语义与官方不一致，
        接口协议）：
        - 官方行为：finish_reason=stop（20_chat_stream_002 /
          20_chat_ms_001 / 20_chat_structured_002 三例）
        - 贵方实测：同一请求渠道返回 finish_reason=length，官方
          返回 stop（三例一致复现）
        - 整改建议：对齐 finish_reason 判定——思考 token 不应把
          正常结束的请求判成 length 截断
        本用例按官方行为进行预期断言（用户指定），覆盖三种请求形
        态（工单三例）× 双协议（chat + msg——K31 起用例须验证双
        协议，用户指定）：
        1. 流式：chat SSE（choices[].finish_reason + delta.content）
           / msg SSE（message_delta.delta.stop_reason +
           content_block_delta.text）
        2. 多段：单条 user 消息 content 数组多段文本（工单
           20_chat_ms_001 的"多段"请求形态）
        3. 结构化：chat response_format=json_object / msg 无该参
           数按 K31 先例 prompt 引导 JSON
        硬断言（每形态 × 每协议，任一失败即 FAIL 并报告协议与形
        态）：
        1. 终止语义对齐官方：chat finish_reason == "stop" /
           msg stop_reason == "end_turn"（Anthropic 协议的自然
           结束语义——msg 侧的 stop 等价；length/max_tokens=缺
           陷复现：思考 token 计入判定把正常结束的请求误判截断
           ——工单三例一致形态）
        2. 正文非空（正常结束的佐证——正文空+length 为思考耗光
           配额的 K31 形态，非本例"正常结束误判"口径）
        max_tokens=512（工单三例未附原始 payload——取适中值：单
        句/短 JSON 正文远低于配额（官方自然结束 stop），默认档
        思考 token 常达数百，计入判定的实现易触顶误判 length，
        对判定语义敏感且不致正文真实截断）；thinking/采样参数工
        单未指定——不传（不注入）；相邻间隔 3s。模型名由环境注
        入。GLM-5.3 专用。（不进 smoke 集：新用例首跑观察期）
        """
        # K36: 三例未附原始 payload——max_tokens 取适中值（见方
        # 法 docstring 设计决策）
        K36_MAX_TOKENS = 512
        # K36: 流式/非流式共用闲聊任务（单句正文，远低于配额）
        K36_STREAM_PROMPT = "请用一句话介绍你自己。"
        # K36: 多段——单条 user 消息 content 数组多段文本
        K36_SEGMENTS = (
            "第一段：我的名字是小明。",
            "第二段：我今年十八岁。",
            "第三段：请用一句话复述我的名字和年龄。",
        )
        # K36: 结构化——json_object 引导（chat 侧 response_format
        # 参数；msg 侧无该参数按 K31 先例 prompt 引导）
        K36_JSON_PROMPT = (
            "请输出一个 JSON 对象，包含 name 和 version 两个字段，"
            "值可以任意。"
        )

        test_logger.info(
            "=== 测试开始: 客户问题 - finish_reason 判定对齐官方"
            "（工单 P1 R-06：官方 stop/贵方 length 三例一致复现——"
            "思考 token 不应把正常结束的请求判成截断；流式/多段/结"
            "构化 × chat+msg 双协议；判据：stop/end_turn+正文非"
            "空）==="
        )

        chat_url = f"{api_client.api_prefix}/chat/completions"
        msg_url = f"{api_client.base_url}/anthropic/v1/messages"
        msg_headers: Dict[str, Any] = {"anthropic-version": "2023-06-01"}
        if api_client.api_key:
            msg_headers["x-api-key"] = api_client.api_key

        def check_chat(
            type_tag: str, finish: Any, content: str, elapsed: float
        ) -> None:
            """K36 chat 协议终止语义断言（三种请求形态共用）"""
            test_logger.info(
                f"[chat-{type_tag}] finish={finish!r}, 正文 "
                f"{len(content.strip())} 字符, elapsed={elapsed:.1f}s"
            )
            # 断言1：正文非空（正常结束的佐证——正文空+length
            # 为思考耗光配额的 K31 形态，混入时以断言1先行报告）
            assert content.strip(), (
                f"[chat-{type_tag}] 正文为空——正常结束无从谈起"
                f"（思考耗光配额的 K31 形态归属 K31，本例判据为"
                f"『正常结束被误判截断』；finish={finish!r}）"
            )
            # 断言2：终止语义对齐官方——finish_reason == stop
            # （length=缺陷复现：思考 token 计入判定把正常结束
            # 的请求误判截断，工单三例一致形态）
            assert finish == "stop", (
                f"[chat-{type_tag}] finish_reason 应对齐官方为 "
                f"stop，实际 {finish!r}（工单 P1 R-06：官方返回 "
                f"stop、贵方实测 length 三例一致复现——思考 token "
                f"不应把正常结束的请求判成 length 截断；正文 "
                f"{len(content.strip())} 字符已正常产出，属误判"
                f"截断形态）"
            )

        def check_msg(
            type_tag: str, stop_reason: Any, text: str,
            elapsed: float
        ) -> None:
            """K36 msg 协议终止语义断言（三种请求形态共用）"""
            test_logger.info(
                f"[msg-{type_tag}] stop_reason={stop_reason!r}, "
                f"正文 {len(text.strip())} 字符, "
                f"elapsed={elapsed:.1f}s"
            )
            # 断言1：正文非空（口径同 chat 侧）
            assert text.strip(), (
                f"[msg-{type_tag}] 正文为空——正常结束无从谈起"
                f"（思考耗光配额的 K31 形态归属 K31，本例判据为"
                f"『正常结束被误判截断』；stop_reason="
                f"{stop_reason!r}）"
            )
            # 断言2：终止语义对齐官方——stop_reason == end_turn
            # （Anthropic 协议的自然结束语义，msg 侧的 stop 等
            # 价；max_tokens=缺陷复现，口径同 chat 侧 length）
            assert stop_reason == "end_turn", (
                f"[msg-{type_tag}] stop_reason 应对齐官方为 "
                f"end_turn，实际 {stop_reason!r}（msg 侧的 "
                f"stop 等价语义；max_tokens=思考 token 计入判"
                f"定把正常结束的请求误判截断——工单 P1 R-06 对"
                f"齐口径；正文 {len(text.strip())} 字符已正常产"
                f"出，属误判截断形态）"
            )

        # ── chat 协议 ──

        # 第 1 轮：流式（K24 send_raw_stream 先例——SSE 收集
        # finish_reason 与正文增量）
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K36_STREAM_PROMPT}],
            {
                "endpoint": "/v1/chat/completions",
                "stream": True,
                "max_tokens": K36_MAX_TOKENS,
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )
        chat_stream_payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "messages": [
                {"role": "user", "content": K36_STREAM_PROMPT}
            ],
            "max_tokens": K36_MAX_TOKENS,
            "stream": True,
        }
        started = time.time()
        try:
            response_s = api_client.session.post(
                chat_url,
                json=chat_stream_payload,
                timeout=api_client.timeout,
                stream=True,
            )
        except Exception as e:
            pytest.fail(f"[chat-流式] 请求发送异常（{chat_url}）: {e}")
        if response_s.status_code != 200:
            pytest.fail(
                f"[chat-流式] 应正常响应 HTTP 200，实际 "
                f"{response_s.status_code}: "
                f"{response_s.text[:400]!r}"
            )
        content_parts: List[str] = []
        finish_s: Any = None
        for line in response_s.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            if delta.get("content"):
                content_parts.append(delta["content"])
            if choices[0].get("finish_reason"):
                finish_s = choices[0]["finish_reason"]
        check_chat(
            "流式", finish_s, "".join(content_parts),
            time.time() - started,
        )

        time.sleep(3)

        # 第 2 轮：多段（content 数组多段文本）
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K36_SEGMENTS}],
            {
                "endpoint": "/v1/chat/completions",
                "stream": False,
                "content 形态": "数组多段文本（3 段）",
                "max_tokens": K36_MAX_TOKENS,
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )
        chat_seg_payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": seg}
                        for seg in K36_SEGMENTS
                    ],
                }
            ],
            "max_tokens": K36_MAX_TOKENS,
            "stream": False,
        }
        started = time.time()
        try:
            response = api_client._post_with_retry(
                chat_url, chat_seg_payload, stream=False
            )
        except Exception as e:
            pytest.fail(f"[chat-多段] 请求发送异常（{chat_url}）: {e}")
        if response.status_code != 200:
            pytest.fail(
                f"[chat-多段] 应正常响应 HTTP 200，实际 "
                f"{response.status_code}: {response.text[:400]!r}"
            )
        data = response.json()
        test_logger.info(
            f"[chat-多段] 真实响应: HTTP 200, "
            f"finish={data.get('choices', [{}])[0].get('finish_reason')!r}"
            f", body={response.text[:800]!r}"
        )
        check_chat(
            "多段",
            (data.get("choices") or [{}])[0].get("finish_reason"),
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content")
            or "",
            time.time() - started,
        )

        time.sleep(3)

        # 第 3 轮：结构化（response_format=json_object）
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K36_JSON_PROMPT}],
            {
                "endpoint": "/v1/chat/completions",
                "stream": False,
                "response_format": {"type": "json_object"},
                "max_tokens": K36_MAX_TOKENS,
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )
        chat_json_payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "messages": [
                {"role": "user", "content": K36_JSON_PROMPT}
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": K36_MAX_TOKENS,
            "stream": False,
        }
        started = time.time()
        try:
            response = api_client._post_with_retry(
                chat_url, chat_json_payload, stream=False
            )
        except Exception as e:
            pytest.fail(
                f"[chat-结构化] 请求发送异常（{chat_url}）: {e}"
            )
        if response.status_code != 200:
            pytest.fail(
                f"[chat-结构化] 应正常响应 HTTP 200，实际 "
                f"{response.status_code}: {response.text[:400]!r}"
            )
        data = response.json()
        test_logger.info(
            f"[chat-结构化] 真实响应: HTTP 200, "
            f"finish={data.get('choices', [{}])[0].get('finish_reason')!r}"
            f", body={response.text[:800]!r}"
        )
        check_chat(
            "结构化",
            (data.get("choices") or [{}])[0].get("finish_reason"),
            (data.get("choices") or [{}])[0]
            .get("message", {})
            .get("content")
            or "",
            time.time() - started,
        )

        time.sleep(3)

        # ── msg 协议（x-api-key + anthropic-version 头——K3 先例）──

        # 第 4 轮：流式（K3 anthropic_stream_request 先例——SSE
        # 收集 message_delta.stop_reason 与 content_block_delta 正文）
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K36_STREAM_PROMPT}],
            {
                "endpoint": "/anthropic/v1/messages",
                "protocol": "anthropic（x-api-key + "
                            "anthropic-version 头）",
                "stream": True,
                "max_tokens": K36_MAX_TOKENS,
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )
        msg_stream_payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "max_tokens": K36_MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": K36_STREAM_PROMPT,
                        }
                    ],
                }
            ],
            "stream": True,
        }
        started = time.time()
        try:
            response_s = api_client.session.post(
                msg_url,
                json=msg_stream_payload,
                headers=msg_headers,
                timeout=api_client.timeout,
                stream=True,
            )
        except Exception as e:
            pytest.fail(f"[msg-流式] 请求发送异常（{msg_url}）: {e}")
        if response_s.status_code != 200:
            pytest.fail(
                f"[msg-流式] 应正常响应 HTTP 200，实际 "
                f"{response_s.status_code}: "
                f"{response_s.text[:400]!r}"
            )
        text_parts: List[str] = []
        stop_reason_s: Any = None
        events = 0
        for line in response_s.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            events += 1
            evt_type = event.get("type")
            if evt_type == "content_block_delta":
                d = event.get("delta") or {}
                if d.get("type") == "text_delta" and d.get("text"):
                    text_parts.append(d["text"])
            elif evt_type == "message_delta":
                d = event.get("delta") or {}
                if d.get("stop_reason"):
                    stop_reason_s = d["stop_reason"]
        if events == 0:
            pytest.fail(f"[msg-流式] 未返回任何 SSE 事件（{msg_url}）")
        check_msg(
            "流式", stop_reason_s, "".join(text_parts),
            time.time() - started,
        )

        time.sleep(3)

        # 第 5 轮：多段（content 数组多段 text 块）
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K36_SEGMENTS}],
            {
                "endpoint": "/anthropic/v1/messages",
                "protocol": "anthropic（x-api-key + "
                            "anthropic-version 头）",
                "stream": False,
                "content 形态": "数组多段文本（3 段）",
                "max_tokens": K36_MAX_TOKENS,
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )
        msg_seg_payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "max_tokens": K36_MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": seg}
                        for seg in K36_SEGMENTS
                    ],
                }
            ],
            "stream": False,
        }
        started = time.time()
        try:
            response = api_client.session.post(
                msg_url,
                json=msg_seg_payload,
                headers=msg_headers,
                timeout=api_client.timeout,
            )
        except Exception as e:
            pytest.fail(f"[msg-多段] 请求发送异常（{msg_url}）: {e}")
        if response.status_code != 200:
            pytest.fail(
                f"[msg-多段] 应正常响应 HTTP 200，实际 "
                f"{response.status_code}: {response.text[:400]!r}"
            )
        data = response.json()
        test_logger.info(
            f"[msg-多段] 真实响应: HTTP 200, "
            f"stop_reason={data.get('stop_reason')!r}, "
            f"body={response.text[:800]!r}"
        )
        check_msg(
            "多段",
            data.get("stop_reason"),
            "".join(
                c.get("text") or ""
                for c in (data.get("content") or [])
                if isinstance(c, dict) and c.get("type") == "text"
            ),
            time.time() - started,
        )

        time.sleep(3)

        # 第 6 轮：结构化（msg 无 json_object 参数——K31 先例
        # prompt 引导 JSON）
        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K36_JSON_PROMPT}],
            {
                "endpoint": "/anthropic/v1/messages",
                "protocol": "anthropic（x-api-key + "
                            "anthropic-version 头）",
                "stream": False,
                "response_format": (
                    "无该参数（K31 先例 prompt 引导 JSON）"
                ),
                "max_tokens": K36_MAX_TOKENS,
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )
        msg_json_payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "max_tokens": K36_MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": K36_JSON_PROMPT}
                    ],
                }
            ],
            "stream": False,
        }
        started = time.time()
        try:
            response = api_client.session.post(
                msg_url,
                json=msg_json_payload,
                headers=msg_headers,
                timeout=api_client.timeout,
            )
        except Exception as e:
            pytest.fail(
                f"[msg-结构化] 请求发送异常（{msg_url}）: {e}"
            )
        if response.status_code != 200:
            pytest.fail(
                f"[msg-结构化] 应正常响应 HTTP 200，实际 "
                f"{response.status_code}: {response.text[:400]!r}"
            )
        data = response.json()
        test_logger.info(
            f"[msg-结构化] 真实响应: HTTP 200, "
            f"stop_reason={data.get('stop_reason')!r}, "
            f"body={response.text[:800]!r}"
        )
        check_msg(
            "结构化",
            data.get("stop_reason"),
            "".join(
                c.get("text") or ""
                for c in (data.get("content") or [])
                if isinstance(c, dict) and c.get("type") == "text"
            ),
            time.time() - started,
        )
        test_logger.info(
            "客户问题整改验证通过: 流式/多段/结构化三种请求形态在 "
            "chat（finish_reason=stop）与 msg（stop_reason="
            "end_turn）双协议下终止语义均对齐官方，正文非空——思"
            "考 token 误判 length 截断缺陷未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    def test_n2_request_hang_timeout(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K37 [P0]: 客户问题 - n=2 请求应 400 拒绝且不挂死
        （返回提示信息）

        客户问题（工单 P0 · n=2 请求挂死：无响应直至超时，异常）：
        - 原始问题：n=2 请求无响应直至超时——参数电池 3/3 轮
          TimeoutError（已重试 1 次仍超时）、协议电池 2 例
          ReadTimeout、直连 300s 超时；挂死同时导致模块 4 的
          n=2 探针被记为『无效』而未计失败
        - 官方行为：原厂 n=2 HTTP 200（返回 1 个 choice）
        - 客户明确需求（2026-11-06，契约口径）：当 n=2 时 400
          拒绝，并返回相应的提示信息，但不能卡死；客户示例响
          应：HTTP 400 {"code":1210,"message":"参数有误：
          glm-5.3 仅支持 n=1，收到 n=2 (request id: ...)"}——
          契约优先级：客户明确需求 > 官方对齐（用户指定按新契
          约断言，替代原官方 200+单 choice 口径）
        本用例 chat 单协议 2 发对齐工单口径（055/056 两采集，
        同请求形态——两次独立采集非重试），硬断言每发：
        1. 30s 硬超时（"不能卡死"——requests timeout=30s，超
           时即 FAIL：挂死缺陷复现；工单原客户端 300s 超时拖死
           整轮的形态不得复现，超时显式计入失败——纠正工单所
           述探针被记为『无效』而未计失败的漏报形态）
        2. HTTP 400（客户新契约：n=2 明确拒绝；200 放行=FAIL
           ——未按客户契约拒绝；500 等=非合规拒绝）
        3. 返回相应的提示信息（"并返回相应的提示信息"）——
           响应体合法 JSON 且 message 非空并指明 n 参数限制
           （含 "n=1" 或 "n=2" 子串，大小写不敏感——客户示
           例：参数有误：glm-5.3 仅支持 n=1，收到 n=2）
        观察记录（不计判据）：错误码 code（如 1210——平台错误
        码口径不硬绑）、request id 痕迹、elapsed 留痕——已返
        回但总时长超 30s 的字节缓流形态留观察人工分派，不作硬
        断言避免边界抖动误报。
        工单原值原样保留：messages="说一句话。"、max_tokens=16、
        n=2（豁免注入，无全局注入口）；thinking/采样参数工单未含
        ——不传（不注入）；单发直发不重试（_post_with_retry 的
        重试会掩盖单发挂死证据并使超时等待翻倍 30s×2）；相邻间隔
        3s。chat 单协议：n 为 OpenAI 协议参数，Anthropic
        /v1/messages 无 n 参数语义——工单证据仅 chat，msg 侧对
        未知参数的行为已由 K33 分支 B（统一忽略）与 K35
        （enable_thinking 拒绝域）覆盖，补 msg 轮并入他例域、不
        构成 n>1 路径挂死的判定证据。模型名由环境注入。GLM-5.3
        专用。（不进 smoke 集：新用例首跑观察期）
        """
        # K37: 工单原值——n=2（挂死复现参数，055/056 两采集同形态）
        K37_N = 2
        # K37: 工单原值原样保留（豁免注入——工单原始请求字段）
        K37_MAX_TOKENS = 16
        # K37: 工单原值
        K37_PROMPT = "说一句话。"
        # K37: 30s 硬超时（客户新契约：n=2 应 400 拒绝但不能卡
        # 死——30s 内必须返回；客户端侧硬超时避免单例拖死整轮——
        # 工单原客户端 read timeout=300s 拖死整轮的形态不得复现）
        K37_HARD_TIMEOUT = 30
        # K37: 2 发对齐工单口径（055/056 两次独立采集，非重试）
        K37_ROUNDS = 2

        test_logger.info(
            "=== 测试开始: 客户问题 - n=2 请求应 400 拒绝且不挂死"
            "（工单 P0：贵方实测无响应直至 300s 超时、重试仍超时；"
            "客户新契约 2026-11-06：n=2 应 400 拒绝并返回提示信息"
            "（示例 code=1210 参数有误：glm-5.3 仅支持 n=1，收到 "
            "n=2）、不得卡死；chat 2 发对齐工单 055/056 口径；超时"
            "即 FAIL 挂死复现）==="
        )

        chat_url = f"{api_client.api_prefix}/chat/completions"

        for round_no in range(1, K37_ROUNDS + 1):
            if round_no > 1:
                time.sleep(3)
            round_tag = f"chat/n=2 第{round_no}/{K37_ROUNDS} 发"
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K37_PROMPT}],
                {
                    "endpoint": "/v1/chat/completions",
                    "round": f"第{round_no}/{K37_ROUNDS} 发",
                    "n": K37_N,
                    "stream": False,
                    "max_tokens": K37_MAX_TOKENS,
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K37: 工单原值原样保留（messages/max_tokens/n）——单
            # 发直发不重试，requests timeout=30s 硬超时
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": K37_PROMPT}],
                "max_tokens": K37_MAX_TOKENS,
                "n": K37_N,
                "stream": False,
            }
            started = time.time()
            try:
                response = api_client.session.post(
                    chat_url,
                    json=payload,
                    timeout=K37_HARD_TIMEOUT,
                )
            except requests.exceptions.Timeout as e:
                # 断言1：30s 硬超时——超时即挂死缺陷复现（工单形
                # 态：无响应直至超时；整改明令不得无限挂起；超时
                # 显式计入失败，纠正工单『探针被记为无效而未计
                # 失败』漏报形态）
                test_logger.error(
                    f"[{round_tag}] {K37_HARD_TIMEOUT}s 硬超时内无任何"
                    f"响应（挂死形态——请求已发出、无响应字节）: {e}"
                )
                pytest.fail(
                    f"[{round_tag}] 挂死缺陷复现——n=2 请求 "
                    f"{K37_HARD_TIMEOUT}s 内无响应（requests 超时："
                    f"{e}；工单形态：n=2 无响应直至 300s 超时、重试"
                    f"仍超时；客户新契约：n=2 应 400 拒绝并返回提示"
                    f"信息、不得卡死——客户端硬超时已按整改要求实"
                    f"施，超时如实计入失败、不拖死整轮）"
                )
            except Exception as e:
                pytest.fail(
                    f"[{round_tag}] 请求发送异常（{chat_url}）: {e}"
                )
            elapsed = time.time() - started
            body = response.text
            test_logger.info(
                f"[{round_tag}] 真实响应: HTTP "
                f"{response.status_code}, elapsed={elapsed:.1f}s, "
                f"body={body[:800]!r}"
            )
            # 断言1（补充留痕）：已返回但总时长超 30s 的字节缓流
            # 形态——观察记录交人工分派（requests 读超时按字节间
            # 隔计时，非总时长），不作硬断言避免边界抖动误报
            if elapsed > K37_HARD_TIMEOUT:
                test_logger.warning(
                    f"[{round_tag}] 已返回但总耗时 {elapsed:.1f}s 超 "
                    f"{K37_HARD_TIMEOUT}s（字节缓流未触发读超时——"
                    f"罕见形态，留观察人工分派）"
                )
            # 断言2：客户新契约（2026-11-06）——n=2 应 HTTP 400
            # 拒绝（200 放行=未按客户契约拒绝；500 等=非合规拒
            # 绝）——客户明确需求优先于官方对齐（官方虽 200+1
            # choice，用户指定按新契约断言）
            assert response.status_code == 400, (
                f"[{round_tag}] 客户契约：n=2 应 HTTP 400 拒绝并返回"
                f"提示信息（示例：参数有误：glm-5.3 仅支持 n=1，收"
                f"到 n=2），实际 HTTP {response.status_code}: "
                f"{body[:400]}"
                f"（200 放行=未按客户契约拒绝——官方虽 200+1 "
                f"choice，客户明确需求为 400 拒绝（2026-11-06 起"
                f"按新契约断言）；500 等=非合规拒绝——均 FAIL）"
            )
            # 断言3：返回相应的提示信息（"并返回相应的提示信
            # 息"）——响应体合法 JSON、message 非空且指明 n 参数
            # 限制（含 "n=1"/"n=2" 子串，大小写不敏感；客户示例
            # 形态：{"code":1210,"message":"参数有误：glm-5.3
            # 仅支持 n=1，收到 n=2 (request id: ...)"}）
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                msg_text = data.get("message") or ""
                err = data.get("error")
                if not msg_text and isinstance(err, dict):
                    msg_text = err.get("message") or ""
            else:
                msg_text = body
            check_text = str(msg_text).lower()
            assert str(msg_text).strip() and (
                "n=1" in check_text or "n=2" in check_text
            ), (
                f"[{round_tag}] 400 拒绝须返回相应的提示信息并指明 "
                f"n 参数限制（客户示例：参数有误：glm-5.3 仅支持 "
                f"n=1，收到 n=2），实际提示: "
                f"{str(msg_text)[:300]!r}（body: {body[:300]!r}）"
            )
            # 观察记录：错误码 code（如 1210——平台错误码口径不
            # 硬绑）、request id 痕迹、elapsed——均不计判据
            obs_code = (
                data.get("code") if isinstance(data, dict) else None
            )
            test_logger.info(
                f"[{round_tag}] 400 拒绝核验: code={obs_code!r}, "
                f"提示信息 {len(str(msg_text))} 字符"
                f"（request id 痕迹: {'request id' in check_text}"
                f"——观察不计判据）, elapsed={elapsed:.1f}s"
            )
        test_logger.info(
            f"客户问题整改验证通过: {K37_ROUNDS} 发（工单 055/056 口"
            f"径）全部在 {K37_HARD_TIMEOUT}s 硬超时内返回 HTTP 400 "
            f"拒绝且提示信息指明 n 参数限制——n=2 路径挂死（无响应"
            f"直至超时）缺陷未复现，客户新契约（400 拒绝 + 提示信"
            f"息、不卡死）达成"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p0
    @pytest.mark.skip(
        reason="K38 暂挂（用户指定 2026-11-06）：官方环境复测同形请"
        "求亦超时——工单『官方判定通过（别名按 max_tokens 语义立"
        "即截断返回）』基线失效，判定口径待澄清后恢复执行"
    )
    def test_max_completion_tokens_alias_single_token(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K38 [P0]: 客户问题 - max_completion_tokens 别名单
        token 请求不挂起（与 tokens 主路径同延迟水平）
        【暂挂 SKIP（用户指定 2026-11-06）：官方环境复测同形请
        求亦超时——官方判定基线（别名立即截断返回）失效，判定
        口径待澄清后恢复执行】

        客户问题（工单 A-A01，异常）：
        - 官方判定通过：max_completion_tokens 别名为单 token
          请求——被接受并按 max_tokens 语义立即截断返回
        - 贵方实测：客户原始请求 1 发即挂起——180s 请求超
          时、无响应（HTTP 0，采集未落盘）
        - 预期行为（整改）：不得触发 180s 级挂起；需与 tokens
          主路径同延迟水平
        本用例按原始请求与预期行为验收（用户指定），chat 单协议
        2 发（别名轮 1 发对齐工单口径 + 主路径轮 1 发延迟对照基
        线）：
        1. 别名轮（工单原样——单 user "Write a long essay
           about turbines." + max_completion_tokens=1，字段序
           model/messages/max_completion_tokens，无 stream 字
           段）：30s 硬超时（requests timeout=30s——对齐 K37
           先例，远低于工单 180s 挂起水平）内返回，超时即 FAIL
           挂起缺陷复现；单发直发不重试（重试掩盖挂起证据且
           超时等待翻倍）
        2. 别名轮 HTTP 200（官方判定通过）+ 响应体合法 JSON +
           usage.completion_tokens<=2（别名生效——单 token 截
           断；字段被丢弃则长文数百 token）
        3. 主路径轮（同 prompt，max_tokens=1 对照基线）：30s 硬
           超时内返回 + HTTP 200
        4. 同延迟水平判据（客户预期）：别名 elapsed <= 主路径
           elapsed*3+10s（宽容因子——网络抖动；挂起形态由 30s
           硬超时兜底；字节缓流形态留观察人工分派，K37 口径）
        观察记录（不计判据）：finish_reason 与正文（1 配额默认
        思考计入易空正文+length——K31 域形态，非本例判据）、两
        轮 elapsed 留痕。chat 单协议（max_completion_tokens
        为 OpenAI Chat Completions 别名字段，Anthropic
        /v1/messages 无该字段——max_tokens 即协议必需主路径字
        段，msg 未知参数行为由 K33/K35 覆盖）。模型名由环境注
        入；thinking/采样参数工单未含——不传（不注入）；相邻
        间隔 3s。GLM-5.3 专用。（不进 smoke 集：新用例首跑观
        察期）
        """
        # K38: 工单 A-A01 原样提示词（单 user 消息）
        K38_PROMPT = "Write a long essay about turbines."
        # K38: 工单原值——max_completion_tokens=1（别名字段）
        K38_MAX_COMPLETION_TOKENS = 1
        # K38: 主路径对照同值——max_tokens=1（同 prompt 同预算）
        K38_MAIN_PATH_MAX_TOKENS = 1
        # K38: 30s 硬超时（对齐 K37 先例；工单挂起形态 180s 无
        # 响应——远低于该水平即判挂起复现；单发直发不重试）
        K38_HARD_TIMEOUT = 30
        # K38: 同延迟水平宽容因子与缓冲（客户预期"与 tokens 主
        # 路径同延迟水平"——3 倍+10s 容网络抖动）
        K38_PARITY_FACTOR = 3
        K38_PARITY_BUFFER = 10

        test_logger.info(
            "=== 测试开始: 客户问题 - max_completion_tokens 别名单"
            " token 请求不挂起（工单 A-A01：官方判定通过——别名为单"
            " token 请求立即截断返回；贵方实测 1 发 180s 超时无响应；"
            "预期不挂起、与 tokens 主路径同延迟水平；chat 2 发=别名"
            "轮 1 发工单口径+主路径轮 1 发延迟对照；30s 硬超时，超"
            "时即 FAIL 挂起复现）==="
        )

        chat_url = f"{api_client.api_prefix}/chat/completions"

        def send_leg(
            leg_tag: str, token_field: str, token_value: int
        ) -> Dict[str, Any]:
            """K38: 单发直发（不重试——重试掩盖挂起证据且超时
            等待翻倍，K37 口径），30s 硬超时；返回 {data,
            elapsed}（超时/异常/非 200/非 JSON 即时 FAIL）"""
            TestLogger.log_request(
                test_logger,
                [{"role": "user", "content": K38_PROMPT}],
                {
                    "endpoint": "/v1/chat/completions",
                    "round": leg_tag,
                    token_field: token_value,
                    "stream": "(工单未带——不传)",
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K38: 工单原样 payload——别名轮字段序 model/messages/
            # max_completion_tokens（A-A01 原序），主路径轮同序
            # 以 max_tokens 替换（对照口径唯一差异）；stream/
            # 采样参数工单未带——不传
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": K38_PROMPT}],
                token_field: token_value,
            }
            started = time.time()
            try:
                response = api_client.session.post(
                    chat_url,
                    json=payload,
                    timeout=K38_HARD_TIMEOUT,
                )
            except requests.exceptions.Timeout as e:
                # 断言1：30s 硬超时——超时即挂起缺陷复现（工单
                # 形态：180s 无响应、HTTP 0）
                test_logger.error(
                    f"[{leg_tag}] {K38_HARD_TIMEOUT}s 硬超时内无任何"
                    f"响应（挂起形态——请求已发出、无响应字节）: {e}"
                )
                pytest.fail(
                    f"[{leg_tag}] 挂起缺陷复现——{token_field}="
                    f"{token_value} 请求 {K38_HARD_TIMEOUT}s 内无响应"
                    f"（requests 超时：{e}；工单 A-A01 形态："
                    f"max_completion_tokens=1 单发 180s 超时无响应"
                    f"（HTTP 0）；预期行为：不得触发 180s 级挂起"
                    f"——超时如实计入失败、不拖死整轮）"
                )
            except Exception as e:
                pytest.fail(
                    f"[{leg_tag}] 请求发送异常（{chat_url}）: {e}"
                )
            elapsed = time.time() - started
            body = response.text
            test_logger.info(
                f"[{leg_tag}] 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, body={body[:800]!r}"
            )
            # 断言1（补充留痕）：字节缓流形态——已返回但总时长超
            # 30s（requests 读超时按字节间隔计时，非总时长），观
            # 察交人工分派（K37 口径）
            if elapsed > K38_HARD_TIMEOUT:
                test_logger.warning(
                    f"[{leg_tag}] 已返回但总耗时 {elapsed:.1f}s 超 "
                    f"{K38_HARD_TIMEOUT}s（字节缓流未触发读超时——"
                    f"罕见形态，留观察人工分派）"
                )
            # 断言2：HTTP 200（官方判定通过——别名单 token 请求
            # 被接受；4xx=别名被拒，与官方通过口径不一致）
            assert response.status_code == 200, (
                f"[{leg_tag}] 官方判定通过（max_completion_tokens 别"
                f"名为单 token 请求被接受），实际 HTTP "
                f"{response.status_code}: {body[:400]}"
            )
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                pytest.fail(
                    f"[{leg_tag}] 响应体非 JSON: {body[:300]!r}"
                )
            return {"data": data, "elapsed": elapsed}

        # ── 轮一：别名轮（工单 A-A01 原样，1 发对齐工单口径）──
        alias_tag = (
            "chat/别名轮（max_completion_tokens=1 工单原样）"
        )
        alias_r = send_leg(
            alias_tag, "max_completion_tokens", K38_MAX_COMPLETION_TOKENS
        )
        alias_data = alias_r["data"]
        alias_elapsed = alias_r["elapsed"]
        choices = alias_data.get("choices") or []
        assert choices, f"[{alias_tag}] 响应缺少 choices: {alias_data!r}"
        # 断言3：别名生效——usage.completion_tokens<=2（单 token
        # 截断；字段被丢弃则长文数百 token；usage 未携带/非数值
        # 时判据降级为延迟判据并留观察，不因缺 usage 误报）
        alias_usage = alias_data.get("usage") or {}
        alias_ct = alias_usage.get("completion_tokens")
        if isinstance(alias_ct, (int, float)):
            assert alias_ct <= 2, (
                f"[{alias_tag}] 别名未生效——max_completion_tokens=1 "
                f"未按单 token 截断（completion_tokens={alias_ct}，"
                f"疑似字段被丢弃后长文输出；官方判定通过口径：别名"
                f"为单 token 请求立即截断）"
            )
        else:
            test_logger.info(
                f"[{alias_tag}] 观察: 响应未携带数值型 usage."
                f"completion_tokens——别名截断判据降级为延迟判据"
            )
        # 观察记录：finish_reason 与正文（1 配额默认思考计入易空
        # 正文+length——K31 域形态，非本例判据）
        choice0 = choices[0] if isinstance(choices[0], dict) else {}
        content0 = (choice0.get("message") or {}).get("content") or ""
        test_logger.info(
            f"[{alias_tag}] finish_reason="
            f"{choice0.get('finish_reason')!r}, 正文 "
            f"{len(str(content0).strip())} 字符, "
            f"completion_tokens={alias_ct!r}, "
            f"elapsed={alias_elapsed:.1f}s"
            f"（观察不计判据——1 配额默认思考计入易空正文+"
            f"length，属 K31 域形态）"
        )

        time.sleep(3)

        # ── 轮二：主路径轮（同 prompt max_tokens=1 对照基线）──
        main_tag = "chat/主路径轮（max_tokens=1 对照基线）"
        main_r = send_leg(main_tag, "max_tokens", K38_MAIN_PATH_MAX_TOKENS)
        main_elapsed = main_r["elapsed"]

        # ── 断言4：同延迟水平（客户预期"与 tokens 主路径同延迟
        # 水平"——3 倍+10s 容网络抖动；挂起形态已由 30s 硬超时
        # 兜底，两判据互补）──
        parity_limit = K38_PARITY_FACTOR * main_elapsed + K38_PARITY_BUFFER
        assert alias_elapsed <= parity_limit, (
            f"[{alias_tag}] 别名路径延迟 {alias_elapsed:.1f}s 超同延迟"
            f"水平宽容线（主路径 {main_elapsed:.1f}s × "
            f"{K38_PARITY_FACTOR} + {K38_PARITY_BUFFER}s = "
            f"{parity_limit:.1f}s）——预期行为：与 tokens 主路径同延"
            f"迟水平（别名轮 elapsed={alias_elapsed:.1f}s）"
        )
        test_logger.info(
            f"客户问题整改验证通过: 别名单 token 请求未挂起——别名"
            f"轮 {alias_elapsed:.1f}s、主路径轮 {main_elapsed:.1f}s"
            f"（同延迟水平：别名 <= 主路径×{K38_PARITY_FACTOR}+"
            f"{K38_PARITY_BUFFER}s），30s 硬超时内全部返回且别名按"
            f"单 token 截断——max_completion_tokens 别名 180s 级"
            f"挂起缺陷未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.KimiK3
    @pytest.mark.p0
    def test_reasoning_dual_field_history_accepted(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K39 [P0]: 客户问题 - 历史 assistant 消息 reasoning/
        reasoning_content 双字段共存兼容接受

        客户问题（工单 AGDC2-47，接口协议）：
        - 官方行为（AGDC2-47 测试资料·官方 API 验证结论，
          2026-11-05 Kimi K3 官方端点）：同一历史 assistant 消息
          同时包含 reasoning 与 reasoning_content，无论内容相同
          或不同、哪个字段在前，官方 API 均接受——14 组合（字段
          变体 × 默认/关闭思考）全部 HTTP 200、finish_reason=
          stop、回答 3，无 400/json_parse_error/duplicate field
        - 贵方实测：双字段共存即 HTTP 400、错误码
          json_parse_error、提示 duplicate field reasoning_
          content——两字段值相同或不同均报错；仅 reasoning 或仅
          reasoning_content 单字段调用成功；客户生产调用产生
          较多报错
        - 预期行为（整改）：历史消息同时存在 reasoning 与
          reasoning_content，无论两字段值相同或不同，均不得
          400 响应，应正常请求成功
        本用例按官方验证请求原样复现（用户指定：只测双字段共存
        场景——单字段/无字段场景不测；调整两字段顺序 × 覆盖
        两字段值相同和不同），chat 单协议 4 发（相邻间隔 3s），
        同一三消息结构（user "What is 1 + 1? Reply with only
        the number." / assistant content="2"+双思考字段 / user
        "Add 1 to the previous answer. Reply with only the
        number."），请求体官方验证原样（字段序 model/stream/
        max_tokens/messages，stream=false、max_tokens=512，
        thinking 默认模式不传）：
        1. 同值/reasoning 在前（两字段均 "1 + 1 = 2."）
        2. 同值/reasoning_content 在前
        3. 异值/reasoning 在前（reasoning="Compute the sum."、
           reasoning_content="The answer is two."）
        4. 异值/reasoning_content 在前
        硬断言每发：HTTP 200（400 json_parse_error/duplicate
        field reasoning_content=缺陷复现——同条消息两思考字段
        被解析层视为同字段别名而拒绝）+ 响应体合法 JSON +
        choices 非空 + 正文非空（空正文+finish=length 留观察
        ——512 预算默认思考计入耗尽属 K31 域形态非本例判据；
        空正文且 finish≠length 即 FAIL）。
        观察记录（不计判据）：finish_reason、回答是否含 3（官
        方验证回答为 3——生成质量非本例判据）、正文长度。显式
        关闭思考模式不测（官方双模式均 200 证明字段兼容性与模
        式正交；K35 已确立网关对关闭思考 400 拒绝口径——另一
        缺陷域）。chat 单协议（reasoning/reasoning_content 为
        chat 历史消息字段，Anthropic /v1/messages 无该字段形
        态——思考经 thinking content block 承载，msg 未知参数
        行为由 K33/K35 覆盖）。模型名由环境注入；thinking/采
        样参数官方验证请求未含——不传（不注入）；双 marker
        GLM53 + KimiK3——工单缺陷经 Kimi K3 官方端点验证，字
        段解析为接口层通用逻辑（与模型无关），同时适用
        GLM-5.3 与 Kimi K3（请求同构，无模型分支）。（不进
        smoke 集：新用例首跑观察期）
        """
        # K39: 三消息结构（AGDC2-47 官方验证请求原样——user 提
        # 问/assistant content=2 携双思考字段/user 追问）
        K39_Q1 = "What is 1 + 1? Reply with only the number."
        K39_Q2 = (
            "Add 1 to the previous answer. Reply with only the "
            "number."
        )
        K39_ASSISTANT_CONTENT = "2"
        # K39: 官方验证原始口径（4 发一致：stream=false、
        # max_tokens=512）
        K39_MAX_TOKENS = 512
        # K39: 双字段同值内容（官方验证原样）
        K39_SAME_VALUE = "1 + 1 = 2."
        # K39: 双字段异值内容（官方验证原样）
        K39_DIFF_REASONING = "Compute the sum."
        K39_DIFF_REASONING_CONTENT = "The answer is two."

        test_logger.info(
            "=== 测试开始: 客户问题 - 历史 assistant 消息 reasoning"
            "/reasoning_content 双字段共存兼容（工单 AGDC2-47：双字段"
            "共存即 400 json_parse_error duplicate field reasoning_"
            "content、同值/异值均报错、单字段正常；官方 API 验证同形态"
            " 14 组合全部 200；预期双字段共存无论值同异、字段顺序均正"
            "常成功；chat 4 发=同值/异值 × reasoning/reasoning_"
            "content 在前，单字段场景不测（用户指定））==="
        )

        chat_url = f"{api_client.api_prefix}/chat/completions"

        # K39: 场景矩阵（用户指定——只测双字段共存：两字段顺序 ×
        # 同值/异值）；reasoning_first 控制双思考字段键序（dict
        # 插入序即 JSON 上送序）
        scenarios = (
            ("同值/reasoning 在前", K39_SAME_VALUE, K39_SAME_VALUE, True),
            (
                "同值/reasoning_content 在前",
                K39_SAME_VALUE,
                K39_SAME_VALUE,
                False,
            ),
            (
                "异值/reasoning 在前",
                K39_DIFF_REASONING,
                K39_DIFF_REASONING_CONTENT,
                True,
            ),
            (
                "异值/reasoning_content 在前",
                K39_DIFF_REASONING,
                K39_DIFF_REASONING_CONTENT,
                False,
            ),
        )

        for idx, (label, reasoning_val, rc_val, reasoning_first) in enumerate(
            scenarios, 1
        ):
            if idx > 1:
                time.sleep(3)
            tag = f"chat/场景{idx}（{label}）"
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": K39_ASSISTANT_CONTENT,
            }
            if reasoning_first:
                assistant_msg["reasoning"] = reasoning_val
                assistant_msg["reasoning_content"] = rc_val
            else:
                assistant_msg["reasoning_content"] = rc_val
                assistant_msg["reasoning"] = reasoning_val
            TestLogger.log_request(
                test_logger,
                [
                    {"role": "user", "content": K39_Q1},
                    assistant_msg,
                    {"role": "user", "content": K39_Q2},
                ],
                {
                    "endpoint": "/v1/chat/completions",
                    "scenario": label,
                    "max_tokens": K39_MAX_TOKENS,
                    "stream": False,
                    "thinking": "(默认模式——不传)",
                    "temperature": "(原始未指定——不注入)",
                    "top_p": "(原始未指定——不注入)",
                    "seed": "(原始未指定——不注入)",
                },
            )
            # K39: 官方验证请求原样（字段序 model/stream/max_tokens/
            # messages；assistant 内双思考字段键序按场景——dict
            # 插入序即 JSON 序）；thinking/采样参数未含——不传
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "stream": False,
                "max_tokens": K39_MAX_TOKENS,
                "messages": [
                    {"role": "user", "content": K39_Q1},
                    assistant_msg,
                    {"role": "user", "content": K39_Q2},
                ],
            }
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    chat_url, payload, stream=False
                )
            except Exception as e:
                pytest.fail(f"[{tag}] 请求发送异常（{chat_url}）: {e}")
            elapsed = time.time() - started
            try:
                data = response.json()
            except ValueError:
                data = None
            test_logger.info(
                f"[{tag}] 真实响应: HTTP {response.status_code}, "
                f"elapsed={elapsed:.1f}s, "
                f"body={response.text[:800]!r}"
            )
            # 断言1：HTTP 200——400 json_parse_error/duplicate
            # field reasoning_content 即缺陷复现（工单形态：同条
            # 消息两思考字段被解析层视为同字段别名而拒绝）
            assert response.status_code == 200, (
                f"[{tag}] 双字段共存历史应正常请求成功（官方 API 验"
                f"证同形态全部 200），实际 HTTP "
                f"{response.status_code}: {response.text[:400]}"
                f"（工单 AGDC2-47 形态：json_parse_error/duplicate "
                f"field reasoning_content=缺陷复现；预期：无论两字段"
                f"值相同或不同、字段顺序如何均不得 400）"
            )
            assert data, f"[{tag}] 响应体应为合法 JSON"
            choices = data.get("choices") or []
            assert choices, f"[{tag}] 响应缺少 choices: {data!r}"
            choice = choices[0] or {}
            message = choice.get("message") or {}
            content = message.get("content") or ""
            finish_reason = choice.get("finish_reason")
            # 断言2：正文非空（正常请求成功判定）——空正文+
            # finish=length 留观察（512 预算默认思考计入耗尽属
            # K31 域形态非本例判据）；空正文且 finish≠length 即
            # FAIL（非截断的空正文为异常形态）
            if not content.strip():
                if finish_reason == "length":
                    test_logger.warning(
                        f"[{tag}] 正文空且 finish=length——512 预算"
                        f"被思考计入耗尽（K31 域形态，留观察不计判"
                        f"据，交人工分派）"
                    )
                else:
                    pytest.fail(
                        f"[{tag}] 正文为空且 finish_reason="
                        f"{finish_reason!r}（非 length 截断的空正文"
                        f"——异常形态，不属 K31 域豁免口径）: "
                        f"{data!r}"
                    )
            # 观察记录：finish_reason/回答含 3（官方验证回答为 3
            # ——生成质量非本例判据）/正文长度
            test_logger.info(
                f"[{tag}] 通过: finish_reason={finish_reason!r}, "
                f"正文 {len(content.strip())} 字符"
                f"（含预期答案 3: {'3' in content}——观察不计判"
                f"据）, elapsed={elapsed:.1f}s"
            )
        test_logger.info(
            f"客户问题整改验证通过: {len(scenarios)} 发（双字段共"
            f"存：同值/异值 × reasoning/reasoning_content 在前）"
            f"全部 HTTP 200 正常请求成功——历史消息 reasoning/"
            f"reasoning_content 双字段共存 400（json_parse_error/"
            f"duplicate field reasoning_content）缺陷未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p1
    def test_thinking_enabled_reasoning_content_stable(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K40 [P1]: 客户问题 - thinking enabled 响应 reasoning_
        content 字段稳定性（三轮 × 每轮 10 并发统一携带核验）

        客户问题（新工单，响应字段稳定性）：请求体 max_tokens=
        16000 + 单 user 消息「证明：对于任意正整数n，n^3-n能被
        6整除」+ thinking={"type": "enabled"}（客户环境模型
        GLM-5.3-jy-b）——响应有时带、有时不带 reasoning_content
        字段，不稳定，客户生产调用产生较多困扰；预期所有请求统
        一携带 reasoning_content 字段。
        预期行为（整改）：thinking enabled 请求的响应须稳定携
        带 reasoning_content——所有轮的所有请求全部存在且非空。
        本用例分三轮、每轮 10 并发（轮内 ThreadPoolExecutor 10
        workers 同拍齐发——E5 并发稳定性先例；轮间串行——每
        轮收齐后再开下一轮；用户指定 2026-11-09：测试分为三
        轮、每轮 10 并发，所有轮的所有请求 reasoning_content
        统一才算通过；同日调整确认：每轮结束收集一次，任一轮
        次不一致即失败中止——避免后续轮次浪费）验证统一性。
        请求体工单原样：max_tokens=16000、单 user 消息、
        thinking={"type": "enabled"}；stream 工单未含——不传
        （非流式默认）；采样参数（temperature/top_p/seed）工单
        未含——不注入；模型名由环境注入（用户确认——staging
        端点为 glm-5.3，GLM-5.3-jy-b 为客户内部档位名）。超时
        沿用全局（工单未涉及超时语义——thinking+16000 预算单
        发通常 10-60s，_post_with_retry timeout=None 沿用全局
        值；三轮串行总时长约 1-3min）。
        判定（逐轮判定——每轮收齐即断言该轮，任一轮次失败即
        用例失败并中止后续轮次，用户指定 2026-11-09：避免无
        效轮次消耗）：
        1. 断言1（逐轮）：该轮 10/10 HTTP 200（非 200/发送异
           常全量列出——请求层失败同样破坏统一性验证）
        2. 断言2（逐轮）：该轮 10/10 响应体合法 JSON + choices
           非空
        3. 断言3（逐轮）：该轮 10/10 choices[0].message.
           reasoning_content 存在且非空（「统一」口径=字段层
           面全部携带，用户确认——空字符串同样属「没有」，内
           容逐字一致不作要求——思考文本天然因请求而异；缺
           失/空串清单全量输出=缺陷复现证据，如「第 2 轮
           8/10 携带，缺失 #R2-3/#R2-7」）
        三轮全部通过才 PASS（所有轮的所有请求统一携带）。
        观察（不计判据）：逐轮+整体 finish_reason/正文长度/思
        考长度分布/耗时。chat 单协议（客户请求为 chat 形态，
        缺陷为 chat 响应字段——Anthropic msg 思考经 thinking
        content block 承载，无 reasoning_content 字段形态）。
        GLM-5.3 专用（工单模型 GLM-5.3-jy-b 为 GLM-5.3 档位
        变体，缺陷为响应字段生成逻辑，模型名由环境注入——无
        模型分支）。（不进 smoke 集：新用例首跑观察期；三轮
        × 每轮 10 请求）
        """
        # K40: 工单原样请求参数（单 user 数学证明题——思考
        # enabled 下必经推理路径；max_tokens=16000、thinking
        # 对象形态 {"type": "enabled"}）
        K40_PROMPT = "证明：对于任意正整数n，n^3-n能被6整除"
        K40_MAX_TOKENS = 16000
        # K40: 轮次/并发数（用户指定 2026-11-09：三轮、每轮
        # 10 并发——所有轮的所有请求 reasoning_content 统一
        # 才通过；每轮收齐即判定，任一轮次失败即中止后续轮
        # 次——避免无效轮次消耗）
        K40_ROUNDS = 3
        K40_CONCURRENCY = 10

        test_logger.info(
            "=== 测试开始: 客户问题 - thinking enabled 响应 "
            "reasoning_content 字段稳定性（工单：max_tokens=16000+"
            "单 user 证明题+thinking enabled——响应有时带/不带 "
            "reasoning_content 不稳定，预期统一携带；三轮 × 每"
            f"轮 {K40_CONCURRENCY} 并发验证统一性，每轮收齐即"
            "判定，任一轮失败即中止后续轮次）==="
        )

        chat_url = f"{api_client.api_prefix}/chat/completions"

        def send_probe(round_no: int, idx: int) -> Dict[str, Any]:
            """K40 并发探针：发单请求并收集判定所需字段（异
            常不抛出——轮内收齐后统一断言，用户确认口径）"""
            # K40: 工单原样 payload（字段序 model/messages/max_
            # tokens/thinking；stream 工单未含——不传；采样参
            # 数未含——不注入；模型名由环境注入）
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [
                    {"role": "user", "content": K40_PROMPT}
                ],
                "max_tokens": K40_MAX_TOKENS,
                "thinking": {"type": "enabled"},
            }
            started = time.time()
            try:
                response = api_client._post_with_retry(
                    chat_url, payload, stream=False
                )
            except Exception as e:
                return {
                    "round": round_no,
                    "idx": idx,
                    "error": f"请求发送异常: {e}",
                    "status": None,
                    "elapsed": 0.0,
                    "data": None,
                    "reasoning_content": None,
                    "content": "",
                    "finish_reason": None,
                }
            elapsed = time.time() - started
            try:
                data = response.json()
            except ValueError:
                data = None
            choices = (data or {}).get("choices") or []
            choice0 = choices[0] if choices else {}
            message = (choice0 or {}).get("message") or {}
            return {
                "round": round_no,
                "idx": idx,
                "status": response.status_code,
                "elapsed": elapsed,
                "data": data,
                "reasoning_content": message.get("reasoning_content"),
                "content": message.get("content") or "",
                "finish_reason": choice0.get("finish_reason"),
            }

        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K40_PROMPT}],
            {
                "endpoint": "/v1/chat/completions",
                "max_tokens": K40_MAX_TOKENS,
                "thinking": {"type": "enabled"},
                "轮次": K40_ROUNDS,
                "并发数(每轮)": K40_CONCURRENCY,
                "stream": "(原始未指定——不传，非流式默认)",
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )

        # K40: 三轮 × 每轮 10 并发（轮间串行——每轮收齐后再开
        # 下一轮；每轮收齐即断言该轮，任一轮次失败即用例失败
        # 并中止后续轮次——用户指定 2026-11-09：避免无效轮次
        # 消耗；轮内 E5 同款 ThreadPoolExecutor 同拍齐发）
        all_results: List[Dict[str, Any]] = []
        for round_no in range(1, K40_ROUNDS + 1):
            test_logger.info(
                f"--- 第 {round_no}/{K40_ROUNDS} 轮: 并发 "
                f"{K40_CONCURRENCY} 发同拍齐发 ---"
            )
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=K40_CONCURRENCY
            ) as executor:
                futures = [
                    executor.submit(send_probe, round_no, i)
                    for i in range(1, K40_CONCURRENCY + 1)
                ]
                results = [f.result() for f in futures]
            results.sort(key=lambda r: r["idx"])

            # K40: 每发真实响应留痕（按 idx 序输出该轮全量矩阵
            # ——失败时同样可见；标识 #R{轮}-{序} 跨轮定位）
            for r in results:
                rid = f"#R{r['round']}-{r['idx']}"
                if r.get("error"):
                    test_logger.error(f"[{rid}] {r['error']}")
                    continue
                rc = r["reasoning_content"]
                rc_desc = (
                    f"reasoning_content {len(str(rc))} 字符"
                    if isinstance(rc, str) and rc.strip()
                    else f"reasoning_content 缺失/空: {rc!r}"
                )
                test_logger.info(
                    f"[{rid}] 真实响应: HTTP {r['status']}, "
                    f"elapsed={r['elapsed']:.1f}s, {rc_desc}, "
                    f"正文 {len(str(r['content']).strip())} 字符, "
                    f"finish_reason={r['finish_reason']!r}"
                )

            # 断言1（本轮）：10/10 HTTP 200（非 200/发送异常全
            # 量列出——请求层失败同样破坏统一性验证；任一轮次
            # 失败即判定并中止后续轮次）
            non_200 = [
                r
                for r in results
                if r.get("error") or r["status"] != 200
            ]
            assert not non_200, (
                f"第 {round_no} 轮存在非 200/发送异常（预期每轮 "
                f"{K40_CONCURRENCY}/{K40_CONCURRENCY} HTTP 200——"
                f"请求层失败同样属统一性未达标；已中止后续轮次"
                f"——任一轮次失败即判定）: "
                + "; ".join(
                    f"#R{r['round']}-{r['idx']}: "
                    f"{r.get('error') or r['status']}"
                    for r in non_200
                )
            )

            # 断言2（本轮）：10/10 响应体合法 JSON + choices 非空
            bad_body = [
                r
                for r in results
                if not r["data"]
                or not (r["data"].get("choices") or [])
            ]
            assert not bad_body, (
                f"第 {round_no} 轮存在响应体异常（非法 JSON/"
                f"choices 空；已中止后续轮次——任一轮次失败即判"
                f"定）: "
                + "; ".join(
                    f"#R{r['round']}-{r['idx']}: "
                    f"{str(r['data'])[:200]}"
                    for r in bad_body
                )
            )

            # 断言3（本轮）：10/10 reasoning_content 存在且非空
            # （工单缺陷直接判据——「统一」=字段层面全部携带，
            # 空串同判缺失；缺失/空串清单全量输出=缺陷复现证据
            # ——任一轮次失败即判定并中止后续轮次，避免无效轮
            # 次消耗）
            missing_rc = [
                r
                for r in results
                if not isinstance(r["reasoning_content"], str)
                or not r["reasoning_content"].strip()
            ]
            assert not missing_rc, (
                f"缺陷复现: 第 {round_no} 轮 reasoning_content "
                f"统一性 {K40_CONCURRENCY - len(missing_rc)}/"
                f"{K40_CONCURRENCY} 携带，缺失/空: "
                + ", ".join(
                    f"#R{r['round']}-{r['idx']}" for r in missing_rc
                )
                + "——预期所有轮的所有请求统一携带 reasoning_"
                f"content（工单形态：有时带/有时不带，不稳定）；"
                f"已中止后续轮次——任一轮次失败即判定，避免无效"
                f"轮次消耗；缺失发响应留痕: "
                + " || ".join(
                    f"#R{r['round']}-{r['idx']}: "
                    f"finish={r['finish_reason']!r}, 正文 "
                    f"{len(str(r['content']).strip())} 字符, "
                    f"reasoning_content={r['reasoning_content']!r}"
                    for r in missing_rc[:5]
                )
            )

            # 本轮通过留痕（观察不计判据）：思考长度/耗时/
            # finish_reason 分布
            rc_lengths = [
                len(str(r["reasoning_content"]).strip())
                for r in results
            ]
            elapsed_list = [r["elapsed"] for r in results]
            finishes = [r["finish_reason"] for r in results]
            finish_dist = {f: finishes.count(f) for f in set(finishes)}
            test_logger.info(
                f"第 {round_no}/{K40_ROUNDS} 轮通过: "
                f"{K40_CONCURRENCY}/{K40_CONCURRENCY} HTTP 200 且 "
                f"reasoning_content 统一携带（存在且非空）——本轮 "
                f"思考长度 min/avg/max={min(rc_lengths)}/"
                f"{sum(rc_lengths) // len(rc_lengths)}/"
                f"{max(rc_lengths)} 字符, 耗时 min/avg/max="
                f"{min(elapsed_list):.1f}/"
                f"{sum(elapsed_list) / len(elapsed_list):.1f}/"
                f"{max(elapsed_list):.1f}s, finish_reason 分布="
                f"{finish_dist}（观察不计判据）"
            )
            all_results.extend(results)

        # 整体观察汇总（不计判据）：三轮共 30 发统一性摘要
        rc_lengths = [
            len(str(r["reasoning_content"]).strip())
            for r in all_results
        ]
        elapsed_list = [r["elapsed"] for r in all_results]
        finishes = [r["finish_reason"] for r in all_results]
        finish_dist = {f: finishes.count(f) for f in set(finishes)}
        test_logger.info(
            f"整体观察: 三轮共 {len(all_results)} 发 "
            f"reasoning_content 长度 min/avg/max={min(rc_lengths)}/"
            f"{sum(rc_lengths) // len(rc_lengths)}/"
            f"{max(rc_lengths)} 字符, 耗时 min/avg/max="
            f"{min(elapsed_list):.1f}/"
            f"{sum(elapsed_list) / len(elapsed_list):.1f}/"
            f"{max(elapsed_list):.1f}s, finish_reason 分布="
            f"{finish_dist}（观察不计判据）"
        )
        test_logger.info(
            f"客户问题整改验证通过: 三轮 × 每轮 {K40_CONCURRENCY} "
            f"并发共 {K40_ROUNDS * K40_CONCURRENCY} 发——所有轮"
            f"的所有请求全部 HTTP 200 且 reasoning_content 统一携"
            f"带（存在且非空），thinking enabled 响应 reasoning_"
            f"content 字段不稳定缺陷未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p1
    def test_empty_stop_array_normal_response(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K41 [P1]: 客户问题 - stop 空数组应正常响应（400 拒
        绝缺陷核验）

        客户问题（新工单，参数校验）：请求带 stop=[]（空数组）时
        平台 400 拒绝，两种错误形态（两个 request id）——上游校
        验错透传 {"error": {"message": "Validation: Stop
        sequences array cannot be empty (...)", "type":
        "upstream_error", "param": "400", "code": "bad_response_
        status_code"}} 与平台参数错 {"code": 1210, "message":
        "max_tokens 超出范围 [1, 131072] (...)"}。
        预期行为（整改）：stop=[] 请求正常响应、正常结束（finish=
        stop），不应触发模型服务的最大输出上限 128k。
        本用例单发 stop=[] 请求（参数处理确定性，K6/K23 先例）。
        请求体最小构造：stop=[]（工单唯一原样参数）+ 自拟最小
        user 消息（工单未携带消息内容）；max_tokens 不传（用户确
        认 2026-11-09——工单未提供不注入，且缺省填充上限缺陷路
        径恰好由不传覆盖：错误形态 2「max_tokens 超出范围 [1,
        131072]」直接指向缺省/上限路径）；stream/thinking/采样参
        数（temperature/top_p/seed）未含——不传不注入；模型名由
        环境注入（工单无模型线索）。超时沿用全局（工单未涉及挂
        死/超时语义）。
        判定（单发，四断言）：
        1. 断言1：HTTP 200（400=缺陷复现——两种工单错误文案归类
           留证）
        2. 断言2：响应体合法 JSON + choices 非空
        3. 断言3：finish_reason == "stop"（正常结束——工单原
           话；length=触发模型服务最大输出上限 128k 的缺陷形
           态）
        4. 断言4：正文非空
        观察（不计判据）：400 时错误体归类（"Stop sequences
        array cannot be empty"→上游校验错形态 / "max_tokens 超
        出范围"+code 1210→平台参数错形态）；200 时 usage.
        completion_tokens 异常大（撞 128k 上限痕迹）留痕。chat
        单协议（错误体为 chat 形态响应；msg 未知参数行为由
        K33/K35 覆盖）。仅 GLM53（工单无模型线索，被测环境
        glm-5.3，缺陷为平台/引擎层 stop 校验与 max_tokens 上限
        路径，无模型分支）。（不进 smoke 集：新用例首跑观察
        期；1 请求）
        """
        # K41: 工单原样参数（stop=[] 空数组——唯一明确参数）；
        # 消息内容工单未携带——自拟最小 user 消息
        K41_STOP: List[str] = []
        K41_PROMPT = "请用一句话解释什么是质数。"

        test_logger.info(
            "=== 测试开始: 客户问题 - stop 空数组应正常响应（工单："
            "stop=[] 请求 400——两种错误形态：Stop sequences array "
            "cannot be empty（upstream_error）/ max_tokens 超出范围 "
            "[1, 131072]（code 1210）；预期正常响应正常结束，不应触"
            "发模型服务最大输出上限 128k；单发，max_tokens 不传——"
            "缺省填充上限缺陷路径由不传覆盖）==="
        )

        chat_url = f"{api_client.api_prefix}/chat/completions"

        # K41: 请求体最小构造（字段序 model/messages/stop；stop=[]
        # 工单原样；max_tokens 不传——工单未提供不注入；stream/
        # thinking/采样参数未含——不传不注入；模型名由环境注入）
        payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": K41_PROMPT}],
            "stop": K41_STOP,
        }

        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K41_PROMPT}],
            {
                "endpoint": "/v1/chat/completions",
                "stop": K41_STOP,
                "max_tokens": "(原始未提供——不传，缺省/上限路径由不传覆盖)",
                "stream": "(原始未指定——不传，非流式默认)",
                "thinking": "(原始未指定——不传)",
                "temperature": "(原始未指定——不注入)",
                "top_p": "(原始未指定——不注入)",
                "seed": "(原始未指定——不注入)",
            },
        )

        # K41: 单发直发（参数处理确定性——K6/K23 先例；超时沿用全
        # 局，工单未涉及挂死语义）
        start_time = time.time()
        response = api_client._post_with_retry(
            chat_url, payload, stream=False
        )
        elapsed = time.time() - start_time
        status = response.status_code
        body_text = response.text

        # K41: 模型真实响应断言前留痕——400 时按工单两种错误文案归
        # 类（缺陷形态留证，失败时同样可见）
        if status == 200:
            test_logger.info(
                f"真实响应: HTTP {status}, elapsed={elapsed:.1f}s"
            )
        else:
            defect_kinds = []
            if "Stop sequences array cannot be empty" in body_text:
                defect_kinds.append(
                    "上游校验错形态（Stop sequences array cannot be "
                    "empty/upstream_error）"
                )
            if (
                "max_tokens" in body_text and "超出范围" in body_text
            ) or "1210" in body_text:
                defect_kinds.append(
                    "平台参数错形态（max_tokens 超出范围 [1, 131072]"
                    "/code 1210）"
                )
            kind_desc = (
                "；".join(defect_kinds)
                if defect_kinds
                else "未归类形态（非工单两种文案）——留证交人工分派"
            )
            test_logger.info(
                f"真实响应: HTTP {status}, elapsed={elapsed:.1f}s, "
                f"缺陷形态归类: {kind_desc}, 响应体全文: {body_text}"
            )

        # 断言1：HTTP 200（400=缺陷复现——工单两种错误体形态留证）
        assert status == 200, (
            f"缺陷复现: stop=[] 空数组请求被 HTTP {status} 拒绝（预期"
            f"正常响应 200——工单形态：Stop sequences array cannot be "
            f"empty（upstream_error）/ max_tokens 超出范围 [1, 131072]"
            f"（code 1210）），elapsed={elapsed:.1f}s, 响应体全文: "
            f"{body_text}"
        )

        # 断言2：响应体合法 JSON + choices 非空
        try:
            data = response.json()
        except ValueError:
            data = None
        choices = (data or {}).get("choices") or []
        assert choices, (
            f"响应体异常（非法 JSON/choices 空）: {body_text}"
        )

        choice0 = choices[0] or {}
        message = choice0.get("message") or {}
        content = message.get("content") or ""
        finish_reason = choice0.get("finish_reason")

        # 断言3：finish_reason == "stop"（正常结束——工单原话；
        # length=触发模型服务最大输出上限 128k 的缺陷形态）
        assert finish_reason == "stop", (
            f"缺陷形态: finish_reason={finish_reason!r}（预期 stop 自然"
            f"结束——length=触发了模型服务最大输出上限 128k，工单明确"
            f"「不应触发」），HTTP {status}, 响应体全文: {body_text}"
        )

        # 断言4：正文非空（正常响应形态）
        assert str(content).strip(), (
            f"缺陷形态: 正文为空（预期正常响应非空正文），finish_"
            f"reason={finish_reason!r}, 响应体全文: {body_text}"
        )

        # 观察记录（不计判据）：usage token 计量——completion_tokens
        # 异常大=撞 128k 上限痕迹（缺省填充上限缺陷的残留形态）留
        # 痕；reasoning_tokens 双路径兼容提取（K7 域字段拼写）
        usage = (data or {}).get("usage") or {}
        completion_tokens = usage.get("completion_tokens")
        details = usage.get("completion_tokens_details")
        reasoning_tokens = (
            details.get("reasoning_tokens")
            if isinstance(details, dict)
            else None
        )
        if reasoning_tokens is None:
            reasoning_tokens = usage.get("reasoning_tokens")
        test_logger.info(
            f"观察: finish_reason={finish_reason!r}, 正文 "
            f"{len(str(content).strip())} 字符, completion_tokens="
            f"{completion_tokens!r}, reasoning_tokens="
            f"{reasoning_tokens!r}（completion_tokens 异常大=撞 "
            f"128k 上限痕迹，观察不计判据）"
        )
        test_logger.info(
            "客户问题整改验证通过: stop=[] 空数组请求 HTTP 200 且自然"
            "结束（finish=stop）正文非空——空 stop 数组 400 拒绝与 "
            "max_tokens 越界（触发 128k 上限）缺陷未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.KimiK3
    @pytest.mark.p1
    def test_kimik3_long_tool_args_stream_no_stall(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K42 [P1]: 客户问题 - Kimi-K3 工具调用长参数流式停流
        核验（间隔<30s+正常终止，chat 单协议）

        客户问题（工单 AGDC2-45 · Kimi-K3 流式中途停流）：kimi-k3
        流式请求正常出流（~70 chunk/s、已出 1480 tokens）后正文结
        束，连续 30s 无任何字节——无 finish_reason/tool_calls/
        [DONE]，连接未断，客户端按 30s 无数据取消策略断开（网关
        日志「客户端已断开，已中断渠道 #20 上游请求」）；多条历史
        请求同形态（中断、finish_reason 为空）。
        根因（排障报告确认）：SGLang 0.5.21 kimik3_detector 工具调
        用解析器按完整 call 整包输出、不增量发工具参数——正文/
        思考可先结束，长参数生成阶段参数全部缓存在解析器内，
        SSE 无新数据无心跳（serving_chat.py 空时不 yield）；线上
        抓包 3 样本空窗 71.697/89.010/116.724s（恢复时一次性返
        回 7952/12831/12044 字符参数），均超客户 30s 取消阈值。
        本用例单发原样回放抓包请求 tests/data/k42_request_
        original.json（231,432 字节，sha256 371b1753...；78
        messages/25 tools/31 历史工具调用，报告方法 C 口径：单
        并发、读空闲 180s、总时限 600s）。
        请求构造：messages/tools/temperature=1/max_completion_
        tokens=131072/stream=true/stream_options={"include_
        usage": true}/reasoning_effort="high" 全部原样（抓包原
        样参数）；stop/tool_choice/seed/采样参数未含——不注入；
        model 由环境注入（用户确认 2026-11-09——与既有 K 用例一
        致，运行环境指向 Kimi-K3 实例）。
        判定（单发，四断言）：
        1. 断言1：HTTP 200 + SSE 事件流（events>0）
        2. 断言2：正常终止——收到非空 finish_reason 且收到
           [DONE]（缺陷形态=两者皆无直至客户端断开）
        3. 断言3：全程任意相邻 SSE 事件间隔 < 30s（客户取消阈
           值；缺陷实测 71.7-116.7s 空窗；TTFT 不计入——首
           token 问题报告声明另行排查）
        4. 断言4：finish=tool_calls 时逐 tool index 拼接
           arguments 为完整 JSON 且工具名非空（报告修复验证标
           准 4）
        观察（不计判据）：TTFT（历史实测 22.6/44.2s）、事件数、
        最大事件间隔及位置、工具参数增量事件数（修复标准 2 证
        据——长参数阶段应有多段 delta 而非整包）、参数字符数、
        usage、请求文件 sha256 留痕。
        超时：读空闲上限 180s（requests 读超时按字节间隔计——
        K37/K38 先例；永久停流触发 ReadTimeout=缺陷形态 FAIL）；
        总时限 600s 墙钟检查。chat 单协议（工单为 chat SSE 流
        式）。仅 KimiK3（工单模型 Kimi-K3，缺陷为 SGLang K3 工
        具解析器层，无其他模型分支）。（不进 smoke 集：新用例
        首跑观察期；单发大上下文 prefill+131072 上限，耗时约
        1.5-4 分钟）
        """
        # K42: 抓包原始请求（报告材料原样入库——231,432 字节）
        K42_REQUEST_FILE = (
            Path(__file__).parent / "data" / "k42_request_original.json"
        )
        # K42: 客户取消策略阈值（工单：30s 无数据断开）——事件间
        # 隔硬断言线
        K42_MAX_EVENT_GAP_S = 30.0
        # K42: 读空闲上限（报告方法 C 口径 180s——requests 读超时
        # 按字节间隔计，K37/K38 先例；TTFT 长等待合法：历史实测
        # 22.6/44.2s；永久停流在此触发 ReadTimeout）
        K42_READ_IDLE_TIMEOUT_S = 180
        # K42: 总时限（报告方法 C 口径 max-seconds 600）
        K42_TOTAL_LIMIT_S = 600.0

        test_logger.info(
            "=== 测试开始: 客户问题 - Kimi-K3 工具调用长参数流式停"
            "流核验（工单：流式出流 1480 tokens 后 30s 无任何字节"
            "——无 finish/tool_calls/DONE，客户端 30s 空闲取消断开；"
            "根因：K3 工具解析器整包缓冲长参数；单发原样回放，间隔"
            "<30s+正常终止）==="
        )

        raw_bytes = K42_REQUEST_FILE.read_bytes()
        payload = json.loads(raw_bytes)
        # 观察：请求文件完整性留痕（报告口径 sha256 一致性）
        file_sha = hashlib.sha256(raw_bytes).hexdigest()
        test_logger.info(
            f"请求文件: {K42_REQUEST_FILE.name}, {len(raw_bytes)} 字"
            f"节, sha256={file_sha}"
        )

        # K42: 客户业务内容不进日志/Allure（报告注明业务内容仅内
        # 部排障使用）——log_request 仅记摘要占位，真实 78
        # messages/25 tools 见数据文件
        TestLogger.log_request(
            test_logger,
            [
                {
                    "role": "user",
                    "content": (
                        "[K42 原样回放摘要] 78 messages（24 system/1 "
                        "user/22 assistant/31 tool）/ 25 tools——客"
                        "户业务内容不入日志，完整请求见 tests/data/"
                        "k42_request_original.json"
                    ),
                }
            ],
            {
                "endpoint": "/v1/chat/completions",
                "stream": "true（抓包原样）",
                "temperature": "1（抓包原样）",
                "max_completion_tokens": "131072（抓包原样）",
                "stream_options": '{"include_usage": true}（抓包原样）',
                "reasoning_effort": "high（抓包原样）",
                "stop/tool_choice/seed": "(抓包未含——不注入)",
                "model": (
                    f"{api_client.model_name!r}（环境注入——用户确认口径）"
                ),
            },
        )

        # K42: model 由环境注入（用户确认 2026-11-09），其余字段全
        # 部原样（不增删、不改值——温度/上限/流式选项/
        # reasoning_effort 均抓包原值）
        payload["model"] = api_client.model_name

        chat_url = f"{api_client.api_prefix}/chat/completions"
        n_messages = len(payload.get("messages") or [])
        n_tools = len(payload.get("tools") or [])
        test_logger.info(
            f"回放参数: messages={n_messages}, tools={n_tools}, "
            f"temperature={payload.get('temperature')!r}, "
            f"max_completion_tokens="
            f"{payload.get('max_completion_tokens')!r}, "
            f"stream={payload.get('stream')!r}, "
            f"reasoning_effort={payload.get('reasoning_effort')!r}, "
            f"model={payload['model']!r}（环境注入）"
        )

        # K42: 单发流式直发（读空闲 180s——requests 读超时按字节
        # 间隔计；总时限 600s 循环内墙钟检查）
        started = time.time()
        response = api_client._post_with_retry(
            chat_url, payload, stream=True, timeout=K42_READ_IDLE_TIMEOUT_S
        )

        # 断言1：HTTP 200（SSE 事件流 events>0 在迭代后断言）
        assert response.status_code == 200, (
            f"缺陷形态: 回放请求被 HTTP {response.status_code} 拒绝: "
            f"{response.text[:500]}"
        )

        events = 0
        got_done = False
        finish_reasons: List[str] = []
        tool_args: Dict[int, Dict[str, Any]] = {}
        tool_delta_events = 0
        max_gap = 0.0
        max_gap_at_event = None
        prev_ts: Optional[float] = None
        ttft: Optional[float] = None
        usage: Dict[str, Any] = {}
        stream_error = None

        try:
            for line in response.iter_lines():
                if time.time() - started > K42_TOTAL_LIMIT_S:
                    pytest.fail(
                        f"缺陷形态: 流式回放超总时限 "
                        f"{K42_TOTAL_LIMIT_S:.0f}s（报告方法 C 口径）"
                        f"仍未结束——events={events}, got_done="
                        f"{got_done}, finish_reasons="
                        f"{finish_reasons}, max_gap={max_gap:.3f}s"
                    )
                if not line:
                    continue
                now = time.time()
                if prev_ts is None:
                    ttft = now - started
                else:
                    gap = now - prev_ts
                    if gap > max_gap:
                        max_gap = gap
                        max_gap_at_event = events + 1
                prev_ts = now
                line_text = line.decode("utf-8")
                if not line_text.startswith("data: "):
                    continue
                data = line_text[6:]
                if data == "[DONE]":
                    got_done = True
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    test_logger.warning(
                        f"非 JSON SSE 事件（留证）: {data[:200]!r}"
                    )
                    continue
                events += 1
                evt_usage = event.get("usage")
                if isinstance(evt_usage, dict):
                    usage.update(evt_usage)
                for choice in event.get("choices") or []:
                    if choice.get("finish_reason"):
                        finish_reasons.append(choice["finish_reason"])
                    delta = choice.get("delta") or {}
                    for tc in delta.get("tool_calls") or []:
                        idx = tc.get("index", 0)
                        slot = tool_args.setdefault(
                            idx, {"name": "", "args": "", "segments": 0}
                        )
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] += fn["name"]
                        if fn.get("arguments"):
                            slot["args"] += fn["arguments"]
                            slot["segments"] += 1
                            tool_delta_events += 1
        except requests.exceptions.ReadTimeout:
            stream_error = (
                f"永久停流形态: 读空闲 {K42_READ_IDLE_TIMEOUT_S}s 无任"
                f"何字节（缺陷复现——TTFT={ttft!r}, events={events}, "
                f"got_done={got_done}, finish_reasons={finish_reasons}"
            )
        except requests.exceptions.RequestException as e:
            stream_error = (
                f"连接异常终止形态（无正常 DONE）: {e!r}（TTFT="
                f"{ttft!r}, events={events}, got_done={got_done}, "
                f"finish_reasons={finish_reasons}"
            )
        total_elapsed = time.time() - started

        if stream_error:
            pytest.fail(
                f"{stream_error}, elapsed={total_elapsed:.1f}s, "
                f"max_gap={max_gap:.3f}s"
            )

        # 断言1（补足）：SSE 事件流非空
        assert events > 0, (
            f"缺陷形态: 200 但空事件流（无任何 SSE data 事件）, "
            f"got_done={got_done}, elapsed={total_elapsed:.1f}s"
        )

        # 断言2：正常终止——非空 finish_reason + [DONE]（工单缺陷
        # 形态=两者皆无直至客户端 30s 空闲取消断开）
        assert finish_reasons and finish_reasons[-1], (
            f"缺陷形态: 未收到 finish_reason（工单形态——流静默至客户"
            f"端断开，无正常结束标记）, TTFT={ttft!r}, events="
            f"{events}, got_done={got_done}, elapsed="
            f"{total_elapsed:.1f}s"
        )
        assert got_done, (
            f"缺陷形态: 未收到 [DONE]（工单形态——流静默至客户端断"
            f"开）, finish_reasons={finish_reasons}, events={events}, "
            f"elapsed={total_elapsed:.1f}s"
        )

        # 断言3：全程任意相邻 SSE 事件间隔 < 30s（客户取消阈值；
        # 缺陷实测 71.7-116.7s 空窗；TTFT 不计入——首 token 问题
        # 报告声明另行排查）
        assert max_gap < K42_MAX_EVENT_GAP_S, (
            f"缺陷复现: 最大事件间隔 {max_gap:.3f}s 超客户取消阈值 "
            f"{K42_MAX_EVENT_GAP_S:.0f}s（第 {max_gap_at_event} 个事件"
            f"前——工单形态：长参数阶段解析器整包缓冲、SSE 无新数"
            f"据）, finish_reasons={finish_reasons}, events={events}, "
            f"TTFT={ttft!r}, elapsed={total_elapsed:.1f}s"
        )

        # 断言4：finish=tool_calls 时逐 tool index 拼接 arguments
        # 为完整 JSON 且工具名非空（报告修复验证标准 4——严格校
        # 验，格式错误不伪装成功）
        if "tool_calls" in finish_reasons:
            assert tool_args, (
                f"缺陷形态: finish=tool_calls 但未收到任何工具调用 "
                f"delta: events={events}"
            )
            for idx, slot in sorted(tool_args.items()):
                assert slot["name"].strip(), (
                    f"缺陷形态: tool index {idx} 工具名为空（报告标准 "
                    f"4——工具名遗漏）: slot={slot!r}"
                )
                try:
                    json.loads(slot["args"])
                except json.JSONDecodeError as e:
                    pytest.fail(
                        f"缺陷形态: tool index {idx}（{slot['name']}）拼"
                        f"接后 arguments 非完整 JSON（报告标准 4）: "
                        f"{e}, args 尾部 200 字符: "
                        f"{slot['args'][-200:]!r}"
                    )

        # 观察记录（不计判据）：流式全貌——TTFT/事件数/最大间隔/
        # 工具增量形态/usage（include_usage）/时长
        tool_summary = "; ".join(
            f"index {idx}: {slot['name'] or '(空)'} 参数 "
            f"{len(slot['args'])} 字符/{slot['segments']} 段"
            for idx, slot in sorted(tool_args.items())
        ) or "（无工具调用）"
        test_logger.info(
            f"观察: TTFT={ttft!r}, events={events}, 最大事件间隔="
            f"{max_gap:.3f}s（第 {max_gap_at_event} 个事件前）, "
            f"finish_reasons={finish_reasons}, got_done={got_done}, "
            f"工具参数增量事件数={tool_delta_events}, {tool_summary}"
        )
        test_logger.info(
            f"观察: usage={usage}, elapsed={total_elapsed:.1f}s（总时"
            f"限内）——工具参数增量事件数>=2 且 max_gap<30s 即为修复"
            f"标准 2/3 的直接证据"
        )
        test_logger.info(
            "客户问题整改验证通过: Kimi-K3 长工具参数流式回放全程无 "
            "30s 级空窗（客户取消阈值内）且正常终止（finish+"
            "[DONE]）——工具解析器整包缓冲长参数致流式静默停流缺陷"
            "未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p1
    def test_responses_empty_input_rejected(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K43 [P1]: 客户问题 - responses 端点空 input 400 拒绝核
        验（对齐官方，responses 单协议）

        客户问题（工单 AGDC2-55 · alayanew vs 智谱官方未对齐
        #48）：相同请求 POST /v1/responses {"model": "glm-5.3",
        "input": [{"role": "user", "content": [{"type": "input_
        text", "text": ""}]}], "max_output_tokens": 32}，alayanew 返
        回 200（错误——空 input 文本被接受并生成 reasoning 内容，
        status=incomplete/incomplete_details.reason=max_output_
        tokens，usage output_tokens=32），智谱官方返回 400
        {"error": {"code": "invalid_request", "message": "输入不能
        为空", "type": "invalid_request"}}。
        预期（对齐官方）：400 拒绝，错误体 code=invalid_request、
        message 含「输入不能为空」。
        本用例单发非流式原样请求（请求体全部工单原样，仅 model 环
        境注入；responses 端点 staging 网关已有——报文实证）。
        判定（单发，三断言）：
        1. 断言1：HTTP 400（200=缺陷复现——空输入被接受，响应结
           构 status/incomplete_details/output/usage 留证）
        2. 断言2：错误体 code=="invalid_request"
        3. 断言3：message 含「输入不能为空」（对齐官方原文）
        观察（不计判据）：400 时错误体全文；200 时缺陷响应结构留
        证。超时沿用全局（工单未涉及挂死/超时语义）。responses 单
        协议（缺陷为 responses 端点空输入校验缺失；chat 端点无
        关）。GLM-5.3 专用（工单模型 glm-5.3）。无新增数据文件
        （请求短小完整内联）。（不进 smoke 集：新用例首跑观察
        期；1 请求）
        """
        test_logger.info(
            "=== 测试开始: 客户问题 - responses 端点空 input 400 拒"
            "绝核验（工单 #48：alayanew 200/官方 400——预期对齐官方 "
            "400 invalid_request「输入不能为空」；单发非流式，请求体"
            "全部工单原样，仅 model 环境注入）==="
        )

        # K43: 工单原样请求体（#48 完整可见——字段序 model/input/
        # max_output_tokens；空 input_text 为缺陷触发参数）
        payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": ""}],
                }
            ],
            "max_output_tokens": 32,
        }

        TestLogger.log_request(
            test_logger,
            [
                {
                    "role": "user",
                    "content": (
                        '[responses input] [{"type": "input_text", '
                        '"text": ""}]——空 input_text（工单原样）'
                    ),
                }
            ],
            {
                "endpoint": "/v1/responses",
                "input": '[{"role": "user", "content": [{"type": "input_text", "text": ""}]}]（工单原样）',
                "max_output_tokens": "32（工单原样）",
                "stream": "(工单未含——不传，非流式默认)",
            },
        )

        # K43: 单发直发（参数校验确定性；超时沿用全局——工单未涉及
        # 挂死语义）
        responses_url = f"{api_client.api_prefix}/responses"
        start_time = time.time()
        response = api_client._post_with_retry(
            responses_url, payload, stream=False
        )
        elapsed = time.time() - start_time
        status = response.status_code
        body_text = response.text

        # K43: 真实响应断言前留痕——200 时按 alayanew 缺陷形态归类
        if status == 200:
            test_logger.info(
                f"真实响应: HTTP {status}, elapsed={elapsed:.1f}s, "
                f"缺陷形态归类: 空 input 被接受并生成内容（alayanew 形"
                f"态）, 响应体全文: {body_text}"
            )
        else:
            test_logger.info(
                f"真实响应: HTTP {status}, elapsed={elapsed:.1f}s, "
                f"响应体全文: {body_text}"
            )

        # 断言1：HTTP 400（200=缺陷复现——空输入被接受）
        assert status == 400, (
            f"缺陷复现: responses 端点空 input_text 请求未被拒绝（预期"
            f"对齐官方 400 invalid_request「输入不能为空」——alayanew "
            f"返回 HTTP {status}），elapsed={elapsed:.1f}s, 响应体全文: "
            f"{body_text}"
        )

        # 断言2/3：错误体 code=="invalid_request" 且 message 含「输
        # 入不能为空」（对齐官方原文）
        try:
            err_data = response.json()
        except ValueError:
            err_data = None
        err = (err_data or {}).get("error") or {}
        assert err.get("code") == "invalid_request", (
            f"错误码未对齐官方: error.code={err.get('code')!r}（预期 "
            f"invalid_request），HTTP {status}, 响应体全文: {body_text}"
        )
        err_msg = str(err.get("message") or "")
        assert "输入不能为空" in err_msg, (
            f"错误文案未对齐官方: error.message={err_msg!r}（预期含"
            f"「输入不能为空」），HTTP {status}, 响应体全文: {body_text}"
        )

        test_logger.info(
            "客户问题整改验证通过: responses 端点空 input_text 请求被 "
            "HTTP 400 拒绝且错误体对齐官方（invalid_request/「输入不"
            "能为空」）——空输入校验缺失缺陷未复现"
        )

    @pytest.mark.k_customer_issue
    @pytest.mark.GLM53
    @pytest.mark.p1
    def test_reasoning_effort_none_accepted(
        self, api_client: ModelAPIClient, test_logger
    ):
        """K44 [P1]: 客户问题 - reasoning_effort="none" 应被接受核
        验（对齐官方，chat 单协议）

        客户问题（工单 AGDC2-55 · alayanew vs 智谱官方未对齐
        #10）：相同请求 POST /v1/chat/completions（确认参数
        max_completion_tokens=128 + reasoning_effort="none"——标题
        与 alayanew 错误文案双重佐证；原始消息 349,732 字符被截断
        不可得，缺陷为参数校验层与消息内容无关），alayanew 返回
        400 {"code": 1210, "message": "reasoning_effort 取值非法:
        none（glm-5.3 仅支持 low / high / max）"}，智谱官方返回
        200（finish=stop，正文非空，reasoning_content 非空 18
        tokens——官方接受 none 并正常生成）。
        预期（对齐官方）：200 正常响应。
        本用例单发非流式：请求体 = 工单确认参数 max_completion_
        tokens=128 + reasoning_effort="none" 原样 + 自拟最小 user
        消息（工单消息不可得且不影响缺陷路径）；模型名由环境注入；
        两侧工单响应均非流式形态——stream 不传（不注入）。
        判定（单发，四断言）：
        1. 断言1：HTTP 200（400=缺陷复现——1210「reasoning_effort
           取值非法: none（glm-5.3 仅支持 low / high / max）」文案
           留证）
        2. 断言2：合法 JSON + choices 非空
        3. 断言3：finish_reason 非空（对齐官方 stop 形态）
        4. 断言4：正文非空
        观察（不计判据）：reasoning_content 存在性/reasoning_tokens
        （官方 none 仍返回 18 reasoning tokens 的形态留痕——none 语
        义为不声明思考努力档位，官方仍产出思考）；400 时错误全文留
        证。超时沿用全局。chat 单协议（缺陷为 chat 参数校验过度严
        格）。GLM-5.3 专用（工单模型 glm-5.3）。无新增数据文件。
        （不进 smoke 集：新用例首跑观察期；1 请求）
        """
        # K44: 工单消息被截断不可得——自拟最小 user 消息（缺陷为参
        # 数校验层，与消息内容无关）
        K44_PROMPT = "Reply with a single word: OK"

        test_logger.info(
            "=== 测试开始: 客户问题 - reasoning_effort=\"none\" 应被"
            "接受核验（工单 #10：alayanew 400/官方 200——预期对齐官方 "
            "200 正常响应；单发非流式，工单确认参数 max_completion_"
            "tokens=128+reasoning_effort=\"none\" 原样+自拟最小消息）==="
        )

        # K44: 请求体（工单确认参数原样：max_completion_tokens=128 +
        # reasoning_effort="none"；stream 不传——不注入）
        payload: Dict[str, Any] = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": K44_PROMPT}],
            "max_completion_tokens": 128,
            "reasoning_effort": "none",
        }

        TestLogger.log_request(
            test_logger,
            [{"role": "user", "content": K44_PROMPT}],
            {
                "endpoint": "/v1/chat/completions",
                "max_completion_tokens": "128（工单确认参数原样）",
                "reasoning_effort": "none（工单确认参数原样——缺陷触发参数）",
                "messages": "(自拟最小——工单消息 349,732 字符被截断不可得)",
                "stream": "(工单两侧响应均非流式——不传，非流式默认)",
            },
        )

        # K44: 单发直发（参数校验确定性；超时沿用全局）
        chat_url = f"{api_client.api_prefix}/chat/completions"
        start_time = time.time()
        response = api_client._post_with_retry(
            chat_url, payload, stream=False
        )
        elapsed = time.time() - start_time
        status = response.status_code
        body_text = response.text

        # K44: 真实响应断言前留痕——400 时按工单 1210 文案归类
        if status == 200:
            test_logger.info(
                f"真实响应: HTTP {status}, elapsed={elapsed:.1f}s"
            )
        else:
            defect_kind = (
                "参数校验过度拒绝形态（1210 reasoning_effort 取值非法: "
                "none）"
                if ("reasoning_effort 取值非法: none" in body_text
                    or "1210" in body_text)
                else "未归类形态——留证交人工分派"
            )
            test_logger.info(
                f"真实响应: HTTP {status}, elapsed={elapsed:.1f}s, "
                f"缺陷形态归类: {defect_kind}, 响应体全文: {body_text}"
            )

        # 断言1：HTTP 200（400=缺陷复现——参数被过度拒绝）
        assert status == 200, (
            f"缺陷复现: reasoning_effort=\"none\" 请求被 HTTP {status} "
            f"拒绝（预期对齐官方 200 正常响应——工单形态：1210 "
            f"reasoning_effort 取值非法: none（glm-5.3 仅支持 low / "
            f"high / max）），elapsed={elapsed:.1f}s, 响应体全文: "
            f"{body_text}"
        )

        # 断言2：合法 JSON + choices 非空
        try:
            data = response.json()
        except ValueError:
            data = None
        choices = (data or {}).get("choices") or []
        assert choices, (
            f"响应体异常（非法 JSON/choices 空）: {body_text}"
        )

        choice0 = choices[0] or {}
        message = choice0.get("message") or {}
        content = message.get("content") or ""
        finish_reason = choice0.get("finish_reason")

        # 断言3：finish_reason 非空（对齐官方 stop 形态——正常结束）
        assert finish_reason, (
            f"缺陷形态: finish_reason 为空（预期正常结束——对齐官方 "
            f"stop），HTTP {status}, 响应体全文: {body_text}"
        )

        # 断言4：正文非空（对齐官方正常生成形态）
        assert str(content).strip(), (
            f"缺陷形态: 正文为空（预期正常响应非空正文——对齐官方 "
            f"200 形态），finish_reason={finish_reason!r}, 响应体全文: "
            f"{body_text}"
        )

        # 观察记录（不计判据）：reasoning_content 存在性/
        # reasoning_tokens（官方 none 仍返回 18 reasoning tokens 的形
        # 态留痕）
        reasoning_content = message.get("reasoning_content")
        usage = (data or {}).get("usage") or {}
        details = usage.get("completion_tokens_details")
        reasoning_tokens = (
            details.get("reasoning_tokens")
            if isinstance(details, dict)
            else None
        )
        if reasoning_tokens is None:
            reasoning_tokens = usage.get("reasoning_tokens")
        test_logger.info(
            f"观察: finish_reason={finish_reason!r}, 正文 "
            f"{len(str(content).strip())} 字符, reasoning_content "
            f"{'存在' if reasoning_content else '缺失/空'}, "
            f"reasoning_tokens={reasoning_tokens!r}（官方 none 仍 18 "
            f"reasoning tokens 形态留痕，观察不计判据）"
        )
        test_logger.info(
            "客户问题整改验证通过: reasoning_effort=\"none\" 请求被接"
            "受且正常响应（finish_reason 非空+正文非空）——参数校验过"
            "度拒绝（1210）缺陷未复现"
        )
