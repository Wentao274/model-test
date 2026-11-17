"""浙江讯盟工单 AGDC2-61 glm-5.3 功能对比失败场景 45 用例复现套件。

数据源（用户指定 2026-11-16）：九章 glm-5.3 功能对比报告 20261110
（GLM-5.3 功能测试对比·智谱官方 vs 九章，277,381 字节）——报告展开
的 42 个失败用例全量覆盖（OpenAI Chat Completions 33 条 + OpenAI
Responses 9 条）；官方基线同样不通过的 KS-MSG-001 / KS-N-001 /
KS-TOOL-009 三条在 20261110 报告中被移除（口径：不算供应商问题），
后依据九章新 url 功能测试报告 20261116（AGDC2-66，45 条复测）按
用户确认 2026-11-17 补入为 #43-#45——断言基准取九章新 url 复测行为
（官方基线异常或双方一致放行，官方 500/400 不可作断言基准），作为
守护口径：平台行为与九章复测基线不符即判 FAIL；响应正文/思考内容
无明确验证要求时只断非空。

实现口径（用户确认 2026-11-16）：
- 请求按报告「实际传参」原始报文原样重放（model 字段运行时替换为
  部署模型名；RESP-019 缺失 model 不注入；RESP-018 报告原文
  assistant content 疑似生成截断为畸形键，按用户确认修正为完整
  句子「Understood. The launch is Tuesday with support notified
  beforehand.」）；
- 预期结果遵循智谱官方行为（报告智谱官方侧实测基线 run
  20261028_191525；官方错误体为 {"error":{"code","message"}}
  结构，code 为字符串）：
  - 4xx 拒绝类：HTTP 状态码 + error 外层结构 + error.code 三重
    对齐官方（报告根因一「错误体缺 error 外层」16 条即靠结构
    断言暴露；OUT-013 官方 error.code="400"——Java 侧 JSON
    反序列化失败的透传形态）；
  - top_p 差异确认两条（KS-SMP-002=1.1 / SMP-TOPP-005=1.5）按
    用户确认取严格官方口径断言 200：平台返回 4xx 判失败，作为
    「九章比官方更严格」的差异暴露（报告口径：不建议平台改、
    仅差异记录，需修的只有错误体外层）；
  - Open Responses 协议 9 条官方基线未实测，按报告判定依据
    （openresponses 规范口径）断言：ResponseResource 必填字段
    取报告点名 8 项（completed_at / presence_penalty /
    frequency_penalty / top_logprobs / max_tool_calls /
    background / service_tier / safety_identifier）+
    object=response / status=completed / output 非空基础断言 +
    各用例专属断言（SSE 逐事件 type+sequence_number 与事件内
    response 必填字段、function_call 条目、multi-turn 用上历史、
    assistant phase 接受）；
  - RESP-015 image-input 按用户确认以「4xx 且错误体含明确错误
    信息」判通过（glm-5.3 文本模型，与 VIS-URL-001 官方 400 行
    为一致；报告建议改用例而非改供应商）；
  - THK-005 官方 400 即通过（含结构断言）；若放行 200，失败信
    息附加诊断——content 是否泄漏思考原文（字面量检查在代码
    内保留原始 ASCII 形态，展示面用全角 token）。

协议端点：
- chat:     POST {api_prefix}/chat/completions（Authorization: Bearer）；
- responses: POST {api_prefix}/responses（Authorization: Bearer）；
- compact:  POST {api_prefix}/responses/compact（Authorization: Bearer）。

请求报文口径：
- 采样参数豁免：conftest RAW_SAMPLING_EXEMPT_FILES 整模块豁免
  （同 test_k / test_lexin 口径），报告原始报文原样发送，不注入
  采样参数；
- marker：zjxm_agdc2_61（conftest 按 test_zjxm_ 前缀自动打标；
  默认收集排除——仅显式点名时执行，与 Jenkinsfile MARKER_ALL
  排除互为双保险）。

报告（base/zjxm_html_report.py）：官方预期 vs 实测对比样式 HTML +
邮件提取用 MD（录制记录会话末导出 zjxm_records.json）。
"""

import inspect
import json
import time

import pytest
import requests

from typing import Any, Dict, Optional


def _zjxm_current_test() -> str:
    """栈回溯取当前所属用例方法名（test_* 帧）；无则返回 'unknown'。"""
    for fr in inspect.stack():
        fn = fr.function
        if fn.startswith("test_"):
            return fn
    return "unknown"


def _zjxm_mask_key(headers: Optional[dict]) -> Dict[str, Any]:
    """请求头脱敏副本：鉴权值打码（前4+****+后4），其余原样。"""
    masked = {}
    for k, v in (headers or {}).items():
        lk = str(k).lower()
        if lk in ("authorization", "x-api-key") and v:
            s = str(v)
            if len(s) <= 12:
                masked[k] = "****"
            else:
                masked[k] = s[:4] + "****" + s[-4:]
        else:
            masked[k] = v
    return masked


def _zjxm_record(test: str, url: str, kind: str, headers: Optional[dict],
                 payload: Optional[dict], status=None, elapsed=None,
                 resp_headers=None, resp_body=None, error=None):
    """录制一条请求记录（内存态，会话末由 conftest 导出）。"""
    _ZJXM_RECORDER.append({
        "test": test,
        "url": url,
        "kind": kind,
        "req_headers": _zjxm_mask_key(headers),
        "req_body": payload,
        "status": status,
        "elapsed": elapsed,
        "resp_headers": dict(resp_headers) if resp_headers else {},
        "resp_body": resp_body,
        "error": str(error) if error else None,
    })


# 全量请求录制（报告数据源）：每请求一条，内存态；conftest 在会话末
# 导出 JSON 并生成 HTML/MD 报告（base/zjxm_html_report.py）。
_ZJXM_RECORDER: list = []

# THK-005 思考原文泄漏检查用闭合 token 字面量（原始 ASCII 形态，
# 展示面统一用全角 ＜/think＞）。
_ZJXM_THINK_CLOSE = chr(60) + "/think" + chr(62)

# ResponseResource 报告点名 8 个必填字段（用户确认口径：报告点名
# 8 字段 + 基础断言；报告提及「另有 3 处未逐条列出」无字段名）。
_ZJXM_RESP_REQUIRED_FIELDS = (
    "completed_at",
    "presence_penalty",
    "frequency_penalty",
    "top_logprobs",
    "max_tool_calls",
    "background",
    "service_tier",
    "safety_identifier",
)


def _zjxm_url(kind: str, api_client) -> str:
    if kind == "chat":
        return f"{api_client.api_prefix}/chat/completions"
    if kind == "compact":
        return f"{api_client.api_prefix}/responses/compact"
    return f"{api_client.api_prefix}/responses"


def _zjxm_headers(kind: str, api_client) -> Dict[str, Any]:
    headers: Dict[str, Any] = {"Content-Type": "application/json"}
    if api_client.api_key:
        headers["Authorization"] = f"Bearer {api_client.api_key}"
    return headers


def _zjxm_stream_flag(payload: dict) -> bool:
    v = payload.get("stream")
    return v is True or v == 1 or v == "1" or (
        isinstance(v, str) and v.strip().lower() == "true"
    )


def _zjxm_json_summary(kind: str, data) -> Dict[str, Any]:
    content = reasoning = ""
    err_bit = 0
    finish_reason = None
    usage = None
    if isinstance(data, dict):
        if data.get("error"):
            err_bit = 1
        if kind == "chat":
            try:
                ch = data["choices"][0]
                msg = ch.get("message") or {}
                content = msg.get("content") or ""
                reasoning = msg.get("reasoning_content") or ""
                finish_reason = ch.get("finish_reason")
            except Exception:
                pass
            u = data.get("usage")
            usage = u if isinstance(u, dict) else None
        elif kind in ("responses", "compact"):
            out = data.get("output")
            if isinstance(out, list):
                for item in out:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "reasoning":
                        for s in item.get("summary") or []:
                            if isinstance(s, dict) and s.get("text"):
                                reasoning += s["text"]
                    if item.get("type") == "message":
                        for c in item.get("content") or []:
                            if isinstance(c, dict) and c.get("text"):
                                content += c["text"]
            u = data.get("usage")
            usage = u if isinstance(u, dict) else None
    return {"err_bit": err_bit, "content": content, "reasoning": reasoning,
            "usage": usage, "finish_reason": finish_reason}


