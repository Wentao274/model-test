# Z. 浙江讯盟功能对比失败场景复现测试

## 概述

浙江讯盟工单 AGDC2-61 glm-5.3 功能对比失败场景 **45 用例复现**套件（`tests/test_zjxm_agdc2_61.py`，marker `zjxm_agdc2_61`）。

数据源（用户指定 2026-11-16）：九章 glm-5.3 功能对比报告 20261110（`GLM-5.3 功能测试对比（智谱官方 vs 九章）20261110`，277,381 字节）——报告展开的 **42 个失败用例**全量覆盖（OpenAI Chat Completions 33 条 + OpenAI Responses 9 条）；官方基线同样不通过的 KS-MSG-001 / KS-N-001 / KS-TOOL-009 三条在 20261110 报告中被移除（报告口径：不算供应商问题），后依据九章新 url 功能测试报告 20261116（AGDC2-66，`token-bj11.alayanew.com:26443` 45 条复测）按用户确认 2026-11-17 补入为 **#43-#45 官方异常守护条目**——断言基准取九章复测行为（官方 500/400 不作断言基准），作为守护口径：平台行为与九章复测基线不符即判 FAIL；响应正文/思考内容无明确验证要求时只断非空。

实现口径（用户确认 2026-11-16）：

- 请求按报告「实际传参」原始报文**原样重放**（仅 model 字段运行时替换为部署模型名；RESP-019 缺失 model 不注入；RESP-018 报告原文 assistant content 疑似生成截断为畸形键，按用户确认修正为完整句子）；
- 预期结果**遵循智谱官方行为**（报告智谱官方侧实测基线 run 20261028_191525；官方错误体为 `{"error":{"code","message"}}` 结构，code 为字符串）：
  - 4xx 拒绝类：HTTP 状态码 + error 外层结构 + error.code 三重对齐官方；
  - top_p 差异确认两条（#31/#32）按用户确认取**严格官方口径**断言 200——平台返回 4xx 判失败，作为「九章比官方更严格」的差异暴露（报告口径：不建议平台改、仅差异记录）；
  - Open Responses 协议 9 条官方基线未实测，按报告判定依据（规范口径）：ResponseResource 必填字段取**报告点名 8 项**（completed_at / presence_penalty / frequency_penalty / top_logprobs / max_tool_calls / background / service_tier / safety_identifier）+ object/status/output 基础断言 + 各用例专属断言；
  - RESP-015 image-input 按用户确认以「4xx 且错误体含明确错误信息」判通过（glm-5.3 文本模型，与 VIS-URL-001 官方 400 行为一致）；
  - THK-005 官方 400 即通过；若放行 200，失败信息附加诊断——content 是否泄漏思考原文（字面量检查保留原始 ASCII 形态，展示面用全角 token）；
- 采样参数豁免：conftest `RAW_SAMPLING_EXEMPT_FILES` 整模块豁免（同 test_k / test_lexin 口径），报告原始报文原样发送，不注入采样参数。

## 测试点列表

