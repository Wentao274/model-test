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


def _split_reason(reason: str):
    """将 '短摘要|详细描述' 格式拆分为两个部分"""
    if "|" in reason:
        parts = reason.split("|", 1)
        return parts[0], parts[1]
    return reason, reason


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
    """获取当前激活的芯片平台名称（小写）"""
    chips = config.get("chips", {})
    for chip_name, chip_cfg in chips.items():
        if isinstance(chip_cfg, dict) and chip_cfg.get("enabled", False):
            return chip_name.lower()
        elif chip_cfg is True:
            return chip_name.lower()
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


def _build_conclusion(
    category_stats: Dict,
    test_results: Dict[str, str],
    failure_reasons: Dict[str, str],
    test_warnings: Dict[str, List[str]],
) -> List[str]:
    """构建测试结论"""
    lines = []
    lines.append("## 测试结论")
    lines.append("")

    critical_issues = []
    important_issues = []
    general_issues = []
    warning_issues = []

    for marker, category in TEST_CATEGORIES.items():
        category_name = category["name"]
        criticality = category.get("criticality", "一般")
        stats = category_stats.get(category_name, {})

        category_failed = []
        category_partial = []
        category_warned = []

        for test_info in category["tests"]:
            test_idx = test_info[0]
            test_name = test_info[1]
            key = f"{marker}_{test_idx}"
            status = test_results.get(key, "未运行")

            if status == "FAILED":
                reason = failure_reasons.get(key, "测试未通过")
                _, detail = _split_reason(reason)
                category_failed.append((test_idx, test_name, detail))
            elif status == "PARTIAL":
                reason = failure_reasons.get(key, "部分用例未通过")
                _, detail = _split_reason(reason)
                category_partial.append((test_idx, test_name, detail))
            elif status == "PASSED":
                warnings = test_warnings.get(key, [])
                if warnings:
                    category_warned.append((test_idx, test_name, "; ".join(warnings)))

        if category_failed or category_partial:
            issue_type = (
                "未通过"
                if category_failed and not category_partial
                else (
                    "部分通过"
                    if category_partial and not category_failed
                    else "未通过/部分通过"
                )
            )
            entry = {
                "category": category_name,
                "criticality": criticality,
                "type": issue_type,
                "failed": category_failed,
                "partial": category_partial,
            }
            if criticality == "关键":
                critical_issues.append(entry)
            elif criticality == "重要":
                important_issues.append(entry)
            else:
                general_issues.append(entry)

        if category_warned:
            warning_issues.append(
                {
                    "category": category_name,
                    "criticality": criticality,
                    "warnings": category_warned,
                }
            )

    has_critical_failure = len(critical_issues) > 0
    has_important_failure = len(important_issues) > 0
    has_general_failure = len(general_issues) > 0
    has_warnings = len(warning_issues) > 0

    if (
        not has_critical_failure
        and not has_important_failure
        and not has_general_failure
    ):
        if has_warnings:
            conclusion = "⚠️ 有条件通过"
            lines.append(f"> **结论：{conclusion}**")
            lines.append("")
            lines.append("所有测试用例均已通过，但存在警告项需要关注：")
        else:
            conclusion = "✅ 通过"
            lines.append(f"> **结论：{conclusion}**")
            lines.append("")
            lines.append("所有测试用例均已通过，测试结果可接受。")
    elif has_critical_failure:
        conclusion = "❌ 不通过"
        lines.append(f"> **结论：{conclusion}**")
        lines.append("")
        lines.append("关键分类存在未通过用例，测试结果不可接受，必须修复后重新测试。")
    else:
        conclusion = "⚠️ 有条件通过"
        lines.append(f"> **结论：{conclusion}**")
        lines.append("")
        if has_important_failure:
            lines.append("重要分类存在未通过用例，建议修复后重新测试。")
        else:
            lines.append("一般分类存在未通过用例，可酌情接受，建议后续修复。")

    lines.append("")

    if critical_issues:
        lines.append("### 关键分类问题")
        lines.append("")
        for entry in critical_issues:
            lines.append(f"**{entry['category']}**（{entry['type']}）：")
            for test_idx, test_name, detail in entry["failed"]:
                lines.append(f"- ❌ {test_idx} {test_name}：{detail}")
            for test_idx, test_name, detail in entry["partial"]:
                lines.append(f"- ⚠️ {test_idx} {test_name}：{detail}")
            lines.append("")

    if important_issues:
        lines.append("### 重要分类问题")
        lines.append("")
        for entry in important_issues:
            lines.append(f"**{entry['category']}**（{entry['type']}）：")
            for test_idx, test_name, detail in entry["failed"]:
                lines.append(f"- ❌ {test_idx} {test_name}：{detail}")
            for test_idx, test_name, detail in entry["partial"]:
                lines.append(f"- ⚠️ {test_idx} {test_name}：{detail}")
            lines.append("")

    if general_issues:
        lines.append("### 一般分类问题")
        lines.append("")
        for entry in general_issues:
            lines.append(f"**{entry['category']}**（{entry['type']}）：")
            for test_idx, test_name, detail in entry["failed"]:
                lines.append(f"- ❌ {test_idx} {test_name}：{detail}")
            for test_idx, test_name, detail in entry["partial"]:
                lines.append(f"- ⚠️ {test_idx} {test_name}：{detail}")
            lines.append("")

    if warning_issues:
        lines.append("### 警告项")
        lines.append("")
        for entry in warning_issues:
            lines.append(f"**{entry['category']}**：")
            for test_idx, test_name, detail in entry["warnings"]:
                lines.append(f"- ⚠️ {test_idx} {test_name}：{detail}")
            lines.append("")

    return lines


