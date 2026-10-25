# CXStudy 超星助手

适用于 **超星学习通**（chaoxing.com / xueyinonline.com）的用户脚本：
自动推进视频 / 音频 / 文档任务点，章节测验与视频内弹题由模型作答；作业与考试默认关闭、需手动触发。

- **当前版本**：`5.2.1-cxstudy.4`
- **形态**：Tampermonkey / ScriptCat 用户脚本（基于 [ocsjs/ocsjs](https://github.com/ocsjs/ocsjs)（MIT）的 **fork + 补丁**，单平台分支，只保留超星）
- **许可证**：MIT（保留上游版权声明与许可声明）

---

## 安装

1. 安装 [Tampermonkey](https://www.tampermonkey.net/) 或 [ScriptCat](https://scriptcat.org/)
2. 安装脚本（二选一）：
   - 打开 [Releases](https://github.com/Zefyro-N/CXStudy/releases) 下载最新 `ocs.user.js` 安装
   - 或直接访问 `https://raw.githubusercontent.com/Zefyro-N/CXStudy/main/ocs.user.js`
3. 打开任意超星课程页面 → 右下角出现面板 → 点 **⚙ 设置** 填 API Key（点「测试连接」确认可用）

---

## 功能

### 学习流程
- 视频 / 音频 / 文档任务点自动推进，**锁定 1.0x**（不做倍速、不拖拽、不改进度）
- **章节测验**：字体解密 + 模型作答 + 自动提交
- **视频内弹题**：模型作答
- 文档 / 图片阅读自动完成；进入页面自动跳到第一个未完成点；全部完成后从头复习

### 答题辅助
- 所有题目都会给出**可复制**的答案
- 每题 `复制答案`；多空题按空拆分：`第N空 [复制]` + `复制全部（按顺序）`
- 状态标注：`⚠ 随机填入`（模型答不出、由脚本随机选择，很可能错）、`需手动作答`
- **主观题**：只显示 + 复制，**不自动填、不提交**
- **图片题**：多模态；题干取不到时自动截图交给模型
- **总开关**：关闭后不自动刷课 / 不自动答题（面板手动「开始」仍然可用）

### 作业与考试（红线）
- 默认**全部关闭**，需要**手动逐次**触发，并必须确认风险声明
- **考试**需单独授权
- **只要题目中含主观题，绝不自动提交**（连点击提交都不做）

---

## 模型接入

| 提供商 | 模型 ID |
|---|---|
| `opencode-go` | `deepseek-v4.1-flash` |
| `deepseek 官方` | `deepseek-flash` |

> ⚠️ **两家的模型 ID 不通用，不能写死成一个值。**
> 实测（2026-10-21）`GET https://api.deepseek.com/models` 只返回 `deepseek-flash` / `deepseek-v4-pro`；
> 给官方传 `deepseek-v4.1-flash` 会直接 `HTTP 400`：
> `The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed deepseek-v4.1-flash`
> 而 `opencode-go` 用 `deepseek-v4.1-flash` 是正常的。脚本已按提供商分别取模型。

其他相关设计：
- `max_tokens = 8192`：推理模型会把额度烧在 `reasoning_content` 上，给低了会出现
  `finish_reason=length` 且 `content` 为空；空时脚本会从 `reasoning_content` 尾部兜底。
- **API Key 只存在脚本本地存储**（`GM_setValue`），不写入任何项目文件、不打印完整密钥；面板提供「测试连接」「清除」，输入框为密码遮罩。

---

## 明确不做的事（硬边界）

- ❌ 不修改播放倍速、不拖拽进度、不伪造协议包
- ❌ 不做人脸识别绕过；**不做验证码识别或绕过**（只检测到就停止）
- ❌ 不自动填写 / 提交主观题；作业与考试默认不参与
- ❌ 不做题库上传、云同步、账号托管

---

## 常见问题

| 现象 | 原因与处理 |
|---|---|
| `HTTP 400 ... supported API model names ...` | 提供商与模型名不匹配，见上文模型表 |
| `Request is missing x-opencode-session ...` | `opencode-go` 需要该会话头（自建请求时容易漏）；用脚本内置请求头即可 |
| 模型返回空内容，`finish_reason=length` | `max_tokens` 被推理过程烧光 → 保持 8192，或改用非推理模型 |
| 视频不累计进度 | 站点要求 1.0x 且不可拖拽；请让页面保持在前台播放 |
| 面板里没有某些按钮 | 单平台分支已删除多余功能（倍速、在线搜题、使用教程、面板缩放等） |

---

## 与上游的差异（简述）

- **删除其它平台**：`zhs` / `yuketang` / `icve` / `icourse` / `zjy` 等约 **7500 行**，只保留超星
- **删除**：更新模块、桌面软件桥接、播放倍数、在线搜题（划词搜索）、使用教程、自定义编辑框、面板缩放
- **新增**：章节测验字体解密、模型答题（含多模态与截图兜底）、作业/考试手动闸门、总开关、多空题逐空复制
- 产物约 **484 KB**（上游约 916 KB）

---

## 构建（开发者）

```bash
# 1. 取上游基线
git clone https://github.com/ocsjs/ocsjs.git refs/ocsjs
cd refs/ocsjs && git checkout 8b25a3f44523a0d4b7373878488056f4aa478cf6

# 2. 应用本仓库补丁
git apply --ignore-whitespace ../../patches/ocsjs-cxstudy.patch

# 3. 安装依赖（Node 18）
pnpm install --node-linker=hoisted

# 4. 构建（会先跑 4 套测试，全绿才产出）
npx gulp -f ./scripts/build-core.js
# 产物：refs/ocsjs/release/ocs.user.js
```

**测试构成**：`resolver 164` · `cx-model.handler 39` · `blank-answers 20` · `cx-videoquiz 30` = **253 项**
（`cx-model.handler` 里包含「模型名必须按提供商区分」的回归断言）

补丁与基线信息见 `patches/`。

---

## 风险说明（请务必阅读）

使用自动化手段存在被平台判定异常的风险，已知后果包括：

**学习记录被清零 → 再次违规则总评 0 分 → 三次可能按作弊处理。**

本项目定位为**提效工具**，不保证成绩、不规避任何检测。请自行评估并承担全部风险。

---

## 许可证与致谢

- 本项目基于 [enncy](https://github.com/ocsjs) 的 [OCS 网课助手](https://github.com/ocsjs/ocsjs)（MIT）修改而来。
- 依据 MIT 协议要求，**原始版权声明与许可声明均已完整保留**（见 `LICENSE` 与脚本头部）。
- 本项目同样以 MIT 协议发布。
