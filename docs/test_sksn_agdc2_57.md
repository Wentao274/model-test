# S. 深空数能 kimi-k3 能力确认测试

## 概述

深空数能工单 AGDC2-57 kimi-k3 能力确认 **38 用例**套件（`tests/test_sksn_agdc2_57.py`，marker `sksn_agdc2_57`）。

数据源（用户指定 2026-11-17）：AGDC2-57 目录两份分析文档——《AGDC2-57-K3官方API响应头与SGLang差异对比》《AGDC2-57-K3模型usage字段说明》。官方行为依据 Kimi 公开文档（Chat Completions API / 上下文缓存最佳实践 / 流式输出指南 / K3 快速开始）与 AGDC2-47 归档样本；本地侧为 SGLang 源码核对结论。

客户 **7 项确认事项** → 用例分组（报告按域展示）：

| 域 | 确认事项 | 用例 |
|----|---------|------|
| C1 缓存写入 | 1. 是否支持缓存写入 | #1-#6（6 条） |
| C2 TTL | 2. 是否支持 1h 缓存；3. 是否支持 TTL（**重点**） | #7-#17（11 条） |
| C3 usage | 4. usage 包含什么字段 | #18-#25（8 条） |
| C4 响应头 | 5. 响应头 | #26-#31（6 条） |
| C5 OpenAI | 6. open ai 支持 | #32-#35（4 条） |
| C6 Anthropic | 7. anthropic 支持 | #36-#38（3 条） |

## 断言口径（用户确认 2026-11-17）

- **硬断言（FAIL）= 协议层**：请求发送异常；基础请求非 200；非流式 JSON 不可解析；SSE 无收束；OpenAI/Anthropic 标准字段缺失；usage 三元组缺失或 `total = prompt + completion` 公式错误；
- **软断言（PASS 仅记录差异）= 能力层**：缓存写入头 / `cache_write_tokens` / `cached_tokens` / 分 TTL 统计 / `Msh-*` 平台身份头 / TTL 内命中 / TTL 过期行为 / 缺省与非法值行为 / Anthropic `cache_creation` 明细——实测行为经 `_sksn_obs` 记录为观察项（observations），用例判 PASS，报告中展示支持/缺口差异；
- 能力请求（缓存/TTL 参数）被 4xx 拒绝属**能力缺口记录**，不判 FAIL（`_sksn_capability_ok` 分流：200 继续结构断言与观察，非 200 记录后 PASS 收尾）。

## 测试点列表

### C1 缓存写入（#1-#6）

| 编号 | 用例 | 硬断言 | 软观察 |
|------|------|--------|--------|
| #1 | mode=write 基础缓存写入 | 200 + JSON + usage 三元组 | 缓存写入头 5m/1h、cache_write_tokens |
| #2 | 写入后二次相同请求命中 | 两次 200 + 三元组 | 第二次 cached_tokens / cache_write_tokens（命中后应不再写入） |
| #3 | 写入与读取字段语义区分 | 200 + 三元组 | cache_write_tokens 与 cached_tokens 分别记录（不得互相冒充） |
| #4 | 无 prompt_cache_options 默认行为 | 200 + 三元组 | 缺省请求下缓存字段/头是否出现（官方未公开，记录） |
| #5 | 三类输入互斥口径 | 两次 200 + 三元组 | cached + write ≤ prompt_tokens 口径记录 |
| #6 | 流式缓存写入最终统计 | 200 + [DONE] + 最终 usage chunk | 最终 usage 缓存读写明细 |

### C2 TTL（#7-#17，重点）

| 编号 | 用例 | 硬断言 | 软观察 |
|------|------|--------|--------|
| #7 | ttl=5m 写入分 TTL 统计 | 200 + 三元组 | 5m 头应计入、1h 头取值 |
| #8 | ttl=1h 写入分 TTL 统计 | 200 + 三元组 | 1h 头应计入、5m 头取值 |
| #9 | ttl=5m TTL 内复用命中 | 两次 200 + 三元组 | 第二次 cached_tokens（TTL 内命中证据） |
| #10 | ttl=1h TTL 内复用命中 | 两次 200 + 三元组 | 第二次 cached_tokens |
| #11 | mode=write 缺省 ttl | 200 + 三元组 | 缺省 TTL 归属（5m 还是 1h 头计入） |
| #12 | ttl=2h 非法枚举 | 请求可达 | 200 放行 / 4xx 拒绝行为记录 |
| #13 | ttl=300 数字类型 | 请求可达 | 同上 |
| #14 | ttl=5M 大写形态 | 请求可达 | 同上 |
| #15 | mode=invalid 非法值 | 请求可达 | 同上 |
| #16 | Anthropic cache_control ttl=1h | 200 + Anthropic 标准字段 | cache_read/cache_creation/cache_creation 明细 |
| #17 | ttl=5m 过期验证（**slow_ttl**，等待 330s） | 三次 200 + 三元组 | TTL 内 vs 窗口外 cached_tokens 对比 |

