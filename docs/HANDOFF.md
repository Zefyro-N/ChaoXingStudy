# 交接文档（HANDOFF）

> **用途**：让新会话在**不回溯对话历史**的情况下 5 分钟内接手。
> 历史细节见 `PROJECT.md`（§1–§26）；**答题准确率专题**见 `docs/analysis-answer-accuracy.md`（§1–§9）。
>
> 最后更新：`5.2.1-cxstudy.8` 完成后（本地已构建，**未发布**）。

---

## 0. 一句话现状

**本地版本 `5.2.1-cxstudy.8`（488,475 B，测试 302 项全绿）已就绪但未发布；
GitHub 上仍是最早的 `5.2.1-cxstudy.2`，落后 6 个版本。**

当前工作主线：**提升答题正确率**。已完成"格式层"改造（选择题只输出字母 + 保守归一化 + 质量优先提示词 + 随机兜底默认关），
**下一步是有真实样本后做 DOM 探针，解决"公式选项残缺"这条最后的准确率短板。**

---

## 1. 怎么让我续接（用户只需说一句）

> 接着做 `E:\Code\ChaoXingStudy`。先读 `docs/HANDOFF.md` 和 `docs/analysis-answer-accuracy.md`，
> 然后按 HANDOFF §8 待办继续。我这边有测试样本了，先做探针。

我会主动做的：读这两份文档 → `git -C refs/ocsjs log --oneline -5` 核对进度 → 从 §8 待办继续 → 遵守 §9 红线。

---

## 2. 三层仓库

| 层 | 路径 | 说明 |
|---|---|---|
| 总项目（本地存档） | `E:\Code\ChaoXingStudy` | 构建、测试、补丁、文档；**无 remote** |
| fork 源码（改代码处） | `E:\Code\ChaoXingStudy\refs\ocsjs` | 独立 git；上游基线 `8b25a3f4…` |
| 发布仓库（公开） | `E:\Code\ChaoXingStudy\.publish` | remote `https://github.com/Zefyro-N/CXStudy.git`；分支 `main` |

安装链接：`https://raw.githubusercontent.com/Zefyro-N/CXStudy/main/ocs.user.js`

---

## 3. 状态快照（2026-11）

```
dist/ocs.user.js     488,475 B   @version 5.2.1-cxstudy.8
                      SHA256 9e2c53fe9205982223ac9b77530a392b5303ae0db80fa3b4c39162a404f1d68f
.publish/ocs.user.js 481,758 B   @version 5.2.1-cxstudy.2   ← 线上就是这个（落后 6 版）
patches/ocsjs-cxstudy.patch      （每次提交前重新导出）
```

| 仓库 | HEAD |
|---|---|
| 外仓 | `829de8a` feat: 随机兜底改为默认关闭 |
| `refs/ocsjs` | `ae42e6c` 同上 |
| `.publish` | `bcfaf6c`（release .2） |

**测试（构建时自动跑，全绿才产出）**：`resolver 164` + `cx-model.handler 88` + `blank-answers 20` + `cx-videoquiz 30` = **302**

---

## 4. 本轮改动：`.2 → .8`（每个都有动机与证据）

| 版本 | 改动 | 依据 |
|---|---|---|
| `.3` | 多空题逐空显示与复制（提示词规定「第N空：」格式） | 用户要求 |
| `.4` | **模型名按提供商分开**：opencode-go `deepseek-v4.1-flash` / deepseek 官方 `deepseek-flash` | 实测官方 `GET /models` 只有 `deepseek-flash`、`deepseek-v4-pro`；传 v4.1-flash 直接 400 |
| `.5` | **选择题只输出选项字母** + 响应归一化 | 10 道线性代数实测：输出全文 40% → 只输出字母 90% |
| `.6` | **修复 .5 归一化误伤填空题**（改保守） | 26 个填空答案差分，.5 误改 7 处（`A、B 两点间距离`→`A` 等） |
| `.7` | **提示词改「质量优先」结构化版** | 用户指出旧版只讲格式、不讲正确率，且第 6 条鼓励瞎猜 |
| `.8` | **随机兜底默认关闭**（`cxRandomFallback: true → false`） | 随机答案必然判错却显示"已作答"，且写进真实成绩 |

### 4.1 关键发现（准确率专题的核心结论）

1. **模型分析能力没问题**：干净选项下，旧/新提示词都是 **10/10**
2. **瓶颈是"输出格式 → 匹配"**：线性代数选项彼此极像（差一个符号/顺序/系数），
   "输出选项全文 + 相似匹配"会**静默挑错**（实测 40%）
3. **只输出字母 = 严格占优**：干净场景一样是 100%，真实场景 90%（+50pp）
4. **归一化必须保守**：拿不到题型时，"不明确就不动"

