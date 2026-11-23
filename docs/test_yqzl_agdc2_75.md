# Y. 杭州耘擎智联 kimi-k3 功能测试报告重放

## 概述

杭州耘擎智联工单 AGDC2-75 kimi-k3 功能测试报告 **239 用例重放**套件（`tests/test_yqzl_agdc2_75.py`，marker `yqzl_agdc2_75`）。

数据源（用户指定 2026-11-23）：九章 kimi-k3 测试报告 `九章kimi-k3测试报告_20261119-192419.html`（7.9MB，239 个 case-detail section）——用例定义经程序化提取至 **`tests/data/yqzl_agdc2_75_cases.json`**（id/标题/类别/总判定/场景期望/逐项判定/每请求 payload 与实测状态/kind/流式/auth/curl URL；**提取产物，勿手工编辑**）。

报告构成与总判定分布：

| 维度 | 内容 |
|------|------|
| 类别 | 基础响应（BASIC/PARAM/REASON/AUTH/BUDGET）、JSON 模式、工具选择与 Agent（TOOL/AGENT/STRICT）、长上下文与记忆（MEMORY/CONTEXT/REPEAT/HISTORY）、类型/角色/content 校验（EX-TYPE/EX-ROLE/EX-CONTENT/EX-EFFORT/EX-THINK）、输出边界（EX-OUT/EX-LOGPROBS/EX-STOP/EX-MODEL）、Responses 协议（RESP-\*）、缓存协议矩阵（PROTO-\* 72 条 + CACHE-TRUTH + EX-CACHE + TTL）、视觉与文件（VISION/FILES） |
| 总判定 | PASS 123 / REVIEW 82 / FAIL 33 / SKIP 1 |
| 协议 | chat 175 / responses 35 / messages（Anthropic）28 / compact 1 |
| 请求数 | 单请求为主；多请求组按序全部重放（AGENT-multi 3 轮、CACHE-REPEAT/TTL/缓存组 2 轮） |

## 断言口径（用户确认 2026-11-23）

- **请求**：按报告「实际请求参数」**原样重放**（仅 model 字段运行时替换为部署模型名；超长上下文原文原样保留；采样参数豁免——conftest `RAW_SAMPLING_EXEMPT_FILES` 整模块豁免，不注入采样参数）；
- **断言基准 = 报告「规范要求 / 场景期望」与「逐项判定」清单**（用户口径：报告里有预期先按报告行为断言）：
  - 逐项判定文本经**映射器**转为可执行断言（HTTP 状态/结构字段/流式收束/工具调用/缓存头与命中/needle 读取等约 50 类规则）；
  - **记录式判定项**（报告明示「记录 2xx/4xx 行为」「缺少可比性」「观察实际行为」）只记录不判；
  - **未映射判定项**降级为观察（报告「能力观察清单」展示），不硬断；
- **skip 规则**（用户口径：没有场景期望的先标记跳过）：
  - 报告 badge=SKIP（VISION-VIDEO——依赖文件上传成功）；
  - 报告无请求信息；
  - 无场景期望且无逐项判定；
  - **不适用项**：FILES-VIDEO / FILES-VIDEO-EXTENSION（multipart 文件上传，fixture 视频文件未随报告提供，JSON 重放不适用）；
- **auth 变体**：AUTH-missing 不带鉴权头、AUTH-invalid 携带无效 token（预期 401）；
- **多请求用例**：按报告请求顺序全部重放（缓存组依赖顺序——先写后读）。

## TTL 缓存边界探针组（TTL-001~007，slow_ttl 慢速标记）

TTL-001~007 为报告的 5m 缓存 TTL 边界探针（报告场景期望：两次同前缀请求、期间静默等待 180/300.1/300/301/360/600/600s，首次 `cache_write_tokens=None`、二次 `cached_tokens=1728`）。报告自身对该组口径为「只记录行为，不因边界时序直接判通过或失败」（REVIEW 待复核）。

按用户确认（2026-11-23 方案 A），本套件将该组独立为 `test_ttl_boundary[TTL-00X]` 专用参数化方法并**复刻报告行为**：

- **执行**：请求 1（缓存写入）→ `time.sleep(报告等待时长)` → 请求 2（同前缀）；
- **断言**：① 两次请求均 HTTP 200；② 第二次 `cached_tokens > 0`（报告 20261119 实测 1728——实测 `cached=0` 时判 FAIL，失败消息注明「若为 5m TTL 正确过期则属报告记录异常，若为缓存未生效则属缺陷，需人工复核」）；
- **观察**：首次 `cache_write_tokens`/`cached_tokens`、二次 `cached_tokens` 数值（记录式，与报告 1728 对照）；
- **慢速标记**：`@pytest.mark.slow_ttl`——7 条等待合计约 **44 分钟**，默认随套件执行，可用 `-m "yqzl_agdc2_75 and not slow_ttl"` 快速排除（232 条）。

## 运行方式

