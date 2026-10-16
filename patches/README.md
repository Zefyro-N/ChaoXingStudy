# ocsjs 本地改进补丁（cxstudy）

**这是什么**：本项目对 [ocsjs/ocsjs](https://github.com/ocsjs/ocsjs)（MIT，3768★）的 fork 级改进。
项目定位是**改进开源项目**，不是重写——驱动层（超星 2450 行 `cx.ts` + 答题框架 + 字体还原）全部复用上游。

| 项 | 值 |
|---|---|
| 上游仓库 | `https://github.com/ocsjs/ocsjs` |
| 基线分支 | `5.0` |
| 基线 commit | `8b25a3f` |
| 许可证 | MIT（保留上游署名，见产物头部 `@author enncy`） |
| 补丁文件 | `ocsjs-cxstudy.patch` |
| 改动范围 | 4 个文件 / +140 −11 行 |
| 产物 | `dist/ocs.user.js`（936,546 bytes，`@version 5.2.1-cxstudy.1`） |

## 改动的 4 个文件

| 文件 | 改了什么 | 对应 |
|---|---|---|
| `scripts/build-core.js` | `metadata.connect` 加入 `opencode.ai`、`api.deepseek.com` | M1 |
| `packages/core/src/core/answer-wrapper/answer.wrapper.handler.ts` | 给 `headers` 接通 `${}` 占位符替换；注入稳定会话 ID `${__session}` | M2 |
| `packages/scripts/src/projects/cx.ts` | 倍速锁定 1.0x、禁用 rateHack、禁用复制粘贴屏蔽、不重置播放进度、禁用 finishJob 秒过、考试硬禁区、**新增验证码提交前门禁** | M3/M4/M7/M8/M9/M10 |
| `package.json` | 版本号加 `-cxstudy.1` 分支标识，便于区分上游产物 | —— |

**不在补丁里的**（属环境前置，见 skill `build-ocsjs-userscript`）：
仓库级 `.npmrc` 的 `proxy=` / `https-proxy=` 覆盖、`pnpm install --node-linker=hoisted`、三个 `.env` 文件。

## 应用补丁

```powershell
# 1. 取上游基线
git clone --depth 1 --single-branch --branch 5.0 https://github.com/ocsjs/ocsjs.git
cd ocsjs
git fetch --depth 1 origin 8b25a3f; git checkout 8b25a3f

# 2. 打补丁
git apply <项目路径>\patches\ocsjs-cxstudy.patch

# 3. 环境前置（关键，缺一不可）
'scripts/.env'          | Set-Content -Value 'BUILD_PATH="../release"'
'packages/core/.env'    | Set-Content -Value 'VITE_BUILD_PATH="../../release"'
'packages/scripts/.env' | Set-Content -Value 'VITE_BUILD_PATH="../../release"'
# 用 Node 18（上游 CI 版本；vite 2.9.18 在 Node 24 上行为不同）
pnpm install --node-linker=hoisted
node_modules\.bin\tsc.cmd -p packages\utils\tsconfig.json

# 4. 构建（约 12~25s）
node_modules\.bin\gulp.cmd -f .\scripts\build-core.js
# 产物：release/ocs.user.js
```

## 已实现 / 未实现

| 编号 | 改造 | 状态 |
|---|---|---|
| M1 | `@connect` 接入两个模型域名 | ✅ 已在产物中验证 |
| M2 | `headers` 占位符 + 稳定会话 ID（OpenCode Go 必需） | ✅ |
| M3 | 倍速锁定 1.0x，禁用 rateHack | ✅ |
| M4 | 禁用"屏蔽复制粘贴限制" | ✅ |
| M7 | **新增验证码提交前门禁**（上游无此能力） | ✅ 代码级完成，**待实机验证** |
| M8 | 不重置播放进度（断点续播） | ✅ |
| M9 | 禁用 `finishJob()` 秒过图片阅读 | ✅ **行为变更，风险最高，必须实机验证** |
| M10 | 考试硬禁区（不做题、不提交） | ✅ |
| **M5** | 视频内题目：随机 → 模型作答 | ⬜ **未做**（需把 `answererWrappers` 接入 `JobRunner.media`） |
| **M6** | 答不出时不再随机，改为放弃 | ⬜ **未做** |

## 必须知道的注意事项

1. **`@connect` 不生效就等于模型不可用。** 上游白名单只有 7 个域名，浏览器会静默拦截跨域请求——
   现象是"答题没有结果"却看不到报错。改完务必用 `Select-String -Path release\ocs.user.js -Pattern '@connect'` 复核。
2. **`minify: false` 但注释仍会被剥离**，所以别用注释里的标记（如 `[cxstudy M3]`）验证产物是否生效，
   要用行为特征（如 `本分支锁定 1.0x` 这类字符串字面量）。
3. **`pnpm install` 会把占位配置写进 `pnpm-workspace.yaml`**（`allowBuilds: set this to true or false`），
   提交前要 `git checkout -- pnpm-workspace.yaml`，否则补丁里会混进垃圾。
4. **绝不要用 PowerShell 读写含中文的源码文件。** `Get-Content -Raw` 在 zh-CN 下按 GBK 解码 UTF-8，
   会把 `在线网络课程辅助工具` 写成 `鍦ㄧ嚎缃戜笟...`，并顺带把 LF 变 CRLF。用 edit 工具或 Node 做字节安全替换。
5. 补丁只覆盖 4 个文件；`.npmrc`、`pnpm-workspace.yaml`、`packages/scripts/assets/css/style.css`（构建产物）
   的改动不要混进来。
