# 发布到 DSH 社区指南：让社区获取你的插件

> 适用对象：任何 DSH 插件作者。底层机制详见 [plugin-development.md](./plugin-development.md) §9 与 deepseek-harness 官方 `docs/user/develop/basic/publish.md`。

## 0. 结论：社区获取插件的三条通道

| 通道 | 社区用户执行 | 发布者工作量 | 备注 |
|---|---|---|---|
| **npm registry**（推荐） | `dsh plugin --profile <name> add <包名>` | `npm publish`（一次） | 最顺滑；包名即身份 |
| **GitHub 仓库** | `dsh plugin --profile <name> add github:<user>/<repo>` | 仓库 + `prepare` 脚本 + README | pnpm≥10 首次要 `allowBuilds` 白名单 |
| **tarball / 本地路径** | `dsh plugin add ./<包>-<ver>.tgz`（或 `./<目录>`） | `pnpm pack` 产物 | 无需任何账号/权限，适合内部分发与验证 |

**背景**：DSH 官方全家桶已公开到 npm（`@deepseek-ai/dsh-*`，dist-tags：`latest=0.0.1-rc.1` 旧序列、`next=0.1.0-rc.6` 当前开发线），社区插件因此可以从 npm 直接安装。

---

## 1. 前置条件：包必须符合 bundle 规范（检查清单）

社区能否用 `dsh plugin add` 安装，取决于包 manifest 是否声明为 bundle：

```jsonc
// package.json 必查项
{
  "name": "dsh-web-search-pro",              // 建议 dsh- 前缀（社区惯例）
  "version": "0.1.0",
  "type": "module",
  "main": "lib/index.js",                     // 构建产物入口
  "types": "lib/index.d.ts",
  "exports": {
    ".": { "types": "./lib/index.d.ts", "default": "./lib/index.js" },
    "./cordis.patch.yml": "./cordis.patch.yml"   // 补丁文件显式导出
  },
  "files": ["lib", "cordis.patch.yml", "README.md", "scripts", "LICENSE"], // 白名单
  "scripts": {
    "build": "tsc -p tsconfig.json",          // 自包含构建（无 workspace 引用）
    "prepublishOnly": "npm run build",        // npm 发布前自动构建
    "prepare": "npm run build"                // ★ git 安装需要（见 §4）
  },
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } }   // ★ 核心声明
}
```

`cordis.patch.yml` 的内容是标准补丁行，`name` 写**包名**（Node 解析，而不是源码路径）：

```yaml
- insert:
    - id: web-search-pro
      name: dsh-web-search-pro
      config:
        verbose: false
```

> 依赖注意：插件依赖的 `@deepseek-ai/*` 必须是**已发布版本**（从 npm 解析），
> 不能用 workspace:*。Cordis 服务按全局 symbol key 品牌化，插件自带的
> `@deepseek-ai/cordis` 副本与 harness 内副本天然互操作，无需对版本。

## 1.5 打包不是必须的：五级"复用"形态（关键结论）

"打包"（`npm pack` → tgz）只是**传输载体**，不是分发前提。真正绕不开的只有"构建产物 `lib/`"
（Node 按 `package.json` 的 `main` 解析 JS）——而且这只对**安装型分发**成立；开发期连构建都不需要。
按"需要准备的东西"从少到多：

| 形态 | 复用/准备什么 | 打包? | 构建? | 适用场景 |
|---|---|---|---|---|
| ① `--patch` 指向 TS 源码 | 源码文件（绝对路径） | 否 | 否（tsx 直接加载 .ts） | 开发期 / 对方用源码运行的 dsh（`pnpm dsh`） |
| ② `dsh plugin add ./<目录>` | 含 `package.json` 的目录 | 否 | 是（一次，产 `lib/`） | 内部分发；**目录已有构建产物时零成本复用** |
| ③ `dsh plugin add github:<user>/<repo>` | 源码仓库 | 否 | 是（安装时 `prepare` 自动构建） | 社区公开分发（GitHub 仓库本身即复用载体） |
| ④ `dsh plugin add <npm包名>` | npm registry | 是（npm 内部即 tgz） | 是（`prepublishOnly`） | 社区公开分发（推荐，包名即身份） |
| ⑤ `dsh plugin add ./x.tgz` | tarball | 是 | 是 | 邮件 / GitHub Release 资产 / 评审分发 |

