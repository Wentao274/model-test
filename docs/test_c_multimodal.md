# C. 多模态能力测试

## 概述
验证模型对图片、视频等多媒体内容的理解和推理能力。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| C1 | 单图理解 | 合成图片+文本提问，验证颜色识别 | P1 |
| C2 | 多图对比 | 输入多张图片，验证跨图比较和推理 | P1 |
| C3 | 高分辨率图片 | 真实高清图片，验证细节识别能力 | P2 |
| C4 | 图表/OCR | 合成文字图片识别 | P1 |
| C5 | 视频理解 | 输入视频文件，验证时序理解和总结 | P2 |
| C6 | 代码截图→代码 | Flask代码截图识别并生成代码 | P2 |
| C7 | 多模态工具调用 | 基于图片内容触发工具调用 | P2 |
| C8 | 图片格式兼容性 | PNG/JPEG/WebP | P1 |
| C9 | 真实图片理解 | 真实图片描述能力 | P1 |
| C10 | 合成4K图片 | 验证大尺寸图片处理能力 | P2 |
| C11 | 表格OCR | 真实表格截图数据识别 | P1 |
| C12 | UI截图生成代码 | UI设计图生成对应代码 | P2 |

## 运行方式

```bash
# 运行所有多模态测试
pytest tests/test_c_multimodal.py -v

# 运行特定测试
pytest tests/test_c_multimodal.py::TestMultimodal::test_single_image_understanding -v
```

## 测试用例说明

### test_single_image_understanding（C1）
生成纯色合成图片（256×256 红图），验证模型能识别图片主色调。

### test_real_image_understanding（C9）
使用真实图片 `fixtures/images/single/sea_animals.png`，验证模型对真实图片内容的描述能力。

### test_multi_image_comparison（C2）
测试多图对比能力，从 `fixtures/images/multi/` 取前 2 张图片（按名称排序，确定性选图），验证跨图比较和推理。

### test_high_resolution_image（C3）
使用真实高清图片 `fixtures/images/high/sun_raise.jpg`，验证模型对高分辨率图片的细节识别能力。

### test_synthetic_4k_image（C10）
生成 3840×2160 合成图片，验证模型对大尺寸图片的处理能力（不被超大图拒绝）。

### test_chart_ocr（C4）
生成含文字的合成图片（800×400，大字号 TTF 字体），验证 OCR 识别能力。

### test_table_ocr（C11）
使用真实表格截图 `fixtures/images/table/bench_metrics.png`，验证模型对表格数据的识别与读取能力。

### test_video_understanding（C5）
通过 URL 输入视频文件，验证视频时序理解和内容总结能力。

### test_screenshot_to_code_flask（C6）
使用代码截图 `fixtures/code/flask_app.png`，验证模型识别代码截图并生成代码的能力。

### test_screenshot_to_code_ui（C12）
使用 UI 设计图 `fixtures/code/login_ui.png`，验证模型根据 UI 截图生成对应代码的能力。

### test_multimodal_tool_call（C7）
基于图片内容触发工具调用，验证模型能否从图片中识别问题并选择正确的工具调用且参数与图片内容对应。

### test_image_format_compatibility（C8）
参数化测试不同图片格式（PNG、JPEG、WebP）的兼容性。

## 注意事项
- 部分模型可能不支持多模态功能，会自动跳过并记录告警
- 需要在 `fixtures/images`、`fixtures/code`、`fixtures/tool` 目录下放置测试素材
- 测试启动前会进行多模态能力探测（按模型名隔离缓存），探测失败则跳过所有 C 类用例
- WebP 编码依赖 PIL 的 libwebp 支持，缺失时该格式用例自动跳过
- 跳过原因会记录在测试报告的"跳过用例说明"区域。当模型不支持多模态时，C 类整类跳过，报告显示一行汇总（如"C. 多模态能力（全部 12 个用例跳过）：Model does not support multimodal input"）