"""M15（重做刷满分）专用只读探针：抓取超星「作业/考试成绩页」的 DOM 契约。

为什么需要它：上游 ocsjs **没有**任何成绩/正确答案回收机制（已 grep 确认），
M15 必须从零实现，而实现的前提是知道成绩页里「题目 / 我的答案 / 正确答案 / 得分」
分别落在什么元素上。猜字段是错的（同架构的 EStudy 项目最初就是因此翻车）。

【严格只读】不点击、不提交、不修改页面状态。

用法：
    # 你先在浏览器里打开一个「已提交作业」的成绩页，然后：
    python tools\\cx_probe_score.py
    python tools\\cx_probe_score.py --out .logs\\score.json
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

ROOT = Path(r"E:\Code\ChaoXingStudy")
LOGS = ROOT / ".logs"
CDP = "http://127.0.0.1:20022"

# 可能的题目容器
QUESTION_SELECTORS = [".questionLi", ".TiMu", ".mark_item", ".questionWrap", "[class*='question']"]
# 可能承载「正确答案 / 我的答案 / 得分」的元素（按关键词扫 class/id）
KEYWORD_HINTS = ["score", "answer", "key", "right", "correct", "wrong", "mark", "result", "fraction", "grade"]


def scan(page):
    return page.evaluate(
        """(hints) => {
          const out = { url: location.href, title: document.title, candidates: [], counts: {} };

          // 1) 题目容器候选计数
          ['.questionLi','.TiMu','.mark_item','.questionWrap','[class*="question"]','.mark_answer','.answerBg','.mark_name']
            .forEach(sel => { try { out.counts[sel] = document.querySelectorAll(sel).length; } catch(e){} });

          // 2) 按关键词扫所有元素的 class/id，找承载得分/答案的节点
          const seen = new Set();
          document.querySelectorAll('*').forEach(el => {
            const cls = (el.className || '').toString();
            const id = el.id || '';
            const sig = cls + ' ' + id;
            if (!sig.trim()) return;
            const low = sig.toLowerCase();
            if (!hints.some(h => low.indexOf(h) >= 0)) return;
            const key = el.tagName + '|' + cls + '|' + id;
            if (seen.has(key)) return;
            seen.add(key);
            const text = (el.innerText || '').trim().replace(/\\s+/g, ' ');
            if (text.length > 120) return;
            out.candidates.push({ tag: el.tagName, cls: cls.slice(0,80), id: id.slice(0,60), text: text.slice(0,120), n: document.querySelectorAll('.'+cls.split(' ').filter(Boolean).join('.')).length });
          });
          out.candidates = out.candidates.slice(0, 120);

          // 3) 第一道题的完整 outerHTML（用于确认「我的答案/正确答案」的实际结构）
          const q = document.querySelector('.questionLi') || document.querySelector('.TiMu') || document.querySelector('.mark_item');
          out.firstQuestionHtml = q ? q.outerHTML.slice(0, 6000) : null;

          // 4) 页面里是否出现「正确答案」这类文案，以及它所在的父元素 class
          out.keyTextHits = [];
          document.querySelectorAll('*').forEach(el => {
            if (el.children.length > 3) return;
            const t = (el.innerText || '').trim();
            if (['正确答案','我的答案','参考答案','得分','满分','正确答案：','批语'].some(w => t.indexOf(w) >= 0) && t.length < 60) {
              out.keyTextHits.push({
                tag: el.tagName,
                cls: (el.className||'').toString().slice(0,80),
                parentCls: (el.parentElement && el.parentElement.className || '').toString().slice(0,80),
                text: t.slice(0,80)
              });
            }
          });
          out.keyTextHits = out.keyTextHits.slice(0, 40);
          return out;
        }""",
        KEYWORD_HINTS,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP)
        except Exception as e:
            print(f"[错误] 无法附着到 {CDP}：{e}")
            print("        请先运行 python tools\\cx_launch.py")
            sys.exit(1)

        pages = [pg for c in browser.contexts for pg in c.pages]
        target = next((pg for pg in pages if "chaoxing.com" in (pg.url or "")), None)
        if target is None:
            print("[错误] 没有找到 chaoxing.com 标签页。")
            sys.exit(1)

        print("=== 当前页面 ===")
        print("  " + target.url[:130])
        time.sleep(2)

        report = scan(target)

        print("\n=== 题目容器候选计数 ===")
        for k, v in report["counts"].items():
            print(f"  {k:<28} {v}")

        print("\n=== 关键词命中的候选元素（找得分/正确答案）===")
        for c in report["candidates"][:40]:
            print(f"  <{c['tag']}> .{c['cls'][:38]:<40} #{c['id'][:20]:<22} {c['text'][:50]}")

        print("\n=== 「正确答案/我的答案/得分」文案命中 ===")
        for c in report["keyTextHits"][:25]:
            print(f"  <{c['tag']}> .{c['cls'][:34]:<36} parent=.{c['parentCls'][:26]:<28} {c['text'][:40]}")

        print("\n=== 第一道题 outerHTML（前 1500 字符）===")
        print((report.get("firstQuestionHtml") or "(未找到题目容器)")[:1500])

        shot = LOGS / f"score-{int(time.time())}.png"
        try:
            target.screenshot(path=str(shot), animations="disabled", timeout=60000)
            print(f"\n=== 截图 ===\n  {shot}  ({shot.stat().st_size} bytes)")
        except Exception as e:
            print(f"\n[注意] 截图失败：{str(e)[:100]}")

        out = Path(args.out) if args.out else (LOGS / f"score-{int(time.time())}.json")
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n=== 报告 ===\n  {out}")
        print("\n本次为只读探针，未点击任何元素、未提交任何数据。")


if __name__ == "__main__":
    main()
