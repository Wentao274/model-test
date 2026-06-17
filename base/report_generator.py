"""
测试报告生成器

集中管理报告生成逻辑，按照参考格式生成测试报告
"""

import os
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


def get_active_chip(config: Dict[str, Any]) -> str:
    """获取当前激活的芯片平台名称（小写）"""
    chips = config.get("chips", {})
    for chip_name, chip_cfg in chips.items():
        if isinstance(chip_cfg, dict) and chip_cfg.get("enabled", False):
            return chip_name.lower()
        elif chip_cfg is True:  # 兼容旧格式
            return chip_name.lower()
    return "default"


class TestReportGenerator:
    """测试报告生成器"""

    def __init__(self, output_dir: str = "test_reports", config: Dict[str, Any] = None):
        self.config = config or {}
        self.chip_name = get_active_chip(self.config)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        model: Dict[str, Any],
        test_results: Dict[str, str],
        test_date: Optional[str] = None,
        test_time: Optional[str] = None,
        chip_name: Optional[str] = None,
        failure_reasons: Optional[Dict[str, str]] = None,
        test_warnings: Optional[Dict[str, List[str]]] = None,
    ) -> Path:
        """生成测试报告"""
        if test_date is None:
            test_date = datetime.now().strftime("%Y-%m-%d")
        if test_time is None:
            test_time = datetime.now().strftime("%H:%M:%S")

        effective_chip = (chip_name or self.chip_name).lower()
        test_datetime = datetime.now().strftime("%Y%m%d%H%M%S")

        content = self._build_report_content(
            model,
            test_results,
            test_date,
            test_time,
            failure_reasons or {},
            test_warnings or {},
        )

        chip_dir = self.output_dir / effective_chip
        chip_dir.mkdir(parents=True, exist_ok=True)

        model_dir = chip_dir / model["name"]
        model_dir.mkdir(parents=True, exist_ok=True)

        output_subdir = model_dir / f"{model['name']}_{test_datetime}"
        output_subdir.mkdir(parents=True, exist_ok=True)

        filename = f"test_report_{model['name']}_{test_datetime}.md"
        filepath = output_subdir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def _build_report_content(
        self,
        model: Dict[str, Any],
        test_results: Dict[str, str],
        test_date: str,
        test_time: str,
        failure_reasons: Dict[str, str] = None,
        test_warnings: Dict[str, List[str]] = None,
    ) -> str:
        """构建报告内容"""
        failure_reasons = failure_reasons or {}
        test_warnings = test_warnings or {}
        model_name = model["name"]
        model_display = model["display_name"]

        lines = []

        lines.append(f"# {model_display} 测试报告")
        lines.append("")
        lines.append(f"> 测试日期：{test_date}")
        lines.append(f"> 测试时间：{test_time}")
        lines.append(f"> 模型：{model_display} (`{model['model_name']}`)")
        lines.append("")

        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        skipped_tests = 0
        partial_tests = 0

        # 按分类统计
        category_stats = {}  # {category_name: {"passed": 0, "failed": 0, "skipped": 0, "partial": 0, "total": 0}}

        for marker, category in TEST_CATEGORIES.items():
            category_name = category["name"]
            tests = category["tests"]

            # 初始化分类统计
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
            lines.append(
                "| #   | 测试点       | 测试内容                        | 状态 | 备注 |"
            )
            lines.append(
                "|-----|------------|-----------------------------|------|------|"
            )

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
                        note_short = warnings[0][:30]
                        note_detail = "; ".join(warnings)
                        issue_notes.append((test_idx, test_name, f"⚠️ {note_detail}"))
                    else:
                        note_short = ""
                        note_detail = ""
                elif status == "FAILED":
                    status_icon = "❌"
                    failed_tests += 1
                    category_stats[category_name]["failed"] += 1
                    reason = failure_reasons.get(key, "测试未通过")
                    note_short, note_detail = _split_reason(reason)
                    issue_notes.append((test_idx, test_name, note_detail))
                elif status == "PARTIAL":
                    status_icon = "⚠️"
                    partial_tests += 1
                    category_stats[category_name]["partial"] += 1
                    reason = failure_reasons.get(key, "部分用例未通过")
                    note_short, note_detail = _split_reason(reason)
                    issue_notes.append((test_idx, test_name, note_detail))
                elif status == "SKIPPED":
                    status_icon = "⏳"
                    skipped_tests += 1
                    category_stats[category_name]["skipped"] += 1
                    reason = failure_reasons.get(key, "未运行此测试")
                    note_short, note_detail = _split_reason(reason)
                    issue_notes.append((test_idx, test_name, note_detail))
                else:
                    status_icon = "⏳"
                    skipped_tests += 1
                    category_stats[category_name]["skipped"] += 1
                    reason = failure_reasons.get(key, "未运行此测试")
                    note_short, note_detail = _split_reason(reason)
                    issue_notes.append((test_idx, test_name, note_detail))

                total_tests += 1
                category_stats[category_name]["total"] += 1

                if len(test_desc) > 26:
                    test_desc = test_desc[:23] + "..."

                lines.append(
                    f"| {test_idx:2s}  | {test_name:10s} | {test_desc:26s} | {status_icon} | {note_short} |"
                )

            if issue_notes:
                lines.append("")
                for test_idx, test_name, reason in issue_notes:
                    lines.append(f"- **{test_idx} {test_name}**: {reason}")

            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## 统计汇总")
        lines.append("")

        tested_count = passed_tests + failed_tests
        pass_rate = (
            f"{passed_tests * 100 // tested_count}%" if tested_count > 0 else "N/A"
        )
        total_run = passed_tests + failed_tests + partial_tests + skipped_tests

        lines.append("| 指标         | 数量   | 占比      |")
        lines.append("|--------------|-------|----------|")
        lines.append(f"| 总测试点     | {total_tests:4d} | -        |")
        lines.append(
            f"| 已通过       | {passed_tests:4d} | {passed_tests * 100 // max(total_tests, 1):6d}%   |"
        )
        lines.append(
            f"| 未通过       | {failed_tests:4d} | {failed_tests * 100 // max(total_tests, 1):6d}%   |"
        )
        lines.append(
            f"| 部分通过     | {partial_tests:4d} | {partial_tests * 100 // max(total_tests, 1):6d}%   |"
        )
        lines.append(
            f"| 未测试       | {skipped_tests:4d} | {skipped_tests * 100 // max(total_tests, 1):6d}%   |"
        )
        lines.append(
            f"| **通过率**   | **{passed_tests}/{tested_count}** | **{pass_rate}**   |"
        )
        lines.append("")

        lines.append(
            f"> **通过率：{pass_rate}** ({passed_tests}/{tested_count} 明确测试的用例)"
        )
        lines.append("")

        # 各测试分类统计
        lines.append("## 分类统计")
        lines.append("")
        lines.append(
            "| 测试分类           | 总数 | 通过 | 未通过 | 部分通过 | 未测试 | 通过率 |"
        )
        lines.append(
            "|-------------------|-----|-----|-------|---------|-------|-------|"
        )

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
                f"| {category_name:17s} | {total:3d} | {passed:3d} | {failed:4d} | {partial:5d} | {skipped:5d} | {cat_pass_rate:5s} |"
            )

        lines.append("")

        lines.append(
            self._build_conclusion(
                category_stats, test_results, failure_reasons, test_warnings
            )
        )

        lines.append("")

        return "\n".join(lines)

    def _build_conclusion(
        self,
        category_stats: Dict,
        test_results: Dict[str, str],
        failure_reasons: Dict[str, str],
        test_warnings: Dict[str, List[str]],
    ) -> str:
        """构建测试结论

        结论判定按测试用例的优先级（P0/P1/P2）划分，分类关键性不再作为判定依据。
        优先级映射：
            P0 = 关键（Critical）
            P1 = 重要（Important）
            P2 = 一般（General）
        SKIPPED（未测试）用例不参与结论判定。
        """
        lines = []
        lines.append("## 测试结论")
        lines.append("")

        critical_issues = []
        important_issues = []
        general_issues = []
        warning_issues = []

        for marker, category in TEST_CATEGORIES.items():
            category_name = category["name"]

            for test_info in category["tests"]:
                test_idx = test_info[0]
                test_name = test_info[1]
                priority = test_info[4] if len(test_info) >= 5 else "P1"
                key = f"{marker}_{test_idx}"
                status = test_results.get(key, "未运行")

                if status == "SKIPPED" or status == "未运行":
                    continue

                if status == "FAILED":
                    reason = failure_reasons.get(key, "测试未通过")
                    _, detail = _split_reason(reason)
                    entry_item = (test_idx, test_name, priority, detail)
                    if priority == "P0":
                        critical_issues.append(entry_item)
                    elif priority == "P1":
                        important_issues.append(entry_item)
                    else:
                        general_issues.append(entry_item)
                elif status == "PARTIAL":
                    reason = failure_reasons.get(key, "部分用例未通过")
                    _, detail = _split_reason(reason)
                    entry_item = (test_idx, test_name, priority, detail)
                    if priority == "P0":
                        critical_issues.append(entry_item)
                    elif priority == "P1":
                        important_issues.append(entry_item)
                    else:
                        general_issues.append(entry_item)
                elif status == "PASSED":
                    warnings = test_warnings.get(key, [])
                    if warnings:
                        warning_issues.append(
                            (
                                test_idx,
                                test_name,
                                category_name,
                                priority,
                                "; ".join(warnings),
                            )
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
                lines.append("所有已运行的测试用例均已通过，但存在警告项需要关注：")
            else:
                conclusion = "✅ 通过"
                lines.append(f"> **结论：{conclusion}**")
                lines.append("")
                lines.append("所有已运行的测试用例均已通过，测试结果可接受。")
        elif has_critical_failure:
            conclusion = "❌ 不通过"
            lines.append(f"> **结论：{conclusion}**")
            lines.append("")
            lines.append(
                "存在 P0（关键）优先级用例未通过，测试结果不可接受，必须修复后重新测试。"
            )
        else:
            conclusion = "⚠️ 有条件通过"
            lines.append(f"> **结论：{conclusion}**")
            lines.append("")
            if has_important_failure:
                lines.append("存在 P1（重要）优先级用例未通过，建议修复后重新测试。")
            else:
                lines.append(
                    "仅存在 P2（一般）优先级用例未通过，可酌情接受，建议后续修复。"
                )

        lines.append("")

        if critical_issues:
            lines.append("### 关键(P0)优先级问题")
            lines.append("")
            for test_idx, test_name, priority, detail in critical_issues:
                lines.append(f"- ❌ {test_idx} {test_name}（{priority}）：{detail}")
            lines.append("")

        if important_issues:
            lines.append("### 重要(P1)优先级问题")
            lines.append("")
            for test_idx, test_name, priority, detail in important_issues:
                lines.append(f"- ❌ {test_idx} {test_name}（{priority}）：{detail}")
            lines.append("")

        if general_issues:
            lines.append("### 一般(P2)优先级问题")
            lines.append("")
            for test_idx, test_name, priority, detail in general_issues:
                lines.append(f"- ❌ {test_idx} {test_name}（{priority}）：{detail}")
            lines.append("")

        if warning_issues:
            lines.append("### 警告项")
            lines.append("")
            for test_idx, test_name, category_name, priority, detail in warning_issues:
                lines.append(
                    f"- ⚠️ {test_idx} {test_name}（{category_name}, {priority}）：{detail}"
                )
            lines.append("")

        return "\n".join(lines)


def generate_test_report(
    model: Dict[str, Any],
    test_results: Dict[str, str],
    output_dir: str = "test_reports",
) -> Path:
    """便捷函数：生成测试报告"""
    generator = TestReportGenerator(output_dir)
    return generator.generate(model, test_results)
