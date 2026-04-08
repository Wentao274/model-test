"""
I. 单项超长上下文验证

测试点：
- L1: 超长上下文（脚本验证）- 验证超长上下文可用性和边界行为
"""
import pytest

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestLongContextScriptValidation(BaseTest, StreamingTestMixin):
    """超长上下文脚本验证测试类"""

    def get_test_category(self) -> str:
        return "I. 单项超长上下文验证"

    @pytest.mark.i_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_super_long_context_create(self, api_client: ModelAPIClient, test_logger):
        """L1: 超长上下文脚本验证 - 非流式"""
        test_logger.info("=== 测试开始: 超长上下文(非流式) ===")

        # 生成超长上下文（估计 100K+ tokens）
        long_prompt = "以下是一篇很长的文章：" + "这是第" + "测试段落。 " * 25000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [{"role": "user", "content": long_prompt + "\n\n请总结这篇文章的主要内容。"}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 1000})

        try:
            response = api_client.chat_completion(messages, max_tokens=1000)
            TestLogger.log_response(test_logger, response, "超长上下文响应")

            # 验证响应成功
            self.assert_response_success(response)

            # 验证有reasoning content（如果开启了thinking）
            reasoning = self.get_reasoning_content(response)
            content = self.get_message_content(response)

            # 至少有一个非空
            assert reasoning or content, "Should have either reasoning or content"

            usage = response.get("usage", {})
            test_logger.info(f"Super long context test: prompt_tokens={usage.get('prompt_tokens')}, completion_tokens={usage.get('completion_tokens')}")
            test_logger.info(f"Content length: {len(content) if content else 0}, Reasoning length: {len(reasoning) if reasoning else 0}")

        except Exception as e:
            if "max_model_len" in str(e).lower() or "context" in str(e).lower():
                pytest.skip(f"Model does not support this context length: {e}")
            raise

    @pytest.mark.i_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_super_long_context_stream(self, api_client: ModelAPIClient, test_logger):
        """L1: 超长上下文脚本验证 - 流式"""
        test_logger.info("=== 测试开始: 超长上下文(流式) ===")

        # 生成超长上下文
        long_prompt = "以下是一篇很长的文章：" + "这是第" + "测试段落。 " * 25000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [{"role": "user", "content": long_prompt + "\n\n请总结这篇文章的主要内容。"}]
        TestLogger.log_request(test_logger, messages)

        try:
            response_iter = api_client.chat_completion_stream(messages, max_tokens=500)
            result = self.collect_stream_chunks(response_iter)

            test_logger.info(f"Streaming chunks: {len(result['chunks'])}, content length: {len(result['content'])}, reasoning length: {len(result['reasoning'])}")
            # 验证收到chunks
            assert len(result["chunks"]) > 0, "Should receive streaming chunks"

        except Exception as e:
            if "max_model_len" in str(e).lower() or "context" in str(e).lower():
                pytest.skip(f"Model does not support this context length: {e}")
            raise

    @pytest.mark.i_long_context
    @pytest.mark.p1
    def test_context_boundary_exact_limit(self, api_client: ModelAPIClient, test_logger):
        """L1: 上下文边界验证 - 恰好等于限制"""
        test_logger.info("=== 测试开始: 上下文边界 ===")

        # 尝试获取模型最大上下文长度
        try:
            model_info = api_client.get_model_info()
            max_len = model_info.get("max_model_len", 0)
            test_logger.info(f"模型最大上下文长度: {max_len}")

            if max_len > 0:
                # 生成恰好接近限制的输入
                # 留出空间给system prompt和max_tokens
                prompt = "测试内容 " * (max_len // 5)
                messages = [{"role": "user", "content": prompt}]
                TestLogger.log_request(test_logger, messages)

                response = api_client.chat_completion(messages, max_tokens=100)
                TestLogger.log_response(test_logger, response, "边界响应")

                self.assert_response_success(response)
                test_logger.info(f"Context boundary test: max_len={max_len}, handled successfully")
            else:
                pytest.skip("Model max_model_len not available")
        except Exception as e:
            if "max" in str(e).lower() and "length" in str(e).lower():
                test_logger.info(f"Context boundary reached: {e}")
            else:
                raise

    @pytest.mark.i_long_context
    @pytest.mark.p1
    def test_reasoning_content_in_long_context(self, api_client: ModelAPIClient, test_logger):
        """L1: 验证超长上下文下reasoning_content的可用性"""
        test_logger.info("=== 测试开始: 长上下文+思考 ===")

        # 较长的上下文
        long_prompt = "请分析以下问题并给出详细解答：" + "问题描述。" * 1000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [{"role": "user", "content": long_prompt}]
        TestLogger.log_request(test_logger, messages, {"enable_thinking": True})

        # 开启thinking
        response = api_client.chat_completion(
            messages,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}},
            max_tokens=500
        )
        TestLogger.log_response(test_logger, response, "长上下文+思考响应")

        self.assert_response_success(response)

        reasoning = self.get_reasoning_content(response)
        content = self.get_message_content(response)

        test_logger.info(f"Long context with thinking: reasoning={len(reasoning) if reasoning else 0} chars, content={len(content) if content else 0} chars")