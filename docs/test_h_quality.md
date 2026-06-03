# H. 质量评估与回答相关性测试

## 概述
验证模型生成内容的质量和回答相关性，包括生成质量、一致性、幻觉率、指令遵循度、回答相关性、乱码检测、无意义回答检测、上下文一致性等。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| H1 | 生成质量 | 质量对比 | P0 |
| H2 | 生成一致性 | 相同输入多次生成的稳定性 | P0 |
| H3 | 幻觉率 | 生成内容中事实错误的比例 | P1 |
| H4 | 指令遵循度 | 复杂指令（格式、长度、角色）遵循程度 | P0 |
| H5 | 响应相关性 | 问答相关性评估 | P0 |
| H6 | 编程领域相关性 | 验证编程问题的回答相关性 | P0 |
| H7 | 数学领域相关性 | 验证数学问题的回答相关性 | P0 |
| H8 | 科学领域相关性 | 验证科学问题的回答相关性 | P1 |
| H9 | 乱码检测 | 检测输出是否为乱码或无效字符 | P0 |
| H10 | 无意义回答检测 | 检测回答是否与问题完全不相关 | P1 |
| H11 | 跨领域相关性 | 天气/烹饪等领域相关性验证 | P1 |
| H12 | 上下文一致性 | 多轮对话中验证上下文一致性 | P0 |
| H13 | 回答具体性 | 确保回答不是泛泛而谈 | P2 |

## 运行方式

```bash
# 运行所有质量评估与回答相关性测试
pytest tests/test_h_quality.py -v

# 运行特定测试
pytest tests/test_h_quality.py::TestQuality::test_generation_quality -v

# 运行 P0 优先级测试
pytest tests/test_h_quality.py -m p0 -v

# 运行乱码检测
pytest tests/test_h_quality.py::TestQuality::test_garbled_text_detection -v
```

## 核心检测逻辑

### ResponseRelevanceChecker 工具类

提供三个核心检测方法：

#### 1. contains_garbled_text()
检测乱码输出，支持以下模式：
- 纯替换字符（`�`）
- 纯控制字符
- 纯数字和符号
- 过短且无语言字符
- 控制字符比例过高

```python
is_garbled, garbled_type = ResponseRelevanceChecker.contains_garbled_text(content)
assert not is_garbled, f"检测到乱码: {garbled_type}"
```

#### 2. check_domain_relevance()
基于领域关键词验证回答相关性：

```python
result = ResponseRelevanceChecker.check_domain_relevance(question, answer, domain)
# result: {"relevant": bool, "score": float, "matched_keywords": [], "reason": str}
```

#### 3. is_nonsensical_response()
检测无意义回答（与问题完全不相关）：

```python
is_nonsensical, reason = ResponseRelevanceChecker.is_nonsensical_response(question, answer)
```

## 测试用例说明

### test_generation_quality (H1)
使用多个不同领域的问题测试生成质量，验证输出非空且长度合理。

### test_generation_consistency (H2)
测试相同输入（temperature=0）的一致性，多次相同请求应产生一致输出。

### test_hallucination_detection (H3)
测试幻觉率，使用简单的事实性问题，验证答案包含预期内容。

### test_instruction_following (H4)
测试指令遵循度，验证模型能遵循复杂的格式要求。

### test_response_relevance (H5)
测试回答相关性，检查回答是否与问题相关，验证包含领域关键词。

### test_response_relevance_programming (H6)
测试编程领域问题的回答相关性：Python 函数定义、递归算法、面向对象编程。

### test_response_relevance_math (H7)
测试数学领域问题的回答相关性：简单计算、勾股定理、导数概念。

### test_response_relevance_science (H8)
测试科学领域问题的回答相关性：水化学式、光合作用、牛顿定律。

### test_garbled_text_detection (H9)
乱码检测测试，验证输出不是乱码。容忍阈值：乱码率 < 20%。

### test_nonsensical_response_detection (H10)
无意义回答检测：关键词重叠度分析、Trivial response 检测。容忍阈值：无意义率 < 20%。

### test_cross_domain_relevance (H11)
跨领域相关性测试（参数化）：weather/cooking 领域验证回答不混淆领域。

### test_conversation_context_consistency (H12)
多轮对话上下文一致性：记住之前提到的信息，多轮追问验证。

### test_response_specificity_check (H13)
回答具体性检查：最小长度要求、关键词详细度验证，防止泛泛而谈。

## 检测阈值说明

| 测试点 | 通过阈值 | 说明 |
|--------|---------|------|
| 乱码检测 | < 20% | 乱码率阈值 |
| 无意义回答 | < 20% | 无意义率阈值 |
| 领域相关性 | >= 67% | 至少2/3通过 |
| 回答具体性 | >= 67% | 至少2/3通过 |

## 注意事项
- 质量评估是主观性较强的测试
- H1的量化质量损失测试需要在不同量化配置下对比
- H3幻觉率测试使用简单问题作为基准
- H6-H13原属J类测试，已合并至H类统一管理
- 领域相关性检测基于关键词匹配，不适用于所有场景
- H9/H10的容忍阈值允许少量异常，避免误报
- 多语言问题可能影响关键词匹配准确性
