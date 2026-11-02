#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
九章云（Alaya）GLM-5.3 网关 · 双接口对照探针
============================================
用同一段会话报文，分别打两种协议接口，核对：
  ① SSE 是否真的下发了内容 / 工具调用
  ② usage 声明的输出 tokens 与实际下发内容是否一致（尤其 reasoning tokens）
  ③ 两种接口的表现是否一致

被测接口（均为本网关自带）
  OpenAI    : POST {BASE}/v1/chat/completions     鉴权 Authorization: Bearer <key>
  Anthropic : POST {BASE}/anthropic/v1/messages   鉴权 x-api-key: <key> + anthropic-version

来源：客户测试工程 probe_alaya.py（AGDC2-25 / 工具调用验核），引入
本框架时仅将 payload 目录指向仓库 requests/AGDC2-25（可用环境变量
PROBE_REQ_DIR 覆盖），其余逻辑与原始探针一致。

仅依赖 Python 3 标准库。用法：
  set ALAYA_KEY=<你的 API Key>
  python probe_alaya.py --n 10              # 两种接口各跑 10 次
  python probe_alaya.py --replay 原始响应    # 离线复算已保存的原始响应

输出：原始响应自动保存到 原始响应/<时间戳>/（每次执行自动新建目录，
不覆盖历史结果）；可用 --out 指定自定义输出目录。
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("ALAYA_BASE", "https://codingplan-staging.alayanew.com:26443")
KEY = os.environ.get("ALAYA_KEY", "")
REQ = os.environ.get("PROBE_REQ_DIR") or os.path.normpath(
    os.path.join(HERE, "..", "requests", "AGDC2-25")
)
OAI_PAYLOAD = os.path.join(REQ, "openai_request.json")
ANT_PAYLOAD = os.path.join(REQ, "anthropic_request.json")


def post(path, obj, raw_path, auth, timeout=300, retries=2):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if auth == "bearer":
        headers["Authorization"] = "Bearer " + KEY
    else:
        headers["x-api-key"] = KEY
        headers["anthropic-version"] = "2023-06-01"
    status, text = None, ""
    for a in range(retries + 1):
        try:
            r = urllib.request.urlopen(urllib.request.Request(BASE + path, data=body, headers=headers),
                                       timeout=timeout)
            status, text = r.status, r.read().decode("utf-8", "replace")
            if text.strip():
                break
        except urllib.error.HTTPError as e:
            status, text = e.code, e.read().decode("utf-8", "replace")
            break
        except Exception as e:
            status, text = None, "%s: %s" % (type(e).__name__, e)
        if a < retries:
            time.sleep(1)
    open(raw_path, "w", encoding="utf-8").write(text)
    return status, text


def parse(text, protocol):
    """返回：chunks / 正文字数 / 思考字数 / 工具调用 / 输出tokens / reasoning tokens / stop_reason"""
    r = {"chunks": 0, "text": 0, "think": 0, "tools": [], "out": None, "reason": None,
         "stop": None, "err": None}
    if "data: " not in text and not text.lstrip().startswith("{"):
        r["err"] = text.strip()[:100] or "(空响应体)"
        r["verdict"] = "错误"
        return r
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        s = line[6:].strip()
        if s == "[DONE]":
            continue
        try:
            j = json.loads(s)
        except Exception:
            continue
        r["chunks"] += 1
        if j.get("usage"):
            u = j["usage"]
            r["out"] = u.get("completion_tokens") if u.get("completion_tokens") is not None \
                else u.get("output_tokens")
            r["reason"] = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if protocol == "openai":
            for ch in (j.get("choices") or []):
                d = ch.get("delta") or {}
                for tc in (d.get("tool_calls") or []):
                    if (tc.get("function") or {}).get("name"):
                        r["tools"].append(tc["function"]["name"])
                r["text"] += len(d.get("content") or "")
                r["think"] += len(d.get("reasoning_content") or "")
                if ch.get("finish_reason"):
                    r["stop"] = ch["finish_reason"]
        else:
            t = j.get("type")
            if t == "content_block_start":
                cb = j.get("content_block") or {}
                if cb.get("type") == "tool_use":
                    r["tools"].append(cb.get("name"))
            elif t == "content_block_delta":
                d = j.get("delta") or {}
                if d.get("type") == "text_delta":
                    r["text"] += len(d.get("text") or "")
                elif d.get("type") == "thinking_delta":
                    r["think"] += len(d.get("thinking") or "")
            elif t == "message_delta":
                r["stop"] = (j.get("delta") or {}).get("stop_reason") or r["stop"]
    r["empty"] = (not r["tools"] and r["text"] == 0 and r["think"] == 0)
    r["verdict"] = "零增量" if r["empty"] else ("工具调用" if r["tools"] else "文本")
    return r


