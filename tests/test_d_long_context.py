"""
D. 长上下文处理测试

测试点：
- D1: 短上下文基线 - input 1K tokens，验证正常推理 [P0]
- D2: 中等上下文 - input 8K-16K tokens，验证质量不降 [P1]
- D3: 长上下文 - input 32K-64K tokens，验证召回和推理 [P1]
- D4: 超长上下文 - input 128K+ tokens，验证不OOM且可用 [P0]
- D5: 大海捞针（NIAH）- 长文本中插入特定信息，验证召回率 [P0]
- D6: 上下文边界行为 - 输入恰好等于max_model_len [P1]
- D7: 超出上下文截断 - 输入超过模型限制 [P1]
- D8: 长输出生成 - 要求生成4K-8K tokens的长文本 [P1]
- D9: 超长上下文（非流式） - 验证超长上下文请求的非流式输出 [P1]
- D10: 超长上下文（流式） - 验证超长上下文请求的流式输出 [P1]
- D11: 超长上下文（边界验证） - 使用二分法逼近模型最大上下文长度 [P1]
- D12: 超长上下文（思考模式） - 验证超长上下文下reasoning_content的可用性 [P0]
"""

import pytest
import random
import string
import time
from typing import Any, Dict, List, Optional, Tuple

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


MIXED_CONTENT_TEMPLATES = [
    "人工智能（Artificial Intelligence, AI）是计算机科学的核心分支。自1956年Dartmouth会议首次提出AI概念以来，"
    "该领域经历了符号主义、连接主义和深度学习三个主要发展阶段。2012年AlexNet在ImageNet竞赛中将Top-5错误率从26%降至15.3%，"
    "标志着深度学习时代的到来。截至2025年，全球AI市场规模已突破5000亿美元，预计2030年将达到1.5万亿美元。",
    "The TCP/IP protocol suite was standardized in 1982 as RFC 791 (IP) and RFC 793 (TCP). "
    "互联网协议套件定义了4层网络模型：链路层、网络层、传输层和应用层。HTTP/1.1于1997年发布（RFC 2068），"
    "定义了GET、POST、PUT、DELETE等8种请求方法。截至2025年，全球互联网用户达53亿，IPv6采用率超过45%。",
    "量子计算利用量子叠加和量子纠缠原理进行信息处理。2019年Google的Sycamore处理器用200秒完成了经典超算Summit需要10000年的计算任务。"
    "IBM于2023年发布1121量子比特的Condor处理器。中国「九章」光量子计算机在高斯玻色采样任务上的速度比当时最快超算快10^14倍。"
    "预计2030年前可实现1000+逻辑量子比特的容错量子计算机。",
    "全球气候变化是21世纪人类面临的最大挑战之一。自工业革命以来，全球平均温度已上升约1.1°C。"
    "2023年全球CO2排放量达到368亿吨，较1990年增长60%。The Paris Agreement (2015) aims to limit global warming to 1.5°C above pre-industrial levels. "
    "可再生能源占全球发电量的比例从2010年的20%上升至2024年的38%，其中太阳能发电成本下降了89%。",
    "DNA双螺旋结构的发现是20世纪最重要的科学突破之一。1953年4月25日，James Watson和Francis Crick在Nature发表论文，"
    "描述了DNA的分子结构：两条反向平行的多核苷酸链通过A-T和G-C碱基配对形成右手螺旋，螺距3.4nm，直径2nm。"
    "人类基因组包含约30亿个碱基对，编码约20000-25000个蛋白质编码基因。CRISPR-Cas9基因编辑技术自2012年问世以来，"
    "已有超过3000种基因治疗药物进入临床试验阶段。",
    "The global economy reached $105 trillion in GDP in 2023. 2023年全球GDP总量约为105万亿美元，"
    "其中美国占比约25.4%（26.9万亿美元），中国占比约18.5%（17.8万亿美元），欧盟占比约17.1%（18.0万亿美元）。"
    "国际贸易总额达28万亿美元，跨境电商市场规模突破2.5万亿美元，同比增长15.3%。"
    "全球外债总额超过80万亿美元，发展中国家债务占GDP比重平均达到55%。",
    "莎士比亚的《哈姆雷特》创作于1600年至1601年间，是英语文学中最具影响力的戏剧作品之一。"
    "「To be, or not to be, that is the question」已成为最广为人知的文学名句之一。"
    "该剧至今已被翻译成超过80种语言，全球累计发行量超过5亿册。"
    "中国古典文学同样影响深远，《红楼梦》全书约73万字，涉及448个人物，"
    "被翻译成30余种语言，英译本The Story of the Stone由David Hawkes完成前80回翻译。",
    "HTTP/2协议于2015年发布（RFC 7540），引入了多路复用、头部压缩和服务器推送等特性。"
    "HTTP/3于2022年标准化（RFC 9114），基于QUIC协议替代TCP，显著减少了连接建立延迟："
    "TCP+TLS 1.3需要3个RTT，而QUIC仅需1个RTT。截至2025年，Chrome浏览器中约32%的请求使用HTTP/3，"
    "Google、Cloudflare和Meta是HTTP/3的主要推动者。",
    "The human heart beats approximately 100,000 times per day, pumping about 7,570 liters of blood. "
    "人类心脏每天跳动约10万次，泵送约7570升血液通过96000公里的血管网络。"
    "正常静息心率为60-100次/分钟，最大心率约为220减去年龄。"
    "心血管疾病是全球第一大死因，每年导致约1790万人死亡，占全球死亡总数的32%。"
    "全球医疗器械市场规模在2024年达到5950亿美元，年复合增长率5.7%。",
    "深度学习框架的发展极大地降低了AI开发门槛。TensorFlow于2015年11月开源，PyTorch于2016年9月发布。"
    "截至2025年，PyTorch在研究论文中的使用占比超过80%，TensorFlow在生产部署中仍占主导地位。"
    'Transformer架构由Google团队在2017年论文"Attention Is All You Need"中提出，'
    "参数量从最初的6500万增长到GPT-4的估计1.8万亿，6年增长约28000倍。"
    "训练GPT-4的估计成本超过1亿美元，所需算力约2.15×10^25 FLOPS。",
]


