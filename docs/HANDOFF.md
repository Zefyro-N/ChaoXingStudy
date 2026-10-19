# 交接文档（HANDOFF）

> **本文件用途**：让新会话（或未来的我 / 其他人）在**不回溯对话历史**的情况下，5 分钟内接手本项目。
> 历史细节在 `PROJECT.md`（§1–§26，1297 行）；**本文件只写"现在是什么状态、怎么继续"**。
>
> 归档时间：2026-10-18 · 归档时工作区：`E:\Code\ChaoXingStudy`

---

## 0. 一句话现状

**版本 `5.2.1-cxstudy.2` 已在 GitHub 公开发布并可正常安装；`5.2.1-cxstudy.3` 已在本地构建（含"多空题逐空显示与逐空复制"），但尚未实机验证、尚未发布。**

唯一待办：**实测 `.3` → 通过后发版**。

---

## 1. 怎么让我（AI）继续这个项目

**你只需要说这一句**（可直接复制）：

> 接着做 `E:\Code\ChaoXingStudy` 的学习通脚本。
> 先完整读 `docs/HANDOFF.md`，再读 `PROJECT.md` 的 §19（交接）与最后一章；
> 然后按 HANDOFF 的"§5 唯一待办"继续。

我会做的事（已写进文档，不必你再提醒）：
1. 读 `docs/HANDOFF.md` + `PROJECT.md` 末尾章节
2. `git -C refs/ocsjs log --oneline -5` 与 `git log --oneline -5` 核对进度是否与文档一致
3. 从 §5 的待办继续，并遵守 §7 的红线

**若你只说"继续学习通"，我应该主动去读这两个文件，而不是让你复述。**

---

## 2. 三条路径（先认清"哪个仓库是哪层"）

| 层 | 路径 | 什么时候动它 |
|---|---|---|
| **总项目（本地存档）** | `E:\Code\ChaoXingStudy` | 构建、测试、补丁导出、文档；**无 remote，不推送** |
| **fork 源码（真正改代码的地方）** | `E:\Code\ChaoXingStudy\refs\ocsjs` | 所有源码修改都在这里（独立 git，上游基线 `8b25a3f4…`） |
| **发布仓库（公开）** | `E:\Code\ChaoXingStudy\.publish` | 只放产物与补丁；remote = `https://github.com/Zefyro-N/CXStudy.git` |

上游项目：`ocsjs/ocsjs`（MIT，作者 enncy）。本项目是**fork + 补丁**，不是自研。

**公开分发**：
- 安装链接 `https://raw.githubusercontent.com/Zefyro-N/CXStudy/main/ocs.user.js`（`@updateURL` 指向此处）
- Releases `https://github.com/Zefyro-N/CXStudy/releases`（已发 `v5.2.1-cxstudy.1`、`v5.2.1-cxstudy.2`）

---

## 3. 状态快照（归档时刻，均已核实）

```
dist/ocs.user.js        484,656 bytes   @version 5.2.1-cxstudy.3   ← 本地已建，未发布
                          SHA256 9931282235c9f6ceb050be994e114fff81ec2ce9a25b0d0c016eca2a31e1b74c
.publish/ocs.user.js    481,758 bytes   = 已发布的 .2（线上就是这个）
                          SHA256 7A67DA07718F6E373754BC83E4839819B5B6A5CA136BFCE1A268A566B07BD8EB
patches/ocsjs-cxstudy.patch  505,148 bytes
```

| 仓库 | HEAD | 说明 |
|---|---|---|
| 外仓（本地） | `f454a99` | feat(blank): 多空题逐空显示与逐空复制 |
| `refs/ocsjs` | `939e2b5` | 同上（内层） |
| `.publish` | `bcfaf6c` | release: 版本递增至 5.2.1-cxstudy.2 |

三个仓库归档时**均为 clean**。

---

## 4. 已交付的能力（用户可见，按功能而非按编号）

**学习流程**
- 视频/音频/文档任务点自动推进，**锁定 1.0x**（无倍速、不拖拽、不改进度）
- 章节测验：字体解密 + 模型答题 + 自动提交（无人值守场景）
- 视频内弹题：模型作答（用户实测 100% 正确，**已冻结，不要动**）
- 文档/图片阅读自动完成；进页面自动跳到第一个未完成点；全部完成后从头复习

