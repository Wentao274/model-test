# 主流大模型推理功能测试点矩阵

> 覆盖模型：Qwen 3.5、Kimi K2.5、GLM-5、Minimax 2.5 <br>
> 目标：梳理推理服务需要覆盖的完整测试点，形成可执行的测试清单

---

## 一、模型基本信息对照

| 维度           | Qwen 3.5                 | Kimi K2.5           | GLM-5               | Minimax 2.1                                 | Minimax 2.5                                 |
|--------------|--------------------------|---------------------|---------------------|---------------------------------------------|---------------------------------------------|
| **发布日期**     | 2026.02.15               | 2026.01             | 2026.02.11          | 以当前接入的 `minimax-m21` 为准                     | 以当前接入的 `minimax-m2.5` 为准                    |
| **架构**       | Hybrid（线性注意力+MoE）        | MoE（384 experts）    | MoE                 | 商业闭源服务形态                                    | 商业闭源服务形态                                    |
| **总参数/激活参数** | 397B / 17B               | 1T / 32B            | 744B / 40B          | 未公开                                         | 未公开                                         |
| **最大上下文**    | 262K（扩展至 1M）             | 128K                | 205K                | 以服务端配置与实测边界为准                               | 以服务端配置与实测边界为准                               |
| **多模态**      | 原生视觉-语言                  | 原生视觉-语言-视频          | 文本为主                | 当前套件已覆盖图片 content parts                     | 当前套件已覆盖图片 content parts                     |
| **思考模式**     | 支持 thinking/non-thinking | 支持 instant/thinking | 支持                  | 支持，关闭后 `reasoning` 仍可能返回文本                  | 支持，关闭后 `reasoning` 仍可能返回文本                  |
| **工具调用**     | 原生内置                     | 原生内置                | 原生内置                | 支持，当前稳定 passing path 为 `tool_choice="auto"` | 支持，当前稳定 passing path 为 `tool_choice="auto"` |
| **开源协议**     | Apache 2.0               | 开源                  | 开源                  | 闭源商用                                        | 闭源商用                                        |
| **推理框架支持**   | vLLM/SGLang/TRT-LLM      | vLLM/SGLang         | vLLM/SGLang/TRT-LLM | 当前通过 OpenAI-compatible 服务接入                 | 当前通过 OpenAI-compatible 服务接入                 |

---

## 二、测试点总览（11 大类 × 130 个测试点）

### 分类概览

| 分类           | 测试点数 | 说明                  |
|--------------|------|---------------------|
| A. 基础推理能力    | 12   | 文本生成、对话、基础控制等       |
| B. 高级生成功能    | 11   | 思考模式、工具调用、结构化输出、reasoning_effort 等    |
| C. 多模态能力     | 12   | 图片理解、视频理解、OCR、代码截图、多模态工具调用     |
| D. 长上下文处理    | 12   | 长文本输入/输出、大海捞针、上下文边界、超长上下文验证 |
| E. 性能指标      | 12   | 延迟、吞吐、并发、显存         |
| F. 稳定性与边界    | 8    | 异常输入、OOM 恢复、长时间运行   |
| G. API 兼容性   | 6    | OpenAI 兼容、参数一致性     |
| H. Chat Completions API 质量评估与回答相关性 | 13   | ChatCompletions API 生成质量、一致性、幻觉率、回答相关性、乱码检测 |
| I. Completions API 质量评估 | 13   | Completions API 生成质量、一致性、幻觉率、回答相关性、乱码检测 |
| J. clear_thinking 参数行为 | 11   | 多轮对话下历史思考的清除/保留、与 enable_thinking 的正交组合、reasoning_content 字段、多 assistant 边界、默认行为、行为级验证、last_user 边界、deployment 能力探测 |
| K. 客户问题复现 | 21   | 客户报障场景原样复现（Pydantic $defs/$ref Schema 工具调用、同一请求循环执行5次、Anthropic 协议 prompt cache、frequency_penalty 防御性钳制、thinking 关闭、关思考温度档、思考强度档位思考长度、required 强制工具调用、tool_choice 四种模式、response_format 三种模式、reasoning_effort 档位（顶层/嵌套）、stop 序列截断正文前置多余字符、孤儿 tool 消息 400 拒绝、短输入缓存阈值、固定前缀/多轮缓存命中率达标、推理换行停止符生效、输出 JSON 回填上下文、图片数超限拒绝、1M 上下文支持、system 消息内嵌 tools 宽容解析、双协议前缀缓存命中率对齐、孤儿 tool 消息官方对齐放行），P0 为主持续追加 |

---

## 三、详细测试点矩阵

状态说明：`✅` 已通过，`⏳` 未测试，`❌` 未通过，`⚠️` 部分通过

### A. 基础推理能力（12 项）

| #   | 测试点              | 测试内容                                                           | 优先级 |
|-----|------------------|----------------------------------------------------------------|-----|
| A1  | 单轮对话             | 发送单条 prompt，验证正常生成                                             | P0  |
| A2  | 多轮对话             | 5 轮对话，验证上下文保持和连贯性                                              | P0  |
| A3  | System Prompt    | 设置系统角色，验证模型遵循程度                                                | P0  |
| A4  | 流式输出             | stream=true，验证 SSE 逐 token 返回                                  | P0  |
| A5  | 非流式输出            | stream=false，验证完整返回                                            | P0  |
| A6  | Temperature 控制   | temp=0（确定性）vs temp=1.0（多样性），验证输出差异                             | P1  |
| A7  | Top-p / Top-k 采样 | 不同 top_p/top_k 值，验证多样性控制生效                                     | P1  |
| A8  | Max Tokens 限制    | 设置 max_tokens=50/100/500，验证输出不超限                               | P0  |
| A9  | Stop Sequences   | 设置 stop=["苹果","香蕉"]，请求列举水果，验证输出在 stop token 处截断且不包含 stop token | P1  |
| A10 | Seed 可复现性        | 相同 seed + temp=0，验证输出一致                                        | P1  |
| A11 | 多语言能力            | 中/英/日/韩/法 等多语言输入输出                                             | P1  |
| A12 | 特殊 Token 处理      | 含 emoji、代码块、数学符号、HTML 标签的输入                                    | P1  |


---

### B. 高级生成功能（11 项）

| #   | 测试点                | 测试内容                                           | 优先级 |
|-----|--------------------|------------------------------------------------|-----|
| B1  | 思考模式（Thinking）     | 开启 thinking mode，验证返回思考链 + 最终答案                | P0  |
| B2  | 非思考模式（Instant）     | 关闭 thinking，拆分验证"请求可接受"与"无 hidden thinking 泄漏"；不支持关闭则告警 | P1  |
| B3  | 思考模式切换             | 同一会话内 thinking↔non-thinking 切换；关闭不支持则告警         | P1  |
| B4  | 工具调用-单工具           | 定义单个 function，验证模型正确调用并传参                      | P0  |
| B5  | 工具调用-多工具           | 定义多个 function，验证模型选择正确的工具                      | P1  |
| B6  | 工具调用-并行调用          | 单次回复中并行调用多个工具                                  | P2  |
| B7  | 工具调用-多步链式          | 工具结果作为下一步输入，验证 3+ 步链式执行                        | P1  |
| B8  | JSON Mode          | response_format=json_object，验证输出合法 JSON        | P0  |
| B9  | 结构化输出              | JSON Schema 约束输出格式，验证字段完整性                     | P0  |
| B10 | Prefix / Suffix 约束 | 指定输出前缀或格式模板，验证遵循度                              | P2  |
| B11 | reasoning_effort 参数 | low/high/max 三档思考强度，不支持的模型告警并跳过                  | P1  |


