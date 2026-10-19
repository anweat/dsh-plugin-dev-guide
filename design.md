# 技术方案 AI 审查工具 —— 设计文档（design.md）

> 版本：V0.2　|　日期：2026-08-17　|　状态：可供开发
> 配套文档：`技术方案AI审查工具-开发需求.md`（需求）、`progress.md`（进度）
> 已产出资产：`rules/capability-open-access-rules.json`（规则包）、`data/seed-solution-parsed.json`（种子方案解析）、`data/ledger/*.json`（台账 mock）

---

## 1. 架构总览

定位：**单机 demo**，外网 API 大模型（配置化，后续切内网地址），全链路「提交 → 解析 → 审查 → 分级意见」，并配套「数据运营」台账视图。

**核心原则：文件即数据库。** 所有数据以本地文件存储，无数据库、无向量库，方便随时人工修改调整，改完立即生效。

```
┌──────────────────── 接入层（Web UI）────────────────────┐
│  方案审查（提交/分级展示） + 数据运营（台账/变更关系）      │
├──────────────────── 服务层（Python FastAPI）────────────┤
│  ① 方案解析器 parser       Markdown → 结构化 JSON        │
│  ② 规则引擎 rule_engine    硬检查，加载 rules/*.json     │
│  ③ 经验检索 retriever      关键词+维度标签，加载经验 MD   │
│  ④ 生成器 generator        LLM 综合，产出分级意见        │
│  ⑤ 编排器 orchestrator     串起 ①→②→③→④                 │
│  ⑥ 台账数据层 ledger_store 读台账文件，聚合方案↔微服务关系│
├──────────────────── 文件数据层 ─────────────────────────┤
│  rules/*.json（规则）+ knowledge/*.md（经验）+           │
│  data/ledger/*.json（台账）+ data/metrics/*.json（运行时）│
├──────────────────── 模型层 ─────────────────────────────┤
│  LLM 客户端（OpenAI 兼容，base_url/api_key/model 可配）  │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 技术栈选型（轻量化、单机）

| 层 | 选型 | 理由 |
|---|---|---|
| 后端 | Python 3.11+ / FastAPI | LLM 生态成熟、轻量 |
| 前端 | 单页 HTML + 原生 JS | 零构建、轻量 |
| 数据存储 | 本地文件（JSON / Markdown） | 可随时人工改、无运维、改完即生效 |
| 经验检索 | 关键词 + 维度标签匹配 | 不依赖 embedding，可解释、零额外依赖 |
| LLM 调用 | OpenAI 兼容 SDK（openai 库） | 兼容外网 API 与内网 DeepSeek/Qwen 端点 |

> 已移除 V0.1 的 chromadb / embedding 方案：向量库与「随时人工修改文件」的诉求冲突（改文件需重新向量化），且对中文审查场景关键词+标签检索已够用。

---

## 3. 模块设计

### 3.1 方案解析器（parser）

输入：Markdown 文本。输出：符合 `data/seed-solution-parsed.json` 结构的方案对象。

- **规则解析**（确定性）：章节切分、Markdown 表格、Mermaid 代码块、资源变更表、接口信息提取。
- **LLM 兜底抽取**（非确定性）：结构不规整时按方案 schema 抽取。

### 3.2 规则引擎（rule_engine）

加载 `rules/*.json`，按 `check_method` 分流：`rule` 走程序化硬检查（零 token），`llm`/`rule+llm`/`llm+data` 交给生成器判定。

### 3.3 经验检索（retriever）

- **存储**：审查经验以 Markdown 存于 `knowledge/`，按「场景/维度」分目录（如 `knowledge/capacity/限流经验.md`）。
- **检索**：规则引擎命中哪些维度 → 加载对应维度的经验文件 → 与方案全文一起注入生成器。
- **不用 embedding**：文件改了立即生效，检索逻辑可解释、可人工调整。

### 3.4 生成器（generator）

输入：方案对象 + 规则命中 + 相关经验 +（可选）运行时数据。输出：分级意见 JSON。

### 3.5 编排器（orchestrator）

串行管线：`parse → rule_check → retrieve → generate → 组装分级意见`。

### 3.6 台账数据层（ledger_store）

- 读 `data/ledger/services.json`（微服务台账）+ `data/ledger/solutions.json`（技术方案 + 变更记录）。
- **实时聚合**「方案 ↔ 微服务」双向关系，不冗余存储：方案→微服务来自 `changes`，微服务→方案反向聚合。
- 提供统计卡片、微服务台账（含变更历史）、方案变更列表三类数据。

### 3.7 评测器（evaluator）—— 质量度量与迭代闭环

**目的**：用准确率 / 召回率量化 AI 审查质量，驱动规则包与经验库持续迭代。四阶段闭环：

```
评测集建设 → 自动评测 → 指标报告 → 反馈迭代 ──(回到评测集)──→
```

1. **评测集建设**：历史方案 + 专家标注的「标准问题清单」（黄金标准）。来源为历史评审意见（真实专家审出，天然是标准答案），映射到 rule_id / dimension。
2. **自动评测**：对评测集每份方案跑 AI 审查，输出检出问题列表，与标准清单对齐比对。
3. **指标报告**：按维度算 precision / recall / F1，输出漏检（FN）、误报（FP）明细。
4. **反馈迭代**：漏检 → 补规则 / 经验；误报 → 收紧规则触发条件；重新评测对比指标变化。

**对齐粒度（第一版）**：以 `rule_id` 为对齐单位（AI 检出与标注都映射到 rule_id 再比对）。可完全自动化、结果稳健；问题条目级语义对齐留作进阶。

---

## 4. 模型调用配置（可配置化）

采用 `config.yaml` + 环境变量。当前默认 DeepSeek（外网），后续改内网只需改 `base_url` / `model`。

```yaml
llm:
  base_url: "https://api.deepseek.com"   # 内网改 http://10.x.x.x:8000/v1
  api_key: "${LLM_API_KEY}"
  model: "deepseek-v4-flash"             # 推理型模型，支持 json_mode
  temperature: 0.1
  timeout: 120
  max_tokens: 8192                        # 审查 JSON 较长，需足够上限

server:
  host: "127.0.0.1"
  port: 8000
```

要点：所有模型访问走统一 `LLMClient`（OpenAI 兼容），业务代码不感知厂商。

---

## 5. 数据模型

### 5.1 规则包 schema（rules/*.json）

`rule_pack` → `dimensions` + `checks[]`。check 关键字段：`id / dimension / name / priority / severity / question / description / evidence_location / check_method / data_dependency / pass_criteria / fail_criteria / suggestion_template / source_examples / tags`。

### 5.2 方案 schema（data/seed-solution-parsed.json）

`meta / resource_changes / background / technical_approach / interfaces / data_planning / implementation_plan / launch_target / resource_assessment / risk_assessment / attachments`。

### 5.3 意见 schema（输出）

`overall_verdict / summary_points[] / issues[]`。issue：`rule_id / dimension / severity(blocker|major|minor) / title / description / evidence[] / suggestion / source(rule|llm|human) / status`。

### 5.4 台账 schema（data/ledger/*.json）

**services.json**（微服务台账，全量清单）：

```json
{ "schema_version": "1.0", "services": [
  { "id": "svc-001", "name": "emss-uia-channel-front", "display_name": "渠道前端",
    "system": "网上国网", "network_position": "外网", "type": "微服务",
    "owner": "营销服务部", "description": "...", "created_at": "2023-05-01", "tags": ["渠道"] }
] }
```

**solutions.json**（技术方案 + 变更记录）：

```json
{ "schema_version": "1.0", "solutions": [
  { "id": "sol-001", "title": "...", "scenario": "capability-open-access",
    "scenario_name": "能力开放/三方接入", "submitted_at": "2026-08-01",
    "status": "已上线", "verdict": "建议整改",
    "changes": [ { "service_id": "svc-001", "service_name": "emss-uia-channel-front", "change_type": "修改" } ] }
] }
```

### 5.5 评测 schema（data/eval/*.json）

**评测集 golden_set.json**：

```json
{ "schema_version": "1.0", "golden_set": [
  { "id": "gs-001", "solution_md": "方案 Markdown 全文",
    "ground_truth": [
      { "rule_id": "CAP-001", "dimension": "capacity", "severity": "blocker", "desc": "缺少限流策略" },
      { "rule_id": "SEC-001", "dimension": "security", "severity": "blocker", "desc": "缺少加密策略" }
    ] }
] }
```

**评测结果 eval_result.json**：

```json
{ "run_at": "2026-08-17", "metrics": {
    "overall": { "precision": 0.72, "recall": 0.65, "f1": 0.68, "weighted_recall": 0.71 },
    "by_dimension": { "capacity": { "tp": 8, "fp": 2, "fn": 3, "precision": 0.8, "recall": 0.73, "f1": 0.76 } }
  },
  "false_negatives": [ { "solution_id": "gs-001", "rule_id": "CAP-001", "dimension": "capacity", "severity": "blocker", "desc": "缺少限流策略" } ],
  "false_positives": [ { "solution_id": "gs-002", "rule_id": "INT-005", "dimension": "interface", "desc": "AI 误报的幂等问题" } ]
}
```

- `tp/fp/fn` 以 rule_id 为对齐单位统计。
- `weighted_recall`：按严重级别加权（blocker=3 / major=2 / minor=1），突出「漏检高风险问题」的代价。

---

## 6. 目录结构

```
project/
├── config.yaml                      # 模型/服务配置（可改调用地址）
├── design.md / progress.md / 需求文档
├── rules/                           # 审查规则包（JSON）
├── knowledge/                       # 审查经验（Markdown，按维度分目录）
├── data/
│   ├── seed-solution-parsed.json    # 种子方案解析 fixture
│   ├── seed-solution.md             # 种子方案 Markdown
│   ├── ledger/                      # 台账（services.json / solutions.json）
│   ├── eval/                        # 评测集（golden_set.json）+ 评测结果
│   └── metrics/                     # 运行时数据（p95/p99/流量，待接入）
├── src/
│   ├── app.py                       # FastAPI 入口 + 台账/评测 API
│   ├── config.py / llm_client.py / ledger_store.py
│   ├── parser/markdown_parser.py
│   └── reviewer/{rule_engine,generator,orchestrator,evaluator}.py
├── web/index.html                   # 单页（方案审查 Tab + 数据运营 Tab）
└── scripts/run_demo.py              # 端到端演示
```

---

## 7. 开发任务状态

| # | 任务 | 状态 |
|---|---|---|
| 1 | 脚手架：FastAPI + config + LLMClient | ✅ 完成 |
| 2 | 方案解析器：Markdown→结构化 JSON | ✅ 完成 |
| 3 | 规则引擎：rules JSON 硬检查 | ✅ 完成 |
| 4 | 经验检索：关键词+维度标签加载经验 MD | ⬜ 待真实经验数据 |
| 5 | 生成器：LLM 综合生成分级意见 | ✅ 完成 |
| 6 | 编排器：串起全管线 | ✅ 完成 |
| 7 | Web UI：方案审查 Tab | ✅ 完成 |
| 8 | 台账数据层 + 数据运营 UI（mock） | ✅ 完成 |
| 9 | 意见库入库脚本（经验 MD 落盘） | ⬜ 待数据 |
| 10 | 评测集 schema + 构建脚本（历史意见→golden set） | ✅ 完成（parse_review_pdf.py + golden_set.json） |
| 11 | 评测执行器：跑审查 + 与标准清单对齐 | ✅ 完成（evaluator.py） |
| 12 | 指标计算器：precision/recall/F1 + 加权召回 | ✅ 完成（evaluator.py） |
| 13 | 评测报告生成 + UI 展示（漏检/误报明细） | ⬜ 报告 JSON 已有，UI 待做 |
| 14 | 反馈迭代闭环：评测→分析→优化规则→重评 | ⬜ 待真实方案原文 |

---

## 8. 关键设计决策记录

| 决策 | 结论 | 原因 |
|---|---|---|
| 部署 | 单机 demo，外网 API 先行 | 快速验证，配置化便于切内网 |
| 模型 | OpenAI 兼容协议封装 | 一套代码兼容外网/内网 |
| 时序图 | 新方案 Mermaid，历史图片离线逆向 | 轻量化 |
| 审查方式 | 规则硬检查 + 经验检索 + LLM 三层 | 规则兜底，经验提供案例，LLM 语义 |
| 数据存储 | 文件即数据库（JSON + MD），无向量库 | 随时人工改、改完即生效、零运维 |
| 经验检索 | 关键词 + 维度标签，不用 embedding | 可解释、文件改了立即生效 |
| 数据管理 | 对话模式（AI 直接改文件），零额外开发 | 自然语言最顺手 |
| 数据展示 | UI 模式（台账 + 变更关系） | 图表表格对话给不了 |
| 台账关系 | 方案↔微服务 实时聚合，不冗余存储 | 单一数据源，避免不同步 |
| 评测对齐 | rule_id 维度对齐（第一版） | 可自动化、结果稳健；问题条目级语义对齐留作进阶 |
| 评测指标 | 召回率优先 + blocker 加权（3/2/1） | 漏检比误报更危险，突出高风险问题代价 |
| 评测集来源 | 历史评审意见作为黄金标准 | 真实专家审出，天然标准答案，无需重新标注 |
| 迭代闭环 | 评测→漏检补规则→误报收紧→重评 | 用指标驱动知识库持续优化 |
