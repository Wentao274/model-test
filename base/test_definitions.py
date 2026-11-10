"""
测试分类定义

集中管理所有测试分类和测试点定义，避免重复
"""

from typing import Dict

TEST_CATEGORIES = {
    "a_basic": {
        "name": "A. 基础推理能力",
        "criticality": "关键",
        "tests": [
            (
                "A1",
                "单轮对话",
                "发送单条prompt，验证正常生成",
                "single_turn_conversation",
                "P0",
            ),
            (
                "A2",
                "多轮对话",
                "5轮对话，验证上下文保持和连贯性",
                "multi_turn_conversation",
                "P0",
            ),
            (
                "A3",
                "System Prompt",
                "设置系统角色，验证模型遵循程度",
                "system_prompt",
                "P0",
            ),
            (
                "A4",
                "流式输出",
                "stream=true，验证SSE逐token返回",
                "streaming_output",
                "P0",
            ),
            (
                "A5",
                "非流式输出",
                "stream=false，验证完整返回",
                "non_streaming_output",
                "P0",
            ),
            (
                "A6",
                "Temperature 控制",
                "temp=0 vs temp=1.0，验证输出差异",
                "temperature_control",
                "P1",
            ),
            (
                "A7",
                "Top-p/Top-k采样",
                "不同top_p/top_k值，验证多样性控制",
                "top_p_top_k_sampling",
                "P1",
            ),
            (
                "A8",
                "Max Tokens限制",
                "设置max_tokens，验证输出不超限",
                "max_tokens_limit",
                "P0",
            ),
            (
                "A9",
                "Stop Sequences",
                "设置stop token，验证截断",
                "stop_sequences",
                "P1",
            ),
            (
                "A10",
                "Seed 可复现性",
                "相同seed+temp=0，验证输出一致",
                "seed_reproducibility",
                "P1",
            ),
            (
                "A11",
                "多语言能力",
                "中/英/日/韩/法等多语言输入输出",
                "multilingual_capability",
                "P1",
            ),
            (
                "A12",
                "特殊Token处理",
                "含emoji、代码块、数学符号、HTML标签",
                "special_tokens_handling",
                "P1",
            ),
        ],
    },
    "b_advanced": {
        "name": "B. 高级生成功能",
        "criticality": "重要",
        "tests": [
            (
                "B1",
                "思考模式（Thinking）",
                "开启thinking mode，验证返回思考链+最终答案",
                "thinking_mode",
                "P0",
            ),
            (
                "B2",
                "非思考模式（Instant）",
                "关闭thinking，验证无hidden thinking泄漏",
                "non_thinking_mode",
                "P1",
            ),
            (
                "B3",
                "思考模式切换",
                "同一会话内thinking↔non-thinking切换",
                "thinking_mode_switch",
                "P1",
            ),
            (
                "B4",
                "工具调用-单工具",
                "定义单个function，验证模型正确调用并传参",
                "single_tool_call",
                "P0",
            ),
            (
                "B5",
                "工具调用-多工具",
                "定义多个function，验证模型选择正确的工具",
                "multiple_tool_call",
                "P1",
            ),
            (
                "B6",
                "工具调用-并行调用",
                "单次回复中并行调用多个工具",
                "parallel_tool_calls",
                "P2",
            ),
            (
                "B7",
                "工具调用-多步链式",
                "工具结果作为下一步输入，验证3+步链式执行",
                "multi_step_tool_chain",
                "P1",
            ),
            (
                "B8",
                "JSON Mode",
                "response_format=json_object，验证输出合法JSON",
                "json_mode",
                "P0",
            ),
            (
                "B9",
                "结构化输出",
                "JSON Schema约束输出格式，验证字段完整性",
                "structured_output",
                "P0",
            ),
            (
                "B10",
                "Prefix/Suffix约束",
                "指定输出前缀或格式模板，验证遵循度",
                "prefix_suffix_constraint",
                "P2",
            ),
            (
                "B11",
                "reasoning_effort 参数",
                "low/high/max 三档思考强度，不支持的模型告警",
                "reasoning_effort",
                "P1",
            ),
        ],
    },
    "c_multimodal": {
        "name": "C. 多模态能力",
        "criticality": "一般",
        "tests": [
            (
                "C1",
                "单图理解",
                "合成图片+文本提问，验证视觉理解",
                "single_image_understanding",
                "P1",
            ),
            ("C2", "多图对比", "跨图比较", "multi_image_comparison", "P1"),
            (
                "C3",
                "高分辨率图片",
                "真实高清图细节识别",
                "high_resolution_image",
                "P2",
            ),
            ("C4", "图表/OCR", "合成文字OCR", "chart_ocr", "P1"),
            ("C5", "视频理解", "视频文件", "video_understanding", "P2"),
            (
                "C6",
                "代码截图→代码",
                "Flask代码截图识别",
                "screenshot_to_code_flask",
                "P2",
            ),
            ("C7", "多模态工具调用", "图片触发工具", "multimodal_tool_call", "P2"),
            (
                "C8",
                "图片格式兼容性",
                "PNG/JPEG/WebP",
                "image_format_compatibility",
                "P1",
            ),
            (
                "C9",
                "真实图片理解",
                "真实图片描述能力",
                "real_image_understanding",
                "P1",
            ),
            ("C10", "合成4K图片", "大图处理能力", "synthetic_4k_image", "P2"),
            ("C11", "表格OCR", "真实表格截图识别", "table_ocr", "P1"),
            (
                "C12",
                "UI截图生成代码",
                "UI设计图生成代码",
                "screenshot_to_code_ui",
                "P2",
            ),
        ],
    },
    "d_long_context": {
        "name": "D. 长上下文处理",
        "criticality": "重要",
        "tests": [
            ("D1", "短上下文基线", "1K tokens", "short_context_baseline", "P0"),
            ("D2", "中等上下文", "8K-16K tokens", "medium_context", "P1"),
            ("D3", "长上下文", "32K-64K tokens", "long_context", "P1"),
            ("D4", "超长上下文", "128K+ tokens", "super_long_context", "P0"),
            ("D5", "大海捞针", "NIAH", "niah_needle_in_a_haystack", "P0"),
            (
                "D6",
                "上下文边界行为",
                "max_model_len",
                "context_boundary_behavior",
                "P1",
            ),
            ("D7", "超出上下文截断", "截断/拒绝", "context_truncation", "P1"),
            ("D8", "长输出生成", "4K-8K tokens", "long_output_generation", "P1"),
            (
                "D9",
                "超长上下文（非流式）",
                "验证超长上下文请求的非流式输出",
                "super_long_context_create",
                "P1",
            ),
            (
                "D10",
                "超长上下文（流式）",
                "验证超长上下文请求的流式输出",
                "super_long_context_stream",
                "P1",
            ),
            (
                "D11",
                "超长上下文（边界验证）",
                "使用二分法逼近模型最大上下文长度",
                "context_boundary_exact_limit",
                "P1",
            ),
            (
                "D12",
                "超长上下文（思考模式）",
                "验证超长上下文下reasoning_content的可用性",
                "reasoning_content_in_long_context",
                "P0",
            ),
        ],
    },
    "e_stability": {
        "name": "E. 稳定性与边界",
        "criticality": "一般",
        "tests": [
            ("E1", "空输入", "空prompt", "empty_input", "P0"),
            ("E2", "超大输入", "超max_model_len", "oversized_input", "P1"),
            ("E3", "非法参数", "temperature=-1", "invalid_parameters", "P2"),
            (
                "E4",
                "特殊字符注入",
                "SQL/Prompt注入",
                "special_character_injection",
                "P0",
            ),
            ("E5", "并发稳定性", "200+并发", "concurrent_stability", "P1"),
            ("E6", "OOM恢复", "显存耗尽", "oom_recovery", "P1"),
            ("E7", "长时间运行", "24小时", "long_running_service", "P1"),
            ("E8", "请求超时处理", "超时断开", "request_timeout_handling", "P1"),
        ],
    },
    "f_api": {
        "name": "F. API兼容性",
        "criticality": "重要",
        "tests": [
            (
                "F1",
                "OpenAI Chat Completions",
                "/v1/chat/completions 接口兼容",
                "chat_completions_api",
                "P0",
            ),
            (
                "F2",
                "OpenAI Completions",
                "/v1/completions 接口兼容",
                "completions_api",
                "P1",
            ),
            ("F3", "模型列表", "/v1/models 返回可用模型", "models_list", "P0"),
            ("F4", "Usage 统计", "usage 字段准确", "usage_statistics", "P0"),
            ("F5", "错误码规范", "401/400/404 错误码", "error_codes", "P1"),
            (
                "F6",
                "客户端 SDK 兼容",
                "Python openai",
                "client_sdk_compatibility",
                "P0",
            ),
            (
                "F7",
                "OpenAI Responses API",
                "/v1/responses 新一代接口兼容",
                "responses_api",
                "P0",
            ),
        ],
    },
    "g_quality_chat_completions": {
        "name": "G. Chat Completions API 质量评估与回答相关性",
        "criticality": "关键",
        "tests": [
            ("G1", "生成质量", "质量对比", "generation_quality", "P0"),
            ("G2", "生成一致性", "多次生成", "generation_consistency", "P1"),
            ("G3", "幻觉率", "事实错误", "hallucination_detection", "P1"),
            ("G4", "指令遵循度", "格式/角色", "instruction_following", "P0"),
            ("G5", "响应相关性", "问答相关性", "response_relevance", "P0"),
            (
                "G6",
                "编程领域相关性",
                "验证编程问题的回答相关性",
                "response_relevance_programming",
                "P0",
            ),
            (
                "G7",
                "数学领域相关性",
                "验证数学问题的回答相关性",
                "response_relevance_math",
                "P0",
            ),
            (
                "G8",
                "科学领域相关性",
                "验证科学问题的回答相关性",
                "response_relevance_science",
                "P0",
            ),
            (
                "G9",
                "乱码检测",
                "检测输出是否为乱码或无效字符",
                "garbled_text_detection",
                "P0",
            ),
            (
                "G10",
                "无意义回答检测",
                "检测回答是否与问题完全不相关",
                "nonsensical_response_detection",
                "P1",
            ),
            (
                "G11",
                "跨领域相关性",
                "天气/烹饪等领域相关性",
                "cross_domain_relevance",
                "P1",
            ),
            (
                "G12",
                "上下文一致性",
                "多轮对话中验证上下文一致性",
                "conversation_context_consistency",
                "P0",
            ),
            (
                "G13",
                "回答具体性",
                "确保回答不是泛泛而谈",
                "response_specificity_check",
                "P2",
            ),
        ],
    },
    "h_clear_thinking": {
        "name": "H. clear_thinking 参数行为",
        "criticality": "重要",
        "tests": [
            (
                "H1",
                "clear_thinking=true 多轮",
                "显式 clear_thinking=true，验证多轮请求成功且无 thinking 泄漏到后续上下文",
                "clear_thinking_true_multi_turn",
                "P1",
            ),
            (
                "H2",
                "clear_thinking=false 多轮",
                "显式 clear_thinking=false，验证多轮请求成功且历史 thinking 被保留",
                "clear_thinking_false_multi_turn",
                "P1",
            ),
            (
                "H3",
                "clear_thinking 对 prompt_tokens 的影响",
                "对比 true/false 在含历史 thinking 的多轮请求下的 prompt_tokens 差异",
                "clear_thinking_prompt_tokens_difference",
                "P2",
            ),
            (
                "H4",
                "clear_thinking 与 enable_thinking 组合",
                "四种 (enable_thinking, clear_thinking) 组合均可被服务端接受",
                "clear_thinking_enable_combinations",
                "P1",
            ),
            (
                "H5",
                "clear_thinking deployment 能力探测",
                "探测服务端是否真实实现 clear_thinking（pt_false > pt_true），"
                "未生效时记录 WARNING 提示运维/算法团队",
                "clear_thinking_deployment_probe",
                "P1",
            ),
            (
                "H6",
                "clear_thinking 对 reasoning_content 独立字段的处理",
                "assistant 消息以 reasoning_content 字段承载思考时验证 clear_thinking 行为",
                "clear_thinking_reasoning_field",
                "P1",
            ),
            (
                "H7",
                "clear_thinking 与 reasoning_effort 组合",
                "GLM-5.3 等模型核心参数组合，验证参数正交性",
                "clear_thinking_with_reasoning_effort",
                "P1",
            ),
            (
                "H8",
                "多 assistant 边界测试",
                "多条历史 assistant 消息下 last_user_index 边界条件",
                "clear_thinking_multi_assistant_boundary",
                "P2",
            ),
            (
                "H9",
                "clear_thinking 默认行为探测",
                "不传 clear_thinking 时的服务端默认值验证",
                "clear_thinking_default_behavior",
                "P2",
            ),
            (
                "H10",
                "clear_thinking 行为级验证",
                "follow-up 依赖历史思考内容，验证模型是否真的看到历史 thinking",
                "clear_thinking_behavioral_verification",
                "P2",
            ),
            (
                "H11",
                "last_user 之后 assistant 思考保留边界",
                "验证模版 loop.index0 > last_user_index 的保留分支",
                "clear_thinking_after_last_user_boundary",
                "P2",
            ),
        ],
    },
    "k_customer_issue": {
        "name": "K. 客户问题复现",
        "criticality": "关键",
        "tests": [
            (
                "K1",
                "Pydantic $defs/$ref Schema 工具调用",
                "客户问题复现：thinking+stream+强制tool_choice+Pydantic v2生成的"
                "$defs/$ref JSON Schema 报【$$不兼容】，原样复现请求验证服务端兼容"
                "（工单原始请求含 temperature=0.1——原样保留并豁免全局采样覆盖）",
                "pydantic_schema_tool_call_stream",
                "P0",
            ),
            (
                "K2",
                "同一请求循环执行5次返回信息异常",
                "客户问题复现：同一 curl（logprobs+top_logprobs+n+thinking+stream+"
                "X-Cache-Buster）循环执行5次左右出现返回信息异常，原样复现并连续"
                "执行5次（间隔3s），验证每次响应与内容均正常（工单原始请求含 "
                "temperature=1、top_p=0.95——原样保留并豁免全局采样覆盖）",
                "repeated_request_stability",
                "P0",
            ),
            (
                "K3",
                "Anthropic 协议 prompt cache 未创建",
                "客户问题复现：Anthropic 协议（/anthropic/v1/messages）请求的"
                "cache_creation_tokens 一直为0（未创建缓存），构造带 cache_control "
                "断点的唯一长前缀连发两次，验证第1次创建、第2次命中",
                "anthropic_prompt_cache_creation",
                "P0",
            ),
            (
                "K4",
                "frequency_penalty=-2 不传 max_tokens 无返回",
                "客户问题复现：fp=-2（合法极值）且不传 max_tokens 时退化重复导致"
                "无界生成、请求一直无返回；修复契约为 fp<0 按 0 处理，输入保持 "
                "-2、不传 max_tokens 连发 3 次（消息各异，间隔3s），断言每次均按"
                "fp=0 预期（预算内返回+自然结束+内容非空）",
                "negative_frequency_penalty_treated_as_zero",
                "P0",
            ),
            (
                "K5",
                "thinking.type=disabled 后思考未关闭",
                "客户问题复现：disabled 后 reasoning_tokens 仍>0、reasoning_content"
                "照常输出，关思考相关功能全部失效；官方端点实测 disabled 应完全"
                "关闭思考（rt 为空、无思考内容、正文正常，FAQ 与实测不符以实测"
                "为准）。输入保持 disabled、temperature=0.6（官方关思考档唯一"
                "合法温度）连发 3 次（消息各异，间隔3s），断言每次均符合官方"
                "实测预期（无思考内容+rt 为空+正文正常返回+自然结束）",
                "thinking_disabled_suppresses_reasoning",
                "P0",
            ),
            (
                "K6",
                "关思考温度档未联动校验",
                "官方契约（kimi-k3）：thinking 与 temperature 档位联动——disabled"
                " 仅允许 0.6（给 1 或 0 报 400 \"only 0.6 is allowed for this "
                "model in non-thinking mode\"）、enabled 仅允许 1（给 0.6 或 0 "
                "报 400 \"only 1 is allowed for this model in thinking mode\"），"
                "客户影响为关思考温度档失效。本用例对 6 个组合各发一次请求，"
                "断言合法组合 200+正文非空、非法组合 400+错误信息含官方文案"
                "（忽略大小写子串）",
                "thinking_temperature_tier",
                "P0",
            ),
            (
                "K7",
                "思考强度档位思考长度倒挂（官方 reasoning_effort）",
                "客户问题复现（kimi-k3）：官方思考强度为顶层 reasoning_effort"
                "（K2.x thinking 配置已废弃），K3 恒开思考，思考长度"
                "（reasoning_tokens）随档位递增。只按官方格式传参（无回退），"
                "请求顺序（客户指定）：low→high→max 比对后 max→high→low 再"
                "比对（正逆两轮排除顺序干扰，均按 low<high<max 软对比，"
                "medium 不参与）；最后 medium 顶层 200 放行、medium 嵌套 400"
                "（废弃配置下非法档位，客户指定契约）；间隔3s、内容与温度相同"
                "（temperature=1）；硬断言每次 200+正文非空+自然结束；倒挂/"
                "持平不判失败，仅告警记入报告",
                "thinking_effort_reasoning_length",
                "P0",
            ),
            (
                "K8",
                "required+闲聊必须调用工具（客户工单级别）",
                "客户问题复现（kimi-k3）：工单原始问题为 required+"
                "闲聊（Reply with exactly: OK）下不发起工具调用——"
                "tool_calls 缺失、finish=length、ct 恒吃满 max_"
                "tokens（关思考 1000/3000）、正文仅 OK；预期 finish="
                "tool_calls、关思考 ct 较小、开思考 rt<max_tokens。"
                "关思考 mt=1000/3000、开思考 mt=3000（get_weather "
                "工具），断言 tool_calls 存在（get_weather、"
                "arguments 合法 JSON）、finish=tool_calls（而非 "
                "length）、ct<max_tokens、开思考 rt<max_tokens"
                "（双拼写兼容）；耗时双峰仅日志留痕",
                "required_chitchat_calls_tool",
                "P1",
            ),
            (
                "K9",
                "required+闲聊必须强制调用工具（按官方行为）",
                "客户问题复现（kimi-k3）：官方 api.moonshot.cn 同场景"
                "（闲聊+required）finish=tool_calls、强制返回 "
                "get_weather（city 瞎猜不限定）、reasoning 仅 38——"
                "符合 [OI] required 必须发起至少一次工具调用规范；"
                "Alaya 缺陷为 finish=length、reasoning 吃满 256/2000"
                " 预算、tool_calls=None。按官方行为为预期（与 K8 同"
                "场景不同级别）：关/开思考 × mt=256/2000，断言 tool_"
                "calls 强制返回（get_weather、arguments 合法 JSON）、"
                "finish=tool_calls、ct<max_tokens、开思考 rt<max_"
                "tokens（双拼写兼容）",
                "required_chitchat_official_behavior",
                "P1",
            ),
            (
                "K10",
                "GLM-5.3-Flash tool_choice 四种模式支持",
                "客户问题（AGDC2-15）：OpenAI 协议 tool_choice 让模型"
                "按请求指定的类型/模式生成工具调用（Agent 自定义工具"
                "场景）；上线前版本未指定模型专属的工具调用格式解析"
                "器，GLM-5.3-Flash 不支持该语义（修复：Worker 侧指定"
                "生成解释器，渲染字段至模型聊天模版）。需支持四种模"
                "式：auto/required/named/none。四模式各一次（原始脚"
                "本 glm53_flash_suite 口径：mt=2048、非流式、不传 "
                "thinking；采样参数豁免（用户口径）——原始脚本指定 "
                "temperature=0，原样保留，不受全局 SAMPLING_PARAMS "
                "覆盖；工具 get_weather+get_current_"
                "time 两个），断言 auto/required 必须发起工具调用（形"
                "状合法、finish=tool_calls）、named 必须调用指定工具"
                "（指定与提示词意图不同向的 get_current_time，未生效"
                "时按意图调 get_weather 即被检出）、none 禁止调用（无"
                " tool_calls、正文非空、finish=stop）；usage 仅日志。"
                "同时适用 Kimi K3（OpenAI 协议通用语义，默认思考不"
                "做断言；2026-10-26 staging 实测 required 轮 500 "
                "prefill_internal_error，该 FAIL 为待修复基线）",
                "tool_choice_four_modes_support",
                "P0",
            ),
            (
                "K11",
                "GLM-5.3-Flash response_format 三种模式支持",
                "客户问题（AGDC2-16）：OpenAI 协议 response_format 让"
                "模型按指定格式输出（Agent 场景）；DingoRouter 不支持"
                "该结构化输出语义（修复：Router 侧支持结构化生成语义"
                "并转发至引擎）。需支持三种模式：json_object/json_"
                "schema/text。三模式各一次（原始脚本 glm53_flash_"
                "suite 口径：temperature=0、mt=2048、非流式、不传 "
                "thinking；采样参数豁免——原始脚本指定 temperature=0 "
                "原样保留，top_p/seed 未指定不注入），断言 json_object "
                "正文为合法 JSON 对象、"
                "json_schema 正文可解析且 city 为字符串、temperature "
                "为数值、键集合恰为 {city,temperature}（weather "
                "strict schema）、text 正文非空；每轮 finish=stop；"
                "usage 仅日志",
                "response_format_three_modes_support",
                "P0",
            ),
            (
                "K12",
                "GLM-5.3-Flash reasoning_effort 档位支持",
                "客户问题（AGDC2-17）：GLM-5.3-Flash 使用 GLM 自己的"
                "聊天模版，字段为 reasoning_effort 且放在 chat_"
                "template_kwargs 里；而 OpenAI 协议/参考脚本将其放"
                "在顶层。Router 需在 OpenAI 协议外层捕获该字段并传"
                "给引擎（修复：Router 侧支持语义转发）。需支持 "
                "low/high/max/空（空=不发送该字段，默认档），且不"
                "管 reasoning_effort 放在顶层还是嵌套在 chat_"
                "template_kwargs 里，请求都能被正常接受和处理并输"
                "出正常响应，否则用例失败。两种放置 × 四档各一次"
                "（原始脚本 glm53_flash_suite 口径：temperature=0、"
                "mt=2048、非流式、不传 thinking、chat_template_"
                "kwargs={clear_thinking:true}；采样参数豁免——原始脚"
                "本指定 temperature=0 原样保留，top_p/seed 未指定不"
                "注入；嵌套放置：reasoning_"
                "effort 放进 chat_template_kwargs），断言每轮 "
                "200+正文非空+finish=stop；档位对思考的实际影响"
                "（rt/reasoning 长度）仅日志留痕；usage 仅日志",
                "reasoning_effort_levels_support",
                "P0",
            ),
            (
                "K13",
                "stop 序列遵循且被截断正文前置多余字符",
                "客户问题：stop=[\"橘子\"] 的流式请求，期望输出 "
                "\"苹果、香蕉、\"（正文在停止词处截断、不含停止词），"
                "实际输出 \">苹果、香蕉、\"——被截断正文前面多输出了"
                "一个 \">\" 符号。按客户原始请求体还原（glm-5.3-flash："
                "stream=true、thinking={type:enabled}、reasoning_"
                "effort=low、stop=[橘子]、其余采样参数不发送）；"
                "KimiK3 环境不传 thinking/reasoning_effort（按 K5 "
                "口径），断言完全一致。硬断言：SSE 解析成功且有正文增"
                "量；finish=stop；合并正文严格等于 \"苹果、香蕉、\""
                "（多余前缀/停止词泄漏/未截断均 FAIL）；正文不含 "
                "\"橘子\"。usage 仅日志",
                "stop_sequence_prefix_leak",
                "P0",
            ),
            (
                "K14",
                "孤儿 tool 消息应 HTTP 400 拒绝",
                "客户问题：messages 中 tool 角色消息前无带 tool_calls "
                "的 assistant 消息（孤儿 tool 消息，且请求未定义任何 "
                "tools），属协议非法请求，网关应校验并返回 400 Bad "
                "Request；实际返回 200 放行，模型把孤儿 tool 消息当普"
                "通上下文推理。按客户原始请求体还原（user 后直接跟 "
                "tool tool_call_id=call_abc123，stream=true，无 tools/"
                "thinking/采样参数）；GLM-5.3 与 GLM-5.3-Flash 断言完"
                "全一致。硬断言：HTTP 400；若 200 放行（缺陷形态）："
                "取样若干 SSE 事件留证后 FAIL。响应体与 usage 仅日志",
                "orphan_tool_message_rejected",
                "P0",
            ),
            (
                "K15",
                "细粒度前缀匹配短输入缓存阈值",
                "客户问题：短文本缓存命中率不达标，根因推理引擎默认前缀缓"
                "存分块撮合的最小可缓存块长过大（vLLM 默认 640 tok 量级）"
                "，客户输入低于该块长（如 625 tok）完全不缓存；平台修复"
                "为细粒度前缀匹配（sglang prefix-match-unit=64）。覆盖两"
                "个测试点：1) 输入 64<N<640 的相同请求连发两次，断言第 "
                "2 次 cached_tokens>0（修复后应正常缓存，修复前不缓存即"
                "缺陷）；2) 输入 N<64 的相同请求连发两次，断言 "
                "cached_tokens==0（低于最细粒度不缓存）。cached_tokens "
                "取 usage.prompt_tokens_details.cached_tokens（兼容 "
                "usage.cached_tokens）。GLM-5.3 与 GLM-5.3-Flash 断言"
                "一致，非流式、不发送采样参数。响应体与 usage 仅日志",
                "short_input_prefix_cache_threshold",
                "P0",
            ),
            (
                "K16",
                "固定前缀/多轮上下文缓存命中率达标",
                "客户问题：短文本缓存命中率不达标——修复前固定前缀每轮 "
                "cached=7680/input=8693（88.35%）、多轮上下文 87.16%，"
                "均低于 90% 目标；根因 640 token 分块粒度将共享前缀截断"
                "（8192→12×640=7680，损失 512），细粒度匹配（64）后应 "
                "≈94.2%≥90%。请求规模由原始信息推算：~12800 中文字符共"
                "享前缀（≈8192 tok）+ ~780 字符/轮唯一问题（≈501 tok）"
                "。两模式：1) 固定前缀 10 轮独立请求（排除 1 轮预热实测"
                " 9 轮）；2) 多轮上下文单会话逐轮追加（回复极短），排除"
                " 1 轮预热实测 9 轮。断言两模式 cached_tokens 总和/"
                "prompt_tokens 总和均 ≥90%，任一 <90% 即 FAIL。GLM-5.3 "
                "与 GLM-5.3-Flash 断言一致，非流式、不发送采样参数。"
                "usage 仅日志",
                "prefix_cache_hit_rate_threshold",
                "P0",
            ),
            (
                "K17",
                "stop 停止符（换行符）在推理阶段生效",
                "客户契约：指定停止符为换行符 \"\\n\" 并开启思考时，停"
                "止符同样作用于推理（reasoning）输出——推理里出现的第"
                "一个换行即触发停止，正文（content）不会生成；反之若"
                "换行未触发停止、继续输出正文，则换行符未生效。适用 "
                "GLM-5.3（thinking={type:enabled} 显式开启思考——K1 "
                "口径）。硬断言：SSE 有事件；合并正文为空（stop 在推"
                "理阶段触发、正文未生成——核心）；finish_reason=="
                "stop；合并 reasoning 不含换行（停止符不泄漏）。模型"
                "真实响应（合并正文/思考全文）断言前打印（失败时同样"
                "可见）；usage "
                "仅日志",
                "stop_newline_in_reasoning",
                "P0",
            ),
            (
                "K18",
                "模型输出 JSON 可回填为下次请求输入上下文",
                "客户问题（AGDC2-28）：上次请求输出的 assistant JSON "
                "作为下次请求的输入上下文提交即报错（missing field "
                "`name`）——助手历史 tool_calls 混有空占位调用"
                "（name=\"\"、id=null）与真实 bash 调用（arguments "
                "缺开头 \"{\"、非合法 JSON）；模型侧修复已明确任何"
                "情况下不返回空 function——按用户指定不再保留空 "
                "function 场景（回放数据已移除空占位调用）。修复：解"
                "析失败后同列表有真实调用时移除空占位项再重新校验；"
                "缺 \"{\" 的 arguments 原样保留（不补）；兼容重复的 "
                "reasoning_content/reasoning_context（保留最后一个"
                "值）。按客户 "
                "agent 两步流程还原（用户指定测试逻辑）：第一个请求"
                "让模型输出技能周报数据 JSON 并落盘测试脚本同级目录"
                "下临时文件（第一步\"输出 JSON 到 *.json 文件\"）；"
                "第二个请求调用工具读取该临时 JSON 文件，将工单原始 "
                "assistant 返回数据（user→assistant→tool(工具读取结"
                "果——协议必需的工具结果配对，实测缺失被 400 拒绝)"
                "→user 追问，带 bash 工具定义，非流式）回填为输入上"
                "下文；测试完成后删除临时 JSON 文件（finally 兜底）。"
                "断言：第一个请求 HTTP 200 且正文可提取合法 JSON 对"
                "象、临时文件回读一致、第二个请求 HTTP 200+choices"
                "+message——上次输出 JSON 必须可作为下次输入上下"
                "文，报错复现即 FAIL；不断言 arguments 被补 \"{\""
                "（通过 router 不代表该字符串成为合法参数 JSON）。后"
                "续问题（开发文档）：修复上线后新问题 "
                "tool_call_id 悬空引用（must reference an unanswered "
                "tool call）——根因为模型返回空 function（id=null），"
                "客户端以 missing_tool_call_id 回填错误结果后被协议"
                "校验拒绝；根上解决为模型不返回空 function。第三个请"
                "求（根因断言）复刻工单首个 user 回合（带 bash 工具"
                "定义），断言模型发起工具调用且每条调用 name/id 非"
                "空、arguments 为合法 JSON 对象。适用 GLM-5.3；采样"
                "参数不发送——test_k 保持原始测试参数（工单原始请"
                "求未指定，不注入），"
                "三个请求一致",
                "output_json_as_input_context",
                "P0",
            ),
            (
                "K19",
                "单次请求图片数超限（>16）应拒绝并返回恰当错误",
                "客户问题：单次请求携带超过 16 张图片导致请求失败；根"
                "因服务端 serving-pool 显式配置 --limit-mm-per-prompt "
                "{\"image\":16,\"video\":1,\"audio\":0}（vLLM 多模态"
                "单项限额）。契约：超限请求应失败并返回恰当错误信息"
                "（参考 \"At most 16 image(s) may be provided in one "
                "prompt\"）。代码生成 17 张 32x32 纯色 PNG（base64 "
                "data URL，无外部依赖），单条 user 消息携带 17 个 "
                "image_url part 提交，断言响应失败（非 200）且错误信"
                "息含 \"at most 16 image\"（大小写不敏感）——恰当拒"
                "绝则 PASS；200 放行（限额未生效）或信息不含该模式均"
                " FAIL。模型真实响应（状态码/响应体全文）断言前打印"
                "（失败时同样可见）。适用 GLM-5.3-Flash；不发送采样"
                "参数（test_k 整套件保持原始测试参数——无全局注入"
                "口，手工 payload 直发）；"
                "恰好 16 张正向对照未纳入（测试要点仅两条且避免重度"
                "视觉计算）",
                "over_image_limit_rejected",
                "P0",
            ),
            (
                "K20",
                "1M 上下文请求应被正常支持",
                "客户问题：请求报错 \"Input length (918451 tokens) "
                "exceeds the maximum allowed length (781754 tokens). "
                "Use a shorter input or enable --allow-auto-truncate."
                "\"（invalid_request_error——网关透传 serving 侧上下"
                "文长度校验拒绝；当时最大允许 781754，未按 1M 上下文"
                "契约配置）。契约：模型需支持 1M 上下文请求——1M 量"
                "级输入应正常响应。1M=输入+输出（用户口径），总量略"
                "小于 1M：探针自校准（重复单元 ×2000 从 "
                "usage.prompt_tokens 精确计量每单元 token 数——客户"
                "端无分词器，启发式误差大：真实环境实测该单元 6.28 字"
                "符/token，chars/4 高估 57%）后按目标生成主请求：输"
                "入 960,000 tokens + 输出预算 max_tokens 覆盖思考+正"
                "文，两轮思考档位（GLM-5.3 不支持禁用思考、仅支持档"
                "位——用户口径；用户指定补 max 场景）——①low 轮"
                "（1024）常规；②max 轮（4096）最大思考负载，输出侧"
                "同步压窗口（真实环境实测默认档思考耗尽 32 预算致 "
                "content 为空——预算必须覆盖思考+正文）→ 总消耗 "
                "≈961K/964K，两种 1M 口径"
                "（1,000,000/1,048,576）下均略小于 1M（余量留给推理"
                "框架额外补充的长度；prompt_tokens 已含聊天模板开"
                "销），且高于原始故障上限 781,754 约 178K，单条 "
                "user 消息非流式提交，断言探针 200 且有 usage、每轮"
                "主请求 HTTP 200、choices/content 非空、每轮主响应 "
                "prompt_tokens（如有）>781,754（规模 sanity）——两"
                "轮均正常响应则 PASS，任一轮被拒（原始报错形态）或"
                "空响应均 FAIL。"
                "请求提示词由程序生成；跑必冷（用户加固，仅 low "
                "轮）：low 轮（含探针）材料头部置每次请求唯一 "
                "nonce（时间戳+uuid，可含中文）——前缀必不命中 "
                "KV 缓存，真 1M 冷 prefill（缓存只省 prefill 重算，"
                "不绕过准入长度校验/不省 KV 内存驻留与 decode 全窗"
                "注意力——核心契约验证本不受缓存影响，此为 prefill "
                "侧压测）；max 轮取消唯一前缀（用户口径：输出侧验"
                "证不受缓存影响，允许命中历史缓存加速）；1M "
                "prefill 临时"
                "上调客户端超时至 900s（finally 恢复）。模型真实响应"
                "（状态码/响应体全文）断言前每轮打印（失败时同样可"
                "见）。适用 "
                "GLM-5.3；采样参数不发送（用户指定）：test_k 保持"
                "原始测试参数（工单原始请求未指定，不注入）",
                "1m_context_request_supported",
                "P0",
            ),
            (
                "K21",
                "system 消息内嵌 tools 的非标请求结构应被接受",
                "客户问题（kimi-k3 工单原始请求体）：messages[2] 为 "
                "role=system 且无 content 字段、代之以内嵌 tools 数组"
                "（Calculator 单工具），服务端反序列化报 400 "
                "invalid_request_error/json_parse_error（\"messages[2]: "
                "data did not match any variant of untagged enum "
                "MessageContent\"）。该结构虽非 OpenAI 协议标准形态"
                "（tools 应为顶层参数），但客户业务实际在用——契约："
                "宽容解析该非标结构并正常响应（预期 200）。按工单原"
                "始请求体原样重放（模型名由环境注入，其余字段不改"
                "动），单次请求（确定性行为，无需连发），断言 HTTP "
                "200（核心——原始报错形态复现即 FAIL）、choices 存"
                "在、message 有效输出（content 或 tool_calls 非空——"
                "文本作答/工具调用响应均为成功形态）；模型真实响应"
                "（状态码/响应体全文）断言前打印；usage 仅日志；适用 "
                "Kimi-K3；采样参数不发送——test_k 保持原始测试参数"
                "（工单原始请求未指定，不注入）；打印口径：运行日志不含具体模型名（系统"
                "提示词正文含模型自我介绍，仅记字符数概要）",
                "system_message_embedded_tools_accepted",
                "P0",
            ),
            (
                "K22",
                "/v1/messages 缓存命中率应与 /v1/chat/completions "
                "基本一致",
                "客户问题：相同请求下，Anthropic 协议（/anthropic/"
                "v1/messages）前缀缓存命中率始终低于 /v1/chat/"
                "completions（\"缓存始终上不去\"）——根因：该链路 "
                "system 头部携带 x-anthropic-billing-header: 逐请求"
                "动态计费行（字符串/块数组两种 system 形态），前缀缓"
                "存要求从位置 0 连续匹配，头部逐请求变化导致整个前缀"
                "永不命中；chat 协议无此行、前缀稳定（K15/K16 已验证"
                " ≥90%）。开发修复：入引擎前条件剥离——system 开头是"
                " x-anthropic-billing-header: 行即去掉，其余内容原"
                "样保留。测试要点（用户口径）：同轮等价请求分别发"
                "送两协议（同轮同问；前缀头部渠道标记行不同——用户"
                "指定：剥离计费行后两协议前缀仍从位置 0 分叉，互不"
                "命中对方缓存条目，各自建条目/各自命中，messages 冷"
                "轮为真冷；标记差异仅数字符，对命中率影响可忽略），"
                "统计二者缓存命中率并逐轮比较——第一次请求为冷"
                "轮（两协议均无缓存可命中，不参与比较；需热轮才能统"
                "计命中率），热轮任意一轮差值超过 3 个百分点（用户"
                "指定容差）。组级判定（用户指定）：单组失败不中"
                "断后续组，5 组中至少 4 组该组全部热轮差值 ≤3 个"
                "百分点即 PASS、不足 4 组 FAIL。热轮 messages 全量"
                " miss（read=0 且 creation=0）时同轮重发一次鉴别"
                "（用户指定）：重发命中→WARN 留痕继续（偶发——疑"
                "似多实例路由/条目可见性问题）；仍 miss→该组不符合"
                "预期（剥离失效形态，判别力不变）。循环 5 次比对"
                "（用户口径：每次循"
                "环的请求消息尽量不一样）：2 组中文、2 组英文、1 组"
                "中英混合，每组前缀 ~8400-12000 tok + 每轮唯一问题"
                " ~330-550 tok，整请求长度尽量超过 8k tokens；覆盖"
                "两条剥离代码路径——块数组形态（断点挂 system 块，"
                "K3 口径）与字符串形态（断点挂 user 首块，每轮唯一"
                "问题置于断点外）。每次循环每协议 1 冷轮 + 2 热轮"
                "（用户口径；冷轮不参与比较），逐轮交替发送两协议"
                "（同轮同问），共 5 次循环 × 2 协议 × 3 轮 = 30 请"
                "求，组间间隔 3 秒（用户指定）；命中率口径：chat="
                "cached_tokens/"
                "prompt_tokens（该轮，K16 字段口径）；messages="
                "cache_read/分母（分母按 input_tokens 口径自适应——"
                "以同轮 chat prompt_tokens 为参照）。硬断言：①组级"
                "判定（用户指定）——单组失败不中断后续组，5 组中至"
                "少 4 组该组全部热轮差值 ≤3 个百分点（不足即 "
                "FAIL——缺陷形态 messages ≈0% vs chat ≈94%，差 "
                "≈90pp，五组全不符合）；②每请求 HTTP 200 且响应正"
                "常（chat："
                "choices；messages：usage+content）。热轮 cache_"
                "creation>0（前缀逐请求重建=剥离失效直接信号）与双"
                "低形态仅日志留痕。运行日志不含具体模型名；适用 "
                "GLM-5.3；采样参数不发送——test_k 保持原始测试参数",
                "cross_protocol_prefix_cache_parity",
                "P0",
            ),
            (
                "K23",
                "孤儿 tool 消息应对齐官方放行并正常消费",
                "客户问题（新工单，官方对齐口径）：messages 中 tool "
                "角色消息前无带 tool_calls 的 assistant 消息（孤儿 "
                "tool 消息，且请求未定义任何 tools），平台返回 400 "
                "（\"Invalid parameter: messages with role 'tool' "
                "must be a response to a preceeding message with "
                "'tool calls'.\"——type: alaya code error、code: "
                "invalid text request——网关层白加的校验）；而智谱"
                "官方源对同一请求 HTTP 200 正常应答「北京今天天气"
                "晴朗，气温18℃」，且模型在 reasoning 中实际引用了 "
                "tool 消息里的数据（工具数据被模型正常消费）。新契"
                "约（客户指定）：预期结果同官方一致——此类消息序列"
                "不做校验、正常出结果。与 K14 的关系：K14 为当时工"
                "单口径的原始契约（网关校验拒绝 400，保持不变——"
                "用户指令），本用例记录新客户需求（官方对齐契约）"
                "——二者输入同类、预期相反，平台采纳官方对齐修复后 "
                "K14 将 FAIL，其保留/退役由用户决定（本用例不改动 "
                "K14）。按客户新工单原始请求体还原（messages=[user "
                "查北京天气、assistant 纯文本（无 tool_calls——孤"
                "儿条件）、tool tool_call_id=call_weather_001 "
                "content={city:北京,temp_c:18,condition:晴}、user "
                "要求据工具数据一句话作答]、max_tokens=200、非流"
                "式、无 tools/thinking），单次请求（确定性行为，无"
                "需连发），断言 HTTP 200（核心——原始 400 拦截形态"
                "复现即 FAIL，报文引用原始报错文案）、响应合法 JSON "
                "且 choices 非空、message 有效输出（content 或 "
                "tool_calls 非空——官方形态为正常答句；思考耗光无输"
                "出+finish=length 以 reasoning_effort=low 回退重发—"
                "—K24/K25/K27 口径，双强度均未产出即 FAIL）；官方行为"
                "细节（输出/推理引用工具数据要素——北京/18/晴）软校"
                "验仅日志；finish/usage 仅日志；采样参数不发送——"
                "test_k 保持原始测试参数（工单原始请求未指定，不注"
                "入）；模型真实响应（状"
                "态码/响应体全文）断言前打印；适用 GLM-5.3；运行日"
                "志不含具体模型名",
                "orphan_tool_message_accepted",
                "P0",
            ),
            (
                "K24",
                "双请求正常响应（思考耗尽预算 low 强度回退）",
                "客户问题（新工单）：客户的两个请求（中文同音词与言部"
                "汉字写作题、英文数学题），temperature=0.0、"
                "max_completion_tokens=32768（工单原始字段名，非 "
                "max_tokens）、非流式，期望均正常响应并返回正文。风"
                "险形态（用户指定）：默认 max 思考强度下思考可能耗"
                "光预算——正文空、finish=length。回退契约（用户指"
                "定）：第 1 轮按工单原始请求体直发（不带 "
                "reasoning_effort）；有正常正文即通过；耗光的请求"
                "以 reasoning_effort=low（GLM 顶层思考强度参数，"
                "K20 口径）重发，断言相同；第 2 轮只重测耗光的"
                "（已通过不重测）。采样参数保持原始（用户指定）：两"
                "请求体均显式 temperature=0.0——工单原始请求体为唯"
                "一口径（test_k 整套件不参与全局采样覆盖），"
                "top_p/seed 不注入。硬断言（每轮每请求）：①HTTP "
                "200；②合法 JSON 且 choices 非空；③message 有效输"
                "出（content 或 tool_calls 非空）；第 1 轮耗光形"
                "态转 low 回退不直接 FAIL，正文空且 finish≠length "
                "直接 FAIL，low 回退仍无正文即 FAIL（双强度均未产"
                "出——留证交开发）；finish/usage 仅日志；模型真实"
                "响应（状态码/响应体全文）断言前打印；适用 "
                "GLM-5.3；运行日志不含具体模型名",
                "dual_request_response_with_effort_fallback",
                "P0",
            ),
            (
                "K25",
                "assistant 历史重复 reasoning_content 字段应被兼容接受",
                "客户问题（工单跟进）：多轮对话回填 assistant 历史时，"
                "同一条消息携带两个 reasoning_content 字段（两轮历史"
                "思考未去重地拼接成同键重复）与上一次请求的正文；客"
                "户原始工单还曾因思考内容含 They're/I'm/It's 等英文"
                "撇号导致 JSON 破损。契约（用户指定）：预期不报错、"
                "正常响应；第一个 reasoning_content 被第二个覆盖（宽"
                "松解析保留最后一个值，K18 修复口径）。因需两段真实"
                "思考，共发三次请求（用户指定，JSON 链式回填——第 "
                "1/2 次响应 JSON 作为下一请求输入、思考随历史一并"
                "回填；提示词为测试自行设计，工单未携带具体提示词"
                "——用户口径仅要求结构）：第 1 次 user 单轮要求仅输"
                "出 JSON（响应用于第 2 次请求输入回填）；第 2 次 "
                "messages=[assistant(content=第 1 次正文（JSON）, "
                "reasoning_content=第 1 次思考), user 追问]（回填第 "
                "1 次历史，单键经 dict 表达——K18 口径，要求仅输出 "
                "JSON——响应用于第 3 次请求输入回填）；第 3 次 "
                "messages=[assistant(content=第 2 次正文（JSON）, "
                "reasoning_content=第 1 次思考, reasoning_content=第 "
                "2 次思考), user 追问]，流式。重复键无法经 dict 表"
                "达——手工拼接 JSON 文本直发；正文/思考可能含单引"
                "号/双引号/换行（用户指定兼容要求），动态值一律 "
                "json.dumps 全转义后拼接，发送"
                "前三重自检（raw body 可被 json.loads 解析、"
                "reasoning_content 键出现次数==2、转义回读值一致——"
                "回读保留最后一个重复键，模拟服务端宽松解析）。硬断"
                "言：第 1/2 次请求思考与正文均非空（构造数据源——被"
                "测环境应开思考，GLM-5.3 默认开思考）、正文为合法 "
                "JSON（JSON 链——作为下一请求输入回填，断裂即场景"
                "无法构造 FAIL；容忍 markdown 代码块围栏）；第 3 次请求"
                "HTTP 200（核心——报错/4xx 复现即 FAIL）+ SSE 事件"
                "非空 + 合并正文非空 + finish_reason 合法。耗光回退"
                "（K24 口径）：max_tokens=8192 下默认 max 档思考可能"
                "耗尽预算（正文空+finish=length）——该形态以 "
                "reasoning_effort=low（GLM 顶层思考强度参数，K20 口"
                "径）仅重发耗光请求（第 3 次重发构造不变仅加顶层 "
                "reasoning_effort 字段——HTTP 200 核心契约首次请求"
                "已达成，重复键历史被接受不以正文是否为空转移），断"
                "言相同；正文空且 finish≠length 直接 FAIL；low 回退"
                "仍无正文即 FAIL（双强度均未产出——留证交开发）。"
                "引号覆盖"
                "度软观察：三个回填值均不含引号/换行字符时 "
                "record_warning 留痕（引号兼容路径本次未被实际覆盖，"
                "构造本身已保证安全，不判失败）。采样参数不发送——"
                "test_k 保持原始测试参数（工单原始请求未指定，不注"
                "入）。max_tokens=8192 为客户工单原始口径，"
                "三次请求一致；usage 仅日志；模型真实响应（状态码/"
                "合并正文/思考）断言前打印（失败时同样可见）；适用 "
                "GLM-5.3",
                "duplicate_reasoning_content_history_accepted",
                "P0",
            ),
            (
                "K26",
                "工具 schema 负向前瞻正则应被兼容放行",
                "客户问题：工具参数 schema 的 pattern 包含 ^(?!...) "
                "负向前瞻正则——后端编译为 structural_tag 生成约束时"
                "底层语法编译器不支持 lookahead：非流式报 400"
                "（Failed to compile structural_tag grammar——"
                "Lookahead is not supported yet）、流式报 "
                "provider_unavailable（upstream_stream_error）。修"
                "复（frontend 预处理兼容，非编译器新增 lookahead 支"
                "持）：GLM-5.3+glm47 解析器+SGLang、tool_choice="
                "auto、工具未显式 strict、schema 含 ^(?! 开头正则时"
                "命中——仅将生成约束工具副本置 strict=false 绕过强"
                "制编译，原始 schema/工具描述/格式约束保留；该路径"
                "不再由 grammar 强制保证参数满足完整 schema。按触发"
                "形态构造：path 参数 pattern 以 ^(?! 开头（禁止路径"
                "穿越）、不显式 strict、tool_choice=auto，非流式+流"
                "式各发一次。断言：非流式 HTTP 200+choices 非空+"
                "message 结构存在；流式 HTTP 200+SSE 事件非空+至少"
                "一个含 choices 数据块——报错复现即 FAIL；不断言工"
                "具被调用与参数满足 pattern（兼容绕过明确口径）。适"
                "用 GLM-5.3；采样参数不发送——test_k 保持原始测试参"
                "数（工单原始请求未指定，不注入），两个请求一致",
                "negative_lookahead_tool_pattern_accepted",
                "P0",
            ),
            (
                "K27",
                "历史非法 JSON arguments 应被容忍",
                "客户问题（AGDC2-19，codex 客户端 + MCP 工具场景）："
                "模型输出的工具调用 arguments 本身非合法 JSON（两处"
                "括号错误——\"refId\": \"A\"}] 缺 }、40}}}] 处多 }，"
                "上游流式日志证实由模型产生）；客户端执行失败、回放"
                "全量历史，服务端校验历史 tool_calls 的 arguments 直"
                "接 400（Assistant tool call function.arguments "
                "must be valid JSON）——纯服务端问题，与 codex 客户"
                "端无本质关系。修复：历史无法解析的 arguments 按字符"
                "串保留、不再 400、让模型继续纠正。复刻客户链路"
                "（user→assistant(畸形 arguments 调用，保真浓缩版—"
                "—两处错误形态与关键结构原样、场景自检必非法)→"
                "tool(执行失败结果，协议配对必需)→user 追问修正重试，"
                "带 MCP 工具定义，非流式），断言 HTTP 200（核心——报"
                "错复现即 FAIL）+choices 存在+message 结构存在+模型"
                "发起修正工具调用且每条调用 name/id 非空、arguments "
                "为合法 JSON 对象（修正行为——修复目的\"让模型继续纠"
                "正\"）；不断言历史被改写/修复。耗光回退（K24/K25 口"
                "径）：预算 16k（max_tokens=16384，工单未载），默认档"
                "思考仍可能耗尽预算（无正文无调用+finish=length——首跑"
                "实测 2048 预算 reasoning_tokens 全耗），以 "
                "reasoning_effort=low 重发，断言相同；双强度"
                "均未产出即 FAIL。适用 GLM-5.3；采样参数不发送——"
                "test_k 保持原始测试参数（工单原始请求未指定，不注"
                "入）",
                "invalid_arguments_history_tolerated",
                "P0",
            ),
            (
                "K28",
                "模型输出字段核验（尾裸/回流/工具参数）",
                "客户问题（AGDC2-24，TR-20261016-02 九章云-模型输出字"
                "段核验）：客户探针报告三项判据——T1 content 尾部裸 "
                "</think> 残留（0 次为通过，被测平台曾 2/15 不通"
                "过）、T2 字段回流（content→reasoning，0 次为通"
                "过）、T3 工具参数完整性（arguments 合法完整 JSON 且 "
                "reasoning 无 <arg_key>/<arg_value>/</tool_call> 原"
                "生标记，100% 为通过）；length 截断只记录不判定。将"
                "客户探针（scripts/probe_think_tag.py）与数据集"
                "（requests/AGDC2-24，工单原始参数 stream=true、"
                "max_tokens=8192、reasoning_effort=max 原样保留）纳"
                "入框架：3 用例×5 次（--runs 硬编码 5，用户指定）流"
                "式请求，只评被测平台（不跑对照），逐条留存 raw 并"
                "统计三项；raw 目录：Jenkins→builds/<TESTER>/"
                "<BUILD_NUMBER>/origin_raw/AGDC2-24/<model>/（与 "
                "allure-report 同级），手动→origin_raw/AGDC2-24/"
                "<model>/<timestamp>/。断言：全部 HTTP 200、T1=0、"
                "T2=0、T3=100%——任一不符合即 FAIL。模型名由环境注"
                "入；请求体不含 temperature/top_p/seed——按用户指定"
                "保持工单原始请求体不变、不注入采样参数",
                "output_fields_think_tag_probe",
                "P0",
            ),
            (
                "K29",
                "双协议零增量响应与工具调用核验",
                "客户问题（AGDC2-25，九章云 Alaya GLM-5.3 网关）：同一"
                "段业务会话报文（195 条消息/19 个工具/stream=true/"
                "max_tokens=4096）分别请求 /v1/chat/completions 与 "
                "/anthropic/v1/messages——OpenAI 协议 13 次中 5 次零"
                "增量响应（HTTP 200、SSE 结构完整但 delta.content/"
                "reasoning_content/tool_calls 三类增量均空、usage."
                "completion_tokens>0），工具调用仅 4/13；Anthropic "
                "协议 8/8 返回工具调用、零增量 0/8。客户探针"
                "（scripts/probe_alaya.py）+ 数据集"
                "（requests/AGDC2-25 两份协议请求体）纳入框架：两种"
                "协议各发 --n 硬编码 10 次（用户指定）流式请求，逐条"
                "留存 raw 并统计三项判据——有效请求 ==10、零增量 "
                "==0、返回工具调用 ==100%（10/10），任一不符合即 "
                "FAIL；每协议追加 1 次强制工具调用（tool_choice "
                "required/any，仅观察不计入）。raw 目录：Jenkins→"
                "builds/<TESTER>/<BUILD_NUMBER>/origin_raw/AGDC2-25/"
                "<model>/（与 allure-report 同级），手动→"
                "origin_raw/AGDC2-25/<model>/<timestamp>/。模型名由"
                "环境注入；stream/max_tokens=4096 按脚本口径覆盖；"
                "temperature/top_p 原始未指定——按用户指定保持不指"
                "定（不注入）",
                "dual_protocol_zero_delta_tool_call",
                "P0",
            ),
            (
                "K30",
                "/v1/responses 校验码输出与 token 计数核验",
                "客户问题（合成短文本 Token 对照测试，/v1/responses "
                "接口）：probe 三项断言未通过——请求明确要求只输出 "
                "SYNTHETIC_SHORT_TEXT_MARKER 实际正文输出 "
                "'4b69a88e6b'（模型未遵守指令）；input_tokens=52 超"
                "基准 43 ±3%（区间 41.71-44.29——整数取值 42/43/"
                "44）；output_tokens 报告 295 而实际可见输出仅 10 "
                "字符且 reasoning_tokens=0（计数与实际文本量明显不"
                "成比例，存在统计口径或隐藏推理未计入疑点）。按客户"
                "原始 curl 还原：POST {base}/v1/responses"
                "（Responses API），input 两消息（content 均 "
                "input_text 类型）、stream=true、max_output_tokens="
                "1024 原样，模型名由环境注入，采样参数原始未指定—"
                "—保持不注入。断言（任一失败即整体失败）：HTTP 200 "
                "且流式结构完整；终态事件 status == completed"
                "（failed/incomplete/cancelled 或无终态事件即失"
                "败）；合并正文严格等于校验码；usage.input_tokens∈"
                "[42,44]；output_tokens 满足 reasoning_tokens ≤ "
                "output ≤ reasoning + len(正文)（总计=思考+正文，1 "
                "token/字符宽松上界）",
                "responses_api_marker_output_usage",
                "P0",
            ),
            (
                "K31",
                "json_object 嵌套结构完整输出与预算回退核验"
                "（256→512，chat+msg 双协议）",
                "客户问题（工单 P1 R-01+A-07a/A-07b，结构化输出）："
                "官方行为 HTTP 200、content 为合法 JSON（嵌套对象/"
                "数组均可解析）；贵方实测 finish_reason=length、"
                "content 为空字符串、思考内容占满 max_tokens=256——"
                "A-07a（嵌套对象 user.name/user.age/address.city）"
                "与 A-07b（数组 3 个 id+title 对象）两种请求各 3 发"
                "全部该形态（3 采样 0 过，2026-11-03）。用户确认：思"
                "考消耗配额致空正文/截断在官方与被测均有一定概率发"
                "生——验收口径调整为预算回退链（用户指定）：核心需"
                "求为在 max_tokens 内能返回完整合法 JSON。chat+msg 双"
                "协议（msg 无 json_object 参数语义——同一 prompt 引"
                "导）× 工单两形态（提示词/请求体工单原样，chat 字段"
                "序 model/messages/max_tokens/response_format、无 "
                "stream 字段）× 预算回退链：轮一 max_tokens=256（工"
                "单原值）——HTTP 200+正文非空+json.loads 成功+嵌套结"
                "构齐备（递归宽容：含 name+age 的 user 对象与含 "
                "city 的 address 对象 / 对象数组每元素含 id+title，"
                "裸数组或对象包裹均认可，数量=3 与类型留观察）→直接"
                "达标；不满足（空正文/json 截断或非法/结构不齐）→"
                "回退 max_tokens=512 同请求重验——满足→测试通过+警"
                "告留痕（警告显示 256 输出空正文或 json 截断及 "
                "finish 状态）；两轮均不满足→FAIL（输出两轮各自形"
                "态）。HTTP 非 200 直接 FAIL（回退链仅针对正文形"
                "态）。历史记录：初版按 R-01 设计（三接口 chat/"
                "responses/msg × 两形态 × 各 2 次）；A-07 证据后重"
                "构为预算回退链并聚焦双协议（用户指定），/v1/"
                "responses 轮移除。模型名由环境注入；采样参数/thin"
                "king/stream 工单未指定——不注入",
                "json_object_nested_empty_content",
                "P1",
            ),
            (
                "K32",
                "temperature 原厂区间 [0, 2] 放行与越界校验"
                "（chat+msg 双协议）",
                "客户问题（工单 P1 R-02+A-03，参数校验）：官方行为 "
                "HTTP 200（原厂取值区间 [0, 2]，1.5 合法）；贵方最"
                "新实测（A-03，2026-11-03）chat 三发 "
                "temperature=1.5 全部 HTTP 400，错误体「temperature"
                " 超出范围 [0, 1]」——本地收紧到 [0, 1]；历史形态"
                "（R-02）6 发全部 400 通用「模型服务调用失败」"
                "(upstream_error)。整改建议（即预期结果，用户指"
                "定）：放开 temperature 到原厂支持的 [0, 2] 区间"
                "（原合法区间 [0, 2) 调整为 [0, 2]——上界端点 "
                "2.0 移入放行），或按原厂取值原样透传，不做本地收"
                "紧；保留非法参数校验（越界 400 并指明参数名与区"
                "间）。本用例双向验收（chat 放行点按工单 A-03 三"
                "发依序复现，其余组合每组合 1 次——K6 先例）双协"
                "议覆盖：chat 协议按原厂区间 [0, 2]——A-03 三发"
                "复现 temperature=1.5、content=\"只回复:好\"、"
                "max_tokens=32（请求体工单原样：字段序 model/"
                "messages/max_tokens/temperature、无 stream 字"
                "段）→ 200+choices 非空（正文/finish_reason 留观"
                "察不计判据——max_tokens=32 小配额下默认思考计入"
                "共享配额易 length/空正文，K31 域形态非本例判"
                "据）；边界轮 2.0（上界端点移入放行；请求对齐 "
                "A-03 短形态 content=\"只回复:好\"+max_tokens=32"
                "+无 stream 字段——用户指定 2026-11-09，本例主目"
                "的为验证 temperature 支持范围，短请求短响应）→ "
                "200+choices 非空（正文/finish_reason 留观察，"
                "K31 域形态非判据——主判据=2.0 被接受 200）；左"
                "边界轮 0.0（下界端点——[0, 2] 含 0.0，用户指定 "
                "2026-11-09 新增验证，此前下界仅由 -0.5 越界轮间"
                "接验证；长形态 content=\"请用一句话介绍你自己。\""
                "+max_tokens=1024）→ 200+choices 非空（正文/"
                "finish_reason 留观察——主判据=0.0 被接受 200）；"
                "越界轮 2.5 与 -0.5（max_tokens=1024——所有轮均"
                "须 max_tokens 限制，用户指定 2026-11-09）→ 400+"
                "错误体指明参数名 temperature+含上界数字 2（区间痕迹辅"
                "助下限口径——错误体含 request id 数字串可能恒满"
                "足，本地收紧主判据在放行轮 200）；msg 协议"
                "（/anthropic/v1/messages）按 Anthropic 官方区间 "
                "[0, 1] 分别校验（A-03 未涉及 msg，维持原口径）——"
                "放行轮 temperature=0.5（工单原值 1.5 在该协议官方"
                "语义下越界，不可作放行点）与 0.0（下界端点——用"
                "户指定 2026-11-09 新增验证，双协议口径一致）→ "
                "200+正文非空+stop_reason 自然结束，越界轮 1.5"
                "（工单原值，与 chat 侧同值不同判——验证网关按协"
                "议语义分别校验）、2.0 与 -0.5 → 400+错误体指明"
                "参数名 temperature+含上界数字 1。非流式直发，每发 60s 硬超时"
                "（K32_HARD_TIMEOUT 用例内自定覆盖全局 timeout——"
                "小请求正常返回毫秒级-秒级，挂起/严重延迟快速失"
                "败：超时即 FAIL 留痕，仅本用例生效不影响他例）；"
                "工单原始值 temperature/max_tokens 原样保留并豁免"
                "全局采样覆盖；top_p/seed/thinking 工单未指定——"
                "不注入；所有轮均须 max_tokens 限制（用户指定 "
                "2026-11-09，当前无限制的 chat 越界轮取 1024）；"
                "msg 协议 max_tokens 为必需字段",
                "temperature_range_validation",
                "P1",
            ),
            (
                "K33",
                "top_logprobs=5 放行核验（未开 logprobs 也接"
                "受，chat+msg 双协议）",
                "客户问题（工单 P2 A-04，参数校验）：官方行为"
                "不变——top_logprobs=5 官方 HTTP 200 接受（未开 "
                "logprobs 时也接受）；贵方最新实测（A-04，"
                "2026-11-03）chat 三发 top_logprobs=5 单独出现（无 "
                "logprobs）全部 HTTP 400，错误体「top_logprobs "
                "is only allowed when logprobs is enabled」——对"
                "未开 logprobs 的 top_logprobs 额外拒绝。整改建议"
                "（即预期结果）：按官方行为处理 top_logprobs（未"
                "开 logprobs 时也接受），不额外拒绝；若上游确实"
                "不支持，错误体应说明能力缺失而非参数非法。用户"
                "判定口径（2026-11-06）：top_logprobs=5 不要拒"
                "绝、按官方 HTTP 200 即可；正文为空不判定失败"
                "（R-03 轮移除，仅保留 A-04 请求——用户指定 "
                "2026-11-06）。双协议覆盖：chat 协议——A-04 "
                "三发复现 top_logprobs=5 单独出现（content=\"只回"
                "复:好\"、max_tokens=32，请求体工单原样：字段序 "
                "model/messages/max_tokens/top_logprobs、无 stream "
                "字段）→ 200+choices 非空（正文/finish_reason/"
                "logprobs 结构留观察不计判据——小配额+默认思考计"
                "入易 length，K31 域形态；客户预期仅定义接受语"
                "义）；"
                "msg 协议（/anthropic/v1/messages）无 logprobs 参数"
                "语义——A-04 镜像 3 发（top_logprobs 单独出现、"
                "content 工单原样字符串、max_tokens=512 套件必需字"
                "段值——工单 32 为 chat 小配额口径）硬断言统一行"
                "为：全部 400 且错误体指明字段"
                "（含 'logprobs'，top_logprobs 子串覆盖，能力缺失"
                "说明口径）或全部 200；正文为空不判定失败（用户"
                "口径：top_logprobs=5 不拒绝、官方 200 即可——空"
                "正文留观察，用户指定 2026-11-06），混现即 FAIL。"
                "max_tokens/thinking/采样参数工单未指定——不传"
                "（不注入）；msg 协议 max_tokens 为必需字段；A-04 "
                "工单三发采集间隔 1s（节奏非判据），复现按套件相邻 "
                "3s",
                "top_logprobs_stable_support",
                "P2",
            ),
            (
                "K34",
                "多模态媒体块该拒未拒（msg 侧静默丢弃返回 200）"
                "应 400 明确拒绝（chat+msg 双协议）",
                "客户问题（工单 P2 R-04 补充证据 A-01，多模态）：官"
                "方行为 glm-5.3 为非多模态模型——请求携带图片/音"
                "频/视频/文档（base64 与 URL 两种载体）必须 400，"
                "返回 2xx 即不合格；原始问题：msg 协议下返回 200 "
                "该拒未拒——媒体块被静默丢弃：prompt_tokens 仅 "
                "17-43（媒体未进入分词器）、正文自述『没有收到"
                "视频/音频/文档』，同一素材 chat 协议渠道返回 400"
                "（同一渠道、同一文件、两种协议两种结果）；整改建"
                "议（客户给出）：/v1/messages → OpenAI 转换层对 "
                "media block（video/audio/document）前置校验返回 "
                "400 并给出明确文案，不得剥离媒体块后继续转发，"
                "URL 载体同样必须 400、不得自行抓取/转文字/降级纯"
                "文本，chat 协议也应相同处理。本用例双协议各 5 发"
                "共 10 发（用户指定：message 协议和 chat 协议都要 "
                "5 轮请求）：msg 5 发按工单原始记录依序复现（缺陷"
                "复现轮）——document×base64、text+audio×base64"
                "（文本块在前——工单原序）、video×base64、"
                "video×url（沿用本仓现有 MDN flower.mp4 地址——"
                "工单原 test-videos.co.uk 不复用，用户指定保留现"
                "有 URL）、video×base64；chat 5 发为同素材/同提"
                "示词/同块序镜像（整改『chat 协议也应相同处理』"
                "——一致性核验轮；part 映射：document→file part"
                "（file_data data URL——OpenAI chat 协议文档输"
                "入标准形态）、audio→input_audio、video→"
                "video_url（base64 发用 data URL））；媒体数据工"
                "单未提供完整 data——代码生成有效 base64（最小 "
                "PDF/WAV/MP4 容器，内存生成不落临时文件；拒绝校"
                "验在媒体块类型层不依赖可解码内容；双协议第 3/5 "
                "发共用同一生成 MP4——判定在类型层）；"
                "max_tokens=1024 工单原值（10 发同值镜像，豁免注"
                "入）；请求体不含 stream 字段（工单原始格式，两协"
                "议默认非流式）；thinking/采样参数未含——不注"
                "入；相邻间隔 3s。硬断言每发：HTTP 400（200=静默"
                "丢弃缺陷复现——A-01 形态（prompt_tokens 仅 "
                "17-43+正文自述未收到）留证）+ 错误体含对应媒体"
                "类型关键词（中英任一命中：document/文档/pdf、"
                "audio/音频/语音、video/视频，大小写不敏感——"
                "20261104 实测整改错误体为中文，原纯英文口径误判"
                "已扩展双语匹配）；'text' 痕迹留观察日志",
                "multimodal_rejection_error_detail",
                "P2",
            ),
            (
                "K35",
                "关闭思考应按原厂 400 拒绝（enable_thinking="
                "false 与 thinking.type=disabled 双路径，chat+msg "
                "双协议）",
                "客户问题（工单 P1 R-07 补充证据 A-02 · chat/msg "
                "协议关闭思考的请求被放行，接口协议）：官方行为"
                "：原厂对关闭思考返回 400（原厂 HTTP 400）；贵"
                "方实测（A-02，2026-11-03 采集，2 发均 HTTP "
                "200）：渠道返回 200 并正常出文——chat 发 "
                "enable_thinking=false 放行且响应带 reasoning_"
                "content（思考仍开启，reasoning_tokens=91）、"
                "msg 发 thinking.type=disabled 放行且 content 带 "
                "thinking 块（思考仍开启），对照记为 http_"
                "status 400→200（HTTP 状态语义）；预期行为（整"
                "改）：统一关闭思考的拒绝口径——enable_thinking="
                "false 与 thinking.type=disabled 两条路径均按原"
                "厂返回 400，不得一条拒一条放。本用例按客户原始"
                "请求 A-02 依序复现（用户指定——两条路径都要按"
                "官方行为返回 400，覆盖两种协议）：路径1 chat 协"
                "议（/v1/chat/completions）enable_thinking=false"
                "（工单原样：content='23+19 等于多少？'、"
                "max_tokens=512、不含 stream 字段）；路径2 msg 协"
                "议（/anthropic/v1/messages，x-api-key + "
                "anthropic-version 头——K3 先例）thinking={"
                "'type': 'disabled'}（工单原样：content='23+19"
                "=?' 为字符串、max_tokens=512、stream=false 显式"
                "携带）；硬断言每路径：HTTP 400（200=放行缺陷"
                "复现——A-02 形态：200 且正常出文（思考仍开启）"
                "；500 等=非合规拒绝）；错误体参数名痕迹（路径1 "
                "enable_thinking/路径2 thinking）留观察不计判据"
                "（官方拒绝文案常含参数名；排除通用『模型服务调"
                "用失败』不含参数名缺陷形态）；max_tokens=512 "
                "工单 2 发同值（豁免注入）；采样参数未含——不注"
                "入；相邻间隔 3s",
                "enable_thinking_param_rejection",
                "P1",
            ),
            (
                "K36",
                "finish_reason 判定对齐官方（stop 语义——流式/多段/结构化 × 双协议）",
                "客户问题（工单 P1 R-06，接口协议）：官方行为 "
                "finish_reason=stop（20_chat_stream_002 / "
                "20_chat_ms_001 / 20_chat_structured_002 三例）；贵"
                "方实测同一请求渠道返回 finish_reason=length，官方"
                "返回 stop（三例一致复现）。整改建议：对齐 "
                "finish_reason 判定——思考 token 不应把正常结束的请"
                "求判成 length 截断。本用例按官方行为进行预期断言"
                "（用户指定），覆盖三种请求形态 × 双协议（chat + "
                "msg——K31 起口径）：流式（SSE 收集终止字段与正文）、"
                "多段（content 数组多段文本）、结构化（chat "
                "response_format=json_object / msg prompt 引导——"
                "K31 先例），硬断言每形态 × 每协议：终止语义对齐官"
                "方——chat finish_reason=='stop' / msg "
                "stop_reason=='end_turn'（length/max_tokens=缺陷"
                "复现：思考 token 计入判定把正常结束的请求误判截"
                "断）+ 正文非空（正常结束的佐证；正文空+length 为"
                "K31 思考耗光形态，非本例口径）。max_tokens=512（工"
                "单未附原始 payload——适中值，正文远低于配额而计入"
                "思考的实现易触顶误判，对判定语义敏感）；thinking/"
                "采样参数未指定——不注入",
                "finish_reason_stop_semantics",
                "P1",
            ),
            (
                "K37",
                "n=2 请求应 400 拒绝且不挂死（返回提示信息）",
                "客户问题（工单 P0，异常）：贵方实测 n=2 请求无响"
                "应直至超时——参数电池 3/3 轮 TimeoutError（已重"
                "试 1 次仍超时）、协议电池 2 例 ReadTimeout、直连"
                " 300s 超时，该挂死同时导致模块 4 的 n=2 探针被记"
                "为『无效』而未计失败；官方行为为 HTTP 200（返"
                "回 1 个 choice）。客户明确需求（2026-11-06，契"
                "约口径）：当 n=2 时 400 拒绝，并返回相应的提示"
                "信息，但不能卡死（示例响应：HTTP 400 "
                "{\"code\":1210,\"message\":\"参数有误：glm-5.3 "
                "仅支持 n=1，收到 n=2 (request id: ...)\"}）——"
                "客户明确需求优先于官方对齐（用户指定按新契约断"
                "言，替代原官方 200+单 choice 口径）。本用例"
                "chat 2 发对齐工单 055/056 口径，工单原值原样保"
                "留（说一句话。/max_tokens=16/n=2），单发直发不"
                "重试，requests timeout=30s 硬超时（超时即 "
                "FAIL——挂死复现显式计入失败，纠正『无效不计失"
                "败』漏报形态）；硬断言每发：30s 内返回 + HTTP "
                "400（200 放行=未按客户契约拒绝；500 等=非合规"
                "拒绝）+ 提示信息指明 n 参数限制（响应体合法 "
                "JSON、message 非空且含 n=1/n=2 子串，大小写不"
                "敏感）；错误码 code（如 1210）/request id/"
                "elapsed 留观察；chat 单协议（n 为 OpenAI 参数，"
                "msg 无该语义——工单证据仅 chat，msg 未知参数行"
                "为由 K33/K35 覆盖）；thinking/采样参数未含——"
                "不注入",
                "n2_request_hang_timeout",
                "P0",
            ),
            (
                "K38",
                "max_completion_tokens 别名单 token 请求不挂起"
                "（与 tokens 主路径同延迟水平）",
                "客户问题（工单 A-A01，异常）：官方判定通过——"
                "max_completion_tokens 别名为单 token 请求，被接受"
                "并按 max_tokens 语义立即截断返回；贵方实测客户原"
                "始请求 1 发即挂起——180s 请求超时、无响应（HTTP "
                "0，采集未落盘）。预期行为（整改）：不得触发 180s "
                "级挂起；需与 tokens 主路径同延迟水平。本用例按原"
                "始请求与预期行为验收（用户指定），chat 单协议 2 "
                "发：别名轮工单原样（Write a long essay about "
                "turbines.+max_completion_tokens=1，字段序 model/"
                "messages/max_completion_tokens，无 stream 字段）"
                "1 发对齐工单口径；主路径轮同 prompt max_tokens=1 "
                "对照基线 1 发。硬断言：别名轮 30s 硬超时（requests "
                "timeout=30s——对齐 K37 先例，远低于工单 180s 挂起"
                "水平；单发直发不重试——重试掩盖挂起证据且超时等待"
                "翻倍）内返回、HTTP 200（官方判定通过）+ 响应体合"
                "法 + usage.completion_tokens<=2（别名生效——单 "
                "token 截断；字段被丢弃则长文数百 token）；主路径"
                "轮 30s 内返回 + 200；同延迟水平判据：别名 "
                "elapsed<=主路径 elapsed*3+10s（容网络抖动）。超"
                "时即 FAIL 挂起复现；字节缓流形态留观察人工分派"
                "（K37 口径）；finish_reason/正文留观察（1 配额默"
                "认思考计入易空正文+length——K31 域形态非本例判"
                "据）。chat 单协议（max_completion_tokens 为 "
                "OpenAI 别名字段、Anthropic /v1/messages 无该字段"
                "——msg 未知参数行为由 K33/K35 覆盖）；模型名由环"
                "境注入；thinking/采样参数工单未含——不注入",
                "max_completion_tokens_alias_single_token",
                "P0",
            ),
            (
                "K39",
                "历史 assistant 消息 reasoning/reasoning_content "
                "双字段共存兼容核验（同值/异值 × 两字段序）",
                "客户问题（工单 AGDC2-47，接口协议）：多轮对话历史 "
                "assistant 消息同时携带 reasoning 与 reasoning_"
                "content（合法 JSON 两个不同键）即 HTTP 400、错误码 "
                "json_parse_error、提示 duplicate field reasoning_"
                "content——两字段值相同或不同均报错；单字段（仅 "
                "reasoning 或仅 reasoning_content）调用成功；客户"
                "生产调用大量报错。官方 API 验证结论（AGDC2-47 测"
                "试资料，2026-11-05 Kimi K3 官方端点）：同一请求形"
                "态 14 组合（字段变体 × 默认/关闭思考）全部 HTTP "
                "200、finish_reason=stop、回答 3——双字段共存不必"
                "然导致错误（含双字段同值/异值 × 两字段序全部 "
                "200）。预期行为（整改）：历史消息同时存在 "
                "reasoning 与 reasoning_content，无论两字段值相同"
                "或不同、哪个字段在前，均不得 400，应正常请求成"
                "功。本用例按官方验证请求原样复现（用户指定：只测"
                "双字段共存场景——单字段/无字段场景不测；调整两字"
                "段顺序 × 覆盖同值/异值），chat 单协议 4 发（相邻"
                "间隔 3s），同一三消息结构（user What is 1 + 1? "
                "Reply with only the number. / assistant "
                "content=2 携双思考字段 / user Add 1 to the "
                "previous answer. Reply with only the number.），"
                "请求体官方验证原样（字段序 model/stream/max_"
                "tokens=512/messages，stream=false，thinking 默认"
                "模式不传）：同值/reasoning 在前、同值/reasoning_"
                "content 在前（两字段均 1 + 1 = 2.）、异值/"
                "reasoning 在前、异值/reasoning_content 在前"
                "（reasoning=Compute the sum.、reasoning_content="
                "The answer is two.）。硬断言每发：HTTP 200（400 "
                "json_parse_error/duplicate field reasoning_"
                "content=缺陷复现）+ 响应体合法 + choices 非空 + "
                "正文非空（空正文+finish=length 留观察——512 预算"
                "默认思考计入耗尽属 K31 域形态；空正文且 finish≠"
                "length 即 FAIL）。finish_reason/回答含 3（官方"
                "验证回答为 3——生成质量非本例判据）留观察。显式关"
                "闭思考模式不测（官方双模式均 200 证明字段兼容性"
                "与模式正交；K35 已确立网关对关闭思考 400 拒绝口"
                "径——另一缺陷域）；chat 单协议（Anthropic /v1/"
                "messages 无 reasoning 字段形态——思考经 thinking "
                "content block 承载，msg 未知参数行为由 K33/K35 "
                "覆盖）；模型名由环境注入；thinking/采样参数官方"
                "验证请求未含——不注入；适用 GLM-5.3 与 Kimi K3"
                "（双 marker GLM53+KimiK3——工单缺陷经 Kimi K3 官"
                "方端点验证，请求同构无模型分支）",
                "reasoning_dual_field_history_accepted",
                "P0",
            ),
            (
                "K40",
                "跨协议 thinking 链路核验（msg 端点思考 block 稳"
                "定+OpenAI 体混用留证，msg 单协议）",
                "客户问题（K40 工单补充信息，2026-11-10）：客户链路"
                "为最终客户 Anthropic 协议 → 乐信网关（协议转换）→ "
                "OpenAI 协议 → 本平台；客户反馈 4 点——①存在协议转"
                "换；②已开启透传；③客户用例疑似「OpenAI 协议请求体"
                "调 Anthropic 协议接口」；④部分乐信重现请求看不到 "
                "thinking 数据。本例在 alayanew 侧回答两点：Anthropic "
                "端点对合法 thinking 请求是否稳定返回 thinking "
                "content block（「看不到 type:thinking」的正向判据"
                "——msg 链路响应映射完整性，工单「统一携带」预期在 msg 侧的口径）；混"
                "用形态行为确定性留证（无官方基线，不定 200/400 正"
                "误）。轮次（用户确认：全部三轮+消息自拟+P1）：正向"
                "稳定轮 ×3 硬断言（Anthropic 原生体 max_tokens=2048"
                "+thinking={\"type\": \"enabled\", \"budget_tokens\":"
                " 1024}——budget 取官方最小合法值且须小于 max_"
                "tokens——每发断言 HTTP 200+含 thinking block 且文"
                "本非空+含 text block 且文本非空+stop_reason=="
                "\"end_turn\"，任发缺 thinking block=客户现象在 "
                "alayanew msg 链路复现）；混用留证轮 ×2 弱断言（OpenAI "
                "体 thinking={\"type\": \"enabled\"} 无 budget_"
                "tokens——K40 工单形态混用签名——打 msg 端点，弱断"
                "言两发行为一致（状态码一致+200 时 thinking 存在性"
                "一致），全量留证）；默认档观察轮 ×1 纯观察（同消息不"
                "带 thinking，观察 thinking block 有无——对账客户第"
                " 4 点请求侧读法）。msg 端点 /anthropic/v1/messages+"
                "x-api-key+anthropic-version: 2023-06-01 头（K3/"
                "K35 先例）；非流式（客户信息未指明 stream——不注"
                "入）；模型名由环境注入；相邻间隔 3s；超时沿用全"
                "局。GLM-5.3 专用（工单模型为客户内部档位名）。不进 smoke 集"
                "：新用例首跑观察期；3+2+1 共 6 请求",
                "anthropic_thinking_block_stable_cross_protocol",
                "P1",
            ),
            (
                "K41",
                "stop 空数组应正常响应核验（400 拒绝缺陷，chat 单"
                "协议）",
                "客户问题（新工单，参数校验）：请求带 stop=[]（空数"
                "组）时平台 400 拒绝，两种错误形态（两个 request "
                "id）——上游校验错透传 {\"error\": {\"message\": "
                "\"Validation: Stop sequences array cannot be "
                "empty (...)\", \"type\": \"upstream_error\", "
                "\"param\": \"400\", \"code\": \"bad_response_"
                "status_code\"}} 与平台参数错 {\"code\": 1210, "
                "\"message\": \"max_tokens 超出范围 [1, 131072] "
                "(...)\"}；预期（整改）：正常响应、正常结束（finish"
                "=stop），不应触发模型服务的最大输出上限 128k。本用"
                "例单发 stop=[] 请求（参数处理确定性，K6/K23 先例），"
                "请求体最小构造（stop=[] 工单唯一原样参数+自拟最小 "
                "user 消息——工单未携带消息内容；max_tokens 不传——"
                "用户确认 2026-11-09：工单未提供不注入，且缺省填充"
                "上限缺陷路径恰好由不传覆盖；stream/thinking/采样参"
                "数未含——不传不注入；模型名由环境注入——工单无模"
                "型线索）。断言：1) HTTP 200（400=缺陷复现——两种"
                "工单错误文案归类留证）；2) 合法 JSON+choices 非空；"
                "3) finish_reason==\"stop\"（正常结束——工单原话；"
                "length=触发输出上限 128k 形态）；4) 正文非空。观察"
                "（不计判据）：400 时错误体归类（Stop sequences "
                "array cannot be empty→上游校验错形态/max_tokens 超"
                "出范围+code 1210→平台参数错形态）；200 时 usage."
                "completion_tokens 异常大（撞 128k 上限痕迹）留痕。"
                "超时沿用全局（工单未涉及挂死/超时语义）。chat 单协"
                "议（错误体为 chat 形态响应；msg 未知参数行为由 "
                "K33/K35 覆盖）。GLM-5.3 专用（工单无模型线索，缺陷"
                "为平台/引擎层 stop 校验与 max_tokens 上限路径，无模"
                "型分支）",
                "empty_stop_array_normal_response",
                "P1",
            ),
            (
                "K42",
                "Kimi-K3 工具调用长参数流式停流核验（间隔<30s+正常终"
                "止，chat 单协议）",
                "客户问题（工单 AGDC2-45 · Kimi-K3 流式中途停流）："
                "kimi-k3 流式请求正常出流（~70 chunk/s、已出 1480 "
                "tokens）后正文结束，连续 30s 无任何字节——无 "
                "finish_reason/tool_calls/[DONE]，连接未断，客户端按 "
                "30s 无数据取消策略断开（网关日志「客户端已断开，已中"
                "断渠道 #20 上游请求」）；多条历史请求同形态（中断、"
                "finish_reason 为空）。根因（排障报告确认）：SGLang "
                "0.5.21 kimik3_detector 工具调用解析器按完整 call 整"
                "包输出、不增量发工具参数——长参数生成阶段参数全部缓"
                "存在解析器内，SSE 无新数据无心跳（serving_chat.py 空"
                "时不 yield）；线上抓包 3 样本空窗 71.697/89.010/"
                "116.724s（恢复时一次性返回 7952/12831/12044 字符参"
                "数），均超客户 30s 取消阈值。本用例单发原样回放抓包请"
                "求 tests/data/k42_request_original.json（231,432 字"
                "节，sha256 371b1753...；78 messages/25 tools/31 历史"
                "工具调用，agentic 工作流场景——报告方法 C 口径：单并"
                "发、读空闲 180s、总时限 600s）。请求构造：messages/"
                "tools/temperature=1/max_completion_tokens=131072/"
                "stream=true/stream_options={\"include_usage\": true}/"
                "reasoning_effort=\"high\" 全部原样（抓包原样参数）；"
                "stop/tool_choice/seed/采样参数未含——不注入；model 由"
                "环境注入（用户确认 2026-11-09——与既有 K 用例一致，"
                "运行环境指向 Kimi-K3 实例）。判定（单发，四断言）："
                "1) HTTP 200 + SSE 事件流；2) 正常终止——收到非空 "
                "finish_reason 且收到 [DONE]（缺陷形态=两者皆无直至"
                "客户端断开）；3) 全程任意相邻 SSE 事件间隔 < 30s（客"
                "户取消阈值；缺陷实测 71.7-116.7s 空窗；TTFT 不计"
                "入——首 token 问题报告声明另行排查）；4) finish="
                "tool_calls 时逐 tool index 拼接 arguments 为完整 "
                "JSON 且工具名非空（报告修复验证标准 4）。观察（不计"
                "判据）：TTFT（历史实测 22.6/44.2s）、事件数、最大事"
                "件间隔及位置、工具参数增量事件数（修复标准 2 证据"
                "——长参数阶段应有多段 delta 而非整包）、参数字符数、"
                "usage、请求文件 sha256 留痕。超时：读空闲上限 180s"
                "（requests 读超时按字节间隔计——K37/K38 先例；永久停"
                "流触发 ReadTimeout=缺陷形态 FAIL）；总时限 600s 墙"
                "钟检查。chat 单协议（工单为 chat SSE 流式）。仅 "
                "KimiK3（工单模型 Kimi-K3，缺陷为 SGLang K3 工具解析"
                "器层，无其他模型分支）",
                "kimik3_long_tool_args_stream_no_stall",
                "P1",
            ),
            (
                "K43",
                "responses 端点空 input 400 拒绝核验（对齐官方，"
                "responses 单协议）",
                "客户问题（工单 AGDC2-55 · alayanew vs 智谱官方未对齐 "
                "#48）：相同请求 POST /v1/responses {\"model\": \"glm-"
                "5.3\", \"input\": [{\"role\": \"user\", \"content\": "
                "[{\"type\": \"input_text\", \"text\": \"\"}]}], "
                "\"max_output_tokens\": 32}，alayanew 返回 200（错误"
                "——空 input 文本被接受并生成 reasoning 内容，status="
                "incomplete/incomplete_details.reason=max_output_"
                "tokens，usage output_tokens=32），智谱官方返回 400 "
                "{\"error\": {\"code\": \"invalid_request\", "
                "\"message\": \"输入不能为空\", \"type\": "
                "\"invalid_request\"}}。预期（对齐官方）：400 拒绝，"
                "错误体 code=invalid_request、message 含「输入不能为"
                "空」。本用例单发非流式原样请求（请求体全部工单原样，"
                "仅 model 环境注入；responses 端点 staging 网关已"
                "有——报文实证）。断言：1) HTTP 400（200=缺陷复现"
                "——空输入被接受，响应结构 status/incomplete_details/"
                "output/usage 留证）；2) 错误体 code==\"invalid_"
                "request\"；3) message 含「输入不能为空」（对齐官方原"
                "文）。观察（不计判据）：400 时错误体全文；200 时缺陷"
                "响应结构留证。超时沿用全局（工单未涉及挂死/超时语"
                "义）。responses 单协议（缺陷为 responses 端点空输入"
                "校验缺失；chat 端点无关）。GLM-5.3 专用（工单模型 "
                "glm-5.3）。无新增数据文件（请求短小完整内联）",
                "responses_empty_input_rejected",
                "P1",
            ),
            (
                "K44",
                "reasoning_effort=\"none\" 应被接受核验（对齐官方，"
                "chat 单协议）",
                "客户问题（工单 AGDC2-55 · alayanew vs 智谱官方未对齐 "
                "#10）：相同请求 POST /v1/chat/completions（确认参数 "
                "max_completion_tokens=128 + reasoning_effort="
                "\"none\"——标题与 alayanew 错误文案双重佐证；原始消"
                "息 349,732 字符被截断不可得，缺陷为参数校验层与消息"
                "内容无关），alayanew 返回 400 {\"code\": 1210, "
                "\"message\": \"reasoning_effort 取值非法: none（glm-"
                "5.3 仅支持 low / high / max）\"}，智谱官方返回 200"
                "（finish=stop，正文非空，reasoning_content 非空 18 "
                "tokens——官方接受 none 并正常生成）。预期（对齐官"
                "方）：200 正常响应。本用例单发非流式：请求体 = 工单"
                "确认参数 max_completion_tokens=128 + reasoning_"
                "effort=\"none\" 原样 + 自拟最小 user 消息（工单消"
                "息不可得且不影响缺陷路径）；模型名由环境注入；两侧工"
                "单响应均非流式形态——stream 不传（不注入）。断言："
                "1) HTTP 200（400=缺陷复现——1210「reasoning_effort "
                "取值非法: none（glm-5.3 仅支持 low / high / max）」"
                "文案留证）；2) 合法 JSON+choices 非空；3) finish_"
                "reason 非空（对齐官方 stop 形态）；4) 正文非空。观察"
                "（不计判据）：reasoning_content 存在性/reasoning_"
                "tokens（官方 none 仍返回 18 reasoning tokens 的形态"
                "留痕——none 语义为不声明思考努力档位，官方仍产出思"
                "考）；400 时错误全文留证。超时沿用全局。chat 单协议"
                "（缺陷为 chat 参数校验过度严格）。GLM-5.3 专用（工单"
                "模型 glm-5.3）。无新增数据文件",
                "reasoning_effort_none_accepted",
                "P1",
            ),
            (
                "K45",
                "responses 端点思考计数核验（reasoning_tokens 恒 0 缺"
                "陷，responses 单协议）",
                "客户问题（工单实证，2026-11-10）：POST /v1/responses 原"
                "样请求（glm-5.3、instructions=\"Answer concisely.\"、"
                "input 单 user 消息「Compute 47*89 step by step, then "
                "reply with just the number.」、max_output_tokens=1024、"
                "stream=false）响应 200 completed——思考已下发（type=="
                "\"reasoning\" 块 summary 为完整思考过程）且已计入 "
                "output_tokens（545 vs 可见正文 \"4183\" ≈2 token），但 "
                "usage.output_tokens_details.reasoning_tokens=0——明细"
                "恒 0 与总量自相矛盾=缺陷。原样回放 ×3（每发独立断"
                "言，相邻 3s——「恒 0」稳定性复现口径）：HTTP 200+合"
                "法 JSON+output 数组；有思考内容（reasoning 块 summary "
                "非空）；有正文（message 块 output_text 非空，数值正误"
                "不定留证）；reasoning_tokens>0（恒 0/缺失=缺陷复现）"
                "且 ≤output_tokens（K30 断言4 下界口径）。请求体五字"
                "段工单原样，仅 model 环境注入；工单密钥不入库（鉴权"
                "走环境配置）；thinking/采样参数未带——不注入；非流"
                "式（stream=false 原样）；超时沿用全局。GLM-5.3 专用"
                "（工单模型 glm-5.3，缺陷为 usage 计数口径，无模型分"
                "支）。无新增数据文件",
                "responses_reasoning_tokens_counted",
                "P1",
            ),
        ],
    },
}


