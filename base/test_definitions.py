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
                "multi_step_tool_chain",
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
            ("C1", "单图理解", "图片+文本提问", "single_image"),
            ("C2", "多图对比", "跨图比较", "multi_image"),
            ("C3", "高分辨率图片", "4K分辨率", "high_res_image"),
            ("C4", "图表/OCR", "表格截图", "chart_ocr"),
            ("C5", "视频理解", "视频文件", "video_understanding"),
            ("C6", "代码截图→代码", "UI截图", "screenshot_to_code"),
            ("C7", "多模态工具调用", "图片触发工具", "multimodal_tool_call"),
            ("C8", "图片格式兼容性", "PNG/JPEG/WebP", "image_format"),
        ],
    },
    "d_long_context": {
        "name": "D. 长上下文处理",
        "tests": [
            ("D1", "短上下文基线", "1K tokens", "short_context"),
            ("D2", "中等上下文", "8K-16K tokens", "medium_context"),
            ("D3", "长上下文", "32K-64K tokens", "long_context"),
            ("D4", "超长上下文", "128K+ tokens", "ultra_long_context"),
            ("D5", "大海捞针", "NIAH", "needle_in_haystack"),
            ("D6", "上下文边界行为", "max_model_len", "context_boundary"),
            ("D7", "超出上下文截断", "截断/拒绝", "context_truncation"),
            ("D8", "长输出生成", "4K-8K tokens", "long_output"),
        ],
    },
    "e_performance": {
        "name": "E. 性能指标",
        "tests": [
            ("E1", "TTFT", "首Token延迟", "ttft"),
            ("E2", "TPOT", "每Token生成时间", "tpot"),
            ("E3", "ITL P50/P95/P99", "分位数统计", "itl_percentiles"),
            ("E4", "端到端延迟", "总时间", "e2e_latency"),
            ("E5", "吞吐量", "tokens/s", "throughput"),
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
            ("G1", "空输入", "空prompt", "empty_input"),
            ("G2", "超大输入", "超max_model_len", "oversized_input"),
            ("G3", "非法参数", "temperature=-1", "invalid_params"),
            ("G4", "特殊字符注入", "SQL/Prompt注入", "special_char_injection"),
            ("G5", "并发稳定性", "200+并发", "concurrent_stability"),
            ("G6", "OOM恢复", "显存耗尽", "oom_recovery"),
            ("G7", "长时间运行", "24小时", "long_running"),
            ("G8", "请求超时处理", "超时断开", "timeout_handling"),
        ],
    },
    "g_api": {
        "name": "G. API兼容性",
        "tests": [
            ("H1", "Chat Completions", "/v1/chat/completions", "chat_completions"),
            ("H2", "Completions", "/v1/completions", "completions"),
            ("H3", "模型列表", "/v1/models", "list_models"),
            ("H4", "Usage统计", "usage字段", "usage_stats"),
        ],
    },
    "h_quality": {
        "name": "H. 质量评估",
        "tests": [
            ("I1", "生成质量", "质量对比", "generation_quality"),
            ("I2", "生成一致性", "多次生成", "generation_consistency"),
            ("I3", "幻觉率", "事实错误", "hallucination_rate"),
            ("I4", "指令遵循度", "格式/角色", "instruction_following"),
        ],
    },
    "i_long_context": {
        "name": "I. 超长上下文验证",
        "tests": [
            ("L1", "超长上下文", "create/stream探测", "ultra_long_context"),
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
