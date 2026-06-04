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
from base.test_definitions import TEST_CATEGORIES
from base.report_generator import TestReportGenerator
from base.allure_reporter import (
    get_test_category_info,
    generate_allure_summary_report,
    clean_allure_results,
)

import allure
from allure_commons.types import AttachmentType


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


@pytest.fixture(scope="session", autouse=True)
def cleanup_loggers():
    """测试会话开始时清理旧的日志记录器"""
    from base.logger import TestLogger

    TestLogger._loggers.clear()
    yield
    TestLogger._loggers.clear()


@pytest.fixture(scope="function")
def api_client(
    config: Dict[str, Any], enabled_models: List[str], request
) -> ModelAPIClient:
    """
    为每个测试创建API客户端

    优先级：
    1. 命令行参数 (--chip, --base-url, --model-name, --api-key, --thinking-mode)
    2. 环境变量 (BASE_URL, API_KEY, MODEL_NAME, CHIP, THINKING_MODE)
    3. config.yaml 中的配置
    """
    # 检查命令行参数
    cmd_chip = request.config.getoption("--chip", default=None)
    cmd_base_url = request.config.getoption("--base-url", default=None)
    cmd_api_key = request.config.getoption("--api-key", default=None)
    cmd_model_name = request.config.getoption("--model-name", default=None)
    cmd_thinking_mode = request.config.getoption("--thinking-mode", default=None)
    cmd_model_key = request.config.getoption("--model", default=None)

    # 如果有命令行参数，使用命令行参数
    if cmd_base_url:
        chip_name = (cmd_chip or "cli").lower()
        api_key = cmd_api_key or "cli-api-key"
        model_name = (
            cmd_model_name or cmd_model_key or config.get("default_model", "qwen35")
        )

        # thinking_mode 优先级：命令行 > 环境变量 > config.yaml（默认启用）
        cmd_no_thinking = request.config.getoption("--no-thinking-mode", default=None)

        thinking_mode = cmd_thinking_mode
        if cmd_no_thinking:
            thinking_mode = False
        elif thinking_mode is None:
            thinking_mode = os.environ.get("THINKING_MODE", "").lower() == "true"
        elif thinking_mode is None:
            model_cfg = config.get("models", {}).get(
                cmd_model_key or cmd_model_name, {}
            )
            thinking_mode = model_cfg.get("thinking_mode", True)

        model_config = {
            "name": model_name,
            "api_key": api_key,
            "thinking_mode": bool(thinking_mode),
            "thinking_key": "enable_thinking",
        }

        return ModelAPIClient(
            api_key=api_key,
            base_url=cmd_base_url,
            model_name=model_name,
            timeout=config["global"]["timeout"],
            config=model_config,
        )

    # 检查环境变量
    env_base_url = os.environ.get("BASE_URL")
    env_api_key = os.environ.get("API_KEY")
    env_model_name = os.environ.get("MODEL_NAME")
    env_chip = os.environ.get("CHIP")
    env_thinking_mode = os.environ.get("THINKING_MODE", "").lower() == "true"

    # 使用环境变量
    if env_base_url:
        chip_name = (env_chip or "env").lower()
        api_key = env_api_key or "env-api-key"
        model_name = env_model_name or config.get("default_model", "qwen35")

        # thinking_mode 优先级：环境变量 > config.yaml
        thinking_mode = env_thinking_mode
        if thinking_mode is None:
            model_cfg = config.get("models", {}).get(model_name, {})
            thinking_mode = model_cfg.get("thinking_mode", True)

        model_config = {
            "name": model_name,
            "api_key": api_key,
            "thinking_mode": bool(thinking_mode),
            "thinking_key": "enable_thinking",
        }

        return ModelAPIClient(
            api_key=api_key,
            base_url=env_base_url,
            model_name=model_name,
            timeout=config["global"]["timeout"],
            config=model_config,
        )

    # 回退到 config.yaml 配置
    chip_name = None
    chip_config = None
    for name, cfg in config.get("chips", {}).items():
        if isinstance(cfg, dict) and cfg.get("enabled", False):
            chip_name = name.lower()
            chip_config = cfg
            break
        elif cfg is True:
            chip_name = name.lower()
            chip_config = {"base_url": ""}
            break

    if not chip_name or not chip_config:
        raise ValueError("No enabled chip found in config")

    if enabled_models:
        model_name = enabled_models[0]
    else:
        model_name = config.get("default_model", "qwen35")

    model_config = config["models"][model_name]
    if model_config.get("thinking_mode") is None:
        model_config["thinking_mode"] = True
    return ModelAPIClient(
        api_key=model_config["api_key"],
        base_url=chip_config["base_url"],
        model_name=model_config["name"],
        timeout=config["global"]["timeout"],
        config=model_config,
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
    # 获取激活的芯片平台
    chip_name = None
    chip_config = None
    for name, cfg in config.get("chips", {}).items():
        if isinstance(cfg, dict) and cfg.get("enabled", False):
            chip_name = name
            chip_config = cfg
            break
        elif cfg is True:  # 兼容旧格式
            chip_name = name
            chip_config = {"base_url": ""}
            break

    if not chip_name or not chip_config:
        raise ValueError("No enabled chip found in config")

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
        base_url=chip_config["base_url"],
        model_name=model_config["name"],
        timeout=config["global"]["timeout"],
        config=model_config,
    )