---

### C. 多模态能力（12 项）

| #    | 测试点       | 测试内容                          | 优先级 |
|------|-----------|-------------------------------|-----|
| C1   | 单图理解      | 合成图片+文本提问，验证颜色识别               | P1  |
| C2   | 多图对比      | 输入多张图片，验证跨图比较和推理               | P1  |
| C3   | 高分辨率图片    | 真实高清图片，验证细节识别能力               | P2  |
| C4   | 图表/OCR    | 合成文字图片识别                       | P1  |
| C5   | 视频理解      | 输入视频文件，验证时序理解和总结               | P2  |
| C6   | 代码截图→代码   | Flask 代码截图识别并生成代码               | P2  |
| C7   | 多模态工具调用    | 基于图片内容触发工具调用                   | P2  |
| C8   | 图片格式兼容性    | PNG/JPEG/WebP                 | P1  |
| C9   | 真实图片理解     | 真实图片描述能力                       | P1  |
| C10  | 合成4K图片     | 验证大尺寸图片处理能力                    | P2  |
| C11  | 表格OCR      | 真实表格截图数据识别                     | P1  |
| C12  | UI截图生成代码   | UI 设计图生成对应代码                    | P2  |


---

### D. 长上下文处理（12 项）

| #   | 测试点        | 测试内容                           | 优先级 |
|-----|------------|--------------------------------|-----|
| D1  | 短上下文基线     | input 1K tokens，验证正常推理         | P0  |
| D2  | 中等上下文      | input 8K-16K tokens，验证质量不降     | P1  |
| D3  | 长上下文       | input 32K-64K tokens，验证召回和推理   | P1  |
| D4  | 超长上下文      | input 128K+ tokens，验证不 OOM 且可用 | P0  |
| D5  | 大海捞针（NIAH） | 长文本中插入特定信息，验证召回率               | P0  |
| D6  | 上下文边界行为    | 输入恰好等于 max_model_len，验证行为      | P1  |
| D7  | 超出上下文截断    | 输入超过模型限制，验证截断/拒绝策略             | P1  |
| D8  | 长输出生成      | 要求生成 4K-8K tokens 的长文本，验证完整性   | P1  |
| D9  | 超长上下文（非流式） | 验证超长上下文请求的非流式输出               | P1  |
| D10 | 超长上下文（流式）  | 验证超长上下文请求的流式输出                | P1  |
| D11 | 超长上下文（边界验证）| 使用二分法逼近模型最大上下文长度              | P1  |
| D12 | 超长上下文（思考模式）| 验证超长上下文下reasoning_content的可用性 | P0  |

---

### E. 性能指标（12 项）

| #   | 测试点                | 测试内容                              | 测试方法                         | 优先级 |
|-----|--------------------|-----------------------------------|------------------------------|-----|
| E1  | TTFT（首 Token 延迟）   | 从请求发出到收到第一个 token 的时间             | benchmark_serving.py / 自定义脚本 | P0  |
| E2  | TPOT（每 Token 生成时间） | Decode 阶段平均每个 token 耗时            | 统计流式输出 token 间隔              | P0  |
| E3  | ITL P50/P95/P99    | Token 间延迟的分位数统计                   | 多轮测试取分位数                     | P0  |
| E4  | 端到端延迟              | 从请求到完整响应的总时间                      | 非流式请求测量                      | P0  |
| E5  | 吞吐量（tokens/s）      | 单位时间生成的 token 总数                  | 并发压测                         | P0  |
| E6  | 请求吞吐（req/s）        | 单位时间完成的请求数                        | 固定 QPS 压测                    | P0  |
| E7  | 并发扩展性              | 并发 1→10→50→100→200 时指标变化          | 阶梯加压测试                       | P0  |
| E8  | 显存占用               | 不同并发/序列长度下的 GPU 显存消耗              | nvidia-smi 监控                | P0  |
| E9  | GPU 利用率            | 推理时 GPU 计算单元利用率                   | nvidia-smi / nvtop           | P1  |
| E10 | 预热时间               | 首次推理 vs 稳态推理的延迟差异                 | 对比前 5 次和稳态                   | P1  |
| E11 | Prefill 速度         | 不同输入长度（1K/4K/16K/64K）的 prefill 耗时 | 固定短输出，变输入长度                  | P1  |
| E12 | 突发流量恢复             | 瞬间 100 并发后恢复到正常响应时间               | burst 模式压测                   | P1  |


---

### F. 稳定性与边界（8 项）

| #   | 测试点    | 测试内容                           | 预期行为              | 优先级 |
|-----|--------|--------------------------------|-------------------|-----|
| F1  | 空输入    | 发送空 prompt 或空 messages         | 返回错误提示，不崩溃        | P0  |
| F2  | 超大输入   | 超过 max_model_len 的输入           | 截断或返回 413 错误      | P1  |
| F3  | 非法参数   | temperature=-1, max_tokens=0 等 | 返回 400 参数错误       | P2  |
| F4  | 特殊字符注入 | SQL 注入、Prompt 注入、XSS payload   | 不执行恶意指令，正常回复      | P0  |
| F5  | 并发稳定性  | 200+ 并发持续运行 1 小时               | 无 crash、无内存泄漏     | P1  |
| F6  | OOM 恢复 | 显存耗尽后的服务行为                     | 拒绝新请求但不崩溃，显存释放后恢复 | P1  |
| F7  | 长时间运行  | 连续服务 24 小时                     | 性能不退化，无内存泄漏       | P1  |
| F8  | 请求超时处理 | 客户端超时断开                        | 服务端正确释放资源         | P1  |

---

### G. API 兼容性（6 项）


| #   | 测试点                     | 测试内容                           | 验证要点                                 | 优先级 |
|-----|-------------------------|--------------------------------|--------------------------------------|-----|
| G1  | OpenAI Chat Completions | /v1/chat/completions 接口兼容      | 请求格式、返回格式完全兼容                        | P0  |
| G2  | OpenAI Completions      | /v1/completions 接口兼容           | 传统 completion 格式支持、max_tokens 超限处理     | P1  |
| G3  | 模型列表                    | /v1/models 返回可用模型              | 正确返回模型 ID 和元信息，当前模型在列表中              | P0  |
| G4  | Usage 统计                | 返回中 usage 字段准确                 | prompt_tokens + completion_tokens 准确 | P0  |
| G5  | 错误码规范                   | 401/400/404 错误码               | 符合 OpenAI 错误格式                       | P1  |
| G6  | 客户端 SDK 兼容              | Python openai                 | 无需修改代码直接调用                           | P0  |

> **注意**：response_format（json_object/json_schema）测试见 B8/B9，stream 参数测试见 A4，G 类不重复测试。


---

### H. Chat Completions API 质量评估与回答相关性（13 项）

