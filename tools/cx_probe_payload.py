# SPDX-FileCopyrightText: 2026 Zefyro-N
# SPDX-License-Identifier: MIT
"""只读探针：按 OCS 自己的选择器，复现「实际发给模型的题干 + 选项 + 图片」。

选择器来源（packages/scripts/src/projects/cx.ts，作业作答页分支）：
    root    : '.questionLi'
    标题    : '.mark_name'（作业页）/ '.Zy_TItle .clearfix'（章节页）
    选项    : '.answerBg .answer_p, .textDIV, .eidtDiv'

本探针不点不提交，只输出：
    1) 每题模型会收到的题干文本（截断显示）
    2) 每题模型会收到的选项文本
    3) 题干/选项里的图片 URL 数量，并下载前 2 张确认可读（大小 + 尺寸）

用法：python tools\\cx_probe_payload.py [--limit 4]
"""
import argparse
import json
import sys
import time
import urllib.request
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
    const h3 = q.querySelector('.mark_name');
    const stemImgs = h3 ? Array.from(h3.querySelectorAll('img')).map(x => x.getAttribute('src') || x.getAttribute('data-original')) : [];
    const stemText = clean(h3 ? h3.innerText : '');
    const optEls = Array.from(q.querySelectorAll('.answerBg .answer_p, .textDIV, .eidtDiv'));
    const opts = optEls.map(el => {
      const imgs = Array.from(el.querySelectorAll('img')).map(x => x.getAttribute('src') || x.getAttribute('data-original'));
      return { text: clean(el.innerText), imgs, imgCount: imgs.length };
    });
    const allImgs = Array.from(q.querySelectorAll('img')).map(x => x.getAttribute('src') || x.getAttribute('data-original'));
    out.push({
      idx: i + 1, qid,
      typename: q.getAttribute('typename'),
      answertype: (document.getElementById('answertype' + qid) || {}).value,
      stemText, stemImgs,
      opts,
      allImgCount: allImgs.length,
      allImgs,
    });
  });
  return { total: out.length, questions: out };
}
"""


def head_ok(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = r.read()
        return f"{len(data)} bytes"
    except Exception as exc:
        return f"ERR {str(exc)[:40]}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=4)
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
            print("  ❌ 没取到 .questionLi")
            return

        qs = data["questions"]
        print(f"  题量: {data['total']}\n")
        for q in qs[: args.limit]:
            print(f"  ── Q{q['idx']} [{q['typename']}] 图片总数={q['allImgCount']} ──")
            print(f"     题干(模型可见): {q['stemText'][:110]!r}")
            print(f"     题干图片: {len(q['stemImgs'])} 张")
            for j, o in enumerate(q["opts"]):
                print(f"       {chr(65+j)}. 文本={o['text'][:40]!r} 图={o['imgCount']}")
            for u in q["allImgs"][:2]:
                print(f"     [下载验证] {u[:78]} → {head_ok(u)}")
            print()

        # 汇总：文本信息量 vs 图片信息量
        tiny_opts = sum(1 for q in qs if q["opts"] and all(len(o["text"]) <= 2 for o in q["opts"]))
        empty_stem = sum(1 for q in qs if len(q["stemText"]) <= 20)
        has_img = sum(1 for q in qs if q["allImgCount"] > 0)
        print(f"  === 汇总（{data['total']} 题）===")
        print(f"  选项文本都只有 1-2 个字（纯字母）: {tiny_opts}")
        print(f"  题干文本 ≤20 字（信息基本为空）  : {empty_stem}")
        print(f"  含图片的题（图片是唯一信息源）    : {has_img}")

        out = ROOT / ".logs" / f"payload-{int(time.time())}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  完整 JSON: {out}")
        browser.close()


if __name__ == "__main__":
    main()
