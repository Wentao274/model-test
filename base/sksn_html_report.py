# -*- coding: utf-8 -*-
"""深空数能 AGDC2-57 sksn 套件 HTML/Markdown 报告生成器。

能力确认/差异记录样式（用户确认 2026-11-17）：协议层硬断言 FAIL
才红；能力层软断言以「观察项」展示支持/缺口/差异事实。报告结构：
7 项问题结论表 + 测试结果统计（含域分组统计）+ 用例结果总览
（全部 38 用例 + 观察项 + 每请求子行）+ 用例明细（断言口径 vs
实测观察，请求/响应折叠）。MD 章节名与通用报告一致，供 Jenkins
邮件正文提取；能力观察清单逐用例列出（7 项问题的答复素材）。

数据源：allure-results + 请求录制记录（sksn_records.json，含
records 与 obs 观察项）+ 用例 docstring 元数据。离线可重生成：
python -m base.sksn_html_report --alluredir <目录> [--records <json>]
[--out-dir <目录>] --model <模型名> --base-url <接入点>
"""

import argparse
import glob
import io
import json
import os
import re
import sys

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

SKSN_MODULE = "tests.test_sksn_agdc2_57"

# 域徽章底色（C1 缓存写入 / C2 TTL / C3 usage / C4 响应头 /
# C5 OpenAI / C6 Anthropic）
DOMAIN_BADGE = {
    "C1 缓存写入": ("b-dom-c1", "C1 缓存写入"),
    "C2 TTL": ("b-dom-c2", "C2 TTL"),
    "C3 usage": ("b-dom-c3", "C3 usage"),
    "C4 响应头": ("b-dom-c4", "C4 响应头"),
    "C5 OpenAI": ("b-dom-c5", "C5 OpenAI"),
    "C6 Anthropic": ("b-dom-c6", "C6 Anthropic"),
}

# 客户 7 项确认事项 → 用例域（结论表行序）
QUESTION_MAP = [
    ("1. 是否支持缓存写入", "C1 缓存写入"),
    ("2. 是否支持 1h 缓存", "C2 TTL"),
    ("3. 是否支持 TTL", "C2 TTL"),
    ("4. usage 包含什么字段", "C3 usage"),
    ("5. 响应头", "C4 响应头"),
    ("6. OpenAI 支持", "C5 OpenAI"),
    ("7. Anthropic 支持", "C6 Anthropic"),
]

_CSS = """
body{font-family:'Segoe UI','Microsoft YaHei',sans-serif;background:#f5f5f4;color:#1c1917;margin:0;padding:24px;}
.wrap{max-width:1280px;margin:0 auto;}
h1{font-size:24px;margin:0 0 4px;}h2{font-size:17px;margin:0 0 10px;border-left:4px solid #78716c;padding-left:8px;}
.sub{color:#57534e;font-size:12px;margin-bottom:16px;line-height:1.7;}
.card{background:#fff;border:1px solid #e7e5e4;border-radius:8px;padding:16px 18px;margin-bottom:18px;}
table{border-collapse:collapse;width:100%;font-size:13px;}
th,td{border:1px solid #e7e5e4;padding:6px 8px;text-align:left;vertical-align:top;}
th{background:#fafaf9;font-weight:600;}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;white-space:nowrap;}
.b-pass{background:#dcfce7;color:#166534;}.b-fail{background:#fee2e2;color:#991b1b;}
.b-err{background:#ffedd5;color:#9a3412;}.b-skip{background:#e0f2fe;color:#075985;}
.b-other{background:#e5e7eb;color:#374151;}
.b-http2{background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;}
.b-http4{background:#fff7ed;color:#c2410c;border:1px solid #fed7aa;}
.b-http5{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;}
.b-dom-c1{background:#ecfccb;color:#3f6212;}.b-dom-c2{background:#fef3c7;color:#92400e;}
.b-dom-c3{background:#cffafe;color:#155e75;}.b-dom-c4{background:#e0e7ff;color:#3730a3;}
.b-dom-c5{background:#dcfce7;color:#166534;}.b-dom-c6{background:#fae8ff;color:#86198f;}
.stat{display:inline-block;text-align:center;padding:8px 16px;margin:4px 10px 4px 0;background:#fafaf9;border:1px solid #e7e5e4;border-radius:8px;min-width:76px;}
.stat .num{font-size:22px;font-weight:700;}.stat .lbl{font-size:12px;color:#57534e;}
.n-pass{color:#166534;}.n-fail{color:#991b1b;}.n-err{color:#9a3412;}
.obs{background:#fffbeb;border-left:3px solid #f59e0b;padding:6px 10px;margin:6px 0;font-size:12px;line-height:1.8;}
.obs li{margin:2px 0;}
.req-row td{background:#fafaf9;font-size:12px;color:#44403c;}
details{margin:4px 0;}summary{cursor:pointer;font-size:12px;color:#57534e;}
pre{background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;overflow-x:auto;max-height:420px;overflow-y:auto;font-size:12px;line-height:1.5;margin:6px 0 14px;white-space:pre-wrap;word-break:break-all;}
.case-row td{vertical-align:middle;}
.small{font-size:12px;color:#57534e;}
"""


