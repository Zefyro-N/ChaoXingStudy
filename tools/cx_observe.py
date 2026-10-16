"""阶段 A：只读观测。附着到已登录的浏览器，抓取学习通课程页的真实结构。

【严格只读】本脚本不会：
  - 点击任何会完成任务点的元素
  - 调用 btnBlueSubmit / submitCheckTimes / finishJob / saveln 等任何提交或上报函数
  - 修改任何 localStorage / cookie / DOM 状态
  - 拖动任何滑块、识别任何验证码

它只做：读 DOM、读 iframe 树、读顶层 attachments、数混淆字体、扫验证码特征、截图。

用法：
    python tools\\cx_observe.py                # 观测当前打开的学习通标签页
    python tools\\cx_observe.py --list          # 只列出页面与 frame 清单
    python tools\\cx_observe.py --out x.json    # 结果落盘
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
CDP = "http://127.0.0.1:9222"

# docs/cx-mechanisms.md §2.2 的任务点判据
JOB_PROBES = {
    "video_or_audio": "#video,#audio",
    "chapter_test": ".TiMu",
    "image_read": "#img.imglook",
    "ppt_with_audio": ".swiper-container",
    "hyperlink": "#hyperlink",
    "time_reader": 'iframe[name="bookifame"][src*="timing"]',
}

# docs/cx-mechanisms.md §7
FONT_PROBE = ".font-cxsecret"

# SAFETY.detectCaptcha 的启发式特征（与 cx-helper.user.js 保持一致）
CAPTCHA_PROBES = [
    "img[src*='captcha']", "img[src*='validate']",
    ".verifyimg", ".validateCode", ".captcha",
    "#verifyCode", "#validateCode", "#captcha",
    "input[name='validateCode']", "input[name='verifyCode']", "input[name='captcha']",
    ".slider", ".nc-container", ".geetest_panel", ".verify-slider", ".slide-verify",
    ".yzm", ".yzmImg", ".picCode", "#yzmImg", ".yzm-tip", ".refresh-code",
]

CAPTCHA_TEXT = ["请输入验证码", "人机验证", "拖动滑块", "完成验证", "验证码校验"]

# docs/cx-mechanisms.md §3 目录/模式判据
CATALOG_PROBES = {
    "special_mode(闯关/解锁)": ".catalog_points_sa,.catalog_points_er",
    "chapter_items": '[onclick^="getTeacherAjax"]',
    "active_chapter": ".posCatalog_active",
    "final_chapter_marker": ".posCatalog_select",
    "tab_bar(prev_ul li)": ".prev_ul li",
    "chapter_completed_icon": ".icon_Completed",
    "quiz_status": ".testTit_status",
}


def probe(doc_root, selector: str) -> dict:
    """返回命中数量与首个元素的简要文本，绝不点击。"""
    try:
        els = doc_root.query_selector_all(selector)
    except Exception as e:
        return {"count": -1, "error": str(e)[:120]}
    out = {"count": len(els)}
    if els:
        try:
            t = (els[0].inner_text() or "").strip().replace("\n", " ")
            out["first_text"] = t[:160]
        except Exception:
            pass
    return out


def scan_frame(frame, depth: int) -> dict:
    info = {
        "depth": depth,
        "url": frame.url,
        "name": frame.name,
        "jobs": {},
        "catalog": {},
        "font_cxsecret": 0,
        "captcha": {"selectors": {}, "text": []},
    }
    try:
        root = frame
    except Exception:
        return info

    for label, sel in JOB_PROBES.items():
        r = probe(root, sel)
        if r.get("count", 0) > 0:
            info["jobs"][label] = r

    for label, sel in CATALOG_PROBES.items():
        r = probe(root, sel)
        if r.get("count", 0) > 0:
            info["catalog"][label] = r

    r = probe(root, FONT_PROBE)
    info["font_cxsecret"] = r.get("count", 0)

    for sel in CAPTCHA_PROBES:
        r = probe(root, sel)
        if r.get("count", 0) > 0:
            info["captcha"]["selectors"][sel] = r.get("count")

    try:
        body = root.query_selector("body")
        txt = (body.inner_text() if body else "")[:20000]
        info["captcha"]["text"] = [w for w in CAPTCHA_TEXT if w in txt]
    except Exception:
        pass
    return info


# [H1/H3] 翻页入口候选：用于校正图片阅读 / 文档 PDF 的翻阅入口（目前是启发式，需实测证据）
PAGER_HINTS = ["next", "prev", "page", "pager", "arrow", "flip", "turn", "swiper", "book"]


def scan_pagers(frame):
    return frame.evaluate(
        """(hints) => {
          const out = [];
          document.querySelectorAll('*').forEach(el => {
            const cls = (el.className || '').toString();
            const id = el.id || '';
            const sig = (cls + ' ' + id).toLowerCase();
            if (!sig.trim()) return;
            if (!hints.some(h => sig.indexOf(h) >= 0)) return;
            if (el.children.length > 2) return;
            const r = el.getBoundingClientRect();
            out.push({
              tag: el.tagName, cls: cls.slice(0, 60), id: id.slice(0, 40),
              text: (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 30),
              visible: !!(el.offsetWidth || el.offsetHeight),
              w: Math.round(r.width), h: Math.round(r.height)
            });
          });
          return out.slice(0, 80);
        }""",
        PAGER_HINTS,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="只列页面与 frame 清单")
    ap.add_argument("--out", default=None, help="结果写入的 JSON 路径")
    args = ap.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP)
        except Exception as e:
            print(f"[错误] 无法附着到 {CDP}：{e}")
            print("        请先运行 python tools\\cx_launch.py")
            sys.exit(1)

        contexts = browser.contexts
        pages = [pg for c in contexts for pg in c.pages]
        if not pages:
            print("[错误] 没有打开的标签页")
            sys.exit(1)

        print("=== 打开的标签页 ===")
        for i, pg in enumerate(pages):
            try:
                print(f"  [{i}] {pg.title()[:60]!r}  {pg.url[:110]}")
            except Exception:
                print(f"  [{i}] (读取失败)")

        # 选一个学习通页面
        target = None
        for pg in pages:
            if "chaoxing.com" in (pg.url or ""):
                target = pg
                break
        if target is None:
            print("\n[提示] 没有找到 chaoxing.com 的标签页。请在浏览器里打开学习通课程播放页后重跑。")
            sys.exit(0)

        print(f"\n=== 观测目标 ===\n  {target.url}")
        try:
            target.wait_for_load_state("load", timeout=15000)
        except Exception:
            pass
        time.sleep(2)

        if args.list:
            print("\n=== Frame 清单 ===")
            for f in target.frames:
                print(f"  {f.url[:120]}")
            sys.exit(0)

        print(f"\n=== 截图 ===")
        shot = LOGS / f"observe-{int(time.time())}.png"
        shot_ok = False
        # 超星个人空间等页面有持续加载的资源，默认 30s 超时会挂：加固并允许失败继续
        for kw in ({"animations": "disabled", "timeout": 60000},
                   {"animations": "disabled", "caret": "initial", "timeout": 120000}):
            try:
                target.screenshot(path=str(shot), full_page=False, **kw)
                shot_ok = True
                break
            except Exception as e:
                print(f"  截图未完成，重试：{str(e)[:110]}")
        if shot_ok:
            print(f"  {shot}  ({shot.stat().st_size} bytes)")
        else:
            print("  截图仍失败（页面有持续加载资源）→ 跳过截图，继续 DOM 探针")

        # 若停在个人空间，枚举课程入口（只读，不点击）
        course_links = []
        if "i.chaoxing.com" in (target.url or ""):
            print("\n=== 个人空间：课程入口枚举（只读，未点击）===")
            try:
                course_links = target.evaluate(
                    """() => {
                      const out = [];
                      document.querySelectorAll('a[href]').forEach(a => {
                        const h = a.getAttribute('href') || '';
                        if (/mycourse|courseId=|course\\//i.test(h)) {
                          out.push({
                            text: (a.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 60),
                            href: h.slice(0, 220)
                          });
                        }
                      });
                      return out.slice(0, 40);
                    }""")
                if course_links:
                    for l in course_links:
                        print(f"  {l['text'][:38]:<40} {l['href']}")
                else:
                    print("  首页未直接找到课程链接（课程列表可能在 iframe 内，或需点『课程』进入）")
            except Exception as e:
                print(f"  枚举失败：{str(e)[:110]}")

        frames_report = []
        print("\n=== 逐 frame 探针（只读） ===")
        for f in target.frames:
            depth = f.url.count("/")
            r = scan_frame(f, depth)
            frames_report.append(r)
            hits = list(r["jobs"].keys())
            if hits or r["font_cxsecret"] or r["captcha"]["selectors"] or r["captcha"]["text"] or r["catalog"]:
                print(f"\n  ── frame {f.url[:100]}")
                if hits:
                    for k in hits:
                        print(f"     任务点[{k}] × {r['jobs'][k]['count']}  {str(r['jobs'][k].get('first_text',''))[:70]}")
                for k, v in r["catalog"].items():
                    print(f"     目录[{k}] × {v['count']}")
                if r["font_cxsecret"]:
                    print(f"     ⚠️ 混淆字体 .font-cxsecret × {r['font_cxsecret']}")
                if r["captcha"]["selectors"]:
                    print(f"     ⚠️ 验证码特征: {r['captcha']['selectors']}")
                if r["captcha"]["text"]:
                    print(f"     ⚠️ 验证码文案: {r['captcha']['text']}")

        # 顶层 attachments
        att = None
        try:
            att = target.evaluate("() => (window.attachments || []).map(a => ({"
                                 "jobid: a.jobid, _jobid: a.property && a.property._jobid,"
                                 "mid: a.property && a.property.mid,"
                                 "name: (a.property && (a.property.name || a.property.title)) || null,"
                                 "isPassed: a.isPassed, hasJob: !!a.job, job: a.job || null }))")
            print(f"\n=== 顶层 attachments × {len(att)} ===")
            for a in att[:40]:
                print(f"  jobid={a['jobid']} _jobid={a['_jobid']} mid={a['mid']} passed={a['isPassed']} "
                      f"hasJob={a['hasJob']} job={a['job']} name={str(a['name'])[:50]}")
        except Exception as e:
            print(f"\n[注意] 读 attachments 失败：{str(e)[:120]}")

        font_global = None
        try:
            font_global = target.evaluate(
                "() => Array.from(document.querySelectorAll('style')).map(s=>s.textContent||'')"
                ".filter(t=>t.includes('font-cxsecret')).map(t=>t.slice(0,300))")
            if font_global:
                print(f"\n=== @font-face(font-cxsecret) 定义 × {len(font_global)} ===")
                for t in font_global[:2]:
                    print("  " + t.replace("\n", " ")[:280])
        except Exception:
            pass

        # [H1/H3] 抓翻页器候选（图片阅读 / 文档 PDF 的翻阅入口）
        print("\n=== 翻页入口候选（H1/H3 校正用）===")
        pager_report = {}
        for f in target.frames:
            try:
                cands = scan_pagers(f)
            except Exception:
                continue
            vis = [c for c in cands if c.get("visible")]
            if vis:
                pager_report[f.url[:120]] = vis
                print(f"\n  ── frame {f.url[:100]}")
                for c in vis[:25]:
                    print(
                        f"     <{c['tag']}> .{c['cls'][:34]:<36} #{c['id'][:18]:<20} "
                        f"{c['w']}x{c['h']} {c['text'][:24]}"
                    )
        if not pager_report:
            print("  (未找到可见的翻页候选)")

        report = {
            "observed_url": target.url,
            "screenshot": str(shot) if shot_ok else None,
            "screenshot_ok": shot_ok,
            "course_links": course_links,
            "frames": frames_report,
            "attachments": att,
            "pagers": pager_report,
            "note": "本次为只读观测，未点击任何完成任务点的元素，未提交任何数据。",
        }
        out = Path(args.out) if args.out else (LOGS / f"observe-{int(time.time())}.json")
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n=== 报告 ===\n  {out}")
        print("\n本次为只读观测，未点击任何完成任务点的元素，未提交任何数据。")
        print("浏览器保持打开，未关闭。")


if __name__ == "__main__":
    main()