| 编号 | 用例（报告 ID · 标题） | 协议 | 严重级 | 官方基准 | 重放预期 |
|------|----------------------|------|--------|---------|---------|
| Z1 | CUS-001 · user.content 传 null | chat | 优先整改 | HTTP 400 error.code=1213 | FAIL（缺陷复现：九章放行 200 烧满 200 token） |
| Z2 | REQ-MSG-004 · user.content 空字符串 | chat | 优先整改 | HTTP 400 error.code=1213 | FAIL（缺陷复现：放行 200） |
| Z3 | REQ-MSG-005 · user.content 空数组 | chat | 优先整改 | HTTP 400 error.code=1213 | FAIL（缺陷复现：放行 200） |
| Z4 | THK-004 · thinking.type=adaptive | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（缺陷复现：静默放行 200） |
| Z5 | EFF-101 · reasoning_effort=xhigh | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z6 | EFF-102 · reasoning_effort=medium | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z7 | EFF-103 · reasoning_effort=minimal | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z8 | EFF-104 · reasoning_effort=none | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z9 | EFF-105 · reasoning_effort=ultra | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z10 | ERR-003 · max_tokens=200000 超上限 | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z11 | REQ-MSG-006 · 仅 system 无 user | chat | 优先整改 | HTTP 400 error.code=1214 | FAIL（错误体缺 error 外层） |
| Z12 | THK-003 · thinking.type=disabled | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z13 | THK-005 · disabled 若放行不得泄漏思考原文 | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层；放行时附加泄漏诊断） |
| Z14 | MIG-002 · disabled+reasoning_effort=low 未迁移写法 | chat | 优先整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z15 | RSP-001 · 响应字段集中校验（14 组） | chat | 优先整改 | HTTP 200 + 字段白名单（顶层含 request_id、choice 无 logprobs） | FAIL（缺陷复现：choice 多 logprobs、顶层缺 request_id） |
| Z16 | KS-TOOL-003 · tool_choice 指向不存在函数 | chat | 整改 | HTTP 400 error.code=1210 | FAIL（错误体缺 error 外层） |
| Z17 | OUT-012 · max_tokens=0 越下界 | chat | 整改 | HTTP 400 error.code=1210 | FAIL（缺陷复现：放行 200） |
| Z18 | OUT-013 · stop 传字符串 | chat | 整改 | HTTP 400 error.code=400（JSON 反序列化失败透传） | FAIL（缺陷复现：静默当单元素数组、正文空） |
| Z19 | KS-ROB-003 · assistant content 为 list | chat | 整改 | HTTP 400 error.code=1214 | FAIL（缺陷复现：500 内部异常） |
| Z20 | KS-ROB-011 · system content 为 list | chat | 整改 | HTTP 400 error.code=1214 | FAIL（缺陷复现：500 内部异常） |
| Z21 | KS-ROB-019 · user content 为 list | chat | 整改 | HTTP 400 error.code=1214（报告口径 200/4xx 均可、不得 5xx） | FAIL（缺陷复现：500 内部异常） |
| Z22 | KS-ROB-020 · user content 缺失 | chat | 建议整改 | HTTP 400 error.code=1213 | FAIL（缺陷复现：放行 200） |
| Z23 | CONV-RID-005 · request_id 长度 5 | chat | 建议整改 | HTTP 400 error.code=1214（minLength 6） | FAIL（缺陷复现：放行 200） |
| Z24 | CONV-RID-065 · request_id 长度 65 | chat | 建议整改 | HTTP 400 error.code=1214（maxLength 64） | FAIL（缺陷复现：放行 200） |
| Z25 | CONV-UID-005 · user_id 长度 5 | chat | 建议整改 | HTTP 400 error.code=1214（minLength 6） | FAIL（缺陷复现：放行 200） |
| Z26 | CONV-UID-129 · user_id 长度 129 | chat | 建议整改 | HTTP 400 error.code=1214（maxLength 128） | FAIL（缺陷复现：放行 200） |
| Z27 | KS-ROB-023 · role 为空串 | chat | 建议整改 | HTTP 400 error.code=1214 | FAIL（错误体缺 error 外层） |
| Z28 | KS-ROB-025 · role 为非法值 | chat | 建议整改 | HTTP 400 error.code=1214 | FAIL（错误体缺 error 外层） |
| Z29 | KS-ROB-026 · role 缺失 | chat | 建议整改 | HTTP 400 error.code=1214 | FAIL（错误体缺 error 外层） |
| Z30 | KS-ROB-027 · role 为空白串 | chat | 建议整改 | HTTP 400 error.code=1214 | FAIL（错误体缺 error 外层） |
| Z31 | KS-SMP-002 · top_p=1.1 官方接受 | chat | 差异确认 | HTTP 200（严格官方口径，用户确认） | FAIL（差异暴露：平台 400 更符合文档，不建议改） |
| Z32 | SMP-TOPP-005 · top_p=1.5 官方接受 | chat | 差异确认 | HTTP 200（严格官方口径，用户确认） | FAIL（差异暴露：平台 400 更符合文档，不建议改） |
| Z33 | VIS-URL-001 · 图片传公网 URL | chat | 建议整改 | HTTP 400 error.code=1210（文本模型拒绝图片） | FAIL（错误体缺 error 外层） |
| Z34 | RESP-011 · Open Responses 基础响应 | responses | 整改 | 200 + ResponseResource 8 必填字段 + completed | FAIL（缺陷复现：缺 8 必填字段） |
| Z35 | RESP-012 · Open Responses 流式事件 | responses | 整改 | SSE 逐事件 schema + 事件内 response 必填字段 + completed 收束 | FAIL（缺陷复现：事件内 response 缺必填字段） |
| Z36 | RESP-013 · Open Responses system 消息 | responses | 整改 | 200 + schema + completed | FAIL（缺陷复现：缺 8 必填字段） |
| Z37 | RESP-014 · Open Responses 工具调用 | responses | 整改 | 200 + schema + output 含 function_call | FAIL（缺陷复现：缺 8 必填字段） |
| Z38 | RESP-016 · Open Responses 多轮历史 | responses | 整改 | 200 + schema + completed + 用到历史信息 | FAIL（缺陷复现：缺 8 必填字段） |
| Z39 | RESP-017 · Open Responses assistant phase 历史 | responses | 建议整改 | 200 + schema + completed（phase 被接受） | FAIL（缺陷复现：缺 8 必填字段） |
| Z40 | RESP-015 · Open Responses 图片输入 | responses | 待确认 | 4xx + 错误信息明确（文本模型，用户确认判通过） | PASS（九章 400 拒绝为预期行为；错误体外层为附加要求） |
| Z41 | RESP-018 · Open Responses 上下文压缩 compact | responses | 建议整改 | 200 + object=response.compaction + output 含 compaction 条目 | FAIL（缺陷复现：404 端点未实现） |
| Z42 | RESP-019 · 压缩缺 model 被拒绝 | responses | 建议整改 | 400/422（缺失必填 model 拒绝） | FAIL（缺陷复现：404 端点未实现） |
| Z43 | KS-MSG-001 · messages 数组含 null 元素 | chat | 官方异常 | HTTP 400 error.code=1214（九章复测基线；官方 500 异常不作基准） | PASS（守护：400 + error 外层 + code 1214） |
| Z44 | KS-N-001 · n=0 流式放行 | chat | 官方异常 | HTTP 200 流式收束（双方一致放行，报告判跳过） | PASS（守护：200 + [DONE] + 正文/思考非空） |
| Z45 | KS-TOOL-009 · 工具 schema 含 \p{L} Unicode 正则 pattern | chat | 官方异常 | HTTP 200 放行（九章复测基线；官方 400 过度拒绝不作基准） | PASS（守护：200 + 正文/思考非空） |

