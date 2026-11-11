# SPDX-FileCopyrightText: 2026 Zefyro-N
# SPDX-License-Identifier: MIT
"""只读探针：把一个选项的完整 HTML 与内部属性 dump 出来，定位 data 属性在哪。

用法：python tools\\cx_probe_option_html.py
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

JS = r"""
() => {
  const q = document.querySelector('.questionLi');
  if (!q) return { error: 'no-questionLi' };
  const qid = q.getAttribute('data');
  const opt = q.querySelector('.answerBg');
  if (!opt) return { error: 'no-answerBg' };
  // 该选项内所有节点的属性
  const nodes = Array.from(opt.querySelectorAll('*')).map(el => {
    const attrs = {};
    for (const a of el.attributes) attrs[a.name] = a.value;
    return { tag: el.tagName, cls: (el.className && el.className.toString()) || '', attrs };
  });
  return {
    qid,
    optionHtml: opt.outerHTML.replace(/\s+/g, ' '),
    optionAttrs: (() => { const o = {}; for (const a of opt.attributes) o[a.name] = a.value; return o; })(),
    nodes,
    // 同类所有选项的 data / class 概况
    all: Array.from(q.querySelectorAll('.answerBg')).map((el, i) => ({
      pos: String.fromCharCode(65 + i),
      cls: (el.className || '').toString().replace(/\s+/g, ' '),
      data: el.getAttribute('data'),
      qid: el.getAttribute('qid'),
      innerData: (el.querySelector('[data]') || {}).getAttribute ? el.querySelector('[data]').getAttribute('data') : null,
    })),
  };
}
"""


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        page = None
        for pg in browser.contexts[0].pages:
            if "dowork" in pg.url or "work" in pg.url:
                page = pg
        if page is None:
            print("  ❌ 作业页不见了")
            return
        data = None
        for fr in page.frames:
            try:
                d = fr.evaluate(JS)
            except Exception:
                continue
            if d and not d.get("error"):
                data = d
                break
        if data is None:
            print("  ❌ 未取到 .answerBg")
            return

        print(f"  qid={data['qid']}")
        print(f"\n  === 选项外层属性 ===")
        for k, v in data["optionAttrs"].items():
            print(f"    {k} = {v!r}")
        print(f"\n  === 选项完整 HTML ===")
        print("    " + data["optionHtml"][:900])
        print(f"\n  === 内部节点（带属性）===")
        for n in data["nodes"][:10]:
            print(f"    <{n['tag']} class={n['cls'][:40]!r}> attrs={json.dumps(n['attrs'], ensure_ascii=False)[:150]}")
        print(f"\n  === 本题目所有选项的 data ===")
        for a in data["all"]:
            print(f"    {a['pos']}  cls={a['cls'][:50]!r}  data={a['data']!r}  innerData={a['innerData']!r}")

        out = ROOT / ".logs" / f"option-html-{int(time.time())}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  完整 JSON: {out}")
        browser.close()


if __name__ == "__main__":
    main()
