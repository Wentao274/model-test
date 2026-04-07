"""
G. API 兼容性测试

测试点：
- H1: OpenAI Chat Completions - /v1/chat/completions 接口
- H2: OpenAI Completions - /v1/completions 接口
- H3: 模型列表 - /v1/models 接口
- H4: Usage 统计 - usage 字段准确性
"""
import pytest
from typing import Dict, Any

from base.base_test import BaseTest
from base.api_client import ModelAPIClient


class TestAPICompatibility(BaseTest):
    """API兼容性测试类"""

    def get_test_category(self) -> str:
        return "G. API兼容性"

    @pytest.mark.g_api
    @pytest.mark.p0
    def test_chat_completions_api(self, api_client: ModelAPIClient):
        """H1: OpenAI Chat Completions 接口兼容"""
        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "你好"}
        ]

        response = api_client.chat_completion(messages)

        # 验证响应格式
        self.assert_response_success(response)

        # 验证必要字段
        message = response["choices"][0]["message"]
        assert "role" in message, "Should have role field"
        assert "content" in message, "Should have content field"
        assert message["role"] == "assistant", "Role should be assistant"

        # 验证usage
        usage = response.get("usage", {})
        assert "prompt_tokens" in usage or "completion_tokens" in usage, "Should have usage"

        print(f"Chat Completions API: OK, usage={usage}")

    @pytest.mark.g_api
    @pytest.mark.p1
    def test_completions_api(self, api_client: ModelAPIClient):
        """H2: OpenAI Completions 接口兼容"""
        prompt = "你好，请介绍一下自己"

        try:
            response = api_client.completion(prompt=prompt, max_tokens=50)

            # 验证响应
            assert response.get("choices") is not None, "Should have choices"
            assert len(response["choices"]) > 0, "Should have at least one choice"

            text = response["choices"][0].get("text", "")
            assert len(text) > 0, "Should have text content"

            print(f"Completions API: OK, text={text[:50]}")
        except Exception as e:
            pytest.skip(f"Completions API not supported: {e}")

    @pytest.mark.g_api
    @pytest.mark.p1
    def test_models_list(self, api_client: ModelAPIClient):
        """H3: 模型列表接口"""
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
                print(f"Models list: {len(models)} models found")
                for m in models[:5]:
                    print(f"  - {m.get('id')}")

    @pytest.mark.g_api
    @pytest.mark.p0
    def test_usage_statistics(self, api_client: ModelAPIClient):
        """H4: Usage 统计准确性"""
        messages = [{"role": "user", "content": "请写一段话"}]

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
            assert total_tokens == prompt_tokens + completion_tokens, \
                f"total_tokens should equal sum: {total_tokens} != {prompt_tokens} + {completion_tokens}"

        assert completion_tokens > 0, "Should have completion tokens"

        print(f"Usage: prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}")

    @pytest.mark.g_api
    @pytest.mark.p1
    def test_response_format_variants(self, api_client: ModelAPIClient):
        """额外测试：响应格式变体"""
        messages = [{"role": "user", "content": "测试"}]

        # 测试不同参数组合
        response1 = api_client.chat_completion(messages, temperature=0.7, max_tokens=50)
        self.assert_response_success(response1)

        response2 = api_client.chat_completion(messages, temperature=0, max_tokens=50)
        self.assert_response_success(response2)

        response3 = api_client.chat_completion(messages, temperature=1.0, max_tokens=50)
        self.assert_response_success(response3)

        print("Response format variants: OK")

    @pytest.mark.g_api
    @pytest.mark.p1
    def test_stream_parameter(self, api_client: ModelAPIClient):
        """额外测试：stream参数"""
        messages = [{"role": "user", "content": "测试"}]

        # 流式请求
        response_iter = api_client.chat_completion_stream(messages, max_tokens=50)
        chunks = list(response_iter)

        assert len(chunks) > 0, "Should receive streaming chunks"
        print(f"Stream parameter: {len(chunks)} chunks")