# -*- coding: utf-8 -*-
"""浙江讯盟 Z 套件（test_zjxm_agdc2_61）专用 HTML/Markdown 报告生成器。

对比样式（用户指定 2026-11-16）：类似九章 glm-5.3 功能对比报告——
stone 主题、卡片分节、每用例「智谱官方预期 vs 实测」两侧对比块。

数据源三合一（离线可重生成）：
1. allure-results 目录（*result.json，过滤 test_zjxm 节点）——用例
   状态/时长/失败消息；
2. 请求录制记录 JSON（tests/test_zjxm_agdc2_61._ZJXM_RECORDER 会话
   末导出，conftest 写入 allure-results 同级 zjxm_records.json）——
   每请求 URL/kind/请求头（鉴权打码）/请求体/状态码/耗时/响应头/
   响应体全文（SSE 行 join）；
3. 用例 docstring 元数据（tests/test_zjxm_agdc2_61 反射解析）——
   首行「#N 用例名（严重级）」、来源/官方基准/断言口径行。

输出：
- HTML：任务概要 / 测试结果统计（含严重级统计）/ 用例结果总览
  （全部用例+每请求子行）/ 用例明细（官方基准 vs 实测两侧对比，
  断言结果 + 请求/响应报文折叠，全部 HTML 转义）；
- Markdown 汇总：## 统计汇总 / ## 分类统计 / ## 测试结论 /
  ## 跳过用例说明（供 Jenkins 邮件正文提取，章节名与通用报告一致）。

请求级 通过/失败 推导：用例 PASS -> 全部请求通过；FAIL/BROKEN ->
失败消息中「请求 N」定位失败请求，之前的通过、之后的未执行。

CLI 离线重生成：
    python -m base.zjxm_html_report --alluredir <dir> [--records <json>] \
        [--out-dir <dir>] [--model <name>] [--base-url <url>]

用例排序：按 docstring 首行 #N 数字升序（与九章报告用例顺序一致，
测试类内按功能分组定义不影响报告顺序）。
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

ZJXM_MODULE = "tests.test_zjxm_agdc2_61"

STATUS_LABEL = {
    "passed": "通过",
    "failed": "失败",
    "broken": "异常",
    "skipped": "跳过",
}

# 严重级徽章底色（九章报告口径：优先整改红 / 整改橙 / 建议整改黄 /
# 差异确认蓝 / 待确认灰 / 官方异常紫——20261116 复测报告补入的
# 官方基线异常守护用例）
SEVERITY_BADGE = {
    "优先整改": ("b-sev-p0", "优先整改"),
    "整改": ("b-sev-p1", "整改"),
    "建议整改": ("b-sev-p2", "建议整改"),
    "差异确认": ("b-sev-diff", "差异确认"),
    "待确认": ("b-sev-na", "待确认"),
    "官方异常": ("b-sev-off", "官方异常"),
}


def _esc(s: Any) -> str:
    """HTML 转义（全部输出文本必须经过本函数）。"""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _jdump(obj: Any) -> str:
    """dict/list -> pretty JSON 文本；其他原样字符串。"""
    if obj is None:
        return ""
    if isinstance(obj, (dict, list)):
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            return str(obj)
    return str(obj)


def _mask_headers_for_display(headers: Any) -> Any:
    """渲染兜底脱敏：Authorization / x-api-key 打码（防录制层遗漏）。

    已打码值（含 ****）原样保留。
    """
    if not isinstance(headers, dict):
        return headers
    out = {}
    for k, v in headers.items():
        lk = str(k).lower()
        if lk in ("authorization", "x-api-key") and v:
            s = str(v)
            out[k] = s if "****" in s else (
                "****" if len(s) <= 12 else s[:4] + "****" + s[-4:])
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# 数据读取
# ---------------------------------------------------------------------------

def load_allure_results(alluredir: str) -> Dict[str, dict]:
    """读 allure-results 下 *result.json，过滤 test_zjxm 节点。

    Returns: {test_func_name: {...}}（name 去重取 failed 优先）
    """
    out: Dict[str, dict] = {}
    for p in sorted(glob.glob(os.path.join(alluredir, "*result.json"))):
        try:
            with io.open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        name = d.get("name") or ""
        nodeid = (d.get("nodeid") or d.get("fullName") or "")
        if "test_zjxm_agdc2_61" not in nodeid:
            continue
        func = name.split("[")[0].strip()
        rec = {
            "func": func,
            "nodeid": nodeid or name,
            "status": d.get("status") or "unknown",
            "duration_ms": int((d.get("stop") or 0) - (d.get("start") or 0)),
            "message": "",
        }
        # 失败消息（exception/message 字段）
        msg = ""
        for k in ("statusTrace", "statusMessage", "message", "trace"):
            v = d.get(k)
            if v:
                msg = str(v)
                break
        rec["message"] = msg
        # 同一用例多阶段结果（setup/call/teardown 各一份 json）——call
        # 阶段优先，其后 failed 优先
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


def load_records(path: str) -> List[dict]:
    """读请求录制 JSON（_ZJXM_RECORDER 导出）。"""
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_docstring_meta() -> Dict[str, dict]:
    """反射解析 zjxm 测试类各方法 docstring 元数据（不依赖 pytest）。"""
    meta: Dict[str, dict] = {}
    try:
        mod = __import__(ZJXM_MODULE, fromlist=["TestZjxmAGDC2_61"])
    except Exception:
        return meta
    cls = getattr(mod, "TestZjxmAGDC2_61", None)
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
        # 首行形如「#1 CUS-001 user.content 传 null，应 400（优先整改）」；
        # 末尾无嵌套括号组作为严重级
        m1 = re.match(r"^#(\d+)\s+(.+)（([^（）]*)）$", first)
        meta[func] = {
            "no": m1.group(1) if m1 else "",
            "title": m1.group(2) if m1 else first,
            "type": m1.group(3) if m1 else "",
            "source": "",
            "official": [],
            "verdict": "",
            "raw_doc": doc,
        }
        for ln in lines[1:]:
            if ln.startswith("来源"):
                meta[func]["source"] = ln.split(":", 1)[-1].strip() if ":" in ln \
                    else ln.split("：", 1)[-1].strip()
            elif ln.startswith("官方基准"):
                meta[func]["official"].append(ln)
            elif ln.startswith("断言口径"):
                meta[func]["verdict"] = ln
    return meta


def load_case_order(meta: Optional[Dict[str, dict]] = None) -> List[str]:
    """按 docstring #N 数字升序取全部 test_* 方法名（对齐报告用例顺序）。"""
    try:
        mod = __import__(ZJXM_MODULE, fromlist=["TestZjxmAGDC2_61"])
        cls = getattr(mod, "TestZjxmAGDC2_61")
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
    """推导每请求状态：'passed' / 'failed' / 'not_run'。

    - PASSED -> 全部 passed；
    - FAILED/BROKEN -> 失败消息 regex「请求 N」定位失败请求 N（首个
      命中），N 之前的 passed、N 及之后的 not_run（未发送=未执行）；
      无命中（发送异常/collect 级失败）则首请求 failed，其余 not_run。
    - SKIPPED -> 全部 not_run。
    """
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