def _esc(s: Any) -> str:
    """HTML 转义（全部输出文本必须经过本函数）。"""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _jdump(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        return str(obj)


def _mask_headers_for_display(headers: Any) -> Any:
    """展示前二次脱敏兜底：鉴权头一律打码。"""
    if not isinstance(headers, dict):
        return headers
    out = {}
    for k, v in headers.items():
        lk = str(k).lower()
        if lk in ("authorization", "x-api-key") and v:
            s = str(v)
            out[k] = "****" if len(s) <= 12 else s[:4] + "****" + s[-4:]
        else:
            out[k] = v
    return out


def load_allure_results(alluredir: str) -> Dict[str, dict]:
    """读 allure-results 下 *result.json，过滤 test_sksn 节点。"""
    out: Dict[str, dict] = {}
    for p in sorted(glob.glob(os.path.join(alluredir, "*result.json"))):
        try:
            with io.open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        name = d.get("name") or ""
        nodeid = (d.get("nodeid") or d.get("fullName") or "")
        if "test_sksn_agdc2_57" not in nodeid:
            continue
        func = name.split("[")[0].strip()
        rec = {
            "func": func,
            "nodeid": nodeid or name,
            "status": d.get("status") or "unknown",
            "duration_ms": int((d.get("stop") or 0) - (d.get("start") or 0)),
            "message": "",
        }
        msg = ""
        for k in ("statusTrace", "statusMessage", "message", "trace"):
            v = d.get(k)
            if v:
                msg = str(v)
                break
        rec["message"] = msg
        old = out.get(func)
        if old is None:
            out[func] = rec
        else:
            rank_old = (1 if old["status"] == "failed" else
                        0 if old["status"] == "passed" else 2)
            rank_new = (1 if rec["status"] == "failed" else
                        0 if rec["status"] == "passed" else 2)
            if rank_new > rank_old:
                out[func] = rec
    return out


def load_records(path: str) -> Tuple[List[dict], Dict[str, list]]:
    """读请求录制 JSON（sksn_records.json）。

    兼容两种形态：{"records": [...], "obs": {...}}（现行导出）或
    纯列表 [...]（兼容手工裁剪）。返回 (records, obs)。
    """
    with io.open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        recs = data.get("records") or []
        obs = data.get("obs") or {}
        return (recs if isinstance(recs, list) else [],
                obs if isinstance(obs, dict) else {})
    if isinstance(data, list):
        return data, {}
    return [], {}


def load_docstring_meta() -> Dict[str, dict]:
    """反射解析 sksn 测试类各方法 docstring 元数据（不依赖 pytest）。"""
    meta: Dict[str, dict] = {}
    try:
        mod = __import__(SKSN_MODULE, fromlist=["TestSksnAGDC2_57"])
    except Exception:
        return meta
    cls = getattr(mod, "TestSksnAGDC2_57", None)
    if cls is None:
        return meta
    for func, m in vars(cls).items():
        if not func.startswith("test_"):
            continue
        doc = (m.__doc__ or "").strip()
        if not doc:
            continue
        lines = [ln.strip() for ln in doc.splitlines()]
        first = lines[0] if lines else ""
        # 首行形如「#1 mode=write 基础缓存写入（C1 缓存写入）」
        m1 = re.match(r"^#(\d+)\s+(.+)（([^（）]*)）$", first)
        meta[func] = {
            "no": m1.group(1) if m1 else "",
            "title": m1.group(2) if m1 else first,
            "type": m1.group(3) if m1 else "",
            "source": "",
            "verdict": "",
            "raw_doc": doc,
        }
        for ln in lines[1:]:
            if ln.startswith("来源"):
                meta[func]["source"] = ln.split(":", 1)[-1].strip() if ":" in ln \
                    else ln.split("：", 1)[-1].strip()
            elif ln.startswith("断言口径"):
                meta[func]["verdict"] = ln
    return meta


def load_case_order(meta: Optional[Dict[str, dict]] = None) -> List[str]:
    """按 docstring #N 数字升序取全部 test_* 方法名。"""
    try:
        mod = __import__(SKSN_MODULE, fromlist=["TestSksnAGDC2_57"])
        cls = getattr(mod, "TestSksnAGDC2_57")
        funcs = [n for n, v in vars(cls).items()
                 if n.startswith("test_") and callable(v)]
    except Exception:
        return []
    meta = meta if meta is not None else load_docstring_meta()
    try:
        return sorted(funcs, key=lambda f: int(meta.get(f, {}).get("no") or "0"))
    except Exception:
        return funcs


# ---------------------------------------------------------------------------
# 请求级 通过/失败 推导
# ---------------------------------------------------------------------------

_REQ_RE = re.compile(r"请求\s*(\d+)")


def derive_request_status(case_status: str, message: str,
                          req_count: int) -> List[str]:
    """推导每请求状态：'passed' / 'failed' / 'not_run'。"""
    if req_count <= 0:
        return []
    if case_status == "passed":
        return ["passed"] * req_count
    if case_status in ("skipped",):
        return ["not_run"] * req_count
    m = _REQ_RE.search(message or "")
    if m:
        fail_n = int(m.group(1))
        return (["passed"] * (fail_n - 1) + ["failed"]
                + ["not_run"] * (req_count - fail_n))
    return ["failed"] + ["not_run"] * (req_count - 1)


def _http_badge(status) -> str:
    """HTTP 状态中性徽章（2xx 绿 / 4xx 橙 / 5xx 红 / 其他灰）——
    能力确认套件 4xx 为合法实测行为，不用 pass/fail 语义。"""
    try:
        s = int(status)
    except Exception:
        return '<span class="badge b-other">-</span>'
    if 200 <= s < 300:
        cls = "b-http2"
    elif 400 <= s < 500:
        cls = "b-http4"
    elif s >= 500:
        cls = "b-http5"
    else:
        cls = "b-other"
    return f'<span class="badge {cls}">HTTP {s}</span>'


def _fold(title: str, content: str) -> str:
    return ('<details><summary>' + _esc(title) + '</summary><pre>'
            + _esc(content) + '</pre></details>')


def _badge_for(status: str) -> str:
    return {
        "passed": '<span class="badge b-pass">通过</span>',
        "failed": '<span class="badge b-fail">失败</span>',
        "broken": '<span class="badge b-err">异常</span>',
        "skipped": '<span class="badge b-skip">跳过</span>',
    }.get(status, '<span class="badge b-other">未执行</span>')


def _stat_badge_req(status: str) -> str:
    if status == "passed":
        return '<span class="badge b-pass">通过</span>'
    if status == "failed":
        return '<span class="badge b-fail">失败</span>'
    return '<span class="badge b-other">未执行</span>'


def _dom_badge(dom: str) -> str:
    cls, label = DOMAIN_BADGE.get(dom, ("b-other", dom or "未标记"))
    return f'<span class="badge {cls}">{_esc(label)}</span>'


def _obs_html(items: List[str]) -> str:
    if not items:
        return '<div class="small">（无能力观察记录）</div>'
    lis = "".join("<li>" + _esc(t) + "</li>" for t in items)
    return '<div class="obs"><ul style="margin:0;padding-left:18px;">' \
        + lis + "</ul></div>"


def build_html(allure: Dict[str, dict], records: List[dict],
               obs: Dict[str, list], meta: Dict[str, dict],
               order: List[str], model_name: str, base_url: str,
               chip_name: str = "", engine: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts: List[str] = []
    parts.append(
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\""
        "utf-8\">\n<title>kimi-k3 能力确认报告 - 深空数能 AGDC2-57"
        "</title>\n<style>\n" + _CSS + "\n</style>\n</head>\n<body>\n"
        "<div class=\"wrap\">\n"
        "<h1>&#129514; kimi-k3 能力确认报告（7 项确认事项 · 协议硬断言 "
        "+ 能力观察记录）</h1>\n"
        "<div class=\"sub\">导出时间：" + _esc(now) + " · 工单：深空数能"
        " AGDC2-57 · 用例源：AGDC2-57 分析文档（K3 官方 API 响应头与 "
        "SGLang 差异对比 / K3 模型 usage 字段说明）· 断言口径：协议层"
        "硬断言 FAIL、能力层软断言记录差异 · 密钥已脱敏</div>\n")

    # ---- 任务概要 ----
    parts.append('<div class="card">\n<h2>任务概要</h2>\n<table>\n')
    rows = [
        ("模型服务", model_name or "unknown"),
        ("接入点（BASE_URL）", base_url or "N/A"),
        ("芯片平台", chip_name or "N/A"),
        ("推理框架", engine or "N/A"),
        ("用例总数", str(len(order))),
        ("请求总数", str(len(records))),
        ("协议端点", "POST /chat/completions（OpenAI）；"
                     "POST /anthropic/v1/messages（Anthropic）"),
    ]
    for k, v in rows:
        parts.append("<tr><th style=\"width:160px;\">" + _esc(k)
                     + "</th><td>" + _esc(v) + "</td></tr>\n")
    parts.append("</table>\n</div>\n")

    # ---- 测试结果统计 ----
    n_pass = n_fail = n_err = n_skip = 0
    for f in order:
        st = allure.get(f, {}).get("status", "not_run")
        if st == "passed":
            n_pass += 1
        elif st == "failed":
            n_fail += 1
        elif st == "broken":
            n_err += 1
        elif st == "skipped":
            n_skip += 1
    n_other = len(order) - n_pass - n_fail - n_err - n_skip
    dur_ms = sum(a.get("duration_ms", 0) for a in allure.values())
    avg = int(dur_ms / len(allure)) if allure else 0
    parts.append('<div class="card">\n<h2>测试结果统计</h2>\n'
                 '<div style="padding:6px 0;">\n')
    for num, lbl, cls in ((len(order), "用例总数", ""),
                          (n_pass, "通过", "n-pass"),
                          (n_fail, "失败", "n-fail"),
                          (n_err, "异常", "n-err"),
                          (n_skip + n_other, "跳过/未执行", "")):
        parts.append('<span class="stat %s"><div class="num">%d</div>'
                     '<div class="lbl">%s</div></span>\n'
                     % (cls, num, _esc(lbl)))
    parts.append('<span class="stat"><div class="num">%d</div>'
                 '<div class="lbl">平均耗时(ms)</div></span>\n</div>\n' % avg)

    # 域分组统计
    dom_stat: Dict[str, List[int]] = {}
    for f in order:
        st = allure.get(f, {}).get("status", "not_run")
        dom = meta.get(f, {}).get("type") or "未标记"
        b = dom_stat.setdefault(dom, [0, 0, 0, 0])
        b[0] += 1
        if st == "passed":
            b[1] += 1
        elif st in ("failed", "broken"):
            b[2] += 1
        else:
            b[3] += 1
    parts.append('<table style="margin-top:8px;"><thead><tr><th>用例域'
                 '</th><th>总数</th><th>通过</th><th>失败/异常</th>'
                 '<th>跳过/未执行</th></tr></thead><tbody>\n')
    for dom, b in dom_stat.items():
        parts.append('<tr><td>' + _dom_badge(dom) + "</td><td>%d</td>"
                     '<td><span class="n-pass">%d</span></td>'
                     '<td><span class="n-fail">%d</span></td><td>%d</td>'
                     "</tr>\n" % (b[0], b[1], b[2], b[3]))
    parts.append("</tbody>\n</table>\n</div>\n")

    # ---- 7 项问题结论表 ----
    parts.append('<div class="card">\n<h2>客户 7 项确认事项结论表</h2>\n'
                 '<table>\n<thead><tr><th style="width:200px;">确认事项</th>'
                 '<th style="width:110px;">对应用例域</th>'
                 '<th style="width:150px;">用例（通过/总数）</th>'
                 '<th>能力观察摘要</th></tr></thead>\n<tbody>\n')
    for q, dom in QUESTION_MAP:
        funcs = [f for f in order if meta.get(f, {}).get("type") == dom]
        ok = sum(1 for f in funcs
                 if allure.get(f, {}).get("status") == "passed")
        obs_items: List[str] = []
        for f in funcs:
            for t in (obs.get(f) or [])[:2]:
                obs_items.append(t)
        summary = "<br>".join(_esc(t[:120]) for t in obs_items[:4]) \
            or '<span class="small">（无观察记录）</span>'
        parts.append("<tr><td>" + _esc(q) + "</td><td>" + _dom_badge(dom)
                     + "</td><td>%d/%d</td><td style=\"font-size:12px;\">%s"
                     "</td></tr>\n" % (ok, len(funcs), summary))
    parts.append("</tbody>\n</table>\n</div>\n")

    # ---- 用例结果总览 ----
    parts.append('<div class="card">\n<h2>用例结果总览（全部用例，含能力'
                 '观察与每条请求）</h2>\n<table>\n<thead><tr>'
                 "<th style=\"width:44px;\">ID</th><th>用例名称</th>"
                 "<th style=\"width:96px;\">用例域</th>"
                 "<th style=\"width:64px;\">状态</th>"
                 "<th>能力观察</th>"
                 "<th style=\"width:70px;\">耗时(ms)</th>"
                 "<th>失败信息</th></tr></thead>\n<tbody>\n")
    for func in order:
        a = allure.get(func, {})
        st = a.get("status", "not_run")
        m = meta.get(func, {})
        case_recs = [r for r in records if r.get("test") == func]
        case_obs = obs.get(func) or []
        msg = (a.get("message") or "").strip().splitlines()
        msg0 = msg[0] if msg else ""
        obs_cell = "<br>".join(_esc(t[:150]) for t in case_obs[:3])
        if len(case_obs) > 3:
            obs_cell += "<br><span class=\"small\">…共 %d 条</span>" \
                % len(case_obs)
        parts.append(
            '<tr class="case-row"><td>' + _esc(m.get("no", "")) + "</td><td>"
            + _esc(m.get("title", func)) + "</td><td>"
            + _dom_badge(m.get("type", "")) + "</td><td>"
            + _badge_for(st)
            + "</td><td style=\"font-size:12px;\">" + (obs_cell or "-")
            + "</td><td>%d" % a.get("duration_ms", 0)
            + "</td><td style=\"font-size:12px;\">" + _esc(msg0[:200])
            + "</td></tr>\n")
        for i, r in enumerate(case_recs):
            st_list = derive_request_status(st, a.get("message", ""),
                                            len(case_recs))
            rs = st_list[i] if i < len(st_list) else "not_run"
            parts.append(
                '<tr class="req-row"><td></td><td colspan="3">请求 %d · '
                '%s <span class="small">%s</span></td><td>%s · %s ms'
                '</td><td>%s</td><td></td></tr>\n'
                % (i + 1, _http_badge(r.get("status")),
                   _esc(str(r.get("url", ""))[:80]),
                   _stat_badge_req(rs),
                   int((r.get("elapsed") or 0) * 1000),
                   _esc(str(r.get("kind", "")))))
    parts.append("</tbody>\n</table>\n</div>\n")

    # ---- 用例明细 ----
    parts.append('<div class="card">\n<h2>用例明细（断言口径 vs 实测观察，'
                 '报文全量不截断）</h2>\n')
    for func in order:
        a = allure.get(func, {})
        st = a.get("status", "not_run")
        m = meta.get(func, {})
        case_recs = [r for r in records if r.get("test") == func]
        case_obs = obs.get(func) or []
        parts.append('<h3 style="font-size:15px;margin:14px 0 6px;">'
                     + _esc("#%s %s" % (m.get("no", "?"),
                                        m.get("title", func)))
                     + " " + _badge_for(st) + "</h3>\n")
        parts.append('<table style="margin-bottom:6px;"><tr>'
                     '<th style="width:50%;">断言口径（docstring）</th>'
                     '<th>实测观察（能力层记录）</th></tr><tr><td>')
        doc_lines = []
        if m.get("source"):
            doc_lines.append("来源：" + m["source"])
        if m.get("verdict"):
            doc_lines.append(m["verdict"])
        parts.append('<div class="small" style="line-height:1.8;">'
                     + "<br>".join(_esc(t) for t in doc_lines)
                     + "</div>")
        parts.append("</td><td>" + _obs_html(case_obs) + "</td></tr></table>\n")
        for i, r in enumerate(case_recs):
            parts.append('<div class="small" style="margin:8px 0 2px;">'
                         "<b>请求 %d</b> · %s · %s · %d ms</div>\n"
                         % (i + 1, _http_badge(r.get("status")),
                            _esc(str(r.get("url", ""))),
                            int((r.get("elapsed") or 0) * 1000)))
            parts.append(_fold("请求头", _jdump(
                _mask_headers_for_display(r.get("req_headers")))))
            parts.append(_fold("请求体", _jdump(r.get("req_body"))))
            parts.append(_fold("响应头", _jdump(r.get("resp_headers"))))
            body = r.get("resp_body")
            if isinstance(body, (dict, list)):
                body_txt = _jdump(body)
            else:
                body_txt = str(body if body is not None else "")
            parts.append(_fold("响应体", body_txt))
            if r.get("error"):
                parts.append('<div class="obs">发送异常：'
                             + _esc(str(r["error"])) + "</div>\n")
    parts.append("</div>\n</div>\n</body>\n</html>\n")
    return "".join(parts)


def build_markdown(allure: Dict[str, dict], records: List[dict],
                   obs: Dict[str, list], meta: Dict[str, dict],
                   order: List[str], model_name: str, base_url: str,
                   chip_name: str = "", engine: str = "") -> str:
    """汇总 MD（章节名与通用报告一致，供 Jenkins 邮件正文提取）。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = []
    lines.append("# kimi-k3 能力确认测试报告（深空数能 AGDC2-57）")
    lines.append("")
    lines.append(f"> 生成时间：{now}")
    lines.append(f"> 模型：{model_name or 'unknown'}")
    lines.append(f"> 接入点：{base_url or 'N/A'}")
    lines.append(f"> 芯片平台：{chip_name or 'N/A'}")
    lines.append(f"> 推理框架：{engine or 'N/A'}")
    lines.append(f"> 请求总数：{len(records)}")
    lines.append("> 用例源：AGDC2-57 分析文档（响应头差异对比 / usage 字段说明）")
    lines.append("> 断言口径：协议层硬断言 FAIL、能力层软断言记录差异（PASS）")
    lines.append("")

    n_pass = n_fail = n_err = n_skip = 0
    for f in order:
        st = allure.get(f, {}).get("status", "not_run")
        if st == "passed":
            n_pass += 1
        elif st == "failed":
            n_fail += 1
        elif st == "broken":
            n_err += 1
        elif st == "skipped":
            n_skip += 1
    n_other = len(order) - n_pass - n_fail - n_err - n_skip

    lines.append("## 统计汇总")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    lines.append(f"| 用例总数 | {len(order)} |")
    lines.append(f"| 通过 | {n_pass} |")
    lines.append(f"| 失败 | {n_fail} |")
    lines.append(f"| 异常 | {n_err} |")
    lines.append(f"| 跳过/未执行 | {n_skip + n_other} |")
    lines.append(f"| 请求总数 | {len(records)} |")
    lines.append("")

    lines.append("## 分类统计")
    lines.append("")
    lines.append("| 用例域 | 通过 | 失败 | 异常 | 跳过/未执行 | 合计 |")
    lines.append("|---|---|---|---|---|---|")
    dom_stat: Dict[str, List[int]] = {}
    for f in order:
        st = allure.get(f, {}).get("status", "not_run")
        k = (meta.get(f, {}).get("type") or "unknown")
        bucket = dom_stat.setdefault(k, [0, 0, 0, 0, 0])
        bucket[4] += 1
        if st == "passed":
            bucket[0] += 1
        elif st == "failed":
            bucket[1] += 1
        elif st == "broken":
            bucket[2] += 1
        else:
            bucket[3] += 1
    for k, b in dom_stat.items():
        lines.append(f"| {k} | {b[0]} | {b[1]} | {b[2]} | {b[3]} | {b[4]} |")
    lines.append("")

    lines.append("## 测试结论")
    lines.append("")
    if n_fail == 0 and n_err == 0:
        if n_pass == len(order):
            lines.append("**结论：**全部用例通过——协议层硬断言全部达标；"
                          "能力层观察项见下「能力观察清单」（支持/缺口/差异"
                          "均已记录，供 7 项确认事项答复）。")
        else:
            lines.append("**结论：**已执行用例全部通过（协议层硬断言达标），"
                          "部分用例未执行/跳过（如 -m 排除 slow_ttl）；能力层"
                          "观察项见下「能力观察清单」。")
    else:
        lines.append("**结论：**存在协议层未通过用例（协议合规性破坏，"
                      "非能力缺口——能力缺口仅记录不判失败）：")
        for f in order:
            a = allure.get(f, {})
            st = a.get("status")
            if st in ("failed", "broken"):
                m = meta.get(f, {})
                msg0 = (a.get("message") or "").strip().splitlines()
                msg0 = msg0[0] if msg0 else ""
                lines.append(f"- {'❌' if st == 'failed' else '⚠️'} "
                             f"{m.get('no', '')} {m.get('title', f)}"
                             f"（协议层失败）：{msg0[:200]}")
    lines.append("")

    lines.append("## 能力观察清单")
    lines.append("")
    lines.append("（能力层软断言实测记录——7 项确认事项答复素材；"
                  "缺口/差异不代表用例失败）")
    lines.append("")
    for f in order:
        m = meta.get(f, {})
        case_obs = obs.get(f) or []
        st = allure.get(f, {}).get("status", "not_run")
        mark = {"passed": "✅", "failed": "❌", "broken": "⚠️"}.get(st, "➖")
        lines.append(f"### {mark} #{m.get('no', '?')} "
                     f"{m.get('title', f)}（{m.get('type', '')}）")
        if case_obs:
            for t in case_obs:
                lines.append(f"- {t}")
        else:
            lines.append("- （无观察记录）")
        lines.append("")

    skip_cases = [f for f in order
                  if allure.get(f, {}).get("status") == "skipped"]
    if skip_cases:
        lines.append("## 跳过用例说明")
        lines.append("")
        for f in skip_cases:
            m = meta.get(f, {})
            lines.append(f"- #{m.get('no', '?')} {m.get('title', f)}")
        lines.append("")
    return "\n".join(lines)


def generate_reports(alluredir: str, records_path: str,
                     out_dir: str, model_name: str = "",
                     base_url: str = "", chip_name: str = "",
                     engine: str = "") -> Tuple[str, str]:
    """生成 HTML + MD，返回 (html_path, md_path)。"""
    allure = load_allure_results(alluredir)
    records, obs = load_records(records_path) if records_path else ([], {})
    meta = load_docstring_meta()
    order = load_case_order(meta)
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = os.path.join(out_dir, f"sksn_test_report_{ts}.html")
    md_path = os.path.join(out_dir, f"sksn_summary_{ts}.md")
    html = build_html(allure, records, obs, meta, order,
                      model_name, base_url, chip_name, engine)
    with io.open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    md = build_markdown(allure, records, obs, meta, order,
                        model_name, base_url, chip_name, engine)
    with io.open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    return html_path, md_path


def _find_records_default(alluredir: str) -> str:
    """默认录制记录路径：allure-results 同级 sksn_records.json。"""
    cand = os.path.join(os.path.dirname(os.path.abspath(alluredir)),
                        "sksn_records.json")
    return cand if os.path.exists(cand) else ""


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="深空数能 AGDC2-57 sksn 套件 HTML/Markdown 报告生成器"
                    "（能力确认/差异记录样式，离线可重生成）")
    p.add_argument("--alluredir", required=True,
                   help="allure-results 目录（含 *result.json）")
    p.add_argument("--records", default=None,
                   help="请求录制记录 JSON（默认 allure-results 同级 "
                        "sksn_records.json）")
    p.add_argument("--out-dir", default=".",
                   help="输出目录（默认当前目录）")
    p.add_argument("--model", default="", help="模型服务名")
    p.add_argument("--base-url", default="", help="接入点 BASE_URL")
    p.add_argument("--chip", default="", help="芯片平台")
    p.add_argument("--engine", default="", help="推理框架")
    args = p.parse_args(argv)
    records = args.records or _find_records_default(args.alluredir)
    html_path, md_path = generate_reports(
        args.alluredir, records, args.out_dir,
        model_name=args.model, base_url=args.base_url,
        chip_name=args.chip, engine=args.engine)
    print(f"HTML: {html_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