### 4.2 当前提示词结构（`cx-model.ts` 的 `SYSTEM_PROMPT`）

```
# 角色          → 严谨解题专家，唯一目标是答案正确
# 工作方式      → 1 先完整推导（不输出）2 必须自检 3 信息不足选最自洽 4 禁止编造 5 不拒绝作答
# 输出格式      → 1 单选只输出字母 2 多选 A,C 3 判断不加标点 4 填空只输出答案
                  5 多空题「第N空：」换行 6 主观题分点 7 [图片N] 说明 8 数学纯文本 9 禁止前后缀
```

### 4.3 响应归一化（`makeResponseHandler`，保守）

只在"整段明显是选择题/判断题答案"时改写，其余原样返回：

| 触发 | 例子 |
|---|---|
| 判断题=极性词 | `错误。`→`错误`、`×`→`错误`、`True`→`正确` |
| 判断+简括注 | `错误（该说法不成立）`→`错误` |
| 单选=单字母（可带括号） | `(B)`→`B` |
| 多选=字母带分隔符 | `A、C`→`A,C`、`A，C`→`A,C` |
| 显式前缀（必须带冒号/是） | `答案：C`→`C`、`答：2x+1`→`2x+1` |
| 口语化短句 | `应该选 D`→`D` |
| **其它** | **原样返回**（填空/主观/多空/选项原文） |

> ⚠️ 不要放宽！v5 就是放宽后把填空题弄坏的（`选项一`→`一`、`A、B 两点间距离`→`A`）。

---

## 5. 测量基建（本轮新增，务必复用）

| 资产 | 用途 |
|---|---|
| `tools/math-bench-questions.json` | **10 道线性代数题**（题干/选项/正确答案/陷阱说明），答案人工核算 |
| `tools/math-bench.mjs` | 基准脚本；变体 `O`=旧版全文输出、`A`=当前发货（字母）、`B`=精简版、`V2`=质量优先版 |
| `docs/analysis-answer-accuracy.md` | 完整分析报告（§8 数学实测、§9 填空题事故复盘） |

**用法**（Key 只从环境变量读，不落盘）：

```powershell
cd E:\Code\ChaoXingStudy
$env:DEEPSEEK_API_KEY = "sk-..."     # 用完请吊销
node tools/math-bench.mjs                          # 干净选项
node tools/math-bench.mjs --garble-options         # 模拟页面公式选项提取失败
node tools/math-bench.mjs --garble-options --only A,V2
```

**已得数字**（选项扰动场景）：`O`(旧版全文) **40%** ／ `A`(字母) **90%** ／ `B`(字母) 90%
`V2`（质量优先，即当前发货的 .7/.8 提示词）**尚未 A/B 实测**（Key 已吊销）。

---

## 6. 环境陷阱（重复踩过）

1. **构建必须在 Windows PowerShell**：Node 18（`D:\NVM\nvm\v18.20.8`）+ 各包 `node_modules/.bin` 进 PATH + `gulp -f ./scripts/build-core.js`
2. **WSL 里的 `bash` 工具**：不能跑 Windows 程序、无 python、`>nul` 会创建真文件
3. **响应处理器以字符串形式被 `Function()` 求值** → 正则必须写 `\\s`（双反斜杠），
   写成 `\s` 会被吃掉变成 `s`（.5 的真实 bug，测试抓到的）
4. **测试引 `@ocsjs/core` 会取到旧 lib** → 测试里直接引源码路径
5. 需要 jsdom 的测试用 `tsx --require ./tests/setup-browser-env.cjs` 且 `cwd` 为仓库根
6. **版本号要改两处**：`scripts/build-core.js`（产物真正取用处）+ `package.json`
7. PowerShell 传中文用 `-Encoding UTF8`；`git commit -F <文件>`（别用 `-m`）
8. **已保存的 GM 配置会覆盖默认值** → 改默认值（模型名、随机兜底）后必须让用户**在面板里手动改一次**

---

## 7. 用户明确要求 / 红线

- **不改倍速、不拖拽、不伪造协议包**；不做人脸/验证码绕过（只检测并停止）
- **作业/考试**：默认关闭、手动逐次触发、需风险声明、考试单独授权；**含主观题绝不自动提交**
- **主观题**：显示 + 复制，不自动填、不提交
- 模型仅 `opencode-go` / `deepseek 官方`；**模型名按提供商不同**（见 §4）
- 总开关必须存在；面板必须有「测试连接」「清除 Key」；Key 只存 GM 存储
- **不要在无法验证的情况下反复交付**（面板缩放的惨痛教训 → 见 `PROJECT.md` §10）

---

## 8. 待办（按优先级，从这里继续）

### P0 · 选项字母映射错位（**2026-11-11 已实测确证，最优先**）

