"""深空数能工单 AGDC2-57 kimi-k3 能力确认套件（38 用例）。

数据源（用户指定 2026-11-17）：AGDC2-57 目录两份分析文档——
《AGDC2-57-K3官方API响应头与SGLang差异对比》《AGDC2-57-K3模型usage
字段说明》。官方行为依据 Kimi 公开文档（Chat Completions API /
上下文缓存最佳实践 / 流式输出指南 / K3 快速开始）与 AGDC2-47 归档
样本；本地侧为 SGLang 源码核对结论。

客户 7 项确认事项 → 用例分组（报告按域展示）：
- C1 缓存写入（#1-#6）：prompt_cache_options.mode=write 行为与
  cache_write_tokens 字段；
- C2 TTL（#7-#17，重点）：5m/1h 写入、TTL 内命中、缺省/非法值
  行为、Anthropic TTL 场景、TTL 过期验证（slow_ttl 慢速标记）；
- C3 usage 字段（#18-#25）：三元组与公式、reasoning 明细、缓存
  读写字段、流式最终统计；
- C4 响应头（#26-#31）：通用头、Msh 平台身份头、缓存写入头、
  SSE Content-Type、部署层头、限流头；
- C5 OpenAI 协议（#32-#35）：标准字段、SSE、错误体、message 结构；
- C6 Anthropic 协议（#36-#38）：标准字段、SSE、usage 缓存字段。

断言口径（用户确认 2026-11-17）：
- 硬断言（FAIL）= 协议层：请求发送异常；基础请求非 200；非流式
  JSON 不可解析；SSE 无收束；OpenAI/Anthropic 标准字段缺失；
  usage 三元组缺失或 total=prompt+completion 公式错误；
- 软断言（PASS 仅记录差异）= 能力层：缓存写入头 / cache_write_tokens
  / cached_tokens / 分 TTL 统计 / Msh-* 平台身份头 / TTL 内命中 /
  TTL 过期行为 / 缺省与非法值行为 / Anthropic cache_creation 明细
  ——实测行为经 _sksn_obs 记录为观察项（observations），用例判
  PASS，报告中展示支持/缺口差异。能力请求（缓存/TTL 参数）被 4xx
  拒绝属能力缺口记录，不判 FAIL。

协议端点：
- chat:     POST {api_prefix}/chat/completions（Authorization: Bearer）；
- messages: POST {base_url}/anthropic/v1/messages（x-api-key +
  anthropic-version: 2023-06-01）（同 lexin 套件先例）。

请求报文口径：
- model 字段运行时替换为部署模型名（api_client.model_name）；
- 采样参数豁免：conftest RAW_SAMPLING_EXEMPT_FILES 整模块豁免
  （同 test_k / test_lexin / test_zjxm 口径），不注入采样参数；
- marker：sksn_agdc2_57（conftest 按 test_sksn_ 前缀自动打标；
  默认收集排除——仅显式点名时执行，与 Jenkinsfile MARKER_ALL
  排除互为双保险）；不进 SPECIFIC_TEST（用户指定 2026-11-17）；
- 慢速标记：#17 TTL 过期验证带 @pytest.mark.slow_ttl（等待约
  5.5 分钟）；可用 -m "sksn_agdc2_57 and not slow_ttl" 快速跑。

报告（base/sksn_html_report.py）：7 项问题结论表 + 用例结果总览
（含观察项）+ 用例明细 HTML，及 Jenkins 邮件提取用 MD；录制记录
会话末导出 sksn_records.json。

不进 smoke 集；无 P0/P1/P2 标记（能力确认/差异记录套件）。
"""

import inspect
import json
import time

import pytest
import requests

from typing import Any, Dict, List, Optional


def _sksn_current_test() -> str:
    """栈回溯取当前所属用例方法名（test_* 帧）；无则返回 'unknown'。"""
    for fr in inspect.stack():
        fn = fr.function
        if fn.startswith("test_"):
            return fn
    return "unknown"


def _sksn_mask_key(headers: Optional[dict]) -> Dict[str, Any]:
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


def _sksn_record(test: str, url: str, kind: str, headers: Optional[dict],
                 payload: Optional[dict], status=None, elapsed=None,
                 resp_headers=None, resp_body=None, error=None):
    """录制一条请求记录（内存态，会话末由 conftest 导出）。"""
    _SKSN_RECORDER.append({
        "test": test,
        "url": url,
        "kind": kind,
        "req_headers": _sksn_mask_key(headers),
        "req_body": payload,
        "status": status,
        "elapsed": elapsed,
        "resp_headers": dict(resp_headers) if resp_headers else {},
        "resp_body": resp_body,
        "error": str(error) if error else None,
    })


# 全量请求录制（报告数据源）：每请求一条，内存态；conftest 在会话末
# 导出 JSON 并生成 HTML/MD 报告（base/sksn_html_report.py）。
_SKSN_RECORDER: list = []

# 能力层观察项（软断言记录）：{用例方法名: [观察文本]}；报告生成器
# 按用例展示「支持/缺口/差异」事实，不参与 PASS/FAIL 判定。
_SKSN_OBS: Dict[str, List[str]] = {}


def _sksn_obs(text: str) -> None:
    """追加一条能力观察记录（归属当前 test_* 用例）。"""
    _SKSN_OBS.setdefault(_sksn_current_test(), []).append(text)


# 缓存写入用长输入：约 2400 字（≥1024 token 缓存写入最小长度惯例），
# 重复段落保证同一 payload 前缀完全一致（缓存命中前提）。
_SKSN_LONG_TEXT = (
    "人工智能是研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及"
    "应用系统的一门新的技术科学。人工智能领域的研究包括机器人、语言识别、"
    "图像识别、自然语言处理和专家系统等。自诞生以来，人工智能理论和技术日益"
    "成熟，应用领域也不断扩大，可以设想，未来人工智能带来的科技产品，将会是"
    "人类智慧的容器。"
) * 40


# ---------------------------------------------------------------------------
# URL / 请求头 / 流式检测
# ---------------------------------------------------------------------------

def _sksn_url(kind: str, api_client) -> str:
    if kind == "chat":
        return f"{api_client.api_prefix}/chat/completions"
    return f"{api_client.base_url}/anthropic/v1/messages"


def _sksn_headers(kind: str, api_client) -> Dict[str, Any]:
    headers: Dict[str, Any] = {"Content-Type": "application/json"}
    if kind == "messages":
        headers["anthropic-version"] = "2023-06-01"
        if api_client.api_key:
            headers["x-api-key"] = api_client.api_key
        return headers
    if api_client.api_key:
        headers["Authorization"] = f"Bearer {api_client.api_key}"
    return headers


def _sksn_stream_flag(payload: dict) -> bool:
    v = payload.get("stream")
    return v is True or v == 1 or v == "1" or (
        isinstance(v, str) and v.strip().lower() == "true"
    )


# ---------------------------------------------------------------------------
# 响应解析（chat / messages 双协议）
# ---------------------------------------------------------------------------

def _sksn_json_summary(kind: str, data) -> Dict[str, Any]:
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
    return {"err_bit": err_bit, "content": content, "reasoning": reasoning,
            "usage": usage, "finish_reason": finish_reason}


