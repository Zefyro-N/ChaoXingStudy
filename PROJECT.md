# 学习通（超星）任务点自动化（ChaoXingStudy）

## 1. 目的与范围

**目的**：在 `mooc1.chaoxing.com` 课程页自动推进**视频 / 音频 / 文档**三类任务点，并对**章节测验**
走 API 作答 + 自动提交；测验若出现人机验证，则在**提交前**放弃本次提交并跳过该任务点。
全程按真实速率（1.0x）挂机，不使用倍速、不拖动、不自建协议请求推进任务点。

**载体**：自研 Tampermonkey 用户脚本（决策 D1，见 §4）。脚本运行在**你已登录的浏览器**中，
不包含任何登录代码——这是"账号密码不进入任何文件与第三方工具"这一硬约束的最强满足方式。

**范围（明确的非目标）**

| 不处理 | 原因 |
|---|---|
| 【考试】 | 需本人完成，硬禁区 |
| 【人脸识别】课程进入 / 任务点进入 / 考试进入 | 硬约束 #3 |
| 验证码识别、滑块轨迹合成 | 硬约束 #3；本方案只**检测并跳过** |
| 倍速播放、拖动 seek、"秒过" | 硬约束 #2 |
| 自建 HTTP 请求推进任务点（协议发包） | 硬约束 #2 |
| 讨论 / 回帖 / 直播 / 签到 / 笔记任务点 | 超出本次范围 |
| 多账号、批量、代刷服务化 | 超出本次范围 |
| 登录流程逆向（超星密码走 CryptoJS 前端加密 + 图形验证码） | 无必要：脚本复用页面自身会话 |

## 2. 硬约束（四条，代码级强制）

| # | 约束 | 强制点 | 验证方式 |
|---|---|---|---|
| 1 | 账号密码不进入任何文件、不交给任何第三方工具 | 用户脚本**不含登录代码**；只复用浏览器现有 Cookie；API Key 存 GM 存储或读环境变量，**绝不写入项目文件** | 全项目 grep 凭据字面量；`git status` 检查无 state 文件入库 |
| 2 | 不使用倍速、不拖动、"秒过"、协议发包 | 不调用 `player.setPlaybackRate`；不调用 `seek`；进度上报**完全交给页面自身**；唯一外发请求是发往**你自己的 LLM API** | 运行期断言 `playbackRate === 1`；网络面板确认无自建超星请求 |
| 3 | 不碰人脸识别绕过、不识别/绕过验证码 | 检测到人脸弹窗 → 硬停手告警；检测到验证码 → **不提交**、跳过、告警 | 代码级双闸；负向用例测试 |
| 4 | 按真实速率挂机 | 任务点完成度只由真实播放/翻阅累积 | 抽查"页面已完成时长 vs 真实播放时长"无背离 |

**关于 blur / visibilitychange**：uXueScript 等工具会拦截页面失焦事件实现"后台防暂停"。
本项目**默认不启用该行为**。原因是超星教师端存在显式开关"**防窗口切换**：勾选后，学生在播放时
不能切换窗口，否则视频暂停"（见超星教师使用手册）。拦截该事件等于对抗一个教师显式开启的开关，
其结果可能出现在学习记录中。若确需后台挂机，改为「保持窗口前台聚焦」而不是拦截事件。

## 3. 架构（镜像 `E:\Code\Estudy` 的四层，新增安全层）

