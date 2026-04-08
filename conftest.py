"""
pytest全局配置和共享fixture
"""
import os
import sys
from datetime import datetime
from pathlib import Path
import pytest
import yaml
from typing import Dict, Any, List

from base.api_client import ModelAPIClient
from base.logger import TestLogger


# 测试分类定义 - 添加英文函数名映射
TEST_CATEGORIES = {
    "a_basic": {
        "name": "A. 基础推理能力",
        "tests": [
            ("A1", "单轮对话", "发送单条prompt，验证正常生成", "single_turn_conversation"),
            ("A2", "多轮对话", "5轮对话，验证上下文保持和连贯性", "multi_turn_conversation"),
            ("A3", "System Prompt", "设置系统角色，验证模型遵循程度", "system_prompt"),
            ("A4", "流式输出", "stream=true，验证SSE逐token返回", "streaming_output"),
            ("A5", "非流式输出", "stream=false，验证完整返回", "non_streaming_output"),
            ("A6", "Temperature 控制", "temp=0 vs temp=1.0，验证输出差异", "temperature_control"),
            ("A7", "Top-p/Top-k采样", "不同top_p/top_k值，验证多样性控制", "top_p_top_k_sampling"),
            ("A8", "Max Tokens限制", "设置max_tokens，验证输出不超限", "max_tokens_limit"),
            ("A9", "Stop Sequences", "设置stop token，验证截断", "stop_sequences"),
            ("A10", "Seed 可复现性", "相同seed+temp=0，验证输出一致", "seed_reproducibility"),
            ("A11", "多语言能力", "中/英/日/韩/法等多语言输入输出", "multilingual_capability"),
            ("A12", "特殊Token处理", "含emoji、代码块、数学符号、HTML标签", "special_tokens_handling"),
        ]
    },
    "b_advanced": {
        "name": "B. 高级生成功能",
        "tests": [
            ("B1", "思考模式（Thinking）", "开启thinking mode，验证返回思考链+最终答案", "thinking_mode"),
            ("B2", "非思考模式（Instant）", "关闭thinking，验证无hidden thinking泄漏", "non_thinking_mode"),
            ("B3", "思考模式切换", "同一会话内thinking↔non-thinking切换", "thinking_mode_switch"),
            ("B4", "工具调用-单工具", "定义单个function，验证模型正确调用并传参", "single_tool_call"),
            ("B5", "工具调用-多工具", "定义多个function，验证模型选择正确的工具", "multiple_tool_call"),
            ("B6", "工具调用-并行调用", "单次回复中并行调用多个工具", "parallel_tool_calls"),
            ("B7", "工具调用-多步链式", "工具结果作为下一步输入，验证3+步链式执行", "multi_step_tool_chain"),
            ("B8", "JSON Mode", "response_format=json_object，验证输出合法JSON", "json_mode"),
            ("B9", "结构化输出", "JSON Schema约束输出格式，验证字段完整性", "structured_output"),
            ("B10", "Prefix/Suffix约束", "指定输出前缀或格式模板，验证遵循度", "prefix_suffix_constraint"),
        ]
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
        ]
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
        ]
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
        ]
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
        ]
    },
    "g_api": {
        "name": "G. API兼容性",
        "tests": [
            ("H1", "Chat Completions", "/v1/chat/completions", "chat_completions"),
            ("H2", "Completions", "/v1/completions", "completions"),
            ("H3", "模型列表", "/v1/models", "list_models"),
            ("H4", "Usage统计", "usage字段", "usage_stats"),
        ]
    },
    "h_quality": {
        "name": "H. 质量评估",
        "tests": [
            ("I1", "生成质量", "质量对比", "generation_quality"),
            ("I2", "生成一致性", "多次生成", "generation_consistency"),
            ("I3", "幻觉率", "事实错误", "hallucination_rate"),
            ("I4", "指令遵循度", "格式/角色", "instruction_following"),
        ]
    },
    "i_long_context": {
        "name": "I. 超长上下文验证",
        "tests": [
            ("L1", "超长上下文", "create/stream探测", "ultra_long_context"),
        ]
    },
}