# ---------------------------------------------------------------------------
# HTML 生成（九章对比报告风格：stone 主题 + 官方/实测两侧对比）
# ---------------------------------------------------------------------------

_BADGE_PASS = '<span class="badge b-pass">通过</span>'
_BADGE_FAIL = '<span class="badge b-fail">失败</span>'
_BADGE_ERR = '<span class="badge b-err">异常</span>'
_BADGE_SKIP = '<span class="badge b-other">跳过</span>'
_BADGE_NOTRUN = '<span class="badge b-other">未执行</span>'


def _http_badge(status) -> str:
    """中性 HTTP 状态徽章（仅呈现状态码，不代表通过/失败——
    Z 套件 41 用例官方基准即为 4xx，不得用判定色渲染）。"""
    try:
        s = int(status)
    except Exception:
        s = 0
    if 200 <= s < 300:
        return '<span class="badge b-http2">HTTP %d</span>' % s
    if 400 <= s < 500:
        return '<span class="badge b-http4">HTTP %d</span>' % s
    if s >= 500:
        return '<span class="badge b-http5">HTTP %d</span>' % s
    return '<span class="badge b-other">HTTP %s</span>' % _esc(
        "—" if status in (None, "") else str(status))

_CSS = """body{font-family:'Microsoft YaHei','PingFang SC',Arial,sans-serif;margin:0;background:#fafaf9;color:#333;font-size:14px;}
.wrap{max-width:1200px;margin:0 auto;padding:24px 16px 60px;}
h1{font-size:22px;margin:0 0 4px;}
.sub{color:#888;font-size:12px;margin-bottom:18px;}
.card{background:#fff;border-radius:8px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:18px 20px;margin-bottom:18px;}
.card h2{font-size:16px;margin:0 0 12px;border-left:4px solid #2563eb;padding-left:8px;}
table{border-collapse:collapse;width:100%;font-size:13px;}
th,td{border:1px solid #e7e5e4;padding:6px 8px;text-align:left;word-break:break-all;vertical-align:top;}
th{background:#f5f5f4;font-weight:600;white-space:nowrap;}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;white-space:nowrap;}
.b-pass{background:#dcfce7;color:#166534;}
.b-fail{background:#fee2e2;color:#991b1b;}
.b-err{background:#fef3c7;color:#92400e;}
.b-other{background:#e5e7eb;color:#374151;}
.b-http2{background:#ecfdf5;color:#047857;}
.b-http4{background:#fff7ed;color:#c2410c;}
.b-http5{background:#fff1f2;color:#be123c;}
.b-reqpass{background:#dbeafe;color:#1e40af;}
.b-sev-p0{background:#fee2e2;color:#991b1b;}
.b-sev-p1{background:#ffedd5;color:#9a3412;}
.b-sev-p2{background:#fef9c3;color:#854d0e;}
.b-sev-diff{background:#dbeafe;color:#1e40af;}
.b-sev-na{background:#e5e7eb;color:#374151;}
.b-sev-off{background:#ede9fe;color:#5b21b6;}
.stat{display:inline-block;margin-right:22px;text-align:center;}
.stat .num{font-size:24px;font-weight:700;}
.stat .lbl{font-size:12px;color:#888;}
.n-pass{color:#16a34a;} .n-fail{color:#dc2626;} .n-err{color:#d97706;}
pre{background:#0f172a;color:#e2e8f0;padding:12px;border-radius:6px;overflow-x:auto;max-height:420px;overflow-y:auto;font-size:12px;line-height:1.5;margin:6px 0 14px;white-space:pre-wrap;word-break:break-all;}
.sec-title{font-weight:700;margin:14px 0 4px;font-size:13px;color:#555;}
tr.case-row td{background:#f8fafc;font-weight:600;}
tr.sub-row td{background:#fff;padding-left:26px;}
.sub-name{color:#1e40af;margin-right:6px;}
.sub-err{color:#b91c1c;font-size:12px;margin-left:4px;}
details.fold{margin:6px 0 10px;border:1px solid #e7e5e4;border-radius:6px;overflow:hidden;background:#fff;}
details.fold>summary{cursor:pointer;list-style:none;padding:7px 12px;background:#f5f5f4;font-size:13px;font-weight:600;color:#44403c;user-select:none;}
details.fold>summary::-webkit-details-marker{display:none;}
details.fold>summary::before{content:'\\25B6 ';font-size:10px;color:#78716c;}
details.fold[open]>summary::before{content:'\\25BC ';}
details.fold>summary:hover{background:#e7e5e4;}
details.fold>pre{margin:0;border-radius:0;}
.toolbar{margin-bottom:10px;}
.toolbar button{cursor:pointer;border:1px solid #cbd5e1;background:#fff;border-radius:6px;padding:4px 12px;font-size:12px;color:#334155;margin-right:8px;}
.toolbar button:hover{background:#f1f5f9;}
.case-block{border:1px solid #e7e5e4;border-radius:8px;margin-bottom:20px;overflow:hidden;background:#fff;}
.case-head{padding:10px 14px;background:#fafaf9;border-bottom:1px solid #e7e5e4;display:flex;flex-wrap:wrap;gap:10px;align-items:center;}
.case-body{padding:14px;}
.kv{color:#888;font-size:12px;}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:8px 0 14px;}
.side{border:1px solid #e7e5e4;border-radius:8px;padding:10px 12px;background:#fafaf9;min-width:0;}
.side h4{margin:0 0 8px;font-size:13px;border-bottom:1px solid #e7e5e4;padding-bottom:6px;}
.side .off-line{font-size:12px;color:#44403c;margin:4px 0;line-height:1.6;word-break:break-all;}
@media (max-width:900px){.grid{grid-template-columns:1fr;}}
@media print { body{background:#fff;} .card{box-shadow:none;border:1px solid #ddd;} }"""

