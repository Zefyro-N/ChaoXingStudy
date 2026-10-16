"""启动一个带调试端口的独立浏览器实例（headed），供后续 CDP 附着使用。

设计要点：
- 独立 user-data-dir：Chrome 136+ 对**默认**资料目录禁用 --remote-debugging-port（官方加固），
  必须另开目录。用 `--user-data-dir=E:\\Code\\ChaoXingStudy\\.browser-profile`。
- 直接启动浏览器（不经 Playwright 的 launch），因此不带 --enable-automation，
  navigator.webdriver 保持 false，指纹更接近日常浏览器。
- --remote-allow-origins=* 是 Chrome 111+ 允许 CDP 客户端连接所必需。
- 本脚本**不会登录、不填任何表单**，只负责把浏览器开起来停在登录页。
  登录由用户本人在窗口里完成，密码不经过脚本、不落盘。

用法：
    python tools\\cx_launch.py            # 启动并打开学习通登录页
    python tools\\cx_launch.py <url>      # 启动并打开指定 URL
"""
import os
import subprocess
import sys
import time
import urllib.request
import json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"E:\Code\ChaoXingStudy")
PROFILE = ROOT / ".browser-profile"
PORT = 9222
DEFAULT_URL = "https://passport2.chaoxing.com/login?fid=&newversion=true&refer=https%3A%2F%2Fi.chaoxing.com"

CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    for p in CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("找不到 Chrome / Edge，请确认安装路径")


def cdp_ready(timeout=30) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2) as r:
                info = json.loads(r.read().decode("utf-8", "replace"))
            print(f"[CDP] 就绪: {info.get('Browser')}")
            return True
        except Exception:
            time.sleep(1)
    return False


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    exe = find_browser()
    PROFILE.mkdir(parents=True, exist_ok=True)

    args = [
        exe,
        f"--user-data-dir={PROFILE}",
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=Translate",
        "--new-window",
        url,
    ]
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP：与本脚本进程解耦，脚本退出后浏览器继续存活
    flags = 0x00000008 | 0x00000200
    print(f"[启动] {exe}")
    print(f"[Profile] {PROFILE}")
    subprocess.Popen(args, creationflags=flags, close_fds=True)

    if cdp_ready():
        print(f"[端口] 127.0.0.1:{PORT}")
        print("[下一步] 请在浏览器窗口里自己完成登录。登录完成后告诉我，我再开始只读观测。")
        print("[提醒] 使用期间请不要用手机 App 同时看同一门课（多端并发本身是异常信号）。")
    else:
        print("[错误] CDP 端口未就绪。可能已有同 profile 的浏览器在运行，请全部关闭后重试。")
        sys.exit(1)


if __name__ == "__main__":
    main()
