"""把新的用户脚本安装/更新进 Tampermonkey（通过 CDP 驱动，无需用户操作）。

原理：Tampermonkey 会拦截对 *.user.js 的导航并弹出安装页，
点击其「安装 / 重新安装」按钮即可完成安装。

实测要点：
  - 按钮文案可能是「安装」/「重新安装」/「更新」/「Install」/「Reinstall」
  - 安装完成后用油猴 dashboard 的「最后更新 / 大小」核验，不靠猜

用法：
    python tools\\cx_install_userscript.py
    python tools\\cx_install_userscript.py --verify-only
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
TM_ID = "iikmkjmpaadaobahmlepeloendndfphd"
DASHBOARD = f"chrome-extension://{TM_ID}/options.html#nav=dashboard"
USERJS = "file:///E:/Code/ChaoXingStudy/dist/ocs.user.js"

INSTALL_TEXTS = ["重新安装", "安装", "更新", "Reinstall", "Install", "Update"]


def shot(page, tag):
    LOGS.mkdir(parents=True, exist_ok=True)
    p = LOGS / f"uinstall-{tag}-{int(time.time())}.png"
    try:
        page.screenshot(path=str(p), animations="disabled", timeout=30000)
        print("    [截图] %s (%d bytes)" % (p.name, p.stat().st_size))
    except Exception as e:
        print("    [截图失败] %s" % str(e)[:80])
    return p


def dump_buttons(page):
    try:
        return page.evaluate(
            """() => Array.from(document.querySelectorAll('button,a[role=button],input[type=button],input[type=submit]'))
                 .map(el => (el.innerText || el.value || el.getAttribute('aria-label') || '').trim())
                 .filter(t => t && t.length < 24).slice(0, 40)"""
        )
    except Exception:
        return []


def try_click(page, texts):
    for t in texts:
        for how in ("button", "link"):
            try:
                loc = page.get_by_role(how, name=t, exact=True)
                if loc.count() == 0:
                    loc = page.get_by_role(how, name=t, exact=False)
                if loc.count() > 0:
                    print("    点击 %s '%s'（命中 %d）" % (how, t, loc.count()))
                    loc.first.click(timeout=8000)
                    return t
            except Exception:
                continue
    return None


def dashboard_text(ctx):
    pg = ctx.new_page()
    try:
        pg.goto(DASHBOARD, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        return pg.inner_text("body")
    except Exception as e:
        return "[读取失败] %s" % str(e)[:100]
    finally:
        try:
            pg.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP)
        except Exception as e:
            print("[错误] 无法附着到 %s：%s" % (CDP, e))
            sys.exit(1)
        ctx = browser.contexts[0]

        print("=== 安装前：油猴里已有的 OCS 脚本 ===")
        before = dashboard_text(ctx)
        for line in before.splitlines():
            if "OCS" in line or "已安装脚本" in line:
                print("  " + line.strip()[:110])

        if not args.verify_only:
            page = ctx.new_page()
            print("\n=== 打开本地 .user.js（应被油猴接管）===")
            try:
                # 注：实测在 CDP 环境下该导航会超时（油猴未接管 file://），
                # 因此这里把超时设短一点，失败也不让脚本崩。
                page.goto(USERJS, wait_until="domcontentloaded", timeout=15000)
            except Exception as e:
                print("  [导航异常] %s" % str(e)[:160])
            time.sleep(4)
            try:
                print("  标题: %r" % page.title())
                print("  URL : %s" % page.url[:130])
                btns = dump_buttons(page)
                print("  可见按钮: %s" % btns)
                shot(page, "page")
            except Exception as e:
                print("  [页面已关闭或不可读] %s" % str(e)[:140])
                btns = []

            print("\n=== 点击安装按钮 ===")
            got = try_click(page, INSTALL_TEXTS)
            if not got:
                print("  [未找到安装按钮]")
                print("  实测结论：本地 file:// 导航在 CDP 环境下会超时（油猴未接管），")
                print("  通常是扩展无权访问文件 URL 所致。对策二选一：")
                print("    a) Edge -> 扩展 -> 篡改猴 -> 详情 -> 打开「允许访问文件 URL」后重试")
                print("    b) 油猴「新建脚本」直接粘贴 dist\\ocs.user.js 的内容（最可靠）")
            time.sleep(6)
            shot(page, "after-install")
            try:
                page.close()
            except Exception:
                pass

        print("\n=== 安装后：油猴里的 OCS 脚本（核验结果）===")
        after = dashboard_text(ctx)
        for line in after.splitlines():
            if "OCS" in line or "cxstudy" in line:
                print("  " + line.strip()[:110])

        print("\n完成。")


if __name__ == "__main__":
    main()