### C3 usage 字段（#18-#25）

| 编号 | 用例 | 硬断言 | 软观察 |
|------|------|--------|--------|
| #18 | 三元组完整与公式 | 200 + 三元组整数 + total=p+c | usage 顶层字段集合、明细形态 |
| #19 | reasoning 明细 | 200 + 三元组 | completion_tokens_details.reasoning_tokens 取值 |
| #20 | 命中后 cached_tokens | 两次 200 + 三元组 | 第二次 cached_tokens、prompt_tokens_details 形态 |
| #21 | 写入后 cache_write_tokens | 200 + 三元组 | cache_write_tokens 存在性（已知本地缺口） |
| #22 | 流式最终 usage chunk | 200 + [DONE] + choices=[] 且带 usage 的 chunk | 最终 usage 字段集合 |
| #23 | 流式中间 chunk usage 行为 | 200 + [DONE] | 中间 chunk 是否携带 usage（官方：不携带） |
| #24 | 顶层 reasoning_tokens | 200 + 三元组 | 顶层 reasoning_tokens 存在性（本地扩展，官方未列） |
| #25 | null/零/字段省略区分 | 200 + 三元组 | 明细对象 null/省略/零值形态 |

### C4 响应头（#26-#31）

| 编号 | 用例 | 硬断言 | 软观察 |
|------|------|--------|--------|
| #26 | 通用头存在性 | 200 + Content-Type 含 application/json | Date/Content-Length/Connection |
| #27 | Msh 平台身份头 | 200 | Msh-Request-Id/Org-Id/Project-Id/Uid/Gid/Trace-Mode/X-Internal-Adhoc-Canary 逐一记录 |
| #28 | 成功响应缓存写入头 | 200 | 5m/1h 缓存写入头存在性 |
| #29 | 流式 Content-Type | 200 + text/event-stream + [DONE] | 流式响应头集合 |
| #30 | 部署层通用头 | 200 | HSTS/Vary/Set-Cookie（部署层差异） |
| #31 | 限流头出现条件 | 200 | Retry-After/Msh-Cooldown-Seconds/X-Retry-After 在 200 下缺省（官方仅 429 出现；不主动触发限流） |

### C5 OpenAI 协议（#32-#35）

| 编号 | 用例 | 硬断言 | 软观察 |
|------|------|--------|--------|
| #32 | 非流式标准字段 | id 非空 + object=chat.completion + model 非空 + choices 非空 + usage 对象 | — |
| #33 | 流式 chunk 结构 | 首 chunk object=chat.completion.chunk + [DONE] + 正文非空 | — |
| #34 | 错误体结构 | 空 messages 应 4xx | error 外层结构与字段集合（官方 Kimi 风格 vs OpenAI 风格） |
| #35 | message 结构 | message.role=assistant + content 非空 + finish_reason 非空 | — |

### C6 Anthropic 协议（#36-#38）

| 编号 | 用例 | 硬断言 | 软观察 |
|------|------|--------|--------|
| #36 | 非流式标准字段 | id 非空 + type=message + role=assistant + content blocks 非空 + stop_reason + usage.input/output_tokens | thinking 块存在性 |
| #37 | 流式 SSE | message_start + message_stop 收束 + 正文非空 | thinking_delta 事件 |
| #38 | usage 缓存字段 | 200 + Anthropic 标准字段 | cache_read_input_tokens / cache_creation_input_tokens / cache_creation 明细 |

## 运行方式

```bash
# 运行整套 S 套件（含 #17 TTL 过期验证，约 5.5 分钟）
pytest -m sksn_agdc2_57 -v

# 快速跑（排除慢速 TTL 过期验证）
pytest -m "sksn_agdc2_57 and not slow_ttl" -v

# 运行单用例
pytest tests/test_sksn_agdc2_57.py::TestSksnAGDC2_57::test_07_ttl_5m_write -v

# Jenkins：勾选 MARKER_SKSN_AGDC2_57 跑整套
#（S 用例不进 SPECIFIC_TEST 用例选择参数——用户指定 2026-11-17）
```

