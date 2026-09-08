"""
H. Chat Completions API 质量评估与回答相关性测试

测试点：
- H1: 生成质量 - 质量对比 [P0]
- H2: 生成一致性 - 多次生成一致性 [P1]
- H3: 幻觉率 - 事实错误检测 [P1]
- H4: 指令遵循度 - 格式/角色遵循 [P0]
- H5: 响应相关性 - 问答相关性评估 [P0]
- H6: 编程领域相关性 - 验证编程问题的回答相关性 [P0]
- H7: 数学领域相关性 - 验证数学问题的回答相关性 [P0]
- H8: 科学领域相关性 - 验证科学问题的回答相关性 [P0]
- H9: 乱码检测 - 检测输出是否为乱码或无效字符 [P0]
- H10: 无意义回答检测 - 检测回答是否与问题完全不相关 [P1]
- H11: 跨领域相关性 - 天气/烹饪等领域相关性验证 [P1]
- H12: 上下文一致性 - 多轮对话中验证上下文一致性 [P0]
- H13: 回答具体性 - 确保回答不是泛泛而谈 [P2]
"""

import json
import pytest
from typing import List, Dict, Any

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger
from base.relevance_checker import ResponseRelevanceChecker


class TestQualityChatCompletions(BaseTest, StreamingTestMixin):
    """Chat Completions API 质量评估与回答相关性测试类"""

    # 通过率/阈值集中管理
    MIN_QUALITY_LENGTH = 20
    MIN_PASS_RATE = 0.5
    MAX_HALLUCINATION_RATE = 0.2
    MIN_CONSISTENCY_SIMILARITY = 0.3
    MAX_NONSENSICAL_RATE = 0.4
    MAX_GARBLED_RATE = 0.2
    DOMAIN_RELEVANCE_THRESHOLD = 0.1

    def get_test_category(self) -> str:
        return "H. Chat Completions API 质量评估与回答相关性"

    @staticmethod
    def _trunc(text: str, n: int = 2000) -> str:
        """截断文本用于日志，超长时附加省略号"""
        return text[:n] + ("..." if len(text) > n else "")

    def _chat_and_get_content(
        self,
        api_client: ModelAPIClient,
        test_logger,
        prompt: str,
        label: str,
        **kwargs,
    ) -> str:
        """发起 chat_completion 请求并返回正式回复内容

        封装 请求/响应日志/断言/取正文 的通用流程。思考模型在 max_tokens
        被 reasoning 耗尽导致 content 为空时，通过 _get_formal_content 回退
        到 content+reasoning，避免误判。不适用于需严格区分正式回复与思考
        内容的用例（JSON 指令遵循、多轮上下文拼接、回答具体性跳过逻辑）。
        """
        messages = [{"role": "user", "content": prompt}]
        params = {"max_tokens": 2000, **kwargs}
        TestLogger.log_request(test_logger, messages, params)
        response = api_client.chat_completion(messages, **params)
        TestLogger.log_response(test_logger, response, "响应")
        self.log_full_response(test_logger, response, label)
        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        return self._get_formal_content(response, test_logger, label)

    def _log_relevance_result(
        self, test_logger, question: str, answer: str, result: Dict[str, Any]
    ):
        """记录相关性检查结果"""
        test_logger.info(f"问题: {question}")
        test_logger.info(f"回答: {self._trunc(answer)}")
        test_logger.info(
            f"相关性得分: {result['score']:.2f}, 相关: {result['relevant']}"
        )
        test_logger.info(f"匹配关键词: {result['matched_keywords']}")
        if result.get("negative_keywords"):
            test_logger.warning(f"发现不相关关键词: {result['negative_keywords']}")
        test_logger.info(f"原因: {result['reason']}")

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    def test_generation_quality(self, api_client: ModelAPIClient, test_logger):
        """H1: 生成质量评分"""
        test_logger.info("=== 测试开始: 生成质量 ===")

        test_cases = [
            "请介绍一下北京",
            "什么是人工智能？",
            "如何学习Python？",
        ]

        quality_scores = []
        for idx, prompt in enumerate(test_cases):
            test_logger.info(f"测试: {prompt}")
            content = self._chat_and_get_content(
                api_client, test_logger, prompt, f"H1-生成质量-{idx + 1}"
            )

            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)
            passed = len(content.strip()) >= self.MIN_QUALITY_LENGTH and not is_spam
            if is_spam:
                test_logger.warning(f"检测到垃圾内容: {spam_reason}")
            quality_scores.append(passed)
            test_logger.info(
                f"响应长度: {len(content)}, 通过: {passed} "
                f"(最低要求: {self.MIN_QUALITY_LENGTH})"
            )

        pass_rate = sum(quality_scores) / len(test_cases)
        test_logger.info(
            f"质量通过率: {pass_rate * 100:.0f}%, "
            f"通过: {sum(quality_scores)}/{len(test_cases)}"
        )
        assert pass_rate >= self.MIN_PASS_RATE, (
            f"Quality pass rate too low: {pass_rate * 100:.0f}%"
        )

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p1
    def test_generation_consistency(self, api_client: ModelAPIClient, test_logger):
        """H2 [P1]: 生成一致性 - 相同输入多次生成的稳定性"""
        test_logger.info("=== 测试开始: 生成一致性 ===")

        prompt = "请用一句话介绍长江"
        responses = []
        for i in range(3):
            test_logger.info(f"第{i + 1}次请求")
            content = self._chat_and_get_content(
                api_client, test_logger, prompt, f"H2-生成一致性-第{i + 1}次",
                temperature=0,
            )
            responses.append(content)
            test_logger.info(f"第{i + 1}次响应: {self._trunc(content)}")

        assert all(r and len(r.strip()) > 0 for r in responses), (
            "All responses should be non-empty"
        )

        all_have_content = all(len(r.strip()) >= 10 for r in responses)
        assert all_have_content, (
            "All responses should have at least 10 chars for consistency check"
        )

        common_chars = set(responses[0]) & set(responses[1]) & set(responses[2])
        similarity = len(common_chars) / max(
            len(set(responses[0]) | set(responses[1]) | set(responses[2])), 1
        )
        test_logger.info(
            f"Consistency test: {len(responses)} responses collected, "
            f"common chars: {len(common_chars)}, "
            f"char-level similarity: {similarity:.2%}, "
            f"lengths: {[len(r) for r in responses]}"
        )
        assert similarity > self.MIN_CONSISTENCY_SIMILARITY, (
            f"Responses should be consistent at temperature=0, "
            f"char-level similarity too low: {similarity:.2%}"
        )

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p1
    def test_hallucination_detection(
        self, api_client: ModelAPIClient, test_logger, record_warning
    ):
        """H3: 幻觉率检测 - 验证事实性回答"""
        test_logger.info("=== 测试开始: 幻觉检测 ===")

        test_facts = [
            ("中国的首都是哪里？", "北京"),
            ("1+1等于多少？", "2"),
        ]

        hallucination_count = 0
        for idx, (question, expected) in enumerate(test_facts):
            test_logger.info(f"测试问题: {question}")
            content = self._chat_and_get_content(
                api_client, test_logger, question, f"H3-幻觉检测-{idx + 1}"
            )

            is_nonsensical, nonsensical_reason = (
                ResponseRelevanceChecker.is_nonsensical_response(question, content)
            )
            expected_found = expected.lower() in content.lower()
            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)

            if not expected_found:
                hallucination_count += 1
                if is_nonsensical:
                    test_logger.warning(
                        f"幻觉: 回答与问题不相关({nonsensical_reason}), "
                        f"期望包含'{expected}', 实际: {content[:500]}"
                    )
                    record_warning(f"幻觉: 回答与问题不相关({nonsensical_reason})")
                else:
                    test_logger.warning(
                        f"幻觉: 期望包含'{expected}', 实际: {content[:500]}"
                    )
                    record_warning(f"幻觉: 期望包含'{expected}'")
            elif is_spam:
                hallucination_count += 1
                test_logger.warning(
                    f"幻觉: 检测到垃圾内容({spam_reason}), 实际: {content[:500]}"
                )
                record_warning(f"幻觉: 检测到垃圾内容({spam_reason})")

        hallucination_rate = hallucination_count / len(test_facts)
        test_logger.info(f"Hallucination rate: {hallucination_rate * 100:.0f}%")
        assert hallucination_rate < self.MAX_HALLUCINATION_RATE, (
            f"Hallucination rate too high: {hallucination_rate * 100:.0f}%"
        )

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    def test_instruction_following(self, api_client: ModelAPIClient, test_logger):
        """H4: 指令遵循度 - 复杂指令（格式、长度、角色）遵循程度"""
        test_logger.info("=== 测试开始: 指令遵循 ===")

        messages = [
            {
                "role": "user",
                "content": "请用JSON格式回答，包含name和age两个字段，不要有其他内容",
            }
        ]
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

        response = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, response, "指令遵循响应")
        self.log_full_response(test_logger, response, "H4-指令遵循")

        self.assert_response_success(response)
        self.assert_content_not_empty(response)
        content = self.get_message_content(
            response, strip_reasoning=True, strip_thinking=True
        )

        try:
            data = json.loads(content)
            assert "name" in data and "age" in data, (
                f"JSON should contain both 'name' and 'age' fields, got: {list(data.keys())}"
            )
            test_logger.info(f"Instruction following test passed, response: {data}")
        except (json.JSONDecodeError, ValueError):
            content_lower = content.lower()
            assert "name" in content_lower and "age" in content_lower, (
                f"Should follow instruction format with both 'name' and 'age', got: {content[:500]}"
            )
            test_logger.info("JSON解析失败但包含关键词")

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    def test_response_relevance(self, api_client: ModelAPIClient, test_logger):
        """H5: 回答相关性"""
        test_logger.info("=== 测试开始: 回答相关性 ===")

        test_cases = [
            ("什么是货币通货膨胀？", ["货币", "通胀", "价格", "上涨", "购买力"]),
            ("如何提高英语口语水平？", ["英语", "口语", "练习", "发音", "语言"]),
        ]

        relevant_count = 0
        for idx, (prompt, keywords) in enumerate(test_cases):
            test_logger.info(f"测试问题: {prompt}")
            content = self._chat_and_get_content(
                api_client, test_logger, prompt, f"H5-回答相关性-{idx + 1}"
            )

            is_nonsensical, nonsensical_reason = (
                ResponseRelevanceChecker.is_nonsensical_response(prompt, content)
            )

            quality = ResponseRelevanceChecker.check_response_quality(
                prompt, content, keywords
            )
            if (
                not is_nonsensical
                and any(kw.lower() in content.lower() for kw in keywords)
                and quality["quality_passed"]
            ):
                relevant_count += 1
            else:
                if is_nonsensical:
                    test_logger.warning(f"无意义回答: {nonsensical_reason}")
                if quality["issues"]:
                    test_logger.warning(f"质量问题: {quality['issues']}")
                test_logger.warning(
                    f"回答不相关: 期望关键词{keywords}, 内容: {content[:500]}"
                )

        relevance_rate = relevant_count / len(test_cases)
        test_logger.info(f"Relevance rate: {relevance_rate * 100:.0f}%")
        assert relevance_rate >= self.MIN_PASS_RATE, (
            f"Low relevance: {relevance_rate * 100:.0f}%"
        )

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_response_relevance_programming(
        self, api_client: ModelAPIClient, test_logger
    ):
        """H6: 编程领域回答相关性验证"""
        test_logger.info("=== 测试开始: 编程领域回答相关性 ===")

        test_cases = [
            {
                "question": "Python中如何定义一个函数？",
                "domain": "programming",
                "expected_keywords": ["def", "函数", "function", "return"],
            },
            {
                "question": "请解释什么是递归算法？",
                "domain": "programming",
                "expected_keywords": ["递归", "recursion", "函数", "调用"],
            },
            {
                "question": "什么是面向对象编程？",
                "domain": "programming",
                "expected_keywords": ["类", "class", "对象", "object", "封装", "继承"],
            },
        ]

        passed_count = 0
        for idx, case in enumerate(test_cases):
            test_logger.info(f"\n--- 测试: {case['question']} ---")
            content = self._chat_and_get_content(
                api_client, test_logger, case["question"], f"H6-编程领域-{idx + 1}"
            )
            test_logger.info(f"回答: {self._trunc(content)}")

            is_garbled, garbled_type = ResponseRelevanceChecker.contains_garbled_text(
                content
            )
            assert not is_garbled, f"检测到乱码: {garbled_type}, 内容: {content[:2000]}"

            result = ResponseRelevanceChecker.check_domain_relevance(
                case["question"], content, case["domain"]
            )
            self._log_relevance_result(test_logger, case["question"], content, result)

            if result["relevant"] and result["score"] >= self.DOMAIN_RELEVANCE_THRESHOLD:
                quality = ResponseRelevanceChecker.check_response_quality(
                    case["question"], content, case["expected_keywords"]
                )
                if quality["quality_passed"]:
                    passed_count += 1
                    test_logger.info("✓ 相关性验证通过")
                else:
                    test_logger.warning(f"✗ 质量问题: {quality['issues']}")
            else:
                test_logger.warning(f"✗ 相关性验证失败: {result['reason']}")

        relevance_rate = passed_count / len(test_cases)
        test_logger.info(f"\n编程领域相关性通过率: {relevance_rate * 100:.0f}%")
        assert relevance_rate >= self.MIN_PASS_RATE, (
            f"编程领域相关性过低: {relevance_rate * 100:.0f}%"
        )

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_response_relevance_math(self, api_client: ModelAPIClient, test_logger):
        """H7: 数学领域回答相关性验证"""
        test_logger.info("=== 测试开始: 数学领域回答相关性 ===")

        test_cases = [
            {
                "question": "请计算 123 + 456 等于多少？",
                "domain": "math",
                "expected_keywords": ["579", "等于", "计算"],
            },
            {
                "question": "什么是勾股定理？",
                "domain": "math",
                "expected_keywords": ["直角", "三角形", "平方", "a²", "b²", "c²"],
            },
            {
                "question": "解释一下什么是导数？",
                "domain": "math",
                "expected_keywords": ["导数", "微分", "极限", "函数", "变化率"],
            },
        ]

        passed_count = 0
        for idx, case in enumerate(test_cases):
            test_logger.info(f"\n--- 测试: {case['question']} ---")
            content = self._chat_and_get_content(
                api_client, test_logger, case["question"], f"H7-数学领域-{idx + 1}"
            )
            test_logger.info(f"回答: {self._trunc(content)}")

            is_garbled, garbled_type = ResponseRelevanceChecker.contains_garbled_text(
                content
            )
            assert not is_garbled, f"检测到乱码: {garbled_type}"

            result = ResponseRelevanceChecker.check_domain_relevance(
                case["question"], content, case["domain"]
            )
            self._log_relevance_result(test_logger, case["question"], content, result)

            quality = ResponseRelevanceChecker.check_response_quality(
                case["question"], content, case["expected_keywords"]
            )
            if (
                result["relevant"]
                or any(kw in content for kw in case["expected_keywords"])
            ) and quality["quality_passed"]:
                passed_count += 1
                test_logger.info("✓ 相关性验证通过")
            else:
                if quality["issues"]:
                    test_logger.warning(f"质量问题: {quality['issues']}")
                test_logger.warning(f"✗ 相关性验证失败")

        relevance_rate = passed_count / len(test_cases)
        test_logger.info(f"\n数学领域相关性通过率: {relevance_rate * 100:.0f}%")
        assert relevance_rate >= self.MIN_PASS_RATE, (
            f"数学领域相关性过低: {relevance_rate * 100:.0f}%"
        )

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    def test_response_relevance_science(self, api_client: ModelAPIClient, test_logger):
        """H8 [P0]: 科学领域回答相关性验证"""
        test_logger.info("=== 测试开始: 科学领域回答相关性 ===")

        test_cases = [
            {
                "question": "水的化学式是什么？",
                "domain": "science",
                "expected_keywords": ["H2O", "氢", "氧"],
            },
            {
                "question": "什么是光合作用？",
                "domain": "science",
                "expected_keywords": ["光", "叶绿体", "二氧化碳", "氧气"],
            },
            {
                "question": "解释牛顿第一定律",
                "domain": "science",
                "expected_keywords": ["惯性", "力", "运动", "定律"],
            },
        ]

        passed_count = 0
        for idx, case in enumerate(test_cases):
            test_logger.info(f"\n--- 测试: {case['question']} ---")
            content = self._chat_and_get_content(
                api_client, test_logger, case["question"], f"H8-科学领域-{idx + 1}"
            )
            test_logger.info(f"回答内容: {content}")

            is_garbled, _ = ResponseRelevanceChecker.contains_garbled_text(content)
            assert not is_garbled, f"检测到乱码"

            result = ResponseRelevanceChecker.check_domain_relevance(
                case["question"], content, case["domain"]
            )
            self._log_relevance_result(test_logger, case["question"], content, result)

            quality = ResponseRelevanceChecker.check_response_quality(
                case["question"], content, case["expected_keywords"]
            )
            if (
                result["relevant"]
                or any(kw in content for kw in case["expected_keywords"])
            ) and quality["quality_passed"]:
                passed_count += 1
                test_logger.info("✓ 相关性验证通过")
            else:
                if quality["issues"]:
                    test_logger.warning(f"质量问题: {quality['issues']}")
                test_logger.warning("✗ 相关性验证失败")

        relevance_rate = passed_count / len(test_cases)
        test_logger.info(f"科学领域相关性通过率: {relevance_rate * 100:.0f}%")
        assert relevance_rate >= self.MIN_PASS_RATE, f"科学领域相关性过低"

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_garbled_text_detection(self, api_client: ModelAPIClient, test_logger):
        """H9: 乱码检测 - 验证输出不是乱码"""
        test_logger.info("=== 测试开始: 乱码检测 ===")

        test_prompts = [
            "请介绍一下区块链技术的基本原理",
            "什么是机器学习？",
            "解释一下什么是深度学习",
            "请用中文介绍中国的传统节日春节",
            "请用中文回答：What is an API?",
        ]

        garbled_count = 0
        for idx, prompt in enumerate(test_prompts):
            test_logger.info(f"\n测试: {prompt}")
            content = self._chat_and_get_content(
                api_client, test_logger, prompt, f"H9-乱码检测-{idx + 1}"
            )
            test_logger.info(f"回答长度: {len(content)}")

            is_garbled, garbled_type = ResponseRelevanceChecker.contains_garbled_text(
                content
            )
            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)

            if is_garbled:
                garbled_count += 1
                test_logger.error(f"✗ 检测到乱码: {garbled_type}")
                test_logger.error(f"乱码内容: {self._trunc(content)}")
            elif is_spam:
                # 垃圾内容（如关键词堆砌、SEO式排版）不等同于乱码。
                # 模型可能使用markdown格式化（列表、标题）导致短行较多，
                # 或在领域回答中反复提及主题词，这些是正常行为，不应计为乱码。
                test_logger.warning(
                    f"⚠ 检测到可能的垃圾内容（不计入乱码率）: {spam_reason}"
                )
            else:
                test_logger.info(f"✓ 内容正常，无乱码")

        garbled_rate = garbled_count / len(test_prompts)
        test_logger.info(f"\n乱码率: {garbled_rate * 100:.0f}%")
        assert garbled_rate < self.MAX_GARBLED_RATE, (
            f"乱码率过高: {garbled_rate * 100:.0f}%"
        )

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p1
    def test_nonsensical_response_detection(
        self, api_client: ModelAPIClient, test_logger
    ):
        """H10: 无意义回答检测 - 验证回答不是完全无关的"""
        test_logger.info("=== 测试开始: 无意义回答检测 ===")

        test_cases = [
            "如何写一封正式的英文邮件？请给出示例",
            "珠穆朗玛峰的海拔高度大约是多少米？",
            "请介绍一下丝绸之路的历史",
            "什么是大数据技术？请详细解释",
            "中国有多少个省级行政区？",
        ]

        nonsensical_count = 0
        for idx, question in enumerate(test_cases):
            test_logger.info(f"\n问题: {question}")
            content = self._chat_and_get_content(
                api_client, test_logger, question, f"H10-无意义检测-{idx + 1}"
            )
            test_logger.info(f"回答: {self._trunc(content)}")

            is_nonsensical, reason = ResponseRelevanceChecker.is_nonsensical_response(
                question, content
            )

            if is_nonsensical:
                nonsensical_count += 1
                test_logger.warning(f"✗ 检测到无意义回答: {reason}")
            else:
                test_logger.info(f"✓ 回答有意义")

        nonsensical_rate = nonsensical_count / len(test_cases)
        test_logger.info(f"\n无意义回答率: {nonsensical_rate * 100:.0f}%")
        assert nonsensical_rate <= self.MAX_NONSENSICAL_RATE, (
            f"无意义回答率过高: {nonsensical_rate * 100:.0f}%"
        )

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p1
    @pytest.mark.parametrize(
        "domain,questions",
        [
            (
                "weather",
                [
                    "上海今天天气怎么样？",
                    "明天会下雨吗？",
                ],
            ),
            (
                "cooking",
                [
                    "红烧肉怎么做？",
                    "如何炒一盘好吃的番茄炒蛋？",
                ],
            ),
        ],
    )
    def test_cross_domain_relevance(
        self, api_client: ModelAPIClient, test_logger, domain: str, questions: List[str]
    ):
        """H11: 跨领域相关性测试"""
        test_logger.info(f"=== 测试开始: {domain}领域回答相关性 ===")

        passed_count = 0
        for idx, question in enumerate(questions):
            test_logger.info(f"\n问题: {question}")
            content = self._chat_and_get_content(
                api_client, test_logger, question, f"H11-{domain}领域-{idx + 1}"
            )
            test_logger.info(f"回答: {self._trunc(content)}")

            is_garbled, _ = ResponseRelevanceChecker.contains_garbled_text(content)
            assert not is_garbled, f"检测到乱码"
            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)
            assert not is_spam, f"检测到垃圾内容: {spam_reason}"

            result = ResponseRelevanceChecker.check_domain_relevance(
                question, content, domain
            )
            test_logger.info(
                f"相关性得分: {result['score']:.2f}, "
                f"匹配关键词: {result['matched_keywords']}"
            )

            if result["relevant"]:
                passed_count += 1

        rate = passed_count / len(questions)
        assert rate >= self.MIN_PASS_RATE, f"{domain}领域相关性过低: {rate * 100:.0f}%"

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    def test_conversation_context_consistency(
        self, api_client: ModelAPIClient, test_logger
    ):
        """H12: 多轮对话上下文一致性验证"""
        test_logger.info("=== 测试开始: 多轮对话上下文一致性 ===")

        messages = []

        q1 = "我喜欢吃苹果"
        test_logger.info(f"第1轮: {q1}")
        messages.append({"role": "user", "content": q1})
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})
        r1 = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, r1, "响应")
        self.log_full_response(test_logger, r1, "H12-上下文一致性-第1轮")
        self.assert_response_success(r1)
        self.assert_content_not_empty(r1)
        c1 = self.get_message_content(r1, strip_reasoning=True, strip_thinking=True)
        messages.append({"role": "assistant", "content": c1})
        test_logger.info(f"第1轮回答: {self._trunc(c1)}")

        q2 = "我刚才说我喜欢吃什么水果？"
        test_logger.info(f"第2轮: {q2}")
        messages.append({"role": "user", "content": q2})
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})
        r2 = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, r2, "响应")
        self.log_full_response(test_logger, r2, "H12-上下文一致性-第2轮")
        self.assert_response_success(r2)
        self.assert_content_not_empty(r2)
        c2 = self.get_message_content(r2, strip_reasoning=True, strip_thinking=True)
        test_logger.info(f"第2轮回答: {self._trunc(c2)}")

        assert "苹果" in c2 or "apple" in c2.lower(), (
            f"模型应该记住上下文，但回答为: {c2[:2000]}"
        )

        q3 = "除了苹果，我还喜欢香蕉，请记住这个"
        test_logger.info(f"第3轮: {q3}")
        messages.append({"role": "user", "content": q3})
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})
        r3 = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, r3, "响应")
        self.log_full_response(test_logger, r3, "H12-上下文一致性-第3轮")
        self.assert_response_success(r3)
        self.assert_content_not_empty(r3)
        c3 = self.get_message_content(r3, strip_reasoning=True, strip_thinking=True)
        messages.append({"role": "assistant", "content": c3})
        test_logger.info(f"第3轮回答: {self._trunc(c3)}")

        q4 = "我刚才说了我喜欢哪两种水果？"
        test_logger.info(f"第4轮: {q4}")
        messages.append({"role": "user", "content": q4})
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})
        r4 = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, r4, "响应")
        self.log_full_response(test_logger, r4, "H12-上下文一致性-第4轮")
        self.assert_response_success(r4)
        self.assert_content_not_empty(r4)
        c4 = self.get_message_content(r4, strip_reasoning=True, strip_thinking=True)
        test_logger.info(f"第4轮回答: {self._trunc(c4)}")

        has_apple = "苹果" in c4 or "apple" in c4.lower()
        has_banana = "香蕉" in c4 or "banana" in c4.lower()

        assert has_apple and has_banana, f"模型应该记住两种水果，但回答为: {c4[:2000]}"

        is_garbled, _ = ResponseRelevanceChecker.contains_garbled_text(c4)
        assert not is_garbled, "检测到乱码"

        is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(c4)
        assert not is_spam, f"检测到垃圾内容: {spam_reason}"

        test_logger.info("✓ 多轮对话上下文一致性验证通过")

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p2
    def test_response_specificity_check(self, api_client: ModelAPIClient, test_logger):
        """H13: 回答具体性检查 - 确保回答不是泛泛而谈"""
        test_logger.info("=== 测试开始: 回答具体性检查 ===")

        test_cases = [
            {
                "question": "Python的list和tuple有什么区别？",
                "min_length": 50,
                "expected_details": [
                    "可变",
                    "不可变",
                    "mutable",
                    "immutable",
                    "列表",
                    "元组",
                ],
            },
            {
                "question": "如何用Python读取JSON文件？",
                "min_length": 80,
                "expected_details": ["json", "load", "open", "import", "读取"],
            },
            {
                "question": "什么是RESTful API？",
                "min_length": 100,
                "expected_details": ["HTTP", "API", "REST", "资源", "状态"],
            },
        ]

        passed_count = 0
        total_evaluated = 0
        for idx, case in enumerate(test_cases):
            test_logger.info(f"\n--- 测试: {case['question']} ---")
            messages = [{"role": "user", "content": case["question"]}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "API 响应")
            self.log_full_response(test_logger, response, f"H13-回答具体性-{idx + 1}")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(
                response, strip_reasoning=True, strip_thinking=True
            )
            test_logger.info(f"回答内容: {self._trunc(content, 500)}")

            if not content or not content.strip():
                test_logger.warning(
                    f"跳过 {case['question']}...: 模型未生成正式回复"
                    f"（可能 max_tokens 不足导致仅输出思考内容）"
                )
                continue

            total_evaluated += 1

            is_garbled, _ = ResponseRelevanceChecker.contains_garbled_text(content)
            assert not is_garbled, f"检测到乱码"

            length_ok = len(content) >= case["min_length"]
            details_ok = any(
                detail.lower() in content.lower() for detail in case["expected_details"]
            )
            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)

            if length_ok and details_ok and not is_spam:
                passed_count += 1
                test_logger.info(f"✓ {case['question']}... - 回答具体")
            else:
                if is_spam:
                    test_logger.warning(f"检测到垃圾内容: {spam_reason}")
                test_logger.warning(f"✗ {case['question']}... - 回答不够具体")
                test_logger.warning(
                    f"  长度: {len(content)}/{case['min_length']}, 详细程度: {details_ok}"
                )

        if total_evaluated == 0:
            pytest.skip("模型未生成任何正式回复，无法评估回答具体性")
        specificity_rate = passed_count / total_evaluated
        assert specificity_rate >= self.MIN_PASS_RATE, (
            f"回答具体性过低: {specificity_rate * 100:.0f}%"
        )
