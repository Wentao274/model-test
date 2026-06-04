"""
B. 高级生成功能测试

测试点：
- B1: 思考模式（Thinking）- 开启thinking mode，验证返回思考链+最终答案
- B2: 非思考模式（Instant）- 关闭thinking，验证无hidden thinking泄漏
- B3: 思考模式切换 - 同一会话内thinking↔non-thinking切换
- B4: 工具调用-单工具 - 定义单个function，验证模型正确调用并传参
- B5: 工具调用-多工具 - 定义多个function，验证模型选择正确的工具
- B6: 工具调用-并行调用 - 单次回复中并行调用多个工具
- B7: 工具调用-多步链式 - 工具结果作为下一步输入，验证3+步链式执行
- B8: JSON Mode - response_format=json_object，验证输出合法JSON
- B9: 结构化输出 - JSON Schema约束输出格式，验证字段完整性
- B10: Prefix / Suffix 约束 - 指定输出前缀或格式模板，验证遵循度
"""

import json
import re
import urllib.request
import urllib.parse
import json as json_lib
import pytest
from datetime import datetime
from typing import List, Dict, Any

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


def extract_json_from_text(text: str) -> Dict:
    """
    从文本中提取JSON
    支持：
    - 纯JSON
    - Markdown代码块包裹的JSON (```json ... ```)
    - 嵌入在其他文本中的JSON
    """
    if not text or not text.strip():
        raise ValueError("Empty content")

    text = text.strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试从Markdown代码块中提取
    json_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    matches = re.findall(json_block_pattern, text)
    for match in matches:
        try:
            return json.loads(match.strip())
        except json.JSONDecodeError:
            continue

    # 尝试提取第一个 { 到最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        json_str = text[start : end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    raise ValueError("No valid JSON found in content")


# 工具定义
TOOLS_GET_WEATHER = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名称"}},
                "required": ["city"],
            },
        },
    }
]

TOOLS_MULTIPLE = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取时间",
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string"}},
                "required": ["timezone"],
            },
        },
    },
]

# 5个不同工具的定义
TOOLS_FIVE = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息，如温度、湿度、天气状况",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名称"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "获取股票当前价格",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "股票代码，如 AAPL"}
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "搜索最新新闻",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "limit": {"type": "integer", "description": "返回新闻数量"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "数学计算器，支持加减乘除运算",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 2+3*4",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "translate",
            "description": "翻译文本到指定语言",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要翻译的文本"},
                    "target_lang": {
                        "type": "string",
                        "description": "目标语言，如 en、zh、ja",
                    },
                },
                "required": ["text", "target_lang"],
            },
        },
    },
]