**答题辅助**
- 所有题目都会搜答案并给出**可复制**的答案
- 每题 `复制答案`；多空题 `第N空 [复制]` + `复制全部（按顺序）`
- 状态标注：`⚠ 随机填入`（很可能错）、`需手动作答`
- 主观题答案：显示 + 复制，**不自动填、不提交**
- 图片题：多模态；题干取不到时截图给模型
- **总开关**：关闭后不自动刷课/答题（面板手动「开始」不受影响）

**作业/考试（红线）**
- 默认**全关**，需**手动逐次**触发，必须风险声明，考试单独授权
- **只要含主观题，绝不自动提交**（连点击提交都不做）

**模型**
- 仅 `opencode-go` / `deepseek` 官方；模型锁 `deepseek-v4.1-flash`
- `max_tokens` 8192（推理模型会烧掉配额，低了会 content 为空）
- API Key 只存 GM 存储；面板有「测试连接」「清除」，输入框为密码遮罩

**界面**
- 单平台分支（已删除 yuketang/icve/icourse/zjy/zhs 等，约 7500 行），产物约 484KB（原 916KB）
- 已删除：播放倍数、使用教程、在线搜题（划词搜索）、百度一下、编辑框、桌面软件桥接、更新模块、面板缩放手柄

---

## 5. 唯一待办（从这里继续）

### 待办 1：实测 `5.2.1-cxstudy.3` 的「多空题逐空复制」

**背景**：用户指出主观题答案里各空用「、」分隔，应逐空显示与复制。
**做法（用户定的方向，正确）**：不猜分隔符，而是**用系统提示词规定模型输出格式** ——
题干有多个空时输出 `第1空：…` / `第2空：…`（各占一行），解析端只认这个格式。

**已完成的**：
- 提示词第 9 条（`packages/scripts/src/utils/cx-model.ts`）
- 解析器 `parseBlankAnswers`（`packages/core/src/core/worker/utils.ts`），**从严校验**：
  编号必须 1..N 连续顺序、每空非空、必须有冒号，否则返回空数组 → 回退整段显示
- 界面逐空渲染 + `复制全部（按顺序）`（`packages/scripts/src/elements/search.infos.ts`）
- 测试 `tests/blank-answers.test.ts`（20 项，已接入构建）

**离线已验**：4 套测试全绿（164 / 31 / 20 / 30）、平台校验通过、产物含新提示词与解析器。

**离线验不了、必须实测的**：**模型是否真的按新格式输出**。
- 成功 → 面板显示 `第1空 xxx [复制]` 逐行
- 未遵循 → 回退为整段显示（**不会出错，只是没有逐空**）→ 需调提示词（例如把格式要求前置、或加"违反格式视为错误"）

### 通过之后：发版 `.3`

```powershell
# 1. 递增版本号（两处都要改，见 §8 陷阱 3）
#    refs/ocsjs/scripts/build-core.js 里 version: '5.2.1-cxstudy.N'
#    refs/ocsjs/package.json 的 version
# 2. 重建 → 复制产物到 dist/
# 3. 导出补丁
# 4. 同步 .publish（ocs.user.js + patch），提交推送
# 5. 建 Release（附 ocs.user.js / ocsjs-cxstudy.patch / SHA256SUMS.txt）
# 6. 发布后验证：raw 链接与 release 链接的 SHA256 必须与本地一致
```

---

## 6. 明确不做的事（不要再提、不要擅自加）

| 项 | 结论 |
|---|---|
| 倍速 / 拖拽进度 / 改协议包 | **不做**（破坏 1.001x 验证与红线） |
| 面板拖拽缩放 | **不做** —— 试了 5+ 轮，用户最终决定放弃，已删净（见 §9 教训） |
| 人脸识别绕过、验证码识别/破解 | **不做**，只检测并停止 |
| 重做刷满分（M15） | **关闭**，不再考虑 |
| 章节测验外自动填入/提交 | **不做**（作业/考试只搜答案 + 可复制） |
| 主观题自动填/按空自动填 | **不做**（只显示 + 复制） |
| 拉取/恢复任何"辅助脚本"的外链 | 不做 |