```
┌────────────────────────────────────────────────────────────────┐
│ 会话层  不需要实现                                              │
│   Tampermonkey 运行在你已登录的浏览器中                          │
│   零登录代码、零 Cookie 读写落盘                                 │
├────────────────────────────────────────────────────────────────┤
│ 适配层  cx_adapt.js —— 学习通站点适配（全部重写，与 ehuixue 不通用）│
│   任务点枚举 → 从页面自身的课程树数据读取（不猜接口）              │
│   播放器     → 视频 / 音频 元素的定位与状态读取（多层 iframe）      │
│   文档       → 翻页器（翻页按钮 / 进度条，**非滚动**，待 recon 确认）│
│   上报       → 完全交给页面自身的完成回调                        │
├────────────────────────────────────────────────────────────────┤
│ 任务层  调度器                                                  │
│   类型识别 → 分派视频/音频/文档处理器                            │
│   闯关/开放/上锁模式下的顺序推进（对应 Estudy 的 tasklock）        │
├────────────────────────────────────────────────────────────────┤
│ 答题层  AnswerProvider 链（新增）                               │
│   QuizbankProvider  → 本地题库精确匹配（零宽字符清洗后）           │
│   TextApiProvider   → 题干可直读时的文本作答                     │
│   VisionApiProvider → 题干被混淆时的截图 + 多模态兜底（待 recon）   │
│   放弃              → 全链失败时**放弃**，不做本地瞎猜（会落库）    │
│   提交 走站点自身 UI：填 → 点[提交] → 点确认弹窗                  │
├────────────────────────────────────────────────────────────────┤
│ 安全层（新增，双闸）                                             │
│   人脸弹窗  → 硬停手 + 告警                                      │
│   考试页面  → 硬禁区（URL 与 DOM 双重判据）                       │
│   验证码    → 提交前门禁：命中即放弃本次提交 + 跳过 + 告警         │
├────────────────────────────────────────────────────────────────┤
│ 审计层  cx_quizbank.json                                         │
│   交卷后回收正确答案，累计准确率，供复盘与题库沉淀                 │
└────────────────────────────────────────────────────────────────┘
```

**核心原则（继承 Estudy §3）**：**不重造 HTTP 请求**，只调用站点自身暴露的函数与数据。
字段永远是对的，站点改版时失效点集中且可定位。

## 4. 决策记录

| 编号 | 决策 | 结论 | 权衡 |
|---|---|---|---|
| **D1** | 实现载体 | **自研油猴脚本** | 唯一同时满足全部四条硬约束；Tampermonkey 天然跨页存活（避开 core.js "刷新后需重粘"）；完全可审计。放弃 uXueScript 桌面端（登录态交给第三方 WebView，违反约束 #1）与 core.js（四个新增模块都要改压缩产物） |
| **D2** | 章节测验 | **自动作答 + 自动提交** | 已明确接受"错答真实落库"的风险。因自动提交无人工复核，答题链**不设本地瞎猜兜底**，全链失败即放弃该题 |
| **D3** | 人机验证 | **提交前检测 → 不提交 → 跳过该任务点** | 检测点必须在点击提交**之前**；若超星只在提交时投验证码，则本次不提交（避免产生错答与未交卷记录），记录后继续下一任务点 |
| **D4** | 混淆字体 `font-cxsecret` | **不自研，移植 ocsjs 的 `font-decrypt` 模块** | 已确认超星确实用 `.font-cxsecret` + `@font-face` data URI 做字形置换。ocsjs 的解法：只破解页面实际出现的字符（通常几十个），比对参照表 `font_ref_cx.bin`（约 0.76MB，FRB2 位打包），其自述"无需随平台改字体而更新"。比自研或截图+多模态都更稳、更省 |
| **D5** | 参考项目 | **ocsjs/ocsjs（MIT，3768★，分支 5.0，commit 8b25a3f）** | 唯一同时满足"成熟 + 活跃 + MIT + 油猴形态 + 支持超星"的候选。已克隆到 `refs/ocsjs`（gitignore），机制提炼见 `docs/cx-mechanisms.md`。淘汰 `pang-qin/chaoxing-toolkit`（52★、**无许可证**、4 个月停更）与 `kukuqi666/chaoxing-script-ai`（形态合适但内容单薄） |

## 5. 风险（如实，不美化）

**平台侧**
1. 学习通任务点进度由播放心跳与页面停留时间累积，脚本能保证"页面不暂停"，**不能伪造真实时长**。
   这正是"按真实速率"这条约束唯一真正有效的地方。
2. 自动提交的行为特征：题干停留时间≈0、无鼠标轨迹、交卷间隔过于整齐。
3. 多端并发（挂机期间同时在手机 App 看同一门课）本身是异常信号。
4. 教师可开启"防拖拽""防窗口切换""防倍速"，服务端下发；本方案不绕过，只如实遵守。
5. 超星对题干做 `font-cxsecret` 混淆并对文本插入零宽字符（u+2002 / u+200b / u+3000），
   直接影响答题链的可行性——待 recon 确认（D4）。

