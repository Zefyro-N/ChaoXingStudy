# SPDX-FileCopyrightText: 2026 Zefyro-N
# SPDX-License-Identifier: MIT
"""只读探针：弄清「提交值要哪种字母」—— 读页面自身函数源码，不点击、不提交。

超星作业页的选项形如：
    <div class="answerBg" onclick="addChoice(this)" aria-label="D D选择"> ... </div>
可见顺序 A/B/C/D 与 aria-label 里的字母可能不一致（选项被页面打乱），
因此必须确认 input#answer<qid> 里最终写的到底是「可见字母」还是「原始字母」。

做法：把 window.addChoice / 提交函数的源码取出来看，同时打印一个未作答题目的
隐藏域初值、aria-label、可见字母 三者对照表。全程只读。

用法：python tools\\cx_probe_answer_semantics.py
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
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  const fnSrc = name => {
    try {
      const f = window[name];
      return typeof f === 'function' ? f.toString().replace(/\s+/g, ' ').slice(0, 1200) : null;
    } catch (e) { return 'ERR:' + e.message; }
  };

  // 取第一道单选题做对照
  const q = document.querySelector('.questionLi');
  let sample = null;
  if (q) {
    const qid = q.getAttribute('data');
    const optEls = Array.from(q.querySelectorAll('.answerBg'));
    sample = {
      qid,
      typename: q.getAttribute('typename'),
      answerInputId: 'answer' + qid,
      answerValue: (document.getElementById('answer' + qid) || {}).value,
      answertypeValue: (document.getElementById('answertype' + qid) || {}).value,
      visibleOrder: optEls.map((el, i) => {
        const aria = clean(el.getAttribute('aria-label'));
        // 可见字母通常来自 <i class="fl"> 或文本首字符
        const fl = el.querySelector('.fl, i, span');
        const visibleLetter = fl ? clean(fl.innerText).replace(/[.、．]/g, '') : '';
        return {
          pos: String.fromCharCode(65 + i),
          visibleLetter: visibleLetter.slice(0, 4),
          aria,
          ariaLetter: (aria.match(/^[A-J]/) || [''])[0],
          textHead: clean(el.innerText).slice(0, 40),
          hasImg: el.querySelectorAll('img').length,
        };
      }),
    };
  }

  // 页面里可能定义的相关函数
  const fns = {};
  ['addChoice', 'addChoiceKeyDown', 'submitWork', 'getAnswer', 'saveWork'].forEach(n => {
    const s = fnSrc(n);
    if (s) fns[n] = s;
  });

  // 是否能看到全局的选项字母映射表
  const globals = Object.keys(window).filter(k => /answer|choice|option/i.test(k) && /^(?!on)/.test(k)).slice(0, 25);

  return { sample, fns, globals };
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
            print("  ❌ 作业页不见了，请重新打开")
            return
        print(f"  页面: {page.title()}")
        for fr in page.frames:
            try:
                data = fr.evaluate(JS)
            except Exception:
                continue
            if not data or not data.get("sample"):
                continue
            s = data["sample"]
            print(f"\n  === 样本题 qid={s['qid']} [{s['typename']}] ===")
            print(f"  {s['answerInputId']} 当前值: {s['answerValue']!r}   answertype: {s['answertypeValue']!r}")
            print(f"  {'位':<3}{'可见字母':<10}{'aria首字母':<12}{'选项文本':<24}{'图'}")
            for o in s["visibleOrder"]:
                print(f"  {o['pos']:<3}{o['visibleLetter'] or '-':<10}{o['ariaLetter'] or '-':<12}{o['textHead'][:22]:<24}{o['hasImg']}")

            print(f"\n  === 页面函数源码 ===")
            for name, src in data["fns"].items():
                print(f"\n  -- {name}() --")
                print("     " + src[:900])
            if data["globals"]:
                print(f"\n  含 answer/choice 的全局变量: {data['globals']}")

            out = ROOT / ".logs" / f"answer-semantics-{int(time.time())}.json"
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"\n  完整 JSON: {out}")
            break
        browser.close()


if __name__ == "__main__":
    main()
