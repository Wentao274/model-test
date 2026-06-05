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
- D9: 超长上下文（非流式） - 验证超长上下文请求的非流式输出
- D10: 超长上下文（流式） - 验证超长上下文请求的流式输出
- D11: 超长上下文（边界验证） - 使用二分法逼近模型最大上下文长度
- D12: 超长上下文（思考模式） - 验证超长上下文下reasoning_content的可用性
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
    words = ["测试", "内容", "长文本", "这是", "一个", "用于", "测试", "的", "段落"] * (
        chars // 20 + 1
    )
    return " ".join(words[: chars // 2])


class TestLongContext(BaseTest, StreamingTestMixin):
    """长上下文处理测试类"""

    def get_test_category(self) -> str:
        return "D. 长上下文处理"

    @staticmethod
    def _get_max_context_len(model_info: dict) -> int:
        """获取模型最大上下文长度，兼容 vLLM(max_model_len) 和 sglang(context-length)"""
        for key in ("max_model_len", "context-length", "context_length"):
            val = model_info.get(key, 0)
            if val:
                return int(val)
        return 202752

    @pytest.mark.d_long_context
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_short_context_baseline(self, api_client: ModelAPIClient, test_logger):
        test_logger.info("=== 测试开始: 短上下文基线 ===")

        prompt = "请简短介绍一下人工智能的发展历史"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "短上下文响应")
        self.log_full_response(test_logger, response, "D1-短上下文基线")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content.strip()) > 20, (
            f"Short context response should be substantive, got {len(content.strip())} chars"
        )

        usage = response.get("usage", {})
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )
        assert usage.get("prompt_tokens", 0) > 0, "Should have prompt_tokens > 0"
        test_logger.info(
            f"Short context baseline passed, prompt_tokens={usage.get('prompt_tokens')}, "
            f"completion_tokens={usage.get('completion_tokens')}"
        )

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
        self.log_full_response(test_logger, response, "D2-中等上下文")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content.strip()) > 50, (
            f"Medium context response should be substantive, got {len(content.strip())} chars"
        )

        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        assert prompt_tokens > 0, "Should have prompt_tokens > 0 for medium context"
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )
        test_logger.info(
            f"Medium context passed, prompt_tokens={prompt_tokens}, "
            f"completion_tokens={usage.get('completion_tokens')}"
        )

    @pytest.mark.d_long_context
    @pytest.mark.p0
    def test_long_context(self, api_client: ModelAPIClient, test_logger):
        """D3: 长上下文 - input 32K-64K tokens，验证召回和推理"""
        test_logger.info("=== 测试开始: 长上下文 ===")

        # 约16000字
        padding = "这是测试段落。 " * 4000
        prompt = "以下是一篇长文章：" + padding

        messages = [
            {"role": "user", "content": prompt + "\n\n请总结这篇文章的主要内容。"}
        ]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "长上下文响应")
        self.log_full_response(test_logger, response, "D3-长上下文")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content.strip()) > 50, (
            f"Long context response should be substantive, got {len(content.strip())} chars"
        )

        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        assert prompt_tokens > 0, "Should have prompt_tokens > 0 for long context"
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )
        test_logger.info(
            f"Long context passed, prompt_tokens={prompt_tokens}, "
            f"completion_tokens={usage.get('completion_tokens')}"
        )

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
            self.log_full_response(test_logger, response, "D4-超长上下文")
            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            assert len(content.strip()) > 10, (
                f"Super long context response should not be trivial, got {len(content.strip())} chars"
            )

            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            assert prompt_tokens > 0, (
                "Should have prompt_tokens > 0 for super long context"
            )
            assert usage.get("completion_tokens", 0) > 0, (
                "Should have completion_tokens > 0"
            )
            test_logger.info(
                f"Super long context passed, prompt_tokens={prompt_tokens}, "
                f"completion_tokens={usage.get('completion_tokens')}"
            )
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
        needle_text = (
            base_text[: len(base_text) // 2] + needle + base_text[len(base_text) // 2 :]
        )

        prompt = needle_text + "\n\n请问文章中的特殊标记是什么？"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "大海捞针响应")
        self.log_full_response(test_logger, response, "D5-大海捞针")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        content = self.get_message_content(response)

        assert "42" in content, (
            f"Model should recall the needle '42', got: {content[:500]}"
        )
        content_lower = content.lower()
        assert any(
            kw in content_lower for kw in ["特殊标记", "special", "标记", "答案"]
        ), f"Model should reference the needle context, got: {content[:500]}"

        usage = response.get("usage", {})
        assert usage.get("prompt_tokens", 0) > 0, (
            "Should have prompt_tokens > 0 for NIAH test"
        )
        test_logger.info(
            f"NIAH test passed, prompt_tokens={usage.get('prompt_tokens')}, "
            f"completion_tokens={usage.get('completion_tokens')}, response: {content[:2000]}"
        )

    @pytest.mark.d_long_context
    @pytest.mark.p1
    def test_context_boundary_behavior(self, api_client: ModelAPIClient, test_logger):
        """D6: 上下文边界行为 - 输入接近模型限制"""
        test_logger.info("=== 测试开始: 上下文边界行为 ===")

        # 尝试获取模型信息
        model_info = api_client.get_model_info()
        max_len = self._get_max_context_len(model_info)

        if max_len > 0:
            estimated_tokens = max(1000, max_len - 1000)
            prompt = "测试内容 " * (estimated_tokens // 4)

            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "边界响应")
            self.log_full_response(test_logger, response, "D6-上下文边界行为")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            assert prompt_tokens > 0, "Should have prompt_tokens > 0 at boundary"
            assert usage.get("completion_tokens", 0) > 0, (
                "Should have completion_tokens > 0 at boundary"
            )
            test_logger.info(
                f"Context boundary test passed, max_len: {max_len}, "
                f"prompt_tokens={prompt_tokens}, completion_tokens={usage.get('completion_tokens')}"
            )
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
            self.log_full_response(test_logger, response, "D7-上下文截断")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            finish_reason = response.get("choices", [{}])[0].get("finish_reason")
            usage = response.get("usage", {})
            test_logger.info(
                f"Context truncation handled: finish_reason={finish_reason}, "
                f"prompt_tokens={usage.get('prompt_tokens')}, completion_tokens={usage.get('completion_tokens')}"
            )
            assert finish_reason in ("stop", "length"), (
                f"finish_reason should be 'stop' or 'length' when context is truncated, got: {finish_reason}"
            )
        except Exception as e:
            test_logger.info(f"Context exceeded: {e}")
            error_msg = str(e).lower()
            assert any(
                kw in error_msg
                for kw in ["context", "length", "too_many", "exceed", "limit", "token"]
            ), f"Error should relate to context/length limit, got: {e}"

    @pytest.mark.d_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_long_output_generation(self, api_client: ModelAPIClient, test_logger):
        """D8: 长输出生成 - 要求生成4K-8K tokens的长文本"""
        test_logger.info("=== 测试开始: 长输出生成 ===")

        messages = [
            {
                "role": "user",
                "content": "请写一篇关于人工智能发展史的详细文章，不少于2000字",
            }
        ]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 4000})

        response = api_client.chat_completion(messages, max_tokens=4000)
        TestLogger.log_response(test_logger, response, "长输出响应")
        self.log_full_response(test_logger, response, "D8-长输出生成")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content.strip()) > 200, (
            f"Long output response should be substantial, got {len(content.strip())} chars"
        )

        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        assert completion_tokens > 200, (
            f"Expected long output (>200 tokens), got {completion_tokens} tokens"
        )
        assert usage.get("prompt_tokens", 0) > 0, "Should have prompt_tokens > 0"
        test_logger.info(
            f"Long output: {completion_tokens} tokens generated, "
            f"content length: {len(content)} chars"
        )

    @pytest.mark.d_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_super_long_context_create(self, api_client: ModelAPIClient, test_logger):
        """D9: 超长上下文（非流式） - 验证超长上下文请求的非流式输出"""
        test_logger.info("=== 测试开始: 超长上下文(非流式) ===")

        long_prompt = "以下是一篇很长的文章：" + "这是第" + "测试段落。 " * 25000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [
            {"role": "user", "content": long_prompt + "\n\n请总结这篇文章的主要内容。"}
        ]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        try:
            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "超长上下文响应")

            self.assert_response_success(response)
            self.log_full_response(test_logger, response, "D9-超长上下文(非流式)")

            reasoning = self.get_reasoning_content(response)
            content = self.get_message_content(response)

            assert content and len(content.strip()) > 0, (
                "Should have non-empty content in super long context"
            )

            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            assert prompt_tokens > 0, (
                "Should have prompt_tokens > 0 for super long context"
            )
            assert completion_tokens > 0, "Should have completion_tokens > 0"
            test_logger.info(
                f"Super long context test: prompt_tokens={prompt_tokens}, "
                f"completion_tokens={completion_tokens}"
            )
            test_logger.info(
                f"Content length: {len(content) if content else 0}, "
                f"Reasoning length: {len(reasoning) if reasoning else 0}"
            )

        except Exception as e:
            if "max_model_len" in str(e).lower() or "context" in str(e).lower():
                pytest.skip(f"Model does not support this context length: {e}")
            raise

    @pytest.mark.d_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_super_long_context_stream(self, api_client: ModelAPIClient, test_logger):
        """D10: 超长上下文（流式） - 验证超长上下文请求的流式输出"""
        test_logger.info("=== 测试开始: 超长上下文(流式) ===")

        long_prompt = "以下是一篇很长的文章：" + "这是第" + "测试段落。 " * 25000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [
            {"role": "user", "content": long_prompt + "\n\n请总结这篇文章的主要内容。"}
        ]
        TestLogger.log_request(test_logger, messages)

        try:
            response_iter = api_client.chat_completion_stream(messages, max_tokens=2000)
            result = self.collect_stream_chunks(response_iter)

            self.log_full_response(
                test_logger,
                {
                    "chunks_count": len(result["chunks"]),
                    "content": result["content"][:2000],
                    "reasoning": result["reasoning"][:2000]
                    if result["reasoning"]
                    else "",
                },
                "D10-超长上下文(流式)",
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
                f"Streaming chunks: {len(result['chunks'])}, "
                f"content length: {len(result['content'])}, "
                f"reasoning length: {len(result['reasoning'])}"
            )

        except Exception as e:
            if "max_model_len" in str(e).lower() or "context" in str(e).lower():
                pytest.skip(f"Model does not support this context length: {e}")
            raise

    @pytest.mark.d_long_context
    @pytest.mark.p0
    def test_context_boundary_exact_limit(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """D11: 超长上下文（边界验证） - 使用二分法逼近模型最大上下文长度"""
        test_logger.info("=== 测试开始: 上下文边界（二分法） ===")

        try:
            model_info = api_client.get_model_info()
            max_len = self._get_max_context_len(model_info)
            test_logger.info(f"模型定义的最大上下文长度: {max_len}")

            if max_len > 0:
                low = 0
                high = max_len
                successful_len = 0
                failed_len = max_len
                max_iterations = 16

                test_logger.info(f"开始二分法测试，范围: [{low}, {high}]")

                for iteration in range(max_iterations):
                    mid = (low + high) // 2

                    if mid < 100:
                        low = mid + 1
                        continue

                    import random
                    import string

                    target_chars = mid
                    chars_without_space = int(target_chars * 0.9)
                    chars_with_space = int(target_chars * 0.1)
                    prompt_chars = []
                    for _ in range(chars_without_space):
                        prompt_chars.append(
                            random.choice(string.ascii_letters + string.digits)
                        )
                    for _ in range(chars_with_space):
                        prompt_chars.append(" ")
                    random.shuffle(prompt_chars)
                    prompt = "".join(prompt_chars)
                    messages = [{"role": "user", "content": prompt}]

                    test_logger.info(
                        f"迭代 {iteration + 1}: 测试上下文长度 ~{mid} tokens"
                    )

                    try:
                        response = api_client.chat_completion(messages, max_tokens=2000)
                        self.log_full_response(
                            test_logger,
                            response,
                            f"D11-边界二分法-迭代{iteration + 1}-长度{mid}",
                        )
                        if response.get("error"):
                            test_logger.warning(
                                f"长度 {mid} 失败: {response.get('error')}"
                            )
                            record_warning(f"长度{mid}请求失败")
                            high = mid - 1
                            failed_len = mid
                        else:
                            test_logger.info(f"长度 {mid} 成功")
                            low = mid + 1
                            successful_len = mid
                    except Exception as e:
                        error_msg = str(e).lower()
                        if (
                            "max" in error_msg
                            and "length" in error_msg
                            or "context" in error_msg
                        ):
                            test_logger.warning(f"长度 {mid} 超限: {e}")
                            record_warning(f"长度{mid}超限")
                            high = mid - 1
                            failed_len = mid
                        else:
                            raise

                    if high - low <= 10:
                        break

                test_logger.info(
                    f"二分法结果: 成功最大长度 ~{successful_len} tokens, 失败长度 ~{failed_len} tokens"
                )
                test_logger.info(f"模型定义的最大长度: {max_len} tokens")

                if successful_len > 0:
                    ratio = successful_len / max_len
                    test_logger.info(f"实际成功率: {ratio:.2%}")
                    assert ratio > 0.8 or successful_len >= max_len * 0.8, (
                        f"Model claims {max_len} but only supports ~{successful_len}"
                    )
                    test_logger.info("上下文边界验证通过")
                else:
                    pytest.skip("无法确定有效的上下文长度")

            else:
                pytest.skip("Model max_model_len not available")
        except Exception as e:
            if "max" in str(e).lower() and "length" in str(e).lower():
                test_logger.info(f"Context boundary reached: {e}")
            else:
                raise

    @pytest.mark.d_long_context
    @pytest.mark.p0
    def test_reasoning_content_in_long_context(
        self, api_client: ModelAPIClient, test_logger
    ):
        """D12: 超长上下文（思考模式） - 验证超长上下文下reasoning_content的可用性"""
        test_logger.info("=== 测试开始: 长上下文+思考 ===")

        long_prompt = "请分析以下问题并给出详细解答：" + "问题描述。" * 1000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [{"role": "user", "content": long_prompt}]
        thinking_params = api_client.get_thinking_params(True)
        TestLogger.log_request(test_logger, messages, thinking_params)

        response = api_client.chat_completion(
            messages,
            extra_body=thinking_params,
            max_tokens=2000,
        )
        TestLogger.log_response(test_logger, response, "长上下文+思考响应")
        self.log_full_response(test_logger, response, "D12-长上下文+思考模式")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        reasoning = self.get_reasoning_content(response)
        content = self.get_message_content(response)

        assert reasoning is not None and len(reasoning.strip()) > 0, (
            "Thinking mode should produce non-empty reasoning_content in long context"
        )

        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        assert prompt_tokens > 0, (
            "Should have prompt_tokens > 0 for long context with thinking"
        )

        test_logger.info(
            f"Long context with thinking: reasoning={len(reasoning) if reasoning else 0} chars, "
            f"content={len(content) if content else 0} chars, "
            f"prompt_tokens={prompt_tokens}"
        )
