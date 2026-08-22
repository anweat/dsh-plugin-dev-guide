# 发布到 DSH 社区指南：让社区获取你的插件

> 适用对象：任何 DSH 插件作者。底层机制详见 [plugin-development.md](./plugin-development.md) §9 与 deepseek-harness 官方 `docs/user/develop/basic/publish.md`。

## 0. 结论：社区获取插件的三条通道

| 通道 | 社区用户执行 | 发布者工作量 | 备注 |
|---|---|---|---|
| **npm registry**（推荐） | `dsh plugin --profile <name> add <包名>` | `npm publish`（一次） | 最顺滑；包名即身份 |
| **GitHub 仓库** | `dsh plugin --profile <name> add github:<user>/<repo>` | 仓库 + `prepare` 脚本 + README | pnpm≥10 首次要 `allowBuilds` 白名单 |
| **tarball / 本地路径** | `dsh plugin add ./<包>-<ver>.tgz`（或 `./<目录>`） | `pnpm pack` 产物 | 无需任何账号/权限，适合内部分发与验证 |

**当前验证基线**：deepseek-harness `dsh-v0.1.1-rc.2`、`pnpm@11.7.0`。DSH 仍处于破坏性演进阶段；社区插件以当前基线适配，不承诺旧版兼容。

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

验证完成后删除临时 profile（`Remove-Item -Recurse <DSH_HOME>/profiles/dsh-plugin-test`）。

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

**名字被占用？用 scoped 包名**：无 scope 的包名（如 `dsh-browser`）可能被他人抢先注册（npm 无法申诉）。
改用 `@<你的npm账号>/<包名>`（如 `@anweat/dsh-browser`）即可：scoped 命名空间归账号所有、**永不冲突**，且保留原名字。
改动点：① 插件 `package.json` 的 `name`；② `cordis.patch.yml` 中 `name:` 引用（YAML 中加引号 `name: '@scope/pkg'`）；
③ 依赖该插件的包（`dependencies` + 重新 `pnpm install` 更新 lockfile）。发布时 scoped 包必须显式 `--access public`
（CI workflow 模板已带）。安装命令变为 `dsh plugin --profile web add @scope/pkg`。

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
- **环境变量**：\`DSH_PLUGIN_OWNER\`（必填，你的 GitHub 用户名）、\`DSH_CHECKOUT_ROOT\`（可选，默认 ~/dsh-plugin-checkouts）。

## 4. 通道 B：GitHub 仓库分发

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
corepack pnpm dsh plugin --profile dsh-plugin-test add <插件目录>/dsh-web-search-pro-0.1.0.tgz
# ② 补丁层自动加入 bundles（reconcile）：dsh.profile.bundles = [base, dsh-web-search-pro]
corepack pnpm dsh --profile dsh-plugin-test --dump-config   # 显示 # == dsh-web-search-pro 层，行 - id: web-search-pro
# ③ 用完删除临时 profile
Remove-Item -Recurse -Force <DSH_HOME>/profiles/dsh-plugin-test
```

`dsh-v0.1.1-rc.2` 适配分支会固定 profile 的 `packageManager: pnpm@11.7.0`，并在
`plugin add/remove/update` 内部自动给 pnpm 补 `-w`；调用方不再手工传递。profile 同时设置
`strictDepBuilds: false`，未明确允许的依赖构建脚本会被忽略，而不会使整个安装失败。

## 7. 常见坑速查

- **npm publish 报 `403 Two-factor authentication ... bypass 2fa`**：npm 强制发布者开启 2FA；CI 发布必须用
  **Automation token**（classic token 创建页勾选 Automation）或开启 "Bypass 2FA on npm publish" 的 Granular token。
  普通 publish token 在 CI 里必 403（实测：tarball 与 provenance 均成功后才在此步被拒）。
- **CI 中 `npm publish dist/*.tgz` 报 git ls-remote 错误**：glob 展开后 `dist/x.tgz` 不带 `./` 前缀会被 npm 11
  当成 GitHub shorthand（`user/repo` 模式）去 ssh 拉取；必须写 `npm publish ./dist/*.tgz`。
- **`dsh plugin add` 报 `ERR_PNPM_ADDING_TO_ROOT`**：当前 Harness 应自动补 `-w`；先确认运行的是 `dsh-v0.1.1-rc.2` 适配分支及 `pnpm@11.7.0`，不要把手工 `-w` 固化到用户命令。
- **发布成功但 pnpm 装不到（"not in the npm registry"）**：npm registry 的 abbreviated metadata（`Accept: application/vnd.npm.install-v1+json`，pnpm 等安装器用的就是它）
  在 publish 后约 1–2 分钟才生成，期间 `npm view` / 完整 metadata 正常、install-v1 返回 404。验证：`curl -H "Accept: application/vnd.npm.install-v1+json" https://registry.npmjs.org/<包名>`
  返回 200 后再安装；不要误判为 restricted 包或删包重发。
- **scoped 包名防占用**：无 scope 名字可能被他人注册（npm 无申诉通道），直接改用 `@<账号>/<包名>`（见 §3 通道 A 的 scoped 说明）。
- **版本对齐**：当前工作区以 `dsh-v0.1.1-rc.2` 为唯一基线。Host 提供的 `@deepseek-ai/*`、Cordis、Schemastery 依赖应声明为精确版本范围的 optional peer，并在 devDependencies 镜像用于构建；不要把它们装成插件私有运行时副本。
- **`npm view <pkg> version` 显示旧版本**：dist-tags 的 `latest` 是历史遗留 `0.0.1-rc.1`，
  当前开发线看 `next`：`npm view @deepseek-ai/dsh-tools dist-tags`。
- **git 安装无 `prepare` 必失败**：TS 源码不会自动编译；要么给 `prepare`，要么发构建产物（npm/tgz）。
- **补丁层顺序**：用户 profile 的 `cordis.patch.yml` 在 bundle 层之后，可覆盖你的行（`config` 整块替换）。
- **设置配置**：插件 Host 半用 `installSettingsSection` 声明自己的 namespace，Client 半可通过 `settingsScope.bind` 注册 `settings.plugin.item` keyed 卡片；凭据仍应使用专门的 credentials/环境变量边界，不要混入普通 settings。