# 测试结果收集器
_test_results = {}


def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return expand_env_vars(config)


def expand_env_vars(config: Any) -> Any:
    """递归处理配置文件中的环境变量"""
    if isinstance(config, dict):
        return {k: expand_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [expand_env_vars(item) for item in config]
    elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
        env_var = config[2:-1]
        return os.getenv(env_var, "")
    return config


@pytest.fixture(scope="session")
def config() -> Dict[str, Any]:
    """全局配置fixture"""
    return load_config()


@pytest.fixture(scope="session")
def enabled_models(config: Dict[str, Any]) -> List[str]:
    """获取所有启用的模型列表"""
    models = config.get("models", {})
    return [name for name, cfg in models.items() if cfg.get("enabled", True)]


@pytest.fixture(scope="session")
def default_model(config: Dict[str, Any]) -> str:
    """默认测试模型"""
    return config.get("default_model", "qwen35")


@pytest.fixture(scope="function")
def api_client(config: Dict[str, Any], default_model: str) -> ModelAPIClient:
    """为每个测试创建API客户端（默认模型）"""
    model_config = config["models"][default_model]
    return ModelAPIClient(
        api_key=model_config["api_key"],
        base_url=model_config["base_url"],
        model_name=model_config["name"],
        timeout=config["global"]["timeout"]
    )


@pytest.fixture(scope="function")
def api_client_for_model(config: Dict[str, Any], request) -> ModelAPIClient:
    """
    根据命令行参数或marker指定模型返回API客户端

    Usage:
        # 指定模型运行测试
        pytest --model=qwen35

        # 或在测试函数中标记
        @pytest.mark.model("qwen35")
        def test_something():
            ...
    """
    # 优先从命令行参数获取模型
    model_name = request.config.getoption("--model", default=None)
    if not model_name:
        # 使用默认模型
        model_name = config.get("default_model", "qwen35")

    model_config = config["models"].get(model_name)
    if not model_config:
        pytest.skip(f"Model '{model_name}' not found in config")

    return ModelAPIClient(
        api_key=model_config["api_key"],
        base_url=model_config["base_url"],
        model_name=model_config["name"],
        timeout=config["global"]["timeout"]
    )


@pytest.fixture(scope="function")
def test_logger(request):
    """
    为每个测试类创建独立的日志器

    Usage:
        def test_something(self, test_logger):
            test_logger.info("测试开始")
            response = api_client.chat(...)
            TestLogger.log_response(test_logger, response)
    """
    # 获取测试类名
    test_class = request.node.cls
    if test_class:
        logger_name = test_class.__name__
    else:
        # 如果没有类名，使用模块名
        logger_name = request.node.module.__name__.split('.')[-1]

    return TestLogger.get_logger(logger_name)


def pytest_addoption(parser):
    """添加命令行选项"""
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="Specify model to test (qwen35, kimi_k25, glm5, minimax21, minimax25)"
    )
    parser.addoption(
        "--all-models",
        action="store_true",
        default=False,
        help="Run tests on all enabled models"
    )


def pytest_collection_modifyitems(config, items):
    """修改测试项，添加marker"""
    # 根据测试文件自动添加分类marker
    for item in items:
        if "test_a_" in item.nodeid:
            item.add_marker(pytest.mark.a_basic)
        elif "test_b_" in item.nodeid:
            item.add_marker(pytest.mark.b_advanced)
        elif "test_c_" in item.nodeid:
            item.add_marker(pytest.mark.c_multimodal)
        elif "test_d_" in item.nodeid:
            item.add_marker(pytest.mark.d_long_context)
        elif "test_e_" in item.nodeid:
            item.add_marker(pytest.mark.e_performance)
        elif "test_f_" in item.nodeid:
            item.add_marker(pytest.mark.f_stability)
        elif "test_g_" in item.nodeid:
            item.add_marker(pytest.mark.g_api)
        elif "test_h_" in item.nodeid:
            item.add_marker(pytest.mark.h_quality)
        elif "test_i_" in item.nodeid:
            item.add_marker(pytest.mark.i_long_context)


