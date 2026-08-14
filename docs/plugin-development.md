# DeepSeek Harness 插件开发详解

> 本文由 [dsh-plugin-dev-guide](https://github.com/anweat/dsh-plugin-dev-guide) 维护，内容基于 deepseek-harness 官方文档整理。

> 源码仓库：`D:\codeproject\deepseek-harness`（下称"仓库"）。本文所有相对路径均相对仓库根。
> 参考文档：`docs/cordis-primer.md`、`docs/user/develop/**`、`docs/cordis-tutorial/**`、`docs/cookbook/adding-a-tool.md`。

---

## 1. 架构总览：一切皆为插件

DSH（DeepSeek Harness）构建在 vendored 的 **Cordis** 插件框架之上（`vendor/cordis`、`vendor/loader`、`vendor/hmr`、`vendor/include`、`vendor/group`、`vendor/schemastery` 等）。
**核心主张：没有任何"特权内核"可打补丁——工具、LLM 适配器、文件访问、agent 循环本身都是挂载在共享上下文里的插件。**（`docs/architecture.md`）

Cordis 的五个核心概念（`docs/cordis-primer.md`）：

1. **插件 = 实现 Service 的对象**：可以是带可选 `inject` 与 `apply(ctx)` 的函数，也可以是 `Service` 子类。
2. **上下文（Context）= 服务仓库**：服务以稳定 key 挂在 `ctx.<key>` 上（`ctx.tools`、`ctx.llm`、`ctx.sessions`……），插件按 key 找服务，而不是 import 具体实现。
3. **用 `inject` 声明依赖**：插件声明所需服务后，等这些服务存在才加载；加载顺序由服务依赖表达，而非手工排序。
4. **类型化事件通信**：服务通过 TS 声明合并声明事件名，按 `emit` / `waterfall` / `parallel` / `serial` 分发。
5. **注册都是可逆效果**：提示词段落、工具 schema、适配器、监听器都通过 `ctx.effect()` / `ctx.on()` 安装，重载/卸载时按注册逆序自动清理。

### 仓库包布局（能力地图）

`packages/<组>/<包>`，包名 `@deepseek-ai/dsh-<name>`：

| 组 | 代表包 | 职责 |
|---|---|---|
| core | dsh-session / dsh-system-prompt / dsh-tools / dsh-agent / dsh-agent-loop | 产品 API 主线：会话、提示词、工具注册、agent 循环 |
| api + typert | dsh-api-remotes / dsh-api-gateway / dsh-typert-* | Remote BFF 装配、类型化 RPC 网关 |
| llm | dsh-llm + 各 provider | LLM 能力：Service Definition/Consumer + DeepSeek 等 provider |
| shell / subprocess / terminal / fs / lsp | dsh-shell + dsh-bash-local / dsh-tool-bash 等 | bash 能力（Definition/Provider/Consumer 三分）、文件系统、语言服务器 |
| skill / web / compaction / subagent / workflow | 各自 Definition + Provider + tool Consumer | 技能、网页搜索/抓取、压缩、子代理、工作流 |
| preset / guard / hooks / interaction | dsh-agent-preset / dsh-tool-timeout / dsh-approval / dsh-ask-user | agent 组合、循环卫生、审批/交互 |
| settings / credentials | dsh-settings-file / dsh-credentials-* | 用户设置文档、凭据引用 |
| bundle | dsh-base / dsh-web-app / dsh-headless | 可安装的 `--profile` 补丁层 bundle |
| host | dsh-host-plugin-inventory 等 | Host（服务端）侧包 |
| client | dsh-client-*（ui-settings、ui-conversation、ui-tool…约 30 个） | Web GUI 浏览器侧插件 |
| extensions | dsh-tool-cordis / dsh-mcp-client | 自指 Cordis 工具集、MCP 客户端 |

生成的**服务/事件 API 目录**在 `docs/subsystems/*.md`（如 `core.md`、`tools.md`、`session.md`），每页含 `cordis-surface` 生成区域：服务公开方法签名 + 事件名/模式/来源。开发插件前先查这里。

---

## 2. 插件的基本形态（具体实现形式）

插件就是一个 TS 模块（ESM）。**完整配置 = 一个 `apply` 函数**。

### 2.1 函数形式（推荐）

```ts
// src/my-plugin.ts
import type { Context } from '@deepseek-ai/cordis'

export const name = 'hello-plugin'          // 可选：显示名（默认取文件名）
export const inject = ['tools']             // 可选：依赖服务，就绪后才 apply
export function apply(ctx: Context) {
  console.log('[hello-plugin] plugin loaded!')
}
```

`apply` 在依赖就绪后被调用，入参 `ctx` 即当前插件上下文。

### 2.2 对象形式

```ts
import type { Context } from '@deepseek-ai/cordis'

export default {
  name: 'my-plugin',
  inject: ['tools'],
  apply(ctx: Context) {
    // ...
  },
}
```

### 2.3 类形式（提供服务给其他插件时用）

```ts
import { Service, type Context } from '@deepseek-ai/cordis'

export default class MyService extends Service {
  static inject = ['tools']

  constructor(ctx: Context) {
    super(ctx, 'myService')   // 'myService' 即 ctx.myService 的 key
  }
}
```

### 2.4 在 cordis.yml 中挂载

插件本身不包含"挂载"信息，由 `cordis.yml`（YAML 补丁）决定。最小示例（`docs/user/develop/basic/index.md`）：

```yaml
- insert:
    - id: hello
      name: '/abs/path/to/deepseek-harness/scratch-plugin/src/my-plugin.ts'
```

`name` 是模块标识：本地开发写**绝对路径**的 TS 文件（`node --import tsx` 直接执行），打包/安装后写**包名**（`name: dsh-hello-plugin`，Node 解析）。

启动 Web GUI：

```sh
pnpm dsh web --patch ./scratch-plugin/cordis.yml   # 仓库根执行
# 打开 http://127.0.0.1:3080，终端打印 [hello-plugin] plugin loaded!
```

---

## 3. 生命周期与自动清理

### 3.1 Fiber 状态机（`docs/user/develop/framework/index.md`）

每个已加载插件拥有一个 **Fiber** 作用域：

```
PENDING → LOADING → ACTIVE
                 ↘ FAILED
ACTIVE → UNLOADING → DISPOSED
```

- `PENDING`：已声明但必需依赖未就绪（`inject` 等待中）
- `LOADING`：依赖就绪，`apply` 正在执行
- `ACTIVE`：运行中；`FAILED`：`apply` 抛错
- `UNLOADING` → `DISPOSED`：卸载并清理资源

### 3.2 依赖驱动的加载与自动重载

声明 `inject = ['tools', 'llm']` 后，`apply` 运行时 `ctx.tools` / `ctx.llm` 一定就绪。
若运行期某个必需服务消失（如 provider 被替换），依赖它的插件**自动卸载**，服务回来后再加载。

### 3.3 自动清理

所有经 `ctx` 的注册在卸载时自动撤销，无需手动 removeListener / clearInterval：

```ts
export function apply(ctx: Context) {
  ctx.on('some-event', handler)                    // 事件监听
  ctx.tools.register(defineTool({ /* ... */ }))    // 工具注册
  ctx.effect(() => {                               // 自定义资源
    const timer = setInterval(() => {}, 5000)
    return () => clearInterval(timer)              // 返回的 disposer 在卸载时运行
  })
}
```

注意：逆序调用 disposer，但**多个异步 disposer 并发执行、无串行完成保证**；顺序敏感的清理应放进同一个 `ctx.effect()` 的单个 disposer 里串行 await。

### 3.4 HMR 热替换

`@deepseek-ai/cordis-plugin-hmr`（base bundle 已挂）监听插件源码文件变更：卸载旧实例 → 加载新代码 → 重新 `apply`。
因为注册都是效果，旧实例的注册不会残留。`cordis.patch.yml` 的编辑同样触发整树事务性重载。

---

## 4. 插件配置（`docs/user/develop/basic/config.md`）

### 4.1 声明 Config 类型 + Schemastery schema

导出 `Config` 接口和**同名**的 schema（Standard Schema 接口，不能用普通对象）：

```ts
import type { Context } from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'

export const name = 'my-plugin'

export interface Config {
  greeting: string
  maxRetries: number
  verbose?: boolean
}

export const Config: Schema<Config> = Schema.object({
  greeting: Schema.string().default('Hello'),
  maxRetries: Schema.number().default(3),
  verbose: Schema.boolean().default(false),
})

export function apply(ctx: Context, config: Config) {
  console.log(config.greeting)  // 用户值或 schema 默认值
}
```

`cordis.yml` 中传入：

```yaml
- insert:
    - id: hello
      name: './src/my-plugin.ts'
      config:
        greeting: 'Hi there'
        maxRetries: 5
```

### 4.2 设计原则

- **一切可调值都进配置**：判断标准是"cordis.yml 能否不改代码就改变它"（`timeoutMs` 而非硬编码 `TIMEOUT`）。
- **快速失败**：约束写进 schema，加载期即报错；涉及服务的引用用依赖注入表达。
- 配置变更 = HMR 整插件替换，旧配置的注册自动清理。

---

## 5. 事件系统（`docs/user/develop/framework/events.md`、`docs/cordis-primer.md`）

### 5.1 分发模式

| 模式 | 等待? | 顺序 | 返回值 |
|---|---|---|---|
| `emit` | 否 | 注册顺序 | 无（广播） |
| `waterfall` | 否 | 注册顺序 | 有（管道） |
| `parallel` | 是 | 全部并行 | 无 |
| `serial` | 是 | 注册顺序 | 有（首个非空短路） |
| `bail` | - | 注册顺序 | 首个非 null/false/undefined 短路（events.md 补充） |

**waterfall 语义**：监听器收到 `(...args, next)`，必须调用 `next()` 委托下游（可包装结果）；不调 `next()` 即短路——这是拦截/网关行为的机制。

### 5.2 类型化事件（声明合并）

```ts
import '@deepseek-ai/cordis'

declare module '@deepseek-ai/cordis' {
  interface Events {
    'my-plugin/ready': (payload: { id: string }) => void
    'my-plugin/transform': (input: string, next: () => Promise<string>) => Promise<string>
  }
}
```

### 5.3 真实例子：工具调用日志插件

```ts
import type { Context } from '@deepseek-ai/cordis'
import '@deepseek-ai/dsh-tools'

export const name = 'tool-logger'

export function apply(ctx: Context) {
  ctx.on('tools/result', (exec, result) => {
    console.log(`[tool] ${exec.name}(${JSON.stringify(exec.arguments)})`)
  })
}
```

DSH 的 Cordis 事件采用 `namespace/action` 命名：`agent/step`、`agent/request`、`tools/result`、`session/event` 等，完整签名在 `docs/subsystems/**` 的 `cordis-surface` 区域。
注意 `turn/*`、`step/*`、`tool/call` 等是**持久化会话事件类型**，不是同名 Cordis 事件——要观察它们需监听 `session/event` 并检查 `event.type`。

---

## 6. 工具插件（模型可调用能力）

工具是模型调用的入口，用 `defineTool` 定义（`docs/user/develop/basic/tool.md`、`docs/cookbook/adding-a-tool.md`）：

```ts
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'greet-tool'
export const inject = ['tools']

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'greet',
    description: 'Greet someone by name.',            // 模型看到的部分
    parameters: {                                      // ParameterSchemaSpec，自动进入系统提示词
      name: { type: 'string', required: true, description: 'The name to greet' },
    },
    output: {                                          // 规范化返回值
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],  // 转模型可见内容
    },
    async execute(args) {
      return `Hello, ${args.name}!`                    // args 已按 schema 校验、类型安全
    },
  }))
}
```

### 6.1 execute 契约要点

- **args 自动校验**：模型生成的 `arguments` 在 `execute` 前按 schema 校验（类型、必需键、字面量约束、exact-one union、嵌套值）；`args` 是只读冻结值。
- **`exec` 对象**：携带不可变身份 + `exec.token`，操作字段是 `exec.signal`（取消信号）——长时间工作必须响应它。
- **返回一个规范化 JSON 值**（`output.schema` 声明）：注册器校验、冻结后交给 `output.render`。抛错或返回非法值 = `isError`。
- **`exec.agent` 异步通知**：`exec.agent.inject({content, source:{kind:'plugin', plugin:'<name>'}})` 追加持久上下文，供**下一次**模型请求看到（不是唤醒）。
- **后台长任务**：用 `ctx.jobs.start({kind, label, owner, run})`，返回类型化句柄 `{kind:'background', jobId}`。

### 6.2 工具级扩展点（部署策略别写死在工具里）

`tools/pre-execute`（放行/拒绝/询问策略）、`ctx.tools.guard()`（最终单调拒绝）、`tools/execute`（包装调度：超时/重试/指标）、`tools/post-execute`（替换展示或返回值）、`tools/result`（观察规范化结果）。
`dsh-tools` README 定义每个扩展点的输入、顺序、返回值与失败行为。

### 6.3 UI 卡片（纯展示投影，可重放）

`presentCall(args)` / `presentResult(args, {content, isError, meta?})` 返回 `card` 标记的渲染意图：`generic` / `terminal` / `diff` / `search` / `web`。
**硬规则**：两者必须是对 args（+ result）的**纯函数**——不能有 I/O、读会话状态、时钟/随机（它们同时跑在直播流和会话回放上）。`output.presentationMeta(args, value)` 可投影可持久化的卡片数据（如 diff hunks）随 `tool/result` 落盘。

---

## 7. 服务：定义、依赖与三方能力模式

### 7.1 提供服务（类形式 + 声明合并）

```ts
import { Service, type Context } from '@deepseek-ai/cordis'

declare module '@deepseek-ai/cordis' {
  interface Context {
    metrics: MetricsService
  }
}

export default class MetricsService extends Service {
  constructor(ctx: Context) {
    super(ctx, 'metrics')   // 服务名 = ctx.metrics
  }
  record(event: string, value: number) { /* ... */ }
}
```

消费：`export const inject = ['metrics']`，`ctx.metrics.record(...)`。
可选依赖：不写 inject，用 `ctx.get('metrics')?.record(...)`。

### 7.2 三方能力设计（Service Definition / Provider / Consumer）

可替换能力（如 Bash 执行）拆三包（`docs/user/develop/practice/index.md`）：

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  dsh-shell   │────▶│  dsh-bash-local  │     │ dsh-tool-bash│
│(definition) │     │    (provider)     │     │(consumer/tool)│
└─────────────┘     └──────────────────┘     └──────────────┘
       ▲                                            │
       └────────────────────────────────────────────┘
                    inject: ['shell']
```

- **Definition** 包：定义抽象 `Service` 子类 + Request/Result 类型 + `declare module` 合并（如 `dsh-shell`）。
- **Provider** 包：实现具体子类（如 `dsh-bash-local`），`apply` 里 `ctx.plugin(MyCapLocal)` 挂载。
- **Consumer** 包：`inject: ['tools', 'shell']`，用 `defineTool` 把能力暴露给模型。
- Provider 与 Consumer **互不依赖**，都只依赖 Definition；在 cordis.yml 里换 Provider 行即可换实现。
- 不要预防性拆分——只有需要独立演进的才拆包。

### 7.3 服务隔离（group + isolate）

`cordis.yml` 中 `cordis-plugin-group` 可让不同插件组看到同一服务的**独立实例**（如两组各自独立的 Bash，互不干扰）：

```yaml
- id: group-a
  name: '@deepseek-ai/cordis-plugin-group'
  group: true
  isolate:
    shell: true
  config:
    - name: '@deepseek-ai/dsh-bash-local'
      config: { timeoutMs: 5000 }
    - name: './src/plugin-a.ts'
```

---

## 8. 加载与组合：cordis.yml 补丁树

### 8.1 行（Entry）格式

`cordis.yml` 是 YAML 补丁列表，`insert` 插入行，或按 `id` 覆盖已有行（`docs/event-producer-consumer.md` 有完整行语义表）：

```yaml
- insert:
    - id: timer
      name: '@deepseek-ai/cordis-plugin-timer'
    - id: llm
      name: '@deepseek-ai/dsh-llm'
    - id: web-search-deepseek
      name: '@deepseek-ai/dsh-web-search-deepseek'
      inject: [llm]                 # 行级依赖
      config: { /* 经插件 schema 校验 */ }
      disabled: false               # 可含 !!js 表达式
```

- `config` 支持 `!!js` 表达式，在**该行的注入上下文**中求值（如 `port: !!js ctx.webStartup.port ?? 3080`）；`disabled` 在每次挂载决策时对 loader 上下文求值。
- 覆盖语义：**整块替换** `config`，不深合并——覆盖一行必须重述它需要的全部键。
- `Group` / `Include` 行保持配置字面量，子行的 `!!js` 属于子行自己的 Fiber。

### 8.2 补丁分层顺序（后层赢，按行覆盖）

1. profile manifest `dsh.profile.bundles` 列表中的各 bundle patch（按列表顺序；`@deepseek-ai/dsh-base` 最先）
2. profile 自己的 `cordis.patch.yml`
3. `$DSH_HOME/cordis.patch.yml`（机器级偏好，跨 profile 共享）
4. 每个 `--patch <path>` 覆盖层（argv 顺序）

`dsh --profile web --dump-config` 可查看组装结果（含来源注释，`!!js` 不求值）。

### 8.3 内置 bundle 长什么样

`packages/bundle/base/cordis.patch.yml` 是 `dsh-base` 的补丁：一次 insert 挂 timer、hmr、llm、session、typert、settings、agent 等所有核心行；`dsh-web-app` 再按 id 覆盖/追加 Web 相关行。**行顺序不承载加载语义**（激活由服务可用性驱动），分组只为可读性。

---

## 9. 打包与分发（`docs/user/develop/basic/publish.md`）

### 9.1 两个概念、两个 manifest

- **Bundle**：npm 包，`package.json` 声明 `dsh.bundle`（回答"这个包贡献什么"——一个补丁层）。作者分发它。
- **Profile**：`$DSH_HOME/profiles/<name>` 目录，manifest 声明 `dsh.profile`（回答"哪些 bundle 以什么顺序组合"）。用户用 `dsh --profile <name>` 启动它。二者互不为对方。

```jsonc
// hello-plugin/package.json —— bundle manifest
{
  "name": "dsh-hello-plugin",
  "version": "0.1.0",
  "type": "module",
  "main": "index.js",
  "files": ["index.js", "cordis.patch.yml"],
  "dsh": { "bundle": { "patch": "./cordis.patch.yml" } }
}
```

```yaml
# hello-plugin/cordis.patch.yml —— 补丁行引用包名而非源码路径
- insert:
    - id: hello
      name: dsh-hello-plugin
```

### 9.2 安装与卸载

```sh
dsh plugin --profile demo add ./hello-plugin       # 转发 pnpm；首次自动初始化 profile（含 dsh-base）
dsh plugin --profile demo remove dsh-hello-plugin
dsh --profile demo --dump-config                   # 验证分层
dsh --profile demo
```

`dsh plugin --profile <name> <pnpm-verb>` 把参数转发给 profile 目录里的 pnpm；每次成功后按安装状态调和 `dsh.profile.bundles`。

### 9.3 Git 安装的坑

git 安装拉的是**源码**：需要作者的 `prepare` 脚本自包含构建（如 `turtle-ui` 的独立 tsdown 配置），且 pnpm ≥10 默认拒绝执行 git 依赖的 `prepare`——首次 `add` 会失败，把 pnpm 打印的包 key 抄进 profile 的 `pnpm-workspace.yaml` 的 `allowBuilds` 再重跑。**这是"允许在安装时执行该包代码"的信任决定**，只放行可信源码并钉 commit。不想麻烦就发 npm 包或 tarball（`pnpm pack`）。

---

## 10. Web GUI（Client）插件

浏览器侧是独立的 client 插件生态（`packages/client/**`），与 Host 插件共用同一套 Cordis 上下文模型，但跑在浏览器里。

### 10.1 声明（`dsh.client`）

```jsonc
// packages/client/ui-tool/package.json 中的 dsh 字段
"dsh": {
  "client": {
    "inject": ["@deepseek-ai/dsh-client-runtime", "@deepseek-ai/dsh-client-locale", "..."],
    "platform": "web"
  }
}
```

### 10.2 构建产物

`packages/client/tsdown.client.ts` 的 `clientBundle(id, libEntry)` 预置生成两种产物：
- **Node 半**（`lib/index.js`）：Host Loader 可导入的入口；
- **浏览器半**（`lib/client.js`）：closure-factory 产物，调用 `window.__ModuleLoader__.load({id, factory})` 注册，通过注入的 require（模块表，无全局/import map）解析外部依赖；CSS Modules 编译后自动注入 `<style data-plugin="<id>">`，卸载时移除。

### 10.3 插槽（slot）系统

UI 扩展点用 slot 表达：`ctx.slots.inject()` 注册贡献（带 `order`），如 `ui-settings-plugins` 声明 `settings.plugins.tab` 根列表插槽，`ui-settings-plugin-inventory` 注入自己的 `all` tab。slot 跟随注册/注销/语言切换/teardown 自动增删。

### 10.4 开发期 HMR

- `dsh web` 启动源码 Host（tsx），**client-plugin HMR receiver 始终挂载**；
- 另开 `pnpm run dev:web`（`scripts/dev-web.ts --poll`）只监视带 `dsh.client` 声明的 client 包并重写 `lib/client.js`；
- 只改 Remote 方法实现体无需重新生成 Typert；改了装饰器/导出名/参数/返回值等契约后要 `pnpm run build:lib`（Host 先生成严格契约，Client 再编译打包）。

### 10.5 Host→浏览器远程调用（@Remote + Typert）

Host 服务方法标 `@Remote` / `@RemoteScope`，构建期 Typert 生成：
`typert.host.js`（Host 反射）、`typert.remote-client.js`（可挂载的 `TypertRemoteContribution`）等；Client 经 `api-remotes` 装配后以 `ctx.remote.<namespace>.<method>(args)` 调用，走 `POST /api/<namespace>/<method>`，参数严格 schema 校验、结果验证。约束：Remote 必须是公开非静态实例方法、参数为必填简单标识符、JSON 可表示；复杂对象需 `TypertLookupMap`。

### 10.6 可配置插件的浏览器卡片

带浏览器半的 Host 插件可在 `settings.plugins.tab` 的 `settings.plugin.item` 插槽注册自己的配置卡片（如 bash 卡编辑 `timeoutMs`/allow 列表）。注意：**暴露是 Host 侧 allowlist 决定的**——仓库外的插件要在这里露脸需要改 `packages/host/apiproxy`。

---

## 11. 高级能力：agent 自改运行时

`packages/extensions/tool-cordis`（`examples/web-cordis` 演示，`pnpm run demo:cordis`）给模型 5 个自指工具：
`cordis_inspect`（只读报告：服务/插件 Fiber/工具/API/事件/client 插槽）、`cordis_define`（记录包定义，不执行）、`cordis_run`（沙箱内求值 Host 半 + 广播浏览器半到所有打开的页面）、`cordis_stop`、`cordis_undefine`。
动态包只活在进程内存，不写文件、不改 cordis.yml、重启即失——想要持久插件仍要走常规开发流程。信任姿态：**沙箱不是安全边界**，按 bash 权限对待。

---

## 12. 开发工作流（源码运行）

```sh
# 首次（仓库根）
pnpm install
pnpm run typecheck        # 含 Host lib 阶段生成的 Typert 契约
pnpm run build            # tsc 发 lib/types + tsdown 打 bundle + build:web

# 日常
pnpm dsh web --patch ./scratch-plugin/cordis.yml   # 源码 Host + Web GUI
pnpm run dev:web          # 另一个终端：client 插件 watcher（HMR）
pnpm run test / test:e2e / lint / hygiene / doc-sync
pnpm dsh --profile headless "task"                 # 一键任务（需 DEEPSEEK_API_KEY）
```

快速上手三步（`docs/user/develop/basic/index.md`）：
1. 仓库根建 `scratch-plugin/src/my-plugin.ts`（最小 `apply`）；
2. 建 `scratch-plugin/cordis.yml`（`- insert:` 一行，`name` 用绝对路径）；
3. `pnpm dsh web --patch ./scratch-plugin/cordis.yml`，看终端日志。

---

## 13. 文档与参考索引

| 主题 | 路径（相对仓库根） |
|---|---|
| 第一个插件 / 工具 / 配置 / 发布 | `docs/user/develop/basic/{index,tool,config,publish}.md` |
| 生命周期 / 服务 / 事件 | `docs/user/develop/framework/{index,service,events}.md` |
| 三方能力 / LLM 适配器 | `docs/user/develop/practice/{index,llm-adapter}.md` |
| Cordis 概念速览 | `docs/cordis-primer.md` |
| Cordis 7 章教程（含组合与 HMR） | `docs/cordis-tutorial/**` |
| Cordis API 参考（context/registry/service 等） | `docs/cordis-api/**` |
| 工具作者参考 | `docs/cookbook/adding-a-tool.md`、`extension-cookbook.md` |
| 服务/事件生成目录 | `docs/subsystems/**`（core/tools/session/llm/shell/web/…） |
| 生成目录：工具 / 配置 / 模块图 | `docs/tool-catalog.md`、`docs/config-catalog.md`、`docs/module-graph.md` |
| 架构 / 能力接缝 / 开发指南 | `docs/architecture.md`、`docs/capability-seams.md`、`docs/development.md` |
| CLI 参考 | `apps/cli/reference/README.md` |
| 真实示例 | `examples/web-cordis/cordis.yml`、`examples/mcp-memory/*.cordis.yml`、`examples/AGENTS.md` |
| 工具集/自指插件 | `packages/extensions/tool-cordis/README.md` |
| 客户端插件规范 | `packages/client/README.md`、`packages/client/tsdown.client.ts` |

**最后提醒**：文档可能滞后于代码。任何"服务有哪些方法、事件有哪些"的问题，以 `docs/subsystems/**` 的 `cordis-surface` 生成区域和对应包的 TypeScript 接口为准；仓库要求"不要维护第二份静态清单"。
