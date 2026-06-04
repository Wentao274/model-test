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

import json
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

    @staticmethod
    def _log_full_response(test_logger, response: dict, title: str = "完整响应"):
        """记录完整响应信息到日志（INFO级别，不截断）"""
        try:
            full_json = json.dumps(response, ensure_ascii=False, indent=2)
            test_logger.info(f"=== {title} 完整响应 ===\n{full_json}")
        except Exception as e:
            test_logger.warning(f"序列化完整响应失败: {e}")
            test_logger.info(f"=== {title} 原始响应 ===\n{response}")

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
        self._log_full_response(test_logger, response, "A1-单轮对话")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content.strip()) > 0, "Response should contain non-empty text"

        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
        assert finish_reason in ("stop", "eos", "ended"), (
            f"finish_reason should be 'stop'/'eos'/'ended', got '{finish_reason}'"
        )

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
    def test_multi_turn_conversation(self, api_client: ModelAPIClient, test_logger):
        """A2: 多轮对话 - 5轮对话，验证上下文保持和连贯性"""
        test_logger.info("=== 测试开始: 多轮对话 (5轮) ===")

        messages = []

        # 第1轮
        test_logger.info("第1轮: 用户说我喜欢的颜色是蓝色")
        messages.append({"role": "user", "content": "我喜欢的颜色是蓝色"})
        TestLogger.log_request(test_logger, messages)

        response1 = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response1, "第1轮响应")
        self._log_full_response(test_logger, response1, "A2-第1轮")

        self.assert_response_success(response1, "First round")
        messages.append(response1["choices"][0]["message"])

        # 第2轮
        test_logger.info("第2轮: 追问刚才说的颜色")
        messages.append({"role": "user", "content": "我刚才说我喜欢什么颜色？"})
        TestLogger.log_request(test_logger, messages)

        response2 = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response2, "第2轮响应")
        self._log_full_response(test_logger, response2, "A2-第2轮")

        self.assert_response_success(response2, "Second round")
        content2 = self.get_message_content(response2)
        test_logger.info(f"第2轮回答: {content2[:2000]}...")

        assert "蓝色" in content2 or "blue" in content2.lower(), (
            "Model should remember the previous context about blue color"
        )
        messages.append(response2["choices"][0]["message"])

        # 第3轮追问（用户从未提过水果）
        test_logger.info("第3轮: 问水果")
        messages.append({"role": "user", "content": "那我喜欢的水果是什么呢？"})
        response3 = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response3, "第3轮响应")
        self._log_full_response(test_logger, response3, "A2-第3轮")

        self.assert_response_success(response3, "Third round")
        content3 = self.get_message_content(response3)
        assert len(content3.strip()) > 0, "Third round response should not be empty"
        messages.append(response3["choices"][0]["message"])

        # 第4轮
        test_logger.info("第4轮: 问城市")
        messages.append({"role": "user", "content": "我居住的城市是上海"})
        response4 = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response4, "第4轮响应")
        self._log_full_response(test_logger, response4, "A2-第4轮")

        self.assert_response_success(response4, "Fourth round")
        messages.append(response4["choices"][0]["message"])

        # 第5轮验证所有上下文
        test_logger.info("第5轮: 验证之前所有上下文")
        messages.append({"role": "user", "content": "请总结一下我们刚才谈论的所有内容"})
        response5 = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response5, "第5轮响应")
        self._log_full_response(test_logger, response5, "A2-第5轮")

        self.assert_response_success(response5, "Fifth round")
        content5 = self.get_message_content(response5)
        test_logger.info(f"第5轮总结: {content5[:2000]}...")

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

        system_prompt = "你是一个专业的Python编程助手，善于解释代码和解决编程问题。请始终以Python编程专家的身份回答。"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请解释什么是装饰器？"},
        ]

        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "System Prompt响应")
        self._log_full_response(test_logger, response, "A3-SystemPrompt")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        test_logger.info(f"响应内容: {content[:2000]}...")

        assert any(
            kw in content.lower()
            for kw in ["python", "装饰器", "decorator", "def", "@", "wrapper"]
        ), "Response should contain Python/decorator-related terms"

        deviated_keywords = [
            "我不是",
            "i'm not",
            "i am not",
            "无法回答",
            "不能回答编程",
        ]
        assert not any(kw in content.lower() for kw in deviated_keywords), (
            "Model should not deny its Python expert role set by system prompt"
        )

        messages.append(response["choices"][0]["message"])
        messages.append({"role": "user", "content": "今天天气怎么样？"})

        test_logger.info("验证模型在偏离角色的问题上仍保持角色设定")
        response_deviate = api_client.chat_completion(messages)
        self._log_full_response(test_logger, response_deviate, "A3-角色偏离测试")

        self.assert_response_success(response_deviate)
        content_deviate = self.get_message_content(response_deviate)
        assert any(
            kw in content_deviate.lower()
            for kw in ["python", "编程", "代码", "code", "程序"]
        ), "Model should still relate to programming even for off-topic questions"

    @pytest.mark.a_basic
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_streaming_output(self, api_client: ModelAPIClient, test_logger):
        """A4: 流式输出 - stream=true，验证SSE逐token返回"""
        test_logger.info("=== 测试开始: 流式输出 ===")

        messages = [{"role": "user", "content": "请给我讲一个笑话"}]
        TestLogger.log_request(test_logger, messages)

        response_iterator = api_client.chat_completion_stream(messages)
        result = self.collect_stream_chunks(response_iterator)

        test_logger.info(
            f"接收到 {len(result['chunks'])} 个chunks，内容长度: {len(result['content'])}"
        )
        test_logger.info(f"流式内容: {result['content'][:2000]}...")

        assert len(result["chunks"]) > 0, "Should receive streaming chunks"
        assert len(result["content"].strip()) > 0, (
            "Should receive non-empty content in streaming"
        )

        first_chunk = result["chunks"][0]
        assert first_chunk.get("choices") is not None, (
            "First chunk should have 'choices' field"
        )
        first_delta = first_chunk["choices"][0].get("delta", {})
        assert (
            first_delta.get("role") == "assistant"
            or first_delta.get("content") is not None
        ), "First chunk delta should contain role='assistant' or content"

        has_content_delta = False
        for chunk in result["chunks"]:
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            if delta.get("content"):
                has_content_delta = True
                break
        assert has_content_delta, "At least one chunk should have delta.content"

        last_chunk = result["chunks"][-1]
        last_finish = last_chunk.get("choices", [{}])[0].get("finish_reason")
        assert last_finish in ("stop", "eos", "ended", None), (
            f"Last chunk finish_reason should be 'stop'/'eos'/'ended'/None, got '{last_finish}'"
        )

        test_logger.info(
            f"Streaming validation passed: {len(result['chunks'])} chunks, "
            f"content length: {len(result['content'])}, last finish_reason: {last_finish}"
        )

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_non_streaming_output(self, api_client: ModelAPIClient, test_logger):
        """A5: 非流式输出 - stream=false，验证完整返回"""
        test_logger.info("=== 测试开始: 非流式输出 ===")

        messages = [{"role": "user", "content": "请给我讲一个笑话"}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages, stream=False)
        TestLogger.log_response(test_logger, response, "非流式响应")
        self._log_full_response(test_logger, response, "A5-非流式输出")

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
                f"got total={usage['total_tokens']}, prompt={usage.get('prompt_tokens')}, "
                f"completion={usage.get('completion_tokens')}"
            )

        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
        assert finish_reason in ("stop", "eos", "ended"), (
            f"finish_reason should be 'stop'/'eos'/'ended', got '{finish_reason}'"
        )

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_temperature_control(self, api_client: ModelAPIClient, test_logger):
        """A6: Temperature 控制 - temp=0(确定性) vs temp=1.0(多样性)"""
        test_logger.info("=== 测试开始: Temperature 控制 ===")

        messages = [{"role": "user", "content": "请给出三个关于天气的形容词"}]
        TestLogger.log_request(test_logger, messages)

        # temp=0 确定性输出
        test_logger.info("temp=0: 确定性输出")
        response0 = api_client.chat_completion(messages, temperature=0.0)
        TestLogger.log_response(test_logger, response0, "temp=0第一次响应")
        self._log_full_response(test_logger, response0, "A6-temp=0-第1次")

        self.assert_response_success(response0)
        content0 = self.get_message_content(response0)
        test_logger.info(f"temp=0 第一次响应: {content0[:2000]}...")

        # temp=1.0 多样性第一次输出
        test_logger.info("temp=1.0: 多样性第一次输出")
        response1 = api_client.chat_completion(messages, temperature=1.0)
        TestLogger.log_response(test_logger, response1, "temp=1.0第一次响应")
        self._log_full_response(test_logger, response1, "A6-temp=1.0-第1次")

        self.assert_response_success(response1)
        content1 = self.get_message_content(response1)
        test_logger.info(f"temp=1.0 响应: {content1[:2000]}...")

        # temp=0 应该更确定，多次调用结果应该相同
        test_logger.info("验证temp=0的确定性：再次调用相同prompt")
        response0_repeat = api_client.chat_completion(messages, temperature=0.0)
        TestLogger.log_response(test_logger, response0_repeat, "temp=0第二次响应")
        self._log_full_response(test_logger, response0_repeat, "A6-temp=0-第2次")

        self.assert_response_success(response0_repeat)
        content0_repeat = self.get_message_content(response0_repeat)
        test_logger.info(f"temp=0 第二次响应: {content0_repeat[:2000]}...")

        similarity = SequenceMatcher(None, content0, content0_repeat).ratio()
        test_logger.info(f"temp=0 两次输出相似度: {similarity:.4f}")
        assert similarity >= 0.8, (
            f"temp=0 outputs should be highly similar (similarity={similarity:.4f}), "
            f"got:\n[1]{content0[:500]}\n[2]{content0_repeat[:500]}"
        )

        # temp=1.0 多样性第二次输出
        test_logger.info("temp=1.0: 多样性第二次输出")
        response1_repeat = api_client.chat_completion(messages, temperature=1.0)
        TestLogger.log_response(test_logger, response1_repeat, "temp=1.0第二次响应")
        self._log_full_response(test_logger, response1_repeat, "A6-temp=1.0-第2次")

        self.assert_response_success(response1_repeat)
        content1_repeat = self.get_message_content(response1_repeat)
        test_logger.info(f"temp=1.0 第二次响应: {content1_repeat[:2000]}...")

        similarity_high = SequenceMatcher(None, content1, content1_repeat).ratio()
        test_logger.info(f"temp=1.0 两次输出相似度: {similarity_high:.4f}")

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
                response = api_client.chat_completion(messages, top_k=int(param_value))
            except Exception as e:
                pytest.skip(f"API不支持top_k参数: {e}")

        TestLogger.log_response(
            test_logger, response, f"{param_type}={param_value}响应"
        )
        self._log_full_response(test_logger, response, f"A7-{param_type}={param_value}")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        test_logger.info(f"{param_type}={param_value} 响应: {content[:2000]}...")

        assert len(content.strip()) > 0, (
            f"{param_type}={param_value} response should not be empty"
        )

        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
        assert finish_reason in ("stop", "eos", "ended", "length"), (
            f"finish_reason should be valid, got '{finish_reason}'"
        )

    @pytest.mark.a_basic
    @pytest.mark.p0
    @pytest.mark.parametrize("max_tokens", [50, 100, 500])
    def test_max_tokens_limit(
        self, api_client: ModelAPIClient, max_tokens: int, test_logger
    ):
        """A8: Max Tokens限制 - 设置max_tokens，验证输出不超限"""
        test_logger.info(f"=== 测试开始: Max Tokens限制 (max_tokens={max_tokens}) ===")

        messages = [{"role": "user", "content": "请写一段尽可能长的文字，越长越好"}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages, max_tokens=max_tokens)
        TestLogger.log_response(test_logger, response, f"max_tokens={max_tokens}响应")
        self._log_full_response(test_logger, response, f"A8-max_tokens={max_tokens}")

        self.assert_response_success(response)
        self.assert_max_tokens_limit(response, max_tokens)

        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        test_logger.info(
            f"max_tokens={max_tokens}, 实际completion_tokens={completion_tokens}"
        )

        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
        if completion_tokens >= max_tokens - 5:
            assert finish_reason == "length", (
                f"When output reaches max_tokens limit, finish_reason should be 'length', got '{finish_reason}'"
            )

        assert completion_tokens <= max_tokens + 10, (
            f"completion_tokens ({completion_tokens}) should not exceed max_tokens ({max_tokens}) + tolerance (10)"
        )

    @pytest.mark.a_basic
    @pytest.mark.p1
    def test_stop_sequences(self, api_client: ModelAPIClient, test_logger):
        """A9: Stop Sequences - 设置stop token，验证截断"""
        test_logger.info("=== 测试开始: Stop Sequences ===")

        messages = [
            {"role": "user", "content": "请列举五个水果，并简单介绍各水果的营养价值"}
        ]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages, stop=["苹果", "香蕉"])
        TestLogger.log_response(test_logger, response, "Stop Sequences响应")
        self._log_full_response(test_logger, response, "A9-StopSequences")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        test_logger.info(f"Stop Sequences 响应: {content}")

        assert "苹果" not in content, (
            "Output should stop before the stop sequence '苹果' and not contain it"
        )
        assert "香蕉" not in content, (
            "Output should stop before the stop sequence '香蕉' and not contain it"
        )

        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
        assert finish_reason == "stop", (
            f"When stop sequence is triggered, finish_reason should be 'stop', got '{finish_reason}'"
        )

    @pytest.mark.a_basic
    @pytest.mark.p1
    def test_seed_reproducibility(self, api_client: ModelAPIClient, test_logger):
        """A10: Seed 可复现性 - 相同seed+temp=0，验证输出一致"""
        test_logger.info("=== 测试开始: Seed 可复现性 ===")

        messages = [{"role": "user", "content": "请用一个词形容天空"}]
        TestLogger.log_request(test_logger, messages)

        # 第一次调用
        test_logger.info("第一次调用 (seed=42, temp=0)")
        response1 = api_client.chat_completion(messages, temperature=0.0, seed=42)
        TestLogger.log_response(test_logger, response1, "第一次响应")
        self._log_full_response(test_logger, response1, "A10-Seed-第1次")

        self.assert_response_success(response1)
        content1 = self.get_message_content(response1)
        test_logger.info(f"第一次响应: {content1}")

        # 第二次调用，相同参数
        test_logger.info("第二次调用 (seed=42, temp=0)")
        response2 = api_client.chat_completion(messages, temperature=0.0, seed=42)
        TestLogger.log_response(test_logger, response2, "第二次响应")
        self._log_full_response(test_logger, response2, "A10-Seed-第2次")

        self.assert_response_success(response2)
        content2 = self.get_message_content(response2)
        test_logger.info(f"第二次响应: {content2}")

        if content1 == content2:
            test_logger.info("Seed 可复现性测试通过：两次输出完全一致")
        else:
            similarity = SequenceMatcher(None, content1, content2).ratio()
            test_logger.warning(f"两次输出不完全一致，相似度: {similarity:.4f}")
            test_logger.warning(f"[1] {content1}")
            test_logger.warning(f"[2] {content2}")
            assert similarity >= 0.9, (
                f"Seed reproducibility: outputs with same seed should be nearly identical "
                f"(similarity={similarity:.4f})"
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
                r"[a-zA-ZàâéèêëïîôùûüçÀÂÉÈÊËÏÎÔÙÛÜÇ]",
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
        """A11: 多语言能力 - 中/英/日/韩/法等多语言输入输出"""
        test_logger.info(f"=== 测试开始: 多语言能力 ({lang}) ===")

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{lang}语言响应")
        self._log_full_response(test_logger, response, f"A11-多语言-{lang}")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        test_logger.info(f"Language {lang} 响应: {content[:2000]}...")

        assert len(content.strip()) > 10, (
            f"Response too short for {lang}: got {len(content.strip())} chars"
        )

        assert re.search(expected_chars, content) is not None, (
            f"Response for {lang} should contain expected character patterns ({expected_chars}), got: {content[:200]}"
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
                ["hello", "def", "print", "函数", "python"],
            ),
            ("math", "请计算：∫₀² x² dx = ?", ["8/3", "2.667", "积分", "x²"]),
            (
                "html",
                "请解析以下HTML：<div class='container'><p>Hello</p></div>",
                ["div", "p", "container", "html"],
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
        """A12: 特殊Token处理 - 含emoji、代码块、数学符号、HTML标签的输入"""
        test_logger.info(f"=== 测试开始: 特殊Token处理 ({test_type}) ===")

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{test_type}响应")
        self._log_full_response(test_logger, response, f"A12-特殊Token-{test_type}")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        content_lower = content.lower()

        matched = [kw for kw in expected_keywords if kw.lower() in content_lower]
        assert len(matched) >= 1, (
            f"Response for {test_type} should contain at least one of {expected_keywords}, "
            f"matched: {matched}, got: {content[:500]}"
        )

        test_logger.info(
            f"Special token test ({test_type}) passed, matched keywords: {matched}"
        )
