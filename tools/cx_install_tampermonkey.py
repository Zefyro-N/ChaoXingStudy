"""通过 CDP 在探针专用浏览器里安装 Tampermonkey（无需用户手动操作）。

目的：让油猴脚本能在我可观测的浏览器里运行，这样验证时我自己看截图/控制台/DOM，
不需要用户转述任何现象。

实测记录（不要改回去）：
  - 商店页主按钮是「获取」
  - 点「获取」后会弹出模态框「安装扩展 / 必须安装扩展才能查看它。」，
    确认真实按钮文案是 **「获取扩展」**
  - 绝不要把宽泛的「添加」放进候选列表 —— 实测会误点评论区的「添加评论」

用法：
    python tools\\cx_install_tampermonkey.py
    python tools\\cx_install_tampermonkey.py --verify-only
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
STORE_URL = "https://microsoftedge.microsoft.com/addons/detail/tampermonkey/iikmkjmpaadaobahmlepeloendndfphd"
LOCAL_USERJS = "file:///E:/Code/ChaoXingStudy/dist/ocs.user.js"

GET_TEXTS = ["获取", "Get", "取得"]
ADD_TEXTS = ["获取扩展", "添加扩展", "Add extension"]


def shot(page, tag):
    LOGS.mkdir(parents=True, exist_ok=True)
    p = LOGS / f"tm-{tag}-{int(time.time())}.png"
    try:
        page.screenshot(path=str(p), animations="disabled", timeout=30000)
        print(f"    [截图] {p.name} ({p.stat().st_size} bytes)")
    except Exception as e:
        print(f"    [截图失败] {str(e)[:80]}")
    return p


def try_click(page, texts, label):
    for t in texts:
        for how in ("button", "link"):
            try:
                loc = page.get_by_role(how, name=t, exact=True)
                if loc.count() == 0:
                    loc = page.get_by_role(how, name=t, exact=False)
                if loc.count() > 0:
                    print(f"    点击 {how} '{t}'（命中 {loc.count()} 个）")
                    loc.first.click(timeout=8000)
                    time.sleep(3)
                    return t
            except Exception:
                continue
    print(f"    [{label}] 未找到可点击目标")
    return None


def verify(ctx):
    """验证油猴是否已接管 .user.js 安装页"""
    vp = ctx.new_page()
    try:
        vp.goto(LOCAL_USERJS, wait_until="domcontentloaded", timeout=30000)
        time.sleep(6)
        body = ""
        try:
            body = (vp.inner_text("body") or "")[:600]
        except Exception:
            pass
        print("  标题: %r" % vp.title())
        print("  URL : %s" % vp.url[:130])
        print("  正文片段: %s" % body.replace("\n", " ")[:260])
        installed = any(k in body for k in ["安装", "Install", "重新安装", "Reinstall"])
        print("  => 判定: %s" % ("已装 Tampermonkey（安装页被接管）" if installed else "未接管（油猴没装上）"))
        shot(vp, "verify")
        return installed
    except Exception as e:
        print("  [验证失败] %s" % str(e)[:120])
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP)
        except Exception as e:
            print(f"[错误] 无法附着到 {CDP}：{e}")
            print("        请先运行 python tools\\cx_launch.py")
            sys.exit(1)

        ctx = browser.contexts[0]

        if not args.verify_only:
            page = ctx.new_page()
            print("=== 1. 打开 Edge 加载项商店 Tampermonkey 页 ===")
            page.goto(STORE_URL, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            print("  标题: %s" % page.title())

            print("\n=== 2. 点「获取」 ===")
            try_click(page, GET_TEXTS, "获取")
            shot(page, "after-get")

            print("\n=== 3. 点弹窗里的「获取扩展」 ===")
            if try_click(page, ADD_TEXTS, "获取扩展"):
                shot(page, "after-add")
                time.sleep(8)
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(2)

        print("\n=== 4. 验证：打开本地 .user.js，看是否被油猴接管 ===")
        ok = verify(ctx)
        print("\n本次未对学习通页面做任何操作。")
        sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
