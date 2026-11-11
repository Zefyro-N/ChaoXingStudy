"""通用页面检视器：看当前状态、抓截图、校验装的是不是我们的构建。

【严格只读】不点击、不提交、不刷新页面。

用法：
    python tools\\cx_inspect.py
    python tools\\cx_inspect.py --watch 20      # 额外抓 20 秒的控制台输出
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

# 只存在于我们这个构建里的字符串 —— 用来确认装的是不是我们的补丁版
OUR_MARKERS = [
    "模型接入（本分支）",
    "作业/考试自动作答",
    "cxModelApiKey",
    "cxModelVision",
    "cxAllowFinishJob",
    "允许图片题",
]

DOM_PROBE = """(markers) => {
  const html = document.documentElement ? document.documentElement.innerHTML : '';
  const text = document.body ? document.body.innerText : '';
  const found = {};
  markers.forEach(m => { found[m] = html.indexOf(m) >= 0 || text.indexOf(m) >= 0; });

  // 找 OCS 的悬浮面板：固定/绝对定位且 z-index 很高的元素
  const panels = [];
  document.querySelectorAll('div,section').forEach(el => {
    try {
      const cs = getComputedStyle(el);
      if ((cs.position === 'fixed' || cs.position === 'absolute') && parseInt(cs.zIndex || '0') > 1000) {
        const t = (el.innerText || '').trim();
        panels.push({ cls: (el.className||'').toString().slice(0,60), z: cs.zIndex, len: t.length, head: t.slice(0, 80) });
      }
    } catch (e) {}
  });

  // 页面上是否出现我们的日志标记
  const logHits = (html.match(/\\[cxstudy[^\\]]*\\]/g) || []).slice(0, 30);

  return {
    url: location.href,
    title: document.title,
    markers: found,
    panelCount: panels.length,
    panels: panels.slice(0, 6),
    logHits: logHits,
    hasJQuery: typeof window.jQuery !== 'undefined',
    iframeCount: document.querySelectorAll('iframe').length
  };
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", type=int, default=0, help="额外抓 N 秒控制台输出")
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP)
        except Exception as e:
            print("[错误] 无法附着到 %s：%s" % (CDP, e))
            sys.exit(1)

        pages = [pg for c in browser.contexts for pg in c.pages]
        print("=== 标签页 ===")
        for i, pg in enumerate(pages):
            try:
                print("  [%d] %s" % (i, pg.url[:120]))
            except Exception:
                print("  [%d] (读取失败)" % i)

        target = next((pg for pg in pages if "chaoxing.com" in (pg.url or "") and "studentstudy" in (pg.url or "")), None)
        if target is None:
            target = next((pg for pg in pages if "chaoxing.com" in (pg.url or "")), None)
        if target is None:
            print("\n[错误] 没有 chaoxing.com 标签页")
            sys.exit(1)

        print("\n=== 观测目标 ===\n  %s" % target.url[:150])

        logs = []
        if args.watch:
            target.on("console", lambda m: logs.append("[%s] %s" % (m.type, m.text[:300])))
            target.on("pageerror", lambda e: logs.append("[pageerror] %s" % str(e)[:300]))
            print("\n(已订阅控制台，抓 %d 秒)" % args.watch)

        shot = LOGS / ("inspect-%d.png" % int(time.time()))
        try:
            target.screenshot(path=str(shot), animations="disabled", timeout=45000)
            print("\n=== 截图 ===\n  %s (%d bytes)" % (shot.name, shot.stat().st_size))
        except Exception as e:
            print("\n[截图失败] %s" % str(e)[:100])

        try:
            info = target.evaluate(DOM_PROBE, OUR_MARKERS)
        except Exception as e:
            print("\n[DOM 探测失败] %s" % str(e)[:140])
            info = None

        if info:
            print("\n=== 这是不是我们的构建 ===")
            for k, v in info["markers"].items():
                print("  %-22s %s" % (k, "命中" if v else "未命中"))
            print("\n=== 页面概况 ===")
            print("  title=%r" % info["title"][:80])
            print("  iframe 数=%d  jQuery=%s" % (info["iframeCount"], info["hasJQuery"]))
            print("  高 z-index 浮层=%d" % info["panelCount"])
            for pn in info["panels"]:
                print("     z=%-6s .%-30s len=%-6s %s" % (pn["z"], pn["cls"][:30], pn["len"], pn["head"][:60]))
            print("\n  页面里的 [cxstudy] 日志标记: %s" % (info["logHits"] if info["logHits"] else "（无）"))

        if args.watch:
            time.sleep(args.watch)
            print("\n=== 控制台输出 ===")
            if logs:
                for l in logs[-60:]:
                    print("  " + l)
            else:
                print("  （这段时间没有输出；若脚本在跑，通常会有周期性日志）")

        print("\n本次为只读检视，未点击、未刷新、未提交。")


if __name__ == "__main__":
    main()
