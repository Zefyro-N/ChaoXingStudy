"""后台控制台日志收集器：把学习通页面的控制台输出持续追加到文件。

为什么需要它：OCS 面板渲染在 closed shadow root 里（JS 读不到，只有截图能看见），
所以「控制台日志」成了唯一可编程读取的观测通道。而章节测验/弹题可能要等十几分钟，
用一个后台进程收集日志，比长时间阻塞一次调用好得多。

用法：
    # 后台运行 30 分钟，日志写到 .logs/live.log
    python tools\\cx_logcollect.py --out .logs\\live.log --duration 1800
    # 或前台短跑
    python tools\\cx_logcollect.py --duration 60
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:20022"
ROOT = Path(r"E:\Code\ChaoXingStudy")

# 噪声屏蔽表（改为黑名单：白名单会误杀关键日志）
# 教训：曾用白名单过滤，结果把章节测验的关键日志 "[debug] 开始答题 OCSWorker"
# 与 "[debug] 题目数量: 5" 也过滤掉了（[debug] 不在白名单里）。
NOISE = [
    "CxRobotSdkJs", "VoiceToonBot", "Permissions policy violation",
    "Deprecated as of", "JQMIGRATE", "Failed to load resource", "net::ERR",
    "CxRobotSdk", "plugin/reading",
]

# 这些词儿命中时额外标一个 *，方便快速扫读
KEY_LOGS = [
    "cxstudy", "[ocsjs]", "模型", "答案", "章节", "任务点", "测验", "作业", "考试",
    "finishJob", "门禁", "预检", "图片", "截图", "playbackRate", "题目数量", "开始答题",
    "开始搜题", "OCR", "字体",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".logs/live.log")
    ap.add_argument("--duration", type=int, default=1800)
    ap.add_argument("--all", action="store_true", help="保留参数（已改为黑名单过滤，默认就记全部非噪声日志）")
    args = ap.parse_args()

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    f = open(out, "a", encoding="utf-8", buffering=1)

    def w(line):
        f.write(line + "\n")

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        w("# ==== 日志收集开始 %s ====" % datetime.now().strftime("%H:%M:%S"))

        subscribed = set()

        def subscribe(pg):
            try:
                key = id(pg)
                if key in subscribed:
                    return
                subscribed.add(key)
                pg.on("console", lambda m: on_console(pg, m))
                pg.on("pageerror", lambda e: w("%s [pageerror] %s | %s" % (
                    datetime.now().strftime("%H:%M:%S"), str(e)[:300], (pg.url or "")[:80])))
                w("%s [subscribed] %s" % (datetime.now().strftime("%H:%M:%S"), (pg.url or "")[:120]))
            except Exception:
                pass

        def on_console(pg, m):
            try:
                txt = m.text
                if any(k in txt for k in NOISE):
                    return
                mark = "* " if any(k in txt for k in KEY_LOGS) else "  "
                w("%s%s[%s] %s | %s" % (
                    datetime.now().strftime("%H:%M:%S"), mark, m.type,
                    txt.replace("\n", " ")[:400], (pg.url or "")[:70]))
            except Exception:
                pass

        t0 = time.time()
        while time.time() - t0 < args.duration:
            try:
                for pg in [x for c in browser.contexts for x in c.pages]:
                    if "chaoxing.com" in (pg.url or ""):
                        subscribe(pg)
            except Exception:
                pass
            time.sleep(3)

        w("# ==== 收集结束 %s ====" % datetime.now().strftime("%H:%M:%S"))
        f.close()


if __name__ == "__main__":
    main()
