#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
思考/正文分离核验探针（单文件，仅需 Python 3 标准库）
====================================================
核验三件事：
  1) 思考是否落在 reasoning_content（而不是混进 content）
  2) content 结尾是否出现裸 </think> 控制标记
  3) 工具调用参数是否为合法完整的 JSON

来源：客户测试工程 probe_think_tag.py（AGDC2-24 / TR-20261016-02-九
章云-模型输出字段核验），引入本框架时仅将请求体目录（REQ）指向仓
库 requests/AGDC2-24（可用环境变量 PROBE_REQ_DIR 覆盖），其余逻辑
与原始探针一致。

用法
----
  # 被测平台（必填）
  set TEST_BASE=https://<被测平台地址>
  set TEST_KEY=<被测平台密钥>
  # 对照平台（可选；不设则跳过对照）
  set CONTROL_BASE=https://open.bigmodel.cn/api/paas/v4
  set CONTROL_KEY=<对照平台密钥>

  python probe_think_tag.py --runs 5

  # 不联网：复算已保存的原始响应（离线可复核本包结论）
  python probe_think_tag.py --replay origin_raw

输出目录
--------
  默认输出到 origin_raw/<时间戳>/（如 origin_raw/20261028_153045/），
  每次执行自动新建目录，不会覆盖历史结果。
  可用 --out 参数指定自定义输出目录。

路径配置
--------
  URL = BASE + CHAT_PATH，两个平台可分别配置：

  TEST_CHAT_PATH     被测平台路径（默认 /v1/chat/completions）
  CONTROL_CHAT_PATH  对照平台路径（默认 /v1/chat/completions）
  CHAT_PATH          全局默认路径（同时影响两个平台）
  MODEL             模型名（默认 glm-5.3）

  示例：智谱官方 API 为 https://open.bigmodel.cn/api/paas/v4/chat/completions，
  路径不含 /v1 前缀，需设置：
    set CONTROL_CHAT_PATH=/chat/completions
