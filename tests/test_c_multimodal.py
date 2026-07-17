"""
C. 多模态能力测试

测试点：
- C1: 单图理解 - 输入一张图片+文本提问，验证视觉理解 [P1]
- C2: 多图对比 - 输入多张图片，验证跨图比较和推理 [P1]
- C3: 高分辨率图片 - 4K分辨率图片，验证细节识别能力 [P2]
- C4: 图表/OCR - 表格截图、流程图、手写文字识别 [P1]
- C5: 视频理解 - 输入视频文件，验证时序理解和总结 [P2]
- C6: 代码截图→代码 - UI设计稿/代码截图，生成对应代码 [P2]
- C7: 多模态工具调用 - 基于图片内容触发工具调用 [P2]
- C8: 图片格式兼容性 - PNG/JPEG/WebP/GIF/Base64编码 [P1]
"""

import json
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
MULTI_IMAGES_DIR = FIXTURES_DIR / "images" / "multi"
VIDEO_DIR = FIXTURES_DIR / "videos"
TOOL_DIR = FIXTURES_DIR / "tool"
CODE_DIR = FIXTURES_DIR / "code"


# 多模态识别失败关键词
NO_IMAGE_KEYWORDS = [
    # 中文 - 无法看到
    "没有看到",
    "看不到",
    "无法看到",
    "无法查看",
    "无法识别",
    "无法访问",
    # 中文 - 未上传/未提供
    "没有上传",
    "没有附上",
    "没有附带",
    "没有提供",
    "没有收到",
    "没有附件",
    "没有成功上传",
    "没有图片",
    "未上传",
    "未提供",
    "未收到",
    "未附",
    "没有任何图片",
    "没有任何图像",
    "忘记上传",
    "忘记附",
    # 中文 - 请求提供
    "请上传图片",
    "请提供图片",
    "请发送图片",
    "请重新上传",
    "请上传",
    "请提供",
    "请将图片",
    "请补充相关",
    # 英文
    "i don't see",
    "i cannot see",
    "i can't see",
    "i am unable to see",
    "no image",
    "don't see any image",
    "cannot see the image",
    "haven't seen",
    "unable to process",
    "cannot process",
    "as an ai",
    "as a text model",
    "as a language model",
    "text-based ai",
    # 模型自述为纯文本模型（受 positive_phrases 保护，正常描述含"纯文本"时不会误判）
    "纯文本",
    # "无法直接看到/查看/识别" 等带修饰词的变体
    "无法直接看到",
    "无法直接查看",
    "无法直接识别",
    # "没有视觉" 原子词（受 positive_phrases 保护）
    "没有视觉",
]

NO_VIDEO_KEYWORDS = [
    # 中文 - 无法看到
    "没有看到",
    "看不到",
    "无法看到",
    "无法查看",
    "无法识别",
    "无法访问",
    # 中文 - 未上传/未提供
    "没有上传",
    "没有附上",
    "没有附带",
    "没有提供",
    "没有收到",
    "没有附件",
    "没有成功上传",
    "没有视频",
    "未上传",
    "未提供",
    "未收到",
    "未附",
    "没有任何视频",
    "忘记上传",
    "忘记附",
    # 中文 - 请求提供
    "请上传视频",
    "请提供视频",
    "请发送视频",
    "请重新上传",
    "请上传",
    "请提供",
    "请将视频",
    "请补充相关",
    # 英文
    "i don't see",
    "i cannot see",
    "i can't see",
    "i am unable to see",
    "no video",
    "don't see any video",
    "cannot see the video",
    "haven't seen",
    "unable to process",
    "cannot process",
    "as an ai",
    "as a text model",
    "as a language model",
    "text-based ai",
    # 模型自述为纯文本模型（受 positive_phrases 保护，正常描述含"纯文本"时不会误判）
    "纯文本",
    # "无法直接看到/查看/识别" 等带修饰词的变体
    "无法直接看到",
    "无法直接查看",
    "无法直接识别",
    # "观看" 是视频专属动词（模型常以"无法观看/无法直接观看视频"拒绝）
    "无法观看",
    "无法直接观看",
    # "没有视觉" 原子词（受 positive_phrases 保护）
    "没有视觉",
]