_last_test_name = {}


@pytest.fixture(scope="function")
def test_logger(request, config):
    """
    为每个测试类创建独立的日志器

    Usage:
        def test_something(self, test_logger):
            test_logger.info("测试开始")
            response = api_client.chat(...)
            TestLogger.log_response(test_logger, response)
    """
    test_class = request.node.cls
    if test_class:
        logger_name = test_class.__name__
    else:
        logger_name = request.node.module.__name__.split(".")[-1]

    # 获取当前使用的模型名称（优先级：命令行 > 环境变量 > config.yaml）
    cmd_model = request.config.getoption(
        "--model-name", default=None
    ) or request.config.getoption("--model", default=None)
    env_model = os.environ.get("MODEL_NAME")

    if cmd_model:
        model_name = cmd_model
    elif env_model:
        model_name = env_model
    else:
        model_name = None
        try:
            enabled_models = config.get("models", {})
            for name, model_cfg in enabled_models.items():
                if model_cfg.get("enabled", False):
                    model_name = name
                    break
            if not model_name:
                model_name = config.get("default_model")
        except:
            pass

    # 获取当前使用的芯片平台名称（优先级：命令行 > 环境变量 > config.yaml）
    cmd_chip = request.config.getoption("--chip", default=None)
    env_chip = os.environ.get("CHIP")

    if cmd_chip:
        chip_name = cmd_chip
    elif env_chip:
        chip_name = env_chip
    else:
        chip_name = None
        try:
            chips = config.get("chips", {})
            for name, chip_cfg in chips.items():
                if isinstance(chip_cfg, dict) and chip_cfg.get("enabled", False):
                    chip_name = name
                    break
                elif chip_cfg is True:
                    chip_name = name
                    break
        except:
            pass

    logger = TestLogger.get_logger(
        logger_name, model_name=model_name, chip_name=chip_name
    )

    test_name = request.node.name

    if logger_name not in _last_test_name:
        _last_test_name[logger_name] = test_name
    elif _last_test_name[logger_name] != test_name:
        logger.info("\n" + "=" * 50)
        _last_test_name[logger_name] = test_name

    logger.info(f"\n>>> 测试: {test_name}")

    # 清空日志缓冲区，确保每个测试独立
    TestLogger.clear_allure_log(logger_name)

    yield logger

    # 测试结束后将日志刷新到 Allure
    TestLogger.flush_to_allure(logger_name, f"测试日志: {test_name}")


def pytest_addoption(parser):
    """添加命令行选项"""
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="Specify model to test (qwen35, kimi_k25, glm5, minimax21, minimax25)",
    )
    parser.addoption(
        "--all-models",
        action="store_true",
        default=False,
        help="Run tests on all enabled models",
    )
    parser.addoption(
        "--chip",
        action="store",
        default=None,
        help="Chip platform name (e.g., nvidia-h100, hygon-bw1000, metax-c550, kunlun-p800)",
    )
    parser.addoption(
        "--base-url",
        action="store",
        default=None,
        help="API base URL (e.g., http://127.0.0.1:8080/v1)",
    )
    parser.addoption(
        "--api-key",
        action="store",
        default=None,
        help="API key for authentication",
    )
    parser.addoption(
        "--model-name",
        action="store",
        default=None,
        help="Model name in the API (e.g., qwen35, glm5, minimax-m2.5)",
    )
    parser.addoption(
        "--thinking-mode",
        action="store_true",
        default=None,
        help="Enable thinking mode (if not specified, use config.yaml setting)",
    )
    parser.addoption(
        "--no-thinking-mode",
        action="store_true",
        default=None,
        help="Disable thinking mode",
    )
    parser.addoption(
        "--infra",
        action="store",
        default=None,
        help="Inference framework (e.g., vllm, sglang)",
    )
    parser.addoption(
        "--pd-mode",
        action="store",
        default=None,
        help="PD disaggregation mode (e.g., agg, disagg)",
    )
    parser.addoption(
        "--tester",
        action="store",
        default=None,
        help="Tester name",
    )
    parser.addoption(
        "--summary-report-dir",
        action="store",
        default=None,
        help="Directory for summary report output (default: allure-report)",
    )


