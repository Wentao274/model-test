# API易工单 AGDC2-74 minimax-h3 视频生成接口测试套件

套件文件：`tests/test_aiyi_agdc2_74.py`（类 `TestAiyiAGDC2_74`，11 用例）
marker：`aiyi_agdc2_74`（AY 类；conftest 自动打标 + 默认收集排除，仅显式点名时执行）
数据源：《反馈-厂商-20261120.md》（AGDC2-74 ones 工单，客户=API易）+ 开发对阻塞与风险 3/4 的回复（2026-11-20）

## 背景

客户（API易）在 staging 环境（`https://codingplan-staging.alayanew.com:26443`）接入 minimax-h3 视频生成模型，反馈 5 项阻塞与风险：

| # | 现象 | 开发回复/口径 | 对应用例 |
|---|---|---|---|
| 1 | 令牌无 `minimax-h3-ref2va` 权限（403），参考图/参考视频工作流完全未验证 | 无（接入前置开通项） | T9 |
| 2 | 显式 `adaptive`+图片不传 `frame_indices` → 200 queued 后 `video_execution_failed`（B1 317.8s / B2 348.1s）；显式比例/不传 ratio 时默认映射正常（单图=首帧、双图=首尾帧） | 无明确修复回复；客户口径「修复为手册默认映射 **或** 手册改必填」 | T5/T6 |
| 3 | 2K 5s 在 5 并发下失败（单发正常）；5 并发时延放大 2-5× | **已修复**：等待过期/生成过期分开计时并延长；单用户并发默认 3，超限 429 干净拒绝 | T7/T8 |
| 4 | 400 校验失败仍留 failed 任务记录（10 非法提交=10 条记录）；错误体不带 request_id（仅响应头 `X-Oneapi-Request-Id`） | **已修复**：10 条非法×带/无键 20 组合统一为 400 + body 带 request_id + 不留任务记录 + 同 key 可复用 | T3/T4 |
| 5 | 直链 15 分钟过期；带 Authorization 头返回 400；过期返回 500（手册写 403） | 无（客户结论：接入必须 R2 转存） | T10/T11 |

客户已验证可用项（不重复消耗任务，作基线/前置）：文生 768P/1080P/2K、比例矩阵 1:1/16:9/9:16/21:9、24fps 音轨、显式 frame_indices 首尾帧（PSNR 37.2/34.7dB）、context-ir、幂等、/content 302、Range、15 分钟重签。

## 接口形态

与 chat 协议不同，multipart 异步任务模型：

- 提交：`POST {api_prefix}/videos`，multipart/form-data（curl `-F`）：`model`/`prompt`/`seconds`/`ratio`/`resolution`/`frame_indices`/`input_references`（文件可重复）；头 `Authorization: Bearer` + `Idempotency-Key: <uuid>`；
- 列表：`GET {api_prefix}/videos?page=1&size=100`；详情：`GET {api_prefix}/videos/{id}`；
- 任务字段：`id`/`status`（queued/in_progress/completed/failed）/`prompt`/`params`/`error.code`；终态分钟级（B1 轨迹：queued ~248s → in_progress ~70s → failed）；
- 直链：任务 JSON 内 `/content` 链接 → 302 → presigned URL（15 分钟有效，Range 支持，不得携带 Authorization 头）。

### URL 构造（防 /v1/v1 双版本段，用户强调）

脚本内一律 `f"{api_client.api_prefix}/videos"`——`base/api_client.py` 的 `split_base_url` 将 BASE_URL 归一为不含版本段，`api_prefix` 恒为恰好一个版本段（带不带 `/v1` 结尾的 BASE_URL 均归一到 `{base}/v1`），不可能双拼；模块内置防御断言（`_aiyi_videos_url`：版本段出现两次即 fail 并提示检查 BASE_URL）。直链与 presigned 为任务返回的绝对 URL，原样使用不拼接。

### HTTP 客户端

全部 `requests` 直发，不用 `api_client.session`——session 内嵌 `Content-Type: application/json` 会破坏 multipart boundary，内嵌 `Authorization` 会污染 presigned 直链请求（工单：带鉴权头 400）。鉴权头按需显式构造（`_aiyi_auth_headers`）。

## 用例概览

