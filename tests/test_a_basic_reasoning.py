"""
A. 基础推理能力测试

测试点：
- A1: 单轮对话 - 发送单条prompt，验证正常生成
- A2: 多轮对话 - 5轮对话，验证上下文保持和连贯性
- A3: System Prompt - 设置系统角色，验证模型遵循程度
- A4: 流式输出 - stream=true，验证SSE逐token返回
- A5: 非流式输出 - stream=false，验证完整返回
- A6: Temperature 控制 - temp=0 vs temp=1.0，验证输出差异
- A7: Top-p / Top-k 采样 - 不同值验证多样性控制
- A8: Max Tokens限制 - 设置max_tokens，验证输出不超限
- A9: Stop Sequences - 设置stop token，验证截断
- A10: Seed 可复现性 - 相同seed+temp=0，验证输出一致
- A11: 多语言能力 - 中/英/日/韩/法等多语言输入输出
- A12: 特殊Token处理 - 含emoji、代码块、数学符号、HTML标签的输入
"""

import re
import pytest
from difflib import SequenceMatcher
from typing import List, Dict, Any

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestBasicReasoning(BaseTest, StreamingTestMixin):
    """基础推理能力测试类"""

    def get_test_category(self) -> str:
        return "A. 基础推理能力"

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _append_assistant_message(
        self, messages: List[Dict[str, Any]], response: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """将 assistant 回复追加到消息列表

        只保留 role 和 content（剥离 reasoning_content 字段），
        避免将思考内容回传给模型导致上下文污染。
        """
        content = self.get_message_content(response, strip_reasoning=True)
        messages.append({"role": "assistant", "content": content})
        return messages

    def _multi_turn_round(
        self,
        api_client: ModelAPIClient,
        test_logger,
        messages: List[Dict[str, Any]],
        user_content: str,
        round_label: str,
    ) -> str:
        """执行单轮多轮对话的公共流程

        追加用户消息 → 发送请求 → 日志记录 → 断言成功/非空 →
        获取正式回复 → 追加 assistant 消息。

        Args:
            user_content: 本轮用户消息内容
            round_label: 轮次标签（如 "第1轮"），用于日志和断言消息
        Returns:
            本轮正式回复内容（已剥离思考内容）
        """
        test_logger.info(f"{round_label}: {user_content}")
        messages.append({"role": "user", "content": user_content})
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{round_label}响应")
        self.log_full_response(test_logger, response, f"A2-{round_label}")

        self.assert_response_success(response, round_label)
        self.assert_content_not_empty(response, round_label)
        content = self._get_formal_content(response, test_logger, f"A2-{round_label}")
        self._append_assistant_message(messages, response)
        return content

    # ------------------------------------------------------------------
    # 测试用例
    # ------------------------------------------------------------------

    @pytest.mark.a_basic
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_single_turn_conversation(self, api_client: ModelAPIClient, test_logger):
        """A1: 单轮对话 - 发送单条prompt，验证正常生成"""
        test_logger.info("=== 测试开始: 单轮对话 ===")

        messages = [{"role": "user", "content": "你好，请介绍一下你自己"}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "单轮对话响应")
        self.log_full_response(test_logger, response, "A1-单轮对话")

        self.assert_response_success(response)
        # assert_content_not_empty 检查 content + reasoning，对思考模型安全
        self.assert_content_not_empty(response)

        content = self._get_formal_content(response, test_logger, "A1")
        finish_reason = self._assert_finish_reason(response)

        assert response.get("id") is not None, "Response should contain 'id' field"
        assert response.get("model") is not None, (
            "Response should contain 'model' field"
        )

        test_logger.info(
            f"Response content length: {len(content)}, finish_reason: {finish_reason}"
        )

    @pytest.mark.a_basic
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_multi_turn_conversation(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """A2: 多轮对话 - 5轮对话，验证上下文保持和连贯性"""
        test_logger.info("=== 测试开始: 多轮对话 (5轮) ===")

        messages = []

        # 第1轮
        self._multi_turn_round(
            api_client, test_logger, messages, "我喜欢的颜色是蓝色", "第1轮"
        )

        # 第2轮: 追问刚才说的颜色
        content2 = self._multi_turn_round(
            api_client, test_logger, messages, "我刚才说我喜欢什么颜色？", "第2轮"
        )
        test_logger.info(f"第2轮回答: {content2[:2000]}")
        assert "蓝色" in content2 or "blue" in content2.lower(), (
            "Model should remember the previous context about blue color"
        )

        # 第3轮追问（用户从未提过水果，验证模型不产生幻觉）
        content3 = self._multi_turn_round(
            api_client, test_logger, messages, "那我喜欢的水果是什么呢？", "第3轮"
        )

        # 幻觉检测：用户从未提及水果，模型不应编造具体水果
        common_fruits = [
            "苹果", "香蕉", "橙子", "葡萄", "西瓜", "草莓", "橘子", "梨",
        ]
        hallucinated = [f for f in common_fruits if f in content3]
        if hallucinated:
            msg = f"第3轮模型可能产生幻觉，编造了用户未提及的水果: {hallucinated}"
            test_logger.warning(msg)
            record_warning(msg)
        else:
            test_logger.info("第3轮幻觉检测通过：模型未编造用户未提及的水果")

        # 第4轮
        self._multi_turn_round(
            api_client, test_logger, messages, "我居住的城市是上海", "第4轮"
        )

        # 第5轮验证所有上下文
        content5 = self._multi_turn_round(
            api_client, test_logger, messages,
            "请总结一下我们刚才谈论的所有内容", "第5轮",
        )
        test_logger.info(f"第5轮总结: {content5[:2000]}")

        has_blue = "蓝色" in content5 or "blue" in content5.lower()
        has_shanghai = "上海" in content5 or "shanghai" in content5.lower()
        assert has_blue, "Summary should mention blue color from round 1"
        assert has_shanghai, "Summary should mention Shanghai from round 4"

        test_logger.info("5轮对话测试完成")

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_system_prompt(self, api_client: ModelAPIClient, test_logger):
        """A3: System Prompt - 设置系统角色，验证模型遵循程度"""
        test_logger.info("=== 测试开始: System Prompt ===")

        system_prompt = (
            "你是一个专业的Python编程助手，善于解释代码和解决编程问题。"
            "请始终以Python编程专家的身份回答。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请解释什么是装饰器？"},
        ]

        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "System Prompt响应")
        self.log_full_response(test_logger, response, "A3-SystemPrompt")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self._get_formal_content(response, test_logger, "A3")
        test_logger.info(f"响应内容: {content[:2000]}")

        assert any(
            kw in content.lower()
            for kw in ["python", "装饰器", "decorator", "def", "@", "wrapper"]
        ), "Response should contain Python/decorator-related terms"

        deviated_keywords = [
            "我不是编程",
            "我不是python",
            "i'm not a python",
            "i am not a python",
            "无法回答编程",
            "不能回答编程",
            "我不是一个编程助手",
        ]
        assert not any(kw in content.lower() for kw in deviated_keywords), (
            "Model should not deny its Python expert role set by system prompt"
        )

        # 第二轮：验证模型在偏离角色的问题上仍保持角色设定
        self._append_assistant_message(messages, response)
        messages.append({"role": "user", "content": "今天天气怎么样？"})

        test_logger.info("验证模型在偏离角色的问题上仍保持角色设定")
        TestLogger.log_request(test_logger, messages)
        response_deviate = api_client.chat_completion(messages)
        self.log_full_response(test_logger, response_deviate, "A3-角色偏离测试")

        self.assert_response_success(response_deviate)
        self.assert_content_not_empty(response_deviate, "Deviate round")
        content_deviate = self._get_formal_content(
            response_deviate, test_logger, "A3-角色偏离"
        )

        # 模型不应否认其 Python 编程助手角色
        assert not any(
            kw in content_deviate.lower() for kw in deviated_keywords
        ), (
            "Model should not deny its Python expert role for off-topic questions"
        )
        # 模型应引导回编程话题或声明无法查询天气（而非直接回答天气问题）
        role_keywords = ["python", "编程", "代码", "code", "程序"]
        limitation_keywords = ["无法", "不能", "不具备", "抱歉", "sorry"]
        assert (
            any(kw in content_deviate.lower() for kw in role_keywords)
            or any(kw in content_deviate.lower() for kw in limitation_keywords)
        ), (
            "Model should either relate to programming or acknowledge "
            "inability to answer weather questions"
        )

    @pytest.mark.a_basic
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_streaming_output(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """A4: 流式输出 - stream=true，验证SSE逐token返回"""
        test_logger.info("=== 测试开始: 流式输出 ===")

        messages = [{"role": "user", "content": "请给我讲一个笑话"}]
        TestLogger.log_request(test_logger, messages)

        response_iterator = api_client.chat_completion_stream(messages)
        result = self.collect_stream_chunks(response_iterator)

        test_logger.info(
            f"接收到 {len(result['chunks'])} 个chunks，"
            f"内容长度: {len(result['content'])}，"
            f"思考内容长度: {len(result['reasoning'])}"
        )
        test_logger.info(f"流式内容: {result['content'][:2000]}")

        assert len(result["chunks"]) > 0, "Should receive streaming chunks"

        # 思考模型可能 content 为空但 reasoning 有内容
        full_content = result["content"] + result["reasoning"]
        assert len(full_content.strip()) > 0, (
            "Should receive non-empty content or reasoning in streaming"
        )

        first_chunk = result["chunks"][0]
        assert first_chunk.get("choices") is not None, (
            "First chunk should have 'choices' field"
        )
        first_delta = first_chunk["choices"][0].get("delta", {})
        assert (
            first_delta.get("role") == "assistant"
            or first_delta.get("content") is not None
            or first_delta.get("reasoning") is not None
            or first_delta.get("reasoning_content") is not None
        ), (
            "First chunk delta should contain role='assistant', "
            "content, or reasoning"
        )

        # 至少一个 chunk 应有 delta.content 或 delta.reasoning
        has_content_delta = False
        for chunk in result["chunks"]:
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            if (
                delta.get("content")
                or delta.get("reasoning")
                or delta.get("reasoning_content")
            ):
                has_content_delta = True
                break
        assert has_content_delta, (
            "At least one chunk should have delta.content or delta.reasoning"
        )

        last_chunk = result["chunks"][-1]
        last_finish = last_chunk.get("choices", [{}])[0].get("finish_reason")
        assert last_finish in self.VALID_STREAM_FINISH_REASONS, (
            f"Last chunk finish_reason should be one of "
            f"{self.VALID_STREAM_FINISH_REASONS}, got '{last_finish}'"
        )

        # 检测流式响应是否被服务端积攒后一次性返回（软告警）
        is_buffered, duplicate_groups, stats = self.detect_buffered_streaming(result)
        if stats.get("skipped"):
            test_logger.info(f"[A4] 流式积攒检测跳过: {stats.get('skip_reason')}")
        else:
            test_logger.info(
                f"[A4] 流式时间戳统计: 总chunk={stats['total_chunks']}, "
                f"唯一时间戳={stats['unique_timestamps']}, "
                f"重复chunk占比={stats['dup_ratio']:.2%}"
            )
            if is_buffered:
                self.log_buffered_streaming_warning(
                    test_logger, result, duplicate_groups, stats, context="A4"
                )
                record_warning(
                    f"流式响应疑似被服务端积攒后一次性返回: "
                    f"重复chunk占比={stats['dup_ratio']:.2%}"
                )

        test_logger.info(
            f"Streaming validation passed: {len(result['chunks'])} chunks, "
            f"content length: {len(result['content'])}, "
            f"reasoning length: {len(result['reasoning'])}, "
            f"last finish_reason: {last_finish}"
        )

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_non_streaming_output(self, api_client: ModelAPIClient, test_logger):
        """A5: 非流式输出 - stream=false，验证完整返回"""
        test_logger.info("=== 测试开始: 非流式输出 ===")

        messages = [
            {"role": "user", "content": "请介绍一下机器学习的基本概念和应用场景"}
        ]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages, stream=False)
        TestLogger.log_response(test_logger, response, "非流式响应")
        self.log_full_response(test_logger, response, "A5-非流式输出")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        usage = self.get_usage(response)
        test_logger.info(f"Usage: {usage}")

        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )
        assert usage.get("prompt_tokens", 0) > 0, "Should have prompt_tokens > 0"

        if "total_tokens" in usage:
            assert usage["total_tokens"] == usage.get("prompt_tokens", 0) + usage.get(
                "completion_tokens", 0
            ), (
                f"total_tokens should equal prompt_tokens + completion_tokens, "
                f"got total={usage['total_tokens']}, "
                f"prompt={usage.get('prompt_tokens')}, "
                f"completion={usage.get('completion_tokens')}"
            )

        self._assert_finish_reason(response)

    @pytest.mark.a_basic
    @pytest.mark.p1
    def test_temperature_control(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """A6: Temperature 控制 - temp=0(确定性) vs temp=1.0(多样性)

        使用开放性 prompt（"描述理想生活"）增大答案空间，使 temp=1.0
        更容易体现多样性差异。使用 _get_formal_content 比较 formal content，
        避免思考模型 reasoning 波动干扰相似度计算。

        思考/推理模型说明：推理链路本身在 temp=0 下存在固有非确定性
        （浮点精度、batching 策略等），不同推理路径会产生不同 formal
        content，此时 temp=0 确定性断言降级为软告警，与 A10
        (test_seed_reproducibility) 保持一致。非思考模型仍使用硬断言。
        """
        test_logger.info("=== 测试开始: Temperature 控制 ===")

        messages = [
            {"role": "user", "content": "请用几句话描述一下你心目中的理想生活"}
        ]
        TestLogger.log_request(test_logger, messages)

        # temp=0 确定性输出
        test_logger.info("temp=0: 确定性输出")
        response0 = api_client.chat_completion(messages, temperature=0.0)
        TestLogger.log_response(test_logger, response0, "temp=0第一次响应")
        self.log_full_response(test_logger, response0, "A6-temp=0-第1次")

        self.assert_response_success(response0)
        content0 = self._get_formal_content(response0, test_logger, "A6-temp=0-1")
        test_logger.info(f"temp=0 第一次响应: {content0[:2000]}")

        # temp=1.0 多样性第一次输出
        test_logger.info("temp=1.0: 多样性第一次输出")
        response1 = api_client.chat_completion(messages, temperature=1.0)
        TestLogger.log_response(test_logger, response1, "temp=1.0第一次响应")
        self.log_full_response(test_logger, response1, "A6-temp=1.0-第1次")

        self.assert_response_success(response1)
        content1 = self._get_formal_content(response1, test_logger, "A6-temp=1.0-1")
        test_logger.info(f"temp=1.0 响应: {content1[:2000]}")

        # temp=0 应该更确定，多次调用结果应该高度相似
        test_logger.info("验证temp=0的确定性：再次调用相同prompt")
        response0_repeat = api_client.chat_completion(messages, temperature=0.0)
        TestLogger.log_response(test_logger, response0_repeat, "temp=0第二次响应")
        self.log_full_response(test_logger, response0_repeat, "A6-temp=0-第2次")

        self.assert_response_success(response0_repeat)
        content0_repeat = self._get_formal_content(
            response0_repeat, test_logger, "A6-temp=0-2"
        )
        test_logger.info(f"temp=0 第二次响应: {content0_repeat[:2000]}")

        similarity = SequenceMatcher(None, content0, content0_repeat).ratio()
        test_logger.info(f"temp=0 两次输出相似度: {similarity:.4f}")

        # 思考/推理模型即使 temp=0 也无法保证确定性：推理链路本身受
        # 浮点精度、batching 策略等影响产生不同 reasoning，进而导致
        # 正式 content 不同。此时将硬断言降级为软告警，与 A10
        # (test_seed_reproducibility) 的处理方式保持一致。
        has_reasoning = bool(
            self.get_reasoning_content(response0)
            or self.get_reasoning_content(response0_repeat)
        )
        if has_reasoning and similarity < 0.8:
            msg = (
                f"temp=0 输出相似度偏低({similarity:.4f}<0.8)，"
                f"模型为思考/推理模型，推理链路在 temp=0 下存在固有非确定性，"
                f"降级为软告警。"
                f"\n[1]{content0[:500]}\n[2]{content0_repeat[:500]}"
            )
            test_logger.warning(msg)
            record_warning(msg)
        else:
            assert similarity >= 0.8, (
                f"temp=0 outputs should be highly similar "
                f"(similarity={similarity:.4f}), "
                f"got:\n[1]{content0[:500]}\n[2]{content0_repeat[:500]}"
            )

        # temp=1.0 多样性第二次输出
        test_logger.info("temp=1.0: 多样性第二次输出")
        response1_repeat = api_client.chat_completion(messages, temperature=1.0)
        TestLogger.log_response(test_logger, response1_repeat, "temp=1.0第二次响应")
        self.log_full_response(test_logger, response1_repeat, "A6-temp=1.0-第2次")

        self.assert_response_success(response1_repeat)
        content1_repeat = self._get_formal_content(
            response1_repeat, test_logger, "A6-temp=1.0-2"
        )
        test_logger.info(f"temp=1.0 第二次响应: {content1_repeat[:2000]}")

        similarity_high = SequenceMatcher(None, content1, content1_repeat).ratio()
        test_logger.info(f"temp=1.0 两次输出相似度: {similarity_high:.4f}")

        # temp=1.0 两次输出完全一致 → temperature 参数可能未生效（硬断言）
        assert similarity_high < 0.99, (
            f"temp=1.0 两次输出完全一致(相似度={similarity_high:.4f})，"
            f"temperature 参数可能未生效"
        )

        # temp=1.0 相似度高于 temp=0 → temperature 多样性控制异常（软告警）
        if similarity_high > similarity:
            msg = (
                f"temp=1.0 相似度({similarity_high:.4f})高于 "
                f"temp=0({similarity:.4f})，temperature 多样性控制可能异常"
            )
            test_logger.warning(msg)
            record_warning(msg)
        else:
            test_logger.info(
                f"Temperature 多样性验证通过: temp=1.0 相似度"
                f"({similarity_high:.4f}) < temp=0 相似度({similarity:.4f})"
            )

        assert len(content0.strip()) > 0, "temp=0 response should not be empty"
        assert len(content1.strip()) > 0, "temp=1.0 response should not be empty"

        test_logger.info("Temperature控制测试完成")

    @pytest.mark.a_basic
    @pytest.mark.p1
    @pytest.mark.parametrize(
        "param_type,param_value",
        [
            ("top_p", 0.5),
            ("top_p", 0.9),
            ("top_k", 20),
            ("top_k", 50),
        ],
    )
    def test_top_p_top_k_sampling(
        self,
        api_client: ModelAPIClient,
        param_type: str,
        param_value: float,
        test_logger,
    ):
        """A7: Top-p / Top-k 采样 - 不同值验证多样性控制"""
        test_logger.info(f"=== 测试开始: {param_type}={param_value} ===")

        messages = [{"role": "user", "content": "请给出五个同义词：高兴"}]
        TestLogger.log_request(test_logger, messages)

        if param_type == "top_p":
            response = api_client.chat_completion(messages, top_p=param_value)
        else:
            try:
                response = api_client.chat_completion(
                    messages, top_k=int(param_value)
                )
            except Exception as e:
                # 仅对 400（参数不支持）跳过，其他错误（超时/500）向上抛出
                if "400" in str(e):
                    pytest.skip(f"API不支持top_k参数: {e}")
                raise

        TestLogger.log_response(
            test_logger, response, f"{param_type}={param_value}响应"
        )
        self.log_full_response(
            test_logger, response, f"A7-{param_type}={param_value}"
        )

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self._get_formal_content(
            response, test_logger, f"A7-{param_type}={param_value}"
        )
        test_logger.info(f"{param_type}={param_value} 响应: {content[:2000]}")

        assert len(content.strip()) > 0, (
            f"{param_type}={param_value} response should not be empty"
        )

        self._assert_finish_reason(response)

    @pytest.mark.a_basic
    @pytest.mark.p0
    @pytest.mark.parametrize("max_tokens", [50, 100, 500])
    def test_max_tokens_limit(
        self, api_client: ModelAPIClient, max_tokens: int, test_logger
    ):
        """A8: Max Tokens限制 - 设置max_tokens，验证输出不超限

        注意：思考模型在 max_tokens 较小时，reasoning 可能消耗全部 token，
        导致 content 为空。本测试验证的是 token 数量限制，使用
        assert_content_not_empty 确保 content 或 reasoning 至少有一个非空，
        但不单独要求 content 非空。使用 temp=0 确保输出一致性。
        """
        test_logger.info(
            f"=== 测试开始: Max Tokens限制 (max_tokens={max_tokens}) ==="
        )

        messages = [{"role": "user", "content": "请写一段尽可能长的文字，越长越好"}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(
            messages, max_tokens=max_tokens, temperature=0.0
        )
        TestLogger.log_response(
            test_logger, response, f"max_tokens={max_tokens}响应"
        )
        self.log_full_response(test_logger, response, f"A8-max_tokens={max_tokens}")

        self.assert_response_success(response)
        # 验证 content 或 reasoning 至少有一个非空
        # （思考模型 reasoning 可能消耗全部 token，content 可能为空）
        self.assert_content_not_empty(response)
        self.assert_max_tokens_limit(response, max_tokens)

        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        test_logger.info(
            f"max_tokens={max_tokens}, "
            f"实际completion_tokens={completion_tokens}"
        )

        finish_reason = self._assert_finish_reason(response)

        # 当输出接近 max_tokens 时，finish_reason 应为 "length"
        if completion_tokens >= max_tokens - 5:
            assert finish_reason == "length", (
                f"When output reaches max_tokens limit "
                f"(completion_tokens={completion_tokens}, "
                f"max_tokens={max_tokens}), "
                f"finish_reason should be 'length', got '{finish_reason}'"
            )

    @pytest.mark.a_basic
    @pytest.mark.p1
    def test_stop_sequences(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """A9: Stop Sequences - 设置stop token，验证截断

        注意：很多模型可能不支持 stop 参数，思考模型在思考模式下 stop
        sequence 还可能不生效（在 reasoning 阶段不触发），因此统一使用
        软告警而非硬断言，本测试作为诊断工具评估 stop 支持情况。
        """
        test_logger.info("=== 测试开始: Stop Sequences ===")

        # 强制指定水果顺序，确保 stop sequence 必然被遇到
        messages = [
            {
                "role": "user",
                "content": (
                    "请按以下顺序依次列举水果并介绍营养价值："
                    "苹果、香蕉、橙子、葡萄、西瓜。"
                    "每种水果用一段话介绍。"
                ),
            }
        ]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages, stop=["苹果", "香蕉"])
        TestLogger.log_response(test_logger, response, "Stop Sequences响应")
        self.log_full_response(test_logger, response, "A9-StopSequences")

        self.assert_response_success(response)
        content = self._get_formal_content(response, test_logger, "A9")
        test_logger.info(f"Stop Sequences 响应(仅正式content): {content[:2000]}")

        finish_reason = self._assert_finish_reason(response)

        is_thinking = api_client.config.get("thinking_mode", False)
        thinking_note = "（思考模式下 stop 序列可能不生效）" if is_thinking else ""

        # 检查 stop sequence 是否被正确触发：输出不应包含 stop 词
        # 很多模型可能不支持 stop 参数，统一使用软告警而非硬断言
        stop_words = ["苹果", "香蕉"]
        violations = [w for w in stop_words if w in content]
        if violations:
            msg = (
                f"Stop sequence 未生效：输出中仍包含 stop 词 {violations}，"
                f"模型可能不支持 stop 参数{thinking_note}"
            )
            test_logger.warning(msg)
            record_warning(msg)
        else:
            test_logger.info(
                f"Stop sequence 生效：输出中不包含 stop 词 {stop_words}，"
                f"内容被正确截断"
            )

        # 验证内容确实被截断：不应包含全部后续水果
        remaining_fruits = ["橙子", "葡萄", "西瓜"]
        mentioned_remaining = [f for f in remaining_fruits if f in content]
        if len(mentioned_remaining) >= 3:
            msg = (
                f"Stop sequence 可能未触发：输出仍包含全部后续水果 "
                f"{mentioned_remaining}，模型可能忽略了stop参数"
            )
            test_logger.warning(msg)
            record_warning(msg)
        else:
            test_logger.info(
                f"Stop sequence 截断验证通过：输出仅包含 {mentioned_remaining} "
                f"(未到达全部后续水果)"
            )

    @pytest.mark.a_basic
    @pytest.mark.p1
    def test_seed_reproducibility(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """A10: Seed 可复现性 - 相同seed+temp=0，验证输出一致

        使用 _get_formal_content 获取正式回复进行比较，避免思考模型
        reasoning 每次波动拉低相似度。

        注意：很多模型不支持 seed 参数或无法保证完全可复现（受硬件浮点
        差异、batching 策略等影响），因此所有不一致情况统一使用软告警，
        本测试作为诊断工具评估 seed 支持情况，不作为硬性失败条件。
        """
        test_logger.info("=== 测试开始: Seed 可复现性 ===")

        messages = [
            {"role": "user", "content": "请用一句话形容天空，并说明原因"}
        ]
        TestLogger.log_request(test_logger, messages)

        # 第一次调用
        test_logger.info("第一次调用 (seed=42, temp=0)")
        response1 = api_client.chat_completion(messages, temperature=0.0, seed=42)
        TestLogger.log_response(test_logger, response1, "第一次响应")
        self.log_full_response(test_logger, response1, "A10-Seed-第1次")

        self.assert_response_success(response1)
        content1 = self._get_formal_content(response1, test_logger, "A10-1")
        test_logger.info(f"第一次响应: {content1[:2000]}")

        # 第二次调用，相同参数
        test_logger.info("第二次调用 (seed=42, temp=0)")
        response2 = api_client.chat_completion(messages, temperature=0.0, seed=42)
        TestLogger.log_response(test_logger, response2, "第二次响应")
        self.log_full_response(test_logger, response2, "A10-Seed-第2次")

        self.assert_response_success(response2)
        content2 = self._get_formal_content(response2, test_logger, "A10-2")
        test_logger.info(f"第二次响应: {content2[:2000]}")

        if content1 == content2:
            test_logger.info("Seed 可复现性测试通过：两次输出完全一致")
        else:
            similarity = SequenceMatcher(None, content1, content2).ratio()
            test_logger.warning(f"两次输出不完全一致，相似度: {similarity:.4f}")
            test_logger.warning(f"[1] {content1[:500]}")
            test_logger.warning(f"[2] {content2[:500]}")
            if similarity < 0.3:
                msg = f"相似度极低({similarity:.4f})，模型可能不支持seed参数"
                test_logger.warning(msg)
                record_warning(msg)
            elif similarity < 0.6:
                msg = (
                    f"相似度较低({similarity:.4f})，模型可能仅部分支持seed参数，"
                    f"可复现性不稳定"
                )
                test_logger.warning(msg)
                record_warning(msg)
            elif similarity < 0.9:
                msg = (
                    f"相似度较高但未完全一致({similarity:.4f})，seed 可复现性"
                    f"基本正常但存在轻微波动"
                )
                test_logger.warning(msg)
                record_warning(msg)
            else:
                test_logger.info(
                    f"Seed 可复现性基本通过：相似度 {similarity:.4f}（接近完全一致）"
                )

    @pytest.mark.a_basic
    @pytest.mark.p1
    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "lang,prompt,expected_chars",
        [
            ("zh", "请用中文介绍一下北京", r"[\u4e00-\u9fff]"),
            ("en", "Please introduce London in English", r"[a-zA-Z]"),
            (
                "ja",
                "日本語で大阪について紹介してください",
                r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]",
            ),
            ("ko", "한국어로 서울에 대해 소개해 주세요", r"[\uac00-\ud7af]"),
            (
                "fr",
                "Présentez Paris en français",
                r"[àâéèêëïîôùûüçÀÂÉÈÊËÏÎÔÙÛÜÇ]",
            ),
        ],
    )
    def test_multilingual_capability(
        self,
        api_client: ModelAPIClient,
        lang: str,
        prompt: str,
        expected_chars: str,
        test_logger,
    ):
        """A11: 多语言能力 - 中/英/日/韩/法等多语言输入输出

        法语正则仅匹配法语特有字符（é/è/ç/ô 等），不包含 a-zA-Z，
        避免英语回复误通过。使用 _get_formal_content 避免思考模型
        reasoning 中的其他语言字符干扰。
        """
        test_logger.info(f"=== 测试开始: 多语言能力 ({lang}) ===")

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{lang}语言响应")
        self.log_full_response(test_logger, response, f"A11-多语言-{lang}")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self._get_formal_content(
            response, test_logger, f"A11-{lang}"
        )
        test_logger.info(f"Language {lang} 响应: {content[:2000]}")

        assert len(content.strip()) > 10, (
            f"Response too short for {lang}: got {len(content.strip())} chars"
        )

        assert re.search(expected_chars, content) is not None, (
            f"Response for {lang} should contain expected character patterns "
            f"({expected_chars}), got: {content[:200]}"
        )

    @pytest.mark.a_basic
    @pytest.mark.p1
    @pytest.mark.parametrize(
        "test_type,prompt,expected_keywords",
        [
            (
                "emoji",
                "请回复以下内容：Hello 👋 World 🌍",
                ["👋", "🌍", "hello", "world"],
            ),
            (
                "code",
                "请解释以下Python代码：\n```python\ndef hello():\n    print('Hello World')\n```",
                ["hello", "def", "print", "函数", "python", "调用"],
            ),
            (
                "math",
                "请计算：∫₀² x² dx = ?",
                ["8/3", "2.667", "2.67", "积分", "x²", "三分之八"],
            ),
            (
                "html",
                "请解析以下HTML：<div class='container'><p>Hello</p></div>",
                ["div", "p", "container", "html", "标签", "class"],
            ),
        ],
    )
    def test_special_tokens_handling(
        self,
        api_client: ModelAPIClient,
        test_type: str,
        prompt: str,
        expected_keywords: list,
        test_logger,
    ):
        """A12: 特殊Token处理 - 含emoji、代码块、数学符号、HTML标签的输入

        使用 _get_formal_content 避免 reasoning 中的关键词干扰，
        最低匹配数从 1 提升到 2，扩充关键词列表。
        """
        test_logger.info(f"=== 测试开始: 特殊Token处理 ({test_type}) ===")

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{test_type}响应")
        self.log_full_response(
            test_logger, response, f"A12-特殊Token-{test_type}"
        )

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self._get_formal_content(
            response, test_logger, f"A12-{test_type}"
        )
        content_lower = content.lower()

        matched = [kw for kw in expected_keywords if kw.lower() in content_lower]
        assert len(matched) >= 2, (
            f"Response for {test_type} should contain at least 2 of "
            f"{expected_keywords}, matched: {matched}, got: {content[:500]}"
        )

        test_logger.info(
            f"Special token test ({test_type}) passed, "
            f"matched keywords: {matched}"
        )
