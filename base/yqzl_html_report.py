# -*- coding: utf-8 -*-
"""杭州耘擎智联 AGDC2-75 yqzl 套件 HTML/Markdown 报告生成器。

报告结构：任务概要 / 测试结果统计（含报告类别分组与报告总判定对照）
/ 用例结果总览（全部 239 用例 + 场景期望 + 每请求子行）/ 用例明细
（左侧报告期望与逐项判定，右侧实测观察 + 请求/响应折叠，报文全量
不截断）。MD 章节名与通用报告一致（统计汇总/分类统计/测试结论/
跳过用例说明），供 Jenkins 邮件正文提取。

meta 数据源：tests/data/yqzl_agdc2_75_cases.json（报告程序化提取），
非 docstring。allure 节点名形如 test_case[BASIC-JSON]，按 case id 关联。

离线重生成：
python -m base.yqzl_html_report --alluredir <目录> [--records <json>]
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

_CASES_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests", "data", "yqzl_agdc2_75_cases.json")

# CSS 复刻自九章原始报告（20261119-192419）：stone 色系 + 浅色 pre +
# metrics 指标卡 + badge 圆角边框 + grid 两栏 side
_CSS = """
:root{--bg:#fafaf9;--fg:#1c1917;--mut:#57534e;--card:#fff;--bd:#e7e5e4;--code:#f5f5f4;--p:#15803d;--f:#b91c1c;--n:#a16207}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.7 -apple-system,'PingFang SC','Microsoft YaHei',sans-serif;overflow-wrap:anywhere}
main{max-width:1200px;margin:auto;padding:28px 18px}
h1{font-size:25px;margin:0 0 6px}h2{font-size:19px;margin:0 0 12px}h3{font-size:16px}
a{color:#235a90;text-underline-offset:3px}
.meta,.muted{color:var(--mut)}.meta{overflow-wrap:anywhere}
section,.card{background:var(--card);border:1px solid var(--bd);border-radius:9px;padding:20px;margin:18px 0;scroll-margin-top:18px}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:20px 0}
.metric{padding:14px 18px;background:white;border:1px solid var(--bd);border-radius:8px}
.metric b{display:block;font-size:28px}
.PASS{color:var(--p)}.FAIL{color:var(--f)}.REVIEW,.SKIP{color:var(--n)}
.badge{display:inline-block;border:1px solid;border-radius:20px;padding:1px 9px;font-size:12px;white-space:nowrap}
.badge.PASS{color:var(--p)}.badge.FAIL{color:var(--f)}.badge.SKIP{color:var(--n)}.badge.REVIEW{color:var(--n)}
.tw{overflow-x:auto;max-width:100%}
table{width:100%;border-collapse:collapse}
th,td{padding:10px 9px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}
th{background:var(--code);font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;min-width:0}
.side{border:1px solid var(--bd);border-radius:6px;padding:16px;min-width:0}
.side h3{margin-top:0}
pre{background:var(--code);border:1px solid var(--bd);border-radius:5px;padding:12px;overflow:auto;max-height:390px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
summary{cursor:pointer;font-weight:600;padding:7px 0}
dt{font-weight:650;margin-top:12px}dd{margin:3px 0 0}ol,ul{padding-left:22px}
.back{float:right;font-size:12px;font-weight:400}
.small{font-size:12px;color:var(--mut)}
"""


def _esc(s: Any) -> str:
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


def load_cases() -> List[dict]:
    with io.open(_CASES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_allure_results(alluredir: str) -> Dict[str, dict]:
    """读 allure-results 下 *result.json，过滤 test_yqzl 节点。
    节点名形如 test_case[BASIC-JSON]；key=case id。"""
    out: Dict[str, dict] = {}
    for p in sorted(glob.glob(os.path.join(alluredir, "*result.json"))):
        try:
            with io.open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        name = d.get("name") or ""
        nodeid = (d.get("nodeid") or d.get("fullName") or "")
        if "test_yqzl_agdc2_75" not in nodeid:
            continue
        m = re.search(r"\[(.+)\]", name)
        cid = m.group(1) if m else name
        rec = {
            "func": cid,
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
        old = out.get(cid)
        if old is None:
            out[cid] = rec
        else:
            rank_old = (1 if old["status"] == "failed" else
                        0 if old["status"] == "passed" else 2)
            rank_new = (1 if rec["status"] == "failed" else
                        0 if rec["status"] == "passed" else 2)
            if rank_new > rank_old:
                out[cid] = rec
    return out


def load_records(path: str) -> Tuple[List[dict], Dict[str, list], Dict[str, list]]:
    """读请求录制 JSON：{"records","obs","evals"}（返回 记录/观察/逐项判定）。"""
    with io.open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        obs = data.get("obs")
        ev = data.get("evals")
        return (data.get("records") or [],
                obs if isinstance(obs, dict) else {},
                ev if isinstance(ev, dict) else {})
    if isinstance(data, list):
        return data, {}, {}
    return [], {}, {}


def _http_text(status) -> str:
    """原始报告请求摘要的 HTTP 状态纯文本。"""
    try:
        return "HTTP %d" % int(status)
    except Exception:
        return "HTTP ?"


def _build_curl(rec: dict, url: str) -> str:
    """按录制记录构造 curl 复现命令（与原始报告同构）。"""
    payload = rec.get("req_body")
    body = _jdump(payload) if isinstance(payload, (dict, list)) \
        else str(payload if payload is not None else "")
    lines = [
        "curl --no-buffer --max-time 180 %s" % url,
        '-H "Authorization: Bearer $API_KEY"',
        '-H "Content-Type: application/json"',
        "--data-binary @- <<'REQUEST_JSON'",
        body,
        "REQUEST_JSON",
    ]
    return "\n".join(lines)


def _cn_badge(status: str) -> str:
    """重放状态 → 原始报告 badge 样式（通过/不通过/跳过/异常/未执行）。"""
    if status == "passed":
        return '<span class="badge PASS">通过</span>'
    if status == "failed":
        return '<span class="badge FAIL">不通过</span>'
    if status == "broken":
        return '<span class="badge FAIL">异常</span>'
    if status == "skipped":
        return '<span class="badge SKIP">跳过</span>'
    return '<span class="badge SKIP">未执行</span>'


def _eval_badge(ok) -> str:
    if ok is True:
        return '<span class="PASS">通过</span>'
    if ok is False:
        return '<span class="FAIL">不通过</span>'
    return '<span class="REVIEW">记录</span>'


def _kind_form(kind: str, stream: bool) -> str:
    return ("SSE 流式" if stream else "普通请求") + (
        {"chat": "", "responses": " · Responses", "messages": " · Anthropic",
         "compact": " · compact"}.get(kind, ""))


def build_html(allure: Dict[str, dict], records: List[dict],
               obs: Dict[str, list], evals: Dict[str, list],
               cases: List[dict], model_name: str, base_url: str,
               chip_name: str = "", engine: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts: List[str] = []

    # ---- 状态统计 ----
    n_pass = n_fail = n_err = n_skip = 0
    for c in cases:
        st = allure.get(c["id"], {}).get("status", "not_run")
        if st == "passed":
            n_pass += 1
        elif st == "failed":
            n_fail += 1
        elif st == "broken":
            n_err += 1
        elif st == "skipped":
            n_skip += 1
    n_other = len(cases) - n_pass - n_fail - n_err - n_skip
    n_exec = n_pass + n_fail + n_err
    pass_rate = ("%.2f%%" % (100.0 * n_pass / n_exec)) if n_exec else "N/A"

    # ---- 头部（复刻原始报告：h1 + meta + metrics 卡） ----
    parts.append(
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\""
        "utf-8\">\n<title>kimi-k3 功能测试报告（重放对比） - 杭州耘擎智联 "
        "AGDC2-75</title>\n<style>\n" + _CSS + "\n</style>\n</head>\n<body>\n"
        "<main>\n"
        "<h1>kimi-k3 功能测试报告（重放对比）</h1>\n"
        "<div class=\"meta\">被测资源：九章 ｜ 模型：" + _esc(model_name or "kimi-k3")
        + " ｜ 报告导出时间：" + _esc(now) + "（北京时间）<br>请求端点："
        + _esc(base_url or "N/A") + "<br>范围：Chat Completions / SSE、"
        "Responses、文件与视觉、缓存 ｜ 对照方式：规范断言（用例源=九章 "
        "kimi-k3 测试报告 20261119-192419，239 用例程序化提取重放；官方接口"
        "未实测，无官方基线） ｜ 密钥已脱敏</div>\n"
        "<div class=\"metrics\">"
        "<div class=\"metric\">场景 / 检查项<b>" + str(len(cases)) + "</b></div>"
        "<div class=\"metric PASS\">通过<b>" + str(n_pass) + "</b></div>"
        "<div class=\"metric FAIL\">不通过<b>" + str(n_fail + n_err) + "</b></div>"
        "<div class=\"metric REVIEW\">跳过<b>" + str(n_skip) + "</b></div>"
        "<div class=\"metric\">未执行<b>" + str(n_other) + "</b></div>"
        "<div class=\"metric\">实际请求<b>" + str(len(records)) + "</b></div>"
        "<div class=\"metric\">已执行项通过率<b>" + _esc(pass_rate) + "</b></div>"
        "</div>\n")

    # ---- 结论与处理建议（复刻原始报告：FAIL 用例清单） ----
    if n_fail + n_err > 0:
        parts.append('<section><h2>结论与处理建议</h2>\n')
        for c in cases:
            a = allure.get(c["id"], {})
            st = a.get("status")
            if st not in ("failed", "broken"):
                continue
            msg = (a.get("message") or "").strip().splitlines()
            msg0 = msg[0] if msg else ""
            parts.append(
                '<p><span class="badge FAIL">不通过</span> '
                '<a href="#%s">%s</a>：%s</p>'
                % (_esc(c["id"]), _esc(c["id"]), _esc(msg0[:300])))
            parts.append(
                '<p><b>影响：</b>重放实测与报告所列断言存在差异，需结合请求'
                '响应确认对接影响。<br><b>建议：</b>按下方原始请求复现并核'
                '对参数、字段及返回内容；修正后重新验证。</p>\n')
        parts.append('</section>\n')

    # ---- 汇总表（复刻原始报告 6 列：用例/类别/场景/结果/官方实测/结果说明） ----
    parts.append('<div class="tw"><table id="summary"><thead><tr>'
                 '<th>用例</th><th>类别</th><th>场景</th><th>结果</th>'
                 '<th>官方实测</th><th>结果说明</th></tr></thead><tbody>\n')
    for c in cases:
        a = allure.get(c["id"], {})
        st = a.get("status", "not_run")
        msg = (a.get("message") or "").strip().splitlines()
        msg0 = msg[0] if msg else ""
        if st == "passed":
            note = "本次所有已列断言均通过。"
        elif st == "skipped":
            note = "跳过（报告标记 SKIP / 无期望 / 不适用项）。"
        elif st == "not_run":
            note = "未执行。"
        else:
            note = msg0[:200]
        parts.append(
            '<tr class="case-row" data-id="%s" data-category="%s" '
            'data-status="%s"><td><a href="#%s">%s</a></td><td>%s</td>'
            '<td>%s</td><td>%s</td><td>未执行</td><td>%s</td></tr>\n'
            % (_esc(c["id"]), _esc(c.get("category", "")),
               "PASS" if st == "passed" else (
                   "FAIL" if st in ("failed", "broken") else "SKIP"),
               _esc(c["id"]), _esc(c["id"]),
               _esc(c.get("category", "")), _esc(c.get("title", "")),
               _cn_badge(st), _esc(note)))
    parts.append('</tbody></table></div>\n')

    # ---- 用例明细（复刻原始 case-detail 结构） ----
    for c in cases:
        a = allure.get(c["id"], {})
        st = a.get("status", "not_run")
        case_recs = [r for r in records if r.get("case_id") == c["id"]]
        case_evals = evals.get(c["id"]) or []
        node_key = "test_case[%s]" % c["id"]
        case_obs = obs.get(node_key) or []
        msg = (a.get("message") or "").strip().splitlines()
        msg0 = msg[0] if msg else ""
        if st == "passed":
            result_note = "本次所有已列断言均通过。"
        elif st == "skipped":
            result_note = "跳过（报告标记 SKIP / 无期望 / 不适用项）。"
        else:
            result_note = msg0[:300]
        parts.append(
            '<section class="case-detail " id="%s"><h2>%s · %s %s'
            '<a class="back" href="#summary">↑ 返回汇总</a></h2>\n'
            % (_esc(c["id"]), _esc(c["id"]), _esc(c.get("title", "")),
               _cn_badge(st)))
        parts.append(
            '<dl><dt>类别</dt><dd>%s</dd>'
            '<dt>结果说明</dt><dd>%s</dd>'
            '<dt>影响与判定边界</dt><dd>按报告所列断言重放验证；差异仅反映重'
            '放环境与报告生产环境的实测变化，不直接等同功能回归。 只验证本'
            '次请求与所列断言。</dd>'
            '<dt>实际操作</dt><dd><ol class="steps">'
            '<li>使用报告所列参数（仅 model 替换为部署模型名），向被测端点'
            '发送 %d 次请求；未调用官方接口。</li>'
            '<li>读取实际响应，按报告所列断言逐条验证。</li>'
            '<li>保存脱敏请求、响应、状态码与逐项判定。</li></ol></dd></dl>\n'
            % (_esc(c.get("category", "")), _esc(result_note),
               len(case_recs)))
        # 左栏：规范要求/场景期望 + 逐项判定（重放执行结果徽章）
        parts.append('<div class="grid"><div class="side">'
                     '<h3>规范要求 / 场景期望</h3><p>%s</p>'
                     % _esc(c.get("expect") or "（报告未提供场景期望）"))
        parts.append('<h4>逐项判定</h4><ul>')
        if case_evals:
            for text, ok, detail in case_evals:
                parts.append('<li>%s · %s%s</li>\n'
                             % (_eval_badge(ok), _esc(text),
                                ('（%s）' % _esc(str(detail)[:120]))
                                if ok is not True else ''))
        else:
            for a2 in c.get("assertions") or []:
                parts.append('<li><span class="REVIEW">未执行</span> · %s</li>\n'
                             % _esc(a2.get("text", "")))
        parts.append('</ul><p class="muted">官方实测：未执行。断言基准为报告'
                     '「规范要求 / 场景期望」与逐项判定；记录式判定项只记录'
                     '不判。</p></div>\n')
        # 右栏：重放 · 实际表现
        parts.append('<div class="side"><h3>重放 · 实际表现</h3>')
        if not case_recs:
            parts.append('<p class="muted">未执行（跳过/未运行）。</p>')
        for i, r in enumerate(case_recs, 1):
            body = r.get("resp_body")
            preview = ""
            if isinstance(body, dict):
                preview = json.dumps(body, ensure_ascii=False)[:60]
            elif isinstance(body, str):
                preview = body[:60]
            parts.append(
                '<p>请求 #%d：%s；kind=%s；耗时 %d ms；响应摘要：%s</p>\n'
                % (i, _http_text(r.get("status")), _esc(str(r.get("kind", ""))),
                   int((r.get("elapsed") or 0) * 1000), _esc(preview)))
        if st in ("failed", "broken"):
            parts.append('<p><b>差异：</b>%s</p>' % _esc(msg0[:200]))
        else:
            parts.append('<p><b>差异：</b>%s</p>' % _esc(result_note))
        parts.append('</div></div>\n')
        # 请求 details（复刻原始结构）
        for i, r in enumerate(case_recs, 1):
            elapsed_ms = int((r.get("elapsed") or 0) * 1000)
            parts.append(
                '<details ><summary>请求 #%d · %s · %s · %d ms</summary>'
                '<p class="muted">耗时为整次请求耗时，不是 TTFT；请求头已'
                '脱敏（鉴权值前4+****+后4）。</p>'
                % (i, _esc(_kind_form(str(r.get("kind", "")),
                                      "data:" in str(r.get("resp_body", "")))),
                   _http_text(r.get("status")), elapsed_ms))
            parts.append('<div class="grid"><div class="side">'
                         '<h4>实际请求参数</h4><pre>%s</pre></div>'
                         % _esc(_jdump(r.get("req_body"))))
            resp_body = r.get("resp_body")
            resp_txt = _jdump(resp_body) if isinstance(resp_body, (dict, list)) \
                else str(resp_body if resp_body is not None else "")
            parts.append('<div class="side"><h4>实际响应</h4><pre>%s</pre></div></div>\n'
                         % _esc(resp_txt))
            parts.append(
                '<details><summary>已保留的响应头（已脱敏）</summary><pre>%s</pre></details>'
                % _esc(_jdump(_mask_headers_for_display(r.get("resp_headers")))))
            curl_url = str(r.get("url", ""))
            parts.append(
                '<details><summary>curl 复现本次请求（手动执行）</summary>'
                '<p>先在运行终端设置 API_KEY 环境变量。此处只展示命令，不自'
                '动发请求；多轮场景中的单条命令复现该轮上下文，不能独立证明'
                '完整工具执行闭环。</p><pre>%s</pre></details>'
                % _esc(_build_curl(r, curl_url)))
            parts.append(
                '<details><summary>原始响应正文 / SSE 事件</summary><pre>%s</pre></details>'
                % _esc(resp_txt))
            if r.get("error"):
                parts.append('<p class="muted">发送异常：%s</p>'
                             % _esc(str(r["error"])))
            parts.append('</details>\n')
        if case_obs:
            parts.append('<details><summary>记录式判定项与观察</summary>'
                         '<ul>')
            for t in case_obs:
                parts.append('<li>%s</li>\n' % _esc(t))
            parts.append('</ul></details>\n')
        parts.append('</section>\n')

    parts.append('</main>\n</body>\n</html>\n')
    return "".join(parts)


def build_markdown(allure: Dict[str, dict], records: List[dict],
                   obs: Dict[str, list], cases: List[dict],
                   model_name: str, base_url: str,
                   chip_name: str = "", engine: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = []
    lines.append("# kimi-k3 功能测试报告重放汇总（杭州耘擎智联 AGDC2-75）")
    lines.append("")
    lines.append(f"> 生成时间：{now}")
    lines.append(f"> 模型：{model_name or 'unknown'}")
    lines.append(f"> 接入点：{base_url or 'N/A'}")
    lines.append(f"> 芯片平台：{chip_name or 'N/A'}")
    lines.append(f"> 推理框架：{engine or 'N/A'}")
    lines.append(f"> 请求总数：{len(records)}")
    lines.append("> 用例源：九章 kimi-k3 测试报告 20261119-192419（239 用例提取重放）")
    lines.append("> 断言基准：报告场景期望与逐项判定（记录式只记录；未映射降级观察）")
    lines.append("")

    n_pass = n_fail = n_err = n_skip = 0
    for c in cases:
        st = allure.get(c["id"], {}).get("status", "not_run")
        if st == "passed":
            n_pass += 1
        elif st == "failed":
            n_fail += 1
        elif st == "broken":
            n_err += 1
        elif st == "skipped":
            n_skip += 1
    n_other = len(cases) - n_pass - n_fail - n_err - n_skip

    lines.append("## 统计汇总")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    lines.append(f"| 用例总数 | {len(cases)} |")
    lines.append(f"| 通过 | {n_pass} |")
    lines.append(f"| 失败 | {n_fail} |")
    lines.append(f"| 异常 | {n_err} |")
    lines.append(f"| 跳过/未执行 | {n_skip + n_other} |")
    lines.append(f"| 请求总数 | {len(records)} |")
    lines.append("")

    lines.append("## 分类统计")
    lines.append("")
    lines.append("| 报告类别 | 通过 | 失败 | 异常 | 跳过/未执行 | 合计 |")
    lines.append("|---|---|---|---|---|---|")
    cat_stat: Dict[str, List[int]] = {}
    for c in cases:
        st = allure.get(c["id"], {}).get("status", "not_run")
        k = c.get("category") or "未分组"
        b = cat_stat.setdefault(k, [0, 0, 0, 0, 0])
        b[4] += 1
        if st == "passed":
            b[0] += 1
        elif st == "failed":
            b[1] += 1
        elif st == "broken":
            b[2] += 1
        else:
            b[3] += 1
    for k, b in cat_stat.items():
        lines.append(f"| {k} | {b[0]} | {b[1]} | {b[2]} | {b[3]} | {b[4]} |")
    lines.append("")

    lines.append("## 测试结论")
    lines.append("")
    if n_fail == 0 and n_err == 0:
        if n_pass == len(cases):
            lines.append("**结论：**全部用例通过——实测行为与报告场景期望"
                          "逐项一致（重放与报告生产环境行为无差异）。")
        else:
            lines.append("**结论：**已执行用例全部通过，部分用例跳过/未执行"
                          "（详见跳过用例说明）。")
    else:
        lines.append("**结论：**存在与报告场景期望不符的用例（重放差异/"
                      "缺陷复现或环境行为变化）：")
        for c in cases:
            a = allure.get(c["id"], {})
            st = a.get("status")
            if st in ("failed", "broken"):
                msg0 = (a.get("message") or "").strip().splitlines()
                msg0 = msg0[0] if msg0 else ""
                lines.append(f"- {'❌' if st == 'failed' else '⚠️'} "
                             f"{c['id']} {c.get('title', '')}（报告判定 "
                             f"{c.get('badge', '?')}）：{msg0[:200]}")
    lines.append("")

    lines.append("## 能力观察清单")
    lines.append("")
    lines.append("（记录式判定项与未映射判定项的实测观察——不参与 PASS/FAIL）")
    lines.append("")
    for c in cases:
        node_key = "test_case[%s]" % c["id"]
        case_obs = obs.get(node_key) or []
        if not case_obs:
            continue
        st = allure.get(c["id"], {}).get("status", "not_run")
        mark = {"passed": "✅", "failed": "❌", "broken": "⚠️"}.get(st, "➖")
        lines.append(f"### {mark} {c['id']} · {c.get('title', '')}")
        for t in case_obs:
            lines.append(f"- {t}")
        lines.append("")

    skip_cases = [c for c in cases
                  if allure.get(c["id"], {}).get("status") == "skipped"]
    if skip_cases:
        lines.append("## 跳过用例说明")
        lines.append("")
        for c in skip_cases:
            lines.append(f"- {c['id']} · {c.get('title', '')}"
                         f"（报告判定 {c.get('badge', '?')}）")
        lines.append("")
    return "\n".join(lines)


def generate_reports(alluredir: str, records_path: str,
                     out_dir: str, model_name: str = "",
                     base_url: str = "", chip_name: str = "",
                     engine: str = "") -> Tuple[str, str]:
    allure = load_allure_results(alluredir)
    records, obs, evals = load_records(records_path) if records_path else ([], {}, {})
    cases = load_cases()
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = os.path.join(out_dir, f"yqzl_test_report_{ts}.html")
    md_path = os.path.join(out_dir, f"yqzl_summary_{ts}.md")
    html = build_html(allure, records, obs, evals, cases,
                      model_name, base_url, chip_name, engine)
    with io.open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    md = build_markdown(allure, records, obs, cases,
                        model_name, base_url, chip_name, engine)
    with io.open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    return html_path, md_path


def _find_records_default(alluredir: str) -> str:
    cand = os.path.join(os.path.dirname(os.path.abspath(alluredir)),
                        "yqzl_records.json")
    return cand if os.path.exists(cand) else ""


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="杭州耘擎智联 AGDC2-75 yqzl 套件 HTML/Markdown 报告生成器"
                    "（报告重放对比样式，离线可重生成）")
    p.add_argument("--alluredir", required=True,
                   help="allure-results 目录（含 *result.json）")
    p.add_argument("--records", default=None,
                   help="请求录制记录 JSON（默认 allure-results 同级 "
                        "yqzl_records.json）")
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