| 用例 | 场景 | 请求要点 | 断言 | 优先级 |
|---|---|---|---|---|
| T1 `test_01_text_to_video_baseline_and_direct_link` | 基线文生+直链 | 768P/4s/16:9 文生（带键，唯一 prompt 标记） | 200 受理→轮询 completed；/content 302；presigned Range 206/200 非空 | P0 |
| T2 `test_02_idempotency_same_key_dedup` | 幂等正向 | T1 同 Idempotency-Key 同参数重发 | 200；返回原任务 id（或列表该 prompt 任务数=1） | P1 |
| T3 `test_03_invalid_params_matrix_400_no_task_leftover` | 400 矩阵修复验证 | 10 条非法×带/无键=20 组合 | ①400 ②error.code 与矩阵逐一匹配 ③body 含 request_id（任意层级非空）④列表无新任务 | P0 |
| T4 `test_04_idempotency_key_reusable_after_400` | 键复用修复验证 | 同 key 先 400（seconds=3）后合法重发 | 第二次 200 受理→completed（key 不毒化） | P0 |
| T5 `test_05_adaptive_single_image_default_mapping` | 缺陷修复验证 | 合成图 1344×768 + adaptive + 不传 frame_indices | 200 受理→completed（手册默认映射=首帧） | P0 |
| T6 `test_06_adaptive_two_images_default_mapping` | 缺陷修复验证 | 2 合成图 + adaptive + 不传 frame_indices | 200 受理→completed（默认首尾帧映射） | P0 |
| T7 `test_07_concurrent_2k_rate_limit_and_completion` | 修复验证 | 5 线程并发 2K/5s（各自唯一键） | ①每发∈{200, 429} ②至少 1 受理 ③受理任务全部 completed（无 video_execution_failed）④时延统计留观察 | P0 |
| T8 `test_08_rate_limit_recovery_after_terminal` | 限流恢复 | T7 任务全部终态后再提 1 发 2K/5s | 200 受理（配额释放）→completed | P2 |
| T9 `test_09_ref2va_reference_workflow_permission` | 阻断复现 | model=REF_MODEL_NAME（Jenkins 透传）+参考图 | 403=权限未开通 FAIL（阻断复现）；200→completed | P0 |
| T10 `test_10_direct_link_with_authorization_header` | 风险观察 | T1 presigned+Authorization 头 | 只记录不判（工单：当前 400；手册语义厂商确认前观察口径） | P2 |
| T11 `test_11_direct_link_expiry_403` | 缺陷复现（慢） | T1 /content 重签→等 15 分钟→过期请求 | 过期直链 403（手册口径；500=缺陷复现 FAIL）；过期后 /content 重签正常 | P2/slow |

### T3 非法参数矩阵（与工单 10 条逐一对应）

| 用例 | 参数 | 期望 error.code |
|---|---|---|
| C1 | seconds=3, 16:9, 768P | `invalid_duration` |
| C2 | seconds=16, 16:9, 768P | `invalid_duration` |
| C3 | seconds=5 + num_frames=120 | `conflicting_duration` |
| C4 | 文生 ratio=adaptive | `unsupported_adaptive_ratio` |
| C5 | 未知字段 foo=bar | `unsupported_parameter` |
| C6 | 旧字段 size=1280x720 | `invalid_size` |
| C7 | resolution=4K | `invalid_resolution` |
| C8 | num_frames=95 | `invalid_num_frames` |
| C11 | 文生不传 ratio | `invalid_aspect_ratio` |
| C12 | prompt 33KB | `prompt_too_long` |

每条跑带键/无键两变体（覆盖开发「20 种组合」口径）；400 body 修复后应含 request_id（工单复现显示修复前仅响应头 `X-Oneapi-Request-Id` 有值、body 无）。

## 断言与判定矩阵（核心口径）

- **缺陷复现判 FAIL**：任何「200 queued → 终态 failed(video_execution_failed)」（T5/T6/T7）；400 后任务列表出现新记录（T3）；过期直链 500（T11）；ref2va 403（T9，权限开通前）。
- **修复验证判 PASS**：T3 四断言全过（400+code+request_id+无遗留）；T4 同 key 合法重发受理；T7 受理任务全部 completed + 被拒全部 429。
- **观察不判**：T7 受理/拒绝数与 3/2 的偏差（并发上限可调）、时延放大倍数、429 响应体形态、T10 带鉴权头直链形态、T11 过期后仍可下载（有效期>15 分钟或被重签）。
- **T5/T6 判定口径**（用户确认 2026-11-25）：按手册默认映射断言 completed；若厂商最终改为「adaptive 必传 frame_indices → 400」口径，需反馈调整断言（用例 fail 消息已内置提示）。
- **T3 request_id 判定口径**（用户确认 2026-11-25）：任意层级非空即算（宽松），同时记录 `X-Oneapi-Request-Id` 头供追溯。

## 参数注入

