# SPDX-FileCopyrightText: 2026 Zefyro-N
# SPDX-License-Identifier: MIT
"""只读探针：量化「题干/选项是否只能靠图片」——决定要不要走截图答题路线。

真实结构（2026-11 实测，超星作业作答页 frame[0]）：
  题目容器 : div.questionLi.fontLabel.singleQuesId  [typename="单选题"] [id="question<qid>"] [data="<qid>"]
  题干     : h3.mark_name > p > img   ← 线性代数题干整段是 PNG
  选项     : div.clearfix.answerBg.workTextWrap  [onclick="addChoice(this)"] [role="radio"] [aria-label="B B、xxx,选择"]
  隐藏字段 : input#answertype<qid> / input#answer<qid>

用法：
    python tools\\cx_probe_options.py            # 统计题量、题型、文本可用性
    python tools\\cx_probe_options.py --full     # 打印前 6 题每个选项的明细
"""
import argparse
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

EXTRACT_JS = r"""
() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const qs = Array.from(document.querySelectorAll('.questionLi'));
  const out = qs.map((q, i) => {
    const qid = q.getAttribute('data') || (q.id || '').replace('question', '');
    const typeName = q.getAttribute('typename') || '';
    const h3 = q.querySelector('h3.mark_name');
    const stemImg = h3 ? h3.querySelectorAll('img').length : 0;
    const stemText = clean(h3 ? h3.innerText : '');
    const opts = Array.from(q.querySelectorAll('.answerBg')).map(li => {
      const aria = clean(li.getAttribute('aria-label'));
      const text = clean(li.innerText);
      const img = li.querySelectorAll('img').length;
      const math = li.querySelectorAll('math, .MathJax, svg').length;
      return { aria: aria.slice(0, 60), text: text.slice(0, 60), img, math };
    });
    const inputs = Array.from(q.querySelectorAll('input[type=checkbox], input[type=radio]'))
      .map(c => ({ name: c.name, cls: c.className.slice(0, 30) }));
    return {
      index: i + 1, qid, typeName,
      stemImg, stemLen: stemText.length,
      stemHead: stemText.slice(0, 70),
      optionCount: opts.length,
      opts,
      inputCount: inputs.length,
      inputNames: inputs.slice(0, 4).map(x => x.name),
    };
  });
  return { total: out.length, questions: out };
}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "dowork" in pg.url or "work" in pg.url:
                page = pg
        if page is None:
            print("  ❌ 作业页不见了，请重新打开")
            return
        print(f"  页面: {page.title()}")
        data = None
        for fr in page.frames:
            try:
                d = fr.evaluate(EXTRACT_JS)
            except Exception:
                continue
            if d and d.get("total"):
                data = d
                data["frameUrl"] = fr.url[:100]
                break
        if data is None:
            print("  ❌ 没有找到 .questionLi")
            return

        qs = data["questions"]
        print(f"  题量: {data['total']}")
        types = {}
        for q in qs:
            types[q["typeName"]] = types.get(q["typeName"], 0) + 1
        print(f"  题型: {types}")

        imgStem = sum(1 for q in qs if q["stemImg"] > 0)
        imgOpt = sum(1 for q in qs if any(o["img"] for o in q["opts"]))
        emptyOptText = sum(1 for q in qs if q["opts"] and all(len(o["text"]) < 3 for o in q["opts"]))
        ariaOk = sum(1 for q in qs if any(len(o["aria"]) > 6 for o in q["opts"]))
        noOpts = sum(1 for q in qs if q["optionCount"] == 0)
        print(f"\n  === 关键统计 ===")
        print(f"  题干含图片的题 : {imgStem}/{data['total']}   ← 文本路径必然残缺")
        print(f"  选项含图片的题 : {imgOpt}/{data['total']}")
        print(f"  选项文本几乎为空: {emptyOptText}/{data['total']}")
        print(f"  选项 aria-label 可用: {ariaOk}/{data['total']}")
        print(f"  没有 .answerBg 选项: {noOpts}/{data['total']}")

        if args.full:
            for q in qs[:6]:
                print(f"\n  Q{q['index']} [{q['typeName']}] qid={q['qid']} 题干图={q['stemImg']} 文本长={q['stemLen']} 选项={q['optionCount']}")
                print(f"     题干文本: {q['stemHead']!r}")
                for j, o in enumerate(q["opts"]):
                    print(f"       {chr(65+j)}. text={o['text']!r} img={o['img']} aria={o['aria']!r}")

        out = ROOT / ".logs" / f"options-{int(time.time())}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  完整 JSON: {out}")
        browser.close()


if __name__ == "__main__":
    main()