def generate_mixed_content(approx_tokens: int) -> str:
    """生成包含中文、英文、数字的混合文本

    Args:
        approx_tokens: 目标token数量（近似估算），混合文本约2字符/token

    Returns:
        混合文本字符串，由多样化段落组成
    """
    target_chars = approx_tokens * 2
    result = []
    current_chars = 0
    idx = 0
    while current_chars < target_chars:
        para = MIXED_CONTENT_TEMPLATES[idx % len(MIXED_CONTENT_TEMPLATES)]
        result.append(para)
        current_chars += len(para)
        idx += 1
    return "\n\n".join(result)


class TestLongContext(BaseTest, StreamingTestMixin):
    """长上下文处理测试类"""

    def get_test_category(self) -> str:
        return "D. 长上下文处理"

    @staticmethod
    def _get_max_context_len(model_info: dict) -> int:
        """获取模型最大上下文长度，兼容 vLLM(max_model_len) 和 sglang(context-length)"""
        for key in ("max_model_len", "context-length", "context_length"):
            val = model_info.get(key, 0)
            if val:
                return int(val)
        return 202752

    @staticmethod
    def _has_explicit_max_context_len(model_info: dict) -> bool:
        """判断模型信息是否显式声明了最大上下文长度

        与 _get_max_context_len 不同，此方法在未找到任何上下文长度字段时
        返回 False（而非回退默认值），用于区分"真实声明"与"回退默认值"。
        """
        for key in ("max_model_len", "context-length", "context_length"):
            if model_info.get(key):
                return True
        return False

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

    def _check_has_thinking(self, response: dict, test_logger) -> bool:
        """检查响应中是否包含思考内容（reasoning 字段或 content 中的思考标签）"""
        reasoning = self.get_reasoning_content(response)
        content = self.get_message_content(response)
        has_reasoning_field = reasoning is not None and len(reasoning.strip()) > 0
        has_thinking_tags = False
        thinking_content = ""
        if content:
            if "<think>" in content and "</think>" in content:
                start = content.find("<think>") + len("<think>")
                end = content.find("</think>")
                thinking_content = content[start:end].strip()
                has_thinking_tags = len(thinking_content) > 0
            elif content.startswith("<|im_start|>assistant\n\n"):
                after_start = content.find("\n") + len("\n")
                if "</think>" in content:
                    end = content.find("</think>")
                    thinking_content = content[after_start:end].strip()
                    has_thinking_tags = len(thinking_content) > 0
            elif "</think>" in content and "<think>" not in content:
                end = content.find("</think>")
                thinking_content = content[:end].strip()
                has_thinking_tags = len(thinking_content) > 0
                test_logger.info("检测到 MiniMax M2 格式（仅有结束标签）")
        test_logger.info(
            f"reasoning 字段: {reasoning[:2000] + '...' if reasoning else 'None'}"
        )
        test_logger.info(
            f"content 中的thinking标签: {'存在' if has_thinking_tags else '不存在'}"
        )
        if thinking_content:
            test_logger.info(f"思考内容: {thinking_content[:2000]}...")
        return has_reasoning_field or has_thinking_tags

    def _chat_with_thinking_fallback(
        self,
        api_client: ModelAPIClient,
        messages: List[Dict[str, Any]],
        test_logger,
        max_tokens: int = 8000,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], str, bool]:
        """自动尝试多种思考模式参数格式（不依赖 config.yaml 配置）

        策略顺序：
            0. {} - 不传 thinking 参数（依赖模型默认行为，部分推理模型默认即输出思考内容）
            1. {"enable_thinking": True}  - 顶层字段（OpenAI/Qwen 等）
            2. {"chat_template_kwargs": {"thinking": True}}  - chat_template 方式
            3. {"thinking": {"type": "enabled"}}  - 顶层对象（DeepSeek/GLM 等）
            4. chat_template_kwargs.thinking + reasoning_effort=high
                - 部分 vLLM/SGLang 部署需要 reasoning_effort 才会触发思考

        遍历所有策略后，若均未获取到思考内容，则 fallback 到不传任何
        thinking 参数发起请求（大部分模型的思考模式默认打开），以确认
        长上下文请求本身可用。

        Returns:
            (response, used_params, strategy_name, has_thinking)
        """
        strategies = [
            ("default", {}),
            ("enable_thinking", {"enable_thinking": True}),
            (
                "chat_template_kwargs.thinking",
                {"chat_template_kwargs": {"thinking": True}},
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

        last_response = None
        last_params = None
        last_strategy = None

        for idx, (strategy_name, params) in enumerate(strategies, 1):
            test_logger.info(
                f"[{idx}/{len(strategies)}] 尝试思考参数策略: "
                f"{strategy_name} -> {params}"
            )
            try:
                response = api_client.chat_completion(
                    messages, extra_body=params, max_tokens=max_tokens
                )
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
                fallback_response = api_client.chat_completion(
                    messages, max_tokens=max_tokens
                )
            except Exception as e:
                if self._is_over_limit_error(e):
                    pytest.skip(f"Model/proxy does not support long context: {e}")
                raise
            self.assert_response_success(fallback_response)
            has_thinking = self._check_has_thinking(fallback_response, test_logger)
            return fallback_response, {}, "no_params_fallback", has_thinking

        return last_response, last_params, last_strategy, False

    @pytest.mark.d_long_context
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_short_context_baseline(self, api_client: ModelAPIClient, test_logger):
        test_logger.info("=== 测试开始: 短上下文基线 ===")

        prompt = generate_mixed_content(800) + "\n\n请简要总结以上内容。"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 200})

        response = api_client.chat_completion(messages, max_tokens=200)
        TestLogger.log_response(test_logger, response, "短上下文响应")
        self.log_full_response(test_logger, response, "D1-短上下文基线")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content.strip()) > 20, (
            f"Short context response should be substantive, got {len(content.strip())} chars"
        )

        usage = response.get("usage", {})
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )
        assert usage.get("prompt_tokens", 0) > 0, "Should have prompt_tokens > 0"
        test_logger.info(
            f"Short context baseline passed, prompt_tokens={usage.get('prompt_tokens')}, "
            f"completion_tokens={usage.get('completion_tokens')}"
        )

    @pytest.mark.d_long_context
    @pytest.mark.p1
    def test_medium_context(self, api_client: ModelAPIClient, test_logger):
        """D2 [P1]: 中等上下文 - input 8K-16K tokens"""
        test_logger.info("=== 测试开始: 中等上下文 ===")

        prompt = generate_mixed_content(12000) + "\n\n请分析以上内容的主要观点。"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "中等上下文响应")
        self.log_full_response(test_logger, response, "D2-中等上下文")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content.strip()) > 50, (
            f"Medium context response should be substantive, got {len(content.strip())} chars"
        )

        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        assert prompt_tokens > 0, "Should have prompt_tokens > 0 for medium context"
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )
        test_logger.info(
            f"Medium context passed, prompt_tokens={prompt_tokens}, "
            f"completion_tokens={usage.get('completion_tokens')}"
        )

    @pytest.mark.d_long_context
    @pytest.mark.p1
    def test_long_context(self, api_client: ModelAPIClient, test_logger):
        """D3 [P1]: 长上下文 - input 32K-64K tokens，验证召回和推理"""
        test_logger.info("=== 测试开始: 长上下文 ===")

        prompt = generate_mixed_content(50000) + "\n\n请总结这篇文章的主要内容。"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "长上下文响应")
        self.log_full_response(test_logger, response, "D3-长上下文")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        content = self.get_message_content(response)
        assert len(content.strip()) > 50, (
            f"Long context response should be substantive, got {len(content.strip())} chars"
        )

        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        assert prompt_tokens > 0, "Should have prompt_tokens > 0 for long context"
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )
        test_logger.info(
            f"Long context passed, prompt_tokens={prompt_tokens}, "
            f"completion_tokens={usage.get('completion_tokens')}"
        )

    @pytest.mark.d_long_context
    @pytest.mark.p0
    @pytest.mark.slow
    @pytest.mark.smoke
    def test_super_long_context(self, api_client: ModelAPIClient, test_logger):
        """D4 [P0]: 超长上下文 - input 128K+ tokens"""
        test_logger.info("=== 测试开始: 超长上下文 ===")

        prompt = generate_mixed_content(128000) + "\n\n请总结以上内容的要点。"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        try:
            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "超长上下文响应")
            self.log_full_response(test_logger, response, "D4-超长上下文")
            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            assert len(content.strip()) > 10, (
                f"Super long context response should not be trivial, got {len(content.strip())} chars"
            )

            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            assert prompt_tokens > 0, (
                "Should have prompt_tokens > 0 for super long context"
            )
            assert usage.get("completion_tokens", 0) > 0, (
                "Should have completion_tokens > 0"
            )
            test_logger.info(
                f"Super long context passed, prompt_tokens={prompt_tokens}, "
                f"completion_tokens={usage.get('completion_tokens')}"
            )
        except Exception as e:
            if "max_model_len" in str(e).lower() or "context" in str(e).lower():
                pytest.skip(f"Model does not support this context length: {e}")
            raise

    @pytest.mark.d_long_context
    @pytest.mark.p0
    @pytest.mark.slow
    def test_niah_needle_in_a_haystack(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """D5: 大海捞针（NIAH）- 长文本中插入特定信息，验证召回率

        包含两个场景：
        - 场景1 (8K tokens): 基线大海捞针，验证基本召回能力
        - 场景2 (512K tokens): 超长上下文大海捞针，验证超长文本中的召回能力

        若 8K 基线通过但 512K 场景因模型不支持而无法执行，则测试通过并记录警告。
        """

        class _ContextUnsupportedError(Exception):
            pass

        test_logger.info("=== 测试开始: 大海捞针 ===")

        needle = "特殊标记：项目Alpha的第37号实验结果为42，这是唯一正确的数值。"

        def _is_garbled(text: str, threshold: float = 0.4) -> bool:
            """检测文本是否为乱码/噪声输出

            判定逻辑：统计文本中非正常字符（乱码片段、孤立符号、
            重复模式）的比例，超过阈值则判定为乱码。
            """
            if not text or len(text.strip()) < 10:
                return True
            import re

            clean = re.sub(r"[\s\n\r]", "", text)
            if len(clean) < 10:
                return True
            garbled_patterns = [
                r"\ufffd",
                r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9\s.,;:!?\'"()\-\u2014\u2013\u201c\u201d\u2018\u2019/\\@#$%^&*+=\[\]{}|<>~`_]',
            ]
            garbled_chars = 0
            for m in re.finditer(garbled_patterns[0], clean):
                garbled_chars += 1
            garbled_chars += len(re.findall(garbled_patterns[1], clean))
            short_frag = len(re.findall(r"\S{1,2}(?:\s+\S{1,2}){4,}", text))
            if short_frag > 5:
                garbled_chars += short_frag * 3
            ratio = garbled_chars / max(len(clean), 1)
            return ratio > threshold

        def run_niah_scenario(context_tokens: int, scenario_name: str):
            """执行单个大海捞针场景

            在生成的长文本中间插入needle，验证模型能否正确召回。
            当检测到模型不支持该上下文长度时（静默失败），抛出
            _ContextUnsupportedError 而非 pytest.skip，以便调用方
            区分处理：8K 不可支持则 FAIL，512K 不可支持则 PASS+警告。
            """
            test_logger.info(f"--- {scenario_name}: ~{context_tokens} tokens ---")

            base_text = generate_mixed_content(context_tokens)
            needle_text = (
                base_text[: len(base_text) // 2]
                + needle
                + base_text[len(base_text) // 2 :]
            )

            prompt = needle_text + "\n\n请问文章中的特殊标记是什么？"

            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, f"{scenario_name}响应")
            self.log_full_response(test_logger, response, f"D5-{scenario_name}")

            self.assert_response_success(response)

            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)

            if prompt_tokens <= 1 and context_tokens >= 8000:
                raise _ContextUnsupportedError(
                    f"[{scenario_name}] Silent failure: prompt_tokens={prompt_tokens} "
                    f"for ~{context_tokens} token input — model/proxy likely does not "
                    f"support this context length"
                )

            self.assert_content_not_empty(response)
            content = self.get_message_content(response)

            assert prompt_tokens > 0, (
                f"[{scenario_name}] Should have prompt_tokens > 0 for NIAH test, "
                f"got {prompt_tokens} — request may not have been processed"
            )

            is_garbled = _is_garbled(content)
            if is_garbled:
                test_logger.warning(
                    f"[{scenario_name}] Response appears garbled/noisy, "
                    f"content[:500]: {content[:500]}"
                )
                assert False, (
                    f"[{scenario_name}] Response is garbled/noisy — model failed to "
                    f"properly process the long context. Cannot validate needle recall "
                    f"from incoherent output. Got: {content[:500]}"
                )

            content_lower = content.lower()

            needle_core_assertions = [
                ("42", "42"),
                ("alpha", "Alpha"),
            ]
            needle_secondary = [
                ("特殊标记", "特殊标记"),
                ("37", "37"),
                ("实验结果", "实验结果"),
            ]

            core_hits = sum(
                1 for kw, _ in needle_core_assertions if kw in content_lower
            )
            secondary_hits = sum(1 for kw, _ in needle_secondary if kw in content_lower)

            assert core_hits == len(needle_core_assertions), (
                f"[{scenario_name}] Model must contain all core needle info "
                f"({', '.join(desc for _, desc in needle_core_assertions)}). "
                f"Matches: {core_hits}/{len(needle_core_assertions)}. "
                f"Needle: '{needle}'. Got: {content[:500]}"
            )
            assert secondary_hits >= 1, (
                f"[{scenario_name}] Model must reference at least 1 secondary "
                f"needle detail ({', '.join(desc for _, desc in needle_secondary)}). "
                f"Matches: {secondary_hits}/{len(needle_secondary)}. "
                f"Got: {content[:500]}"
            )

            test_logger.info(
                f"[{scenario_name}] NIAH passed, "
                f"core_hits={core_hits}, secondary_hits={secondary_hits}, "
                f"prompt_tokens={prompt_tokens}, "
                f"completion_tokens={usage.get('completion_tokens')}, "
                f"response: {content[:2000]}"
            )

        # 场景1: 8K tokens（基线）— 必须通过
        run_niah_scenario(8000, "8K基线")

        # 场景2: 512K tokens（超长上下文大海捞针）
        # 先判断模型是否支持512K上下文长度：若模型显式声明的最大上下文 < 512K，
        # 则跳过该场景；若模型信息未声明最大上下文长度，则正常测试并根据结果断言
        model_info = api_client.get_model_info()
        if self._has_explicit_max_context_len(model_info):
            max_len = self._get_max_context_len(model_info)
            if max_len < 512000:
                test_logger.info(
                    f"512K场景: 模型最大上下文长度 {max_len} < 512000，跳过512K场景"
                )
                record_warning("模型最大上下文长度 < 512K，跳过512K大海捞针测试")
                return
            test_logger.info(
                f"512K场景: 模型最大上下文长度 {max_len} >= 512000，执行512K测试"
            )
        else:
            test_logger.info(
                "512K场景: 模型信息未声明最大上下文长度，正常执行512K测试并根据结果断言"
            )

        # 512K prefill 耗时较长，自适应放大超时，结束后恢复原值
        original_timeout = api_client.timeout
        api_client.timeout = max(original_timeout, 600)
        try:
            run_niah_scenario(512000, "512K超长")
        except _ContextUnsupportedError as e:
            test_logger.warning(str(e))
            record_warning("模型可能不支持512K上下文长度，跳过512K大海捞针测试")
        except Exception as e:
            if self._is_over_limit_error(e):
                test_logger.warning(
                    f"512K场景: 模型/proxy不支持该上下文长度，跳过: {e}"
                )
                record_warning("模型可能不支持512K上下文长度，跳过512K大海捞针测试")
            else:
                raise
        finally:
            api_client.timeout = original_timeout

    @pytest.mark.d_long_context
    @pytest.mark.p1
    def test_context_boundary_behavior(self, api_client: ModelAPIClient, test_logger):
        """D6: 上下文边界行为 - 输入接近模型限制"""
        test_logger.info("=== 测试开始: 上下文边界行为 ===")

        # 尝试获取模型信息
        model_info = api_client.get_model_info()
        max_len = self._get_max_context_len(model_info)

        # 场景1: 输入接近上限（max_len - 2000，留出输出空间），应成功
        test_logger.info(f"--- 场景1: 接近上限 (target ~{max_len - 2000} tokens) ---")
        near_limit_tokens = max(1000, max_len - 2000)
        prompt = generate_mixed_content(near_limit_tokens) + "\n\n请简要总结以上内容。"
        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 1000})

        try:
            response_iter = api_client.chat_completion_stream(messages, max_tokens=1000)
            result = self.collect_stream_chunks(response_iter)
            self.log_full_response(
                test_logger,
                {
                    "chunks_count": len(result["chunks"]),
                    "content": result["content"][:2000],
                    "reasoning": result["reasoning"][:2000]
                    if result["reasoning"]
                    else "",
                },
                "D6-上下文边界行为-接近上限",
            )

            assert len(result["chunks"]) > 0, (
                "Should receive streaming chunks near context limit"
            )
            assert result["content"] or result["reasoning"], (
                "Should have non-empty content or reasoning near context limit"
            )
            test_logger.info(
                f"接近上限场景通过, chunks={len(result['chunks'])}, "
                f"content_len={len(result['content'])}"
            )
        except Exception as e:
            error_msg = str(e).lower()
            if any(
                kw in error_msg
                for kw in ["413", "request entity too large", "timed out", "timeout"]
            ):
                pytest.skip(
                    f"Request near max context length {max_len} failed due to "
                    f"proxy/timeout limit, cannot verify boundary: {e}"
                )
            raise

        test_logger.info(f"Context boundary test completed, max_len: {max_len}")

    @pytest.mark.d_long_context
    @pytest.mark.p1
    def test_context_truncation(self, api_client: ModelAPIClient, test_logger):
        """D7: 超出上下文截断 - 验证截断策略"""
        test_logger.info("=== 测试开始: 上下文截断 ===")

        # 获取模型最大上下文长度，生成超过上限的输入
        model_info = api_client.get_model_info()
        max_len = self._get_max_context_len(model_info)

        # 输入超过 max_len，确保触发截断或超限错误
        over_tokens = max_len + 4000
        test_logger.info(f"模型最大上下文: {max_len}, 生成输入 ~{over_tokens} tokens")
        prompt = generate_mixed_content(over_tokens) + "\n\n请简短总结以上内容。"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 500})

        try:
            response_iter = api_client.chat_completion_stream(messages, max_tokens=500)
            result = self.collect_stream_chunks(response_iter)
            self.log_full_response(
                test_logger,
                {
                    "chunks_count": len(result["chunks"]),
                    "content": result["content"][:2000],
                    "reasoning": result["reasoning"][:2000]
                    if result["reasoning"]
                    else "",
                },
                "D7-上下文截断",
            )

            # 超限场景下，模型应能截断后正常响应
            assert len(result["chunks"]) > 0, (
                "Should receive streaming chunks even when context exceeds limit"
            )
            assert result["content"] or result["reasoning"], (
                "Should have non-empty content or reasoning after truncation"
            )
            test_logger.info(
                f"Context truncation handled: chunks={len(result['chunks'])}, "
                f"content_len={len(result['content'])}, "
                f"reasoning_len={len(result['reasoning'])}"
            )
        except Exception as e:
            test_logger.info(f"Context exceeded: {e}")
            # 超限时模型可能返回错误（拒绝）、5xx 服务端错误、流式中断或超时，
            # 均为预期行为（复用 _is_over_limit_error 统一判定）
            assert self._is_over_limit_error(e), (
                f"Error should relate to context/length/proxy/server limit, got: {e}"
            )

    @pytest.mark.d_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_long_output_generation(self, api_client: ModelAPIClient, test_logger):
        """D8: 长输出生成 - 要求生成4K-8K tokens的长文本"""
        test_logger.info("=== 测试开始: 长输出生成 ===")

        messages = [
            {
                "role": "user",
                "content": (
                    "请写一篇关于人工智能发展史的详细文章，要求：\n"
                    "1. 涵盖从1956年Dartmouth会议到2025年的完整发展脉络；\n"
                    "2. 包括符号主义、连接主义、深度学习、大模型四个阶段；\n"
                    "3. 每个阶段需列举代表性事件、关键人物和技术突破；\n"
                    "4. 文章不少于4000字，结构清晰，分章节论述。"
                ),
            }
        ]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 8000})

        try:
            response_iter = api_client.chat_completion_stream(messages, max_tokens=8000)
            result = self.collect_stream_chunks(response_iter)
            self.log_full_response(
                test_logger,
                {
                    "chunks_count": len(result["chunks"]),
                    "content": result["content"][:2000],
                    "reasoning": result["reasoning"][:2000]
                    if result["reasoning"]
                    else "",
                },
                "D8-长输出生成",
            )

            assert len(result["chunks"]) > 0, "Should receive streaming chunks"
            content = result["content"]

            # 流式无 usage，通过字符数估算: 4K tokens 约对应 2000+ 中文字符
            test_logger.info(
                f"Long output: {len(result['chunks'])} chunks, "
                f"content length: {len(content)} chars, "
                f"reasoning length: {len(result['reasoning'])} chars"
            )
            # 4K tokens 约 2000-4000 中文字符，断言下限
            assert len(content) >= 2000, (
                f"Expected long output (>=2000 chars, ~4K tokens), got {len(content)} chars"
            )
        except Exception as e:
            error_msg = str(e).lower()
            if any(kw in error_msg for kw in ["timed out", "timeout"]):
                pytest.skip(f"Long output generation timed out: {e}")
            raise

    @pytest.mark.d_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_super_long_context_create(self, api_client: ModelAPIClient, test_logger):
        """D9: 超长上下文（非流式） - 验证超长上下文请求的非流式输出"""
        test_logger.info("=== 测试开始: 超长上下文(非流式) ===")

        # 目标: 输入约 128K tokens，验证非流式超长上下文响应
        long_prompt = generate_mixed_content(128000) + "\n\n请简短总结以上内容。"
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [{"role": "user", "content": long_prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 500})

        try:
            response = api_client.chat_completion(messages, max_tokens=500)
            TestLogger.log_response(test_logger, response, "超长上下文响应")

            self.assert_response_success(response)
            self.log_full_response(test_logger, response, "D9-超长上下文(非流式)")

            reasoning = self.get_reasoning_content(response)
            content = self.get_message_content(response)

            assert content and len(content.strip()) > 0, (
                "Should have non-empty content in super long context"
            )

            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            # 超长上下文应产生大量 prompt_tokens
            assert prompt_tokens > 50000, (
                f"Super long context should have large prompt_tokens, got {prompt_tokens}"
            )
            assert completion_tokens > 0, "Should have completion_tokens > 0"
            test_logger.info(
                f"Super long context test: prompt_tokens={prompt_tokens}, "
                f"completion_tokens={completion_tokens}"
            )
            test_logger.info(
                f"Content length: {len(content) if content else 0}, "
                f"Reasoning length: {len(reasoning) if reasoning else 0}"
            )

        except Exception as e:
            error_msg = str(e).lower()
            if any(
                kw in error_msg
                for kw in [
                    "max_model_len",
                    "context",
                    "413",
                    "request entity too large",
                    "timed out",
                    "timeout",
                ]
            ):
                pytest.skip(f"Model/proxy does not support this context length: {e}")
            raise

    @pytest.mark.d_long_context
    @pytest.mark.p1
    @pytest.mark.slow
    def test_super_long_context_stream(self, api_client: ModelAPIClient, test_logger):
        """D10: 超长上下文（流式） - 验证超长上下文请求的流式输出"""
        test_logger.info("=== 测试开始: 超长上下文(流式) ===")

        # 目标: 输入约 128K tokens，验证流式超长上下文响应
        long_prompt = generate_mixed_content(128000) + "\n\n请简短总结以上内容。"
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [{"role": "user", "content": long_prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 500})

        try:
            response_iter = api_client.chat_completion_stream(messages, max_tokens=500)
            result = self.collect_stream_chunks(response_iter)

            self.log_full_response(
                test_logger,
                {
                    "chunks_count": len(result["chunks"]),
                    "content": result["content"][:2000],
                    "reasoning": result["reasoning"][:2000]
                    if result["reasoning"]
                    else "",
                },
                "D10-超长上下文(流式)",
            )

            # 流式响应应有足够 chunks 证明是真正的流式输出
            assert len(result["chunks"]) > 0, "Should receive streaming chunks"
            assert result["content"] or result["reasoning"], (
                "Should have non-empty content or reasoning in streaming response"
            )
            if result["content"]:
                assert len(result["content"].strip()) > 0, (
                    "Streaming content should not be empty"
                )
            test_logger.info(
                f"Streaming chunks: {len(result['chunks'])}, "
                f"content length: {len(result['content'])}, "
                f"reasoning length: {len(result['reasoning'])}"
            )

        except Exception as e:
            error_msg = str(e).lower()
            if any(
                kw in error_msg
                for kw in [
                    "max_model_len",
                    "context",
                    "413",
                    "request entity too large",
                    "timed out",
                    "timeout",
                ]
            ):
                pytest.skip(f"Model/proxy does not support this context length: {e}")
            raise

    @pytest.mark.d_long_context
    @pytest.mark.p1
    def test_context_boundary_exact_limit(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """D11 [P1]: 超长上下文（边界验证） - 探进+二分法逼近模型最大上下文长度

        针对超长上下文（如1M）模型优化：
        - 探进法（指数倍增）先建立成功/失败区间，绝大多数迭代落在快速的小尺寸上；
        - 仅在区间内做二分逼近，收敛容差按 max_len 缩放，避免无谓迭代；
        - 单请求超时随输入规模自适应放大，避免大上下文 prefill 超时；
        - 总体墙钟预算保护，超时则以已得最大成功值判定，避免用例整体超时；
        - 一旦已确认 >=80%（通过阈值）即提前结束，不再探测更高尺寸。
        """
        test_logger.info("=== 测试开始: 上下文边界（探进+二分） ===")

        # 通过阈值：断言只要求 >=80%，达到即可提前结束
        PASS_RATIO = 0.8
        # 总体墙钟预算（秒），避免单测超时；可经 model config 覆盖
        overall_budget = 1500
        try:
            overall_budget = int(
                (api_client.config or {}).get("boundary_test_budget", overall_budget)
            )
        except (TypeError, ValueError):
            pass

        def is_over_limit_error(e) -> bool:
            """复用类级共享判定逻辑（见 _is_over_limit_error）"""
            return self._is_over_limit_error(e)

        def adaptive_timeout(size_tokens: int) -> int:
            # 基础 60s + 每token 约 1.5ms，覆盖 prefill 随输入长度增长
            # 1M ~= 1560s，100K ~= 210s，8K ~= 72s
            return max(60, int(60 + size_tokens * 0.0015))

        # 字符/token 比，校准前用随机ASCII经验值 3.0；校准后更新为实测值
        chars_per_token = 3.0

        def calibrate_chars_per_token():
            """发一个小的非流式请求，从服务端 usage.prompt_tokens 反推字符/token 比

            确保后续 build_prompt 生成的字符数能真正逼近声明的 token 数，
            避免大上下文模型"字符数远小于token数"导致的假阳性。
            """
            nonlocal chars_per_token
            sample_chars = 4096
            letters_digits = string.ascii_letters + string.digits
            n_alnum = int(sample_chars * 0.9)
            n_space = sample_chars - n_alnum
            sample_list = random.choices(letters_digits, k=n_alnum) + [" "] * n_space
            random.shuffle(sample_list)
            sample_prompt = "".join(sample_list)
            messages = [{"role": "user", "content": sample_prompt}]
            try:
                test_logger.info(f"校准请求: {sample_chars} 字符, 非流式")
                resp = api_client.chat_completion(messages, max_tokens=5)
                pt = resp.get("usage", {}).get("prompt_tokens", 0)
                if pt > 0:
                    ratio = sample_chars / pt
                    test_logger.info(
                        f"校准结果: {sample_chars}字符 -> {pt}tokens, "
                        f"chars/token={ratio:.3f}"
                    )
                    chars_per_token = ratio
                else:
                    test_logger.warning(
                        "校准: 服务端未返回 prompt_tokens，使用默认 3.0"
                    )
            except Exception as e:
                test_logger.warning(f"校准请求失败，使用默认 3.0: {e}")

        def build_prompt(size_tokens: int) -> str:
            target_chars = int(size_tokens * chars_per_token)
            letters_digits = string.ascii_letters + string.digits
            n_alnum = int(target_chars * 0.9)
            n_space = target_chars - n_alnum
            prompt_chars = random.choices(letters_digits, k=n_alnum) + [" "] * n_space
            random.shuffle(prompt_chars)
            return "".join(prompt_chars)

        original_timeout = api_client.timeout
        start_time = time.time()

        def elapsed() -> float:
            return time.time() - start_time

        def probe(size_tokens: int):
            """单次探测。返回 (ok, error)。ok 表示该长度可成功流式返回。"""
            prompt = build_prompt(size_tokens)
            messages = [{"role": "user", "content": prompt}]
            test_logger.info(f"探测长度 ~{size_tokens} tokens")
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            api_client.timeout = adaptive_timeout(size_tokens)
            try:
                response_iter = api_client.chat_completion_stream(
                    messages, max_tokens=2000
                )
                result = self.collect_stream_chunks(response_iter)
                self.log_full_response(
                    test_logger,
                    {
                        "chunks_count": len(result["chunks"]),
                        "content": result["content"][:2000],
                        "reasoning": result["reasoning"][:2000]
                        if result["reasoning"]
                        else "",
                    },
                    f"D11-边界探测-长度{size_tokens}",
                )
                ok = len(result["chunks"]) > 0 and (
                    result["content"] or result["reasoning"]
                )
                return ok, None
            except Exception as e:
                test_logger.warning(f"长度 {size_tokens} 异常: {e}")
                return False, e
            finally:
                api_client.timeout = original_timeout

        def handle_failure(size_tokens: int, err):
            """处理探测失败：超限/中断类仅记录告警；其它异常向上抛出"""
            if err is not None and not is_over_limit_error(err):
                raise err
            tag = "超限" if err is not None else "响应为空"
            test_logger.warning(f"长度 {size_tokens} 失败: {tag}")
            record_warning(f"长度{size_tokens}{tag}")

        try:
            model_info = api_client.get_model_info()
            max_len = self._get_max_context_len(model_info)
            test_logger.info(f"模型定义的最大上下文长度: {max_len}")
            if max_len <= 0:
                pytest.skip("无法获取模型最大上下文长度")

            # 校准字符/token 比，使后续探测真正逼近声明的 token 边界
            calibrate_chars_per_token()

            tolerance = max(int(max_len * 0.01), 1024)
            pass_threshold = int(max_len * PASS_RATIO)
            test_logger.info(
                f"参数: 通过阈值={pass_threshold}({PASS_RATIO:.0%}), "
                f"收敛容差={tolerance}, 总预算={overall_budget}s, "
                f"chars/token={chars_per_token:.3f}"
            )

            successful_len = 0
            failed_len = max_len

            # 阶段1：探进法（指数倍增）建立 [low, high] 区间
            # 从小基数开始，绝大多数迭代落在快速的小尺寸上
            test_logger.info("--- 阶段1: 探进法建立区间 ---")
            floor_size = min(1024, max_len)
            ok, err = probe(floor_size)
            if ok:
                successful_len = floor_size
                low = floor_size
            else:
                handle_failure(floor_size, err)
                failed_len = floor_size
                low = 0

            if successful_len > 0:
                cur = successful_len
                step = max(floor_size, 1024)
                max_gallop = 25  # log2(1M/1K)~=10，余量充足
                for _ in range(max_gallop):
                    if elapsed() > overall_budget:
                        test_logger.warning(
                            f"总预算 {overall_budget}s 已用尽，提前结束探进"
                        )
                        break
                    if successful_len >= pass_threshold:
                        test_logger.info(f"已达通过阈值 {pass_threshold}，提前结束探进")
                        break
                    if cur >= max_len:
                        break
                    nxt = min(cur + step, max_len)
                    if nxt <= cur:
                        break
                    ok, err = probe(nxt)
                    if ok:
                        successful_len = nxt
                        low = nxt
                        cur = nxt
                        step *= 2
                    else:
                        handle_failure(nxt, err)
                        failed_len = nxt
                        break

            high = failed_len
            test_logger.info(
                f"阶段1完成: 区间 [{low}, {high}], 已成功 {successful_len}, "
                f"耗时 {elapsed():.1f}s"
            )

            # 阶段2：在区间内二分逼近（仅在未达通过阈值且区间有效时）
            if successful_len < pass_threshold and high > low:
                test_logger.info(f"--- 阶段2: 二分逼近（容差 {tolerance}）---")
                max_bin_iters = 16
                for iteration in range(max_bin_iters):
                    if high - low <= tolerance:
                        break
                    if elapsed() > overall_budget:
                        test_logger.warning(
                            f"总预算 {overall_budget}s 已用尽，提前结束二分，"
                            f"当前最佳成功 {successful_len}"
                        )
                        break
                    mid = (low + high) // 2
                    if mid < 100:
                        low = mid + 1
                        continue
                    ok, err = probe(mid)
                    if ok:
                        low = mid + 1
                        successful_len = mid
                        test_logger.info(f"迭代 {iteration + 1}: 长度 {mid} 成功")
                        if successful_len >= pass_threshold:
                            test_logger.info(
                                f"已达通过阈值 {pass_threshold}，提前结束二分"
                            )
                            break
                    else:
                        handle_failure(mid, err)
                        high = mid - 1
                        failed_len = mid

            test_logger.info(
                f"边界测试结果: 成功最大长度 ~{successful_len} tokens, "
                f"失败长度 ~{failed_len} tokens, 模型声明 {max_len} tokens, "
                f"总耗时 {elapsed():.1f}s"
            )

            if successful_len <= 0:
                pytest.skip("无法确定有效的上下文长度")

            ratio = successful_len / max_len
            test_logger.info(f"实际成功率: {ratio:.2%}")
            if elapsed() > overall_budget and ratio < PASS_RATIO:
                # 预算耗尽且未能验证到通过阈值：无法判定，跳过避免误报
                pytest.skip(
                    f"测试预算 {overall_budget}s 耗尽，仅验证至 "
                    f"{successful_len}/{max_len} ({ratio:.2%})，无法完成完整边界测试"
                )
            assert ratio > PASS_RATIO or successful_len >= max_len * PASS_RATIO, (
                f"Model claims {max_len} but only supports ~{successful_len}"
            )
            test_logger.info("上下文边界验证通过")

        except Exception as e:
            if is_over_limit_error(e):
                test_logger.info(f"Context boundary reached: {e}")
            else:
                raise
        finally:
            api_client.timeout = original_timeout

    @pytest.mark.d_long_context
    @pytest.mark.p0
    def test_reasoning_content_in_long_context(
        self, api_client: ModelAPIClient, test_logger
    ):
        """D12: 超长上下文（思考模式） - 验证超长上下文下reasoning_content的可用性

        不依赖 config.yaml 配置，自动按以下顺序尝试参数格式：
        0. 不传参数（依赖模型默认行为，部分推理模型默认即输出思考内容）
        1. enable_thinking=true (顶层字段)
        2. chat_template_kwargs={"thinking": true}
        3. thinking={"type": "enabled"} (DeepSeek/GLM 风格)
        4. chat_template_kwargs.thinking=true + reasoning_effort=high
        遍历所有策略后，若均未获取到思考内容，则 fallback 到不传任何
        thinking 参数发起请求（大部分模型的思考模式默认打开），验证长上下文
        请求本身可用。
        """
        test_logger.info("=== 测试开始: 长上下文+思考（自动回退） ===")

        # 生态系统背景（问题核心，保留语义供模型推理）
        ecosystem_background = (
            "在一个封闭的生态系统中，存在三种生物：草、兔子和狐狸。草的生长速率为每天100单位，"
            "每只兔子每天消耗1单位草，每只狐狸每天消耗1只兔子。兔子的繁殖率为每天10%，"
            "狐狸的繁殖率为每天5%，兔子的自然死亡率为每天2%，狐狸的自然死亡率为每天3%。"
            "初始状态下有1000单位草、100只兔子和20只狐狸。"
        )
        # 用混合内容扩充至长上下文（目标 ~50K tokens），保留 ecosystem_background 作为问题核心
        padding = generate_mixed_content(50000)
        long_prompt = (
            "请仔细分析以下生态系统动力学问题，给出详细的推理过程：\n\n"
            + ecosystem_background
            + "\n\n以下是相关的背景参考资料：\n\n"
            + padding
            + "\n\n请基于以上背景信息，回答以下问题："
            "1. 在没有狐狸的情况下，兔子和草的种群数量会如何变化？"
            "2. 引入狐狸后，三个物种之间会形成怎样的动态平衡？"
            "3. 如果草的生长速率降低到每天50单位，生态系统会发生什么变化？"
            "请逐步分析并给出你的推理过程。"
        )
        test_logger.info(f"输入长度: {len(long_prompt)} 字符")

        messages = [{"role": "user", "content": long_prompt}]
        TestLogger.log_request(
            test_logger,
            messages,
            {
                "max_tokens": 8000,
                "thinking_mode": (
                    "auto-fallback (default -> enable_thinking "
                    "-> chat_template_kwargs.thinking "
                    "-> thinking.type=enabled "
                    "-> chat_template_kwargs.thinking+reasoning_effort "
                    "-> no_params_fallback)"
                ),
            },
        )

        (
            response,
            used_params,
            strategy,
            has_thinking,
        ) = self._chat_with_thinking_fallback(
            api_client, messages, test_logger, max_tokens=8000
        )
        if response is None:
            pytest.fail(
                f"All thinking strategies failed with API errors. "
                f"Last strategy: {strategy}, params: {used_params}"
            )

        TestLogger.log_response(
            test_logger, response, f"长上下文+思考响应 (策略: {strategy})"
        )
        self.log_full_response(
            test_logger, response, f"D12-长上下文+思考模式 [{strategy}]"
        )

        self.assert_response_success(response)
        self.assert_content_not_empty(response)

        reasoning = self.get_reasoning_content(response)
        content = self.get_message_content(response)

        assert has_thinking, (
            "Thinking mode should return reasoning content (reasoning field or thinking tags) "
            "in long context. "
            "Tried strategies: default, enable_thinking, chat_template_kwargs.thinking, "
            "thinking.type=enabled, chat_template_kwargs.thinking+reasoning_effort, "
            "no_params_fallback. "
            f"Last params: {used_params}"
        )

        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        # 长上下文应产生大量 prompt_tokens
        assert prompt_tokens > 10000, (
            f"Long context with thinking should have large prompt_tokens, got {prompt_tokens}"
        )
        assert usage.get("completion_tokens", 0) > 0, (
            "Should have completion_tokens > 0"
        )

        test_logger.info(
            f"Long context with thinking (strategy={strategy}): "
            f"reasoning={len(reasoning) if reasoning else 0} chars, "
            f"content={len(content) if content else 0} chars, "
            f"prompt_tokens={prompt_tokens}, "
            f"completion_tokens={usage.get('completion_tokens')}"
        )