**直接结论**：一个已经构建好的 bundle 目录（`lib/` 已存在）就是分发的最小单位——内部分发直接 `dsh plugin add ./<插件目录>`，**不需要重新打包**；给社区则二选一：npm 发布（④，最顺滑）或 GitHub 分发（③，需补 `prepare`）。"复用"的两种理解都成立：复用已构建产物（lib/），或复用源码仓库（git 分发），打包只在对方拿不到目录/仓库时才需要。

## 2. 本地验证（发布前必做，零风险）

```sh
cd <插件目录>
npm run build            # ① 构建通过 → lib/ 生成
npm pack                 # ② 生成 <name>-<ver>.tgz，检查内容齐全
```

```sh
# ③ 端到端：临时 profile 装 tarball（模拟社区用户；不碰现有 profile）
cd <deepseek-harness 仓库根>
pnpm dsh plugin --profile dsh-plugin-test add <插件目录>/dsh-web-search-pro-0.1.0.tgz
pnpm dsh --profile dsh-plugin-test --dump-config | findstr web-search-pro   # ④ 确认补丁层生效
```

验证完成后删除临时 profile（`Remove-Item -Recurse $env:USERPROFILE\.dsh\profiles\dsh-plugin-test`）。

## 3. 通道 A：发布到 npm（推荐）

前置：npm 账号（`npm whoami` 确认已登录；未登录先 `npm login`）。

```sh
cd <插件目录>
npm publish               # prepublishOnly 会自动构建；产物含 lib/ + cordis.patch.yml
```

发布后社区即可安装：

```sh
dsh plugin --profile web add dsh-web-search-pro
```

可选：发布后补一个 Git tag 并与 GitHub Release 关联（`npm version patch` 自动打 tag）。

> 注意：npm 对 `@scope` 包默认 restricted，无 scope 的包（如 `dsh-web-search-pro`）直接 public，无需 access 参数。

## 3.5 自动化发布：GitHub Actions 全自动接管（推荐）

仓库 `.github/workflows/publish.yml` 已写好（对齐官方 `deepseek-harness` release.yml 的
"pack 无凭据验证 + publish 显式确认"模式），**推 tag 即自动发布**：

- **pack job**（每次运行都跑，无 registry 凭据）：`pnpm install --frozen-lockfile` →
  校验 `tag == package.json version`（不匹配即失败）→ `pnpm build` → `pnpm pack` →
  上传 tarball artifact；
- **publish job**（tag push 或手动 dispatch 勾选 publish）：只消费 pack 的字节（不重建），
  `npm publish dist/*.tgz --provenance --access public`，走 `environment: npm-publish` +
  `secrets.NPM_TOKEN`，发布全局串行化；
- **release job**（tag push 时）：自动建 GitHub Release 并附 tgz 资产（社区第三条获取通道）。

**一次性配置（只需做一次）**：

```sh
# 1. npm 账号生成 Automation token（绕过 2FA 提示）：
#    https://www.npmjs.com/settings/<你的用户名>/tokens → Generate New Token → Automation
# 2. GitHub 仓库 Settings → Secrets and variables → Actions → New repository secret：
#    NPM_TOKEN = 上一步的 token
# 3.（可选）Settings → Environments → npm-publish → Required reviewers：发布需人工审批
# 4. 推送工作流文件：
git add .github/workflows/publish.yml && git commit -m "ci: auto publish to npm on tag" && git push
```

**日常发布**：

```sh
# ① 改版本号并构建验证
npm version patch        # 或手动改 package.json version + commit
# ② 打 tag 推上去，CI 全自动：构建 → 校验 → npm publish → GitHub Release
git tag v0.1.1 && git push origin v0.1.1
```

不想发布只想预演：Actions 页面手动运行 workflow、不勾选 publish（dry-run pack）。
tag 推错（与 version 不匹配）：pack job 会 fail 并给出错误信息，不会触碰 registry。

