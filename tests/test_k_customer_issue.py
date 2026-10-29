"""
K. 客户问题复现测试

本测试类专门收录来自客户反馈的真实问题，将客户提供的 curl 命令还原为
标准模型请求进行复现与回归验证。优先级按客户工单标定：K1-K7、K10-K25
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
  （保留最后一个值）。本用例按客户 agent 两步流程还原（用户指定
  测试逻辑）：第一个请求让模型输出技能周报数据 JSON 并落盘测试脚
  本同级目录下临时文件（第一步"输出 JSON 到 *.json 文件"）；第
  二个请求调用工具读取该临时 JSON 文件，将工单原始 assistant 返
  回数据（user→assistant(空占位+bash 调用+reasoning 双字段)→
  user 追问携带文件内容，带 bash 工具定义，非流式）回填为输入上
  下文；测试完成后删除临时 JSON 文件（finally 兜底）。硬断言：
  第一个请求 HTTP 200 且正文可提取合法 JSON 对象、临时文件回读
  一致、第二个请求 HTTP 200+choices 存在+message 结构存在——上
  次输出 JSON 必须可作为下次输入上下文，报错复现即 FAIL。不断
  言 arguments 被补 "{"（修复明确不补）与占位被移除（router 内
  部行为）。GLM-5.3 专用；采样参数不豁免——由全局
  SAMPLING_PARAMS 覆盖（temperature 无覆盖时回退 0.7、top_p/
  seed 注入），两个请求一致。docx 中 role 拼写 "assitant" 判定为
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
  允许命中历史缓存加速）。采样参数不豁免
  （用户指定）：由全局 SAMPLING_PARAMS（Jenkinsfile）覆盖——
  temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入
  （K10/K18 口径）。模型真实响应（状态码/响应体全文）断言前每
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
  采样参数不豁免（默认口径——未明确指定加入豁免名单）：由全局
  SAMPLING_PARAMS（Jenkinsfile）覆盖——temperature 无覆盖时回
  退 0.7、top_p/seed 显式指定时注入（K10/K18/K20 口径）。打印
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
  choices 非空；③message 有效输出（content 或 tool_calls 非空）。
  官方行为细节（输出/推理引用工具数据要素）软校验仅日志；
  finish/usage 仅日志。采样参数不豁免（默认口径——未明确指定加入
  豁免名单）：由全局 SAMPLING_PARAMS 覆盖——temperature 无覆盖时
  回退 0.7、top_p/seed 显式指定时注入（K10/K18/K20 口径）。模型
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
  同；第 2 轮只重测耗光的（已通过不重测）。采样参数豁免（用户指
  定）：两请求体均显式 temperature=0.0——工单体为唯一口径，通
  过 RAW_SAMPLING_PARAM_TESTS 豁免全局 SAMPLING_PARAMS 覆盖。硬
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
  造本身已保证安全，不判失败）。采样参数不豁免（默认口径）：由
  全局 SAMPLING_PARAMS 覆盖——temperature 无覆盖时回退 0.7、
  top_p/seed 显式指定时注入（K10/K18/K20 口径）。usage 仅日志；
  模型真实响应（状态码/合并正文/思考）断言前打印（失败时同样可
  见）。（不进 smoke 集：新用例首跑观察期）
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
            "=== 测试开始: 客户问题 - tool_choice 四种"
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
        发形态（docx 原样还原）：助手历史 tool_calls 混有
        1) 空占位调用：function.name=""、id=null、arguments="{}"
           （报错 missing field `name` 即指向它）——按客户 agent
           两步流程，该调用即第一步"输出 JSON 到 *.json 文件"，
           其 name/id 在返回数据中丢失；
        2) 真实 bash 调用：name="bash"、id="call_8af1ab36a4154c25"，
            arguments 为 '"command":"cd ... ", "description":
            "..."}'——缺开头 "{"、非合法 JSON（命令为运行绘图脚本
            并读取/复制第一步输出的 skill_weekly.json；内部
            data,json、SKlLL 等怪字符均为工单原文，原样保留）。
        修复逻辑：解析失败后，同列表还有其他真实调用时移除空占位
        项、保留真实调用再重新校验；缺 "{" 的 arguments 原样保留
        （不补 "{"——通过 router 不代表该字符串成为合法参数
        JSON）；兼容 assistant 历史重复的 reasoning_content/
        reasoning_context（保留最后一个值）。
        本用例按客户 agent 两步流程还原（用户指定测试逻辑）：
        - 第一个请求：模型直接输出技能周报数据 JSON，测试代为执
          行"输出 JSON 到 *.json 文件"——写入测试脚本同级目录下
          的临时文件 k18_temp_skill_weekly.json；
        - 第二个请求：测试代为执行 bash 工具读取该临时 JSON 文件
          （读取第一个请求输出的 json 文件），将工单原始 assistant
          返回数据（空占位+bash 调用+reasoning 双字段并存）与读到
          的文件内容一并回填为输入上下文：user →
          assistant(返回数据) → user(携带文件内容)，带 bash 工具
          定义，非流式；
        - 测试完成后删除生成的临时 JSON 文件（finally 兜底，断言
          失败同样清理）。
        硬断言：
        1. 第一个请求 HTTP 200 且正文可提取合法 JSON 对象（第一
           步契约：输出 JSON 到文件）
        2. 工具读取临时 JSON 文件成功（回读 json 与输出一致）
        3. 第二个请求 HTTP 200（核心——上次输出 JSON 必须可作为
           下次请求的输入上下文，报错复现即 FAIL）
        4. choices 存在且非空 + message 结构存在（响应可正常生成）
        明确不断言：arguments 被补 "{"（修复明确不补）、空占位被
        移除（router 内部行为，响应不可见）。响应形态（正文/继续
        调用工具）宽松留日志——测试要点是上下文被接受。
        docx 中 role 拼写 "assitant" 判定为笔误（报错与修复均不涉
        及 role），按标准 assistant 还原。reasoning 同键字面重复
        无法经 dict 表达，以 reasoning_content + reasoning_context
        两拼写并存覆盖兼容路径。GLM-5.3 专用；采样参数不豁免——
        由全局 SAMPLING_PARAMS 覆盖（temperature 无覆盖时回退
        0.7、top_p/seed 注入），两个请求一致。usage 仅日志。
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
        # K18: 第二个请求（返回数据回填上下文）预算——工单口径
        K18_MAX_TOKENS = 512
        # K18: 第一个请求提示词——按客户 agent 流程第一步"输出
        # JSON 到 *.json 文件"：让模型直接输出技能周报数据 JSON
        #（不带工具定义——直接输出 JSON 才可确定性落盘）
        K18_REQ1_PROMPT = (
            "请分析工作区数据并生成技能周报数据：直接输出一个 JSON "
            '对象，包含 3-5 条技能记录，每条含技能名称（skill）、'
            '本周事件数（events）、评分（score）字段；以 { 开头、'
            "以 } 结尾，不要使用 markdown 代码块，不要输出 JSON 以"
            "外的任何内容。"
        )
        # K18: 第一个请求预算——简单数据生成任务，2048 留足思考
        # 预算余量（防御正文被思考耗光）
        K18_REQ1_MAX_TOKENS = 2048
        # K18: 临时 JSON 文件名——第一个请求"输出 JSON 到 *.json
        # 文件"的落盘产物（测试脚本同级目录下，对应工单中的
        # skill_weekly.json），测试完成后删除
        K18_TEMP_FILE_NAME = "k18_temp_skill_weekly.json"
        # K18: 第二个请求 user 追问携带文件内容的防御性截断上限
        K18_FILE_CONTEXT_LIMIT = 3000

        test_logger.info(
            "=== 测试开始: 客户问题 - 模型输出 JSON 回填为下次请求"
            "输入上下文（两步流程：第一个请求输出临时 JSON 文件 → "
            "第二个请求调用工具读取后回填上下文；assistant 历史含空"
            "占位调用/缺 \"{\" 的 bash arguments/reasoning 双字段；"
            "修复后应被接受，报错复现即 FAIL）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        # 手工构造 payload 直发（需按工单原样还原 assistant 历史怪
        # 异结构，chat_completion 封装不支持）；采样参数不豁免（用户
        # 指令）——由全局 SAMPLING_PARAMS（Jenkinsfile，经 conftest
        # 注入 client）覆盖：temperature 全局值优先（无覆盖时回退
        # 0.7），top_p/seed 未显式指定时注入；两个请求一致
        sampling_extra: Dict[str, Any] = {}
        if api_client.top_p is not None:
            sampling_extra["top_p"] = api_client.top_p
        if api_client.seed:
            try:
                sampling_extra["seed"] = int(api_client.seed)
            except (ValueError, TypeError):
                sampling_extra["seed"] = api_client.seed

        temp_file = Path(__file__).with_name(K18_TEMP_FILE_NAME)
        try:
            # ---- 第一个请求：模型输出技能周报数据 JSON ----
            req1_payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [
                    {"role": "user", "content": K18_REQ1_PROMPT}
                ],
                "max_tokens": K18_REQ1_MAX_TOKENS,
                "temperature": api_client._effective_temperature(0.7),
                "stream": False,
                **sampling_extra,
            }
            TestLogger.log_request(
                test_logger,
                req1_payload["messages"],
                {
                    "max_tokens": K18_REQ1_MAX_TOKENS,
                    "temperature": req1_payload["temperature"],
                    "top_p": req1_payload.get("top_p", "(不注入)"),
                    "seed": req1_payload.get("seed", "(不注入)"),
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
                    f"响应体: {response1.text[:300]}"
                )
            choices1 = result1.get("choices") or []
            assert choices1, (
                f"第一个请求响应缺少 choices: "
                f"{json.dumps(result1, ensure_ascii=False)[:500]}"
            )
            message1 = choices1[0].get("message")
            assert isinstance(message1, dict), (
                f"第一个请求响应 message 结构缺失: "
                f"{json.dumps(result1, ensure_ascii=False)[:500]}"
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
                f"JSON 到临时文件: {response1.text[:400]}"
            )
            json_start = content1.find("{")
            json_end = content1.rfind("}")
            assert json_start != -1 and json_end > json_start, (
                f"第一个请求正文中未找到 JSON 对象: {content1[:400]!r}"
            )
            try:
                skill_data = json.loads(
                    content1[json_start : json_end + 1]
                )
            except json.JSONDecodeError as e:
                pytest.fail(
                    f"第一个请求输出的 JSON 对象解析失败: {e}. "
                    f"正文: {content1[:400]!r}"
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
            assert file_data == skill_data, (
                f"临时 JSON 文件回读内容与第一个请求输出不一致: "
                f"{file_text[:400]!r}"
            )
            test_logger.info(
                f"第二步完成: 工具已读取第一个请求输出的临时 JSON "
                f"文件 {temp_file}（{len(file_text)} 字符）: "
                f"{file_text[:400]!r}"
            )

            # ---- 第二个请求：返回数据回填为输入上下文（核心断言） ----
            req2_followup = (
                "请继续完成任务。工具已读取第一个请求输出的技能周报数"
                "据文件，内容如下：\n"
                f"{file_text[:K18_FILE_CONTEXT_LIMIT]}\n"
                "请基于以上数据继续。"
            )
            payload: Dict[str, Any] = {
                "model": api_client.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": "请分析工作区数据并生成技能周报图表。",
                    },
                    K18_ASSISTANT,
                    {"role": "user", "content": req2_followup},
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
                    "step": (
                        "第二个请求（工具读取 JSON 文件后回填上下文）"
                    ),
                    "assistant_history": (
                        "空占位调用(name=\"\", id=null) + bash 调用"
                        "(arguments 缺 \"{\") + reasoning 双字段"
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
            # ——修复前此请求报 400（missing field `name`），报错
            # 复现即 FAIL
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
                    f"第二个请求响应不是合法 JSON: {e}. "
                    f"响应体: {response.text[:300]}"
                )
            # 断言4：choices 存在（上下文被接受且正常生成）
            choices = result.get("choices") or []
            assert choices, (
                f"第二个请求响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            message = choices[0].get("message")
            assert isinstance(message, dict), (
                f"第二个请求响应 message 结构缺失: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
                "到临时文件、工具读取成功、上次输出 JSON（含空占位调"
                "用/缺 \"{\" 的 bash arguments/reasoning 双字段的 "
                "assistant 历史）已被接受为下次请求的输入上下文，正常"
                "生成响应"
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
        - 采样参数不豁免（用户指定）：由全局 SAMPLING_PARAMS
          （Jenkinsfile）覆盖——temperature 无覆盖时回退 0.7、
          top_p/seed 显式指定时注入（K10/K18 口径）
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

        url = f"{api_client.base_url}/v1/chat/completions"

        test_logger.info(
            "=== 测试开始: 客户问题 - 1M 上下文请求应被正常支持"
            f"（探针自校准精确计量；目标输入 {K20_TARGET_PROMPT_TOKENS} "
            f"tokens + 输出预算 low 轮 1024 / max 轮 4096——输入+输出 "
            f"略小于 1M；采样参数不豁免——全局 SAMPLING_PARAMS 覆盖；"
            f"low 轮唯一 nonce 头部绕过 KV 缓存——跑必冷、"
            f"max 轮无唯一前缀（允许命中缓存）；"
            f"期望每轮 HTTP 200 + 非空正文）==="
        )

        # 采样参数不豁免（用户指定）：由全局 SAMPLING_PARAMS
        # （Jenkinsfile）覆盖——temperature 无覆盖时回退 0.7、
        # top_p/seed 显式指定时注入（K10/K18 口径）
        sampling_extra: Dict[str, Any] = {}
        if api_client.top_p is not None:
            sampling_extra["top_p"] = api_client.top_p
        if api_client.seed is not None:
            try:
                sampling_extra["seed"] = int(api_client.seed)
            except (TypeError, ValueError):
                sampling_extra["seed"] = api_client.seed

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
            """构造带全局采样参数的 K20 请求体（探针/两轮共用）"""
            return {
                "model": api_client.model_name,
                "messages": [{"role": "user", "content": nonce + text}],
                "max_tokens": max_tokens,
                "reasoning_effort": effort,
                "temperature": api_client._effective_temperature(0.7),
                "stream": False,
                **sampling_extra,
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
                "temperature": api_client._effective_temperature(0.7),
                "top_p": sampling_extra.get("top_p", "(未注入)"),
                "seed": sampling_extra.get("seed", "(未注入)"),
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
                    "temperature": api_client._effective_temperature(0.7),
                    "top_p": sampling_extra.get("top_p", "(未注入)"),
                    "seed": sampling_extra.get("seed", "(未注入)"),
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
                    f"第 {round_index} 轮响应体非 JSON（{e}）: "
                    f"{response.text[:400]}"
                )
            choices = body.get("choices") or []
            assert choices, (
                f"第 {round_index} 轮 choices 为空: {response.text[:400]}"
            )
            message = (choices[0] or {}).get("message") or {}
            content_out = (message.get("content") or "").strip()
            assert content_out, (
                f"客户问题复现失败（第 {round_index} 轮 "
                f"reasoning_effort={effort}）：1M 量级输入已接受"
                f"（HTTP 200）但响应正文为空: {response.text[:400]}"
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
        见）；usage 仅日志。采样参数不豁免（默认口径——未明确指定
        加入豁免名单）：由全局 SAMPLING_PARAMS（Jenkinsfile，经
        conftest 注入 client）覆盖——temperature 无覆盖时回退 0.7、
        top_p/seed 显式指定时注入（K10/K18/K20 口径）。打印口径
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

        url = f"{api_client.base_url}/v1/chat/completions"

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
        # 采样参数不豁免（默认口径——未明确指定加入豁免名单）：
        # 由全局 SAMPLING_PARAMS（Jenkinsfile，经 conftest 注入
        # client）覆盖：temperature 全局值优先（无覆盖时回退
        # 0.7），top_p/seed 显式指定时注入（K10/K18/K20 口径）
        sampling_extra: Dict[str, Any] = {}
        if api_client.top_p is not None:
            sampling_extra["top_p"] = api_client.top_p
        if api_client.seed is not None:
            try:
                sampling_extra["seed"] = int(api_client.seed)
            except (TypeError, ValueError):
                sampling_extra["seed"] = api_client.seed
        payload = {
            "model": api_client.model_name,
            "messages": messages,
            "temperature": api_client._effective_temperature(0.7),
            "stream": False,
            **sampling_extra,
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
                "temperature": api_client._effective_temperature(0.7),
                "top_p": sampling_extra.get("top_p", "(未注入)"),
                "seed": sampling_extra.get("seed", "(未注入)"),
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
                f"响应不是合法 JSON: {e}. 响应体: {response.text[:400]}"
            )
        choices = result.get("choices") or []
        assert choices, (
            f"响应缺少 choices: {json.dumps(result, ensure_ascii=False)[:500]}"
        )

        # 断言3：有效输出——content 非空或 tool_calls 非空（宽容解析
        # 后文本作答/工具调用响应均为成功形态；两者皆空即未正常响应）
        message = (choices[0] or {}).get("message") or {}
        content_out = (message.get("content") or "").strip()
        tool_calls_out = message.get("tool_calls") or []
        assert content_out or tool_calls_out, (
            f"客户问题复现失败：请求已接受（HTTP 200）但响应无有效输"
            f"出（content 与 tool_calls 均为空）: {response.text[:400]}"
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

        chat_url = f"{api_client.base_url}/v1/chat/completions"
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
            assert choices, (
                f"[{label}] 响应缺少 choices: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
            assert content_blocks, (
                f"[{label}] 响应缺少 content: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
            )
            usage = result.get("usage") or {}
            assert usage, (
                f"[{label}] 响应缺少 usage: "
                f"{json.dumps(result, ensure_ascii=False)[:500]}"
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
        官方行为细节（输出/推理引用工具数据要素）为软校验仅日志；
        finish/usage 仅日志。采样参数不豁免（默认口径——未明确指定
        加入豁免名单）：由全局 SAMPLING_PARAMS 覆盖——temperature
        无覆盖时回退 0.7、top_p/seed 显式指定时注入（K10/K18/K20
        口径）。模型真实响应（状态码/响应体全文）断言前打印（失败
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

        url = f"{api_client.base_url}/v1/chat/completions"

        # 采样参数不豁免（默认口径）：由全局 SAMPLING_PARAMS
        # （Jenkinsfile）覆盖——temperature 无覆盖时回退 0.7、
        # top_p/seed 显式指定时注入（K10/K18/K20 口径）
        sampling_extra: Dict[str, Any] = {}
        if api_client.top_p is not None:
            sampling_extra["top_p"] = api_client.top_p
        if api_client.seed is not None:
            try:
                sampling_extra["seed"] = int(api_client.seed)
            except (TypeError, ValueError):
                sampling_extra["seed"] = api_client.seed

        # 手工构造 payload 直发（含 tool 角色消息，chat_completion
        # 封装不支持；工单原始请求体为非流式——不传 stream，采样按
        # 全局覆盖注入）
        payload = {
            "model": api_client.model_name,
            "messages": K23_MESSAGES,
            "max_tokens": K23_MAX_TOKENS,
            "temperature": api_client._effective_temperature(0.7),
            **sampling_extra,
        }

        TestLogger.log_request(
            test_logger,
            K23_MESSAGES,
            {
                "max_tokens": K23_MAX_TOKENS,
                "tools": "(未定义)",
                "thinking": "(不传，工单原始请求体口径)",
                "stream": "(不传——默认非流式)",
                "temperature": api_client._effective_temperature(0.7),
                "top_p": sampling_extra.get("top_p", "(未注入)"),
                "seed": sampling_extra.get("seed", "(未注入)"),
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
                f"——{response.text[:400]!r}"
            )
        choices = body.get("choices") or []
        assert choices, (
            f"客户问题复现失败：choices 为空——{response.text[:400]!r}"
        )

        # 断言3：message 有效输出（官方形态为正常答句）
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or []
        finish = choices[0].get("finish_reason")
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
            f"应答{budget_note}——{response.text[:400]!r}"
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
        采样参数豁免（用户指定）：两个请求体均显式指定
        temperature=0.0——工单原始请求体为唯一口径，全局
        SAMPLING_PARAMS 覆盖不得生效（通过 RAW_SAMPLING_PARAM_TESTS
        豁免），top_p/seed 亦不注入。
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
                    f"解析异常: {e}——{response.text[:400]!r}"
                )
            choices = body.get("choices") or []
            assert choices, (
                f"客户问题复现失败：{label} choices 为空——"
                f"{response.text[:400]!r}"
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
                    f"finish={finish}）——{response.text[:400]!r}"
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
                f"输出，报文留证交开发——{response.text[:400]!r}"
            )

        test_logger.info(
            "=== 测试开始: 客户问题 - 双请求正常响应（默认 max 思考"
            "强度有正文即过；思考耗光预算按 reasoning_effort=low "
            "回退重发且仅测耗光请求——用户指定契约；temperature=0.0"
            " 工单口径豁免全局采样覆盖）==="
        )

        url = f"{api_client.base_url}/v1/chat/completions"

        # 采样参数豁免（用户指定）：两个请求体均显式 temperature=
        # 0.0——工单原始请求体为唯一口径，通过 RAW_SAMPLING_PARAM_
        # TESTS 豁免全局 SAMPLING_PARAMS 覆盖，top_p/seed 亦不注
        # 入——payload 直用工单原值

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
        采样参数不豁免（默认口径）：由全局 SAMPLING_PARAMS 覆盖
        ——temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注
        入（K10/K18/K20 口径）。max_tokens=8192 为客户工单原始口
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
            采样参数不豁免（默认口径）：chat_completion_stream 自
            动注入全局 temperature/top_p/seed（temperature 无覆盖时
            回退 0.7）。
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
                        "temperature": "全局覆盖优先（无覆盖时回退 0.7）",
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
                assert parsed_json is not None, (
                    f"{label} 响应正文非合法 JSON——第 1/2 次响应须"
                    f"作为下一请求输入回填（JSON 链条断裂，场景无法构"
                    f"造）: {collected['content'][:400]!r}"
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

        url = f"{api_client.base_url}/v1/chat/completions"

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

        # 采样参数不豁免（默认口径）：temperature 无覆盖时回退 0.7、
        # top_p/seed 显式指定时注入（K10/K18/K20 口径）——手工拼入
        # raw body（直发路径不经 chat_completion 封装）
        sampling_fields = ""
        if api_client.top_p is not None:
            sampling_fields += f'"top_p": {dumps(api_client.top_p)}, '
        if api_client.seed:
            try:
                sampling_fields += f'"seed": {dumps(int(api_client.seed))}, '
            except (ValueError, TypeError):
                sampling_fields += f'"seed": {dumps(api_client.seed)}, '

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
                f'"temperature": {dumps(api_client._effective_temperature(0.7))}, '
                f"{effort_fields}"
                f"{sampling_fields}"
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
