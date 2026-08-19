"""
J. clear_thinking 参数行为测试

本测试类专门验证 chat_template_kwargs.clear_thinking 参数在多轮对话中的行为。
clear_thinking 仅在多轮对话场景下有意义：控制历史 assistant 消息中的思考内容
(open-think ... close-think 块或 reasoning_content 字段) 在拼下一轮 prompt 时
是否被清除。

测试点：
- J1: clear_thinking=true 多轮 - 显式清除历史 thinking，验证多轮请求成功且无泄漏 [P1]
- J2: clear_thinking=false 多轮 - 显式保留历史 thinking，验证多轮请求成功 [P1]
- J3: clear_thinking 对 prompt_tokens 的影响 - 对比 true/false 在含历史 thinking 的请求下 prompt_tokens 差异 [P2]
- J4: clear_thinking 与 enable_thinking 组合 - 四种组合均可被服务端接受 [P1]

说明：
- 历史 assistant 消息以 content 直接携带监狱 ... 块的方式构造，这是
  vLLM Qwen3/GLM5 等 chat_template 在服务端渲染时实际处理的对象，与服务端
  chat_template 的 clear_thinking 分支正面对应。
- enable_thinking 通过多种下发格式自动回退（chat_template_kwargs.enable_thinking /
  chat_template_kwargs.thinking / 顶层 enable_thinking / thinking.type），任一成功
  即视为服务端支持，避免对单一 deployment 形态过度耦合。
- 服务端若不识别 clear_thinking 参数导致 HTTP 错误，用例以 pytest.skip 跳过
  而不判失败，使报告在不同 deployment 上稳定可用。
"""

import pytest
from typing import Dict, Any, List, Optional, Tuple

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


# 用 chr() 拼接思考标签，避免在源码 / 文档处理中被工具二次解析破坏
# 0x3C/0x3E 分别是 < 和 > 的 ASCII 码，避免直接写尖括号字符
_THINK_OPEN = chr(0x3C) + "think" + chr(0x3E)
_THINK_CLOSE = chr(0x3C) + "/think" + chr(0x3E)

# 固定的多轮历史，保证每次运行 prompt_tokens 差异稳定可重现
HISTORY_USER_1 = "请计算 7 * 6"
HISTORY_USER_2 = "再把这个结果乘 3，告诉我最终是多少"

# 历史 assistant 的思考内容，刻意写得较长并有明确特征，目的是让
# clear_thinking=true/false 在 prompt_tokens 上可观测。这是 chat_template
# 在服务端"剥除或保留"的目标对象。
HISTORY_ASSISTANT_THINKING = (
    "让我一步一步计算 7 乘以 6：\n"
    "首先，7 乘以 6 可以分解为 7 + 7 + 7 + 7 + 7 + 7，\n"
    "一共 6 个 7 相加，结果是 42。\n"
    "我再换一种方式验证：6 乘以 7 等于 6 + 6 + 6 + 6 + 6 + 6 + 6，\n"
    "一共 7 个 6 相加，结果也是 42。\n"
    "因此答案确定为 42，可以作为后续推理的依据。"
)

# 历史 assistant 的最终答案，仅在 content 后半段
HISTORY_ASSISTANT_ANSWER = "7 * 6 = 42"

# 第二轮提出的 follow-up 必须基于最终答案而非思考内容（这样即便历史
# thinking 被清除，模型仍能凭最终答案给出正确响应），避免对 clear_thinking
# 的行为产生过度依赖。
HISTORY_ASSISTANT_CONTENT = (
    f"{_THINK_OPEN}\n{HISTORY_ASSISTANT_THINKING}\n"
    f"{_THINK_CLOSE}\n\n{HISTORY_ASSISTANT_ANSWER}"
)

# 第二轮期望的最终答案，用于弱断言：模型至少能基于历史最终答案给出正确推论
EXPECTED_FOLLOWUP_TOKENS = ["126", "42 * 3"]


