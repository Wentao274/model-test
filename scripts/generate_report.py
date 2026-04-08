"""
测试报告生成器

根据pytest测试结果生成类似checkpoints.md格式的测试报告
"""

import os
import sys
import json
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base.test_definitions import TEST_CATEGORIES
from base.report_generator import TestReportGenerator


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """加载配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_enabled_models(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """获取所有启用的模型"""
    models = []
    for name, cfg in config.get("models", {}).items():
        if cfg.get("enabled", False):
            models.append(
                {
                    "name": name,
                    "display_name": cfg.get("display_name", name),
                    "model_name": cfg.get("name", name),
                }
            )
    return models


def load_pytest_json(json_path: str) -> Dict[str, Any]:
    """加载pytest的JSON报告"""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="生成测试报告")
    parser.add_argument("--config", "-c", default="config.yaml", help="配置文件路径")
    parser.add_argument("--output", "-o", default="test_reports", help="输出目录")
    parser.add_argument("--json", "-j", help="pytest JSON报告路径")
    parser.add_argument("--model", "-m", help="指定模型名称")

    args = parser.parse_args()

    config = load_config(args.config)

    if args.json and os.path.exists(args.json):
        test_results = load_pytest_json(args.json)
    else:
        test_results = {}

    enabled_models = get_enabled_models(config)

    if args.model:
        test_model = next((m for m in enabled_models if m["name"] == args.model), None)
        if not test_model:
            print(f"警告: 模型 {args.model} 未启用或不存在")
            return
        models_to_test = [test_model]
    else:
        models_to_test = enabled_models

    test_date = datetime.now().strftime("%Y-%m-%d")
    test_time = datetime.now().strftime("%H:%M:%S")

    generator = TestReportGenerator(args.output)

    for model in models_to_test:
        filepath = generator.generate(model, test_results, test_date, test_time)
        print(f"报告已生成: {filepath}")


if __name__ == "__main__":
    main()