def run(protocol, n, outdir):
    path = "/v1/chat/completions" if protocol == "openai" else "/anthropic/v1/messages"
    src = OAI_PAYLOAD if protocol == "openai" else ANT_PAYLOAD
    base_req = json.load(open(src, encoding="utf-8"))
    base_req["stream"] = True
    base_req["max_tokens"] = 4096
    forced = json.loads(json.dumps(base_req))
    forced["tool_choice"] = "required" if protocol == "openai" else {"type": "any"}

    print("=" * 96)
    print("### %s ｜ %s" % ("九章云 Alaya", path))
    print("   %-10s %5s %7s %8s %8s %8s %10s  %s" %
          ("用例", "HTTP", "chunks", "正文", "思考", "输出tok", "reasoning", "判定"))
    rows = []
    for i in range(1, n + 1):
        tag = "%s_%02d" % (protocol, i)
        st, txt = post(path, base_req, os.path.join(outdir, tag + ".raw"),
                       "bearer" if protocol == "openai" else "x-api-key")
        r = parse(txt, protocol)
        rows.append(r)
        if r["err"]:
            print("   %-10s %5s  ← %s" % ("#%d" % i, st, r["err"]))
            continue
        print("   %-10s %5s %7d %8d %8d %8s %10s  %s" %
              ("#%d" % i, st, r["chunks"], r["text"], r["think"], r["out"], r["reason"],
               r["verdict"] + ("  ⚠️零增量（仅 usage）" if r["empty"] and (r["out"] or 0) > 0 else "")))
    st, txt = post(path, forced, os.path.join(outdir, protocol + "_forced.raw"),
                   "bearer" if protocol == "openai" else "x-api-key")
    rf = parse(txt, protocol)
    if rf["err"]:
        print("   %-10s %5s  ← %s" % ("强制调用", st, rf["err"]))
    else:
        print("   %-10s %5s %7d %8d %8d %8s %10s  %s" %
              ("强制调用", st, rf["chunks"], rf["text"], rf["think"], rf["out"], rf["reason"],
               rf["verdict"]))
    ok = [r for r in rows if not r["err"]]
    emp = [r for r in ok if r["empty"]]
    print("   → 小计：%d 次有效响应，空响应 %d（%.0f%%），工具调用 %d"
          % (len(ok), len(emp), 100.0 * len(emp) / max(len(ok), 1),
             sum(1 for r in ok if r["tools"])))
    return rows


def replay(dirpath):
    files = [os.path.join(root, fn) for root, _, fns in os.walk(dirpath)
             for fn in fns if fn.endswith(".raw")]
    for path in sorted(files):
        fn = os.path.basename(path)
        proto = "openai" if fn.startswith("openai") else "anthropic"
        txt = open(path, encoding="utf-8", errors="replace").read()
        r = parse(txt, proto)
        flag = "  ⚠️零增量（仅 usage）" if r.get("empty") and (r.get("out") or 0) > 0 else ""
        print("   %-24s chunks=%-5d 正文=%-6d 思考=%-6d 输出tok=%-6s reasoning=%-6s %s%s"
              % (fn[:-4], r["chunks"], r["text"], r["think"], r["out"], r["reason"],
                 r.get("verdict", r.get("err", "")), flag))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="每种接口重复次数")
    ap.add_argument("--out", default=None,
                    help="输出目录；不指定时默认为 原始响应/<时间戳>/，"
                         "每次执行自动新建目录，不会覆盖历史结果")
    ap.add_argument("--replay", default=None, help="离线复算目录下的 *.raw（含子目录）")
    args = ap.parse_args()

    if args.replay:
        replay(args.replay)
        return
    if not KEY:
        raise SystemExit("请先设置 ALAYA_KEY")
    if args.out is None:
        from datetime import datetime
        args.out = os.path.join("原始响应", datetime.now().strftime("%Y%m%d_%H%M%S"))
    outdir = os.path.join(HERE, args.out)
    os.makedirs(outdir, exist_ok=True)
    run("anthropic", args.n, outdir)
    print()
    run("openai", args.n, outdir)
    print("\n原始响应保存在 %s/" % args.out)


if __name__ == "__main__":
    main()