统计：45 用例 45 个请求（每用例单请求）。重放预期口径（分两段）——Z1-Z42（42 失败场景）：20261110 渠道原状下除 Z40（4xx 判通过）外全部 FAIL（缺陷复现/差异暴露），渠道修复对齐官方后 42/42 全部 PASS；Z43-Z45（官方异常守护）：预期始终 PASS（守护九章复测基线，平台行为偏离基线即 FAIL）。

## 运行方式

```bash
# 运行整套 Z 套件
pytest -m zjxm_agdc2_61 -v

# 运行单用例
pytest tests/test_zjxm_agdc2_61.py::TestZjxmAGDC2_61::test_01_chat_user_content_null -v

# Jenkins：勾选 MARKER_ZJXM_AGDC2_61 跑整套
#（Z 用例不进 SPECIFIC_TEST 用例选择参数——用户指定 2026-11-16）
```

不进 smoke 集；无 P0/P1/P2 标记（严重级沿用报告口径：优先整改/整改/建议整改/差异确认/待确认）。**默认收集不含 Z 用例**（conftest 收集排除与 Jenkinsfile `MARKER_ALL` 排除双层口径，2026-11-16 用户指定）：裸 `pytest` / `pytest -m p0` / `pytest -m lexin_agdc2_65` 等不会执行 Z 用例；仅以下方式执行——`pytest -m zjxm_agdc2_61`、命令行显式指定 `tests/test_zjxm_agdc2_61.py`（或节点）、Jenkins 勾选 `MARKER_ZJXM_AGDC2_61`（Jenkins「全部测试」`MARKER_ALL` 不含 Z）。

