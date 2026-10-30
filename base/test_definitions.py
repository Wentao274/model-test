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
    "e_performance": {
        "name": "E. 性能指标",
        "criticality": "一般",
        "tests": [
            ("E1", "TTFT", "首Token延迟", "ttft", "P0"),
            ("E2", "TPOT", "每Token生成时间", "tpot", "P0"),
            ("E3", "ITL P50/P95/P99", "分位数统计", "itl_percentiles", "P0"),
            ("E4", "端到端延迟", "总时间", "end_to_end_latency", "P0"),
            ("E5", "吞吐量", "tokens/s", "token_throughput", "P0"),
            ("E6", "请求吞吐", "req/s", "request_throughput", "P0"),
            ("E7", "并发扩展性", "并发1→200", "concurrency_scaling", "P0"),
            ("E8", "显存占用", "GPU显存", "gpu_memory", "P0"),
            ("E9", "GPU利用率", "计算单元", "gpu_utilization", "P1"),
            ("E10", "预热时间", "首次vs稳态", "warmup_time", "P1"),
            ("E11", "Prefill速度", "不同输入长度", "prefill_speed", "P1"),
            ("E12", "突发流量恢复", "100并发恢复", "burst_recovery", "P1"),
        ],
    },
    "f_stability": {
        "name": "F. 稳定性与边界",
        "criticality": "一般",
        "tests": [
            ("F1", "空输入", "空prompt", "empty_input", "P0"),
            ("F2", "超大输入", "超max_model_len", "oversized_input", "P1"),
            ("F3", "非法参数", "temperature=-1", "invalid_parameters", "P2"),
            (
                "F4",
                "特殊字符注入",
                "SQL/Prompt注入",
                "special_character_injection",
                "P0",
            ),
            ("F5", "并发稳定性", "200+并发", "concurrent_stability", "P1"),
            ("F6", "OOM恢复", "显存耗尽", "oom_recovery", "P1"),
            ("F7", "长时间运行", "24小时", "long_running_service", "P1"),
            ("F8", "请求超时处理", "超时断开", "request_timeout_handling", "P1"),
        ],
    },
    "g_api": {
        "name": "G. API兼容性",
        "criticality": "重要",
        "tests": [
            (
                "G1",
                "OpenAI Chat Completions",
                "/v1/chat/completions 接口兼容",
                "chat_completions_api",
                "P0",
            ),
            (
                "G2",
                "OpenAI Completions",
                "/v1/completions 接口兼容",
                "completions_api",
                "P1",
            ),
            ("G3", "模型列表", "/v1/models 返回可用模型", "models_list", "P0"),
            ("G4", "Usage 统计", "usage 字段准确", "usage_statistics", "P0"),
            ("G5", "错误码规范", "401/400/404 错误码", "error_codes", "P1"),
            (
                "G6",
                "客户端 SDK 兼容",
                "Python openai",
                "client_sdk_compatibility",
                "P0",
            ),
        ],
    },
    "h_quality_chat_completions": {
        "name": "H. Chat Completions API 质量评估与回答相关性",
        "criticality": "关键",
        "tests": [
            ("H1", "生成质量", "质量对比", "generation_quality", "P0"),
            ("H2", "生成一致性", "多次生成", "generation_consistency", "P1"),
            ("H3", "幻觉率", "事实错误", "hallucination_detection", "P1"),
            ("H4", "指令遵循度", "格式/角色", "instruction_following", "P0"),
            ("H5", "响应相关性", "问答相关性", "response_relevance", "P0"),
            (
                "H6",
                "编程领域相关性",
                "验证编程问题的回答相关性",
                "response_relevance_programming",
                "P0",
            ),
            (
                "H7",
                "数学领域相关性",
                "验证数学问题的回答相关性",
                "response_relevance_math",
                "P0",
            ),
            (
                "H8",
                "科学领域相关性",
                "验证科学问题的回答相关性",
                "response_relevance_science",
                "P0",
            ),
            (
                "H9",
                "乱码检测",
                "检测输出是否为乱码或无效字符",
                "garbled_text_detection",
                "P0",
            ),
            (
                "H10",
                "无意义回答检测",
                "检测回答是否与问题完全不相关",
                "nonsensical_response_detection",
                "P1",
            ),
            (
                "H11",
                "跨领域相关性",
                "天气/烹饪等领域相关性",
                "cross_domain_relevance",
                "P1",
            ),
            (
                "H12",
                "上下文一致性",
                "多轮对话中验证上下文一致性",
                "conversation_context_consistency",
                "P0",
            ),
            (
                "H13",
                "回答具体性",
                "确保回答不是泛泛而谈",
                "response_specificity_check",
                "P2",
            ),
        ],
    },
    "i_quality_completions": {
        "name": "I. Completions API 质量评估与回答相关性",
        "criticality": "重要",
        "tests": [
            ("I1", "生成质量", "Completions API质量对比", "generation_quality", "P1"),
            (
                "I2",
                "生成一致性",
                "Completions API多次生成",
                "generation_consistency",
                "P1",
            ),
            (
                "I3",
                "幻觉率",
                "Completions API事实错误",
                "hallucination_detection",
                "P1",
            ),
            (
                "I4",
                "指令遵循度",
                "Completions API格式/角色",
                "instruction_following",
                "P1",
            ),
            (
                "I5",
                "响应相关性",
                "Completions API问答相关性",
                "response_relevance",
                "P1",
            ),
            (
                "I6",
                "编程领域相关性",
                "Completions API验证编程问题的回答相关性",
                "response_relevance_programming",
                "P1",
            ),
            (
                "I7",
                "数学领域相关性",
                "Completions API验证数学问题的回答相关性",
                "response_relevance_math",
                "P1",
            ),
            (
                "I8",
                "科学领域相关性",
                "Completions API验证科学问题的回答相关性",
                "response_relevance_science",
                "P1",
            ),
            (
                "I9",
                "乱码检测",
                "Completions API检测输出是否为乱码或无效字符",
                "garbled_text_detection",
                "P1",
            ),
            (
                "I10",
                "无意义回答检测",
                "Completions API检测回答是否与问题完全不相关",
                "nonsensical_response_detection",
                "P1",
            ),
            (
                "I11",
                "跨领域相关性",
                "Completions API天气/烹饪等领域相关性",
                "cross_domain_relevance",
                "P1",
            ),
            (
                "I12",
                "上下文一致性",
                "Completions API多轮对话中验证上下文一致性",
                "conversation_context_consistency",
                "P1",
            ),
            (
                "I13",
                "回答具体性",
                "Completions API确保回答不是泛泛而谈",
                "response_specificity_check",
                "P2",
            ),
        ],
    },
    "j_clear_thinking": {
        "name": "J. clear_thinking 参数行为",
        "criticality": "重要",
        "tests": [
            (
                "J1",
                "clear_thinking=true 多轮",
                "显式 clear_thinking=true，验证多轮请求成功且无 thinking 泄漏到后续上下文",
                "clear_thinking_true_multi_turn",
                "P1",
            ),
            (
                "J2",
                "clear_thinking=false 多轮",
                "显式 clear_thinking=false，验证多轮请求成功且历史 thinking 被保留",
                "clear_thinking_false_multi_turn",
                "P1",
            ),
            (
                "J3",
                "clear_thinking 对 prompt_tokens 的影响",
                "对比 true/false 在含历史 thinking 的多轮请求下的 prompt_tokens 差异",
                "clear_thinking_prompt_tokens_difference",
                "P2",
            ),
            (
                "J4",
                "clear_thinking 与 enable_thinking 组合",
                "四种 (enable_thinking, clear_thinking) 组合均可被服务端接受",
                "clear_thinking_enable_combinations",
                "P1",
            ),
            (
                "J5",
                "clear_thinking deployment 能力探测",
                "探测服务端是否真实实现 clear_thinking（pt_false > pt_true），"
                "未生效时记录 WARNING 提示运维/算法团队",
                "clear_thinking_deployment_probe",
                "P1",
            ),
            (
                "J6",
                "clear_thinking 对 reasoning_content 独立字段的处理",
                "assistant 消息以 reasoning_content 字段承载思考时验证 clear_thinking 行为",
                "clear_thinking_reasoning_field",
                "P1",
            ),
            (
                "J7",
                "clear_thinking 与 reasoning_effort 组合",
                "GLM-5.3 等模型核心参数组合，验证参数正交性",
                "clear_thinking_with_reasoning_effort",
                "P1",
            ),
            (
                "J8",
                "多 assistant 边界测试",
                "多条历史 assistant 消息下 last_user_index 边界条件",
                "clear_thinking_multi_assistant_boundary",
                "P2",
            ),
            (
                "J9",
                "clear_thinking 默认行为探测",
                "不传 clear_thinking 时的服务端默认值验证",
                "clear_thinking_default_behavior",
                "P2",
            ),
            (
                "J10",
                "clear_thinking 行为级验证",
                "follow-up 依赖历史思考内容，验证模型是否真的看到历史 thinking",
                "clear_thinking_behavioral_verification",
                "P2",
            ),
            (
                "J11",
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
                "$defs/$ref JSON Schema 报【$$不兼容】，原样复现请求验证服务端兼容",
                "pydantic_schema_tool_call_stream",
                "P0",
            ),
            (
                "K2",
                "同一请求循环执行5次返回信息异常",
                "客户问题复现：同一 curl（logprobs+top_logprobs+n+thinking+stream+"
                "X-Cache-Buster）循环执行5次左右出现返回信息异常，原样复现并连续"
                "执行5次（间隔3s），验证每次响应与内容均正常",
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
                "thinking；采样参数不豁免（用户指令）——由全局 "
                "SAMPLING_PARAMS 覆盖，temperature=0 为无覆盖时回退"
                "值；工具 get_weather+get_current_"
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
                "thinking），断言 json_object 正文为合法 JSON 对象、"
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
                "kwargs={clear_thinking:true}；嵌套放置：reasoning_"
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
                "参数不豁免——由全局 SAMPLING_PARAMS 覆盖"
                "（temperature 无覆盖时回退 0.7、top_p/seed 注入），"
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
                "参数（豁免）；"
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
                "GLM-5.3；采样参数不豁免（用户指定）：由全局 "
                "SAMPLING_PARAMS 覆盖——temperature 无覆盖时回退 "
                "0.7、top_p/seed 显式指定时注入",
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
                "Kimi-K3；采样参数不豁免（默认口径——未明确指定加入"
                "豁免名单）：由全局 SAMPLING_PARAMS 覆盖——"
                "temperature 无覆盖时回退 0.7、top_p/seed 显式指定时"
                "注入；打印口径：运行日志不含具体模型名（系统"
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
                "GLM-5.3；采样参数不豁免（默认口径——未明确指定加"
                "入豁免名单）",
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
                "tool_calls 非空——官方形态为正常答句）；官方行为"
                "细节（输出/推理引用工具数据要素——北京/18/晴）软校"
                "验仅日志；finish/usage 仅日志；采样参数不豁免（默"
                "认口径——未明确指定加入豁免名单）：由全局 "
                "SAMPLING_PARAMS 覆盖——temperature 无覆盖时回退 "
                "0.7、top_p/seed 显式指定时注入；模型真实响应（状"
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
                "（已通过不重测）。采样参数豁免（用户指定）：两请求"
                "体均显式 temperature=0.0——工单原始请求体为唯一"
                "口径，通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖，"
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
                "构造本身已保证安全，不判失败）。采样参数不豁免（默"
                "认口径）：由全局 SAMPLING_PARAMS 覆盖——temperature "
                "无覆盖时回退 0.7、top_p/seed 显式指定时注入（K10/"
                "K18/K20 口径）。max_tokens=8192 为客户工单原始口径，"
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
                "用 GLM-5.3；采样参数不豁免——由全局 SAMPLING_PARAMS"
                " 覆盖（temperature 无覆盖时回退 0.7、top_p/seed 注"
                "入），两个请求一致",
                "negative_lookahead_tool_pattern_accepted",
                "P0",
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
