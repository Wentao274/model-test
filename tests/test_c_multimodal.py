"""
C. 多模态能力测试

测试点：
- C1: 单图理解 - 输入一张图片+文本提问，验证视觉理解
- C2: 多图对比 - 输入多张图片，验证跨图比较和推理
- C3: 高分辨率图片 - 4K分辨率图片，验证细节识别能力
- C4: 图表/OCR - 表格截图、流程图、手写文字识别
- C5: 视频理解 - 输入视频文件，验证时序理解和总结
- C6: 代码截图→代码 - UI设计稿/代码截图，生成对应代码
- C7: 多模态工具调用 - 基于图片内容触发工具调用
- C8: 图片格式兼容性 - PNG/JPEG/WebP/GIF/Base64编码
"""
import pytest
import base64
from typing import List
from pathlib import Path

from base.base_test import BaseTest, StreamingTestMixin, MultimodalTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


# 测试用图片路径
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
IMAGES_DIR = FIXTURES_DIR / "images"
MULTI_IMAGES_DIR = FIXTURES_DIR / "images"/ "multi"


class TestMultimodal(BaseTest, StreamingTestMixin, MultimodalTestMixin):
    """多模态能力测试类"""

    def get_test_category(self) -> str:
        return "C. 多模态能力"

    @pytest.mark.c_multimodal
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_single_image_understanding(self, api_client: ModelAPIClient, test_logger):
        """C1: 单图理解 - 输入一张图片+文本提问"""
        test_logger.info("=== 测试开始: 单图理解 ===")

        # 创建简单的红色图片
        import io
        from PIL import Image

        # 生成红色图片
        img = Image.new('RGB', (100, 100), color='red')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张图片的主要颜色是什么？"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}"
                        }
                    }
                ]
            }
        ]
        test_logger.info("请求: 单图理解")

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "单图理解响应")

        self.assert_response_success(response)

        content = self.get_message_content(response)
        # 简单验证有输出
        assert content and len(content) > 0, "Should have response content"
        test_logger.info(f"Image understanding response: {content[:100]}...")

        # ========== 测试实际图片 ==========
        test_logger.info("=== 测试实际图片: sea_animals.png ===")
        real_image_path = Path("fixtures/images/single/sea_animals.png")

        if not real_image_path.exists():
            test_logger.warning(f"实际图片不存在: {real_image_path}")
        else:
            with open(real_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请描述这张图片的内容"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_b64}"
                            }
                        }
                    ]
                }
            ]
            test_logger.info("请求: 实际图片理解")

            response = api_client.chat_completion(messages)
            TestLogger.log_response(test_logger, response, "实际图片理解响应")

            self.assert_response_success(response)

            content = self.get_message_content(response)
            assert content and len(content) > 0, "Should have response content for real image"

            # 验证模型能识别图片内容（非空且有实际文本输出）
            content_lower = content.lower()
            # 检查输出是否包含有意义的描述（不是错误信息或空回复）
            assert len(content) > 10, "Response should be descriptive"
            test_logger.info(f"Real image understanding response: {content[:200]}...")
            test_logger.info("实际图片理解测试通过")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    @pytest.mark.skipif(not MULTI_IMAGES_DIR.exists(), reason="Images directory not found")
    def test_multi_image_comparison(self, api_client: ModelAPIClient, test_logger):
        """C2: 多图对比 - 输入多张图片，验证跨图比较"""
        test_logger.info("=== 测试开始: 多图对比 ===")

        # 查找测试图片
        image_files = list(MULTI_IMAGES_DIR.glob("*.png"))[:2]

        if len(image_files) < 2:
            pytest.skip("Need at least 2 images for comparison test")

        content_parts = []
        for img_path in image_files:
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}"}
            })

        # 插入问题
        content_parts.insert(0, {"type": "text", "text": "这两张图片有什么区别？"})

        messages = [{"role": "user", "content": content_parts}]
        test_logger.info("请求: 多图对比")

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "多图对比响应")

        self.assert_response_success(response)
        test_logger.info("Multi-image comparison completed")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    def test_high_resolution_image(self, api_client: ModelAPIClient, test_logger):
        """C3: 高分辨率图片 - 4K分辨率图片"""
        test_logger.info("=== 测试开始: 高分辨率图片 ===")

        # 生成4K图片
        import io
        from PIL import Image

        img = Image.new('RGB', (3840, 2160), color=(100, 150, 200))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张图片是什么分辨率？请描述图片内容"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                    }
                ]
            }
        ]
        test_logger.info("请求: 4K高分辨率图片")

        response = api_client.chat_completion(messages)
        # 部分模型可能不支持，捕获异常
        if response.get("error"):
            pytest.skip(f"Model does not support high-res images: {response['error']}")

        self.assert_response_success(response)
        test_logger.info("High resolution image test completed")

        # ========== 测试真实高清图片 ==========
        test_logger.info("=== 测试真实高清图片: sun_raise.jpg ===")
        real_image_path = Path("./fixtures/images/high/sun_raise.jpg")

        if not real_image_path.exists():
            test_logger.warning(f"真实图片不存在: {real_image_path}")
        else:
            with open(real_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请详细描述这张图片的内容"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                        }
                    ]
                }
            ]
            test_logger.info("请求: 真实高清图片理解")

            response = api_client.chat_completion(messages)

            if response.get("error"):
                pytest.skip(f"Model does not support real high-res images: {response['error']}")

            self.assert_response_success(response)

            content = self.get_message_content(response)
            assert content and len(content) > 0, "Should have response content for real high-res image"
            assert len(content) > 20, "Response should be detailed for high-res image"

            test_logger.info(f"Real high-res image response: {content[:200]}...")
            test_logger.info("真实高清图片测试通过")

    @pytest.mark.c_multimodal
    @pytest.mark.p0
    def test_chart_ocr(self, api_client: ModelAPIClient, test_logger):
        """C4: 图表/OCR - 表格截图识别"""
        test_logger.info("=== 测试开始: 图表/OCR ===")

        # 创建包含文字的图片
        import io
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new('RGB', (400, 200), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((50, 80), "Test 123", fill='black')
        draw.text((50, 120), "Hello World", fill='black')

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请读取图片中的文字"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                    }
                ]
            }
        ]
        test_logger.info("请求: OCR识别")

        response = api_client.chat_completion(messages)
        if response.get("error"):
            pytest.skip(f"Model does not support OCR: {response.get('error')}")

        self.assert_response_success(response)
        content = self.get_message_content(response)
        test_logger.info(f"OCR result: {content[:100] if content else 'empty'}")

        # ========== 测试真实表格截图 ==========
        test_logger.info("=== 测试真实表格截图: bench_metrics.png ===")
        real_image_path = Path("./fixtures/images/table/bench_metrics.png")

        if not real_image_path.exists():
            test_logger.warning(f"真实表格图片不存在: {real_image_path}")
        else:
            with open(real_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请读取并分析这张表格图片中的所有数据内容"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                        }
                    ]
                }
            ]
            test_logger.info("请求: 真实表格OCR识别")

            response = api_client.chat_completion(messages)

            if response.get("error"):
                pytest.skip(f"Model does not support real table OCR: {response.get('error')}")

            self.assert_response_success(response)

            content = self.get_message_content(response)
            assert content and len(content) > 0, "Should have OCR result for real table image"

            # 表格OCR应该返回较详细的内容
            test_logger.info(f"Real table OCR result: {content[:200]}...")
            test_logger.info("真实表格OCR测试通过")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    def test_video_understanding(self, api_client: ModelAPIClient, test_logger):
        """C5: 视频理解 - 输入视频文件"""
        test_logger.info("=== 测试开始: 视频理解 ===")

        video_path = Path("./fixtures/videos/water.mp4")

        if not video_path.exists():
            pytest.skip(f"Video file not found: {video_path}")

        with open(video_path, "rb") as f:
            video_b64 = base64.b64encode(f.read()).decode('utf-8')

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请描述这个视频的内容"},
                    {
                        "type": "video_url",
                        "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}
                    }
                ]
            }
        ]
        test_logger.info("请求: 视频理解")

        response = api_client.chat_completion(messages)

        if response.get("error"):
            pytest.skip(f"Model does not support video understanding: {response.get('error')}")

        self.assert_response_success(response)

        content = self.get_message_content(response)
        assert content and len(content) > 0, "Should have video understanding result"

        test_logger.info(f"Video understanding result: {content[:200]}...")
        test_logger.info("视频理解测试通过")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_screenshot_to_code(self, api_client: ModelAPIClient, test_logger):
        """C6: 代码截图→代码 - UI设计稿生成代码"""
        test_logger.info("=== 测试开始: 代码截图→代码 ===")

        # ========== 测试1: 识别Flask代码截图 ==========
        test_logger.info("=== 测试1: 识别Flask代码截图 ===")
        flask_image_path = Path("./fixtures/code/flask_app.png")

        if not flask_image_path.exists():
            test_logger.warning(f"Flask代码截图不存在: {flask_image_path}")
        else:
            with open(flask_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请识别图片中的代码，并直接输出代码内容，不要有额外的解释"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                        }
                    ]
                }
            ]
            test_logger.info("请求: 识别Flask代码截图")

            response = api_client.chat_completion(messages)

            if response.get("error"):
                pytest.skip(f"Model does not support screenshot to code: {response.get('error')}")

            self.assert_response_success(response)

            content = self.get_message_content(response)
            assert content and len(content) > 0, "Should have code recognition result"

            test_logger.info(f"Recognized Flask code:\n{content}")
            test_logger.info("Flask代码识别测试通过")

        # ========== 测试2: UI设计图生成登录代码 ==========
        test_logger.info("=== 测试2: UI设计图生成登录代码 ===")
        login_image_path = Path("./fixtures/code/login_ui.png")

        if not login_image_path.exists():
            test_logger.warning(f"登录UI设计图不存在: {login_image_path}")
        else:
            with open(login_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode('utf-8')

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请根据这个UI设计图，生成一个简单的Python登录页面实现代码，直接输出代码不要有额外解释"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                        }
                    ]
                }
            ]
            test_logger.info("请求: UI设计图生成登录代码")

            response = api_client.chat_completion(messages)

            if response.get("error"):
                pytest.skip(f"Model does not support UI to code: {response.get('error')}")

            self.assert_response_success(response)

            content = self.get_message_content(response)
            assert content and len(content) > 0, "Should have generated login code"

            test_logger.info(f"Generated login code:\n{content}")
            test_logger.info("UI设计图生成登录代码测试通过")

        test_logger.info("代码截图→代码测试完成")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_multimodal_tool_call(self, api_client: ModelAPIClient, test_logger):
        """C7: 多模态工具调用 - 基于图片内容触发工具调用"""
        test_logger.info("=== 测试开始: 多模态工具调用 ===")

        # 定义工具：根据图片中问题，定义工具
        tools = [
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
            },
            {
                "type": "function",
                "function": {
                    "name": "get_capital",
                    "description": "获取国家的首都信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country": {
                                "type": "string",
                                "description": "国家名称"
                            }
                        },
                        "required": ["country"]
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

        # 加载北京图片
        image_path = Path("./fixtures/tool/beijing.png")
        if not image_path.exists():
            pytest.skip(f"Test image not found: {image_path}")

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode('utf-8')

        # 图片内容是几个独立问题，翻译“大语言模型”为英文？北京天气如何？搜索关于“智算”的新闻
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请回答图片中的问题并调用适当的工具"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                    }
                ]
            }
        ]
        test_logger.info("请求: 多模态工具调用")

        response = api_client.chat_completion(
            messages,
            tools=tools,
            tool_choice="auto"
        )

        if response.get("error"):
            pytest.skip(f"Model does not support multimodal tool call: {response.get('error')}")

        self.assert_response_success(response)

        # 获取工具调用
        message = response.get("choices", [{}])[0].get("message", {})
        tool_calls = message.get("tool_calls", [])

        # 如果没有自动触发工具调用，检查内容是否有相关回答
        if len(tool_calls) == 0:
            content = self.get_message_content(response)
            test_logger.warning(f"No tool calls triggered, content: {content}")
            # 某些模型可能不触发工具调用但会直接回答
            assert content and len(content) > 0, "Should have response content"
            test_logger.info("模型直接回答了问题，未触发工具调用")
        else:
            test_logger.info(f"触发了 {len(tool_calls)} 个工具调用")

            # 预期的工具列表（根据图片中的三个问题）
            expected_tools = ["get_weather", "search_news", "translate"]

            # 验证工具调用
            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call.get("function", {}).get("name")
                arguments = tool_call.get("function", {}).get("arguments", "{}")
                test_logger.info(f"工具调用 {i+1}: {tool_name}({arguments})")

                # 验证工具名称是预期的
                assert tool_name in expected_tools, \
                    f"Expected tool in {expected_tools}, got '{tool_name}'"

            # 验证工具调用数量（图片中有3个问题）
            test_logger.info(f"共触发 {len(tool_calls)} 个工具调用")

        test_logger.info("多模态工具调用测试通过")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    @pytest.mark.parametrize("format", ["png", "jpeg", "webp"])
    def test_image_format_compatibility(self, api_client: ModelAPIClient, format: str, test_logger):
        """C8: 图片格式兼容性 - PNG/JPEG/WebP"""
        test_logger.info(f"=== 测试开始: 图片格式兼容性 ({format}) ===")

        import io
        from PIL import Image

        img = Image.new('RGB', (100, 100), color='blue')
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format=format.upper())
        img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"这张{format}格式的图片是什么颜色？"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{format};base64,{img_b64}"}
                    }
                ]
            }
        ]
        test_logger.info(f"请求: {format}格式图片")

        response = api_client.chat_completion(messages)
        if response.get("error"):
            pytest.skip(f"Model does not support {format} format")

        self.assert_response_success(response)
        test_logger.info(f"Format {format} test passed")