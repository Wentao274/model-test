"""
运行测试并生成报告的脚本 - 支持所有测试分类
"""
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path
import subprocess
import re


def main():
    # 加载配置
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 获取启用的模型
    model = None
    for name, cfg in config.get('models', {}).items():
        if cfg.get('enabled', False):
            model = {
                'name': name,
                'display_name': cfg.get('display_name', name),
                'model_name': cfg.get('name', name)
            }
            break

    if not model:
        print("错误: 没有启用的模型")
        sys.exit(1)

    print(f"测试模型: {model['display_name']}")
    print("运行测试...")

    # 运行测试 - 先运行P0测试
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-v', '--tb=line', '-m', 'p0'],
        capture_output=True,
        text=True
    )

    # 解析测试结果
    test_results = {}  # key -> PASSED/FAILED

    # 定义测试名称到测试ID的映射
    test_mapping = {
        # A类 - 基础推理能力
        'test_single_turn': 'A1',
        'test_multi_turn': 'A2',
        'test_system_prompt': 'A3',
        'test_streaming_output': 'A4',
        'test_non_streaming': 'A5',
        'test_temperature_control': 'A6',
        'test_top_p': 'A7',
        'test_max_tokens': 'A8',
        'test_stop_sequences': 'A9',
        'test_seed_reproducibility': 'A10',
        'test_multilingual': 'A11',
        'test_special_tokens': 'A12',
        # B类 - 高级生成功能
        'test_thinking_mode': 'B1',
        'test_non_thinking_mode': 'B2',
        'test_thinking_mode_switch': 'B3',
        'test_single_tool_call': 'B4',
        'test_multiple_tool': 'B5',
        'test_parallel_tool': 'B6',
        'test_multi_step_tool': 'B7',
        'test_json_mode': 'B8',
        'test_structured_output': 'B9',
        'test_prefix_suffix': 'B10',
    }

    # 匹配测试行
    pattern = r'(test_\w+)(?:\[([^\]]+)\])?\s+(PASSED|FAILED|SKIPPED)'

    for line in result.stdout.split('\n'):
        match = re.search(pattern, line)
        if match:
            test_name = match.group(1)
            params = match.group(2)
            status = match.group(3)

            # 查找对应的测试ID
            for func_name, test_id in test_mapping.items():
                if func_name in test_name:
                    # 分类
                    if test_id.startswith('A'):
                        marker = 'a_basic'
                    elif test_id.startswith('B'):
                        marker = 'b_advanced'
                    else:
                        marker = 'unknown'

                    test_results[f"{marker}_{test_id}"] = status
                    break

    print(f"解析到 {len(test_results)} 个测试结果")

    # 生成报告
    test_date = datetime.now().strftime("%Y%m%d%H%M%S")
    test_date_formatted = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path("test_reports") / f"{model['name']}_{test_date}"
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# {model['display_name']} 测试报告")
    lines.append("")
    lines.append(f"> 测试日期：{test_date_formatted}")
    lines.append(f"> 测试时间：{datetime.now().strftime('%H:%M:%S')}")
    lines.append(f"> 模型：{model['display_name']} (`{model['model_name']}`)")
    lines.append("")

    total_a = 0
    passed_a = 0
    failed_a = 0

    # A类测试
    lines.append("## A. 基础推理能力")
    lines.append("")
    lines.append("| #   | 测试点           | 测试内容                             | 状态 |")
    lines.append("|-----|----------------|----------------------------------|------|")

    a_tests = [
        ("A1", "单轮对话", "发送单条prompt，验证正常生成"),
        ("A2", "多轮对话", "5轮对话，验证上下文保持和连贯性"),
        ("A3", "System Prompt", "设置系统角色，验证模型遵循程度"),
        ("A4", "流式输出", "stream=true，验证SSE逐token返回"),
        ("A5", "非流式输出", "stream=false，验证完整返回"),
        ("A6", "Temperature 控制", "temp=0 vs temp=1.0，验证输出差异"),
        ("A7", "Top-p/Top-k采样", "不同top_p/top_k值，验证多样性控制"),
        ("A8", "Max Tokens限制", "设置max_tokens，验证输出不超限"),
        ("A9", "Stop Sequences", "设置stop token，验证截断"),
        ("A10", "Seed 可复现性", "相同seed+temp=0，验证输出一致"),
        ("A11", "多语言能力", "中/英/日/韩/法等多语言输入输出"),
        ("A12", "特殊Token处理", "含emoji、代码块、数学符号、HTML标签"),
    ]

    for test_id, test_name, test_desc in a_tests:
        key = f"a_basic_{test_id}"
        status = test_results.get(key, "未运行")

        if status == "PASSED":
            status_icon = "✅"
            passed_a += 1
        elif status == "FAILED":
            status_icon = "❌"
            failed_a += 1
        else:
            status_icon = "⏳"

        total_a += 1

        if len(test_desc) > 30:
            test_desc = test_desc[:27] + "..."

        lines.append(f"| {test_id:2s}  | {test_name:12s} | {test_desc:30s} | {status_icon}  |")

    lines.append("")

    total_b = 0
    passed_b = 0
    failed_b = 0

    # B类测试
    lines.append("## B. 高级生成功能")
    lines.append("")
    lines.append("| #   | 测试点           | 测试内容                             | 状态 |")
    lines.append("|-----|----------------|----------------------------------|------|")

    b_tests = [
        ("B1", "思考模式（Thinking）", "开启thinking mode，验证返回思考链+最终答案"),
        ("B2", "非思考模式（Instant）", "关闭thinking，验证无hidden thinking泄漏"),
        ("B3", "思考模式切换", "同一会话内thinking↔non-thinking切换"),
        ("B4", "工具调用-单工具", "定义单个function，验证模型正确调用并传参"),
        ("B5", "工具调用-多工具", "定义多个function，验证模型选择正确的工具"),
        ("B6", "工具调用-并行调用", "单次回复中并行调用多个工具"),
        ("B7", "工具调用-多步链式", "工具结果作为下一步输入，验证3+步链式执行"),
        ("B8", "JSON Mode", "response_format=json_object，验证输出合法JSON"),
        ("B9", "结构化输出", "JSON Schema约束输出格式，验证字段完整性"),
        ("B10", "Prefix/Suffix约束", "指定输出前缀或格式模板，验证遵循度"),
    ]

    for test_id, test_name, test_desc in b_tests:
        key = f"b_advanced_{test_id}"
        status = test_results.get(key, "未运行")

        if status == "PASSED":
            status_icon = "✅"
            passed_b += 1
        elif status == "FAILED":
            status_icon = "❌"
            failed_b += 1
        else:
            status_icon = "⏳"

        total_b += 1

        if len(test_desc) > 30:
            test_desc = test_desc[:27] + "..."

        lines.append(f"| {test_id:2s}  | {test_name:12s} | {test_desc:30s} | {status_icon}  |")

    lines.append("")

    # 状态说明
    lines.append("---")
    lines.append("")
    lines.append("**状态说明**：")
    lines.append("- ✅ 已通过")
    lines.append("- ❌ 未通过")
    lines.append("- ⏳ 未测试")
    lines.append("")

    # 统计汇总
    total = total_a + total_b
    passed = passed_a + passed_b
    failed = failed_a + failed_b
    not_tested = total - passed - failed

    lines.append("## 统计汇总")
    lines.append("")
    lines.append(f"- 运行测试点：{passed + failed}")
    lines.append(f"- 已通过：{passed}")
    lines.append(f"- 未通过：{failed}")
    lines.append(f"- 未测试：{not_tested}")
    lines.append(f"- 通过率：{passed*100//max(passed+failed,1)}%")

    filename = f"test_report_{model['name']}_{test_date}.md"
    filepath = output_dir / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print(f"\n报告已生成: {filepath}")
    print(f"测试结果: 通过 {passed}/{total}")
    print(f"模型: {model['display_name']}")
    print(f"日期: {test_date_formatted}")


if __name__ == "__main__":
    main()