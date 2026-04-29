"""
日志模块 - 为每个测试类创建独立的日志文件
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


def get_active_chip(config: Dict[str, Any]) -> str:
    """获取当前激活的芯片平台名称"""
    chips = config.get("chips", {})
    for chip_name, is_active in chips.items():
        if is_active:
            return chip_name
    return "default"


class TestLogger:
    """测试日志管理器"""

    _loggers = {}

    @classmethod
    def get_logger(
        cls,
        test_class_name: str,
        log_dir: str = "logs",
        model_name: Optional[str] = None,
        chip_name: Optional[str] = None,
    ) -> logging.Logger:
        """获取或创建测试类专用的日志器

        Args:
            test_class_name: 测试类名称
            log_dir: 日志根目录
            model_name: 模型名称，用于创建模型子目录
            chip_name: 芯片平台名称
        """
        # 构建目录路径: logs/chip_name/model_name/test_class_name
        if chip_name:
            log_path = Path(log_dir) / chip_name
            if model_name:
                log_path = log_path / model_name / test_class_name
            else:
                log_path = log_path / test_class_name
        elif model_name:
            log_path = Path(log_dir) / model_name / test_class_name
        else:
            log_path = Path(log_dir) / test_class_name
        log_path.mkdir(parents=True, exist_ok=True)

        # 生成日志文件名
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        log_file = log_path / f"{test_class_name}_{timestamp}.log"

        # 创建 logger
        logger = logging.getLogger(test_class_name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False  # 不传播到父 logger

        # 清除已有的 handlers
        logger.handlers.clear()

        # 文件 handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

        # 控制台 handler（可选，用于调试）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(file_format)
        logger.addHandler(console_handler)

        cls._loggers[test_class_name] = logger

        # 记录日志文件路径
        logger.info(f"日志文件: {log_file}")

        return logger

    @classmethod
    def log_response(
        cls, logger: logging.Logger, response: dict, title: str = "API Response"
    ):
        """格式化记录 API 响应"""
        import json

        logger.info(f"=== {title} ===")

        # 记录基本信息
        if "choices" in response and response["choices"]:
            message = response["choices"][0].get("message", {})
            content = message.get("content", "")
            reasoning = message.get("reasoning")

            if content:
                logger.info(f"Content: {content[:500]}...")  # 限制长度
            if reasoning:
                logger.info(f"Reasoning: {reasoning[:500]}...")

        # 记录完整响应（可选）
        logger.debug(
            f"Full Response: {json.dumps(response, ensure_ascii=False, indent=2)}"
        )

    @classmethod
    def log_request(cls, logger: logging.Logger, messages: list, params: dict = None):
        """记录 API 请求"""
        import json

        logger.info("=== API Request ===")
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                # 多模态消息
                content_preview = f"[多模态消息，包含 {len(content)} 个部分]"
            else:
                content_preview = content[:200] if content else ""
            logger.info(f"Message {i} [{role}]: {content_preview}")

        if params:
            logger.info(f"Params: {json.dumps(params, ensure_ascii=False)}")