| 参数 | 通道 | 说明 |
|---|---|---|
| 主模型名 | Jenkins `MODEL` → `--model-name` → `api_client.model_name` | minimax-h3 |
| ref2va 模型名 | Jenkins `REF_MODEL_NAME` → `--ref-model-name`（本地回退 env `REF_MODEL_NAME`，再缺省 `minimax-h3-ref2va`） | `none/skip/-` 表示跳过 T9（用户指定：模型名需 Jenkins 透传 2026-11-25） |
| 直链过期开关 | Jenkins `AGDC2_74_LINK_EXPIRY` → `--link-expiry-test`（本地回退 env `AIYI_LINK_EXPIRY_TEST=1/true/yes/on`） | 慢用例默认关闭按需触发（用户确认 2026-11-25） |

BASE_URL 仍由 Jenkins 传入（`split_base_url` 归一，脚本内经 `api_prefix` 固定拼 `/videos`，防双 v1）。

## 设计决策记录

1. **requests 直发不用 session**：session 内嵌 `Content-Type: application/json` 破坏 multipart boundary、内嵌 `Authorization` 污染 presigned 直链（工单确认带鉴权头 400）。
2. **合成参考图**：PIL 生成 1344×768 PNG 条纹图（工单素材同尺寸），消除外部素材依赖；不做 PSNR 断言（非客户原图无意义，留人工）。
3. **任务 JSON 字段防御性提取**：列表/详情响应形态做多重兼容（裸数组 / data/videos/items/list/results/tasks 包装 + 递归兜底），`/content` 直链递归查找含 "/content" 的 URL 字符串——服务端字段名变化时 dump 全文辅助定位而非误判。
4. **T1 产物会话内复用**：T2/T10/T11 依赖 T1 的任务 id/幂等键/直链（模块级 `_AIYI_STATE`），避免重复生成任务控制成本；单独点名执行依赖用例时按依赖缺失 skip 并说明。
5. **T7 断言不锁死 3/2 分流**：开发口径「并发默认 3、上限可调」，故只断言「受理或 429 二态干净分流」+「受理必完成」，受理数与 3/2 的偏差留观察。
6. **慢用例开关**：T11 等待约 15 分钟，经参数控制默认不执行（套件默认时长 25-45 分钟可控）。
7. **不进 all 默认集**：同 L/Z/S/Y 套件口径，conftest 默认排除 + Jenkinsfile MARKER_ALL 排除双保险（视频任务分钟级有生成成本）；进 SPECIFIC_TEST（同 L 套件先例，11 用例全量可点）。
8. **顺序依赖设计，不支持 xdist 并行**：T2/T10/T11 依赖 T1、T8 依赖 T7；pytest 按定义顺序执行（Jenkins 不带 `-n`）。
9. **采样豁免**：视频接口无采样参数概念，`RAW_SAMPLING_EXEMPT_FILES` 整模块豁免（同 test_k/L/Z/S/Y 口径）。

## 成本与时长

- 生成任务预算约 8 个：T1/T4/T5/T6/T9 各 1（768P/4s）+ T7 受理 ≤3×2K/5s + T8 1×2K/5s（T2 幂等重发预期不新建任务、T3 全部 400 不产生任务）。
- 轮询：10s 间隔；768P 超时 900s、2K 超时 1800s；套件典型时长 25-45 分钟（2K 并行受理时最慢）。

## 不覆盖范围

- 首尾帧 PSNR 抽帧核对（需客户原始素材，留人工）；
- 24fps/音轨等成片细节（需视频解码，仅记录任务元数据字段）；
- 参考音频字段（手册未提供字段名，待厂商补充后加用例）；
- context-ir 结构化提示编译（客户已验证可用，非本轮风险项）；
- 1080P/2K 文生全比例矩阵（客户已验证，套件只做 768P 基线 + 2K 并发场景）。

## 执行方式

```bash
# 本地全量（Jenkins 勾选 MARKER_AIYI_AGDC2_74 等价 -m aiyi_agdc2_74）
pytest -m aiyi_agdc2_74 --base-url https://codingplan-staging.alayanew.com:26443 \
    --api-key <KEY> --model-name minimax-h3

# 含直链过期慢用例
pytest -m aiyi_agdc2_74 --link-expiry-test ...

# 跳过 ref2va 用例（权限未开通时）
pytest -m aiyi_agdc2_74 --ref-model-name none ...

# 单用例（Jenkins SPECIFIC_TEST 等价）
pytest "tests/test_aiyi_agdc2_74.py::TestAiyiAGDC2_74::test_03_invalid_params_matrix_400_no_task_leftover" ...
```

预期结果：ref2va 权限开通前 T9 FAIL（阻断复现，属预期失败）；其余用例在修复生效后 PASS。T5/T6 在厂商未修复前 FAIL（缺陷复现，属预期失败）。