真实作业页（线性代数，18 题）实测：**选项在页面上被打乱**，可见顺序 ≠ 原始字母。

```
Q1  A. text='A A'  aria='A A选择'
    B. text='B D'  aria='D D选择'   ← 可见 B 实际是原始 D
    C. text='C C'  aria='C C选择'
    D. text='D B'  aria='B B选择'   ← 可见 D 实际是原始 B
```

→ 模型看到的是**可见顺序**，站点要的是**原始字母**；不映射就必然错位。
这正是历史现象「我的答案 A / 正确答案 B」的真因，**不是模型答错**。

**做法**：从 `.answerBg` 的 `aria-label`（形如 `"B B、xxx,选择"`）或隐藏域
`input#answer<qid>` 读出「可见位 ↔ 原始字母」映射，再把模型答案做一次转换后填。
**必须先用探针确认**：提交值到底要原始字母还是可见字母（对比 `input#answer<qid>` 在提交前后的值）。

### P0 · 题干/选项是图片 → 视觉路线（同一批样本已确证）

```
题干含图片 : 17/18     ← 线性代数题干整段是 PNG（p.ananas.chaoxing.com）
选项含图片 :  6/18
选项文本几乎为空: 5/18
```

文本路径对这类题**根本无效**（bodyHead 里 `若方阵满足 ，则的特征值…` 就是公式被丢掉的痕迹）。
→ 必须走**题干+选项整块截图 + 视觉模型**（现有的 `cx-screenshot.ts` 与 M13 截图路径可复用）。

### P0（原计划，保留） · 公式选项残缺 → 自动截图

**问题**：数学/物理题的选项在页面上是 MathJax/图片渲染，OCS 取到的是文本残片；
即使模型答对，字母与选项的对应关系也可能错乱（实测该场景只剩 34%~50%）。

**计划（需要真实 DOM 证据，不许猜）**：
1. 用现成探针（`tools/cx_launch.py` + `tools/probe_browser.py` / `cx_observe.py`）打开真实作业页
2. 抓 **选项区的 DOM 结构**：
   - 选项容器选择器、每题选项数量
   - 每个选项的真实文本（`innerText`）与是否有 `<img>` / `<math>` / MathJax 节点
   - `env.options` 在 resolver 里对应的到底是什么（`work.ts` 里 env 的构造处）
3. 判定"选项文本不可靠"的**客观特征**（例如：多个选项文本相同/极短/含 `[图片`/含 MathJax 残留），
   据此触发 `captureElementAsDataUrl` 截图（参考现有 M13 逻辑 `work.ts:585-608`）
4. 用探针数据做**离线验证**：同样的 10 题，比较"文本路径"与"截图路径"的答案可解析率

**已知的探针入口**：`tools/cx_launch.py`（启动 CDP 浏览器）、`tools/probe_browser.py`、
`tools/cx_observe.py`、`tools/cx_inspect.py`、`tools/cx_measure.py`
（**注意：同一时刻只能有一个 CDP 客户端**）

### P0 · 多空填空题格式与 resolver 不兼容

`resolveCompletion` 要求**段数 == 空数**，而 `splitAnswer` 分隔符是
`['===','#','---','###','|',';','；']`——**不含换行、逗号、顿号**。
现在提示词要求多空题输出 `第1空：甲\n第2空：乙` → 段数=1 ≠ 空数 → 整题失败（只有单空题能过）。

**可选修法**（择一，需先确认不会破坏"逐空复制"的显示）：
- 提示词改为用 `；` 分隔（与默认分隔符一致）
- 或把 `\n` 加入 `answerSeparators`
- 或在 handler 里把 `第N空：` 格式规范化成 `；` 分隔（显示与填入分离）

> 注意：用户曾说"填空的填入问题不大"，先用真实样本确认多空题的占比再决定。

### P1 · 质量优先提示词（.7）的 A/B 实测

拿到新 Key 后跑：`node tools/math-bench.mjs --garble-options --only A,V2`，
确认 V2 不劣于 A（预期：正确率持平或更高，代价是延迟与 reasoning token 增加）。

### P1 · 发布 `.8`（线上落后 6 个版本）

`.publish/ocs.user.js` 仍是 `.2`（含 deepseek 官方模型名 bug、无字母输出）。
发版需用户提供**新的** GitHub token（细粒度、只勾本仓库 Contents、7 天过期），推送后比对 SHA256。

### P2 · 答题缓存的错误答案复用

若开启答题缓存，随机/错误答案会被缓存复用。建议：不缓存"随机兜底"产生的答案（`.8` 后随机已默认关闭，风险下降）。

---

## 9. 有样本后的探针操作（照着做）