| #   | 测试点    | 测试内容                     | 评估方法                      | 优先级 |
|-----|--------|--------------------------|---------------------------|-----|
| H1  | 量化质量损失 | Chat Completions API FP16 vs INT4/INT8 输出质量对比 | 相同 prompt 对比，人工评分 + 自动化指标 | P0  |
| H2  | 生成一致性  | Chat Completions API 相同输入多次生成的稳定性             | seed 固定后比较输出              | P1  |
| H3  | 幻觉率    | Chat Completions API 生成内容中事实错误的比例             | RAG 场景下对比原文验证             | P1  |
| H4  | 指令遵循度  | Chat Completions API 复杂指令（格式、长度、角色）遵循程度       | IFBench / 自定义指令集          | P0  |
| H5  | 响应相关性  | Chat Completions API 问答相关性评估                  | 使用不同领域的问题，检查是否包含相关关键词     | P0  |
| H6  | 编程领域相关性 | Chat Completions API 验证编程问题的回答相关性             | 检查回答是否包含编程领域关键词           | P0  |
| H7  | 数学领域相关性 | Chat Completions API 验证数学问题的回答相关性             | 检查回答是否包含数学领域关键词           | P0  |
| H8  | 科学领域相关性 | Chat Completions API 验证科学问题的回答相关性             | 检查回答是否包含科学领域关键词           | P0  |
| H9  | 乱码检测   | Chat Completions API 检测输出是否为乱码或无效字符           | 正则检测控制字符、纯符号、异常编码等        | P0  |
| H10 | 无意义回答检测 | Chat Completions API 检测回答是否与问题完全不相关           | 关键词重叠度分析、trivial response检测 | P1  |
| H11 | 跨领域相关性 | Chat Completions API 天气/烹饪等领域相关性验证            | 跨领域关键词匹配检测                | P1  |
| H12 | 上下文一致性 | Chat Completions API 多轮对话中验证上下文一致性            | 多轮记忆验证（记住之前提到的内容）         | P0  |
| H13 | 回答具体性  | Chat Completions API 确保回答不是泛泛而谈               | 长度+关键词详细度检测               | P2  |

---

### I. Completions API 质量评估与回答相关性（13 项）

| #   | 测试点    | 测试内容                     | 评估方法                      | 优先级 |
|-----|--------|--------------------------|---------------------------|-----|
| I1  | 生成质量 | Completions API 输出质量对比 | 相同 prompt 对比，自动检测长度与关键词 | P1  |
| I2  | 生成一致性  | 相同输入多次生成的稳定性             | temperature=0 比较输出一致性         | P1  |
| I3  | 幻觉率    | Completions API 事实错误检测       | 简单事实性问题验证             | P1  |
| I4  | 指令遵循度  | 复杂指令（格式、长度、角色）遵循程度       | JSON 格式指令验证          | P1  |
| I5  | 响应相关性  | Completions API 问答相关性评估      | 使用不同领域的问题，检查是否包含相关关键词     | P1  |
| I6  | 编程领域相关性 | Completions API 验证编程问题的回答相关性 | 检查回答是否包含编程领域关键词           | P1  |
| I7  | 数学领域相关性 | Completions API 验证数学问题的回答相关性 | 检查回答是否包含数学领域关键词           | P1  |
| I8  | 科学领域相关性 | Completions API 验证科学问题的回答相关性 | 检查回答是否包含科学领域关键词           | P1  |
| I9  | 乱码检测   | Completions API 检测输出是否为乱码或无效字符 | 正则检测控制字符、纯符号、异常编码等        | P1  |
| I10 | 无意义回答检测 | Completions API 检测回答是否与问题完全不相关 | 关键词重叠度分析、trivial response检测 | P1  |
| I11 | 跨领域相关性 | Completions API 天气/烹饪等领域相关性验证 | 跨领域关键词匹配检测                | P1  |
| I12 | 上下文一致性 | Completions API 多轮对话中验证上下文一致性（通过拼接 prompt 模拟） | 多轮记忆验证（记住之前提到的内容）         | P1  |
| I13 | 回答具体性  | Completions API 确保回答不是泛泛而谈               | 长度+关键词详细度检测               | P2  |

---

### J. clear_thinking 参数行为（11 项）

验证 `chat_template_kwargs.clear_thinking` 在多轮对话场景下对历史 assistant 思考内容
（open-think ... close-think 块）的清除/保留行为，以及与 `enable_thinking` 的正交性。
仅在多轮对话场景下有意义，单轮请求无效果。J6/J7/J8 覆盖 GLM-5.3 chat_template 的
`reasoning_content` 独立字段分支、`reasoning_effort` 参数组合、多 assistant 边界逻辑；
J9/J10/J11 为补充用例，分别覆盖默认行为探测、行为级验证、last_user 之后 assistant
思考保留边界。

| #    | 测试点                                 | 测试内容                                                            | 验证方法                                                | 优先级 |
|------|------------------------------------|-------------------------------------------------------------------|-----------------------------------------------------|-----|
| J1   | clear_thinking=true 多轮              | 显式清除历史 thinking，验证多轮请求成功且无 thinking 泄漏到后续上下文                      | 多轮 messages 含历史 think 块，断言响应成功且最终回答可基于历史最终答案推论     | P1  |
| J2   | clear_thinking=false 多轮             | 显式保留历史 thinking，验证多轮请求成功（此时历史思考被服务端保留并送入上下文）                       | 同 J1 历史，断言响应成功且最终回答可基于历史最终答案推论                     | P1  |
| J3   | clear_thinking 对 prompt_tokens 的影响  | 对比 true/false 在含历史 thinking 的请求下 prompt_tokens 差异                  | 同一组多轮 messages 分别以 true/false 发送，pt_false > pt_true 时 PASS；未生效（相等）时 record_warning + SKIP | P2  |
| J4   | clear_thinking 与 enable_thinking 组合 | 四种 (enable_thinking, clear_thinking) 组合均可被服务端接受                    | enable_thinking=True 的两个组合必须通过；enable_thinking=False 的组合若检测到模型强制开启思考则 SKIP + WARNING | P1  |
| J5   | clear_thinking deployment 能力探测       | 探测服务端是否真实实现 clear_thinking（pt_false > pt_true），未生效时记录 WARNING      | 探测未生效时 WARNING + record_warning（不 SKIP，始终报告 deployment 能力）；J3 在此基础上做行为验证 | P1  |
| J6   | clear_thinking 对 reasoning_content 独立字段的处理 | assistant 以 reasoning_content 独立字段承载思考时验证 clear_thinking 行为（GLM-5.3 模版 L137-138） | 对比 true/false 的 prompt_tokens，相等时 record_warning（不 FAIL） | P1  |
| J7   | clear_thinking 与 reasoning_effort 组合 | GLM-5.3 核心参数组合，验证参数正交性                            | 四种组合 (clear × effort) 至少 2 个通过；极端组合 pt 相等则 record_warning | P1  |
| J8   | 多 assistant 边界测试 | 多条历史 assistant 消息下 last_user_index 边界条件（模版 L143，剥除分支）          | user1→assistant1→user2→assistant2→user3，对比 true/false 的 prompt_tokens | P2  |
| J9   | clear_thinking 默认行为探测 | 不传 clear_thinking 时的服务端默认值验证（Qwen3 预期默认 true） | 不传 vs 显式 true/false 三次请求对比 prompt_tokens，默认 false 或不等则 record_warning | P2  |
| J10  | clear_thinking 行为级验证 | follow-up 依赖历史思考内容（而非最终答案），验证模型是否真的"看到"历史 thinking | clear=false 应命中思考关键词、true 不命中（软断言）；两者均命中/均不命中则 record_warning | P2  |
| J11  | last_user 之后 assistant 思考保留边界 | 验证模版 loop.index0 > last_user_index 的"保留"分支（J8 只覆盖"剥除"分支） | user1→assistant1→user2→assistant2，assistant2 在 last_user 之后应保留思考；对比 prompt_tokens | P2  |

### K. 客户问题复现（27 项）

收录客户反馈的真实问题，按客户原始请求（curl）逐字段原样复现。全部 P0：客户报障
场景纳入每次回归的必验范围；修复后保留为长期回归用例。与"四、按模型特性的差异化
测试点"中的 Kimi 专项 K1-K4 编号相互独立（本类为测试分类编号）。

