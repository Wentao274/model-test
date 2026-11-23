"""
pytest全局配置和共享fixture
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
import pytest
import requests
import yaml
from typing import Dict, Any, List, Optional, Tuple

from base.api_client import ModelAPIClient, split_base_url
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
_failure_reasons = {}
_test_warnings = {}


def sanitize_model_name(name: str) -> str:
    """处理模型名中的路径分隔符，取最后一段作为模型名"""
    if not name:
        return name
    return name.rsplit("/", 1)[-1]


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


# 参数行为类测试用例豁免名单（a-h 套件）：
# 这些用例显式指定 temperature/top_p/seed——或其测试点即采样参数行为，
# 全局采样参数覆盖对其不生效，始终按用例自身参数执行。
# 默认规则（用户口径）：未明确指定加入豁免的 a-h 用例一律不豁免——全局采样覆盖生效。
RAW_SAMPLING_PARAM_TESTS = {
    "test_temperature_control",      # A6: temperature 控制（temp=0/1.0 对比断言）
    "test_top_p_top_k_sampling",     # A7: top_p/top_k 采样（参数化显式传参）
    "test_seed_reproducibility",    # A10: seed 可复现性（seed=42 一致性断言）
    "test_invalid_parameters",       # E3: 非法参数校验（temperature=-1/5.0）
    "test_generation_consistency",  # G2: temperature=0 生成一致性断言
}

# test_k 套件整体不参与全局采样覆盖（用户口径）：所有 K 用例保持原始
# 测试参数——工单/原始请求含采样参数的原样保留（K1 temperature=0.1、
# K2 temperature=1+top_p=0.95、K5-K9 思考档契约温度、K10/K11/K12 脚本
# temperature=0、K24 temperature=0.0），其余未含参数的用例一律不注入
# （无全局注入口）。新增 K 用例自动适用本规则，无需登记。
# 河南乐信 L 套件（test_lexin_agdc2_65.py）同样整模块豁免（用户口径
# 2026-11-13）：run-432「测试结果报文详情」全量导出的请求体原样发送
# （官方基准复现），不注入采样参数；新增 L 用例自动适用。
# 浙江讯盟 Z 套件（test_zjxm_agdc2_61.py）同样整模块豁免（用户口径
# 2026-11-16）：九章功能对比报告 20261110「实际传参」原始报文原样
# 发送（官方行为复现），不注入采样参数；新增 Z 用例自动适用。
# 深空数能 sksn 套件（test_sksn_agdc2_57.py）同样整模块豁免（用户口径
# 2026-11-17）：能力确认请求（含缓存/TTL 参数）原样发送，不注入采样
# 参数；新增 sksn 用例自动适用。
# 杭州耘擎智联 yqzl 套件（test_yqzl_agdc2_75.py）同样整模块豁免（用户
# 口径 2026-11-23）：九章 kimi-k3 测试报告「实际请求参数」原样重放，
# 不注入采样参数；报告用例变更自动适用。
RAW_SAMPLING_EXEMPT_FILES = {"test_k_customer_issue.py", "test_lexin_agdc2_65.py", "test_zjxm_agdc2_61.py", "test_sksn_agdc2_57.py", "test_yqzl_agdc2_75.py"}


def _parse_sampling_params(raw: str) -> Optional[Dict[str, Any]]:
    """解析 --sampling-params JSON 配置（全局采样参数覆盖）

    三态语义（未给值 = 不覆盖该参数，请求不携带）：
    - 整个参数留空 → 返回 None（不启用任何全局覆盖）
    - 字段省略、为 null 或空串 → 该字段不覆盖（不注入）

    Returns:
        {"temperature": Optional[float], "top_p": Optional[float],
         "seed": Optional[str]}，None 表示未启用
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise pytest.UsageError(f"--sampling-params 不是合法 JSON: {e}")
    if not isinstance(data, dict):
        raise pytest.UsageError(
            '--sampling-params 必须是 JSON 对象，'
            '如 {"temperature": 1.0, "top_p": 0.95, "seed": ""}'
        )

    def _num(key: str) -> Optional[float]:
        value = data.get(key)
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            raise pytest.UsageError(
                f"--sampling-params 中 {key} 不是数值: {value!r}"
            )

    seed = data.get("seed")
    if seed is not None:
        seed = str(seed).strip() or None
    return {
        "temperature": _num("temperature"),
        "top_p": _num("top_p"),
        "seed": seed,
    }