PLACEHOLDER_KEYWORDS = [
    "placeholder",
    "占位符",
    "视频占位",
    "image_placeholder",
    "video_placeholder",
    "<|",
]

# 强拒绝关键词：模型明确声明无法处理图片/视频输入。出现即判定多模态不支持，
# 不受 positive_phrases 影响。用于避免模型在拒绝后追加"例如图片中有什么"
# 等澄清性提问，导致 positive_phrases 误判为已识别图片。
# 仅收录明确表达"无能力/纯文本"的短语，避免误伤正常图片描述。
STRONG_REFUSAL_COMMON = [
    "无法看到或处理",
    # "查看/直接" 变体：模型常以"无法直接查看或处理您上传的图片"明确拒绝，
    # 属于强拒绝，须绕过 positive_phrases，避免拒绝后提及"图片中显示"等措辞
    # 导致 has_positive 误判为已识别而漏检。
    "无法查看或处理",
    "无法直接看到或处理",
    "无法直接查看或处理",
    "作为纯文本",
    "作为一个纯文本",
    "纯文本模型",
    "纯文本ai",
    "纯文本的人工智能",
    # "基于文本的AI/模型" 自述（明确声明自身为文本模型）
    "基于文本",
    "没有多模态",
    "没有多模态输入",
    "没有多模态能力",
    # "不具备多模态" 变体（与"没有多模态"等价，模型常以"不具备多模态输入能力"拒绝）
    "不具备多模态",
    "不具备多模态输入",
    "不具备多模态能力",
    "没有视觉能力",
    "没有视觉处理能力",
    "没有图像识别能力",
    "没有图片识别能力",
    "text-only",
    "text-based ai",
    "no visual capability",
    "no multimodal",
    "unable to see",
    "unable to analyze",
]

STRONG_REFUSAL_IMAGE = [
    "无法处理图片",
    "无法处理图像",
    "无法看到图片",
    "无法查看图片",
    "无法分析图片",
    "无法分析图像",
    "cannot process image",
    "unable to process image",
    "cannot analyze image",
]

STRONG_REFUSAL_VIDEO = [
    "无法处理视频",
    "无法看到视频",
    "无法查看视频",
    "无法分析视频",
    # "观看" 是视频专属动词，模型常以"无法观看视频"/"无法直接观看或处理...视频"拒绝
    "无法观看视频",
    "无法观看或处理",
    "无法直接观看或处理",
    "无法直接观看",
    "cannot process video",
    "unable to process video",
    "cannot analyze video",
]


