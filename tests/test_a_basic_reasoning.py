"""
A. 基础推理能力测试

测试点：
- A1: 单轮对话 - 发送单条prompt，验证正常生成
- A2: 多轮对话 - 3-5轮对话，验证上下文保持和连贯性
- A3: System Prompt - 设置系统角色，验证模型遵循程度
- A4: 流式输出 - stream=true，验证SSE逐token返回
- A5: 非流式输出 - stream=false，验证完整返回
- A6: Max Tokens限制 - 设置max_tokens=50/100/500，验证输出不超限
- A7: 多语言能力 - 中/英/日/韩/法等多语言输入输出
- A8: 特殊Token处理 - 含emoji、代码块、数学符号、HTML标签的输入
"""
import pytest
from typing import List, Dict, Any

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient


class TestBasicReasoning(BaseTest, StreamingTestMixin):
    """基础推理能力测试类"""

    def get_test_category(self) -> str:
        return "A. 基础推理能力"

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_single_turn_conversation(self, api_client: ModelAPIClient):
        """A1: 单轮对话 - 发送单条prompt，验证正常生成"""
        messages = [{"role": "user", "content": "你好，请介绍一下你自己"}]
        response = api_client.chat_completion(messages)

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content) > 0, "Response should contain text"
        print(f"Response: {content[:100]}...")

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_multi_turn_conversation(self, api_client: ModelAPIClient):
        """A2: 多轮对话 - 3-5轮对话，验证上下文保持和连贯性"""
        messages = []

        # 第1轮
        messages.append({"role": "user", "content": "我喜欢的颜色是蓝色"})
        response1 = api_client.chat_completion(messages)
        self.assert_response_success(response1, "First round")
        messages.append(response1["choices"][0]["message"])
        messages.append({"role": "user", "content": "我刚才说我喜欢什么颜色？"})
        response2 = api_client.chat_completion(messages)
        self.assert_response_success(response2, "Second round")
        content2 = self.get_message_content(response2)
        # 验证模型记得之前的对话
        assert "蓝色" in content2 or "blue" in content2.lower(), \
            "Model should remember the previous context"

        # 第3轮追问
        messages.append(response2["choices"][0]["message"])
        messages.append({"role": "user", "content": "那我喜欢的水果是什么呢？"})
        # 故意问一个没提到的，验证模型知道不知道
        response3 = api_client.chat_completion(messages)
        self.assert_response_success(response3, "Third round")

        print(f"Multi-turn conversation completed successfully")

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_system_prompt(self, api_client: ModelAPIClient):
        """A3: System Prompt - 设置系统角色，验证模型遵循程度"""
        system_prompt = "你是一个专业的Python编程助手，善于解释代码和解决编程问题"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "请解释什么是装饰器？"}
        ]

        response = api_client.chat_completion(messages)
        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        # 验证回答与Python/编程相关
        assert any(keyword in content.lower() for keyword in ["python", "装饰器", "decorator", "函数", "wrapper"]), \
            "Response should be related to Python and programming"

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_streaming_output(self, api_client: ModelAPIClient):
        """A4: 流式输出 - stream=true，验证SSE逐token返回"""
        messages = [{"role": "user", "content": "请给我讲一个笑话"}]

        response_iterator = api_client.chat_completion_stream(messages)
        result = self.collect_stream_chunks(response_iterator)

        assert len(result["chunks"]) > 0, "Should receive streaming chunks"
        assert len(result["content"]) > 0, "Should receive content in streaming"
        print(f"Received {len(result['chunks'])} chunks, content length: {len(result['content'])}")

    @pytest.mark.a_basic
    @pytest.mark.p0
    def test_non_streaming_output(self, api_client: ModelAPIClient):
        """A5: 非流式输出 - stream=false，验证完整返回"""
        messages = [{"role": "user", "content": "请给我讲一个笑话"}]

        response = api_client.chat_completion(messages, stream=False)

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        # 验证usage字段存在
        usage = self.get_usage(response)
        assert usage.get("completion_tokens", 0) > 0, "Should have completion tokens"

    @pytest.mark.a_basic
    @pytest.mark.p0
    @pytest.mark.parametrize("max_tokens", [50, 100, 500])
    def test_max_tokens_limit(self, api_client: ModelAPIClient, max_tokens: int):
        """A6: Max Tokens限制 - 设置max_tokens，验证输出不超限"""
        messages = [{"role": "user", "content": "请写一段尽可能长的文字，越长越好"}]

        response = api_client.chat_completion(messages, max_tokens=max_tokens)

        self.assert_response_success(response)
        self.assert_max_tokens_limit(response, max_tokens)
        print(f"max_tokens={max_tokens}, actual={response.get('usage', {}).get('completion_tokens', 0)}")

    @pytest.mark.a_basic
    @pytest.mark.p1
    @pytest.mark.parametrize("lang,prompt", [
        ("zh", "请用中文介绍一下北京"),
        ("en", "Please introduce London in English"),
        ("ja", "日本語で大阪について介紹してください"),
        ("ko", "한국어로 서울에 대해 소개해 주세요"),
        ("fr", "Présentez Paris en français"),
    ])
    def test_multilingual_capability(self, api_client: ModelAPIClient, lang: str, prompt: str):
        """A7: 多语言能力 - 中/英/日/韩/法等多语言输入输出"""
        messages = [{"role": "user", "content": prompt}]

        response = api_client.chat_completion(messages)
        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        # 简单验证有实际输出
        assert len(content) > 10, f"Response too short for {lang}"
        print(f"Language {lang}: {content[:50]}...")

    @pytest.mark.a_basic
    @pytest.mark.p1
    @pytest.mark.parametrize("test_type,prompt", [
        ("emoji", "请回复以下内容：Hello 👋 World 🌍"),
        ("code", "请解释以下Python代码：\n```python\ndef hello():\n    print('Hello World')\n```"),
        ("math", "请计算：∫₀² x² dx = ?"),
        ("html", "请解析以下HTML：<div class='container'><p>Hello</p></div>"),
    ])
    def test_special_tokens_handling(self, api_client: ModelAPIClient, test_type: str, prompt: str):
        """A8: 特殊Token处理 - 含emoji、代码块、数学符号、HTML标签的输入"""
        messages = [{"role": "user", "content": prompt}]

        response = api_client.chat_completion(messages)
        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        print(f"Special token test ({test_type}) passed")