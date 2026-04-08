"""
测试运行和报告生成脚本

运行测试并生成类似checkpoints.md格式的测试报告
"""
import os
import sys
import json
import yaml
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple
import subprocess


# 测试分类与测试点定义
TEST_CATEGORIES = {
    "a_basic": {
        "name": "A. 基础推理能力",
        "tests": [
            ("A1", "单轮对话", "发送单条prompt，验证正常生成", "P0"),
            ("A2", "多轮对话", "5轮对话，验证上下文保持和连贯性", "P0"),
            ("A3", "System Prompt", "设置系统角色，验证模型遵循程度", "P0"),
            ("A4", "流式输出", "stream=true，验证SSE逐token返回", "P0"),
            ("A5", "非流式输出", "stream=false，验证完整返回", "P0"),
            ("A6", "Temperature 控制", "temp=0 vs temp=1.0，验证输出差异", "P0"),
            ("A7", "Top-p/Top-k采样", "不同top_p/top_k值，验证多样性控制", "P1"),
            ("A8", "Max Tokens限制", "设置max_tokens，验证输出不超限", "P0"),
            ("A9", "Stop Sequences", "设置stop token，验证截断", "P1"),
            ("A10", "Seed 可复现性", "相同seed+temp=0，验证输出一致", "P1"),
            ("A11", "多语言能力", "中/英/日/韩/法等多语言输入输出", "P1"),
            ("A12", "特殊Token处理", "含emoji、代码块、数学符号、HTML标签", "P1"),
        ]
    },
    "b_advanced": {
        "name": "B. 高级生成功能",
        "tests": [
            ("B1", "思考模式（Thinking）", "开启thinking mode，验证返回思考链+最终答案", "P0"),
            ("B2", "非思考模式（Instant）", "关闭thinking，验证无hidden thinking泄漏", "P0"),
            ("B3", "思考模式切换", "同一会话内thinking↔non-thinking切换", "P1"),
            ("B4", "工具调用-单工具", "定义单个function，验证模型正确调用并传参", "P0"),
            ("B5", "工具调用-多工具", "定义多个function，验证模型选择正确的工具", "P0"),
            ("B6", "工具调用-并行调用", "单次回复中并行调用多个工具", "P1"),
            ("B7", "工具调用-多步链式", "工具结果作为下一步输入，验证3+步链式执行", "P1"),
            ("B8", "JSON Mode", "response_format=json_object，验证输出合法JSON", "P0"),
            ("B9", "结构化输出", "JSON Schema约束输出格式，验证字段完整性", "P0"),
            ("B10", "Prefix/Suffix约束", "指定输出前缀或格式模板，验证遵循度", "P2"),
        ]
    },
    "c_multimodal": {
        "name": "C. 多模态能力",
        "tests": [
            ("C1", "单图理解", "输入一张图片+文本提问，验证视觉理解", "P0"),
            ("C2", "多图对比", "输入多张图片，验证跨图比较和推理", "P1"),
            ("C3", "高分辨率图片", "4K分辨率图片，验证细节识别能力", "P1"),
            ("C4", "图表/OCR", "表格截图、流程图、手写文字识别", "P0"),
            ("C5", "视频理解", "输入视频文件，验证时序理解和总结", "P1"),
            ("C6", "代码截图→代码", "UI设计稿/代码截图，生成对应代码", "P2"),
            ("C7", "多模态工具调用", "基于图片内容触发工具调用", "P2"),
            ("C8", "图片格式兼容性", "PNG/JPEG/WebP/GIF/Base64编码", "P1"),
        ]
    },
    "d_long_context": {
        "name": "D. 长上下文处理",
        "tests": [
            ("D1", "短上下文基线", "input 1K tokens，验证正常推理", "P0"),
            ("D2", "中等上下文", "input 8K-16K tokens，验证质量不降", "P0"),
            ("D3", "长上下文", "input 32K-64K tokens，验证召回和推理", "P0"),
            ("D4", "超长上下文", "input 128K+ tokens，验证不OOM且可用", "P1"),
            ("D5", "大海捞针（NIAH）", "长文本中插入特定信息，验证召回率", "P0"),
            ("D6", "上下文边界行为", "输入恰好等于max_model_len", "P1"),
            ("D7", "超出上下文截断", "输入超过模型限制，验证截断/拒绝策略", "P1"),
            ("D8", "长输出生成", "要求生成4K-8K tokens的长文本", "P1"),
        ]
    },
    "e_performance": {
        "name": "E. 性能指标",
        "tests": [
            ("E1", "TTFT（首Token延迟）", "从请求发出到收到第一个token的时间", "P0"),
            ("E2", "TPOT（每Token生成时间）", "Decode阶段平均每个token耗时", "P0"),
            ("E3", "ITL P50/P95/P99", "Token间延迟的分位数统计", "P0"),
            ("E4", "端到端延迟", "从请求到完整响应的总时间", "P0"),
            ("E5", "吞吐量（tokens/s）", "单位时间生成的token总数", "P0"),
            ("E6", "请求吞吐（req/s）", "单位时间完成的请求数", "P0"),
            ("E7", "并发扩展性", "并发1→10→50→100→200时指标变化", "P0"),
            ("E8", "显存占用", "不同并发/序列长度下的GPU显存消耗", "P0"),
            ("E9", "GPU利用率", "推理时GPU计算单元利用率", "P1"),
            ("E10", "预热时间", "首次推理vs稳态推理的延迟差异", "P1"),
            ("E11", "Prefill速度", "不同输入长度（1K/4K/16K/64K）的prefill耗时", "P1"),
            ("E12", "突发流量恢复", "瞬间100并发后恢复到正常响应时间", "P1"),
        ]
    },
    "f_stability": {
        "name": "F. 稳定性与边界",
        "tests": [
            ("G1", "空输入", "发送空prompt或空messages", "P0"),
            ("G2", "超大输入", "超过max_model_len的输入", "P0"),
            ("G3", "非法参数", "temperature=-1, max_tokens=0等", "P0"),
            ("G4", "特殊字符注入", "SQL注入、Prompt注入、XSS payload", "P0"),
            ("G5", "并发稳定性", "200+并发持续运行1小时", "P0"),
            ("G6", "OOM恢复", "显存耗尽后的服务行为", "P1"),
            ("G7", "长时间运行", "连续服务24小时", "P1"),
            ("G8", "请求超时处理", "客户端超时断开", "P1"),
        ]
    },
    "g_api": {
        "name": "G. API兼容性",
        "tests": [
            ("H1", "OpenAI Chat Completions", "/v1/chat/completions接口兼容", "P0"),
            ("H2", "OpenAI Completions", "/v1/completions接口兼容", "P1"),
            ("H3", "模型列表", "/v1/models返回可用模型", "P1"),
            ("H4", "Usage统计", "usage字段准确，验证token计数", "P0"),
        ]
    },
    "h_quality": {
        "name": "H. 质量评估",
        "tests": [
            ("I1", "生成质量", "FP16 vs INT4/INT8输出质量对比", "P0"),
            ("I2", "生成一致性", "相同输入多次生成的稳定性", "P0"),
            ("I3", "幻觉率", "生成内容中事实错误的比例", "P1"),
            ("I4", "指令遵循度", "复杂指令（格式、长度、角色）遵循程度", "P0"),
        ]
    },
    "i_long_context": {
        "name": "I. 单项超长上下文验证",
        "tests": [
            ("L1", "超长上下文（脚本验证）", "使用独立脚本执行超长上下文create/stream探测", "P1"),
        ]
    },
}


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_enabled_model(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取启用的模型"""
    for name, cfg in config.get('models', {}).items():
        if cfg.get('enabled', False):
            return {
                'name': name,
                'display_name': cfg.get('display_name', name),
                'model_name': cfg.get('name', name)
            }
    return None


def run_tests_and_collect() -> Tuple[Dict[str, str], int, int, int]:
    """运行测试并收集结果"""
    print("开始运行测试...")

    # 运行pytest并生成JSON报告
    json_report = "test_results/test_output.json"

    # 确保输出目录存在
    os.makedirs("test_results", exist_ok=True)

    # 运行pytest
    cmd = [
        sys.executable, "-m", "pytest",
        "-v", "--tb=short",
        f"--json-report",
        f"--json-report-file={json_report}",
        "-x"  # 遇到失败停止
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # 解析测试结果
    test_results = {}  # test_id -> status (passed/failed/skipped)

    if os.path.exists(json_report):
        with open(json_report, 'r', encoding='utf-8') as f:
            report_data = json.load(f)

        for test in report_data.get('tests', []):
            test_id = test.get('test_id', '')
            # 提取测试名称中的marker和测试点ID
            # 格式: tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_conversation
            status = test.get('outcome', 'unknown')

            # 简化处理：根据test_id判断
            test_results[test_id] = status

    passed = result.returncode == 0

    return test_results, result.returncode, passed, 0


def parse_pytest_output(stdout: str) -> Dict[str, str]:
    """解析pytest输出来获取测试结果"""
    results = {}

    # 解析类似 "tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_conversation PASSED"
    for line in stdout.split('\n'):
        if ' PASSED' in line or ' FAILED' in line or ' SKIPPED' in line:
            parts = line.split()
            if len(parts) >= 2:
                test_path = parts[0]
                status = parts[-1]

                # 提取测试点信息
                for marker, category in TEST_CATEGORIES.items():
                    if f"test_{marker}" in test_path:
                        for test_id, test_name, _, _ in category['tests']:
                            if test_name in line or test_id in test_path:
                                results[f"{marker}_{test_id}"] = status
                        break

    return results


def generate_report(model: Dict[str, Any], test_results: Dict[str, str]):
    """生成测试报告"""
    model_name = model['name']
    model_display = model['display_name']
    test_date = datetime.now().strftime("%Y-%m-%d")

    # 创建输出目录
    output_dir = Path("test_reports") / f"{model_name}_{test_date}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 构建报告内容
    lines = []

    # 标题
    lines.append(f"# {model_display} 测试报告")
    lines.append("")
    lines.append(f"> 测试日期：{test_date}")
    lines.append(f"> 测试时间：{datetime.now().strftime('%H:%M:%S')}")
    lines.append(f"> 模型：{model_display} (`{model['model_name']}`)")
    lines.append("")

    # 统计
    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    skipped_tests = 0

    # 遍历每个测试分类
    for marker, category in TEST_CATEGORIES.items():
        category_name = category['name']
        tests = category['tests']

        lines.append(f"## {category_name}")
        lines.append("")

        # 表头
        lines.append(f"| #   | 测试点           | 测试内容                             | 状态   |")
        lines.append(f"|-----|----------------|----------------------------------|------|")

        for test_id, test_name, test_desc, priority in tests:
            # 查找测试状态
            test_key = f"{marker}_{test_id}"
            status = test_results.get(test_key, "⏳")

            # 转换状态
            if status == "PASSED":
                status_icon = "✅"
                passed_tests += 1
            elif status == "FAILED":
                status_icon = "❌"
                failed_tests += 1
            elif status == "SKIPPED":
                status_icon = "⏳"
                skipped_tests += 1
            else:
                # 检查是否在pytest输出中
                status_icon = "⏳"
                skipped_tests += 1

            total_tests += 1

            # 截断描述
            if len(test_desc) > 30:
                test_desc = test_desc[:27] + "..."

            lines.append(f"| {test_id:2s}  | {test_name:12s} | {test_desc:30s} | {status_icon}   |")

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
    total_tested = passed_tests + failed_tests
    pass_rate = f"{passed_tests*100//max(total_tested,1)}%" if total_tested > 0 else "N/A"

    lines.append("## 统计汇总")
    lines.append("")
    lines.append(f"| 指标     | 数量   | 占比    |")
    lines.append(f"|---------|-------|--------|")
    lines.append(f"| 总测试点 | {total_tests}   | -      |")
    lines.append(f"| 已通过   | {passed_tests}   | {passed_tests*100//max(total_tests,1)}%     |")
    lines.append(f"| 未通过   | {failed_tests}   | {failed_tests*100//max(total_tests,1)}%     |")
    lines.append(f"| 未测试   | {skipped_tests}   | {skipped_tests*100//max(total_tests,1)}%     |")
    lines.append(f"| **通过率** | **{passed_tests}/{total_tested}** | **{pass_rate}** |")
    lines.append("")
    lines.append(f"> **通过率：{pass_rate}** ({passed_tests}/{total_tested} 明确测试的用例)")

    # 生成文件名
    filename = f"test_report_{model_name}_{test_date}.md"
    filepath = output_dir / filename

    # 写入文件
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))

    print(f"\n报告已生成: {filepath}")

    # 同时生成JSON结果
    json_file = output_dir / f"test_results_{model_name}_{test_date}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'model': model,
            'test_date': test_date,
            'test_results': test_results,
            'summary': {
                'total': total_tests,
                'passed': passed_tests,
                'failed': failed_tests,
                'skipped': skipped_tests
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"JSON结果已保存: {json_file}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="运行测试并生成报告")
    parser.add_argument('--config', '-c', default='config.yaml', help='配置文件路径')
    parser.add_argument('--categories', '-m', nargs='+',
                        help='指定测试分类，如 a_basic b_advanced')
    parser.add_argument('--output', '-o', default='test_reports', help='输出目录')

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 获取启用的模型
    model = get_enabled_model(config)
    if not model:
        print("错误: 没有启用的模型，请检查配置文件")
        sys.exit(1)

    print(f"测试模型: {model['display_name']}")

    # 构建pytest参数
    pytest_args = ['-v', '--tb=short']

    if args.categories:
        for cat in args.categories:
            pytest_args.extend(['-m', cat])
    else:
        # 运行所有启用的测试
        pytest_args.extend(['-m', 'p0'])  # 默认运行P0测试

    # 运行测试
    print(f"运行命令: pytest {' '.join(pytest_args)}")

    result = subprocess.run(
        [sys.executable, '-m', 'pytest'] + pytest_args,
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # 解析测试结果
    test_results = parse_pytest_output(result.stdout)

    # 生成报告
    generate_report(model, test_results)


if __name__ == "__main__":
    main()