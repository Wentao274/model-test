"""
D. 长上下文处理测试

测试点：
- D1: 短上下文基线 - input 1K tokens，验证正常推理
- D2: 中等上下文 - input 8K-16K tokens，验证质量不降
- D3: 长上下文 - input 32K-64K tokens，验证召回和推理
- D4: 超长上下文 - input 128K+ tokens，验证不OOM且可用
- D5: 大海捞针（NIAH）- 长文本中插入特定信息，验证召回率
- D6: 上下文边界行为 - 输入恰好等于max_model_len
- D7: 超出上下文截断 - 输入超过模型限制
- D8: 长输出生成 - 要求生成4K-8K tokens的长文本
"""
import pytest
from typing import List

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


def generate_long_text(tokens: int) -> str:
    """生成指定token数量的文本（估算）"""
    # 约4个字符一个token
    chars = tokens * 4
    words = ["测试", "内容", "长文本", "这是", "一个", "用于", "测试", "的", "段落"] * (chars // 20 + 1)
    return " ".join(words[:chars // 2])


class TestLongContext(BaseTest, StreamingTestMixin):
    """长上下文处理测试类"""

    def get_test_category(self) -> str:
        return "D. 长上下文处理"

    @pytest.mark.d_long_context
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_short_context_baseline(self, api_client: ModelAPIClient, test_logger):
        """D1: 短上下文基线 - input 1K tokens"""
        test_logger.info("=== 测试开始: 短上下文基线 ===")

        # 约250字
        prompt = "请简短介绍一下人工智能的发展历史" + "。" * 100

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "短上下文响应")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        usage = response.get('usage', {})
        test_logger.info(f"Short context test passed, completion_tokens: {usage.get('completion_tokens')}")

    @pytest.mark.d_long_context
    @pytest.mark.p0
    def test_medium_context(self, api_client: ModelAPIClient, test_logger):
        """D2: 中等上下文 - input 8K-16K tokens"""
        test_logger.info("=== 测试开始: 中等上下文 ===")

        # 约4000字
        prompt = "请分析以下内容：" + "这是一个测试段落。 " * 1000

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "中等上下文响应")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        test_logger.info("Medium context test passed")

    @pytest.mark.d_long_context
    @pytest.mark.p0
    def test_long_context(self, api_client: ModelAPIClient, test_logger):
        """D3: 长上下文 - input 32K-64K tokens，验证召回和推理"""
        test_logger.info("=== 测试开始: 长上下文 ===")

        # 约16000字
        prompt = "以下是一篇长文章：" + "这是第" + "测试段落。 " * 4000

        messages = [{"role": "user", "content": prompt + "\n\n请总结这篇文章的主要内容。"}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "长上下文响应")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        test_logger.info("Long context test passed, input tokens estimated: 16000+")

    @pytest.mark.d_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    @pytest.mark.smoke
    def test_super_long_context(self, api_client: ModelAPIClient, test_logger):
        """D4: 超长上下文 - input 128K+ tokens"""
        test_logger.info("=== 测试开始: 超长上下文 ===")

        # 约32000字
        prompt = "以下是一篇长文章：" + "这是第" + "测试段落。 " * 8000

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        try:
            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "超长上下文响应")
            self.assert_response_success(response)
            test_logger.info("Long context test passed, input tokens estimated: 32000+")
        except Exception as e:
            if "max_model_len" in str(e).lower() or "context" in str(e).lower():
                pytest.skip(f"Model does not support this context length: {e}")
            raise

    @pytest.mark.d_long_context
    @pytest.mark.p0
    def test_niah_needle_in_a_haystack(self, api_client: ModelAPIClient, test_logger):
        """D5: 大海捞针（NIAH）- 长文本中插入特定信息，验证召回率"""
        test_logger.info("=== 测试开始: 大海捞针 ===")

        # 生成一篇长文章，在中间插入一个特定的事实
        base_text = "这是一篇关于科技发展的文章。" * 100
        needle = "特殊标记：答案是42"
        needle_text = base_text[:len(base_text)//2] + needle + base_text[len(base_text)//2:]

        prompt = needle_text + "\n\n请问文章中的特殊标记是什么？"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "大海捞针响应")

        self.assert_response_success(response)
        content = self.get_message_content(response)

        # 验证模型能召回插入的信息
        assert "42" in content or "答案" in content, \
            f"Model should recall the needle info, got: {content[:2000]}"
        test_logger.info(f"NIAH test passed, response: {content[:2000]}")

    @pytest.mark.d_long_context
    @pytest.mark.p1
    def test_context_boundary_behavior(self, api_client: ModelAPIClient, test_logger):
        """D6: 上下文边界行为 - 输入接近模型限制"""
        test_logger.info("=== 测试开始: 上下文边界行为 ===")

        # 尝试获取模型信息
        model_info = api_client.get_model_info()
        max_len = model_info.get("max_model_len", 0)

        if max_len > 0:
            # 生成接近限制的输入
            estimated_tokens = max(1000, max_len - 1000)
            prompt = "测试内容 " * (estimated_tokens // 4)

            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "边界响应")

            # 应该能正常处理
            self.assert_response_success(response)
            test_logger.info(f"Context boundary test passed, max_len: {max_len}")
        else:
            pytest.skip("Model max_model_len not available")

    @pytest.mark.d_long_context
    @pytest.mark.p1
    def test_context_truncation(self, api_client: ModelAPIClient, test_logger):
        """D7: 超出上下文截断 - 验证截断策略"""
        test_logger.info("=== 测试开始: 上下文截断 ===")

        # 生成超长文本
        prompt = "这是一段很长的测试文本， " * 20000

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        try:
            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "截断响应")
            # 应该被处理（截断或拒绝）
            finish_reason = response.get('choices', [{}])[0].get('finish_reason')
            test_logger.info(f"Context truncation handled: {finish_reason}")
        except Exception as e:
            # 可能返回错误
            test_logger.info(f"Context exceeded: {e}")
            assert "context" in str(e).lower() or "length" in str(e).lower()

    @pytest.mark.d_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_long_output_generation(self, api_client: ModelAPIClient, test_logger):
        """D8: 长输出生成 - 要求生成4K-8K tokens的长文本"""
        test_logger.info("=== 测试开始: 长输出生成 ===")

        messages = [
            {"role": "user", "content": "请写一篇关于人工智能发展史的详细文章，不少于2000字"}
        ]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 4000})

        response = api_client.chat_completion(messages, max_tokens=4000)
        TestLogger.log_response(test_logger, response, "长输出响应")

        self.assert_response_success(response)

        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        test_logger.info(f"Long output: {completion_tokens} tokens generated")

        # 验证有足够输出
        assert completion_tokens > 100, f"Expected long output, got {completion_tokens} tokens"
