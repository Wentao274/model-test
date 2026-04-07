# I. 单项超长上下文验证

## 概述
验证模型在超长上下文场景下的可用性和边界行为，通过独立脚本探测超长上下文create/stream路径。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| L1 | 超长上下文（脚本验证） | 使用独立脚本执行超长上下文create/stream探测 | P1 |

## 运行方式

```bash
# 运行所有超长上下文验证测试
pytest tests/test_i_long_context.py -v

# 排除慢速测试
pytest tests/test_i_long_context.py -m "not slow" -v
```

## 测试用例说明

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
- 发送接近限制的输入
- 验证边界行为

### test_reasoning_content_in_long_context
超长上下文下的思考内容验证：
- 在长上下文下开启thinking模式
- 验证reasoning_content在长上下文下仍然可用

## 注意事项
- 所有测试都标记为slow，耗时较长
- 需要模型支持超长上下文才能运行
- 测试会验证reasoning_content在超长上下文下的表现