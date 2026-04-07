# H. 质量评估测试

## 概述
验证模型生成内容的质量，包括生成质量、一致性、幻觉率、指令遵循度等。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| I1 | 量化质量损失 | FP16 vs INT4/INT8 输出质量对比 | P0 |
| I2 | 生成一致性 | 相同输入多次生成的稳定性 | P0 |
| I3 | 幻觉率 | 生成内容中事实错误的比例 | P1 |
| I4 | 指令遵循度 | 复杂指令（格式、长度、角色）遵循程度 | P0 |

## 运行方式

```bash
# 运行所有质量评估测试
pytest tests/test_h_quality.py -v

# 运行特定测试
pytest tests/test_h_quality.py::TestQuality::test_generation_quality -v
```

## 测试用例说明

### test_generation_quality
使用多个不同领域的问题测试生成质量：
- 验证输出非空且长度合理
- 统计质量通过率

### test_generation_consistency
测试相同输入（temperature=0）的一致性：
- 多次相同请求应产生一致输出

### test_hallucination_detection
测试幻觉率，使用简单的事实性问题：
- "中国的首都是哪里？"
- "1+1等于多少？"
- 验证答案包含预期内容

### test_instruction_following
测试指令遵循度：
- 验证模型能遵循复杂的格式要求
- 检查返回内容是否包含指定字段

### test_response_relevance
测试回答相关性：
- 检查回答是否与问题相关
- 验证包含领域关键词

## 注意事项
- 质量评估是主观性较强的测试
- I1的量化质量损失测试需要在不同量化配置下对比
- I3幻觉率测试使用简单问题作为基准