```bash
# 运行整套 Y 套件（239 用例，含 3 条 skip + 7 条 slow_ttl 约 44 分钟）
pytest -m yqzl_agdc2_75 -v

# 快速跑（排除 slow_ttl 慢速边界探针，232 条）
pytest -m "yqzl_agdc2_75 and not slow_ttl" -v

# 运行单用例（参数化节点名=报告用例 id）
pytest "tests/test_yqzl_agdc2_75.py::TestYqzlAGDC2_75::test_case[BASIC-JSON]" -v
pytest "tests/test_yqzl_agdc2_75.py::TestYqzlAGDC2_75::test_case[CONTEXT-256-lines]" -v
pytest "tests/test_yqzl_agdc2_75.py::TestYqzlAGDC2_75::test_ttl_boundary[TTL-001]" -v

# Jenkins：勾选 MARKER_YQZL_AGDC2_75 跑整套
#（Y 用例不进 SPECIFIC_TEST 用例选择参数——同 Z/S 套件口径）
```

不进 smoke 集；无 P0/P1/P2 标记（客户报告重放套件）。**默认收集不含 Y 用例**（conftest 收集排除与 Jenkinsfile `MARKER_ALL` 排除双层口径）：裸 `pytest` / `pytest -m p0` 等不会执行 Y 用例；仅 `pytest -m yqzl_agdc2_75`、显式指定文件/节点、Jenkins 勾选 `MARKER_YQZL_AGDC2_75` 执行。

## 测试报告

Y 套件运行自动生成专用报告（同 L/Z/S 套件接线模式）：

- **请求录制**（`_yqzl_send` 内 `_YQZL_RECORDER`）：每请求一条内存记录——所属用例（栈回溯 + case_id）、URL/协议 kind（chat/responses/messages/compact）/请求头（鉴权打码）/请求体/状态码/耗时/响应头/响应体全文（SSE 为事件行 join）/发送异常；**观察项**（`_YQZL_OBS`）：记录式判定项与未映射判定项；
- **会话末导出与生成**（conftest `pytest_terminal_summary` 接线，无 yqzl 节点时零导入零输出）：
  - 录制记录+观察写 `yqzl_records.json`（allure-results 同级，`{"records": [...], "obs": {...}}`，可离线重生成）；
  - **纯 yqzl 运行**：顶替通用 Markdown 汇总与 `test_reports/` 报告，仅生成 Y 套件 HTML + 汇总 MD（输出至 `--summary-report-dir`）；
  - **混合运行**：通用报告照旧，Y 套件 HTML/MD 额外生成（lexin/zjxm/sksn 行为不变）；
- **HTML 报告**（`base/yqzl_html_report.py`）：任务概要 / 测试结果统计（含**报告类别分组统计**与报告总判定对照徽章）/ 用例结果总览（全部 239 用例 + 场景期望列 + 每请求子行，HTTP 状态中性徽章）/ 用例明细（左侧报告期望与逐项判定（含报告原判定 ✅/❌/➖）、右侧实测观察 + 请求/响应折叠，报文全量不截断）；
- **汇总 MD**：章节名与通用报告一致（`## 统计汇总` / `## 分类统计`（按报告类别）/ `## 测试结论` / `## 跳过用例说明`）+ **能力观察清单**（记录式/未映射判定项逐用例列出）；
- **Jenkins**：HTML 报告随 `*.html` 拉取到 `reports/<构建号>/`，检测到即追加为邮件附件——复用 L/Z/S 套件通用链路，无需额外接线；
- **CLI 离线重生成**：`python -m base.yqzl_html_report --alluredir <目录> [--records <json>] [--out-dir <目录>] --model <模型名> --base-url <接入点>`。

## 注意事项

- 套件不计入 README/checkpoints 的「9 大类 × N 测试点」口径（同 L/Z/S 套件口径，Y 单列）；
- 用例定义为**报告提取产物**（`tests/data/yqzl_agdc2_75_cases.json`）——报告更新时重新运行提取脚本覆盖，勿手工编辑；
- 报告 FAIL 总判定的 33 条（如 CONTEXT-256-lines 位置读取）按场景期望断言——重放环境若已修复则 PASS（修复验证），未修复则 FAIL（缺陷复现），两种结果均为有效信号；
- REVIEW 总判定的 82 条多为「应返回 HTTP 4xx 或明确错误」（类型/参数非法值）——按规范期望断言；实测 2xx 放行且错误不明确时判 FAIL（与报告 REVIEW 待复核口径一致）；
- 缓存协议矩阵（PROTO-\*）的命中类断言（cached_tokens>0）依赖同前缀缓存生效——首跑可能因缓存未建立而不命中，属环境时序因素，重跑通常恢复；
- TTL 边界探针组（TTL-001~007）为 slow_ttl 慢速用例（详见上节），Jenkins 全量跑含约 44 分钟等待；
- 流式用例的结构断言（响应标识/模型标识/对象类型）兼容流式形态——标识取自首条 SSE 事件顶层（非流式取 JSON 顶层）；
- CONTEXT-8192-lines 为超长上下文用例（payload 约 60KB），单次请求耗时长——整套运行时间主要消耗在长上下文组；
- 用例 nodeid 为参数化形式 `test_case[<报告用例ID>]`，Jenkins SPECIFIC_TEST 暂不支持该套件（同 Z/S 口径）。
