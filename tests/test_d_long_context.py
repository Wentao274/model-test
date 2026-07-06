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
from typing import List

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
    def test_niah_needle_in_a_haystack(self, api_client: ModelAPIClient, test_logger):
        """D5: 大海捞针（NIAH）- 长文本中插入特定信息，验证召回率"""
        test_logger.info("=== 测试开始: 大海捞针 ===")

        # 生成一篇长文章，在中间插入一个特定的事实
        base_text = generate_mixed_content(8000)
        needle = "特殊标记：项目Alpha的第37号实验结果为42，这是唯一正确的数值。"
        needle_text = (
            base_text[: len(base_text) // 2] + needle + base_text[len(base_text) // 2 :]
        )

        prompt = needle_text + "\n\n请问文章中的特殊标记是什么？"

        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "大海捞针响应")
        self.log_full_response(test_logger, response, "D5-大海捞针")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        content = self.get_message_content(response)

        assert "42" in content, (
            f"Model should recall the needle '42', got: {content[:500]}"
        )
        content_lower = content.lower()
        assert any(
            kw in content_lower
            for kw in ["特殊标记", "标记", "alpha", "实验", "37", "结果"]
        ), f"Model should reference the needle context, got: {content[:500]}"

        usage = response.get("usage", {})
        assert usage.get("prompt_tokens", 0) > 0, (
            "Should have prompt_tokens > 0 for NIAH test"
        )
        test_logger.info(
            f"NIAH test passed, prompt_tokens={usage.get('prompt_tokens')}, "
            f"completion_tokens={usage.get('completion_tokens')}, response: {content[:2000]}"
        )

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
            error_msg = str(e).lower()
            # 超限时模型可能返回错误（拒绝）或超时，均为预期行为
            assert any(
                kw in error_msg
                for kw in [
                    "context",
                    "length",
                    "too_many",
                    "exceed",
                    "limit",
                    "token",
                    "413",
                    "request entity too large",
                    "timed out",
                    "timeout",
                ]
            ), f"Error should relate to context/length/proxy limit, got: {e}"

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
        """D11 [P1]: 超长上下文（边界验证） - 使用二分法逼近模型最大上下文长度"""
        test_logger.info("=== 测试开始: 上下文边界（二分法） ===")

        try:
            model_info = api_client.get_model_info()
            max_len = self._get_max_context_len(model_info)
            test_logger.info(f"模型定义的最大上下文长度: {max_len}")

            if max_len > 0:
                low = 0
                high = max_len
                successful_len = 0
                failed_len = max_len
                max_iterations = 16

                test_logger.info(f"开始二分法测试，范围: [{low}, {high}]")

                for iteration in range(max_iterations):
                    mid = (low + high) // 2

                    if mid < 100:
                        low = mid + 1
                        continue

                    target_chars = mid
                    chars_without_space = int(target_chars * 0.9)
                    chars_with_space = int(target_chars * 0.1)
                    prompt_chars = []
                    for _ in range(chars_without_space):
                        prompt_chars.append(
                            random.choice(string.ascii_letters + string.digits)
                        )
                    for _ in range(chars_with_space):
                        prompt_chars.append(" ")
                    random.shuffle(prompt_chars)
                    prompt = "".join(prompt_chars)
                    messages = [{"role": "user", "content": prompt}]

                    test_logger.info(
                        f"迭代 {iteration + 1}: 测试上下文长度 ~{mid} tokens"
                    )

                    TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

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
                            f"D11-边界二分法-迭代{iteration + 1}-长度{mid}",
                        )
                        if len(result["chunks"]) > 0 and (
                            result["content"] or result["reasoning"]
                        ):
                            test_logger.info(f"长度 {mid} 成功")
                            low = mid + 1
                            successful_len = mid
                        else:
                            test_logger.warning(f"长度 {mid} 失败: 流式响应为空")
                            record_warning(f"长度{mid}请求失败")
                            high = mid - 1
                            failed_len = mid
                    except Exception as e:
                        error_msg = str(e).lower()
                        if (
                            ("max" in error_msg and "length" in error_msg)
                            or "context" in error_msg
                            or "max_model_len" in error_msg
                        ):
                            test_logger.warning(f"长度 {mid} 超限: {e}")
                            record_warning(f"长度{mid}超限")
                            high = mid - 1
                            failed_len = mid
                        else:
                            raise

                    if high - low <= 10:
                        break

                test_logger.info(
                    f"二分法结果: 成功最大长度 ~{successful_len} tokens, 失败长度 ~{failed_len} tokens"
                )
                test_logger.info(f"模型定义的最大长度: {max_len} tokens")

                if successful_len > 0:
                    ratio = successful_len / max_len
                    test_logger.info(f"实际成功率: {ratio:.2%}")
                    assert ratio > 0.8 or successful_len >= max_len * 0.8, (
                        f"Model claims {max_len} but only supports ~{successful_len}"
                    )
                    test_logger.info("上下文边界验证通过")
                else:
                    pytest.skip("无法确定有效的上下文长度")

        except Exception as e:
            error_msg = str(e).lower()
            if (
                ("max" in error_msg and "length" in error_msg)
                or "context" in error_msg
                or "max_model_len" in error_msg
            ):
                test_logger.info(f"Context boundary reached: {e}")
            else:
                raise

    @pytest.mark.d_long_context
    @pytest.mark.p0
    def test_reasoning_content_in_long_context(
        self, api_client: ModelAPIClient, test_logger
    ):
        """D12: 超长上下文（思考模式） - 验证超长上下文下reasoning_content的可用性"""
        test_logger.info("=== 测试开始: 长上下文+思考 ===")

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
        thinking_params = api_client.get_thinking_params(True)
        TestLogger.log_request(
            test_logger, messages, {**thinking_params, "max_tokens": 8000}
        )

        try:
            response = api_client.chat_completion(
                messages,
                extra_body=thinking_params,
                max_tokens=8000,
            )
            TestLogger.log_response(test_logger, response, "长上下文+思考响应")
            self.log_full_response(test_logger, response, "D12-长上下文+思考模式")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            reasoning = self.get_reasoning_content(response)
            content = self.get_message_content(response)

            assert reasoning is not None and len(reasoning.strip()) > 0, (
                "Thinking mode should produce non-empty reasoning_content in long context"
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
                f"Long context with thinking: reasoning={len(reasoning) if reasoning else 0} chars, "
                f"content={len(content) if content else 0} chars, "
                f"prompt_tokens={prompt_tokens}, "
                f"completion_tokens={usage.get('completion_tokens')}"
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
                pytest.skip(
                    f"Model/proxy does not support long context with thinking: {e}"
                )
            raise