def pytest_configure(config):
    """注册自定义marker"""
    config.addinivalue_line("markers", "a_basic: A类测试 - 基础推理能力")
    config.addinivalue_line("markers", "b_advanced: B类测试 - 高级生成功能")
    config.addinivalue_line("markers", "c_multimodal: C类测试 - 多模态能力")
    config.addinivalue_line("markers", "d_long_context: D类测试 - 长上下文处理")
    config.addinivalue_line("markers", "e_performance: E类测试 - 性能指标")
    config.addinivalue_line("markers", "f_stability: F类测试 - 稳定性与边界")
    config.addinivalue_line("markers", "g_api: G类测试 - API兼容性")
    config.addinivalue_line("markers", "h_quality: H类测试 - 质量评估")
    config.addinivalue_line("markers", "i_long_context: I类测试 - 单项超长上下文验证")
    config.addinivalue_line("markers", "slow: 慢速测试")
    config.addinivalue_line("markers", "integration: 集成测试")

    # 注册报告生成hook
    config.addinivalue_line(
        "markers",
        "report: 测试完成后自动生成报告 (默认开启)"
    )


def pytest_runtest_logreport(report):
    """收集测试结果"""
    global _test_results

    if report.when == "call":  # 只记录实际测试执行结果
        test_id = report.nodeid

        # 解析测试名称 - 使用 test_idx (如 A1, B2) 来匹配
        for marker, category in TEST_CATEGORIES.items():
            for test_info in category['tests']:
                # 处理元组长度兼容（新格式有4个元素，旧格式有3个）
                if len(test_info) >= 4:
                    test_idx, test_name, test_desc, test_func = test_info
                else:
                    test_idx, test_name, test_desc = test_info
                    test_func = test_name.replace("-", "_").replace(" ", "_")

                # 用 test_idx 检查是否匹配当前分类的测试
                # test_id 格式: tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_conversation
                # 或者: tests/test_a_basic_reasoning.py::TestBasicReasoning::test_max_tokens_limit[50]
                if f"test_{marker}" in test_id:
                    # 提取测试函数名（去掉参数化部分）
                    test_func_name = test_id.split("::")[-1].split("[")[0]
                    # 使用英文函数名精确匹配 - 需要完整匹配函数名
                    # 例如 test_non_streaming_output 应该匹配 non_streaming_output，不是 streaming_output
                    if test_func_name == f"test_{test_func}":
                        key = f"{marker}_{test_idx}"
                        if report.passed:
                            _test_results[key] = "PASSED"
                        elif report.failed:
                            _test_results[key] = "FAILED"
                        else:
                            _test_results[key] = "SKIPPED"
                        break


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """测试结束后自动生成报告"""
    global _test_results

    # 获取启用的模型
    model = None
    try:
        cfg = load_config()
        for name, model_cfg in cfg.get('models', {}).items():
            if model_cfg.get('enabled', False):
                model = {
                    'name': name,
                    'display_name': model_cfg.get('display_name', name),
                    'model_name': model_cfg.get('name', name)
                }
                break
    except:
        pass

    if not model:
        return

    # 生成报告
    test_date = datetime.now().strftime("%Y-%m-%d")
    test_time = datetime.now().strftime("%H:%M:%S")
    test_datetime = datetime.now().strftime("%Y%m%d%H%M%S")

    # 创建输出目录
    output_dir = Path("test_reports") / f"{model['name']}_{test_datetime}"
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# {model['display_name']} 测试报告")
    lines.append("")
    lines.append(f"> 测试日期：{test_date}")
    lines.append(f"> 测试时间：{test_time}")
    lines.append(f"> 模型：{model['display_name']} (`{model['model_name']}`)")
    lines.append("")

    # 遍历所有测试分类
    for marker, category in TEST_CATEGORIES.items():
        lines.append(f"## {category['name']}")
        lines.append("")
        # 在表格前添加状态说明
        lines.append("> 状态说明：✅ 已通过，⏳ 未测试，❌ 未通过，⚠️ 部分通过")
        lines.append("")
        lines.append(f"| #   | 测试点       | 测试内容                        | 状态 |")
        lines.append(f"|-----|------------|-----------------------------|------|")

        # 收集需要添加说明的测试
        tests_needing_notes = []

        for test_info in category['tests']:
            # 处理元组长度兼容
            if len(test_info) >= 4:
                test_idx, test_name, test_desc, test_func = test_info
            else:
                test_idx, test_name, test_desc = test_info

            key = f"{marker}_{test_idx}"
            status = _test_results.get(key, "未运行")

            if status == "PASSED":
                status_icon = "✅"
            elif status == "FAILED":
                status_icon = "❌"
                tests_needing_notes.append((test_idx, test_name, "测试未通过"))
            elif status == "PARTIAL":
                status_icon = "⚠️"
                tests_needing_notes.append((test_idx, test_name, "部分用例未通过"))
            elif status == "SKIPPED":
                status_icon = "⏳"
                tests_needing_notes.append((test_idx, test_name, "未运行此测试"))
            else:
                status_icon = "⏳"
                tests_needing_notes.append((test_idx, test_name, "未运行此测试"))

            if len(test_desc) > 26:
                test_desc = test_desc[:23] + "..."

            lines.append(f"| {test_idx:2s}  | {test_name:10s} | {test_desc:26s} | {status_icon} |")

        # 为有问题的测试添加说明
        if tests_needing_notes:
            lines.append("")
            for test_idx, test_name, reason in tests_needing_notes:
                lines.append(f"- **{test_idx} {test_name}**: {reason}")

        lines.append("")

    # 统计汇总
    lines.append("---")
    lines.append("")
    lines.append("## 统计汇总")

    # 基于 _test_results 统计实际运行的测试点
    # 只统计当前运行的分类
    categories_run = set()
    for key in _test_results.keys():
        marker = key.split('_')[0]
        categories_run.add(marker)

    # 计算当前运行的测试点统计
    run_passed = sum(1 for v in _test_results.values() if v == "PASSED")
    run_failed = sum(1 for v in _test_results.values() if v == "FAILED")
    run_partial = sum(1 for v in _test_results.values() if v == "PARTIAL")
    run_skipped = sum(1 for v in _test_results.values() if v in ("SKIPPED", "未运行"))
    run_total = len(_test_results)

    # 计算通过率
    pass_rate = run_passed * 100 // run_total if run_total > 0 else 0

    lines.append("")
    lines.append(f"- 运行测试点：{run_total}")
    lines.append(f"- 已通过：{run_passed}")
    lines.append(f"- 部分通过：{run_partial}")
    lines.append(f"- 未通过：{run_failed}")
    lines.append(f"- 未测试：{run_skipped}")
    lines.append(f"- 通过率：{pass_rate}%")

    # 获取实际运行的 pytest 测试统计
    stats = terminalreporter.stats
    actual_passed = len(stats.get('passed', []))
    actual_failed = len(stats.get('failed', []))
    actual_skipped = len(stats.get('skipped', []))

    # 使用实际运行的测试数量
    total_actual = actual_passed + actual_failed + actual_skipped

    lines.append("")
    lines.append("## 实际运行结果")
    lines.append("")
    lines.append(f"- 实际通过（pytest函数级）：{actual_passed}")
    lines.append(f"- 实际失败：{actual_failed}")
    lines.append(f"- 实际跳过：{actual_skipped}")
    lines.append(f"- 总计（函数级）：{total_actual}")

    # 写入文件
    filename = f"test_report_{model['name']}_{test_datetime}.md"
    filepath = output_dir / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    terminalreporter.write_sep("=", "测试报告已生成")
    terminalreporter.write_line(f"报告路径: {filepath}")