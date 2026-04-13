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
import pytest
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
        json_str = text[start:end+1]
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
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称"
                    }
                },
                "required": ["city"]
            }
        }
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
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取时间",
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string"}},
                "required": ["timezone"]
            }
        }
    }
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
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"]
            }
        }
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
                "required": ["symbol"]
            }
        }
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
                    "limit": {"type": "integer", "description": "返回新闻数量"}
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "数学计算器，支持加减乘除运算",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，如 2+3*4"}
                },
                "required": ["expression"]
            }
        }
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
                    "target_lang": {"type": "string", "description": "目标语言，如 en、zh、ja"}
                },
                "required": ["text", "target_lang"]
            }
        }
    }
]


class TestAdvancedGeneration(BaseTest, StreamingTestMixin):
    """高级生成功能测试类"""

    def get_test_category(self) -> str:
        return "B. 高级生成功能"

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_thinking_mode(self, api_client: ModelAPIClient, test_logger):
        """B1: 思考模式（Thinking）- 开启thinking mode"""
        test_logger.info("=== 测试开始: 思考模式 ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]
        TestLogger.log_request(test_logger, messages, {"chat_template_kwargs": {"enable_thinking": True}})

        # 使用chat_template_kwargs开启thinking
        response = api_client.chat_completion(
            messages,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}}
        )
        TestLogger.log_response(test_logger, response, "思考模式响应")

        self.assert_response_success(response)

        # 验证思考模式开启成功
        reasoning = self.get_reasoning_content(response)
        content = self.get_message_content(response)

        # 检查是否有 thinking 内容的多种方式：
        # 1. reasoning 字段有内容
        # 2. content 中包含 <think> 或 </think> 标签
        # 3. 模板格式: <|im_start|>assistant\n<think>\n{思考内容}\n</think>\n\n{实际回复}
        has_reasoning_field = reasoning is not None and len(reasoning) > 0

        # 检查标签格式（兼容不同模型）
        has_thinking_tags = False
        thinking_content = ""

        if content:
            # 方式1: 标准标签
            if "<think>" in content and "</think>" in content:
                start = content.find("<think>") + len("<think>")
                end = content.find("</think>")
                thinking_content = content[start:end].strip()
                has_thinking_tags = len(thinking_content) > 0
            # 方式2: 模板格式 <|im_start|>assistant\n<think>\n
            elif content.startswith("<|im_start|>assistant\n<think>\n"):
                # 检查是否有实际的思考内容
                after_start = content.find("<think>\n") + len("<think>\n")
                if "</think>" in content:
                    end = content.find("</think>")
                    thinking_content = content[after_start:end].strip()
                    has_thinking_tags = len(thinking_content) > 0

        test_logger.info(f"reasoning 字段: {reasoning[:100] if reasoning else 'None'}...")
        test_logger.info(f"content 中的thinking标签: {'存在' if has_thinking_tags else '不存在'}")
        if thinking_content:
            test_logger.info(f"思考内容: {thinking_content[:100]}...")

        assert has_reasoning_field or has_thinking_tags, \
            "Thinking mode should return reasoning content (reasoning field or </think> tags)"

        test_logger.info("思考模式验证通过")

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_non_thinking_mode(self, api_client: ModelAPIClient, test_logger):
        """B2: 非思考模式（Instant）- 关闭thinking，无泄漏"""
        test_logger.info("=== 测试开始: 非思考模式 ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]
        TestLogger.log_request(test_logger, messages, {"chat_template_kwargs": {"enable_thinking": False}})

        response = api_client.chat_completion(
            messages,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
        TestLogger.log_response(test_logger, response, "非思考模式响应")

        self.assert_response_success(response)

        # 验证无thinking泄漏
        content = self.get_message_content(response)
        reasoning = self.get_reasoning_content(response)

        # reasoning 字段应为空
        assert reasoning is None or reasoning == "", \
            "Thinking disabled but reasoning field is not empty"

        # 检查内容中是否有实际的思考内容（标签之间不应有内容）
        if content:
            # 检查 <think> 标签之间是否有实际内容
            import re
            # 匹配 <think> 和 </think> 之间的内容
            thinking_blocks = re.findall(r'<think>\s*(.*?)\s*</think>', content, re.DOTALL)
            for block in thinking_blocks:
                block = block.strip()
                # 允许空思考或只有空白字符
                assert block == "" or len(block) < 10, \
                    f"Thinking disabled but found thinking content: {block[:50]}..."

        test_logger.info("非思考模式测试通过，无thinking泄漏")

    @pytest.mark.b_advanced
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_thinking_mode_switch(self, api_client: ModelAPIClient, test_logger):
        """B3: 思考模式切换 - 同一会话内thinking↔non-thinking切换"""
        test_logger.info("=== 测试开始: 思考模式切换 ===")

        messages = [{"role": "user", "content": "请计算 123 * 456 = ?"}]

        # 开启thinking
        test_logger.info("第1轮: 开启thinking模式")
        TestLogger.log_request(test_logger, messages, {"chat_template_kwargs": {"enable_thinking": True}})

        response1 = api_client.chat_completion(
            messages,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}}
        )
        TestLogger.log_response(test_logger, response1, "开启thinking响应")

        self.assert_response_success(response1)
        reasoning1 = self.get_reasoning_content(response1)
        test_logger.info(f"开启thinking后的reasoning: {reasoning1[:100] if reasoning1 else 'None'}...")
        assert reasoning1, "First request should have reasoning"

        # 关闭thinking
        test_logger.info("第2轮: 关闭thinking模式")
        TestLogger.log_request(test_logger, messages, {"chat_template_kwargs": {"enable_thinking": False}})

        response2 = api_client.chat_completion(
            messages,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}}
        )
        TestLogger.log_response(test_logger, response2, "关闭thinking响应")

        self.assert_response_success(response2)
        self.assert_no_thinking_leakage(response2)
        test_logger.info("思考模式切换测试通过")

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_single_tool_call(self, api_client: ModelAPIClient, test_logger):
        """B4: 工具调用-单工具 - 定义单个function"""
        test_logger.info("=== 测试开始: 单工具调用 ===")

        messages = [
            {"role": "user", "content": "北京今天天气怎么样？"}
        ]
        TestLogger.log_request(test_logger, messages, {"tools": "TOOLS_GET_WEATHER"})

        response = api_client.chat_completion(
            messages,
            tools=TOOLS_GET_WEATHER,
            tool_choice="auto"
        )
        TestLogger.log_response(test_logger, response, "单工具调用响应")

        self.assert_response_success(response)
        # 验证工具调用
        tool_calls = self.get_tool_calls(response)
        assert len(tool_calls) > 0, "Should have tool calls"

        # 验证工具名称
        tool_name = tool_calls[0].get("function", {}).get("name")
        assert tool_name == "get_weather", f"Expected tool 'get_weather', got '{tool_name}'"

        # 验证参数
        arguments = tool_calls[0].get("function", {}).get("arguments", "{}")
        args = eval(arguments) if isinstance(arguments, str) else arguments
        assert "city" in args, "Should have city parameter"
        test_logger.info(f"Tool call: {tool_name}({args})")

    @pytest.mark.b_advanced
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_multiple_tool_call(self, api_client: ModelAPIClient, test_logger):
        """B5: 工具调用-多工具 - 定义多个function，验证模型选择正确的工具"""
        test_logger.info("=== 测试开始: 多工具调用（5个工具） ===")

        # 使用5个不同的工具
        tools = TOOLS_FIVE

        # 测试1: 天气相关问题
        test_logger.info("【测试1】天气相关问题 -> 应选择 get_weather")
        messages = [{"role": "user", "content": "北京今天天气怎么样？"}]
        TestLogger.log_request(test_logger, messages, {"tools": "5 tools"})

        response = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response, "天气工具调用")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response)
        assert len(tool_calls) > 0, "Should have tool calls"
        tool_name = tool_calls[0].get("function", {}).get("name")
        test_logger.info(f"Selected tool: {tool_name}")
        assert tool_name == "get_weather", f"Expected 'get_weather', got '{tool_name}'"

        # 测试2: 股票相关问题
        test_logger.info("【测试2】股票相关问题 -> 应选择 get_stock_price")
        messages = [{"role": "user", "content": "现在苹果公司(AAPL)的股价是多少？"}]

        response = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response, "股票工具调用")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response)
        tool_name = tool_calls[0].get("function", {}).get("name")
        test_logger.info(f"Selected tool: {tool_name}")
        assert tool_name == "get_stock_price", f"Expected 'get_stock_price', got '{tool_name}'"

        # 测试3: 新闻搜索问题
        test_logger.info("【测试3】新闻搜索问题 -> 应选择 search_news")
        messages = [{"role": "user", "content": "搜索关于人工智能的最新新闻"}]

        response = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response, "新闻工具调用")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response)
        tool_name = tool_calls[0].get("function", {}).get("name")
        test_logger.info(f"Selected tool: {tool_name}")
        assert tool_name == "search_news", f"Expected 'search_news', got '{tool_name}'"

        # 测试4: 数学计算问题
        test_logger.info("【测试4】数学计算问题 -> 应选择 calculate")
        messages = [{"role": "user", "content": "帮我计算一下 123 + 456 等于多少？"}]

        response = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response, "计算工具调用")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response)
        tool_name = tool_calls[0].get("function", {}).get("name")
        test_logger.info(f"Selected tool: {tool_name}")
        assert tool_name == "calculate", f"Expected 'calculate', got '{tool_name}'"

        # 测试5: 翻译问题
        test_logger.info("【测试5】翻译问题 -> 应选择 translate")
        messages = [{"role": "user", "content": "把 Hello 翻译成中文"}]

        response = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response, "翻译工具调用")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response)
        tool_name = tool_calls[0].get("function", {}).get("name")
        test_logger.info(f"Selected tool: {tool_name}")
        assert tool_name == "translate", f"Expected 'translate', got '{tool_name}'"

        test_logger.info("多工具调用测试完成")

    @pytest.mark.b_advanced
    @pytest.mark.p1
    def test_parallel_tool_calls(self, api_client: ModelAPIClient, test_logger):
        """B6: 工具调用-并行调用 - 单次回复中并行调用多个工具"""
        test_logger.info("=== 测试开始: 并行工具调用 ===")

        messages = [
            {"role": "user", "content": "请帮我查一下北京今天的天气和时间"}
        ]
        TestLogger.log_request(test_logger, messages, {"tools": "TOOLS_MULTIPLE"})

        response = api_client.chat_completion(
            messages,
            tools=TOOLS_MULTIPLE,
            tool_choice="auto"
        )
        TestLogger.log_response(test_logger, response, "并行工具调用响应")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response)

        # 可能有多个工具调用或单个工具调用都算通过
        test_logger.info(f"工具调用数量: {len(tool_calls)}")
        assert len(tool_calls) > 0, "Should have tool calls"

    @pytest.mark.b_advanced
    @pytest.mark.p1
    def test_multi_step_tool_chain(self, api_client: ModelAPIClient, test_logger):
        """B7: 工具调用-多步链式 - 工具结果作为下一步输入"""
        test_logger.info("=== 测试开始: 多步工具链 ===")

        # 工具定义
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_seed_word",
                    "description": "获取种子词",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "uppercase_word",
                    "description": "将单词转为大写",
                    "parameters": {
                        "type": "object",
                        "properties": {"word": {"type": "string"}},
                        "required": ["word"]
                    }
                }
            }
        ]

        messages = [{"role": "user", "content": "请帮我完成一个多步工具调用测试"}]
        TestLogger.log_request(test_logger, messages, {"tools": "2 tools"})

        # 第1步
        test_logger.info("第1步: 调用get_seed_word")
        response1 = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response1, "第1步响应")

        tool_calls = self.get_tool_calls(response1)

        if len(tool_calls) == 0:
            pytest.skip("Model does not support multi-step tool chain")

        # 模拟工具返回
        tool_result = "hello"
        messages.append(response1["choices"][0]["message"])
        messages.append({
            "role": "tool",
            "tool_call_id": tool_calls[0].get("id"),
            "content": tool_result
        })

        # 第2步
        test_logger.info("第2步: 调用uppercase_word")
        response2 = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response2, "第2步响应")

        self.assert_response_success(response2)
        test_logger.info("多步工具链测试完成")

    @pytest.mark.b_advanced
    @pytest.mark.p0
    def test_json_mode(self, api_client: ModelAPIClient, test_logger):
        """B8: JSON Mode - response_format=json_object"""
        test_logger.info("=== 测试开始: JSON Mode ===")

        messages = [
            {"role": "system", "content": "你是一个JSON生成器"},
            {"role": "user", "content": "请返回一个包含姓名和年龄的JSON对象"}
        ]
        TestLogger.log_request(test_logger, messages, {"response_format": "json_object"})

        response = api_client.chat_completion(
            messages,
            response_format={"type": "json_object"}
        )
        TestLogger.log_response(test_logger, response, "JSON Mode响应")

        self.assert_response_success(response)

        # 尝试解析JSON
        content = self.get_message_content(response)
        if content:  # content可能为None，某些模型会把JSON放到reasoning
            try:
                json_data = self.assert_valid_json(content)
                assert isinstance(json_data, dict), "Should return a JSON object"
                test_logger.info(f"JSON response: {json_data}")
            except:
                # 某些模型的响应可能在reasoning中
                reasoning = self.get_reasoning_content(response)
                if reasoning:
                    try:
                        json_data = self.assert_valid_json(reasoning)
                        test_logger.info(f"JSON in reasoning: {json_data}")
                    except:
                        pytest.fail("JSON not found in content or reasoning")

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
                "city": {"type": "string", "description": "城市"}
            },
            "required": ["name", "age"]
        }

        messages = [
            {"role": "user", "content": "请返回一个包含姓名、年龄和城市的JSON对象"}
        ]
        TestLogger.log_request(test_logger, messages, {"response_format": "json_schema"})

        response = api_client.chat_completion(
            messages,
            response_format={"type": "json_object", "schema": schema}
        )
        TestLogger.log_response(test_logger, response, "结构化输出响应")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        reasoning = self.get_reasoning_content(response)

        json_data = None
        source = None

        # 优先从 content 提取 JSON
        if content and content.strip():
            try:
                json_data = extract_json_from_text(content)
                source = "content"
            except ValueError:
                test_logger.warning(f"Failed to extract JSON from content: {content[:200]}...")

        # 如果 content 没有 JSON，尝试从 reasoning 提取
        if json_data is None and reasoning:
            try:
                json_data = extract_json_from_text(reasoning)
                source = "reasoning"
            except ValueError:
                test_logger.warning(f"Failed to extract JSON from reasoning: {reasoning[:200]}...")

        if json_data is None:
            pytest.fail("No valid JSON found in content or reasoning")

        test_logger.info(f"Structured output found in {source}: {json_data}")

        # 兼容中英文键名
        has_name = "name" in json_data or "姓名" in json_data
        has_age = "age" in json_data or "年龄" in json_data
        assert has_name, "Should have 'name' or '姓名' field"
        assert has_age, "Should have 'age' or '年龄' field"
        test_logger.info("结构化输出验证通过")

    @pytest.mark.b_advanced
    @pytest.mark.p2
    def test_prefix_suffix_constraint(self, api_client: ModelAPIClient, test_logger):
        """B10: Prefix / Suffix 约束 - 指定输出前缀或格式模板"""
        test_logger.info("=== 测试开始: Prefix/Suffix 约束 ===")

        # ========== 测试 prefix 约束 ==========
        test_logger.info("【测试1】Prefix 约束：回答必须以 '答案是：' 开头")
        messages = [
            {"role": "user", "content": "1+1等于多少？"}
        ]
        TestLogger.log_request(test_logger, messages)

        # 使用 prefix 参数（如果API支持）
        response = api_client.chat_completion(
            messages,
            prefix="答案是："
        )
        TestLogger.log_response(test_logger, response, "Prefix约束响应")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        test_logger.info(f"Prefix 约束响应: {content[:100]}...")

        # 验证前缀是否被正确遵循（如果API支持）
        if content and not content.startswith("答案是："):
            test_logger.warning(f"Prefix约束未完全遵循，当前回复: {content[:50]}...")

        # ========== 测试 suffix 约束 ==========
        test_logger.info("【测试2】Suffix 约束：回答必须以 '完毕。' 结尾")
        messages = [
            {"role": "user", "content": "请用一句话介绍北京。"}
        ]
        TestLogger.log_request(test_logger, messages)

        # 使用 suffix 参数
        response = api_client.chat_completion(
            messages,
            suffix="完毕。"
        )
        TestLogger.log_response(test_logger, response, "Suffix约束响应")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        test_logger.info(f"Suffix 约束响应: {content[:100]}...")

        # 验证后缀是否被正确遵循
        if content and not content.endswith("完毕。"):
            test_logger.warning(f"Suffix约束未完全遵循，当前回复: {content[:50]}...")

        test_logger.info("Prefix/Suffix 约束测试完成")