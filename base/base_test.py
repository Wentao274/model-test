"""
基础测试类 - 所有测试用例的基类
"""

import json
import pytest
from typing import Dict, Any, List, Optional
from abc import ABC


class BaseTest(ABC):
    """测试基类，提供通用的测试方法和断言"""

    # 这些属性将由 pytest fixture 自动注入
    api_client = None
    config = None

    def assert_response_success(self, response: Dict[str, Any], message: str = ""):
        """断言响应成功"""
        assert response.get("choices") is not None, (
            f"Response has no choices: {message}"
        )
        assert len(response.get("choices", [])) > 0, (
            f"No choices in response: {message}"
        )

    def get_response_content(self, response: Dict[str, Any]) -> str:
        """获取响应内容，同时支持 content 和 reasoning_content"""
        message = response.get("choices", [{}])[0].get("message", {})
        content = message.get("content") or ""
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        return content + reasoning

    def assert_content_not_empty(self, response: Dict[str, Any], message: str = ""):
        """断言响应内容不为空"""
        content = self.get_response_content(response)
        assert content and len(content.strip()) > 0, (
            f"Response content is empty: {message}"
        )

    def get_message_content(
        self, response: Dict[str, Any], strip_thinking: bool = False
    ) -> str:
        """获取消息内容

        Args:
            response: API响应
            strip_thinking: 是否去除思考内容（</think>标签之间的内容）
        """
        content = self.get_response_content(response)
        if strip_thinking:
            import re

            content = re.sub(r"</think>.*?", "", content)
        return content

    def get_reasoning_content(self, response: Dict[str, Any]) -> Optional[str]:
        """获取思考内容"""
        message = response.get("choices", [{}])[0].get("message", {})
        return message.get("reasoning") or message.get("reasoning_content")

    def get_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取工具调用列表"""
        message = response.get("choices", [{}])[0].get("message", {})
        return message.get("tool_calls", [])

    def assert_streaming_response(self, response_iterator) -> str:
        """断言流式响应正确返回"""
        tokens = []
        for chunk in response_iterator:
            if chunk.get("choices") and chunk["choices"][0].get("delta"):
                delta = chunk["choices"][0]["delta"]
                if delta.get("content"):
                    tokens.append(delta["content"])
        assert len(tokens) > 0, "No tokens received in streaming response"
        return "".join(tokens)

    def assert_thinking_mode(self, response: Dict[str, Any], message: str = ""):
        """断言思考模式正确工作"""
        message_obj = response.get("choices", [{}])[0].get("message", {})
        reasoning = message_obj.get("reasoning") or message_obj.get("reasoning_content")
        assert reasoning is not None and len(reasoning) > 0, (
            f"Thinking mode is enabled but no reasoning returned: {message}"
        )

    def assert_no_thinking_leakage(self, response: Dict[str, Any], message: str = ""):
        """断言思考模式关闭时没有思考内容泄漏"""
        message_obj = response.get("choices", [{}])[0].get("message", {})
        reasoning = message_obj.get("reasoning") or message_obj.get("reasoning_content")
        content = message_obj.get("content", "")

        assert reasoning is None or reasoning == "", (
            f"Thinking disabled but reasoning is not empty: {message}"
        )

        # 检查常见思考模式标记
        thinking_markers = [
            "让我思考",
            "让我分析",
            "首先",
            "其次",
            "因此",
            "<think>",
            "</think>",
        ]
        for marker in thinking_markers:
            if marker in content:
                pytest.fail(f"Potential thinking leakage in content: found '{marker}'")

    def assert_tool_calls(
        self,
        response: Dict[str, Any],
        expected_tool_names: Optional[List[str]] = None,
        message: str = "",
    ):
        """断言工具调用正确执行"""
        tool_calls = self.get_tool_calls(response)
        assert len(tool_calls) > 0, f"No tool calls found in response: {message}"

        if expected_tool_names:
            actual_tools = [tc.get("function", {}).get("name") for tc in tool_calls]
            for expected in expected_tool_names:
                assert expected in actual_tools, (
                    f"Expected tool '{expected}' not found in {actual_tools}: {message}"
                )

    def assert_max_tokens_limit(
        self, response: Dict[str, Any], max_tokens: int, tolerance: int = 10
    ):
        """断言输出不超过max_tokens限制"""
        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        # 允许一定的容差
        assert completion_tokens <= max_tokens + tolerance, (
            f"Completion tokens {completion_tokens} exceeds max_tokens {max_tokens}"
        )

    def get_usage(self, response: Dict[str, Any]) -> Dict[str, int]:
        """获取usage信息"""
        return response.get("usage", {})

    @staticmethod
    def log_full_response(test_logger, response: dict, title: str = "完整响应"):
        """记录完整响应信息到日志"""
        try:
            full_json = json.dumps(response, ensure_ascii=False, indent=2)
            test_logger.info(f"=== {title} 完整响应 ===\n{full_json}")
        except Exception as e:
            test_logger.warning(f"序列化完整响应失败: {e}")
            test_logger.info(f"=== {title} 原始响应 ===\n{response}")


class StreamingTestMixin:
    """流式测试Mixin"""

    def collect_stream_chunks(self, response_iterator) -> Dict[str, Any]:
        """收集流式响应所有chunk"""
        chunks = []
        content_parts = []
        reasoning_parts = []

        for chunk in response_iterator:
            chunks.append(chunk)
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            if delta.get("content"):
                content_parts.append(delta["content"])
            if delta.get("reasoning_content"):
                reasoning_parts.append(delta["reasoning_content"])

        return {
            "chunks": chunks,
            "content": "".join(content_parts),
            "reasoning": "".join(reasoning_parts),
        }


class MultimodalTestMixin:
    """多模态测试Mixin"""

    @staticmethod
    def create_image_message(image_path: str, text: str = None) -> Dict[str, Any]:
        """创建图片消息（Base64编码）"""
        import base64

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_data}"},
            }
        ]

        if text:
            content.insert(0, {"type": "text", "text": text})

        return {"role": "user", "content": content}

    @staticmethod
    def create_url_image_message(image_url: str, text: str = None) -> Dict[str, Any]:
        """创建图片消息（URL）"""
        content = [{"type": "image_url", "image_url": {"url": image_url}}]

        if text:
            content.insert(0, {"type": "text", "text": text})

        return {"role": "user", "content": content}
