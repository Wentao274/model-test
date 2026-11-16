# L. 河南乐信客户卷子重放测试

## 概述

河南乐信工单 AGDC2-62/AGDC2-65 glm-5.3 客户卷子 72 用例**全量重放**套件（`tests/test_lexin_agdc2_65.py`，marker `lexin_agdc2_65`）。

数据源（用户确认 2026-11-13）：平台「测试结果报文详情」全量导出——运行 #432（glm-5.3-glm/glm5.3 #202611131640，2026-11-13 16:40 运行，54 通过/18 失败），覆盖 72 用例共 142 个请求的完整请求报文、逐请求断言与官方基准。用例编号与平台全量编号一致（#1-#15、#18-#74；#16/#17 平台未收录）。

实现口径：

- 142 个请求体全部**原样内嵌**重放（仅 model 字段运行时替换为部署模型名；#39 缺失 model / #40 model=null / #41 空 JSON {} 不注入）；
- 断言基准 = 平台记录官方基准：16:40 运行 18 个失败用例为缺陷复现（渠道修复对齐官方前预期 FAIL），54 个通过用例为回归守护（应 PASS）；
- #1-#3 缓存命中聚合：请求命中率与 Token 命中率 ≥ 阈值 69% 为硬断言，逐请求 cached_tokens 命中仅日志记录；
- 采样参数豁免：conftest `RAW_SAMPLING_EXEMPT_FILES` 整模块豁免（同 test_k 口径），全局采样覆盖不生效。

## 测试点列表