**处置后果（用户已知情，原文保留）**：学习记录清零 → 再犯总评 0 分 → 三次按作弊处理。多校已通报。

**不可逆性提示**：D2 选择自动提交后，错答会真实记入课程成绩构成。是否可重做覆盖**取决于课程设置**，
侦察第 4 项必须给出结论；若不可重做，则错答不可逆。

**能力缺口（需手工）**
- 考试、人脸识别环节、讨论/直播/签到类任务点。
- 验证码命中后的那次测验（由 D3 主动放弃）。

## 6. 技术障碍（与参考项目 ehuixue 的差异）

| 障碍 | 说明 |
|---|---|
| 站点适配层零复用 | ehuixue 的 `vue.editpart` / `player.onComplete` / `tanchu` / `saveinfo` 在超星不存在。超星是 `mooc1.chaoxing.com` + 多层 iframe 结构，适配层必须重写 |
| 题干混淆字体 | 见 D4。这是"接 API 答题"的最大技术风险 |
| 零宽 Unicode 污染 | 题库精确匹配前必须清洗 u+2002 / u+200b / u+3000 |
| 文档推进方式 | 超星教师手册明确"展开中翻页主要是点击翻页按钮或拖动进度条，**不可滚动翻页**"。第三方工具的"PDF 自动滚到底部"在超星可能是错的，必须实测 |
| 判断题取值 | 可能是 1/2 而非 A/B（Estudy §6 踩过），recon 第 4 项确认 |

## 7. 验证结果

> 每次验证必须记录：**真实命令 / 真实输出 / 通过或失败**。禁止只写结论。
> 「未验证」= 无账号条件下的客观限制，不是已完成。

| 验证项 | 证据 | 结果 |
|---|---|---|
| `node --check cx-helper.user.js` | `D:\Nodejs\nodejs\node.exe --check` → 无输出，退出码 0 | ✅ 通过 |
| 脚本行数 | 1126 行（含面板 UI 与注释） | ✅ |
| 占位符残留扫描 | `grep -nE 'LICENSED_MODEL\|TODO\|FIXME\|XXX'` → 仅命中 uuid() 正则里的 `xy`，无占位符 | ✅ 通过（发现 1 处笔误并修正） |
| 凭据零落盘 | `git grep -niE 'sk-[A-Za-z0-9]{10,}\|oc_sk_\|password\s*[:=]\s*["'']'` → 无命中 | ✅ 通过 |
| 超星机制提取（代替 recon） | `docs/cx-mechanisms.md`，全部来自 ocsjs 生产验证代码 | ✅ 完成 |
| 任务点枚举（attachments + data 属性） | — | ⚠️ 未验证（需真实课程页） |
| 视频/音频 1.0x 推进 | 代码已锁 1.0x，但无实机运行 | ⚠️ 未验证 |
| 文档 / PPT / 长时阅读推进 | 选择器来自 ocsjs，但翻页入口用了多选择器启发式 | ⚠️ 未验证（最高风险项） |
| 章节测验作答 + 自动提交 | 流程已按 ocsjs 的 `btnBlueSubmit`→`submitCheckTimes` 实现 | ⚠️ 未验证 |
| 验证码提交前门禁 | 代码级实现，可用 `__cxHelper.testGate('captcha')` 离线触发 | ⚠️ 仅能离线自测，真实验证码时点未知 |
| 人脸弹窗硬停手 | 采用 ocsjs 的只检测不绕过语义 | ⚠️ 未验证 |
| 题干混淆字体还原 | **未实现**（仅检测 + 告警 + 跳过） | ❌ 未完成（下一阶段） |

## 8. 文件清单

