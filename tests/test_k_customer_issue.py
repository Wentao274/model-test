"""
K. 客户问题复现测试

本测试类专门收录来自客户反馈的真实问题，将客户提供的 curl 命令还原为
标准模型请求进行复现与回归验证。优先级按客户工单标定：K1-K7、K10-K20
为 P0（任何失败应阻断发布），K8/K9 为 P1。

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
  可正常接受该 Schema 并返回合法的强制工具调用结果。
- K2: 同一请求循环执行5次返回信息异常 [P0]
  客户问题：同一 curl 命令循环执行 5 次左右出现返回信息异常。
  请求特征：logprobs+top_logprobs+n+thinking+stream+stream_options+
  frequency_penalty/presence_penalty+user 字段 + X-Cache-Buster 防缓存请求头。
  本用例按客户原始 curl 原样复现并连续执行 5 次（相邻间隔 3s），断言每次的响应与内容均正常。
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
  thinking——GLM-5.3-Flash 默认思考，不做思考断言；采样参数不豁
  免（用户指令）——由全局 SAMPLING_PARAMS（Jenkinsfile，经
  --sampling-params 注入）覆盖：temperature 全局值优先（原始脚
  本口径 0 为无覆盖时的回退值），top_p/seed 未显式指定时注入）。
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
  0、max_tokens=2048、非流式、不传 thinking）。json_object 轮按
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
  temperature=0、max_tokens=2048、非流式、不传 thinking；顶层
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
  "low"、stop=["橘子"]、其余采样参数不发送（通过 RAW_SAMPLING_
  PARAM_TESTS 豁免全局覆盖）；KimiK3 环境不传 thinking/
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
  "{\"weather\":\"晴\"}"，stream=true，无 tools/thinking/采样参
  数——通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）。硬断言：
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
  （通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）。（不进 smoke
  集：新用例首跑观察期）
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
  cached_tokens 总和/prompt_tokens 总和 ≥90%。GLM-5.3 与
  GLM-5.3-Flash 断言  一致，非流式、不发送采样参数（通过
  RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）。（不进 smoke 集：
  新用例首跑观察期）
- K17: stop 停止符（换行符）在推理阶段生效 [P0]
  客户契约：指定停止符为换行符 "\n" 并开启思考时，停止符同样作用
  于推理（reasoning）输出——推理里出现的第一个换行即触发停止，
  正文（content）不会生成；反之若换行未触发停止、继续输出正文，
  则换行符未生效。本用例按该场景构造（GLM-5.3：
  thinking={"type":"enabled"} 显式开启思考（K1 口径）；
  stream=true、stop=["\n"]、
  max_tokens=512 仅作防御性预算（正常应在推理早期触发停止）、其余
  采样参数不发送——通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）。
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
  JSON，按工单原样保留）。修复：解析失败后同列表有真实调用时移
  除空占位项再重新校验；缺 "{" 的 arguments 原样保留（不补）；
  兼容 assistant 历史重复的 reasoning_content/reasoning_context
  （保留最后一个值）。本用例按工单还原该 assistant 消息回填为多
  轮上下文（user→assistant(空占位+bash 调用+reasoning 双字段)→
  user 追问，带 bash 工具定义，非流式），硬断言 HTTP 200+choices
  存在+message 结构存在——上次输出 JSON 必须可作为下次输入上下
  文，报错复现即 FAIL。不断言 arguments 被补 "{"（修复明确不
  补）与占位被移除（router 内部行为）。GLM-5.3 专用；采样参数
  不豁免——由全局 SAMPLING_PARAMS 覆盖（temperature 无覆盖时回
  退 0.7、top_p/seed 注入）。docx 中 role 拼写 "assitant" 判定为
  笔误（报错与修复均不涉及 role），按标准 assistant 还原。
  usage 仅日志。（不进 smoke 集：新用例首跑观察期）
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
  息不含该模式（信息不恰当）均 FAIL。GLM-5.3-Flash 专用；不发
  送采样参数（通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）。
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
  tokens（自校准计量）+ 输出 max_tokens=1024 且 reasoning_effort=
  low（GLM-5.3 不支持禁用思考、仅支持档位——用户口径；low 最小
  化思考，预算覆盖思考+正文——真实环境实测默认档思考耗尽 32 预
  算致 content 为空）
  → 总消耗 ≈961K，两种 1M 口径（1,000,000/1,048,576）下均略
  小于 1M，且高于原始故障上限 781,754 约 178K（缺陷可复现），
  单条 user 消息非流式提交，硬断言：探针 200 且返回 usage；主请
  求 HTTP 200（未被拒绝）；choices 非空且 content 非空（可正常
  响应）；主响应 usage.prompt_tokens（如有）> 781,754（规模
  sanity——确保真正压过原始故障点）——1M 量级输入正常响应则
  PASS，被拒（原始报错形态）或空响应均 FAIL。1M token prefill
  耗时长，临时将客户端超时上调至 900s（finally 恢复；ReadTimeout
  不重试——框架约定）。请求提示词由程序生成（无外部文件）。不
  发送采样参数（RAW_SAMPLING_PARAM_TESTS 豁免）。模型真实响应
  （状态码/响应体全文）断言前打印（失败时同样可见）；usage 仅
  日志。（不进 smoke 集：新用例首跑观察期）
"""

