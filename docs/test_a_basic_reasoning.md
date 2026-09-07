# A. 基础推理能力测试

## 概述
验证模型的基础文本生成和对话能力。

## 测试点列表

| ID  | 测试点            | 测试内容                      | 优先级 |
|-----|----------------|---------------------------|-----|
| A1  | 单轮对话           | 发送单条prompt，验证正常生成         | P0  |
| A2  | 多轮对话           | 5轮对话，验证上下文保持和连贯性          | P0  |
| A3  | System Prompt  | 设置系统角色，验证模型遵循程度           | P0  |
| A4  | 流式输出           | stream=true，验证SSE逐token返回 | P0  |
| A5  | 非流式输出          | stream=false，验证完整返回       | P0  |
| A6  | Temperature 控制 | temp=0 vs temp=1.0，验证输出差异 | P1  |
| A7  | Top-p/Top-k 采样 | 不同top_p/top_k值，验证多样性控制    | P1  |
| A8  | Max Tokens 限制  | 设置max_tokens，验证输出不超限      | P0  |
| A9  | Stop Sequences | 设置stop token，验证截断效果（软告警） | P1  |
| A10 | Seed 可复现性      | 相同seed+temp=0，评估输出一致性（软告警） | P1  |
| A11 | 多语言能力          | 中/英/日/韩/法等多语言输入输出         | P1  |
| A12 | 特殊 Token 处理    | 含emoji、代码块、数学符号、HTML标签的输入 | P1  |

## 运行方式

```bash
# 运行所有基础推理测试
pytest tests/test_a_basic_reasoning.py -v

# 运行特定测试
pytest tests/test_a_basic_reasoning.py::TestBasicReasoning::test_single_turn_conversation -v

# 只运行P0优先级测试
pytest tests/test_a_basic_reasoning.py -m p0 -v

# 指定模型运行
pytest tests/test_a_basic_reasoning.py --model=qwen35 -v
```

## 测试用例说明

### test_single_turn_conversation
验证模型能正确响应单条用户消息，返回有效的文本内容。

### test_multi_turn_conversation
验证模型能在5轮对话中保持上下文连贯性，能记住之前对话中提到的信息。

### test_system_prompt
验证模型能正确遵循system prompt设置的角色定位。

### test_streaming_output
验证流式输出（stream=true）能正确返回SSE格式的增量响应。

### test_non_streaming_output
验证非流式输出（stream=false）能一次性返回完整响应，使用"机器学习的基本概念和应用场景"作为 prompt（与 A4 流式测试使用不同 prompt 避免重复），并验证 usage 字段中 completion_tokens、prompt_tokens 大于 0，total_tokens 等于二者之和。

### test_temperature_control
验证 temperature 参数的效果。使用开放性 prompt（"描述理想生活"）增大答案空间。temp=0 两次输出相似度须 >= 0.8（硬断言）；temp=1.0 两次输出不应完全一致（相似度 < 0.99，硬断言）；temp=1.0 相似度高于 temp=0 时记录软告警。比较时使用正式回复（剥离 reasoning），避免思考模型 reasoning 波动干扰。

### test_top_p_top_k_sampling
参数化测试top_p和top_k采样参数，验证多样性控制效果。

### test_max_tokens_limit
参数化测试不同max_tokens值（50, 100, 500），验证输出token数不超过限制。

### test_stop_sequences
验证 stop 参数的截断效果。请求按顺序列举 5 种水果并设置 stop=["苹果","香蕉"]，检查输出是否在 stop 词处截断。很多模型可能不支持 stop 参数，思考模型在思考模式下 stop 序列也可能不生效，因此统一使用软告警（record_warning）而非硬断言，作为诊断工具评估 stop 支持情况。

### test_seed_reproducibility
验证相同 seed（42）+ temperature=0 时两次输出的可复现性。比较时使用正式回复（剥离 reasoning）。很多模型不支持 seed 参数或无法保证完全可复现（受硬件浮点差异、batching 策略等影响），因此所有不一致情况统一使用软告警（record_warning），本测试作为诊断工具评估 seed 支持情况，不作为硬性失败条件。

### test_multilingual_capability
参数化测试多语言（中文、英文、日文、韩文、法文）输入输出能力。

### test_special_tokens_handling
测试特殊token（emoji、代码块、数学符号、HTML标签）的处理能力。

## 预期结果
- P0 测试必须全部通过（A1-A5, A8）
- P1 测试中核心功能为硬断言（A6 temperature 效果、A7 采样基本可用性、A11 多语言输出、A12 特殊 Token 处理）
- P1 测试中以下为诊断型软告警，不作为硬性失败条件：
  - A9 Stop Sequences：很多模型不支持 stop 参数，思考模式下也可能不生效
  - A10 Seed 可复现性：很多模型不支持 seed 或无法保证完全可复现
- 软告警信息会记录在测试报告中，用于评估模型对该特性的支持情况