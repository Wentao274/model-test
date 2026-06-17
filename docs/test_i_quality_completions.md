# I. Completions API 质量评估与回答相关性测试

## 概述
验证 `/v1/completions` 接口的模型生成内容质量和回答相关性。与 H 类测试用例一致，区别在于使用 Completions API 而非 Chat Completions API。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| I1 | 生成质量 | Completions API 质量对比 | P1 |
| I2 | 生成一致性 | Completions API 相同输入多次生成的稳定性 | P1 |
| I3 | 幻觉率 | Completions API 生成内容中事实错误的比例 | P1 |
| I4 | 指令遵循度 | Completions API 复杂指令（格式、长度、角色）遵循程度 | P1 |
| I5 | 响应相关性 | Completions API 问答相关性评估 | P1 |
| I6 | 编程领域相关性 | Completions API 验证编程问题的回答相关性 | P1 |
| I7 | 数学领域相关性 | Completions API 验证数学问题的回答相关性 | P1 |
| I8 | 科学领域相关性 | Completions API 验证科学问题的回答相关性 | P1 |
| I9 | 乱码检测 | Completions API 检测输出是否为乱码或无效字符 | P1 |
| I10 | 无意义回答检测 | Completions API 检测回答是否与问题完全不相关 | P1 |
| I11 | 跨领域相关性 | Completions API 天气/烹饪等领域相关性验证 | P1 |
| I12 | 上下文一致性 | Completions API 多轮对话中验证上下文一致性 | P1 |
| I13 | 回答具体性 | Completions API 确保回答不是泛泛而谈 | P2 |

## 运行方式

```bash
# 运行所有 Completions API 质量评估测试
pytest tests/test_i_quality_completions.py -v

# 使用 marker 运行
pytest -m i_quality_completions -v

# 运行特定测试
pytest tests/test_i_quality_completions.py::TestQualityCompletions::test_generation_quality -v

# 运行 P0 优先级测试
pytest tests/test_i_quality_completions.py -m p0 -v

# 运行乱码检测
pytest tests/test_i_quality_completions.py::TestQualityCompletions::test_garbled_text_detection -v
```

## 与 H 类测试的区别

| 维度 | H. 质量评估与回答相关性 | I. Completions API 质量评估 |
|------|----------------------|---------------------------|
| 接口 | `/v1/chat/completions` | `/v1/completions` |
| 调用方式 | `api_client.chat_completion(messages)` | `api_client.completion(prompt)` |
| 输入格式 | `messages` 列表（含 role） | `prompt` 字符串 |
| 响应格式 | `choices[0].message.content` | `choices[0].text` |
| 多轮对话 | 原生支持 messages 数组 | 通过拼接 prompt 模拟上下文 |
| reasoning_content | 支持 | 不支持 |

## 核心差异实现

### 响应内容获取

```python
# H 类：从 message.content 获取
content = self.get_message_content(response)

# I 类：从 choices[0].text 获取
content = self.get_message_content(response)  # 类内重写，自动从 text 字段获取
```

### 多轮对话模拟

```python
# H 类：使用 messages 数组
messages = [
    {"role": "user", "content": "我喜欢吃苹果"},
    {"role": "assistant", "content": c1},
    {"role": "user", "content": "我刚才说我喜欢吃什么水果？"},
]

# I 类：拼接 prompt 文本
conversation = [
    "用户: 我喜欢吃苹果",
    "助手: ...",
    "用户: 我刚才说我喜欢吃什么水果？",
    "助手:"
]
prompt = "\n".join(conversation)
```

## 核心检测逻辑

复用 `ResponseRelevanceChecker` 工具类，与 H 类测试共享相同的检测逻辑：

- `contains_garbled_text()` - 乱码检测
- `check_domain_relevance()` - 领域相关性检测
- `is_nonsensical_response()` - 无意义回答检测

## 检测阈值说明

| 测试点 | 通过阈值 | 说明 |
|--------|---------|------|
| 乱码检测 | < 20% | 乱码率阈值 |
| 无意义回答 | <= 40% | 无意义率阈值 |
| 领域相关性 | >= 50% | 至少半数通过 |
| 回答具体性 | >= 50% | 至少半数通过 |
| 幻觉率 | < 20% | 幻觉率阈值 |
| 幻觉率 | < 20% | 幻觉率阈值 |

## 注意事项

- Completions API 不支持 reasoning_content，`get_reasoning_content()` 返回 None
- 多轮对话通过拼接文本模拟，上下文保持能力取决于模型对 prompt 格式的理解
- 部分 API 服务可能不支持 `/v1/completions` 接口，测试将失败并输出错误原因（如 404 Not Found）
- 响应内容从 `choices[0].text` 获取，与 Chat Completions 的 `choices[0].message.content` 不同
