# 上游 5.4.0 对比评估（`E:\Desktop\OCSJS.md`）

> 文件性质：`// @version 5.2.1-cxstudy.1` → **上游 `5.4.0`** 的完整 diff。
> 规模：6469 行，`+2974 / -1415`，171 个 hunk。
> 基线：我们的 fork 停在 `5.2.1`（上游 `8b25a3f4…`）。
> 评估时间：2026-11（对应本地 `5.2.1-cxstudy.12`）

---

## 一、结论先说

上游 5.4.0 的增量**主要在「多站点覆盖」和「新站点项目」**，与我们的准确率问题**没有交集**：

- 新增 `@match` **31 条**（zhihuishu / icve / icourse163 / yuketang / xuetangx / polymas …）
- 新站点项目：知乎、短视频类等
- **对「选项乱序」与「题干为图片」仍然没有任何处理**（已单独 grep 确认）

但有 **5 处技术实现值得借鉴**，其中 3 处直接关系我们的准确率。

---

## 二、值得借鉴（按价值排序）

### ⭐⭐⭐ 1. `normalizeStringKeepSign` + `disambiguateBySign` —— 保留符号的消歧匹配

上游 5.4.0 在答案匹配里新增了一组"保留正负号"的归一化：

```js
function clearStringKeepSign(str) {
  return clearString(str, "\\-", "\\+", "−");   // 只保留 - + − ，其余字符清掉
}
function normalizeStringKeepSign(str) {
  return clearStringKeepSign(
    str.replace(/[−–—]/g, "-")                                  // 各种破折号统一成 -
       .replace(/[，。！？；：""''、（）【】《》\s]/g, "")        // 中文标点去掉
       .replace(/[,.\-!?;:'"()[\]<>]/g, (m) => (m === "-" ? m : ""))  // 英文标点：只留 -
  );
}
function disambiguateBySign(answers, options) {
  if (options.length <= 1) return options;
  const _answers = answers.map((a) => normalizeStringKeepSign(removeRedundant(a)));
  const strict = options.filter((opt) => {
    const no = normalizeStringKeepSign(removeRedundant(opt));
    return _answers.some((na) => na === no);
  });
  // 只有"部分命中"时才收紧；全不命中或全命中都返回 []，交给上层回退
  return strict.length > 0 && strict.length < options.length ? strict : [];
}
```

**为什么值得我们借鉴**：我们的痛点正是"多个选项只差一个符号"。

`removeRedundant` 会把这几个选项归一化成**同一个字符串**：

```
-1、6、9      →  169
 1、6、9      →  169
```

于是相似度匹配无法区分 → 只能靠运气。`normalizeStringKeepSign` 保留符号后：

```
-1、6、9  →  -169
 1、6、9  →   169
```

**落地方式**：在 `resolveSingle` / `resolveMultiple` 的「阶段 2 相似匹配」之后加一步符号消歧，
命中部分选项时收紧候选，未命中则保持原逻辑（上游的 `return []` 语义正好是"不干预"）。

### ⭐⭐⭐ 2. `linearizeLatex` —— LaTeX 线性化，作为响应后处理

上游新增了把 LaTeX 转成线性文本的函数（`\frac{}{}`、`\sqrt[]{}` 等），diff 里长行被截断，
但**思路与我们的需求完全一致**：我们的提示词禁止模型输出 LaTeX，可模型偶尔仍会输出。

**建议用法**：在 `makeResponseHandler` 里加一道**兜底线性化**（不是替换，只在检测到 `\frac` / `\sqrt` / `$…$` 时处理）：

```
\frac{a}{b}   →  a/b
\sqrt{x}      →  √x
x^{2}         →  x^2
a_{n}         →  a_n
$...$         →  去美元符
```

这与我们既定的"公式纯文本可粘贴"策略一致，也能减少"模型输出 LaTeX → 匹配失败"这一类失败。

### ⭐⭐ 3. `normalizeQuestion` —— 归一化后的缓存 key

```js
const normalizeQuestion = (question) =>
  question.replace(/https?:\/\//gi, "//").replace(/[^\p{L}\p{N}]/gu, "");
```

去掉协议差异与全部标点，只留字母数字。**用途**：答题缓存的 key。

我们现在直接用原始题干做缓存 key，同一道题若题干里 [图片N] 编号或 URL 不同，会重复请求模型
（既费钱也可能拿到不一致的答案）。用这个归一化当 key 更稳。

### ⭐⭐ 4. `flushTabWrites` + `GM_getTab/GM_saveTab` + `beforeunload`

```js
window.addEventListener("beforeunload", () => this.flushTabWrites());
flushTabWrites() {
  const entries = Array.from(this.tabPendingWrites.entries());
  this.tabPendingWrites.clear();
  GM_getTab((tab = {}) => { for (const [k, p] of entries) Reflect.set(tab, k, p.value);
                            GM_saveTab(tab); /* 逐个 resolve */ });
}
```

配合 `tabPendingWrites` / `tabFlushTimer`（`setTimeout(..., 0)` 合并写）+ 每个 key 挂 `pending.resolves`。

**为什么值得我们借鉴**：超星作业页有 **5 个 frame（4 个 iframe）**，多 frame 同时写同一个 store 时
存在竞态与丢写风险。这套"写缓冲 + 帧内合并 + 卸载前落盘 + Promise 等待落盘完成"的模式是成熟解法。

### ⭐ 5. `DANGEROUS_PATTERNS` —— 脚本安全审计表

上游对**第三方答题脚本**做静态审计，把危险 API 与理由列成表：

| 检测 | feature | 判定理由 |
|---|---|---|
| `eval` / `Function()` | 动态执行 | 执行任意代码 |
| `fetch` / `XMLHttpRequest` / `GM_xmlhttpRequest` | 网络请求 | 可能外传账号数据 |
| `localStorage` / `indexedDB` / `cookie` | 本地存储 | 可能窃取登录凭据 |
| `sendBeacon` / `WebSocket` / `postMessage` | 外传通道 | 静默外发数据 |
| `location` / `window` / `unsafeWindow` | 全局对象 | 可跳转钓鱼页、操控页面 |
| `constructor` / `__proto__` | 原型链 | 常用于绕过检测 |

我们已删除第三方题库，**当前用不到**；但如果将来要支持自定义答题源，这张表可以原样复用，
也与我们"凭据绝不外流"的红线一致。

---

## 三、明确不借鉴

| 上游做法 | 为什么不借鉴 |
|---|---|
| 新增 31 个 `@match` 站点 | 我们只做超星单平台，已删除约 7500 行多平台代码 |
| 视频倍速 / PPT 翻阅速度 | **红线**：倍速已正式放弃，锁定 1.0x |
| 讨论自动回复 | 超出范围（我们只做任务点 + 测验 + 作业/考试） |
| 随堂测验自动答题 | 属"未要求的自动提交"，与我们的手动触发原则冲突 |
| 随机填空 / 随机选择（仅超星） | 思路与我们一致，但我们已改为**默认关闭 + 红标提示**，无需改动 |

---

## 四、建议的落地顺序

1. **`disambiguateBySign`**（最直接提升数学题正确率，改动局部、可单测）
2. **`linearizeLatex` 响应兜底**（减少"输出 LaTeX 导致匹配失败"）
3. **缓存 key 归一化**（省钱 + 避免答案漂移）
4. **多 frame 写缓冲**（可靠性，超星作业页 5 frame 场景真实存在）
5. 安全审计表（留档，以后再考虑）