```powershell
cd E:\Code\ChaoXingStudy
python tools\cx_launch.py                       # 启动带 CDP 的浏览器（会停在登录页，你自己登录）
# 然后按需运行其中一个（示例）：
python tools\cx_observe.py                       # 观测当前页
python tools\cx_inspect.py                       # 检查脚本是否注入/面板状态
```

探针要采集的东西（对应 §8 P0）：

1. **选项容器与选项元素**：`body` 里每道题的选项区 DOM（class、层级、数量）
2. **选项文本质量**：`innerText` 是否为空/重复/含 math 残留
3. **图片/公式节点**：`img`、`math`、`.MathJax`、`svg` 的存在与数量
4. **resolver 实际拿到的 `env`**：在 `work.ts` 里打点或直接在控制台查看调试日志

> 采集到证据之前，**不要动 `work.ts` 的截图触发条件**（避免重演"面板缩放"那种盲改）。

---

## 9.5 实测证据（2026-11-11，真实作业页）

**样本**：线性代数「第十次作业-矩阵的对角化」18 题（单选 10 / 填空 2 / 判断 6），
课程 `courseid=86653594` `clazzid=152588382`。

**真实 DOM 结构**（作业作答页，题目在 `frame[0]`）：

```
题目容器 : div.questionLi.fontLabel.singleQuesId
           [typename="单选题"] [id="question<qid>"] [data="<qid>"]
题干     : h3.mark_name > p > img        ← 常整段是图片
选项     : div.clearfix.answerBg.workTextWrap
           [onclick="addChoice(this)"] [role="radio"] [aria-label="B B、xxx,选择"]
隐藏字段 : input#answertype<qid> / input#answer<qid>   （题型 / 提交值）
```

**关键统计**：题干含图片 17/18；选项含图片 6/18；选项文本几乎为空 5/18；
`aria-label` 可用 3/18。**选项顺序被页面打乱**（见 §8 P0）。

**探针工具（新增，只读）**：

| 工具 | 作用 |
|---|---|
| `tools/cx_probe_login.py` | 确认 CDP 连通 / 已登录 / iframe 数 / 页面文本头部 |
| `tools/cx_probe_struct.py` | dump 各 frame 的真实结构（不猜选择器） |
| `tools/cx_probe_options.py` | 统计题干/选项的图片与文本可用性，`--full` 打印每题明细 |

**CDP 端口已从 9222 改为 20022**（重要）：
`9222` 落在 Windows Hyper-V/WSL 的保留端口段 `9211–9310` 内，Chromium **无法绑定**。
所有 `tools/*.py` 已统一改为 `20022`。启动方式：
`python tools\cx_launch.py --url "<作业页>"`；若报「CDP 端口未就绪」而端口不在保留段内，
检查是否有同 profile 的残留 Edge 进程（`browser-profile-edge`）并清理。

### 9.6 面板标签含义（用户问过）

| 标记 | 含义 |
|---|---|
| 🔴 `⚠ 随机填入` | **该题答案是脚本随机选的，很可能错**（tooltip：模型未给出可用答案）|
| 🟠 `需手动作答` | 未自动填入（富文本/需上传附件），请复制答案手动作答 |

注：`cxRandomFilled` 标记链路已完整（`cx.ts` 赋值 → `work.ts:442` → `common.ts:890` → `search.infos.ts:193`），
`.8` 起随机兜底**默认关闭**，所以正常情况下不会出现红标。

## 10. 其它三个项目的状态（同一用户名下）

| 项目 | 路径 | 状态 |
|---|---|---|
| SnapAsk | `E:\Code\SnapAsk` | `0.5.1`，MIT，`main` 分支；仅屏幕框选；81 项测试；**未发布**（需配 remote） |
| Estudy（E会学） | `E:\Code\Estudy` | 油猴 `1.2.7` + Python driver；MIT；**已 git init**；模型名已按提供商修正 |
| YuketangStudy（雨课堂） | `E:\Code\YuketangStudy` | 立项 + 只读探针已跑通（WS 端点、`/cards/` 路由表）；**只做随堂测验**；未写实现 |
| DeskAsk（VM 会议监看） | — | **已按要求删除** |

三者都已完成"**模型名按提供商分开**"的修正：
`opencode-go → deepseek-v4.1-flash`、`deepseek 官方 → deepseek-flash`。

---

## 11. 变更记录

- **2026-11-11**：真实作业页探针完成（`tools/cx_probe_*.py`）；确证「题干是图片 + 选项顺序被打乱」；
  CDP 端口 9222 → **20022**（Windows 保留端口段冲突）；面板标签含义写档
- **2026-11（本轮）**：`.2 → .8`；新增 `tools/math-bench*`、`docs/analysis-answer-accuracy.md`；
  修复模型名、选择题字母输出、填空误伤、提示词质量、随机兜底默认值
- 更早的历史见 `PROJECT.md` §1–§26
