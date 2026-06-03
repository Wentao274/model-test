# D. 长上下文处理测试

## 概述
验证模型处理长文本输入输出的能力，包括上下文边界行为、NIAH（大海捞针）测试，以及超长上下文下的非流式/流式输出和思考模式验证。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| D1 | 短上下文基线 | input 1K tokens，验证正常推理 | P0 |
| D2 | 中等上下文 | input 8K-16K tokens，验证质量不降 | P0 |
| D3 | 长上下文 | input 32K-64K tokens，验证召回和推理 | P0 |
| D4 | 超长上下文 | input 128K+ tokens，验证不OOM且可用 | P1 |
| D5 | 大海捞针（NIAH） | 长文本中插入特定信息，验证召回率 | P0 |
| D6 | 上下文边界行为 | 输入恰好等于max_model_len | P1 |
| D7 | 超出上下文截断 | 输入超过模型限制，验证截断/拒绝策略 | P1 |
| D8 | 长输出生成 | 要求生成4K-8K tokens的长文本 | P1 |
| D9 | 超长上下文（非流式） | 验证超长上下文请求的非流式输出 | P1 |
| D10 | 超长上下文（流式） | 验证超长上下文请求的流式输出 | P1 |
| D11 | 超长上下文（边界验证） | 使用二分法逼近模型最大上下文长度 | P0 |
| D12 | 超长上下文（思考模式） | 验证超长上下文下reasoning_content的可用性 | P0 |

## 运行方式

```bash
# 运行所有长上下文测试
pytest tests/test_d_long_context.py -v

# 排除慢速测试
pytest tests/test_d_long_context.py -m "not slow" -v

# 运行特定测试
pytest tests/test_d_long_context.py::TestLongContext::test_short_context_baseline -v
```

## 测试用例说明

### test_short_context_baseline
基线测试，验证短文本输入（~1K tokens）的正常处理。

### test_medium_context
测试中等长度上下文（8K-16K tokens）的处理能力。

### test_long_context
测试长上下文（32K-64K tokens）的召回和推理能力。

### test_super_long_context
测试超长上下文（128K+ tokens），验证模型不会OOM。

### test_niah_needle_in_a_haystack
测试大海捞针能力，在长文本中插入特定信息并验证能否正确召回。

### test_context_boundary_behavior
测试上下文边界行为，验证接近模型最大限制时的处理。

### test_context_truncation
测试超过上下文限制时的截断或拒绝策略。

### test_long_output_generation
测试长文本生成能力，要求生成4K-8K tokens。

### test_super_long_context_create
超长上下文非流式验证：
- 发送100K+ tokens的输入
- 验证响应成功
- 检查reasoning_content和content的可用性
- 验证usage统计正确

### test_super_long_context_stream
超长上下文流式验证：
- 发送100K+ tokens的输入
- 验证流式响应正常工作
- 检查reasoning_content和content的增量返回

### test_context_boundary_exact_limit
上下文边界精确验证：
- 尝试获取模型的max_model_len
- 使用二分法逐步逼近最大上下文长度
- 验证模型声称的最大上下文长度可达

### test_reasoning_content_in_long_context
超长上下文下的思考内容验证：
- 在长上下文下开启thinking模式
- 验证reasoning_content在长上下文下仍然可用

## 注意事项
- 标记为slow的测试耗时较长
- 超长上下文测试可能因模型限制而跳过
- D9-D12原属I类测试，已合并至D类统一管理
