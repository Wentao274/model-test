"""
基础测试类 - 所有测试用例的基类
"""

import json
import time
import pytest
from collections import defaultdict
from typing import Dict, Any, List, Optional, Tuple
from abc import ABC


class BaseTest(ABC):
    """测试基类，提供通用的测试方法和断言"""

    # 这些属性将由 pytest fixture 自动注入
    api_client = None
    config = None

    # 合法的 finish_reason 值（非流式最终响应）
    VALID_FINISH_REASONS = ("stop", "eos", "ended", "length")
    # 流式最后一chunk的 finish_reason 额外允许 None（中间chunk无 finish_reason）
    VALID_STREAM_FINISH_REASONS = ("stop", "eos", "ended", "length", None)

    def assert_response_success(self, response: Dict[str, Any], message: str = ""):
        """断言响应成功"""
        assert response.get("choices") is not None, (
            f"Response has no choices: {message}"
        )
        assert len(response.get("choices", [])) > 0, (
            f"No choices in response: {message}"
        )

    def get_response_content(self, response: Dict[str, Any]) -> str:
        """获取响应内容，同时支持 content 和 reasoning_content"""
        message = response.get("choices", [{}])[0].get("message", {})
        content = message.get("content") or ""
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        return content + reasoning

    def assert_content_not_empty(self, response: Dict[str, Any], message: str = ""):
        """断言响应内容不为空"""
        content = self.get_response_content(response)
        assert content and len(content.strip()) > 0, (
            f"Response content is empty: {message}"
        )

    def get_message_content(
        self,
        response: Dict[str, Any],
        strip_thinking: bool = False,
        strip_reasoning: bool = False,
    ) -> str:
        """获取消息内容

        Args:
            response: API响应
            strip_thinking: 是否去除思考内容（<think>标签之间的内容）
            strip_reasoning: 是否去除独立的 reasoning_content 字段，仅返回纯 content。
                当为 True 时直接取 message.content，不拼接 reasoning_content，
                适用于垃圾内容检测、上下文拼接等只需正式回复的场景。
        """
        if strip_reasoning:
            message = response.get("choices", [{}])[0].get("message", {})
            content = message.get("content") or ""
        else:
            content = self.get_response_content(response)
        if strip_thinking:
            content = self.strip_thinking_content(content)
        return content

    @staticmethod
    def strip_thinking_content(content: str) -> str:
        """从 content 中剥离思考内容，兼容多种思考格式

        - 标准 <think>...</think>（含 MiniMax 仅 </think> 结束标签的情况）
        - kimi-k3: <思考内容><|close|>think[<|sep|>]<最终答案>
        返回最终答案部分；无思考标记时原样返回。
        """
        if not content:
            return content
        TS = chr(60) + "think" + chr(62)
        TE = chr(60) + "/think" + chr(62)
        # kimi-k3 格式优先（其 content 不含 <think> 开标签）
        if "<|close|>think" in content and TS not in content:
            close_sep = "<|close|>think<|sep|>"
            if close_sep in content:
                parts = content.split(close_sep, 1)
                return parts[1].strip() if len(parts) > 1 else ""
            parts = content.split("<|close|>think", 1)
            return parts[1].strip() if len(parts) > 1 else ""
        # 标准 <think>...</think> 或 MiniMax 仅 </think> 结束标签
        if TE in content:
            parts = content.split(TE, 1)
            return parts[1].strip() if len(parts) > 1 else ""
        return content

    def get_reasoning_content(self, response: Dict[str, Any]) -> Optional[str]:
        """获取思考内容"""
        message = response.get("choices", [{}])[0].get("message", {})
        return message.get("reasoning") or message.get("reasoning_content")

    def get_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取工具调用列表"""
        message = response.get("choices", [{}])[0].get("message", {})
        return message.get("tool_calls", [])

    def assert_streaming_response(self, response_iterator) -> str:
        """断言流式响应正确返回"""
        tokens = []
        for chunk in response_iterator:
            if chunk.get("choices") and chunk["choices"][0].get("delta"):
                delta = chunk["choices"][0]["delta"]
                if delta.get("content"):
                    tokens.append(delta["content"])
                # 思考模型可能仅输出 reasoning，无 content
                reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                if reasoning:
                    tokens.append(reasoning)
        assert len(tokens) > 0, "No tokens received in streaming response"
        return "".join(tokens)

    def assert_thinking_mode(self, response: Dict[str, Any], message: str = ""):
        """断言思考模式正确工作"""
        message_obj = response.get("choices", [{}])[0].get("message", {})
        reasoning = message_obj.get("reasoning") or message_obj.get("reasoning_content")
        assert reasoning is not None and len(reasoning) > 0, (
            f"Thinking mode is enabled but no reasoning returned: {message}"
        )

    def assert_no_thinking_leakage(self, response: Dict[str, Any], message: str = ""):
        """断言思考模式关闭时没有思考内容泄漏"""
        message_obj = response.get("choices", [{}])[0].get("message", {})
        reasoning = message_obj.get("reasoning") or message_obj.get("reasoning_content")
        content = message_obj.get("content", "")

        assert reasoning is None or reasoning == "", (
            f"Thinking disabled but reasoning is not empty: {message}"
        )

        # 检查常见思考模式标记
        thinking_markers = [
            "让我思考",
            "让我分析",
            "首先",
            "其次",
            "因此",
            "<think>",
            "</think>",
        ]
        for marker in thinking_markers:
            if marker in content:
                pytest.fail(f"Potential thinking leakage in content: found '{marker}'")

    def assert_tool_calls(
        self,
        response: Dict[str, Any],
        expected_tool_names: Optional[List[str]] = None,
        message: str = "",
    ):
        """断言工具调用正确执行"""
        tool_calls = self.get_tool_calls(response)
        assert len(tool_calls) > 0, f"No tool calls found in response: {message}"

        if expected_tool_names:
            actual_tools = [tc.get("function", {}).get("name") for tc in tool_calls]
            for expected in expected_tool_names:
                assert expected in actual_tools, (
                    f"Expected tool '{expected}' not found in {actual_tools}: {message}"
                )

    def assert_max_tokens_limit(
        self, response: Dict[str, Any], max_tokens: int, tolerance: int = 10
    ):
        """断言输出不超过max_tokens限制"""
        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        # 允许一定的容差
        assert completion_tokens <= max_tokens + tolerance, (
            f"Completion tokens {completion_tokens} exceeds max_tokens {max_tokens}"
        )

    def get_usage(self, response: Dict[str, Any]) -> Dict[str, int]:
        """获取usage信息"""
        return response.get("usage", {})

    @staticmethod
    def log_full_response(test_logger, response: dict, title: str = "完整响应"):
        """记录完整响应信息到日志"""
        try:
            full_json = json.dumps(response, ensure_ascii=False, indent=2)
            test_logger.info(f"=== {title} 完整响应 ===\n{full_json}")
        except Exception as e:
            test_logger.warning(f"序列化完整响应失败: {e}")
            test_logger.info(f"=== {title} 原始响应 ===\n{response}")

    # ------------------------------------------------------------------
    # finish_reason / content 辅助方法（跨测试类共享）
    # ------------------------------------------------------------------

    def _get_formal_content(
        self, response: Dict[str, Any], test_logger=None, context: str = ""
    ) -> str:
        """获取正式回复内容

        优先返回 strip_reasoning + strip_thinking 后的纯 content（排除
        reasoning_content 字段和 think 标签内容）。
        若 content 为空（思考模型可能被 reasoning 消耗完 max_tokens），
        回退到 content + reasoning_content，避免因思考模型 content 为空
        导致后续断言失败。

        Args:
            response: API 响应字典
            test_logger: 日志器（可选），回退时记录提示信息
            context: 日志上下文标识
        """
        content = self.get_message_content(
            response, strip_reasoning=True, strip_thinking=True
        )
        if not content.strip():
            full = self.get_message_content(response)
            if test_logger and full.strip():
                test_logger.info(
                    f"[{context}] 正式content为空，回退到content+reasoning"
                    f"（思考模型可能被reasoning消耗了max_tokens）"
                )
            return full
        return content

    def _assert_finish_reason(
        self, response: Dict[str, Any], allow_none: bool = False
    ) -> str:
        """断言 finish_reason 合法并返回其值

        Args:
            response: API 响应字典
            allow_none: 是否允许 None（流式中间chunk）
        """
        finish_reason = response.get("choices", [{}])[0].get("finish_reason")
        valid = (
            self.VALID_STREAM_FINISH_REASONS
            if allow_none
            else self.VALID_FINISH_REASONS
        )
        assert finish_reason in valid, (
            f"finish_reason should be one of {valid}, got '{finish_reason}'"
        )
        return finish_reason

    @staticmethod
    def _get_max_context_len(model_info: dict, default: int = 202752) -> int:
        """获取模型最大上下文长度，兼容 vLLM(max_model_len) 和
        sglang(context-length) 以及部分模型(context_window)。

        Args:
            model_info: /v1/models 返回的模型信息字典
            default: 未找到任何上下文长度字段时的回退值。边界探测测试
                传 202752（假设大默认），显式判断测试传 0（跳过）。
        """
        for key in (
            "max_model_len",
            "context-length",
            "context_length",
            "context_window",
        ):
            val = model_info.get(key, 0)
            if val:
                return int(val)
        return default

    @staticmethod
    def _is_over_limit_error(e) -> bool:
        """判断异常是否表示上下文超限/连接中断/服务端边界失败

        边界探测/超限测试中，服务端对超大输入的失败不一定带规范错误码：
        - 显式 context/length/limit/token 错误
        - HTTP 413 (Request Entity Too Large)
        - HTTP 5xx 服务端错误（超大输入常引发 500/502/503/504）
        - 流式传输中断（ChunkedEncodingError/ProtocolError）
        - 连接重置/超时
        """
        if e is None:
            return False
        error_msg = str(e).lower()
        exc_name = type(e).__name__.lower()
        keywords = [
            "context",
            "length",
            "too_many",
            "exceed",
            "limit",
            "token",
            "413",
            "request entity too large",
            "500",
            "502",
            "503",
            "504",
            "internal server",
            "server error",
            "chunked",
            "protocol",
            "premature",
            "connection",
            "reset",
            "timeout",
            "timed out",
            "ended",
        ]
        return any(kw in error_msg or kw in exc_name for kw in keywords)

    # ------------------------------------------------------------------
    # 思考模式辅助方法（跨测试类共享）
    # ------------------------------------------------------------------

    def _check_has_thinking(self, response: dict, test_logger) -> bool:
        """检查响应中是否包含思考内容（reasoning 字段或 content 中的思考标签）

        标签检测复用基类 strip_thinking_content（兼容 MiniMax/kimi-k3 等格式），
        避免与各测试类历史实现重复维护。
        """
        reasoning = self.get_reasoning_content(response)
        content = self.get_message_content(response)
        finish_reason = response.get("choices", [{}])[0].get("finish_reason", "")
        has_reasoning_field = reasoning is not None and len(reasoning.strip()) > 0
        has_thinking_tags = False
        thinking_content = ""
        if content:
            # 复用基类 strip_thinking_content 检测 content 中是否含思考标签：
            # 若剥离后内容变短，说明存在思考标签
            TS = chr(60) + "think" + chr(62)
            TE = chr(60) + "/think" + chr(62)
            stripped = self.strip_thinking_content(content)
            if stripped != content:
                thinking_content = content[: content.find(stripped)] if stripped else content
                thinking_content = thinking_content.strip()
                has_thinking_tags = len(thinking_content) > 0
                if has_thinking_tags and "<|close|>think" in content and TS not in content:
                    test_logger.info("检测到 kimi-k3 格式（<|close|>think 分隔符）")
                elif has_thinking_tags and TE in content and TS not in content:
                    test_logger.info("检测到 MiniMax M2 格式（仅有结束标签）")
            elif finish_reason == "length" and not has_reasoning_field:
                # kimi-k3 思考被 max_tokens 截断：未输出思考结束标志，
                # 整段 content 为被截断的思考。通过推理特征语言区分思考 vs 普通回答。
                reasoning_markers = [
                    "the user", "i should", "i need to", "let me",
                    "i'll", "i must", "用户想", "用户问",
                    "让我", "我需要", "我应该", "我来",
                ]
                cl = content.lower()
                if len(content.strip()) > 100 and any(m in cl for m in reasoning_markers):
                    thinking_content = content.strip()
                    has_thinking_tags = len(thinking_content) > 0
                    if has_thinking_tags:
                        test_logger.info(
                            "检测到被截断的思考内容（finish_reason=length，"
                            "content 含推理特征语言且无思考结束标志）"
                        )
        test_logger.info(
            f"reasoning 字段: {reasoning[:2000] + '...' if reasoning else 'None'}"
        )
        test_logger.info(
            f"content 中的thinking标签: {'存在' if has_thinking_tags else '不存在'}"
        )
        if thinking_content:
            test_logger.info(f"思考内容: {thinking_content[:2000]}...")
        return has_reasoning_field or has_thinking_tags

    # 思考模式参数下发策略（开启）
    _THINKING_ON_STRATEGIES = [
        ("default", {}),
        ("enable_thinking", {"enable_thinking": True}),
        (
            "chat_template_kwargs.thinking",
            {"chat_template_kwargs": {"thinking": True}},
        ),
        (
            "chat_template_kwargs.enable_thinking",
            {"chat_template_kwargs": {"enable_thinking": True}},
        ),
        (
            "thinking.type.enabled",
            {"thinking": {"type": "enabled"}},
        ),
        (
            "chat_template_kwargs.thinking+reasoning_effort",
            {
                "chat_template_kwargs": {"thinking": True},
                "reasoning_effort": "high",
            },
        ),
    ]

    # 思考模式参数下发策略（关闭）
    _THINKING_OFF_STRATEGIES = [
        ("no_thinking_params", {}),
        ("enable_thinking_false", {"enable_thinking": False}),
        (
            "chat_template_kwargs.thinking_false",
            {"chat_template_kwargs": {"thinking": False}},
        ),
        (
            "chat_template_kwargs.enable_thinking_false",
            {"chat_template_kwargs": {"enable_thinking": False}},
        ),
        (
            "thinking.type.disabled",
            {"thinking": {"type": "disabled"}},
        ),
    ]

    def _chat_with_thinking_fallback(
        self,
        api_client: "ModelAPIClient",
        messages: List[Dict[str, Any]],
        test_logger,
        max_tokens: Optional[int] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], str, bool]:
        """自动尝试多种思考模式参数格式（不依赖 config.yaml 配置）

        策略顺序：
            0. {} - 不传 thinking 参数（依赖模型默认行为，部分推理模型默认即输出思考内容）
            1. {"enable_thinking": True}  - 顶层字段（OpenAI/Qwen 等）
            2. {"chat_template_kwargs": {"thinking": True}}  - chat_template 方式
            3. {"chat_template_kwargs": {"enable_thinking": True}}  - chat_template 方式（vLLM/Qwen3 等）
            4. {"thinking": {"type": "enabled"}}  - 顶层对象（DeepSeek/GLM 等）
            5. chat_template_kwargs.thinking + reasoning_effort=high

        遍历所有策略后，若均未获取到思考内容，则 fallback 到不传任何
        thinking 参数发起请求（大部分模型的思考模式默认打开），以确认
        长上下文请求本身可用。

        Args:
            max_tokens: 长上下文场景需传入较大值（如 20000）；
                None 时不传该参数（短上下文，走 API 默认 2048）。
        """
        strategies = self._THINKING_ON_STRATEGIES

        last_response = None
        last_params = None
        last_strategy = None

        for idx, (strategy_name, params) in enumerate(strategies, 1):
            test_logger.info(
                f"[{idx}/{len(strategies)}] 尝试思考参数策略: "
                f"{strategy_name} -> {params}"
            )
            try:
                kwargs = {"extra_body": params}
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                response = api_client.chat_completion(messages, **kwargs)
            except Exception as e:
                if self._is_over_limit_error(e):
                    pytest.skip(
                        f"Model/proxy does not support long context with thinking: {e}"
                    )
                test_logger.warning(f"策略 {strategy_name} 请求异常: {e}，尝试下一策略")
                last_strategy = strategy_name
                last_params = params
                continue

            self.assert_response_success(response)
            has_thinking = self._check_has_thinking(response, test_logger)

            if has_thinking:
                test_logger.info(f"策略 {strategy_name} 成功获取到思考内容")
                return response, params, strategy_name, True

            test_logger.warning(
                f"策略 {strategy_name} 未获取到思考内容，将尝试下一策略"
            )
            last_response = response
            last_params = params
            last_strategy = strategy_name

        if last_response is None:
            test_logger.info("所有思考参数策略均请求异常，fallback 到不传任何参数请求")
            try:
                kwargs = {}
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                fallback_response = api_client.chat_completion(messages, **kwargs)
            except Exception as e:
                if self._is_over_limit_error(e):
                    pytest.skip(f"Model/proxy does not support long context: {e}")
                raise
            self.assert_response_success(fallback_response)
            has_thinking = self._check_has_thinking(fallback_response, test_logger)
            return fallback_response, {}, "no_params_fallback", has_thinking

        return last_response, last_params, last_strategy, False

    def _chat_without_thinking_fallback(
        self,
        api_client: "ModelAPIClient",
        messages: List[Dict[str, Any]],
        test_logger,
        max_tokens: Optional[int] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], str, bool]:
        """自动尝试多种关闭思考模式的参数格式（不依赖 config.yaml 配置）

        任一策略无思考内容泄漏即返回；若全部仍泄漏，则 has_no_thinking=False。

        Args:
            max_tokens: 长上下文场景需传入较大值；None 时不传该参数。
        """
        strategies = self._THINKING_OFF_STRATEGIES

        last_response = None
        last_params = None
        last_strategy = None

        for idx, (strategy_name, params) in enumerate(strategies, 1):
            display_params = params if params else "(空)"
            test_logger.info(
                f"[{idx}/{len(strategies)}] 尝试非思考策略: "
                f"{strategy_name} -> {display_params}"
            )
            try:
                kwargs = {"extra_body": params}
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                response = api_client.chat_completion(messages, **kwargs)
            except Exception as e:
                if self._is_over_limit_error(e):
                    pytest.skip(
                        f"Model/proxy does not support long context without thinking: {e}"
                    )
                test_logger.warning(f"策略 {strategy_name} 请求异常: {e}，尝试下一策略")
                last_strategy = strategy_name
                last_params = params
                continue

            self.assert_response_success(response)
            has_thinking = self._check_has_thinking(response, test_logger)

            if not has_thinking:
                test_logger.info(f"策略 {strategy_name} 成功获取到无思考泄漏的响应")
                return response, params, strategy_name, True

            test_logger.warning(
                f"策略 {strategy_name} 检测到思考内容泄漏，将尝试下一策略"
            )
            last_response = response
            last_params = params
            last_strategy = strategy_name

        return last_response, last_params, last_strategy, False


class StreamingTestMixin:
    """流式测试Mixin"""

    def collect_stream_chunks(self, response_iterator) -> Dict[str, Any]:
        """收集流式响应所有chunk，并记录每个chunk到达的时间戳"""
        chunks = []
        timestamps = []
        content_parts = []
        reasoning_parts = []

        for chunk in response_iterator:
            chunks.append(chunk)
            timestamps.append(time.perf_counter())
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            if delta.get("content"):
                content_parts.append(delta["content"])
            # 同时支持 reasoning 和 reasoning_content 字段，与非流式
            # get_reasoning_content 保持一致（glm 系列使用 reasoning）
            reasoning = delta.get("reasoning") or delta.get("reasoning_content")
            if reasoning:
                reasoning_parts.append(reasoning)

        return {
            "chunks": chunks,
            "timestamps": timestamps,
            "content": "".join(content_parts),
            "reasoning": "".join(reasoning_parts),
        }

    def _assert_stream_finish_reason(self, result: Dict[str, Any]) -> str:
        """断言流式响应最后 chunk 的 finish_reason 合法并返回其值

        Args:
            result: collect_stream_chunks 返回的字典
        """
        chunks = result.get("chunks", [])
        assert len(chunks) > 0, "No streaming chunks received"
        last_chunk = chunks[-1]
        finish_reason = last_chunk.get("choices", [{}])[0].get("finish_reason")
        assert finish_reason in self.VALID_STREAM_FINISH_REASONS, (
            f"Last chunk finish_reason should be one of "
            f"{self.VALID_STREAM_FINISH_REASONS}, got '{finish_reason}'"
        )
        return finish_reason

    def detect_buffered_streaming(
        self,
        result: Dict[str, Any],
        dup_ratio_threshold: float = 0.3,
        min_chunks: int = 5,
    ) -> Tuple[bool, List[List[int]], Dict[str, Any]]:
        """检测流式响应是否被服务端积攒后一次性返回

        判定规则：当出现重复时间戳的chunk占比 >= dup_ratio_threshold 时，
        视为服务端未真正流式发送（被积攒后一次性推回）。

        Args:
            result: collect_stream_chunks 返回的字典
            dup_ratio_threshold: 重复chunk占比阈值，默认 0.3
            min_chunks: chunk总数少于此值时不做检测（样本太少），默认 5

        Returns:
            (is_buffered, duplicate_groups, stats)
            - is_buffered: 是否判定为积攒
            - duplicate_groups: 每组重复时间戳对应的chunk索引列表
            - stats: 检测统计信息（总数、唯一时间戳数、重复数、占比等）
        """
        timestamps = result.get("timestamps", [])
        chunks = result.get("chunks", [])
        total = len(timestamps)

        stats = {
            "total_chunks": total,
            "unique_timestamps": 0,
            "duplicate_chunks": 0,
            "duplicate_groups": 0,
            "dup_ratio": 0.0,
            "skipped": False,
            "skip_reason": "",
        }

        if total < min_chunks:
            stats["skipped"] = True
            stats["skip_reason"] = (
                f"chunk总数({total}) < {min_chunks}，样本不足跳过检测"
            )
            return False, [], stats

        groups: Dict[float, List[int]] = defaultdict(list)
        for idx, ts in enumerate(timestamps):
            groups[ts].append(idx)

        duplicate_groups = [idxs for idxs in groups.values() if len(idxs) > 1]
        duplicate_chunks = sum(len(g) for g in duplicate_groups)
        dup_ratio = duplicate_chunks / total if total > 0 else 0.0

        stats["unique_timestamps"] = len(groups)
        stats["duplicate_chunks"] = duplicate_chunks
        stats["duplicate_groups"] = len(duplicate_groups)
        stats["dup_ratio"] = dup_ratio

        is_buffered = dup_ratio >= dup_ratio_threshold
        return is_buffered, duplicate_groups, stats

    def log_buffered_streaming_warning(
        self,
        test_logger,
        result: Dict[str, Any],
        duplicate_groups: List[List[int]],
        stats: Dict[str, Any],
        context: str = "",
    ):
        """打印流式响应疑似被积攒的告警日志"""
        prefix = f"[{context}] " if context else ""
        test_logger.warning(
            f"{prefix}检测到流式响应疑似被服务端积攒后一次性返回: "
            f"共{stats['total_chunks']}个chunk，"
            f"{stats['duplicate_groups']}组重复时间戳，"
            f"重复chunk占比={stats['dup_ratio']:.2%} "
            f"(阈值={0.3:.0%})"
        )
        test_logger.warning(f"{prefix}唯一时间戳数: {stats['unique_timestamps']}")

        timestamps = result.get("timestamps", [])
        for g in duplicate_groups:
            test_logger.warning(
                f"{prefix}  时间戳 {timestamps[g[0]]:.6f}s "
                f"对应chunk索引: {g} (共{len(g)}个chunk)"
            )


class MultimodalTestMixin:
    """多模态测试Mixin - 统一的多模态识别失败检测与图片消息构建"""

    # 占位符关键词（响应中出现即判定为未真实识别）
    PLACEHOLDER_KEYWORDS = [
        "placeholder",
        "占位符",
        "视频占位",
        "image_placeholder",
        "video_placeholder",
        "<|",
    ]

    # 强拒绝关键词：模型明确声明无法处理图片/视频输入。出现即判定多模态不支持，
    # 不受 positive_phrases 影响。用于避免模型在拒绝后追加"例如图片中有什么"
    # 等澄清性提问，导致 positive_phrases 误判为已识别图片。
    STRONG_REFUSAL_COMMON = [
        "无法看到或处理",
        # "查看/直接" 变体：模型常以"无法直接查看或处理您上传的图片"明确拒绝
        "无法查看或处理",
        "无法直接看到或处理",
        "无法直接查看或处理",
        "作为纯文本",
        "作为一个纯文本",
        "纯文本模型",
        "纯文本ai",
        "纯文本的人工智能",
        # "基于文本的AI/模型" 自述（明确声明自身为文本模型）
        "基于文本",
        "没有多模态",
        "没有多模态输入",
        "没有多模态能力",
        "不具备多模态",
        "不具备多模态输入",
        "不具备多模态能力",
        "没有视觉能力",
        "没有视觉处理能力",
        "没有图像识别能力",
        "没有图片识别能力",
        "text-only",
        "text-based ai",
        "no visual capability",
        "no multimodal",
        "unable to see",
        "unable to analyze",
    ]

    STRONG_REFUSAL_IMAGE = [
        "无法处理图片",
        "无法处理图像",
        "无法看到图片",
        "无法查看图片",
        "无法分析图片",
        "无法分析图像",
        "cannot process image",
        "unable to process image",
        "cannot analyze image",
    ]

    STRONG_REFUSAL_VIDEO = [
        "无法处理视频",
        "无法看到视频",
        "无法查看视频",
        "无法分析视频",
        # "观看" 是视频专属动词，模型常以"无法观看视频"拒绝
        "无法观看视频",
        "无法观看或处理",
        "无法直接观看或处理",
        "无法直接观看",
        "cannot process video",
        "unable to process video",
        "cannot analyze video",
    ]

    # 一般多模态识别失败关键词（受 positive_phrases 保护）
    NO_IMAGE_KEYWORDS = [
        # 中文 - 无法看到
        "没有看到",
        "看不到",
        "无法看到",
        "无法查看",
        "无法识别",
        "无法访问",
        # 中文 - 未上传/未提供
        "没有上传",
        "没有附上",
        "没有附带",
        "没有提供",
        "没有收到",
        "没有附件",
        "没有成功上传",
        "没有图片",
        "未上传",
        "未提供",
        "未收到",
        "未附",
        "没有任何图片",
        "没有任何图像",
        "忘记上传",
        "忘记附",
        # 中文 - 请求提供
        "请上传图片",
        "请提供图片",
        "请发送图片",
        "请重新上传",
        "请上传",
        "请提供",
        "请将图片",
        "请补充相关",
        # 英文
        "i don't see",
        "i cannot see",
        "i can't see",
        "i am unable to see",
        "no image",
        "don't see any image",
        "cannot see the image",
        "haven't seen",
        "unable to process",
        "cannot process",
        "as an ai",
        "as a text model",
        "as a language model",
        "text-based ai",
        # 模型自述为纯文本模型（受 positive_phrases 保护）
        "纯文本",
        # "无法直接看到/查看/识别" 等带修饰词的变体
        "无法直接看到",
        "无法直接查看",
        "无法直接识别",
        # "没有视觉" 原子词（受 positive_phrases 保护）
        "没有视觉",
    ]

    NO_VIDEO_KEYWORDS = [
        # 中文 - 无法看到
        "没有看到",
        "看不到",
        "无法看到",
        "无法查看",
        "无法识别",
        "无法访问",
        # 中文 - 未上传/未提供
        "没有上传",
        "没有附上",
        "没有附带",
        "没有提供",
        "没有收到",
        "没有附件",
        "没有成功上传",
        "没有视频",
        "未上传",
        "未提供",
        "未收到",
        "未附",
        "没有任何视频",
        "忘记上传",
        "忘记附",
        # 中文 - 请求提供
        "请上传视频",
        "请提供视频",
        "请发送视频",
        "请重新上传",
        "请上传",
        "请提供",
        "请将视频",
        "请补充相关",
        # 英文
        "i don't see",
        "i cannot see",
        "i can't see",
        "i am unable to see",
        "no video",
        "don't see any video",
        "cannot see the video",
        "haven't seen",
        "unable to process",
        "cannot process",
        "as an ai",
        "as a text model",
        "as a language model",
        "text-based ai",
        "纯文本",
        "无法直接看到",
        "无法直接查看",
        "无法直接识别",
        # "观看" 是视频专属动词
        "无法观看",
        "无法直接观看",
        "没有视觉",
    ]

    # 仅当响应中明确包含"正在描述媒体内容"的短语时，才认为失败关键词是误报。
    # 要求短语带描述动词（显示/可以看到/有/包含等），避免"图片中的问题"等
    # 引用用户问题的措辞被误判为正面。
    POSITIVE_PHRASES = [
        "图片中显示",
        "图片中可以看到",
        "图片中有",
        "图片中包含",
        "图片中呈现",
        "图片中是",
        "图片里显示",
        "图片里可以看到",
        "图片里有",
        "图片里包含",
        "画面中显示",
        "画面中可以看到",
        "画面中有",
        "画面里显示",
        "画面里可以看到",
        "图像中显示",
        "图像中可以看到",
        "图像中有",
        "图中显示",
        "图中可以看到",
        "图中有",
        "图中包含",
        "图中呈现",
        "从图可以",
        "从图片可以",
        "从图中可以",
        "可以看到",
        "呈现出",
        "显示了一张",
        "显示了一个",
        "展示了",
        "视频中显示",
        "视频中可以看到",
        "视频中有",
        "视频中包含",
        "视频里显示",
        "视频里可以看到",
        "the image shows",
        "the picture shows",
        "the video shows",
        "in the image, we can see",
        "in the image, there is",
        "this image contains",
        "this image shows",
        "in the video, we can see",
    ]

    @staticmethod
    def _infer_media_type(messages):
        """从消息内容推断媒体类型 (image/video)"""
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        ptype = part.get("type", "")
                        if "video" in ptype:
                            return "video"
                        if "image" in ptype:
                            return "image"
        return "image"

    @staticmethod
    def check_multimodal_failure(
        response: dict, media_type: str = "image", use_positive_phrases: bool = True
    ):
        """检查多模态响应是否包含识别失败的关键词

        仅检查 message.content（模型给用户的最终回复），不检查
        reasoning_content（内部思维链），因为 reasoning 常引用用户问题中的
        "图片中"等措辞，会导致误判为"已看到图片"。

        Args:
            use_positive_phrases: True 时（实际测试用），若响应中明确包含
                "正在描述媒体内容"的短语，则失败关键词视为误报；False 时
                （能力探测用），任何失败关键词即判定不支持，避免模型说
                "看不到图片，但图片中显示的应该是红色"时被误判为已识别。

        Returns:
            匹配到的失败关键词，未匹配返回 None
        """
        message = response.get("choices", [{}])[0].get("message", {})
        content = message.get("content") or ""
        if not content:
            return None
        content_lower = content.lower()

        for keyword in MultimodalTestMixin.PLACEHOLDER_KEYWORDS:
            if keyword in content_lower:
                return keyword

        strong_keywords = MultimodalTestMixin.STRONG_REFUSAL_COMMON[:]
        if media_type == "image":
            strong_keywords += MultimodalTestMixin.STRONG_REFUSAL_IMAGE
        else:
            strong_keywords += MultimodalTestMixin.STRONG_REFUSAL_VIDEO
        for keyword in strong_keywords:
            if keyword in content_lower:
                return keyword

        keywords = (
            MultimodalTestMixin.NO_IMAGE_KEYWORDS
            if media_type == "image"
            else MultimodalTestMixin.NO_VIDEO_KEYWORDS
        )
        if use_positive_phrases:
            has_positive = any(
                phrase in content_lower
                for phrase in MultimodalTestMixin.POSITIVE_PHRASES
            )
        else:
            has_positive = False
        for keyword in keywords:
            if keyword in content_lower:
                if has_positive:
                    continue
                return keyword
        return None

    @staticmethod
    def _check_content_unsupported(response, media_type="image"):
        """检查响应内容是否表明模型不支持多模态（能力探测用）

        等价于 check_multimodal_failure(use_positive_phrases=False)：任何失败
        关键词即判定不支持，不使用 positive_phrases 覆盖，避免"看不到图片，
        但图片中显示的应该是红色"被误判为已识别。

        Returns:
            matched keyword if unsupported, None otherwise
        """
        return MultimodalTestMixin.check_multimodal_failure(
            response, media_type, use_positive_phrases=False
        )

    def skip_if_unsupported(
        self, response: dict, media_type: str, test_logger, context: str = ""
    ):
        """检测多模态识别失败则跳过测试，并记录告警日志"""
        failed_keyword = self.check_multimodal_failure(response, media_type)
        if failed_keyword:
            test_logger.warning(
                f"模型可能不支持多模态（{context}）。"
                f"Response contains: '{failed_keyword}'"
            )
            pytest.skip(
                f"Model may not support multimodal ({context} failed). "
                f"Response contains: '{failed_keyword}'"
            )

    @staticmethod
    def load_image_as_base64(path) -> str:
        """读取图片文件并返回 base64 编码字符串"""
        import base64

        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    @staticmethod
    def generate_solid_image_base64(color, size=(100, 100), fmt: str = "PNG") -> str:
        """生成纯色图片并返回 base64 编码字符串"""
        import base64
        import io
        from PIL import Image

        img = Image.new("RGB", size, color=color)
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    @staticmethod
    def generate_text_image_base64(
        lines, size=(800, 400), bg="white", fg="black", font_size: int = 48
    ) -> str:
        """生成包含文字的图片并返回 base64 编码

        优先使用系统 TTF 字体（大字号，提升 OCR 可识别性），失败回退默认字体。
        """
        import base64
        import io
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", size, color=bg)
        draw = ImageDraw.Draw(img)

        font = None
        for font_path in (
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ):
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                continue

        y = 60
        for line in lines:
            draw.text((60, y), line, fill=fg, font=font)
            y += font_size + 30

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    @staticmethod
    def build_image_messages(text: str, img_b64: str, mime: str = "image/png") -> list:
        """构建单图+文本的用户消息列表"""
        return [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{img_b64}"},
                    },
                ],
            }
        ]

    @staticmethod
    def create_image_message(image_path: str, text: str = None) -> Dict[str, Any]:
        """创建图片消息（Base64编码）"""
        image_data = MultimodalTestMixin.load_image_as_base64(image_path)
        content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_data}"},
            }
        ]
        if text:
            content.insert(0, {"type": "text", "text": text})
        return {"role": "user", "content": content}

    @staticmethod
    def create_url_image_message(image_url: str, text: str = None) -> Dict[str, Any]:
        """创建图片消息（URL）"""
        content = [{"type": "image_url", "image_url": {"url": image_url}}]
        if text:
            content.insert(0, {"type": "text", "text": text})
        return {"role": "user", "content": content}