def check_multimodal_failure(response: dict, media_type: str = "image") -> str | None:
    """检查多模态响应是否包含识别失败的关键词

    仅检查 message.content（模型给用户的最终回复），不检查
    reasoning_content（内部思维链），因为 reasoning 常引用用户问题中的
    "图片中"等措辞，会导致误判为"已看到图片"。

    当模型回复"看不到图片"等失败信息时返回匹配的关键词，用于判定多模态识别失败。
    positive_phrases 仅保留明确表示"正在描述媒体内容"的短语（需带描述动词），
    避免使用"图片中"等过于宽泛的词——否则模型说"您提到了图片中的问题，
    但我没有看到图片"会因含"图片中"而误判为成功。
    """
    message = response.get("choices", [{}])[0].get("message", {})
    content = message.get("content") or ""
    if not content:
        return None
    content_lower = content.lower()
    for keyword in PLACEHOLDER_KEYWORDS:
        if keyword in content_lower:
            return keyword
    # 强拒绝关键词优先：模型明确声明无法处理图片/视频输入时直接判定失败，
    # 不受 positive_phrases 影响。
    strong_keywords = STRONG_REFUSAL_COMMON[:]
    if media_type == "image":
        strong_keywords += STRONG_REFUSAL_IMAGE
    else:
        strong_keywords += STRONG_REFUSAL_VIDEO
    for keyword in strong_keywords:
        if keyword in content_lower:
            return keyword
    keywords = NO_IMAGE_KEYWORDS if media_type == "image" else NO_VIDEO_KEYWORDS
    # 仅当响应中明确包含"正在描述媒体内容"的短语时，才认为失败关键词是误报。
    # 要求短语带描述动词（显示/可以看到/有/包含等），避免"图片中的问题"等
    # 引用用户问题的措辞被误判为正面。
    positive_phrases = [
        "图片中显示",
        "图片中可以看到",
        "图片中有",
        "图片中包含",
        "图片中呈现",
        "图片中是",
        "图片里显示",
        "图片里可以看到",
        "图片里有",
        "图片里包含",
        "画面中显示",
        "画面中可以看到",
        "画面中有",
        "画面里显示",
        "画面里可以看到",
        "图像中显示",
        "图像中可以看到",
        "图像中有",
        "图中显示",
        "图中可以看到",
        "图中有",
        "图中包含",
        "图中呈现",
        "从图可以",
        "从图片可以",
        "从图中可以",
        "可以看到",
        "呈现出",
        "显示了一张",
        "显示了一个",
        "展示了",
        "视频中显示",
        "视频中可以看到",
        "视频中有",
        "视频中包含",
        "视频里显示",
        "视频里可以看到",
        "the image shows",
        "the picture shows",
        "the video shows",
        "in the image, we can see",
        "in the image, there is",
        "this image contains",
        "this image shows",
        "in the video, we can see",
    ]
    has_positive = any(phrase in content_lower for phrase in positive_phrases)
    for keyword in keywords:
        if keyword in content_lower:
            if has_positive:
                continue
            return keyword
    return None