def pytest_collection_modifyitems(config, items):
    """修改测试项，添加marker"""
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
            item.add_marker(pytest.mark.skip(reason="E类性能测试已禁用"))
        elif "test_f_" in item.nodeid:
            item.add_marker(pytest.mark.f_stability)
        elif "test_g_" in item.nodeid:
            item.add_marker(pytest.mark.g_api)
        elif "test_h_" in item.nodeid:
            item.add_marker(pytest.mark.h_quality)


def pytest_configure(config):
    """注册自定义marker"""
    config.addinivalue_line("markers", "a_basic: A类测试 - 基础推理能力")
    config.addinivalue_line("markers", "b_advanced: B类测试 - 高级生成功能")
    config.addinivalue_line("markers", "c_multimodal: C类测试 - 多模态能力")
    config.addinivalue_line("markers", "d_long_context: D类测试 - 长上下文处理")
    config.addinivalue_line("markers", "e_performance: E类测试 - 性能指标")
    config.addinivalue_line("markers", "f_stability: F类测试 - 稳定性与边界")
    config.addinivalue_line("markers", "g_api: G类测试 - API兼容性")
    config.addinivalue_line("markers", "h_quality: H类测试 - 质量评估与回答相关性")
    config.addinivalue_line("markers", "slow: 慢速测试")
    config.addinivalue_line("markers", "integration: 集成测试")

    # 注册报告生成hook
    config.addinivalue_line("markers", "report: 测试完成后自动生成报告 (默认开启)")

    # 获取当前芯片和模型，创建对应的 allure-results 目录
    chip_name = "default"
    model_name = "default"
    try:
        cfg = load_config()
        # 从命令行获取
        cmd_chip = config.getoption("--chip", default=None)
        cmd_model = config.getoption("--model-name", default=None) or config.getoption(
            "--model", default=None
        )

        # 从环境变量获取
        env_chip = os.environ.get("CHIP")
        env_model = os.environ.get("MODEL_NAME")

        # 优先级：命令行 > 环境变量 > config.yaml
        if cmd_chip:
            chip_name = cmd_chip.lower()
        elif env_chip:
            chip_name = env_chip.lower()
        else:
            for name, chip_cfg in cfg.get("chips", {}).items():
                if isinstance(chip_cfg, dict) and chip_cfg.get("enabled", False):
                    chip_name = name.lower()
                    break

        if cmd_model:
            model_name = cmd_model
        elif env_model:
            model_name = env_model
        else:
            model_name = cfg.get("default_model", "default")
    except:
        pass

    # 设置 allure-results 目录
    # 优先级：命令行 --alluredir > 自动生成时间戳目录
    alluredir = getattr(config.option, "alluredir", None)
    if alluredir:
        # 已通过 --alluredir 指定，直接使用
        allure_results_dir = alluredir
    else:
        # 自动生成时间戳目录
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        allure_results_dir = f"allure-results/{chip_name}/{model_name}/{timestamp}"

    # 更新 pytest 的 alluredir 选项
    config.option.alluredir = allure_results_dir


_last_test_file = None
_last_test_func = None


def pytest_runtest_logreport(report):
    """收集测试结果并输出分隔线，同时记录到 Allure"""
    global _test_results, _last_test_file, _last_test_func

    if report.when == "call":
        test_id = report.nodeid
        test_file = test_id.split("::")[0]
        test_func = test_id.split("::")[-1].split("[")[0]

        if _last_test_file and _last_test_file != test_file:
            print("\n" + "=" * 60)

        if _last_test_func and _last_test_func != test_func:
            print("-" * 40)

        _last_test_file = test_file
        _last_test_func = test_func

        # 提取测试函数名（去掉 test_ 前缀）
        test_func_base = (
            test_func.replace("test_", "")
            if test_func.startswith("test_")
            else test_func
        )

        # 遍历所有测试分类，匹配测试函数名
        matched = False
        for marker, category in TEST_CATEGORIES.items():
            for test_info in category["tests"]:
                if len(test_info) >= 4:
                    test_idx, test_name, test_desc, test_func_name = test_info
                else:
                    test_idx, test_name, test_desc = test_info
                    test_func_name = test_name.replace("-", "_").replace(" ", "_")

                # 匹配测试函数名
                if test_func_base == test_func_name:
                    key = f"{marker}_{test_idx}"
                    if report.passed:
                        _test_results[key] = "PASSED"
                    elif report.failed:
                        _test_results[key] = "FAILED"
                    else:
                        _test_results[key] = "SKIPPED"
                    matched = True
                    break
            if matched:
                break