import base64
import json
import math
import struct
import time
import uuid
import zlib
import pytest
import requests
from typing import Any, Dict, List

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
    @pytest.mark.smoke
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
            pytest.fail(
                f"Tool call arguments is not valid JSON: {args_raw[:500]}, error: {e}"
            )

        # schema 必填项校验：required = ["core_work_type"]
        assert "core_work_type" in args, (
            f"Tool arguments missing required field 'core_work_type': {args}"
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
    @pytest.mark.smoke
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
    @pytest.mark.smoke
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

        # 专用预算客户端（F8 先例）：短超时 + retry_times=0，保证未修复时
        # 单次最坏耗时 = 单次预算而非预算×(重试+1)；构造时只透传鉴权与
        # 模型，不携带全局采样参数，保持客户原始参数面
        budget_client = ModelAPIClient(
            api_key=api_client.api_key,
            base_url=api_client.base_url,
            model_name=api_client.model_name,
            timeout=K4_RESPONSE_BUDGET_SECONDS,
            config=api_client.config,
            retry_times=0,
        )
        url = f"{budget_client.base_url}/v1/chat/completions"

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
            # max_tokens。chat_completion 封装会强制注入默认 max_tokens=2048
            # 与 temperature，破坏"不传 max_tokens"的前提，故按 K3 先例
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
                pytest.fail(
                    f"第 {index}/{len(K4_USER_PROMPTS)} 次响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )

            choices = result.get("choices") or []
            assert choices, (
                f"第 {index}/{len(K4_USER_PROMPTS)} 次响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
    @pytest.mark.smoke
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

        url = f"{api_client.base_url}/v1/chat/completions"

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
                pytest.fail(
                    f"第 {index}/{len(K5_USER_PROMPTS)} 次响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )

            choices = result.get("choices") or []
            assert choices, (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
            assert not reasoning_text.strip(), (
                f"第 {index}/{len(K5_USER_PROMPTS)} 次客户问题复现失败："
                f"thinking.type=disabled 后仍返回思考内容（官方实测应无 "
                f"reasoning_content），思考内容长度 {len(reasoning_text)}，"
                f"预览: {reasoning_text[:60]}，消息: {prompt[:30]}"
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
    @pytest.mark.smoke
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

        url = f"{api_client.base_url}/v1/chat/completions"

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
                    pytest.fail(
                        f"场景[{label}] 响应不是合法 JSON: {e}. "
                        f"响应体: {response.text[:300]}"
                    )
                choices = result.get("choices") or []
                assert choices, (
                    f"场景[{label}] 响应缺少 choices: "
                    f"{json.dumps(result, ensure_ascii=False)[:500]}"
                )
                content = (
                    (choices[0].get("message") or {}).get("content") or ""
                ).strip()
                # 合法组合应正常生成正文（enabled 场景可能含
                # reasoning_content，属正常思考输出，不在本用例断言范围
                # ——关思考本身由 K5 验证）
                assert content, (
                    f"场景[{label}] 客户问题复现失败：合法组合应正常返回正文，"
                    f"实际正文为空: {json.dumps(result, ensure_ascii=False)[:300]}"
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
                assert response.status_code == 400, (
                    f"场景[{label}] 客户问题复现失败：官方契约应 400 拒绝"
                    f"（错误信息含 '{expected_msg}'），实际 HTTP "
                    f"{response.status_code}: {response.text[:300]}"
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

        url = f"{api_client.base_url}/v1/chat/completions"
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
                pytest.fail(
                    f"第[{index}]次（reasoning_effort={effort}）响应不是"
                    f"合法 JSON: {e}. 响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"第[{index}]次（reasoning_effort={effort}）响应缺少 "
                f"choices: {json.dumps(result, ensure_ascii=False)[:500]}"
            )
            message = choices[0].get("message") or {}
            content = (message.get("content") or "").strip()
            assert content, (
                f"第[{index}]次（reasoning_effort={effort}）正文为空: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
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

            assert response.status_code == 400, (
                f"第[{index}]次（嵌套 thinking.effort=medium）预期 400 "
                f"拒绝（废弃的 K2.x thinking 配置下 medium 为非法"
                f"档位），实际 HTTP {response.status_code}: "
                f"{response.text[:300]}"
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

        url = f"{api_client.base_url}/v1/chat/completions"

        def run_round(
            label: str, thinking_type: str, temperature: float,
            max_tokens: int,
        ) -> None:
            """K8 单轮：required+有工具意图，断言必须调用工具且预算不被吃满"""
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
            # 档位温度，chat_completion 封装会强制覆盖 max_tokens/
            # temperature）
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
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"[{label}] 响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls")
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            # usage 为预算断言数据源，缺失即失败
            assert usage, (
                f"[{label}] 客户问题复现失败：响应缺少 usage——预算"
                f"断言无从进行: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
            assert tool_calls, (
                f"[{label}] 客户问题复现失败：required 下未发起工具"
                f"调用——tool_calls 键缺失（finish={finish}、ct={ct}/"
                f"{max_tokens}；缺陷形态：finish=length、completion_"
                f"tokens 恒吃满 max_tokens、正文仅 OK）: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )
            first = tool_calls[0] or {}
            fn = first.get("function") or {}
            assert (
                first.get("type") == "function"
                and fn.get("name") == "get_weather"
            ), (
                f"[{label}] 客户问题复现失败：工具调用形状异常（应 "
                f"function/get_weather，实际 "
                f"{json.dumps(first, ensure_ascii=False)[:200]}）"
            )
            try:
                fn_args = json.loads(fn.get("arguments") or "")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                pytest.fail(
                    f"[{label}] 客户问题复现失败：工具调用 arguments "
                    f"不是合法 JSON: {e}（{fn.get('arguments')!r}）"
                )
            assert isinstance(fn_args, dict), (
                f"[{label}] 客户问题复现失败：工具调用 arguments 应为"
                f" JSON 对象: {fn.get('arguments')!r}"
            )

            # 断言2：finish 必须为 tool_calls（length 即 token 预算
            # 被消耗殆尽的缺陷形态——关/开思考均不允许，断言不分模式）
            assert finish == "tool_calls", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"tool_calls（required 必须调用工具），实际 {finish}"
                f"（ct={ct}/{max_tokens}、rt={rt}——token 被消耗殆尽"
                f"的缺陷形态）: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
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

        url = f"{api_client.base_url}/v1/chat/completions"

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
            # 档位温度，chat_completion 封装会强制覆盖 max_tokens/
            # temperature）
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
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"[{label}] 响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls")
            finish = choices[0].get("finish_reason")
            usage = result.get("usage") or {}

            # usage 为预算断言数据源，缺失即失败
            assert usage, (
                f"[{label}] 客户问题复现失败：响应缺少 usage——预算"
                f"断言无从进行: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
            assert tool_calls, (
                f"[{label}] 客户问题复现失败：required 下闲聊未强制"
                f"发起工具调用——tool_calls 键缺失（finish={finish}、"
                f"ct={ct}/{max_tokens}；官方行为为 finish=tool_calls"
                f" 强制返回 get_weather，Alaya 缺陷形态为 finish="
                f"length、reasoning 吃满预算、tool_calls=None）: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )
            first = tool_calls[0] or {}
            fn = first.get("function") or {}
            assert (
                first.get("type") == "function"
                and fn.get("name") == "get_weather"
            ), (
                f"[{label}] 客户问题复现失败：工具调用形状异常（应 "
                f"function/get_weather，实际 "
                f"{json.dumps(first, ensure_ascii=False)[:200]}）"
            )
            try:
                fn_args = json.loads(fn.get("arguments") or "")
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                pytest.fail(
                    f"[{label}] 客户问题复现失败：工具调用 arguments "
                    f"不是合法 JSON: {e}（{fn.get('arguments')!r}）"
                )
            assert isinstance(fn_args, dict), (
                f"[{label}] 客户问题复现失败：工具调用 arguments 应为"
                f" JSON 对象: {fn.get('arguments')!r}"
            )

            # 断言2：finish 必须为 tool_calls（官方行为；而非 length）
            assert finish == "tool_calls", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"tool_calls（required 必须调用工具），实际 {finish}"
                f"（ct={ct}/{max_tokens}、rt={rt}）: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
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
        言；采样参数不豁免（用户指令）——由全局 SAMPLING_PARAMS
        （Jenkinsfile，经 --sampling-params 注入）覆盖：temperature
        全局值优先（原始脚本口径 0 为无覆盖时的回退值），top_p/
        seed 未显式指定时注入；reasoning_effort 不在此列，保持原
        始口径不传）。工具两个：get_weather(city)+
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
            "=== 测试开始: 客户问题 - GLM-5.3-Flash tool_choice 四种"
            "模式支持（auto/required/named/none；mt=2048、非流式、"
            "不传 thinking，按原始脚本口径；采样参数不豁免——由全局"
            " SAMPLING_PARAMS 覆盖（temperature=0 为无覆盖时回退"
            "值）；named 指定与天气意图不同向的 get_current_time "
            "以验证强制语义）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        def run_round(
            label: str, tool_choice: Any, prompt: str, expect: str
        ) -> None:
            """K10 单轮：按 tool_choice 模式断言语义生效"""
            # 手工构造 payload 直发（需 tools/tool_choice 直进 payload；
            # 采样参数不豁免（用户指令）——由全局 SAMPLING_PARAMS
            # （Jenkinsfile，经 conftest 注入 client）覆盖：
            # temperature 全局值优先（原始脚本口径 0 为无覆盖时的回退
            # 值），top_p/seed 未显式指定时注入；reasoning_effort 不在
            # 此列，保持原始口径不传）
            sampling_extra: Dict[str, Any] = {}
            if api_client.top_p is not None:
                sampling_extra["top_p"] = api_client.top_p
            if api_client.seed:
                try:
                    sampling_extra["seed"] = int(api_client.seed)
                except (ValueError, TypeError):
                    sampling_extra["seed"] = api_client.seed
            payload = {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "tools": K10_TOOLS,
                "tool_choice": tool_choice,
                "max_tokens": 2048,
                "temperature": api_client._effective_temperature(0),
                "stream": False,
                **sampling_extra,
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
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"[{label}] 响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
                    f"{json.dumps(first, ensure_ascii=False)[:200]}）"
                )
                try:
                    fn_args = json.loads(fn.get("arguments") or "")
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    pytest.fail(
                        f"[{label}] 客户问题复现失败：工具调用 arguments "
                        f"不是合法 JSON: {e}（{fn.get('arguments')!r}）"
                    )
                assert isinstance(fn_args, dict), (
                    f"[{label}] 客户问题复现失败：工具调用 arguments 应为"
                    f" JSON 对象: {fn.get('arguments')!r}"
                )
                return fn.get("name")

            if expect == "no_call":
                # 断言（none）：禁止调用工具，正文正常回复
                assert not tool_calls, (
                    f"[{label}] 客户问题复现失败：tool_choice=none 下仍"
                    f"发起工具调用（none 语义未生效）: "
                    f"{json.dumps(result, ensure_ascii=False)[:300]}"
                )
                assert content, (
                    f"[{label}] 客户问题复现失败：tool_choice=none 下"
                    f"正文为空（应正常文本回复）: "
                    f"{json.dumps(result, ensure_ascii=False)[:300]}"
                )
                assert finish == "stop", (
                    f"[{label}] 客户问题复现失败：tool_choice=none 下"
                    f"finish_reason 应为 stop，实际 {finish}: "
                    f"{json.dumps(result, ensure_ascii=False)[:300]}"
                )
            else:
                # 断言（auto/required/named）：必须发起工具调用
                assert tool_calls, (
                    f"[{label}] 客户问题复现失败：该模式下未发起工具"
                    f"调用（模式不被支持/语义未生效，finish="
                    f"{finish}）: "
                    f"{json.dumps(result, ensure_ascii=False)[:300]}"
                )
                called = check_call_shape(tool_calls)
                assert finish == "tool_calls", (
                    f"[{label}] 客户问题复现失败：finish_reason 应为 "
                    f"tool_calls，实际 {finish}: "
                    f"{json.dumps(result, ensure_ascii=False)[:300]}"
                )
                if expect == "call_named":
                    # 断言（named）：必须调用指定工具（与提示词意图
                    # 不同向，named 未生效时模型按意图调 get_weather
                    # 即在此被检出）
                    named_name = tool_choice["function"]["name"]
                    assert called == named_name, (
                        f"[{label}] 客户问题复现失败：named 指定 "
                        f"{named_name} 但实际调用 {called}（named 强"
                        f"制语义未生效，按提示词意图选择了工具）: "
                        f"{json.dumps(result, ensure_ascii=False)[:300]}"
                    )

        for label, tool_choice, prompt, expect in K10_ROUNDS:
            run_round(label, tool_choice, prompt, expect)

        test_logger.info(
            "客户问题复现通过: GLM-5.3-Flash tool_choice 四种模式"
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
            "=== 测试开始: 客户问题 - GLM-5.3-Flash response_format "
            "三种模式支持（json_object/json_schema/text；temperature="
            "0、mt=2048、非流式、不传 thinking，按原始脚本口径）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

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

            # 手工构造 payload 直发（需 response_format/temperature=0，
            # chat_completion 封装会强制覆盖 max_tokens/temperature）
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
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"[{label}] 响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
                f"[{label}] 客户问题复现失败：正文为空: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )
            assert finish == "stop", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"stop，实际 {finish}: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )

            # 断言2：模式语义（json_object/json_schema 输出结构化
            # JSON；text 纯文本不强制 JSON）
            if expect in ("json_object", "json_schema"):
                try:
                    parsed = json.loads(content)
                except (json.JSONDecodeError, ValueError) as e:
                    pytest.fail(
                        f"[{label}] 客户问题复现失败：正文不是合法 "
                        f"JSON（结构化输出语义未生效，{e}）: "
                        f"{content[:200]!r}"
                    )
                assert isinstance(parsed, dict), (
                    f"[{label}] 客户问题复现失败：正文应为 JSON 对象"
                    f"（dict），实际 {type(parsed).__name__}: "
                    f"{content[:200]!r}"
                )
                if expect == "json_schema":
                    keys = set(parsed.keys())
                    assert keys == {"city", "temperature"}, (
                        f"[{label}] 客户问题复现失败：json_schema 正文"
                        f"键集合应为 {{city, temperature}}，实际 "
                        f"{sorted(keys)}: {content[:200]!r}"
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
            "客户问题复现通过: GLM-5.3-Flash response_format 三种"
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
            "=== 测试开始: 客户问题 - GLM-5.3-Flash reasoning_"
            "effort 档位支持（顶层/嵌套 chat_template_kwargs 两种"
            "放置 × low/high/max/空 四档；temperature=0、mt=2048、"
            "非流式、不传 thinking、chat_template_kwargs="
            "{clear_thinking:true}，按原始脚本口径）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

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
            # effort/chat_template_kwargs/temperature=0，chat_
            # completion 封装会强制覆盖 max_tokens/temperature；
            # 空档不发送 reasoning_effort 字段）
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
                pytest.fail(
                    f"[{label}] 响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )
            choices = result.get("choices") or []
            assert choices, (
                f"[{label}] 响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
                f"[{label}] 客户问题复现失败：正文为空: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )
            assert finish == "stop", (
                f"[{label}] 客户问题复现失败：finish_reason 应为 "
                f"stop，实际 {finish}: "
                f"{json.dumps(result, ensure_ascii=False)[:300]}"
            )

        for label, placement, effort in K12_ROUNDS:
            run_round(label, placement, effort)

        test_logger.info(
            "客户问题复现通过: GLM-5.3-Flash reasoning_effort 两种"
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
        stop=["橘子"]、其余采样参数不发送——客户原始请求体即如此，
        通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖），KimiK3 环境
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

        url = f"{api_client.base_url}/v1/chat/completions"

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
            f"实际 {finish}（content={content!r}）"
        )

        # 断言2（核心）：合并正文严格等于期望——多余前缀（如 ">"）、
        # 停止词泄漏、未截断均在此检出
        assert content == K13_EXPECTED, (
            f"客户问题复现失败：被截断正文应为 {K13_EXPECTED!r}，"
            f"实际 {content!r}（多余前缀/停止词泄漏/未截断）"
        )

        # 断言3：正文不含停止词（stop 语义遵循）
        assert "橘子" not in content, (
            f"客户问题复现失败：正文不应包含停止词 '橘子'，"
            f"实际 {content!r}"
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
        thinking/采样参数——客户原始请求体即如此，通过 RAW_SAMPLING_
        PARAM_TESTS 豁免全局覆盖；GLM-5.3 与 GLM-5.3-Flash 断言完
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

        url = f"{api_client.base_url}/v1/chat/completions"

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
                f"events={events}, reasoning/正文预览: "
                f"{preview[:120]!r}）"
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

        url = f"{api_client.base_url}/v1/chat/completions"

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

        url = f"{api_client.base_url}/v1/chat/completions"

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
        - 其余采样参数不发送（通过 RAW_SAMPLING_PARAM_TESTS 豁免
          全局覆盖）
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

        url = f"{api_client.base_url}/v1/chat/completions"

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
            f"换行处触发停止、正文不应生成，实际收到正文 "
            f"{content[:120]!r}（长度 {len(content)}）——换行符未生效"
            f"（推理继续并输出了正文；reasoning_len={len(reasoning)}, "
            f"finish={finish}）"
        )

        # 断言2：stop 触发（非 length/其他）
        assert finish == "stop", (
            f"客户问题复现失败：换行停止符应触发 finish_reason=stop，"
            f"实际 {finish}（content={content!r}, "
            f"reasoning_len={len(reasoning)}）"
        )

        # 断言3：合并 reasoning 不含换行（停止符前截断、不泄漏）
        assert "\n" not in reasoning, (
            f"客户问题复现失败：stop=[\"\\n\"] 下输出应在第一个换行"
            f"前截断，合并 reasoning 中出现换行（{len(reasoning)} "
            f"字符，前 120 字符 {reasoning[:120]!r}）——推理中的换行"
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
        发形态（docx 原样还原）：助手历史 tool_calls 列表混有
        1) 空占位调用：function.name=""、id=null、arguments="{}"
           （报错 missing field `name` 即指向它）；
        2) 真实 bash 调用：name="bash"、id="call_8af1ab36a4154c25"，
           arguments 为 '"command":"cd ... ", "description":
           "..."}'——缺开头 "{"、非合法 JSON（内部 data,json、SKlLL
           等怪字符均为工单原文，原样保留）。
        修复逻辑：解析失败后，同列表还有其他真实调用时移除空占位
        项、保留真实调用再重新校验；缺 "{" 的 arguments 原样保留
        （不补 "{"——通过 router 不代表该字符串成为合法参数
        JSON）；兼容 assistant 历史重复的 reasoning_content/
        reasoning_context（保留最后一个值）。
        本用例按工单还原该 assistant 消息回填为多轮上下文：
        user → assistant(空占位+bash 调用+reasoning 双字段并存) →
        user 追问，带 bash 工具定义，非流式。
        硬断言：
        1. HTTP 200（核心——上次输出 JSON 必须可作为下次请求的输
           入上下文，报错复现即 FAIL）
        2. choices 存在且非空
        3. message 结构存在（响应可正常生成）
        明确不断言：arguments 被补 "{"（修复明确不补）、空占位被
        移除（router 内部行为，响应不可见）。响应形态（正文/继续
        调用工具）宽松留日志——测试要点是上下文被接受。
        docx 中 role 拼写 "assitant" 判定为笔误（报错与修复均不涉
        及 role），按标准 assistant 还原。reasoning 同键字面重复
        无法经 dict 表达，以 reasoning_content + reasoning_context
        两拼写并存覆盖兼容路径。GLM-5.3 专用；采样参数不豁免——
        由全局 SAMPLING_PARAMS 覆盖（temperature 无覆盖时回退
        0.7、top_p/seed 注入）。usage 仅日志。（不进 smoke 集：
        新用例首跑观察期）
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
        # ——空占位调用（name=""、id=null、arguments="{}"）与真实
        # bash 调用（arguments 缺 "{"）同列表，reasoning 双拼写并
        # 存（重复 reasoning 字段兼容路径）
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
                    "function": {"arguments": "{}", "name": ""},
                    "id": None,
                    "type": "function",
                },
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
        K18_MAX_TOKENS = 512

        test_logger.info(
            "=== 测试开始: 客户问题 - 模型输出 JSON 回填为下次请求"
            "输入上下文（assistant 历史含空占位调用/缺 \"{\" 的 bash "
            "arguments/reasoning 双字段；修复后应被接受，报错复现即 "
            "FAIL）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        # 手工构造 payload 直发（需按工单原样还原 assistant 历史怪
        # 异结构，chat_completion 封装不支持）；采样参数不豁免（用户
        # 指令）——由全局 SAMPLING_PARAMS（Jenkinsfile，经 conftest
        # 注入 client）覆盖：temperature 全局值优先（无覆盖时回退
        # 0.7），top_p/seed 未显式指定时注入
        sampling_extra: Dict[str, Any] = {}
        if api_client.top_p is not None:
            sampling_extra["top_p"] = api_client.top_p
        if api_client.seed:
            try:
                sampling_extra["seed"] = int(api_client.seed)
            except (ValueError, TypeError):
                sampling_extra["seed"] = api_client.seed
        payload = {
            "model": api_client.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": "请分析工作区数据并生成技能周报图表。",
                },
                K18_ASSISTANT,
                {"role": "user", "content": "请继续完成任务。"},
            ],
            "tools": K18_TOOLS,
            "max_tokens": K18_MAX_TOKENS,
            "temperature": api_client._effective_temperature(0.7),
            "stream": False,
            **sampling_extra,
        }

        TestLogger.log_request(
            test_logger,
            payload["messages"],
            {
                "tools": [t["function"]["name"] for t in K18_TOOLS],
                "max_tokens": K18_MAX_TOKENS,
                "temperature": payload["temperature"],
                "top_p": payload.get("top_p", "(不注入)"),
                "seed": payload.get("seed", "(不注入)"),
                "stream": False,
                "assistant_history": (
                    "空占位调用(name=\"\", id=null) + bash 调用"
                    "(arguments 缺 \"{\") + reasoning 双字段"
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

        # 断言1（核心）：上次输出 JSON 可作为下次请求输入上下文——
        # 修复前此请求报 400（missing field `name`），报错复现即 FAIL
        assert response.status_code == 200, (
            f"客户问题复现失败：上次请求输出的 assistant JSON 应可"
            f"作为下次请求的输入上下文，实际 HTTP "
            f"{response.status_code}（工单原始报错：missing field "
            f"`name`；修复应移除空占位项后重新校验放行）: "
            f"{response.text[:400]}"
        )

        try:
            result = response.json()
        except (json.JSONDecodeError, ValueError) as e:
            pytest.fail(
                f"响应不是合法 JSON: {e}. 响应体: {response.text[:300]}"
            )

        # 断言2：choices 存在（上下文被接受且正常生成）
        choices = result.get("choices") or []
        assert choices, (
            f"响应缺少 choices: "
            f"{json.dumps(result, ensure_ascii=False)[:500]}"
        )
        message = choices[0].get("message")

        # 断言3：message 结构存在
        assert isinstance(message, dict), (
            f"响应 message 结构缺失: "
            f"{json.dumps(result, ensure_ascii=False)[:500]}"
        )

        content = message.get("content") or ""
        tool_calls = message.get("tool_calls")
        finish = choices[0].get("finish_reason")
        usage = result.get("usage") or {}

        TestLogger.log_response(test_logger, result, "K18-响应")
        test_logger.info(
            f"HTTP 200, elapsed={elapsed:.1f}s, finish={finish}, "
            f"content_len={len(content)}, tool_calls="
            f"{'有' if tool_calls else '无'}, usage="
            f"{json.dumps(usage, ensure_ascii=False)}"
        )
        test_logger.info(
            "客户问题复现通过: 上次输出 JSON 已被接受为下次请求的"
            "输入上下文（含空占位调用/缺 \"{\" 的 bash arguments/"
            "reasoning 双字段的 assistant 历史通过校验，正常生成响"
            "应）"
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
        被拒绝）。不发送采样参数（通过 RAW_SAMPLING_PARAM_TESTS
        豁免全局覆盖）。模型真实响应（状态码/响应体全文）在断言前
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

        url = f"{api_client.base_url}/v1/chat/completions"

        # 手工构造 payload 直发（多模态 image_url part 形态，封
        # 装不支持）；不发送采样参数（豁免全局覆盖）
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
        assert response.status_code != 200, (
            f"客户问题复现失败：单次请求携带 {K19_IMAGE_COUNT} 张图"
            f"（超过 serving 限额 {K19_IMAGE_LIMIT}）应被拒绝，实际"
            f" HTTP 200 放行（限额未生效）: "
            f"{response.text[:400]}"
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
          + 输出预算 max_tokens=1024 且 reasoning_effort=low
          （GLM-5.3 不支持禁用思考、仅支持档位——用户口径；low
          最小化思考，预算覆盖思考+正文。真实环境实测默认档思考
          耗尽 32 预算致 content 为空——预算过小的教训）→ 总消耗
          ≈961K，两种 1M 口径
          （1,000,000 / 1,048,576）下均略小于 1M（余量 39K/87K
          tokens；prompt_tokens 已含聊天模板等框架开销），且高
          于原始故障上限 781,754 约 178K（缺陷可复现）
        - 单条 user 消息非流式提交（程序生成，无外部文件）
        硬断言：
        1. 探针 200 且返回 usage.prompt_tokens（计量前提）
        2. 主请求 HTTP 200（未被拒绝——1M 量级输入应被接受）
        3. choices 非空且 content 非空（可正常响应）
        4. 主响应 usage.prompt_tokens（如有）> 781,754——规模
           sanity（确保真正压过原始故障点，防计量偏差）
        PASS：1M 量级输入正常响应；FAIL：被拒（原始报错形态）或
        空响应。
        超时处理：1M token prefill 耗时长，临时将客户端超时上调
        至 900s（finally 恢复；ReadTimeout 不重试——框架约定）。
        请求提示词由程序生成（无外部文件）。不发送采样参数
        （RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖）。模型真实响应
        （状态码/响应体全文）断言前打印（失败时同样可见，便于诊
        断）。usage/响应体仅日志。
        （不进 smoke 集：新用例首跑观察期）
        """
        # K20: 场景常量——1M = 输入+输出（用户口径），总量略小于 1M
        # （1,000,000 / 1,048,576 两种 1M 口径均满足；余量留给推理
        # 框架额外补充的长度——prompt_tokens 已含聊天模板等开销，
        # 输出预算 1024 计入总量）
        K20_TARGET_PROMPT_TOKENS = 960_000
        K20_MAX_TOKENS = 1024  # 输出预算（思考+正文，计入总量）
        K20_REASONING_EFFORT = "low"  # 思考强度档位（GLM-5.3 不支持禁用思考——用户口径）
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

        url = f"{api_client.base_url}/v1/chat/completions"

        test_logger.info(
            "=== 测试开始: 客户问题 - 1M 上下文请求应被正常支持"
            f"（探针自校准精确计量；目标输入 {K20_TARGET_PROMPT_TOKENS} "
            f"tokens + 输出 {K20_MAX_TOKENS}——输入+输出 略小于 1M；"
            f"期望 HTTP 200 + 非空正文）==="
        )

        # ---- 阶段1：探针自校准（精确测量每单元 token 数）----
        # 客户端无分词器，chars/token 启发式误差可达 ±30%——先发小
        # 规模探针，从 usage.prompt_tokens 精确得出每单元 token 数
        # （1M 契约判定的前提，主请求规模必须可靠）
        probe_content = K20_UNIT * K20_PROBE_UNITS
        probe_payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": probe_content}],
            "max_tokens": 1,
            "reasoning_effort": K20_REASONING_EFFORT,
            "stream": False,
        }
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
            pytest.fail(
                f"探针响应体非 JSON（{e}）: {probe_resp.text[:400]}"
            )
        probe_prompt_tokens = (probe_body.get("usage") or {}).get(
            "prompt_tokens"
        )
        assert probe_prompt_tokens, (
            "探针响应缺少 usage.prompt_tokens，无法精确计量 1M 目标"
            f"规模: {probe_resp.text[:400]}"
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

        # 手工构造 payload 直发（超长单消息形态）；不发送采样参数
        # （豁免全局覆盖）；GLM-5.3 不支持禁用思考、仅支持
        # reasoning_effort 档位（用户口径）——取 low 最小化思考，
        # 输出预算 1024 覆盖思考+正文（真实环境实测默认档思考对该
        # 指令约 40 tokens 即将收尾，low 档更短，1024 为充分余量）
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": K20_MAX_TOKENS,
            "reasoning_effort": K20_REASONING_EFFORT,
            "stream": False,
        }

        TestLogger.log_request(
            test_logger,
            [
                {
                    "role": "user",
                    "content": (
                        f"[程序生成背景材料 {len(content)} 字符"
                        f"（自校准预计 {predicted_tokens} tokens）"
                        f"+ 尾部指令]"
                    ),
                }
            ],
            {
                "predicted_prompt_tokens": predicted_tokens,
                "chars": len(content),
                "unit_repeats": main_units,
                "max_tokens": K20_MAX_TOKENS,
                "reasoning_effort": (
                    f"{K20_REASONING_EFFORT}"
                    "（GLM-5.3 不支持禁用思考——用户口径）"
                ),
                "stream": False,
                "temperature": "(不发送)",
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
            pytest.fail(f"请求发送异常（{url}）: {e}")
        finally:
            api_client.timeout = original_timeout
        elapsed = time.time() - started

        # 模型真实响应信息（用户要求打印；置于断言前——失败时日志
        # 中同样可见，便于诊断）
        test_logger.info(
            f"K20 真实响应 - HTTP {response.status_code}, "
            f"elapsed={elapsed:.1f}s"
        )
        test_logger.info(
            f"K20 真实响应 - 响应体({len(response.text)} 字符): "
            f"{response.text!r}"
        )

        # 断言1（核心之一）：未被拒绝——1M 量级输入应被接受
        assert response.status_code == 200, (
            f"客户问题复现失败：约 {predicted_tokens} tokens（自校准）"
            f"的 1M 量级输入应被支持，实际被拒绝（HTTP "
            f"{response.status_code}）: {response.text[:400]}"
        )

        # 断言2（核心之二）：可正常响应——choices/content 非空
        try:
            body = response.json()
        except ValueError as e:
            pytest.fail(
                f"响应体非 JSON（{e}）: {response.text[:400]}"
            )
        choices = body.get("choices") or []
        assert choices, f"choices 为空: {response.text[:400]}"
        message = (choices[0] or {}).get("message") or {}
        content_out = (message.get("content") or "").strip()
        assert content_out, (
            "客户问题复现失败：1M 量级输入已接受（HTTP 200）但响应"
            f"正文为空: {response.text[:400]}"
        )

        # usage 仅日志；prompt_tokens 附加规模 sanity 断言——必须高
        # 于原始故障上限 781754（确保用例真正压过故障点，防计量偏差）
        usage = body.get("usage") or {}
        actual_prompt_tokens = usage.get("prompt_tokens")
        if actual_prompt_tokens is None:
            test_logger.info(
                "K20 真实响应 - usage 缺 prompt_tokens（跳过规模 "
                "sanity 断言）"
            )
        else:
            assert actual_prompt_tokens > K20_OLD_INPUT_LIMIT, (
                f"规模 sanity 断言失败：实际 prompt_tokens="
                f"{actual_prompt_tokens} 未超过原始故障上限 "
                f"{K20_OLD_INPUT_LIMIT}——用例未真正压过故障点（探针"
                f"自校准 {tokens_per_unit:.3f} tokens/单元，预计 "
                f"{predicted_tokens}）"
            )
        test_logger.info(
            f"K20 真实响应 - usage: {json.dumps(usage, ensure_ascii=False)}"
        )
        test_logger.info(
            "客户问题复现通过: 1M 量级输入（自校准预计 "
            f"{predicted_tokens} tokens，实际 {actual_prompt_tokens}）"
            "被正常接受并返回非空响应（输入+输出 "
            f"{actual_prompt_tokens}+{K20_MAX_TOKENS} tokens，略小于 1M）"
        )
