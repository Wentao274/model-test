"""
回答相关性检查器 - 供质量评估测试类（H/I 等）共享

提供领域关键词匹配、乱码检测、垃圾内容（SEO堆砌/关键词重复）检测、
句子级相关性检查、综合质量检查、领域相关性检查、无意义回答检测等能力。
"""

import re
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional


class ResponseRelevanceChecker:
    """回答相关性检查器"""

    # 句子级相关性默认最低占比阈值
    SENTENCE_RELEVANCE_MIN_RATIO = 0.15

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
                "类",
                "对象",
                "封装",
                "继承",
                "多态",
                "抽象",
                "方法",
                "属性",
                "实例",
                "接口",
                "面向对象",
                "递归",
                "调用",
                "参数",
                "返回值",
                "语法",
                "编译",
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
                "炒",
                "煮",
                "炖",
                "蒸",
                "煎",
                "炸",
                "烤",
                "焖",
                "焯水",
                "翻炒",
                "收汁",
                "调味",
                "火候",
                "下锅",
                "出锅",
                "切丝",
                "切块",
                "切片",
                "搅拌",
                "沥干",
                "爆香",
                "糖色",
                "料酒",
                "生抽",
                "老抽",
                "食盐",
                "白糖",
                "冰糖",
                "葱花",
                "蒜末",
                "姜片",
                "油温",
                "大火",
                "小火",
                "中火",
                "毫升",
                "克",
                "汤匙",
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

        math_expression_pattern = r"^[\d\s\+\-\*/=<>±×÷≤≥≠≈∞√∫∑∏∂∇²³ⁿπ\u03b1-\u03c9\u0391-\u03a9\u3000-\u303f\uff00-\uffef\(\)\[\]\.,:;!?]+$"
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

        # 1. 检测重复句子（同一句子出现3次以上）
        # 注意：过滤掉纯markdown格式行（代码围栏```、分隔线---等），
        # 避免将编程回答中多个代码块的```python标记误判为重复句子。
        # 同样需过滤代码注释行（#、//、; 等）：编程回答中多个示例常含
        # 相同注释（如 "# 调用函数"），属于正常代码文档，不应判为堆砌。
        # 额外：先剥离代码块内容再做散文句子分析——代码块中的重复语句
        # （如多个示例中的 "import json"）是正常代码，不是散文堆砌。
        prose_text = re.sub(r"```[^\n]*\n.*?```", "", text_clean, flags=re.DOTALL)
        sentences = re.split(r"[。！？\n.!?]", prose_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        sentences = [
            s
            for s in sentences
            if not re.match(r"^(?:```+[\w]*|---+|===+|\*\*\*+|___+)\s*$", s)
            and not re.match(r"^(?:#{1,6}\s+|//|;|/\*|<!--)", s)
        ]

        if sentences:
            sentence_counts = Counter(sentences)
            for sent, count in sentence_counts.items():
                if count >= 3:
                    return True, f"repeated_sentence: '{sent[:30]}...' x{count}"

        # 2. 检测关键词堆砌（同一中文词组出现频率过高）
        # 注意：原逻辑对任意子串重复都判违规，会将"天气"在"天气App"/
        # "墨迹天气"/"实时天气"等不同复合词中的合理使用误判为堆砌。
        # 改进：区分"连续机械重复"（真堆砌）与"在不同复合词中作为语素"
        # （正常）。对领域问题的回答中，主题词（如天气领域的"天气"）
        # 反复出现是合理的，不应判失败。
        for ngram_len in range(2, 7):
            cn_words = re.findall(
                rf"[\u4e00-\u9fff]{{{ngram_len},{ngram_len}}}", text_clean
            )
            if cn_words:
                word_counts = Counter(cn_words)
                total_words = len(cn_words)
                for word, count in word_counts.items():
                    # 2a. 检测连续重复（如"优惠优惠优惠"），这是最典型的堆砌
                    # 同一词连续出现3次及以上视为机械堆砌
                    consecutive_pattern = rf"(?:{re.escape(word)}){{3,}}"
                    if re.search(consecutive_pattern, text_clean):
                        return (
                            True,
                            f"keyword_stuffing: '{word}' x{count} ({count / total_words:.0%})",
                        )
                    # 2b. 检测高频孤立重复：仅统计该词作为"独立词"（前后为非
                    # 中文字符）出现的次数，排除作为子串嵌在其他词中的情况。
                    # 例如"天气"在"天气App"中算独立词，但在"墨迹天气"中不算。
                    # 阈值放宽到>8次且>8%，避免领域回答中主题词的正常重复。
                    isolated_pattern = (
                        rf"(?:^|[^\u4e00-\u9fff]){re.escape(word)}"
                        rf"(?=[^\u4e00-\u9fff]|$)"
                    )
                    isolated_count = len(re.findall(isolated_pattern, text_clean))
                    if isolated_count > 8 and count / total_words > 0.08:
                        return (
                            True,
                            f"keyword_stuffing: '{word}' x{count} ({count / total_words:.0%})",
                        )

        # 3. 检测SEO式内容（大量短行包含相似关键词）
        # 注意：仅"短行多"不足以判定为SEO垃圾——格式良好的markdown回复
        # （列表、标题）也会产生大量短行。需额外检查短行的词汇多样性：
        # SEO垃圾的短行反复使用相同关键词（多样性低），而markdown列表项
        # 内容各异（多样性高）。
        lines = [l.strip() for l in text_clean.split("\n") if l.strip()]
        if len(lines) > 10:
            short_lines = [l for l in lines if len(l) < 30]
            if len(short_lines) > len(lines) * 0.6:
                # 检查短行的词汇多样性：提取2字中文n-gram，计算 unique/total
                short_text = "".join(short_lines)
                short_cn_words = re.findall(r"[\u4e00-\u9fff]{2}", short_text)
                if short_cn_words:
                    short_word_counts = Counter(short_cn_words)
                    short_diversity = len(short_word_counts) / len(short_cn_words)
                    # 多样性低于0.4表示短行高度重复（典型SEO垃圾特征）
                    if short_diversity < 0.4:
                        return (
                            True,
                            f"seo_style_content: {len(short_lines)}/{len(lines)} short lines, diversity={short_diversity:.2f}",
                        )

        # 4. 检测重复模式（高相似度句子过多）
        # 注意：排除含内联代码(backticks)的行——这类结构化对比行
        # （如 "传统：`GET /api/...`" vs "RESTful：`GET /api/...`"）
        # 格式相似但属正常技术对比，不应判为重复模式。
        prose_sentences = [s for s in sentences if "`" not in s]
        if len(prose_sentences) > 10:
            similar_count = 0
            for i in range(len(prose_sentences)):
                for j in range(i + 1, min(i + 10, len(prose_sentences))):
                    set_i = set(prose_sentences[i])
                    set_j = set(prose_sentences[j])
                    if set_i and set_j:
                        overlap = len(set_i & set_j) / max(len(set_i | set_j), 1)
                        if overlap > 0.7 and len(prose_sentences[i]) > 10:
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
                answer,
                expected_keywords,
                min_ratio=ResponseRelevanceChecker.SENTENCE_RELEVANCE_MIN_RATIO,
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
        # 负向词惩罚：单个负向词常出现在类比/举例中（如用"电影院"解释递归），
        # 不应直接否定整段领域回答。按命中比例扣分，仅当负向词较多时才显著降分。
        negative_count = len(matched_negative)
        negative_ratio = negative_count / max(
            len(domain_info.get("negative_keywords", [])), 1
        )
        negative_penalty = negative_ratio * 0.5

        score = max(0, positive_score - negative_penalty)

        # 句子级相关性调节 - 如果大部分句子不含领域关键词，降低分数
        all_keywords = domain_info.get("keywords", [])
        if all_keywords and len(answer) > 100:
            sent_rel = ResponseRelevanceChecker.check_sentence_relevance(
                answer, all_keywords, min_ratio=0.0
            )
            if sent_rel["total_sentences"] > 0:
                score = score * (0.4 + 0.6 * sent_rel["ratio"])

        # 仅当负向词数量较多（>=2）或超过正向词数量时才判不相关；
        # 单个负向词通常只是举例/类比，不应否定整段领域回答。
        is_relevant = (
            score >= 0.1
            and negative_count < 2
            and negative_count <= len(matched_positive)
        )

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
