"""字体解密依赖自检：确认混淆字体确实存在、且参照表能取到。

为什么需要：M16（在章节测验页补做字体解密）依赖 `loadRefTable()`，
而它是用**原生 fetch** 取 `cdn.ocsjs.com` 的 .bin（不是 GM_xmlhttpRequest），
因此受 **CORS** 约束、`@connect` 白名单无效。必须实测。

【只读】只读 DOM 与发一个 GET（不修改任何状态）。

用法：
    python tools\\cx_font_probe.py
    python tools\\cx_font_probe.py --url "<章节测验页>"
"""
import argparse
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
REF_URL = "https://cdn.ocsjs.com/resources/font/font_ref_cx.bin"

FONT_PROBE = """() => {
  const els = Array.from(document.querySelectorAll('.font-cxsecret'));
  const styles = Array.from(document.querySelectorAll('style,link[rel=stylesheet]'))
    .map(s => s.textContent || '')
    .filter(t => t.indexOf('font-cxsecret') >= 0);
  const fontFaces = [];
  try {
    document.fonts.forEach(f => fontFaces.push({ family: f.family, status: f.status }));
  } catch (e) {}
  return {
    cxsecretCount: els.length,
    sample: els.slice(0, 3).map(e => (e.textContent || '').slice(0, 40)),
    styleHasFontFace: styles.length > 0,
    styleSnippet: styles.length ? styles[0].slice(0, 200) : '',
    fontFaces: fontFaces.slice(0, 8)
  };
}"""

CORS_PROBE = """async (url) => {
  const t0 = performance.now();
  try {
    const r = await fetch(url, { cache: 'force-cache' });
    const buf = await r.arrayBuffer();
    const head = new Uint8Array(buf.slice(0, 4));
    const magic = String.fromCharCode.apply(null, head);
    return { ok: true, status: r.status, bytes: buf.byteLength, magic: magic,
             ms: Math.round(performance.now() - t0) };
  } catch (e) {
    return { ok: false, error: String(e && e.message || e), ms: Math.round(performance.now() - t0) };
  }
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        pages = [pg for c in browser.contexts for pg in c.pages]
        target = next((pg for pg in pages if "studentstudy" in (pg.url or "")), None) \
            or next((pg for pg in pages if "chaoxing.com" in (pg.url or "")), None)
        if target is None:
            print("[错误] 没有 chaoxing.com 标签页")
            sys.exit(1)

        if args.url:
            print("[导航] %s" % args.url[:120])
            try:
                target.goto(args.url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)
            except Exception as e:
                print("  [异常] %s" % str(e)[:100])

        print("[页面] %s" % target.url[:140])

        print("\n=== 1. 页面上的混淆字体检测（各 frame）===")
        found_any = False
        # 优先查承载题目的 frame，也顺带查全部
        for f in target.frames:
            try:
                r = f.evaluate(FONT_PROBE)
            except Exception:
                continue
            if r["cxsecretCount"] or r["styleHasFontFace"]:
                found_any = True
                print("  frame: %s" % (f.url or "")[:110])
                print("    .font-cxsecret 元素数: %d" % r["cxsecretCount"])
                if r["sample"]:
                    print("    样例文本: %s" % r["sample"])
                print("    style 里含 font-cxsecret: %s" % r["styleHasFontFace"])
                if r["styleSnippet"]:
                    print("    style 片段: %s" % r["styleSnippet"].replace("\n", " ")[:180])
                if r["fontFaces"]:
                    print("    document.fonts: %s" % r["fontFaces"])
        if not found_any:
            print("  （所有 frame 都未检测到 .font-cxsecret / font-cxsecret 的 @font-face）")
            print("  => 当前页可能不是测验页；若要确认，请用 --url 指向一个章节测验页")

        print("\n=== 2. 参照表能否取到（CORS 实测）===")
        print("  URL: %s" % REF_URL)
        try:
            r = target.evaluate(CORS_PROBE, REF_URL)
        except Exception as e:
            print("  [探测失败] %s" % str(e)[:140])
            r = None
        if r is None:
            pass
        elif r.get("ok"):
            print("  ✅ 可获取: status=%s bytes=%s magic=%r 耗时=%sms" % (
                r["status"], r["bytes"], r["magic"], r["ms"]))
            if r["magic"] != "FRB2":
                print("  ⚠️ magic 不是 FRB2，响应可能不是预期的特征表")
            else:
                print("  => 格式正确（FRB2），M16 的字体解密具备可用的参照表")
        else:
            print("  ❌ 获取失败: %s（耗时 %sms）" % (r.get("error"), r.get("ms")))
            print("  => 说明 cdn.ocsjs.com 未提供允许本页 origin 的 CORS 头，")
            print("     loadRefTable() 的原生 fetch 会被浏览器拦下 —— M16 无法生效。")
            print("     对策：改为用 GM_xmlhttpRequest 取表（不受 CORS 限制），")
            print("     并把 cdn.ocsjs.com 加进 @connect 白名单。")

        print("\n本次只读 DOM + 一个 GET 请求，未修改任何状态。")


if __name__ == "__main__":
    main()