| 编号 | 用例（run-432 标题） | 协议 | 请求数 | 16:40 结果 | 重放预期 |
|------|--------------------|------|-------|-----------|---------|
| L1 | chat-缓存命中-尾部变化 | chat | 20 | 成功 | PASS（回归守护） |
| L2 | chat-缓存命中-多轮对话 | chat | 20 | 成功 | PASS（回归守护） |
| L3 | chat-缓存命中-重复请求 | chat | 14 | 成功 | PASS（回归守护） |
| L4 | chat-思考控制-多场景 | chat | 4 | 失败 | FAIL（缺陷复现） |
| L5 | chat-JSON格式输出验证-多场景 | chat | 2 | 成功 | PASS（回归守护） |
| L6 | chat-stop参数生效-多场景 | chat | 1 | 成功 | PASS（回归守护） |
| L7 | chat-采样参数-多场景 | chat | 2 | 成功 | PASS（回归守护） |
| L8 | chat-工具调用-多场景 | chat | 1 | 成功 | PASS（回归守护） |
| L9 | chat-输出tokens校验-多场景 | chat | 1 | 成功 | PASS（回归守护） |
| L10 | 没有返回正常报错，而是多包了一层data，导致客户无法正常解析错误信息 | chat | 1 | 成功 | PASS（回归守护） |
| L11 | 供应商上游模型服务内部处理超时 | chat | 1 | 成功 | PASS（回归守护） |
| L12 | stop 列表 6 项超限被放行，官方拒绝 | chat | 1 | 成功 | PASS（回归守护） |
| L13 | top_logprobs=5 | chat | 1 | 成功 | PASS（回归守护） |
| L14 | msg 协议关闭思考 | chat | 1 | 失败 | FAIL（缺陷复现） |
| L15 | json_schema(strict) 输出不合规，官方合规 | chat | 1 | 成功 | PASS（回归守护） |
| L18 | stop 列表 6 项超限被放行 | chat | 1 | 成功 | PASS（回归守护） |
| L19 | top_logprobs=5 | chat | 1 | 成功 | PASS（回归守护） |
| L20 | msg 协议 thinking.type=disabled 被放行 | chat | 1 | 失败 | FAIL（缺陷复现） |
| L21 | json_schema(strict) 输出不合规 | chat | 1 | 成功 | PASS（回归守护） |
| L22 | `enable_thinking=false` 应拒却 200 放行 | chat | 1 | 失败 | FAIL（缺陷复现） |
| L23 | responses 端点空 input 未拒 | responses | 1 | 失败 | FAIL（缺陷复现） |
| L24 | messages 协议 enable_thinking=false 被过度拒绝，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L25 | messages 协议 chat_template_kwargs 被过度拒绝，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L26 | messages 协议 reasoning_effort=none 被过度拒绝，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L27 | messages 协议 reasoning_effort=minimal 被过度拒绝，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L28 | messages 协议 reasoning_effort=low 被过度拒绝，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L29 | messages 协议 reasoning_effort=high 被过度拒绝，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L30 | messages 协议 reasoning_effort=max 被过度拒绝，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L31 | messages 协议 budget_tokens 未实现被拒，官方支持 | messages | 1 | 成功 | PASS（回归守护） |
| L32 | chat 协议 budget_tokens 未实现被拒，官方支持 | chat | 1 | 成功 | PASS（回归守护） |
| L33 | /v1/messages 响应缺 thinking 内容块 | messages | 1 | 成功 | PASS（回归守护） |
| L34 | chat stream=字符串true 被拒/崩溃，官方真值转换接受 | chat | 1 | 成功 | PASS（回归守护） |
| L35 | chat stream=1 被拒/崩溃，官方接受 | chat | 1 | 成功 | PASS（回归守护） |
| L36 | chat stream=0 被拒/崩溃，官方接受 | chat | 1 | 成功 | PASS（回归守护） |
| L37 | messages stream=数字1 被拒/崩溃，官方接受 | messages | 1 | 成功 | PASS（回归守护） |
| L38 | responses stream=null 被拒/崩溃，官方接受 | responses | 1 | 成功 | PASS（回归守护） |
| L39 | 缺失 model 字段被拒，官方 200(体内error) | chat | 1 | 成功 | PASS（回归守护） |
| L40 | model=null 被拒，官方 200(体内error) | chat | 1 | 成功 | PASS（回归守护） |
| L41 | 请求体为空 JSON {} 被拒，官方 200(体内error) | chat | 1 | 成功 | PASS（回归守护） |
| L42 | messages[0].content 为空字符串，官方拒绝 | chat | 1 | 成功 | PASS（回归守护） |
| L43 | responses 缺失 Authorization 头，官方 200(体内error) | responses | 1 | 成功 | PASS（回归守护） |
| L44 | responses 无效 Token，官方 200(体内error) | responses | 1 | 成功 | PASS（回归守护） |
| L45 | messages 图片输入被拒，官方解析计费 | messages | 1 | 成功 | PASS（回归守护） |
| L46 | messages 音频输入被拒，官方忽略(NO_MEDIA) | messages | 1 | 失败 | FAIL（缺陷复现） |
| L47 | messages 坏 base64 被拒，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L48 | messages 多轮媒体被拒，官方解析 | messages | 1 | 成功 | PASS（回归守护） |
| L49 | messages流式 图片被拒，官方解析 | messages | 1 | 成功 | PASS（回归守护） |
| L50 | messages流式 音频被拒，官方忽略 | messages | 1 | 失败 | FAIL（缺陷复现） |
| L51 | messages流式 坏 base64 被拒，官方忽略 | messages | 1 | 成功 | PASS（回归守护） |
| L52 | messages流式 多轮媒体被拒，官方解析 | messages | 1 | 成功 | PASS（回归守护） |
| L53 | responses 图片被拒，官方接受(疑似丢弃媒体) | responses | 1 | 成功 | PASS（回归守护） |
| L54 | responses 音频被拒，官方忽略(NO_MEDIA) | responses | 1 | 成功 | PASS（回归守护） |
| L55 | responses 坏 base64 被拒，官方忽略 | responses | 1 | 成功 | PASS（回归守护） |
| L56 | responses 多轮媒体被拒，官方解析 | responses | 1 | 成功 | PASS（回归守护） |
| L57 | responses流式 图片被拒，官方接受 | responses | 1 | 成功 | PASS（回归守护） |
| L58 | responses流式 音频被拒，官方忽略 | responses | 1 | 成功 | PASS（回归守护） |
| L59 | responses流式 坏 base64 被拒，官方忽略 | responses | 1 | 成功 | PASS（回归守护） |
| L60 | responses流式 多轮媒体被拒，官方解析 | responses | 1 | 成功 | PASS（回归守护） |
| L61 | messages 协议顶层 cache_control 非法值被过度拒绝，官方忽略 | messages | 1 | 失败 | FAIL（缺陷复现） |
| L62 | responses 协议顶层 reasoning_effort=none 无思考输出，官方仍返回思考内容 | responses | 1 | 失败 | FAIL（缺陷复现） |
| L63 | /v1/messages 开启思考时响应缺 thinking 内容块 | messages | 5 | 成功 | PASS（回归守护） |
| L64 | chat 协议关闭思考参数被过度放行，官方拒绝 | chat | 3 | 失败 | FAIL（缺陷复现） |
| L65 | messages 协议 thinking.type=disabled 被过度放行，官方拒绝 | messages | 5 | 成功 | PASS（回归守护） |
| L66 | responses 协议思考开关 | responses | 5 | 失败 | FAIL（缺陷复现） |
| L67 | DNS 解析失败 | chat | 1 | 失败 | FAIL（缺陷复现） |
| L68 | 系统拦截，上游断开连接 | chat | 1 | 成功 | PASS（回归守护） |
| L69 | chat reasoning_effort=none 关闭思考未明确拒绝 | chat | 1 | 失败 | FAIL（缺陷复现） |
| L70 | chat reasoning_effort=none 关闭思考未明确拒绝(2048) | chat | 1 | 失败 | FAIL（缺陷复现） |
| L71 | resp reasoning.effort=none 关闭思考未明确拒绝(2048) | responses | 1 | 失败 | FAIL（缺陷复现） |
| L72 | resp reasoning.effort=none 关闭思考未明确拒绝 | responses | 1 | 失败 | FAIL（缺陷复现） |
| L73 | resp reasoning.effort=none 关闭思考未明确拒绝(4096) | responses | 1 | 失败 | FAIL（缺陷复现） |
| L74 | messages 顶层非法 cache_control 处置 | messages | 1 | 失败 | FAIL（缺陷复现） |

