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

import re
import json
import pytest
from typing import List, Dict, Any, Set, Tuple, Optional

from base.base_test import BaseTest, StreamingTestMixin
from base.api_client import ModelAPIClient
from base.logger import TestLogger


class ResponseRelevanceChecker:
    """回答相关性检查器"""

    DOMAIN_KEYWORDS = {
        "programming": {
            "keywords": [
                "python",
                "java",
                "javascript",
                "code",
                "function",
                "class",
                "def",
                "编程",
                "代码",
                "函数",
                "变量",
                "算法",
                "数据结构",
                "loop",
                "if",
                "return",
                "import",
                "module",
                "api",
                "sdk",
                "compiler",
                "debug",
            ],
            "negative_keywords": [
                "天气",
                "weather",
                "水果",
                "fruit",
                "电影",
                "movie",
                "音乐",
                "music",
            ],
        },
        "math": {
            "keywords": [
                "计算",
                "数学",
                "math",
                "equation",
                "公式",
                "加",
                "减",
                "乘",
                "除",
                "等于",
                "结果",
                "答案",
                "number",
                "数字",
                "sum",
                "difference",
                "积分",
                "微分",
                "导数",
                "函数",
                "equation",
                "solve",
                "解",
            ],
            "negative_keywords": ["天气", "weather", "旅游", "travel"],
        },
        "science": {
            "keywords": [
                "science",
                "物理",
                "化学",
                "生物",
                "实验",
                "原子",
                "分子",
                "元素",
                "反应",
                "力",
                "能量",
                "光",
                "电",
                "磁场",
                "gravity",
                "electron",
                "proton",
                "chemical",
                "reaction",
                "cell",
                "DNA",
                "RNA",
            ],
            "negative_keywords": ["烹饪", "cooking", "娱乐", "entertainment"],
        },
        "general_knowledge": {
            "keywords": [
                "是什么",
                "什么是",
                "介绍",
                "解释",
                "历史",
                "文化",
                "国家",
                "城市",
                "what is",
                "explain",
                "introduce",
                "history",
                "culture",
                "country",
                "city",
            ],
            "negative_keywords": [],
        },
        "weather": {
            "keywords": [
                "天气",
                "weather",
                "温度",
                "temperature",
                "雨",
                "雪",
                "晴",
                "多云",
                "humidity",
                "湿度",
                "预报",
                "forecast",
                "气候",
                "climate",
            ],
            "negative_keywords": ["python", "代码", "算法"],
        },
        "cooking": {
            "keywords": [
                "烹饪",
                "做饭",
                "菜谱",
                "食材",
                "调料",
                "cook",
                "recipe",
                "food",
                "dishes",
                "ingredient",
                "spice",
                "味道",
                "taste",
                "厨房",
                "kitchen",
            ],
            "negative_keywords": ["python", "算法", "物理"],
        },
    }

    @staticmethod
    def contains_garbled_text(text: str) -> Tuple[bool, str]:
        """
        检测乱码
        返回: (是否乱码, 乱码类型描述)
        """
        if not text or len(text.strip()) == 0:
            return True, "empty_text"

        text_clean = text.strip()

        math_expression_pattern = r"^[\d\s\+\-\*/=<>±×÷≤≥≠≈∞√∫∑∏∂∇²³ⁿπ\u03b1-\u03c9\u0391-\u03a9\(\)\[\]\.,:;!?]+$"
        if re.match(math_expression_pattern, text_clean):
            return False, ""

        garbled_patterns = [
            (r"^[�]+$", "replacement_char_only"),
            (r"^[\u0000-\u001F\u007F-\u009F]+$", "control_chars_only"),
            (
                r"^[^a-zA-Z\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\uac00-\ud7af\u0400-\u04ff]+$",
                "non_text_chars",
            ),
            (r"^[\d\W]+$", "only_digits_and_symbols"),
        ]

        for pattern, pattern_name in garbled_patterns:
            if re.match(pattern, text_clean):
                return True, pattern_name

        if (
            len(text_clean) < 5
            and not re.search(r"[\u4e00-\u9fff]", text_clean)
            and not re.search(r"[a-zA-Z]{2,}", text_clean)
        ):
            return True, "too_short_and_no_language_chars"

        control_char_ratio = sum(
            1 for c in text if ord(c) < 32 and c not in "\n\r\t"
        ) / max(len(text), 1)
        if control_char_ratio > 0.1:
            return True, "too_many_control_chars"

        return False, ""

    @staticmethod
    def detect_spam_content(text: str) -> Tuple[bool, str]:
        """检测SEO垃圾内容、关键词堆砌和重复内容

        返回: (是否垃圾内容, 垃圾类型描述)
        """
        if not text or len(text.strip()) == 0:
            return True, "empty_text"

        text_clean = text.strip()
        from collections import Counter

        # 1. 检测重复句子（同一句子出现3次以上）
        sentences = re.split(r"[。！？\n.!?]", text_clean)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

        if sentences:
            sentence_counts = Counter(sentences)
            for sent, count in sentence_counts.items():
                if count >= 3:
                    return True, f"repeated_sentence: '{sent[:30]}...' x{count}"

        # 2. 检测关键词堆砌（同一中文词组出现频率过高）
        for ngram_len in range(2, 7):
            cn_words = re.findall(
                rf"[\u4e00-\u9fff]{{{ngram_len},{ngram_len}}}", text_clean
            )
            if cn_words:
                word_counts = Counter(cn_words)
                total_words = len(cn_words)
                for word, count in word_counts.items():
                    if count > 5 and count / total_words > 0.05:
                        return (
                            True,
                            f"keyword_stuffing: '{word}' x{count} ({count / total_words:.0%})",
                        )

        # 3. 检测SEO式内容（大量短行包含相似关键词）
        lines = [l.strip() for l in text_clean.split("\n") if l.strip()]
        if len(lines) > 15:
            short_lines = [l for l in lines if len(l) < 30]
            if len(short_lines) > len(lines) * 0.6:
                return (
                    True,
                    f"seo_style_content: {len(short_lines)}/{len(lines)} short lines",
                )

        # 4. 检测重复模式（高相似度句子过多）
        if len(sentences) > 10:
            similar_count = 0
            for i in range(len(sentences)):
                for j in range(i + 1, min(i + 10, len(sentences))):
                    set_i = set(sentences[i])
                    set_j = set(sentences[j])
                    if set_i and set_j:
                        overlap = len(set_i & set_j) / max(len(set_i | set_j), 1)
                        if overlap > 0.7 and len(sentences[i]) > 10:
                            similar_count += 1
                if similar_count > 5:
                    break

            if similar_count > 5:
                return (
                    True,
                    f"repetitive_pattern: {similar_count} similar sentence pairs",
                )

        return False, ""

    @staticmethod
    def check_sentence_relevance(
        answer: str, keywords: List[str], min_ratio: float = 0.15
    ) -> Dict[str, Any]:
        """检查句子级别的相关性 - 有多少比例的句子包含相关关键词"""
        sentences = re.split(r"[。！？\n.!?]", answer)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 3]

        if not sentences:
            return {
                "relevant": False,
                "ratio": 0.0,
                "total_sentences": 0,
                "relevant_sentences": 0,
                "reason": "no_valid_sentences",
            }

        relevant_sentences = 0
        for s in sentences:
            if any(kw.lower() in s.lower() for kw in keywords):
                relevant_sentences += 1

        ratio = relevant_sentences / len(sentences)

        return {
            "relevant": ratio >= min_ratio,
            "ratio": ratio,
            "total_sentences": len(sentences),
            "relevant_sentences": relevant_sentences,
            "reason": f"{relevant_sentences}/{len(sentences)} sentences ({ratio:.0%})",
        }

    @staticmethod
    def check_response_quality(
        question: str, answer: str, expected_keywords: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """综合质量检查 - 检查垃圾内容、相关性和长度适当性"""
        issues = []

        # 1. 垃圾内容检测
        is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(answer)
        if is_spam:
            issues.append(f"spam: {spam_reason}")

        # 2. 乱码检测
        is_garbled, garbled_type = ResponseRelevanceChecker.contains_garbled_text(
            answer
        )
        if is_garbled:
            issues.append(f"garbled: {garbled_type}")

        # 3. 句子级相关性检查
        sentence_relevance = None
        if expected_keywords:
            sentence_relevance = ResponseRelevanceChecker.check_sentence_relevance(
                answer, expected_keywords, min_ratio=0.15
            )
            if not sentence_relevance["relevant"]:
                issues.append(f"low_sentence_relevance: {sentence_relevance['reason']}")

        # 4. 响应长度适当性检查
        # 对于简短问题，响应不应过长且答案不在前部
        if len(question) < 30 and len(answer) > 3000 and expected_keywords:
            first_portion = answer[:500]
            has_early_answer = any(
                kw.lower() in first_portion.lower() for kw in expected_keywords
            )
            if not has_early_answer:
                issues.append("answer_not_in_early_portion")

        return {
            "quality_passed": len(issues) == 0,
            "issues": issues,
            "is_spam": is_spam,
            "spam_reason": spam_reason if is_spam else "",
            "is_garbled": is_garbled,
            "sentence_relevance": sentence_relevance,
        }

    @staticmethod
    def check_domain_relevance(
        question: str, answer: str, domain: str
    ) -> Dict[str, Any]:
        """
        检查回答在指定领域的相关性
        返回: {relevant: bool, score: float, matched_keywords: [], reason: str}
        """
        domain_info = ResponseRelevanceChecker.DOMAIN_KEYWORDS.get(domain, {})

        question_lower = question.lower()
        answer_lower = answer.lower()

        # 垃圾内容检测 - 垃圾内容直接0分
        is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(answer)
        if is_spam:
            return {
                "relevant": False,
                "score": 0.0,
                "matched_keywords": [],
                "negative_keywords": [],
                "reason": f"spam_content: {spam_reason}",
                "is_spam": True,
            }

        matched_positive = []
        for kw in domain_info.get("keywords", []):
            if kw.lower() in answer_lower:
                matched_positive.append(kw)

        matched_negative = []
        for kw in domain_info.get("negative_keywords", []):
            if kw.lower() in answer_lower:
                matched_negative.append(kw)

        positive_score = len(matched_positive) / max(
            len(domain_info.get("keywords", [])), 1
        )
        negative_penalty = len(matched_negative) * 0.3

        score = max(0, positive_score - negative_penalty)

        # 句子级相关性调节 - 如果大部分句子不含领域关键词，降低分数
        all_keywords = domain_info.get("keywords", [])
        if all_keywords and len(answer) > 100:
            sent_rel = ResponseRelevanceChecker.check_sentence_relevance(
                answer, all_keywords, min_ratio=0.0
            )
            if sent_rel["total_sentences"] > 0:
                score = score * (0.4 + 0.6 * sent_rel["ratio"])

        is_relevant = score >= 0.1 and len(matched_negative) == 0

        reason = f"matched {len(matched_positive)}/{len(domain_info.get('keywords', []))} positive keywords"
        if matched_negative:
            reason += f", {len(matched_negative)} negative keywords found"

        return {
            "relevant": is_relevant,
            "score": score,
            "matched_keywords": matched_positive,
            "negative_keywords": matched_negative,
            "reason": reason,
            "is_spam": False,
        }

    @staticmethod
    def _detect_primary_domain(text: str):
        """检测文本主要所属领域，返回 (domain, score) 或 (None, 0)"""
        text_lower = text.lower()
        domain_scores = {}
        for domain, domain_info in ResponseRelevanceChecker.DOMAIN_KEYWORDS.items():
            score = sum(
                1 for kw in domain_info.get("keywords", []) if kw.lower() in text_lower
            )
            if score > 0:
                domain_scores[domain] = score

        if not domain_scores:
            return None, 0

        best_domain = max(domain_scores.keys(), key=lambda d: domain_scores[d])
        best_score = domain_scores[best_domain]
        total = sum(domain_scores.values())

        if best_score >= 2 and best_score / total > 0.4:
            return best_domain, best_score / total

        return None, 0

    @staticmethod
    def _extract_bigrams(text: str) -> set:
        """提取文本的2字符滑动窗口集合，用于中文细粒度匹配"""
        result = set()
        cn_chars = re.findall(r"[\u4e00-\u9fff]", text)
        for i in range(len(cn_chars) - 1):
            result.add(cn_chars[i] + cn_chars[i + 1])
        return result

    @staticmethod
    def is_nonsensical_response(question: str, answer: str) -> Tuple[bool, str]:
        """
        检测无意义回答（与问题完全不相关）
        返回: (是否无意义, 原因)
        """
        question_lower = question.lower()
        answer_lower = answer.lower()

        nonsensical_patterns = [
            (r"^[\s\n]*$", "empty_response"),
            (r"^(好的|ok|okay|yep|yes|no)\s*[.。]?\s*$", "trivial_affirmation"),
            (r"^对不起|抱歉|我不明白|无法回答", "refusal_or_uncertainty"),
        ]

        for pattern, pattern_name in nonsensical_patterns:
            if re.match(pattern, answer_lower):
                return True, pattern_name

        if len(answer_lower) < 3:
            return True, "too_short"

        # 垃圾内容检测 - SEO堆砌、关键词重复等视为无意义
        is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(answer)
        if is_spam:
            return True, f"spam_content: {spam_reason}"

        q_bigrams = ResponseRelevanceChecker._extract_bigrams(question_lower)
        a_bigrams = ResponseRelevanceChecker._extract_bigrams(answer_lower)

        q_en_words = set(re.findall(r"[a-zA-Z]{3,}", question_lower))
        a_en_words = set(re.findall(r"[a-zA-Z]{3,}", answer_lower))

        cn_overlap = len(q_bigrams & a_bigrams) / max(len(q_bigrams), 1)
        en_overlap = (
            len(q_en_words & a_en_words) / max(len(q_en_words), 1)
            if q_en_words
            else 1.0
        )

        has_cn_overlap = cn_overlap >= 0.15
        # 只有当问题本身包含英文单词时，英文重叠才有意义
        # 纯中文问题不应该因为"没有英文可匹配"就自动通过
        has_en_overlap = bool(q_en_words) and en_overlap >= 0.2

        if not has_cn_overlap and not has_en_overlap:
            if len(answer_lower) > 50:
                return True, "no_keyword_overlap"
            if len(answer_lower) > 10:
                return True, "no_keyword_overlap_short"

        # 对于简短问题和长回答，检查是否有任何句子与问题相关
        if len(question) < 50 and len(answer) > 1000 and q_bigrams:
            answer_sentences = re.split(r"[。！？\n.!?]", answer)
            answer_sentences = [
                s.strip() for s in answer_sentences if len(s.strip()) > 5
            ]
            has_relevant_sentence = False
            for sent in answer_sentences:
                sent_bigrams = ResponseRelevanceChecker._extract_bigrams(sent)
                if len(q_bigrams & sent_bigrams) > 0:
                    has_relevant_sentence = True
                    break
            if not has_relevant_sentence:
                return True, "long_response_no_question_relevance"

        q_domain, q_confidence = ResponseRelevanceChecker._detect_primary_domain(
            question
        )
        a_domain, a_confidence = ResponseRelevanceChecker._detect_primary_domain(answer)

        if (
            q_domain
            and a_domain
            and q_domain != a_domain
            and q_confidence > 0.3
            and a_confidence > 0.3
        ):
            if not has_cn_overlap and not has_en_overlap:
                return (
                    True,
                    f"domain_mismatch: question({q_domain}) vs answer({a_domain})",
                )

        return False, ""


class TestQualityChatCompletions(BaseTest, StreamingTestMixin):
    """Chat Completions API 质量评估与回答相关性测试类"""

    def get_test_category(self) -> str:
        return "H. Chat Completions API 质量评估与回答相关性"

    def _log_relevance_result(
        self, test_logger, question: str, answer: str, result: Dict[str, Any]
    ):
        """记录相关性检查结果"""
        test_logger.info(f"问题: {question}")
        test_logger.info(f"回答: {answer[:2000]}...")
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
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, f"质量测试响应")
            self.log_full_response(test_logger, response, f"H1-生成质量-{idx + 1}")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)
            content = self.get_message_content(response)

            min_length = 20
            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)
            passed = len(content.strip()) >= min_length and not is_spam
            if is_spam:
                test_logger.warning(f"检测到垃圾内容: {spam_reason}")
            quality_scores.append(passed)
            test_logger.info(
                f"响应长度: {len(content)}, 通过: {passed} (最低要求: {min_length})"
            )

        pass_rate = sum(quality_scores) / len(test_cases)
        test_logger.info(
            f"质量通过率: {pass_rate * 100:.0f}%, 通过: {sum(quality_scores)}/{len(test_cases)}"
        )
        assert pass_rate >= 0.5, f"Quality pass rate too low: {pass_rate * 100:.0f}%"

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p1
    def test_generation_consistency(self, api_client: ModelAPIClient, test_logger):
        """H2 [P1]: 生成一致性 - 相同输入多次生成的稳定性"""
        test_logger.info("=== 测试开始: 生成一致性 ===")

        prompt = "请用一句话介绍北京"
        messages = [{"role": "user", "content": prompt}]
        TestLogger.log_request(
            test_logger, messages, {"max_tokens": 2000, "temperature": 0}
        )

        responses = []
        for i in range(3):
            test_logger.info(f"第{i + 1}次请求")
            response = api_client.chat_completion(
                messages, max_tokens=2000, temperature=0
            )
            TestLogger.log_response(
                test_logger, response, f"生成一致性-第{i + 1}次响应"
            )
            self.log_full_response(test_logger, response, f"H2-生成一致性-第{i + 1}次")
            self.assert_response_success(response)
            self.assert_content_not_empty(response)
            content = self.get_message_content(response)
            responses.append(content)
            test_logger.info(f"第{i + 1}次响应: {content[:2000]}...")

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
        assert similarity > 0.3, (
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
            messages = [{"role": "user", "content": question}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "幻觉检测响应")
            self.log_full_response(test_logger, response, f"H3-幻觉检测-{idx + 1}")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)
            content = self.get_message_content(response)

            is_nonsensical, nonsensical_reason = (
                ResponseRelevanceChecker.is_nonsensical_response(question, content)
            )
            expected_found = expected.lower() in content.lower()
            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)

            if not expected_found:
                hallucination_count += 1
                test_logger.warning(
                    f"幻觉: 期望包含'{expected}', 实际: {content[:500]}"
                )
                record_warning(f"幻觉: 期望包含'{expected}'")
            elif is_nonsensical:
                hallucination_count += 1
                test_logger.warning(
                    f"幻觉: 回答与问题不相关({nonsensical_reason}), 期望包含'{expected}', 实际: {content[:500]}"
                )
                record_warning(f"幻觉: 回答与问题不相关({nonsensical_reason})")
            elif is_spam:
                hallucination_count += 1
                test_logger.warning(
                    f"幻觉: 检测到垃圾内容({spam_reason}), 实际: {content[:500]}"
                )
                record_warning(f"幻觉: 检测到垃圾内容({spam_reason})")

        hallucination_rate = hallucination_count / len(test_facts)
        test_logger.info(f"Hallucination rate: {hallucination_rate * 100:.0f}%")
        assert hallucination_rate < 0.2, (
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
        content = self.get_message_content(response)

        try:
            import json as _json

            data = _json.loads(content)
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
            ("Python中如何定义函数？", ["def", "函数", "定义"]),
            ("水的化学式是什么？", ["H2O", "水", "化学"]),
        ]

        relevant_count = 0
        for idx, (prompt, keywords) in enumerate(test_cases):
            test_logger.info(f"测试问题: {prompt}")
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "相关性响应")
            self.log_full_response(test_logger, response, f"H5-回答相关性-{idx + 1}")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)
            content = self.get_message_content(response).lower()

            quality = ResponseRelevanceChecker.check_response_quality(
                prompt, content, keywords
            )
            if (
                any(kw.lower() in content for kw in keywords)
                and quality["quality_passed"]
            ):
                relevant_count += 1
            else:
                if quality["issues"]:
                    test_logger.warning(f"质量问题: {quality['issues']}")
                test_logger.warning(
                    f"回答不相关: 期望关键词{keywords}, 内容: {content[:500]}"
                )

        relevance_rate = relevant_count / len(test_cases)
        test_logger.info(f"Relevance rate: {relevance_rate * 100:.0f}%")
        assert relevance_rate >= 0.5, f"Low relevance: {relevance_rate * 100:.0f}%"

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
            messages = [{"role": "user", "content": case["question"]}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "响应")
            self.log_full_response(test_logger, response, f"H6-编程领域-{idx + 1}")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)
            content = self.get_message_content(response)
            test_logger.info(f"回答: {content[:2000]}...")

            is_garbled, garbled_type = ResponseRelevanceChecker.contains_garbled_text(
                content
            )
            assert not is_garbled, f"检测到乱码: {garbled_type}, 内容: {content[:2000]}"

            result = ResponseRelevanceChecker.check_domain_relevance(
                case["question"], content, case["domain"]
            )
            self._log_relevance_result(test_logger, case["question"], content, result)

            if result["relevant"] and result["score"] >= 0.1:
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
        assert relevance_rate >= 0.5, f"编程领域相关性过低: {relevance_rate * 100:.0f}%"

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
        for case in test_cases:
            test_logger.info(f"\n--- 测试: {case['question']} ---")
            messages = [{"role": "user", "content": case["question"]}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "响应")
            self.log_full_response(
                test_logger, response, f"H7-数学领域-{test_cases.index(case) + 1}"
            )

            self.assert_response_success(response)
            self.assert_content_not_empty(response)
            content = self.get_message_content(response)
            test_logger.info(f"回答: {content[:2000]}...")

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
        assert relevance_rate >= 0.5, f"数学领域相关性过低: {relevance_rate * 100:.0f}%"

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    def test_response_relevance_science(self, api_client: ModelAPIClient, test_logger):
        """H8 [P0]: 科学领域回答相关性验证"""
        test_logger.info("=== 测试开始: 科学领域回答相关性 ===")

        test_cases = [
            {
                "question": "水的化学式是什么？",
                "domain": "science",
                "expected": ["H2O", "氢", "氧"],
            },
            {
                "question": "什么是光合作用？",
                "domain": "science",
                "expected": ["光", "叶绿体", "二氧化碳", "氧气"],
            },
            {
                "question": "解释牛顿第一定律",
                "domain": "science",
                "expected": ["惯性", "力", "运动", "定律"],
            },
        ]

        passed_count = 0
        for idx, case in enumerate(test_cases):
            test_logger.info(f"\n--- 测试: {case['question']} ---")
            messages = [{"role": "user", "content": case["question"]}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "API 响应")
            self.log_full_response(test_logger, response, f"H8-科学领域-{idx + 1}")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)
            content = self.get_message_content(response)
            test_logger.info(f"回答内容: {content}")

            is_garbled, _ = ResponseRelevanceChecker.contains_garbled_text(content)
            assert not is_garbled, f"检测到乱码"

            result = ResponseRelevanceChecker.check_domain_relevance(
                case["question"], content, case["domain"]
            )
            self._log_relevance_result(test_logger, case["question"], content, result)

            quality = ResponseRelevanceChecker.check_response_quality(
                case["question"], content, case["expected"]
            )
            if (
                result["relevant"] or any(kw in content for kw in case["expected"])
            ) and quality["quality_passed"]:
                passed_count += 1
                test_logger.info("✓ 相关性验证通过")
            else:
                if quality["issues"]:
                    test_logger.warning(f"质量问题: {quality['issues']}")
                test_logger.warning("✗ 相关性验证失败")

        relevance_rate = passed_count / len(test_cases)
        test_logger.info(f"科学领域相关性通过率: {relevance_rate * 100:.0f}%")
        assert relevance_rate >= 0.5, f"科学领域相关性过低"

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p0
    @pytest.mark.smoke
    def test_garbled_text_detection(self, api_client: ModelAPIClient, test_logger):
        """H9: 乱码检测 - 验证输出不是乱码"""
        test_logger.info("=== 测试开始: 乱码检测 ===")

        test_prompts = [
            "请介绍一下人工智能的发展历史",
            "什么是机器学习？",
            "解释一下什么是深度学习",
            "Python中的列表和元组有什么区别？",
            "请用中文回答：What is an API?",
        ]

        garbled_count = 0
        for prompt in test_prompts:
            test_logger.info(f"\n测试: {prompt}")
            messages = [{"role": "user", "content": prompt}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "响应")
            self.log_full_response(
                test_logger, response, f"H9-乱码检测-{test_prompts.index(prompt) + 1}"
            )

            self.assert_response_success(response)
            content = self.get_message_content(response)
            test_logger.info(f"回答长度: {len(content)}")

            is_garbled, garbled_type = ResponseRelevanceChecker.contains_garbled_text(
                content
            )
            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)

            if is_garbled:
                garbled_count += 1
                test_logger.error(f"✗ 检测到乱码: {garbled_type}")
                test_logger.error(f"乱码内容: {content[:2000]}...")
            elif is_spam:
                garbled_count += 1
                test_logger.error(f"✗ 检测到垃圾内容: {spam_reason}")
                test_logger.error(f"垃圾内容: {content[:2000]}...")
            else:
                test_logger.info(f"✓ 内容正常，无乱码")

        garbled_rate = garbled_count / len(test_prompts)
        test_logger.info(f"\n乱码率: {garbled_rate * 100:.0f}%")
        assert garbled_rate < 0.2, f"乱码率过高: {garbled_rate * 100:.0f}%"

    @pytest.mark.h_quality_chat_completions
    @pytest.mark.p1
    def test_nonsensical_response_detection(
        self, api_client: ModelAPIClient, test_logger
    ):
        """H10: 无意义回答检测 - 验证回答不是完全无关的"""
        test_logger.info("=== 测试开始: 无意义回答检测 ===")

        test_cases = [
            "Python中如何定义一个函数？请给出示例代码",
            "水的沸点是多少摄氏度？",
            "请介绍一下北京的历史",
            "什么是人工智能？请详细解释",
            "1加1等于几？",
        ]

        nonsensical_count = 0
        for question in test_cases:
            test_logger.info(f"\n问题: {question}")
            messages = [{"role": "user", "content": question}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})

            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "响应")
            self.log_full_response(
                test_logger,
                response,
                f"H10-无意义检测-{test_cases.index(question) + 1}",
            )

            self.assert_response_success(response)
            content = self.get_message_content(response)
            test_logger.info(f"回答: {content[:2000]}...")

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
        assert nonsensical_rate <= 0.4, (
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
                    "北京今天天气怎么样？",
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
            messages = [{"role": "user", "content": question}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})
            response = api_client.chat_completion(messages, max_tokens=2000)
            TestLogger.log_response(test_logger, response, "响应")
            self.log_full_response(test_logger, response, f"H11-{domain}领域-{idx + 1}")
            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            test_logger.info(f"回答: {content[:2000]}...")

            is_garbled, _ = ResponseRelevanceChecker.contains_garbled_text(content)
            assert not is_garbled, f"检测到乱码"
            is_spam, spam_reason = ResponseRelevanceChecker.detect_spam_content(content)
            assert not is_spam, f"检测到垃圾内容: {spam_reason}"

            result = ResponseRelevanceChecker.check_domain_relevance(
                question, content, domain
            )
            test_logger.info(
                f"相关性得分: {result['score']:.2f}, 匹配关键词: {result['matched_keywords']}"
            )

            if result["relevant"]:
                passed_count += 1

        rate = passed_count / len(questions)
        assert rate >= 0.5, f"{domain}领域相关性过低: {rate * 100:.0f}%"

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
        c1 = self.get_message_content(r1)
        messages.append({"role": "assistant", "content": c1})
        test_logger.info(f"第1轮回答: {c1[:2000]}...")

        q2 = "我刚才说我喜欢吃什么水果？"
        test_logger.info(f"第2轮: {q2}")
        messages.append({"role": "user", "content": q2})
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})
        r2 = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, r2, "响应")
        self.log_full_response(test_logger, r2, "H12-上下文一致性-第2轮")
        self.assert_response_success(r2)
        self.assert_content_not_empty(r2)
        c2 = self.get_message_content(r2)
        test_logger.info(f"第2轮回答: {c2[:2000]}...")

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
        c3 = self.get_message_content(r3)
        messages.append({"role": "assistant", "content": c3})
        test_logger.info(f"第3轮回答: {c3[:2000]}...")

        q4 = "我刚才说了我喜欢哪两种水果？"
        test_logger.info(f"第4轮: {q4}")
        messages.append({"role": "user", "content": q4})
        TestLogger.log_request(test_logger, messages, {"max_tokens": 2000})
        r4 = api_client.chat_completion(messages, max_tokens=2000)
        TestLogger.log_response(test_logger, r4, "响应")
        self.log_full_response(test_logger, r4, "H12-上下文一致性-第4轮")
        self.assert_response_success(r4)
        self.assert_content_not_empty(r4)
        c4 = self.get_message_content(r4)
        test_logger.info(f"第4轮回答: {c4[:2000]}...")

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
        for idx, case in enumerate(test_cases):
            test_logger.info(f"\n--- 测试: {case['question']} ---")
            messages = [{"role": "user", "content": case["question"]}]
            TestLogger.log_request(test_logger, messages, {"max_tokens": 800})

            response = api_client.chat_completion(messages, max_tokens=800)
            TestLogger.log_response(test_logger, response, "API 响应")
            self.log_full_response(test_logger, response, f"H13-回答具体性-{idx + 1}")

            self.assert_response_success(response)
            self.assert_content_not_empty(response)

            content = self.get_message_content(response)
            test_logger.info(f"回答内容: {content}")

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

        specificity_rate = passed_count / len(test_cases)
        assert specificity_rate >= 0.5, f"回答具体性过低: {specificity_rate * 100:.0f}%"