def _zjxm_sse_summary(kind: str, lines) -> Dict[str, Any]:
    content = reasoning = ""
    err_bit = 0
    done = False
    finish_reason = None
    usage = None
    for ln in lines:
        if ln.strip() == "data: [DONE]":
            done = True
            continue
        if not ln.startswith("data:"):
            continue
        try:
            ev = json.loads(ln[5:].strip())
        except Exception:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("error"):
            err_bit = 1
        if kind == "chat":
            try:
                ch = ev["choices"][0]
                if ch.get("finish_reason"):
                    finish_reason = ch["finish_reason"]
                delta = ch.get("delta") or {}
                content += delta.get("content") or ""
                reasoning += delta.get("reasoning_content") or ""
            except Exception:
                pass
            if isinstance(ev.get("usage"), dict):
                usage = ev["usage"]
        elif kind in ("responses", "compact"):
            et = ev.get("type")
            resp_obj = ev.get("response") or {}
            if et == "error" or (et == "response.failed" and resp_obj.get("error")):
                err_bit = 1
            if et == "response.output_text.delta" and ev.get("delta"):
                content += ev["delta"]
            if et == "response.reasoning_summary_text.delta" and ev.get("delta"):
                reasoning += ev["delta"]
            if et == "response.completed":
                done = True
                u = resp_obj.get("usage")
                if isinstance(u, dict):
                    usage = u
    return {"err_bit": err_bit, "content": content, "reasoning": reasoning,
            "done": done, "finish_reason": finish_reason, "usage": usage}


def _zjxm_send(api_client, kind: str, payload: dict) -> Dict[str, Any]:
    """发送一条请求并录制；返回 状态/原始报文/解析结果 摘要。

    流式请求额外返回 events（逐 SSE data 事件解析结果，供
    RESP-012 逐事件断言）。
    """
    test = _zjxm_current_test()
    url = _zjxm_url(kind, api_client)
    headers = _zjxm_headers(kind, api_client)
    streaming = _zjxm_stream_flag(payload)
    t0 = time.time()
    try:
        resp = api_client.session.post(
            url, json=payload, headers=headers,
            timeout=api_client.timeout, stream=streaming,
        )
    except Exception as e:
        _zjxm_record(test, url, kind, headers, payload,
                    error=e, elapsed=time.time() - t0)
        pytest.fail(f"请求发送异常（{url}）: {e}")
    status = resp.status_code
    if streaming:
        lines = [ln for ln in resp.iter_lines(decode_unicode=True) if ln]
        elapsed = time.time() - t0
        _zjxm_record(test, url, kind, headers, payload,
                     status=status, elapsed=elapsed,
                     resp_headers=resp.headers,
                     resp_body="\n".join(lines))
        if lines and any(ln.startswith("data:") for ln in lines):
            s = _zjxm_sse_summary(kind, lines)
            events = []
            for ln in lines:
                if ln.strip() == "data: [DONE]" or not ln.startswith("data:"):
                    continue
                try:
                    ev = json.loads(ln[5:].strip())
                except Exception:
                    continue
                if isinstance(ev, dict):
                    events.append(ev)
            return {"status": status, "raw": f"<SSE 共 {len(lines)} 行>",
                    "json": None, "err_bit": s["err_bit"], "content": s["content"],
                    "reasoning": s["reasoning"], "usage": s["usage"],
                    "finish_reason": s["finish_reason"], "sse": True,
                    "done": s["done"], "events": events}
        raw = "\n".join(lines)
    else:
        raw = resp.text
        elapsed = time.time() - t0
        _zjxm_record(test, url, kind, headers, payload,
                     status=status, elapsed=elapsed,
                     resp_headers=resp.headers,
                     resp_body=raw)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    s = _zjxm_json_summary(kind, parsed)
    return {"status": status, "raw": raw, "json": parsed, "err_bit": s["err_bit"],
            "content": s["content"], "reasoning": s["reasoning"], "usage": s["usage"],
            "finish_reason": s["finish_reason"], "sse": False, "done": None,
            "events": []}


# ---------------------------------------------------------------------------
# 断言辅助（断言消息统一「#N 请求 M」前缀，供报告生成器定位失败请求）
# ---------------------------------------------------------------------------

def _zjxm_assert_chat_400(result: Dict[str, Any], no: int, code: str) -> dict:
    """chat 4xx 拒绝类官方基准断言：HTTP 400 + error 外层 + error.code。

    官方错误体结构 {"error":{"code":"<str>","message":"<str>"}}；报告
    根因一（错误体缺 error 外层）由本断言的 error 外层检查暴露。
    Returns: error dict（message 可供日志）。
    """
    assert result["status"] == 400, (
        f"#{no} 请求 1 官方基准 HTTP 400，实测 HTTP {result['status']}；"
        f"响应: {result['raw'][:300]}"
    )
    body = result["json"] if isinstance(result["json"], dict) else {}
    err = body.get("error")
    assert isinstance(err, dict) and err, (
        f"#{no} 请求 1 官方错误体为 error 外层结构（error.code={code}），"
        f"实测缺少 error 外层或为空；响应: {result['raw'][:300]}"
    )
    got = err.get("code")
    assert str(got) == str(code), (
        f"#{no} 请求 1 官方 error.code={code}，实测 error.code={got!r}；"
        f"错误体: {result['raw'][:300]}"
    )
    return err


def _zjxm_assert_chat_200_content(result: Dict[str, Any], no: int) -> None:
    """chat 200 类官方基准断言：HTTP 200 + 正文非空字符串。"""
    assert result["status"] == 200, (
        f"#{no} 请求 1 官方基准 HTTP 200，实测 HTTP {result['status']}；"
        f"响应: {result['raw'][:300]}"
    )
    assert isinstance(result["content"], str) and result["content"].strip(), (
        f"#{no} 请求 1 官方返回 200 且正文非空，实测正文为空；"
        f"响应: {result['raw'][:300]}"
    )


def _zjxm_resp_missing(r) -> list:
    """ResponseResource 必填字段缺失清单（非 dict 视为全缺）。"""
    if not isinstance(r, dict):
        return list(_ZJXM_RESP_REQUIRED_FIELDS)
    return [f for f in _ZJXM_RESP_REQUIRED_FIELDS if f not in r]


def _zjxm_resp_output_text(body: dict) -> str:
    """提取 Responses output 中全部 message/output_text 文本。"""
    text = ""
    out = body.get("output")
    if isinstance(out, list):
        for item in out:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for c in item.get("content") or []:
                    if isinstance(c, dict) and c.get("text"):
                        text += c["text"]
    return text


def _zjxm_assert_resp_resource(result: Dict[str, Any], no: int) -> dict:
    """Responses 非流式用例规范基准断言（报告判定依据口径）。

    HTTP 200 + ResponseResource 报告点名 8 必填字段 + object=response
    + status=completed + output 非空。Returns: 响应 body dict。
    """
    assert result["status"] == 200, (
        f"#{no} 请求 1 规范基准 HTTP 200，实测 HTTP {result['status']}；"
        f"响应: {result['raw'][:300]}"
    )
    body = result["json"]
    assert isinstance(body, dict), (
        f"#{no} 请求 1 响应应为 JSON 对象，实测: {result['raw'][:300]}"
    )
    missing = _zjxm_resp_missing(body)
    assert not missing, (
        f"#{no} 请求 1 ResponseResource 缺少规范必填字段（报告点名 8 项）: "
        f"{missing}；响应: {result['raw'][:400]}"
    )
    assert body.get("object") == "response", (
        f"#{no} 请求 1 object 应为 response，实测 {body.get('object')!r}；"
        f"响应: {result['raw'][:300]}"
    )
    assert body.get("status") == "completed", (
        f"#{no} 请求 1 status 应为 completed，实测 {body.get('status')!r}；"
        f"响应: {result['raw'][:300]}"
    )
    out = body.get("output")
    assert isinstance(out, list) and out, (
        f"#{no} 请求 1 output 应为非空数组，实测 {out!r}；"
        f"响应: {result['raw'][:300]}"
    )
    return body