| 文件 | 作用 |
|---|---|
| `PROJECT.md` | 本文件：定位、非目标、硬约束、决策、风险 |
| `docs/cx-mechanisms.md` | **超星前端机制知识库**（借自 ocsjs，MIT，含署名与本项目不采用的行为清单） |
| `cx-helper.user.js` | **油猴主程序 v0.1.0**（1126 行，语法已校验，未实机验证） |
| `tools/cx_launch.py` | 启动带调试端口的独立浏览器（headed，不登录），供 CDP 附着 |
| `tools/cx_observe.py` | **阶段 A 只读观测**：抓 iframe 树 / 任务点判据 / 混淆字体 / 验证码特征 / attachments / 截图 |
| `tools/probe_browser.py` | 能力探测脚本（已证实本机可驱动可见浏览器并截图回读） |
| `.browser-profile/` | 自动化专用浏览器资料目录（含登录态 Cookie，**gitignore，用完可删**） |
| `prompts.md` | 早期阶段提示词（P0 侦察 / P1 实现 / P2 验收）。已改由直接施工，保留作参考 |
| `refs/ocsjs/` | 第三方参考仓库（只读，gitignore，非交付物） |

### 内部模块（`cx-helper.user.js`）

| 模块 | 职责 | 状态 |
|---|---|---|
| `CFG` / 面板 UI | 配置与操作界面，模型锁定 `deepseek-v4.1-flash` | ✅ |
| `askModel()` | 模型调用，1:1 复刻 Estudy 的请求构造/鉴权头/`reasoning_content` 兜底 | ✅ |
| `CX` | 超星适配层（iframe 遍历、任务点枚举、题型编号、媒体定位） | ✅ |
| `SAFETY` | 人脸检测、验证码提交前门禁、考试禁区 | ✅ |
| `Job.media()` | 视频/音频 1.0x 推进 + 弹题作答 + 暂停恢复 | ✅ |
| `Job.chapter()` | 章节测验作答 + 自动提交 + 验证码门禁插点 | ✅ |
| `Job.read/readPPTWithAudio/timereader/hyperlink` | 文档类任务点 | ⚠️ 翻页入口为启发式，待实机校正 |
| `FONT` | `.font-cxsecret` 检测；**还原未实现** | ❌ 下一阶段 |
| `Sched` | 任务点调度与闯关模式推进 | ✅ |

## 9. 参考

- `E:\Code\Estudy\PROJECT.md` —— 同架构项目（ehuixue.cn）的完整站点逆向、陷阱清单、超时参数表。
  复用其**方法论**（不重造 HTTP 请求、白名单而非黑名单、两步提交、审计回收），
  **不复用其安全策略**（该项目硬禁章节测验，与本项目 D2 相反）。
- 超星学习通教师使用手册（防拖拽 / 防窗口切换 / 任务点设置 / 文档翻页机制）
- 超星学习通学生使用指南（学习模式：闯关 / 开放 / 上锁）

## 10. 复用性验证结论（ocsjs）—— 已实测

**结论：可以复用，而且应当以「fork + patch + 重建」为项目核心，不再重写驱动层。**

### 10.1 构建已真实跑通（证据）

| 项 | 证据 |
|---|---|
| 构建命令 | `node_modules\.bin\gulp.cmd -f .\scripts\build-core.js`（绕开 pnpm 的依赖校验） |
| 退出码 | `exit=0`，`Finished 'default' after 12 s` |
| 上游自带测试 | `testResolver` → **✅ 164 通过 ❌ 0 失败** |
| vite 编译 | core 140 模块；scripts 194 模块，无错 |
| 产物 | `release/ocs.user.js` **932,939 bytes**（主交付物）、`ocs.common.user.js` 933,111、`core.js` 185,018、`index.js` 872,714、`ocs.meta.js`、`style.css` |
| 产物元数据 | `@version 5.2.1`、`@license MIT`、**34 个 `@match`**（含 `*://*.chaoxing.com/*`）、`@run-at document-start`、含 `GM_xmlhttpRequest` |

完整可复现配方见 skill `build-ocsjs-userscript`。

### 10.2 三个坑（非代码缺陷，均为环境漂移）

