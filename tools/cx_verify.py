"""实机验证：导航到指定页面，抓启动日志 + 校验我们的构建是否在运行。

【关键】先订阅控制台，再导航 —— 这样能抓到脚本启动期的日志。
不点击任何按钮、不提交、不修改设置。

用法：
    python tools\\cx_verify.py --url "<课程播放页 URL>"
    python tools\\cx_verify.py --url "<...>" --seconds 40
    python tools\\cx_verify.py --current            # 只观测当前页，不导航
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

OUR_MARKERS = [
    "模型接入（本分支）",
    "作业/考试自动作答",
    "cxModelApiKey",
    "cxModelVision",
    "cxAllowFinishJob",
    "允许图片题",
]

KEY_LOGS = ["cxstudy", "OCS", "ocs", "模型", "finishJob", "门禁", "预检"]

DEEP_SEARCH = """(markers) => {
  const hits = {};
  markers.forEach(m => hits[m] = 0);
  const seen = new Set();
  const visit = (root) => {
    if (!root || seen.has(root)) return;
    seen.add(root);
    try { const html = root.innerHTML || ''; markers.forEach(m => { if (html.indexOf(m) >= 0) hits[m]++; }); } catch (e) {}
    try {
      Array.from(root.querySelectorAll('*')).forEach(el => {
        if (el.shadowRoot) visit(el.shadowRoot);
        if (el.tagName === 'IFRAME') { try { if (el.contentDocument) visit(el.contentDocument); } catch (e) {} }
      });
    } catch (e) {}
  };
  visit(document);
  return hits;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--current", action="store_true")
    ap.add_argument("--seconds", type=int, default=30)
    args = ap.parse_args()
    if not args.url and not args.current:
        print("需要 --url 或 --current")
        sys.exit(1)

    LOGS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP)
        except Exception as e:
            print("[错误] 无法附着到 %s：%s" % (CDP, e))
            sys.exit(1)
        ctx = browser.contexts[0]
        pages = [pg for c in browser.contexts for pg in c.pages]
        # 优先选课程播放页（studentstudy），而不是个人空间/课程列表
        target = next((pg for pg in pages if "studentstudy" in (pg.url or "")), None)
        if target is None:
            target = next((pg for pg in pages if "chaoxing.com" in (pg.url or "")), None)
        if target is None:
            target = ctx.new_page()

        logs = []
        target.on("console", lambda m: logs.append((m.type, m.text[:400])))
        target.on("pageerror", lambda e: logs.append(("pageerror", str(e)[:400])))

        if args.url:
            print("=== 导航到 ===\n  %s" % args.url[:160])
            try:
                target.goto(args.url, wait_until="domcontentloaded", timeout=90000)
            except Exception as e:
                print("  [导航异常] %s" % str(e)[:140])
        else:
            print("=== 观测当前页 ===\n  %s" % target.url[:160])

        print("\n等待 %d 秒收集日志..." % args.seconds)
        time.sleep(args.seconds)

        try:
            target.screenshot(path=str(LOGS / ("verify-%d.png" % int(time.time()))),
                              animations="disabled", timeout=45000)
            print("  截图已保存")
        except Exception as e:
            print("  [截图失败] %s" % str(e)[:100])

        print("\n=== URL ===\n  %s" % target.url[:170])

        hits = {}
        try:
            hits = target.evaluate(DEEP_SEARCH, OUR_MARKERS)
        except Exception as e:
            print("[深度搜索失败] %s" % str(e)[:120])
        print("\n=== 我们的构建是否在运行（含 shadow DOM / iframe）===")
        for k, v in hits.items():
            print("  %-22s %s" % (k, ("命中 %d 处" % v) if v else "未命中"))
        print("  => %s" % ("✅ 我们的构建正在该页运行" if any(v for v in hits.values())
                           else "❌ 该页未见我们的构建（可能此页不挂面板，或脚本未在此页激活）"))

        print("\n=== 控制台输出（共 %d 条）===" % len(logs))
        if not logs:
            print("  （无输出）")
        for t, txt in logs:
            mark = "  *  " if any(k in txt for k in KEY_LOGS) else "     "
            print("%s[%s] %s" % (mark, t, txt.replace("\n", " ")[:300]))

        print("\n本次未点击任何按钮、未提交、未修改设置。")


if __name__ == "__main__":
    main()
