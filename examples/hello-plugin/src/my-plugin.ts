// 最小 DSH 插件示例：加载日志 + 一个模型可调用的 greet 工具。
// 三种形式中推荐"函数形式"：导出 name（可选）、inject（可选）、apply（必需）。
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'hello-plugin'

// 声明依赖：tools 服务就绪后才执行 apply（可选，注释掉也能加载）
export const inject = ['tools']

export function apply(ctx: Context) {
  console.log('[hello-plugin] plugin loaded!')

  // 注册工具：模型可调用 greet(name) -> 'Hello, <name>!'
  ctx.tools.register(defineTool({
    name: 'greet',
    description: 'Greet someone by name.',
    parameters: {
      name: { type: 'string', required: true, description: 'The name to greet' },
    },
    output: {
      schema: { type: 'string' },
      // 把规范化返回值转成模型可见内容
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      return `Hello, ${args.name}!`
    },
  }))
}
