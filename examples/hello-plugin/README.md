# hello-plugin（示例插件骨架）

最小可用的 DSH 插件：加载时打印日志，并向模型注册一个 `greet` 工具。
新插件开发直接复制本目录，改 `name` / `apply` 内容即可。

## 加载（开发期）

从 deepseek-harness 源码仓库根执行：

```sh
pnpm dsh web --patch /abs/path/to/examples/hello-plugin/cordis.yml
```

打开 http://127.0.0.1:3080，终端应打印 `[hello-plugin] plugin loaded!`；
向 agent 提问 `Use the greet tool to greet Ada.` 可看到工具调用与结果。

## 结构

- `src/my-plugin.ts` — 插件实现（name + inject + apply + defineTool）
- `cordis.yml` — 挂载补丁（`name` 为源码绝对路径；打包分发后改为包名）
