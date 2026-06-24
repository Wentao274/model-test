"""
B. 高级生成功能测试

测试点：
- B1: 思考模式（Thinking）- 开启thinking mode，验证返回思考链+最终答案 [P0]
- B2: 非思考模式（Instant）- 关闭thinking，验证无hidden thinking泄漏 [P1]
- B3: 思考模式切换 - 同一会话内thinking↔non-thinking切换 [P1]
- B4: 工具调用-单工具 - 定义单个function，验证模型正确调用并传参 [P0]
- B5: 工具调用-多工具 - 定义多个function，验证模型选择正确的工具 [P1]
- B6: 工具调用-并行调用 - 单次回复中并行调用多个工具 [P2]
- B7: 工具调用-多步链式 - 工具结果作为下一步输入，验证3+步链式执行 [P1]
- B8: JSON Mode - response_format=json_object，验证输出合法JSON [P0]
- B9: 结构化输出 - JSON Schema约束输出格式，验证字段完整性 [P0]
- B10: Prefix / Suffix 约束 - 指定输出前缀或格式模板，验证遵循度 [P2]
"""

import json
import re
import urllib.request
import urllib.parse
import json as json_lib
import pytest
from datetime import datetime
from typing import List, Dict, Any, Tuple

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

    # 尝试提取第一个完整的JSON对象
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    json_str = text[start : i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        break

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

    def _chat_with_thinking_fallback(
        self,
        api_client: ModelAPIClient,
        messages: List[Dict[str, Any]],
        test_logger,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str, bool]:
        """
        自动尝试多种思考模式参数格式（不依赖 config.yaml 配置）

        策略顺序：
            1. {"enable_thinking": True}  - 顶层字段（OpenAI/Qwen 等）
            2. {"chat_template_kwargs": {"thinking": True}}  - chat_template 方式
            3. {"thinking": {"type": "enabled"}}  - 顶层对象（DeepSeek/GLM 等）
            4. chat_template_kwargs.thinking + reasoning_effort=high
                - 部分 vLLM/SGLang 部署需要 reasoning_effort 才会触发思考

        Args:
            api_client: API 客户端
            messages: 请求消息列表
            test_logger: 测试日志器

        Returns:
            (response, used_params, strategy_name, has_thinking)
            - response: 最后一次（成功的或最后一次失败的）响应
            - used_params: 实际生效的参数
            - strategy_name: 策略名称（如 'enable_thinking'）
            - has_thinking: 是否成功获取到思考内容
        """
        strategies = [
            ("enable_thinking", {"enable_thinking": True}),
            (
                "chat_template_kwargs.thinking",
                {"chat_template_kwargs": {"thinking": True}},
            ),
            (
                "thinking.type.enabled",
                {"thinking": {"type": "enabled"}},
            ),
            (
                "chat_template_kwargs.thinking+reasoning_effort",
                {
                    "chat_template_kwargs": {"thinking": True},
                    "reasoning_effort": "high",
                },
            ),
        ]

        last_response = None
        last_params = None
        last_strategy = None

        for idx, (strategy_name, params) in enumerate(strategies, 1):
            test_logger.info(
                f"[{idx}/{len(strategies)}] 尝试思考参数策略: "
                f"{strategy_name} -> {params}"
            )
            try:
                response = api_client.chat_completion(messages, extra_body=params)
            except Exception as e:
                test_logger.warning(f"策略 {strategy_name} 请求异常: {e}，尝试下一策略")
                last_strategy = strategy_name
                last_params = params
                continue

            self.assert_response_success(response)
            has_thinking = self._check_has_thinking(response, test_logger)

            if has_thinking:
                test_logger.info(f"策略 {strategy_name} 成功获取到思考内容")
                return response, params, strategy_name, True

            test_logger.warning(
                f"策略 {strategy_name} 未获取到思考内容，将尝试下一策略"
            )
            last_response = response
            last_params = params
            last_strategy = strategy_name

        return last_response, last_params, last_strategy, False

    def _chat_without_thinking_fallback(
        self,
        api_client: ModelAPIClient,
        messages: List[Dict[str, Any]],
        test_logger,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], str, bool]:
        """
        自动尝试多种关闭思考模式的参数格式（不依赖 config.yaml 配置）

        策略顺序：
            1. {} - 不传 thinking 参数（依赖模型默认行为）
            2. {"enable_thinking": False} - 顶层字段显式关闭
            3. {"chat_template_kwargs": {"thinking": False}} - chat_template 方式
            4. {"thinking": {"type": "disabled"}} - 顶层对象（DeepSeek/GLM 等）

        任一策略无思考内容泄漏即返回；若全部仍泄漏，则 has_no_thinking=False。

        Returns:
            (response, used_params, strategy_name, has_no_thinking)
        """
        strategies = [
            ("no_thinking_params", {}),
            ("enable_thinking_false", {"enable_thinking": False}),
            (
                "chat_template_kwargs.thinking_false",
                {"chat_template_kwargs": {"thinking": False}},
            ),
            (
                "thinking.type.disabled",
                {"thinking": {"type": "disabled"}},
            ),
        ]

        last_response = None
        last_params = None
        last_strategy = None

        for idx, (strategy_name, params) in enumerate(strategies, 1):
            display_params = params if params else "(空)"
            test_logger.info(
                f"[{idx}/{len(strategies)}] 尝试非思考策略: "
                f"{strategy_name} -> {display_params}"
            )
            try:
                response = api_client.chat_completion(messages, extra_body=params)
            except Exception as e:
                test_logger.warning(f"策略 {strategy_name} 请求异常: {e}，尝试下一策略")
                last_strategy = strategy_name
                last_params = params
                continue

            self.assert_response_success(response)
            has_thinking = self._check_has_thinking(response, test_logger)

            if not has_thinking:
                test_logger.info(f"策略 {strategy_name} 成功获取到无思考泄漏的响应")
                return response, params, strategy_name, True

            test_logger.warning(
                f"策略 {strategy_name} 检测到思考内容泄漏，将尝试下一策略"
            )
            last_response = response
            last_params = params
            last_strategy = strategy_name

        return last_response, last_params, last_strategy, False

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_thinking_mode(self, api_client: ModelAPIClient, test_logger):
        """B1: 思考模式（Thinking）- 开启thinking mode

        不依赖 config.yaml 配置，自动按以下顺序尝试参数格式：
        1. enable_thinking=true (顶层字段)
        2. chat_template_kwargs={"thinking": true}
        3. thinking={"type": "enabled"} (DeepSeek/GLM 风格)
        4. chat_template_kwargs.thinking=true + reasoning_effort=high
        若四种方式均未获取到思考内容，则断言失败。
        """
        test_logger.info("=== 测试开始: 思考模式（自动回退） ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "thinking_mode": (
                    "auto-fallback on (enable_thinking "
                    "-> chat_template_kwargs.thinking "
                    "-> thinking.type=enabled "
                    "-> chat_template_kwargs.thinking+reasoning_effort)"
                )
            },
        )

        (
            response,
            used_params,
            strategy,
            has_thinking,
        ) = self._chat_with_thinking_fallback(api_client, messages, test_logger)
        TestLogger.log_response(
            test_logger, response, f"思考模式响应 (策略: {strategy})"
        )
        self.log_full_response(test_logger, response, f"B1-思考模式 [{strategy}]")

        self.assert_content_not_empty(response)

        assert has_thinking, (
            "Thinking mode should return reasoning content (reasoning field or thinking tags). "
            "Tried strategies: enable_thinking, chat_template_kwargs.thinking, "
            "thinking.type=enabled, chat_template_kwargs.thinking+reasoning_effort. "
            f"Last params: {used_params}"
        )

        content = self.get_message_content(response)
        content_clean = self._strip_thinking_tags(content)
        test_logger.info(f"最终回答内容: {content_clean[:2000]}...")

        assert len(content_clean.strip()) > 0, (
            "Final answer content should not be empty"
        )
        assert any(kw in content_clean for kw in ["56088", "56088.0", "56,088"]), (
            f"Thinking mode should produce correct answer 56088, got: {content_clean[:500]}"
        )

        test_logger.info(f"思考模式验证通过 (使用策略: {strategy})")

    @pytest.mark.b_advanced
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_non_thinking_mode(self, api_client: ModelAPIClient, test_logger):
        """B2 [P1]: 非思考模式（Instant）- 关闭thinking，无泄漏

        不依赖 config.yaml 配置，自动按以下顺序尝试关闭思考模式：
        1. 不传 thinking 参数（依赖模型默认行为）
        2. enable_thinking=false (顶层字段)
        3. chat_template_kwargs={"thinking": false}
        4. thinking={"type": "disabled"} (DeepSeek/GLM 风格)
        若四种方式均存在思考内容泄漏，则断言失败。
        """
        test_logger.info("=== 测试开始: 非思考模式（自动回退） ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "thinking_mode": (
                    "auto-fallback off (no_params -> enable_thinking:false "
                    "-> chat_template_kwargs.thinking:false "
                    "-> thinking.type=disabled)"
                )
            },
        )

        (
            response,
            used_params,
            strategy,
            has_no_thinking,
        ) = self._chat_without_thinking_fallback(api_client, messages, test_logger)
        TestLogger.log_response(
            test_logger, response, f"非思考模式响应 (策略: {strategy})"
        )
        self.log_full_response(test_logger, response, f"B2-非思考模式 [{strategy}]")

        self.assert_content_not_empty(response)

        assert has_no_thinking, (
            "Non-thinking mode should not leak any reasoning content. "
            "Tried strategies: no_thinking_params, enable_thinking:false, "
            "chat_template_kwargs.thinking:false, thinking.type=disabled. "
            f"Last params: {used_params}"
        )

        content = self.get_message_content(response)
        content_clean = self._strip_thinking_tags(content)
        test_logger.info(f"最终回答内容: {content_clean[:2000]}...")

        assert len(content_clean.strip()) > 0, (
            "Non-thinking mode should still produce a content response"
        )
        assert any(kw in content_clean for kw in ["56088", "56088.0", "56,088"]), (
            f"Non-thinking mode should produce correct answer 56088, got: {content_clean[:500]}"
        )

        test_logger.info(f"非思考模式测试通过 (使用策略: {strategy})，无thinking泄漏")

    @pytest.mark.b_advanced
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_thinking_mode_switch(self, api_client: ModelAPIClient, test_logger):
        """B3: 思考模式切换 - 同一会话内thinking↔non-thinking切换

        开启部分采用自动回退策略：
            enable_thinking=true -> chat_template_kwargs={"thinking": true}
            -> thinking={"type": "enabled"}
            -> chat_template_kwargs.thinking=true + reasoning_effort=high
        关闭部分采用自动回退策略：
            no_params -> enable_thinking=false -> chat_template_kwargs={"thinking": false}
            -> thinking={"type": "disabled"}
        """
        test_logger.info("=== 测试开始: 思考模式切换 ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]

        test_logger.info("第1轮: 开启thinking模式（自动回退）")
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "thinking_mode": (
                    "auto-fallback on (enable_thinking "
                    "-> chat_template_kwargs.thinking "
                    "-> thinking.type=enabled "
                    "-> chat_template_kwargs.thinking+reasoning_effort)"
                )
            },
        )

        (
            response1,
            used_params1,
            strategy1,
            has_thinking1,
        ) = self._chat_with_thinking_fallback(api_client, messages, test_logger)
        TestLogger.log_response(
            test_logger, response1, f"开启thinking响应 (策略: {strategy1})"
        )
        self.log_full_response(test_logger, response1, f"B3-开启thinking [{strategy1}]")

        self.assert_content_not_empty(response1)
        assert has_thinking1, (
            "First request with thinking=ON should have thinking content. "
            "Tried strategies: enable_thinking, chat_template_kwargs.thinking, "
            "thinking.type=enabled, chat_template_kwargs.thinking+reasoning_effort. "
            f"Last params: {used_params1}"
        )

        content1 = self.get_message_content(response1)
        content1_clean = self._strip_thinking_tags(content1)
        assert len(content1_clean.strip()) > 0, (
            "Thinking mode response should have final answer"
        )

        test_logger.info("第2轮: 关闭thinking模式（自动回退）")
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "thinking_mode": (
                    "auto-fallback off (no_params -> enable_thinking:false "
                    "-> chat_template_kwargs.thinking:false "
                    "-> thinking.type=disabled)"
                )
            },
        )

        (
            response2,
            used_params2,
            strategy2,
            has_no_thinking2,
        ) = self._chat_without_thinking_fallback(api_client, messages, test_logger)
        TestLogger.log_response(
            test_logger, response2, f"关闭thinking响应 (策略: {strategy2})"
        )
        self.log_full_response(test_logger, response2, f"B3-关闭thinking [{strategy2}]")

        self.assert_content_not_empty(response2)
        assert has_no_thinking2, (
            "Second request with thinking=OFF should have no thinking content. "
            "Tried strategies: no_thinking_params, enable_thinking:false, "
            "chat_template_kwargs.thinking:false, thinking.type=disabled. "
            f"Last params: {used_params2}"
        )

        content2 = self.get_message_content(response2)
        content2_clean = self._strip_thinking_tags(content2)
        assert len(content2_clean.strip()) > 0, (
            "Non-thinking response should have content"
        )
        assert any(kw in content2_clean for kw in ["56088", "56088.0", "56,088"]), (
            f"Non-thinking mode should produce correct answer, got: {content2_clean[:500]}"
        )

        test_logger.info(
            f"思考模式切换测试通过 (开启策略: {strategy1}, 关闭策略: {strategy2})"
        )

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
        elif tool_name == "send_email":
            return {
                "status": "sent",
                "to": arguments.get("to", ""),
                "subject": arguments.get("subject", ""),
                "message_id": f"msg_{hash(arguments.get('body', '')) % 10000:04d}",
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

        tool_calls = self.get_tool_calls(response) or []
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
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_multiple_tool_call(self, api_client: ModelAPIClient, test_logger):
        """B5 [P1]: 工具调用-多工具 - 定义多个function，验证模型选择正确的工具"""
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
            tool_calls = self.get_tool_calls(response) or []
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
    @pytest.mark.p2
    def test_parallel_tool_calls(self, api_client: ModelAPIClient, test_logger):
        """B6 [P2]: 工具调用-并行调用 - 单次回复中并行调用多个工具"""
        test_logger.info("=== 测试开始: 并行工具调用 ===")

        messages = [{"role": "user", "content": "请帮我查一下北京今天的天气和时间"}]
        TestLogger.log_request(test_logger, messages, {"tools": "TOOLS_MULTIPLE"})

        response = api_client.chat_completion(
            messages, tools=TOOLS_MULTIPLE, tool_choice="auto"
        )
        TestLogger.log_response(test_logger, response, "并行工具调用响应")
        self.log_full_response(test_logger, response, "B6-并行工具调用")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response) or [] or []

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
    def test_multi_step_tool_chain(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """B7: 工具调用-多步链式 - 工具结果作为下一步输入，验证3+步链式执行"""
        test_logger.info("=== 测试开始: 多步外部API工具链(3步) ===")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "获取指定城市的当前天气信息，包括温度、湿度、天气状况",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "城市名称"}
                        },
                        "required": ["city"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "执行数学计算表达式并返回结果",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "数学表达式",
                            },
                        },
                        "required": ["expression"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "发送邮件给指定收件人。必须通过此工具发送邮件，无法自行发送。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "收件人邮箱地址",
                            },
                            "subject": {
                                "type": "string",
                                "description": "邮件主题",
                            },
                            "body": {
                                "type": "string",
                                "description": "邮件正文内容",
                            },
                        },
                        "required": ["to", "subject", "body"],
                    },
                },
            },
        ]

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个助手，必须通过调用工具来完成任务。"
                    "请按顺序依次调用工具：先用get_weather查询天气，"
                    "再用calculate计算温差，最后用send_email将结果发送邮件。"
                    "发送邮件必须调用send_email工具，你无法自行发送邮件。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请帮我完成以下任务：1) 查询上海的天气 2) 计算上海温度与0度的温差 "
                    "3) 将天气和温差信息通过邮件发送给 user@example.com，"
                    "邮件主题为'上海天气报告'。"
                    "请逐步调用工具完成。"
                ),
            },
        ]
        TestLogger.log_request(
            test_logger,
            messages,
            {"tools": "3 tools (get_weather + calculate + send_email)"},
        )

        called_tools = set()
        tool_results_map = {}
        max_steps = 5
        step = 0

        while step < max_steps:
            step += 1
            test_logger.info(f"第{step}步: 发送请求")

            response = api_client.chat_completion(
                messages, tools=tools, tool_choice="auto"
            )
            TestLogger.log_response(test_logger, response, f"第{step}步响应")
            self.log_full_response(test_logger, response, f"B7-第{step}步")

            tool_calls = self.get_tool_calls(response) or []

            if len(tool_calls) == 0:
                test_logger.info(f"第{step}步: 模型未调用工具，链式调用结束")
                break

            for tool_call in tool_calls:
                function_name = tool_call.get("function", {}).get("name")
                function_args = json.loads(
                    tool_call.get("function", {}).get("arguments", "{}")
                )
                tool_result = self._execute_tool(function_name, function_args)
                test_logger.info(
                    f"第{step}步工具 [{function_name}] 执行结果: {tool_result}"
                )

                assert function_name in ("get_weather", "calculate", "send_email"), (
                    f"Expected one of [get_weather, calculate, send_email], got {function_name}"
                )
                assert function_args, "Tool should have parameters"

                called_tools.add(function_name)
                tool_results_map[function_name] = tool_result

                messages.append(response["choices"][0]["message"])
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": json.dumps(tool_result),
                    }
                )

        test_logger.info(
            f"链式调用完成，共调用 {len(called_tools)} 个不同工具: {called_tools}"
        )

        # 断言：至少完成了2步工具调用
        assert len(called_tools) >= 2, (
            f"Multi-step tool chain should call at least 2 different tools, "
            f"but only called: {called_tools}"
        )

        # 断言：get_weather 必须被调用（第一步是查询天气）
        assert "get_weather" in called_tools, (
            f"Expected get_weather to be called, got: {called_tools}"
        )

        # 验证工具结果有效性
        if "get_weather" in tool_results_map:
            weather_result = tool_results_map["get_weather"]
            assert "temperature" in weather_result or "condition" in weather_result, (
                f"get_weather result should contain temperature or condition, got: {weather_result}"
            )

        if "calculate" in tool_results_map:
            calc_result = tool_results_map["calculate"]
            assert "result" in calc_result, (
                f"calculate result should contain 'result', got: {calc_result}"
            )

        # 理想情况：3个工具都被调用
        if called_tools == {"get_weather", "calculate", "send_email"}:
            test_logger.info(
                "3步工具链完整执行：get_weather -> calculate -> send_email"
            )

            if "send_email" in tool_results_map:
                email_result = tool_results_map["send_email"]
                assert "status" in email_result, (
                    f"send_email result should contain 'status', got: {email_result}"
                )
        elif "send_email" not in called_tools:
            record_warning(
                f"模型未调用send_email工具完成3步链，实际调用: {called_tools}"
            )
            test_logger.warning(
                f"模型未完成完整3步链，缺少send_email，实际调用: {called_tools}"
            )

        self.assert_response_success(response)
        test_logger.info("多步链式工具调用测试完成")

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
    def test_structured_output(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
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
                record_warning("Content JSON提取失败")

        # 如果 content 没有 JSON，尝试从 reasoning 提取
        if json_data is None and reasoning:
            try:
                json_data = extract_json_from_text(reasoning)
                source = "reasoning"
            except ValueError:
                test_logger.warning(
                    f"Failed to extract JSON from reasoning: {reasoning[:2000]}..."
                )
                record_warning("Reasoning JSON提取失败")

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
    def test_prefix_suffix_constraint(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
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
        if content.strip().startswith("答案是："):
            test_logger.info("Prefix约束验证通过")
        else:
            msg = "Prefix约束未遵循，模型可能不支持prefix参数"
            test_logger.warning(msg)
            record_warning(msg)

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
        if content.strip().endswith("完毕。"):
            test_logger.info("Suffix约束验证通过")
        else:
            msg = "Suffix约束未遵循，模型可能不支持suffix参数"
            test_logger.warning(msg)
            record_warning(msg)

        test_logger.info("Prefix/Suffix 约束测试完成")