class TestAdvancedGeneration(BaseTest, StreamingTestMixin):
    """高级生成功能测试类"""

    def get_test_category(self) -> str:
        return "B. 高级生成功能"

    @staticmethod
    def _strip_thinking_tags(content: str) -> str:
        if not content:
            return content
        if "</think>" in content:
            parts = content.split("</think>", 1)
            return parts[1].strip() if len(parts) > 1 else ""
        return content

    def _check_has_thinking(self, response: dict, test_logger) -> bool:
        reasoning = self.get_reasoning_content(response)
        content = self.get_message_content(response)
        has_reasoning_field = reasoning is not None and len(reasoning.strip()) > 0
        has_thinking_tags = False
        thinking_content = ""
        if content:
            if "<think>" in content and "</think>" in content:
                start = content.find("<think>") + len("<think>")
                end = content.find("</think>")
                thinking_content = content[start:end].strip()
                has_thinking_tags = len(thinking_content) > 0
            elif content.startswith("<|im_start|>assistant\n\n"):
                after_start = content.find("\n") + len("\n")
                if "</think>" in content:
                    end = content.find("</think>")
                    thinking_content = content[after_start:end].strip()
                    has_thinking_tags = len(thinking_content) > 0
            elif "</think>" in content and "<think>" not in content:
                end = content.find("</think>")
                thinking_content = content[:end].strip()
                has_thinking_tags = len(thinking_content) > 0
                test_logger.info("检测到 MiniMax M2 格式（仅有结束标签）")
        test_logger.info(
            f"reasoning 字段: {reasoning[:2000] if reasoning else 'None'}..."
        )
        test_logger.info(
            f"content 中的thinking标签: {'存在' if has_thinking_tags else '不存在'}"
        )
        if thinking_content:
            test_logger.info(f"思考内容: {thinking_content[:2000]}...")
        return has_reasoning_field or has_thinking_tags

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_thinking_mode(self, api_client: ModelAPIClient, test_logger):
        """B1: 思考模式（Thinking）- 开启thinking mode"""
        test_logger.info("=== 测试开始: 思考模式 ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]
        thinking_params = api_client.get_thinking_params(True)
        TestLogger.log_request(test_logger, messages, thinking_params)

        response = api_client.chat_completion(messages, extra_body=thinking_params)
        TestLogger.log_response(test_logger, response, "思考模式响应")
        self.log_full_response(test_logger, response, "B1-思考模式")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        has_thinking = self._check_has_thinking(response, test_logger)
        assert has_thinking, (
            "Thinking mode should return reasoning content (reasoning field or thinking tags)"
        )

        content = self.get_message_content(response)
        content_clean = self._strip_thinking_tags(content)
        test_logger.info(f"最终回答内容: {content_clean[:2000]}...")

        assert len(content_clean.strip()) > 0, (
            "Final answer content should not be empty"
        )
        assert any(kw in content_clean for kw in ["56088", "56088.0"]), (
            f"Thinking mode should produce correct answer 56088, got: {content_clean[:500]}"
        )

        test_logger.info("思考模式验证通过")

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_non_thinking_mode(self, api_client: ModelAPIClient, test_logger):
        """B2: 非思考模式（Instant）- 关闭thinking，无泄漏"""
        test_logger.info("=== 测试开始: 非思考模式 ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]

        thinking_params = api_client.get_thinking_params(False)
        TestLogger.log_request(test_logger, messages, thinking_params)

        response = api_client.chat_completion(messages, extra_body=thinking_params)
        TestLogger.log_response(test_logger, response, "非思考模式响应")
        self.log_full_response(test_logger, response, "B2-非思考模式")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        reasoning = self.get_reasoning_content(response)

        assert reasoning is None or reasoning == "", (
            f"Thinking disabled but reasoning field is not empty: {reasoning[:500]}"
        )

        if content:
            if "<think>" in content and "</think>" in content:
                thinking_blocks = re.findall(r"<think>\s*(.*?)\s*</think>", content, re.DOTALL)
                for block in thinking_blocks:
                    assert not block.strip(), (
                        f"Thinking disabled but found thinking content: {block[:2000]}..."
                    )
            elif "</think>" in content and "<think>" not in content:
                end = content.find("</think>")
                potential_thinking = content[:end].strip()
                assert not potential_thinking.strip(), (
                    f"Thinking disabled but found thinking content before end tag: "
                    f"{potential_thinking[:2000]}..."
                )

        content_clean = self._strip_thinking_tags(content)
        assert len(content_clean.strip()) > 0, (
            "Non-thinking mode should still produce a content response"
        )
        assert any(kw in content_clean for kw in ["56088", "56088.0"]), (
            f"Non-thinking mode should produce correct answer 56088, got: {content_clean[:500]}"
        )

        test_logger.info("非思考模式测试通过，无thinking泄漏")

    @pytest.mark.b_advanced
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_thinking_mode_switch(self, api_client: ModelAPIClient, test_logger):
        """B3: 思考模式切换 - 同一会话内thinking↔non-thinking切换"""
        test_logger.info("=== 测试开始: 思考模式切换 ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]

        test_logger.info("第1轮: 开启thinking模式")
        thinking_params_on = api_client.get_thinking_params(True)
        thinking_params_off = api_client.get_thinking_params(False)

        TestLogger.log_request(test_logger, messages, thinking_params_on)

        response1 = api_client.chat_completion(messages, extra_body=thinking_params_on)
        TestLogger.log_response(test_logger, response1, "开启thinking响应")
        self.log_full_response(test_logger, response1, "B3-开启thinking")

        self.assert_response_success(response1)
        has_thinking1 = self._check_has_thinking(response1, test_logger)
        assert has_thinking1, (
            "First request with thinking=ON should have thinking content"
        )

        content1 = self.get_message_content(response1)
        content1_clean = self._strip_thinking_tags(content1)
        assert len(content1_clean.strip()) > 0, (
            "Thinking mode response should have final answer"
        )

        test_logger.info("第2轮: 关闭thinking模式")
        TestLogger.log_request(test_logger, messages, thinking_params_off)

        response2 = api_client.chat_completion(messages, extra_body=thinking_params_off)
        TestLogger.log_response(test_logger, response2, "关闭thinking响应")
        self.log_full_response(test_logger, response2, "B3-关闭thinking")

        self.assert_response_success(response2)

        reasoning2 = self.get_reasoning_content(response2)
        assert reasoning2 is None or reasoning2 == "", (
            f"Thinking OFF should have no reasoning field, got: {reasoning2[:500]}"
        )

        content2 = self.get_message_content(response2)
        content2_clean = self._strip_thinking_tags(content2)
        assert len(content2_clean.strip()) > 0, (
            "Non-thinking response should have content"
        )
        assert any(kw in content2_clean for kw in ["56088", "56088.0"]), (
            f"Non-thinking mode should produce correct answer, got: {content2_clean[:500]}"
        )

        test_logger.info("思考模式切换测试通过")

    def _execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """模拟工具执行"""
        if tool_name == "get_weather":
            city = arguments.get("city", "")
            fallback_data = {
                "北京": {"temperature": 22, "humidity": 45, "condition": "晴朗"},
                "上海": {"temperature": 25, "humidity": 60, "condition": "多云"},
                "广州": {"temperature": 28, "humidity": 75, "condition": "雷阵雨"},
                "深圳": {"temperature": 27, "humidity": 80, "condition": "大雨"},
                "成都": {"temperature": 20, "humidity": 70, "condition": "阴天"},
                "杭州": {"temperature": 23, "humidity": 65, "condition": "晴朗"},
            }
            if city in fallback_data:
                data = fallback_data[city]
                return {
                    "city": city,
                    "temperature": data["temperature"],
                    "humidity": data["humidity"],
                    "condition": data["condition"],
                }
            return {
                "city": city,
                "temperature": 25,
                "humidity": 60,
                "condition": "晴朗",
            }
        elif tool_name == "get_stock_price":
            symbol = arguments.get("symbol", "").upper()
            fallback_prices = {
                "AAPL": {"price": 175.50, "currency": "USD"},
                "GOOGL": {"price": 140.25, "currency": "USD"},
                "MSFT": {"price": 380.00, "currency": "USD"},
                "TSLA": {"price": 245.30, "currency": "USD"},
                "SH600519": {"price": 1850.00, "currency": "CNY"},
                "SZ000001": {"price": 12.50, "currency": "CNY"},
                "SZ399001": {"price": 10500.00, "currency": "CNY"},
            }
            if symbol in fallback_prices:
                data = fallback_prices[symbol]
                return {
                    "symbol": symbol,
                    "price": data["price"],
                    "currency": data["currency"],
                }
            return {"symbol": symbol, "price": 100.00, "currency": "USD"}
        elif tool_name == "search_news":
            keyword = arguments.get("keyword", "")
            fallback_news = {
                "AI": [
                    "AI领域最新突破：大模型技术持续演进",
                    "ChatGPT用户突破10亿",
                    "国产大模型取得新进展",
                ],
                "科技": [
                    "科技创新推动产业升级",
                    "数字经济蓬勃发展",
                    "新技术应用改变生活",
                ],
                "经济": ["经济增长稳中向好", "消费市场持续回暖", "投资增速保持稳定"],
                "default": [
                    "今日要闻：多方面取得新进展",
                    "行业动态：技术创新引领发展",
                    "社会热点：民生关注度上升",
                ],
            }
            results = fallback_news.get(keyword, fallback_news["default"])
            return {"keyword": keyword, "results": results}
        elif tool_name == "calculate":
            try:
                result = eval(arguments.get("expression", "0"))
                return {"expression": arguments.get("expression"), "result": result}
            except:
                return {"expression": arguments.get("expression"), "result": "计算错误"}
        elif tool_name == "translate":
            text = arguments.get("text", "")
            target_lang = arguments.get("target_lang", "zh")
            translations = {
                ("hello", "zh"): "你好",
                ("world", "zh"): "世界",
                ("good morning", "zh"): "早上好",
                ("artificial intelligence", "zh"): "人工智能",
                ("你好", "en"): "hello",
                ("世界", "en"): "world",
                ("天气", "en"): "weather",
                ("时间", "en"): "time",
            }
            key = (text.lower().strip(), target_lang)
            result = translations.get(key, f"[翻译结果: {text} -> {target_lang}]")
            return {"text": text, "target_lang": target_lang, "result": result}
        elif tool_name == "get_time":
            from datetime import datetime, timezone, timedelta

            tz = arguments.get("timezone", "Asia/Shanghai")
            tz_map = {
                "Asia/Shanghai": 8,
                "Asia/Tokyo": 9,
                "America/New_York": -4,
                "America/Los_Angeles": -7,
                "Europe/London": 1,
                "Europe/Paris": 2,
            }
            offset_hours = tz_map.get(tz, 8)
            tz_obj = timezone(timedelta(hours=offset_hours))
            current_time = datetime.now(tz_obj).strftime("%Y-%m-%d %H:%M:%S")
            return {"timezone": tz, "time": current_time}
        elif tool_name == "get_seed_word":
            return {"word": "hello"}
        elif tool_name == "uppercase_word":
            return {
                "word": arguments.get("word"),
                "result": arguments.get("word", "").upper()
                if arguments.get("word")
                else "",
            }
        return {}

    def _execute_tool_call(self, api_client, messages, tool_call, test_logger):
        tool_call_id = tool_call.get("id")
        function_name = tool_call.get("function", {}).get("name")
        function_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))

        tool_result = self._execute_tool(function_name, function_args)
        test_logger.info(f"工具 [{function_name}] 执行结果: {tool_result}")

        messages.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": json.dumps(function_args),
                        },
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(tool_result),
            }
        )

        final_response = api_client.chat_completion(messages)
        self.log_full_response(
            test_logger, final_response, f"工具[{function_name}]最终响应"
        )
        final_content = self.get_message_content(final_response)
        test_logger.info(f"模型最终响应: {final_content}")
        return final_content, final_response

    def _execute_parallel_tool_calls(
        self, api_client, messages, tool_calls, tools, test_logger
    ):
        tool_results = []
        for tool_call in tool_calls:
            tool_call_id = tool_call.get("id")
            function_name = tool_call.get("function", {}).get("name")
            function_args = json.loads(
                tool_call.get("function", {}).get("arguments", "{}")
            )

            tool_result = self._execute_tool(function_name, function_args)
            test_logger.info(f"工具 [{function_name}] 执行结果: {tool_result}")
            tool_results.append(
                {
                    "id": tool_call_id,
                    "function_name": function_name,
                    "function_args": function_args,
                    "result": tool_result,
                }
            )

        messages.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": tr["id"],
                        "type": "function",
                        "function": {
                            "name": tr["function_name"],
                            "arguments": json.dumps(tr["function_args"]),
                        },
                    }
                    for tr in tool_results
                ],
            }
        )

        for tr in tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tr["id"],
                    "content": json.dumps(tr["result"]),
                }
            )

        final_response = api_client.chat_completion(
            messages, tools=tools, tool_choice="auto"
        )
        self.log_full_response(test_logger, final_response, "并行工具调用最终响应")
        final_content = self.get_message_content(final_response)
        test_logger.info(f"模型最终响应: {final_content}")
        return final_content, final_response

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_single_tool_call(self, api_client: ModelAPIClient, test_logger):
        """B4: 工具调用-单工具 - 定义单个function"""
        test_logger.info("=== 测试开始: 单工具调用 ===")

        messages = [{"role": "user", "content": "北京今天天气怎么样？"}]
        TestLogger.log_request(test_logger, messages, {"tools": "TOOLS_GET_WEATHER"})

        response = api_client.chat_completion(
            messages, tools=TOOLS_GET_WEATHER, tool_choice="auto"
        )
        TestLogger.log_response(test_logger, response, "单工具调用响应")
        self.log_full_response(test_logger, response, "B4-单工具调用")

        self.assert_response_success(response)

        tool_calls = self.get_tool_calls(response)
        assert len(tool_calls) > 0, "Should have tool calls"

        tool_name = tool_calls[0].get("function", {}).get("name")
        assert tool_name == "get_weather", (
            f"Expected tool 'get_weather', got '{tool_name}'"
        )

        assert tool_calls[0].get("id") is not None, "Tool call should have 'id' field"
        assert len(tool_calls[0].get("id", "")) > 0, "Tool call id should not be empty"

        arguments_raw = tool_calls[0].get("function", {}).get("arguments", "{}")
        try:
            args = (
                json.loads(arguments_raw)
                if isinstance(arguments_raw, str)
                else arguments_raw
            )
        except json.JSONDecodeError as e:
            pytest.fail(
                f"Tool call arguments is not valid JSON: {arguments_raw}, error: {e}"
            )

        assert "city" in args, f"Should have 'city' parameter, got args: {args}"
        assert args["city"].strip() != "", "City parameter should not be empty"
        test_logger.info(f"Tool call: {tool_name}({args})")

        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
        assert finish_reason == "tool_calls", (
            f"When tool is called, finish_reason should be 'tool_calls', got '{finish_reason}'"
        )

        final_content, final_response = self._execute_tool_call(
            api_client, messages, tool_calls[0], test_logger
        )
        self.assert_response_success(final_response)
        assert len(final_content.strip()) > 0, (
            "Final response after tool execution should not be empty"
        )

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_multiple_tool_call(self, api_client: ModelAPIClient, test_logger):
        """B5: 工具调用-多工具 - 定义多个function，验证模型选择正确的工具"""
        test_logger.info("=== 测试开始: 多工具调用（5个工具） ===")

        tools = TOOLS_FIVE

        test_cases = [
            ("天气相关问题", "北京今天天气怎么样？", "get_weather"),
            ("股票相关问题", "现在苹果公司(AAPL)的股价是多少？", "get_stock_price"),
            ("新闻搜索问题", "搜索关于人工智能的最新新闻", "search_news"),
            ("数学计算问题", "帮我计算一下 123 + 456 等于多少？", "calculate"),
            ("翻译问题", "把 Hello 翻译成中文", "translate"),
        ]

        for idx, (desc, user_msg, expected_tool) in enumerate(test_cases, 1):
            test_logger.info(f"【测试{idx}】{desc} -> 应选择 {expected_tool}")
            messages = [{"role": "user", "content": user_msg}]
            TestLogger.log_request(test_logger, messages, {"tools": "5 tools"})

            response = api_client.chat_completion(
                messages, tools=tools, tool_choice="auto"
            )
            TestLogger.log_response(test_logger, response, f"{desc}工具调用")
            self.log_full_response(test_logger, response, f"B5-测试{idx}-{desc}")

            self.assert_response_success(response)
            tool_calls = self.get_tool_calls(response)
            assert len(tool_calls) > 0, (
                f"[测试{idx}] Should have tool calls for '{desc}'"
            )

            tool_name = tool_calls[0].get("function", {}).get("name")
            test_logger.info(f"Selected tool: {tool_name}")
            assert tool_name == expected_tool, (
                f"[测试{idx}] Expected '{expected_tool}', got '{tool_name}'"
            )

            assert tool_calls[0].get("id") is not None, (
                f"[测试{idx}] Tool call should have 'id' field"
            )

            arguments_raw = tool_calls[0].get("function", {}).get("arguments", "{}")
            try:
                args = (
                    json.loads(arguments_raw)
                    if isinstance(arguments_raw, str)
                    else arguments_raw
                )
            except json.JSONDecodeError as e:
                pytest.fail(f"[测试{idx}] Invalid JSON in arguments: {arguments_raw}")

            assert isinstance(args, dict) and len(args) > 0, (
                f"[测试{idx}] Tool arguments should be non-empty dict, got: {args}"
            )

            self._execute_tool_call(api_client, messages, tool_calls[0], test_logger)

        test_logger.info("多工具调用测试完成")

    @pytest.mark.b_advanced
    @pytest.mark.p1
    def test_parallel_tool_calls(self, api_client: ModelAPIClient, test_logger):
        """B6: 工具调用-并行调用 - 单次回复中并行调用多个工具"""
        test_logger.info("=== 测试开始: 并行工具调用 ===")

        messages = [{"role": "user", "content": "请帮我查一下北京今天的天气和时间"}]
        TestLogger.log_request(test_logger, messages, {"tools": "TOOLS_MULTIPLE"})

        response = api_client.chat_completion(
            messages, tools=TOOLS_MULTIPLE, tool_choice="auto"
        )
        TestLogger.log_response(test_logger, response, "并行工具调用响应")
        self.log_full_response(test_logger, response, "B6-并行工具调用")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response)

        test_logger.info(f"工具调用数量: {len(tool_calls)}")
        assert len(tool_calls) > 0, "Should have tool calls"

        called_tools = set()
        for tc in tool_calls:
            fn_name = tc.get("function", {}).get("name")
            assert fn_name is not None, "Tool call should have function name"
            assert tc.get("id") is not None, (
                f"Tool call '{fn_name}' should have 'id' field"
            )
            called_tools.add(fn_name)

            arguments_raw = tc.get("function", {}).get("arguments", "{}")
            try:
                args = (
                    json.loads(arguments_raw)
                    if isinstance(arguments_raw, str)
                    else arguments_raw
                )
            except json.JSONDecodeError:
                pytest.fail(
                    f"Tool '{fn_name}' arguments is not valid JSON: {arguments_raw}"
                )

            assert isinstance(args, dict), f"Tool '{fn_name}' arguments should be dict"

        test_logger.info(f"调用的工具集合: {called_tools}")
        assert called_tools.issubset({"get_weather", "get_time"}), (
            f"Called tools should be subset of available tools, got: {called_tools}"
        )

        if len(tool_calls) >= 2:
            test_logger.info("模型并行调用了多个工具")

        final_content, final_response = self._execute_parallel_tool_calls(
            api_client, messages, tool_calls, TOOLS_MULTIPLE, test_logger
        )
        self.assert_response_success(final_response)
        assert len(final_content.strip()) > 0, "Final response should not be empty"

    @pytest.mark.b_advanced
    @pytest.mark.p1
    def test_multi_step_tool_chain(self, api_client: ModelAPIClient, test_logger):
        """B7: 工具调用-多步链式 - 工具结果作为下一步输入，验证3+步链式执行"""
        test_logger.info("=== 测试开始: 多步外部API工具链(3步) ===")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "获取指定时区的当前时间",
                    "parameters": {
                        "type": "object",
                        "properties": {"timezone": {"type": "string"}},
                        "required": ["timezone"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "获取城市天气",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "translate",
                    "description": "翻译文本到指定语言",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "target_lang": {"type": "string"},
                        },
                        "required": ["text", "target_lang"],
                    },
                },
            },
        ]

        messages = [
            {
                "role": "user",
                "content": "请获取上海的当前时间，然后查询当前的天气，最后将天气信息翻译成英文",
            }
        ]
        TestLogger.log_request(
            test_logger,
            messages,
            {"tools": "3 tools (get_time + get_weather + translate)"},
        )

        # 第1步: 调用get_time获取当前时间
        test_logger.info("第1步: 调用get_time获取上海当前时间")
        response1 = api_client.chat_completion(
            messages, tools=tools, tool_choice="auto"
        )
        TestLogger.log_response(test_logger, response1, "第1步响应")
        self.log_full_response(test_logger, response1, "B7-第1步")

        tool_calls = self.get_tool_calls(response1)
        if len(tool_calls) == 0:
            pytest.skip("Model does not support multi-step tool chain")

        tool_call = tool_calls[0]
        function_name = tool_call.get("function", {}).get("name")
        function_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
        tool_result = self._execute_tool(function_name, function_args)
        test_logger.info(f"工具 [{function_name}] 执行结果: {tool_result}")

        # 校验第1步结果
        assert function_name == "get_time", f"Expected get_time, got {function_name}"
        assert function_args.get("timezone") is not None, (
            "get_time should have timezone parameter"
        )
        assert "time" in tool_result, "Expected 'time' in tool result"

        messages.append(response1["choices"][0]["message"])
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.get("id"),
                "content": json.dumps(tool_result),
            }
        )

        # 第2步: 调用get_weather获取当前天气
        test_logger.info("第2步: 调用get_weather获取上海当前天气")
        response2 = api_client.chat_completion(
            messages, tools=tools, tool_choice="auto"
        )
        TestLogger.log_response(test_logger, response2, "第2步响应")
        self.log_full_response(test_logger, response2, "B7-第2步")

        tool_calls2 = self.get_tool_calls(response2)
        if len(tool_calls2) == 0:
            pytest.skip("Model did not call get_weather tool")

        tool_call2 = tool_calls2[0]
        function_name2 = tool_call2.get("function", {}).get("name")
        function_args2 = json.loads(
            tool_call2.get("function", {}).get("arguments", "{}")
        )
        tool_result2 = self._execute_tool(function_name2, function_args2)
        test_logger.info(f"工具 [{function_name2}] 执行结果: {tool_result2}")

        # 校验第2步调用
        assert function_name2 == "get_weather", (
            f"Expected get_weather, got {function_name2}"
        )
        assert function_args2.get("city") is not None, (
            "get_weather should have city parameter"
        )
        assert "temperature" in tool_result2, "Expected 'temperature' in tool result"
        assert "condition" in tool_result2, "Expected 'condition' in tool result"

        weather_info = f"{tool_result2.get('city')}当前天气: {tool_result2.get('condition')}, 温度: {tool_result2.get('temperature')}度"
        test_logger.info(f"天气信息: {weather_info}")

        messages.append(response2["choices"][0]["message"])
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call2.get("id"),
                "content": json.dumps(tool_result2),
            }
        )

        # 第3步: 调用translate翻译天气信息
        test_logger.info("第3步: 调用translate翻译天气信息为英文")
        response3 = api_client.chat_completion(
            messages, tools=tools, tool_choice="auto"
        )
        TestLogger.log_response(test_logger, response3, "第3步响应")
        self.log_full_response(test_logger, response3, "B7-第3步")

        tool_calls3 = self.get_tool_calls(response3)
        if len(tool_calls3) == 0:
            pytest.skip("Model did not call translate tool")

        tool_call3 = tool_calls3[0]
        function_name3 = tool_call3.get("function", {}).get("name")
        function_args3 = json.loads(
            tool_call3.get("function", {}).get("arguments", "{}")
        )
        tool_result3 = self._execute_tool(function_name3, function_args3)
        test_logger.info(f"工具 [{function_name3}] 执行结果: {tool_result3}")

        # 校验第3步调用
        assert function_name3 == "translate", (
            f"Expected translate, got {function_name3}"
        )
        assert "text" in function_args3, "Expected 'text' in function arguments"
        assert "target_lang" in function_args3, (
            "Expected 'target_lang' in function arguments"
        )
        assert function_args3.get("target_lang", "").lower() in (
            "en",
            "english",
            "英文",
        ), (
            f"Expected target_lang to be English/en, got: {function_args3.get('target_lang')}"
        )

        # 校验第3步结果
        assert "result" in tool_result3, "Expected 'result' in tool_result3"
        test_logger.info(f"翻译结果: {tool_result3['result']}")

        self.assert_response_success(response3)
        test_logger.info("3步外部API工具链测试完成")

    @pytest.mark.b_advanced
    @pytest.mark.p0
    def test_json_mode(self, api_client: ModelAPIClient, test_logger):
        """B8: JSON Mode - response_format=json_object"""
        test_logger.info("=== 测试开始: JSON Mode ===")

        messages = [
            {
                "role": "system",
                "content": "你是一个JSON生成器，请始终返回合法的JSON对象",
            },
            {"role": "user", "content": "请返回一个包含姓名和年龄的JSON对象"},
        ]
        TestLogger.log_request(
            test_logger, messages, {"response_format": "json_object"}
        )

        response = api_client.chat_completion(
            messages, response_format={"type": "json_object"}
        )
        TestLogger.log_response(test_logger, response, "JSON Mode响应")
        self.log_full_response(test_logger, response, "B8-JSON-Mode")

        self.assert_response_success(response)

        content = self.get_message_content(response)

        json_data = None
        json_error = None

        if content and content.strip():
            try:
                json_data = json.loads(content.strip())
            except json.JSONDecodeError:
                try:
                    json_data = extract_json_from_text(content)
                except ValueError as e:
                    json_error = f"Failed to parse JSON from content: {e}"

        if json_data is None:
            reasoning = self.get_reasoning_content(response)
            if reasoning:
                try:
                    json_data = json.loads(reasoning.strip())
                except json.JSONDecodeError:
                    try:
                        json_data = extract_json_from_text(reasoning)
                    except ValueError as e:
                        json_error = f"JSON not found in content or reasoning. Content: {content[:500]}"

        if json_data is None:
            pytest.fail(json_error or "No valid JSON found in response")

        assert isinstance(json_data, dict), (
            f"Should return a JSON object (dict), got {type(json_data).__name__}"
        )
        test_logger.info(f"JSON response: {json_data}")

        assert len(json_data) > 0, "JSON object should not be empty"

        has_name_field = any(k in json_data for k in ["name", "姓名", "名字"])
        has_age_field = any(k in json_data for k in ["age", "年龄", "岁数"])
        assert has_name_field, (
            f"JSON should contain a name-related field, got keys: {list(json_data.keys())}"
        )
        assert has_age_field, (
            f"JSON should contain an age-related field, got keys: {list(json_data.keys())}"
        )

        age_value = (
            json_data.get("age") or json_data.get("年龄") or json_data.get("岁数")
        )
        if age_value is not None:
            assert isinstance(age_value, (int, float)), (
                f"Age field should be numeric, got {type(age_value).__name__}: {age_value}"
            )

    @pytest.mark.b_advanced
    @pytest.mark.p0
    def test_structured_output(self, api_client: ModelAPIClient, test_logger):
        """B9: 结构化输出 - JSON Schema约束输出格式"""
        test_logger.info("=== 测试开始: 结构化输出 ===")

        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "姓名"},
                "age": {"type": "integer", "description": "年龄"},
                "city": {"type": "string", "description": "城市"},
            },
            "required": ["name", "age"],
        }

        messages = [
            {"role": "user", "content": "请返回一个包含姓名、年龄和城市的JSON对象"}
        ]
        TestLogger.log_request(
            test_logger, messages, {"response_format": "json_schema"}
        )

        response = api_client.chat_completion(
            messages, response_format={"type": "json_object", "schema": schema}
        )
        TestLogger.log_response(test_logger, response, "结构化输出响应")
        self.log_full_response(test_logger, response, "B9-结构化输出")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        reasoning = self.get_reasoning_content(response)

        json_data = None
        source = None

        # 处理 content 中包含 </think> 思考内容的情况
        if content and "</think>" in content:
            content = content.split("</think>", 1)[1].strip()
            test_logger.info(f"Extracted JSON after </think>: {content[:2000]}...")

        # 优先从 content 提取 JSON
        if content and content.strip():
            try:
                json_data = extract_json_from_text(content)
                source = "content"
            except ValueError:
                test_logger.warning(
                    f"Failed to extract JSON from content: {content[:2000]}..."
                )

        # 如果 content 没有 JSON，尝试从 reasoning 提取
        if json_data is None and reasoning:
            try:
                json_data = extract_json_from_text(reasoning)
                source = "reasoning"
            except ValueError:
                test_logger.warning(
                    f"Failed to extract JSON from reasoning: {reasoning[:2000]}..."
                )

        if json_data is None:
            pytest.fail("No valid JSON found in content or reasoning")

        test_logger.info(f"Structured output found in {source}: {json_data}")

        has_name = "name" in json_data or "姓名" in json_data
        has_age = "age" in json_data or "年龄" in json_data
        assert has_name, (
            f"Should have 'name' or '姓名' field, got keys: {list(json_data.keys())}"
        )
        assert has_age, (
            f"Should have 'age' or '年龄' field, got keys: {list(json_data.keys())}"
        )

        assert isinstance(json_data, dict), (
            f"Should return a JSON object, got {type(json_data).__name__}"
        )

        age_value = json_data.get("age") or json_data.get("年龄")
        if age_value is not None:
            assert isinstance(age_value, int), (
                f"'age' field should be integer per schema, got {type(age_value).__name__}: {age_value}"
            )

        name_value = json_data.get("name") or json_data.get("姓名")
        if name_value is not None:
            assert isinstance(name_value, str) and len(name_value.strip()) > 0, (
                f"'name' field should be non-empty string, got: {name_value}"
            )

        test_logger.info("结构化输出验证通过")

    @pytest.mark.b_advanced
    @pytest.mark.p2
    def test_prefix_suffix_constraint(self, api_client: ModelAPIClient, test_logger):
        """B10: Prefix / Suffix 约束 - 指定输出前缀或格式模板"""
        test_logger.info("=== 测试开始: Prefix/Suffix 约束 ===")

        # ========== 测试 prefix 约束 ==========
        test_logger.info("【测试1】Prefix 约束：回答必须以 '答案是：' 开头")
        messages = [{"role": "user", "content": "1+1等于多少？"}]
        TestLogger.log_request(test_logger, messages)

        # 使用 prefix 参数（如果API支持）
        try:
            response = api_client.chat_completion(messages, prefix="答案是：")
        except Exception as e:
            if "prefix" in str(e).lower() or "unsupported" in str(e).lower():
                pytest.skip(f"API不支持prefix参数: {e}")
            raise

        TestLogger.log_response(test_logger, response, "Prefix约束响应")
        self.log_full_response(test_logger, response, "B10-Prefix约束")

        self.assert_response_success(response)
        content = self.get_message_content(response)

        test_logger.info(f"Prefix 约束响应: {content[:2000]}...")

        assert content is not None and len(content.strip()) > 0, (
            "Prefix constraint response should not be empty"
        )
        assert content.strip().startswith("答案是："), (
            f"Prefix约束未遵循，期望以'答案是：'开头，实际回复: {content[:500]}"
        )

        # ========== 测试 suffix 约束 ==========
        test_logger.info("【测试2】Suffix 约束：回答必须以 '完毕。' 结尾")
        messages = [{"role": "user", "content": "请用一句话介绍北京。"}]
        TestLogger.log_request(test_logger, messages)

        # 使用 suffix 参数
        try:
            response = api_client.chat_completion(messages, suffix="完毕。")
        except Exception as e:
            if "suffix" in str(e).lower() or "unsupported" in str(e).lower():
                pytest.skip(f"API不支持suffix参数: {e}")
            raise

        TestLogger.log_response(test_logger, response, "Suffix约束响应")
        self.log_full_response(test_logger, response, "B10-Suffix约束")

        self.assert_response_success(response)
        content = self.get_message_content(response)


        test_logger.info(f"Suffix 约束响应: {content[:2000]}...")

        assert content is not None and len(content.strip()) > 0, (
            "Suffix constraint response should not be empty"
        )
        assert content.strip().endswith("完毕。"), (
            f"Suffix约束未遵循，期望以'完毕。'结尾，实际回复: {content[:500]}"
        )

        test_logger.info("Prefix/Suffix 约束测试完成")
