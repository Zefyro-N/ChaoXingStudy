"""按关键词找到指定课程并进入，然后观测脚本工作状态。

【这个脚本会真的让脚本开始在课程上干活】—— 由用户在对话中明确授权后才运行。

用法：
    python tools\\cx_goto_course.py --match 知识论            # 只列出候选，不进入
    python tools\\cx_goto_course.py --match 知识论 --enter     # 进入并观测
    python tools\\cx_goto_course.py --match 知识论 --enter --seconds 60
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
LIST_URLS = [
    "https://i.mooc.chaoxing.com/space/index",
    "https://i.chaoxing.com/base",
]

DUMP_LINKS = """() => {
  const out = [];
  document.querySelectorAll('a[href]').forEach(a => {
    const h = a.getAttribute('href') || '';
    if (!/courseId=|mycourse|studentstudy|course\\/index/i.test(h)) return;
    const box = a.closest('li,div') || a;
    const t = ((box.innerText || a.innerText || '') + '').trim().replace(/\\s+/g, ' ').slice(0, 120);
    out.push({ href: h.slice(0, 300), text: t });
  });
  return out.slice(0, 120);
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True)
    ap.add_argument("--enter", action="store_true")
    ap.add_argument("--seconds", type=int, default=45)
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        pages = [pg for c in browser.contexts for pg in c.pages]
        target = next((pg for pg in pages if "chaoxing.com" in (pg.url or "")), None) or ctx.new_page()

        logs = []
        target.on("console", lambda m: logs.append((m.type, m.text[:300])))

        links = []
        for url in LIST_URLS:
            print("=== 打开课程列表: %s ===" % url)
            try:
                target.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print("  [导航异常] %s" % str(e)[:100])
                continue
            time.sleep(6)
            try:
                found = target.evaluate(DUMP_LINKS)
            except Exception as e:
                print("  [读取失败] %s" % str(e)[:100])
                continue
            print("  找到 %d 个课程相关链接" % len(found))
            for f in found:
                mark = "  *" if args.match in f["text"] else "   "
                print("%s %s" % (mark, f["text"][:90]))
                print("      %s" % f["href"][:150])
            if any(args.match in f["text"] for f in found):
                links = found
                break

        hit = [f for f in links if args.match in f["text"]]
        if not hit:
            print("\n[未找到含 '%s' 的课程链接]" % args.match)
            return
        print("\n=== 命中 %d 个 ===" % len(hit))
        for h in hit:
            print("  %s\n    %s" % (h["text"][:100], h["href"][:200]))

        if not args.enter:
            print("\n（未指定 --enter，所以没有进入课程）")
            return

        # 进入第一个命中的课程
        href = hit[0]["href"]
        print("\n=== 进入课程 ===\n  %s" % href[:180])
        try:
            target.goto(href, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            print("  [导航异常] %s" % str(e)[:120])

        print("\n等待 %d 秒，观测脚本是否开始工作..." % args.seconds)
        time.sleep(args.seconds)

        print("\n=== 当前 URL ===\n  %s" % target.url[:180])
        try:
            target.screenshot(path=str(LOGS / ("course-%d.png" % int(time.time()))),
                              animations="disabled", timeout=45000)
            print("  截图已保存")
        except Exception as e:
            print("  [截图失败] %s" % str(e)[:100])

        print("\n=== 控制台输出（%d 条）===" % len(logs))
        for t, txt in logs[-40:]:
            print("  [%s] %s" % (t, txt.replace("\n", " ")[:260]))

        print("\n本次已按用户要求进入课程。")


if __name__ == "__main__":
    main()