"""
import argparse, json, os, sys, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REQ = os.environ.get("PROBE_REQ_DIR") or os.path.normpath(
    os.path.join(HERE, "..", "requests", "AGDC2-24")
)
CASES = ["artifact_python_target", "minimal_template_escaped", "PTB-0083_seq406"]
MODEL = os.environ.get("MODEL", "glm-5.3")
PATH = os.environ.get("CHAT_PATH", "/v1/chat/completions")
TEST_PATH = os.environ.get("TEST_CHAT_PATH", PATH)
CONTROL_PATH = os.environ.get("CONTROL_CHAT_PATH", PATH)


def call(base, key, obj, raw_path, path, timeout=900, retries=1):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    h = {"Content-Type": "application/json", "Accept": "text/event-stream",
         "Authorization": "Bearer " + key, "x-api-key": key}
    status, text = None, ""
    for a in range(retries + 1):
        try:
            r = urllib.request.urlopen(urllib.request.Request(base.rstrip("/") + path,
                                                              data=body, headers=h), timeout=timeout)
            status, text = r.status, r.read().decode("utf-8", "replace")
            if text.strip():
                break
        except urllib.error.HTTPError as e:
            status, text = e.code, e.read().decode("utf-8", "replace")
            break
        except Exception as e:
            status, text = None, "%s: %s" % (type(e).__name__, e)
        if a < retries:
            time.sleep(2)
    open(raw_path, "w", encoding="utf-8").write(text)
    return status, text


def analyse(t):
    c, r, seq, tools, args, finish = [], [], [], [], "", None
    for line in t.splitlines():
        if not line.startswith("data: "):
            continue
        s = line[6:].strip()
        if s == "[DONE]":
            continue
        try:
            j = json.loads(s)
        except Exception:
            continue
        for ch in (j.get("choices") or []):
            d = ch.get("delta") or {}
            if d.get("content"):
                c.append(d["content"])
                if not seq or seq[-1] != "C":
                    seq.append("C")
            if d.get("reasoning_content"):
                r.append(d["reasoning_content"])
                if not seq or seq[-1] != "R":
                    seq.append("R")
            for tc in (d.get("tool_calls") or []):
                fn = tc.get("function") or {}
                if fn.get("name"):
                    tools.append(fn["name"])
                args += fn.get("arguments") or ""
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]
    ct, rt = "".join(c), "".join(r)
    try:
        json.loads(args) if args else None
        ok = True
    except Exception:
        ok = False
    return {"c": len(ct), "r": len(rt), "seq": "→".join(seq), "tools": tools, "args_ok": ok,
            "finish": finish, "bare": ct.rstrip().endswith("</think>"),
            "ratio": round(len(rt) / len(ct), 2) if ct else None,
            "native": sum(rt.count(x) for x in ("<arg_key>", "<arg_value>", "</tool_call>"))}


HDR = "%-26s %6s %7s %9s %7s %-12s %-18s %8s  %s"


def row(label, a):
    print(HDR % (label, a["c"], a["r"], a["ratio"], "是" if a["bare"] else "否",
                 a["seq"], ",".join(a["tools"]) or "-", a["finish"],
                 "参数非法" if not a["args_ok"] else ("原生标记泄漏" if a["native"] else "")))


def run_base(name, base, key, runs, outdir, tagpfx, path):
    os.makedirs(outdir, exist_ok=True)
    print("=" * 118)
    print("### %s  %s%s" % (name, base, path))
    print(HDR % ("用例/次数", "content", "reason", "R/C", "尾裸", "字段切换", "工具调用", "finish", "备注"))
    bad_bare = tot = 0
    ratios = []
    for case in CASES:
        p = json.load(open(os.path.join(REQ, case + ".json"), encoding="utf-8"))
        p.pop("url", None)
        for i in range(1, runs + 1):
            st, txt = call(base, key, p, os.path.join(outdir, "%s_%s_r%d.raw" % (tagpfx, case, i)), path)
            a = analyse(txt)
            tot += 1
            bad_bare += 1 if a["bare"] else 0
            if a["ratio"] is not None:
                ratios.append(a["ratio"])
            row("%s #%d" % (case, i), a)
    print()
    if ratios:
        print("  → %s：R/C 比值 min=%.2f max=%.2f ｜ 尾部裸 </think> %d/%d" %
              (name, min(ratios), max(ratios), bad_bare, tot))
    print()


def replay(dirpath):
    groups = {}
    for root, _, fns in os.walk(dirpath):
        for fn in fns:
            if not fn.endswith(".raw"):
                continue
            rel = os.path.relpath(root, dirpath).replace(os.sep, "/")
            label = os.path.basename(os.path.normpath(dirpath)) if rel == "." else rel
            groups.setdefault(label, []).append(os.path.join(root, fn))
    for d in sorted(groups):
        print("=" * 118)
        print("### %s（离线复算）" % d)
        print(HDR % ("文件", "content", "reason", "R/C", "尾裸", "字段切换", "工具调用", "finish", "备注"))
        bad = tot = 0
        for f in sorted(groups[d]):
            a = analyse(open(f, encoding="utf-8", errors="replace").read())
            tot += 1
            bad += 1 if a["bare"] else 0
            row(os.path.basename(f)[:-4], a)
        print("\n  → %s：尾部裸 </think> %d/%d\n" % (d, bad, tot))


if __name__ == "__main__":
    from datetime import datetime
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--out", default=None,
                    help="输出目录；不指定时默认为 origin_raw/<时间戳>/（内分 test/ 与 control/ 子目录），"
                         "每次执行自动新建目录，不会覆盖历史结果")
    ap.add_argument("--replay", default=None)
    args = ap.parse_args()
    if args.replay:
        replay(args.replay)
        sys.exit(0)
    tb, tk = os.environ.get("TEST_BASE", ""), os.environ.get("TEST_KEY", "")
    if not tb or not tk:
        sys.exit("请先设置 TEST_BASE 与 TEST_KEY")
    if args.out is None:
        args.out = os.path.join("origin_raw", datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(os.path.join(HERE, args.out, "test"), exist_ok=True)
    run_base("test", tb, tk, args.runs, os.path.join(HERE, args.out, "test"), "test", TEST_PATH)
    cb, ck = os.environ.get("CONTROL_BASE", ""), os.environ.get("CONTROL_KEY", "")
    if cb and ck:
        run_base("control", cb, ck, args.runs, os.path.join(HERE, args.out, "control"), "control", CONTROL_PATH)