1. **缺 `.env`**：`vite.config.ts` 的 `outDir: process.env.VITE_BUILD_PATH` 无默认值 → vite 执行 `path.resolve(root, undefined)` → `TypeError [ERR_INVALID_ARG_TYPE]: "paths[1]"`。
   报错栈指向 vite 内部的 `resolve` 定义行，**极易误判为 Node 版本不兼容**（实测 Node 24 与 Node 18 报同一个错）。
   修法：照 CI 手动建 `scripts/.env`、`packages/core/.env`、`packages/scripts/.env`。
2. **`node-linker=hoisted` 未生效**：仓库 `.npmrc` 里写了这行，但 pnpm 10+/11 不再读它，出来的是隔离布局 → `packages/scripts` 看不到 `packages/core` 声明的 `@types/lodash` → `TS7016 Could not find a declaration file for module 'lodash/debounce'`。
   修法：`pnpm install --node-linker=hoisted`。
3. **`packages/utils` 需先单独编译**：`build-core.js:9` 在编译任何东西之前就 `require('../packages/utils')`。
   修法：`tsc -p packages/utils/tsconfig.json`（即上游 `scripts/tsc.js` 的第一步）。

另：`pnpm 11` 的供应链策略会把 `pnpm run build` 的依赖校验判为失败（`ERR_PNPM_IGNORED_BUILDS`），直接调 gulp 即可。

### 10.3 免费得到的能力（不用写一行代码）

任务点枚举（`attachments` + iframe `data` 属性）、iframe 递归遍历、音频/视频播放器驱动（`#video,#audio`）、文档与长时阅读、章节测验 DOM 契约与提交流程（`btnBlueSubmit`→`submitCheckTimes`）、题型编号体系、人脸识别“只检测不绕过”语义、`.font-cxsecret` 混淆字体还原（含参照表）、OCSWorker + 题型 resolver 答题框架、通用 HTTP 答题器、面板 UI/日志/配置系统、34 个域名 `@match`。

**关键**：它的答题器是「`url` + `headers` + 一段可执行 `handler` 字符串」的通用 HTTP 答题器，因此本项目要的 `opencode-go` / `deepseek` 属于**原生配置能力**，不需要改源码。

### 10.4 必须改造的清单（这就是“自研部分”）

每项都给了精确定位，便于 patch：

| # | 改造 | 位置 | 对应约束 |
|---|---|---|---|
| M1 | `@connect` 白名单加 `opencode.ai`、`api.deepseek.com` | `scripts/build-core.js` metadata.connect（现仅 7 个域名，**不加则模型请求会被脚本管理器拦截**） | —— |
| M2 | 模型锁定：只允许这两个提供商 + 锁死 `deepseek-v4.1-flash` | 答题器配置层 | —— |
| M3 | 删除 `rateHack()`（“屏蔽倍速限制”）与倍速配置项，强制 1.0x | `cx.ts:664`、`cx.ts:669`、`cx.ts:1338`、`cx.ts:227` | #2 |
| M4 | 删除“屏蔽复制粘贴限制” | `cx.ts:673` | #2 |
| M5 | 视频内题目由“随机”改为模型作答 | `cx.ts:229`（默认 `random`）、`cx.ts:1839`、`cx.ts:1841` | D2 |
| M6 | 答不出时不再随机作答，改为放弃该题 | `cx.ts:2144`、`cx.ts:2152`、`cx.ts:2158` | D2 |
| M7 | **新增**验证码提交前门禁（OCS 完全无此能力） | 插在 `cx.ts:2232` `btnBlueSubmit()` 与 `:2238` `submitCheckTimes()` 之间 | #3 |
| M8 | 不重置播放进度（断点续播） | `cx.ts:1908` `media.currentTime = 0` | #2 |
| M9 | 图片阅读不调 `finishJob()` 秒过 | `cx.ts:1923`~`1925` | #2 |
| M10 | 禁用考试自动答题（硬禁区） | `cx.ts` 作业/考试入口 | #3 |

### 10.5 对载体决策 D1 的影响