def pytest_runtest_setup(item):
    """在每个测试函数运行前检查文件变化并输出分隔线"""
    global _last_test_file
    try:
        from _pytest.config import get_plugin_manager

        terminalreporter = item.config.pluginmanager.getplugin("terminalreporter")
        if terminalreporter and _last_test_file:
            test_file = item.nodeid.split("::")[0]
            if _last_test_file != test_file:
                terminalreporter.write_sep("-", " ", cyan=True, bold=True)
        _last_test_file = item.nodeid.split("::")[0]
    except:
        pass


_last_test_file = None


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """测试结束后自动生成报告"""
    global _test_results

    # 获取配置
    cfg = None
    chip_name = "default"
    model_name = "unknown"

    try:
        cfg = load_config()
    except:
        pass

    # 获取芯片名称（优先级：命令行 > 环境变量 > config.yaml）
    cmd_chip = config.getoption("--chip", default=None)
    env_chip = os.environ.get("CHIP")

    if cmd_chip:
        chip_name = cmd_chip.lower()
    elif env_chip:
        chip_name = env_chip.lower()
    elif cfg:
        for name, chip_cfg in cfg.get("chips", {}).items():
            if isinstance(chip_cfg, dict) and chip_cfg.get("enabled", False):
                chip_name = name.lower()
                break

    # 获取模型名称（优先级：命令行 > 环境变量 > config.yaml）
    cmd_model = config.getoption("--model-name", default=None) or config.getoption(
        "--model", default=None
    )
    env_model = os.environ.get("MODEL_NAME")

    if cmd_model:
        model_name = cmd_model
    elif env_model:
        model_name = env_model
    elif cfg:
        for name, model_cfg in cfg.get("models", {}).items():
            if model_cfg.get("enabled", False):
                model_name = model_cfg.get("name", name)
                break
        if not model_name or model_name == "unknown":
            model_name = cfg.get("default_model", "unknown")

    model = {
        "name": model_name,
        "display_name": model_name,
        "model_name": model_name,
    }

    if not model:
        return

    # 使用公共报告生成器 (保留原有的 Markdown 报告)
    test_date = datetime.now().strftime("%Y-%m-%d")
    test_time = datetime.now().strftime("%H:%M:%S")

    generator = TestReportGenerator("test_reports", config=cfg)
    filepath = generator.generate(model, _test_results, test_date, test_time)

    # 生成 Allure 汇总报告
    allure_summary_path = None
    try:
        summary_report_dir = (
            config.getoption("--summary-report-dir", default=None) or "allure-report"
        )
        allure_summary_path = generate_allure_summary_report(
            _test_results,
            summary_report_dir,
            model.get("name", "unknown"),
            chip_name,
            config.getoption("--infra", default=None),
            config.getoption("--pd-mode", default=None),
            config.getoption("--tester", default=None),
            cfg,
        )
    except Exception as e:
        terminalreporter.write_line(f"Allure 汇总报告生成失败: {e}")

    # 获取pytest实际统计
    stats = terminalreporter.stats
    actual_passed = len(stats.get("passed", []))
    actual_failed = len(stats.get("failed", []))
    actual_skipped = len(stats.get("skipped", []))

    # 获取 allure-results 目录（从 pytest 配置获取实际路径）
    allure_results_dir = (
        config.option.alluredir
        or f"allure-results/{chip_name}/{model.get('name', 'unknown')}"
    )
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    allure_report_dir = (
        f"allure-report/{chip_name}/{model.get('name', 'unknown')}/{timestamp}"
    )

    terminalreporter.write_sep("=", "测试报告已生成")
    terminalreporter.write_line(f"Markdown 报告路径: {filepath}")
    if allure_summary_path:
        terminalreporter.write_line(f"Allure 汇总报告: {allure_summary_path}")
    terminalreporter.write_line(
        f"pytest函数级: 通过 {actual_passed}, 失败 {actual_failed}, 跳过 {actual_skipped}"
    )
    terminalreporter.write_line("")
    terminalreporter.write_line(
        f"生成 Allure HTML 报告: allure generate {allure_results_dir} -o {allure_report_dir} --clean"
    )
    terminalreporter.write_line(f"打开 Allure 报告: allure open {allure_report_dir}")