不进 smoke 集；无 P0/P1/P2 标记（能力确认/差异记录套件）。**默认收集不含 S 用例**（conftest 收集排除与 Jenkinsfile `MARKER_ALL` 排除双层口径）：裸 `pytest` / `pytest -m p0` / `pytest -m lexin_agdc2_65` 等不会执行 S 用例；仅以下方式执行——`pytest -m sksn_agdc2_57`、命令行显式指定 `tests/test_sksn_agdc2_57.py`（或节点）、Jenkins 勾选 `MARKER_SKSN_AGDC2_57`。

## 测试报告

S 套件运行自动生成专用报告（同 L/Z 套件接线模式，能力确认/差异记录样式）：

- **请求录制**（`_sksn_send` 内 `_SKSN_RECORDER`）：每请求一条内存记录——所属用例（栈回溯）、URL/协议 kind（chat/messages）/请求头（鉴权打码）/请求体/状态码/耗时/响应头/响应体全文（SSE 为事件行 join）/发送异常；**能力观察**（`_SKSN_OBS`）：每用例一组观察文本（缓存头/字段存在性、TTL 命中与过期、非法值行为等）；
- **会话末导出与生成**（conftest `pytest_terminal_summary` 接线，无 sksn 节点时零导入零输出）：
  - 录制记录+观察写 `sksn_records.json`（allure-results 同级，`{"records": [...], "obs": {...}}`，可离线重生成）；
  - **纯 sksn 运行**：顶替通用 Markdown 汇总与 `test_reports/` 报告，仅生成 S 套件 HTML + 汇总 MD（输出至 `--summary-report-dir`）；
  - **混合运行**：通用报告照旧，S 套件 HTML/MD 额外生成（lexin/zjxm 行为不变）；
- **HTML 报告**（`base/sksn_html_report.py`）：任务概要 / 测试结果统计（含域分组统计表）/ **客户 7 项确认事项结论表**（每问题对应用例域 + 通过计数 + 观察摘要）/ 用例结果总览（全部 38 用例 + 观察项 + 每请求子行，HTTP 状态中性徽章——4xx 为合法实测）/ 用例明细（左断言口径、右实测观察 + 请求/响应折叠，全量不截断）；
- **汇总 MD**：章节名与通用报告一致（`## 统计汇总` / `## 分类统计` / `## 测试结论` / `## 跳过用例说明`）+ **能力观察清单**（逐用例列出观察项——7 项确认事项答复素材）；
- **请求级 通过/失败 推导**：用例 PASS → 全部请求通过；FAIL → 失败消息「请求 N」定位失败请求；
- **Jenkins**：HTML 报告随 `*.html` 拉取到 `reports/<构建号>/`，检测到即追加为邮件附件——复用 L/Z 套件通用链路，无需额外接线；
- **CLI 离线重生成**：`python -m base.sksn_html_report --alluredir <目录> [--records <json>] [--out-dir <目录>] --model <模型名> --base-url <接入点>`。

## 注意事项

- 套件不计入 README/checkpoints 的「9 大类 × 134 测试点」口径（同 L/Z 套件口径，S 单列）；
- 采样参数豁免：conftest `RAW_SAMPLING_EXEMPT_FILES` 整模块豁免，全局采样覆盖不生效，能力确认请求（含缓存/TTL 参数）原样发送；
- S 用例不进 Jenkinsfile `SPECIFIC_TEST` 用例选择参数（用户指定 2026-11-17）；
- **#17 TTL 过期验证**为慢速用例（`@pytest.mark.slow_ttl`，等待 330 秒）；快速回归可用 `-m "sksn_agdc2_57 and not slow_ttl"` 排除；
- 缓存命中类用例（#2/#5/#9/#10/#20）依赖同一 payload 前缀完全一致；缓存写入最小长度按惯例取 ≥1024 token（套件长输入约 2400 字）；
- Anthropic 协议端点同 lexin 套件先例：`POST {base_url}/anthropic/v1/messages`（`x-api-key` + `anthropic-version: 2023-06-01`）；
- #16/#38 的 Anthropic `cache_control`（含 ttl=1h beta）属能力层——平台 4xx 拒绝时记录能力缺口，用例仍 PASS；
- 能力缺口已知项（来自文档源码核对）：`cache_write_tokens` 字段、`Msh-Usage-Cache-Write-Tokens-5m/1h` 响应头、`Msh-*` 平台身份头在本地 SGLang 引擎均无生成逻辑——首跑预期这些观察项记录「缺失（官方能力缺口记录）」，用例 PASS；
- 测试类内方法按域分组定义（C1→C6），报告展示按 docstring `#N` 数字升序。
