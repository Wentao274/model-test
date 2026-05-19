# 测试文档导航

本目录包含各测试分类的详细说明文档。

## 文档列表

| 文档 | 测试分类 | 测试点数 |
|------|---------|---------|
| [test_a_basic_reasoning.md](test_a_basic_reasoning.md) | A. 基础推理能力 | 12 |
| [test_b_advanced_generation.md](test_b_advanced_generation.md) | B. 高级生成功能 | 10 |
| [test_c_multimodal.md](test_c_multimodal.md) | C. 多模态能力 | 8 |
| [test_d_long_context.md](test_d_long_context.md) | D. 长上下文处理 | 8 |
| [test_e_performance.md](test_e_performance.md) | E. 性能指标 | 12 |
| [test_f_stability.md](test_f_stability.md) | F. 稳定性与边界 | 8 |
| [test_g_api_compatibility.md](test_g_api_compatibility.md) | G. API兼容性 | 8 |
| [test_h_quality.md](test_h_quality.md) | H. 质量评估 | 5 |
| [test_i_long_context.md](test_i_long_context.md) | I. 单项超长上下文验证 | 4 |
| [test_j_response_quality.md](test_j_response_quality.md) | J. 回答质量与相关性 | 8 |

## 快速运行

```bash
# 运行所有测试
pytest

# 按分类运行
pytest -m a_basic -v        # 基础推理能力
pytest -m b_advanced -v     # 高级生成功能
pytest -m c_multimodal -v   # 多模态能力
pytest -m d_long_context -v # 长上下文处理
pytest -m e_performance -v  # 性能指标
pytest -m f_stability -v    # 稳定性与边界
pytest -m g_api -v          # API兼容性
pytest -m h_quality -v      # 质量评估
pytest -m i_long_context -v # 超长上下文验证
pytest -m j_quality -v      # 回答质量与相关性

# 按优先级运行
pytest -m p0 -v  # P0 优先级测试
pytest -m p1 -v  # P1 优先级测试
```