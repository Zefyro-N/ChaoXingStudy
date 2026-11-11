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

CDP = "http://127.0.0.1:20022"
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
    ap.add_argument("--interval", type=int, default=2, help="采样间隔秒")
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
        print("    duration=%s  currentTime=%.1f  rate=%s  paused=%s" % (
            s0["duration"], s0["currentTime"], s0["playbackRate"], s0["paused"]))
        if s0["duration"] > 0:
            print("    进度 %.1f%%" % (100.0 * s0["currentTime"] / s0["duration"]))

        # ---- 连续采样：量化暂停占比（单次快照很容易误判）----
        interval = args.interval
        n = max(1, int(args.seconds / interval))
        print("\n=== 连续采样：%d 次，每次间隔 %ds（共约 %ds）===" % (n, interval, n * interval))
        samples = []
        wall0 = time.time()
        for i in range(n):
            target_ct = s0["currentTime"]
            try:
                now = vf.evaluate(PROBE_ALL)
                cur = None
                for c in now:
                    if c["tag"] == s0["tag"]:
                        cur = c
                        break
            except Exception:
                cur = None
            if cur:
                samples.append(cur)
            time.sleep(interval)
        wall1 = time.time()

        if len(samples) < 2:
            print("[采样不足] 元素可能已切走")
            sys.exit(1)

        a, b = samples[0], samples[-1]
        vt = b["currentTime"] - a["currentTime"]
        wt = wall1 - wall0
        eff = vt / wt if wt else 0
        paused_n = sum(1 for c in samples if c["paused"])
        rates = sorted(set(c["playbackRate"] for c in samples))

        print("  样本数          %d" % len(samples))
        print("  视频前进      %.2f 秒" % vt)
        print("  实际流逝      %.2f 秒" % wt)
        print("  有效速率      %.3f x" % eff)
        print("  暂停样本占比  %d/%d = %.0f%%" % (paused_n, len(samples), 100.0 * paused_n / len(samples)))
        print("  出现过的 rate  %s" % rates)
        if b["duration"] > 0:
            print("  当前进度      %.1f%%" % (100.0 * b["currentTime"] / b["duration"]))

        print("\n=== 结论 ===")
        if any(r > 1 for r in rates):
            print("  => ❌ 出现过 playbackRate>1：存在倍速（违反约束 #2）")
        elif vt < -0.5:
            print("  => ❌ currentTime 倒退：发生了 seek/重播")
        elif eff > 1.08:
            print("  => ❌ 有效速率 >1：存在跳进（违反约束 #2）")
        elif abs(eff - 1.0) <= 0.08:
            print("  => ✅ 真实速率成立（1.0x），符合约束 #2")
        else:
            print("  => ⚠️ 有效速率 %.2fx，低于 1.0；暂停样本占比 %.0f%%" % (eff, 100.0 * paused_n / len(samples)))
            print("     最可能原因：页面不在前台/窗口最小化（超星要求“观看时不可离开或最小化”，")
            print("     OCS 也弹过此类警告）。上游的 pause->play 只能部分兼底。")
            print("     若要彻底消除：需恢复 M11（伪装可见性状态），目前按用户要求已回退。")

        print("\n本次只读取播放器状态，未点击、未拖动。")


if __name__ == "__main__":
    main()