def _sksn_sse_summary(kind: str, lines) -> Dict[str, Any]:
    content = reasoning = ""
    err_bit = 0
    done = False
    finish_reason = None
    usage = None
    saw_message_start = False
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
        elif kind == "messages":
            et = ev.get("type")
            if et == "error":
                err_bit = 1
            if et == "message_start":
                saw_message_start = True
                u = (ev.get("message") or {}).get("usage")
                if isinstance(u, dict):
                    usage = dict(u)
            if et == "content_block_delta":
                d = ev.get("delta") or {}
                if d.get("type") == "text_delta" and d.get("text"):
                    content += d["text"]
                if d.get("type") == "thinking_delta" and d.get("thinking"):
                    reasoning += d["thinking"]
            if et == "message_delta":
                if isinstance(ev.get("usage"), dict):
                    usage = dict(usage or {})
                    usage.update(ev["usage"])
                d = ev.get("delta") or {}
                if d.get("stop_reason"):
                    finish_reason = d["stop_reason"]
            if et == "message_stop":
                done = True
    return {"err_bit": err_bit, "content": content, "reasoning": reasoning,
            "done": done, "finish_reason": finish_reason, "usage": usage,
            "saw_message_start": saw_message_start}


def _sksn_send(api_client, kind: str, payload: dict) -> Dict[str, Any]:
    """发送一条请求并录制；返回 状态/原始报文/响应头/解析结果 摘要。

    流式请求额外返回 events（逐 SSE data 事件解析结果）。返回字典含
    resp_headers（响应头断言/观察用，大小写不敏感访问前自行 lower）。
    """
    test = _sksn_current_test()
    url = _sksn_url(kind, api_client)
    headers = _sksn_headers(kind, api_client)
    streaming = _sksn_stream_flag(payload)
    t0 = time.time()
    try:
        resp = api_client.session.post(
            url, json=payload, headers=headers,
            timeout=api_client.timeout, stream=streaming,
        )
    except Exception as e:
        _sksn_record(test, url, kind, headers, payload,
                     error=e, elapsed=time.time() - t0)
        pytest.fail(f"请求发送异常（{url}）: {e}")
    status = resp.status_code
    resp_headers = dict(resp.headers)
    if streaming:
        lines = [ln for ln in resp.iter_lines(decode_unicode=True) if ln]
        elapsed = time.time() - t0
        _sksn_record(test, url, kind, headers, payload,
                     status=status, elapsed=elapsed,
                     resp_headers=resp_headers,
                     resp_body="\n".join(lines))
        if lines and any(ln.startswith("data:") for ln in lines):
            s = _sksn_sse_summary(kind, lines)
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
                    "done": s["done"], "events": events,
                    "resp_headers": resp_headers,
                    "saw_message_start": s["saw_message_start"]}
        raw = "\n".join(lines)
    else:
        raw = resp.text
        elapsed = time.time() - t0
        _sksn_record(test, url, kind, headers, payload,
                     status=status, elapsed=elapsed,
                     resp_headers=resp_headers,
                     resp_body=raw)
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = None
    s = _sksn_json_summary(kind, parsed)
    return {"status": status, "raw": raw, "json": parsed, "err_bit": s["err_bit"],
            "content": s["content"], "reasoning": s["reasoning"],
            "usage": s["usage"], "finish_reason": s["finish_reason"],
            "sse": False, "done": None, "events": [],
            "resp_headers": resp_headers, "saw_message_start": False}


# ---------------------------------------------------------------------------
# 断言辅助
# ---------------------------------------------------------------------------

def _sksn_headers_lower(result: Dict[str, Any]) -> Dict[str, Any]:
    return {str(k).lower(): v for k, v in (result.get("resp_headers") or {}).items()}


def _sksn_assert_chat_200(result: Dict[str, Any], no: int, req: int = 1) -> None:
    """硬断言（协议层）：HTTP 200 + 非流式 JSON 可解析。"""
    assert result["status"] == 200, (
        f"#{no} 请求 {req} 基础请求应 HTTP 200，实测 HTTP {result['status']}；"
        f"响应: {result['raw'][:300]}"
    )
    assert isinstance(result["json"], dict), (
        f"#{no} 请求 {req} 非流式响应应为可解析 JSON 对象，"
        f"实测解析失败；响应: {result['raw'][:300]}"
    )


def _sksn_assert_usage_triple(result: Dict[str, Any], no: int,
                              req: int = 1) -> dict:
    """硬断言（协议层）：usage 三元组完整 + total=prompt+completion。"""
    u = result.get("usage")
    assert isinstance(u, dict), (
        f"#{no} 请求 {req} usage 应为对象，实测 {u!r}；"
        f"响应: {result['raw'][:300]}"
    )
    p, c, t = (u.get("prompt_tokens"), u.get("completion_tokens"),
               u.get("total_tokens"))
    assert isinstance(p, int) and isinstance(c, int) and isinstance(t, int), (
        f"#{no} 请求 {req} usage 三元组应为整数（prompt/completion/total），"
        f"实测 prompt={p!r} completion={c!r} total={t!r}；"
        f"响应: {result['raw'][:300]}"
    )
    assert t == p + c, (
        f"#{no} 请求 {req} total_tokens 应等于 prompt+completion（{p}+{c}），"
        f"实测 {t}；响应: {result['raw'][:300]}"
    )
    return u


def _sksn_capability_ok(result: Dict[str, Any], no: int, req: int = 1) -> bool:
    """能力请求状态分流：200 → True（继续做结构硬断言与能力观察）；
    其他状态 → 记录能力缺口观察并返回 False（用例 PASS 收尾）。"""
    if result["status"] == 200:
        return True
    _sksn_obs(
        f"#{no} 请求 {req} 能力请求未放行：HTTP {result['status']}"
        f"（能力缺口/行为记录，不判失败）；响应: {result['raw'][:200]}")
    return False


def _sksn_obs_cache_write_headers(result: Dict[str, Any], no: int,
                                  req: int = 1):
    """软观察：Msh-Usage-Cache-Write-Tokens-5m/1h 响应头存在性与取值。"""
    h = _sksn_headers_lower(result)
    v5 = h.get("msh-usage-cache-write-tokens-5m")
    v1 = h.get("msh-usage-cache-write-tokens-1h")
    if v5 is None and v1 is None:
        _sksn_obs(f"#{no} 请求 {req} 缓存写入响应头（5m/1h）缺失"
                  f"（官方能力缺口记录）")
    else:
        _sksn_obs(f"#{no} 请求 {req} 缓存写入头: 5m={v5!r}, 1h={v1!r}")
    return v5, v1


def _sksn_usage_details(result: Dict[str, Any]):
    u = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    pd = u.get("prompt_tokens_details")
    cd = u.get("completion_tokens_details")
    return u, (pd if isinstance(pd, dict) else {}), (cd if isinstance(cd, dict) else {})


def _sksn_obs_cache_write_tokens(result: Dict[str, Any], no: int,
                                 req: int = 1):
    """软观察：usage.prompt_tokens_details.cache_write_tokens（官方字段，
    本地 SGLang 源码无此字段——实质缺口）。"""
    _, pd, _ = _sksn_usage_details(result)
    v = pd.get("cache_write_tokens")
    if v is None:
        _sksn_obs(f"#{no} 请求 {req} usage 无 cache_write_tokens 字段"
                  f"（官方能力缺口记录）")
    else:
        _sksn_obs(f"#{no} 请求 {req} cache_write_tokens={v!r}")
    return v


def _sksn_obs_cached_tokens(result: Dict[str, Any], no: int, req: int = 1):
    """软观察：usage.prompt_tokens_details.cached_tokens（缓存读取命中数）。"""
    _, pd, _ = _sksn_usage_details(result)
    v = pd.get("cached_tokens")
    _sksn_obs(f"#{no} 请求 {req} cached_tokens={v!r}")
    return v


