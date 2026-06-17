# C. 多模态能力测试

## 概述
验证模型对图片、视频等多媒体内容的理解和推理能力。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| C1 | 单图理解 | 输入一张图片+文本提问，验证视觉理解 | P1 |
| C2 | 多图对比 | 输入多张图片，验证跨图比较和推理 | P1 |
| C3 | 高分辨率图片 | 4K分辨率图片，验证细节识别能力 | P2 |
| C4 | 图表/OCR | 表格截图、流程图、手写文字识别 | P1 |
| C5 | 视频理解 | 输入视频文件，验证时序理解和总结 | P2 |
| C6 | 代码截图→代码 | UI设计稿/代码截图，生成对应代码 | P2 |
| C7 | 多模态工具调用 | 基于图片内容触发工具调用 | P2 |
| C8 | 图片格式兼容性 | PNG/JPEG/WebP/GIF/Base64编码 | P1 |

## 运行方式

```bash
# 运行所有多模态测试
pytest tests/test_c_multimodal.py -v

# 运行特定测试
pytest tests/test_c_multimodal.py::TestMultimodal::test_single_image_understanding -v
```

## 测试用例说明

### test_single_image_understanding
生成简单的测试图片（纯色图），验证模型能识别图片内容。

### test_multi_image_comparison
测试多图对比能力，需要至少2张测试图片（需要创建fixtures/images目录）。

### test_high_resolution_image
测试4K分辨率图片的处理能力。

### test_chart_ocr
测试文字识别（OCR）能力，验证模型能读取图片中的文字。

### test_video_understanding
测试视频理解能力（需要实际视频文件，当前跳过）。

### test_screenshot_to_code
测试UI截图转代码能力（需要UI截图素材，当前跳过）。

### test_multimodal_tool_call
测试基于图片内容触发工具调用（需要工具定义，当前跳过）。

### test_image_format_compatibility
参数化测试不同图片格式（PNG、JPEG、WebP）的兼容性。

## 注意事项
- 部分模型可能不支持多模态功能
- 需要在fixtures/images目录下放置测试图片
- 某些测试需要实际的视频或截图素材