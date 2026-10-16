"""读取油猴中【已安装脚本的实际内容】，确认装的是不是含 M16 的最新构建。

为什么需要：dashboard 的「878 KB / 5 min」在两个构建下都一样，无法区分版本；
而「点脚本名 → 编辑」能拿到真实源码，检索标记即可确定。

【只读】只打开编辑器读取内容，不保存、不修改。

用法：
    python tools\\cx_check_installed_content.py
"""
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"
LOGS = Path(r"E:\Code\ChaoXingStudy\.logs")
TM_ID = "iikmkjmpaadaobahmlepeloendndfphd"
DASHBOARD = f"chrome-extension://{TM_ID}/options.html#nav=dashboard"

# 用这些标记判断装的是哪一版
MARKERS = [
    ("M17 解密等待+校验", "decryptFontsWithRetry"),
    ("M17 解密结果日志", "字体解密成功"),
    ("M16 章节测验解密调用", "章节测验字体解密失败"),
    ("M14 作业考试闸门", "cxWorkGate"),
    ("M13 截图兜底", "captureElementAsDataUrl"),
    ("M12 图片题多模态", "image_url"),
    ("M12 图片题开关标签", "允许图片题"),
    ("M9 finishJob 开关", "cxAllowFinishJob"),
    ("M5 弹题走模型", "answerVideoQuiz"),
    ("M3 倍速锁定", "本分支锁定 1.0x"),
    ("M2 模型绑定", "deepseek-v4.1-flash"),
    ("M1 @connect", "@connect"),
]

READ_EDITOR = """() => {
  // Tampermonkey 编辑器：优先取 CodeMirror，退化到 textarea
  const out = { cm: 0, ta: 0, len: 0, text: '' };
  try {
    if (window.CodeMirror) {
      const insts = document.querySelectorAll('.CodeMirror');
      out.cm = insts.length;
      let s = '';
      insts.forEach(el => { if (el.CodeMirror) s += el.CodeMirror.getValue(); });
      if (s) { out.len = s.length; out.text = s; return out; }
    }
  } catch (e) {}
  const tas = Array.from(document.querySelectorAll('textarea'));
  out.ta = tas.length;
  let best = '';
  tas.forEach(t => { if ((t.value || '').length > best.length) best = t.value || ''; });
  out.len = best.length;
  out.text = best;
  return out;
}"""


def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp(CDP, timeout=20000)
        except Exception as e:
            print("[错误] 无法附着：%s" % e)
            sys.exit(1)
        ctx = b.contexts[0]
        pg = ctx.new_page()
        try:
            print("=== 打开油猴 dashboard ===")
            pg.goto(DASHBOARD, wait_until="domcontentloaded", timeout=45000)
            time.sleep(4)
            print("  标题: %r" % pg.title())

            print("\n=== 点击脚本名进入编辑器 ===")
            clicked = False
            for name in ["OCS 网课助手", "OCS"]:
                for how in ("link", "button"):
                    try:
                        loc = pg.get_by_role(how, name=name, exact=False)
                        if loc.count() > 0:
                            loc.first.click(timeout=10000)
                            clicked = True
                            print("  已点击 %s '%s'" % (how, name))
                            break
                    except Exception:
                        continue
                if clicked:
                    break
            if not clicked:
                try:
                    pg.locator("text=OCS 网课助手").first.click(timeout=10000)
                    clicked = True
                    print("  已点击 text=OCS 网课助手")
                except Exception as e:
                    print("  [点击失败] %s" % str(e)[:120])

            time.sleep(6)
            print("  当前 URL: %s" % pg.url[:140])
            shot = LOGS / ("installed-content-%d.png" % int(time.time()))
            try:
                pg.screenshot(path=str(shot), animations="disabled", timeout=30000)
                print("  [截图] %s" % shot.name)
            except Exception:
                pass

            print("\n=== 读取编辑器内容 ===")
            r = pg.evaluate(READ_EDITOR)
            print("  CodeMirror 实例=%s  textarea=%s  内容长度=%s" % (r["cm"], r["ta"], r["len"]))
            txt = r["text"] or ""
            if not txt:
                print("  ❌ 没读到脚本内容（编辑器可能未加载）")
                sys.exit(2)

            print("\n=== 版本标记检查 ===")
            ok = True
            critical = ["M17", "M16", "M2"]
            for label, needle in MARKERS:
                hit = needle in txt
                if any(label.startswith(c) for c in critical) and not hit:
                    ok = False
                print("  %-24s %s" % (label, "命中" if hit else "未命中"))
            ver = ""
            for line in txt.splitlines():
                if line.startswith("// @version"):
                    ver = line.strip()
                    break
            print("\n  版本行: %s" % ver)
            print("  元数据关键行（直接看，不靠检索）:")
            shown = 0
            for line in txt.splitlines():
                s = line.strip()
                if s.startswith("// @connect") or s.startswith("// @match") or s.startswith("// @version") or s.startswith("// @name"):
                    print("    %s" % s[:90])
                    shown += 1
                    if shown > 18:
                        print("    ...")
                        break
            print("  结论: %s" % ("✅ 装的是含 M17 的最新构建" if ok else "❌ 装的不是最新构建（关键标记缺失），需要重新安装"))
        finally:
            try:
                pg.close()
            except Exception:
                pass
            try:
                b.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
