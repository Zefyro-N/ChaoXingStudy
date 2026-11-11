"""读取 OCS 面板内容 / 切换面板标签（逐 frame 探测，不受同源策略限制）。

为什么必须逐 frame：OCS 面板可能渲染在某个子 frame 里，而页内 JS 遍历
（el.contentDocument）受同源策略限制进不去。Playwright 的 frame.evaluate 走 CDP，
可以进入跨域 frame —— 这是读取面板的唯一可靠方式。

【只读性质】在 safe_tabs 白名单内切换面板标签；不触碰任何任务点/提交按钮。

用法：
    python tools\\cx_panel.py --list
    python tools\\cx_panel.py --tab 通用
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

SAFE_TABS = ["超星学习通", "通用", "其他", "课程学习", "全局设置", "高级设置", "关于", "搜索结果"]

PROBE = """() => {
  const seen = new Set();
  const found = [];
  const walk = (root) => {
    if (!root || seen.has(root)) return;
    seen.add(root);
    let els;
    try { els = root.querySelectorAll('*'); } catch (e) { return; }
    for (const el of els) {
      let tc = '';
      try { tc = el.textContent || ''; } catch (e) { continue; }
      if (tc.indexOf('OCS') >= 0 && tc.length < 5000) {
        let cs = null;
        try { cs = getComputedStyle(el); } catch (e) {}
        found.push({
          el: el, len: tc.length, tag: el.tagName,
          cls: (el.className || '').toString().slice(0, 50),
          pos: cs ? cs.position : '?', z: cs ? cs.zIndex : '?', disp: cs ? cs.display : '?',
          tc: tc
        });
      }
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  if (!found.length) return { empty: true, host: location.href.slice(0, 120), total: document.querySelectorAll('*').length };
  found.sort((a, b) => a.len - b.len);
  const p = found[0];
  return {
    empty: false,
    host: location.href.slice(0, 120),
    candidates: found.length,
    pos: p.pos, z: p.z, disp: p.disp,
    text: (p.tc || '').slice(0, 4000),
    clicks: Array.from(p.el.querySelectorAll('a,button,li,span'))
      .map(el => (el.textContent || '').trim())
      .filter(t => t && t.length <= 14)
      .filter((v, i, a) => a.indexOf(v) === i)
      .slice(0, 80)
  };
}"""


def find_panel(target):
    """逐 frame 探测面板；返回 (frame, info) 或 (None, None)"""
    for fr in target.frames:
        try:
            info = fr.evaluate(PROBE)
        except Exception:
            continue
        if info and not info.get("empty"):
            return fr, info
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--url", default=None)
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        pages = [pg for c in browser.contexts for pg in c.pages]
        target = next((pg for pg in pages if "studentstudy" in (pg.url or "")), None) \
            or next((pg for pg in pages if "chaoxing.com" in (pg.url or "")), None)
        if target is None:
            print("[错误] 没有 chaoxing.com 标签页")
            sys.exit(1)
        print("[目标] %s" % target.url[:150])
        print("[frames] %d 个" % len(target.frames))

        if args.url:
            print("[导航] %s" % args.url[:120])
            try:
                target.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print("  [异常] %s" % str(e)[:100])

        fr, info = None, None
        for attempt in range(20):
            fr, info = find_panel(target)
            if info:
                print("  （第 %d 次探测命中，位于 frame: %s）" % (attempt + 1, info["host"]))
                break
            time.sleep(1.5)

        if not info:
            print("\n[仍未找到面板] 各 frame 概览：")
            for f in target.frames:
                try:
                    n = f.evaluate("() => document.querySelectorAll('*').length")
                    has = f.evaluate("() => (document.body ? document.body.textContent.indexOf('OCS') >= 0 : false)")
                except Exception:
                    n, has = -1, None
                print("   elements=%-6s 含OCS=%-6s %s" % (n, has, f.url[:100]))
            # 结构诊断：主 frame 的 body 直接子节点（看面板到底挂在哪）
            print("\n[结构诊断] 主 frame 的 body 子节点：")
            try:
                kids = target.main_frame.evaluate("""() => Array.from(document.body.children).map(el => {
                  const cs = getComputedStyle(el);
                  const r = el.getBoundingClientRect();
                  return {
                    tag: el.tagName, cls: (el.className||'').toString().slice(0,60), id: el.id||'',
                    pos: cs.position, z: cs.zIndex, disp: cs.display,
                    size: Math.round(r.width)+'x'+Math.round(r.height),
                    txt: (el.textContent||'').length
                  };
                })""")
                for k in kids:
                    print("   <%s> #%-14s .%-30s pos=%-8s z=%-8s disp=%-8s %-11s textLen=%s" % (
                        k["tag"], k["id"][:14], k["cls"][:30], k["pos"], k["z"], k["disp"], k["size"], k["txt"]))
            except Exception as e:
                print("   [失败] %s" % str(e)[:120])
            # 任何含 OCS 的元素（放宽到整个 documentElement.outerHTML）
            try:
                hit = target.main_frame.evaluate("() => { const h = document.documentElement.outerHTML; const i = h.indexOf('OCS'); return i < 0 ? null : h.slice(Math.max(0,i-200), i+200); }")
                print("\n[outerHTML 里的 OCS 片段] %s" % (hit[:400] if hit else "（无）"))
            except Exception:
                pass
            shot = LOGS / ("panel-miss-%d.png" % int(time.time()))
            try:
                target.screenshot(path=str(shot), animations="disabled", timeout=45000)
                print("\n[截图] %s（与上面诊断同一时刻，用于对比）" % shot.name)
            except Exception:
                pass
            sys.exit(2)

        print("  候选 %d 个  pos=%s z=%s disp=%s" % (info["candidates"], info["pos"], info["z"], info["disp"]))
        print("\n=== 面板里的可点标签 ===")
        print("  " + " | ".join(info["clicks"][:40]))

        if args.list or not args.tab:
            print("\n=== 当前面板内容 ===")
            print(info["text"][:3000])
            shot = LOGS / ("panel-list-%d.png" % int(time.time()))
            try:
                target.screenshot(path=str(shot), animations="disabled", timeout=45000)
                print("\n[截图] %s" % shot.name)
            except Exception as e:
                print("\n[截图失败] %s" % str(e)[:80])
            return

        tab = args.tab.strip()
        if tab not in SAFE_TABS:
            print("\n[拒绝] '%s' 不在安全白名单 %s 内" % (tab, SAFE_TABS))
            sys.exit(3)

        print("\n=== 点击面板标签 '%s' ===" % tab)
        ok = False
        try:
            loc = fr.get_by_text(tab, exact=True)
            if loc.count() == 0:
                loc = fr.get_by_text(tab, exact=False)
            if loc.count() > 0:
                loc.first.click(timeout=8000)
                ok = True
        except Exception as e:
            print("  [点击失败] %s" % str(e)[:120])
        time.sleep(3)

        fr2, info2 = find_panel(target)
        print("\n=== 切换后（点击%s）的面板内容 ===" % ("成功" if ok else "失败"))
        print((info2 or {}).get("text", "(未读到)")[:3500])

        shot = LOGS / ("panel-%s-%d.png" % (tab, int(time.time())))
        try:
            target.screenshot(path=str(shot), animations="disabled", timeout=45000)
            print("\n[截图] %s" % shot.name)
        except Exception as e:
            print("\n[截图失败] %s" % str(e)[:80])
        print("\n本次只在白名单内点击了面板标签。")


if __name__ == "__main__":
    main()
