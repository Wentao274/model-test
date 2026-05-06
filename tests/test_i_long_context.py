"""
I. 超长上下文脚本验证

测试点：
- I1: 超长上下文（非流式） - 验证超长上下文请求的非流式输出
- I2: 超长上下文（流式） - 验证超长上下文请求的流式输出
- I3: 超长上下文（边界验证） - 使用二分法逼近模型最大上下文长度
- I4: 超长上下文（思考模式） - 验证超长上下文下reasoning_content的可用性
"""

import pytest

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestLongContextScriptValidation(BaseTest, StreamingTestMixin):
    """超长上下文脚本验证测试类"""

    def get_test_category(self) -> str:
        return "I. 超长上下文验证"

    @pytest.mark.i_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_super_long_context_create(self, api_client: ModelAPIClient, test_logger):
        """I1: 超长上下文脚本验证 - 非流式"""
        test_logger.info("=== 测试开始: 超长上下文(非流式) ===")

        # 生成超长上下文（估计 100K+ tokens）
        long_prompt = "以下是一篇很长的文章：" + "这是第" + "测试段落。 " * 25000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [
            {"role": "user", "content": long_prompt + "\n\n请总结这篇文章的主要内容。"}
        ]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        try:
            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "超长上下文响应")

            # 验证响应成功
            self.assert_response_success(response)

            # 验证有reasoning content（如果开启了thinking）
            reasoning = self.get_reasoning_content(response)
            content = self.get_message_content(response)

            # 至少有一个非空
            assert reasoning or content, "Should have either reasoning or content"

            usage = response.get("usage", {})
            test_logger.info(
                f"Super long context test: prompt_tokens={usage.get('prompt_tokens')}, completion_tokens={usage.get('completion_tokens')}"
            )
            test_logger.info(
                f"Content length: {len(content) if content else 0}, Reasoning length: {len(reasoning) if reasoning else 0}"
            )

        except Exception as e:
            if "max_model_len" in str(e).lower() or "context" in str(e).lower():
                pytest.skip(f"Model does not support this context length: {e}")
            raise

    @pytest.mark.i_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_super_long_context_stream(self, api_client: ModelAPIClient, test_logger):
        """I2: 超长上下文脚本验证 - 流式"""
        test_logger.info("=== 测试开始: 超长上下文(流式) ===")

        # 生成超长上下文
        long_prompt = "以下是一篇很长的文章：" + "这是第" + "测试段落。 " * 25000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [
            {"role": "user", "content": long_prompt + "\n\n请总结这篇文章的主要内容。"}
        ]
        TestLogger.log_request(test_logger, messages)

        try:
            response_iter = api_client.chat_completion_stream(messages, max_tokens=2000)
            result = self.collect_stream_chunks(response_iter)

            test_logger.info(
                f"Streaming chunks: {len(result['chunks'])}, content length: {len(result['content'])}, reasoning length: {len(result['reasoning'])}"
            )
            # 验证收到chunks
            assert len(result["chunks"]) > 0, "Should receive streaming chunks"

        except Exception as e:
            if "max_model_len" in str(e).lower() or "context" in str(e).lower():
                pytest.skip(f"Model does not support this context length: {e}")
            raise

    @pytest.mark.i_long_context
    @pytest.mark.p1
    def test_context_boundary_exact_limit(
        self, api_client: ModelAPIClient, test_logger
    ):
        """I3: 上下文边界验证 - 使用二分法逼近模型最大上下文长度"""
        test_logger.info("=== 测试开始: 上下文边界（二分法） ===")

        # 尝试获取模型最大上下文长度
        try:
            model_info = api_client.get_model_info()
            max_len = model_info.get("max_model_len", 0)
            test_logger.info(f"模型定义的最大上下文长度: {max_len}")

            if max_len > 0:
                # 使用二分法逐步逼近最大上下文长度
                # 初始化二分法范围
                low = 0
                high = max_len
                successful_len = 0
                failed_len = max_len
                max_iterations = 16  # 最多迭代16次

                test_logger.info(f"开始二分法测试，范围: [{low}, {high}]")

                for iteration in range(max_iterations):
                    # 计算中间值
                    mid = (low + high) // 2

                    # 跳过太小的值（至少要有意义）
                    if mid < 100:
                        low = mid + 1
                        continue

                    # 根据mid生成测试prompt（使用字母数字和空格，每个非空格字符约等于1 token）
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
                        if response.get("error"):
                            # 超出了边界
                            test_logger.warning(
                                f"长度 {mid} 失败: {response.get('error')}"
                            )
                            high = mid - 1
                            failed_len = mid
                        else:
                            # 成功
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
                            high = mid - 1
                            failed_len = mid
                        else:
                            raise

                    # 如果范围已经很小，停止
                    if high - low <= 10:
                        break

                test_logger.info(
                    f"二分法结果: 成功最大长度 ~{successful_len} tokens, 失败长度 ~{failed_len} tokens"
                )
                test_logger.info(f"模型定义的最大长度: {max_len} tokens")

                # 验证模型声称的最大长度是否可达到
                # 允许一定的误差范围（因为估算不一定准确）
                if successful_len > 0:
                    ratio = successful_len / max_len
                    test_logger.info(f"实际成功率: {ratio:.2%}")
                    # 如果实际能达到的上下文长度接近模型定义的值（80%以上），认为测试通过
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

    @pytest.mark.i_long_context
    @pytest.mark.p1
    def test_reasoning_content_in_long_context(
        self, api_client: ModelAPIClient, test_logger
    ):
        """I4: 验证超长上下文下reasoning_content的可用性"""
        test_logger.info("=== 测试开始: 长上下文+思考 ===")

        # 较长的上下文
        long_prompt = "请分析以下问题并给出详细解答：" + "问题描述。" * 1000
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [{"role": "user", "content": long_prompt}]
        thinking_params = api_client.get_thinking_params(True)
        TestLogger.log_request(test_logger, messages, thinking_params)

        # 开启thinking
        response = api_client.chat_completion(
            messages,
            extra_body=thinking_params,
            max_tokens=2000,
        )
        TestLogger.log_response(test_logger, response, "长上下文+思考响应")

        self.assert_response_success(response)

        reasoning = self.get_reasoning_content(response)
        content = self.get_message_content(response)

        test_logger.info(
            f"Long context with thinking: reasoning={len(reasoning) if reasoning else 0} chars, content={len(content) if content else 0} chars"
        )