| #   | 测试点                            | 测试内容                                                                                     | 验证方法                                                                 | 优先级 |
|-----|--------------------------------|--------------------------------------------------------------------------------------------|--------------------------------------------------------------------|-----|
| K1  | Pydantic $defs/$ref Schema 工具调用 | 客户问题：glm-5.3 流式请求（thinking+stream+stream_options+强制 tool_choice+Pydantic v2 生成的 $defs/$ref Schema）报【$$不兼容】 | 按客户原始 curl 原样复现：断言流式 chunks 非空、finish_reason 合法、强制工具 submit_d2_product 返回（含 id）、参数为合法 JSON 且必填 core_work_type 非空、usage 软校验 | P0  |
| K2  | 同一请求循环执行5次返回信息异常 | 客户问题：同一 curl（logprobs+top_logprobs+n+thinking+stream+X-Cache-Buster 防缓存头）循环执行 5 次左右出现返回信息异常 | 按客户原始 curl 原样复现并连续执行 5 次（相邻间隔 3s）：断言每次流式 chunks 非空、finish_reason 合法、内容非空；5 次全部正常才 PASS，失败时报告第几次 | P0  |
| K3  | Anthropic 协议 prompt cache 未创建 | 客户问题：Anthropic 协议（/anthropic/v1/messages，stream=true）请求（prompt_tokens=111283）的服务端日志 cache_creation_tokens 一直为 0（未创建缓存） | 构造带 cache_control 断点的唯一长前缀（~11 万 tokens，对齐客户场景规模）连发两次：断言第 1 次 cache_creation_input_tokens>0（创建）、第 2 次 cache_read_input_tokens>0（命中）；兼容网关内部字段名拼写 | P0  |
| K4  | frequency_penalty=-2 不传 max_tokens 无返回 | 客户问题：fp=-2（OpenAI 规范 [-2,2] 合法极值）且不传 max_tokens 时退化重复导致无界生成、请求一直无返回（fp<0 奖励已出现 token 压制 EOS，自然终止失效） | 修复契约 fp<0 按 0 处理：输入保持 -2、不传 max_tokens 连发 3 次（消息各异，相邻间隔 3s），断言每次均按 fp=0 预期——单次 120s 预算内返回、finish_reason 自然结束（非 length）、内容非空；任一次失败报告第几次；专用预算客户端（retry=0）检测挂起 | P0  |
| K5  | thinking.type=disabled 后思考未关闭 | 客户问题：thinking.type=disabled 后 reasoning_tokens 仍=100/75、reasoning_content 照常输出，关思考相关功能（低延迟模式、关思考温度档）全部失效；官方端点实测 disabled 后思考完全关闭（官方 FAQ 与实测不符，以实测为准） | 输入保持客户原值 disabled、temperature=0.6（官方关思考档唯一合法温度）、不传 max_tokens 连发 3 次（消息各异，相邻间隔 3s），断言每次均按官方实测预期——无思考内容（reasoning_content/reasoning）、reasoning_tokens 为空（0/缺失，兼容两种字段拼写）、正文正常返回且 finish_reason 自然结束；任一次失败报告第几次 | P0  |
| K6  | 关思考温度档未联动校验 | 客户影响：关思考相关功能（关思考温度档）失效；官方契约（kimi-k3）：thinking 与 temperature 档位联动——disabled 仅允许 0.6（给 1 或 0 报 400 "only 0.6 is allowed for this model in non-thinking mode"）、enabled 仅允许 1（给 0.6 或 0 报 400 "only 1 is allowed for this model in thinking mode"） | 对 6 个组合（disabled/enabled × 0.6/1/0）各发一次请求（同一 prompt，参数为唯一变量；参数校验为确定性行为无需多次连发），断言合法组合 200+正文非空、非法组合 400+错误信息含官方文案（忽略大小写子串匹配，对错误体 JSON 结构不敏感） | P0  |
| K7  | 思考强度档位思考长度倒挂（官方 reasoning_effort） | 官方契约（kimi-k3 文档）：思考强度为顶层 reasoning_effort（K2.x thinking 配置已废弃），K3 恒开思考，思考长度（reasoning_tokens）应随档位递增 | 只按官方格式传参（无回退），请求顺序（客户指定）：low→high→max 比对思考长度，max→high→low 逆向重发再比对（正逆两轮排除顺序干扰，均按 low<high<max 软对比，medium 不参与）；最后 medium 顶层 200 放行、medium 嵌套 400（废弃配置下非法档位，客户指定契约）；间隔 3s、内容与 temperature=1 相同；硬断言每次 200+正文非空+自然结束；倒挂/持平不判失败，仅告警记入报告；reasoning_tokens 兼容两种字段拼写 | P0  |
| K8  | required+闲聊必须调用工具（客户工单级别） | 客户工单原始问题：required+闲聊（"Reply with exactly: OK"，无工具意图）下不发起工具调用——tool_calls 键缺失、finish=length、ct 恒吃满 max_tokens（关思考 1000/3000 均如此）、正文仅 OK、耗时 15.6s 双峰；开思考 reasoning 消耗远小于预算但整体仍被吃满；预期 finish=tool_calls、关思考 ct 较小、开思考 rt<max_tokens、正文收到工具调用响应信息 | 关思考 mt=1000/3000、开思考 mt=3000（get_weather 工具，温度按档位联动 0.6/1），断言每轮 tool_calls 存在（get_weather、arguments 合法 JSON）、finish_reason==tool_calls（而非 length）、ct<max_tokens、开思考 rt<max_tokens（rt 双拼写兼容）；耗时双峰仅日志留痕 | P1  |
| K9  | required+闲聊必须强制调用工具（按官方行为） | 官方 api.moonshot.cn 实测：闲聊+required → finish=tool_calls、强制返回 get_weather（city 瞎猜不限定）、reasoning 仅 38——符合 [OI] required 必须发起至少一次工具调用规范；Alaya 同场景 finish=length、reasoning 吃满 256/2000 预算、tool_calls=None；有工具意图时两站一致正常 | 关/开思考 × mt=256/2000（温度按档位联动 0.6/1，与 K8 同场景不同级别），按官方行为断言每轮 tool_calls 强制返回（get_weather、arguments 合法 JSON）、finish_reason==tool_calls、ct<max_tokens、开思考 rt<max_tokens（rt 双拼写兼容）；耗时双峰仅日志留痕 | P1  |
| K10 | GLM-5.3-Flash tool_choice 四种模式支持 | 客户问题（AGDC2-15）：OpenAI 协议 tool_choice 让模型按请求指定的类型/模式生成工具调用（Agent 自定义工具场景）；上线前版本未指定模型专属工具调用格式解析器，GLM-5.3-Flash 不支持该语义；修复为 Worker 侧指定生成解释器、渲染字段至聊天模版；需支持 auto/required/named/none；同时适用 Kimi K3（OpenAI 协议通用语义，默认思考不做断言） | 四模式各一次（原始脚本 glm53_flash_suite 口径：mt=2048、非流式、不传 thinking；采样参数不豁免——由全局 SAMPLING_PARAMS（Jenkinsfile）覆盖，temperature=0 为无覆盖时回退值；工具 get_weather+get_current_time 两个），断言 auto/required 必须发起工具调用（type=function、arguments 合法 JSON、finish=tool_calls）、named 必须调用指定工具（指定与提示词天气意图不同向的 get_current_time，未生效时按意图调 get_weather 即被检出）、none 禁止调用（无 tool_calls、正文非空、finish=stop）；usage 仅日志 | P0  |
| K11 | GLM-5.3-Flash response_format 三种模式支持 | 客户问题（AGDC2-16）：OpenAI 协议 response_format 让模型按指定格式输出（Agent 场景）；DingoRouter 不支持该结构化输出语义；修复为 Router 侧支持结构化生成语义并转发至引擎；需支持 json_object/json_schema/text | 三模式各一次（原始脚本 glm53_flash_suite 口径：temperature=0、mt=2048、非流式、不传 thinking），断言 json_object 正文可解析为 JSON 对象、json_schema 正文可解析且 city 为字符串、temperature 为数值、键集合恰为 {city,temperature}（weather strict schema）、text 正文非空；每轮 finish=stop；usage 仅日志 | P0  |
| K12 | GLM-5.3-Flash reasoning_effort 档位支持 | 客户问题（AGDC2-17）：GLM-5.3-Flash 使用 GLM 自己的聊天模版，字段为 reasoning_effort 且放在 chat_template_kwargs 里；而 OpenAI 协议/参考脚本将其放在顶层；Router 需在 OpenAI 协议外层捕获该字段并传给引擎；修复为 Router 侧支持语义转发；需支持 low/high/max/空（空=不发送该字段，默认档），且不管 reasoning_effort 放在顶层还是嵌套在 chat_template_kwargs 里，请求都能被正常接受和处理并输出正常响应 | 两种放置（顶层/嵌套 chat_template_kwargs）× 四档各一次（原始脚本 glm53_flash_suite 口径：temperature=0、mt=2048、非流式、不传 thinking、chat_template_kwargs={clear_thinking:true}；嵌套放置：reasoning_effort 放进 chat_template_kwargs），断言每轮 200+正文非空+finish=stop；档位对思考的实际影响（rt/reasoning 长度）仅日志留痕；usage 仅日志 | P0  |
| K13 | stop 序列遵循且被截断正文前置多余字符 | 客户问题：stop=["橘子"] 的流式请求，期望输出 "苹果、香蕉、"（正文在停止词处截断、不含停止词），实际输出 ">苹果、香蕉、"——被截断正文前面多输出了一个 ">" 符号；同时适用 KimiK3（缺陷为通用 stop 截断逻辑） | 按客户原始请求体还原（stream=true、stop=[橘子]、glm-5.3-flash 另传 thinking={type:enabled}+reasoning_effort=low、其余采样参数不发送；KimiK3 不传 thinking/reasoning_effort），断言 SSE 有正文增量、finish=stop、合并正文严格等于 "苹果、香蕉、"（多余前缀/停止词泄漏/未截断均 FAIL）、不含 "橘子"；usage 仅日志 | P0  |
| K14 | 孤儿 tool 消息应 HTTP 400 拒绝 | 客户问题：messages 中 tool 角色消息前无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未定义任何 tools），属协议非法请求，网关应校验并返回 400 Bad Request；实际返回 200 放行，模型把孤儿 tool 消息当普通上下文推理；同时适用 GLM-5.3 与 GLM-5.3-Flash | 按客户原始请求体还原（user "今天天气怎么样？" 后直接跟 tool tool_call_id=call_abc123、stream=true、无 tools/thinking/采样参数），断言 HTTP 400；若 200 放行（缺陷形态）取样若干 SSE 事件留证后 FAIL；响应体与 usage 仅日志 | P0  |
| K15 | 细粒度前缀匹配短输入缓存阈值 | 客户问题：短文本缓存命中率不达标，根因推理引擎默认前缀缓存分块撮合的最小可缓存块长过大（vLLM 默认 640 tok 量级），客户输入低于该块长（如 625 tok）完全不缓存；平台修复为细粒度前缀匹配（sglang prefix-match-unit=64）；同时适用 GLM-5.3 与 GLM-5.3-Flash | 两个测试点（OpenAI 协议非流式、不发送采样参数，cached_tokens 取 usage.prompt_tokens_details.cached_tokens 兼容 usage.cached_tokens）：1) 输入 64<N<640 的相同请求连发两次，断言第 2 次 cached_tokens>0（修复后应正常缓存，修复前不缓存即缺陷）；2) 输入 N<64 的相同请求连发两次，断言 cached_tokens==0（低于最细粒度不缓存）；以服务端 prompt_tokens 校验输入规模前提；usage 仅日志 | P0  |
| K16 | 固定前缀/多轮上下文缓存命中率达标 | 客户问题：短文本缓存命中率不达标——修复前固定前缀每轮 cached=7680/input=8693（88.35%）、多轮上下文 87.16%，均低于 90% 目标；根因 640 token 分块粒度将共享前缀截断（8192→12×640=7680，损失 512），细粒度匹配（64）后应 ≈94.2%≥90%；同时适用 GLM-5.3 与 GLM-5.3-Flash | 请求规模由原始信息推算（~12800 中文字符共享前缀 ≈8192 tok + ~780 字符/轮唯一问题 ≈501 tok）；两模式（OpenAI 协议非流式、不发送采样参数）：1) 固定前缀 10 轮独立请求（同一前缀+每轮唯一问题）；2) 多轮上下文单会话逐轮追加（回复极短）；均排除第 1 轮预热实测 9 轮，断言各模式 cached_tokens 总和/prompt_tokens 总和 ≥90%，任一 <90% 即 FAIL；零命中轮次留痕、usage 仅日志 | P0  |
| K17 | stop 停止符（换行符）在推理阶段生效 | 客户契约：指定停止符为换行符 "\n" 并开启思考时，停止符同样作用于推理（reasoning）输出——推理里出现的第一个换行即触发停止，正文（content）不会生成；反之若换行未触发停止、继续输出正文，则换行符未生效；适用 GLM-5.3 | 按场景构造流式请求（stream=true、stop=["\n"]、thinking={type:enabled} 显式开启思考（K1 口径）、max_tokens=512 防御性预算、不发送采样参数），断言 SSE 有事件、合并正文为空（核心——收到正文即换行符未生效）、finish_reason==stop、合并 reasoning 不含换行（停止符不泄漏）；模型真实响应（合并正文/思考全文）断言前打印、失败时同样可见；usage 仅日志 | P0  |
| K18 | 模型输出 JSON 可回填为下次请求输入上下文 | 客户问题（AGDC2-28）：上次请求输出的 assistant JSON 作为下次请求的输入上下文提交即报错（missing field `name`）——助手历史 tool_calls 混有空占位调用（name=""、id=null）与真实 bash 调用（arguments 缺开头 "{"、非合法 JSON）；修复为解析失败后同列表有真实调用时移除空占位项再校验、缺 "{" 的 arguments 原样保留（不补）、兼容重复 reasoning_content/reasoning_context；后续问题（开发文档）：修复上线后新问题 tool_call_id 悬空引用（must reference an unanswered tool call）——根因为模型返回空 function（id=null），客户端以 missing_tool_call_id 回填错误结果后被协议校验拒绝，根上解决为模型不返回空 function；空 function 场景按用户指定不再保留（回放数据移除空占位调用）；适用 GLM-5.3 | 按客户 agent 两步流程还原（用户指定测试逻辑）：第一个请求让模型输出技能周报数据 JSON（示例记录——明确无需真实数据，防御模型因无数据拒绝虚构）并落盘测试脚本同级目录下临时文件（第一步"输出 JSON 到 *.json 文件"）；第二个请求调用工具读取该临时 JSON 文件，将工单原始 assistant 返回数据（user→assistant(真实 bash 调用（arguments 缺 "{"）+reasoning 双字段——空占位调用已按用户指定移除)→tool(工具读取结果——协议必需的工具结果配对，实测缺失被 400 拒绝)→user 追问，带 bash 工具定义，非流式）回填为输入上下文；第三个请求（根因断言）复刻工单首个 user 回合（带 bash 工具定义）断言模型工具调用结构完整；测试完成后删除临时 JSON 文件（finally 兜底，断言失败同样清理）；断言：第一个请求 HTTP 200 且正文可提取合法 JSON 对象、临时文件回读一致、第二个请求 HTTP 200（核心——报错复现即 FAIL）、choices 存在、message 结构存在、第三个请求模型发起工具调用且每条调用 name/id 非空、arguments 为合法 JSON 对象（根因断言：模型不得返回空 function）；不断言 arguments 被补 "{"；采样参数不豁免——由全局 SAMPLING_PARAMS 覆盖；usage 仅日志 | P0  |
| K19 | 单次请求图片数超限（>16）应拒绝并返回恰当错误 | 客户问题：单次请求携带超过 16 张图片导致请求失败；根因服务端 serving-pool 显式配置 --limit-mm-per-prompt {"image":16,"video":1,"audio":0}（vLLM 多模态单项限额）；契约为超限请求应失败并返回恰当错误信息（参考 "At most 16 image(s) may be provided in one prompt"）；适用 GLM-5.3-Flash | 代码生成 17 张 32x32 纯色 PNG（base64 data URL，无外部依赖），单条 user 消息携带 17 个 image_url part 非流式提交（不发送采样参数——豁免），断言响应失败（非 200——200 放行即限额未生效 FAIL）且错误信息含 "at most 16 image"（大小写不敏感——信息不恰当即 FAIL）；恰好 16 张正向对照未纳入；模型真实响应（状态码/响应体全文）断言前打印、失败时同样可见；usage 仅日志 | P0  |
| K20 | 1M 上下文请求应被正常支持 | 客户问题：请求报错 "Input length (918451 tokens) exceeds the maximum allowed length (781754 tokens). Use a shorter input or enable --allow-auto-truncate."（invalid_request_error——网关透传 serving 侧上下文长度校验拒绝；当时最大允许 781754，未按 1M 上下文契约配置）；契约：模型需支持 1M 上下文请求——1M 量级输入应正常响应；适用 GLM-5.3 | 1M=输入+输出（用户口径），总量略小于 1M：探针自校准（重复单元 ×2000 从 usage.prompt_tokens 精确计量每单元 token 数——客户端无分词器，启发式误差大：真实环境实测该单元 6.28 字符/token，chars/4 高估 57%）后按目标生成主请求：输入 960,000 tokens + 输出预算 max_tokens 覆盖思考+正文，两轮思考档位（GLM-5.3 不支持禁用思考、仅支持档位——用户口径；用户指定补 max 场景）——low 轮（1024）常规、max 轮（4096）最大思考负载，输出侧同步压窗口（真实环境实测默认档思考耗尽 32 预算致 content 为空——预算必须覆盖思考+正文）（总消耗 ≈961K/964K，1,000,000/1,048,576 两种 1M 口径均满足——余量留给推理框架额外补充的长度；高于原始故障上限 781,754 约 178K），单条 user 消息非流式提交（采样参数不豁免——用户指定：全局 SAMPLING_PARAMS 覆盖，temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入；1M prefill 临时上调客户端超时至 900s，finally 恢复），断言探针 200 且有 usage、每轮主请求 HTTP 200、choices/content 非空、每轮主响应 prompt_tokens（如有）>781,754（规模 sanity）；请求提示词由程序生成；跑必冷（用户加固，仅 low 轮）：low 轮（含探针）材料头部置每次请求唯一 nonce（时间戳+uuid，可含中文）——前缀必不命中 KV 缓存，真 1M 冷 prefill（缓存只省 prefill 重算，不绕过准入长度校验/不省 KV 内存驻留与 decode 全窗注意力——核心契约验证本不受缓存影响）；max 轮取消唯一前缀（用户口径：输出侧验证不受缓存影响，允许命中历史缓存加速）；模型真实响应（状态码/响应体全文）断言前每轮打印、失败时同样可见；usage 仅日志 | P0  |
| K21 | system 消息内嵌 tools 的非标请求结构应被接受 | 客户问题（kimi-k3 工单原始请求体）：messages[2] 为 role=system 且无 content 字段、代之以内嵌 tools 数组（Calculator 单工具），服务端反序列化报 400 invalid_request_error/json_parse_error（"messages[2]: data did not match any variant of untagged enum MessageContent"）——结构虽非 OpenAI 协议标准形态（tools 应为顶层参数），但客户业务实际在用；契约：宽容解析该非标结构并正常响应（预期 200）；适用 Kimi-K3 | 按工单原始请求体原样重放（模型名由环境注入，其余字段——系统提示词/用户问题/内嵌 tools 结构——均不改动；采样参数不豁免——默认口径：全局 SAMPLING_PARAMS 覆盖，temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入），单次请求（结构解析为确定性行为，无需连发），断言 HTTP 200（核心——原始报错形态复现即 FAIL）、响应合法 JSON 且 choices 存在、message 有效输出（content 或 tool_calls 非空——宽容解析后文本作答/工具调用响应均为成功形态）；模型真实响应（状态码/响应体全文）断言前打印、失败时同样可见；usage 仅日志；运行日志不含具体模型名（系统提示词正文含模型自我介绍，仅记字符数概要） | P0  |
| K22 | /v1/messages 缓存命中率应与 /v1/chat/completions 基本一致 | 客户问题：相同请求下 Anthropic 协议（/anthropic/v1/messages）前缀缓存命中率始终低于 chat 协议（"缓存始终上不去"）——根因：该链路 system 头部携带 x-anthropic-billing-header: 逐请求动态计费行（字符串/块数组两种 system 形态），前缀缓存要求从位置 0 连续匹配，头部逐请求变化导致整个前缀永不命中；chat 协议无此行、前缀稳定（K15/K16 已验证 ≥90%）；开发修复：入引擎前条件剥离——system 开头是 x-anthropic-billing-header: 行即去掉、其余内容原样保留；适用 GLM-5.3 | 测试要点（用户口径）：同轮等价请求逐轮交替发送 /v1/chat/completions 与 /anthropic/v1/messages 两协议（同轮同问；前缀头部渠道标记行不同——用户指定：剥离计费行后两协议前缀仍从位置 0 分叉，互不命中对方缓存条目，各自建条目/各自命中，messages 冷轮为真冷；标记差异仅数字符，对命中率影响可忽略），统计二者缓存命中率并逐轮比较——第一次请求为冷轮（两协议均无缓存可命中，不参与比较；需热轮才能统计命中率），组级判定（用户指定）：单组失败不中断后续组，5 组中至少 4 组该组全部热轮差值 ≤3 个百分点（用户指定容差）即 PASS、不足 4 组 FAIL；热轮 messages 全量 miss（read=0 且 creation=0）时同轮重发一次鉴别（用户指定）：重发命中→WARN 留痕继续（偶发——疑似多实例路由/条目可见性问题）；仍 miss→该组不符合预期（剥离失效形态，判别力不变）；每请求在 system 头部构造逐请求变化的计费行（值必须变化：静态值修复前前缀也相同、缺陷无法复现=假阴性）；五组不同请求消息即循环 5 次比对（用户口径：每次循环的请求消息尽量不一样）：2 组中文、2 组英文、1 组中英混合，每组前缀 ~8400-12000 tok + 每轮唯一问题 ~330-550 tok，整请求长度尽量超过 8k tokens；覆盖两条剥离代码路径——块数组形态（断点挂 system 块，K3 口径）与字符串形态（断点挂 user 首块，每轮唯一问题置于断点外）；每次循环每协议 1 冷轮 + 2 热轮（用户口径；冷轮不参与比较），共 5 次循环 × 2 协议 × 3 轮 = 30 请求，组间间隔 3 秒（用户指定）；命中率口径：chat=cached_tokens/prompt_tokens（该轮，K16 字段口径）、messages=cache_read/分母（分母按 input_tokens 口径自适应——以同轮 chat prompt_tokens 为参照）；硬断言：①组级判定（用户指定）——单组失败不中断后续组，5 组中至少 4 组该组全部热轮差值 ≤3 个百分点即 PASS、不足 4 组 FAIL（缺陷形态 messages ≈0% vs chat ≈94%，五组全不符合）；②每请求 HTTP 200 且响应正常（chat：choices；messages：usage+content）；热轮 cache_creation>0（前缀逐请求重建=剥离失效直接信号）与双低形态仅日志留痕；运行日志不含具体模型名 | P0  |
| K23 | 孤儿 tool 消息应对齐官方放行并正常消费 | 客户问题（新工单，官方对齐口径）：messages 中 tool 角色消息前无带 tool_calls 的 assistant 消息（孤儿 tool 消息，且请求未定义任何 tools），平台返回 400（"Invalid parameter: messages with role 'tool' must be a response to a preceeding message with 'tool calls'."——type: alaya code error、code: invalid text request——网关层白加的校验）；智谱官方源对同一请求 HTTP 200 正常应答「北京今天天气晴朗，气温18℃」且模型在 reasoning 中实际引用 tool 数据（工具数据被正常消费）；新契约（客户指定）：预期结果同官方一致——此类消息序列不做校验、正常出结果；与 K14 关系：K14 为当时工单口径原始契约（网关校验拒绝 400，保持不变——用户指令），二者输入同类预期相反，平台采纳官方对齐修复后 K14 将 FAIL、其保留/退役由用户决定；适用 GLM-5.3 | 按客户新工单原始请求体还原（messages=[user"查一下北京天气"、assistant"好的，我来为您查询北京天气数据。"（纯文本无 tool_calls——孤儿条件）、tool tool_call_id="call_weather_001" content={"city":"北京","temp_c":18,"condition":"晴"}、user"根据工具返回的数据，用一句话告诉我天气。"]、max_tokens=200、非流式、无 tools/thinking；采样参数不豁免——默认口径：全局 SAMPLING_PARAMS 覆盖，temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入），单次请求（确定性行为，无需连发），断言 HTTP 200（核心——原始 400 拦截形态复现即 FAIL，报文引用原始报错文案）、响应合法 JSON 且 choices 非空、message 有效输出（content 或 tool_calls 非空——官方形态为正常答句）；官方行为细节（输出/推理引用工具数据要素——北京/18/晴）软校验仅日志；finish/usage 仅日志；模型真实响应（状态码/响应体全文）断言前打印 | P0  |
| K24 | 双请求正常响应（思考耗尽预算 low 强度回退） | 客户问题（新工单）：客户两个请求（中文同音词与言部汉字写作题、英文数学题）——temperature=0.0、max_completion_tokens=32768（工单原始字段名）、非流式，期望均正常响应并返回正文；风险形态（用户指定）：默认 max 思考强度下思考可能耗光预算（正文空+finish=length）；适用 GLM-5.3 | 按工单原始请求体还原两请求直发（采样参数豁免——用户指定：两请求体均显式 temperature=0.0，工单体为唯一口径，通过 RAW_SAMPLING_PARAM_TESTS 豁免全局覆盖，top_p/seed 不注入）；第 1 轮默认 max 思考强度（不带 reasoning_effort），有正常正文即通过，断言 HTTP 200、响应合法 JSON 且 choices 非空、message 有效输出（content 或 tool_calls 非空）；耗光形态（正文空+finish=length）按用户指定契约转 reasoning_effort=low（GLM 顶层思考强度参数，K20 口径）重发，断言相同，且仅重测耗光请求（已通过不重测）；正文空且 finish≠length 直接 FAIL；low 回退仍无正文即 FAIL（双强度均未产出——留证交开发）；finish/usage 仅日志；模型真实响应（状态码/响应体全文）断言前打印 | P0  |
| K25 | assistant 历史重复 reasoning_content 字段应被兼容接受 | 客户问题（工单跟进）：多轮对话回填 assistant 历史时，同一条消息携带两个 reasoning_content 字段（两轮历史思考未去重地拼接成同键重复）与上一次请求的正文；客户原始工单还曾因思考内容含 They're/I'm/It's 等英文撇号导致 JSON 破损——正文与思考可能含单引号/双引号/换行等字符，须兼容处理、不影响请求格式（用户指定）；契约（用户指定）：预期不报错、正常响应，第一个 reasoning_content 被第二个覆盖（宽松解析保留最后一个值，K18 修复口径）；适用 GLM-5.3 | 共发三次请求（用户指定，JSON 链式回填——第 1/2 次响应 JSON 作为下一请求输入、思考随历史一并回填；提示词为测试自行设计，工单未携带具体提示词——用户口径仅要求结构）：第 1 次 user 单轮流式要求仅输出 JSON——采集第 1 段思考+第 1 次正文（JSON，作为第 2 次请求输入回填）；第 2 次流式回填第 1 次历史 messages=[assistant(content=第 1 次正文（JSON）, reasoning_content=第 1 次思考), user 追问]（单键经 dict 表达——K18 口径）并要求仅输出 JSON——采集第 2 段思考+第 2 次正文（JSON，作为第 3 次请求输入回填）；第 3 次流式回填 messages=[assistant(content=第 2 次正文（JSON）, reasoning_content=第 1 次思考, reasoning_content=第 2 次思考), user 追问]——重复键无法经 dict 表达，手工拼接 JSON 文本直发，动态值一律 json.dumps 全转义（单/双引号、换行、反斜杠全转义），发送前三重自检（raw body 可被 json.loads 解析、reasoning_content 键出现次数==2、转义回读值一致——回读保留最后一个重复键，模拟服务端宽松解析）；断言第 1/2 次思考与正文均非空（构造数据源，被测环境应开思考）且正文为合法 JSON（JSON 链断裂即场景无法构造 FAIL；容忍 markdown 代码块围栏）、第 3 次 HTTP 200（核心——报错/4xx 复现即 FAIL）+ SSE 事件非空 + 合并正文非空 + finish_reason 合法；耗光回退（K24 口径）：max_tokens=8192 下默认 max 档思考可能耗尽预算（正文空+finish=length）——该形态以 reasoning_effort=low（GLM 顶层思考强度参数，K20 口径）仅重发耗光请求（第 3 次重发构造不变仅加顶层 reasoning_effort 字段——HTTP 200 核心契约首次请求已达成，重复键历史被接受不以正文是否为空转移），断言相同，正文空且 finish≠length 直接 FAIL，low 回退仍无正文即 FAIL（双强度均未产出——留证交开发）；引号覆盖度软观察（三个回填值均无引号/换行字符时 record_warning，不判失败）；采样参数不豁免（默认口径：全局 SAMPLING_PARAMS 覆盖，temperature 无覆盖时回退 0.7、top_p/seed 显式指定时注入）；max_tokens=8192 工单口径三次一致；usage 仅日志；模型真实响应断言前打印 | P0  |
| K26 | 工具 schema 负向前瞻正则应被兼容放行 | 客户问题：工具参数 schema 的 pattern 包含 ^(?!...) 负向前瞻正则——后端编译为 structural_tag 生成约束时底层语法编译器不支持 lookahead：非流式报 400（Failed to compile structural_tag grammar——Lookahead is not supported yet，request id 2026102616110264231215776333070）、流式报 provider_unavailable（upstream_stream_error）；修复（frontend 预处理兼容，非编译器新增 lookahead 支持）：GLM-5.3+glm47 解析器+SGLang、tool_choice=auto、工具未显式 strict、schema 含 ^(?! 开头正则时命中——仅将生成约束工具副本置 strict=false 绕过强制编译，原始 schema/工具描述/格式约束保留；该路径不再由 grammar 强制保证参数满足完整 schema；适用 GLM-5.3 | 按触发形态构造：path 参数 pattern 以 ^(?! 开头（禁止路径穿越 ^(?!.*\.\.).+$）、不显式 strict、tool_choice=auto（显式——对齐触发条件），user 消息自然诱导 write_workspace_file 调用（path 取值合法），非流式+流式各发一次；断言：非流式 HTTP 200（核心——grammar 编译错误复现即 FAIL）+choices 非空+message 结构存在，流式 HTTP 200（核心——provider_unavailable 复现即 FAIL）+SSE 事件非空+至少一个含 choices 数据块；不断言工具被调用（auto 下可正文回答——要点是请求被放行）与参数满足 pattern（兼容绕过明确口径），响应形态宽松留日志；采样参数不豁免（用户指定——不进豁免名单，全局 SAMPLING_PARAMS 覆盖，temperature 无覆盖时回退 0.7、top_p/seed 注入，两个请求一致）；usage 仅日志 | P0  |
| K27 | 历史非法 JSON arguments 应被容忍 | 客户问题（AGDC2-19，codex 客户端 + MCP 工具场景）：模型输出的工具调用 arguments 本身非合法 JSON（两处括号错误——"refId": "A"}] 缺 }、40}}}] 处多 }，上游流式日志证实由模型产生）；客户端执行失败、回放全量历史，服务端校验历史 tool_calls 的 arguments 直接 400（Assistant tool call function.arguments must be valid JSON）——纯服务端问题，与 codex 客户端无本质关系；修复：历史无法解析的 arguments 按字符串保留、不再 400、让模型继续纠正；适用 GLM-5.3 | 复刻客户链路（user→assistant(畸形 arguments 调用，保真浓缩版——两处错误形态与关键结构原样、场景自检必非法)→tool(执行失败结果，协议配对必需)→user 追问修正重试，带 mcp__grafana__update_dashboard 工具定义，非流式，max_tokens=2048），断言 HTTP 200（核心——报错复现即 FAIL）+choices 非空+message 结构存在+模型发起修正工具调用且每条调用 name/id 非空、arguments 为合法 JSON 对象（修正行为——修复目的"让模型继续纠正"）；不断言历史被改写/修复；采样参数不豁免——全局 SAMPLING_PARAMS 覆盖；usage 仅日志 | P0  |

