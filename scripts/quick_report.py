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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base.test_definitions import TEST_CATEGORIES, get_test_func_mapping
from base.report_generator import TestReportGenerator


def main():
    # 加载配置
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 获取启用的模型
    model = None
    for name, cfg in config.get("models", {}).items():
        if cfg.get("enabled", False):
            model = {
                "name": name,
                "display_name": cfg.get("display_name", name),
                "model_name": cfg.get("name", name),
            }
            break

    if not model:
        print("错误: 没有启用的模型")
        sys.exit(1)

    print(f"测试模型: {model['display_name']}")
    print("运行测试...")

    # 运行测试 - 先运行P0测试
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "--tb=line", "-m", "p0"],
        capture_output=True,
        text=True,
    )

    # 解析测试结果
    test_results = {}

    test_mapping = get_test_func_mapping()

    pattern = r"(test_\w+)(?:\[([^\]]+)\])?\s+(PASSED|FAILED|SKIPPED)"

    for line in result.stdout.split("\n"):
        match = re.search(pattern, line)
        if match:
            test_name = match.group(1)
            params = match.group(2)
            status = match.group(3)

            for func_name, test_id in test_mapping.items():
                if func_name in test_name:
                    if test_id.startswith("A"):
                        marker = "a_basic"
                    elif test_id.startswith("B"):
                        marker = "b_advanced"
                    elif test_id.startswith("C"):
                        marker = "c_multimodal"
                    elif test_id.startswith("D"):
                        marker = "d_long_context"
                    elif test_id.startswith("E"):
                        marker = "e_performance"
                    elif test_id.startswith("F"):
                        marker = "f_stability"
                    elif test_id.startswith("G"):
                        marker = "g_api"
                    elif test_id.startswith("H"):
                        marker = "h_quality_chat_completions"
                    elif test_id.startswith("I"):
                        marker = "i_quality_completions"
                    else:
                        marker = "unknown"

                    test_results[f"{marker}_{test_id}"] = status
                    break

    print(f"解析到 {len(test_results)} 个测试结果")

    test_date = datetime.now().strftime("%Y-%m-%d")
    test_time = datetime.now().strftime("%H:%M:%S")

    generator = TestReportGenerator("test_reports", config=config)
    filepath = generator.generate(model, test_results, test_date, test_time)

    passed = sum(1 for v in test_results.values() if v == "PASSED")
    total = len(test_results)

    print(f"\n报告已生成: {filepath}")
    print(f"测试结果: 通过 {passed}/{total}")
    print(f"模型: {model['display_name']}")
    print(f"日期: {test_date}")


if __name__ == "__main__":
    main()