class TestMultimodal(BaseTest, StreamingTestMixin, MultimodalTestMixin):
    """多模态能力测试类"""

    def get_test_category(self) -> str:
        return "C. 多模态能力"

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_single_image_understanding(self, api_client: ModelAPIClient, test_logger):
        """C1 [P1]: 单图理解 - 输入一张图片+文本提问"""
        test_logger.info("=== 测试开始: 单图理解 ===")

        # 创建简单的红色图片
        import io
        from PIL import Image

        # 生成红色图片
        img = Image.new("RGB", (100, 100), color="red")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张图片的主要颜色是什么？"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            }
        ]
        test_logger.info("请求: 单图理解")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "单图理解响应")
        self.log_full_response(test_logger, response, "C1-红色图理解")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        failed_keyword = check_multimodal_failure(response, "image")
        if failed_keyword:
            test_logger.warning(
                f"模型可能不支持多模态（未能识别图片）。Response contains: '{failed_keyword}'"
            )
            pytest.skip(
                f"Model may not support multimodal (image recognition failed). "
                f"Response contains: '{failed_keyword}'"
            )

        content = self.get_message_content(response)
        content_lower = content.lower()
        assert any(kw in content_lower for kw in ["红", "red", "红色"]), (
            f"Model should identify the image color as red, got: {content[:500]}"
        )
        test_logger.info(f"Image understanding response: {content[:2000]}...")

        # ========== 测试实际图片 ==========
        test_logger.info("=== 测试实际图片: sea_animals.png ===")
        real_image_path = IMAGES_DIR / "single" / "sea_animals.png"

        if not real_image_path.exists():
            test_logger.warning(f"测试图片不存在，跳过实际图片测试: {real_image_path}")
        else:
            with open(real_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请描述这张图片的内容"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                    ],
                }
            ]
            test_logger.info("请求: 实际图片理解")
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages)
            TestLogger.log_response(test_logger, response, "实际图片理解响应")
            self.log_full_response(test_logger, response, "C1-实际图片理解")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            failed_keyword = check_multimodal_failure(response, "image")
            if failed_keyword:
                test_logger.warning(
                    f"模型可能不支持多模态（未能识别实际图片）。Response contains: '{failed_keyword}'"
                )
                pytest.skip(
                    f"Model may not support multimodal (real image recognition failed). "
                    f"Response contains: '{failed_keyword}'"
                )

            assert len(content) > 10, (
                f"Response should be descriptive, got only {len(content)} chars"
            )
            test_logger.info(f"Real image understanding response: {content[:2000]}...")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    @pytest.mark.skipif(
        not MULTI_IMAGES_DIR.exists(), reason="Images directory not found"
    )
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
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                }
            )

        # 插入问题
        content_parts.insert(0, {"type": "text", "text": "这两张图片有什么区别？"})

        messages = [{"role": "user", "content": content_parts}]
        test_logger.info("请求: 多图对比")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "多图对比响应")
        self.log_full_response(test_logger, response, "C2-多图对比")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        failed_keyword = check_multimodal_failure(response, "image")
        if failed_keyword:
            test_logger.warning(
                f"模型可能不支持多模态（未能识别多图）。Response contains: '{failed_keyword}'"
            )
            pytest.skip(
                f"Model may not support multimodal (multi-image recognition failed). "
                f"Response contains: '{failed_keyword}'"
            )

        assert len(content.strip()) > 20, (
            f"Comparison response should be descriptive, got only {len(content.strip())} chars"
        )

        content_lower = content.lower()
        assert any(
            kw in content_lower
            for kw in ["区别", "不同", "差异", "differ", "comparison", "对比", "相比"]
        ), f"Response should describe differences between images, got: {content[:500]}"

        test_logger.info("Multi-image comparison completed")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_high_resolution_image(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """C3 [P2]: 高分辨率图片 - 4K分辨率图片"""
        test_logger.info("=== 测试开始: 高分辨率图片 ===")

        # ========== 测试真实高清图片 ==========
        test_logger.info("=== 测试真实高清图片: sun_raise.jpg ===")
        real_image_path = IMAGES_DIR / "high" / "sun_raise.jpg"

        if not real_image_path.exists():
            test_logger.warning(
                f"测试图片不存在，跳过真实高清图片测试: {real_image_path}"
            )
            record_warning("测试图片不存在")
        else:
            with open(real_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请详细描述这张图片的内容"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
                        },
                    ],
                }
            ]
            test_logger.info("请求: 真实高清图片理解")
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages)
            TestLogger.log_response(test_logger, response, "真实高清图片响应")
            self.log_full_response(test_logger, response, "C3-真实高清图")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            failed_keyword = check_multimodal_failure(response, "image")
            if failed_keyword:
                test_logger.warning(
                    f"模型可能不支持多模态（未能识别真实高清图片）。Response contains: '{failed_keyword}'"
                )
                pytest.skip(
                    f"Model may not support multimodal (real high-res image recognition failed). "
                    f"Response contains: '{failed_keyword}'"
                )

            assert len(content) > 20, (
                f"Response should be detailed for high-res image, got {len(content)} chars"
            )

            test_logger.info(f"Real high-res image response: {content[:2000]}...")

        test_logger.info("=== 测试程序生成高清图片 ===")
        # 生成4K图片
        import io
        from PIL import Image

        img = Image.new("RGB", (3840, 2160), color=(100, 150, 200))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张图片是什么分辨率？请描述图片内容"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            }
        ]
        test_logger.info("请求: 4K高分辨率图片")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "4K高分辨率图片响应")
        self.log_full_response(test_logger, response, "C3-4K生成图")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        failed_keyword = check_multimodal_failure(response, "image")
        if failed_keyword:
            test_logger.warning(
                f"模型可能不支持多模态（未能识别高分辨率图片）。Response contains: '{failed_keyword}'"
            )
            pytest.skip(
                f"Model may not support multimodal (high-res image recognition failed). "
                f"Response contains: '{failed_keyword}'"
            )

        content_lower = content.lower()
        assert any(
            kw in content_lower
            for kw in ["蓝", "blue", "灰", "gray", "grey", "青", "颜色", "color"]
        ), f"Model should identify the image color, got: {content[:500]}"

        test_logger.info("High resolution image test completed")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    def test_chart_ocr(self, api_client: ModelAPIClient, test_logger, record_warning):
        """C4 [P1]: 图表/OCR - 表格截图识别"""
        test_logger.info("=== 测试开始: 图表/OCR ===")

        # 创建包含文字的图片
        import io
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (400, 200), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((50, 80), "Test 123", fill="black")
        draw.text((50, 120), "Hello World", fill="black")

        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请读取图片中的文字"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            }
        ]
        test_logger.info("请求: OCR识别")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "OCR识别响应")
        self.log_full_response(test_logger, response, "C4-生成文字OCR")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        content = self.get_message_content(response)
        failed_keyword = check_multimodal_failure(response, "image")
        if failed_keyword:
            test_logger.warning(
                f"模型可能不支持多模态（未能识别OCR图片）。Response contains: '{failed_keyword}'"
            )
            pytest.skip(
                f"Model may not support multimodal (OCR image recognition failed). "
                f"Response contains: '{failed_keyword}'"
            )
        test_logger.info(f"OCR result: {content[:2000] if content else 'empty'}")

        content_lower = content.lower()
        has_test = "test" in content_lower or "123" in content
        has_hello = "hello" in content_lower or "world" in content_lower
        assert has_test or has_hello, (
            f"OCR should recognize 'Test 123' or 'Hello World', got: {content[:500]}"
        )

        # ========== 测试真实表格截图 ==========
        test_logger.info("=== 测试真实表格截图: bench_metrics.png ===")
        real_image_path = IMAGES_DIR / "table" / "bench_metrics.png"

        if not real_image_path.exists():
            record_warning(f"真实表格测试图片不存在: {real_image_path}")
            test_logger.warning(f"测试图片不存在，跳过真实表格OCR: {real_image_path}")
        else:
            with open(real_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请读取并分析这张表格图片中的所有数据内容",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                    ],
                }
            ]
            test_logger.info("请求: 真实表格OCR识别")
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages)
            TestLogger.log_response(test_logger, response, "真实表格OCR响应")
            self.log_full_response(test_logger, response, "C4-真实表格OCR")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            failed_keyword = check_multimodal_failure(response, "image")
            if failed_keyword:
                test_logger.warning(
                    f"模型可能不支持多模态（未能识别表格图片）。Response contains: '{failed_keyword}'"
                )
                pytest.skip(
                    f"Model may not support multimodal (table image recognition failed). "
                    f"Response contains: '{failed_keyword}'"
                )

            assert len(content.strip()) > 30, (
                f"Table OCR response should be detailed, got {len(content.strip())} chars"
            )

            test_logger.info(f"Real table OCR result: {content[:2000]}...")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_video_understanding(self, api_client: ModelAPIClient, test_logger):
        """C5 [P2]: 视频理解 - 输入视频文件"""
        test_logger.info("=== 测试开始: 视频理解 ===")

        video_url = "http://10.201.132.50:9999/videos/water.mp4"

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {"url": video_url},
                    },
                    {"type": "text", "text": "请描述这个视频的内容"},
                ],
            }
        ]
        test_logger.info("请求: 视频理解")

        response = api_client.chat_completion(messages)
        self.log_full_response(test_logger, response, "C5-视频理解")

        if response.get("error"):
            pytest.skip(
                f"Model does not support video understanding: {response.get('error')}"
            )

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        failed_keyword = check_multimodal_failure(response, "video")
        if failed_keyword:
            test_logger.warning(
                f"模型可能不支持多模态（未能识别视频）。Response contains: '{failed_keyword}'"
            )
            pytest.skip(
                f"Model may not support multimodal (video recognition failed). "
                f"Response contains: '{failed_keyword}'"
            )

        assert len(content.strip()) > 20, (
            f"Video understanding response should be descriptive, got {len(content.strip())} chars"
        )

        test_logger.info(f"Video understanding result: {content[:2000]}...")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_screenshot_to_code(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """C6: 代码截图→代码 - UI设计稿生成代码"""
        test_logger.info("=== 测试开始: 代码截图→代码 ===")

        # ========== 测试1: 识别Flask代码截图 ==========
        test_logger.info("=== 测试1: 识别Flask代码截图 ===")
        flask_image_path = CODE_DIR / "flask_app.png"

        if not flask_image_path.exists():
            test_logger.warning(
                f"测试图片不存在，跳过Flask代码识别: {flask_image_path}"
            )
            record_warning("Flask测试图片不存在")
        else:
            with open(flask_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请识别图片中的代码，并直接输出代码内容，不要有额外的解释",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                    ],
                }
            ]
            test_logger.info("请求: 识别Flask代码截图")
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages)
            TestLogger.log_response(test_logger, response, "Flask代码识别响应")
            self.log_full_response(test_logger, response, "C6-Flask代码识别")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            failed_keyword = check_multimodal_failure(response, "image")
            if failed_keyword:
                test_logger.warning(
                    f"模型可能不支持多模态（未能识别代码截图）。Response contains: '{failed_keyword}'"
                )
                pytest.skip(
                    f"Model may not support multimodal (screenshot recognition failed). "
                    f"Response contains: '{failed_keyword}'"
                )

            content_lower = content.lower()
            assert any(
                kw in content_lower
                for kw in ["flask", "app", "def ", "import", "route", "```"]
            ), f"Response should contain code-related content, got: {content[:500]}"

            test_logger.info(f"Recognized Flask code:\n{content}")

        # ========== 测试2: UI设计图生成登录代码 ==========
        test_logger.info("=== 测试2: UI设计图生成登录代码 ===")
        login_image_path = CODE_DIR / "login_ui.png"

        if not login_image_path.exists():
            test_logger.warning(
                f"测试图片不存在，跳过UI登录代码生成: {login_image_path}"
            )
            record_warning("UI测试图片不存在")
        else:
            with open(login_image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请根据这个UI设计图，生成一个简单的Python实现代码，直接输出代码不要有额外解释, 代码不需要保存到磁盘",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                    ],
                }
            ]
            test_logger.info("请求: UI设计图生成登录代码")
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages)
            TestLogger.log_response(test_logger, response, "UI登录代码响应")
            self.log_full_response(test_logger, response, "C6-UI登录代码")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            failed_keyword = check_multimodal_failure(response, "image")
            if failed_keyword:
                test_logger.warning(
                    f"模型可能不支持多模态（未能识别UI设计图）。Response contains: '{failed_keyword}'"
                )
                pytest.skip(
                    f"Model may not support multimodal (UI image recognition failed). "
                    f"Response contains: '{failed_keyword}'"
                )

            content_lower = content.lower()
            assert any(
                kw in content_lower
                for kw in [
                    "def ",
                    "class ",
                    "import",
                    "```",
                    "login",
                    "input",
                    "button",
                ]
            ), f"Response should contain code-related content, got: {content[:500]}"

            test_logger.info(f"Generated login code:\n{content}")

        test_logger.info("代码截图→代码测试完成")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_multimodal_tool_call(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
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
                            "city": {"type": "string", "description": "城市名称"}
                        },
                        "required": ["city"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_capital",
                    "description": "获取国家的首都信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "country": {"type": "string", "description": "国家名称"}
                        },
                        "required": ["country"],
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

        # 加载北京图片
        image_path = TOOL_DIR / "beijing.png"
        if not image_path.exists():
            pytest.skip(f"Test image not found: {image_path}")

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        # 图片内容是几个独立问题，翻译“大语言模型”为英文？北京天气如何？搜索关于“智算”的新闻
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请回答图片中的问题并调用适当的工具"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                    },
                ],
            }
        ]
        test_logger.info("请求: 多模态工具调用")
        TestLogger.log_request(test_logger, messages, {"tools": "4 tools"})

        response = api_client.chat_completion(messages, tools=tools, tool_choice="auto")
        TestLogger.log_response(test_logger, response, "多模态工具调用响应")
        self.log_full_response(test_logger, response, "C7-多模态工具调用")

        self.assert_response_success(response)

        message = response.get("choices", [{}])[0].get("message", {})
        tool_calls = message.get("tool_calls") or []

        if len(tool_calls) == 0:
            content = self.get_message_content(response)
            test_logger.warning(f"No tool calls triggered, content: {content}")
            failed_keyword = check_multimodal_failure(response, "image")
            if failed_keyword:
                test_logger.warning(
                    f"模型可能不支持多模态（未能识别工具调用所需图片）。Response contains: '{failed_keyword}'"
                )
                pytest.skip(
                    f"Model may not support multimodal (image for tool call recognition failed). "
                    f"Response contains: '{failed_keyword}'"
                )
            record_warning("未触发工具调用")
            assert content and len(content.strip()) > 0, "Should have response content"
        else:
            test_logger.info(f"触发了 {len(tool_calls)} 个工具调用")

            expected_tools = ["get_weather", "search_news", "translate", "get_capital"]
            called_tool_names = []

            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call.get("function", {}).get("name")
                arguments_raw = tool_call.get("function", {}).get("arguments", "{}")
                test_logger.info(f"工具调用 {i + 1}: {tool_name}({arguments_raw})")

                assert tool_name is not None, (
                    f"Tool call {i + 1} should have function name"
                )
                assert tool_name in expected_tools, (
                    f"Expected tool in {expected_tools}, got '{tool_name}'"
                )
                assert tool_call.get("id") is not None, (
                    f"Tool call '{tool_name}' should have 'id' field"
                )

                try:
                    args = (
                        json.loads(arguments_raw)
                        if isinstance(arguments_raw, str)
                        else arguments_raw
                    )
                except json.JSONDecodeError:
                    pytest.fail(
                        f"Tool '{tool_name}' arguments is not valid JSON: {arguments_raw}"
                    )

                assert isinstance(args, dict), (
                    f"Tool '{tool_name}' arguments should be dict"
                )
                assert len(args) > 0, (
                    f"Tool '{tool_name}' arguments should be non-empty, got: {args}"
                )
                called_tool_names.append(tool_name)

            assert len(called_tool_names) > 0, "Should have at least one tool call"

            test_logger.info(
                f"共触发 {len(tool_calls)} 个工具调用: {called_tool_names}"
            )

        test_logger.info("多模态工具调用测试通过")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    @pytest.mark.parametrize("format", ["png", "jpeg", "webp"])
    def test_image_format_compatibility(
        self, api_client: ModelAPIClient, format: str, test_logger
    ):
        """C8: 图片格式兼容性 - PNG/JPEG/WebP"""
        test_logger.info(f"=== 测试开始: 图片格式兼容性 ({format}) ===")

        import io
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="blue")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format=format.upper())
        img_b64 = base64.b64encode(img_byte_arr.getvalue()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"这张{format}格式的图片是什么颜色？"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{format};base64,{img_b64}"},
                    },
                ],
            }
        ]
        test_logger.info(f"请求: {format}格式图片")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{format}格式图片响应")
        self.log_full_response(test_logger, response, f"C8-{format}格式")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        failed_keyword = check_multimodal_failure(response, "image")
        if failed_keyword:
            test_logger.warning(
                f"模型可能不支持多模态（未能识别{format}格式图片）。Response contains: '{failed_keyword}'"
            )
            pytest.skip(
                f"Model may not support multimodal ({format} image recognition failed). "
                f"Response contains: '{failed_keyword}'"
            )

        content_lower = content.lower()
        # 仅接受表示具体颜色"蓝"的关键词，不接受"颜色"/"color"等泛化词——
        # 拒绝回复常含"无法看到图片的颜色"等措辞，泛化词会导致误判通过。
        assert any(kw in content_lower for kw in ["蓝", "blue"]), (
            f"Model should identify the {format} image color as blue, got: {content[:500]}"
        )

        test_logger.info(f"Format {format} test passed")
