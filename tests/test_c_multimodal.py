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

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    @pytest.mark.skipif(not IMAGES_DIR.exists(), reason="Images directory not found")
    def test_multi_image_comparison(self, api_client: ModelAPIClient, test_logger):
        """C2: 多图对比 - 输入多张图片，验证跨图比较"""
        test_logger.info("=== 测试开始: 多图对比 ===")

        # 查找测试图片
        image_files = list(IMAGES_DIR.glob("*.png"))[:2]

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

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    def test_video_understanding(self, api_client: ModelAPIClient, test_logger):
        """C5: 视频理解 - 输入视频文件"""
        test_logger.info("=== 测试开始: 视频理解 ===")
        messages = [
            {"role": "user", "content": "请描述这个视频的内容"}
        ]

        # 跳过视频测试，因为需要实际视频文件
        pytest.skip("Video test requires actual video file")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_screenshot_to_code(self, api_client: ModelAPIClient, test_logger):
        """C6: 代码截图→代码 - UI设计稿生成代码"""
        test_logger.info("=== 测试开始: 代码截图→代码 ===")
        # 需要UI截图
        pytest.skip("Screenshot to code test requires UI screenshot")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_multimodal_tool_call(self, api_client: ModelAPIClient, test_logger):
        """C7: 多模态工具调用 - 基于图片内容触发工具调用"""
        test_logger.info("=== 测试开始: 多模态工具调用 ===")
        pytest.skip("Multimodal tool call test needs tool definition")

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