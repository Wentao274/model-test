"""
测试分类定义

集中管理所有测试分类和测试点定义，避免重复
"""

from typing import Dict

TEST_CATEGORIES = {
    "a_basic": {
        "name": "A. 基础推理能力",
        "tests": [
            (
                "A1",
                "单轮对话",
                "发送单条prompt，验证正常生成",
                "single_turn_conversation",
            ),
            (
                "A2",
                "多轮对话",
                "5轮对话，验证上下文保持和连贯性",
                "multi_turn_conversation",
            ),
            ("A3", "System Prompt", "设置系统角色，验证模型遵循程度", "system_prompt"),
            ("A4", "流式输出", "stream=true，验证SSE逐token返回", "streaming_output"),
            ("A5", "非流式输出", "stream=false，验证完整返回", "non_streaming_output"),
            (
                "A6",
                "Temperature 控制",
                "temp=0 vs temp=1.0，验证输出差异",
                "temperature_control",
            ),
            (
                "A7",
                "Top-p/Top-k采样",
                "不同top_p/top_k值，验证多样性控制",
                "top_p_top_k_sampling",
            ),
            (
                "A8",
                "Max Tokens限制",
                "设置max_tokens，验证输出不超限",
                "max_tokens_limit",
            ),
            ("A9", "Stop Sequences", "设置stop token，验证截断", "stop_sequences"),
            (
                "A10",
                "Seed 可复现性",
                "相同seed+temp=0，验证输出一致",
                "seed_reproducibility",
            ),
            (
                "A11",
                "多语言能力",
                "中/英/日/韩/法等多语言输入输出",
                "multilingual_capability",
            ),
            (
                "A12",
                "特殊Token处理",
                "含emoji、代码块、数学符号、HTML标签",
                "special_tokens_handling",
            ),
        ],
    },
    "b_advanced": {
        "name": "B. 高级生成功能",
        "tests": [
            (
                "B1",
                "思考模式（Thinking）",
                "开启thinking mode，验证返回思考链+最终答案",
                "thinking_mode",
            ),
            (
                "B2",
                "非思考模式（Instant）",
                "关闭thinking，验证无hidden thinking泄漏",
                "non_thinking_mode",
            ),
            (
                "B3",
                "思考模式切换",
                "同一会话内thinking↔non-thinking切换",
                "thinking_mode_switch",
            ),
            (
                "B4",
                "工具调用-单工具",
                "定义单个function，验证模型正确调用并传参",
                "single_tool_call",
            ),
            (
                "B5",
                "工具调用-多工具",
                "定义多个function，验证模型选择正确的工具",
                "multiple_tool_call",
            ),
            (
                "B6",
                "工具调用-并行调用",
                "单次回复中并行调用多个工具",
                "parallel_tool_calls",
            ),
            (
                "B7",
                "工具调用-多步链式",
                "工具结果作为下一步输入，验证3+步链式执行",
                "multi_step_external_api_chain",
            ),
            (
                "B8",
                "JSON Mode",
                "response_format=json_object，验证输出合法JSON",
                "json_mode",
            ),
            (
                "B9",
                "结构化输出",
                "JSON Schema约束输出格式，验证字段完整性",
                "structured_output",
            ),
            (
                "B10",
                "Prefix/Suffix约束",
                "指定输出前缀或格式模板，验证遵循度",
                "prefix_suffix_constraint",
            ),
        ],
    },
    "c_multimodal": {
        "name": "C. 多模态能力",
        "tests": [
            ("C1", "单图理解", "图片+文本提问", "single_image_understanding"),
            ("C2", "多图对比", "跨图比较", "multi_image_comparison"),
            ("C3", "高分辨率图片", "4K分辨率", "high_resolution_image"),
            ("C4", "图表/OCR", "表格截图", "chart_ocr"),
            ("C5", "视频理解", "视频文件", "video_understanding"),
            ("C6", "代码截图→代码", "UI截图", "screenshot_to_code"),
            ("C7", "多模态工具调用", "图片触发工具", "multimodal_tool_call"),
            ("C8", "图片格式兼容性", "PNG/JPEG/WebP", "image_format_compatibility"),
        ],
    },
    "d_long_context": {
        "name": "D. 长上下文处理",
        "tests": [
            ("D1", "短上下文基线", "1K tokens", "short_context_baseline"),
            ("D2", "中等上下文", "8K-16K tokens", "medium_context"),
            ("D3", "长上下文", "32K-64K tokens", "long_context"),
            ("D4", "超长上下文", "128K+ tokens", "super_long_context"),
            ("D5", "大海捞针", "NIAH", "niah_needle_in_a_haystack"),
            ("D6", "上下文边界行为", "max_model_len", "context_boundary_behavior"),
            ("D7", "超出上下文截断", "截断/拒绝", "context_truncation"),
            ("D8", "长输出生成", "4K-8K tokens", "long_output_generation"),
        ],
    },
    "e_performance": {
        "name": "E. 性能指标",
        "tests": [
            ("E1", "TTFT", "首Token延迟", "ttft"),
            ("E2", "TPOT", "每Token生成时间", "tpot"),
            ("E3", "ITL P50/P95/P99", "分位数统计", "itl_percentiles"),
            ("E4", "端到端延迟", "总时间", "end_to_end_latency"),
            ("E5", "吞吐量", "tokens/s", "token_throughput"),
            ("E6", "请求吞吐", "req/s", "request_throughput"),
            ("E7", "并发扩展性", "并发1→200", "concurrency_scaling"),
            ("E8", "显存占用", "GPU显存", "gpu_memory"),
            ("E9", "GPU利用率", "计算单元", "gpu_utilization"),
            ("E10", "预热时间", "首次vs稳态", "warmup_time"),
            ("E11", "Prefill速度", "不同输入长度", "prefill_speed"),
            ("E12", "突发流量恢复", "100并发恢复", "burst_recovery"),
        ],
    },
    "f_stability": {
        "name": "F. 稳定性与边界",
        "tests": [
            ("F1", "空输入", "空prompt", "empty_input"),
            ("F2", "超大输入", "超max_model_len", "oversized_input"),
            ("F3", "非法参数", "temperature=-1", "invalid_parameters"),
            ("F4", "特殊字符注入", "SQL/Prompt注入", "special_character_injection"),
            ("F5", "并发稳定性", "200+并发", "concurrent_stability"),
            ("F6", "OOM恢复", "显存耗尽", "oom_recovery"),
            ("F7", "长时间运行", "24小时", "long_running_service"),
            ("F8", "请求超时处理", "超时断开", "request_timeout_handling"),
        ],
    },
    "g_api": {
        "name": "G. API兼容性",
        "tests": [
            (
                "G1",
                "OpenAI Chat Completions",
                "/v1/chat/completions 接口兼容",
                "chat_completions_api",
            ),
            ("G2", "OpenAI Completions", "/v1/completions 接口兼容", "completions_api"),
            ("G3", "模型列表", "/v1/models 返回可用模型", "models_list"),
            ("G4", "Usage 统计", "usage 字段准确", "usage_statistics"),
            ("G5", "错误码规范", "400/401/404/429/500 错误码", "error_codes"),
            (
                "G6",
                "客户端 SDK 兼容",
                "Python openai / JS @openai/sdk",
                "client_sdk_compatibility",
            ),
            ("G7", "响应格式变体", "不同response_format", "response_format_variants"),
            ("G8", "Stream参数", "stream参数测试", "stream_parameter"),
        ],
    },
    "h_quality": {
        "name": "H. 质量评估",
        "tests": [
            ("H1", "生成质量", "质量对比", "generation_quality"),
            ("H2", "生成一致性", "多次生成", "generation_consistency"),
            ("H3", "幻觉率", "事实错误", "hallucination_detection"),
            ("H4", "指令遵循度", "格式/角色", "instruction_following"),
            ("H5", "响应相关性", "问答相关性", "response_relevance"),
        ],
    },
    "i_long_context": {
        "name": "I. 超长上下文验证",
        "tests": [
            (
                "I1",
                "超长上下文（非流式）",
                "验证超长上下文请求的非流式输出",
                "super_long_context_create",
            ),
            (
                "I2",
                "超长上下文（流式）",
                "验证超长上下文请求的流式输出",
                "super_long_context_stream",
            ),
            (
                "I3",
                "超长上下文（边界验证）",
                "使用二分法逼近模型最大上下文长度",
                "context_boundary_exact_limit",
            ),
            (
                "I4",
                "超长上下文（思考模式）",
                "验证超长上下文下reasoning_content的可用性",
                "reasoning_content_in_long_context",
            ),
        ],
    },
    "j_quality": {
        "name": "J. 回答质量与相关性",
        "tests": [
            (
                "J1-1",
                "编程领域相关性",
                "验证编程问题的回答相关性",
                "response_relevance_programming",
            ),
            (
                "J1-2",
                "数学领域相关性",
                "验证数学问题的回答相关性",
                "response_relevance_math",
            ),
            (
                "J1-3",
                "科学领域相关性",
                "验证科学问题的回答相关性",
                "response_relevance_science",
            ),
            (
                "J2",
                "乱码检测",
                "检测输出是否为乱码或无效字符",
                "garbled_text_detection",
            ),
            (
                "J3",
                "无意义回答检测",
                "检测回答是否与问题完全不相关",
                "nonsensical_response_detection",
            ),
            ("J4", "跨领域相关性", "天气/烹饪等领域相关性", "cross_domain_relevance"),
            (
                "J5",
                "上下文一致性",
                "多轮对话中验证上下文一致性",
                "conversation_context_consistency",
            ),
            ("J6", "回答具体性", "确保回答不是泛泛而谈", "response_specificity_check"),
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