D1 原选择“自研油猴脚本”的理由之一是“完全可审计”。实测后修正为：
**以 ocsjs 为基座做 fork + patch**，理由：驱动层（2450 行 `cx.ts` + 答题框架）已在生产验证，重写它属于用户明确反对的“给自己上强度”；
而需改动的 10 项全部集中在可定位的单点，构建闭环仅 12s，改进成本极低。
`cx-helper.user.js`（本轮已写的 1126 行）**降级为对照参考与门禁逻辑的设计底稿**，不再作为主交付路径。

## 11. 改造进度（施工中）

补丁：`patches/ocsjs-cxstudy.patch`（4 个文件，+140 −11）。复现步骤与陷阱见 `patches/README.md`
与 skill `build-ocsjs-userscript`。

| 编号 | 改造 | 状态 | 验证方式 |
|---|---|---|---|
| M1 | `@connect` 接入 `opencode.ai` / `api.deepseek.com` | ✅ 完成 | 产物中 `Select-String '@connect'` 已命中两个域名 |
| M2 | `headers` 接通 `${}` 占位符 + 注入稳定会话 ID `${__session}` | ✅ 完成 | 产物含 `__session` |
| M3 | 倍速锁定 1.0x、禁用 rateHack | ✅ 完成 | 产物含 `本分支锁定 1.0x`；`cx.ts` 中活动赋值仅 `playbackRate = 1` |
| M4 | 禁用屏蔽复制粘贴 | ✅ 完成 | 产物含 `__cxstudy_never_matches__` |
| M7 | **新增验证码提交前门禁** | ✅ 代码级 | 产物含 `__cxstudyDetectCaptcha` + `cxstudy M7`；**待实机验证** |
| M8 | 不重置播放进度 | ✅ 完成 | `cx.ts` 中仅剩注释行 |
| M9 | 禁用 `finishJob()` 秒过 | ✅ 完成 | 产物含 `cxstudy M9`；**行为变更风险最高，待实机验证** |
| M10 | 考试硬禁区 | ✅ 完成 | 产物含 `cxstudy M10` |
| M5 | 视频内题目：随机 → 模型作答 | ⬜ 待做 | 需把 `answererWrappers` 接入 `JobRunner.media` |
| M6 | 答不出不再随机，改为放弃 | ⬜ 待做 | `cx.ts` 的 `randomWork-choice` / `randomWork-complete` |

### 11.1 验证记录（真实命令与输出）

| 项 | 证据 | 结果 |
|---|---|---|
| 构建 | `node_modules\.bin\gulp.cmd -f .\scripts\build-core.js` → `exit=0`，`Finished 'default' after 22 s` | ✅ |
| 上游单测 | `testResolver` → `✅ 164 通过 ❌ 0 失败 共 164 项` | ✅ |
| 产物版本 | `// @version  5.2.1-cxstudy.1`（证明版本号补丁生效） | ✅ |
| 产物大小 | `release/ocs.user.js` = 936,546 bytes（上游为 932,939） | ✅ |
| 补丁可重放 | `git apply --check -R patches/ocsjs-cxstudy.patch` → 通过 | ✅ |
| 编码完整性 | `package.json` 中文描述仍为 `在线网络课程辅助工具`，无 `鍦ㄧ嚎` 乱码 | ✅ |

### 11.2 施工中踩到的两个自身失误（已修正，记录以免重犯）

1. **类型收窄**：M3 把 `playbackRate` 配置从 `{...playbackRate}` 改成字面量对象后，
   `cfg.playbackRate` 由 `any` 收窄为 `string`，连带三处 TS 报错（`TS2365`/`TS2322`/`TS2345`）。
   用 `{...} as any` 保住上游的类型宽度。
2. **PowerShell 破坏 UTF-8**：用 `Get-Content -Raw` + `Set-Content` 改 `package.json`，
   在 zh-CN 下按 GBK 解码 UTF-8 源码，把中文描述写成乱码并顺带改了行尾。
   已用 `git checkout` 回滚，改用 edit 工具做定点替换。**以后禁止用 PowerShell 读写含中文的源码文件。**
3. **BOM 导致构建失败**：`Set-Content -Encoding utf8` 会写入 UTF-8 BOM，`tsx` 解析 `package.json` 直接报
   `Error parsing: package.json`。需用 `UTF8Encoding($false)` 无 BOM 写入。