## 3.6 自动发现 / 同步 / 发送：discover-plugins.mjs（一键接管整个插件矩阵）

工作区脚本 \`scripts/discover-plugins.mjs\` 实现"搜索账号下所有 dsh 相关仓库 → 对比 npm 发布状态 →
同步本地 checkout → 打 tag 触发各仓库 CI 自动发布"的**全自动发布体系**（需要 gh CLI 已登录）：

\`\`\`sh
node scripts/discover-plugins.mjs                        # ① 发现 + 状态报告（只读）
node scripts/discover-plugins.mjs --sync                 # ② + 同步本地 checkout（clone/pull）
node scripts/discover-plugins.mjs --sync --auto-tag      # ③ + 对未发布版本打 v<version> tag 并推送（触发各仓库 publish.yml → npm publish → GitHub Release）
\`\`\`

- **发现口径**：名字含 \`dsh\` + topic \`dsh-plugin\`/\`dsh\`/\`deepseek-harness\` 的仓库，自动读取远程 package.json，
  检测 \`dsh.bundle\`/\`dsh.client\`/\`prepare\`/\`publish.yml\`，npm 版本对比 → PENDING / PUBLISHED / OUTDATED / BEHIND。
- **状态清单**：写入 \`plugins-inventory.json\`；表格输出含每个仓库的发布就绪度（缺 prepare / 缺 CI 会告警）。
- **安全**：默认只读；\`--sync\` 只写本地；只有显式 \`--auto-tag\` 才会推送 tag。
  自动发送的前提是各仓库已配好 \`NPM_TOKEN\`（见 §3.5），否则 CI 的 publish job 会失败。
- **环境变量**：\`DSH_PLUGIN_OWNER\`（必填，你的 GitHub 用户名）、\`DSH_CHECKOUT_ROOT\`（可选，默认 `~/dsh-plugin-checkouts`） 4. 通道 B：GitHub 仓库分发

仓库结构即 bundle 包本身（源码 + `package.json` + `cordis.patch.yml`）。

**必须满足两点**，否则用户 git 安装会失败：

1. **`prepare` 脚本自包含构建**：pnpm git 安装后运行 `prepare`（源码不带构建产物），
   如 `"prepare": "npm run build"`；构建配置不得依赖仓库外上下文（如 sibling monorepo）。
2. **用户侧 allowBuilds 白名单**：pnpm ≥10 默认拒绝执行 git 依赖的 `prepare`。
   用户首次 `add` 会失败并打印提示，把包 key 抄进 profile 的 `pnpm-workspace.yaml`：

   ```yaml
   allowBuilds:
     dsh-web-search-pro: true
   ```

   然后重跑 `dsh plugin --profile web add github:<owner>/<plugin-repo>`。
   这是"允许在安装时执行该包代码"的信任决定——README 要写清楚，并建议用户钉 commit（`#<sha>`）。

**社区可见性**：给仓库打 `dsh-plugin` topic（GitHub 上 `github.com/topics/dsh-plugin` 是当前社区聚合地），
README 顶部写安装命令。可再加 GitHub Release（用户可 `dsh plugin add ./dsh-web-search-pro-0.1.0.tgz` 直接装 release 资产）。

## 5. 通道 C：tarball / 本地路径（零权限）

```sh
pnpm pack                 # 产出 dsh-web-search-pro-0.1.0.tgz
# 分发给用户：
dsh plugin --profile web add ./dsh-web-search-pro-0.1.0.tgz
# 或直接指向未打包目录（含 package.json 即可）：
dsh plugin --profile web add ./dsh-web-search-pro
```

无构建权限问题、无网络依赖，适合内网/评审期分发；缺点是升级要靠手动替换。

## 6. 社区现状与定位（调研结论，2026-08）

GitHub topic `dsh-plugin` 上的现有插件（详见 `web-search-pro/RESEARCH.md` §1.6）：

