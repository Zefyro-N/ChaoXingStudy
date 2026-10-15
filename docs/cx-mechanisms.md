# 超星学习通前端机制（借自 ocsjs，MIT）

> **来源与许可**：本文件是对 [ocsjs/ocsjs](https://github.com/ocsjs/ocsjs)（MIT License，3768★，
> 分支 `5.0`，commit `8b25a3f`）中 `packages/scripts/src/projects/cx.ts` 与
> `packages/scripts/src/utils/font-decrypt/` 的**阅读提炼**，不是逐行抄写。
> 保留此署名。ocsjs 是经过大量用户生产验证的实现，这些选择器与流程是它的核心资产。
>
> 本地参考副本：`refs/ocsjs/`（已 gitignore，不作为交付物）

## 1. 为什么借它而不是自己侦察

我们无法在无账号条件下对真实课程做 DOM 侦察。ocsjs 的 `cx.ts`（2450 行）就是一份**已被
生产验证的超星前端规格**，比任何猜测都可靠。这符合用户要求："尽量复用他人的成熟经验，不要给自己上强度"。

## 2. 任务点枚举

### 2.1 iframe 遍历
超星任务点分散在多层 iframe 中，递归收集所有**可访问** `contentWindow.document` 的 iframe
（跨域会抛异常，需 try/catch 跳过）：

```js
function searchIFrame(root) {
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
}
```

### 2.2 任务类型判据（iframe 内 DOM 特征）
| 任务类型 | 选择器 | 处理器 |
|---|---|---|
| 视频 / 音频 | `#video, #audio` | `media()` |
| 章节测验 | `.TiMu` | `chapter()` |
| 图片阅读 | `#img.imglook` | `read()` |
| **带音频的 PPT** | `.swiper-container` | `readPPTWithAudio()` |
| 超链接任务点 | `#hyperlink` | `hyperlink()` |
| 长时阅读 | `iframe[name="bookifame"][src*="timing"]` | `timereader()` |

### 2.3 任务点元数据
```js
// iframe 上的 data 属性是 JSON
const frame_data = JSON.parse(
  win.frameElement.getAttribute('data') ||
  // 带音频的 PPT 套两层 iframe，要往上再取一层
  win.frameElement.contentWindow.parent.frameElement.getAttribute('data') ||
  '{}'
);
const target_jobid = frame_data.jobid || frame_data._jobid;

// 顶层 unsafeWindow.attachments 是任务点数组
const attachment = unsafeWindow.attachments.find(a =>
  String(a.jobid || a.property._jobid) === String(target_jobid));

// 完成状态
const work_type = attachment.job ? 'job' : attachment.isPassed ? 'finished' : 'not-job';
// 名称 / 唯一键
const jobName = attachment.property.name || attachment.property.title
             || (attachment.property.bookname ? attachment.property.bookname + attachment.property.author : null)
             || '未知任务';
const mid = attachment.property.mid;   // 用于任务点去重
```

### 2.4 章节测验完成状态
```js
win.document.querySelector('.testTit_status')?.classList.contains('testTit_status_complete')
```

## 3. 课程目录与学习模式（`CXAnalyses`）

| 判据 | 选择器 / 表达式 | 含义 |
|---|---|---|
| 闯关/解锁模式 | `.catalog_points_sa, .catalog_points_er` 存在 | 特殊模式，任务点必须顺序完成 |
| 全部章节 | `[onclick^="getTeacherAjax"]` | 遍历章节元素 |
| 章节 ID | `onclick` 里 match `/\(('(.*)','(.*)','(.*)')\)/` 第 3 组 | chapterId |
| 章节未完成数 | `el.parentElement.querySelector('.jobUnfinishCount').value` | 是否还有任务点 |
| 当前章节 | `.posCatalog_active` | 活动章节 |
| 章节已完成 | 当前章节内 `.icon_Completed` 存在 | 章节完成标记 |
| 小节任务栏 | `.prev_ul li`（最后一个 `active` = 最后一小节） | 小节切换 |
| 章节下拉 | `.posCatalog_select` | 目录选择 |

**卡死检测**：同一 chapterId 重试 3 次仍不动 → 判定 stuck，跳过该章节（ocsjs 的做法）。

## 4. 视频 / 音频驱动

```js
const media = await waitForMedia({ root: doc });   // 轮询 'video,audio'
const videojs = doc.querySelector('#video,#audio'); // videojs 容器
unsafeWindow.top.currentMedia = media;             // 超星把当前媒体挂在 top 上
// 固定显示进度条
doc.querySelector('.vjs-control-bar').style.opacity = '1';
```

- 播放失败检测：`.vjs-modal-dialog-content` 的 innerText 含
  `'视频文件损坏' | '网络错误导致视频下载中途失败' | '视频因格式不支持' | '网络的问题无法加载'` → 跳过该任务点
- 播放恢复：监听 `pause` → 重新 `play()`（章节测验弹层关闭后必须靠这个恢复）
- ⚠️ **ocsjs 会 `media.currentTime = 0` 从头播**。本项目**不复刻**：真实速率方案下
  应从超星自己的断点续播处继续，重置为 0 是浪费已看时长。

### 4.1 视频内弹题（in-video quiz）
```js
submitBtn = doc.querySelector('#videoquiz-submit');        // 提交按钮
options   = doc.querySelectorAll('.ans-videoquiz-opt label'); // 选项
container = doc.querySelector('#video .ans-videoquiz');       // 容器
components= doc.querySelectorAll('.x-component-default');     // 需隐藏的包裹层
```
ocsjs 默认**随机选**（其配置注释自述"好像并不计算在分数内，所以可以忽略"）。
本项目改为**走模型作答**（用户要求），并在作答后收起容器。

## 5. 章节测验（`JobRunner.chapter`）—— 本项目的核心

### 5.1 题目 DOM 契约
| 目标 | 选择器 |
|---|---|
| 每题根 | `.TiMu` |
| 题干 | `.Zy_TItle .clearfix`（连线题另有 `.firstUlList` / `.secondUlList`） |
| 选项 | `ul li .after`（单选/多选）、`ul li label:not(.before)`（判断）、`ul li textarea, ul textarea`（填空） |
| 题型输入 | `input[id^="answertype"]` |
| 连线选择框 | `.thirdUlList .dept_select` |
| 阅读理解 / 完形填空 | `span.saveSingleSelect[data="答案"]` |

### 5.2 题型编号（超星自有，**与 ehuixue 完全不同**）
```js
0 单选 | 1 多选 | 2 简答 | 3 判断 | 4 填空 | 5 名词解释
6 论述 | 7 计算 | 8 其他(多为填空) | 9,10 填空族
11 连线 | 14 选词填空(fill) | 15 阅读理解(reader)
```
> 注意：非预览模式下页面存在**多个干扰用的 `type` input**，必须取
> `name` 匹配 `/type\d+/` 的那个的 `value`，否则题型判断会错。

### 5.3 题干清洗（超星专属冗余）
```js
text.replace(/^\d+[。、.]/, '')                 // 行首题号
    .replace(/（\d+\.\d+分）/, '')               // 分值
    .replace(/\(..题, \d+?分\)/, '')
    .replace(/\(..题, \d+\.\d+分\)/, '')
    .replace(/[[(【（](..题|名词解释|完形填空|阅读理解)[\])】）]/, '');
```
外加**零宽字符清洗**（ocsjs 未显式处理，本项目补上）：
`/[\u2002\u200b\u3000\u00a0\ufeff]/g`

### 5.4 作答与填答
- 单选/多选/判断：**点击选项元素**（不是设 value）。点击前检查
  `option.parentElement.querySelector('label input')?.getAttribute('checked') === 'checked'`
  或 `parentElement.getAttribute('aria-checked') === 'true'`（2023/9 新版），已选则跳过
- 填空/简答类：写 `option.parentElement.querySelector('textarea').value`，
  同时写 `option.parentElement.querySelector('iframe').contentDocument.body.innerHTML`，
  然后点 `[onclick*=saveQuestion]`
- 判断题选项文字可能是 `True`/`False`/`對`/`錯`，ocsjs 会改写 DOM 文本便于识别；
  **本项目不改写 DOM**，改为在模型侧按选项序号作答（见 §6）

### 5.5 【关键】提交流程（验证码门禁的插入点）
```js
frameWindow.btnBlueSubmit();      // ① 点「提交」
await sleep(3000);
frameWindow.submitCheckTimes();   // ② 触发「确认提交」弹窗（超星自己的函数）
top.$('#workpop').hide();         // ③ 2024/4 改版后需手动关掉残留弹窗

// 不满足提交条件时（未答满等）：
frameWindow.alert = () => {};     // 禁掉 alert 阻塞
frameWindow.noSubmit();           // 暂存
```
- **`btnBlueSubmit` 与 `submitCheckTimes` 之间就是人机验证门禁的唯一正确插点。**
  在 ② 之前扫描验证码特征；命中则**不调用 ②**，本次不提交，记录并跳过。
- 全程调用**超星页面自身的函数**，不自建任何请求 → 满足硬约束 #2。

## 6. 与 ehuixue 的关键差异（决定不能照抄 Estudy）

| 维度 | ehuixue（Estudy） | 超星（本项目） |
|---|---|---|
| 题型编号 | attr1: 1单选/2多选/3判断 | 0单选/1多选/3判断/4+填空/11连线/14选词/15阅读 |
| 选项定位 | `input[name=sq_xxx]` 的 `value` | `ul li .after` 等**元素**，点击而非赋值 |
| 判断题取值 | `1`/`2` | 元素序号，文字为 √/×/True/False/對/錯 |
| 提交 | `saveinfo(this,0)` + layer.confirm | `btnBlueSubmit()` + `submitCheckTimes()` |
| 任务点元数据 | `vue` 全局对象 | iframe `data` 属性 + `unsafeWindow.attachments` |
| 题干混淆 | 无 | `.font-cxsecret` + `@font-face` data URI |
| 播放器 | `player.getPosition()` | `waitForMedia()` → `video`/`audio` 元素 |
| 文档推进 | 无 | `.swiper-container` / `#img.imglook` / `timing` iframe |

## 7. 题干混淆字体 `.font-cxsecret`（ocsjs 的解法）

```js
const fontBuffer = extractFontFromStyle(doc, 'font-cxsecret');  // 从 @font-face data URI 取字体
const els = Array.from(doc.querySelectorAll('.font-cxsecret'))
  .map(f => f.querySelector('.after') || f);   // 有 .after 就取它，否则会连选项按钮一起删掉
const { map, details } = await crackFont(fontBuffer, collectChars(els), {
  refTableUrl: 'https://cdn.ocsjs.com/resources/font/font_ref_cx.bin'
});
decryptElements(els, map);
els.forEach(el => el.classList.remove('font-cxsecret'));
```

- 特征表为 FRB2 位打包格式，单平台约 **0.76MB**
- ocsjs 称该表"与平台加密方式无关，**无需随平台改字体而更新**"
- 只破解**页面实际出现的字符**（通常几十个），不做全字表扫描
- `details[].margin < 0.3` 表示置信度低，需告警
- 模块位置：`packages/scripts/src/utils/font-decrypt/`（bitmap.ts 400 / worker.ts 242 /
  ref-table.ts 92 / types.ts 77 / decryptor.ts 167），自包含，无第三方依赖，用 Web Worker 算

**结论（D4）**：不需要自研，也不需要多模态截图。移植该模块即可。
待办：把该模块 TS→JS 移植为单文件内嵌 Web Worker。

## 8. 人脸识别（ocsjs 的语义正合本项目约束 #3）

```js
// 旧版：#fcqrimg 的 img src 非空 = 人脸识别出现（src 为空串时不算）
// 新版：.chapterVideoFaceMaskDiv 的 style.display !== 'none' = 出现
// 出现后：提示"检测到人脸识别，请手动进行识别后脚本才会继续运行"，
//         轮询 3s 一直等，直到人脸消失才 resolve 继续
```
ocsjs **只检测 + 停下等待，绝不上传照片、绝不绕过**。本项目直接采用该语义。

## 9. 其他可复用点

| 点 | 实现 |
|---|---|
| 链接任务点 | 暂存 `a.onclick` → 改为 `() => false`（防弹窗）→ `click()` → 还原 |
| 长时阅读 | 从 `iframe[name="bookifame"]` 的 src 取 `timing` 参数，等 `(timing+3)*3` 秒 |
| 带音频的 PPT | 循环 `win.swiperNext?.()`，次数 = `.swiper-container .swiper-slide` 长度 |
| 图片阅读 | 直接调 `win.finishJob()`（⚠️ 见下方风险） |
| 进度条常显 | `.vjs-control-bar` 的 `opacity = 1` |
| 繁体字 | `對`/`錯` → `√`/`x`（ocsjs 的做法） |

## 10. 从 ocsjs 抄到的、本项目**明确不采用**的行为

| 行为 | ocsjs 位置 | 不采用的理由 |
|---|---|---|
| `rateHack()` 屏蔽倍速限制 | `cx.ts:1338`，模块名"屏蔽倍速限制" | 硬约束 #2。且 ocsjs 自己在 UI 上警告"高倍速可能导致学习记录清空/回退"，属于平台明确风控 |
| 屏蔽复制粘贴限制 | `cx.ts:673`，模块名"屏蔽复制粘贴限制" | 同属对抗性行为，非本项目所需 |
| `media.currentTime = 0` 重置进度 | `JobRunner.media` | 浪费已看时长；真实速率方案下应断点续播 |
| 视频内题目**随机**作答 | `videoQuizStrategy: 'random'` | 本项目按用户要求走模型 API |
| 章节测验答不出时**随机**作答 | `randomWork-choice` / `randomWork-complete` | 自动提交场景下随机=确定错答落库，本项目改为**放弃该题** |
| 直接调 `finishJob()` 秒过图片阅读 | `JobRunner.read` | 等于不做而标记完成，属"秒过"性质。本项目改为驱动真实翻阅，`finishJob` 仅作显式 opt-in |
| 作业/考试自动提交 | `workOrExam` 只填不提交 | 本项目范围仅章节测验；考试为硬禁区 |

## 11. 未知项（需要真实账号下验证，不能假设）

1. 本章程的 `.font-cxsecret` 特征表是否仍匹配当前超星字体（ocsjs 称不需更新，但未在本机验证）
2. 超星章节测验的验证码**究竟在哪个时点出现**（进卷 / 点提交 / 点确认）
3. "不提交直接离开"是否会留下"未交卷"记录
4. 章节测验错答是否可重做覆盖（决定错答是否不可逆）
5. `attachments` 的字段在闯关模式下是否与 `data` 属性一致