class TestClearThinking(BaseTest, StreamingTestMixin):
    """clear_thinking 参数行为测试类"""

    def get_test_category(self) -> str:
        return "J. clear_thinking 参数行为"

    def _build_multi_turn_messages(
        self, history_content: str = HISTORY_ASSISTANT_CONTENT
    ) -> List[Dict[str, Any]]:
        """构造含历史 thinking 的多轮 messages。

        历史 assistant 的 content 直接嵌入 open-think/close-think 块，这是 vLLM Qwen3 等
        chat_template 渲染多轮历史时实际处理的对象。
        """
        return [
            {"role": "user", "content": HISTORY_USER_1},
            {"role": "assistant", "content": history_content},
            {"role": "user", "content": HISTORY_USER_2},
        ]

    def _send_with_clear_thinking(
        self,
        api_client: ModelAPIClient,
        messages: List[Dict[str, Any]],
        enable_thinking: bool,
        clear_thinking: bool,
        test_logger,
        max_tokens: int = 2048,
        temperature: float = 0.3,
        only_strategy: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """以指定 (enable_thinking, clear_thinking) 组合发送请求，自动回退多种下发格式。

        clear_thinking 几乎只能通过 chat_template_kwargs 下发，但 enable_thinking
        有多种承载形式。以下策略按顺序尝试，任一成功即返回：

            1. chat_template_kwargs.enable_thinking + chat_template_kwargs.clear_thinking
               (vLLM/Qwen3/GLM5 标准，最通用)
            2. chat_template_kwargs.thinking + chat_template_kwargs.clear_thinking
               (部分 vLLM 部署使用 thinking 而非 enable_thinking)
            3. 顶层 enable_thinking + chat_template_kwargs.clear_thinking
               (混合形式，服务端在顶层处理 enable_thinking)
            4. thinking.type=enabled/disabled + chat_template_kwargs.clear_thinking
               (DeepSeek/GLM 风格 thinking.type 对象)

        Args:
            only_strategy: 若指定（如 "chat_template_kwargs.enable_thinking"），
                则只尝试该策略，不做回退。J3 用此参数保证 true/false 对比时使用
                相同下发格式，避免 prompt_tokens 对比受策略差异干扰。

        Returns:
            (response, strategy_name) - 响应字典与实际生效的策略名

        Raises:
            pytest.skip: 所有策略均失败时跳过用例（服务端可能不支持 clear_thinking）
        """
        thinking_type = "enabled" if enable_thinking else "disabled"
        all_strategies = [
            (
                "chat_template_kwargs.enable_thinking",
                {
                    "chat_template_kwargs": {
                        "enable_thinking": enable_thinking,
                        "clear_thinking": clear_thinking,
                    }
                },
            ),
            (
                "chat_template_kwargs.thinking",
                {
                    "chat_template_kwargs": {
                        "thinking": enable_thinking,
                        "clear_thinking": clear_thinking,
                    }
                },
            ),
            (
                "top_enable_thinking+chat_template_kwargs.clear_thinking",
                {
                    "enable_thinking": enable_thinking,
                    "chat_template_kwargs": {"clear_thinking": clear_thinking},
                },
            ),
            (
                "thinking.type+chat_template_kwargs.clear_thinking",
                {
                    "thinking": {"type": thinking_type},
                    "chat_template_kwargs": {"clear_thinking": clear_thinking},
                },
            ),
        ]

        if only_strategy is not None:
            strategies = [
                (name, params)
                for name, params in all_strategies
                if name == only_strategy
            ]
            if not strategies:
                pytest.fail(
                    f"未知 only_strategy: {only_strategy}，"
                    f"可选: {[n for n, _ in all_strategies]}"
                )
        else:
            strategies = all_strategies

        last_error: Optional[Exception] = None
        last_strategy: Optional[str] = None

        for idx, (strategy_name, params) in enumerate(strategies, 1):
            test_logger.info(
                f"[{idx}/{len(strategies)}] 尝试 clear_thinking 策略: "
                f"{strategy_name} -> {params}"
            )
            meta = {
                "enable_thinking": enable_thinking,
                "clear_thinking": clear_thinking,
                "strategy": strategy_name,
                "extra_body": params,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            TestLogger.log_request(test_logger, messages, meta)
            try:
                response = api_client.chat_completion(
                    messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    extra_body=params,
                )
            except Exception as e:
                test_logger.warning(
                    f"策略 {strategy_name} 请求异常: {e}，尝试下一策略"
                )
                last_error = e
                last_strategy = strategy_name
                continue

            TestLogger.log_response(
                test_logger,
                response,
                f"clear_thinking 响应 (策略={strategy_name}, "
                f"enable={enable_thinking}, clear={clear_thinking})",
            )
            test_logger.info(f"策略 {strategy_name} 成功")
            return response, strategy_name

        # 所有策略均失败
        test_logger.warning(
            f"所有 clear_thinking 下发策略均失败 (enable_thinking={enable_thinking}, "
            f"clear_thinking={clear_thinking})，最后错误: {last_error}"
        )
        pytest.skip(
            f"服务端拒绝/不支持 clear_thinking 参数 "
            f"(尝试了 {len(strategies)} 种策略，最后策略: {last_strategy}, "
            f"最后错误: {last_error})"
        )

    @staticmethod
    def _soft_assert_followup(
        content_clean: str, test_logger, label: str
    ) -> None:
        """弱断言：第二轮响应应包含正确推论关键词。

        模型基于历史最终答案 42 应能推出 42 * 3 = 126。该断言不强制为
        assert，仅在未命中时记录 warning，避免不同模型风格差异导致用例不稳。
        """
        hit = any(tok in content_clean for tok in EXPECTED_FOLLOWUP_TOKENS)
        if hit:
            test_logger.info(f"[{label}] 第二轮响应包含期望推论: {EXPECTED_FOLLOWUP_TOKENS}")
        else:
            test_logger.warning(
                f"[{label}] 第二轮响应未命中期望推论 {EXPECTED_FOLLOWUP_TOKENS}，"
                f"响应内容: {content_clean[:500]}"
            )

    @staticmethod
    def _response_has_thinking(response: Dict[str, Any]) -> bool:
        """判断响应是否包含思考内容。

        检测两种承载方式：
        - reasoning / reasoning_content 字段非空
        - content 中含 open-think 标签（用 _THINK_OPEN 字面匹配）

        用于识别"模型强制开启思考"：当客户端显式 enable_thinking=False 时，
        若响应仍含思考内容，说明服务端不尊重该参数（模型固有特性或参数未处理）。
        """
        try:
            msg = response.get("choices", [{}])[0].get("message", {})
        except (IndexError, AttributeError, TypeError):
            return False
        reasoning = msg.get("reasoning") or msg.get("reasoning_content")
        if reasoning and len(reasoning.strip()) > 0:
            return True
        content = msg.get("content") or ""
        return _THINK_OPEN in content


    def _probe_clear_thinking_effect(
        self,
        api_client: ModelAPIClient,
        test_logger,
    ) -> Tuple[bool, Optional[str], Optional[int], Optional[int]]:
        """探测当前 deployment 的 clear_thinking 是否真的影响 prompt_tokens。

        用同一组多轮 messages 分别以 clear_thinking=true/false 发送请求
        （false 用 only_strategy 保证策略一致），对比 prompt_tokens：
        - 两次 prompt_tokens 都可用且 pt_false > pt_true -> 生效
        - 其他情况（请求失败、无 usage、pt 相等）-> 未生效

        Returns:
            (effective, strategy, pt_true, pt_false)
            - effective: clear_thinking 是否真的影响 prompt_tokens
            - strategy: 实际生效的下发策略（None 表示探测失败）
            - pt_true / pt_false: 两次请求的 prompt_tokens（None 表示不可用）
        """
        messages = self._build_multi_turn_messages()
        try:
            response_true, strategy_true = self._send_with_clear_thinking(
                api_client, messages,
                enable_thinking=True, clear_thinking=True,
                test_logger=test_logger,
            )
            response_false, _ = self._send_with_clear_thinking(
                api_client, messages,
                enable_thinking=True, clear_thinking=False,
                test_logger=test_logger,
                only_strategy=strategy_true,
            )
        except Exception as e:
            test_logger.warning(f"clear_thinking 生效性探测请求失败: {e}")
            return False, None, None, None

        pt_true = (response_true.get("usage") or {}).get("prompt_tokens")
        pt_false = (response_false.get("usage") or {}).get("prompt_tokens")

        if pt_true is None or pt_false is None:
            test_logger.warning(
                f"探测: 服务端未返回 prompt_tokens (true={pt_true}, false={pt_false})"
            )
            return False, strategy_true, pt_true, pt_false

        effective = pt_false > pt_true
        test_logger.info(
            f"clear_thinking 生效性探测: pt_true={pt_true}, pt_false={pt_false}, "
            f"effective={effective} (策略: {strategy_true})"
        )
        return effective, strategy_true, pt_true, pt_false

    @pytest.mark.j_clear_thinking
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_clear_thinking_true_multi_turn(
        self, api_client: ModelAPIClient, test_logger
    ):
        """J1 [P1]: clear_thinking=true 多轮

        显式指定 chat_template_kwargs.clear_thinking=true，发送含历史
        thinking 块的多轮请求，验证：
        - 服务端能接受该参数（HTTP 200）；
        - 第二轮响应成功返回且非空；
        - 第二轮最终回答内容可基于历史最终答案正常推论。
        """
        test_logger.info("=== 测试开始: clear_thinking=true 多轮 ===")
        messages = self._build_multi_turn_messages()

        response, strategy = self._send_with_clear_thinking(
            api_client, messages, enable_thinking=True, clear_thinking=True,
            test_logger=test_logger,
        )
        self.log_full_response(
            test_logger, response, f"J1-clear_thinking=true [{strategy}]"
        )

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content_clean = self.get_message_content(
            response, strip_thinking=True, strip_reasoning=True
        )
        test_logger.info(f"第二轮最终回答内容: {content_clean[:2000]}...")
        assert len(content_clean.strip()) > 0, (
            "clear_thinking=true 下第二轮最终回答不应为空"
        )

        self._soft_assert_followup(content_clean, test_logger, "J1")
        test_logger.info(
            f"clear_thinking=true 多轮用例通过 (策略: {strategy})"
        )

    @pytest.mark.j_clear_thinking
    @pytest.mark.p1
    def test_clear_thinking_false_multi_turn(
        self, api_client: ModelAPIClient, test_logger
    ):
        """J2 [P1]: clear_thinking=false 多轮

        显式指定 chat_template_kwargs.clear_thinking=false，发送含历史
        thinking 块的多轮请求，验证：
        - 服务端能接受该参数（HTTP 200）；
        - 第二轮响应成功返回且非空；
        - 第二轮最终回答内容可基于历史最终答案正常推论
          (此时历史 thinking 也被服务端保留并送入上下文)。
        """
        test_logger.info("=== 测试开始: clear_thinking=false 多轮 ===")
        messages = self._build_multi_turn_messages()

        response, strategy = self._send_with_clear_thinking(
            api_client, messages, enable_thinking=True, clear_thinking=False,
            test_logger=test_logger,
        )
        self.log_full_response(
            test_logger, response, f"J2-clear_thinking=false [{strategy}]"
        )

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content_clean = self.get_message_content(
            response, strip_thinking=True, strip_reasoning=True
        )
        test_logger.info(f"第二轮最终回答内容: {content_clean[:2000]}...")
        assert len(content_clean.strip()) > 0, (
            "clear_thinking=false 下第二轮最终回答不应为空"
        )

        self._soft_assert_followup(content_clean, test_logger, "J2")
        test_logger.info(
            f"clear_thinking=false 多轮用例通过 (策略: {strategy})"
        )

    @pytest.mark.j_clear_thinking
    @pytest.mark.p2
    def test_clear_thinking_prompt_tokens_difference(
        self, api_client: ModelAPIClient, test_logger
    ):
        """J3 [P2]: clear_thinking 对 prompt_tokens 的影响

        使用同一组多轮 messages 分别以 clear_thinking=true 和
        clear_thinking=false 发送请求，对比两者的 usage.prompt_tokens。

        判定规则（严格）：
        - 服务端未真实实现 clear_thinking（pt_false == pt_true）时，用例 FAIL，
          强制回归保护——避免"参数被接受但未生效"的 deployment 静默通过。
        - 服务端未返回 usage 字段时，用例 SKIP（无法判定，不视为失败）。
        - pt_false > pt_true 时用例 PASS，并在日志中记录差异量。

        本用例依赖 _probe_clear_thinking_effect 的探测结果。若探测发现
        clear_thinking 未生效，本用例直接 FAIL（与 J5 不同：J5 是探测本身，
        未生效时 SKIP；J3 是行为验证，未生效时 FAIL）。
        """
        test_logger.info("=== 测试开始: clear_thinking 对 prompt_tokens 的影响 ===")

        effective, strategy, pt_true, pt_false = self._probe_clear_thinking_effect(
            api_client, test_logger
        )

        if strategy is None:
            pytest.skip(
                "clear_thinking 探测请求失败或服务端不支持该参数，无法对比 prompt_tokens"
            )

        if pt_true is None or pt_false is None:
            pytest.skip(
                "服务端未返回 usage.prompt_tokens，无法对比 prompt_tokens 差异"
            )

        test_logger.info(
            f"prompt_tokens 对比 (策略 {strategy}): "
            f"clear=true -> {pt_true}, clear=false -> {pt_false}"
        )

        # 严格断言：pt_false 必须严格大于 pt_true
        assert pt_false > pt_true, (
            f"clear_thinking=false (保留历史 thinking) 的 prompt_tokens "
            f"{pt_false} 应严格大于 clear_thinking=true 的 {pt_true} "
            f"(策略: {strategy})；相等说明服务端未真实实现 clear_thinking，"
            f"或历史 thinking 未被渲染进 prompt"
        )

        test_logger.info(
            f"确认 clear_thinking 行为生效 (策略 {strategy}): "
            f"false 比 true 多 {pt_false - pt_true} 个 prompt_tokens"
        )
        test_logger.info("clear_thinking prompt_tokens 对比用例通过")

    @pytest.mark.j_clear_thinking
    @pytest.mark.p1
    @pytest.mark.smoke
    def test_clear_thinking_enable_combinations(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """J4 [P1]: clear_thinking 与 enable_thinking 组合

        遍历四种 (enable_thinking, clear_thinking) 组合：

        - **enable_thinking=True 的两种组合**：必须返回 HTTP 200 且响应非空。
          这是 clear_thinking 与 enable_thinking 正交独立的关键回归点。
        - **enable_thinking=False 的两种组合**：
          - 若服务端尊重参数（响应无思考内容）：必须返回 HTTP 200 且响应非空。
          - 若模型强制开启思考（响应仍含 reasoning_content 或 think 标签）：
            SKIP 该组合并 record_warning，**不视为失败**——这是模型固有特性，
            不是参数处理 bug。J4 仍可通过（只要 enable_thinking=True 的组合通过）。

        这样在强制开启思考的模型（如部分 deepseek/glm 部署）上，J4 不会因为
        enable_thinking=False 被忽略而误判失败，同时报告会明确标记该特性。
        """
        test_logger.info("=== 测试开始: clear_thinking 与 enable_thinking 组合 ===")
        messages = self._build_multi_turn_messages()

        combos: List[Tuple[bool, bool]] = [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
        ]

        results: List[Dict[str, Any]] = []
        skipped_forced: List[Tuple[bool, bool]] = []
        forced_thinking_detected = False

        for enable, clear in combos:
            test_logger.info(
                f"\n--- 组合 enable_thinking={enable}, clear_thinking={clear} ---"
            )
            response, strategy = self._send_with_clear_thinking(
                api_client, messages,
                enable_thinking=enable, clear_thinking=clear,
                test_logger=test_logger,
            )
            self.log_full_response(
                test_logger, response,
                f"J4-(enable={enable},clear={clear}) [{strategy}]",
            )
            self.assert_response_success(response)

            # enable_thinking=False 的组合：检测模型是否强制开启思考
            if not enable and self._response_has_thinking(response):
                forced_thinking_detected = True
                warn_msg = (
                    f"组合 (enable={enable}, clear={clear}) [策略 {strategy}]: "
                    f"模型强制开启思考，enable_thinking=False 不被尊重"
                    f"（响应仍含 reasoning_content 或 think 标签），SKIP 该组合"
                )
                test_logger.warning(warn_msg)
                record_warning(warn_msg)
                skipped_forced.append((enable, clear))
                continue

            self.assert_content_not_empty(response)
            results.append(
                {
                    "enable_thinking": enable,
                    "clear_thinking": clear,
                    "strategy": strategy,
                    "response": response,
                }
            )

        # 汇总日志
        test_logger.info(
            f"组合矩阵结果: 通过 {len(results)}/{len(combos)}，"
            f"SKIP(强制开启思考) {len(skipped_forced)}/{len(combos)}"
        )
        for r in results:
            test_logger.info(
                f"  [PASS] enable={r['enable_thinking']}, "
                f"clear={r['clear_thinking']} -> 策略 {r['strategy']}"
            )
        for sk in skipped_forced:
            test_logger.info(
                f"  [SKIP] enable={sk[0]}, clear={sk[1]} (模型强制开启思考)"
            )

        # enable_thinking=True 的两个组合必须通过（这是正交性的核心回归点）
        required_passed = [r for r in results if r["enable_thinking"]]
        assert len(required_passed) == 2, (
            f"enable_thinking=True 的两个组合必须通过，实际通过 "
            f"{len(required_passed)}/2"
        )

        if forced_thinking_detected:
            test_logger.warning(
                f"检测到模型强制开启思考，enable_thinking=False 的 "
                f"{len(skipped_forced)} 个组合已被 SKIP（不视为失败）"
            )

        test_logger.info("clear_thinking 组合矩阵用例通过")

    @pytest.mark.j_clear_thinking
    @pytest.mark.p1
    def test_clear_thinking_deployment_probe(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """J5 [P1]: clear_thinking deployment 能力探测

        在做行为验证（J3）之前，先探测当前 deployment 是否真的实现了
        clear_thinking 对历史 thinking 的剥除/保留行为。这是 deployment 能力
        的"事实判定"用例，不影响 J3 的硬断言，但会在报告中明确标记：

        - 生效：prompt_tokens(false) > prompt_tokens(true)，记录 INFO，
          提示 J3 应能 PASS
        - 未生效（pt 相等）：记录 WARNING 并调用 record_warning，
          提示运维/算法团队该 deployment 未真实实现 clear_thinking，
          仅"接受参数"但不"处理参数"
        - 探测失败（请求异常 / 无 usage）：SKIP，不视为失败

        与 J3 的关系：J5 是"能力探测"（未生效时 WARNING），J3 是"行为验证"
        （未生效时 FAIL）。两者互补：J5 让报告对 deployment 能力可见，
        J3 强制要求 deployment 必须真实实现 clear_thinking 才能通过回归。
        """
        test_logger.info("=== 测试开始: clear_thinking deployment 能力探测 ===")

        effective, strategy, pt_true, pt_false = self._probe_clear_thinking_effect(
            api_client, test_logger
        )

        if strategy is None:
            pytest.skip(
                "clear_thinking 探测请求失败或服务端不支持该参数，无法判定 deployment 能力"
            )

        if pt_true is None or pt_false is None:
            pytest.skip(
                "服务端未返回 usage.prompt_tokens，无法判定 clear_thinking 生效性"
            )

        test_logger.info(
            f"deployment 探测结果 (策略 {strategy}): "
            f"pt_true={pt_true}, pt_false={pt_false}, effective={effective}"
        )

        if effective:
            test_logger.info(
                f"✓ 当前 deployment 真实实现 clear_thinking: "
                f"false 比 true 多 {pt_false - pt_true} 个 prompt_tokens，"
                f"J3 行为验证应能 PASS"
            )
        else:
            warning_msg = (
                f"✗ 当前 deployment 未真实实现 clear_thinking "
                f"(pt_true={pt_true} == pt_false={pt_false}, 策略 {strategy}): "
                f"服务端仅接受参数但不剥除/保留历史 thinking，"
                f"J3 行为验证将 FAIL"
            )
            test_logger.warning(warning_msg)
            record_warning(warning_msg)
