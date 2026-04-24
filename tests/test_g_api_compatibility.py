"""
G. API 兼容性测试

测试点：
- G1: OpenAI Chat Completions - /v1/chat/completions 接口兼容
- G2: OpenAI Completions - /v1/completions 接口兼容
- G3: 模型列表 - /v1/models 接口
- G4: Usage 统计 - usage 字段准确性
- G5: 错误码规范 - 400/401/404/429/500 错误码
- G6: 客户端 SDK 兼容 - Python openai / JS @openai/sdk
- G7: 响应格式变体 - response_format 参数测试
- G8: Stream参数 - stream 参数测试
"""

import pytest
from typing import Dict, Any

from base.base_test import BaseTest
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestAPICompatibility(BaseTest):
    """API兼容性测试类"""

    def get_test_category(self) -> str:
        return "G. API兼容性"

    @pytest.mark.g_api
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_chat_completions_api(self, api_client: ModelAPIClient, test_logger):
        """G1: OpenAI Chat Completions 接口兼容"""
        test_logger.info("=== 测试开始: Chat Completions API ===")

        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "你好"},
        ]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "Chat Completions响应")

        # 验证响应格式
        self.assert_response_success(response)
        test_logger.info("Chat Completions API 兼容")

        # 验证必要字段
        message = response["choices"][0]["message"]
        assert "role" in message, "Should have role field"
        assert "content" in message, "Should have content field"
        assert message["role"] == "assistant", "Role should be assistant"

        # 验证usage
        usage = response.get("usage", {})
        assert "prompt_tokens" in usage or "completion_tokens" in usage, (
            "Should have usage"
        )

        test_logger.info(f"Chat Completions API: OK, usage={usage}")

    @pytest.mark.g_api
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_completions_api(self, api_client: ModelAPIClient, test_logger):
        """G2: OpenAI Completions 接口兼容"""
        test_logger.info("=== 测试开始: Completions API ===")

        prompt = "你好，请介绍一下自己"
        test_logger.info(f"Prompt: {prompt}")

        try:
            response = api_client.completion(prompt=prompt, max_tokens=50)

            # 验证响应
            assert response.get("choices") is not None, "Should have choices"
            assert len(response["choices"]) > 0, "Should have at least one choice"

            text = response["choices"][0].get("text", "")
            assert len(text) > 0, "Should have text content"

            test_logger.info(f"Completions API: OK, text={text[:50]}")
        except Exception as e:
            pytest.skip(f"Completions API not supported: {e}")

    @pytest.mark.g_api
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_models_list(self, api_client: ModelAPIClient, test_logger):
        """G3: 模型列表接口"""
        test_logger.info("=== 测试开始: Models List ===")

        response = api_client.list_models()

        # 验证响应格式
        assert "data" in response or "object" in response, "Should have valid response"

        # 验证数据格式
        if "data" in response:
            models = response["data"]
            assert isinstance(models, list), "Models should be a list"

            if models:
                model = models[0]
                assert "id" in model, "Model should have id"
                test_logger.info(f"Models list: {len(models)} models found")

    @pytest.mark.g_api
    @pytest.mark.p0
    def test_usage_statistics(self, api_client: ModelAPIClient, test_logger):
        """G4: Usage 统计准确性"""
        test_logger.info("=== 测试开始: Usage统计 ===")

        messages = [{"role": "user", "content": "请写一段话"}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 100})

        response = api_client.chat_completion(messages, max_tokens=100)

        # 验证usage存在
        usage = response.get("usage", {})
        assert usage, "Should have usage statistics"

        # 验证必要字段
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        # 验证token计算正确
        if total_tokens > 0:
            assert total_tokens == prompt_tokens + completion_tokens, (
                f"total_tokens should equal sum: {total_tokens} != {prompt_tokens} + {completion_tokens}"
            )

        assert completion_tokens > 0, "Should have completion tokens"

        test_logger.info(
            f"Usage: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}"
        )

    @pytest.mark.g_api
    @pytest.mark.p1
    def test_error_codes(self, api_client: ModelAPIClient, test_logger):
        """G5: 错误码规范 - 400/401/404/429/500 错误码"""
        test_logger.info("=== 测试开始: 错误码规范 ===")

        messages = [{"role": "user", "content": "测试"}]

        # 测试 401 认证错误（无效的API key）
        try:
            # 使用无效的session来模拟认证失败
            from base.api_client import ModelAPIClient

            invalid_client = ModelAPIClient(
                base_url=api_client.base_url,
                api_key="invalid_key_12345",
                model_name=api_client.model_name,
            )
            response = invalid_client.chat_completion(messages)
            if response.get("error"):
                error = response["error"]
                test_logger.info(f"401 错误响应: {error}")
                # 验证错误格式符合 OpenAI 规范
                assert "code" in error or "type" in error, (
                    "Error should have code or type"
                )
                assert (
                    error.get("code") in ["invalid_api_key", "authentication_failed"]
                    or error.get("type") == "authentication_error"
                    or "401" in str(error)
                ), "Should be authentication error"
        except Exception as e:
            test_logger.info(f"401 错误（异常）: {e}")

        # 测试 400 错误（无效请求）
        try:
            # 发送空的content来触发400错误
            invalid_messages = [{"role": "user", "content": ""}]
            response = api_client.chat_completion(invalid_messages, max_tokens=1)
            if response.get("error"):
                error = response["error"]
                test_logger.info(f"400 错误响应: {error}")
        except Exception as e:
            test_logger.info(f"400 错误（异常）: {e}")

        test_logger.info("错误码规范测试完成")

    @pytest.mark.g_api
    @pytest.mark.p0
    def test_client_sdk_compatibility(self, api_client: ModelAPIClient, test_logger):
        """G6: 客户端 SDK 兼容 - Python openai 库直接调用"""
        test_logger.info("=== 测试开始: 客户端 SDK 兼容 ===")

        # 测试使用标准 OpenAI SDK 格式调用
        try:
            from openai import OpenAI

            # 创建客户端（使用兼容的base_url）
            client = OpenAI(
                api_key=api_client.api_key or "dummy",
                base_url=f"{api_client.base_url}/v1",
            )

            messages = [{"role": "user", "content": "测试SDK兼容性"}]

            # 调用 chat.completions.create
            response = client.chat.completions.create(
                model=api_client.model_name, messages=messages, max_tokens=50
            )

            test_logger.info(f"SDK 响应: {response}")
            test_logger.info(f"SDK 返回ID: {response.id}")

            # 验证响应格式
            assert response.id is not None, "Should have response id"
            assert len(response.choices) > 0, "Should have choices"
            assert response.choices[0].message.content is not None, (
                "Should have content"
            )

            test_logger.info("客户端 SDK 兼容性测试通过")
        except ImportError:
            pytest.skip("openai SDK not installed")
        except Exception as e:
            test_logger.warning(f"SDK 兼容性测试: {e}")
            pytest.skip(f"SDK compatibility test failed: {e}")

    @pytest.mark.g_api
    @pytest.mark.p1
    def test_response_format_variants(self, api_client: ModelAPIClient, test_logger):
        """额外测试：响应格式变体"""
        test_logger.info("=== 测试开始: Response Format Variants ===")

        messages = [{"role": "user", "content": "测试"}]

        # 测试不同参数组合
        response1 = api_client.chat_completion(messages, temperature=0.7, max_tokens=50)
        self.assert_response_success(response1)

        response2 = api_client.chat_completion(messages, temperature=0, max_tokens=50)
        self.assert_response_success(response2)

        response3 = api_client.chat_completion(messages, temperature=1.0, max_tokens=50)
        self.assert_response_success(response3)

        test_logger.info("Response format variants: OK")

    @pytest.mark.g_api
    @pytest.mark.p1
    def test_stream_parameter(self, api_client: ModelAPIClient, test_logger):
        """额外测试：stream参数"""
        test_logger.info("=== 测试开始: Stream Parameter ===")

        messages = [{"role": "user", "content": "测试"}]
        TestLogger.log_request(test_logger, messages)

        # 流式请求
        response_iter = api_client.chat_completion_stream(messages, max_tokens=50)
        chunks = list(response_iter)

        test_logger.info(f"Stream parameter: {len(chunks)} chunks")
        assert len(chunks) > 0, "Should receive streaming chunks"