---

## 7. 硬约束（代码级强制，改代码前必读）

1. **账号密码永不写入任何文件、永不交给第三方**；复用已有浏览器会话
2. **GitHub token 永不落盘**（只走环境变量；推送时 `credential.helper=` 置空）
3. **模型仅** `opencode-go` / `deepseek` 官方；**模型硬锁** `deepseek-v4.1-flash`
4. **1.0x 锁死**；不 seek、不拖拽、不发协议包
5. **作业/考试默认关**、手动触发、风险声明、考试单独授权
6. **含主观题绝不自动提交**
7. **总开关必须有**（关闭后无自动学习/答题，但面板手动可用）
8. 公式一律**纯文本可粘贴**（Unicode 符号，禁 LaTeX/KaTeX）
9. 这是**提效工具**，不是全自动答题机 —— 不做功能膨胀
10. **低复现问题不许猜**，要证据（截图/日志）

---

## 8. 构建、测试、导出（确切命令，Windows PowerShell）

### 8.1 环境前提

- Node：`D:\NVM\nvm\v18.20.8`（**必须 18**）
- 三个 `.env` 已就绪；依赖用 `pnpm install --node-linker=hoisted`
- **构建必须在 Windows PowerShell 里跑**（WSL 侧跑 tsx 会因 esbuild/Node 版本不一致失败）

### 8.2 构建（含 4 套测试，全绿才继续）

```powershell
cd E:\Code\ChaoXingStudy\refs\ocsjs
$R = 'E:\Code\ChaoXingStudy\refs\ocsjs'
$env:PATH = "D:\NVM\nvm\v18.20.8;$R\node_modules\.bin;$R\packages\core\node_modules\.bin;$R\packages\scripts\node_modules\.bin;$R\packages\utils\node_modules\.bin;" + $env:PATH
& .\node_modules\.bin\gulp.cmd -f .\scripts\build-core.js
# 产物：refs\ocsjs\release\ocs.user.js  → 复制到 dist\ocs.user.js
```

测试组成（构建前自动跑）：
`resolver.test.ts` 164 · `cx-model.handler.test.ts` 31 · `blank-answers.test.ts` 20 · `cx-videoquiz.test.ts` 30

### 8.3 导出补丁

```bash
base=$(cat patches/UPSTREAM_BASE.txt)
paths=$(git -C refs/ocsjs diff --ignore-cr-at-eol --numstat $base HEAD | awk '$1+0!=0||$2+0!=0 {print $3}' | grep -v '^\.npmrc$' | tr '\n' ' ')
git -C refs/ocsjs diff --ignore-cr-at-eol --output=/mnt/e/Code/ChaoXingStudy/patches/ocsjs-cxstudy.patch $base HEAD -- $paths
```

### 8.4 判断"真的有改动"（CRLF 噪音规避）

```bash
git status --short   # 会显示 ~114 个 M，全是 CRLF 噪音，不可信
git diff --ignore-cr-at-eol --numstat | awk '$1+0!=0||$2+0!=0'   # 用这个
```

---

## 9. 环境陷阱（重复踩过，务必避免）

**工具与环境**
1. **`bash` 工具 = WSL（Ubuntu, root）**，不是 cmd/Git Bash：无 `cd /d`、无 `>nul`（会建出真文件 `nul`）、**调不动 Windows 程序**（`Exec format error`）。Windows 操作用 `powershell` 工具。
2. **绝不用 PowerShell 读写中文源码**（GBK 破坏 UTF-8）；`Set-Content -Encoding utf8` 会写 BOM → tsx 报 `Error parsing`。
   写文件用 Python 算好内容 → 临时文件 → `os.replace`（**不要** `open(p,'wb').write(<表达式>)`）。
3. **PowerShell 不能传 bash heredoc**（`<<'MSG'` 直接失败）；`git commit -m $msg` 会把裸 `/` 当路径参数 → **用 `-F <文件>`**。
4. PowerShell `Select-String` **不区分大小写**（曾把注释里的 `[cxstudy` 误判成违规标记）。
5. **WSL 连不上代理** → 所有 GitHub 操作走 Windows PowerShell。
6. **同一时刻只能有一个 CDP 客户端**；常驻的日志收集进程会饿死其他 `connect_over_cdp`。

