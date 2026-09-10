"""
C. 多模态能力测试

测试点：
- C1: 单图理解 - 合成图片+文本提问，验证视觉理解 [P1]
- C2: 多图对比 - 输入多张图片，验证跨图比较和推理 [P1]
- C3: 高分辨率图片 - 真实高清图片，验证细节识别能力 [P2]
- C4: 图表/OCR - 合成文字图片识别 [P1]
- C5: 视频理解 - 输入视频文件，验证时序理解和总结 [P2]
- C6: 代码截图→代码 - Flask代码截图识别并生成代码 [P2]
- C7: 多模态工具调用 - 基于图片内容触发工具调用 [P2]
- C8: 图片格式兼容性 - PNG/JPEG/WebP [P1]
- C9: 真实图片理解 - 真实图片描述能力 [P1]
- C10: 合成4K图片 - 验证大尺寸图片处理能力 [P2]
- C11: 表格OCR - 真实表格截图数据识别 [P1]
- C12: UI截图生成代码 - UI设计图生成对应代码 [P2]
"""

import os
import json
import pytest
from pathlib import Path

from base.base_test import BaseTest, MultimodalTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


# 测试用图片路径
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
IMAGES_DIR = FIXTURES_DIR / "images"
MULTI_IMAGES_DIR = FIXTURES_DIR / "images" / "multi"
VIDEO_DIR = FIXTURES_DIR / "videos"
TOOL_DIR = FIXTURES_DIR / "tool"
CODE_DIR = FIXTURES_DIR / "code"

# 模块级多模态支持探测结果缓存（按模型名隔离，避免多模型串测时缓存污染）
# model_name -> bool
_multimodal_probe_results = {}
# model_name -> str
_multimodal_probe_reasons = {}


def _probe_multimodal_support(api_client, test_logger, model_name):
    """探测当前模型是否支持多模态输入

    发送一个带图片的简单请求，检测：
    1. API 层：HTTP 400/422/404/501 异常，或响应体含 error 字段
    2. 内容层：HTTP 200 但模型回复"看不到图片""无法处理图片"等拒绝文本

    内容层检测不使用 positive_phrases 覆盖，避免模型说
    "看不到图片，但图片中显示的应该是红色"时被误判为已识别。
    """
    img_b64 = MultimodalTestMixin.generate_solid_image_base64("red", (100, 100), "PNG")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这张图片是什么颜色？"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                },
            ],
        }
    ]

    test_logger.info("=== 多模态能力探测开始 ===")

    try:
        response = api_client.chat_completion(messages)
    except Exception as e:
        error_msg = str(e)
        error_lower = error_msg.lower()
        skip_status_codes = [
            "status 400",
            "status 422",
            "status 404",
            "status 501",
        ]
        multimodal_keywords = [
            "image",
            "multimodal",
            "vision",
            "visual",
            "video",
            "图片",
            "图像",
            "多模态",
            "视觉",
            "视频",
            "not support",
            "unsupported",
            "不支持",
            "无法处理",
        ]
        is_skip_status = any(sc in error_lower for sc in skip_status_codes)
        has_multimodal_keyword = any(kw in error_lower for kw in multimodal_keywords)
        if is_skip_status or has_multimodal_keyword:
            _multimodal_probe_results[model_name] = False
            _multimodal_probe_reasons[model_name] = f"API rejected: {error_msg[:200]}"
            test_logger.warning(f"模型不支持多模态输入: {error_msg[:200]}")
            return False
        raise

    if response.get("error"):
        error_detail = response.get("error")
        if isinstance(error_detail, dict):
            error_msg = error_detail.get("message", str(error_detail))
        else:
            error_msg = str(error_detail)
        _multimodal_probe_results[model_name] = False
        _multimodal_probe_reasons[model_name] = f"API error: {error_msg[:200]}"
        test_logger.warning(f"模型不支持多模态输入: {error_msg[:200]}")
        return False

    unsupported_keyword = MultimodalTestMixin._check_content_unsupported(
        response, "image"
    )
    if unsupported_keyword:
        _multimodal_probe_results[model_name] = False
        _multimodal_probe_reasons[model_name] = (
            f"Response indicates inability to process image: "
            f"matched '{unsupported_keyword}'"
        )
        test_logger.warning(
            f"模型不支持多模态（响应含拒绝关键词 '{unsupported_keyword}'）"
        )
        return False

    _multimodal_probe_results[model_name] = True
    test_logger.info("=== 多模态能力探测通过，模型支持多模态 ===")
    return True


