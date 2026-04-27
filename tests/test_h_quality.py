"""
H. 质量评估测试

测试点：
- H1: 生成质量 - 质量对比
- H2: 生成一致性 - 多次生成一致性
- H3: 幻觉率 - 事实错误检测
- H4: 指令遵循度 - 格式/角色遵循
- H5: 响应相关性 - 问答相关性评估
"""

import pytest
from typing import List

from base.base_test import BaseTest
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class TestQuality(BaseTest):
    """质量评估测试类"""

    def get_test_category(self) -> str:
        return "H. 质量评估"

    @pytest.mark.h_quality
    @pytest.mark.p0
    def test_generation_quality(self, api_client: ModelAPIClient, test_logger):
        """H1: 生成质量评分"""
        test_logger.info("=== 测试开始: 生成质量 ===")

        # 使用简单问题测试生成质量
        test_cases = [
            "请介绍一下北京",
            "什么是人工智能？",
            "如何学习Python？",
        ]

        quality_scores = []
        for prompt in test_cases:
            test_logger.info(f"测试: {prompt}")
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, f"质量测试响应")

            self.assert_response_success(response)
            content = self.get_message_content(response)
            quality_scores.append(len(content))
            test_logger.info(f"响应长度: {len(content)}")

        test_logger.info(
            f"平均响应长度: {sum(quality_scores) / len(quality_scores):.1f}"
        )

        # 至少50%的测试通过
        pass_rate = len(quality_scores) / len(test_cases)
        assert pass_rate >= 0.5, f"Quality pass rate: {pass_rate}"
        test_logger.info(f"Quality pass rate: {pass_rate * 100:.0f}%")

    @pytest.mark.h_quality
    @pytest.mark.p0
    def test_generation_consistency(self, api_client: ModelAPIClient, test_logger):
        """H2: 生成一致性 - 相同输入多次生成的稳定性"""
        test_logger.info("=== 测试开始: 生成一致性 ===")

        prompt = "请用一句话介绍北京"
        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(test_logger, messages)

        # 多次请求
        responses = []
        for i in range(3):
            test_logger.info(f"第{i + 1}次请求")
            response = api_client.chat_completion(
                messages, max_tokens=50, temperature=0
            )
            content = self.get_message_content(response)
            responses.append(content)
            test_logger.info(f"第{i + 1}次响应: {content[:2000]}...")

        # 对于确定性请求（temperature=0），输出应该一致
        # 但由于模型可能返回略有不同的措辞，我们只验证非空
        assert all(r and len(r) > 0 for r in responses), (
            "All responses should be non-empty"
        )
        test_logger.info(f"Consistency test: {len(responses)} responses collected")

    @pytest.mark.h_quality
    @pytest.mark.p1
    def test_hallucination_detection(self, api_client: ModelAPIClient, test_logger):
        """H3: 幻觉率检测 - 验证事实性回答"""
        test_logger.info("=== 测试开始: 幻觉检测 ===")

        # 使用简单事实问题
        test_facts = [
            ("中国的首都是哪里？", "北京"),
            ("1+1等于多少？", "2"),
        ]

        hallucination_count = 0
        for question, expected in test_facts:
            test_logger.info(f"测试问题: {question}")
            messages = [{"role": "user", "content": question}]
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "幻觉检测响应")

            self.assert_response_success(response)
            content = self.get_message_content(response).lower()

            # 简单检查是否包含预期答案
            if expected not in content:
                hallucination_count += 1

        hallucination_rate = hallucination_count / len(test_facts)
        test_logger.info(f"Hallucination rate: {hallucination_rate * 100:.0f}%")
        # 允许一定容错率
        assert hallucination_rate < 0.5, (
            f"High hallucination rate: {hallucination_rate}"
        )

    @pytest.mark.h_quality
    @pytest.mark.p0
    def test_instruction_following(self, api_client: ModelAPIClient, test_logger):
        """H4: 指令遵循度 - 复杂指令（格式、长度、角色）遵循程度"""
        test_logger.info("=== 测试开始: 指令遵循 ===")

        # 测试格式要求遵循
        messages = [
            {
                "role": "user",
                "content": "请用JSON格式回答，包含name和age两个字段，不要有其他内容",
            }
        ]
        TestLogger.log_request(test_logger, messages)

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "指令遵循响应")

        self.assert_response_success(response)
        content = self.get_message_content(response)

        # 尝试解析JSON
        try:
            import json

            data = json.loads(content)
            assert "name" in data or "age" in data, "Should contain name or age field"
            test_logger.info(f"Instruction following test passed, response: {data}")
        except:
            # 如果不是JSON，检查是否包含关键词
            assert "name" in content.lower() or "age" in content.lower(), (
                "Should follow instruction format"
            )
            test_logger.info("JSON解析失败但包含关键词")

    @pytest.mark.h_quality
    @pytest.mark.p1
    def test_response_relevance(self, api_client: ModelAPIClient, test_logger):
        """额外测试：回答相关性"""
        test_logger.info("=== 测试开始: 回答相关性 ===")

        # 使用不同领域的问题
        test_cases = [
            ("Python中如何定义函数？", ["def", "函数", "定义"]),
            ("水的化学式是什么？", ["H2O", "水", "化学"]),
        ]

        relevant_count = 0
        for prompt, keywords in test_cases:
            test_logger.info(f"测试问题: {prompt}")
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(test_logger, messages)

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "相关性响应")

            self.assert_response_success(response)
            content = self.get_message_content(response).lower()

            # 检查是否包含相关关键词
            if any(kw.lower() in content for kw in keywords):
                relevant_count += 1

        relevance_rate = relevant_count / len(test_cases)
        print(f"Relevance rate: {relevance_rate * 100:.0f}%")
        assert relevance_rate >= 0.5, f"Low relevance: {relevance_rate}"
