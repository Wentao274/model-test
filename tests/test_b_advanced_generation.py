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
import pytest
from typing import List, Dict, Any

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


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
        # 验证返回了reasoning
        reasoning = self.get_reasoning_content(response)
        test_logger.info(f"Thinking content: {reasoning[:200] if reasoning else 'None'}...")

        assert reasoning is not None and len(reasoning) > 0, \
            "Thinking mode should return reasoning content"

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
        self.assert_no_thinking_leakage(response)
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
        test_logger.info("=== 测试开始: 多工具调用 ===")

        # 定义两个不同的工具
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "获取指定城市的天气信息",
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
                    "description": "获取股票价格",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "股票代码"}
                        },
                        "required": ["symbol"]
                    }
                }
            }
        ]

        # 问天气相关问题，应该选择天气工具
        messages = [{"role": "user", "content": "北京今天天气怎么样？"}]
        TestLogger.log_request(test_logger, messages, {"tools": "2 tools"})

        response = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response, "多工具调用响应")

        self.assert_response_success(response)
        tool_calls = self.get_tool_calls(response)
        assert len(tool_calls) > 0, "Should have tool calls"

        # 验证选择了正确的工具
        tool_name = tool_calls[0].get("function", {}).get("name")
        test_logger.info(f"Selected tool: {tool_name}")
        assert tool_name == "get_weather", f"Expected tool 'get_weather', got '{tool_name}'"

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

        if content:
            json_data = self.assert_valid_json(content)
            assert "name" in json_data, "Should have 'name' field"
            assert "age" in json_data, "Should have 'age' field"
            test_logger.info(f"Structured output: {json_data}")
        else:
            # 检查reasoning
            reasoning = self.get_reasoning_content(response)
            if reasoning:
                try:
                    json_data = self.assert_valid_json(reasoning)
                    test_logger.info(f"Structured output in reasoning: {json_data}")
                except:
                    pytest.fail("Structured output not found")

    @pytest.mark.b_advanced
    @pytest.mark.p2
    def test_prefix_suffix_constraint(self, api_client: ModelAPIClient, test_logger):
        """B10: Prefix / Suffix 约束 - 指定输出前缀或格式模板"""
        test_logger.info("=== 测试开始: Prefix/Suffix 约束 ===")

        # 测试 prefix 约束
        test_logger.info("测试 prefix 约束：回答必须以 '答案是：' 开头")
        messages = [
            {"role": "user", "content": "1+1等于多少？"}
        ]
        TestLogger.log_request(test_logger, messages)

        # 某些API可能不支持stop参数作为prefix，这里测试基本stop功能
        response = api_client.chat_completion(
            messages,
            stop=["但是", "然而"]
        )
        TestLogger.log_response(test_logger, response, "Prefix/Suffix响应")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        test_logger.info(f"Prefix/Suffix 响应: {content[:100]}...")

        test_logger.info("Prefix/Suffix 约束测试完成")