统计：72 用例，142 个请求；16:40 运行通过 54（回归守护，重放应 PASS）/ 失败 18（缺陷复现，渠道修复对齐官方前预期 FAIL：L4、L14、L20、L22、L23、L46、L50、L61、L62、L64、L66、L67、L69-L74）。

## 运行方式

```bash
# 运行整套 L 套件
pytest -m lexin_agdc2_65 -v

# 运行单用例
pytest tests/test_lexin_agdc2_65.py::TestLexinAGDC2_65::test_01_chat_logic_basic -v

# Jenkins：勾选 MARKER_LEXIN_AGDC2_65 跑整套，或在用例选择参数中指定单用例
#（Jenkinsfile 已注册 72 条单用例 choice，与方法名一一对应）
```

不进 smoke 集；套件首跑观察期，无 P0/P1/P2 标记。**默认收集不含 L 用例**（conftest 收集排除与 Jenkinsfile `MARKER_ALL` 排除双层口径，2026-11-13 用户指定）：裸 `pytest` / `pytest -m p0` 等不会执行 L 用例；仅以下方式执行——`pytest -m lexin_agdc2_65`、命令行显式指定 `tests/test_lexin_agdc2_65.py`（或节点）、Jenkins 勾选 `MARKER_LEXIN_AGDC2_65`、或 `SPECIFIC_TEST` 点名（Jenkins「全部测试」`MARKER_ALL` 不含 L）。

## 测试报告（用户确认 2026-11-15）

L 套件运行自动生成专用报告（区别于 a-h/K 套件的通用 Markdown 汇总）：

- **请求录制**（`_lexin_send` 内 `_LEXIN_RECORDER`）：每请求一条内存记录——所属用例（栈回溯取 `test_*` 帧名）、URL/协议 kind/请求头（鉴权值打码：前4+****+后4）/请求体/状态码/耗时/响应头/响应体全文（SSE 为事件行 join）、发送异常；
- **会话末导出与生成**（conftest `pytest_terminal_summary` 接线）：
  - 录制记录写 `lexin_records.json`（allure-results 同级，可离线重生成）；
  - **纯 lexin 运行**（`-m lexin_agdc2_65` / 点名单用例）：**顶替**通用 Markdown 汇总与 `test_reports/` 报告，仅生成乐信 HTML + 乐信汇总 MD（输出至 `--summary-report-dir`）；
  - **混合运行**：通用报告照旧，乐信 HTML/MD 额外生成；