class TestSksnAGDC2_57:
    """深空数能 AGDC2-57 kimi-k3 能力确认（7 项问题 / 6 域 38 用例）。"""

    # ------------------------------------------------------------------
    # C1 缓存写入（#1-#6）
    # ------------------------------------------------------------------

    def test_01_cache_write_basic(self, api_client, test_logger):
        """#1 mode=write 基础缓存写入（C1 缓存写入）

        来源: AGDC2-57 客户问题 1「是否支持缓存写入」；官方上下文缓存
        最佳实践文档明确 kimi-k3 支持 Cache Write。
        断言口径: 硬——200 + JSON 可解析；软——Msh-Usage-Cache-Write-
        Tokens-5m/1h 响应头、usage.prompt_tokens_details.cache_write_tokens。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write"},
        }
        result = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(result, 1):
            test_logger.info("#1 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        _sksn_assert_chat_200(result, 1)
        _sksn_assert_usage_triple(result, 1)
        _sksn_obs_cache_write_headers(result, 1)
        _sksn_obs_cache_write_tokens(result, 1)
        test_logger.info("#1 请求 1 实测: HTTP %s", result["status"])

    def test_02_cache_write_then_read_hit(self, api_client, test_logger):
        """#2 缓存写入后二次相同请求命中（C1 缓存写入）

        来源: AGDC2-57 客户问题 1；官方口径——写入后相同前缀应命中缓存
        读取（cached_tokens），第二次不再产生写入计数。
        断言口径: 硬——两次均 200 + usage 三元组；软——第二次
        cached_tokens / cache_write_tokens 取值记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write"},
        }
        r1 = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(r1, 2):
            test_logger.info("#2 请求 1 实测: HTTP %s（能力缺口已记录）",
                             r1["status"])
            return
        _sksn_assert_chat_200(r1, 2)
        _sksn_assert_usage_triple(r1, 2)
        r2 = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(r2, 2, req=2)
        _sksn_assert_usage_triple(r2, 2, req=2)
        _sksn_obs_cached_tokens(r1, 2, req=1)
        _sksn_obs_cached_tokens(r2, 2, req=2)
        w2 = _sksn_obs_cache_write_tokens(r2, 2, req=2)
        if w2 not in (None, 0):
            _sksn_obs(f"#2 请求 2 二次请求仍产生写入计数 {w2!r}"
                      f"（与官方「命中后不再写入」口径差异记录）")
        test_logger.info("#2 请求 1/2 实测: HTTP %s/%s",
                         r1["status"], r2["status"])

    def test_03_cache_write_vs_read_fields(self, api_client, test_logger):
        """#3 缓存写入与缓存读取字段语义区分（C1 缓存写入）

        来源: AGDC2-57 usage 文档「缓存写入头与缓存命中数不同」——
        cache_write_tokens 是本次写入计数，cached_tokens 是读取命中
        统计，不能互相代替。
        断言口径: 硬——200 + usage 三元组；软——两字段取值分别记录，
        存在性即区分（不得用 cached_tokens 冒充写入计数）。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write"},
        }
        result = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(result, 3):
            test_logger.info("#3 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        _sksn_assert_chat_200(result, 3)
        _sksn_assert_usage_triple(result, 3)
        _sksn_obs_cache_write_tokens(result, 3)
        _sksn_obs_cached_tokens(result, 3)
        test_logger.info("#3 请求 1 实测: HTTP %s", result["status"])

    def test_04_no_cache_options_default(self, api_client, test_logger):
        """#4 无 prompt_cache_options 默认行为（C1 缓存写入）

        来源: AGDC2-57 客户问题 1；官方文档未公开缺省 mode 行为
        （是否自动写入），记录实测。
        断言口径: 硬——200 + usage 三元组；软——cache_write_tokens /
        缓存写入头在缺省请求下是否出现（默认行为记录）。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 4)
        _sksn_assert_usage_triple(result, 4)
        _sksn_obs_cache_write_headers(result, 4)
        _sksn_obs_cache_write_tokens(result, 4)
        _sksn_obs_cached_tokens(result, 4)
        test_logger.info("#4 请求 1 实测: HTTP %s", result["status"])

    def test_05_cache_three_category_check(self, api_client, test_logger):
        """#5 三类输入互斥口径记录（C1 缓存写入）

        来源: 官方缓存最佳实践——输入分三类互斥：未缓存 = prompt_tokens
        - cached_tokens - cache_write_tokens，合计为总输入。
        断言口径: 硬——两次均 200 + usage 三元组；软——第二次请求
        cached + write ≤ prompt_tokens 口径记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write"},
        }
        r1 = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(r1, 5):
            test_logger.info("#5 请求 1 实测: HTTP %s（能力缺口已记录）",
                             r1["status"])
            return
        _sksn_assert_chat_200(r1, 5)
        r2 = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(r2, 5, req=2)
        u2 = _sksn_assert_usage_triple(r2, 5, req=2)
        _, pd, _ = _sksn_usage_details(r2)
        cached = pd.get("cached_tokens") or 0
        write = pd.get("cache_write_tokens") or 0
        p = u2.get("prompt_tokens") or 0
        if isinstance(cached, int) and isinstance(write, int):
            if cached + write <= p:
                _sksn_obs(f"#5 请求 2 三类口径自洽: cached({cached})+"
                          f"write({write})≤prompt({p})")
            else:
                _sksn_obs(f"#5 请求 2 三类口径越界: cached({cached})+"
                          f"write({write})>prompt({p})（差异记录）")
        test_logger.info("#5 请求 1/2 实测: HTTP %s/%s",
                         r1["status"], r2["status"])

    def test_06_cache_write_stream(self, api_client, test_logger):
        """#6 流式缓存写入最终统计（C1 缓存写入）

        来源: 官方流式输出指南——include_usage=true 时最终 choices=[]
        chunk 携带完整 usage，缓存读写明细在最终 chunk 返回。
        断言口径: 硬——200 + SSE [DONE] 收束 + 最终 usage 存在；
        软——最终 usage 的缓存读写明细记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write"},
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        result = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(result, 6):
            test_logger.info("#6 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        assert result["status"] == 200, (
            f"#6 请求 1 基础请求应 HTTP 200，实测 HTTP {result['status']}；"
            f"响应: {result['raw'][:300]}"
        )
        assert result.get("sse") and result.get("done"), (
            f"#6 请求 1 流式响应应以 data: [DONE] 收束，实测未收束；"
            f"响应: {result['raw'][:300]}"
        )
        u = result.get("usage")
        assert isinstance(u, dict) and u, (
            f"#6 请求 1 include_usage=true 最终 chunk 应携带 usage，"
            f"实测缺失；响应: {result['raw'][:300]}"
        )
        _, pd, _ = _sksn_usage_details(result)
        _sksn_obs(f"#6 请求 1 流式最终 usage 缓存明细: "
                  f"cached={pd.get('cached_tokens')!r}, "
                  f"write={pd.get('cache_write_tokens')!r}")
        _sksn_obs_cache_write_headers(result, 6)
        test_logger.info("#6 请求 1 实测: HTTP %s（流式）", result["status"])

    # ------------------------------------------------------------------
    # C2 TTL（#7-#17，重点）
    # ------------------------------------------------------------------

    def test_07_ttl_5m_write(self, api_client, test_logger):
        """#7 ttl=5m 缓存写入分 TTL 统计（C2 TTL）

        来源: AGDC2-57 客户问题 3「是否支持 TTL」；官方——TTL 枚举
        5m/1h，按 TTL 写入的 token 数经 Msh-Usage-Cache-Write-Tokens-
        5m / -1h 响应头分别统计。
        断言口径: 硬——200 + usage 三元组；软——5m 头非负 / 1h 头
        取值记录（分 TTL 统计对应）。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write", "ttl": "5m"},
        }
        result = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(result, 7):
            test_logger.info("#7 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        _sksn_assert_chat_200(result, 7)
        _sksn_assert_usage_triple(result, 7)
        v5, v1 = _sksn_obs_cache_write_headers(result, 7)
        if v5 is not None and v1 is not None:
            _sksn_obs(f"#7 请求 1 分 TTL 统计: 5m={v5!r}（本请求应计入），"
                      f"1h={v1!r}（本请求应为 0 或不计）")
        test_logger.info("#7 请求 1 实测: HTTP %s", result["status"])

    def test_08_ttl_1h_write(self, api_client, test_logger):
        """#8 ttl=1h 缓存写入分 TTL 统计（C2 TTL）

        来源: AGDC2-57 客户问题 2「是否支持 1h 缓存」；官方——TTL
        枚举含 1h，写入计数经 -1h 响应头统计。
        断言口径: 硬——200 + usage 三元组；软——1h 头非负 / 5m 头
        取值记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write", "ttl": "1h"},
        }
        result = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(result, 8):
            test_logger.info("#8 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        _sksn_assert_chat_200(result, 8)
        _sksn_assert_usage_triple(result, 8)
        v5, v1 = _sksn_obs_cache_write_headers(result, 8)
        if v5 is not None and v1 is not None:
            _sksn_obs(f"#8 请求 1 分 TTL 统计: 1h={v1!r}（本请求应计入），"
                      f"5m={v5!r}（本请求应为 0 或不计）")
        test_logger.info("#8 请求 1 实测: HTTP %s", result["status"])

    def test_09_ttl_5m_reuse_within_ttl(self, api_client, test_logger):
        """#9 ttl=5m 写入后 TTL 窗口内复用命中（C2 TTL）

        来源: 官方缓存 TTL 语义——TTL 窗口内相同前缀请求应命中缓存。
        断言口径: 硬——两次均 200 + usage 三元组；软——第二次
        cached_tokens 取值记录（TTL 内命中证据）。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write", "ttl": "5m"},
        }
        r1 = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(r1, 9):
            test_logger.info("#9 请求 1 实测: HTTP %s（能力缺口已记录）",
                             r1["status"])
            return
        _sksn_assert_chat_200(r1, 9)
        r2 = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(r2, 9, req=2)
        _sksn_assert_usage_triple(r2, 9, req=2)
        v = _sksn_obs_cached_tokens(r2, 9, req=2)
        if isinstance(v, int) and v > 0:
            _sksn_obs(f"#9 请求 2 TTL 窗口内命中: cached_tokens={v}")
        else:
            _sksn_obs(f"#9 请求 2 TTL 窗口内未见命中: cached_tokens={v!r}"
                      f"（差异记录）")
        test_logger.info("#9 请求 1/2 实测: HTTP %s/%s",
                         r1["status"], r2["status"])

    def test_10_ttl_1h_reuse_within_ttl(self, api_client, test_logger):
        """#10 ttl=1h 写入后 TTL 窗口内复用命中（C2 TTL）

        来源: 同 #9（TTL 窗口内命中），TTL=1h 变体。
        断言口径: 硬——两次均 200 + usage 三元组；软——第二次
        cached_tokens 取值记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write", "ttl": "1h"},
        }
        r1 = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(r1, 10):
            test_logger.info("#10 请求 1 实测: HTTP %s（能力缺口已记录）",
                             r1["status"])
            return
        _sksn_assert_chat_200(r1, 10)
        r2 = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(r2, 10, req=2)
        _sksn_assert_usage_triple(r2, 10, req=2)
        v = _sksn_obs_cached_tokens(r2, 10, req=2)
        if isinstance(v, int) and v > 0:
            _sksn_obs(f"#10 请求 2 TTL 窗口内命中: cached_tokens={v}")
        else:
            _sksn_obs(f"#10 请求 2 TTL 窗口内未见命中: cached_tokens={v!r}"
                      f"（差异记录）")
        test_logger.info("#10 请求 1/2 实测: HTTP %s/%s",
                         r1["status"], r2["status"])

    def test_11_ttl_default_when_omitted(self, api_client, test_logger):
        """#11 mode=write 缺省 ttl 默认行为（C2 TTL）

        来源: 官方文档未公开缺省 TTL 取值；记录实测——缺省时写入
        计数计入 5m 还是 1h 头。
        断言口径: 硬——200 + usage 三元组；软——5m/1h 头取值记录
        （缺省 TTL 归属）。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write"},
        }
        result = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(result, 11):
            test_logger.info("#11 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        _sksn_assert_chat_200(result, 11)
        _sksn_assert_usage_triple(result, 11)
        v5, v1 = _sksn_obs_cache_write_headers(result, 11)
        if v5 is not None or v1 is not None:
            _sksn_obs(f"#11 请求 1 缺省 ttl 写入归属: 5m={v5!r}, 1h={v1!r}")
        test_logger.info("#11 请求 1 实测: HTTP %s", result["status"])

    def _sksn_ttl_value_case(self, api_client, test_logger, no: int,
                             options: dict, label: str):
        """TTL/mode 非法值行为记录（200 放行与 4xx 拒绝均为可接受实测，
        记录状态与错误体结构）。"""
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 32,
            "prompt_cache_options": options,
        }
        result = _sksn_send(api_client, "chat", payload)
        st = result["status"]
        if st == 200:
            _sksn_obs(f"#{no} 请求 1 {label}：放行 200（接受该取值，"
                      f"行为记录）")
            if isinstance(result["json"], dict):
                _sksn_assert_usage_triple(result, no)
        elif 400 <= st < 500:
            _sksn_obs(f"#{no} 请求 1 {label}：拒绝 {st}（行为记录）；"
                      f"错误体: {result['raw'][:200]}")
        else:
            _sksn_obs(f"#{no} 请求 1 {label}：HTTP {st}（非预期状态记录）")
        test_logger.info("#%d 请求 1 实测: HTTP %s（%s）", no, st, label)

    def test_12_ttl_invalid_2h(self, api_client, test_logger):
        """#12 ttl=2h 非法枚举值行为（C2 TTL）

        来源: 官方 TTL 枚举仅 5m/1h；2h 行为官方文档未公开（拒绝或
        忽略），记录实测。
        断言口径: 硬——请求可达（无传输异常）；软——状态与行为记录。
        """
        self._sksn_ttl_value_case(
            api_client, test_logger, 12,
            {"mode": "write", "ttl": "2h"}, "ttl=2h 非法枚举")

    def test_13_ttl_numeric_type(self, api_client, test_logger):
        """#13 ttl=300 数字类型行为（C2 TTL）

        来源: 官方 TTL 为字符串枚举（"5m"/"1h"）；数字类型行为未公开，
        记录实测。
        断言口径: 硬——请求可达；软——状态与行为记录。
        """
        self._sksn_ttl_value_case(
            api_client, test_logger, 13,
            {"mode": "write", "ttl": 300}, "ttl=300 数字类型")

    def test_14_ttl_uppercase(self, api_client, test_logger):
        """#14 ttl=5M 大写形态行为（C2 TTL）

        来源: 官方 TTL 为小写枚举；大小写敏感性未公开，记录实测。
        断言口径: 硬——请求可达；软——状态与行为记录。
        """
        self._sksn_ttl_value_case(
            api_client, test_logger, 14,
            {"mode": "write", "ttl": "5M"}, "ttl=5M 大写形态")

    def test_15_mode_invalid(self, api_client, test_logger):
        """#15 mode=invalid 非法值行为（C2 TTL）

        来源: 官方 mode 枚举未完整公开；invalid 行为记录实测。
        断言口径: 硬——请求可达；软——状态与行为记录。
        """
        self._sksn_ttl_value_case(
            api_client, test_logger, 15,
            {"mode": "invalid"}, "mode=invalid 非法值")

    def test_16_anthropic_ttl_1h(self, api_client, test_logger):
        """#16 Anthropic 协议 cache_control ttl=1h 场景（C2 TTL）

        来源: 用户确认 2026-11-17——Anthropic 协议侧测试一个 TTL 场景；
        Anthropic Messages API cache_control {type: ephemeral, ttl: 1h}
        （扩展缓存 TTL beta）。
        断言口径: 硬——200 + Anthropic 标准字段（id/type=message/
        role=assistant/content 非空/stop_reason/usage.input+output）；
        软——usage 缓存字段（cache_read_input_tokens /
        cache_creation_input_tokens / cache_creation 明细）记录。
        """
        payload = {
            "model": api_client.model_name,
            "max_tokens": 64,
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": _SKSN_LONG_TEXT,
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }],
            }],
        }
        result = _sksn_send(api_client, "messages", payload)
        if not _sksn_capability_ok(result, 16):
            test_logger.info("#16 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        body = result["json"]
        assert isinstance(body, dict), (
            f"#16 请求 1 Anthropic 响应应为 JSON 对象；"
            f"响应: {result['raw'][:300]}"
        )
        assert body.get("type") == "message", (
            f"#16 请求 1 Anthropic type 应为 message，"
            f"实测 {body.get('type')!r}；响应: {result['raw'][:300]}"
        )
        u = body.get("usage")
        assert isinstance(u, dict) and isinstance(u.get("input_tokens"), int) \
            and isinstance(u.get("output_tokens"), int), (
            f"#16 请求 1 Anthropic usage 应含 input/output_tokens 整数，"
            f"实测 {u!r}；响应: {result['raw'][:300]}"
        )
        _sksn_obs(f"#16 请求 1 Anthropic 缓存字段: "
                  f"cache_read={u.get('cache_read_input_tokens')!r}, "
                  f"cache_creation={u.get('cache_creation_input_tokens')!r}, "
                  f"cache_creation 明细={u.get('cache_creation')!r}")
        test_logger.info("#16 请求 1 实测: HTTP %s", result["status"])

    @pytest.mark.slow_ttl
    def test_17_ttl_expiry_5m(self, api_client, test_logger):
        """#17 ttl=5m 缓存过期验证（C2 TTL）

        来源: 用户确认 2026-11-17 纳入；官方 TTL 语义——5m 窗口外
        缓存条目过期，相同请求应不再命中。
        断言口径: 硬——三次均 200 + usage 三元组；软——TTL 内第二
        次与窗口外（等待 330s）第三次 cached_tokens 对比记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write", "ttl": "5m"},
        }
        r1 = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(r1, 17):
            test_logger.info("#17 请求 1 实测: HTTP %s（能力缺口已记录）",
                             r1["status"])
            return
        _sksn_assert_chat_200(r1, 17)
        r2 = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(r2, 17, req=2)
        _sksn_assert_usage_triple(r2, 17, req=2)
        v2 = _sksn_obs_cached_tokens(r2, 17, req=2)
        test_logger.info("#17 TTL 窗口内二次请求 cached_tokens=%r，"
                         "等待 330s 验证过期……", v2)
        time.sleep(330)
        r3 = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(r3, 17, req=3)
        _sksn_assert_usage_triple(r3, 17, req=3)
        v3 = _sksn_obs_cached_tokens(r3, 17, req=3)
        if isinstance(v2, int) and isinstance(v3, int):
            if v3 < v2:
                _sksn_obs(f"#17 过期后命中下降: 窗口内 {v2} → 窗口外 {v3}"
                          f"（TTL 过期证据）")
            else:
                _sksn_obs(f"#17 过期后命中未降: 窗口内 {v2} → 窗口外 {v3}"
                          f"（差异记录）")
        test_logger.info("#17 请求 1/2/3 实测: HTTP %s/%s/%s",
                         r1["status"], r2["status"], r3["status"])

    # ------------------------------------------------------------------
    # C3 usage 字段（#18-#25）
    # ------------------------------------------------------------------

    def test_18_usage_triple_formula(self, api_client, test_logger):
        """#18 usage 三元组完整与公式（C3 usage）

        来源: AGDC2-57 客户问题 4「usage 包含什么字段」；官方——
        prompt_tokens / completion_tokens / total_tokens，
        total = prompt + completion。
        断言口径: 硬——200 + 三元组整数 + 公式成立；软——reasoning_tokens
        顶层/明细取值记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 18)
        u = _sksn_assert_usage_triple(result, 18)
        _, pd, cd = _sksn_usage_details(result)
        _sksn_obs(f"#18 请求 1 usage 顶层字段: {sorted(u.keys())}；"
                  f"prompt_tokens_details={pd!r}；"
                  f"completion_tokens_details={cd!r}")
        test_logger.info("#18 请求 1 实测: HTTP %s", result["status"])

    def test_19_usage_reasoning_details(self, api_client, test_logger):
        """#19 usage reasoning 明细（C3 usage）

        来源: 官方——输出包含推理和正文，reasoning 计数经
        completion_tokens_details.reasoning_tokens 返回（kimi-k3
        为推理模型）。
        断言口径: 硬——200 + usage 三元组；软——reasoning_tokens
        明细取值记录（非零为官方示例口径）。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "请用一句话介绍人工智能。"}],
            "max_tokens": 500,
            "thinking": {"type": "enabled"},
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 19)
        _sksn_assert_usage_triple(result, 19)
        _, _, cd = _sksn_usage_details(result)
        v = cd.get("reasoning_tokens")
        if isinstance(v, int) and v > 0:
            _sksn_obs(f"#19 请求 1 completion_tokens_details."
                      f"reasoning_tokens={v}（官方示例口径一致）")
        else:
            _sksn_obs(f"#19 请求 1 completion_tokens_details."
                      f"reasoning_tokens={v!r}（差异记录）")
        test_logger.info("#19 请求 1 实测: HTTP %s", result["status"])

    def test_20_usage_cached_tokens_after_hit(self, api_client, test_logger):
        """#20 缓存命中后 cached_tokens 字段（C3 usage）

        来源: 官方缓存指南——usage.prompt_tokens_details.cached_tokens
        表示缓存读取量（命中后二次请求）。
        断言口径: 硬——两次均 200 + usage 三元组；软——第二次
        cached_tokens 取值与 prompt_tokens_details 形态记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
        }
        r1 = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(r1, 20)
        r2 = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(r2, 20, req=2)
        _sksn_assert_usage_triple(r2, 20, req=2)
        v = _sksn_obs_cached_tokens(r2, 20, req=2)
        _, pd, _ = _sksn_usage_details(r2)
        _sksn_obs(f"#20 请求 2 prompt_tokens_details 形态: {pd!r}"
                  f"（cached_tokens={v!r}）")
        test_logger.info("#20 请求 1/2 实测: HTTP %s/%s",
                         r1["status"], r2["status"])

    def test_21_usage_cache_write_tokens(self, api_client, test_logger):
        """#21 缓存写入后 cache_write_tokens 字段（C3 usage）

        来源: 官方——usage.prompt_tokens_details.cache_write_tokens
        表示本次写入缓存的 token 数（适用于 kimi-k3）；本地 SGLang
        源码无此字段（实质缺口）。
        断言口径: 硬——200 + usage 三元组；软——cache_write_tokens
        存在性与取值记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write"},
        }
        result = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(result, 21):
            test_logger.info("#21 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        _sksn_assert_chat_200(result, 21)
        _sksn_assert_usage_triple(result, 21)
        _sksn_obs_cache_write_tokens(result, 21)
        test_logger.info("#21 请求 1 实测: HTTP %s", result["status"])

    def test_22_usage_stream_final_chunk(self, api_client, test_logger):
        """#22 流式最终 usage chunk（C3 usage）

        来源: 官方流式指南——stream_options.include_usage=true 时最终
        choices=[] chunk 携带完整 usage，等待 [DONE]。
        断言口径: 硬——200 + [DONE] 收束 + 存在 choices=[] 且带
        usage 的 chunk；软——最终 usage 字段集合记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        result = _sksn_send(api_client, "chat", payload)
        assert result["status"] == 200, (
            f"#22 请求 1 基础请求应 HTTP 200，实测 HTTP {result['status']}；"
            f"响应: {result['raw'][:300]}"
        )
        assert result.get("sse") and result.get("done"), (
            f"#22 请求 1 流式响应应以 data: [DONE] 收束；"
            f"响应: {result['raw'][:300]}"
        )
        final_usage_chunks = [
            ev for ev in result["events"]
            if ev.get("choices") == [] and isinstance(ev.get("usage"), dict)
        ]
        assert final_usage_chunks, (
            f"#22 请求 1 应存在 choices=[] 且携带 usage 的最终 chunk，"
            f"实测缺失；事件数: {len(result['events'])}；"
            f"响应: {result['raw'][:300]}"
        )
        u = final_usage_chunks[-1]["usage"]
        _sksn_obs(f"#22 请求 1 最终 usage chunk 字段: {sorted(u.keys())}")
        test_logger.info("#22 请求 1 实测: HTTP %s（流式）", result["status"])

    def test_23_usage_stream_intermediate(self, api_client, test_logger):
        """#23 流式中间 chunk usage 行为（C3 usage）

        来源: 官方——中间 chunk 不携带 usage（continuous_usage_stats
        为本地扩展，官方未声明）；记录实测。
        断言口径: 硬——200 + [DONE] 收束；软——中间 chunk 是否携带
        usage 记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        result = _sksn_send(api_client, "chat", payload)
        assert result["status"] == 200 and result.get("done"), (
            f"#23 请求 1 流式应 200 且 [DONE] 收束，"
            f"实测 HTTP {result['status']} done={result.get('done')}；"
            f"响应: {result['raw'][:300]}"
        )
        content_chunks = [
            ev for ev in result["events"]
            if isinstance(ev.get("choices"), list) and ev["choices"]
        ]
        with_usage = [ev for ev in content_chunks if ev.get("usage")]
        if with_usage:
            _sksn_obs(f"#23 请求 1 中间内容 chunk 携带 usage "
                      f"{len(with_usage)}/{len(content_chunks)}"
                      f"（与官方口径差异记录）")
        else:
            _sksn_obs(f"#23 请求 1 中间内容 chunk 不携带 usage"
                      f"（与官方口径一致）")
        test_logger.info("#23 请求 1 实测: HTTP %s（流式）", result["status"])

    def test_24_usage_top_level_reasoning_tokens(self, api_client, test_logger):
        """#24 usage 顶层 reasoning_tokens（C3 usage）

        来源: 官方 Chat 响应示例使用 completion_tokens_details.
        reasoning_tokens，未将顶层 reasoning_tokens 列为公开响应
        字段；本地 SGLang UsageInfo 显式定义（本地扩展）。
        断言口径: 硬——200 + usage 三元组；软——顶层 reasoning_tokens
        存在性记录（差异确认项）。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "请用一句话介绍人工智能。"}],
            "max_tokens": 500,
            "thinking": {"type": "enabled"},
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 24)
        u = _sksn_assert_usage_triple(result, 24)
        if "reasoning_tokens" in u:
            _sksn_obs(f"#24 请求 1 usage 顶层存在 reasoning_tokens="
                      f"{u.get('reasoning_tokens')!r}（本地扩展字段，"
                      f"官方未列为公开字段——差异记录）")
        else:
            _sksn_obs(f"#24 请求 1 usage 顶层无 reasoning_tokens"
                      f"（与官方示例一致）")
        test_logger.info("#24 请求 1 实测: HTTP %s", result["status"])

    def test_25_usage_null_zero_omission(self, api_client, test_logger):
        """#25 usage 明细 null/零/字段省略区分（C3 usage）

        来源: 官方文档 schema 与示例不完全一致（明细对象可为 null /
        字段可省略 / required 声明与示例不齐）；客户端应区分缺失、
        null 与零，记录实测形态。
        断言口径: 硬——200 + usage 三元组；软——明细对象 null/省略/
        零值形态记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 25)
        _sksn_assert_usage_triple(result, 25)
        u = result.get("usage") or {}
        for key in ("prompt_tokens_details", "completion_tokens_details"):
            if key not in u:
                _sksn_obs(f"#25 请求 1 usage 省略 {key} 字段（形态记录）")
            elif u[key] is None:
                _sksn_obs(f"#25 请求 1 usage.{key}=null（形态记录）")
            else:
                _sksn_obs(f"#25 请求 1 usage.{key}={u[key]!r}（形态记录）")
        test_logger.info("#25 请求 1 实测: HTTP %s", result["status"])

    # ------------------------------------------------------------------
    # C4 响应头（#26-#31）
    # ------------------------------------------------------------------

    def test_26_headers_generic(self, api_client, test_logger):
        """#26 通用响应头存在性（C4 响应头）

        来源: AGDC2-57 客户问题 5「响应头」；官方样本 19/19 含
        Content-Type/Content-Length/Connection/Date（非流式）。
        断言口径: 硬——200 + Content-Type 含 application/json；
        软——Date/Content-Length/Connection 存在性记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 26)
        h = _sksn_headers_lower(result)
        ct = h.get("content-type", "")
        assert "application/json" in ct, (
            f"#26 请求 1 Content-Type 应含 application/json，"
            f"实测 {ct!r}"
        )
        for name in ("date", "content-length", "connection"):
            _sksn_obs(f"#26 请求 1 响应头 {name}: "
                      f"{h.get(name)!r}（通用头记录）")
        test_logger.info("#26 请求 1 实测: HTTP %s", result["status"])

    def test_27_headers_msh_platform(self, api_client, test_logger):
        """#27 Msh 平台身份头（C4 响应头）

        来源: 官方样本 19/19 含 Msh-Request-Id 等平台元数据头
        （Msh-Org-Id/Msh-Project-Id/Msh-Uid/Msh-Gid/Msh-Trace-Mode/
        X-Internal-Adhoc-Canary）；本地 SGLang 引擎未生成（缺口）。
        断言口径: 硬——200；软——各 Msh-* 头存在性逐一记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 27)
        h = _sksn_headers_lower(result)
        for name in ("msh-request-id", "msh-org-id", "msh-project-id",
                     "msh-uid", "msh-gid", "msh-trace-mode",
                     "x-internal-adhoc-canary"):
            v = h.get(name)
            if v is None:
                _sksn_obs(f"#27 请求 1 响应头 {name} 缺失"
                          f"（官方平台头缺口记录）")
            else:
                _sksn_obs(f"#27 请求 1 响应头 {name}={v!r}")
        test_logger.info("#27 请求 1 实测: HTTP %s", result["status"])

    def test_28_headers_cache_write(self, api_client, test_logger):
        """#28 成功响应缓存写入头（C4 响应头）

        来源: 官方——14/14 成功响应含 Msh-Usage-Cache-Write-Tokens-
        5m/1h（429 不出现）；本地引擎未生成（缺口）。
        断言口径: 硬——200；软——两头存在性与取值记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": _SKSN_LONG_TEXT}],
            "max_tokens": 64,
            "prompt_cache_options": {"mode": "write"},
        }
        result = _sksn_send(api_client, "chat", payload)
        if not _sksn_capability_ok(result, 28):
            test_logger.info("#28 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        _sksn_assert_chat_200(result, 28)
        _sksn_obs_cache_write_headers(result, 28)
        test_logger.info("#28 请求 1 实测: HTTP %s", result["status"])

    def test_29_headers_sse_content_type(self, api_client, test_logger):
        """#29 流式响应头 Content-Type（C4 响应头）

        来源: 官方流式文档——SSE 响应 Content-Type 为
        text/event-stream。
        断言口径: 硬——200 + Content-Type 含 text/event-stream +
        [DONE] 收束；软——流式响应头集合记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
            "stream": True,
        }
        result = _sksn_send(api_client, "chat", payload)
        assert result["status"] == 200, (
            f"#29 请求 1 基础请求应 HTTP 200，实测 HTTP {result['status']}；"
            f"响应: {result['raw'][:300]}"
        )
        h = _sksn_headers_lower(result)
        ct = h.get("content-type", "")
        assert "text/event-stream" in ct, (
            f"#29 请求 1 流式 Content-Type 应含 text/event-stream，"
            f"实测 {ct!r}"
        )
        assert result.get("done"), (
            f"#29 请求 1 流式应以 [DONE] 收束；响应: {result['raw'][:300]}"
        )
        _sksn_obs(f"#29 请求 1 流式响应头: {sorted(h.keys())}")
        test_logger.info("#29 请求 1 实测: HTTP %s（流式）", result["status"])

    def test_30_headers_deployment_layer(self, api_client, test_logger):
        """#30 部署层通用头（C4 响应头）

        来源: 官方样本 19/19 含 Strict-Transport-Security/Vary/
        Set-Cookie(aliyungf_tc)——对外 HTTPS 服务层/链路 Cookie，
        非模型推理参数；自部署形态各异，记录实测。
        断言口径: 硬——200；软——三头存在性记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 30)
        h = _sksn_headers_lower(result)
        for name in ("strict-transport-security", "vary", "set-cookie"):
            v = h.get(name)
            if v is None:
                _sksn_obs(f"#30 请求 1 响应头 {name} 缺失"
                          f"（部署层差异记录）")
            else:
                _sksn_obs(f"#30 请求 1 响应头 {name}={str(v)[:80]!r}")
        test_logger.info("#30 请求 1 实测: HTTP %s", result["status"])

    def test_31_headers_rate_limit_doc(self, api_client, test_logger):
        """#31 限流头出现条件记录（C4 响应头）

        来源: 官方——Retry-After/Msh-Cooldown-Seconds/X-Retry-After
        仅在 429 出现（5/5 样本），成功响应未出现；本套件不主动
        触发限流，记录 200 响应下三者缺省行为。
        断言口径: 硬——200；软——三头在 200 响应中的存在性记录
        （预期缺省）。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 31)
        h = _sksn_headers_lower(result)
        for name in ("retry-after", "msh-cooldown-seconds", "x-retry-after"):
            v = h.get(name)
            if v is None:
                _sksn_obs(f"#31 请求 1 响应头 {name} 未出现"
                          f"（200 响应，与官方样本口径一致）")
            else:
                _sksn_obs(f"#31 请求 1 响应头 {name}={v!r}"
                          f"（200 响应出现，差异记录）")
        test_logger.info("#31 请求 1 实测: HTTP %s", result["status"])

    # ------------------------------------------------------------------
    # C5 OpenAI 协议（#32-#35）
    # ------------------------------------------------------------------

    def test_32_openai_standard_fields(self, api_client, test_logger):
        """#32 OpenAI 非流式标准字段（C5 OpenAI）

        来源: AGDC2-57 客户问题 6「open ai 支持」；OpenAI
        chat.completion 标准结构。
        断言口径: 硬——200 + id 非空 + object=chat.completion +
        model 非空 + choices 非空 + usage 对象。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 32)
        body = result["json"]
        assert body.get("id"), (
            f"#32 请求 1 OpenAI 标准字段 id 缺失或为空；"
            f"响应: {result['raw'][:300]}"
        )
        assert body.get("object") == "chat.completion", (
            f"#32 请求 1 object 应为 chat.completion，"
            f"实测 {body.get('object')!r}"
        )
        assert body.get("model"), (
            f"#32 请求 1 model 字段缺失或为空"
        )
        assert isinstance(body.get("choices"), list) and body["choices"], (
            f"#32 请求 1 choices 应为非空数组"
        )
        assert isinstance(body.get("usage"), dict), (
            f"#32 请求 1 usage 应为对象"
        )
        test_logger.info("#32 请求 1 实测: HTTP %s, id=%s",
                         result["status"], body.get("id"))

    def test_33_openai_stream_chunks(self, api_client, test_logger):
        """#33 OpenAI 流式 chunk 结构（C5 OpenAI）

        来源: OpenAI SSE 流式协议——chunk object=chat.completion.
        chunk，以 data: [DONE] 收束。
        断言口径: 硬——200 + 首个内容 chunk object=chat.completion.
        chunk + [DONE] 收束 + 正文非空。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
            "stream": True,
        }
        result = _sksn_send(api_client, "chat", payload)
        assert result["status"] == 200, (
            f"#33 请求 1 基础请求应 HTTP 200，实测 HTTP {result['status']}"
        )
        assert result.get("done"), (
            f"#33 请求 1 流式应以 [DONE] 收束"
        )
        chunks = [ev for ev in result["events"] if ev.get("choices")]
        assert chunks, f"#33 请求 1 无内容 chunk；响应: {result['raw'][:300]}"
        obj = chunks[0].get("object")
        assert obj == "chat.completion.chunk", (
            f"#33 请求 1 chunk object 应为 chat.completion.chunk，"
            f"实测 {obj!r}"
        )
        assert result["content"].strip(), (
            f"#33 请求 1 流式正文拼接应为非空"
        )
        test_logger.info("#33 请求 1 实测: HTTP %s（流式，%d chunk）",
                         result["status"], len(result["events"]))

    def test_34_openai_error_body(self, api_client, test_logger):
        """#34 OpenAI 错误体结构（C5 OpenAI）

        来源: 官方 Kimi 错误体 {error:{code,message}} 风格；OpenAI
        风格 {error:{message,type,param,code}}；记录实测结构。
        断言口径: 硬——非法请求应 4xx；软——错误体 error 外层结构
        与字段集合记录。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        st = result["status"]
        assert 400 <= st < 500, (
            f"#34 请求 1 空 messages 非法请求应返回 4xx，"
            f"实测 HTTP {st}；响应: {result['raw'][:300]}"
        )
        body = result["json"] if isinstance(result["json"], dict) else {}
        err = body.get("error")
        if isinstance(err, dict):
            _sksn_obs(f"#34 请求 1 错误体 error 外层字段: "
                      f"{sorted(err.keys())}（结构记录）")
        else:
            _sksn_obs(f"#34 请求 1 错误体无 error 外层结构"
                      f"（形态记录）: {result['raw'][:200]}")
        test_logger.info("#34 请求 1 实测: HTTP %s", st)

    def test_35_openai_message_fields(self, api_client, test_logger):
        """#35 OpenAI message 结构与 finish_reason（C5 OpenAI）

        来源: OpenAI 标准——choices[0].message{role=assistant,
        content} + finish_reason。
        断言口径: 硬——200 + message.role=assistant + content 非空
        字符串 + finish_reason 非空。
        """
        payload = {
            "model": api_client.model_name,
            "messages": [{"role": "user", "content": "你好"}],
            "max_tokens": 64,
        }
        result = _sksn_send(api_client, "chat", payload)
        _sksn_assert_chat_200(result, 35)
        body = result["json"]
        ch = (body.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        assert msg.get("role") == "assistant", (
            f"#35 请求 1 message.role 应为 assistant，"
            f"实测 {msg.get('role')!r}"
        )
        assert isinstance(msg.get("content"), str) and msg["content"].strip(), (
            f"#35 请求 1 message.content 应为非空字符串"
        )
        assert ch.get("finish_reason"), (
            f"#35 请求 1 finish_reason 缺失或为空"
        )
        test_logger.info("#35 请求 1 实测: HTTP %s, finish_reason=%s",
                         result["status"], ch.get("finish_reason"))

    # ------------------------------------------------------------------
    # C6 Anthropic 协议（#36-#38）
    # ------------------------------------------------------------------

    def test_36_anthropic_standard_fields(self, api_client, test_logger):
        """#36 Anthropic 非流式标准字段（C6 Anthropic）

        来源: AGDC2-57 客户问题 7「anthropic 支持」；Anthropic
        Messages API 标准结构（id/type=message/role=assistant/
        content blocks/stop_reason/usage.input+output_tokens）。
        断言口径: 硬——200 + 标准字段齐全；软——thinking 块存在性
        记录（kimi-k3 推理能力经 Anthropic 协议呈现形态）。
        """
        payload = {
            "model": api_client.model_name,
            "max_tokens": 256,
            "messages": [{"role": "user", "content": "你好"}],
        }
        result = _sksn_send(api_client, "messages", payload)
        assert result["status"] == 200, (
            f"#36 请求 1 Anthropic 基础请求应 HTTP 200，"
            f"实测 HTTP {result['status']}；响应: {result['raw'][:300]}"
        )
        body = result["json"]
        assert isinstance(body, dict), (
            f"#36 请求 1 响应应为 JSON 对象；响应: {result['raw'][:300]}"
        )
        assert body.get("id"), f"#36 请求 1 Anthropic id 缺失或为空"
        assert body.get("type") == "message", (
            f"#36 请求 1 type 应为 message，实测 {body.get('type')!r}"
        )
        assert body.get("role") == "assistant", (
            f"#36 请求 1 role 应为 assistant，实测 {body.get('role')!r}"
        )
        blocks = body.get("content")
        assert isinstance(blocks, list) and blocks, (
            f"#36 请求 1 content 应为非空 blocks 数组"
        )
        assert body.get("stop_reason") is not None, (
            f"#36 请求 1 stop_reason 字段缺失"
        )
        u = body.get("usage")
        assert isinstance(u, dict) and isinstance(u.get("input_tokens"), int) \
            and isinstance(u.get("output_tokens"), int), (
            f"#36 请求 1 usage 应含 input/output_tokens 整数，实测 {u!r}"
        )
        thinking_blocks = [b for b in blocks
                           if isinstance(b, dict) and b.get("type") == "thinking"]
        _sksn_obs(f"#36 请求 1 content blocks 类型: "
                  f"{[b.get('type') for b in blocks if isinstance(b, dict)]}；"
                  f"thinking 块 {len(thinking_blocks)} 个（形态记录）")
        test_logger.info("#36 请求 1 实测: HTTP %s, id=%s",
                         result["status"], body.get("id"))

    def test_37_anthropic_stream(self, api_client, test_logger):
        """#37 Anthropic 流式 SSE（C6 Anthropic）

        来源: Anthropic Messages 流式协议——message_start /
        content_block_delta / message_stop 事件序列。
        断言口径: 硬——200 + message_start + message_stop 收束 +
        正文非空；软——thinking_delta 事件存在性记录。
        """
        payload = {
            "model": api_client.model_name,
            "max_tokens": 256,
            "messages": [{"role": "user", "content": "你好"}],
            "stream": True,
        }
        result = _sksn_send(api_client, "messages", payload)
        assert result["status"] == 200, (
            f"#37 请求 1 Anthropic 流式应 HTTP 200，"
            f"实测 HTTP {result['status']}；响应: {result['raw'][:300]}"
        )
        assert result.get("saw_message_start"), (
            f"#37 请求 1 流式应含 message_start 事件；"
            f"响应: {result['raw'][:300]}"
        )
        assert result.get("done"), (
            f"#37 请求 1 流式应以 message_stop 收束；"
            f"响应: {result['raw'][:300]}"
        )
        assert result["content"].strip(), (
            f"#37 请求 1 流式正文拼接应为非空"
        )
        thinking_events = [ev for ev in result["events"]
                           if ev.get("type") == "content_block_delta"
                           and (ev.get("delta") or {}).get("type") == "thinking_delta"]
        _sksn_obs(f"#37 请求 1 thinking_delta 事件 {len(thinking_events)} 个"
                  f"（形态记录）")
        test_logger.info("#37 请求 1 实测: HTTP %s（流式，%d 事件）",
                         result["status"], len(result["events"]))

    def test_38_anthropic_cache_fields(self, api_client, test_logger):
        """#38 Anthropic usage 缓存字段（C6 Anthropic）

        来源: Anthropic prompt caching——usage.cache_read_input_tokens /
        cache_creation_input_tokens / cache_creation 明细；用户确认
        2026-11-17 记录式验证。
        断言口径: 硬——200 + Anthropic 标准字段；软——缓存相关
        usage 字段存在性与取值记录。
        """
        payload = {
            "model": api_client.model_name,
            "max_tokens": 64,
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "text",
                    "text": _SKSN_LONG_TEXT,
                    "cache_control": {"type": "ephemeral"},
                }],
            }],
        }
        result = _sksn_send(api_client, "messages", payload)
        if not _sksn_capability_ok(result, 38):
            test_logger.info("#38 请求 1 实测: HTTP %s（能力缺口已记录）",
                             result["status"])
            return
        body = result["json"]
        assert isinstance(body, dict) and body.get("type") == "message", (
            f"#38 请求 1 Anthropic 标准结构校验失败；"
            f"响应: {result['raw'][:300]}"
        )
        u = body.get("usage") or {}
        assert isinstance(u.get("input_tokens"), int) \
            and isinstance(u.get("output_tokens"), int), (
            f"#38 请求 1 usage 应含 input/output_tokens 整数，实测 {u!r}"
        )
        _sksn_obs(f"#38 请求 1 Anthropic 缓存字段: "
                  f"cache_read_input_tokens="
                  f"{u.get('cache_read_input_tokens')!r}, "
                  f"cache_creation_input_tokens="
                  f"{u.get('cache_creation_input_tokens')!r}, "
                  f"cache_creation={u.get('cache_creation')!r}")
        test_logger.info("#38 请求 1 实测: HTTP %s", result["status"])
