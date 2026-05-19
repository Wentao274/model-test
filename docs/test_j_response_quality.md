# J. 回答质量与相关性测试

## 概述

验证模型回答的质量和相关性，包括回答相关性、乱码检测、无意义回答检测、上下文一致性等。本测试类专注于检测模型输出是否存在以下问题：

- 回答与问题完全不相关
- 输出乱码或无效字符
- 无意义回答（如纯确认回复）
- 跨领域混淆（问编程答天气）

## 测试点列表

| ID  | 测试点 | 测试内容 | 优先级 |
|-----|--------|---------|--------|
| J1-1 | 编程领域相关性 | 验证编程问题的回答相关性 | P0 |
| J1-2 | 数学领域相关性 | 验证数学问题的回答相关性 | P0 |
| J1-3 | 科学领域相关性 | 验证科学问题的回答相关性 | P1 |
| J2 | 乱码检测 | 检测输出是否为乱码或无效字符 | P0 |
| J3 | 无意义回答检测 | 检测回答是否与问题完全不相关 | P1 |
| J4 | 跨领域相关性 | 天气/烹饪等领域相关性验证 | P1 |
| J5 | 上下文一致性 | 多轮对话中验证上下文一致性 | P0 |
| J6 | 回答具体性 | 确保回答不是泛泛而谈 | P2 |

## 运行方式

```bash
# 运行所有回答质量测试
pytest tests/test_j_response_quality.py -v

# 运行特定测试
pytest tests/test_j_response_quality.py::TestResponseQuality::test_response_relevance_programming -v

# 运行 P0 优先级测试
pytest tests/test_j_response_quality.py -m p0 -v

# 运行乱码检测
pytest tests/test_j_response_quality.py::TestResponseQuality::test_garbled_text_detection -v
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
domain_info = {
    "programming": {
        "keywords": ["python", "def", "函数", "class", "return"],
        "negative_keywords": ["天气", "weather", "水果"]
    },
    ...
}
result = ResponseRelevanceChecker.check_domain_relevance(question, answer, domain)
# result: {"relevant": bool, "score": float, "matched_keywords": [], "reason": str}
```

相关性判定标准：
- `score >= 0.1` 且无 negative keywords
- 匹配正向关键词越多分数越高
- 发现负向关键词扣分

#### 3. is_nonsensical_response()
检测无意义回答（与问题完全不相关）：

```python
is_nonsensical, reason = ResponseRelevanceChecker.is_nonsensical_response(question, answer)
# reason: "empty_response", "trivial_affirmation", "no_keyword_overlap", etc.
```

无意义回答判定标准：
- 空回复或仅确认回复
- 关键词重叠率 < 5%
- 纯拒绝/不确定回复

## 测试用例说明

### test_response_relevance_programming (J1-1)

测试编程领域问题的回答相关性：
- Python 函数定义
- 递归算法
- 面向对象编程

验证回答包含编程领域关键词，无乱码。

### test_response_relevance_math (J1-2)

测试数学领域问题的回答相关性：
- 简单计算
- 勾股定理
- 导数概念

验证回答包含数学领域关键词，正确性验证。

### test_response_relevance_science (J1-3)

测试科学领域问题的回答相关性：
- 水化学式
- 光合作用
- 牛顿定律

### test_garbled_text_detection (J2)

乱码检测测试，验证输出不是乱码：
- 多种 prompt 类型测试
- 正则检测控制字符
- 异常编码检测

容忍阈值：乱码率 < 20%

### test_nonsensical_response_detection (J3)

无意义回答检测：
- 关键词重叠度分析
- Trivial response 检测
- 纯确认回复识别

容忍阈值：无意义率 < 20%

### test_cross_domain_relevance (J4)

跨领域相关性测试（参数化）：
- weather（天气）领域
- cooking（烹饪）领域

验证回答不混淆领域。

### test_conversation_context_consistency (J5)

多轮对话上下文一致性：
- 记住之前提到的信息（喜欢的水果）
- 多轮追问验证

```python
# 第1轮
messages.append({"role": "user", "content": "我喜欢吃苹果"})
# 第2轮
messages.append({"role": "user", "content": "我刚才说我喜欢吃什么水果？"})
# 验证回答包含"苹果"
```

### test_response_specificity_check (J6)

回答具体性检查：
- 最小长度要求
- 关键词详细度验证
- 防止泛泛而谈

## 检测阈值说明

| 测试点 | 通过阈值 | 说明 |
|--------|---------|------|
| 乱码检测 | < 20% | 乱码率阈值 |
| 无意义回答 | < 20% | 无意义率阈值 |
| 领域相关性 | >= 67% | 至少2/3通过 |
| 回答具体性 | >= 67% | 至少2/3通过 |

## 注意事项

- 领域相关性检测基于关键词匹配，不适用于所有场景
- J2/J3 的容忍阈值允许少量异常，避免误报
- J6 回答具体性检测依赖于合理的最小长度阈值
- 多语言问题可能影响关键词匹配准确性

## 依赖更新

- `base/base_test.py` - 基类方法
- `tests/test_j_response_quality.py` - 测试实现
- `conftest.py` - marker 注册
- `base/test_definitions.py` - 测试定义