_JS = """function toggleAllFolds(open){document.querySelectorAll('details.fold').forEach(function(d){d.open=open;});}"""


def _fold(title: str, content: str) -> str:
    body = _esc(content)
    return ('<details class="fold"><summary>' + _esc(title)
            + '</summary><pre>' + body + '</pre></details>')


def _badge_for(status: str) -> str:
    return {
        "passed": _BADGE_PASS,
        "failed": _BADGE_FAIL,
        "broken": _BADGE_ERR,
        "skipped": _BADGE_SKIP,
    }.get(status, _BADGE_NOTRUN)


def _stat_badge_req(status: str) -> str:
    if status == "passed":
        return '<span class="badge b-pass">通过</span>'
    if status == "failed":
        return '<span class="badge b-fail">失败</span>'
    return '<span class="badge b-other">未执行</span>'


def _sev_badge(sev: str) -> str:
    cls, label = SEVERITY_BADGE.get(sev, ("b-sev-na", sev or "未标记"))
    return f'<span class="badge {cls}">{_esc(label)}</span>'


def _official_summary(meta: dict) -> str:
    """左侧官方基准一句话（首条 官方基准 行压缩）。"""
    lines = meta.get("official") or []
    if not lines:
        return ""
    txt = lines[0]
    txt = txt.split("：", 1)[-1] if txt.startswith("官方基准：") else txt
    txt = txt.split(":", 1)[-1] if txt.startswith("官方基准:") else txt
    return txt[:200]


