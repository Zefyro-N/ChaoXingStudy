"""导航工具：只做"页面跳转 / 点导航菜单"，绝不做任何会被记为任务点完成的动作。

设计上的安全闸：
  - 点击目标必须是**导航白名单**里的词（课程/章节/目录/返回/首页/学习/我的课程…）。
  - 命中**危险黑名单**（提交/交卷/暂存/确认/开始考试/完成任务/保存…）一律拒绝执行。
  - 点击前先打印所有候选元素（文本 + 标签 + class），可见、可审。
  - 不做任何鼠标轨迹伪造，不拖动滑块，不识别验证码。

用法：
    python tools\\cx_nav.py --list                     # 只列出可点候选
    python tools\\cx_nav.py --click 课程                # 点导航项
    python tools\\cx_nav.py --url https://...           # 直接跳转
"""
import argparse
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:20022"

# 只允许这些词（导航性质）
ALLOW = ["课程", "我的课程", "章节", "目录", "返回", "首页", "学习", "个人空间", "首页", "班级"]

# 出现这些词一律拒绝（会造成真实状态变更）
DENY = ["提交", "交卷", "暂存", "保存", "确认", "确定", "开始考试", "完成任务", "完成学习",
        "结束", "重做", "重考", "删除", "退出", "签到", "继续答题", "开始答题"]

DANGEROUS_SELECTOR = "[onclick*='submit'],[onclick*='Submit'],#btnBlueSubmit,.btnBlueSubmit"


def find_candidates(page):
    return page.evaluate(
        """() => {
          const out = [];
          document.querySelectorAll('a,button,li,span,div').forEach((el, i) => {
            const t = (el.innerText || '').trim().replace(/\\s+/g, ' ');
            if (!t || t.length > 20) return;
            if (el.children.length > 0 && el.tagName === 'DIV') return;
            const r = el.getBoundingClientRect();
            if (r.width < 8 || r.height < 8) return;
            out.push({
              idx: i, text: t, tag: el.tagName,
              cls: (el.className || '').toString().slice(0, 50)
            });
          });
          return out.slice(0, 200);
        }"""
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--click", default=None)
    ap.add_argument("--url", default=None)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        pages = [pg for c in browser.contexts for pg in c.pages]
        target = next((pg for pg in pages if "chaoxing.com" in (pg.url or "")), None)
        if target is None:
            print("[错误] 没有找到 chaoxing.com 标签页")
            sys.exit(1)
        print(f"[当前] {target.url[:120]}")

        if args.url:
            print(f"[跳转] {args.url}")
            target.goto(args.url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            print(f"[结果] {target.url[:120]}")
            return

        if args.list or not args.click:
            print("\n=== 候选元素（只列不点）===")
            for c in find_candidates(target):
                print(f"  {c['text'][:24]:<26} <{c['tag']}>  {c['cls']}")
            return

        text = args.click.strip()
        if text not in ALLOW:
            print(f"[拒绝] '{text}' 不在导航白名单 {ALLOW} 内。这个工具只允许做页面导航。")
            sys.exit(2)
        for d in DENY:
            if d in text:
                print(f"[拒绝] '{text}' 命中危险黑名单（{d}）")
                sys.exit(2)

        # 用 Playwright 的文本定位，优先可见的精确匹配
        loc = target.get_by_text(text, exact=True)
        n = loc.count()
        print(f"[匹配] 文本 '{text}' 命中 {n} 个")
        if n == 0:
            print("[失败] 未找到，先用 --list 看看实际文本")
            sys.exit(1)

        el = loc.first
        try:
            el.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        print(f"[点击] {text}（仅导航，不涉及任何提交）")
        el.click(timeout=15000)
        time.sleep(4)
        print(f"[结果] {target.url[:150]}")


if __name__ == "__main__":
    main()
