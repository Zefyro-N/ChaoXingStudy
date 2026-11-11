"""启动一个带调试端口的独立浏览器实例（headed），供后续 CDP 附着使用。

默认使用 **Microsoft Edge**（可用 --browser chrome 切换）。

设计要点：
- 独立 user-data-dir：Chrome/Edge 136+ 对**默认**资料目录禁用 --remote-debugging-port（官方加固），
  必须另开目录。且按浏览器分开（.browser-profile-edge / .browser-profile-chrome），
  避免两种浏览器共用同一 profile 时出现修复提示或状态错乱。
- 直接启动浏览器（不经 Playwright 的 launch），因此不带 --enable-automation，
  navigator.webdriver 保持 false，指纹更接近日常浏览器。
- --remote-allow-origins=* 是 Chromium 111+ 允许 CDP 客户端连接所必需。
- 本脚本**不会登录、不填任何表单**，只负责把浏览器开起来停在登录页。
  登录由用户本人在窗口里完成，密码不经过脚本、不落盘。

【重要：这个 profile 是全新的，没有安装任何扩展】
  因此这个窗口适用于「只读探针 / 观测」——探针不需要油猴，只要登录态。
  如果你要**测试油猴脚本**，请直接用你日常那个已装好油猴的浏览器，不需要本脚本。

用法：
    python tools\\cx_launch.py                 # 默认 Edge，打开学习通登录页
    python tools\\cx_launch.py --browser chrome
    python tools\\cx_launch.py --url https://mooc1.chaoxing.com/
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"E:\Code\ChaoXingStudy")
PORT = 20022
DEFAULT_URL = "https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com"

BROWSERS = {
    "edge": {
        "label": "Microsoft Edge",
        "profile": ".browser-profile-edge",
        "candidates": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge Beta\Application\msedge.exe",
        ],
    },
    "chrome": {
        "label": "Google Chrome",
        "profile": ".browser-profile-chrome",
        "candidates": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Google\Chrome Beta\Application\chrome.exe",
        ],
    },
}
DEFAULT_BROWSER = "edge"


def find_browser(kind: str) -> str:
    inc = BROWSERS[kind]["candidates"]
    for p in inc:
        if Path(p).exists():
            return p
    # 回退：也查一下用户级安装
    home = Path.home()
    fallback = {
        "chrome": home / r"AppData\Local\Google\Chrome\Application\chrome.exe",
        "edge": home / r"AppData\Local\Microsoft\Edge\Application\msedge.exe",
    }[kind]
    if fallback.exists():
        return str(fallback)
    raise SystemExit("找不到 %s，请确认安装路径" % BROWSERS[kind]["label"])


def cdp_ready(timeout=30) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2) as r:
                info = json.loads(r.read().decode("utf-8", "replace"))
            print("[CDP] 就绪: %s" % info.get("Browser"))
            return True
        except Exception:
            time.sleep(1)
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description="启动带 CDP 的独立浏览器（探针专用）")
    ap.add_argument("--browser", choices=list(BROWSERS.keys()), default=DEFAULT_BROWSER,
                    help="默认 %s" % DEFAULT_BROWSER)
    ap.add_argument("--url", default=DEFAULT_URL)
    # 兼容旧用法：第一个位置参数当作 URL
    ap.add_argument("url_positional", nargs="?", default=None)
    args = ap.parse_args()

    url = args.url_positional or args.url
    kind = args.browser
    exe = find_browser(kind)
    profile = ROOT / BROWSERS[kind]["profile"]
    profile.mkdir(parents=True, exist_ok=True)

    argv = [
        exe,
        "--user-data-dir=%s" % profile,
        "--remote-debugging-port=%d" % PORT,
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--new-window",
        url,
    ]
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP：与本脚本进程解耦，脚本退出后浏览器继续存活
    flags = 0x00000008 | 0x00000200
    print("[浏览器] %s" % BROWSERS[kind]["label"])
    print("[启动] %s" % exe)
    print("[Profile] %s" % profile)
    subprocess.Popen(argv, creationflags=flags, close_fds=True)

    if cdp_ready():
        print("[端口] 127.0.0.1:%d" % PORT)
        print()
        print("[下一步] 请在窗口里自己完成登录（密码不经过脚本）。登录完成后告诉我。")
        print("[提醒 1] 这个 profile 是全新的，**没有装油猴/扩展** ——")
        print("         它只用于只读探针与观测。要测试油猴脚本，请用你日常的浏览器。")
        print("[提醒 2] 换浏览器（edge/chrome）等于换 profile，需要各自登录一次。")
        print("[提醒 3] 挂机期间不要用手机 App 同时看同一门课（多端并发本身是异常信号）。")
    else:
        print("[错误] CDP 端口未就绪。可能已有同 profile 的浏览器在运行，请全部关闭后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
