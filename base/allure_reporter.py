"""
Allure 报告生成器

为 pytest 测试框架提供 Allure 报告生成功能
"""

import os
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from base.test_definitions import TEST_CATEGORIES


class AllureReporter:
    """Allure 报告生成器"""

    def __init__(
        self,
        allure_results_dir: str = "allure-results",
        config: Optional[Dict[str, Any]] = None,
    ):
        self.allure_results_dir = Path(allure_results_dir)
        self.allure_results_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or {}
        self.test_results = {}

    def get_allure_command(self) -> str:
        """获取 allure 命令路径"""
        return "allure"

    def generate_report(self, output_dir: str = "allure-report") -> bool:
        """
        生成 Allure HTML 报告

        Args:
            output_dir: 报告输出目录

        Returns:
            是否生成成功
        """
        try:
            result = subprocess.run(
                [
                    self.get_allure_command(),
                    "generate",
                    str(self.allure_results_dir),
                    "-o",
                    output_dir,
                    "--clean",
                ],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            print("警告: allure 命令未找到，请先安装 Allure 命令行工具")
            print("安装方法: https://docs.qameta.io/allure/#_installing_a_commandline")
            return False

    def open_report(self, report_dir: str = "allure-report") -> bool:
        """
        打开 Allure 报告

        Args:
            report_dir: 报告目录

        Returns:
            是否打开成功
        """
        try:
            subprocess.run([self.get_allure_command(), "open", report_dir])
            return True
        except FileNotFoundError:
            return False


def get_active_chip(config: Dict[str, Any]) -> str:
    """获取当前激活的芯片平台名称"""
    chips = config.get("chips", {})
    for chip_name, chip_cfg in chips.items():
        if isinstance(chip_cfg, dict) and chip_cfg.get("enabled", False):
            return chip_name
        elif chip_cfg is True:
            return chip_name
    return "default"


def get_test_category_info(test_nodeid: str) -> Optional[tuple]:
    """
    从测试节点 ID 获取测试分类信息

    Args:
        test_nodeid: pytest 测试节点 ID (如 "tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_chat")

    Returns:
        (category_marker, test_idx, test_name, test_desc, category_name) 或 None
    """
    for marker, category in TEST_CATEGORIES.items():
        if f"test_{marker}" in test_nodeid:
            test_func_name = test_nodeid.split("::")[-1].split("[")[0]
            for test_info in category["tests"]:
                if len(test_info) >= 4:
                    test_idx, test_name, test_desc, func_name = test_info
                else:
                    test_idx, test_name, test_desc = test_info
                    func_name = test_name.replace("-", "_").replace(" ", "_")

                if f"test_{func_name}" == test_func_name:
                    return (marker, test_idx, test_name, test_desc, category["name"])
    return None


def generate_allure_summary_report(
    test_results: Dict[str, str],
    output_path: str = "allure-report/summary.md",
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    生成 Allure 汇总报告 (Markdown 格式)

    Args:
        test_results: 测试结果字典 {test_key: status}
        output_path: 输出路径
        config: 配置

    Returns:
        报告文件路径
    """
    config = config or {}
    chip_name = get_active_chip(config)

    total_tests = 0
    passed_tests = 0
    failed_tests = 0
    skipped_tests = 0
    partial_tests = 0

    category_stats = {}

    lines = []
    lines.append("# 测试汇总报告 (Allure)")
    lines.append("")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> 芯片平台：{chip_name}")
    lines.append("")

    # 按分类统计
    for marker, category in TEST_CATEGORIES.items():
        category_name = category["name"]
        tests = category["tests"]

        category_stats[category_name] = {
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "partial": 0,
            "total": 0,
        }

        lines.append(f"## {category_name}")
        lines.append("")
        lines.append("> 状态说明：✅ 已通过，⏳ 未测试，❌ 未通过，⚠️ 部分通过")
        lines.append("")
        lines.append("| # | 测试点 | 测试内容 | 状态 |")
        lines.append("|---|--------|----------|------|")

        issue_notes = []

        for test_info in tests:
            test_idx = test_info[0]
            test_name = test_info[1]
            test_desc = test_info[2]

            key = f"{marker}_{test_idx}"
            status = test_results.get(key, "未运行")

            if status == "PASSED":
                status_icon = "✅"
                passed_tests += 1
                category_stats[category_name]["passed"] += 1
            elif status == "FAILED":
                status_icon = "❌"
                failed_tests += 1
                category_stats[category_name]["failed"] += 1
                issue_notes.append((test_idx, test_name, "测试未通过"))
            elif status == "PARTIAL":
                status_icon = "⚠️"
                partial_tests += 1
                category_stats[category_name]["partial"] += 1
                issue_notes.append((test_idx, test_name, "部分用例未通过"))
            else:
                status_icon = "⏳"
                skipped_tests += 1
                category_stats[category_name]["skipped"] += 1
                issue_notes.append((test_idx, test_name, "未运行此测试"))

            total_tests += 1
            category_stats[category_name]["total"] += 1

            if len(test_desc) > 26:
                test_desc = test_desc[:23] + "..."

            lines.append(
                f"| {test_idx:2s} | {test_name:10s} | {test_desc:26s} | {status_icon} |"
            )

        if issue_notes:
            lines.append("")
            for test_idx, test_name, reason in issue_notes:
                lines.append(f"- **{test_idx} {test_name}**: {reason}")

        lines.append("")

    # 统计汇总
    lines.append("---")
    lines.append("")
    lines.append("## 统计汇总")
    lines.append("")

    tested_count = passed_tests + failed_tests
    pass_rate = f"{passed_tests * 100 // tested_count}%" if tested_count > 0 else "N/A"

    lines.append("| 指标 | 数量 | 占比 |")
    lines.append("|------|------|------|")
    lines.append(f"| 总测试点 | {total_tests:4d} | - |")
    lines.append(
        f"| 已通过 | {passed_tests:4d} | {passed_tests * 100 // max(total_tests, 1):6d}% |"
    )
    lines.append(
        f"| 未通过 | {failed_tests:4d} | {failed_tests * 100 // max(total_tests, 1):6d}% |"
    )
    lines.append(
        f"| 部分通过 | {partial_tests:4d} | {partial_tests * 100 // max(total_tests, 1):6d}% |"
    )
    lines.append(
        f"| 未测试 | {skipped_tests:4d} | {skipped_tests * 100 // max(total_tests, 1):6d}% |"
    )
    lines.append(
        f"| **通过率** | **{passed_tests}/{tested_count}** | **{pass_rate}** |"
    )
    lines.append("")

    # 分类统计
    lines.append("## 分类统计")
    lines.append("")
    lines.append("| 测试分类 | 总数 | 通过 | 未通过 | 部分通过 | 未测试 | 通过率 |")
    lines.append("|----------|------|------|--------|----------|--------|--------|")

    for category_name, stats in category_stats.items():
        total = stats["total"]
        passed = stats["passed"]
        failed = stats["failed"]
        partial = stats.get("partial", 0)
        skipped = stats["skipped"]
        cat_pass_rate = (
            f"{passed * 100 // max(passed + failed, 1)}%"
            if (passed + failed) > 0
            else "N/A"
        )
        lines.append(
            f"| {category_name:14s} | {total:3d} | {passed:3d} | {failed:4d} | {partial:5d} | {skipped:5d} | {cat_pass_rate:5s} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*报告由 Allure 测试框架自动生成*")

    # 写入文件
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return str(output_file)


def clean_allure_results(allure_results_dir: str = "allure-results"):
    """清理 Allure 结果目录"""
    results_path = Path(allure_results_dir)
    if results_path.exists():
        shutil.rmtree(results_path)
    results_path.mkdir(parents=True, exist_ok=True)
