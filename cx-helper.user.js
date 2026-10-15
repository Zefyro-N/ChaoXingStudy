// ==UserScript==
// @name         学习通任务点助手（ChaoXingStudy）
// @namespace    local.cxstudy
// @version      0.1.0
// @description  学习通(超星)任务点自动推进：视频/音频/文档 + 章节测验 API 作答自动提交。验证码提交前门禁跳过，1.0x 真实速率，人脸识别只检测不绕过。
// @author       local
// @match        *://mooc1.chaoxing.com/*
// @match        *://mooc2-ans.chaoxing.com/*
// @run-at       document-end
// @noframes
// @grant        unsafeWindow
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      opencode.ai
// @connect      api.deepseek.com
// ==/UserScript==

/*
 * 设计文档：PROJECT.md / docs/cx-mechanisms.md
 * 超星站点机制借自 ocsjs/ocsjs（MIT License, https://github.com/ocsjs/ocsjs, 分支 5.0）
 *   —— 任务点判据、iframe 遍历、题型编号、章节测验 DOM 契约、人脸检测语义、提交流程
 * 模型接入层严格复刻本地项目 E:\Code\Estudy\ehuixue-helper.user.js 的 askModel() 设计
 *
 * 硬约束（见 PROJECT.md §2）：
 *  1. 不含登录逻辑，不读写 document.cookie，凭据不落盘（API Key 只存 GM 存储）
 *  2. 不用倍速(恒 1.0x)、不 seek、不自建超星请求；进度上报完全交给页面自身
 *  3. 不识别/绕过验证码、不做任何人脸相关处理
 *  4. 按真实速率挂机；不拦截 blur / visibilitychange
 */

