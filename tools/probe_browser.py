"""能力探测：证明本机 Windows 侧可以驱动可见浏览器并截图取证。

只访问中性页面（example.com），不接触学习通、不登录、不写任何凭据。
"""
import sys
import pathlib

OUT = pathlib.Path(r"E:\Code\ChaoXingStudy\.logs")
OUT.mkdir(parents=True, exist_ok=True)

try:
    import playwright
    print(f"[1] playwright 已安装: {playwright.__version__ if hasattr(playwright, '__version__') else 'unknown'}")
except Exception as e:
    print(f"[1] playwright 导入失败: {e}")
    sys.exit(1)

from playwright.sync_api import sync_playwright

shot = OUT / "selfcheck.png"
with sync_playwright() as p:
    # 与 E:\Code\Estudy 一致的 channel=msedge（本机已验证可用）
    browser = p.chromium.launch(channel="msedge", headless=False)
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    page.goto("https://example.com", wait_until="load", timeout=30000)
    page.screenshot(path=str(shot))
    print(f"[2] 标题: {page.title()!r}")
    print(f"[3] URL : {page.url}")
    print(f"[4] 截图: {shot}  ({shot.stat().st_size} bytes)")
    browser.close()
print("[5] 浏览器已关闭")
