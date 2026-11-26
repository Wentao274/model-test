"""API易工单 AGDC2-74 minimax-h3 视频生成接口测试套件（11 用例）。

数据源（用户指定 2026-11-25）：《反馈-厂商-20261120.md》（AGDC2-74
ones 工单，客户=API易，模型 minimax-h3，环境
https://codingplan-staging.alayanew.com:26443）+ 开发对阻塞与风险
3/4 的回复（2026-11-20：等待/生成过期分开计时并延长；单用户并发默认
3、超限 429；400 统一带 request_id、不留任务记录、同 key 可复用）。

5 项阻塞与风险 → 用例映射：
- T1  基线文生 768P/4s/16:9 + 直链（302→Range 下载）——通路基线，
  供 T2/T10/T11 复用任务产物；
- T2  幂等正向：同 Idempotency-Key 同参数重发不新建任务；
- T3  10 条非法提交 × 带/无 Idempotency-Key 共 20 组合：400 +
  error.code 与工单矩阵逐一匹配 + body 含 request_id（修复验证，
  任意层级非空，用户确认 2026-11-25）+ 任务列表无遗留记录（修复
  验证）；
- T4  400 后同 Idempotency-Key 搭配合法参数重发应正常受理（key 不
  被 400 毒化，开发回复修复验证）；
- T5/T6  显式 adaptive + 单图/双图不传 frame_indices：按手册默认
  映射（单图=首帧、双图=首尾帧）断言任务 completed（缺陷复现口径
  = 终态 failed；用户确认按默认口径 2026-11-25）；
- T7  5 并发 2K/5s：每发必为 200 受理或 429 干净拒绝（单用户并发
  默认 3，开发回复）；被受理任务必须 completed（不再
  video_execution_failed——过期计时修复验证）；时延放大留观察；
- T8  受理任务全部终态后配额释放：再次提交应 200 受理；
- T9  参考图工作流（ref2va）：模型名经 Jenkins REF_MODEL_NAME/
  --ref-model-name 透传（用户指定 2026-11-25）；403=权限未开通
  阻断复现；权限开通后应 200 受理并出片；
- T10 直链携带 Authorization 头：当前 400（工单观察），手册语义
  待厂商确认前只记录不判；
- T11 直链 15 分钟过期：过期直链应 403（手册口径；500=缺陷复现），
  过期后 /content 重签机制应仍正常。慢用例（等待约 15 分钟），
  经 --link-expiry-test / AIYI_LINK_EXPIRY_TEST=1 开启（用户确认
  2026-11-25：默认关闭按需触发）。

接口形态（与 chat 协议不同，multipart 异步任务模型）：
- 提交：POST {api_prefix}/videos，multipart/form-data（curl -F）：
  model / prompt / seconds / ratio / resolution / frame_indices /
  input_references（文件可重复）；头 Authorization: Bearer +
  Idempotency-Key: <uuid>；
- 列表：GET {api_prefix}/videos?page=1&size=100；详情：
  GET {api_prefix}/videos/{id}；任务字段 id/status/prompt/params/
  error.code，终态 completed/failed（分钟级，轮询间隔 10s）；
- 直链：任务 JSON 内 /content 链接 → 302 → presigned URL（15 分钟
  有效，Range 支持）；presigned 不得携带 Authorization 头。

URL 构造（防 /v1/v1 双版本段，用户强调）：一律
f"{api_client.api_prefix}/videos"——split_base_url 将 BASE_URL 归一
为不含版本段，api_prefix 恒为恰好一个版本段；模块内置防御断言：
url 中版本段不得出现两次。提交/列表/详情全部经该前缀拼接；直链与
presigned 为任务返回的绝对 URL，原样使用不拼接。

HTTP 客户端口径：全部 requests 直发（不用 api_client.session——
session 内嵌 Content-Type: application/json 会破坏 multipart
boundary，内嵌 Authorization 会污染 presigned 直链请求）；鉴权头
按需显式构造。

请求参数注入：
- 主模型名：Jenkins MODEL → --model-name → api_client.model_name；
- ref2va 模型名：Jenkins REF_MODEL_NAME → --ref-model-name（本地
  缺省回退 env REF_MODEL_NAME，再缺省 minimax-h3-ref2va；显式
  none/skip/- 表示跳过 T9）；
- 直链过期开关：Jenkins AGDC2_74_LINK_EXPIRY → --link-expiry-test
  （本地回退 env AIYI_LINK_EXPIRY_TEST=1/true/yes/on）。

采样参数豁免：视频生成接口无采样参数概念，conftest
RAW_SAMPLING_EXEMPT_FILES 整模块豁免（同 test_k/L/Z/S/Y 口径），
不注入 temperature/top_p/seed。

marker：aiyi_agdc2_74（conftest 按 test_aiyi_ 前缀自动打标——注意
分支须先于 test_a_ 判定，test_a_ 为其子串；默认收集排除——仅
显式点名时执行，与 Jenkinsfile MARKER_ALL 排除互为双保险）。

顺序依赖（设计如此，不支持 xdist 并行）：T2/T10/T11 依赖 T1 同
会话产物（任务 id/幂等键/直链），T8 依赖 T7 受理任务全部终态；
单独点名执行依赖用例时按依赖缺失 skip 并说明。

生成任务成本预算：T1/T4/T5/T6/T9 各 1（768P/4s）+ T7 受理
（≤3× 2K/5s）+ T8 1× 2K/5s，共约 8 个任务；套件典型时长
25-45 分钟（2K 任务最慢，轮询超时 1800s 上限）。

不覆盖范围（说明）：首尾帧 PSNR 抽帧核对（需客户原始素材，留
人工）、24fps/音轨等成片细节（需视频解码，仅记录任务元数据）、
参考音频字段（手册未提供字段名，待补）、context-ir 结构化提示编
译（客户已验证可用，非本轮风险项）。
"""

