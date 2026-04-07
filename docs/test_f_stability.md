# F. 稳定性与边界测试

## 概述
验证模型在异常情况、边界条件下的稳定性和容错能力，包括空输入、超大输入、非法参数、特殊字符注入、并发稳定性等。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| G1 | 空输入 | 发送空 prompt 或空 messages | P0 |
| G2 | 超大输入 | 超过 max_model_len 的输入 | P0 |
| G3 | 非法参数 | temperature=-1, max_tokens=0 等 | P0 |
| G4 | 特殊字符注入 | SQL注入、Prompt注入、XSS payload | P0 |
| G5 | 并发稳定性 | 200+ 并发持续运行 | P0 |
| G6 | OOM恢复 | 显存耗尽后的服务行为 | P1 |
| G7 | 长时间运行 | 连续服务 24 小时 | P1 |
| G8 | 请求超时处理 | 客户端超时断开 | P1 |

## 运行方式

```bash
# 运行所有稳定性测试
pytest tests/test_f_stability.py -v

# 排除慢速测试
pytest tests/test_f_stability.py -m "not slow" -v

# 运行特定测试
pytest tests/test_f_stability.py::TestStabilityAndBoundary::test_empty_input -v
```

## 测试用例说明

### test_empty_input
测试对空消息的处理，验证不会崩溃，返回适当错误。

### test_oversized_input
测试对超过max_model_len输入的处理，验证截断或返回413错误。

### test_invalid_parameters
测试非法参数（temperature=-1, max_tokens=0）的处理。

### test_special_character_injection
测试特殊字符注入（SQL注入、Prompt注入、XSS）的防护。

### test_concurrent_stability
测试并发稳定性，50并发请求的成功率。

### test_oom_recovery
测试显存耗尽后的服务恢复能力。

### test_long_running_service
测试长时间运行（需24小时，简化版为10分钟）。

### test_request_timeout_handling
测试客户端超时断开时服务端的资源释放。

## 注意事项
- 标记为slow的测试耗时较长
- G7长时间运行测试默认跳过
- 这些测试验证服务端的稳定性和安全性