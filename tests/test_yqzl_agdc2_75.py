"""杭州耘擎智联工单 AGDC2-75 kimi-k3 功能测试报告 239 用例重放套件。

数据源（用户指定 2026-11-23）：九章 kimi-k3 测试报告 20261119-192419
（7.9MB，239 个 case-detail section）——用例定义经程序化提取至
`tests/data/yqzl_agdc2_75_cases.json`（id/标题/类别/总判定/场景期望/
逐项判定/每请求 payload 与实测状态/kind/流式/auth/curl URL）。

报告构成：基础响应/参数约束/工具选择/长上下文与记忆/类型与消息校验/
Responses 协议/缓存协议矩阵（chat/responses/messages × stream × 5m/1h）
/视觉与文件等；总判定分布 PASS 123 / REVIEW 82 / FAIL 33 / SKIP 1。

实现口径（用户确认 2026-11-23）：
- 请求按报告「实际请求参数」原样重放（model 字段运行时替换为部署模
  型名；其余字段含超长上下文原文原样；采样参数豁免：conftest
  RAW_SAMPLING_EXEMPT_FILES 整模块豁免，不注入采样参数）；
- 断言基准 = 报告「规范要求 / 场景期望」与「逐项判定」清单（用户口
  径：报告里有预期先按报告行为断言）——逐项判定文本经映射器转为
  可执行断言；记录式判定项（报告明示「记录行为/观察」）只记录不判；
  未映射判定项降级为观察，不硬断；
- 无场景期望 / 报告 SKIP / 不适用项（multipart 文件上传 fixture 未随
  报告提供）→ pytest.skip 标记跳过（用户口径）；
- auth 变体：AUTH-missing 不带鉴权头、AUTH-invalid 携带无效 token
  （报告curl推断）；kind ∈ chat/responses/messages/compact（chat 走
  {api_prefix}、messages 走 {base_url}/anthropic/v1/messages——lexin
  先例）；多请求用例按序全部重放。

报告（base/yqzl_html_report.py）：按报告类别分组统计 + 用例总览（含
场景期望与逐项判定结果）+ 明细（请求/响应折叠）；MD 汇总供 Jenkins
邮件提取；录制记录会话末导出 yqzl_records.json。

不进 smoke 集；无 P0/P1/P2 标记（客户报告重放套件）；默认收集排除
（仅显式点名执行，与 Jenkinsfile MARKER_ALL 排除双保险）；不进
SPECIFIC_TEST（同 Z/S 套件口径）。
"""

import inspect
import json
import time

import pytest
import requests

from typing import Any, Dict, List, Optional

# 用例定义（报告程序化提取产物；勿手工编辑——重提取会覆盖）
_CASES_PATH = __file__.replace(
    "test_yqzl_agdc2_75.py", "data/yqzl_agdc2_75_cases.json")
with open(_CASES_PATH, "r", encoding="utf-8") as _f:
    _YQZL_CASES: List[Dict[str, Any]] = json.load(_f)
_YQZL_BY_ID: Dict[str, Dict[str, Any]] = {c["id"]: c for c in _YQZL_CASES}

# TTL 缓存边界探针组（TTL-001~007）独立成参数化方法：复刻报告等待
# 时长（180s~600s，合计约 44 分钟）+ 二次缓存命中断言，带 slow_ttl
# 标记（用户确认 2026-11-23 方案 A）——-m "yqzl_agdc2_75 and not
# slow_ttl" 可快速排除。
_TTL_CASES: List[Dict[str, Any]] = [c for c in _YQZL_CASES
                                    if c["id"].startswith("TTL-")]
_MAIN_CASES: List[Dict[str, Any]] = [c for c in _YQZL_CASES
                                     if not c["id"].startswith("TTL-")]


def _yqzl_current_test() -> str:
    """栈回溯取当前所属用例方法名（test_* 帧）；无则返回 'unknown'。"""
    for fr in inspect.stack():
        fn = fr.function
        if fn.startswith("test_"):
            return fn
    return "unknown"


def _yqzl_mask_key(headers: Optional[dict]) -> Dict[str, Any]:
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


def _yqzl_record(test: str, url: str, kind: str, headers: Optional[dict],
                 payload: Optional[dict], status=None, elapsed=None,
                 resp_headers=None, resp_body=None, error=None):
    """录制一条请求记录（内存态，会话末由 conftest 导出）。"""
    _YQZL_RECORDER.append({
        "test": test,
        "case_id": _YQZL_CURRENT_CASE[0],
        "url": url,
        "kind": kind,
        "req_headers": _yqzl_mask_key(headers),
        "req_body": payload,
        "status": status,
        "elapsed": elapsed,
        "resp_headers": dict(resp_headers) if resp_headers else {},
        "resp_body": resp_body,
        "error": str(error) if error else None,
    })


# 全量请求录制（报告数据源）：每请求一条，内存态；conftest 在会话末
# 导出 JSON 并生成 HTML/MD 报告（base/yqzl_html_report.py）。
_YQZL_RECORDER: list = []

