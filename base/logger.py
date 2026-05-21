"""
日志模块 - 为每个测试类创建独立的日志文件，并自动附加到 Allure 报告
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import allure
    from allure_commons.types import AttachmentType

    ALLURE_AVAILABLE = True
except ImportError:
    ALLURE_AVAILABLE = False


def get_active_chip(config: Dict[str, Any]) -> str:
    """获取当前激活的芯片平台名称（小写）"""
    chips = config.get("chips", {})
    for chip_name, chip_cfg in chips.items():
        if isinstance(chip_cfg, dict) and chip_cfg.get("enabled", False):
            return chip_name.lower()
        elif chip_cfg is True:
            return chip_name.lower()
    return "default"


class AllureLogHandler(logging.Handler):
    """自定义日志处理器，收集日志并在测试结束时一次性附加到 Allure"""

    def __init__(self):
        super().__init__()
        self._log_buffer = []

    def emit(self, record: logging.LogRecord):
        """收集日志记录到缓冲区"""
        try:
            # 过滤第三方库的 DEBUG 日志
            if record.levelno == logging.DEBUG:
                # 只保留本项目模块的 DEBUG 日志
                if not record.name.startswith(("tests.", "base.", "__main__")):
                    return

            msg = self.format(record)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self._log_buffer.append(f"[{timestamp}] [{record.levelname}] {msg}")
        except Exception:
            pass

    def get_full_log(self) -> str:
        """获取完整日志内容"""
        return "\n".join(self._log_buffer)

    def clear(self):
        """清空日志缓冲"""
        self._log_buffer.clear()

    def flush_to_allure(self, test_name: str = "测试日志"):
        """将日志一次性附加到 Allure"""
        if not ALLURE_AVAILABLE:
            return

        if self._log_buffer:
            try:
                full_log = self.get_full_log()
                allure.attach(
                    full_log,
                    name=test_name,
                    attachment_type=AttachmentType.TEXT,
                )
            except Exception:
                pass


class TestLogger:
    """测试日志管理器"""

    _loggers = {}
    _allure_handlers = {}  # 存储 allure handler

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
        # 如果已存在该测试类的 logger，直接返回（每个测试类一个日志文件）
        if test_class_name in cls._loggers:
            return cls._loggers[test_class_name]

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

        # 控制台 handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(file_format)
        logger.addHandler(console_handler)

        # Allure 日志 handler
        if ALLURE_AVAILABLE:
            allure_handler = AllureLogHandler()
            allure_handler.setLevel(logging.DEBUG)
            allure_handler.setFormatter(file_format)
            logger.addHandler(allure_handler)
            cls._allure_handlers[test_class_name] = allure_handler

        cls._loggers[test_class_name] = logger

        # 记录日志文件路径
        logger.info(f"日志文件: {log_file}")

        return logger

    @classmethod
    def flush_to_allure(cls, test_class_name: str, test_name: str = "测试日志"):
        """将指定测试类的日志刷新到 Allure"""
        if test_class_name in cls._allure_handlers:
            handler = cls._allure_handlers[test_class_name]
            handler.flush_to_allure(test_name)

    @classmethod
    def clear_allure_log(cls, test_class_name: str):
        """清空指定测试类的日志缓冲"""
        if test_class_name in cls._allure_handlers:
            cls._allure_handlers[test_class_name].clear()

    @classmethod
    def log_response(
        cls, logger: logging.Logger, response: dict, title: str = "API Response"
    ):
        """格式化记录 API 响应，并附加到 Allure"""
        import json

        logger.info(f"=== {title} ===")

        if "choices" in response and response["choices"]:
            message = response["choices"][0].get("message", {})
            content = message.get("content", "")
            reasoning = message.get("reasoning")

            if content:
                logger.info(f"Content: {content[:500]}...")
            if reasoning:
                logger.info(f"Reasoning: {reasoning[:500]}...")

        logger.debug(
            f"Full Response: {json.dumps(response, ensure_ascii=False, indent=2)}"
        )

        # 附加完整响应到 Allure
        if ALLURE_AVAILABLE:
            try:
                formatted_response = json.dumps(response, ensure_ascii=False, indent=2)
                allure.attach(
                    formatted_response,
                    name=title,
                    attachment_type=AttachmentType.JSON,
                )
            except Exception:
                pass

    @classmethod
    def log_request(cls, logger: logging.Logger, messages: list, params: dict = None):
        """记录 API 请求，并附加到 Allure"""
        import json

        logger.info("=== API Request ===")
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                content_preview = f"[多模态消息，包含 {len(content)} 个部分]"
            else:
                content_preview = content[:200] if content else ""
            logger.info(f"Message {i} [{role}]: {content_preview}")

        if params:
            logger.info(f"Params: {json.dumps(params, ensure_ascii=False)}")

        # 附加完整请求到 Allure
        if ALLURE_AVAILABLE:
            try:
                request_data = {"messages": messages, "params": params or {}}
                formatted_request = json.dumps(
                    request_data, ensure_ascii=False, indent=2
                )
                allure.attach(
                    formatted_request,
                    name="API Request",
                    attachment_type=AttachmentType.JSON,
                )
            except Exception:
                pass