def generate_allure_summary_report(
    test_results: Dict[str, str],
    output_dir: str = "allure-report",
    model_name: Optional[str] = None,
    chip_name: Optional[str] = None,
    infra: Optional[str] = None,
    pd_mode: Optional[str] = None,
    tester: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    failure_reasons: Optional[Dict[str, str]] = None,
    test_warnings: Optional[Dict[str, List[str]]] = None,
) -> str:
    """
    生成 Allure 汇总报告 (Markdown 格式)

    Args:
        test_results: 测试结果字典 {test_key: status}
        output_dir: 输出目录
        model_name: 模型名称
        chip_name: 芯片平台名称
        infra: 推理框架
        pd_mode: PD分离模式
        tester: 测试人员
        config: 配置

    Returns:
        报告文件路径
    """
    config = config or {}
    failure_reasons = failure_reasons or {}
    test_warnings = test_warnings or {}
    chip_name = chip_name or get_active_chip(config)
    model_name = model_name or "unknown"

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
    lines.append(f"> 模型：{model_name}")
    lines.append(f"> 推理框架：{infra or 'N/A'}")
    lines.append(f"> PD模式：{pd_mode or 'N/A'}")
    lines.append(f"> 测试人员：{tester or 'N/A'}")
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
        lines.append("| # | 测试点 | 测试内容 | 状态 | 备注 |")
        lines.append("|---|--------|----------|------|------|")

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
                warnings = test_warnings.get(key, [])
                if warnings:
                    status_icon = "⚠️✅"
                    remark = warnings[0][:30]
                    detail = "; ".join(warnings)
                    issue_notes.append((test_idx, test_name, f"⚠️ {detail}"))
                else:
                    remark = ""
            elif status == "FAILED":
                status_icon = "❌"
                failed_tests += 1
                category_stats[category_name]["failed"] += 1
                reason = failure_reasons.get(key, "测试未通过")
                remark, detail = _split_reason(reason)
                issue_notes.append((test_idx, test_name, detail))
            elif status == "PARTIAL":
                status_icon = "⚠️"
                partial_tests += 1
                category_stats[category_name]["partial"] += 1
                reason = failure_reasons.get(key, "部分用例未通过")
                remark, detail = _split_reason(reason)
                issue_notes.append((test_idx, test_name, detail))
            else:
                status_icon = "⏳"
                skipped_tests += 1
                category_stats[category_name]["skipped"] += 1
                reason = failure_reasons.get(key, "未运行此测试")
                remark, detail = _split_reason(reason)
                issue_notes.append((test_idx, test_name, detail))

            total_tests += 1
            category_stats[category_name]["total"] += 1

            if len(test_desc) > 26:
                test_desc = test_desc[:23] + "..."

            lines.append(
                f"| {test_idx:2s} | {test_name:10s} | {test_desc:26s} | {status_icon} | {remark} |"
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

    conclusion_lines = _build_conclusion(
        category_stats, test_results, failure_reasons, test_warnings
    )
    lines.extend(conclusion_lines)

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*报告由 Allure 测试框架自动生成*")

    # 写入文件 - 按照 test_reports 的目录结构
    test_datetime = datetime.now().strftime("%Y%m%d%H%M%S")
    output_base = Path(output_dir)
    chip_dir = output_base / chip_name
    model_dir = chip_dir / model_name
    report_subdir = model_dir / f"{model_name}_{test_datetime}"
    report_subdir.mkdir(parents=True, exist_ok=True)

    output_file = report_subdir / f"test_report_{model_name}_{test_datetime}.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return str(output_file)


def clean_allure_results(allure_results_dir: str = "allure-results"):
    """清理 Allure 结果目录"""
    results_path = Path(allure_results_dir)
    if results_path.exists():
        shutil.rmtree(results_path)
    results_path.mkdir(parents=True, exist_ok=True)
