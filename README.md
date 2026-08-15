# dsh-plugin-dev-guide — DeepSeek Harness 插件开发集成指南

> DSH（DeepSeek Harness）插件开发的完整指南仓库：从第一个插件到自动发布到社区。
> 面向 DSH 插件作者（agent 开发者），内容基于官方源码仓库 [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)。

![License](https://img.shields.io/badge/license-MIT-blue)

## 目录

| 内容 | 路径 | 说明 |
|---|---|---|
| **插件开发详解** | [docs/plugin-development.md](./docs/plugin-development.md) | 实现形式 / 生命周期 / 事件 / 工具 / 服务 / cordis.yml / 打包 / Web UI 插件 / 远程调用 / 工作流 / 参考索引 |
| **发布到社区指南** | [docs/publishing.md](./docs/publishing.md) | npm / GitHub / tarball 三通道，打包非必须的复用形态，GitHub Actions 全自动发布，自动发现/同步/发送体系 |
| **插件前端开发指南** | [docs/plugin-frontend.md](./docs/plugin-frontend.md) | Web GUI / Client 插件：`dsh.client` 包契约、Slot 槽位目录与选型、主题、设置卡片、外部包构建协议、HMR、Host↔Client 通信 |
| **示例插件** | [examples/hello-plugin](./examples/hello-plugin/) | 最小可用插件骨架（加载日志 + greet 工具），可直接复制改造成新插件 |
| **发布巡检脚本** | [scripts/discover-plugins.mjs](./scripts/discover-plugins.mjs) | 自动搜索账号下 dsh 相关仓库 → 对比 npm 发布状态 → 同步 checkout → 打 tag 触发 CI 发布 |
| **插件索引（作者）** | [plugins.md](./plugins.md) | anweat 的 DSH 插件集合：安装命令 / 版本 / 说明 / 新增流程 |

## 快速开始

### 1. 准备

- Node.js ^22.19 || >=24，pnpm（仓库 pin pnpm@11.7.0）
- deepseek-harness 源码仓库克隆（pnpm install && pnpm run build 后可用 pnpm dsh 源码运行）

### 2. 第一个插件（3 步）

复制 [examples/hello-plugin](./examples/hello-plugin/) 到你的项目，然后：

```ts
// src/my-plugin.ts —— 插件 = 一个导出 apply 的 TS 模块
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'hello-plugin'
export const inject = ['tools']

export function apply(ctx: Context) {
  console.log('[hello-plugin] plugin loaded!')
  ctx.tools.register(defineTool({
    name: 'greet',
    description: 'Greet someone by name.',
    parameters: { name: { type: 'string', required: true, description: 'The name to greet' } },
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    async execute(args) { return `Hello, ${args.name}!` },
  }))
}
```

```yaml
# cordis.yml —— 挂载补丁（name 为插件源码绝对路径）
- insert:
    - id: hello
      name: '/abs/path/to/your-plugin/src/my-plugin.ts'
```

```sh
cd <deepseek-harness 仓库根>
pnpm dsh web --patch /abs/path/to/your-plugin/cordis.yml
# 打开 http://127.0.0.1:3080，终端打印 [hello-plugin] plugin loaded!
```

### 3. 发布到社区

1. 按 [发布指南](./docs/publishing.md) 把插件改造成 bundle 包（dsh.bundle manifest + cordis.patch.yml + prepare 脚本）；
2. 复制 .github/workflows/publish.yml（发布指南 §3.5 有完整模板），推 tag 即自动发布到 npm + GitHub Release；
3. 用 scripts/discover-plugins.mjs 一键巡检/发布你账号下的所有 dsh 插件。

## 设计要点速览

- **一切皆插件**：DSH 构建在 vendored Cordis 上，工具、LLM 适配器、文件访问、agent 循环都是插件；没有特权内核。
- **插件 = 函数**：export function apply(ctx)，可选 name/inject/Config；注册即可逆效果，卸载自动清理，天然支持 HMR。
- **ctx = 服务仓库**：ctx.tools/ctx.llm/ctx.sessions…… 按 key 取服务，不 import 具体实现；inject 声明依赖。
- **配置**：Config 接口 + 同名 Schemastery schema，cordis.yml 传入并校验、填默认值；!!js 表达式可读运行时服务。
- **工具**：defineTool({name, description, parameters, output, execute})，args 自动校验、结果规范化、UI 卡片纯函数投影。
- **发布分层**：bundle patch → profile patch → 全局 patch → --patch 覆盖；后层按行覆盖，config 整块替换。

## 官方参考（deepseek-harness 仓库内）

| 内容 | 路径 |
|---|---|
| 用户插件教程（第一个插件→工具→配置→发布） | docs/user/develop/basic/** |
| 生命周期 / 服务 / 事件 | docs/user/develop/framework/** |
| 三方能力设计（Definition/Provider/Consumer） | docs/user/develop/practice/** |
| Cordis 概念速览 + 7 章教程 | docs/cordis-primer.md、docs/cordis-tutorial/** |
| 服务/事件 API 目录（按子系统生成） | docs/subsystems/** |
| 工具作者参考 | docs/cookbook/adding-a-tool.md |
| 架构说明 | docs/architecture.md、docs/capability-seams.md |

## 相关项目

- [deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) — DSH 本体
- [dsh-web-search-pro](https://github.com/anweat/dsh-web-search-pro) — 增强型网页搜索插件（本指南的实践案例）
- [dsh-voice-webspeech](https://github.com/anweat/dsh-voice-webspeech) — 浏览器语音输入插件（client 插件实践案例）

## License

MIT