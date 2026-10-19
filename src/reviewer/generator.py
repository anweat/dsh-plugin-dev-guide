"""LLM 综合审查生成器。

将「规则清单 + 硬检查结果 + 方案全文」组织为 prompt，调用 LLM 产出分级审查意见 JSON。
省 token 策略：只传 llm 类规则（rule 类已硬检查），规则只保留关键字段。
"""
from __future__ import annotations

import json
from typing import Any

from ..llm_client import LLMClient

SYSTEM_PROMPT = """你是网上国网技术方案审核专家预审助手。你的任务是根据给定的审查规则清单，审查一份技术方案，输出结构化的预审意见。

要求：
1. 逐条对照审查规则清单，判断方案是否存在问题；只输出「确实存在」的问题，不确定的不要编造。
2. 每条问题必须给出：所属规则ID、维度、严重级别、标题、描述、证据（引用方案原文关键句）、整改建议。
3. 严重级别：blocker(阻塞，对应评审不通过) / major(重要，对应建议整改) / minor(建议)。
4. 最终给整体判定：通过 / 建议整改 / 不通过。
5. 整改建议优先参考规则里的 suggestion_template 改写，贴合方案实际。
6. 严格只输出 JSON，不要输出任何解释文字。

输出 JSON 结构（严格遵守）：
{
  "overall_verdict": "通过|建议整改|不通过",
  "summary_points": ["要点1", "要点2"],
  "issues": [
    {
      "rule_id": "规则ID",
      "dimension": "维度",
      "severity": "blocker|major|minor",
      "title": "问题标题",
      "description": "问题描述",
      "evidence": ["方案原文关键句"],
      "suggestion": "整改建议"
    }
  ]
}
"""


def _build_user_prompt(solution_text: str, rules_slim: list[dict], hard_hits: list[dict],
                       experience: str = "") -> str:
    lines: list[str] = []
    lines.append("## 审查规则清单（仅需逐条判断这些规则）")
    lines.append(json.dumps(rules_slim, ensure_ascii=False, indent=1))
    lines.append("")
    lines.append("## 已通过程序检查发现的问题（这些已确认，请在最终输出中保留，不要重复）")
    lines.append(json.dumps(hard_hits, ensure_ascii=False, indent=1))
    if experience:
        lines.append("")
        lines.append("## 相关审查经验（供参考，帮助判断与措辞）")
        lines.append(experience)
    lines.append("")
    lines.append("## 技术方案全文")
    lines.append(solution_text)
    lines.append("")
    lines.append("请严格按上述 JSON 结构输出审查意见。")
    return "\n".join(lines)


class Generator:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def generate(self, solution_text: str, rules_slim: list[dict],
                 hard_hits: list[dict], experience: str = "") -> dict[str, Any]:
        user_prompt = _build_user_prompt(solution_text, rules_slim, hard_hits, experience)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        resp = self.llm.chat(messages, json_mode=True)
        try:
            opinion = json.loads(resp)
        except json.JSONDecodeError:
            # 兜底：尝试提取 JSON 片段
            import re
            m = re.search(r"\{.*\}", resp, flags=re.DOTALL)
            opinion = json.loads(m.group(0)) if m else {"overall_verdict": "建议整改", "issues": []}
        return opinion