## 测试报告

Z 套件运行自动生成专用报告（同 L 套件接线模式，样式为九章对比报告风格——「智谱官方预期 vs 实测」两侧对比）：

- **请求录制**（`_zjxm_send` 内 `_ZJXM_RECORDER`）：每请求一条内存记录——所属用例（栈回溯取 `test_*` 帧名）、URL/协议 kind（chat/responses/compact）/请求头（鉴权值打码：前4+****+后4）/请求体/状态码/耗时/响应头/响应体全文（SSE 为事件行 join）、发送异常；
- **会话末导出与生成**（conftest `pytest_terminal_summary` 接线，stats 前置隔离——无 zjxm 节点时零导入零输出）：
  - 录制记录写 `zjxm_records.json`（allure-results 同级，可离线重生成）；
  - **纯 zjxm 运行**：顶替通用 Markdown 汇总与 `test_reports/` 报告，仅生成 Z 套件 HTML + 汇总 MD（输出至 `--summary-report-dir`）；
  - **混合运行**（zjxm + lexin / zjxm + 通用用例）：通用报告照旧，Z 套件 HTML/MD 额外生成（lexin 行为不变）；
- **HTML 报告**（`base/zjxm_html_report.py`，stone 主题对比样式）：任务概要 / 测试结果统计（含严重级统计表）/ 用例结果总览（全部 45 用例 + 官方基准列 + 每请求子行）/ 用例明细（每用例左右两栏——左侧智谱官方预期（官方基准/断言口径），右侧实测（断言结果 + 请求头/请求体/响应头/响应体折叠，全部 HTML 转义、报文全量不截断））；
- **汇总 MD**：章节名与通用报告一致（`## 统计汇总` / `## 分类统计` / `## 测试结论` / `## 跳过用例说明`），供 Jenkins 邮件正文提取（纯 zjxm 运行经回落 `*.md` 选取）；
- **请求级 通过/失败 推导**：用例 PASS → 全部请求通过；FAIL/BROKEN → 失败消息「请求 N」定位失败请求（之前的通过、之后的未执行）；
- **Jenkins**：HTML 报告随 `*.html` 拉取到 `reports/<构建号>/`，检测到即追加为邮件附件（`*.md` 附件始终存在）——均复用 L 套件通用链路，无需额外接线；
- **CLI 离线重生成**：`python -m base.zjxm_html_report --alluredir <目录> [--records <json>] [--out-dir <目录>] --model <模型名> --base-url <接入点>`。

## 断言口径

断言基准 = 智谱官方行为（报告智谱官方侧实测 + Open Responses 规范口径）：

