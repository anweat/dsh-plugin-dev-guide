"""规则引擎：加载审查规则包，做程序化硬检查（零 token）。

check_method == "rule" 的规则走确定性关键词/结构检查；
check_method 含 "llm" 的规则交给 LLM 综合审查（见 generator.py）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# rule 类规则的硬检查关键词：规则 id -> 命中关键词列表
# 语义：方案文本中出现任一关键词，视为该检查项「已覆盖」；否则视为缺失，产出意见。
RULE_KEYWORDS: dict[str, list[str]] = {
    "CAP-002": ["压测", "压力测试", "性能测试", "全链路压测"],
    "INT-004": ["渠道标识", "渠道编号"],
    "MON-001": ["埋点"],
    # 时序图必须文本化（Mermaid），图片形式 AI 读不到，视为缺失
    "DOC-001": ["```mermaid", "sequenceDiagram", "flowchart", "stateDiagram"],
    "DOC-002": ["优化前", "原型对比", "原型"],
}


class RuleEngine:
    def __init__(self, rules_path: str):
        self.rules_path = Path(rules_path)
        with open(self.rules_path, "r", encoding="utf-8") as f:
            self.rule_pack = json.load(f)
        self.checks: list[dict] = self.rule_pack["rule_pack"]["checks"]
        self.dimensions: dict = self.rule_pack["rule_pack"]["dimensions"]

    def get_rule_by_id(self, rule_id: str) -> dict | None:
        for c in self.checks:
            if c["id"] == rule_id:
                return c
        return None

    def hard_check(self, solution_text: str) -> list[dict]:
        """确定性硬检查，返回「未命中」的问题列表（零 token）。"""
        results: list[dict] = []
        for check in self.checks:
            if check.get("check_method") != "rule":
                continue
            keywords = RULE_KEYWORDS.get(check["id"], [])
            if not keywords:
                continue
            hit = any(kw in solution_text for kw in keywords)
            if not hit:
                results.append({
                    "rule_id": check["id"],
                    "dimension": check["dimension"],
                    "name": check["name"],
                    "severity": check.get("severity", "major"),
                    "hit": False,
                    "description": check.get("description", ""),
                    "suggestion": check.get("suggestion_template", ""),
                    "evidence": [],
                    "source": "rule",
                })
        return results

    def llm_candidate_rules(self) -> list[dict]:
        """返回需要 LLM 语义判断的规则（check_method 含 llm）。"""
        return [c for c in self.checks if "llm" in c.get("check_method", "")]

    def all_rules_for_prompt(self) -> list[dict]:
        """返回精简的规则清单，供 LLM prompt 使用（仅保留关键字段）。"""
        slim = []
        for c in self.checks:
            slim.append({
                "id": c["id"],
                "dimension": c.get("dimension_name") or self.dimensions.get(c["dimension"], {}).get("name", c["dimension"]),
                "name": c["name"],
                "severity": c.get("severity", "major"),
                "question": c.get("question", ""),
                "pass_criteria": c.get("pass_criteria", ""),
                "fail_criteria": c.get("fail_criteria", ""),
                "suggestion_template": c.get("suggestion_template", ""),
            })
        return slim
