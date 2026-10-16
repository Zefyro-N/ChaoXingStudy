"""确认油猴里到底装了什么脚本（直接问扩展自己，不猜）。

【只读】只打开扩展的管理页读取列表，不修改任何设置、不动学习通页面。

用法：
    python tools\\cx_check_script.py
"""
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
LOGS = Path(r"E:\Code\ChaoXingStudy\.logs")
TM_ID = "iikmkjmpaadaobahmlepeloendndfphd"  # Tampermonkey (Edge)
DASHBOARD = f"chrome-extension://{TM_ID}/options.html#nav=dashboard"

OUR_MARKERS = [
    "模型接入（本分支）",
    "作业/考试自动作答",
    "cxModelApiKey",
    "cxModelVision",
    "cxAllowFinishJob",
]

# 深度搜索：包含 shadow root 与同源 iframe
DEEP_SEARCH = """(markers) => {
  const hits = {};
  markers.forEach(m => hits[m] = 0);
  const seen = new Set();
  const visit = (root) => {
    if (!root || seen.has(root)) return;
    seen.add(root);
    try {
      const html = root.innerHTML || '';
      markers.forEach(m => { if (html.indexOf(m) >= 0) hits[m]++; });
    } catch (e) {}
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
    LOGS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP)
        except Exception as e:
            print("[错误] 无法附着到 %s：%s" % (CDP, e))
            sys.exit(1)

        ctx = browser.contexts[0]

        # ---------- 1) 油猴的已安装脚本列表 ----------
        print("=== 1. 油猴已安装脚本列表 ===")
        page = ctx.new_page()
        try:
            page.goto(DASHBOARD, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            print("  标题: %r" % page.title())
            txt = ""
            try:
                txt = page.inner_text("body")
            except Exception:
                pass
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            print("  ---- 页面文本（前 60 行）----")
            for l in lines[:60]:
                print("    " + l[:120])
            low = txt.lower()
            for name in ["ocs", "网课助手", "cxstudy", "学习通"]:
                print("  含 %-10s : %s" % (name, name.lower() in low))
            shot = LOGS / ("tm-dashboard-%d.png" % int(time.time()))
            try:
                page.screenshot(path=str(shot), animations="disabled", timeout=30000)
                print("  [截图] %s (%d bytes)" % (shot.name, shot.stat().st_size))
            except Exception as e:
                print("  [截图失败] %s" % str(e)[:80])
        except Exception as e:
            print("  [失败] %s" % str(e)[:140])

        # ---------- 2) 学习通页面：含 shadow DOM 的深度搜索 ----------
        print("\n=== 2. 学习通页面深度搜索（含 shadow DOM / iframe）===")
        pages = [pg for c in browser.contexts for pg in c.pages]
        cx = next((pg for pg in pages if "chaoxing.com" in (pg.url or "")), None)
        if cx is None:
            print("  没有 chaoxing.com 标签页")
        else:
            print("  目标: %s" % cx.url[:120])
            try:
                hits = cx.evaluate(DEEP_SEARCH, OUR_MARKERS)
                for k, v in hits.items():
                    print("    %-22s 命中 %d 处" % (k, v))
                if all(v == 0 for v in hits.values()):
                    print("    => 深度搜索也没找到：该页面上没有我们的构建在渲染")
            except Exception as e:
                print("    [失败] %s" % str(e)[:140])

        print("\n本次为只读检查。")


if __name__ == "__main__":
    main()