| 断言 | 判定 |
|------|------|
| 4xx 拒绝类（Z1-Z14、Z16-Z30、Z33） | HTTP 400 + `error` 外层结构（`{"error":{"code","message"}}`）+ `error.code` 对齐官方（1213/1214/1210/400） |
| 200 类（Z15、Z31、Z32） | HTTP 200 + 正文非空；Z15 另做 14 组字段白名单逐组校验（顶层/choice/message/usage 键集合，失败不短路） |
| Responses 非流式（Z34、Z36-Z39） | HTTP 200 + ResponseResource 报告点名 8 必填字段 + object=response + status=completed + output 非空（+ 各用例专属断言） |
| Responses 流式（Z35） | SSE 逐事件 type+sequence_number；事件内 response 8 必填字段；response.completed 收束 + status=completed + output 非空 + 正文非空 |
| Responses 图片输入（Z40） | 4xx + 错误体含 `error` 外层与明确错误信息（用户确认判通过口径） |
| compact 端点（Z41/Z42） | Z41：HTTP 200 + object=response.compaction + output 含 type=compaction 条目；Z42：HTTP 400/422（缺 model 拒绝） |
| THK-005（Z13） | 400 即通过（含结构断言）；若放行 200，失败信息附加诊断——content 是否泄漏思考原文（原始 ASCII 字面量检查，展示面全角） |
| 官方异常守护（Z43-Z45） | 断言基准 = 九章新 url 复测报告 20261116 实测行为（官方 500/400 不作基准）：Z43 HTTP 400 + error 外层 + code=1214；Z44 HTTP 200 + SSE [DONE] 收束 + 正文非空 + 思考非空；Z45 HTTP 200 + 正文非空 + 思考非空（tool_calls 属模型决策不硬断，九章实测调用了 skillhub_install） |

## 预期结果

- **首跑（20261110 渠道原状）**：41 失败（缺陷复现 39 + 差异暴露 2）+ 1 通过（Z40 image-input 4xx 判通过）——与九章报告 20261110 失败清单一致即为复现成立（Z31/Z32 为报告口径「差异确认·不建议改」的严格官方差异暴露）；Z43-Z45 为 2026-11-17 补入，无首跑历史；
- **九章新 url 复测现状（2026-11-16，45 用例按套件断言基准）**：预期 **32 通过 / 13 失败**——13 条失败与复测报告 ok=False 集合一致：Z15（RSP-001：usage.details 多 audio_tokens/accepted_prediction_tokens/rejected_prediction_tokens、message 多 refusal/annotations，字段白名单断言暴露）、Z18（OUT-013）、Z2/Z3（REQ-MSG-004/005）、Z34-Z40（RESP-011~017 缺 ResponseResource 必填字段或 4xx、RESP-015 200 放行按用户口径判 FAIL、RESP-018/019 compact 端点 501 未实现）；Z43-Z45 复测行为与九章复测基线一致，预期 PASS；其余 29 条（错误体外层、4xx 对齐组、top_p 差异确认、ID 边界等）复测已修复，作为回归守护；
- **渠道修复对齐官方后**：45/45 全部 PASS（其中 Z31/Z32 需平台放开 top_p 越界值或与用例库确认豁免口径）。

## 注意事项

- 套件不计入 README/checkpoints 的「9 大类 × 134 测试点」口径（同 L 套件口径，Z 单列）；
- 采样参数豁免：conftest `RAW_SAMPLING_EXEMPT_FILES` 整模块豁免，全局采样覆盖不生效，报告原始报文原样重放（Z43-Z45 同口径，20261116 复测报告报文原样）；
- Z 用例不进 Jenkinsfile `SPECIFIC_TEST` 用例选择参数（用户指定 2026-11-16，含 Z43-Z45）；
- 官方基线 run 20261028_191525 未覆盖 OpenAI Responses 协议（19 条），Z34-Z42 按报告判定依据（openresponses 规范口径）断言——官方侧可自行复跑补齐对比（报告左侧地址与请求体可复跑）；
- Z43-Z45 断言基准 = 九章复测行为而非官方行为（官方 500 内部错误/400 过度校验属基线异常），docstring 严重级统一为「官方异常」——失败语义为「守护基线偏离」，与 Z1-Z42 的「缺陷复现」区分（HTML/MD 报告结论分类已区分）；
- CONV-RID-065（Z24）/CONV-UID-129（Z26）越界字符串按 20261116 复测报告精确长度重放（65/129 字符，运行时程序化构造）；
- RESP-018 请求报文按用户确认修正报告原文的疑似截断（畸形键还原为完整 assistant content 句子）；
- 测试类内方法按功能分组定义（空输入/thinking/边界/结构与 role/ID 长度/工具与多模态/差异确认/字段校验/Responses 协议/官方异常守护），报告展示按 docstring `#N` 数字升序（与九章报告用例顺序一致）。