---

## 四、按模型特性的差异化测试点

除通用测试点外，各模型还需要结合当前仓库的已知 passing path 和接口差异做专项验证：

### Qwen 3.5 专项

| #   | 测试点            | 说明                            |
|-----|----------------|-------------------------------|
| Q1  | 混合注意力机制        | 线性注意力 + 标准注意力的切换行为，特别是在超长上下文下 |
| Q2  | 201 语言覆盖       | 抽样测试小语种（泰语、阿拉伯语、斯瓦希里语等）质量     |
| Q3  | 1M Token 扩展上下文 | 验证扩展到 1M tokens 后的质量和性能       |
| Q4  | 早期融合多模态        | 视觉-语言混合推理的一致性（vs 后期融合方案）      |

### Kimi K2.5 专项

| #   | 测试点            | 说明                          |
|-----|----------------|-----------------------------|
| K1  | Agent Swarm 模式 | 多 agent 协作执行复杂任务的稳定性        |
| K2  | 3.2% 激活率       | 极低激活率下的质量保持，边缘 case 是否有性能退化 |
| K3  | 视频理解深度         | 2K 视频多片段理解、时序推理准确度          |
| K4  | 原生 INT4 QAT    | QAT 量化 vs PTQ 量化的质量对比       |

### GLM-5 专项

