"""只读探测「视频内弹题」的真实 DOM 结构与题型标记。

用途：弹题出现概率低、难以复现。本工具用于
  1) 立刻探测当前页面/iframe 里弹题相关 DOM 是否存在、结构如何；
  2) 用 --watch 常驻轮询，弹题一出现就把真实结构打出来并截图。

【只读】不点击任何元素，不修改页面。

用法：
    python tools\\cx_probe_videoquiz.py
    python tools\\cx_probe_videoquiz.py --watch --seconds 1800
    python tools\\cx_probe_videoquiz.py --all-frames        # 也扫描隐藏 iframe
"""
import argparse
import json
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

# 一次性把关心的结构全部读出来（只读）
PROBE = r"""() => {
  const q = (s) => document.querySelector(s);
  const qa = (s) => Array.from(document.querySelectorAll(s));
  const out = {
    href: location.href.slice(0, 160),
    hasVideo: !!q('#video'),
    hasAudio: !!q('#audio'),
    videoquizSubmit: !!q('#videoquiz-submit'),
    ansVideoquiz: qa('#video .ans-videoquiz').length,
    ansVideoquizAny: qa('.ans-videoquiz').length,
    optLabels: qa('.ans-videoquiz-opt label').length,
    xComponents: qa('.x-component-default').length,
  };
  // 弹题容器结构（截断）
  const c = q('#video .ans-videoquiz') || q('.ans-videoquiz');
  if (c) {
    out.containerHTML = (c.outerHTML || '').slice(0, 900);
    const st = getComputedStyle(c);
    out.containerVisible = st.display !== 'none' && st.visibility !== 'hidden';
  }
  // 选项：文本 + input 类型（radio=单选 / checkbox=多选）
  const labels = qa('.ans-videoquiz-opt label');
  if (labels.length) {
    out.options = labels.map((l) => {
      const inp = l.querySelector('input');
      return {
        text: (l.innerText || '').trim().slice(0, 60),
        inputType: inp ? (inp.type || inp.getAttribute('type') || '?') : null,
        checked: inp ? !!inp.checked : null,
        value: inp ? (inp.value ?? null) : null,
        valueAttr: inp ? inp.getAttribute('value') : null,
      };
    });
  }
  // 兼容另一形态：input[name='ans-videoquiz-opt']
  const namedInputs = qa("input[name='ans-videoquiz-opt']");
  if (!labels.length && namedInputs.length) {
    out.options = namedInputs.map((inp) => ({
      text: ((inp.closest('label') || inp.parentElement || inp).innerText || '').trim().slice(0, 60),
      inputType: inp.type || inp.getAttribute('type') || '?',
      checked: !!inp.checked,
      value: inp.value ?? null,
      valueAttr: inp.getAttribute('value'),
    }));
    out.optionSelector = "input[name='ans-videoquiz-opt']";
  } else if (labels.length) {
    out.optionSelector = '.ans-videoquiz-opt label';
  }
  // 提交按钮（两种形态）
  const sb = q('#videoquiz-submit') || q('.ans-videoquiz-submit');
  if (sb) {
    out.submitSelector = q('#videoquiz-submit') ? '#videoquiz-submit' : '.ans-videoquiz-submit';
    out.submitHTML = (sb.outerHTML || '').slice(0, 300);
  }
  // 题干候选：容器内非选项文本
  if (c) {
    const t = (c.innerText || '').trim().replace(/\s+/g, ' ');
    out.containerText = t.slice(0, 200);
  }
  // 媒体状态
  const all = qa('video,audio');
  out.media = all.map((m) => ({
    tag: m.tagName, id: m.id || null,
    dur: Number.isFinite(m.duration) ? Math.round(m.duration) : null,
    cur: Number.isFinite(m.currentTime) ? Math.round(m.currentTime) : null,
    paused: m.paused, rate: m.playbackRate, readyState: m.readyState,
  }));
  return out;
}"""


def scan(target, verbose):
    found = []
    for f in target.frames:
        try:
            r = f.evaluate(PROBE)
        except Exception:
            continue
        hit = r.get("videoquizSubmit") or r.get("ansVideoquizAny") or r.get("ansVideoquiz") or r.get("optLabels")
        if hit or verbose:
            r["_frameUrl"] = (f.url or "")[:120]
            r["_isMain"] = f == target.main_frame
            found.append(r)
    return found