class TestZjxmAGDC2_61:
    """浙江讯盟 AGDC2-61 glm-5.3 功能对比报告 42 失败用例复现。"""

    # ------------------------------------------------------------------
    # 一、空输入放行组（报告根因二：4 条——content null/空串/空数组/缺失）
    # ------------------------------------------------------------------

    def test_01_chat_user_content_null(self, api_client, test_logger):
        """#1 CUS-001 user.content 传 null，应 400（优先整改）

        来源: 九章对比报告 20261110 · CUS-001（智谱官方基线 run 20261028_191525 实测）。
        官方基准: HTTP 400，error.code=1213「未正常接收到prompt参数。」——content 必填，null 一律 400。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1213；九章实测放行 200 并烧满 200 token（正文空、全部 token 花在无关思考上）属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": null,
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 1, "1213")
        test_logger.info("#1 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1213）",
                         result["status"], err)

    def test_02_chat_user_content_empty_string(self, api_client, test_logger):
        """#2 REQ-MSG-004 user.content 为空字符串，应 400（优先整改）

        来源: 九章对比报告 20261110 · REQ-MSG-004（2026-10-19 官方实测）。
        官方基准: HTTP 400，error.code=1213「未正常接收到prompt参数。」——content 必填非空。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1213；九章实测放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 2, "1213")
        test_logger.info("#2 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1213）",
                         result["status"], err)

    def test_03_chat_user_content_empty_array(self, api_client, test_logger):
        """#3 REQ-MSG-005 user.content 为空数组，应 400（优先整改）

        来源: 九章对比报告 20261110 · REQ-MSG-005（2026-10-19 官方实测）。
        官方基准: HTTP 400，error.code=1213「未正常接收到prompt参数。」——content 必填非空。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1213；九章实测放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": [],
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 3, "1213")
        test_logger.info("#3 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1213）",
                         result["status"], err)

    def test_22_chat_user_content_missing(self, api_client, test_logger):
        """#22 KS-ROB-020 role=user content 缺失，应 4xx（建议整改）

        来源: 九章对比报告 20261110 · KS-ROB-020（KS robust-messages-user-content-missing）。
        官方基准: HTTP 400，error.code=1213「未正常接收到prompt参数。」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1213；九章实测放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "role": "user"
    }
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 22, "1213")
        test_logger.info("#22 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1213）",
                         result["status"], err)

    # ------------------------------------------------------------------
    # 二、thinking / reasoning_effort 参数组
    # ------------------------------------------------------------------

    def test_04_chat_thinking_adaptive(self, api_client, test_logger):
        """#4 THK-004 thinking.type=adaptive 非法值，应 400（优先整改）

        来源: 九章对比报告 20261110 · THK-004（报告根因三：thinking.type 只挡了 disabled 没做白名单）。
        官方基准: HTTP 400，error.code=1210「该模型始终思考，不支持关闭思考；请使用 low、high 或 max。」——GLM-5.3 仅支持 enabled。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210；九章实测静默放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "adaptive"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 4, "1210")
        test_logger.info("#4 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_05_chat_effort_xhigh(self, api_client, test_logger):
        """#5 EFF-101 reasoning_effort=xhigh，5.3 不支持，应 400（优先整改）

        来源: 九章对比报告 20261110 · EFF-101。
        官方基准: HTTP 400，error.code=1210「该模型始终思考，不支持关闭思考；请使用 low、high 或 max。」——GLM-5.3 仅支持 low/high/max。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（状态码/错误码官方一致，报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "reasoning_effort": "xhigh"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 5, "1210")
        test_logger.info("#5 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_06_chat_effort_medium(self, api_client, test_logger):
        """#6 EFF-102 reasoning_effort=medium，5.3 不支持，应 400（优先整改）

        来源: 九章对比报告 20261110 · EFF-102。
        官方基准: HTTP 400，error.code=1210——GLM-5.3 仅支持 low/high/max 档位。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "reasoning_effort": "medium"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 6, "1210")
        test_logger.info("#6 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_07_chat_effort_minimal(self, api_client, test_logger):
        """#7 EFF-103 reasoning_effort=minimal，5.3 不支持，应 400（优先整改）

        来源: 九章对比报告 20261110 · EFF-103。
        官方基准: HTTP 400，error.code=1210——GLM-5.3 仅支持 low/high/max 档位。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "reasoning_effort": "minimal"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 7, "1210")
        test_logger.info("#7 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_08_chat_effort_none(self, api_client, test_logger):
        """#8 EFF-104 reasoning_effort=none，5.3 不支持，应 400（优先整改）

        来源: 九章对比报告 20261110 · EFF-104。
        官方基准: HTTP 400，error.code=1210——GLM-5.3 始终思考，不支持关闭。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "reasoning_effort": "none"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 8, "1210")
        test_logger.info("#8 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_09_chat_effort_ultra(self, api_client, test_logger):
        """#9 EFF-105 reasoning_effort=ultra 非法值，应 400（优先整改）

        来源: 九章对比报告 20261110 · EFF-105。
        官方基准: HTTP 400，error.code=1210——非法值拒绝。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "reasoning_effort": "ultra"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 9, "1210")
        test_logger.info("#9 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_12_chat_thinking_disabled(self, api_client, test_logger):
        """#12 THK-003 thinking.type=disabled，5.3 强制思考，应 400（优先整改）

        来源: 九章对比报告 20261110 · THK-003（2026-10-19 官方实测）。
        官方基准: HTTP 400，error.code=1210「该模型始终思考，不支持关闭思考；请使用 low、high 或 max。」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "disabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 12, "1210")
        test_logger.info("#12 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_13_chat_thinking_disabled_no_think_leak(self, api_client, test_logger):
        """#13 THK-005 disabled 若被放行，正文不得泄漏思考原文（优先整改）

        来源: 九章对比报告 20261110 · THK-005（THK-003 的补充断言，单独成例）。
        官方基准: HTTP 400，error.code=1210——官方 disabled 直接拒绝，400 即通过。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210；若网关放行 200，失败信息附加诊断——content 是否泄漏＜/think＞及之前的思考原文（2026-10-19 生产复查曾出现「思考原文＜/think＞正文」形态）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "disabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        st = result["status"]
        if st != 400:
            leak = _ZJXM_THINK_CLOSE in (result["content"] or "")
            assert st == 400, (
                f"#13 请求 1 官方基准 HTTP 400（disabled 应拒绝），实测 HTTP {st}"
                + ("；网关放行且 content 出现＜/think＞思考原文泄漏（放行场景要求 content 不得泄漏思考原文）" if st == 200 and leak else "")
                + f"；响应: {result['raw'][:300]}"
            )
        err = _zjxm_assert_chat_400(result, 13, "1210")
        test_logger.info("#13 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_14_chat_disabled_plus_effort_low(self, api_client, test_logger):
        """#14 MIG-002 未迁移写法 disabled+reasoning_effort=low，应 400（优先整改）

        来源: 九章对比报告 20261110 · MIG-002（迁移提示场景）。
        官方基准: HTTP 400，error.code=1210——thinking.type 需改为 enabled 并设置 reasoning_effort=low；只加 low 不改 disabled 仍应失败。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210；九章若静默放行即判失败（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "reasoning_effort": "low",
  "thinking": {
    "type": "disabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 14, "1210")
        test_logger.info("#14 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    # ------------------------------------------------------------------
    # 三、数值边界组
    # ------------------------------------------------------------------

    def test_10_chat_max_tokens_over_limit(self, api_client, test_logger):
        """#10 ERR-003 max_tokens=200000 超上限，应 400（优先整改）

        来源: 九章对比报告 20261110 · ERR-003。
        官方基准: HTTP 400，error.code=1210「max_tokens参数非法：限制数值范围[1,131072]」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200000,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 10, "1210")
        test_logger.info("#10 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_17_chat_max_tokens_zero(self, api_client, test_logger):
        """#17 OUT-012 max_tokens=0 越下界，应 400（整改）

        来源: 九章对比报告 20261110 · OUT-012。
        官方基准: HTTP 400，error.code=1210「max_tokens参数非法：限制数值范围[1,131072]」——minimum 1。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210；九章实测放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 0,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 17, "1210")
        test_logger.info("#17 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_18_chat_stop_string(self, api_client, test_logger):
        """#18 OUT-013 stop 传字符串，仅支持数组，应 400（整改）

        来源: 九章对比报告 20261110 · OUT-013（2026-10-19 官方实测）。
        官方基准: HTTP 400，error.code=400（Java 侧 JSON 反序列化失败透传——stop 需为数组，字符串 "。" 无法反序列化为 ArrayList）。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=400；九章实测静默当单元素数组放行 200、思考中途命中停止词正文为空，属静默数据错误（报告：比报错更危险）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "stop": "。",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 18, "400")
        test_logger.info("#18 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 400）",
                         result["status"], err)

    # ------------------------------------------------------------------
    # 四、messages 结构与 role 非法组
    # ------------------------------------------------------------------

    def test_11_chat_system_only_no_user(self, api_client, test_logger):
        """#11 REQ-MSG-006 仅 system 无 user 消息，应 400（优先整改）

        来源: 九章对比报告 20261110 · REQ-MSG-006（2026-10-19 官方实测）。
        官方基准: HTTP 400，error.code=1214「messages 参数非法。请检查文档。」——messages 需包含 user 消息。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": "你是一个有用的助手。",
      "role": "system"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 11, "1214")
        test_logger.info("#11 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_19_chat_assistant_content_list(self, api_client, test_logger):
        """#19 KS-ROB-003 role=assistant content 为 list，应 4xx（整改）

        来源: 九章对比报告 20261110 · KS-ROB-003（KS robust-messages-assistant-content-list）。
        官方基准: HTTP 400，error.code=1214「messages[0].content[0].type:不能为空」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214；九章实测 content 传 list 触发内部异常返回 500（同形态 dict/int 均正确 400，仅 list 500），属缺陷复现（报告建议 P2 提级 P1）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": [
        123
      ],
      "role": "assistant"
    },
    {
      "content": "继续",
      "role": "user"
    }
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 19, "1214")
        test_logger.info("#19 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_20_chat_system_content_list(self, api_client, test_logger):
        """#20 KS-ROB-011 role=system content 为 list，应 4xx（整改）

        来源: 九章对比报告 20261110 · KS-ROB-011（KS robust-messages-system-content-list）。
        官方基准: HTTP 400，error.code=1214「messages[0].content[0].type:不能为空」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214；九章实测 500 属缺陷复现（三条 KS-ROB-003/011/019 同根因）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": [
        123
      ],
      "role": "system"
    },
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 20, "1214")
        test_logger.info("#20 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_21_chat_user_content_list(self, api_client, test_logger):
        """#21 KS-ROB-019 role=user content 为 list，应 4xx（整改）

        来源: 九章对比报告 20261110 · KS-ROB-019（KS robust-messages-user-content-list）。
        官方基准: HTTP 400，error.code=1214「messages[0].content[0].type:不能为空」——报告口径 200 或 4xx 均可、不得 5xx；按官方行为取 400。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214；九章实测 500（标准 error 包装但属另一代码路径）属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 200,
  "messages": [
    {
      "content": [
        123
      ],
      "role": "user"
    }
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 21, "1214")
        test_logger.info("#21 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_27_chat_role_empty_string(self, api_client, test_logger):
        """#27 KS-ROB-023 messages[].role 为空串，应 4xx（建议整改）

        来源: 九章对比报告 20261110 · KS-ROB-023（KS robust-messages-role-empty-string）。
        官方基准: HTTP 400，error.code=1214「角色信息不能为空」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 64,
  "messages": [
    {
      "content": "你好",
      "role": ""
    }
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 27, "1214")
        test_logger.info("#27 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_28_chat_role_invalid(self, api_client, test_logger):
        """#28 KS-ROB-025 messages[].role 为非法值，应 4xx（建议整改）

        来源: 九章对比报告 20261110 · KS-ROB-025（KS robust-messages-role-invalid）。
        官方基准: HTTP 400，error.code=1214「角色信息不正确」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 64,
  "messages": [
    {
      "content": "你好",
      "role": "unknown_role"
    }
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 28, "1214")
        test_logger.info("#28 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_29_chat_role_missing(self, api_client, test_logger):
        """#29 KS-ROB-026 messages[].role 缺失，应 4xx（建议整改）

        来源: 九章对比报告 20261110 · KS-ROB-026（KS robust-messages-role-missing）。
        官方基准: HTTP 400，error.code=1214「角色信息不能为空」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 64,
  "messages": [
    {
      "content": "你好"
    }
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 29, "1214")
        test_logger.info("#29 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_30_chat_role_whitespace(self, api_client, test_logger):
        """#30 KS-ROB-027 messages[].role 为空白串，应 4xx（建议整改）

        来源: 九章对比报告 20261110 · KS-ROB-027（KS robust-messages-role-whitespace）。
        官方基准: HTTP 400，error.code=1214「角色信息不能为空」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 64,
  "messages": [
    {
      "content": "你好",
      "role": "  "
    }
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 30, "1214")
        test_logger.info("#30 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    # ------------------------------------------------------------------
    # 五、request_id / user_id 长度越界组（下游存储字段，minLength/maxLength）
    # ------------------------------------------------------------------

    def test_23_chat_request_id_len5(self, api_client, test_logger):
        """#23 CONV-RID-005 request_id 长度 5 越下界，应 400（建议整改）

        来源: 九章对比报告 20261110 · CONV-RID-005。
        官方基准: HTTP 400，error.code=1214「request_id:The request task ID length must be between 6 and 64 characters.」（minLength 6）。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214；九章实测放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 100,
  "messages": [
    {
      "content": "hi",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "request_id": "rrrrr"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 23, "1214")
        test_logger.info("#23 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_24_chat_request_id_len65(self, api_client, test_logger):
        """#24 CONV-RID-065 request_id 长度 65 越上界，应 400（建议整改）

        来源: 九章对比报告 20261110 · CONV-RID-065。
        官方基准: HTTP 400，error.code=1214「request_id:The request task ID length must be between 6 and 64 characters.」（maxLength 64）。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214；九章实测放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 100,
  "messages": [
    {
      "content": "hi",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "request_id": "r"
}
"""
        )
        payload["model"] = api_client.model_name
        payload["request_id"] = "r" * 65  # 报告原文 65 字符（越上界，maxLength 64）
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 24, "1214")
        test_logger.info("#24 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_25_chat_user_id_len5(self, api_client, test_logger):
        """#25 CONV-UID-005 user_id 长度 5 越下界，应 400（建议整改）

        来源: 九章对比报告 20261110 · CONV-UID-005。
        官方基准: HTTP 400，error.code=1214「user_id:The unique ID of the user must be between 6 and 128 characters in length.」（minLength 6）。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214；九章实测放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 100,
  "messages": [
    {
      "content": "hi",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "user_id": "uuuuu"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 25, "1214")
        test_logger.info("#25 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    def test_26_chat_user_id_len129(self, api_client, test_logger):
        """#26 CONV-UID-129 user_id 长度 129 越上界，应 400（建议整改）

        来源: 九章对比报告 20261110 · CONV-UID-129。
        官方基准: HTTP 400，error.code=1214「user_id:The unique ID of the user must be between 6 and 128 characters in length.」（maxLength 128）。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1214；九章实测放行 200 属缺陷复现。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 100,
  "messages": [
    {
      "content": "hi",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "user_id": "u"
}
"""
        )
        payload["model"] = api_client.model_name
        payload["user_id"] = "u" * 129  # 报告原文 129 字符（越上界，maxLength 128）
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 26, "1214")
        test_logger.info("#26 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1214）",
                         result["status"], err)

    # ------------------------------------------------------------------
    # 六、工具调用 / 多模态输入
    # ------------------------------------------------------------------

    def test_16_chat_tool_choice_nonexistent(self, api_client, test_logger):
        """#16 KS-TOOL-003 tool_choice 指定不存在的函数名，应 4xx（整改）

        来源: 九章对比报告 20261110 · KS-TOOL-003（2026-09-29 KS 实测小马正式返回 500）。
        官方基准: HTTP 400，error.code=1210「API 调用参数有误，请检查文档。」——GLM-5.3 官方 tool_choice 仅支持 auto；指向 tools 里不存在的函数应 4xx，不得 5xx。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 500,
  "messages": [
    {
      "content": "帮我查一下北京的天气。",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "tool_choice": {
    "function": {
      "name": "nonexistent_function_xyz"
    },
    "type": "function"
  },
  "tools": [
    {
      "function": {
        "description": "获取指定城市的天气信息，返回温度和天气状况",
        "name": "get_weather",
        "parameters": {
          "properties": {
            "city": {
              "description": "城市名称",
              "type": "string"
            }
          },
          "required": [
            "city"
          ],
          "type": "object"
        }
      },
      "type": "function"
    }
  ]
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 16, "1210")
        test_logger.info("#16 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    def test_33_chat_image_url_text_model(self, api_client, test_logger):
        """#33 VIS-URL-001 图片传公网 URL，文本模型应拒绝（建议整改）

        来源: 九章对比报告 20261110 · VIS-URL-001（ChatCompletionVisionRequest：仅 GLM-5.3-Flash 系列支持视觉理解，GLM-5.3 为文本模型）。
        官方基准: HTTP 400，error.code=1210「messages.content.type 参数非法，取值范围 ['text']」。
        断言口径: 官方行为——HTTP 400 + error 外层 + error.code=1210（报告失败点为错误体缺 error 外层）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 1024,
  "messages": [
    {
      "content": [
        {
          "image_url": {
            "url": "http://115.191.70.236:18080/report-20260923-062409-f92b96/content_k3_red_square.png"
          },
          "type": "image_url"
        },
        {
          "text": "这张图里有什么？请说出颜色和文字。",
          "type": "text"
        }
      ],
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        err = _zjxm_assert_chat_400(result, 33, "1210")
        test_logger.info("#33 请求 1 实测: HTTP %s, error=%s（官方: HTTP 400 code 1210）",
                         result["status"], err)

    # ------------------------------------------------------------------
    # 七、top_p 差异确认组（严格官方口径：官方实测均 200）
    # ------------------------------------------------------------------

    def test_31_chat_top_p_1_1_official_accepts(self, api_client, test_logger):
        """#31 KS-SMP-002 top_p=1.1 官方接受，严格官方口径断言 200（差异确认）

        来源: 九章对比报告 20261110 · KS-SMP-002（差异确认·不建议改——九章 400 更符合文档，官方放行才是官方的问题）。
        官方基准: HTTP 200，正常 chat completion 返回（文档范围 [0.01,1]，官方实测接受 1.1）。
        断言口径: 用户确认严格官方——HTTP 200 + 正文非空；平台返回 4xx 判失败，作为「九章比官方更严格」差异暴露；若返回 400，错误体仍应带 error 外层（报告要求）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 500,
  "messages": [
    {
      "content": "请用一句话介绍人工智能。",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "temperature": 1.0,
  "thinking": {
    "type": "enabled"
  },
  "top_p": 1.1
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        if result["status"] != 200:
            body = result["json"] if isinstance(result["json"], dict) else {}
            if result["status"] == 400:
                assert isinstance(body.get("error"), dict) and body["error"], (
                    f"#31 请求 1 top_p=1.1 平台返回 400 属「九章比官方更严格」差异（报告口径不建议改），"
                    f"但错误体应带 error 外层；实测: {result['raw'][:300]}"
                )
        _zjxm_assert_chat_200_content(result, 31)
        test_logger.info("#31 请求 1 实测: HTTP %s（官方: HTTP 200）", result["status"])

    def test_32_chat_top_p_1_5_official_accepts(self, api_client, test_logger):
        """#32 SMP-TOPP-005 top_p=1.5 官方接口接受，严格官方口径断言 200（差异确认）

        来源: 九章对比报告 20261110 · SMP-TOPP-005（差异确认·不建议改；2026-09-22 官方接口实测接受 1.5，为官方线上行为与文档不一致的探测记录）。
        官方基准: HTTP 200，正常 chat completion 返回。
        断言口径: 用户确认严格官方——HTTP 200 + 正文非空；平台返回 4xx 判失败，作为差异暴露；若返回 400，错误体仍应带 error 外层（报告要求）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 500,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  },
  "top_p": 1.5
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        if result["status"] != 200:
            body = result["json"] if isinstance(result["json"], dict) else {}
            if result["status"] == 400:
                assert isinstance(body.get("error"), dict) and body["error"], (
                    f"#32 请求 1 top_p=1.5 平台返回 400 属「九章比官方更严格」差异（报告口径不建议改），"
                    f"但错误体应带 error 外层；实测: {result['raw'][:300]}"
                )
        _zjxm_assert_chat_200_content(result, 32)
        test_logger.info("#32 请求 1 实测: HTTP %s（官方: HTTP 200）", result["status"])

    # ------------------------------------------------------------------
    # 八、响应字段集中校验（RSP-001 14 组，逐组报告不短路）
    # ------------------------------------------------------------------

    def test_15_chat_response_fields_all(self, api_client, test_logger):
        """#15 RSP-001 响应字段集中校验 14 组，逐项报告失败（优先整改）

        来源: 九章对比报告 20261110 · RSP-001（聚合 RSP-001～015 共 14 组字段断言，失败不短路）。
        官方基准: HTTP 200；顶层 id/request_id/created/model/object/choices/usage（request_id 与 id 同值）；choice 为 index/message/finish_reason（无 logprobs）；message 为 role/content/reasoning_content/tool_calls（无工具调用不返回 tool_calls）；usage 仅 prompt_tokens/completion_tokens/total_tokens/prompt_tokens_details.cached_tokens/completion_tokens_details.reasoning_tokens。
        断言口径: 官方行为——14 组字段逐组校验（组号沿用报告 RSP-001～015 编号），全部不符项一次报出；九章实测 choice 多出 logprobs、顶层缺 request_id（两处一行改动）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 500,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        test_logger.info("#15 请求 1 实测: HTTP %s, content=%r（官方: HTTP 200）",
                         result["status"], (result["content"] or "")[:60])
        failures = []

        def chk(gid: str, label: str, ok: bool, detail: str = ""):
            if not ok:
                failures.append(f"[{gid}] {label}" + (f"：{detail}" if detail else ""))

        body = result["json"]
        chk("[RSP-基础]", "HTTP 200 且响应为 JSON 对象",
            result["status"] == 200 and isinstance(body, dict),
            f"HTTP {result['status']}, body={result['raw'][:120]}")
        if not isinstance(body, dict):
            assert not failures, (
                f"#15 请求 1 响应字段集中校验失败 {len(failures)} 组："
                + "；".join(failures)
                + f"；响应: {result['raw'][:400]}"
            )
            return
        choices = body.get("choices")
        choice = choices[0] if isinstance(choices, list) and choices else None
        msg = (choice or {}).get("message") if isinstance(choice, dict) else None
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        chk("[RSP-001]", "id 为非空字符串",
            isinstance(body.get("id"), str) and bool(body["id"].strip()),
            repr(body.get("id")))
        chk("[RSP-002]", "object 为 chat.completion",
            body.get("object") == "chat.completion", repr(body.get("object")))
        chk("[RSP-003]", "created 为 Unix 秒",
            isinstance(body.get("created"), int) and body["created"] > 0,
            repr(body.get("created")))
        chk("[RSP-004]", "响应 model 等于请求",
            body.get("model") == api_client.model_name, repr(body.get("model")))
        chk("[RSP-005]", "index 为 0",
            isinstance(choice, dict) and choice.get("index") == 0,
            repr(choice.get("index") if isinstance(choice, dict) else None))
        chk("[RSP-006]", "role 为 assistant",
            isinstance(msg, dict) and msg.get("role") == "assistant",
            repr((msg or {}).get("role")))
        chk("[RSP-007]", "content 为字符串",
            isinstance(msg, dict) and isinstance(msg.get("content"), str),
            repr(type((msg or {}).get("content")).__name__))
        chk("[RSP-009]", "finish_reason 合法",
            isinstance(choice, dict) and choice.get("finish_reason") in
            ("stop", "length", "tool_calls"),
            repr((choice or {}).get("finish_reason")))
        chk("[RSP-010]", "prompt_tokens 正整数",
            isinstance(usage.get("prompt_tokens"), int)
            and usage["prompt_tokens"] > 0, repr(usage.get("prompt_tokens")))
        chk("[RSP-011]", "completion_tokens 正整数",
            isinstance(usage.get("completion_tokens"), int)
            and usage["completion_tokens"] > 0, repr(usage.get("completion_tokens")))
        chk("[RSP-012]", "total_tokens 严格等于两者之和",
            isinstance(usage.get("total_tokens"), int)
            and usage.get("total_tokens") ==
            (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0),
            repr(usage.get("total_tokens")))
        pt_details = usage.get("prompt_tokens_details")
        ct_details = usage.get("completion_tokens_details")
        chk("[RSP-013]", "usage.prompt_tokens_details.cached_tokens 表示缓存命中",
            isinstance(pt_details, dict)
            and isinstance(pt_details.get("cached_tokens"), int),
            repr(pt_details))
        chk("[RSP-014]", "usage 键白名单（官方仅 prompt_tokens/completion_tokens/"
            "total_tokens/prompt_tokens_details.cached_tokens/"
            "completion_tokens_details.reasoning_tokens）",
            set(usage.keys()) == {"prompt_tokens", "completion_tokens",
                                  "total_tokens", "prompt_tokens_details",
                                  "completion_tokens_details"}
            and isinstance(pt_details, dict)
            and set(pt_details.keys()) <= {"cached_tokens"}
            and isinstance(ct_details, dict)
            and set(ct_details.keys()) <= {"reasoning_tokens"},
            f"usage keys={sorted(usage.keys())}, "
            f"pt_details={sorted((pt_details or {}).keys()) if isinstance(pt_details, dict) else pt_details}, "
            f"ct_details={sorted((ct_details or {}).keys()) if isinstance(ct_details, dict) else ct_details}")
        chk("[RSP-015]", "顶层/choices/message 字段白名单（官方顶层 id/request_id/"
            "created/model/object/choices/usage；choice 为 index/message/finish_reason；"
            "message 为 role/content/reasoning_content/tool_calls）",
            set(body.keys()) == {"id", "request_id", "created", "model",
                                 "object", "choices", "usage"}
            and isinstance(choice, dict)
            and set(choice.keys()) == {"index", "message", "finish_reason"}
            and isinstance(msg, dict)
            and set(msg.keys()) <= {"role", "content", "reasoning_content",
                                    "tool_calls"},
            f"top={sorted(body.keys())}, "
            f"choice={sorted(choice.keys()) if isinstance(choice, dict) else choice}, "
            f"message={sorted(msg.keys()) if isinstance(msg, dict) else msg}")
        assert not failures, (
            f"#15 请求 1 响应字段集中校验失败 {len(failures)} 项"
            f"（基础 + 14 组字段）："
            + "；".join(failures)
            + f"；响应: {result['raw'][:400]}"
        )

    # ------------------------------------------------------------------
    # 九、Open Responses 协议组（官方基线未实测，按报告判定依据/规范口径）
    # ------------------------------------------------------------------

    def test_34_resp_basic_response(self, api_client, test_logger):
        """#34 RESP-011 Open Responses 基础响应 basic-response（整改）

        来源: 九章对比报告 20261110 · RESP-011（官方基线 run 20261028_191525 未覆盖该协议，按 Open Responses 规范判定）。
        官方基准: openresponses 合规测试 basic-response——input 为 message 数组，响应符合 ResponseResource schema，output 非空且 status=completed；报告点名缺失必填 8 项：completed_at/presence_penalty/frequency_penalty/top_logprobs/max_tool_calls/background/service_tier/safety_identifier。
        断言口径: 规范口径——HTTP 200 + 8 必填字段 + object=response + status=completed + output 非空；九章实测缺 8 项属缺陷复现（一个根因 7 条，改一处消 6~7 条）。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": "Say hello in exactly 3 words.",
      "role": "user",
      "type": "message"
    }
  ],
  "max_output_tokens": 2048,
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "responses", payload)
        body = _zjxm_assert_resp_resource(result, 34)
        test_logger.info("#34 请求 1 实测: HTTP %s, output %d 项（规范: HTTP 200 + ResponseResource）",
                         result["status"], len(body.get("output") or []))

    def test_35_resp_streaming_response(self, api_client, test_logger):
        """#35 RESP-012 Open Responses 流式事件 streaming-response（整改）

        来源: 九章对比报告 20261110 · RESP-012（官方基线未覆盖，按规范判定）。
        官方基准: 每个 SSE 事件符合规范对应 type 的 StreamingEvent schema（含 sequence_number 等必填字段），事件内 response 对象同样符合 ResponseResource（报告点名 8 必填项），最终 response 符合 ResponseResource 且 status=completed。
        断言口径: 规范口径——SSE 逐事件 type+sequence_number；事件内 response 8 必填字段；response.completed 收束且 status=completed、output 非空；流式正文非空。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": "Count from 1 to 5.",
      "role": "user",
      "type": "message"
    }
  ],
  "max_output_tokens": 2048,
  "model": "glm-5.3",
  "stream": true
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "responses", payload)
        events = result.get("events") or []
        assert result["sse"] and events, (
            f"#35 请求 1 流式响应应返回 SSE data 事件，实测 sse={result['sse']}，"
            f"事件数 {len(events)}；响应: {result['raw'][:300]}"
        )
        bad_shape = []
        for idx, ev in enumerate(events, 1):
            if not ev.get("type"):
                bad_shape.append(f"事件{idx}缺type")
            if "sequence_number" not in ev:
                bad_shape.append(f"事件{idx}缺sequence_number")
        assert not bad_shape, (
            f"#35 请求 1 流式事件 StreamingEvent 必填字段缺失 "
            f"{len(bad_shape)} 处（type/sequence_number）："
            + "；".join(bad_shape[:8])
            + f"；SSE 原文: {result['raw'][:300]}"
        )
        missing_res = []
        for idx, ev in enumerate(events, 1):
            r = ev.get("response")
            if isinstance(r, dict):
                m = _zjxm_resp_missing(r)
                if m:
                    missing_res.append(
                        f"事件{idx}({ev.get('type')}) 缺 {','.join(m)}")
        assert not missing_res, (
            f"#35 请求 1 流式事件内 response 对象缺少规范必填字段"
            f"（报告点名 8 项）{len(missing_res)} 处："
            + "；".join(missing_res[:6])
            + f"；SSE 原文: {result['raw'][:300]}"
        )
        comp = [ev for ev in events if ev.get("type") == "response.completed"]
        assert comp, (
            f"#35 请求 1 流式应以 response.completed 事件收束，实测事件类型: "
            + ",".join(str(ev.get("type")) for ev in events[:10])
            + f"；SSE 原文: {result['raw'][:300]}"
        )
        final = comp[-1].get("response") or {}
        assert final.get("status") == "completed", (
            f"#35 请求 1 最终 response.status 应为 completed，"
            f"实测 {final.get('status')!r}；SSE 原文: {result['raw'][:300]}"
        )
        assert isinstance(final.get("output"), list) and final["output"], (
            f"#35 请求 1 最终 response.output 应为非空数组；"
            f"SSE 原文: {result['raw'][:300]}"
        )
        assert (result["content"] or "").strip(), (
            f"#35 请求 1 流式应输出正文文本，实测为空；"
            f"SSE 原文: {result['raw'][:300]}"
        )
        test_logger.info("#35 请求 1 实测: HTTP %s, SSE %d 事件, content=%r",
                         result["status"], len(events), result["content"][:60])

    def test_36_resp_system_prompt(self, api_client, test_logger):
        """#36 RESP-013 Open Responses system 消息 system-prompt（整改）

        来源: 九章对比报告 20261110 · RESP-013（官方基线未覆盖，按规范判定）。
        官方基准: input 里带 role=system 的 message，响应符合 ResponseResource schema 且 status=completed。
        断言口径: 规范口径——HTTP 200 + 8 必填字段 + object/status/output + output 含非空 message 文本（system 指令生效）。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": "You are a pirate. Always respond in pirate speak.",
      "role": "system",
      "type": "message"
    },
    {
      "content": "Say hello.",
      "role": "user",
      "type": "message"
    }
  ],
  "max_output_tokens": 2048,
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "responses", payload)
        body = _zjxm_assert_resp_resource(result, 36)
        text = _zjxm_resp_output_text(body)
        assert text.strip(), (
            f"#36 请求 1 output 应包含非空 message 文本（system 指令场景），"
            f"实测为空；响应: {result['raw'][:300]}"
        )
        test_logger.info("#36 请求 1 实测: HTTP %s, text=%r",
                         result["status"], text[:60])

    def test_37_resp_tool_calling(self, api_client, test_logger):
        """#37 RESP-014 Open Responses 工具调用 tool-calling（整改）

        来源: 九章对比报告 20261110 · RESP-014（官方基线未覆盖，按规范判定）。
        官方基准: 定义 function 工具，响应符合 schema，output 中出现 type=function_call 的条目。
        断言口径: 规范口径——HTTP 200 + 8 必填字段 + object/status/output + output 含 type=function_call 条目（name/call_id/arguments 齐备）。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": "What's the weather like in San Francisco?",
      "role": "user",
      "type": "message"
    }
  ],
  "max_output_tokens": 2048,
  "model": "glm-5.3",
  "tools": [
    {
      "description": "Get the current weather for a location",
      "name": "get_weather",
      "parameters": {
        "properties": {
          "location": {
            "description": "The city and state, e.g. San Francisco, CA",
            "type": "string"
          }
        },
        "required": [
          "location"
        ],
        "type": "object"
      },
      "type": "function"
    }
  ]
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "responses", payload)
        body = _zjxm_assert_resp_resource(result, 37)
        fc = [it for it in body["output"]
              if isinstance(it, dict) and it.get("type") == "function_call"]
        assert fc, (
            f"#37 请求 1 output 中应出现 type=function_call 的条目，"
            f"实测 output types: "
            + ",".join(str(it.get("type")) for it in body["output"] if isinstance(it, dict))
            + f"；响应: {result['raw'][:300]}"
        )
        item = fc[0]
        assert item.get("name") and item.get("call_id") and item.get("arguments"), (
            f"#37 请求 1 function_call 条目应含 name/call_id/arguments，"
            f"实测 {item!r}；响应: {result['raw'][:300]}"
        )
        test_logger.info("#37 请求 1 实测: HTTP %s, function_call name=%r",
                         result["status"], item.get("name"))

    def test_38_resp_multi_turn(self, api_client, test_logger):
        """#38 RESP-016 Open Responses 多轮历史 multi-turn（整改）

        来源: 九章对比报告 20261110 · RESP-016（官方基线未覆盖，按规范判定）。
        官方基准: input 里带 assistant 历史消息，响应符合 schema 且 status=completed，并能用到历史信息。
        断言口径: 规范口径——HTTP 200 + 8 必填字段 + object/status/output + 正文用到历史信息（"My name is Alice." -> 问名字应答出 Alice）。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": "My name is Alice.",
      "role": "user",
      "type": "message"
    },
    {
      "content": "Hello Alice! Nice to meet you. How can I help you today?",
      "role": "assistant",
      "type": "message"
    },
    {
      "content": "What is my name?",
      "role": "user",
      "type": "message"
    }
  ],
  "max_output_tokens": 2048,
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "responses", payload)
        body = _zjxm_assert_resp_resource(result, 38)
        text = _zjxm_resp_output_text(body)
        assert "alice" in text.lower(), (
            f"#38 请求 1 多轮历史应被用到（问名字应答出 Alice），"
            f"实测正文: {text[:200]}；响应: {result['raw'][:300]}"
        )
        test_logger.info("#38 请求 1 实测: HTTP %s, text=%r",
                         result["status"], text[:60])

    def test_39_resp_assistant_phase(self, api_client, test_logger):
        """#39 RESP-017 Open Responses assistant phase 历史 assistant-phase（建议整改）

        来源: 九章对比报告 20261110 · RESP-017（官方基线未覆盖，按规范判定）。
        官方基准: input 里的 assistant 消息带 phase=commentary / final_answer，网关应接受该字段，响应符合 schema 且 status=completed。
        断言口径: 规范口径——HTTP 200 + 8 必填字段 + object/status/output（phase 字段被接受不报错、正常完成）。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": "I should answer with the saved number.",
      "phase": "commentary",
      "role": "assistant",
      "type": "message"
    },
    {
      "content": "The number is four.",
      "phase": "final_answer",
      "role": "assistant",
      "type": "message"
    },
    {
      "content": "Repeat only the number.",
      "role": "user",
      "type": "message"
    }
  ],
  "max_output_tokens": 2048,
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "responses", payload)
        body = _zjxm_assert_resp_resource(result, 39)
        test_logger.info("#39 请求 1 实测: HTTP %s, output %d 项（phase 字段接受）",
                         result["status"], len(body.get("output") or []))

    def test_40_resp_image_input(self, api_client, test_logger):
        """#40 RESP-015 Open Responses 图片输入 image-input，4xx 判通过（待确认）

        来源: 九章对比报告 20261110 · RESP-015（官方基线未覆盖；报告建议改用例而非改供应商——glm-5.3 文本模型拒绝图片输入是预期行为）。
        官方基准: glm-5.3 为文本模型，不支持图片输入（与 VIS-001 官方 400 行为一致）；openresponses 原断言「应 200」对本模型不成立。
        断言口径: 用户确认——4xx 且错误体含明确错误信息即通过（error 外层 + message 非空）；若放行 200 属超出模型能力的异常放行，判失败。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": [
        {
          "text": "What do you see in this image? Answer in one sentence.",
          "type": "input_text"
        },
        {
          "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAABmklEQVR42tyWAaTyUBzFew/eG4AHz+MBSAHKBiJRGFKwIgQQJKLUIioBIhCAiCAAEizAQIAECaASqFFJq84nudjnaqvuPnxzgP9xfrq5938csPn7PwHTKSoViCIEAYEAMhmoKsU2mUCWEQqB5xEMIp/HaGQG2G6RSuH9HQ7H34rFrtPbdz4jl6PbwmEsl3QA1mt4vcRKk8dz9eg6IpF7tt9fzGY0gCgafFRFo5Blc5vLhf3eCOj1yNhM5GRMVK0aATxPZoz09YXjkQDmczJgquGQAPp9WwCNBgG027YACgUC6HRsAZRKBDAY2AJoNv/ZnwzA6WScznG3p4UAymXGAEkyXrTFAh8fLAGqagQAyGaZpYsi7bHTNPz8MEj//LxuFPo+UBS8vb0KaLXubrRa7aX0RMLCykwmn0z3+XA4WACcTpCkh9MFAZpmuVXo+mO/w+/HZvNgbblcUCxaSo/Hyck80Yu6XXDcvfVZr79cvMZjuN2U9O9vKAqjZrfbIZ0mV4TUi9Xqz6jddNy//7+e3n8Fhf/Llo2kxi8AQyGRoDkmAhAAAAAASUVORK5CYII=",
          "type": "input_image"
        }
      ],
      "role": "user",
      "type": "message"
    }
  ],
  "max_output_tokens": 2048,
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "responses", payload)
        st = result["status"]
        assert 400 <= st < 500, (
            f"#40 请求 1 glm-5.3 文本模型 image-input 应返回 4xx 明确错误"
            f"（报告口径：不支持视觉的模型应返回明确 4xx），实测 HTTP {st}；"
            f"响应: {result['raw'][:300]}"
        )
        body = result["json"] if isinstance(result["json"], dict) else {}
        err = body.get("error")
        assert isinstance(err, dict) and (
            (err.get("message") or "").strip() or (err.get("code") or "")
        ), (
            f"#40 请求 1 4xx 错误体应含 error 外层与明确错误信息"
            f"（报告要求：错误体按 error 外层结构补齐），实测: {result['raw'][:300]}"
        )
        test_logger.info("#40 请求 1 实测: HTTP %s, error=%s（4xx 明确拒绝判通过）",
                         st, err)

    def test_41_resp_compact_response(self, api_client, test_logger):
        """#41 RESP-018 Open Responses 上下文压缩 compact-response（建议整改）

        来源: 九章对比报告 20261110 · RESP-018（官方基线未覆盖，按规范判定；报告原文 assistant content 疑似生成截断为畸形键，按用户确认修正为完整句子）。
        官方基准: POST /responses/compact，响应符合 CompactResource schema，object=response.compaction，output 中有 type=compaction 的条目。
        断言口径: 规范口径——HTTP 200 + object=response.compaction + output 含 type=compaction 条目；九章实测 404 Invalid URL（端点未实现）属缺陷复现（报告：404 文案会被当成路径拼错，至少应改为明确的「该端点暂未支持」）。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": "We agreed to launch on Tuesday and notify support first.",
      "role": "user",
      "type": "message"
    },
    {
      "content": "Understood. The launch is Tuesday with support notified beforehand.",
      "role": "assistant",
      "type": "message"
    }
  ],
  "model": "glm-5.3",
  "prompt_cache_key": "openresponses-compact-test"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "compact", payload)
        assert result["status"] == 200, (
            f"#41 请求 1 规范基准 HTTP 200（/responses/compact 端点应实现），"
            f"实测 HTTP {result['status']}；响应: {result['raw'][:300]}"
        )
        body = result["json"]
        assert isinstance(body, dict) and body.get("object") == "response.compaction", (
            f"#41 请求 1 object 应为 response.compaction，"
            f"实测 {body.get('object') if isinstance(body, dict) else body!r}；"
            f"响应: {result['raw'][:300]}"
        )
        out = body.get("output")
        assert isinstance(out, list) and any(
            isinstance(it, dict) and it.get("type") == "compaction" for it in out
        ), (
            f"#41 请求 1 output 中应有 type=compaction 的条目，实测 {out!r}；"
            f"响应: {result['raw'][:300]}"
        )
        test_logger.info("#41 请求 1 实测: HTTP %s, object=%s",
                         result["status"], body.get("object"))

    def test_42_resp_compact_missing_model(self, api_client, test_logger):
        """#42 RESP-019 Open Responses 压缩缺 model 被拒绝 compact-missing-model（建议整改）

        来源: 九章对比报告 20261110 · RESP-019（官方基线未覆盖，按规范判定）。
        官方基准: /responses/compact 请求体不带必填的 model，应返回 400 或 422。
        断言口径: 规范口径——HTTP 400/422（model 缺失须拒绝，不得 404/500）；请求报文按报告原文不带 model，不注入。
        """
        payload = json.loads(
            r"""
{
  "input": [
    {
      "content": "Compact this conversation.",
      "role": "user",
      "type": "message"
    }
  ]
}
"""
        )
        result = _zjxm_send(api_client, "compact", payload)
        st = result["status"]
        assert st in (400, 422), (
            f"#42 请求 1 缺失必填 model 应返回 400/422，实测 HTTP {st}；"
            f"响应: {result['raw'][:300]}"
        )
        test_logger.info("#42 请求 1 实测: HTTP %s（规范: 400/422）", st)

    # ------------------------------------------------------------------
    # 七、官方基线异常守护（九章新 url 复测报告 20261116 补入，
    #     断言基准取九章复测行为，官方 500/400 不作断言基准）
    # ------------------------------------------------------------------

    def test_43_chat_messages_null_element(self, api_client, test_logger):
        """#43 KS-MSG-001 messages 数组含 null 元素，应 400 拒绝（官方异常）

        来源: 九章对比报告 20261110 · KS-MSG-001（官方基线 500 内部错误，
        报告移除）；九章新 url 功能测试报告 20261116 复测补入。
        官方基准: HTTP 500「内部错误」——官方基线自身异常，不作断言基准。
        断言口径: 九章复测基线——HTTP 400 + error 外层 + error.code=1214
        「非法的 role: ...」；messages 数组含 null 元素应明确拒绝且错误体
        规范，不得 500 崩溃。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 64,
  "messages": [
    {
      "content": "你好",
      "role": "user"
    },
    null
  ],
  "model": "glm-5.3"
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        assert result["status"] == 400, (
            f"#43 请求 1 九章复测基线 HTTP 400（官方基线 500 异常），"
            f"实测 HTTP {result['status']}；响应: {result['raw'][:300]}"
        )
        body = result["json"] if isinstance(result["json"], dict) else {}
        err = body.get("error")
        assert isinstance(err, dict) and err, (
            f"#43 请求 1 九章复测错误体为 error 外层结构（error.code=1214），"
            f"实测缺少 error 外层或为空；响应: {result['raw'][:300]}"
        )
        got = err.get("code")
        assert str(got) == "1214", (
            f"#43 请求 1 九章复测 error.code=1214，实测 error.code={got!r}；"
            f"错误体: {result['raw'][:300]}"
        )
        test_logger.info("#43 请求 1 实测: HTTP %s, error=%s（九章复测: "
                         "HTTP 400 code 1214；官方: 500 异常）",
                         result["status"], err)

    def test_44_chat_n_zero_stream(self, api_client, test_logger):
        """#44 KS-N-001 n=0 流式请求放行，200 正常返回（官方异常）

        来源: 九章对比报告 20261110 · KS-N-001（双方一致放行 200，报告
        判跳过并移除）；九章新 url 功能测试报告 20261116 复测补入。
        官方基准: HTTP 200 流式正常返回——双方一致放行，n=0 按双方
        实际口径不构成拒绝条件（报告判定依据与官方基线同为 200）。
        断言口径: 九章复测基线——HTTP 200 + SSE [DONE] 收束 + 正文
        非空 + 思考非空（正文/思考无明确验证要求，按用户确认只断
        非空）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 500,
  "messages": [
    {
      "content": "请用一句话介绍人工智能。",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "n": 0,
  "stream": true,
  "stream_options": {
    "include_usage": true
  },
  "temperature": 1.0,
  "thinking": {
    "type": "enabled"
  }
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        assert result["status"] == 200, (
            f"#44 请求 1 九章复测基线 HTTP 200（流式放行），"
            f"实测 HTTP {result['status']}；响应: {result['raw'][:300]}"
        )
        assert result.get("sse") and result.get("done"), (
            f"#44 请求 1 九章复测流式响应应以 data: [DONE] 收束，"
            f"实测未收束；响应: {result['raw'][:300]}"
        )
        assert isinstance(result.get("content"), str) and result["content"].strip(), (
            f"#44 请求 1 九章复测返回 200 且正文非空，实测正文为空；"
            f"响应: {result['raw'][:300]}"
        )
        assert isinstance(result.get("reasoning"), str) and result["reasoning"].strip(), (
            f"#44 请求 1 九章复测返回 200 且思考非空，实测思考为空；"
            f"响应: {result['raw'][:300]}"
        )
        test_logger.info("#44 请求 1 实测: HTTP %s（流式 [DONE] 收束，正文 %d 字，"
                         "思考 %d 字；九章复测: 200 放行）",
                         result["status"], len(result["content"]),
                         len(result["reasoning"]))

    def test_45_chat_tool_schema_unicode_pattern(self, api_client, test_logger):
        """#45 KS-TOOL-009 工具参数 schema 含 Unicode 正则 pattern 不报错（官方异常）

        来源: 九章对比报告 20261110 · KS-TOOL-009（官方基线 400 过度拒绝，
        报告移除）；九章新 url 功能测试报告 20261116 复测补入。
        官方基准: HTTP 400 error.code=1210「API 调用参数有误」——官方基线
        对含 \\p{L} 的 schema 过度校验拒绝，不作断言基准。
        断言口径: 九章复测基线——HTTP 200 + 正文非空 + 思考非空
        （工具 schema 含 Unicode 正则 pattern 应通过校验正常响应；
        tool_calls 调用与否属模型决策不硬断，九章实测调用了
        skillhub_install {"action":"check_env"}）。
        """
        payload = json.loads(
            r"""
{
  "max_tokens": 800,
  "messages": [
    {
      "content": "帮我安装一个名为 data-viz 的 skill",
      "role": "user"
    }
  ],
  "model": "glm-5.3",
  "tool_choice": "auto",
  "tools": [
    {
      "function": {
        "description": "安装 SkillHub CLI 和 Skills",
        "name": "skillhub_install",
        "parameters": {
          "properties": {
            "action": {
              "enum": [
                "check_env",
                "install_cli",
                "install_skill"
              ],
              "type": "string"
            },
            "skillName": {
              "pattern": "^[\\w\\-\\.\\p{L}]{1,128}$",
              "type": "string"
            }
          },
          "required": [
            "action"
          ],
          "type": "object"
        }
      },
      "type": "function"
    }
  ]
}
"""
        )
        payload["model"] = api_client.model_name
        result = _zjxm_send(api_client, "chat", payload)
        assert result["status"] == 200, (
            f"#45 请求 1 九章复测基线 HTTP 200（官方基线 400 过度拒绝），"
            f"实测 HTTP {result['status']}；响应: {result['raw'][:300]}"
        )
        assert isinstance(result.get("content"), str) and result["content"].strip(), (
            f"#45 请求 1 九章复测返回 200 且正文非空，实测正文为空；"
            f"响应: {result['raw'][:300]}"
        )
        assert isinstance(result.get("reasoning"), str) and result["reasoning"].strip(), (
            f"#45 请求 1 九章复测返回 200 且思考非空，实测思考为空；"
            f"响应: {result['raw'][:300]}"
        )
        test_logger.info("#45 请求 1 实测: HTTP %s（正文 %d 字，思考 %d 字；"
                         "九章复测: 200 放行并调用工具；官方: 400 过度拒绝）",
                         result["status"], len(result["content"]),
                         len(result["reasoning"]))
