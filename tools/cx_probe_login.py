# SPDX-FileCopyrightText: 2026 Zefyro-N
# SPDX-License-Identifier: MIT
"""只读探针：确认 CDP 已连上、页面已登录、作业/测验入口在哪。

不点击、不提交、不修改任何页面状态。
用法：python tools\\cx_probe_login.py
"""
import sys

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:20022"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        if not browser.contexts:
            print("  ❌ 没有 context")
            return
        ctx = browser.contexts[0]
        print(f"  contexts={len(browser.contexts)} pages={len(ctx.pages)}")
        target = None
        for pg in ctx.pages:
            if "chaoxing" in pg.url:
                target = pg
        if target is None:
            print("  ❌ 没找到超星页面")
            return
        print(f"  URL  : {target.url[:120]}")
        print(f"  标题 : {target.title()}")
        info = target.evaluate(
            """() => {
                const q = s => document.querySelector(s);
                const txt = s => { const e = q(s); return e ? (e.innerText || '').trim().slice(0, 50) : null; };
                return {
                    hasLoginForm: !!q('#loginNormal, .login-box, input[name="uname"]'),
                    userName: txt('#zl_username, .user-name, .userInfo .name'),
                    courseTitle: txt('.course-title, .course-name, h1, .tit'),
                    chapterItems: document.querySelectorAll('.chapter_item, .zj_ico, .posCatalog_select').length,
                    workEntries: document.querySelectorAll('a[href*="work"], a[href*="dowork"], a[href*="exam"]').length,
                    iframeCount: document.querySelectorAll('iframe').length,
                    bodyHead: (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim().slice(0, 200),
                };
            }"""
        )
        for key, value in info.items():
            print(f"  {key}: {value}")
        browser.close()


if __name__ == "__main__":
    main()