def get_all_test_ids() -> dict:
    """获取所有测试ID的映射表 key -> test_idx"""
    result = {}
    for marker, category in TEST_CATEGORIES.items():
        for test_info in category["tests"]:
            test_idx = test_info[0]
            result[f"{marker}_{test_idx}"] = test_idx
    return result


def get_test_func_mapping() -> dict:
    """获取测试函数名到test_idx的映射"""
    result = {}
    for marker, category in TEST_CATEGORIES.items():
        for test_info in category["tests"]:
            if len(test_info) >= 4:
                test_idx = test_info[0]
                test_func = test_info[3]
                result[test_func] = test_idx
    return result


def get_test_priority(marker: str, test_idx: str) -> str:
    """获取测试用例的优先级 (P0/P1/P2)，未找到返回 P1"""
    category = TEST_CATEGORIES.get(marker)
    if not category:
        return "P1"
    for test_info in category["tests"]:
        if test_info[0] == test_idx:
            if len(test_info) >= 5:
                return test_info[4]
            return "P1"
    return "P1"


def priority_to_criticality(priority: str) -> str:
    """将优先级 (P0/P1/P2) 映射为中文级别名（关键/重要/一般）"""
    return {"P0": "关键", "P1": "重要", "P2": "一般"}.get(priority, "重要")