def show(r):
    print("  frame: %s%s" % (r.get("_frameUrl"), "  [主框架]" if r.get("_isMain") else ""))
    print("    视频#video=%s  音频#audio=%s  弹题提交按钮#videoquiz-submit=%s"
          % (r.get("hasVideo"), r.get("hasAudio"), r.get("videoquizSubmit")))
    print("    #video .ans-videoquiz=%s   .ans-videoquiz=%s   .ans-videoquiz-opt label=%s   .x-component-default=%s"
          % (r.get("ansVideoquiz"), r.get("ansVideoquizAny"), r.get("optLabels"), r.get("xComponents")))
    if r.get("containerVisible") is not None:
        print("    弹题容器可见: %s" % r.get("containerVisible"))
    if r.get("options"):
        print("    选项（input 类型决定题型）:")
        for i, o in enumerate(r["options"]):
            print("      [%d] type=%-9s checked=%-5s value=%-6s valueAttr=%-6s %s"
                  % (i, o.get("inputType"), o.get("checked"), o.get("value"), o.get("valueAttr"), o.get("text")))
        types = {o.get("inputType") for o in r["options"]}
        kind = "多选题" if "checkbox" in types else ("单选题/判断题" if "radio" in types else "未知（无 input？）")
        print("    => 由 DOM 推断题型: %s" % kind)
        vals = [o.get("valueAttr") for o in r["options"]]
        if vals.count("true") == 1:
            print("    [线索] 恰有一个选项 value=\"true\" —— 可能是页面自带的正确项标记（待确认）")
        elif vals.count("true") > 1:
            print("    [线索] 多个选项 value=\"true\" —— 不像是正确项标记")
        for kk in ("optionSelector", "submitSelector"):
            if r.get(kk):
                print("    命中的选择器 %s: %s" % (kk, r.get(kk)))
    if r.get("containerText"):
        print("    容器文本: %s" % r.get("containerText"))
    if r.get("submitHTML"):
        print("    提交按钮 HTML: %s" % r.get("submitHTML")[:200])
    for m in (r.get("media") or []):
        print("    媒体[%s]: 时长=%s 当前=%s 暂停=%s 倍速=%s readyState=%s"
              % (m["tag"], m["dur"], m["cur"], m["paused"], m["rate"], m["readyState"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="常驻轮询，弹题出现时输出结构并截图")
    ap.add_argument("--seconds", type=int, default=300, help="watch 最长持续时间")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--all-frames", action="store_true", help="连隐藏 iframe 也一起打印")
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(CDP, timeout=25000)
        pages = [pg for c in b.contexts for pg in c.pages]
        target = next((pg for pg in pages if "studentstudy" in (pg.url or "")), None)
        if target is None:
            print("[错误] 没找到 studentstudy 标签页；当前打开的页面：")
            for pg in pages:
                print("   " + (pg.url or "")[:140])
            sys.exit(1)
        print("[页面] %s\n" % target.url[:150])

        print("=== 当前弹题 DOM 状态 ===")
        for r in scan(target, args.all_frames):
            show(r)

        if not args.watch:
            print("\n（加 --watch 可常驻等待弹题出现）")
            b.close()
            return

        print("\n=== 进入监听：每 %.1fs 轮询，最多 %ds（出现弹题即输出并截图）===" % (args.interval, args.seconds))
        t0 = time.time()
        seen = False
        n = 0
        while time.time() - t0 < args.seconds:
            n += 1
            rows = scan(target, False)
            live = [r for r in rows if r.get("videoquizSubmit") or r.get("optLabels")]
            if live and not seen:
                seen = True
                print("\n🚨 检测到视频内弹题！（第 %d 轮，已等待 %.0fs）" % (n, time.time() - t0))
                for r in live:
                    show(r)
                try:
                    shot = LOGS / ("videoquiz-%d.png" % int(time.time()))
                    target.screenshot(path=str(shot), animations="disabled", timeout=30000)
                    print("    已截图: %s" % shot.name)
                except Exception as e:
                    print("    截图失败: %s" % str(e)[:80])
                # 记录 JSON 便于后续比对
                try:
                    (LOGS / ("videoquiz-%d.json" % int(time.time()))).write_text(
                        json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                break
            if n % 15 == 1:
                print("  ...第 %d 轮，无弹题（已等 %.0fs）" % (n, time.time() - t0))
            time.sleep(args.interval)
        if not seen:
            print("\n监听结束：%d 秒内未出现弹题。" % args.seconds)
        b.close()


if __name__ == "__main__":
    main()