| 插件 | 类型 |
|---|---|
| `zhu1090093659/dsh-web-ui`、`ccch1mneyyy/dsh-cc-tui`、`Small-tailqwq/dsh-deep-whale` | Web UI / 皮肤 / TUI |
| `<owner>/<your-plugin>` | 你发布的插件（搜索 / 内容类仍是社区空白点） |

社区分发范式 = **npm 包 + `dsh.bundle` manifest + `dsh plugin add`**。
搜索/内容类插件仍是空白，且 DSH 官方在 `packages/bundle` 之外不维护插件市场——
**"发布到 npm + GitHub topic 曝光"就是当前唯一的社区分发路径**。

## 6.5 已验证的端到端安装链路（2026-08 实测）

```sh
cd <deepseek-harness 仓库根>
# ① 初始化临时 profile（自动含 @deepseek-ai/dsh-base）
pnpm dsh plugin --profile dsh-plugin-test add -w <插件目录>/dsh-web-search-pro-0.1.0.tgz
# ② 补丁层自动加入 bundles（reconcile）：dsh.profile.bundles = [base, dsh-web-search-pro]
pnpm dsh --profile dsh-plugin-test --dump-config   # 显示 # == dsh-web-search-pro 层，行 - id: web-search-pro
# ③ 用完删除临时 profile
Remove-Item -Recurse -Force $env:USERPROFILE\.dsh\profiles\dsh-plugin-test
```

**⚠ 实测（pnpm 9.15.9）下 `dsh plugin add` 必须带 `-w`**：dsh 初始化 profile 会生成
`pnpm-workspace.yaml`（`packages: [.]`），profile 因此是 workspace root；pnpm 9/11 在 root 内
`add` 直接报 `ERR_PNPM_ADDING_TO_ROOT` 拒绝执行，`-w`（pnpm 参数透传，dsh 不拦截）显式确认后成功。
这是 dsh 0.1.0-rc.5 与 pnpm 9/11 的兼容行为，遇到报错先试 `-w`，或在该 profile 的
`pnpm-workspace.yaml` 加 `ignore-workspace-root-check: true`。

## 7. 常见坑速查

- **npm publish 报 `403 Two-factor authentication ... bypass 2fa`**：npm 强制发布者开启 2FA；CI 发布必须用
  **Automation token**（classic token 创建页勾选 Automation）或开启 "Bypass 2FA on npm publish" 的 Granular token。
  普通 publish token 在 CI 里必 403（实测：tarball 与 provenance 均成功后才在此步被拒）。
- **CI 中 `npm publish dist/*.tgz` 报 git ls-remote 错误**：glob 展开后 `dist/x.tgz` 不带 `./` 前缀会被 npm 11
  当成 GitHub shorthand（`user/repo` 模式）去 ssh 拉取；必须写 `npm publish ./dist/*.tgz`。
- **`dsh plugin add` 报 `ERR_PNPM_ADDING_TO_ROOT`**：profile 是 workspace root，命令加 `-w`（见 §6.5）。
- **版本对齐**：npm 上 `@deepseek-ai/*` 最新是 `next=0.1.0-rc.6`，本地源码 checkout 是 rc.5；
  插件 dependencies 用 `^0.1.0-rc.6` 即可从 npm 解析，不与源码运行冲突（Cordis 品牌互操作）。
  若装进本机 profile 遇版本冲突，用 `dsh plugin add ./<路径>` 并手工对齐 profile 的 `pnpm-workspace.yaml`。
- **`npm view <pkg> version` 显示旧版本**：dist-tags 的 `latest` 是历史遗留 `0.0.1-rc.1`，
  当前开发线看 `next`：`npm view @deepseek-ai/dsh-tools dist-tags`。
- **git 安装无 `prepare` 必失败**：TS 源码不会自动编译；要么给 `prepare`，要么发构建产物（npm/tgz）。
- **补丁层顺序**：用户 profile 的 `cordis.patch.yml` 在 bundle 层之后，可覆盖你的行（`config` 整块替换）。
- **凭据类配置**：settings/credentials 命名空间的暴露是 harness 的 allowlist 决定的，
  社区插件不能随包分发 UI 配置卡片（`packages/host/apiproxy` 白名单）；用 `settings.yaml` / cordis config / env 代替。
