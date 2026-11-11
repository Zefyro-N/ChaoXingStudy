# SPDX-FileCopyrightText: 2026 Zefyro-N
# SPDX-License-Identifier: MIT
"""只读探针：导出「可见位 ↔ 选项 data 属性 ↔ aria-label」映射表。

依据（实测 addChoice 源码）：
    $(".choice"+qid).each(function(){ if (hasClass('check_answer'))
        choiceContent += $(this).attr("data"); });
    $("#answer"+qid).val(choiceContent);
→ 提交值是选中选项的 data 属性拼接，与可见字母无关。

本探针只读 DOM，不点击、不修改。

用法：python tools\\cx_probe_choice_data.py
"""
import argparse
import json
import re
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
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const out = [];
  document.querySelectorAll('.questionLi').forEach((q, i) => {
    const qid = q.getAttribute('data');
    const opts = Array.from(q.querySelectorAll('.answerBg'));
    out.push({
      idx: i + 1,
      qid,
      typename: q.getAttribute('typename'),
      answertype: (document.getElementById('answertype' + qid) || {}).value,
      answer: (document.getElementById('answer' + qid) || {}).value,
      options: opts.map((el, j) => {
        const aria = clean(el.getAttribute('aria-label'));
        const numOpt = el.querySelector('.num_option');
        return {
          pos: String.fromCharCode(65 + j),
          data: el.getAttribute('data'),
          qid: el.getAttribute('qid'),
          qtype: el.getAttribute('qtype'),
          aria,
          numLetter: numOpt ? clean(numOpt.innerText).replace(/[.、．]/g, '').slice(0, 3) : '',
          text: clean(el.innerText).replace(/\s+/g, ' ').slice(0, 50),
          img: el.querySelectorAll('img').length,
        };
      }),
    });
  });
  return { total: out.length, questions: out };
}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="打印全部题目（默认前 6 题）")
    args = ap.parse_args()

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
            if d and d.get("total"):
                data = d
                break
        if data is None:
            print("  ❌ 页面里没有 .questionLi（可能被 403 或未加载）")
            return

        qs = data["questions"]
        print(f"  题量: {data['total']}")
        show = qs if args.all else qs[:6]
        for q in show:
            print(f"\n  Q{q['idx']} [{q['typename']}] qid={q['qid']} answertype={q['answertype']} 当前答案={q['answer']!r}")
            print(f"    {'可见':<4}{'data':<8}{'aria首字母':<10}{'num_option':<12}{'文本':<20}图")
            for o in q["options"]:
                aria_letter = (re.match(r"^[A-J]", o["aria"]) or [""])[0] if re.match(r"^[A-J]", o["aria"]) else ""
                print(f"    {o['pos']:<4}{str(o['data']):<8}{aria_letter:<10}{o['numLetter']:<12}{o['text'][:18]:<20}{o['img']}")

        # 一致性检查：data 是否 == 可见位？是否等于 aria 首字母？
        same_pos = same_aria = other = 0
        for q in qs:
            for o in q["options"]:
                aria_letter = (re.match(r"^[A-J]", o["aria"]) or [""])[0] if re.match(r"^[A-J]", o["aria"]) else ""
                if o["data"] == o["pos"]:
                    same_pos += 1
                elif aria_letter and o["data"] == aria_letter:
                    same_aria += 1
                else:
                    other += 1
        print(f"\n  === data 属性语义判定 ===")
        print(f"  data == 可见字母 : {same_pos}")
        print(f"  data == aria首字母: {same_aria}")
        print(f"  其它            : {other}")

        out = ROOT / ".logs" / f"choice-data-{int(time.time())}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  完整 JSON: {out}")
        browser.close()


if __name__ == "__main__":
    main()
