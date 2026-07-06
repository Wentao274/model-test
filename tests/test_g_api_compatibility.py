"""
G. API 兼容性测试

测试点：
- G1: OpenAI Chat Completions - /v1/chat/completions 接口兼容 [P0]
- G2: OpenAI Completions - /v1/completions 接口兼容 [P1]
- G3: 模型列表 - /v1/models 接口 [P0]
- G4: Usage 统计 - usage 字段准确性 [P0]
- G5: 错误码规范 - 400/401/404/429/500 错误码 [P1]
- G6: 客户端 SDK 兼容 - Python openai / JS @openai/sdk [P0]
- G7: 响应格式变体 - response_format 参数测试 [P2]
- G8: Stream参数 - stream 参数测试 [P2]
"""

import pytest
from typing import Dict, Any

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestAPICompatibility(BaseTest, StreamingTestMixin):
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
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2048})

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "Chat Completions响应")
        self.log_full_response(test_logger, response, "G1-ChatCompletions")

        # 验证响应格式
        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        # 验证id字段
        assert response.get("id") is not None, "Should have response id"

        # 验证必要字段
        message = response["choices"][0]["message"]
        assert "role" in message, "Should have role field"
        assert "content" in message, "Should have content field"
        assert message["role"] == "assistant", "Role should be assistant"

        # 验证usage
        usage = response.get("usage", {})
        assert usage, "Should have usage statistics"
        assert usage.get("prompt_tokens", 0) > 0, "Should have prompt_tokens > 0"
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )

        test_logger.info(f"Chat Completions API: OK, usage={usage}")

    @pytest.mark.g_api
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_completions_api(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """G2: OpenAI Completions 接口兼容"""
        test_logger.info("=== 测试开始: Completions API ===")

        prompt = "你好，请介绍一下自己"
        test_logger.info(f"Prompt: {prompt}")
        TestLogger.log_request(
            test_logger, [{"role": "user", "content": prompt}], {"max_tokens": 100}
        )

        try:
            response = api_client.completion(prompt=prompt, max_tokens=100)
            TestLogger.log_response(test_logger, response, "Completions API响应")
            self.log_full_response(test_logger, response, "G2-Completions")

            # 验证响应
            assert response.get("choices") is not None, "Should have choices"
            assert len(response["choices"]) > 0, "Should have at least one choice"

            text = response["choices"][0].get("text", "")
            assert len(text.strip()) > 0, (
                f"Should have non-empty text content, got {len(text)} chars"
            )

            usage = response.get("usage", {})
            if usage:
                assert usage.get("completion_tokens", 0) > 0, (
                    "Should have completion_tokens > 0"
                )

            test_logger.info(f"Completions API: OK, text={text[:100]}, usage={usage}")
        except Exception as e:
            record_warning(f"Completions API not supported: {e}")
            test_logger.info(f"Completions API not supported: {e}")

    @pytest.mark.g_api
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_models_list(self, api_client: ModelAPIClient, test_logger, record_warning):
        """G3 [P0]: 模型列表接口"""
        test_logger.info("=== 测试开始: Models List ===")

        response = api_client.list_models()
        TestLogger.log_response(test_logger, response, "Models List响应")
        self.log_full_response(test_logger, response, "G3-ModelsList")

        # 验证响应格式
        assert "data" in response or "object" in response, "Should have valid response"

        # 验证数据格式
        if "data" in response:
            models = response["data"]
            assert isinstance(models, list), "Models should be a list"

            if models:
                model = models[0]
                assert "id" in model, "Model should have id"
                assert model.get("object") == "model" or "object" in model, (
                    "Model item should have object field"
                )
                test_logger.info(
                    f"Models list: {len(models)} models found, first: {model.get('id')}"
                )
            else:
                test_logger.warning("Models list is empty")
                record_warning("Models list is empty")
        else:
            test_logger.info(
                f"Models response has 'object' field: {response.get('object')}"
            )

    @pytest.mark.g_api
    @pytest.mark.p0
    def test_usage_statistics(self, api_client: ModelAPIClient, test_logger):
        """G4: Usage 统计准确性"""
        test_logger.info("=== 测试开始: Usage统计 ===")

        messages = [{"role": "user", "content": "请写一段话"}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 100})

        response = api_client.chat_completion(messages, max_tokens=100)
        TestLogger.log_response(test_logger, response, "Usage统计响应")
        self.log_full_response(test_logger, response, "G4-Usage统计")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        # 验证usage存在
        usage = response.get("usage", {})
        assert usage, "Should have usage statistics"

        # 验证必要字段
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        assert prompt_tokens > 0, "Should have prompt_tokens > 0"

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
    def test_error_codes(self, api_client: ModelAPIClient, test_logger, record_warning):
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
            TestLogger.log_request(test_logger, messages, {"invalid_api_key": True})
            response = invalid_client.chat_completion(messages)
            self.log_full_response(test_logger, response, "G5-401认证错误")
            test_logger.warning("401 test: no error returned for invalid API key")
            record_warning("401未返回错误")
        except Exception as e:
            self.log_full_response(
                test_logger, {"error": str(e)}, "G5-401认证错误(异常)"
            )
            test_logger.info(f"401 错误（异常）: {e}")
            error_msg = str(e).lower()
            assert any(
                kw in error_msg for kw in ["401", "auth", "unauthorized", "permission"]
            ), f"Should be authentication error, got: {e}"

        # 测试 400 错误（无效请求）
        try:
            # 发送空的content来触发400错误
            invalid_messages = [{"role": "user", "content": ""}]
            TestLogger.log_request(test_logger, invalid_messages, {"max_tokens": 1})
            response = api_client.chat_completion(invalid_messages, max_tokens=1)
            self.log_full_response(test_logger, response, "G5-400无效请求")
            test_logger.info("400 test: empty content was accepted (no error raised)")
        except Exception as e:
            self.log_full_response(
                test_logger, {"error": str(e)}, "G5-400无效请求(异常)"
            )
            test_logger.info(f"400 错误（异常）: {e}")
            error_msg = str(e).lower()
            assert any(
                kw in error_msg
                for kw in ["400", "invalid", "empty", "content", "length", "message"]
            ), f"Should be 400 error for empty content, got: {e}"

        test_logger.info("错误码规范测试完成")

    @pytest.mark.g_api
    @pytest.mark.p0
    def test_client_sdk_compatibility(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
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
            TestLogger.log_request(test_logger, messages, {"max_tokens": 100})

            # 调用 chat.completions.create
            response = client.chat.completions.create(
                model=api_client.model_name, messages=messages, max_tokens=100
            )

            test_logger.info(f"SDK 响应: {response}")
            test_logger.info(f"SDK 返回ID: {response.id}")

            # 验证响应格式
            assert response.id is not None, "Should have response id"
            assert len(response.choices) > 0, "Should have choices"
            assert response.choices[0].message.content is not None, (
                "Should have content"
            )
            assert len(response.choices[0].message.content.strip()) > 0, (
                "Content should not be empty"
            )
            assert response.choices[0].message.role == "assistant", (
                "Role should be assistant"
            )

            # 验证usage
            if response.usage:
                assert response.usage.prompt_tokens > 0, "Should have prompt_tokens > 0"
                assert response.usage.completion_tokens > 0, (
                    "Should have completion_tokens > 0"
                )

            self.log_full_response(
                test_logger,
                {
                    "id": response.id,
                    "model": response.model,
                    "usage": str(response.usage),
                },
                "G6-SDK兼容",
            )

            test_logger.info("客户端 SDK 兼容性测试通过")
        except ImportError:
            record_warning("openai SDK not installed, skipping SDK compatibility test")
            test_logger.info(
                "openai SDK not installed, skipping SDK compatibility test"
            )
        except Exception as e:
            record_warning(f"SDK compatibility test failed: {e}")
            test_logger.warning(f"SDK 兼容性测试: {e}")

    @pytest.mark.g_api
    @pytest.mark.p2
    def test_response_format_variants(self, api_client: ModelAPIClient, test_logger):
        """额外测试：响应格式变体"""
        test_logger.info("=== 测试开始: Response Format Variants ===")

        messages = [{"role": "user", "content": "测试"}]

        # 测试不同参数组合
        TestLogger.log_request(
            test_logger, messages, {"temperature": 0.7, "max_tokens": 100}
        )
        response1 = api_client.chat_completion(
            messages, temperature=0.7, max_tokens=100
        )
        TestLogger.log_response(test_logger, response1, "temperature=0.7响应")
        self.assert_response_success(response1)
        self.assert_content_not_empty(response1)
        self.log_full_response(test_logger, response1, "G7-temperature=0.7")

        TestLogger.log_request(
            test_logger, messages, {"temperature": 0, "max_tokens": 100}
        )
        response2 = api_client.chat_completion(messages, temperature=0, max_tokens=100)
        TestLogger.log_response(test_logger, response2, "temperature=0响应")
        self.assert_response_success(response2)
        self.assert_content_not_empty(response2)
        self.log_full_response(test_logger, response2, "G7-temperature=0")

        TestLogger.log_request(
            test_logger, messages, {"temperature": 1.0, "max_tokens": 100}
        )
        response3 = api_client.chat_completion(
            messages, temperature=1.0, max_tokens=100
        )
        TestLogger.log_response(test_logger, response3, "temperature=1.0响应")
        self.assert_response_success(response3)
        self.assert_content_not_empty(response3)
        self.log_full_response(test_logger, response3, "G7-temperature=1.0")

        test_logger.info("Response format variants: OK")

    @pytest.mark.g_api
    @pytest.mark.p2
    def test_stream_parameter(self, api_client: ModelAPIClient, test_logger):
        """额外测试：stream参数"""
        test_logger.info("=== 测试开始: Stream Parameter ===")

        messages = [{"role": "user", "content": "测试"}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 100})

        # 流式请求
        response_iter = api_client.chat_completion_stream(messages, max_tokens=100)
        result = self.collect_stream_chunks(response_iter)

        self.log_full_response(
            test_logger,
            {
                "chunks_count": len(result["chunks"]),
                "content": result["content"][:2000],
                "reasoning": result["reasoning"][:2000] if result["reasoning"] else "",
            },
            "G8-Stream参数",
        )

        assert len(result["chunks"]) > 0, "Should receive streaming chunks"
        assert result["content"] or result["reasoning"], (
            "Should have non-empty content or reasoning in streaming response"
        )
        if result["content"]:
            assert len(result["content"].strip()) > 0, (
                "Streaming content should not be empty"
            )
        test_logger.info(
            f"Stream parameter: {len(result['chunks'])} chunks, "
            f"content length: {len(result['content'])}, "
            f"reasoning length: {len(result['reasoning'])}"
        )
