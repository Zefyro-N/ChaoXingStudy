# SPDX-FileCopyrightText: 2026 Zefyro-N
# SPDX-License-Identifier: MIT
"""只读探针：把作业页各 frame 的真实 DOM 结构 dump 出来（不猜选择器）。

输出：
  1) 每个 frame 的 url / 文本长度 / .TiMu 计数
  2) 题目密集的 frame 里，第一道题的 className、id、outerHTML 片段
  3) 该题内部所有元素的 class 名统计（定位"选项"到底是什么标签）

用法：python tools\\cx_probe_struct.py
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:20022"
ROOT = Path(r"E:\Code\ChaoXingStudy")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FRAME_INFO_JS = r"""
() => {
  const n = s => document.querySelectorAll(s).length;
  return {
    textLen: document.body ? document.body.innerText.length : 0,
    hasWorkTitle: !!document.body && /单选题|多选题|判断题|填空题/.test(document.body.innerText),
    TiMu: n('.TiMu'),
    questionLi: n('li.questionLi, .questionLi'),
    Zy_TItle: n('.Zy_TItle'),
    markCount: n('.mark_name, .colorShallow, .answerBg'),
    stemLike: n('.fontLabel, .qtContent, .stem_content'),
    bodyClasses: (document.body && document.body.className || '').slice(0, 120),
  };
}
"""

DETAIL_JS = r"""
() => {
  // 找"最像题目"的容器：包含 (单选题) 且内部有若干 li 的最小块
  const all = Array.from(document.querySelectorAll('div,li,section'));
  const cands = all.filter(e => {
    const t = (e.innerText || '');
    return t.length > 40 && t.length < 2500 && /[(（](单选题|多选题|判断题|填空题|简答题|计算题)[)）]/.test(t);
  });
  if (!cands.length) return { error: 'no-candidate' };
  // 取最深的那个（子元素最少的）
  cands.sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);
  const el = cands[0];
  const classStats = {};
  el.querySelectorAll('*').forEach(c => {
    const cn = (c.className && typeof c.className === 'string') ? c.className.trim().split(/\s+/)[0] : '';
    if (!cn) return;
    classStats[cn] = (classStats[cn] || 0) + 1;
  });
  const lis = Array.from(el.querySelectorAll('li')).map(li => ({
    cls: (li.className || '').slice(0, 60),
    text: (li.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 80),
    html: li.innerHTML.replace(/\s+/g, ' ').slice(0, 220),
  }));
  const imgs = Array.from(el.querySelectorAll('img')).map(i => ({
    src: (i.getAttribute('src') || '').slice(0, 90),
    cls: (i.className || '').slice(0, 40),
  }));
  return {
    tag: el.tagName,
    cls: (el.className || '').slice(0, 120),
    id: el.id || '',
    outerHead: el.outerHTML.replace(/\s+/g, ' ').slice(0, 900),
    classStats,
    liCount: lis.length,
    lis,
    imgCount: imgs.length,
    imgs: imgs.slice(0, 8),
  };
}
"""


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "dowork" in pg.url or "work" in pg.url:
                page = pg
        if page is None:
            print("  ❌ 作业页不见了（可能被关了），请重新打开作业页")
            return
        print(f"  页面: {page.title()}  frames={len(page.frames)}")
        dump = []
        for i, fr in enumerate(page.frames):
            try:
                info = fr.evaluate(FRAME_INFO_JS)
            except Exception as exc:
                info = {"error": str(exc)[:80]}
            info["frameIndex"] = i
            info["url"] = fr.url[:130]
            dump.append(info)
            flag = "  ★" if info.get("hasWorkTitle") else "   "
            print(f"{flag} frame[{i}] textLen={info.get('textLen')} TiMu={info.get('TiMu')} "
                  f"questionLi={info.get('questionLi')} Zy_TItle={info.get('Zy_TItle')}")
            print(f"      {info['url']}")

        # 在最像题的 frame 里 dump 结构
        best = max(
            [d for d in dump if d.get("hasWorkTitle") and not d.get("error")],
            key=lambda d: d.get("textLen", 0),
            default=None,
        )
        if best is None:
            print("  ❌ 没有 frame 含题目文本")
            return
        fr = page.frames[best["frameIndex"]]
        print(f"\n  === 在 frame[{best['frameIndex']}] 里 dump 题目结构 ===")
        detail = fr.evaluate(DETAIL_JS)
        if detail.get("error"):
            print("  ", detail["error"])
        else:
            print(f"  容器: <{detail['tag']} class='{detail['cls']}' id='{detail['id']}'>")
            print(f"  li 数: {detail['liCount']}  img 数: {detail['imgCount']}")
            print(f"\n  -- class 统计（前 18）--")
            for k, v in sorted(detail["classStats"].items(), key=lambda kv: -kv[1])[:18]:
                print(f"     {v:>3}  {k}")
            print(f"\n  -- li 明细（前 6）--")
            for j, li in enumerate(detail["lis"][:6]):
                print(f"     li[{j}] cls={li['cls']!r} text={li['text']!r}")
                print(f"            html={li['html'][:180]}")
            print(f"\n  -- img（前 6）--")
            for im in detail["imgs"]:
                print(f"     src={im['src']!r} cls={im['cls']!r}")
            print(f"\n  -- outerHTML 片段（900 字符）--")
            print("     " + detail["outerHead"])

        out = ROOT / ".logs" / f"struct-{int(time.time())}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps({"frames": dump, "detail": detail}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  完整 JSON: {out}")
        browser.close()


if __name__ == "__main__":
    main()