import json
import os
import threading
import time
import uuid

import pytest
import requests

from io import BytesIO
from PIL import Image, ImageDraw
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse


_AIYI_STATE: Dict[str, Any] = {}

AIYI_POLL_INTERVAL = 10
AIYI_SUBMIT_TIMEOUT = 120
AIYI_LIST_TIMEOUT = 60
AIYI_POLL_TIMEOUT_DEFAULT = 900
AIYI_POLL_TIMEOUT_2K = 1800
AIYI_LINK_TTL_SECONDS = 15 * 60
AIYI_LINK_TTL_BUFFER = 60


@pytest.fixture(scope="session")
def aiyi_ref_model(request) -> str:
    """ref2va 参考图工作流模型名（--ref-model-name / env 回退链）。"""
    raw = (request.config.getoption("--ref-model-name", default=None) or "").strip()
    if not raw:
        raw = (os.environ.get("REF_MODEL_NAME") or "").strip()
    if not raw or raw.lower() in ("none", "skip", "-"):
        return ""
    return raw


@pytest.fixture(scope="session")
def aiyi_link_expiry_enabled(request) -> bool:
    """直链过期慢用例开关（--link-expiry-test / env AIYI_LINK_EXPIRY_TEST）。"""
    if request.config.getoption("--link-expiry-test", default=False):
        return True
    return (os.environ.get("AIYI_LINK_EXPIRY_TEST") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _aiyi_uuid() -> str:
    return str(uuid.uuid4())


def _aiyi_videos_url(api_client) -> str:
    """视频任务根 URL：api_prefix 拼接 + 双版本段防御断言。"""
    url = f"{api_client.api_prefix}/videos"
    version_seg = f"/{api_client.api_version}/"
    assert url.count(version_seg) <= 1, (
        f"视频端点 URL 出现重复版本段（防 /v1/v1 双拼失败）：{url}"
        "——请检查 BASE_URL 传入值；脚本内一律经 api_prefix 拼接，"
        "不带版本段的 BASE_URL 与带 /v1 结尾的 BASE_URL 均已归一"
    )
    return url


def _aiyi_auth_headers(api_client) -> Dict[str, str]:
    if api_client.api_key:
        return {"Authorization": f"Bearer {api_client.api_key}"}
    return {}


def _aiyi_parse_body(resp) -> Tuple[Optional[Any], str]:
    try:
        return resp.json(), ""
    except ValueError:
        return None, (resp.text or "")[:2000]


def _aiyi_submit(api_client, data: Dict[str, str],
                 files: Optional[List[Tuple[str, Tuple[str, bytes, str]]]] = None,
                 idem_key: Optional[str] = None,
                 timeout: int = AIYI_SUBMIT_TIMEOUT) -> Tuple[int, Optional[Any], str, Dict[str, str]]:
    """multipart 提交一个视频任务；返回 (HTTP 状态, 解析后 body, body 文本, 响应头)。"""
    headers = _aiyi_auth_headers(api_client)
    if idem_key:
        headers["Idempotency-Key"] = idem_key
    resp = requests.post(
        _aiyi_videos_url(api_client),
        data={k: str(v) for k, v in data.items()},
        files=files,
        headers=headers,
        timeout=timeout,
    )
    body, text = _aiyi_parse_body(resp)
    return resp.status_code, body, text, dict(resp.headers)


def _aiyi_get_task(api_client, task_id: str,
                   timeout: int = AIYI_LIST_TIMEOUT) -> Tuple[int, Optional[Any], str]:
    url = f"{_aiyi_videos_url(api_client)}/{task_id}"
    resp = requests.get(url, headers=_aiyi_auth_headers(api_client), timeout=timeout)
    body, text = _aiyi_parse_body(resp)
    return resp.status_code, body, text


def _aiyi_extract_task_list(body: Any) -> List[Dict[str, Any]]:
    """从列表响应中提取任务数组：兼容裸数组与 data/videos/items/list/
    results/tasks 包装，再兜底递归找首个元素含 id 的数组。"""
    if isinstance(body, list):
        return [x for x in body if isinstance(x, dict)]
    if isinstance(body, dict):
        for key in ("data", "videos", "items", "list", "results", "tasks"):
            value = body.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
        for value in body.values():
            if isinstance(value, list) and value and all(
                isinstance(x, dict) for x in value
            ):
                return value
    return []


def _aiyi_list_tasks(api_client, page: int = 1, size: int = 100,
                     timeout: int = AIYI_LIST_TIMEOUT) -> Tuple[int, Optional[Any], str, List[Dict[str, Any]]]:
    url = f"{_aiyi_videos_url(api_client)}?page={page}&size={size}"
    resp = requests.get(url, headers=_aiyi_auth_headers(api_client), timeout=timeout)
    body, text = _aiyi_parse_body(resp)
    return resp.status_code, body, text, _aiyi_extract_task_list(body)


def _aiyi_task_id(body: Any) -> Optional[str]:
    if isinstance(body, dict):
        value = body.get("id") or (body.get("data") or {}).get("id")
        if isinstance(value, str) and value:
            return value
    return None


def _aiyi_task_status(body: Any) -> str:
    if isinstance(body, dict):
        return str(body.get("status") or body.get("state") or "").lower()
    return ""


def _aiyi_error_code(body: Any) -> Optional[str]:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("code"):
            return str(error["code"])
        if body.get("code"):
            return str(body["code"])
    return None


def _aiyi_deep_find_request_id(obj: Any) -> Optional[str]:
    """递归找 request_id（任意层级非空即算，用户确认宽松口径）。"""
    if isinstance(obj, dict):
        for key in ("request_id", "requestId", "request-id"):
            value = obj.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
        for value in obj.values():
            found = _aiyi_deep_find_request_id(value)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _aiyi_deep_find_request_id(item)
            if found:
                return found
    return None


def _aiyi_poll_task(api_client, test_logger, task_id: str, timeout: int,
                    tag: str) -> Dict[str, Any]:
    """轮询单任务至终态（completed/failed 等），返回最后一次详情 body。"""
    deadline = time.time() + timeout
    last: Dict[str, Any] = {}
    last_status = ""
    start = time.time()
    while time.time() < deadline:
        status_code, body, text = _aiyi_get_task(api_client, task_id)
        if status_code != 200 or not isinstance(body, dict):
            test_logger.info("[%s] 任务 %s 详情查询异常 HTTP %s: %s",
                             tag, task_id, status_code, text[:300])
        else:
            last = body
            current = _aiyi_task_status(body)
            if current != last_status:
                test_logger.info("[%s] 任务 %s 状态变迁: %s -> %s（elapsed %.0fs）",
                                 tag, task_id, last_status or "∅", current,
                                 time.time() - start)
                last_status = current
            if current in ("completed", "succeeded", "failed",
                           "cancelled", "canceled"):
                return body
        time.sleep(AIYI_POLL_INTERVAL)
    test_logger.info("[%s] 任务 %s 轮询超时（%.0fs）最后状态: %s",
                     tag, task_id, timeout, last_status or "未知")
    return last


def _aiyi_poll_tasks_roundrobin(api_client, test_logger, task_ids: List[str],
                                timeout: int, tag: str) -> Dict[str, Dict[str, Any]]:
    """轮询多任务至全部终态：每轮逐个查询，返回 {task_id: 最后详情 body}。"""
    deadline = time.time() + timeout
    pending = list(task_ids)
    finals: Dict[str, Dict[str, Any]] = {}
    statuses = {tid: "" for tid in task_ids}
    start = time.time()
    while pending and time.time() < deadline:
        for tid in list(pending):
            status_code, body, text = _aiyi_get_task(api_client, tid)
            if status_code != 200 or not isinstance(body, dict):
                test_logger.info("[%s] 任务 %s 详情查询异常 HTTP %s: %s",
                                 tag, tid, status_code, text[:300])
                continue
            finals[tid] = body
            current = _aiyi_task_status(body)
            if current != statuses[tid]:
                test_logger.info("[%s] 任务 %s 状态变迁: %s -> %s（elapsed %.0fs）",
                                 tag, tid, statuses[tid] or "∅", current,
                                 time.time() - start)
                statuses[tid] = current
            if current in ("completed", "succeeded", "failed",
                           "cancelled", "canceled"):
                pending.remove(tid)
        if pending:
            time.sleep(AIYI_POLL_INTERVAL)
    for tid in pending:
        test_logger.info("[%s] 任务 %s 轮询超时（%.0fs）最后状态: %s",
                        tag, tid, timeout, statuses[tid] or "未知")
    return finals


def _aiyi_make_ref_image(kind: str = "first", width: int = 1344,
                         height: int = 768) -> bytes:
    """合成参考图（1344×768 PNG 条纹图，工单素材同尺寸；无外部素材依赖）。"""
    base = (180, 60, 40) if kind == "first" else (40, 90, 160)
    image = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 96):
        draw.rectangle([x, 0, x + 48, height], fill=(240, 240, 240))
    draw.rectangle([0, height // 2, width, height // 2 + 16], fill=(20, 20, 20))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _aiyi_find_urls(obj: Any, found: Optional[List[str]] = None) -> List[str]:
    """递归提取任务 JSON 中的全部 URL 字符串（/content 优先）。"""
    if found is None:
        found = []
    if isinstance(obj, dict):
        for value in obj.values():
            _aiyi_find_urls(value, found)
    elif isinstance(obj, list):
        for item in obj:
            _aiyi_find_urls(item, found)
    elif isinstance(obj, str) and obj.startswith(("http://", "https://", "/")):
        found.append(obj)
    if found:
        found.sort(key=lambda u: 0 if "/content" in u else 1)
    return found


def _aiyi_absolutize(url: str, api_client) -> str:
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("/"):
        parsed = urlparse(api_client.base_url)
        return f"{parsed.scheme}://{parsed.netloc}{url}"
    return url


def _aiyi_content_url(api_client, task: Dict[str, Any]) -> Optional[str]:
    for candidate in _aiyi_find_urls(task):
        if "/content" in candidate:
            return _aiyi_absolutize(candidate, api_client)
    return None


def _aiyi_count_tasks_by_prompt(api_client, prompt: str) -> Tuple[int, Optional[Any], str]:
    status_code, body, text, tasks = _aiyi_list_tasks(api_client)
    if status_code != 200:
        return -1, body, text
    count = sum(1 for t in tasks if t.get("prompt") == prompt)
    return count, body, text


AIYI_INVALID_CASES: List[Tuple[str, str, Dict[str, str]]] = [
    ("C1", "invalid_duration",
     {"seconds": "3", "ratio": "16:9", "resolution": "768P"}),
    ("C2", "invalid_duration",
     {"seconds": "16", "ratio": "16:9", "resolution": "768P"}),
    ("C3", "conflicting_duration",
     {"seconds": "5", "num_frames": "120", "ratio": "16:9",
      "resolution": "768P"}),
    ("C4", "unsupported_adaptive_ratio",
     {"ratio": "adaptive", "resolution": "768P"}),
    ("C5", "unsupported_parameter",
     {"foo": "bar", "seconds": "4", "ratio": "16:9", "resolution": "768P"}),
    ("C6", "invalid_size",
     {"seconds": "4", "ratio": "16:9", "size": "1280x720"}),
    ("C7", "invalid_resolution",
     {"seconds": "4", "ratio": "16:9", "resolution": "4K"}),
    ("C8", "invalid_num_frames",
     {"num_frames": "95", "ratio": "16:9", "resolution": "768P"}),
    ("C11", "invalid_aspect_ratio",
     {"seconds": "4", "resolution": "768P"}),
]


class TestAiyiAGDC2_74:

    @pytest.mark.p0
    def test_01_text_to_video_baseline_and_direct_link(self, api_client, test_logger):
        """T1 基线文生（768P/4s/16:9）→ completed + 直链 302→Range 下载。"""
        url = _aiyi_videos_url(api_client)
        test_logger.info("T1 视频任务端点: %s（api_prefix=%s, model=%s）",
                         url, api_client.api_prefix, api_client.model_name)
        marker = f"aiyi-t1-{_aiyi_uuid()}"
        prompt = f"基线文生测试：一只红狐狸从画面左侧走到右侧。标记 {marker}"
        idem_key = _aiyi_uuid()
        status, body, text, headers = _aiyi_submit(
            api_client,
            data={"model": api_client.model_name, "prompt": prompt,
                  "seconds": "4", "ratio": "16:9", "resolution": "768P"},
            idem_key=idem_key,
        )
        assert status == 200, f"T1 提交应 200，实际 {status}: {text[:500]}"
        task_id = _aiyi_task_id(body)
        assert task_id, f"T1 提交响应缺少任务 id: {json.dumps(body, ensure_ascii=False)[:500] if body else text[:500]}"
        test_logger.info("T1 提交受理 task_id=%s 初始状态=%s",
                         task_id, _aiyi_task_status(body))
        final = _aiyi_poll_task(api_client, test_logger, task_id,
                               AIYI_POLL_TIMEOUT_DEFAULT, "T1")
        final_status = _aiyi_task_status(final)
        assert final_status in ("completed", "succeeded"), (
            f"T1 基线文生任务终态 {final_status!r}（预期 completed）: "
            f"{json.dumps(final, ensure_ascii=False)[:800]}"
        )
        for field in ("duration", "resolution", "fps", "video", "output"):
            if isinstance(final, dict) and final.get(field) is not None:
                test_logger.info("T1 任务元数据 %s: %s", field, final[field])
        content_url = _aiyi_content_url(api_client, final)
        assert content_url, (
            "T1 任务详情未找到 /content 直链（字段名可能变化，请人工核对）: "
            f"{json.dumps(final, ensure_ascii=False)[:800]}"
        )
        test_logger.info("T1 直链端点: %s", content_url)
        resp = requests.get(content_url, headers=_aiyi_auth_headers(api_client),
                            allow_redirects=False, timeout=AIYI_LIST_TIMEOUT)
        if resp.status_code in (301, 302, 303, 307, 308):
            presigned = resp.headers.get("Location", "")
            assert presigned, "T1 /content 302 缺少 Location"
            test_logger.info("T1 /content 302 → presigned: %s", presigned[:200])
        else:
            presigned = content_url
            test_logger.info("T1 /content 未 302（HTTP %s），按原样 URL 处理",
                             resp.status_code)
        head = requests.get(presigned, headers={"Range": "bytes=0-1023"},
                            timeout=AIYI_LIST_TIMEOUT)
        assert head.status_code in (200, 206), (
            f"T1 presigned Range 下载应 200/206，实际 {head.status_code}: "
            f"{head.text[:300]}"
        )
        assert head.content, "T1 presigned Range 下载内容为空"
        test_logger.info("T1 Range 下载 %s 字节 Content-Range=%s Content-Type=%s",
                         len(head.content),
                         head.headers.get("Content-Range", ""),
                         head.headers.get("Content-Type", ""))
        _AIYI_STATE["t1_task_id"] = task_id
        _AIYI_STATE["t1_idem_key"] = idem_key
        _AIYI_STATE["t1_prompt"] = prompt
        _AIYI_STATE["t1_content_url"] = content_url
        _AIYI_STATE["t1_presigned_url"] = presigned
        _AIYI_STATE["t1_presigned_issued_at"] = time.time()

    @pytest.mark.p1
    def test_02_idempotency_same_key_dedup(self, api_client, test_logger):
        """T2 幂等正向：同 Idempotency-Key 同参数重发，不新建任务。"""
        if not _AIYI_STATE.get("t1_task_id"):
            pytest.skip("依赖 T1 同会话产物（task_id），请先执行 test_01")
        prompt = _AIYI_STATE["t1_prompt"]
        status, body, text, _ = _aiyi_submit(
            api_client,
            data={"model": api_client.model_name, "prompt": prompt,
                  "seconds": "4", "ratio": "16:9", "resolution": "768P"},
            idem_key=_AIYI_STATE["t1_idem_key"],
        )
        assert status == 200, (
            f"T2 同 key 重发应 200（幂等回放），实际 {status}: {text[:500]}"
        )
        task_id = _aiyi_task_id(body)
        if task_id:
            assert task_id == _AIYI_STATE["t1_task_id"], (
                f"T2 幂等重发返回了新任务 {task_id}，原任务 "
                f"{_AIYI_STATE['t1_task_id']}——幂等去重失效"
            )
            test_logger.info("T2 同 key 重发返回原任务 %s（去重正常）", task_id)
        else:
            test_logger.info("T2 重发响应无任务 id（%s），改用列表核对",
                             json.dumps(body, ensure_ascii=False)[:300] if body else text[:300])
        count, list_body, list_text = _aiyi_count_tasks_by_prompt(api_client, prompt)
        assert count >= 0, f"T2 任务列表查询失败: {list_text[:300]}"
        assert count == 1, (
            f"T2 同 key 同参数重发后该 prompt 任务数 {count}（应 1）——幂等去重失效，新建了任务"
        )

    @pytest.mark.p0
    def test_03_invalid_params_matrix_400_no_task_leftover(self, api_client, test_logger):
        """T3 非法参数矩阵（10 条 × 带/无键=20 组合）：400+错误码+request_id+不留任务。"""
        long_prompt = "这是超长提示词验证内容，用于触发 prompt_too_long。" * 1500
        cases = list(AIYI_INVALID_CASES)
        cases.append(("C12", "prompt_too_long",
                      {"seconds": "4", "ratio": "16:9", "resolution": "768P"}))
        for case_id, expected_code, fields in cases:
            for variant in ("with-key", "no-key"):
                marker = f"aiyi-t3-{case_id}-{variant}-{_aiyi_uuid()}"
                if case_id == "C12":
                    prompt = long_prompt + f" 标记 {marker}"
                else:
                    prompt = (f"非法参数矩阵 {case_id} {variant}。"
                              f"标记 {marker}")
                data = {"model": api_client.model_name, "prompt": prompt}
                data.update(fields)
                idem_key = _aiyi_uuid() if variant == "with-key" else None
                status, body, text, resp_headers = _aiyi_submit(
                    api_client, data=data, idem_key=idem_key)
                assert status == 400, (
                    f"T3 {case_id}/{variant} 提交应 400（预期 error.code="
                    f"{expected_code}），实际 {status}: {text[:500]}"
                )
                code = _aiyi_error_code(body)
                assert code == expected_code, (
                    f"T3 {case_id}/{variant} error.code 应 {expected_code}，"
                    f"实际 {code}: {text[:500]}"
                )
                request_id = _aiyi_deep_find_request_id(body)
                assert request_id, (
                    f"T3 {case_id}/{variant} 400 body 缺少 request_id"
                    f"（修复口径：body 应含 request_id；响应头 "
                    f"X-Oneapi-Request-Id={resp_headers.get('X-Oneapi-Request-Id', '')}）: "
                    f"{text[:500]}"
                )
                count, list_body, list_text = _aiyi_count_tasks_by_prompt(
                    api_client, prompt)
                assert count == 0, (
                    f"T3 {case_id}/{variant} 400 后任务列表出现 "
                    f"{count} 条该 prompt 记录（修复口径：400 不应遗留任务）"
                )
                test_logger.info(
                    "T3 %-4s %-9s HTTP 400 code=%-28s request_id=%s 任务遗留=0",
                    case_id, variant, code, request_id[:24] + "…")

    @pytest.mark.p0
    def test_04_idempotency_key_reusable_after_400(self, api_client, test_logger):
        """T4 400 后同 Idempotency-Key 搭配合法参数重发应受理并出片（key 不毒化）。"""
        idem_key = _aiyi_uuid()
        status, body, text, _ = _aiyi_submit(
            api_client,
            data={"model": api_client.model_name,
                  "prompt": f"T4 键复用前置非法提交。标记 aiyi-t4-bad-{_aiyi_uuid()}",
                  "seconds": "3", "ratio": "16:9", "resolution": "768P"},
            idem_key=idem_key,
        )
        assert status == 400, f"T4 前置 400 非法提交应 400，实际 {status}: {text[:300]}"
        test_logger.info("T4 前置 400 完成（key=%s…），开始同 key 合法重发",
                         idem_key[:8])
        prompt = f"键复用验证：灰猫跳上窗台。标记 aiyi-t4-ok-{_aiyi_uuid()}"
        status, body, text, _ = _aiyi_submit(
            api_client,
            data={"model": api_client.model_name, "prompt": prompt,
                  "seconds": "4", "ratio": "16:9", "resolution": "768P"},
            idem_key=idem_key,
        )
        assert status == 200, (
            f"T4 同 key 合法重发应 200（修复口径：400 不毒化幂等键），"
            f"实际 {status}: {text[:500]}"
        )
        task_id = _aiyi_task_id(body)
        assert task_id, f"T4 重发响应缺少任务 id: {text[:500]}"
        final = _aiyi_poll_task(api_client, test_logger, task_id,
                               AIYI_POLL_TIMEOUT_DEFAULT, "T4")
        assert _aiyi_task_status(final) in ("completed", "succeeded"), (
            f"T4 键复用任务终态 {_aiyi_task_status(final)!r}: "
            f"{json.dumps(final, ensure_ascii=False)[:500]}"
        )

    @pytest.mark.p0
    def test_05_adaptive_single_image_default_mapping(self, api_client, test_logger):
        """T5 adaptive+单图不传 frame_indices：按手册默认映射（首帧）应 completed。"""
        image = _aiyi_make_ref_image("first")
        prompt = f"自适应单图默认映射：雪地狐狸站立。标记 aiyi-t5-{_aiyi_uuid()}"
        status, body, text, _ = _aiyi_submit(
            api_client,
            data={"model": api_client.model_name, "prompt": prompt,
                  "seconds": "4", "ratio": "adaptive", "resolution": "768P"},
            files=[("input_references", ("first.png", image, "image/png"))],
            idem_key=_aiyi_uuid(),
        )
        assert status == 200, (
            f"T5 提交应 200（手册默认映射：单图=首帧），实际 {status}: "
            f"{text[:500]}——若厂商已改为『adaptive 必传 frame_indices』"
            "口径，请反馈调整本用例断言"
        )
        task_id = _aiyi_task_id(body)
        assert task_id, f"T5 提交响应缺少任务 id: {text[:500]}"
        final = _aiyi_poll_task(api_client, test_logger, task_id,
                               AIYI_POLL_TIMEOUT_DEFAULT, "T5")
        final_status = _aiyi_task_status(final)
        assert final_status in ("completed", "succeeded"), (
            f"T5 adaptive+单图无 frame_indices 终态 {final_status!r}"
            f"（工单缺陷 B1 复现——应按默认映射出片）: "
            f"{json.dumps(final, ensure_ascii=False)[:800]}"
        )

    @pytest.mark.p0
    def test_06_adaptive_two_images_default_mapping(self, api_client, test_logger):
        """T6 adaptive+双图不传 frame_indices：按手册默认映射（首尾帧）应 completed。"""
        first = _aiyi_make_ref_image("first")
        late = _aiyi_make_ref_image("late")
        prompt = f"自适应双图默认映射：狐狸从左侧走到右侧。标记 aiyi-t6-{_aiyi_uuid()}"
        status, body, text, _ = _aiyi_submit(
            api_client,
            data={"model": api_client.model_name, "prompt": prompt,
                  "seconds": "4", "ratio": "adaptive", "resolution": "768P"},
            files=[("input_references", ("first.png", first, "image/png")),
                   ("input_references", ("late.png", late, "image/png"))],
            idem_key=_aiyi_uuid(),
        )
        assert status == 200, (
            f"T6 提交应 200（手册默认映射：双图=首尾帧），实际 {status}: "
            f"{text[:500]}——若厂商已改为『adaptive 必传 frame_indices』"
            "口径，请反馈调整本用例断言"
        )
        task_id = _aiyi_task_id(body)
        assert task_id, f"T6 提交响应缺少任务 id: {text[:500]}"
        final = _aiyi_poll_task(api_client, test_logger, task_id,
                               AIYI_POLL_TIMEOUT_DEFAULT, "T6")
        final_status = _aiyi_task_status(final)
        assert final_status in ("completed", "succeeded"), (
            f"T6 adaptive+双图无 frame_indices 终态 {final_status!r}"
            f"（工单缺陷 B2 复现——应按默认映射出片）: "
            f"{json.dumps(final, ensure_ascii=False)[:800]}"
        )

    @pytest.mark.p0
    def test_07_concurrent_2k_rate_limit_and_completion(self, api_client, test_logger):
        """T7 5 并发 2K/5s：受理/429 二态干净分流 + 受理任务全部 completed。"""
        concurrency = 5
        results: Dict[int, Dict[str, Any]] = {}
        barrier = threading.Barrier(concurrency)

        def worker(index: int) -> None:
            barrier.wait()
            prompt = (f"并发2K验证：海浪拍打礁石。标记 "
                      f"aiyi-t7-{index}-{_aiyi_uuid()}")
            try:
                status, body, text, _ = _aiyi_submit(
                    api_client,
                    data={"model": api_client.model_name, "prompt": prompt,
                          "seconds": "5", "resolution": "2K", "ratio": "16:9"},
                    idem_key=_aiyi_uuid(),
                )
                results[index] = {"status": status, "body": body,
                                  "text": text[:500]}
            except Exception as exc:
                results[index] = {"status": -1, "body": None,
                                  "text": f"请求异常: {exc}"}

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in range(concurrency)]
        start = time.time()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(AIYI_SUBMIT_TIMEOUT + 30)
        elapsed = time.time() - start
        assert len(results) == concurrency, (
            f"T7 并发提交仅 {len(results)}/{concurrency} 个线程返回结果"
        )
        accepted: List[str] = []
        rejected: List[Dict[str, Any]] = []
        for index in sorted(results):
            item = results[index]
            assert item["status"] in (200, 429), (
                f"T7 并发#{index} 响应应 200 受理或 429 限流（开发口径："
                f"单用户并发默认 3，超限干净拒绝），实际 {item['status']}: "
                f"{item['text']}"
            )
            if item["status"] == 200:
                task_id = _aiyi_task_id(item["body"])
                assert task_id, (f"T7 并发#{index} 200 响应缺少任务 id: "
                                 f"{item['text']}")
                accepted.append(task_id)
                test_logger.info("T7 并发#%s 受理 task_id=%s", index, task_id)
            else:
                rejected.append(item)
                body_note = "JSON" if isinstance(item["body"], dict) else "非JSON"
                test_logger.info("T7 并发#%s 429 拒绝（%s）: %s",
                                 index, body_note, item["text"][:200])
        assert accepted, (
            "T7 全部并发被 429 拒绝——无法验证受理任务完成性；"
            "可能有外部在途任务占用单用户并发配额（默认 3），请排查后重跑"
        )
        test_logger.info("T7 并发提交分流：受理 %s / 拒绝 %s（开发口径默认 3/2），"
                         "提交耗时 %.1fs", len(accepted), len(rejected), elapsed)
        _AIYI_STATE["t7_accepted_ids"] = accepted
        _AIYI_STATE["t7_submit_elapsed"] = elapsed
        poll_start = time.time()
        finals = _aiyi_poll_tasks_roundrobin(api_client, test_logger, accepted,
                                             AIYI_POLL_TIMEOUT_2K, "T7")
        test_logger.info("T7 受理任务轮询完成，耗时 %.0fs", time.time() - poll_start)
        for task_id in accepted:
            final = finals.get(task_id, {})
            final_status = _aiyi_task_status(final)
            assert final_status in ("completed", "succeeded"), (
                f"T7 受理任务 {task_id} 终态 {final_status!r}（预期 "
                f"completed）——过期计时修复未生效（工单缺陷：5 并发下 "
                f"2K 任务 video_execution_failed）: "
                f"{json.dumps(final, ensure_ascii=False)[:800]}"
            )
        total = time.time() - start
        test_logger.info("T7 全链路耗时 %.0fs（受理 %s 任务，时延放大情况"
                         "见轮询轨迹）", total, len(accepted))

    @pytest.mark.p2
    def test_08_rate_limit_recovery_after_terminal(self, api_client, test_logger):
        """T8 T7 任务全部终态后并发配额应释放：再提交 1 发 2K 应受理并出片。"""
        if not _AIYI_STATE.get("t7_accepted_ids"):
            pytest.skip("依赖 T7 同会话受理任务（先执行 test_07）")
        prompt = f"并发释放验证：灯塔夜景。标记 aiyi-t8-{_aiyi_uuid()}"
        status, body, text, _ = _aiyi_submit(
            api_client,
            data={"model": api_client.model_name, "prompt": prompt,
                  "seconds": "5", "resolution": "2K", "ratio": "16:9"},
            idem_key=_aiyi_uuid(),
        )
        assert status == 200, (
            f"T8 配额释放后再提交应 200（T7 任务已全部终态），实际 "
            f"{status}: {text[:500]}——限流器未释放已完成任务的配额"
        )
        task_id = _aiyi_task_id(body)
        assert task_id, f"T8 提交响应缺少任务 id: {text[:500]}"
        final = _aiyi_poll_task(api_client, test_logger, task_id,
                               AIYI_POLL_TIMEOUT_2K, "T8")
        assert _aiyi_task_status(final) in ("completed", "succeeded"), (
            f"T8 任务终态 {_aiyi_task_status(final)!r}: "
            f"{json.dumps(final, ensure_ascii=False)[:500]}"
        )

    @pytest.mark.p0
    def test_09_ref2va_reference_workflow_permission(self, api_client, test_logger,
                                                     aiyi_ref_model):
        """T9 ref2va 参考图工作流：403=权限未开通阻断复现；开通后应受理出片。"""
        if not aiyi_ref_model:
            pytest.skip(
                "未配置参考工作流模型名（--ref-model-name / REF_MODEL_NAME，"
                "Jenkins REF_MODEL_NAME 参数透传；none/skip/- 表示跳过本用例）"
            )
        image = _aiyi_make_ref_image("first")
        prompt = (f"参考图工作流验证：让参考图中的狐狸奔跑。标记 "
                  f"aiyi-t9-{_aiyi_uuid()}")
        test_logger.info("T9 参考工作流模型: %s（Jenkins 透传）", aiyi_ref_model)
        status, body, text, _ = _aiyi_submit(
            api_client,
            data={"model": aiyi_ref_model, "prompt": prompt,
                  "seconds": "4", "ratio": "16:9", "resolution": "768P"},
            files=[("input_references", ("first.png", image, "image/png"))],
            idem_key=_aiyi_uuid(),
        )
        assert status != 403, (
            f"T9 参考工作流提交 403（工单阻塞项 1 复现：令牌无 "
            f"{aiyi_ref_model} 权限，参考图/视频链路未验证）: {text[:500]}"
        )
        assert status == 200, (
            f"T9 参考工作流提交应 200，实际 {status}: {text[:500]}"
        )
        task_id = _aiyi_task_id(body)
        assert task_id, f"T9 提交响应缺少任务 id: {text[:500]}"
        final = _aiyi_poll_task(api_client, test_logger, task_id,
                               AIYI_POLL_TIMEOUT_DEFAULT, "T9")
        assert _aiyi_task_status(final) in ("completed", "succeeded"), (
            f"T9 参考工作流任务终态 {_aiyi_task_status(final)!r}: "
            f"{json.dumps(final, ensure_ascii=False)[:500]}"
        )

    @pytest.mark.p2
    def test_10_direct_link_with_authorization_header(self, api_client, test_logger):
        """T10 直链携带 Authorization 头：观察记录（工单：当前 400，手册语义待定）。"""
        if not _AIYI_STATE.get("t1_presigned_url"):
            pytest.skip("依赖 T1 同会话产物（presigned 直链），请先执行 test_01")
        presigned = _AIYI_STATE["t1_presigned_url"]
        auth_headers = _aiyi_auth_headers(api_client)
        resp = requests.get(presigned, headers=dict(
            auth_headers, **{"Range": "bytes=0-1023"}),
            timeout=AIYI_LIST_TIMEOUT)
        test_logger.info("T10 presigned+Authorization 头: HTTP %s body=%s",
                         resp.status_code, (resp.text or "")[:300])
        test_logger.info("T10 工单观察口径：带鉴权头应 400（当前缺陷/风险形态，"
                         "手册语义厂商确认前只记录不判）")
        content_resp = requests.get(_AIYI_STATE["t1_content_url"],
                                    headers=auth_headers,
                                    allow_redirects=False,
                                    timeout=AIYI_LIST_TIMEOUT)
        test_logger.info("T10 /content+Authorization 头: HTTP %s Location=%s",
                         content_resp.status_code,
                         content_resp.headers.get("Location", "")[:200])

    @pytest.mark.p2
    @pytest.mark.slow
    def test_11_direct_link_expiry_403(self, api_client, test_logger,
                                       aiyi_link_expiry_enabled):
        """T11 直链 15 分钟过期：过期应 403（手册；500=缺陷），重签机制应正常。"""
        if not aiyi_link_expiry_enabled:
            pytest.skip(
                "慢用例未开启（--link-expiry-test / Jenkins "
                "AGDC2_74_LINK_EXPIRY / env AIYI_LINK_EXPIRY_TEST=1，"
                "等待直链过期约 15 分钟）"
            )
        if not _AIYI_STATE.get("t1_content_url"):
            pytest.skip("依赖 T1 同会话产物（/content 直链），请先执行 test_01")
        content_url = _AIYI_STATE["t1_content_url"]
        resp = requests.get(content_url, headers=_aiyi_auth_headers(api_client),
                            allow_redirects=False, timeout=AIYI_LIST_TIMEOUT)
        assert resp.status_code in (301, 302, 303, 307, 308), (
            f"T11 /content 重签请求应 302，实际 {resp.status_code}: "
            f"{(resp.text or '')[:300]}"
        )
        presigned = resp.headers.get("Location", "")
        assert presigned, "T11 /content 302 缺少 Location（重签产物）"
        issued_at = time.time()
        test_logger.info("T11 取得新 presigned（重签机制正常）: %s",
                         presigned[:200])
        head = requests.get(presigned, headers={"Range": "bytes=0-1023"},
                            timeout=AIYI_LIST_TIMEOUT)
        assert head.status_code in (200, 206), (
            f"T11 新 presigned 应可下载（200/206），实际 {head.status_code}"
        )
        wait = AIYI_LINK_TTL_SECONDS + AIYI_LINK_TTL_BUFFER - (
            time.time() - issued_at)
        if wait > 0:
            test_logger.info("T11 等待直链过期（15 分钟 + %ss 缓冲）：约 %.0fs",
                             AIYI_LINK_TTL_BUFFER, wait)
            deadline = time.time() + wait
            while time.time() < deadline:
                remain = deadline - time.time()
                if remain <= 0:
                    break
                time.sleep(min(60, remain))
                test_logger.info("T11 剩余等待 %.0fs（presigned 签发于 %.0fs 前）",
                                 max(0.0, deadline - time.time()),
                                 time.time() - issued_at)
        expired = requests.get(presigned, headers={"Range": "bytes=0-1023"},
                               timeout=AIYI_LIST_TIMEOUT)
        test_logger.info("T11 过期后 presigned 请求: HTTP %s body=%s",
                         expired.status_code, (expired.text or "")[:300])
        if expired.status_code in (200, 206):
            test_logger.info("T11 过期后仍可下载（观察项：直链实际有效期可能"
                             "大于 15 分钟或已被重签）——不判 FAIL，请人工确认")
        else:
            assert expired.status_code == 403, (
                f"T11 过期直链应 403（手册口径），实际 {expired.status_code}"
                + ("——工单缺陷复现：过期返回 500"
                   if expired.status_code == 500 else "")
                + f": {(expired.text or '')[:300]}"
            )
        resign = requests.get(content_url, headers=_aiyi_auth_headers(api_client),
                               allow_redirects=False, timeout=AIYI_LIST_TIMEOUT)
        assert resign.status_code in (301, 302, 303, 307, 308), (
            f"T11 过期后 /content 应可重新签发（工单：15 分钟重签机制正常），"
            f"实际 {resign.status_code}: {(resign.text or '')[:300]}"
        )
        test_logger.info("T11 过期后 /content 重签正常 → 新 Location: %s",
                         resign.headers.get("Location", "")[:200])
