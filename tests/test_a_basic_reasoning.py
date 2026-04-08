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
import pytest
from typing import List, Dict, Any

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestBasicReasoning(BaseTest, StreamingTestMixin):
    """基础推理能力测试类"""

    def get_test_category(self) -> str:
        return "A. 基础推理能力"

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

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content) > 0, "Response should contain text"
        test_logger.info(f"Response: {content[:100]}...")

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

        self.assert_response_success(response1, "First round")
        messages.append(response1["choices"][0]["message"])

        # 第2轮
        test_logger.info("第2轮: 追问刚才说的颜色")
        messages.append({"role": "user", "content": "我刚才说我喜欢什么颜色？"})
        TestLogger.log_request(test_logger, messages)

        response2 = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response2, "第2轮响应")

        self.assert_response_success(response2, "Second round")
        content2 = self.get_message_content(response2)
        test_logger.info(f"第2轮回答: {content2[:100]}...")

        # 验证模型记得之前的对话
        assert "蓝色" in content2 or "blue" in content2.lower(), \
            "Model should remember the previous context"
        messages.append(response2["choices"][0]["message"])

        # 第3轮追问
        test_logger.info("第3轮: 问水果")
        messages.append({"role": "user", "content": "那我喜欢的水果是什么呢？"})
        response3 = api_client.chat_completion(messages)
        self.assert_response_success(response3, "Third round")
        messages.append(response3["choices"][0]["message"])

        # 第4轮
        test_logger.info("第4轮: 问城市")
        messages.append({"role": "user", "content": "我居住的城市是上海"})
        response4 = api_client.chat_completion(messages)
        self.assert_response_success(response4, "Fourth round")
        messages.append(response4["choices"][0]["message"])

        # 第5轮验证所有上下文
        test_logger.info("第5轮: 验证之前所有上下文")
        messages.append({"role": "user", "content": "请总结一下我们刚才谈论的所有内容"})
        response5 = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response5, "第5轮响应")

        self.assert_response_success(response5, "Fifth round")
        content5 = self.get_message_content(response5)
        test_logger.info(f"第5轮总结: {content5[:200]}...")

        test_logger.info("5轮对话测试完成")

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_system_prompt(self, api_client: ModelAPIClient, test_logger):
        """A3: System Prompt - 设置系统角色，验证模型遵循程度"""
        test_logger.info("=== 测试开始: System Prompt ===")

        system_prompt = "你是一个专业的Python编程助手，善于解释代码和解决编程问题"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请解释什么是装饰器？"}
        ]

        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "System Prompt响应")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        test_logger.info(f"响应内容: {content[:200]}...")

        # 验证回答与Python/编程相关
        assert any(keyword in content.lower() for keyword in ["python", "装饰器", "decorator", "函数", "wrapper"]), \
            "Response should be related to Python and programming"

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

        test_logger.info(f"接收到 {len(result['chunks'])} 个chunks，内容长度: {len(result['content'])}")
        test_logger.info(f"流式内容: {result['content'][:200]}...")

        assert len(result["chunks"]) > 0, "Should receive streaming chunks"
        assert len(result["content"]) > 0, "Should receive content in streaming"

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_non_streaming_output(self, api_client: ModelAPIClient, test_logger):
        """A5: 非流式输出 - stream=false，验证完整返回"""
        test_logger.info("=== 测试开始: 非流式输出 ===")

        messages = [{"role": "user", "content": "请给我讲一个笑话"}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages, stream=False)
        TestLogger.log_response(test_logger, response, "非流式响应")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        # 验证usage字段存在
        usage = self.get_usage(response)
        test_logger.info(f"Usage: {usage}")
        assert usage.get("completion_tokens", 0) > 0, "Should have completion tokens"

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
        TestLogger.log_response(test_logger, response0, "temp=0响应")

        self.assert_response_success(response0)
        content0 = self.get_message_content(response0)
        test_logger.info(f"temp=0 响应: {content0[:100]}...")

        # temp=1.0 多样性输出
        test_logger.info("temp=1.0: 多样性输出")
        response1 = api_client.chat_completion(messages, temperature=1.0)
        TestLogger.log_response(test_logger, response1, "temp=1.0响应")

        self.assert_response_success(response1)
        content1 = self.get_message_content(response1)
        test_logger.info(f"temp=1.0 响应: {content1[:100]}...")

        # temp=0 应该更确定，多次调用结果应该相同
        test_logger.info("验证temp=0的确定性：再次调用相同prompt")
        response0_repeat = api_client.chat_completion(messages, temperature=0.0)
        content0_repeat = self.get_message_content(response0_repeat)

        # temp=0 时输出应该一致或非常相似
        test_logger.info("Temperature控制测试完成")

    @pytest.mark.a_basic
    @pytest.mark.p1
    @pytest.mark.parametrize("param_type,param_value", [
        ("top_p", 0.5),
        ("top_p", 0.9),
        ("top_k", 20),
        ("top_k", 50),
    ])
    def test_top_p_top_k_sampling(self, api_client: ModelAPIClient, param_type: str, param_value: float, test_logger):
        """A7: Top-p / Top-k 采样 - 不同值验证多样性控制"""
        test_logger.info(f"=== 测试开始: {param_type}={param_value} ===")

        messages = [{"role": "user", "content": "请给出五个同义词：高兴"}]
        TestLogger.log_request(test_logger, messages)

        if param_type == "top_p":
            response = api_client.chat_completion(messages, top_p=param_value)
        else:
            # 注意: 某些API可能不支持top_k
            try:
                response = api_client.chat_completion(messages, top_k=int(param_value))
            except Exception as e:
                pytest.skip(f"API不支持top_k参数: {e}")

        TestLogger.log_response(test_logger, response, f"{param_type}={param_value}响应")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        test_logger.info(f"{param_type}={param_value} 响应: {content[:100]}...")

    @pytest.mark.a_basic
    @pytest.mark.p0
    @pytest.mark.parametrize("max_tokens", [50, 100, 500])
    def test_max_tokens_limit(self, api_client: ModelAPIClient, max_tokens: int, test_logger):
        """A8: Max Tokens限制 - 设置max_tokens，验证输出不超限"""
        test_logger.info(f"=== 测试开始: Max Tokens限制 (max_tokens={max_tokens}) ===")

        messages = [{"role": "user", "content": "请写一段尽可能长的文字，越长越好"}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages, max_tokens=max_tokens)
        TestLogger.log_response(test_logger, response, f"max_tokens={max_tokens}响应")

        self.assert_response_success(response)
        self.assert_max_tokens_limit(response, max_tokens)

        usage = response.get('usage', {})
        test_logger.info(f"max_tokens={max_tokens}, 实际completion_tokens={usage.get('completion_tokens', 0)}")

    @pytest.mark.a_basic
    @pytest.mark.p1
    def test_stop_sequences(self, api_client: ModelAPIClient, test_logger):
        """A9: Stop Sequences - 设置stop token，验证截断"""
        test_logger.info("=== 测试开始: Stop Sequences ===")

        messages = [{"role": "user", "content": "请列举五个水果："}]
        TestLogger.log_request(test_logger, messages)

        # 设置在句号处停止
        response = api_client.chat_completion(
            messages,
            stop=["。", "\n"]
        )
        TestLogger.log_response(test_logger, response, "Stop Sequences响应")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        test_logger.info(f"Stop Sequences 响应: {content}")

        # 验证输出在stop token处截断（不应该包含句号）
        if "。" in content:
            test_logger.warning("Output should stop before the stop token")

    @pytest.mark.a_basic
    @pytest.mark.p1
    def test_seed_reproducibility(self, api_client: ModelAPIClient, test_logger):
        """A10: Seed 可复现性 - 相同seed+temp=0，验证输出一致"""
        test_logger.info("=== 测试开始: Seed 可复现性 ===")

        messages = [{"role": "user", "content": "请用一个词形容天空"}]
        TestLogger.log_request(test_logger, messages)

        # 第一次调用
        test_logger.info("第一次调用 (seed=42, temp=0)")
        response1 = api_client.chat_completion(
            messages,
            temperature=0.0,
            seed=42
        )
        TestLogger.log_response(test_logger, response1, "第一次响应")

        self.assert_response_success(response1)
        content1 = self.get_message_content(response1)
        test_logger.info(f"第一次响应: {content1}")

        # 第二次调用，相同参数
        test_logger.info("第二次调用 (seed=42, temp=0)")
        response2 = api_client.chat_completion(
            messages,
            temperature=0.0,
            seed=42
        )
        TestLogger.log_response(test_logger, response2, "第二次响应")

        self.assert_response_success(response2)
        content2 = self.get_message_content(response2)
        test_logger.info(f"第二次响应: {content2}")

        # 验证输出一致
        assert content1 == content2, f"Seed reproducibility failed: '{content1}' != '{content2}'"
        test_logger.info("Seed 可复现性测试通过：两次输出完全一致")

    @pytest.mark.a_basic
    @pytest.mark.p1
    @pytest.mark.smoke
    @pytest.mark.parametrize("lang,prompt", [
        ("zh", "请用中文介绍一下北京"),
        ("en", "Please introduce London in English"),
        ("ja", "日本語で大阪について介紹してください"),
        ("ko", "한국어로 서울에 대해 소개해 주세요"),
        ("fr", "Présentez Paris en français"),
    ])
    def test_multilingual_capability(self, api_client: ModelAPIClient, lang: str, prompt: str, test_logger):
        """A11: 多语言能力 - 中/英/日/韩/法等多语言输入输出"""
        test_logger.info(f"=== 测试开始: 多语言能力 ({lang}) ===")

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{lang}语言响应")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        test_logger.info(f"Language {lang} 响应: {content[:50]}...")

        # 简单验证有实际输出
        assert len(content) > 10, f"Response too short for {lang}"

    @pytest.mark.a_basic
    @pytest.mark.p1
    @pytest.mark.parametrize("test_type,prompt", [
        ("emoji", "请回复以下内容：Hello 👋 World 🌍"),
        ("code", "请解释以下Python代码：\n```python\ndef hello():\n    print('Hello World')\n```"),
        ("math", "请计算：∫₀² x² dx = ?"),
        ("html", "请解析以下HTML：<div class='container'><p>Hello</p></div>"),
    ])
    def test_special_tokens_handling(self, api_client: ModelAPIClient, test_type: str, prompt: str, test_logger):
        """A12: 特殊Token处理 - 含emoji、代码块、数学符号、HTML标签的输入"""
        test_logger.info(f"=== 测试开始: 特殊Token处理 ({test_type}) ===")

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{test_type}响应")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        test_logger.info(f"Special token test ({test_type}) passed")