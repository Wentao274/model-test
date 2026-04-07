# E. 性能指标测试

## 概述
验证模型的性能指标，包括延迟、吞吐量、并发能力等。

## 测试点列表

| ID | 测试点 | 测试内容 | 优先级 |
|----|--------|---------|--------|
| E1 | TTFT | 首Token延迟 | P0 |
| E2 | TPOT | 每Token生成时间 | P0 |
| E3 | ITL P50/P95/P99 | Token间延迟分位数统计 | P0 |
| E4 | 端到端延迟 | 从请求到完整响应的总时间 | P0 |
| E5 | 吞吐量 | tokens/s | P0 |
| E6 | 请求吞吐 | req/s | P0 |
| E7 | 并发扩展性 | 并发1→10→50→100→200 | P0 |
| E8 | 显存占用 | GPU显存消耗 | P0 |
| E9 | GPU利用率 | GPU计算单元利用率 | P1 |
| E10 | 预热时间 | 首次推理vs稳态推理 | P1 |
| E11 | Prefill速度 | 不同输入长度的prefill耗时 | P1 |
| E12 | 突发流量恢复 | 瞬间100并发后恢复 | P1 |

## 运行方式

```bash
# 运行所有性能测试
pytest tests/test_e_performance.py -v

# 排除慢速测试
pytest tests/test_e_performance.py -m "not slow" -v

# 运行特定指标测试
pytest tests/test_e_performance.py::TestPerformance::test_ttft -v
```

## 测试用例说明

### test_ttft
测量首Token时间（Time to First Token），从请求发出到收到第一个token。

### test_tpot
测量平均每Token生成时间（Time Per Output Token）。

### test_itl_percentiles
测量Token间延迟的分位数（P50、P95、P99）。

### test_end_to_end_latency
测量端到端延迟，从请求发出到完整响应的时间。

### test_token_throughput
测量token吞吐量（tokens/秒）。

### test_request_throughput
测量请求吞吐量（requests/秒）。

### test_concurrency_scaling
测试并发扩展性，验证不同并发下的表现。

### test_gpu_memory
测试GPU显存占用（需要nvidia-smi，当前跳过）。

### test_gpu_utilization
测试GPU计算单元利用率（需要nvidia-smi，当前跳过）。

### test_warmup_time
测试预热时间，比较首次请求和稳态请求的延迟差异。

### test_prefill_speed
测试不同输入长度的prefill速度。

### test_burst_recovery
测试突发流量后的恢复能力。

## 注意事项
- 性能测试结果受网络和服务器负载影响
- 标记为slow的测试耗时较长
- GPU相关测试需要nvidia-smi工具