(function () {
  'use strict';

  const W = (typeof unsafeWindow !== 'undefined') ? unsafeWindow : window;
  const TOP = (() => { try { return window.top; } catch (e) { return window; } })();

  // ============================================================
  // 配置
  // ============================================================
  const CFG_KEY = 'cx_userscript_cfg_v1';
  const LOG_KEY = 'cx_userscript_log_v1';
  const REC_KEY = 'cx_userscript_records_v1';

  /** 只允许这两个提供商；模型严格锁定，不提供修改入口 */
  const LOCKED_MODEL = 'deepseek-v4.1-flash';
  const PROVIDERS = {
    'opencode-go': { baseUrl: 'https://opencode.ai/inference/go/v1', userAgent: 'cx-userscript/1.0', needSession: true },
    'deepseek': { baseUrl: 'https://api.deepseek.com', userAgent: '', needSession: false }
  };

  const CFG_DEFAULT = {
    enabled: false,               // 总开关（默认关：装好后由你手动开）
    autoAdvance: true,            // 任务完成后自动切下一个任务点
    muted: true,                  // 静音播放
    // ---- 视频/音频 ----
    autoResumeOnPause: true,      // 暂停后自动恢复播放（章节测验弹层关闭后必须靠它）
    videoQuizEnabled: true,       // 视频内弹题是否作答
    // ---- 章节测验 ----
    quizEnabled: true,            // 是否作答章节测验
    autoSubmit: true,             // 作答完成后自动提交（用户已确认接受风险）
    quizSubmitDelayMs: 3000,      // 点[提交]后等多久（超星自己是 3000）
    captchaGate: true,            // 提交前人机验证门禁：命中则不提交、跳过
    /** 验证码特征选择器：真实观测到以后填进来，比启发式靠谱 */
    captchaSelectors: '',
    // ---- 答题模型 ----
    provider: 'opencode-go',
    apiKey: '',
    maxTokens: 4096,
    modelTimeout: 45000,
    fontStrategy: 'skip',         // 题干被 .font-cxsecret 混淆时：skip=不做模型作答 | raw=照发(可能乱码)
    // ---- 超时（毫秒）：超星经常卡顿，一律给宽 ----
    to: {
      mediaReady: 90000,
      taskSwitch: 60000,
      quizReady: 90000,
      submitConfirm: 60000,
      stall: 180000,            // 位置完全不动多久才算停滞
      resumeAfter: 15000,       // 位置多久没前进就主动恢复播放
      heartbeat: 30000,
      facePoll: 3000
    }
  };

  let CFG = Object.assign({}, CFG_DEFAULT, safeGet(CFG_KEY, {}));
  CFG.to = Object.assign({}, CFG_DEFAULT.to, CFG.to || {});
  const SESSION_ID = uuid();

  function safeGet(k, d) { try { const v = GM_getValue(k); return v === undefined ? d : v; } catch (e) { return d; } }
  function safeSet(k, v) { try { GM_setValue(k, v); } catch (e) { } }
  function saveCfg() { safeSet(CFG_KEY, CFG); }
  function TO(k, d) { return (CFG.to && CFG.to[k]) || d; }
  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
  function uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }
  function baseUrl() { return (PROVIDERS[CFG.provider] || PROVIDERS['opencode-go']).baseUrl; }

  // ============================================================
  // 状态
  // ============================================================
  const S = {
    running: false,
    phase: 'idle',              // idle / scanning / media / quiz / waiting-face / blocked / done
    startedAt: 0,
    handledMids: {},            // 已处理任务点（防重复）
    seenMids: [],
    stats: { tasksOk: 0, tasksFail: 0, quizOk: 0, quizSkipCaptcha: 0, qOk: 0, qGiveUp: 0, faceStops: 0 },
    lastPos: -1, lastMove: 0,
    fontObfuscated: false,
    blockedReason: '',
    stoppedReason: ''
  };

  // ============================================================
  // 日志
  // ============================================================
  const LOG = [];
  const LOG_PERSIST = 400;

  function log(msg) {
    const line = '[' + new Date().toLocaleTimeString('zh-CN', { hour12: false }) + '] ' + msg;
    LOG.push(line);
    if (LOG.length > 600) LOG.splice(0, LOG.length - 600);
    console.log('%c[CX] %c' + msg, 'color:#2e86de;font-weight:bold', 'color:inherit');
    uiRefresh();
  }
  function flushLog() { try { safeSet(LOG_KEY, { at: Date.now(), lines: LOG.slice(-LOG_PERSIST) }); } catch (e) { } }
  function restorePrevLog() {
    const v = safeGet(LOG_KEY, null);
    if (!v || !v.lines || !v.lines.length) return;
    if (Date.now() - (v.at || 0) > 30 * 60 * 1000) return;
    LOG.push('[=== 上次会话（' + new Date(v.at).toLocaleString('zh-CN', { hour12: false }) + '，共 ' + v.lines.length + ' 行）===]');
    v.lines.forEach(l => LOG.push(l));
    LOG.push('[=== 本次会话 ===]');
  }
  function dumpLog() {
    const blob = new Blob([LOG.join('\n')], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'cx-userscript-' + Date.now() + '.log';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }

  // ============================================================
  // 站点适配层 —— 对应 docs/cx-mechanisms.md
  // ============================================================
  const CX = {
    /** §2.1 递归收集可访问的 iframe */
    searchIFrame(root) {
      let list = Array.from(root.querySelectorAll('iframe'));
      const result = [];
      while (list.length) {
        const frame = list.shift();
        try {
          if (frame && frame.contentWindow && frame.contentWindow.document) {
            result.push(frame);
            list = list.concat(Array.from(frame.contentWindow.document.querySelectorAll('iframe') || []));
          }
        } catch (e) { /* 跨域，忽略 */ }
      }
      return result;
    },

    /** 顶层文档（超星的目录/任务点数据在 top） */
    topDoc() { try { return TOP.document; } catch (e) { return document; } },

    /** §3 是否处于闯关/解锁模式 */
    isInSpecialMode() {
      return this.topDoc().querySelectorAll('.catalog_points_sa,.catalog_points_er').length !== 0;
    },

    /** §3 全部章节：{el, chapterId, unFinishCount} */
    getChapterInfos() {
      return Array.from(this.topDoc().querySelectorAll('[onclick^="getTeacherAjax"]')).map(el => ({
        element: el,
        chapterId: (el.getAttribute('onclick') || '').match(/\('(.*)','(.*)','(.*)'\)/)?.[3],
        unFinishCount: parseInt(el.parentElement?.querySelector('.jobUnfinishCount')?.value || '0', 10)
      }));
    },

    /** §3 当前活动章节 */
    activeChapter() { return this.topDoc().querySelector('.posCatalog_active'); },

    /** §3 当前章节是否已完成 */
    isCurrentChapterFinished() {
      const c = this.activeChapter();
      return !!(c && c.querySelector('.icon_Completed') !== null);
    },

    /** §3 是否在最后一小节 */
    isInFinalTab() {
      const tabs = Array.from(this.topDoc().querySelectorAll('.prev_ul li'));
      if (!tabs.length) return true;
      return tabs[tabs.length - 1].classList.contains('active');
    },

    /** §5.2 超星题型编号 → 语义 */
    getQuestionType(val) {
      if (val === 0) return 'single';
      if (val === 1) return 'multiple';
      if (val === 3) return 'judgement';
      if ([2, 4, 5, 6, 7, 8, 9, 10].includes(val)) return 'completion';
      if (val === 11) return 'line';
      if (val === 14) return 'fill';
      if (val === 15) return 'reader';
      return 'unknown';
    },

    /** §4 取播放器容器 */
    videojs(doc) { return doc.querySelector('#video,#audio'); },

    /** §4 固定显示进度条（纯显示，无副作用） */
    fixProgressBar() {
      const doc = this.mediaDoc();
      if (!doc) return;
      const bar = doc.querySelector('.vjs-control-bar');
      if (bar) bar.style.opacity = '1';
    },

    /** 当前承载媒体的 document */
    mediaDoc() {
      for (const f of this.searchIFrame(this.topDoc())) {
        try {
          if (f.contentWindow.document.querySelector('#video,#audio')) return f.contentWindow.document;
        } catch (e) { }
      }
      return null;
    },

    /** §4 等待媒体元素 */
    waitForMedia(timeout) {
      const limit = timeout || TO('mediaReady', 90000);
      const t0 = Date.now();
      return new Promise((resolve, reject) => {
        const tick = () => {
          const doc = this.mediaDoc();
          const media = doc ? doc.querySelector('video,audio') : null;
          if (media) { resolve(media); return; }
          if (Date.now() - t0 > limit) { reject(new Error('等待媒体元素超时')); return; }
          setTimeout(tick, 1000);
        };
        tick();
      });
    },

    /** §4 播放失败检测 */
    mediaErrorText(doc) {
      const el = doc.querySelector('.vjs-modal-dialog-content');
      if (!el) return '';
      const t = el.innerText || '';
      const bad = ['视频文件损坏', '网络错误导致视频下载中途失败', '视频因格式不支持', '网络的问题无法加载'];
      return bad.some(s => t.includes(s)) ? t.slice(0, 80) : '';
    },

    /** §2.2 在某个 iframe 内识别任务点类型 */
    jobKindInFrame(frame) {
      const doc = frame.contentWindow.document;
      const q = sel => doc.querySelector(sel);
      return {
        doc,
        videojs: q('#video,#audio'),
        chapterTest: q('.TiMu'),
        read: q('#img.imglook'),
        pptWithAudio: q('.swiper-container'),
        hyperlink: q('#hyperlink'),
        timereader: q('iframe[name="bookifame"][src*="timing"]')
      };
    },

    /** §2.3 从 iframe 的 data 属性取 jobid */
    frameJobId(frame) {
      try {
        const raw = frame.getAttribute('data')
          || frame.contentWindow?.parent?.frameElement?.getAttribute('data')
          || '{}';
        const d = JSON.parse(raw || '{}');
        return d.jobid || d._jobid || null;
      } catch (e) { return null; }
    },

    /** §2.3 顶层任务点数组 */
    attachments() {
      try { return TOP.attachments || []; } catch (e) { return []; }
    }
  };

  // ============================================================
  // 安全层（硬约束 #3）
  // ============================================================
  const SAFETY = {
    /** §8 旧版人脸识别：#fcqrimg 的 src 非空 */
    hasFaceRecognition() {
      const faces = Array.from(TOP.document.querySelectorAll('#fcqrimg'));
      return faces.some(f => !!f.getAttribute('src'));
    },
    /** §8 新版人脸识别：.chapterVideoFaceMaskDiv 未隐藏 */
    hasNewFaceRecognition() {
      const faces = Array.from(TOP.document.querySelectorAll('.chapterVideoFaceMaskDiv'));
      return faces.some(f => f.style.display !== 'none');
    },
    hasAnyFace() { return this.hasFaceRecognition() || this.hasNewFaceRecognition(); },
    /** 一直等人脸消失；只提示，不做任何识别/上传/绕过 */
    waitFaceGone(reason) {
      let notified = false;
      S.phase = 'waiting-face';
      S.stats.faceStops++;
      return new Promise(resolve => {
        const iv = setInterval(() => {
          if (this.hasAnyFace()) {
            if (!notified) {
              notified = true;
              const msg = '⚠️ 检测到人脸识别（' + reason + '），已停手等你手动完成识别。脚本不做任何绕过。';
              log(msg); uiAlert(msg);
            }
          } else {
            clearInterval(iv);
            log('人脸识别已消失，继续运行。');
            resolve();
          }
        }, TO('facePoll', 3000));
      });
    },

    /** 考试页硬禁区（URL 判据） */
    isExamUrl(u) {
      const s = String(u || '').toLowerCase();
      return ['joinexam', 'exam-ans', 'exam/test', 'exam/phone', 'exampaper', 'examcode']
        .some(k => s.indexOf(k) >= 0);
    },

    /**
     * D3 提交前人机验证门禁。
     * 命中 => 本次不提交。只检测，不识别、不拖动、不重试。
     * 判据优先级：用户配置的 captchaSelectors > 启发式特征。
     */
    detectCaptcha(doc) {
      // 1) 用户真实观测到的选择器
      const custom = (CFG.captchaSelectors || '').split(',').map(s => s.trim()).filter(Boolean);
      for (const sel of custom) {
        try { if (doc.querySelector(sel)) return { hit: true, by: '自定义选择器 ' + sel }; } catch (e) { }
        try { if (TOP.document.querySelector(sel)) return { hit: true, by: '自定义选择器(top) ' + sel }; } catch (e) { }
      }
      // 2) 启发式特征（保守：宁可误判跳过，也不误提交）
      const hints = [
        { sel: 'img[src*="captcha"]', by: 'captcha 图片' },
        { sel: 'img[src*="validate"]', by: 'validate 图片' },
        { sel: '.verifyimg, .validateCode, .captcha', by: '验证码容器类名' },
        { sel: '#verifyCode, #validateCode, #captcha', by: '验证码元素 id' },
        { sel: 'input[name="validateCode"], input[name="verifyCode"], input[name="captcha"]', by: '验证码输入框' },
        { sel: '.slider, .nc-container, .geetest_panel, .verify-slider, .slide-verify', by: '滑块验证组件' },
        { sel: '.yzm, .yzmImg, .picCode', by: '图形验证码(超星常用名)' },
        { sel: '#yzmImg, .yzm-tip, .refresh-code', by: '图形验证码提示' }
      ];
      for (const h of hints) {
        try { if (doc.querySelector(h.sel)) return { hit: true, by: h.by + ' @frame' }; } catch (e) { }
        try { if (TOP.document.querySelector(h.sel)) return { hit: true, by: h.by + ' @top' }; } catch (e) { }
      }
      // 3) 文案特征
      try {
        const txt = (doc.body ? doc.body.innerText : '') + ' ' + (TOP.document.body ? TOP.document.body.innerText : '');
        const words = ['请输入验证码', '人机验证', '拖动滑块', '完成验证', '验证码校验'];
        for (const w of words) if (txt.indexOf(w) >= 0) return { hit: true, by: '文案「' + w + '」' };
      } catch (e) { }
      return { hit: false };
    },

    /** 检测到不认识的弹窗/遮挡：只等不抢 */
    markBlocked(reason) {
      S.phase = 'blocked';
      S.blockedReason = reason;
      const msg = '⏸ 遇到无法识别的弹窗/状态，已暂停抢播等你处理：' + reason;
      log(msg); uiAlert(msg);
    }
  };

  // ============================================================
  // 答题层 —— 严格复刻 E:\Code\Estudy\ehuixue-helper.user.js 的 askModel()
  // ============================================================
  const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

  /** 零宽 / 特殊空白清洗（超星题干常见污染） */
  function cleanText(t) {
    return String(t || '')
      .replace(/[\u2002\u200b\u200c\u200d\u3000\u00a0\ufeff]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  /** §5.3 超星题干冗余清洗 */
  function cleanTitle(t) {
    return cleanText(t)
      .replace(/^\d+[。、.]/, '')
      .replace(/（\d+\.\d+分）/, '')
      .replace(/\(..题, \d+?分\)/, '')
      .replace(/\(..题, \d+\.\d+分\)/, '')
      .replace(/[[(【（](..题|名词解释|完形填空|阅读理解)[\])】）]/, '')
      .trim();
  }

  /** 题目对象：{ qtype, text, options:[{index,text,el}], answerEl } */
  function buildPrompt(item) {
    const kindName = {
      single: '单选题', multiple: '多选题', judgement: '判断题',
      completion: '填空/简答题', line: '连线题', fill: '选词填空题', reader: '阅读理解题'
    }[item.qtype] || '题目';

    const optLines = item.options.length
      ? item.options.map((o, i) => LETTERS[i] + '. ' + o.text).join('\n')
      : '（本题无选项，请直接给出答案文本）';

    return '你是答题助手。请回答下面的' + kindName + '，只输出答案。\n' +
      '单选/判断题输出一个大写字母；多选题输出多个大写字母用英文逗号分隔，' +
      '不要空格、不要解释、不要标点。\n' +
      '填空题/简答题直接输出答案文本。\n\n' +
      '题干：' + item.text + '\n' +
      (item.options.length ? ('选项：\n' + optLines + '\n\n') : '') +
      '答案：';
  }

  /** 把模型输出的字母映射成选项下标数组 */
  function parseLetterIndexes(item, raw) {
    if (!item.options.length) {
      const txt = cleanText(raw);
      return txt ? { text: txt } : null;
    }
    let letters = String(raw).toUpperCase().match(/[A-Z]/g) || [];
    const idx = [];
    letters.forEach(l => {
      const i = LETTERS.indexOf(l);
      if (i >= 0 && i < item.options.length && idx.indexOf(i) < 0) idx.push(i);
    });
    if (!idx.length) return null;
    idx.sort((a, b) => a - b);
    return { indexes: idx, letters: idx.map(i => LETTERS[i]).join(',') };
  }

  /** 调用模型。1:1 复刻 Estudy 的请求构造、鉴权头、reasoning_content 兜底 */
  function askModel(item, cb) {
    if (!CFG.apiKey) { log('  [模型] 未配置 API Key，放弃本题'); cb(null); return; }
    const p = PROVIDERS[CFG.provider] || PROVIDERS['opencode-go'];

    const headers = {
      'Authorization': 'Bearer ' + CFG.apiKey,
      'Content-Type': 'application/json'
    };
    // OpenCode Go 要求：自定义 UA + 稳定会话 ID
    if (/opencode\.ai/.test(p.baseUrl)) {
      headers['User-Agent'] = p.userAgent;
      headers['x-opencode-session'] = SESSION_ID;
    }

    const url = p.baseUrl.replace(/\/+$/, '') + '/chat/completions';
    const body = {
      model: LOCKED_MODEL,
      messages: [{ role: 'user', content: buildPrompt(item) }],
      max_tokens: CFG.maxTokens,
      stream: false
    };

    GM_xmlhttpRequest({
      method: 'POST',
      url: url,
      headers: headers,
      data: JSON.stringify(body),
      timeout: CFG.modelTimeout,
      onload: function (r) {
        if (r.status !== 200) {
          log('  [模型] HTTP ' + r.status + ' @' + CFG.provider + ' : ' + String(r.responseText).slice(0, 200));
          cb(null); return;
        }
        let j;
        try { j = JSON.parse(r.responseText); } catch (e) { log('  [模型] 响应不是 JSON'); cb(null); return; }
        const ch = (j.choices || [{}])[0] || {};
        const msg = ch.message || {};
        let text = String(msg.content || '').trim();
        if (!text) {
          // 思考模型可能烧光 max_tokens 导致 content 为空 -> 从 reasoning 尾部兜底
          const rs = String(msg.reasoning_content || '');
          const cand = rs.slice(-500).toUpperCase().match(/\b([A-F])\b/g);
          if (cand && cand.length) text = cand[cand.length - 1];
          else { log('  [模型] content 为空 (finish_reason=' + ch.finish_reason + ')'); cb(null); return; }
        }
        const parsed = parseLetterIndexes(item, text);
        if (!parsed) { log('  [模型] 解析不出选项：' + text.slice(0, 60)); cb(null); return; }
        cb({ parsed: parsed, raw: text.slice(0, 40) });
      },
      onerror: function () { log('  [模型] 请求失败（网络或 CORS）'); cb(null); },
      ontimeout: function () { log('  [模型] 超时'); cb(null); }
    });
  }

  // ============================================================
  // 题干混淆字体（docs/cx-mechanisms.md §7）—— 待移植
  // ============================================================
  const FONT = {
    /**
     * 检测 .font-cxsecret 并决定作答策略。
     * 移植状态：未完成。ocsjs 的 bitmap 破解器（font_ref_cx.bin 参照表）尚未移植，
     * 因此当前只能在"混淆"与"放弃模型作答"之间二选一，不做假还原。
     */
    async prepare(doc) {
      const els = Array.from(doc.querySelectorAll('.font-cxsecret'));
      if (!els.length) { S.fontObfuscated = false; return true; }
      S.fontObfuscated = true;
      log('⚠️ 检测到 ' + els.length + ' 个 .font-cxsecret 混淆元素（题干被字形置换保护）');
      if (CFG.fontStrategy === 'raw') {
        log('  fontStrategy=raw：仍将原文发给模型。提示：题干很可能是乱码，答案不可信。');
        return true;
      }
      log('  fontStrategy=skip：本题不做模型作答（避免把乱码当题干）。');
      log('  → 待办：移植 ocsjs 的 font-decrypt（参照表 https://cdn.ocsjs.com/resources/font/font_ref_cx.bin）');
      return false;
    }
  };

  // ============================================================
  // 任务执行器
  // ============================================================
  const Job = {
    /** §4 视频 / 音频 */
    async media(doc) {
      S.phase = 'media';
      let media;
      try { media = await CX.waitForMedia(); }
      catch (e) { log('视频/音频检测不到，跳过：' + e.message); S.stats.tasksFail++; return; }

      const vjs = CX.videojs(doc);
      if (!vjs) { log('未找到 #video/#audio 容器，跳过。'); S.stats.tasksFail++; return; }

      try { TOP.currentMedia = media; } catch (e) { }
      CX.fixProgressBar();

      // 1.0x 锁定（硬约束 #2）。绝不提升倍速，只做纠正
      const lockRate = () => {
        if (Math.abs(media.playbackRate - 1) > 1e-6) {
          log('  [速率] 检测到 playbackRate=' + media.playbackRate + '，已纠正为 1.0');
          media.playbackRate = 1;
        }
      };
      lockRate();
      media.addEventListener('ratechange', lockRate);

      media.volume = CFG.muted ? 0 : 1;

      // 视频内弹题：改为模型作答（不采用 ocsjs 的随机模式）
      let quizLoopStop = false;
      const quizLoop = async () => {
        while (!quizLoopStop && S.running) {
          try {
            if (CFG.videoQuizEnabled) await Job.videoQuiz(doc);
          } catch (e) { log('  [弹题] 异常：' + e.message); }
          await sleep(3000);
        }
      };
      if (CFG.videoQuizEnabled) quizLoop();

      // 暂停后恢复播放（章节测验弹层关闭、挂机弹窗都会触发 pause）
      const onPause = async () => {
        if (!CFG.autoResumeOnPause || !S.running) return;
        if (SAFETY.hasAnyFace()) return;                 // 人脸识别时不抢播
        if (S.phase === 'quiz') return;                  // 章节测验期间不抢播
        if (media.ended) return;
        await sleep(800);
        try { await media.play(); } catch (e) { log('  [恢复] play() 被拒：' + (e.message || e)); }
      };
      media.addEventListener('pause', onPause);

      // 播放失败检测
      const errIv = setInterval(() => {
        const t = CX.mediaErrorText(doc);
        if (t) { log('⚠️ 视频加载失败：' + t + ' → 跳过该任务点'); clearInterval(errIv); }
      }, 3000);

      log('开始播放（1.0x，静音=' + !!CFG.muted + '），时长=' + (media.duration || '未知') + 's');
      try { await media.play(); } catch (e) { log('  [播放] 首次 play() 被拒（可能是自动播放策略）：' + (e.message || e)); }

      // 看护：位置停滞检测 + 人脸识别 + 播放结束
      await new Promise(resolve => {
        S.lastPos = -1; S.lastMove = Date.now();
        const iv = setInterval(async () => {
          if (!S.running) { clearInterval(iv); resolve(); return; }

          if (SAFETY.hasAnyFace()) {
            clearInterval(iv);
            await SAFETY.waitFaceGone('播放中');
            S.phase = 'media';
            try { await media.play(); } catch (e) { }
            Job.mediaWatch(doc, media, resolve, iv);   // 重新挂看护
            return;
          }

          if (media.ended) {
            log('视频/音频播放完毕');
            clearInterval(iv); quizLoopStop = true;
            media.removeEventListener('pause', onPause);
            clearInterval(errIv);
            resolve();
            return;
          }

          const pos = media.currentTime;
          if (Math.abs(pos - S.lastPos) > 0.3) { S.lastPos = pos; S.lastMove = Date.now(); }
          else if (Date.now() - S.lastMove > TO('resumeAfter', 15000)) {
            log('  [看护] 位置 ' + pos.toFixed(1) + 's 超过 ' + (TO('resumeAfter', 15000) / 1000) + 's 没前进，尝试恢复播放');
            try { await media.play(); } catch (e) { }
            S.lastMove = Date.now();
          }
          if (Date.now() - S.startedAt > 0 && (Date.now() - S.lastMove) > TO('stall', 180000)) {
            log('⚠️ 停滞超过 ' + (TO('stall', 180000) / 1000) + 's，放弃该任务点');
            clearInterval(iv); S.stats.tasksFail++;
            resolve();
          }
        }, 3000);
      });

      quizLoopStop = true;
    },

    /** 供人脸恢复后重新挂看护（与上面同构，抽出避免递归膨胀） */
    mediaWatch(doc, media, resolve, _unused) {
      S.lastPos = media.currentTime; S.lastMove = Date.now();
      const iv = setInterval(() => {
        if (!S.running || media.ended) { clearInterval(iv); resolve(); return; }
        if (Math.abs(media.currentTime - S.lastPos) > 0.3) { S.lastPos = media.currentTime; S.lastMove = Date.now(); }
      }, 3000);
    },

    /** §4.1 视频内弹题：模型作答（替换 ocsjs 的随机） */
    async videoQuiz(doc) {
      const btn = doc.querySelector('#videoquiz-submit');
      if (!btn) return;
      const labels = Array.from(doc.querySelectorAll('.ans-videoquiz-opt label'));
      if (!labels.length) return;

      const item = {
        qtype: 'single',
        text: cleanText(doc.querySelector('#video .ans-videoquiz')?.innerText || '视频内题目').slice(0, 500),
        options: labels.map((el, i) => ({ index: i, text: cleanText(el.innerText), el: el }))
      };
      log('  [弹题] 检测到视频内题目，' + item.options.length + ' 个选项，走模型作答');
      item.options.forEach(o => log('      ' + LETTERS[o.index] + '. ' + o.text.slice(0, 70)));

      const r = await new Promise(res => askModel(item, res));
      if (r && r.parsed.indexes) {
        labels[r.parsed.indexes[0]]?.click();
        log('  [弹题] => ' + r.parsed.letters + '  (来源 ' + CFG.provider + ' / ' + LOCKED_MODEL + ')');
      } else {
        log('  [弹题] 模型无结果 → 放弃本题（不随机作答）');
        S.stats.qGiveUp++;
      }
      await sleep(1000);
      btn.click();
      await sleep(3000);
      // 收起残留容器，避免遮挡播放
      doc.querySelector('#video .ans-videoquiz')?.remove();
      Array.from(doc.querySelectorAll('.x-component-default')).forEach(c => { c.style.display = 'none'; });
    },

    /** §9 图片阅读：驱动真实翻阅（不使用 ocsjs 的 finishJob 秒过） */
    async read(frame) {
      const win = frame.contentWindow;
      const doc = win.document;
      log('文档/图片阅读任务：驱动翻页');
      const turns = 300;                       // 上限保护
      let lastHtml = '';
      for (let i = 0; i < turns && S.running; i++) {
        const cur = doc.body ? doc.body.innerHTML.length : 0;
        if (cur === lastHtml) { /* 内容不再变化 */ }
        lastHtml = cur;
        // 尝试多种常见翻页入口，取存在的那个
        const next = doc.querySelector('.nextBtn, .btnNext, #nextBtn, .swiper-button-next, a[onclick*="next"]');
        if (!next) break;
        try { next.click(); } catch (e) { }
        await sleep(1500);
      }
      log('文档翻页循环结束');
      await sleep(2000);
    },

    /** §9 带音频的 PPT */
    async readPPTWithAudio(frame) {
      const win = frame.contentWindow;
      Array.from(win.document.querySelectorAll('audio')).forEach(a => {
        a.addEventListener('play', () => { a.muted = true; });
      });
      const len = win.document.querySelectorAll('.swiper-container .swiper-slide').length;
      log('带音频 PPT：' + len + ' 页，逐页翻阅');
      for (let i = 0; i < len && S.running; i++) {
        try { win.swiperNext?.(); } catch (e) { }
        await sleep(1000);
      }
      await sleep(3000);
    },

    /** §9 长时阅读 */
    async timereader(iframe) {
      const src = iframe.getAttribute('src') || '';
      let timing = 60;
      try { timing = parseInt(new URL(src, location.href).searchParams.get('timing') || '60', 10); } catch (e) { }
      const total = (timing + 3) * 3 * 1000;
      log('长时阅读任务：需等待约 ' + Math.round(total / 1000) + 's（不要切走）');
      const t0 = Date.now();
      while (Date.now() - t0 < total && S.running) await sleep(2000);
      await sleep(5000);
    },

    /** §9 链接任务点 */
    async hyperlink(a) {
      const old = a.onclick;
      a.onclick = () => false;   // 防弹窗
      try { a.click(); } finally { a.onclick = old; }
      await sleep(3000);
    },

    // ---------------- §5 章节测验 ----------------
    /** 抽取一道题 */
    extractQuestion(tiMu, doc) {
      const typeInput = Array.from(tiMu.querySelectorAll('input[id^="answertype"]'))[0];
      let typeVal = -1;
      // 非预览模式存在干扰 type input：优先取 name 匹配 /type\d+/ 的
      const candidates = Array.from(tiMu.querySelectorAll('input[id^="answertype"], input[name^="type"]'));
      const good = candidates.find(i => /type\d+/.test(i.getAttribute('name') || ''));
      if (good) typeVal = parseInt(good.getAttribute('value') || '-1', 10);
      else if (typeInput) typeVal = parseInt(typeInput.value || '-1', 10);

      const qtype = CX.getQuestionType(typeVal);

      const titleEl = tiMu.querySelector('.Zy_TItle .clearfix') || tiMu.querySelector('.Zy_TItle');
      const text = cleanTitle(titleEl ? titleEl.innerText : '');

      const optEls = Array.from(tiMu.querySelectorAll('ul li .after, ul li label:not(.before), ul li textarea, ul textarea'));

      return {
        qtype: qtype,
        typeVal: typeVal,
        text: text,
        // 填空型：保存 textarea 自身便于回填
        options: (qtype === 'completion')
          ? []
          : optEls.map((el, i) => ({ index: i, text: cleanText(el.innerText), el: el })),
        completionInputs: (qtype === 'completion') ? optEls : []
      };
    },

    /** 填答 */
    async fill(item, parsed) {
      if (item.qtype === 'completion') {
        const ansText = parsed.text || '';
        if (!ansText) return false;
        for (const el of item.completionInputs) {
          const ta = el.tagName === 'TEXTAREA' ? el : el.parentElement?.querySelector('textarea');
          if (ta) ta.value = ansText;
          const ifr = el.parentElement?.querySelector('iframe') || (el.tagName === 'IFRAME' ? el : null);
          try { if (ifr && ifr.contentDocument) ifr.contentDocument.body.innerHTML = ansText; } catch (e) { }
          const save = el.parentElement?.parentElement?.querySelector('[onclick*=saveQuestion]');
          if (save) save.click();
          await sleep(400);
        }
        return true;
      }

      if (!parsed.indexes || !parsed.indexes.length) return false;
      for (const i of parsed.indexes) {
        const o = item.options[i];
        if (!o || !o.el) continue;
        // 已选过就跳过（适配 2023/9 新版 aria-checked）
        const parent = o.el.parentElement;
        const checked = parent?.querySelector('label input')?.getAttribute('checked') === 'checked'
          || parent?.getAttribute('aria-checked') === 'true';
        if (!checked) o.el.click();
        await sleep(300);
      }
      return true;
    },

    /** §5.5 章节测验全流程（含 D3 验证码门禁） */
    async chapter(frame, jobName) {
      S.phase = 'quiz';
      const win = frame.contentWindow;
      const doc = win.document;

      const tiMus = Array.from(doc.querySelectorAll('.TiMu'));
      if (!tiMus.length) { log('章节测验页面未找到题目（.TiMu），跳过。'); S.stats.tasksFail++; return; }

      log('章节测验：' + jobName + '，共 ' + tiMus.length + ' 题');
      if (SAFETY.isExamUrl(win.location.href) || SAFETY.isExamUrl(frame.src)) {
        log('⛔ 该页面命中考试禁区判据，拒绝作答。'); S.phase = 'blocked'; return;
      }

      // 题干混淆检查（D4）
      const readable = await FONT.prepare(doc);
      if (!readable && CFG.fontStrategy === 'skip') {
        log('因题干混淆且未移植还原模块，本次测验放弃（不提交）。');
        S.stats.quizSkipCaptcha++;
        S.phase = 'idle';
        return;
      }

      let filled = 0, gaveUp = 0;
      for (let i = 0; i < tiMus.length && S.running; i++) {
        const item = this.extractQuestion(tiMus[i], doc);
        log('  Q' + (i + 1) + ' (type=' + item.qtype + '/' + item.typeVal + ') ' + (item.text || '').slice(0, 90));
        item.options.forEach(o => log('      ' + LETTERS[o.index] + '. ' + o.text.slice(0, 70)));

        if (item.qtype === 'line' || item.qtype === 'fill' || item.qtype === 'reader' || item.qtype === 'unknown') {
          log('  → 题型 ' + item.qtype + ' 暂不支持，放弃本题（不随机作答）');
          gaveUp++; continue;
        }

        const r = await new Promise(res => askModel(item, res));
        if (r) {
          const ok = await this.fill(item, r.parsed);
          if (ok) {
            filled++;
            log('  => ' + (r.parsed.letters || r.parsed.text || '').slice(0, 40) + '  (来源 ' + CFG.provider + ')');
          } else { gaveUp++; log('  → 回填失败，放弃本题'); }
        } else {
          gaveUp++; log('  → 模型无结果，放弃本题（不随机作答）');
        }
        await sleep(300);
      }

      log('作答完成：成功 ' + filled + ' / 放弃 ' + gaveUp + ' / 共 ' + tiMus.length);

      if (!CFG.autoSubmit) {
        log('自动提交已关闭 → 请自行检查后提交。');
        S.phase = 'idle';
        return;
      }

      // ---- §5.5 提交流程 ----
      log('等待 ' + CFG.quizSubmitDelayMs + 'ms 后提交（超星自身节奏）');
      await sleep(CFG.quizSubmitDelayMs);

      try { win.btnBlueSubmit(); }
      catch (e) { log('btnBlueSubmit() 调用失败：' + e.message + ' → 本次不提交'); S.stats.quizSkipCaptcha++; S.phase = 'idle'; return; }
      log('已点击[提交]，等待确认弹窗出现…');
      await sleep(3000);

      // ★ D3 门禁：在「提交」与「确认」之间检测人机验证，命中则不确认
      if (CFG.captchaGate) {
        const cap = SAFETY.detectCaptcha(doc);
        if (cap.hit) {
          S.stats.quizSkipCaptcha++;
          const msg = '🛑 提交前检测到人机验证（' + cap.by + '）→ 本次【不确认提交】，跳过该测验。';
          log(msg); uiAlert(msg);
          log('  说明：未调用 submitCheckTimes()，因此不会产生提交记录。请人工处理该测验。');
          try { TOP.$ && TOP.$('#workpop') && TOP.$('#workpop').hide(); } catch (e) { }
          S.phase = 'idle';
          return;
        }
        log('提交前门禁：未检测到人机验证，继续确认提交。');
      }

      try { win.submitCheckTimes(); }
      catch (e) { log('submitCheckTimes() 调用失败：' + e.message + ' → 请人工检查是否已提交'); S.phase = 'idle'; return; }
      await sleep(3000);
      try { TOP.$ && TOP.$('#workpop') && TOP.$('#workpop').hide(); } catch (e) { }

      S.stats.quizOk++;
      this.recordQuiz(jobName, tiMus.length, filled, gaveUp);
      log('✅ 章节测验已提交：' + jobName);
      S.phase = 'idle';
    },

    recordQuiz(title, total, filled, gaveUp) {
      const recs = safeGet(REC_KEY, []) || [];
      recs.push({
        at: new Date().toLocaleString('zh-CN', { hour12: false }),
        title: title, total: total, filled: filled, gaveUp: gaveUp,
        provider: CFG.provider, model: LOCKED_MODEL
      });
      while (recs.length > 100) recs.shift();
      safeSet(REC_KEY, recs);
    }
  };

  // ============================================================
  // 任务点枚举与调度
  // ============================================================
  const Sched = {
    /** §2.2/§2.3 找到下一个可执行任务点 */
    findNextJob() {
      const attachments = CX.attachments();
      if (!attachments.length) return { err: '拿不到顶层 attachments（可能不在课程页）' };

      for (const frame of CX.searchIFrame(CX.topDoc())) {
        let kind;
        try { kind = CX.jobKindInFrame(frame); } catch (e) { continue; }

        const hit = kind.videojs || kind.chapterTest || kind.read || kind.pptWithAudio || kind.hyperlink || kind.timereader;
        if (!hit) continue;

        const jobId = CX.frameJobId(frame);
        if (!jobId) continue;

        const att = attachments.find(a =>
          String(a.jobid || (a.property && a.property._jobid)) === String(jobId));
        if (!att) continue;

        const mid = att.property && att.property.mid;
        if (!mid || S.handledMids[mid]) continue;

        const p = att.property || {};
        const jobName = p.name || p.title
          || (p.bookname ? p.bookname + (p.author || '') : null) || '未知任务';
        const workType = att.job ? 'job' : (att.isPassed ? 'finished' : 'not-job');

        return { frame, kind, att, mid, jobName, workType };
      }
      return null;
    },

    async run() {
      S.running = true;
      S.startedAt = Date.now();
      log('==================================================');
      log('本次将作答并自动提交章节测验（已获用户授权）。速率固定 1.0x，不自建超星请求。');
      log('提供商=' + CFG.provider + '  模型=' + LOCKED_MODEL + '  API Key=' + (CFG.apiKey ? '已配置' : '未配置'));
      log('==================================================');

      while (S.running) {
        if (SAFETY.hasAnyFace()) { await SAFETY.waitFaceGone('调度循环检测'); }

        const job = this.findNextJob();

        if (!job) {
          log('暂无可执行任务点。若为闯关模式，需前一任务点完成后才会解锁，60s 后复查。');
          await sleep(60000);
          continue;
        }
        if (job.err) { log(job.err); await sleep(30000); continue; }

        log('▶ 任务点：' + job.jobName + '  状态=' + job.workType
          + (job.kind.videojs ? ' [视频/音频]' : job.kind.chapterTest ? ' [章节测验]'
            : job.kind.read ? ' [图片阅读]' : job.kind.pptWithAudio ? ' [PPT]'
              : job.kind.timereader ? ' [长时阅读]' : job.kind.hyperlink ? ' [链接]' : ''));

        if (job.workType === 'finished') { S.handledMids[job.mid] = 1; continue; }

        S.phase = 'switching';
        try {
          if (job.kind.videojs) await Job.media(job.kind.doc);
          else if (job.kind.chapterTest) await Job.chapter(job.frame, job.jobName);
          else if (job.kind.read) await Job.read(job.frame);
          else if (job.kind.pptWithAudio) await Job.readPPTWithAudio(job.frame);
          else if (job.kind.timereader) await Job.timereader(job.kind.timereader);
          else if (job.kind.hyperlink) await Job.hyperlink(job.kind.hyperlink);

          S.handledMids[job.mid] = 1;
          S.stats.tasksOk++;
          log('✔ 任务点处理结束：' + job.jobName);
        } catch (e) {
          S.stats.tasksFail++;
          log('✘ 任务点异常：' + job.jobName + ' → ' + (e && e.message ? e.message : e));
        }

        if (!CFG.autoAdvance) { log('自动切换已关闭，停止。'); S.running = false; break; }
        if (!S.running) break;
        log('等待页面提交任务点状态（超星有延迟）…');
        await sleep(8000);
      }
      S.phase = 'idle';
      log('循环结束。统计：' + JSON.stringify(S.stats));
    },

    stop(reason) {
      S.running = false;
      S.stoppedReason = reason || '';
      S.phase = 'idle';
      log('已停止：' + (reason || '用户操作'));
      uiRefresh();
    }
  };

  // ============================================================
  // 面板 UI
  // ============================================================
  let panel = null, logBox = null, statusEl = null;

  function fmtStats() {
    const s = S.stats;
    return '阶段=' + S.phase + ' | 任务点 成功' + s.tasksOk + '/失败' + s.tasksFail
      + ' | 测验提交' + s.quizOk + '/验证码跳过' + s.quizSkipCaptcha
      + ' | 题目 放弃' + s.qGiveUp + ' | 人脸停手' + s.faceStops;
  }

  function uiRefresh() {
    if (statusEl) statusEl.textContent = fmtStats();
    if (logBox && LOG.length) {
      logBox.value = LOG.slice(-200).join('\n');
      logBox.scrollTop = logBox.scrollHeight;
    }
  }
  function uiAlert(msg) {
    uiRefresh();
    if (!panel) return;
    panel.style.borderColor = '#e74c3c';
    panel.style.boxShadow = '0 6px 30px rgba(231,76,60,.5)';
    setTimeout(() => { if (panel) { panel.style.borderColor = '#2e86de'; panel.style.boxShadow = '0 6px 30px rgba(0,0,0,.35)'; } }, 3000);
  }

  function buildPanel() {
    if (panel) return;
    panel = document.createElement('div');
    panel.id = 'cx-helper-panel';
    panel.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
        <b style="flex:1">学习通任务点助手 v0.1</b>
        <a href="javascript:;" id="cx-min" style="color:#ccd">—</a>
      </div>
      <div id="cx-status" style="font-size:11px;color:#9cf;margin-bottom:6px"></div>
      <div style="display:flex;gap:6px;margin-bottom:6px">
        <button id="cx-start" style="flex:1">开始</button>
        <button id="cx-stop" style="flex:1">停止</button>
      </div>
      <div style="font-size:11px;line-height:1.9">
        <label><input type="checkbox" id="cx-enabled"> 总开关</label>
        <label style="margin-left:8px"><input type="checkbox" id="cx-advance"> 自动切下一任务点</label><br>
        <label><input type="checkbox" id="cx-muted"> 静音</label>
        <label style="margin-left:8px"><input type="checkbox" id="cx-resume"> 暂停后自动恢复</label><br>
        <label><input type="checkbox" id="cx-vquiz"> 视频内题目作答</label>
        <label style="margin-left:8px"><input type="checkbox" id="cx-quiz"> 章节测验作答</label><br>
        <label><input type="checkbox" id="cx-submit"> 自动提交测验</label>
        <label style="margin-left:8px"><input type="checkbox" id="cx-captcha"> 验证码提交前门禁</label>
      </div>
      <div style="font-size:11px;margin-top:6px">
        提供商
        <select id="cx-provider" style="width:100%">
          <option value="opencode-go">opencode-go</option>
          <option value="deepseek">deepseek 官方</option>
        </select>
        模型：<b>${LOCKED_MODEL}</b>（锁定，不可改）<br>
        API Key<br><input id="cx-key" type="password" style="width:100%" placeholder="只存在本机 GM 存储，不写入任何文件">
        <div style="color:#f9a;margin-top:4px">题干混淆时：
          <select id="cx-font">
            <option value="skip">跳过模型作答（安全）</option>
            <option value="raw">照发（可能乱码）</option>
          </select>
        </div>
        验证码选择器（真实观测后填）<input id="cx-cap-sel" style="width:100%" placeholder="如 .yzmImg,#yzmImg">
      </div>
      <div style="display:flex;gap:6px;margin:6px 0">
        <button id="cx-save" style="flex:1">保存设置</button>
        <button id="cx-dumplog" style="flex:1">导出日志</button>
      </div>
      <textarea id="cx-log" readonly style="width:100%;height:190px;font-size:11px;background:#111;color:#ccc;border:1px solid #333"></textarea>
      <div style="font-size:10px;color:#889;margin-top:4px">
        1.0x 真实速率 · 不 seek · 不自建超星请求 · 身份验证只检测不绕过<br>
        超星机制借自 ocsjs/ocsjs (MIT)
      </div>`;
    Object.assign(panel.style, {
      position: 'fixed', right: '14px', bottom: '14px', width: '330px', zIndex: 999999,
      background: '#1c2333', color: '#fff', padding: '10px', borderRadius: '8px',
      fontFamily: 'system-ui,Microsoft YaHei', fontSize: '12px',
      boxShadow: '0 6px 30px rgba(0,0,0,.35)', border: '1px solid #2e86de'
    });
    document.body.appendChild(panel);
    logBox = panel.querySelector('#cx-log');
    statusEl = panel.querySelector('#cx-status');

    const $id = s => panel.querySelector('#' + s);
    const bind = (id, key) => {
      $id(id).checked = !!CFG[key];
      $id(id).addEventListener('change', e => { CFG[key] = e.target.checked; if (key === 'enabled' && !e.target.checked) Sched.stop('总开关关闭'); });
    };
    bind('cx-enabled', 'enabled'); bind('cx-advance', 'autoAdvance');
    bind('cx-muted', 'muted'); bind('cx-resume', 'autoResumeOnPause');
    bind('cx-vquiz', 'videoQuizEnabled'); bind('cx-quiz', 'quizEnabled');
    bind('cx-submit', 'autoSubmit'); bind('cx-captcha', 'captchaGate');

    $id('cx-provider').value = CFG.provider;
    $id('cx-key').value = CFG.apiKey || '';
    $id('cx-font').value = CFG.fontStrategy;
    $id('cx-cap-sel').value = CFG.captchaSelectors || '';

    $id('cx-save').addEventListener('click', () => {
      CFG.provider = $id('cx-provider').value;
      CFG.apiKey = $id('cx-key').value.trim();
      CFG.fontStrategy = $id('cx-font').value;
      CFG.captchaSelectors = $id('cx-cap-sel').value.trim();
      saveCfg();
      log('设置已保存：provider=' + CFG.provider + ' model=' + LOCKED_MODEL
        + ' key=' + (CFG.apiKey ? '已配置' : '空') + ' font=' + CFG.fontStrategy);
    });
    $id('cx-start').addEventListener('click', () => {
      CFG.enabled = true; $id('cx-enabled').checked = true; saveCfg();
      if (S.running) { log('已在运行。'); return; }
      Sched.run();
    });
    $id('cx-stop').addEventListener('click', () => Sched.stop('用户点击停止'));
    $id('cx-dumplog').addEventListener('click', dumpLog);
    $id('cx-min').addEventListener('click', () => {
      const box = panel.querySelector('#cx-log');
      box.style.display = box.style.display === 'none' ? 'block' : 'none';
    });

    // 拖拽
    let dragging = false, ox = 0, oy = 0;
    panel.addEventListener('mousedown', e => {
      if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT' || e.target.tagName === 'BUTTON') return;
      dragging = true; ox = e.clientX - panel.offsetLeft; oy = e.clientY - panel.offsetTop;
    });
    document.addEventListener('mousemove', e => {
      if (!dragging) return;
      panel.style.left = (e.clientX - ox) + 'px';
      panel.style.top = (e.clientY - oy) + 'px';
      panel.style.right = 'auto'; panel.style.bottom = 'auto';
    });
    document.addEventListener('mouseup', () => { dragging = false; });

    uiRefresh();
  }

  // ============================================================
  // 启动
  // ============================================================
  function boot() {
    restorePrevLog();
    buildPanel();
    log('脚本已加载。v0.1.0');
    log('提示：请先在本面板配置 API Key 并保存，再点「开始」。');
    log('本项目：1.0x 真实速率 / 不自建超星请求 / 不拦截失焦事件 / 人脸与验证码只检测不绕过。');
    if (/mooc2-ans\.chaoxing\.com/.test(location.host)) {
      log('当前为 mooc2-ans 页面（只读取课程元数据，不启动任务）。请进入 mooc1 课程播放页。');
    }
    // 定时刷新状态
    setInterval(uiRefresh, 2000);
    window.addEventListener('beforeunload', flushLog);
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') setTimeout(boot, 1500);
  else window.addEventListener('DOMContentLoaded', () => setTimeout(boot, 1500));

  // 调试入口（P2 负向用例用）
  try {
    W.__cxHelper = {
      S, CFG, SAFETY, CX, Sched, Job,
      testGate: kind => {
        if (kind === 'captcha') {
          const fake = document.createElement('div');
          fake.id = 'cx-test-captcha';
          fake.className = 'yzmImg';
          document.body.appendChild(fake);
          const r = SAFETY.detectCaptcha(document);
          fake.remove();
          log('[测试] 验证码门禁 → ' + JSON.stringify(r));
          return r;
        }
        if (kind === 'face') return { hasFace: SAFETY.hasAnyFace() };
        if (kind === 'exam') return { isExam: SAFETY.isExamUrl(location.href) };
        return null;
      }
    };
  } catch (e) { }
})();