def build_html(allure: Dict[str, dict], records: List[dict],
               meta: Dict[str, dict], order: List[str],
               model_name: str, base_url: str,
               chip_name: str = "", engine: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts: List[str] = []
    parts.append(
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\""
        "utf-8\">\n<title>GLM-5.3 功能对比测试报告 - 浙江讯盟 AGDC2-61"
        "</title>\n<style>\n"
        + _CSS + "\n</style>\n</head>\n<body>\n<div class=\"wrap\">\n"
        "<h1>&#129514; GLM-5.3 功能对比测试报告（智谱官方预期 vs 被测平台"
        "实测）</h1>\n"
        "<div class=\"sub\">导出时间：" + _esc(now) + " · 工单：浙江讯盟"
        " AGDC2-61 · 用例源：九章 glm-5.3 功能对比报告 20261110（42 失败"
        "场景复现）+ 九章新 url 复测报告 20261116（3 条官方基线异常守护，"
        "共 45 用例） · 预期基准：智谱官方 run 20261028_191525 / Open "
        "Responses 规范 / 九章复测基线（官方异常条目） · 数据源："
        "allure-results + 请求录制记录 + 用例元数据 · 密钥已脱敏</div>\n")

    # ---- 任务概要 ----
    total_req = len(records)
    parts.append('<div class="card">\n<h2>任务概要</h2>\n<table>\n')
    rows = [
        ("模型服务", model_name or "unknown"),
        ("接入点（BASE_URL）", base_url or "N/A"),
        ("芯片平台", chip_name or "N/A"),
        ("推理框架", engine or "N/A"),
        ("用例总数", str(len(order))),
        ("请求总数", str(total_req)),
        ("预期基准", "智谱官方行为（报告智谱官方侧实测 + Open Responses "
                     "规范口径）"),
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
                 '<div class="lbl">平均耗时(ms)</div></span>\n</div>\n')

    # 严重级统计（九章报告「主要问题类别」口径）
    sev_stat: Dict[str, List[int]] = {}
    for f in order:
        st = allure.get(f, {}).get("status", "not_run")
        sev = meta.get(f, {}).get("type") or "未标记"
        b = sev_stat.setdefault(sev, [0, 0, 0, 0, 0])
        b[0] += 1
        if st == "passed":
            b[1] += 1
        elif st in ("failed", "broken"):
            b[2] += 1
        else:
            b[3] += 1
    parts.append('<table style="margin-top:8px;"><thead><tr><th>严重级'
                 '</th><th>总数</th><th>通过</th><th>失败/异常</th>'
                 '<th>跳过/未执行</th></tr></thead><tbody>\n')
    for sev, b in sev_stat.items():
        parts.append('<tr><td>' + _sev_badge(sev) + "</td><td>%d</td>"
                     '<td><span class="n-pass">%d</span></td>'
                     '<td><span class="n-fail">%d</span></td><td>%d</td>'
                     "</tr>\n" % (b[0], b[1], b[2], b[3]))
    parts.append("</tbody>\n</table>\n</div>\n")

    # ---- 用例结果总览（全部用例 + 官方基准列 + 每请求子行） ----
    parts.append('<div class="card">\n<h2>用例结果总览（全部用例，含官方'
                 '基准与每条请求）</h2>\n<table>\n<thead><tr>'
                 "<th style=\"width:44px;\">ID</th><th>用例名称</th>"
                 "<th style=\"width:82px;\">严重级</th>"
                 "<th style=\"width:64px;\">状态</th>"
                 "<th>官方基准（预期）</th>"
                 "<th style=\"width:104px;\">请求(通过/失败/未执行)</th>"
                 "<th style=\"width:70px;\">耗时(ms)</th>"
                 "<th>失败信息</th></tr></thead>\n<tbody>\n")
    for func in order:
        a = allure.get(func, {})
        st = a.get("status", "not_run")
        m = meta.get(func, {})
        case_recs = [r for r in records if r.get("test") == func]
        st_list = derive_request_status(
            st, a.get("message", ""), len(case_recs))
        p_cnt = st_list.count("passed")
        f_cnt = st_list.count("failed")
        nr_cnt = st_list.count("not_run")
        msg = (a.get("message") or "").strip().splitlines()
        msg0 = msg[0] if msg else ""
        parts.append(
            '<tr class="case-row"><td>' + _esc(m.get("no", "")) + "</td><td>"
            + _esc(m.get("title", func)) + "</td><td>"
            + _sev_badge(m.get("type", "")) + "</td><td>"
            + _badge_for(st)
            + "</td><td style=\"font-size:12px;color:#44403c;\">"
            + _esc(_official_summary(m)) + "</td><td>%d (<span class=\"n-pass"
            "\">%d</span>/<span class=\"n-fail\">%d</span>/%d)</td><td>%d"
            "</td><td>" % (len(st_list), p_cnt, f_cnt, nr_cnt,
                           a.get("duration_ms", 0))
            + _esc(msg0[:300]) + "</td></tr>\n")
        for i, r in enumerate(case_recs):
            rs = st_list[i] if i < len(st_list) else "not_run"
            err_txt = ""
            if rs == "failed" and a.get("message"):
                err_txt = ('<span class="sub-err">'
                           + _esc(msg0[:200]) + "</span>")
            parts.append(
                '<tr class="sub-row"><td></td><td colspan="7"><span '
                'class="sub-name">&#8627; 请求 %d</span> %s <span '
                'class="badge b-reqpass">%s</span> %s <span class="kv">'
                "耗时 %.0f ms</span> %s</td></tr>\n"
                % (i + 1, _stat_badge_req(rs),
                   _esc((r.get("kind") or "").upper()),
                   _http_badge(r.get("status")),
                   float(r.get("elapsed") or 0) * 1000, err_txt))
    parts.append("</tbody>\n</table>\n</div>\n")

    # ---- 用例明细（官方基准 vs 实测，两侧对比） ----
    parts.append('<div class="card">\n<h2>用例明细（智谱官方预期 vs 实测'
                 '，断言结果 + 请求/响应报文）</h2>\n'
                 '<div class="toolbar"><button type="button" onclick='
                 '"toggleAllFolds(true)">全部展开报文</button>'
                 '<button type="button" onclick="toggleAllFolds(false)">'
                 '全部折叠报文</button><span class="kv">（报文默认折叠，'
                 "点击标题展开）</span></div>\n")
    for func in order:
        a = allure.get(func, {})
        st = a.get("status", "not_run")
        m = meta.get(func, {})
        case_recs = [r for r in records if r.get("test") == func]
        st_list = derive_request_status(
            st, a.get("message", ""), len(case_recs))
        parts.append('<div class="case-block">\n<div class="case-head">'
                     "<strong>#" + _esc(m.get("no", "")) + " "
                     + _esc(m.get("title", func)) + "</strong>"
                     + _sev_badge(m.get("type", ""))
                     + _badge_for(st)
                     + '<span class="kv">耗时 %d ms</span></div>\n'
                     '<div class="case-body">\n' % a.get("duration_ms", 0))
        parts.append('<div class="sec-title">&#9997; 用例说明</div>\n')
        doc = m.get("raw_doc", "")
        parts.append(_fold("用例 docstring（点击展开）", doc))
        parts.append('<div class="grid">\n')
        # 左侧：智谱官方预期
        parts.append('<div class="side">\n<h4>&#127919; 智谱官方预期（基准'
                     '）</h4>\n')
        for ln in (m.get("official") or []):
            parts.append('<div class="off-line">' + _esc(ln) + "</div>\n")
        if m.get("verdict"):
            parts.append('<div class="off-line" style="margin-top:6px;">'
                         + _esc(m["verdict"]) + "</div>\n")
        if not (m.get("official") or m.get("verdict")):
            parts.append('<div class="kv">（官方基准见用例 docstring）'
                         "</div>\n")
        parts.append("</div>\n")
        # 右侧：实测（断言结果 + 报文）
        parts.append('<div class="side">\n<h4>&#128228; 实测（被测平台）'
                     "</h4>\n")
        if st == "passed":
            parts.append('<div class="kv">用例通过——实测行为符合官方/'
                         "规范基准。</div>\n")
        else:
            parts.append('<pre>' + _esc(a.get("message")
                         or "(无失败消息)") + "</pre>\n")
        for i, r in enumerate(case_recs):
            rs = st_list[i] if i < len(st_list) else "not_run"
            parts.append(
                '<div style="border:1px dashed #d1d5db;border-radius:6px;'
                'padding:10px 12px;margin:10px 0;background:#fff;">\n'
                '<div style="font-weight:700;font-size:13px;margin-bottom:'
                '6px;color:#1e40af;">请求 %d（%s）</div>\n'
                '<div style="margin-bottom:6px;">%s <code style="word-'
                'break:break-all;font-size:12px;">%s</code> %s %s <span '
                'class="kv">耗时 %.0f ms</span></div>\n'
                % (i + 1, _esc(r.get("kind") or ""),
                   '<span class="badge b-other">POST</span>',
                   _esc(r.get("url") or ""), _stat_badge_req(rs),
                   _http_badge(r.get("status")),
                   float(r.get("elapsed") or 0) * 1000))
            parts.append(_fold("📤 请求头（已脱敏）",
                               _jdump(_mask_headers_for_display(
                                   r.get("req_headers")))))
            parts.append(_fold("📤 请求体（%s B）"
                               % format(len(_jdump(r.get("req_body"))), ","),
                               _jdump(r.get("req_body"))))
            if r.get("error"):
                parts.append('<pre>发送异常: ' + _esc(r["error"])
                             + "</pre>\n")
            else:
                parts.append(_fold("📥 响应头（%d 项）"
                                    % len(r.get("resp_headers") or {}),
                                   _jdump(r.get("resp_headers"))))
                parts.append(_fold("📥 响应体（%s B）"
                                   % format(len(r.get("resp_body") or ""),
                                            ","),
                                   r.get("resp_body") or ""))
            parts.append("</div>\n")
        if not case_recs:
            parts.append('<div class="kv">（无请求记录——用例未执行或'
                         "发送前失败）</div>\n")
        parts.append("</div>\n")  # side 实测
        parts.append("</div>\n")  # grid
        parts.append("</div>\n</div>\n")  # case-body / case-block
    parts.append("</div>\n")  # card
    parts.append("</div>\n</div>\n</div>\n<script>\n" + _JS
                 + "\n</script>\n</body>\n</html>\n")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Markdown 汇总（章节名与通用报告一致，供 Jenkins 邮件提取）
# ---------------------------------------------------------------------------

def build_markdown(allure: Dict[str, dict], records: List[dict],
                   meta: Dict[str, dict], order: List[str],
                   model_name: str, base_url: str,
                   chip_name: str = "", engine: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_pass = sum(1 for f in order
                 if allure.get(f, {}).get("status") == "passed")
    n_fail = sum(1 for f in order
                 if allure.get(f, {}).get("status") == "failed")
    n_err = sum(1 for f in order
                if allure.get(f, {}).get("status") == "broken")
    n_skip = sum(1 for f in order
                 if allure.get(f, {}).get("status") == "skipped")
    n_other = len(order) - n_pass - n_fail - n_err - n_skip
    lines: List[str] = []
    lines.append("# 浙江讯盟 AGDC2-61 GLM-5.3 功能对比测试汇总报告")
    lines.append("")
    lines.append(f"> 生成时间：{now}")
    lines.append(f"> 模型：{model_name or 'unknown'}")
    lines.append(f"> 接入点：{base_url or 'N/A'}")
    lines.append(f"> 芯片平台：{chip_name or 'N/A'}")
    lines.append(f"> 推理框架：{engine or 'N/A'}")
    lines.append(f"> 请求总数：{len(records)}")
    lines.append("> 用例源：九章 glm-5.3 功能对比报告 20261110（42 失败场景复现）"
                 "+ 九章新 url 复测报告 20261116（3 条官方基线异常守护）")
    lines.append("> 预期基准：智谱官方 run 20261028_191525 / Open Responses 规范"
                 " / 九章复测基线（官方异常条目）")
    lines.append("")
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
    lines.append("| 严重级 | 通过 | 失败 | 异常 | 跳过/未执行 | 合计 |")
    lines.append("|---|---|---|---|---|---|")
    sev_stat: Dict[str, List[int]] = {}
    for f in order:
        st = allure.get(f, {}).get("status", "not_run")
        k = (meta.get(f, {}).get("type") or "unknown")
        bucket = sev_stat.setdefault(k, [0, 0, 0, 0, 0])
        bucket[4] += 1
        if st == "passed":
            bucket[0] += 1
        elif st == "failed":
            bucket[1] += 1
        elif st == "broken":
            bucket[2] += 1
        else:
            bucket[3] += 1
    for k, b in sev_stat.items():
        lines.append(f"| {k} | {b[0]} | {b[1]} | {b[2]} | {b[3]} | {b[4]} |")
    lines.append("")
    lines.append("## 测试结论")
    lines.append("")
    if n_fail == 0 and n_err == 0 and n_pass == len(order):
        lines.append("**结论：**全部用例通过——被测平台行为与智谱官方"
                      "预期/规范口径一致，且 3 条官方基线异常守护"
                      "条目与九章复测基线一致（45 用例全量达标）。")
    else:
        lines.append("**结论：**存在未通过/未执行用例（42 条失败场景"
                      "预期=智谱官方行为；3 条官方异常守护预期=九章"
                      "复测基线，未通过即与预期基准存在差异）：")
        for f in order:
            a = allure.get(f, {})
            st = a.get("status")
            if st in ("failed", "broken"):
                m = meta.get(f, {})
                if m.get("type") == "差异确认":
                    verdict = ("差异暴露（报告口径「差异确认·不建议改」，"
                               "记录与官方的严格口径差异）")
                elif m.get("type") == "官方异常":
                    verdict = ("守护基线偏离（预期=九章复测基线，"
                               "与复测行为不符）")
                else:
                    verdict = "缺陷复现（修复对齐官方前预期 FAIL）"
                msg0 = (a.get("message") or "").strip().splitlines()
                msg0 = msg0[0] if msg0 else ""
                lines.append(f"- {'❌' if st == 'failed' else '⚠️'} "
                             f"{m.get('no', '')} {m.get('title', f)}"
                             f"（{verdict}）：{msg0[:200]}")
    lines.append("")
    skip_cases = [f for f in order
                  if allure.get(f, {}).get("status") in ("skipped",)
                  or f not in allure]
    lines.append("## 跳过用例说明")
    lines.append("")
    if skip_cases:
        for f in skip_cases:
            m = meta.get(f, {})
            reason = (allure.get(f, {}).get("message")
                      or "默认收集排除/未勾选执行")
            lines.append(f"- **{m.get('no', '')} {m.get('title', f)}**："
                          f"{reason[:200]}")
    else:
        lines.append("本次运行无跳过用例。")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def generate_reports(alluredir: str, records_path: str,
                     out_dir: str, model_name: str = "",
                     base_url: str = "", chip_name: str = "",
                     engine: str = "") -> Tuple[str, str]:
    """生成 HTML + MD，返回 (html_path, md_path)。"""
    allure = load_allure_results(alluredir)
    records = load_records(records_path) if records_path else []
    meta = load_docstring_meta()
    order = load_case_order(meta)
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = os.path.join(out_dir, f"zjxm_test_report_{ts}.html")
    md_path = os.path.join(out_dir, f"zjxm_summary_{ts}.md")
    html = build_html(allure, records, meta, order,
                      model_name, base_url, chip_name, engine)
    with io.open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    md = build_markdown(allure, records, meta, order,
                        model_name, base_url, chip_name, engine)
    with io.open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    return html_path, md_path


def _find_records_default(alluredir: str) -> str:
    """默认录制记录路径：allure-results 同级 zjxm_records.json。"""
    cand = os.path.join(os.path.dirname(os.path.abspath(alluredir)),
                        "zjxm_records.json")
    return cand if os.path.exists(cand) else ""


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="浙江讯盟 AGDC2-61 Z 套件 HTML/Markdown 报告生成器"
                    "（官方 vs 实测对比样式，离线可重生成）")
    p.add_argument("--alluredir", required=True,
                   help="allure-results 目录（含 *result.json）")
    p.add_argument("--records", default=None,
                   help="请求录制记录 JSON（默认 allure-results 同级 "
                        "zjxm_records.json）")
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