| #   | 测试点                                    | 说明                                                               |
|-----|----------------------------------------|------------------------------------------------------------------|
| G-1 | `enable_thinking=false` 返回行为           | 当前重点验证显式 `reasoning=null`，且最终 `content` 不混入 explanation，需要持续回归验证 |
| G-2 | forced named `tool_choice` 错误路径        | 明确记录顶层 `error` 的错误形状，防止回归为 silent failure                        |
| G-3 | auto `tool_choice` StructuredOutput 路径 | 持续验证 `tool_choice="auto"` 是否仍是最佳 passing path                    |
| G-4 | 205K 上下文边界                             | 接近上限时的质量、延迟和拒绝策略变化                                               |

### Minimax 2.1 与 2.5 专项

| #   | 测试点                                           | 说明                                                                                                  |
|-----|-----------------------------------------------|-----------------------------------------------------------------------------------------------------|
| M-1 | `enable_thinking=false` 下的 hidden thinking 泄漏 | 当前已知请求可接受，但 `reasoning` 仍可能返回文本，且流式 explanation 也可能混进 `content`，需要比较 `minimax-m21` 与 `minimax-m2.5` |
| M-2 | forced named `tool_choice` 错误路径               | 当前已知 forced named `tool_choice` 可能返回 `500 upstream_error`，需持续量化                                     |
| M-3 | 图片 content parts create / stream              | 与基础 chat 套件对齐，持续验证图片输入的 create / stream 路径                                                          |
| M-4 | `minimax-m21` vs `minimax-m2.5` 稳定性差异         | 比较重复同名 tool call、structured output 和上下文边界等细分行为差异                                                    |

