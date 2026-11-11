"""切到章节测验页并抓取 M16/M17 字体解密的真实效果。

【这个脚本会点击「章节测验」标签】—— 即真正开始一次章节测验
（用户已在对话中明确授权；章节测验自动作答是既定功能）。

流程：附着 -> 先订阅控制台 -> 截图 -> 点击「章节测验」-> 等待 -> 截图 -> 输出关键日志

用法：
    python tools\\cx_open_quiz.py --seconds 90
    python tools\\cx_open_quiz.py --list        # 只列出候选标签，不点击
"""
import argparse
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:20022"
LOGS = Path(r"E:\Code\ChaoXingStudy\.logs")

TAB_KEYWORDS = ["章节测验", "章节检测", "测验"]

# 关注这些日志（M17 的成败、发给模型的题干是否可读）
HIGHLIGHT = ["cxstudy M17", "cxstudy M16", "字体解密", "font-cxsecret", "发送给模型的 prompt",
             "题目数量", "开始答题", "开始搜题", "解析出的答案", "模型原始响应", "cxstudy M2"]

NOISE = ["CxRobotSdkJs", "VoiceToonBot", "Permissions policy violation", "Deprecated as of",
         "JQMIGRATE", "Failed to load resource", "net::ERR"]

DUMP_TABS = """(kws) => {
  const out = [];
  document.querySelectorAll('a,li,span,div,button').forEach(el => {
    const t = (el.innerText || '').trim();
    if (!t || t.length > 16) return;
    if (!kws.some(k => t.indexOf(k) >= 0)) return;
    const r = el.getBoundingClientRect();
    if (r.width < 6 || r.height < 6) return;
    out.push({ tag: el.tagName, cls: (el.className||'').toString().slice(0,50),
               text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2) });
  });
  return out.slice(0, 20);
}"""


def find_quiz_doc(target):
    """找到含 .TiMu 或 .font-cxsecret 的 frame"""
    for f in target.frames:
        try:
            n = f.evaluate("() => ({ timu: document.querySelectorAll('.TiMu').length, fx: document.querySelectorAll('.font-cxsecret').length })")
        except Exception:
            continue
        if n.get("timu") or n.get("fx"):
            return f, n
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=90)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP, timeout=25000)
        ctx = b.contexts[0]
        pages = [pg for c in b.contexts for pg in c.pages]
        target = next((pg for pg in pages if "studentstudy" in (pg.url or "")), None)
        if target is None:
            print("[错误] 没有 studentstudy 标签页")
            sys.exit(1)
        print("[页面] %s" % target.url[:150])

        logs = []
        target.on("console", lambda m: logs.append((m.type, m.text)))
        target.on("pageerror", lambda e: logs.append(("pageerror", str(e))))

        shot0 = LOGS / ("quiz-before-%d.png" % int(time.time()))
        try:
            target.screenshot(path=str(shot0), animations="disabled", timeout=40000)
            print("[截图] %s" % shot0.name)
        except Exception as e:
            print("[截图失败] %s" % str(e)[:80])

        print("\n=== 候选标签 ===")
        cands = []
        for f in target.frames:
            try:
                cs = f.evaluate(DUMP_TABS, TAB_KEYWORDS)
            except Exception:
                continue
            for c in cs:
                c["frame"] = f
                cands.append(c)
        for c in cands:
            print("  <%s> .%-24s '%s' (%d,%d)" % (c["tag"], c["cls"][:24], c["text"], c["x"], c["y"]))
        if not cands:
            print("  （未找到含「章节测验」的可点元素）")

        if args.list:
            return

        # 优先点“恰好是标签”的元素（避开包含整串目录的容器 div）
        pick = None
        exact_ok = ["章节测验", "3章节测验", "2章节测验", "章节检测"]
        for c in cands:
            if c["tag"] in ("LI", "SPAN", "A") and c["text"].strip() in exact_ok:
                pick = c
                break
        if pick is None:
            for c in cands:
                if c["tag"] in ("LI", "SPAN", "A") and ("测验" in c["text"] or "检测" in c["text"]):
                    pick = c
                    break
        if pick is None:
            print("\n[无法点击] 没找到合适的标签")
            sys.exit(2)

        print("\n=== 点击 '%s' ===" % pick["text"])
        try:
            pick["frame"].evaluate(
                """(t) => {
                    const els = Array.from(document.querySelectorAll('li,span,a'));
                    const el = els.find(e => (e.innerText||'').trim() === t)
                            || els.find(e => (e.innerText||'').trim().indexOf(t) >= 0);
                    if (el) { el.click(); return true; }
                    return false;
                }""", pick["text"])
            print("  已点击")
        except Exception as e:
            print("  [点击失败] %s" % str(e)[:140])

        print("\n等待 %d 秒，观察解密与答题..." % args.seconds)
        time.sleep(args.seconds)

        fr, n = find_quiz_doc(target)
        print("\n=== 测验 frame 现状 ===")
        if fr:
            print("  frame: %s" % (fr.url or "")[:130])
            print("  .TiMu=%s  剩余 .font-cxsecret=%s" % (n.get("timu"), n.get("fx")))
            print("  => %s" % ("✅ 字体已被解密（.font-cxsecret 已清空）" if n.get("fx") == 0 and n.get("timu")
                               else ("⚠️ 仍有未解密元素" if n.get("fx") else "（无题目元素）")))
            # 抓一段可见题干文本，直接看是否可读
            try:
                sample = fr.evaluate("""() => {
                    const q = document.querySelector('.TiMu');
                    return q ? (q.innerText || '').replace(/\\s+/g, ' ').slice(0, 200) : '';
                }""")
                print("  样例题干文本: %s" % sample)
            except Exception:
                pass
        else:
            print("  未找到含题目的 frame")

        try:
            target.screenshot(path=str(LOGS / ("quiz-after-%d.png" % int(time.time()))),
                              animations="disabled", timeout=40000)
            print("  [截图已保存]")
        except Exception:
            pass

        print("\n=== 关键日志 ===")
        shown = 0
        for t, txt in logs:
            if any(k in txt for k in NOISE):
                continue
            if any(k in txt for k in HIGHLIGHT):
                print("  * [%s] %s" % (t, txt.replace("\n", " ")[:420]))
                shown += 1
        print("\n=== 全部非噪声日志（最后 90 条，便于看漏掉的信息）===")
        kept = [(t, txt) for t, txt in logs if not any(k in txt for k in NOISE)]
        print("  （非噪声共 %d 条）" % len(kept))
        for t, txt in kept[-90:]:
            print("    [%s] %s" % (t, txt.replace("\n", " ")[:300]))

        try:
            b.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