@pytest.fixture(autouse=True)
def probe_multimodal_support(api_client: ModelAPIClient, test_logger):
    """多模态能力探测 fixture（autouse，function 级）

    在第一个多模态测试用例执行前进行一次探测，结果按模型名缓存。
    如果模型不支持多模态，后续所有 C 类测试用例均自动跳过。
    """
    model_name = api_client.model_name
    if _multimodal_probe_results.get(model_name) is False:
        pytest.skip(
            f"Model does not support multimodal input "
            f"(probed earlier): {_multimodal_probe_reasons.get(model_name, '')}"
        )
    elif _multimodal_probe_results.get(model_name) is True:
        return

    if not _probe_multimodal_support(api_client, test_logger, model_name):
        pytest.skip(
            f"Model does not support multimodal input: "
            f"{_multimodal_probe_reasons.get(model_name, '')}"
        )


class TestMultimodal(BaseTest, MultimodalTestMixin):
    """多模态能力测试类"""

    def get_test_category(self) -> str:
        return "C. 多模态能力"

    def _skip_if_image_missing(
        self, path: Path, test_logger, record_warning, desc: str
    ):
        """真实图片缺失时统一告警并跳过"""
        if not path.exists():
            msg = f"测试图片不存在，跳过{desc}: {path}"
            test_logger.warning(msg)
            record_warning(msg)
            pytest.skip(msg)

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_single_image_understanding(self, api_client: ModelAPIClient, test_logger):
        """C1 [P1]: 单图理解 - 合成图片+文本提问，验证颜色识别"""
        test_logger.info("=== 测试开始: 单图理解（合成图） ===")

        # 生成 256x256 红色图片（避免过小被部分模型拒绝）
        img_b64 = self.generate_solid_image_base64("red", (256, 256), "PNG")
        messages = self.build_image_messages(
            "这张图片的主要颜色是什么？", img_b64, "image/png"
        )
        test_logger.info("请求: 合成单图理解")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "单图理解响应")
        self.log_full_response(test_logger, response, "C1-合成红图理解")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "合成红图理解")

        content = self.get_message_content(response)
        content_lower = content.lower()
        assert any(kw in content_lower for kw in ["红", "red", "红色"]), (
            f"Model should identify the image color as red, got: {content[:500]}"
        )
        test_logger.info(f"合成图理解响应: {content[:2000]}...")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    def test_real_image_understanding(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """C9 [P1]: 真实图片理解 - 真实图片描述能力"""
        test_logger.info("=== 测试开始: 真实图片理解 ===")

        real_image_path = IMAGES_DIR / "single" / "sea_animals.png"
        self._skip_if_image_missing(
            real_image_path, test_logger, record_warning, "真实图片理解"
        )

        img_b64 = self.load_image_as_base64(real_image_path)
        messages = self.build_image_messages(
            "请描述这张图片的内容", img_b64, "image/png"
        )
        test_logger.info("请求: 真实图片理解")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "真实图片理解响应")
        self.log_full_response(test_logger, response, "C9-真实图片理解")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "真实图片理解")

        content = self.get_message_content(response)
        assert len(content) > 10, (
            f"Response should be descriptive, got only {len(content)} chars"
        )
        test_logger.info(f"真实图片理解响应: {content[:2000]}...")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    @pytest.mark.skipif(
        not MULTI_IMAGES_DIR.exists(), reason="Images directory not found"
    )
    def test_multi_image_comparison(self, api_client: ModelAPIClient, test_logger):
        """C2 [P1]: 多图对比 - 输入多张图片，验证跨图比较"""
        test_logger.info("=== 测试开始: 多图对比 ===")

        # 排序保证图片选择确定，便于定位与复现
        image_files = sorted(MULTI_IMAGES_DIR.glob("*.png"))[:2]

        if len(image_files) < 2:
            pytest.skip("Need at least 2 images for comparison test")

        content_parts = [{"type": "text", "text": "这两张图片有什么区别？"}]
        for img_path in image_files:
            img_b64 = self.load_image_as_base64(img_path)
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                }
            )

        messages = [{"role": "user", "content": content_parts}]
        test_logger.info(
            f"请求: 多图对比 (图片: {[p.name for p in image_files]})"
        )
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "多图对比响应")
        self.log_full_response(test_logger, response, "C2-多图对比")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "多图对比")

        content = self.get_message_content(response)
        assert len(content.strip()) > 20, (
            f"Comparison response should be descriptive, "
            f"got only {len(content.strip())} chars"
        )

        content_lower = content.lower()
        assert any(
            kw in content_lower
            for kw in ["区别", "不同", "差异", "differ", "comparison", "对比", "相比"]
        ), f"Response should describe differences between images, got: {content[:500]}"

        test_logger.info("多图对比测试完成")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_high_resolution_image(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """C3 [P2]: 高分辨率图片 - 真实高清图，验证细节识别能力"""
        test_logger.info("=== 测试开始: 高分辨率图片（真实高清） ===")

        real_image_path = IMAGES_DIR / "high" / "sun_raise.jpg"
        self._skip_if_image_missing(
            real_image_path, test_logger, record_warning, "真实高清图片"
        )

        img_b64 = self.load_image_as_base64(real_image_path)
        messages = self.build_image_messages(
            "请详细描述这张图片的内容", img_b64, "image/jpeg"
        )
        test_logger.info("请求: 真实高清图片理解")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "真实高清图片响应")
        self.log_full_response(test_logger, response, "C3-真实高清图")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "真实高清图片")

        content = self.get_message_content(response)
        assert len(content) > 20, (
            f"Response should be detailed for high-res image, got {len(content)} chars"
        )

        test_logger.info(f"真实高清图片响应: {content[:2000]}...")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_synthetic_4k_image(self, api_client: ModelAPIClient, test_logger):
        """C10 [P2]: 合成4K图片 - 验证大尺寸图片处理能力"""
        test_logger.info("=== 测试开始: 合成4K图片 ===")

        img_b64 = self.generate_solid_image_base64(
            (100, 150, 200), (3840, 2160), "PNG"
        )
        messages = self.build_image_messages(
            "这张图片是什么分辨率？请描述图片内容", img_b64, "image/png"
        )
        test_logger.info("请求: 4K高分辨率图片")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "4K高分辨率图片响应")
        self.log_full_response(test_logger, response, "C10-4K生成图")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "4K图片")

        content = self.get_message_content(response)
        content_lower = content.lower()
        # 仅接受具体颜色词，不接受"颜色"/"color"等泛化词——
        # 拒绝回复常含"无法看到图片的颜色"等措辞，泛化词会导致误判通过。
        assert any(
            kw in content_lower for kw in ["蓝", "blue", "灰", "gray", "grey", "青"]
        ), f"Model should identify the image color, got: {content[:500]}"

        test_logger.info("4K图片测试完成")

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    def test_chart_ocr(self, api_client: ModelAPIClient, test_logger):
        """C4 [P1]: 图表/OCR - 合成文字图片识别"""
        test_logger.info("=== 测试开始: 图表/OCR（合成文字） ===")

        # 大尺寸 + TTF 大字号，提升 OCR 可识别性
        img_b64 = self.generate_text_image_base64(
            ["Test 123", "Hello World"], size=(800, 400), font_size=48
        )
        messages = self.build_image_messages(
            "请读取图片中的文字", img_b64, "image/png"
        )
        test_logger.info("请求: 合成文字OCR识别")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "OCR识别响应")
        self.log_full_response(test_logger, response, "C4-合成文字OCR")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "合成文字OCR")

        content = self.get_message_content(response)
        test_logger.info(f"OCR result: {content[:2000] if content else 'empty'}")

        content_lower = content.lower()
        # 使用 "123" 与 "hello+world" 等较具体特征，避免 "test" 单词误判
        has_test = "123" in content or "test 123" in content_lower
        has_hello = "hello" in content_lower and "world" in content_lower
        assert has_test or has_hello, (
            f"OCR should recognize 'Test 123' or 'Hello World', got: {content[:500]}"
        )

    @pytest.mark.c_multimodal
    @pytest.mark.p1
    def test_table_ocr(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """C11 [P1]: 表格OCR - 真实表格截图数据识别"""
        test_logger.info("=== 测试开始: 表格OCR ===")

        real_image_path = IMAGES_DIR / "table" / "bench_metrics.png"
        self._skip_if_image_missing(
            real_image_path, test_logger, record_warning, "真实表格OCR"
        )

        img_b64 = self.load_image_as_base64(real_image_path)
        messages = self.build_image_messages(
            "请读取并分析这张表格图片中的所有数据内容", img_b64, "image/png"
        )
        test_logger.info("请求: 真实表格OCR识别")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "真实表格OCR响应")
        self.log_full_response(test_logger, response, "C11-真实表格OCR")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "真实表格OCR")

        content = self.get_message_content(response)
        assert len(content.strip()) > 30, (
            f"Table OCR response should be detailed, got {len(content.strip())} chars"
        )

        test_logger.info(f"真实表格OCR结果: {content[:2000]}...")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_video_understanding(self, api_client: ModelAPIClient, test_logger):
        """C5 [P2]: 视频理解 - 输入视频文件"""
        test_logger.info("=== 测试开始: 视频理解 ===")

        video_url = "http://10.201.132.50:9999/videos/water.mp4"

        # 清除代理环境变量，避免影响视频访问
        _proxy_env_keys = [
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "all_proxy",
            "ALL_PROXY",
        ]
        _saved_proxies = {}
        for _key in _proxy_env_keys:
            if _key in os.environ:
                _saved_proxies[_key] = os.environ.pop(_key)
                test_logger.warning(
                    f"检测并清除代理环境变量: {_key}={_saved_proxies[_key]}"
                )
        test_logger.info(
            f"代理状态检查: http_proxy={os.environ.get('http_proxy', '(未设置)')}, "
            f"https_proxy={os.environ.get('https_proxy', '(未设置)')}"
        )

        try:
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
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages)
            self.log_full_response(test_logger, response, "C5-视频理解")

            if response.get("error"):
                pytest.skip(
                    f"Model does not support video understanding: {response.get('error')}"
                )

            self.assert_response_success(response)
            self.assert_content_not_empty(response)
            self.skip_if_unsupported(response, "video", test_logger, "视频理解")

            content = self.get_message_content(response)
            assert len(content.strip()) > 20, (
                f"Video understanding response should be descriptive, "
                f"got {len(content.strip())} chars"
            )

            test_logger.info(f"视频理解结果: {content[:2000]}...")
        finally:
            for _key, _val in _saved_proxies.items():
                os.environ[_key] = _val

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_screenshot_to_code_flask(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """C6 [P2]: 代码截图→代码 - Flask代码截图识别"""
        test_logger.info("=== 测试开始: 代码截图→代码（Flask） ===")

        flask_image_path = CODE_DIR / "flask_app.png"
        self._skip_if_image_missing(
            flask_image_path, test_logger, record_warning, "Flask代码截图"
        )

        img_b64 = self.load_image_as_base64(flask_image_path)
        messages = self.build_image_messages(
            "请识别图片中的代码，并直接输出代码内容，不要有额外的解释",
            img_b64,
            "image/png",
        )
        test_logger.info("请求: 识别Flask代码截图")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "Flask代码识别响应")
        self.log_full_response(test_logger, response, "C6-Flask代码识别")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "Flask代码截图")

        content = self.get_message_content(response)
        content_lower = content.lower()
        # 优先以代码块或 Flask 专属特征判定，避免 "app" 等通用词误判
        has_code_block = "```" in content_lower
        has_flask_specific = any(
            kw in content_lower
            for kw in ["flask", "from flask", "@app.route", "route"]
        )
        has_code_struct = "def " in content_lower and "import" in content_lower
        assert has_code_block or has_flask_specific or has_code_struct, (
            f"Response should contain code-related content, got: {content[:500]}"
        )

        test_logger.info(f"识别的Flask代码:\n{content}")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_screenshot_to_code_ui(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """C12 [P2]: UI截图生成代码 - UI设计图生成对应代码"""
        test_logger.info("=== 测试开始: UI截图生成代码 ===")

        login_image_path = CODE_DIR / "login_ui.png"
        self._skip_if_image_missing(
            login_image_path, test_logger, record_warning, "UI登录图"
        )

        img_b64 = self.load_image_as_base64(login_image_path)
        messages = self.build_image_messages(
            "请根据这个UI设计图，生成一个简单的Python实现代码，"
            "直接输出代码不要有额外解释, 代码不需要保存到磁盘",
            img_b64,
            "image/png",
        )
        test_logger.info("请求: UI设计图生成登录代码")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, "UI登录代码响应")
        self.log_full_response(test_logger, response, "C12-UI登录代码")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, "UI设计图")

        content = self.get_message_content(response)
        content_lower = content.lower()
        # 要求同时具备代码结构特征与 UI 元素特征，避免单纯描述性文本误判
        has_code = ("```" in content_lower) or any(
            kw in content_lower for kw in ["def ", "class ", "import"]
        )
        has_ui = any(
            kw in content_lower
            for kw in ["login", "input", "button", "password", "submit"]
        )
        assert has_code and has_ui, (
            f"Response should contain code with UI elements, got: {content[:500]}"
        )

        test_logger.info(f"生成的登录代码:\n{content}")

    @pytest.mark.c_multimodal
    @pytest.mark.p2
    def test_multimodal_tool_call(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """C7 [P2]: 多模态工具调用 - 基于图片内容触发工具调用"""
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

        img_b64 = self.load_image_as_base64(image_path)

        # 图片内容是几个独立问题：翻译"大语言模型"为英文？北京天气如何？搜索关于"智算"的新闻
        messages = self.build_image_messages(
            "请回答图片中的问题并调用适当的工具", img_b64, "image/png"
        )
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
            test_logger.warning(f"未触发工具调用, content: {content}")
            self.skip_if_unsupported(response, "image", test_logger, "工具调用图片识别")
            record_warning("未触发工具调用")
            assert content and len(content.strip()) > 0, "Should have response content"
            return

        test_logger.info(f"触发了 {len(tool_calls)} 个工具调用")

        expected_tools = ["get_weather", "search_news", "translate", "get_capital"]
        # 图片中实际问题对应的工具及其参数相关性校验
        relevant_tool_check = {
            "get_weather": lambda args: any(
                k in str(args.get("city", "")).lower() for k in ["北京", "beijing"]
            ),
            "search_news": lambda args: any(
                k in str(args.get("keyword", "")).lower() for k in ["智算", "zhisuan"]
            ),
            "translate": lambda args: (
                "大语言模型" in str(args.get("text", ""))
                or "language model" in str(args.get("text", "")).lower()
            )
            and bool(args.get("target_lang")),
        }

        called_tool_names = []
        content_relevant_called = False

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

            if tool_name in relevant_tool_check and relevant_tool_check[tool_name](args):
                content_relevant_called = True

        assert len(called_tool_names) > 0, "Should have at least one tool call"
        # 至少一个工具的参数需与图片内容对应，避免模型随机调用无关工具/干扰项
        assert content_relevant_called, (
            f"At least one tool call args should match image content, "
            f"got: {called_tool_names}"
        )

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
        """C8 [P1]: 图片格式兼容性 - PNG/JPEG/WebP"""
        test_logger.info(f"=== 测试开始: 图片格式兼容性 ({format}) ===")

        try:
            img_b64 = self.generate_solid_image_base64(
                "blue", (256, 256), format.upper()
            )
        except (KeyError, OSError) as e:
            pytest.skip(f"PIL does not support {format} encoding in this env: {e}")

        messages = self.build_image_messages(
            f"这张{format}格式的图片是什么颜色？",
            img_b64,
            f"image/{format}",
        )
        test_logger.info(f"请求: {format}格式图片")
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages)
        TestLogger.log_response(test_logger, response, f"{format}格式图片响应")
        self.log_full_response(test_logger, response, f"C8-{format}格式")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        self.skip_if_unsupported(response, "image", test_logger, f"{format}格式图片")

        content = self.get_message_content(response)
        content_lower = content.lower()
        # 仅接受表示具体颜色"蓝"的关键词，不接受"颜色"/"color"等泛化词——
        # 拒绝回复常含"无法看到图片的颜色"等措辞，泛化词会导致误判通过。
        assert any(kw in content_lower for kw in ["蓝", "blue"]), (
            f"Model should identify the {format} image color as blue, got: {content[:500]}"
        )

        test_logger.info(f"Format {format} test passed")