---

## 五、测试执行优先级建议

### P0（上线必测，59 项）

```
A1-A5, A8        基础推理 6 项
B1, B4           高级功能 2 项（B1 思考模式、B4 单工具调用）
B8, B9           结构化输出 2 项
                     多模态 0 项（C 类已降为 P1/P2，仅视觉模型按需评估）
D1, D4, D5, D12  上下文处理 4 项（D4 超长上下文升至 P0，D2/D3/D11 降为 P1）
E1-E8            性能指标 8 项
F1, F4           稳定性 2 项（F1 空输入、F4 特殊字符注入；F2/F3/F5 降为 P1/P2）
G1, G3, G4, G6   API 兼容 4 项（G3 模型列表升至 P0）
H1, H4, H5, H6, H7, H8, H9, H12  Chat Completions API 质量评估 8 项（H2 降为 P1，H8 升至 P0）
                     Completions API 质量评估 0 项（I 类全部降为 P1，仅做选测）
                     clear_thinking 参数行为 0 项（J 类全部降为 P1/P2，仅做选测）
K1-K7, K10-K27  客户问题复现 25 项（均 P0，客户报障必测）
```

总计 6 + 2 + 2 + 0 + 4 + 8 + 2 + 4 + 8 + 0 + 0 + 25 = 61 项。

### P1（选测，60 项）

```
A6, A7, A9-A12              基础推理 6 项
B2, B3, B5, B7, B11         高级功能 5 项
C1, C2, C4, C8, C9, C11     多模态 6 项
D2, D3, D6-D11              上下文处理 8 项
E9-E12                       性能指标 4 项
F2, F5-F8                    稳定性 5 项
G2, G5                       API 兼容 2 项
H2, H3, H10, H11            Chat Completions API 质量评估 4 项
I1-I12                       Completions API 质量评估 12 项
J1, J2, J4, J5, J6, J7       clear_thinking 参数行为 6 项
K8, K9                       客户问题复现 2 项（required 工具调用，按客户工单 P1）
```

### P2（低优，16 项）

```
B6, B10                     高级功能 2 项
C3, C5-C7, C10, C12         多模态 6 项
F3                          稳定性 1 项
                            API 兼容 0 项（G7/G8 已移除，response_format 见 B8/B9，stream 见 A4）
H13                         Chat Completions API 质量评估 1 项
I13                         Completions API 质量评估 1 项
J3, J8, J9, J10, J11        clear_thinking 参数行为 5 项
```