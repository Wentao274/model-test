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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base.test_definitions import TEST_CATEGORIES
from base.report_generator import TestReportGenerator


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """加载配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_enabled_model(config: Dict[str, Any]) -> Dict[str, Any]:
    """获取启用的模型"""
    for name, cfg in config.get("models", {}).items():
        if cfg.get("enabled", False):
            return {
                "name": name,
                "display_name": cfg.get("display_name", name),
                "model_name": cfg.get("name", name),
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
        sys.executable,
        "-m",
        "pytest",
        "-v",
        "--tb=short",
        f"--json-report",
        f"--json-report-file={json_report}",
        "-x",  # 遇到失败停止
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    # 解析测试结果
    test_results = {}  # test_id -> status (passed/failed/skipped)

    if os.path.exists(json_report):
        with open(json_report, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        for test in report_data.get("tests", []):
            test_id = test.get("test_id", "")
            # 提取测试名称中的marker和测试点ID
            # 格式: tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_conversation
            status = test.get("outcome", "unknown")

            # 简化处理：根据test_id判断
            test_results[test_id] = status

    passed = result.returncode == 0

    return test_results, result.returncode, passed, 0


def parse_pytest_output(stdout: str) -> Dict[str, str]:
    """解析pytest输出来获取测试结果"""
    results = {}

    # 解析类似 "tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_conversation PASSED"
    for line in stdout.split("\n"):
        if " PASSED" in line or " FAILED" in line or " SKIPPED" in line:
            parts = line.split()
            if len(parts) >= 2:
                test_path = parts[0]
                status = parts[-1]

                # 提取测试点信息
                for marker, category in TEST_CATEGORIES.items():
                    if f"test_{marker}" in test_path:
                        for test_id, test_name, _, _ in category["tests"]:
                            if test_name in line or test_id in test_path:
                                results[f"{marker}_{test_id}"] = status
                        break

    return results


def generate_report(model: Dict[str, Any], test_results: Dict[str, str]):
    """生成测试报告"""
    test_date = datetime.now().strftime("%Y-%m-%d")
    test_time = datetime.now().strftime("%H:%M:%S")

    generator = TestReportGenerator("test_reports")
    filepath = generator.generate(model, test_results, test_date, test_time)

    print(f"\n报告已生成: {filepath}")

    json_file = (
        filepath.parent
        / f"test_results_{model['name']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    )
    total = sum(1 for _ in TEST_CATEGORIES.values() for _ in _["tests"])
    passed = sum(1 for v in test_results.values() if v == "PASSED")
    failed = sum(1 for v in test_results.values() if v == "FAILED")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": model,
                "test_date": test_date,
                "test_results": test_results,
                "summary": {"total": total, "passed": passed, "failed": failed},
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"JSON结果已保存: {json_file}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="运行测试并生成报告")
    parser.add_argument("--config", "-c", default="config.yaml", help="配置文件路径")
    parser.add_argument(
        "--categories", "-m", nargs="+", help="指定测试分类，如 a_basic b_advanced"
    )
    parser.add_argument("--output", "-o", default="test_reports", help="输出目录")

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
    pytest_args = ["-v", "--tb=short"]

    if args.categories:
        for cat in args.categories:
            pytest_args.extend(["-m", cat])
    else:
        # 运行所有启用的测试
        pytest_args.extend(["-m", "p0"])  # 默认运行P0测试

    # 运行测试
    print(f"运行命令: pytest {' '.join(pytest_args)}")

    result = subprocess.run(
        [sys.executable, "-m", "pytest"] + pytest_args, capture_output=True, text=True
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
