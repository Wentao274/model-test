"""
pytest全局配置和共享fixture
"""
import os
import pytest
import yaml
from typing import Dict, Any, List

from base.api_client import ModelAPIClient


def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
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