- **HTML 报告**（`base/lexin_html_report.py`，与官方平台「测试任务报告」导出同构）：任务概要 / 测试结果统计 / 用例结果总览（全部 72 用例 + 每请求子行）/ 用例明细（用例说明 + 断言结果 + 每请求请求头/请求体/响应头/响应体折叠，全部 HTML 转义、报文全量不截断）；
- **汇总 MD**：章节名与通用报告一致（`## 统计汇总` / `## 分类统计` / `## 测试结论` / `## 跳过用例说明`），供 Jenkins 邮件正文提取；
- **请求级 通过/失败 推导**：用例 PASS → 全部请求通过；FAIL/BROKEN → 失败消息「请求 N」定位失败请求（之前的通过、之后的未执行）；无编号命中（发送异常形态）→ 首请求失败、其余未执行；
- **Jenkins**：HTML 报告随 `*.html` 拉取到 `reports/<构建号>/`，检测到即追加为邮件附件（`*.md` 附件始终存在）；
- **CLI 离线重生成**：`python -m base.lexin_html_report --alluredir <目录> [--records <json>] [--out-dir <目录>] --model <模型名> --base-url <接入点>`。

## 断言口径

断言基准 = 平台 run-432 记录的官方基准，逐请求断言 Code 语义：

| 断言 Code | 判定 |
|----------|------|
| `http_status_NNN`（硬） | HTTP 状态码 == 官方基准 |
| `official_response_match`（err 位硬） | 响应体含非空 error 键 = 1；渠道扁平 {code,message} / responses error:null 形态 = 0；content/reasoning/logprobs 位软口径仅日志（平台「不判失败」同款） |
| `thinking_fields_ok`（硬） | 返回思考字段且 content == "OK" |
| `usage_triple`（硬） | prompt/completion/total 三元组完整 |
| `usage_complete`（硬） | prompt/completion 字段完整 |
| `sse_content_present`（硬） | SSE 以 [DONE]/message_stop 收束且 content 非空 |
| `stream_format`（硬） | SSE 收束 + finish_reason=stop + content 非空 + 含 usage |
| `stop_param_effective_any`（硬） | finish_reason == "stop" |
| `tokens_within_limit`（硬） | completion_tokens ≤ 请求上限 |
| `content_absent`（硬） | 响应不含 content（工具调用场景） |
| `cache_hit_rate` / `cache_token_hit_rate` | 用例级聚合硬断言 ≥ 69%（#1-#3）；请求级仅日志软记录 |

## 特殊用例说明

- **#1/#2/#3 缓存命中**：分别为 20/20/14 个约 41KB 请求（#1 各请求仅尾部「随机数」不同、#2 递增长文 41859→45188、#3 逐请求原样回放 X-Cache-Tag 头），按序重放后聚合断言请求命中率与 Token 命中率 ≥ 69%（平台记录基准：100.0% / 99.8%）；
- **#43** 缺失 Authorization 头裸发（auth=omit）；**#44** 按记录回放无效 Token `invalid-token-for-test`（auth=invalid）；
- **#39/#40/#41** 请求体无有效 model 字段，不注入模型名（isinstance 守卫为 False），原样重放验证官方 200(体内error) 形态；
- **#8** 工具调用场景断言响应不含 content；**#9** completion_tokens ≤ 上限 16；**#5** SSE 格式四合一硬断言；**#6/#7** usage 完整性 + stop 生效；
- **#67/#68/#10** 大报文用例（原始导出报文约 467KB/298KB/159KB）；
- 注：#14/#20 平台标题含「msg 协议」，但 run-432 导出报文实际重放端点为 chat（以导出报文为准，测试按实际端点重放）。

## 预期结果

- **首跑（渠道未修复）**：54 通过（回归守护 PASS）+ 18 失败（缺陷复现 FAIL，与 16:40 运行一致即为复现成立）；
- **渠道修复对齐官方后**：72/72 全部 PASS；
- 缓存聚合三项若低于 69% 阈值则硬失败（前缀缓存缺陷信号）。

## 注意事项

- 套件不计入 README/checkpoints 的「9 大类 × 134 测试点」口径（用户口径 2026-11-13，L 单列）；
- 采样参数豁免：conftest `RAW_SAMPLING_EXEMPT_FILES` 整模块豁免，全局采样覆盖不生效，报文参数原样重放；
- 单次全量运行耗时显著（142 请求，含多组长提示文与大报文）；
- 测试方法名与 Jenkinsfile 用例选择参数一一对应（保持现名，不随平台标题变动）。