**构建**
7. **版本号要改两处**：`refs/ocsjs/scripts/build-core.js`（显式写死，**这是产物真正取用的地方**）
   与 `refs/ocsjs/package.json`。原因：构建流程里 package.json 的 version 不生效，
   而版本号决定油猴能否识别更新 —— 漏改会导致用户收不到更新。
8. **测试引 `@ocsjs/core` 会取到上一版 lib**（构建顺序是"先测试、后 tsc"）→ 测试里要**直接引源码路径**。
9. 测试若引入 `@ocsjs/core` 入口，会碰到 `HTMLElement` → 需 `tsx --require ./tests/setup-browser-env.cjs`，且 `cwd` 为仓库根。
10. 提示词通过 `${JSON.stringify(SYSTEM_PROMPT)}` 嵌入 handler 源码，换行会被转义 → 安全；
    **但**手写进模板字符串的 `\n` 会变成真换行，直接让 `Function()` 求值失败 → **所有题全炸**（踩过）。

**取证**
11. **OCS 面板在 closed shadow root 内** —— JS 读不到它的 DOM，只能靠控制台日志 + 截图。
    **因此无法实机验证的 UI 特性不要反复盲改**（见 §10）。
12. 字体解密参照表：`https://cdn.ocsjs.com/resources/font/font_ref_cx.bin`（需 `@connect ocsjs.com`）。

---

## 10. 本项目最重要的一次失败（务必读）

**面板拖拽缩放：连续 5+ 轮都没做成，最后被用户要求整体删除。**

根因不是技术难度，而是**方法错误**：

- 面板在 **closed shadow root** 内，我**无法用 CDP 检查它的真实 DOM**
- 我却连续多轮"推断结构 → 改代码 → 让用户安装 → 反馈失败 → 再推断"
- 用户成了我的测试机，浪费了大量时间；最后一轮交付的还不如不改

**沉淀为规则（写进项目约束）**：

> **无法实机验证的特性，不要用"推断 + 交付"的方式反复迭代。**
> 应当：① 先取得真实 DOM/日志证据；或 ② 一开始就明确声明"这个我验不了"；
> 或 ③ 把诊断能力**做进产物**（让脚本自己把结构打印/显示出来），用户一次截图即可定位。
> 绝不让用户承担我本该自己完成的验证。

---

## 11. 凭据与安全

- **曾有一个 GitHub token（`ghp_…`）在对话中明文暴露 → 用户应已撤销或需撤销**。
  今后推送建议：**细粒度令牌，仅本仓库 `Contents: Read and write`，7 天过期**。
- 产物安全性已审计：无字面 Key（`Authorization: "Bearer " + key` 是变量引用）、无题号/课程号/Cookie/本地路径/`.env`。
- 发布时 **MIT 合规**：保留上游版权与许可声明，LICENSE 用标准 MIT 结构（否则 GitHub 报 `NOASSERTION`）。

---

## 12. 相关文件索引

| 路径 | 作用 |
|---|---|
| `PROJECT.md` | **历史与决策全记录**（§1–§26）；§19 是旧交接章 |
| `docs/HANDOFF.md` | **本文件**（当前状态与续接方式） |
| `docs/cx-mechanisms.md` | 学习通机制说明（字体混淆、弹题、任务点等） |
| `README.md` | 面向用户/开源读者 |
| `LICENSE` | MIT（上游 + 派生） |
| `refs/ocsjs/` | fork 源码（改代码在这里） |
| `patches/ocsjs-cxstudy.patch` | 相对上游的可复现补丁 |
| `patches/UPSTREAM_BASE.txt` | 上游基线 commit |
| `dist/ocs.user.js` | 最新本地产物 |
| `tools/*.py` | 只读探针（浏览器/字体/面板/日志），见 `PROJECT.md` §19.4 |
| `.logs/` | 构建日志、发布材料（含各版本 SHA256SUMS） |
| `refs/ocsjs/tests/` | 4 套测试（构建前自动执行） |
| `cx-helper.user.js` | 早期自研参考实现，**仅参考，不参与构建** |
