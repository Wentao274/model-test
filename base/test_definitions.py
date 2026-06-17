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
                "P0",
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
        ],
    },
    "c_multimodal": {
        "name": "C. 多模态能力",
        "criticality": "一般",
        "tests": [
            ("C1", "单图理解", "图片+文本提问", "single_image_understanding", "P1"),
            ("C2", "多图对比", "跨图比较", "multi_image_comparison", "P1"),
            ("C3", "高分辨率图片", "4K分辨率", "high_resolution_image", "P2"),
            ("C4", "图表/OCR", "表格截图", "chart_ocr", "P1"),
            ("C5", "视频理解", "视频文件", "video_understanding", "P2"),
            ("C6", "代码截图→代码", "UI截图", "screenshot_to_code", "P2"),
            ("C7", "多模态工具调用", "图片触发工具", "multimodal_tool_call", "P2"),
            (
                "C8",
                "图片格式兼容性",
                "PNG/JPEG/WebP",
                "image_format_compatibility",
                "P1",
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
            ("G5", "错误码规范", "400/401/404/429/500 错误码", "error_codes", "P1"),
            (
                "G6",
                "客户端 SDK 兼容",
                "Python openai / JS @openai/sdk",
                "client_sdk_compatibility",
                "P0",
            ),
            (
                "G7",
                "响应格式变体",
                "不同response_format",
                "response_format_variants",
                "P2",
            ),
            ("G8", "Stream参数", "stream参数测试", "stream_parameter", "P2"),
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