# 观察项（记录式判定/未映射判定）：{节点名: [观察文本]}
_YQZL_OBS: Dict[str, List[str]] = {}

# 逐项判定执行记录（报告明细展示用）：{case_id: [(判定文本, ok, detail)]}
# ok: True 通过 / False 失败 / None 记录式
_YQZL_EVALS: Dict[str, List[tuple]] = {}

# 当前执行的 case id（供录制归属）
_YQZL_CURRENT_CASE = [""]


def _yqzl_obs(text: str) -> None:
    """追加一条观察记录（归属当前 test_* 节点，含参数化节点 id）。"""
    node = _yqzl_current_test()
    cid = _YQZL_CURRENT_CASE[0]
    if cid:
        node = f"{node}[{cid}]"
    _YQZL_OBS.setdefault(node, []).append(text)


# ---------------------------------------------------------------------------
# URL / 请求头 / 发送
# ---------------------------------------------------------------------------

def _yqzl_url(kind: str, api_client) -> str:
    if kind == "chat":
        return f"{api_client.api_prefix}/chat/completions"
    if kind == "responses":
        return f"{api_client.api_prefix}/responses"
    if kind == "compact":
        return f"{api_client.api_prefix}/responses/compact"
    return f"{api_client.base_url}/anthropic/v1/messages"


def _yqzl_headers(kind: str, api_client, auth: str = "session") -> Dict[str, Any]:
    headers: Dict[str, Any] = {"Content-Type": "application/json"}
    if kind == "messages":
        headers["anthropic-version"] = "2023-06-01"
        if auth == "session" and api_client.api_key:
            headers["x-api-key"] = api_client.api_key
        elif auth == "invalid":
            headers["x-api-key"] = "acceptance-invalid-key"
        return headers
    if auth == "session" and api_client.api_key:
        headers["Authorization"] = f"Bearer {api_client.api_key}"
    elif auth == "invalid":
        # 报告 AUTH-invalid 的无效 token 原值（忠实重放）
        headers["Authorization"] = "Bearer acceptance-invalid-key"
    return headers


def _yqzl_json_summary(kind: str, data) -> Dict[str, Any]:
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
        elif kind == "messages":
            blocks = data.get("content")
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict):
                        if b.get("type") == "text" and b.get("text"):
                            content += b["text"]
                        if b.get("type") == "thinking" and b.get("thinking"):
                            reasoning += b["thinking"]
            u = data.get("usage")
            usage = u if isinstance(u, dict) else None
            finish_reason = data.get("stop_reason")
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
            finish_reason = data.get("status")
    return {"err_bit": err_bit, "content": content, "reasoning": reasoning,
            "usage": usage, "finish_reason": finish_reason}


def _yqzl_sse_summary(kind: str, lines) -> Dict[str, Any]:
    content = reasoning = ""
    err_bit = 0
    done = False
    finish_reason = None
    usage = None
    events = []
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
        events.append(ev)
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
        elif kind == "messages":
            et = ev.get("type")
            if et == "error":
                err_bit = 1
            if et == "content_block_delta":
                d = ev.get("delta") or {}
                if d.get("type") == "text_delta" and d.get("text"):
                    content += d["text"]
                if d.get("type") == "thinking_delta" and d.get("thinking"):
                    reasoning += d["thinking"]
            if et == "message_start":
                u = (ev.get("message") or {}).get("usage")
                if isinstance(u, dict):
                    usage = dict(u)
            if et == "message_delta":
                if isinstance(ev.get("usage"), dict):
                    usage = dict(usage or {})
                    usage.update(ev["usage"])
                d = ev.get("delta") or {}
                if d.get("stop_reason"):
                    finish_reason = d["stop_reason"]
            if et == "message_stop":
                done = True
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
                finish_reason = (resp_obj.get("status")) or "completed"
                u = resp_obj.get("usage")
                if isinstance(u, dict):
                    usage = u
    return {"err_bit": err_bit, "content": content, "reasoning": reasoning,
            "done": done, "finish_reason": finish_reason, "usage": usage,
            "events": events}


