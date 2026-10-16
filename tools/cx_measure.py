"""测量真实播放速率：验证"按真实速率挂机"（约束 #2）是否成立。

方法：枚举**所有** frame 里的 video/audio 元素（超星页面里有未加载的占位 <audio>，
只挑第一个会测错），按「是否已加载/是否在播」挑出真正在播放的那个，
读 currentTime / playbackRate，隔一段时间再读一次，算有效速率。

判读标准：
    ≈1.00      正常（真实速率）
    <1.0       被暂停/失焦打断（或卡顿）
    >1.0       ❌ 有倍速（违反约束 #2）
    倒退/跳变    ❌ 有 seek/拖动（违反约束 #2）

用法：
    python tools\\cx_measure.py --seconds 25
    python tools\\cx_measure.py --seconds 25 --all     # 列出所有候选，便于排查
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

CDP = "http://127.0.0.1:9222"
LOGS = Path(r"E:\Code\ChaoXingStudy\.logs")

PROBE_ALL = """() => Array.from(document.querySelectorAll('video,audio')).map(v => ({
  tag: v.tagName,
  id: v.id || '',
  cls: (v.className || '').toString().slice(0, 40),
  src: (v.currentSrc || v.src || '').slice(0, 90),
  currentTime: v.currentTime,
  duration: (isFinite(v.duration) ? v.duration : -1),
  playbackRate: v.playbackRate,
  paused: v.paused,
  ended: v.ended,
  muted: v.muted,
  volume: v.volume,
  readyState: v.readyState,
  w: v.offsetWidth, h: v.offsetHeight
}))"""


def collect(target):
    """返回 [(frame, candidate), ...]"""
    out = []
    for f in target.frames:
        try:
            items = f.evaluate(PROBE_ALL)
        except Exception:
            continue
        for it in items:
            out.append((f, it))
    return out


def score(c):
    """给候选打分：优先 已加载 且 在播 且 有时长"""
    s = 0
    if c["readyState"] > 0:
        s += 100
    if c["duration"] > 0:
        s += 50
    if not c["paused"]:
        s += 200
    if not c["ended"]:
        s += 10
    if c["tag"] == "VIDEO":
        s += 20
    s += min(c["duration"], 100000) / 100000.0
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=25)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        pages = [c for cc in browser.contexts for c in cc.pages]
        target = next((pg for pg in pages if "studentstudy" in (pg.url or "")), None)
        if target is None:
            print("[错误] 没有 studentstudy 标签页")
            sys.exit(1)
        print("[页面] %s" % target.url[:130])

        cands = collect(target)
        print("\n=== 所有 video/audio 候选（%d 个）===" % len(cands))
        for f, c in cands:
            print("  <%s> #%-10s .%-22s dur=%-9s ct=%-8.1f rate=%s paused=%-6s rs=%s %sx%s" % (
                c["tag"], c["id"][:10], c["cls"][:22],
                ("%.1f" % c["duration"]) if c["duration"] > 0 else "NaN",
                c["currentTime"], c["playbackRate"], c["paused"], c["readyState"], c["w"], c["h"]))
            print("      frame: %s" % (f.url or "")[:100])

        if not cands:
            print("[错误] 没有 video/audio 元素")
            sys.exit(1)

        cands.sort(key=lambda t: score(t[1]), reverse=True)
        vf, s0 = cands[0]
        print("\n=== 选中（分数最高，最像真在播的那个）===")
        print("  <%s> frame=%s" % (s0["tag"], (vf.url or "")[:100]))
        for k, v in s0.items():
            print("    %-14s %s" % (k, v))
        if s0["duration"] > 0:
            print("    进度           %.1f%%" % (100.0 * s0["currentTime"] / s0["duration"]))

        print("\n等待 %d 秒..." % args.seconds)
        wall0 = time.time()
        time.sleep(args.seconds)
        wall1 = time.time()

        try:
            now = vf.evaluate(PROBE_ALL)
        except Exception as e:
            print("[T1 读取失败] %s" % str(e)[:120])
            sys.exit(1)
        s1 = None
        for c in now:
            if c["tag"] == s0["tag"] and c["src"] == s0["src"]:
                s1 = c
                break
        if s1 is None and now:
            s1 = now[0]
        if s1 is None:
            print("[T1] 元素消失（可能已切任务）")
            sys.exit(1)

        vt = s1["currentTime"] - s0["currentTime"]
        wt = wall1 - wall0
        eff = vt / wt if wt else 0

        print("=== T1 ===")
        for k in ("currentTime", "playbackRate", "paused", "ended", "readyState"):
            print("    %-14s %s" % (k, s1[k]))

        print("\n=== 结论 ===")
        print("  视频前进      %.2f 秒" % vt)
        print("  实际流逝      %.2f 秒" % wt)
        print("  有效速率      %.3f x" % eff)
        print("  playbackRate  %.2f -> %.2f" % (s0["playbackRate"], s1["playbackRate"]))

        if vt < -0.5:
            print("  => ❌ currentTime 倒退：发生了 seek/重播")
        elif abs(eff - 1.0) <= 0.08 and s1["playbackRate"] == 1:
            print("  => ✅ 真实速率成立（1.0x），符合约束 #2")
        elif eff > 1.08 or s1["playbackRate"] > 1:
            print("  => ❌ 存在倍速/跳进（违反约束 #2）")
        else:
            print("  => ⚠️ 有效速率 <1：被暂停打断（paused=%s）" % s1["paused"])

        print("\n本次只读取播放器状态，未点击、未拖动。")


if __name__ == "__main__":
    main()
