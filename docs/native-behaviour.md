# DSH 原生行为注意事项

本文只记**实测确认过**的运行时行为,不复述官方文档已经说清的部分。每条都注明是怎么确认的,因为其中好几条与直觉相反,而只有一条是从文档里读出来的。

来源:构建 [dsh-substrate](https://github.com/anweat/dsh-substrate) 时对真 harness 做的机制实验(160 条断言)与 2,768 个语料包的端到端启动。实验代码在那个仓库的 `experiments/` 与 `e2e/`。

---

## 1. 注册身份取自调用方的 fiber

`SlotRegistry` 从 `this.ctx.fiber.name` 盖 `registrant`,`connection.rpc` 捕获 `owner = this.ctx`。而 Cordis 的 service 代理会把 `this.ctx` 重绑到**读取服务的那个 Context**。

后果:**一个"帮你注册"的辅助函数,必须用你自己的 `ctx` 调用。**

```js
// 你的插件里
export function apply(ctx) {
  helper(ctx, spec)        // registrant = 你的插件名
}

// 辅助函数持有自己的 ctx 去注册
function helperWrong(spec) {
  myOwnCtx.slots.register(spec, Comp)   // registrant = 辅助库的名字
}
```

实测(真 `SlotRegistry`):同一个函数,传插件 ctx 得 `plugin-a`,传辅助库自己的 ctx 得 `the-scaffold`。

`register()` 的 `options.registrant` 可以显式覆盖,但那是逃生口,不是常规写法。

**路由是例外:`webServer.register({ kind, path, handler })` 不带任何归属信息。** 想知道一条路由是谁注册的,只能从调用方上下文推。这和 slots / rpc 的不对称是真实存在的。

## 2. 后端侧没有任何一条接缝是"相加"的

| 接缝 | 撞名时 |
|---|---|
| `webServer.register(path)` | 抛错 |
| `connection.rpc.handle(channel)` | 内部落成 prefix 路由,**同样抛错** |
| `connection.rpc.intercept('/api', …)` | 全进程**只有一个** interceptor 座位,第二个抛错 |
| `tools.register(name)` | 同一层内抛错 |
| slot `single` / `keyed` | 同一 priority 上第二个抛错 |
| slot `list` / `chain` | 相加,不冲突 |

所以路径和工具名**不是可以自由取的名字**。把包名放进路径里,不同包之间撞车就从"不太可能"变成"不可能"。

实测:在真 `WebServer` + `connection` 上,两个不同包的同名面板共存;同一个包挂第二次仍然抛错。

## 3. `run_code` 是无条件保留名

`tools.register('run_code')` 与 `tools.restrict('run_code')` 都抛错,**scope 分层对它无效**。它是 Code Mode 的表示层通道,不是一个普通工具。

这一条是把全语料灌进真注册表才暴露的——只看文档不会注意到它和其它保留不是一回事。

## 4. 激活顺序由服务可用性决定,不由行序 ⚠

这是最容易踩的一条。

```
一个探针插件追加在 cordis.yml 的最后一行,inject: ['tools']
  它 apply 时看见的工具数:   0
  启动完成后再读:            15
```

原因:探针 inject `tools`,而 `tools` 在 agent-spine 提供的**那一刻**就可用了——那早于各个工具包往里注册。行序完全没参与。

**所以:不要在 `apply()` 里读注册表来"看看现在有什么"。** 那时候多半是空的。要在全局视图完整之后动作,得等到 boot 之后(比如 agent 建立期)。

想强制顺序的话,`inject` 是 entry 选项,补丁层可以让一行依赖另一行,依赖图会强制顺序。

## 5. 提供服务的垫片不能 inject 同名服务

在 `cordis:group` 上写 `isolate: { tools: true }` 可以给子树换一个 `tools` 实例——**纯配置声明,零上游改动**。但那个提供者本身:

```js
export const inject = ['tools']   // ✗ 死锁:realm 里这个名字解析到它自己要提供的那个
```

它会永远 pending。正确做法是不声明 inject,用 `ctx.root.get('tools')` 越过 realm 重映射去拿真实现。

## 6. 前端平面的三条硬限制

**`BootPluginRow` 只有 `{ id, inject, immediately }`。** 没有 config 位,也没有 priority。所以两个客户端插件抢同一个 `single` 槽时,今天唯一的补救是**撤下其中一个插件的整个前端半**——粒度是"整个插件",不是"那一个座位"。

**平台种子词是固定的一小组:** `react`、`react/jsx-runtime`、`react-dom`、`react-dom/client`、`@deepseek-ai/cordis`、`dsh-client-ui-slots`、`dsh-client-ui-primitives`。这些是**共享的同一个实例**。你的 bundle 引用这几个之外、又不是启动图中一行的模块,会在 require 时抛错。

**设计令牌是环境继承的,但没有导出面。** 外壳把令牌定义在 `body` 与 `body[data-ds-dark-theme]` 上,所以你的 CSS 直接 `var(--dsw-…)` 就能用,不需要 import。分层是关键:

```
alias   78 个,其中 66 个在暗色下翻转   ← 主题相关的属性用这层
static  73 个,只有 1 个翻转           ← 固定调色板
```

**主题相关的属性(`color`/`background`/`border-color`/`box-shadow`/…)用 `alias`。** 用 `static` 或写死颜色,暗色模式下不会跟随。

例外确实存在:品牌色渐变在两色下故意一致;`--dsw-alias-tooltip-bg` 浅色 850 / 暗色 750 **两色都深**,所以浮层上写死白字是对的。

顺带:官方自己的 `packages/client` 里有 10 处引用了仓库中不存在的令牌且无回退。`var()` 引用未定义属性且无回退时,该声明在 invalid at computed-value time 阶段失效——继承型属性退回继承值,非继承型退回 initial。**不是"用了默认色",是静默不生效。**

## 7. 热更新:改补丁层不重启,爆炸半径就是那一行

`cordis.patch.yml` 被监视,改动经 `entry.update()` 重新应用。实测:

| 编辑 | 代价 |
|---|---|
| 停掉一行 | 只有那行 dispose,其它插件既不 dispose 也不重新 apply |
| 清空补丁 | 只有被停的那行重新 apply |
| **整体重写补丁文件** | 未变的行不动 |
| 改一行的 config | 那行 **dispose + apply**(不是就地重配) |
| 写入坏补丁 | 树不被拆,进程存活,之后的好补丁照常生效 |

第四行值得注意:**config 变更会重启那个插件**,不是热改配置。有状态的插件要考虑这一点。

**但浏览器那侧收不到名册变更。** `/plugins/events` 只有 `graph` 与 `rebuilt` 两种帧;`graph` 只在连接建立那一刻写一次,之后主机唯一的订阅是 `onRebuilt`。所以:

> **主机平面的改动即时生效;前端平面的改动需要刷新页面。**

## 8. scope 的几个具体点

- `createScope(ctx, key)` 返回 `{ ctx, dispose, rawDispose }`——**不带 key 的句柄**。key 是你传进去的那个 Symbol,后面 `tools.schemas(key)` 和链绑定都要用,自己存好。
- 裸的 scope Context **不能直接读 `ctx.tools`**——Cordis 的 inject 纪律会拒绝。注册必须经由一个挂在该 scope 里的真插件 fiber。
- **两个 scope 可以 claim 同一个工具名;同一个 scope 里的两个插件不行。** 想让 N 个争用者共存,就要 N 个 scope,不是一个共享沙箱。
- 链序即优先级,不是激活顺序;近的遮蔽远的。

## 9. 几个具体的写法坑

- **工具定义必须有 `output.render`。** 缺了会在注册时炸,报 `Cannot read properties of undefined (reading 'render')`,信息不指向真正的原因。
- **`StoredEntry` 的 `id` 嵌在 `options` 下**,不是顶层:读 `entry.options.id`,不是 `entry.id`。
- **RPC 通道文法是 `^\/[A-Za-z0-9._~-]+$`——只有一段,不许内层斜杠。** `/a/b` 直接被拒。`/api` 是保留通道,只能 `intercept`,不能 `handle`。
- **`Object.assign(fn, { name })` 设不上**——函数的 `name` 只读。要给插件命名,用具名函数声明。

## 10. 组合里约三分之一的包从不作为"行"出现 ⚠

读 `cordis.yml`(或组合后的 entry list)去推"这个部署装了什么",会漏掉一大块。组合有**三层嵌套,只有两层是看得见的**:

| 层 | 形态 | 在 entry list 里可见? |
|---|---|---|
| 补丁层 bundle | `packages/bundle/*/cordis.patch.yml` | ✅ 应用后就是普通的行 |
| 分组 | `cordis:group` + 数组 config | ✅ 嵌套的行,递归展开即可 |
| **一个插件挂子插件** | 它在自己 `apply` 里 `ctx.plugin(X)` | ❌ **完全不可见** |

第三层是问题所在。`@deepseek-ai/dsh-agent-spine-demo` 是一行,但它在 `apply` 里挂了 `tool-bash`、`tool-jobs`、`tool-skill` 等等——**这些包名在组合出的配置里一次都不出现**。

实测两个出厂 profile:

```
web        135 行 -> 展开后 171 个包    其中 37 个从不作为行出现
headless    81 行 -> 展开后 119 个包    其中 39 个从不作为行出现
```

后果很具体:按行列表推导"哪些工具名已被占用",headless 上只能得到 15 个里的 12 个,漏掉 `bash`、`skill`、`job_list` 等等——而这些恰恰是最容易被第三方插件重名的。

### 唯一的静态线索是 `peerDependencies`

harness 的包把自己要挂的子包声明为 `peerDependencies`(`dependencies` 按约定几乎是空的)。按 peer 做闭包展开,漏报从 6 个降到 0:

```
仅行列表       12 / 15
peer 闭包      15 / 15
peer + dev     15 / 15   ← 一个工具都不多,所以用更窄的 peer
```

### 展开必然会多报,而这是对的方向

peer 闭包会带进"依赖了但没挂"的包,以及**条件注册**的工具(`read_image`、`list_agents`、`report` 在出厂 profile 里确实没注册)。headless 上多报 14 个。

不要试图消掉多报。**两种错误的代价不对称**:

- 名字误判为"被占" → 某个插件白挨一次改名或降级
- 名字误判为"空着" → **整个组合起不来**

所以往多报那边偏,并且在数据里标明这是**上界**而不是精确集合(我们用 `mayRegisterMore: true`)。

### 另外:一个包可以以多个名字出现

工具名可以是加载期 config——`tool-subagent` 的 `toolName` 就是。出厂组合把它按不同 subagent 后端加载了两次,所以模型看到的是 `subagent` **和** `subagent_fork`。按"一个包一组固定工具名"建模会漏掉别名。

## 11. 前端插件的三处实测坑

写完一个真的 client 插件、装进 web profile 跑起来之后拿到的,每一条都只有真跑才会暴露。

**bundle 必须自己向模块表注册。** 本指南 §9.3 的模板里有这段,而它容易被当成样板略过 —— 略过之后构建、类型检查、bundle 下载全都正常,只有启动会失败。产物要包成:

```js
window.__ModuleLoader__.load({ id: '<包名>', factory: (require) => {
  var module = { exports: {} }; var exports = module.exports;
  /* … */
  return module.exports;
} })
```

少了这层包装,构建通过、类型全过、bundle 也被下载了,启动时报 `loaded without registering "<pkg>" via __ModuleLoader__.load`。外置的平台模块正是通过注入的那个 `require` 解析的,不走全局也不走 import map。

**注册一张设置卡要三样东西齐全,少一样就静默不显示。**

```js
export const inject = ['slots', 'locale', 'settingsScope']   // ← locale 必需

ctx.effect(() => ctx.locale.register(NS, { zh, en }), '…')   // ← 先注册词典
ctx.slots.inject('settings.plugin.item', () => ctx.slots.register({
  name: 'settings.plugin.item',
  key: NS,
  locale: NS,                                                 // ← 卡片靠它取文案
  inject: () => face,
}, Card))
```

`dsh.client.inject` 里还要列上 **`@deepseek-ai/dsh-client-ui-settings-plugins`** —— 声明这个槽的那个包。少了它,`slots.inject` 等的槽可能还没出现。

漏掉 `locale` 或漏掉那条 client inject 时,bundle 正常加载、控制台没有任何报错、插件也在启动图里,**卡片就是不出现**。

**卡片的表单基础设施是内部的。** `ui-settings-plugins` 渲染自家三张卡用的 `PluginCard` / `ValueField` / `CardForm` 不在它的 exports 里,第三方卡从 `ui-primitives` 和环境令牌搭。

**这些包的 `latest` dist-tag 不可靠,要按 DSH 版本对齐着装。** `npm view @deepseek-ai/dsh-client-runtime version` 给的是 `0.0.1-rc.1`,一个陈旧发布;它依赖 `@deepseek-ai/dsh-compact`,而那个包已改名 `dsh-compaction`,registry 里没有,于是安装直接 404。

实际与 DSH 对齐的版本是 `0.1.1-rc.2`(和 `@deepseek-ai/dsh` 同号),只有 2 个依赖,干净。

```bash
npm view @deepseek-ai/dsh-client-runtime versions   # 看列表,不要只看 latest
```

按 `latest` 装会得到一个装不上的旧版本,而报错指向一个不存在的包名 —— 很容易被误判成"官方发布坏了"。

## 12. profile 的 node_modules 里没有 loader

想给 loader 之类的核心包打 `pnpm patch` 时会撞上这个:

```
<home>/profiles/node_modules/@deepseek-ai/cordis-plugin-include
  → 符号链接 → dsh 自身安装目录下的那一份
```

`healProfilesModuleFallback` 把 **dsh 自己的依赖**软链进 profiles 目录。所以 loader **不是任何 profile 的依赖**,它属于 dsh 的安装。把 `patchedDependencies` 写进 `<profile>/pnpm-workspace.yaml`,pnpm 会照常装完、不报任何错,而**补丁一行都没生效**——因为要打的目标根本不在那个工作区里。

## 13. 有些事静态判定不了

写工具的人容易高估静态分析能拿到多少:

- **37% 的路由注册路径不是字面量**,静态不可判。
- **条件注册的工具**(`if (config.x) ctx.tools.register(...)`)一般情况下不可判定。
- 槽的 `key` 与 `priority` 也经常是非字面量。

如果你在写分析或校验工具,把这些如实报为"未知",不要当成"没有"。**未知被读成"这个名字空着",代价是整个组合起不来。**