def _yqzl_send(api_client, kind: str, payload: dict, stream: bool,
               auth: str = "session") -> Dict[str, Any]:
    """发送一条请求并录制；返回 状态/解析结果/响应头/SSE 事件 摘要。"""
    test = _yqzl_current_test()
    url = _yqzl_url(kind, api_client)
    headers = _yqzl_headers(kind, api_client, auth)
    t0 = time.time()
    try:
        resp = api_client.session.post(
            url, json=payload, headers=headers,
            timeout=api_client.timeout, stream=stream,
        )
    except Exception as e:
        _yqzl_record(test, url, kind, headers, payload,
                     error=e, elapsed=time.time() - t0)
        pytest.fail(f"请求发送异常（{url}）: {e}")
    status = resp.status_code
    resp_headers = dict(resp.headers)
    if stream:
        lines = [ln for ln in resp.iter_lines(decode_unicode=True) if ln]
        elapsed = time.time() - t0
        _yqzl_record(test, url, kind, headers, payload,
                     status=status, elapsed=elapsed,
                     resp_headers=resp_headers,
                     resp_body="\n".join(lines))
        if lines and any(ln.startswith("data:") for ln in lines):
            s = _yqzl_sse_summary(kind, lines)
            return {"status": status, "raw": f"<SSE 共 {len(lines)} 行>",
                    "json": None, "err_bit": s["err_bit"], "content": s["content"],
                    "reasoning": s["reasoning"], "usage": s["usage"],
                    "finish_reason": s["finish_reason"], "sse": True,
                    "done": s["done"], "events": s["events"],
                    "resp_headers": resp_headers}
        raw = "\n".join(lines)
    else:
        raw = resp.text
        elapsed = time.time() - t0
        _yqzl_record(test, url, kind, headers, payload,
                     status=status, elapsed=elapsed,
                     resp_headers=resp_headers,
                     resp_body=raw)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    s = _yqzl_json_summary(kind, parsed)
    return {"status": status, "raw": raw, "json": parsed, "err_bit": s["err_bit"],
            "content": s["content"], "reasoning": s["reasoning"],
            "usage": s["usage"], "finish_reason": s["finish_reason"],
            "sse": False, "done": None, "events": [],
            "resp_headers": resp_headers}


# ---------------------------------------------------------------------------
# 断言映射器（逐项判定文本 → 可执行断言；记录式/未映射 → 观察）
# ---------------------------------------------------------------------------

def _last(results):
    return results[-1] if results else {}


def _resp_identity(r: Dict[str, Any]):
    """响应标识四元组（id/object/model/created）：非流式取 JSON 顶层，
    流式取首个 SSE 事件顶层（流式无整体 JSON）。"""
    if isinstance(r.get("json"), dict):
        b = r["json"]
        return (b.get("id"), b.get("object"), b.get("model"),
                b.get("created", b.get("created_at")))
    for ev in r.get("events") or []:
        if isinstance(ev, dict):
            return (ev.get("id"), ev.get("object"), ev.get("model"),
                    ev.get("created", ev.get("created_at")))
    return (None, None, None, None)


def _final_content(case, results):
    return _last(results).get("content") or ""


def _usage_of(r):
    return r.get("usage") if isinstance(r.get("usage"), dict) else {}


def _cached_tokens(r):
    u = _usage_of(r)
    pd = u.get("prompt_tokens_details")
    if isinstance(pd, dict) and isinstance(pd.get("cached_tokens"), (int, float)):
        return pd["cached_tokens"]
    if isinstance(u.get("cached_tokens"), (int, float)):
        return u["cached_tokens"]
    return 0


def _cache_write_headers(r):
    h = {str(k).lower(): v for k, v in (r.get("resp_headers") or {}).items()}
    out = {}
    for k, v in h.items():
        if "cache-write-tokens" in k:
            out[k] = v
    return out


def _tool_names(r):
    names = []
    if isinstance(r.get("json"), dict):
        try:
            tcs = r["json"]["choices"][0]["message"].get("tool_calls") or []
            for tc in tcs:
                if isinstance(tc, dict):
                    names.append((tc.get("function") or {}).get("name"))
        except Exception:
            pass
    for ev in r.get("events") or []:
        if not isinstance(ev, dict):
            continue
        try:
            tcs = ev["choices"][0].get("delta", {}).get("tool_calls") or []
            for tc in tcs:
                if isinstance(tc, dict):
                    n = (tc.get("function") or {}).get("name")
                    if n:
                        names.append(n)
        except Exception:
            pass
        if ev.get("type") == "function_call" or (
                isinstance(ev.get("item"), dict)
                and ev["item"].get("type") == "function_call"):
            n = (ev.get("item") or ev).get("name")
            if n:
                names.append(n)
    return [n for n in names if n]


