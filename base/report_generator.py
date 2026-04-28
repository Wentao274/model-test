"""
测试报告生成器

集中管理报告生成逻辑，按照参考格式生成测试报告
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from base.test_definitions import TEST_CATEGORIES


class TestReportGenerator:
    """测试报告生成器"""

    def __init__(self, output_dir: str = "test_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        model: Dict[str, Any],
        test_results: Dict[str, str],
        test_date: Optional[str] = None,
        test_time: Optional[str] = None,
    ) -> Path:
        """生成测试报告"""
        if test_date is None:
            test_date = datetime.now().strftime("%Y-%m-%d")
        if test_time is None:
            test_time = datetime.now().strftime("%H:%M:%S")

        test_datetime = datetime.now().strftime("%Y%m%d%H%M%S")

        content = self._build_report_content(model, test_results, test_date, test_time)

        output_subdir = self.output_dir / f"{model['name']}_{test_datetime}"
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
    ) -> str:
        """构建报告内容"""
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
                "| #   | 测试点       | 测试内容                        | 状态 |"
            )
            lines.append("|-----|------------|-----------------------------|------|")

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
                elif status == "SKIPPED":
                    status_icon = "⏳"
                    skipped_tests += 1
                    category_stats[category_name]["skipped"] += 1
                    issue_notes.append((test_idx, test_name, "未运行此测试"))
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
                    f"| {test_idx:2s}  | {test_name:10s} | {test_desc:26s} | {status_icon} |"
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

        return "\n".join(lines)


def generate_test_report(
    model: Dict[str, Any],
    test_results: Dict[str, str],
    output_dir: str = "test_reports",
) -> Path:
    """便捷函数：生成测试报告"""
    generator = TestReportGenerator(output_dir)
    return generator.generate(model, test_results)
