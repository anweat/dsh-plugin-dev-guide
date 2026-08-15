# DSH 插件索引（by anweat）

> 由 [dsh-plugin-dev-guide](https://github.com/anweat/dsh-plugin-dev-guide) 维护的插件集合索引。
> 所有插件遵循官方发现机制：仓库均打 `dsh-plugin` topic（[GitHub topic 页](https://github.com/topics/dsh-plugin)），可从 npm 直接安装。

## 插件列表

| 包 | 版本 | 类型 | 说明 | 安装 |
|---|---|---|---|---|
| [dsh-web-search-pro](https://github.com/anweat/dsh-web-search-pro) | 0.1.2 | Host | 增强型、可持久化的网页搜索：多引擎路由（DeepSeek/Exa/DDG/Bing/Jina + GitHub/B站/YouTube/V2EX/小红书/Twitter/Reddit/RSS）、SQLite+LRU 缓存、userscript 风格抽取、Playwright 渲染 | `dsh plugin --profile web add dsh-web-search-pro` |
| [dsh-voice-webspeech](https://github.com/anweat/dsh-voice-webspeech) | 0.1.0 | Host+Client | 浏览器 Web Speech API 语音输入：零服务端、零密钥、零模型下载（Edge=Azure 语音、Chrome=Google 语音） | `dsh plugin --profile web add dsh-voice-webspeech` |
| [dsh-browser](https://github.com/anweat/dsh-browser) | 0.1.3 | Host | 自包含浏览器运行时：插件本地打包 Playwright(chromium)+OpenCLI（全局复用回退），提供 `browser` 服务 + 9 个交互式浏览器工具 | `dsh plugin --profile web add @anweat/dsh-browser` |
| [dsh-restart](https://github.com/anweat/dsh-restart) | 0.1.0 | Host+Client | 重启 DSH：可配置重启方式（Node 原生/旧 PowerShell 适配）、重启后自动继续提示词、可选看门狗自动拉起 | `dsh plugin --profile web add dsh-restart` |
| [dsh-assistant-message-forge](https://github.com/anweat/dsh-assistant-message-forge) | 0.1.0 | Host+Client | 消息锻造台：创建/修改/注入测试用 assistant 消息，导入识别 session.jsonl(.zstd) 会话日志 | `dsh plugin --profile web add dsh-assistant-message-forge` |

## 设计要点

- **发布流水线全自动**：推 `v*` tag → CI 构建/校验 → npm publish（sigstore provenance）→ GitHub Release（详见 [publishing.md](./publishing.md) §3.5）
- **名字占用**：无 scope 包名可能被他人注册，改用 `@<账号>/<包名>`（scoped 永不冲突）
- **依赖关系**：dsh-web-search-pro 的浏览器类能力依赖 dsh-browser 提供 `browser` 服务（Cordis `inject` 自动排序）

## 新增插件流程

1. 按 [plugin-development.md](./plugin-development.md) 开发（bundle 规范 + `prepare` + `repository` 字段）
2. 复制 `.github/workflows/publish.yml`（[模板](https://github.com/anweat/dsh-web-search-pro/blob/master/.github/workflows/publish.yml)）
3. 仓库打 `dsh-plugin` topic（官方收录机制）
4. 推 `v*` tag 自动发布，然后在本页补一行