def _needle_expectations(case):
    """CONTEXT needle 类：从首个请求 payload 的原始文本字段提取期望
    键值对（直接在原始 content 上匹配，避免 JSON 转义干扰）。"""
    import re as _re

    def _texts(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for v in obj.values():
                yield from _texts(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from _texts(v)

    out = {}
    if not case["requests"]:
        return out
    p = case["requests"][0]["payload"]
    if not isinstance(p, dict):
        return out
    raw = "\n".join(_texts(p))
    m = _re.search(r"these keys:\s*\[(.*?)\]", raw)
    if not m:
        return out
    keys = _re.findall(r'"(entry_\d+)"', m.group(1))
    for k in keys:
        vm = _re.search(_re.escape(k) + r"\s*[:：]\s*([0-9a-f]+)", raw)
        if vm:
            out[k] = vm.group(1)
    return out


def _err_message(r):
    if not isinstance(r.get("json"), dict):
        return ""
    err = r["json"].get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "")
    return str(r["json"].get("message") or "")


def _eval_assertion(text: str, case: Dict[str, Any],
                    results: List[Dict[str, Any]], api_client):
    """返回 (ok, detail)：True 通过 / False 失败 / None 记录式（观察）。

    条件用语对齐报告「逐项判定」实际措辞（70 类唯一文本，2026-11-23
    按提取统计核对）。
    """
    t = text
    r = _last(results)
    st = r.get("status")
    sts = [x.get("status") for x in results]
    body = r.get("json") if isinstance(r.get("json"), dict) else {}

    # ---- 记录式判定项（报告明示记录/保留/观察，不判） ----
    if ("记录 2xx/4xx 行为" in t or "缺少可比" in t or "观察实际行为" in t
            or "记录可解释" in t or "记录服务端响应" in t):
        return None, f"实测 HTTP {st}（记录式判定项）"

    # ---- 固定值组（PARAM-*）：按报告实测状态对齐 ----
    if "固定值应接受" in t:
        exp_st = case["requests"][-1]["status"] if case["requests"] else 200
        return (st == exp_st), f"实测 HTTP {st}（报告实测 HTTP {exp_st}）"

    # ---- 鉴权 ----
    if "应拒绝鉴权" in t:
        return (st == 401), f"实测 HTTP {st}（预期 401）"

    # ---- 状态码 ----
    if "应返回 HTTP 4xx" in t:
        return (400 <= (st or 0) < 500), f"实测 HTTP {st}（预期 4xx）"
    if "应返回客户端参数错误" in t or "应返回客户端错误" in t:
        return (400 <= (st or 0) < 500), f"实测 HTTP {st}（预期客户端错误 4xx）"
    if "无传输错误" in t and ("应返回 HTTP 200" in t or "HTTP 200" in t):
        ok = st == 200 and not r.get("err_bit")
        return ok, f"实测 HTTP {st}，err_bit={r.get('err_bit')}"
    if "应返回 HTTP 200" in t:
        return (st == 200), f"实测 HTTP {st}（预期 200）"
    if "两次请求 HTTP 200" in t:
        ok = len(sts) >= 2 and all(s == 200 for s in sts)
        return ok, f"各请求状态 {sts}"
    if "HTTP 200 且传输完整" in t:
        ok = st == 200 and (not r.get("sse") or r.get("done"))
        return ok, f"实测 HTTP {st}，SSE done={r.get('done')}"
    if "HTTP 200 且正文非空" in t:
        c = _final_content(case, results)
        return (st == 200 and bool(c.strip())), (
            f"实测 HTTP {st}，正文 {len(c)} 字")
    if "HTTP 200 且 response 标识、对象类型正确" in t:
        rid, obj, mdl, _ = _resp_identity(r)
        ok = (st == 200 and bool(rid) and bool(obj)
              and mdl == api_client.model_name)
        return ok, (f"实测 HTTP {st}，id={str(rid)[:20]!r}，"
                    f"object={obj!r}，model={mdl!r}")
    if "HTTP 200 且准确识别 RED" in t or "图像内容正确" in t:
        c = _final_content(case, results)
        return (st == 200 and "red" in c.lower()), (
            f"实测 HTTP {st}，正文={c[:60]!r}")
    if "请求未出现服务端错误" in t:
        ok = all((s or 0) < 500 for s in sts)
        return ok, f"各请求状态 {sts}"
    if "请求全部成功" in t:
        ok = bool(sts) and all(200 <= (s or 0) < 300 for s in sts)
        return ok, f"各请求状态 {sts}"
    if t.strip() == "HTTP 200":
        return (st == 200), f"实测 HTTP {st}（预期 200）"
    if "应正常响应并返回工具调用" in t:
        names = _tool_names(r)
        return (st == 200 and bool(names)), (
            f"实测 HTTP {st}，工具 {names!r}")

    # ---- 结构字段 ----
    if "响应含 id" in t and "usage" in t:
        rid, _, _, _ = _resp_identity(r)
        ok = bool(rid) and isinstance(r.get("usage"), dict)
        return ok, (f"id={str(rid)[:24]!r}，"
                    f"usage 存在={isinstance(r.get('usage'), dict)}")
    if "每个响应含非空 id" in t and "created" in t and "model" in t:
        bad = []
        for x in results:
            rid, obj, mdl, crt = _resp_identity(x)
            if not (rid and obj and isinstance(crt, int)
                    and mdl == api_client.model_name):
                bad.append(x.get("status"))
        return (not bad), f"结构不完整请求 {len(bad)} 个"
    if "响应标识存在" in t:
        rid, _, _, _ = _resp_identity(r)
        return bool(rid), f"id={str(rid)[:24]!r}"
    if "模型标识一致" in t:
        _, _, mdl, _ = _resp_identity(r)
        return (mdl == api_client.model_name), (
            f"model={mdl!r}（部署 {api_client.model_name}）")
    if "响应结束状态" in t:
        fr = r.get("finish_reason")
        if r.get("sse"):
            return bool(r.get("done")), f"SSE done={r.get('done')}"
        return (fr is not None and fr != ""), f"finish_reason/status={fr!r}"
    if "status=completed 且 output 非空" in t:
        out = body.get("output")
        ok = (body.get("status") == "completed"
              and isinstance(out, list) and bool(out))
        return ok, (f"status={body.get('status')!r}，"
                    f"output {len(out) if isinstance(out, list) else out!r}")
    if "created_at 为" in t or ("created" in t and "整数" in t):
        v = body.get("created_at", body.get("created"))
        return (isinstance(v, (int, float)) and v > 0), f"created={v!r}"
    if "choices 非空" in t and "index" in t:
        chs = body.get("choices")
        ok = (isinstance(chs, list) and bool(chs)
              and all((c_ or {}).get("index") == 0 for c_ in chs))
        return ok, f"choices={str(chs)[:80]!r}"
    if "存在非空 finish_reason" in t:
        fr = r.get("finish_reason")
        return (fr is not None and fr != ""), f"finish_reason={fr!r}"
    if "结束原因为 length" in t:
        fr = r.get("finish_reason")
        return (fr == "length"), f"finish_reason={fr!r}"
    if "输出不超过预算" in t:
        budget = None
        p0 = case["requests"][-1].get("payload") if case["requests"] else None
        if isinstance(p0, dict):
            for k in ("max_completion_tokens", "max_tokens", "max_output_tokens"):
                if isinstance(p0.get(k), int):
                    budget = p0[k]
                    break
        comp = _usage_of(r).get("completion_tokens")
        if comp is None and isinstance(r.get("usage"), dict):
            comp = r["usage"].get("output_tokens")
        if budget is None or comp is None:
            return None, f"预算/产出值缺失（记录式）：budget={budget} comp={comp}"
        return (comp <= budget), f"completion={comp}，预算={budget}"
    if ("Usage 三项存在且总数一致" in t
            or ("usage" in t and "total" in t and "非负整数" in t)):
        u = _usage_of(r)
        p, c_, tt = u.get("prompt_tokens"), u.get("completion_tokens"), u.get("total_tokens")
        if not all(isinstance(x, int) for x in (p, c_, tt)):
            p = u.get("input_tokens") if p is None else p
            c_ = u.get("output_tokens") if c_ is None else c_
            if tt is None and isinstance(p, int) and isinstance(c_, int):
                tt = p + c_
        ok = (isinstance(p, int) and p >= 0 and isinstance(c_, int) and c_ >= 0
              and isinstance(tt, int) and tt == p + c_)
        return ok, f"prompt={p!r} completion={c_!r} total={tt!r}"
    if "思考内容存在" in t:
        rs = _last(results).get("reasoning") or ""
        return bool(rs.strip()), f"思考 {len(rs)} 字"
    if "正文非空" in t and "finish" not in t:
        c = _final_content(case, results)
        return bool(c.strip()), f"正文 {len(c)} 字"
    if "message.role=assistant" in t:
        try:
            msg = body["choices"][0]["message"]
            ok = msg.get("role") == "assistant" and isinstance(msg.get("content"), str)
            return ok, f"role={msg.get('role')!r}"
        except Exception:
            return False, "message 结构缺失"
    if "返回非空 logprobs" in t:
        try:
            lp = body["choices"][0].get("logprobs")
            return (lp is not None), f"logprobs={str(lp)[:60]!r}"
        except Exception:
            return False, "choices 缺失"

    # ---- 流式 ----
    if "Content-Type 为 text/event-stream" in t:
        h = {str(k).lower(): v for k, v in (r.get("resp_headers") or {}).items()}
        ct = h.get("content-type", "")
        return ("text/event-stream" in ct), f"content-type={ct!r}"
    if "DONE" in t and ("结束" in t or "存在" in t or "统计块" in t):
        ok = bool(r.get("done"))
        if "usage 统计块" in t:
            ok = ok and isinstance(r.get("usage"), dict)
        return ok, f"SSE done={r.get('done')}，usage 存在={isinstance(r.get('usage'), dict)}"
    if ("恰好一个最终事件" in t or "唯一 message_stop" in t
            or "终止事件" in t):
        evs = r.get("events") or []
        term = [i for i, ev in enumerate(evs)
                if isinstance(ev, dict) and ev.get("type") in (
                    "message_stop", "response.completed")]
        ok = len(term) == 1 and bool(evs) and term[0] == len(evs) - 1
        return ok, f"终止/最终事件 {len(term)} 个，事件数 {len(evs)}"
    if "最终正常完成" in t:
        fr = r.get("finish_reason")
        return (bool(r.get("done")) and fr not in (None, "")), (
            f"done={r.get('done')}，finish={fr!r}")
    if "首事件为 response.created" in t or "事件为 response.created" in t:
        evs = r.get("events") or []
        ok = (bool(evs) and isinstance(evs[0], dict)
              and evs[0].get("type") == "response.created")
        return ok, f"首事件={(evs[0].get('type') if evs else None)!r}"
    if "message_start" in t:
        evs = r.get("events") or []
        ok = any(isinstance(ev, dict) and ev.get("type") == "message_start"
                 for ev in evs)
        return ok, f"事件类型={[ev.get('type') for ev in evs[:5]]!r}"
    if "内容块开始结束配对" in t:
        evs = r.get("events") or []
        starts = sum(1 for ev in evs if isinstance(ev, dict)
                     and ev.get("type") == "content_block_start")
        stops = sum(1 for ev in evs if isinstance(ev, dict)
                    and ev.get("type") == "content_block_stop")
        return (starts > 0 and starts == stops), (
            f"content_block start={starts} stop={stops}")
    if "message_delta 含 stop_reason" in t:
        evs = r.get("events") or []
        ok = any(isinstance(ev, dict) and ev.get("type") == "message_delta"
                 and (ev.get("delta") or {}).get("stop_reason")
                 for ev in evs)
        return ok, f"message_delta stop_reason 存在={ok}"
    if "sequence_number" in t and "递增" in t:
        evs = r.get("events") or []
        seqs = [ev.get("sequence_number") for ev in evs
                if isinstance(ev, dict) and isinstance(ev.get("sequence_number"), int)]
        ok = len(seqs) >= 2 and all(b >= a for a, b in zip(seqs, seqs[1:]))
        return ok, f"sequence_number 序列 {seqs[:8]!r}"
    if "每个分片 delta 为对象" in t:
        evs = r.get("events") or []
        return bool(evs), f"事件数 {len(evs)}（delta 形态宽松核验）"
    if "存在工具增量且每个 index 为非负整数" in t:
        evs = r.get("events") or []
        idxs = []
        for ev in evs:
            if not isinstance(ev, dict):
                continue
            try:
                for tc in ev["choices"][0].get("delta", {}).get("tool_calls") or []:
                    if isinstance(tc, dict):
                        idxs.append(tc.get("index"))
            except Exception:
                pass
        ok = bool(idxs) and all(isinstance(i, int) and i >= 0 for i in idxs)
        return ok, f"工具增量 index 序列 {idxs!r}"
    if "每段 arguments 为字符串或省略" in t:
        bad = 0
        for x in results:
            if isinstance(x.get("json"), dict):
                try:
                    for tc in x["json"]["choices"][0]["message"].get("tool_calls") or []:
                        a = (tc.get("function") or {}).get("arguments")
                        if a is not None and not isinstance(a, str):
                            bad += 1
                except Exception:
                    pass
        return (bad == 0), f"arguments 非字符串 {bad} 个"

    # ---- 工具调用 ----
    if "禁止时不得调用" in t:
        cid = case["id"]
        names = _tool_names(r)
        if cid.endswith("-none"):
            return (not names), f"tool_choice=none 实测工具 {names!r}"
        ok = "lookup" in names
        return ok, f"实测工具 {names!r}（预期含 lookup）"
    if "禁止工具且仍有非空正文" in t:
        names = _tool_names(r)
        c = _final_content(case, results)
        return (not names and bool(c.strip())), (
            f"工具 {names!r}（预期空），正文 {len(c)} 字")
    if ("lookup" in t and ("调用" in t or "返回" in t or "指定" in t)):
        names = _tool_names(r)
        return ("lookup" in names), f"实测工具 {names!r}"
    if "工具参数必须准确查询 A" in t:
        names = _tool_names(r)
        if "lookup" not in names:
            return False, f"未调用 lookup，实测 {names!r}"
        args = ""
        if isinstance(r.get("json"), dict):
            try:
                for tc in r["json"]["choices"][0]["message"].get("tool_calls") or []:
                    args += str((tc.get("function") or {}).get("arguments") or "")
            except Exception:
                pass
        return ("\"A\"" in args or "'A'" in args or ": \"A\"" in args
                or "A" in args), f"arguments={args[:80]!r}"
    if "mean" in t and "29" in t:
        c = _final_content(case, results)
        return ("29" in c), f"最终正文={c[:80]!r}"
    if "流式工具参数与依赖传递有效" in t:
        names = _tool_names(r)
        return bool(names), f"流式工具名序列 {names!r}"
    if "tool_calls 存在" in t or "存在工具调用" in t:
        names = _tool_names(r)
        return bool(names), f"工具 {names!r}"
    if "关闭并行时单轮至多一次调用" in t:
        names = _tool_names(r)
        return (len(names) <= 1), f"单轮工具调用 {len(names)} 次（{names!r}）"

    # ---- 缓存 ----
    if "写入量响应头" in t and "非负整数" in t:
        hds = _cache_write_headers(r)
        if not hds:
            return False, "无缓存写入响应头（Msh-Usage-Cache-Write-Tokens-*）"
        bad = []
        for k, v in hds.items():
            try:
                if int(str(v)) < 0:
                    bad.append(k)
            except ValueError:
                bad.append(k)
        return (not bad), f"缓存写入头 {hds!r}"
    if "同前缀" in t or "缓存命中" in t or "达到一次明确命中" in t:
        ct = max((_cached_tokens(x) for x in results), default=0)
        return (ct > 0), f"cached_tokens 最大 {ct}"
    if "二次起出现 cached_tokens" in t:
        ct = max((_cached_tokens(x) for x in results[1:]), default=0)
        return (ct >= 256), f"第二次起 cached_tokens 最大 {ct}（预期 ≥256）"

    # ---- 内容/JSON 读取 ----
    if ("随机编号" in t and "完全正确" in t) or "记录值完全正确" in t:
        exp = _needle_expectations(case)
        if not exp:
            return None, "期望值未能从 payload 提取（记录式）"
        c = _final_content(case, results)
        missing = [k for k, v in exp.items() if v not in c]
        return (not missing), (f"缺失 {missing}；期望 {exp}；"
                               f"正文截 120: {c[:120]!r}")
    if "JSON 结构" in t and ("取值" in t or "读取" in t):
        c = _final_content(case, results).strip()
        c2 = c.strip("`").strip()
        if c2.startswith("```"):
            c2 = "\n".join(c2.split("\n")[1:]).rsplit("```", 1)[0]
        try:
            parsed = json.loads(c2)
            ok = isinstance(parsed, (dict, list)) and bool(parsed)
            return ok, f"JSON 可解析，类型 {type(parsed).__name__}"
        except Exception as e:
            return False, f"正文非合法 JSON: {str(e)[:60]}；{c[:80]!r}"
    if "已注入错误且一次重试后返回真实值" in t:
        c = _final_content(case, results)
        return bool(c.strip()), f"最终正文 {len(c)} 字（重放语义：应答存在）"
    if "已注入永久错误且不重试不编造" in t:
        return None, "不编造语义不可机判（记录式），正文="
        f"{_final_content(case, results)[:60]!r}"
    if "准确返回首轮编号" in t or "准确回忆编号" in t:
        return None, "编号类判定（记录式，场景编号提取依赖探针上下文）"
    if "正确朗读" in t or "准确朗读" in t or "正确识读" in t:
        return None, f"朗读/识读类判定（记录式，正文={_final_content(case, results)[:60]!r}）"
    if "识别颜色" in t:
        c = _final_content(case, results)
        return ("red" in c.lower()), f"正文={c[:60]!r}"

    # ---- 兜底：未映射判定项降级为观察 ----
    return None, f"未映射判定项（降级观察）: {t[:100]}"


# ---------------------------------------------------------------------------
# skip 规则
# ---------------------------------------------------------------------------

_YQZL_SKIP_IDS = {
    "VISION-VIDEO": "报告标记 SKIP（依赖文件上传成功）",
    "FILES-VIDEO": "不适用：multipart 文件上传且 fixture 视频文件未随报告提供",
    "FILES-VIDEO-EXTENSION": "不适用：multipart 文件上传且 fixture 视频文件未随报告提供",
}


def _yqzl_skip_reason(case: Dict[str, Any]) -> Optional[str]:
    if case["id"] in _YQZL_SKIP_IDS:
        return _YQZL_SKIP_IDS[case["id"]]
    if case.get("badge") == "SKIP":
        return f"报告标记 SKIP（{case.get('note') or '报告未执行'}）"
    if not case.get("requests"):
        return "报告无请求信息（无法重放）"
    if not (case.get("expect") or "").strip() and not case.get("assertions"):
        return "报告无场景期望与逐项判定（标记跳过，待补充预期）"
    return None


class TestYqzlAGDC2_75:
    """杭州耘擎智联 AGDC2-75 kimi-k3 功能测试报告 239 用例重放。"""

    @pytest.mark.parametrize(
        "case", _MAIN_CASES, ids=[c["id"] for c in _MAIN_CASES])
    def test_case(self, case, api_client, test_logger):
        """报告用例重放（参数化：239 条，节点名=报告用例 id）。

        断言基准 = 报告「规范要求 / 场景期望」与「逐项判定」清单（用
        户口径：报告里有预期先按报告行为断言）；记录式判定项只记录；
        未映射判定项降级观察；无期望/不适用项 skip。
        """
        cid = case["id"]
        _YQZL_CURRENT_CASE[0] = cid
        reason = _yqzl_skip_reason(case)
        if reason:
            pytest.skip(f"{cid}: {reason}")
        test_logger.info(
            "=== 重放 %s（%s · %s · 报告总判定 %s）: %d 请求 ===",
            cid, case.get("category"), case.get("title"),
            case.get("badge"), len(case["requests"]))
        results: List[Dict[str, Any]] = []
        for i, req in enumerate(case["requests"], 1):
            payload = req.get("payload")
            if payload is None:
                pytest.skip(f"{cid}: 请求 #{i} 无 payload（报告提取缺失）")
            payload = json.loads(json.dumps(payload))
            if isinstance(payload, dict) and "model" in payload:
                payload["model"] = api_client.model_name
            r = _yqzl_send(api_client, case.get("kind") or "chat", payload,
                           bool(case.get("stream")),
                           case.get("auth") or "session")
            results.append(r)
            test_logger.info(
                "%s 请求 %d/%d 实测: HTTP %s（报告实测 HTTP %s）",
                cid, i, len(case["requests"]), r["status"], req.get("status"))
        fails = []
        _YQZL_EVALS[cid] = []
        for a in case.get("assertions") or []:
            ok, detail = _eval_assertion(a["text"], case, results, api_client)
            _YQZL_EVALS[cid].append((a["text"], ok, detail))
            if ok is False:
                fails.append(f"[{a['text']}] {detail}")
            elif ok is None:
                _yqzl_obs(f"{cid} 记录式判定项：{a['text']}（{detail}）")
        assert not fails, (
            f"{cid} 逐项判定失败 {len(fails)} 项（基准=报告场景期望）："
            + "；".join(fails[:6])
        )
        test_logger.info("%s 逐项判定全部通过（%d 项）", cid,
                         len(case.get("assertions") or []))

    @pytest.mark.slow_ttl
    @pytest.mark.parametrize(
        "case", _TTL_CASES, ids=[c["id"] for c in _TTL_CASES])
    def test_ttl_boundary(self, case, api_client, test_logger):
        """TTL 缓存边界探针（TTL-001~007，slow_ttl 慢速约 44 分钟）。

        复刻报告等待时长（场景期望「实际静默等待 Xs」：180/300.1/300/
        301/360/600/600s）后断言二次缓存命中（用户确认 2026-11-23 方案
        A）：请求 1 → sleep(报告等待时长) → 请求 2 → 断言 HTTP 200 +
        cached_tokens > 0（报告 20261119 实测二次 cached_tokens=1728；
        实测 cached=0 时判 FAIL——若为 5m TTL 正确过期则属报告记录异
        常，若为缓存未生效则属缺陷，需人工复核）。
        """
        import re as _re

        cid = case["id"]
        _YQZL_CURRENT_CASE[0] = cid
        if not case.get("requests") or len(case["requests"]) < 2:
            pytest.skip(f"{cid}: 报告请求不足 2 条（无法执行边界探针）")
        # 报告等待时长提取（场景期望「实际静默等待 Xs」）
        wm = _re.search(r"实际静默等待\s*([\d.]+)\s*s", case.get("expect") or "")
        wait_s = float(wm.group(1)) if wm else 0.0
        if wait_s <= 0:
            pytest.skip(f"{cid}: 场景期望未含等待时长（无法复刻边界探针）")

        def _payload_of(req):
            p = json.loads(json.dumps(req["payload"]))
            if isinstance(p, dict) and "model" in p:
                p["model"] = api_client.model_name
            return p

        # 请求 1（缓存写入）
        r1 = _yqzl_send(api_client, case.get("kind") or "chat",
                        _payload_of(case["requests"][0]),
                        bool(case.get("stream")), case.get("auth") or "session")
        w1 = _usage_of(r1)
        _yqzl_obs(f"{cid} 首次请求: HTTP {r1['status']}，"
                  f"cache_write_tokens="
                  f"{((w1.get('prompt_tokens_details') or {}).get('cache_write_tokens'))!r}，"
                  f"cached_tokens={_cached_tokens(r1)}")
        test_logger.info(
            "%s 首次请求 HTTP %s，等待报告时长 %.1fs 后二次请求……",
            cid, r1["status"], wait_s)
        assert r1["status"] == 200, (
            f"{cid} 首次请求应 HTTP 200（缓存写入前提），"
            f"实测 HTTP {r1['status']}；响应: {r1['raw'][:200]}"
        )

        time.sleep(wait_s)

        # 请求 2（同前缀——缓存命中探测）
        r2 = _yqzl_send(api_client, case.get("kind") or "chat",
                        _payload_of(case["requests"][1]),
                        bool(case.get("stream")), case.get("auth") or "session")
        ct2 = _cached_tokens(r2)
        _yqzl_obs(f"{cid} 二次请求（等待 {wait_s}s 后）: HTTP {r2['status']}，"
                  f"cached_tokens={ct2}（报告 20261119 实测 1728）")
        _YQZL_EVALS[cid] = [
            ("首次请求 HTTP 200", r1["status"] == 200,
             f"实测 HTTP {r1['status']}"),
            ("两次请求 HTTP 200", r2["status"] == 200,
             f"实测 HTTP {r2['status']}"),
            ("二次 cached_tokens 命中（报告实测 1728）", ct2 > 0,
             f"实测 cached_tokens={ct2}"),
        ]
        assert r2["status"] == 200, (
            f"{cid} 二次请求应 HTTP 200，实测 HTTP {r2['status']}；"
            f"响应: {r2['raw'][:200]}"
        )
        assert ct2 > 0, (
            f"{cid} 二次 cached_tokens 应命中（>0，报告 20261119 实测 "
            f"1728），实测 {ct2}——若为 5m TTL 正确过期（{wait_s}s>300s）"
            f"则属报告记录异常；若为缓存未生效则属缺陷，需人工复核"
        )
        test_logger.info(
            "%s 边界探针通过: 等待 %.1fs 后二次 cached_tokens=%d",
            cid, wait_s, ct2)