def _resolve_global_sampling_params(request) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """解析当前用例适用的全局采样参数 (temperature, top_p, seed)

    豁免名单内的用例与 test_k 套件用例（整套件保持原始测试参数——
    不参与全局采样覆盖）返回 (None, None, None)，按用例自身参数执行。
    --sampling-params 与旧 --seed 同时给出时，--sampling-params 优先。
    """
    if request.node.name.split("[")[0] in RAW_SAMPLING_PARAM_TESTS:
        return None, None, None
    # test_k 套件整体豁免：保持原始测试参数，不注入全局采样值
    fspath = getattr(request.node, "fspath", None)
    if fspath is not None and os.path.basename(str(fspath)) in RAW_SAMPLING_EXEMPT_FILES:
        return None, None, None
    sampling = _parse_sampling_params(
        request.config.getoption("--sampling-params", default=None)
    )
    if sampling is not None:
        return sampling["temperature"], sampling["top_p"], sampling["seed"]
    # 兼容旧 --seed 参数（仅在未提供 --sampling-params 时生效）
    cmd_seed = request.config.getoption("--seed", default=None)
    cmd_seed = cmd_seed.strip() if cmd_seed else None
    return None, None, cmd_seed


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
def record_warning(request):
    """记录测试警告信息，用于在报告中展示"""

    def _record(warning_msg: str):
        test_func = request.node.name.split("[")[0]
        test_func_base = (
            test_func.replace("test_", "")
            if test_func.startswith("test_")
            else test_func
        )
        for marker, category in TEST_CATEGORIES.items():
            for test_info in category["tests"]:
                if len(test_info) >= 4:
                    test_idx, test_name, test_desc, test_func_name = test_info[:4]
                else:
                    test_idx, test_name, test_desc = test_info
                    test_func_name = test_name.replace("-", "_").replace(" ", "_")
                if test_func_base == test_func_name:
                    key = f"{marker}_{test_idx}"
                    if key not in _test_warnings:
                        _test_warnings[key] = []
                    _test_warnings[key].append(warning_msg)
                    break

    return _record


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

    全局采样参数覆盖 (--sampling-params)：非豁免用例注入全局
    temperature/top_p/seed；豁免用例（RAW_SAMPLING_PARAM_TESTS）
    与 test_k 套件用例（整套件保持原始测试参数）不注入。
    """
    # 检查命令行参数
    cmd_chip = request.config.getoption("--chip", default=None)
    cmd_base_url = request.config.getoption("--base-url", default=None)
    cmd_api_key = request.config.getoption("--api-key", default=None)
    cmd_model_name = request.config.getoption("--model-name", default=None)
    cmd_thinking_mode = request.config.getoption("--thinking-mode", default=None)
    cmd_model_key = request.config.getoption("--model", default=None)
    # 全局 reasoning_effort（空字符串归一为 None，表示不传该参数）
    cmd_reasoning_effort = request.config.getoption("--reasoning-effort", default=None)
    cmd_reasoning_effort = cmd_reasoning_effort.strip() if cmd_reasoning_effort else None
    # 全局采样参数（temperature/top_p/seed，--sampling-params JSON 解析），
    # 豁免名单与 test_k 套件用例不注入
    global_temperature, global_top_p, global_seed = (
        _resolve_global_sampling_params(request)
    )

    # 如果有命令行参数，使用命令行参数
    if cmd_base_url:
        chip_name = (cmd_chip or "cli").lower()
        api_key = cmd_api_key if cmd_api_key is not None else "cli-api-key"
        model_name = (
            cmd_model_name or cmd_model_key or config.get("default_model", "qwen35")
        )
        model_name = sanitize_model_name(model_name)

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
            reasoning_effort=cmd_reasoning_effort,
            temperature=global_temperature,
            top_p=global_top_p,
            seed=global_seed,
            retry_times=config["global"].get("retry_times", 3),
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
        api_key = env_api_key if env_api_key is not None else "env-api-key"
        model_name = env_model_name or config.get("default_model", "qwen35")
        model_name = sanitize_model_name(model_name)

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
            reasoning_effort=cmd_reasoning_effort,
            temperature=global_temperature,
            top_p=global_top_p,
            seed=global_seed,
            retry_times=config["global"].get("retry_times", 3),
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
    model_name = sanitize_model_name(model_name)

    model_config = config["models"][model_name]
    if model_config.get("thinking_mode") is None:
        model_config["thinking_mode"] = True
    return ModelAPIClient(
        api_key=model_config["api_key"],
        base_url=chip_config["base_url"],
        model_name=model_config["name"],
        timeout=config["global"]["timeout"],
        config=model_config,
        reasoning_effort=cmd_reasoning_effort,
        temperature=global_temperature,
        top_p=global_top_p,
        seed=global_seed,
        retry_times=config["global"].get("retry_times", 3),
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

    cmd_reasoning_effort = request.config.getoption("--reasoning-effort", default=None)
    cmd_reasoning_effort = cmd_reasoning_effort.strip() if cmd_reasoning_effort else None
    # 全局采样参数（temperature/top_p/seed），豁免名单与 test_k 套件
    # 用例不注入
    global_temperature, global_top_p, global_seed = (
        _resolve_global_sampling_params(request)
    )

    return ModelAPIClient(
        api_key=model_config["api_key"],
        base_url=chip_config["base_url"],
        model_name=model_config["name"],
        timeout=config["global"]["timeout"],
        config=model_config,
        reasoning_effort=cmd_reasoning_effort,
        temperature=global_temperature,
        top_p=global_top_p,
        seed=global_seed,
        retry_times=config["global"].get("retry_times", 3),
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

    if model_name:
        model_name = sanitize_model_name(model_name)

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
        help="API base URL, optional version suffix (e.g., http://127.0.0.1:8080/v1, "
        "Zhipu official: https://open.bigmodel.cn/api/paas/v4)",
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
        "--reasoning-effort",
        action="store",
        default=None,
        help="Global reasoning_effort param (low/high/max); empty means not sent",
    )
    parser.addoption(
        "--seed",
        action="store",
        default=None,
        help="Global seed param (integer string); deprecated, use --sampling-params instead; "
        "only effective when --sampling-params is not provided",
    )
    parser.addoption(
        "--sampling-params",
        action="store",
        default=None,
        help=(
            'Global sampling params as JSON, e.g. '
            '{"temperature": 0.7, "top_p": 0.9, "seed": "42"}. '
            "Numeric field means global override; "
            "omitted/null/empty field means no override "
            "(param not sent unless a test explicitly sets it); "
            "empty value disables all overrides; "
            "exempt tests (RAW_SAMPLING_PARAM_TESTS) and the whole "
            "test_k suite (original ticket params) are never overridden"
        ),
    )
    parser.addoption(
        "--engine",
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
        "--build-number",
        action="store",
        default=None,
        help="Jenkins build number (Jenkinsfile passes BUILD_NUMBER "
        "through for K28/K29 raw output routing; empty in manual runs)",
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
            item.add_marker(pytest.mark.e_stability)
        elif "test_f_" in item.nodeid:
            item.add_marker(pytest.mark.f_api)
        elif "test_g_" in item.nodeid:
            item.add_marker(pytest.mark.g_quality_chat_completions)
        elif "test_h_" in item.nodeid:
            item.add_marker(pytest.mark.h_clear_thinking)
        elif "test_k_customer_" in item.nodeid:
            item.add_marker(pytest.mark.k_customer_issue)
        elif "test_lexin_" in item.nodeid:
            item.add_marker(pytest.mark.lexin_agdc2_65)
        elif "test_zjxm_" in item.nodeid:
            item.add_marker(pytest.mark.zjxm_agdc2_61)
        elif "test_sksn_" in item.nodeid:
            item.add_marker(pytest.mark.sksn_agdc2_57)
        elif "test_yqzl_" in item.nodeid:
            item.add_marker(pytest.mark.yqzl_agdc2_75)

    # L 套件（test_lexin_agdc2_65）默认排除口径（用户指定 2026-11-13，
    # 与 Jenkinsfile MARKER_ALL 排除互为双保险）：无显式点名时不收集
    # L 用例——仅当 -m 表达式含 lexin_agdc2_65 或命令行显式指定该
    # 文件/节点时收集（Jenkins 勾选 MARKER_LEXIN_AGDC2_65、
    # SPECIFIC_TEST 点名、本地 -m lexin_agdc2_65/指定路径均属显式）。
    markexpr = getattr(config.option, "markexpr", "") or ""
    lexin_explicit = "lexin_agdc2_65" in markexpr or any(
        "test_lexin_agdc2_65" in str(a) for a in (config.args or [])
    )
    if not lexin_explicit:
        items[:] = [i for i in items if "test_lexin_agdc2_65" not in i.nodeid]

    # Z 套件（test_zjxm_agdc2_61）默认排除口径（用户指定 2026-11-16，
    # 同 L 套件双保险）：无显式点名时不收集 Z 用例——仅当 -m 表达式
    # 含 zjxm_agdc2_61 或命令行显式指定该文件/节点时收集（Jenkins
    # 勾选 MARKER_ZJXM_AGDC2_61、本地 -m zjxm_agdc2_61/指定路径均属
    # 显式；Z 用例不进 SPECIFIC_TEST，用户指定）。
    zjxm_explicit = "zjxm_agdc2_61" in markexpr or any(
        "test_zjxm_agdc2_61" in str(a) for a in (config.args or [])
    )
    if not zjxm_explicit:
        items[:] = [i for i in items if "test_zjxm_agdc2_61" not in i.nodeid]

    # sksn 套件（test_sksn_agdc2_57）默认排除口径（用户指定 2026-11-17，
    # 同 L/Z 套件双保险）：无显式点名时不收集 sksn 用例——仅当 -m 表达式
    # 含 sksn_agdc2_57 或命令行显式指定该文件/节点时收集（Jenkins 勾选
    # MARKER_SKSN_AGDC2_57、本地 -m sksn_agdc2_57/指定路径均属显式；
    # sksn 用例不进 SPECIFIC_TEST，用户指定）。
    sksn_explicit = "sksn_agdc2_57" in markexpr or any(
        "test_sksn_agdc2_57" in str(a) for a in (config.args or [])
    )
    if not sksn_explicit:
        items[:] = [i for i in items if "test_sksn_agdc2_57" not in i.nodeid]

    # yqzl 套件（test_yqzl_agdc2_75）默认排除口径（用户指定 2026-11-23，
    # 同 L/Z/S 套件双保险）：无显式点名时不收集 yqzl 用例——仅当 -m 表达式
    # 含 yqzl_agdc2_75 或命令行显式指定该文件/节点时收集（Jenkins 勾选
    # MARKER_YQZL_AGDC2_75、本地 -m yqzl_agdc2_75/指定路径均属显式；
    # yqzl 用例不进 SPECIFIC_TEST，同 Z/S 套件口径）。
    yqzl_explicit = "yqzl_agdc2_75" in markexpr or any(
        "test_yqzl_agdc2_75" in str(a) for a in (config.args or [])
    )
    if not yqzl_explicit:
        items[:] = [i for i in items if "test_yqzl_agdc2_75" not in i.nodeid]


def pytest_configure(config):
    """注册自定义marker"""
    # 启动时校验 --sampling-params，非法配置 fail-fast，避免测试跑到一半才失败
    _parse_sampling_params(config.getoption("--sampling-params", default=None))

    config.addinivalue_line("markers", "a_basic: A类测试 - 基础推理能力")
    config.addinivalue_line("markers", "b_advanced: B类测试 - 高级生成功能")
    config.addinivalue_line("markers", "c_multimodal: C类测试 - 多模态能力")
    config.addinivalue_line("markers", "d_long_context: D类测试 - 长上下文处理")
    config.addinivalue_line("markers", "e_stability: E类测试 - 稳定性与边界")
    config.addinivalue_line("markers", "f_api: F类测试 - API兼容性")
    config.addinivalue_line(
        "markers",
        "g_quality_chat_completions: G类测试 - Chat Completions API质量评估与回答相关性",
    )
    config.addinivalue_line(
        "markers",
        "h_clear_thinking: H类测试 - clear_thinking 参数行为",
    )
    config.addinivalue_line(
        "markers",
        "k_customer_issue: K类测试 - 反馈问题验证",
    )
    config.addinivalue_line(
        "markers",
        "lexin_agdc2_65: L类测试 - 河南乐信工单 AGDC2-62/65 glm-5.3 客户卷子 72 用例复现",
    )
    config.addinivalue_line(
        "markers",
        "zjxm_agdc2_61: Z类测试 - 浙江讯盟工单 AGDC2-61 glm-5.3 功能对比报告失败场景 45 用例复现（42 失败场景 + 3 条官方基线异常守护）",
    )
    config.addinivalue_line(
        "markers",
        "sksn_agdc2_57: S类测试 - 深空数能工单 AGDC2-57 kimi-k3 能力确认 38 用例（协议层硬断言 + 能力层差异记录）",
    )
    config.addinivalue_line(
        "markers",
        "yqzl_agdc2_75: Y类测试 - 杭州耘擎智联工单 AGDC2-75 kimi-k3 功能测试报告 239 用例重放（断言基准=报告场景期望与逐项判定）",
    )
    config.addinivalue_line(
        "markers",
        "slow_ttl: 慢速 TTL 过期验证（等待约 5.5 分钟，-m 可排除）",
    )
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

        model_name = sanitize_model_name(model_name)
    except:
        pass

    # 设置 allure-results 目录
    # 优先级：命令行 --alluredir > 自动生成时间戳目录
    # 注意：allure-pytest 2.14+ 将 --alluredir 存入 config.option.allure_report_dir，
    # 旧版本为 config.option.alluredir，两者都检查以保持兼容
    alluredir = (
        getattr(config.option, "allure_report_dir", None)
        or getattr(config.option, "alluredir", None)
    )
    if alluredir:
        # 已通过 --alluredir 指定，直接使用
        allure_results_dir = alluredir
    else:
        # 自动生成时间戳目录
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        allure_results_dir = f"allure-results/{chip_name}/{model_name}/{timestamp}"

    # 同时写回两个属性：allure_report_dir 是 allure-pytest 2.14+ 实际读取的
    # 属性（决定结果文件写到哪里）；alluredir 供汇总提示逻辑使用
    config.option.allure_report_dir = allure_results_dir
    config.option.alluredir = allure_results_dir


_last_test_file = None
_last_test_func = None


def _extract_failure_reason(report) -> str:
    """从失败报告中提取简明的失败原因，格式: 短摘要|详细描述"""
    if not hasattr(report, "longrepr") or report.longrepr is None:
        return "未知错误|未知错误"
    longrepr = report.longrepr
    if hasattr(longrepr, "reprcrash") and longrepr.reprcrash:
        message = longrepr.reprcrash.message
    elif isinstance(longrepr, str):
        message = longrepr
    elif hasattr(longrepr, "reprtraceback") and longrepr.reprtraceback:
        entries = longrepr.reprtraceback.reprentries
        if entries:
            message = str(entries[-1].reprfileloc)
        else:
            message = str(longrepr)
    else:
        message = str(longrepr)
    short, detail = _summarize_error(message)
    detail = detail[:300] if len(detail) > 300 else detail
    return f"{short}|{detail}"


def _summarize_error(message: str):
    """将错误信息总结为(短摘要, 详细描述)"""
    msg = message.strip()
    error_rules = [
        ("IndexError: list index out of range", "索引越界"),
        ("IndexError", "索引越界"),
        ("TypeError: object of type 'NoneType' has no len()", "返回值为None"),
        ("TypeError", "类型错误"),
        ("ValueError: empty separator", "空分隔符"),
        ("ValueError", "值错误"),
        ("NameError", "变量未定义"),
        ("AssertionError", "断言失败"),
        ("json_parse_error", "JSON解析错误"),
        ("missing field `type`", "缺少type字段"),
        ("missing field", "缺少必填字段"),
        ("TimeoutError", "请求超时"),
        ("ConnectionError", "连接错误"),
        ("API request failed", "API请求失败"),
    ]
    for pattern, short in error_rules:
        if pattern in msg:
            detail = msg.replace("\n", " ").strip()
            if len(detail) > 200:
                detail = detail[:197] + "..."
            return short, detail
    last_line = msg.split("\n")[-1].strip() if "\n" in msg else msg
    short = last_line[:15] + "..." if len(last_line) > 15 else last_line
    detail = msg.replace("\n", " ").strip()
    if len(detail) > 200:
        detail = detail[:197] + "..."
    return short or "未知错误", detail or "未知错误"


def _get_skip_reason(report) -> str:
    """获取跳过原因

    对于 pytest.skip() 调用，report.longrepr 是一个三元组 (path, lineno, reason)。
    对于 @pytest.mark.skip(reason=...) 标记，格式相同。
    对于 xfail 预期失败，report.wasxfail 存储原因字符串。
    """
    wasxfail = getattr(report, "wasxfail", None)
    if wasxfail:
        detail = wasxfail[:300]
        return f"预期失败|{detail}"
    longrepr = getattr(report, "longrepr", None)
    if longrepr is not None:
        if isinstance(longrepr, (tuple, list)) and len(longrepr) >= 3:
            reason = str(longrepr[2])
            # 去掉 pytest 自动添加的 "Skipped: " 前缀
            if reason.startswith("Skipped: "):
                reason = reason[len("Skipped: "):]
            return f"跳过|{reason[:300]}"
        if isinstance(longrepr, str):
            return f"跳过|{longrepr[:300]}"
    return "跳过|未知原因"


def _match_test_category(report):
    """将测试报告匹配到测试分类和测试编号。

    Returns:
        (marker, test_idx) 或 None
    """
    test_id = report.nodeid
    test_file = test_id.split("::")[0]
    test_func = test_id.split("::")[-1].split("[")[0]

    marker_from_file = None
    test_file_basename = test_file.replace("\\", "/").split("/")[-1]
    if test_file_basename.startswith("test_g_"):
        marker_from_file = "g_quality_chat_completions"
    elif test_file_basename.startswith("test_h_"):
        marker_from_file = "h_clear_thinking"
    elif test_file_basename.startswith("test_k_customer_"):
        marker_from_file = "k_customer_issue"

    test_func_base = (
        test_func.replace("test_", "")
        if test_func.startswith("test_")
        else test_func
    )

    for marker, category in TEST_CATEGORIES.items():
        if marker_from_file and marker != marker_from_file:
            continue
        for test_info in category["tests"]:
            if len(test_info) >= 4:
                test_idx, test_name, test_desc, test_func_name = test_info[:4]
            else:
                test_idx, test_name, test_desc = test_info
                test_func_name = test_name.replace("-", "_").replace(" ", "_")
            if test_func_base == test_func_name:
                return marker, test_idx
    return None


def pytest_runtest_logreport(report):
    """收集测试结果并输出分隔线，同时记录到 Allure"""
    global _test_results, _last_test_file, _last_test_func

    # 处理 setup 阶段的跳过（@pytest.mark.skip 标记、fixture 中的 pytest.skip）
    # 这类跳过不会产生 call 阶段报告，需要在此捕获
    if report.when == "setup" and report.skipped:
        matched = _match_test_category(report)
        if matched:
            marker, test_idx = matched
            key = f"{marker}_{test_idx}"
            # 仅在尚未记录时写入，避免覆盖 call 阶段的结果
            if key not in _test_results:
                _test_results[key] = "SKIPPED"
                _failure_reasons[key] = _get_skip_reason(report)
        return

    if report.when != "call":
        return

    test_id = report.nodeid
    test_file = test_id.split("::")[0]
    test_func = test_id.split("::")[-1].split("[")[0]

    if _last_test_file and _last_test_file != test_file:
        print("\n" + "=" * 60)

    if _last_test_func and _last_test_func != test_func:
        print("-" * 40)

    _last_test_file = test_file
    _last_test_func = test_func

    matched = _match_test_category(report)
    if matched:
        marker, test_idx = matched
        key = f"{marker}_{test_idx}"
        if report.passed:
            _test_results[key] = "PASSED"
        elif report.failed:
            _test_results[key] = "FAILED"
            _failure_reasons[key] = _extract_failure_reason(report)
        else:
            _test_results[key] = "SKIPPED"
            skip_reason = _get_skip_reason(report)
            if skip_reason:
                _failure_reasons[key] = skip_reason


def pytest_runtest_setup(item):
    """在每个测试函数运行前检查文件变化并输出分隔线"""
    # 仅清除当前测试的警告记录，保留其他测试已记录的警告。
    # 之前使用 _test_warnings.clear() 会清除所有测试的警告，
    # 导致非最后一个测试的警告在最终报告中丢失。
    category_info = get_test_category_info(item.nodeid)
    if category_info:
        marker, test_idx = category_info[0], category_info[1]
        _test_warnings.pop(f"{marker}_{test_idx}", None)
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


def _generate_lexin_reports(terminalreporter, config, cfg, chip_name,
                            model_name):
    """乐信 L 套件报告：导出请求录制记录 JSON 并生成 HTML + 汇总 MD。

    隔离口径（用户确认 2026-11-15）：本次运行无任何 test_lexin 节点时
    直接返回 None——不导入 lexin 模块、不产生任何输出，通用报告流程
    与未改动前完全一致；仅 lexin 实际运行时才生成。
    返回 (html_path, md_path)。
    """
    stats = getattr(terminalreporter, "stats", None) or {}
    ran = []
    for key in ("passed", "failed", "skipped", "error"):
        ran.extend(stats.get(key) or [])
    if not any(
        getattr(r, "nodeid", "").startswith("tests/test_lexin_agdc2_65")
        for r in ran
    ):
        return None
    from tests.test_lexin_agdc2_65 import _LEXIN_RECORDER
    summary_report_dir = (
        config.getoption("--summary-report-dir", default=None)
        or "allure-report"
    )
    alluredir = (
        getattr(config.option, "alluredir", None) or "allure-results"
    )
    # 导出录制记录（供离线重生成与追溯）
    os.makedirs(alluredir, exist_ok=True)
    records_path = os.path.join(
        os.path.dirname(os.path.abspath(alluredir)), "lexin_records.json"
    )
    with open(records_path, "w", encoding="utf-8") as f:
        json.dump(_LEXIN_RECORDER, f, ensure_ascii=False, indent=1)
    from base.lexin_html_report import generate_reports
    base_url = config.getoption("--base-url", default=None) or ""
    html_path, md_path = generate_reports(
        alluredir, records_path, summary_report_dir,
        model_name=model_name, base_url=base_url,
        chip_name=chip_name,
        engine=config.getoption("--engine", default=None) or "",
    )
    return html_path, md_path


def _generate_zjxm_reports(terminalreporter, config, cfg, chip_name,
                           model_name):
    """浙江讯盟 Z 套件报告：导出请求录制记录 JSON 并生成 HTML + 汇总 MD。

    隔离口径（同 L 套件，用户确认 2026-11-16）：本次运行无任何
    test_zjxm 节点时直接返回 None——不导入 zjxm 模块、不产生任何输出，
    通用报告流程与未改动前完全一致；仅 zjxm 实际运行时才生成。
    返回 (html_path, md_path)。
    """
    stats = getattr(terminalreporter, "stats", None) or {}
    ran = []
    for key in ("passed", "failed", "skipped", "error"):
        ran.extend(stats.get(key) or [])
    if not any(
        getattr(r, "nodeid", "").startswith("tests/test_zjxm_agdc2_61")
        for r in ran
    ):
        return None
    from tests.test_zjxm_agdc2_61 import _ZJXM_RECORDER
    summary_report_dir = (
        config.getoption("--summary-report-dir", default=None)
        or "allure-report"
    )
    alluredir = (
        getattr(config.option, "alluredir", None) or "allure-results"
    )
    # 导出录制记录（供离线重生成与追溯）
    os.makedirs(alluredir, exist_ok=True)
    records_path = os.path.join(
        os.path.dirname(os.path.abspath(alluredir)), "zjxm_records.json"
    )
    with open(records_path, "w", encoding="utf-8") as f:
        json.dump(_ZJXM_RECORDER, f, ensure_ascii=False, indent=1)
    from base.zjxm_html_report import generate_reports
    base_url = config.getoption("--base-url", default=None) or ""
    html_path, md_path = generate_reports(
        alluredir, records_path, summary_report_dir,
        model_name=model_name, base_url=base_url,
        chip_name=chip_name,
        engine=config.getoption("--engine", default=None) or "",
    )
    return html_path, md_path


def _generate_sksn_reports(terminalreporter, config, cfg, chip_name,
                           model_name):
    """深空数能 sksn 套件报告：导出请求录制记录+能力观察 JSON 并生成
    HTML + 汇总 MD。

    隔离口径（同 L/Z 套件，用户确认 2026-11-17）：本次运行无任何
    test_sksn 节点时直接返回 None——不导入 sksn 模块、不产生任何输出，
    通用报告流程与未改动前完全一致；仅 sksn 实际运行时才生成。
    返回 (html_path, md_path)。
    """
    stats = getattr(terminalreporter, "stats", None) or {}
    ran = []
    for key in ("passed", "failed", "skipped", "error"):
        ran.extend(stats.get(key) or [])
    if not any(
        getattr(r, "nodeid", "").startswith("tests/test_sksn_agdc2_57")
        for r in ran
    ):
        return None
    from tests.test_sksn_agdc2_57 import _SKSN_RECORDER, _SKSN_OBS
    summary_report_dir = (
        config.getoption("--summary-report-dir", default=None)
        or "allure-report"
    )
    alluredir = (
        getattr(config.option, "alluredir", None) or "allure-results"
    )
    # 导出录制记录+能力观察（供离线重生成与追溯）
    os.makedirs(alluredir, exist_ok=True)
    records_path = os.path.join(
        os.path.dirname(os.path.abspath(alluredir)), "sksn_records.json"
    )
    with open(records_path, "w", encoding="utf-8") as f:
        json.dump({"records": _SKSN_RECORDER, "obs": _SKSN_OBS},
                  f, ensure_ascii=False, indent=1)
    from base.sksn_html_report import generate_reports
    base_url = config.getoption("--base-url", default=None) or ""
    html_path, md_path = generate_reports(
        alluredir, records_path, summary_report_dir,
        model_name=model_name, base_url=base_url,
        chip_name=chip_name,
        engine=config.getoption("--engine", default=None) or "",
    )
    return html_path, md_path


def _generate_yqzl_reports(terminalreporter, config, cfg, chip_name,
                           model_name):
    """杭州耘擎智联 yqzl 套件报告：导出请求录制记录+观察 JSON 并生成
    HTML + 汇总 MD。

    隔离口径（同 L/Z/S 套件，用户确认 2026-11-23）：本次运行无任何
    test_yqzl 节点时直接返回 None——不导入 yqzl 模块、不产生任何输出，
    通用报告流程与未改动前完全一致；仅 yqzl 实际运行时才生成。
    返回 (html_path, md_path)。
    """
    stats = getattr(terminalreporter, "stats", None) or {}
    ran = []
    for key in ("passed", "failed", "skipped", "error"):
        ran.extend(stats.get(key) or [])
    if not any(
        getattr(r, "nodeid", "").startswith("tests/test_yqzl_agdc2_75")
        for r in ran
    ):
        return None
    from tests.test_yqzl_agdc2_75 import _YQZL_RECORDER, _YQZL_OBS, _YQZL_EVALS
    summary_report_dir = (
        config.getoption("--summary-report-dir", default=None)
        or "allure-report"
    )
    alluredir = (
        getattr(config.option, "alluredir", None) or "allure-results"
    )
    # 导出录制记录+观察+逐项判定（供离线重生成与追溯）
    os.makedirs(alluredir, exist_ok=True)
    records_path = os.path.join(
        os.path.dirname(os.path.abspath(alluredir)), "yqzl_records.json"
    )
    with open(records_path, "w", encoding="utf-8") as f:
        json.dump({"records": _YQZL_RECORDER, "obs": _YQZL_OBS,
                   "evals": {k: [[t, ok, d] for t, ok, d in v]
                             for k, v in _YQZL_EVALS.items()}},
                  f, ensure_ascii=False, indent=1)
    from base.yqzl_html_report import generate_reports
    base_url = config.getoption("--base-url", default=None) or ""
    html_path, md_path = generate_reports(
        alluredir, records_path, summary_report_dir,
        model_name=model_name, base_url=base_url,
        chip_name=chip_name,
        engine=config.getoption("--engine", default=None) or "",
    )
    return html_path, md_path


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

    model_name = sanitize_model_name(model_name)

    model = {
        "name": model_name,
        "display_name": model_name,
        "model_name": model_name,
    }

    if not model:
        return

    # 乐信 L 套件报告（HTML + 汇总 MD + 录制记录 JSON）：
    # - 纯 lexin 运行（_test_results 为空——lexin 不注册进
    #   TEST_CATEGORIES、结果不采集）-> 顶替两份通用 MD 报告；
    # - 混合运行 -> 通用 MD 照旧生成，lexin HTML/MD 额外追加。
    # 浙江讯盟 Z 套件报告（2026-11-16）：同 L 套件口径——纯 zjxm 运行
    # 顶替通用报告；混合运行（zjxm+lexin 或 zjxm+通用用例）时通用报告
    # 照旧生成，zjxm HTML/MD 额外追加。
    # 深空数能 sksn 套件报告（2026-11-17）：同 L/Z 套件口径——纯 sksn
    # 运行顶替通用报告；混合运行时通用报告照旧，sksn HTML/MD 额外追加。
    lexin_report = None
    try:
        lexin_report = _generate_lexin_reports(
            terminalreporter, config, cfg, chip_name, model.get("name"))
    except Exception as e:
        terminalreporter.write_line(f"乐信 L 套件报告生成失败: {e}")

    zjxm_report = None
    try:
        zjxm_report = _generate_zjxm_reports(
            terminalreporter, config, cfg, chip_name, model.get("name"))
    except Exception as e:
        terminalreporter.write_line(f"浙江讯盟 Z 套件报告生成失败: {e}")

    sksn_report = None
    try:
        sksn_report = _generate_sksn_reports(
            terminalreporter, config, cfg, chip_name, model.get("name"))
    except Exception as e:
        terminalreporter.write_line(f"深空数能 sksn 套件报告生成失败: {e}")

    yqzl_report = None
    try:
        yqzl_report = _generate_yqzl_reports(
            terminalreporter, config, cfg, chip_name, model.get("name"))
    except Exception as e:
        terminalreporter.write_line(f"杭州耘擎智联 yqzl 套件报告生成失败: {e}")

    if not _test_results:
        if lexin_report:
            html_path, md_path = lexin_report
            terminalreporter.write_sep("=", "乐信 L 套件测试报告已生成")
            terminalreporter.write_line(f"HTML 报告路径: {html_path}")
            terminalreporter.write_line(f"Markdown 汇总路径: {md_path}")
        if zjxm_report:
            html_path, md_path = zjxm_report
            terminalreporter.write_sep("=", "浙江讯盟 Z 套件测试报告已生成")
            terminalreporter.write_line(f"HTML 报告路径: {html_path}")
            terminalreporter.write_line(f"Markdown 汇总路径: {md_path}")
        if sksn_report:
            html_path, md_path = sksn_report
            terminalreporter.write_sep("=", "深空数能 sksn 套件测试报告已生成")
            terminalreporter.write_line(f"HTML 报告路径: {html_path}")
            terminalreporter.write_line(f"Markdown 汇总路径: {md_path}")
        if yqzl_report:
            html_path, md_path = yqzl_report
            terminalreporter.write_sep("=", "杭州耘擎智联 yqzl 套件测试报告已生成")
            terminalreporter.write_line(f"HTML 报告路径: {html_path}")
            terminalreporter.write_line(f"Markdown 汇总路径: {md_path}")
        if lexin_report or zjxm_report or sksn_report or yqzl_report:
            return
        # 非 lexin/zjxm/sksn/yqzl 且无采集结果（如空跑）——落到通用流程兜底

    # 使用公共报告生成器 (保留原有的 Markdown 报告)
    test_date = datetime.now().strftime("%Y-%m-%d")
    test_time = datetime.now().strftime("%H:%M:%S")

    generator = TestReportGenerator("test_reports", config=cfg)
    filepath = generator.generate(
        model,
        _test_results,
        test_date,
        test_time,
        chip_name=chip_name,
        failure_reasons=_failure_reasons,
        test_warnings=_test_warnings,
    )

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
            config.getoption("--engine", default=None),
            config.getoption("--pd-mode", default=None),
            config.getoption("--tester", default=None),
            cfg,
            failure_reasons=_failure_reasons,
            test_warnings=_test_warnings,
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


def _resolve_connectivity_config(session) -> Dict[str, Any]:
    """解析连通性检查所需的 base_url / api_key / model_name

    优先级：
    - base_url: 命令行 --base-url > 环境变量 BASE_URL > config.yaml 启用的 chip
    - api_key:  命令行 --api-key > 环境变量 API_KEY（可为空）
    - model_name: 命令行 --model-name/--model > 环境变量 MODEL_NAME > config.yaml default_model
    """
    cfg = {}
    try:
        cfg = load_config()
    except Exception as e:
        print(f"[连通性检查] 警告: 加载 config.yaml 失败: {e}")

    py_config = session.config

    base_url = py_config.getoption("--base-url", default=None) or os.environ.get(
        "BASE_URL"
    )
    if not base_url:
        for name, chip_cfg in cfg.get("chips", {}).items():
            if isinstance(chip_cfg, dict) and chip_cfg.get("enabled", False):
                base_url = chip_cfg.get("base_url")
                break
            elif chip_cfg is True:
                base_url = ""
                break

    cmd_api_key = py_config.getoption("--api-key", default=None)
    api_key = cmd_api_key if cmd_api_key else os.environ.get("API_KEY", "")

    cmd_model = py_config.getoption(
        "--model-name", default=None
    ) or py_config.getoption("--model", default=None)
    env_model = os.environ.get("MODEL_NAME")
    model_name = cmd_model or env_model or cfg.get("default_model", "qwen35")

    normalized_base_url, api_version = split_base_url(base_url)

    return {
        "base_url": normalized_base_url,
        "api_version": api_version,
        "api_key": api_key or "",
        "model_name": model_name,
    }


def _fail_and_exit(msg: str, code: int = 2) -> None:
    """打印错误消息并直接退出 Python

    使用 os._exit() 而非 pytest.exit()，是为了绕过 pytest 在
    pytest_sessionstart 阶段对 Exit 异常的双重 traceback 输出，
    确保错误信息只打印一次。

    同时将失败原因写入标记文件（路径由 CONNECTIVITY_FAILED_FLAG
    环境变量指定），供 Jenkinsfile 检测并在邮件中提示。
    """
    flag_file = os.environ.get("CONNECTIVITY_FAILED_FLAG", "")
    if flag_file:
        try:
            flag_dir = os.path.dirname(flag_file)
            if flag_dir:
                os.makedirs(flag_dir, exist_ok=True)
            with open(flag_file, "w", encoding="utf-8") as f:
                f.write(msg)
        except Exception:
            pass
    print(f"\n{msg}", file=sys.stderr)
    os._exit(code)


def _run_connectivity_check(session) -> None:
    """在测试运行前执行模型 API 连通性检查

    检查项：
      1. GET {base_url}/models
      2. POST {base_url}/chat/completions (messages=[hello])

    api_key 为空时不传 Authorization 头，否则自动添加 Bearer 鉴权。
    检查失败直接退出进程（exit code 2），避免无效用例执行。
    """
    info = _resolve_connectivity_config(session)
    base_url = info["base_url"]
    api_version = info.get("api_version", "v1")
    api_key = info["api_key"]
    model_name = info["model_name"]

    if not base_url:
        print(
            "\n[连通性检查] 跳过: 未配置 BASE_URL（命令行、环境变量、config.yaml 均无）"
        )
        return

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    print("\n=== API 连通性检查 ===")
    print(f"  BASE_URL: {base_url} (端点版本号段: /{api_version})")
    print(f"  MODEL: {model_name}")
    if api_key:
        masked = f"***{api_key[-4:]}" if len(api_key) > 4 else "***"
        print(f"  API_KEY: {masked}")
    else:
        print("  API_KEY: (空, 不携带鉴权头)")

    # 1. 检查 /models
    # models_url = f"{base_url}/v1/models"
    # try:
    #     resp = requests.get(models_url, headers=headers, timeout=10)
    # except requests.exceptions.RequestException as e:
    #     _fail_and_exit(f"ERROR: API 连通性检查失败, 无法访问 {models_url}: {e}")
    #
    # if resp.status_code != 200:
    #     _fail_and_exit(
    #         f"ERROR: API 连通性检查失败, HTTP状态码: {resp.status_code}, URL: {models_url}\n"
    #         f"响应内容: {resp.text[:500]}"
    #     )
    # print(f"  [OK] /models 连通性检查通过, HTTP状态码: {resp.status_code}")

    # 2. 检查 /chat/completions
    chat_url = f"{base_url}/{api_version}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 10,
    }
    try:
        resp = requests.post(chat_url, headers=headers, json=payload, timeout=30)
    except requests.exceptions.RequestException as e:
        _fail_and_exit(
            f"ERROR: Chat Completions 接口检查失败, 无法访问 {chat_url}: {e}"
        )

    if resp.status_code != 200:
        _fail_and_exit(
            f"ERROR: Chat Completions 接口检查失败, HTTP状态码: {resp.status_code}\n"
            f"响应内容: {resp.text[:500]}\n"
            f"提示: 目标服务若使用非 /v1 版本路径（如智谱官方 "
            f"https://open.bigmodel.cn/api/paas/v4），BASE_URL 需以版本号段结尾"
        )
    print(f"  [OK] /chat/completions 连通性检查通过, HTTP状态码: {resp.status_code}")
    print("=== API 连通性检查完成 ===\n")


def pytest_sessionstart(session):
    """pytest 会话开始时执行 API 连通性检查

    不在此处捕获异常: pytest.exit 内部抛出的 _pytest.outcomes.Exit 是
    Exception 的子类，外层再包装一次会导致错误信息被打印两次。
    任何真实的异常将由 pytest 自行输出 traceback。
    """
    _run_connectivity_check(session)
