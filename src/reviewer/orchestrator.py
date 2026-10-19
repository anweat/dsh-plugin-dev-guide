"""审查编排器：串起 解析 → 规则硬检查 → LLM 综合 → 组装分级意见。"""
from __future__ import annotations

import json
from typing import Any

from ..config import get_paths
from ..llm_client import LLMClient
from ..parser.markdown_parser import parse_solution
from .generator import Generator
from .retriever import load_experience
from .rule_engine import RuleEngine


class Orchestrator:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        paths = get_paths(cfg)
        llm_cfg = cfg.get("llm", {})
        self.llm = LLMClient(
            base_url=llm_cfg["base_url"],
            api_key=llm_cfg["api_key"],
            model=llm_cfg["model"],
            temperature=llm_cfg.get("temperature", 0.1),
            timeout=llm_cfg.get("timeout", 120),
            max_tokens=llm_cfg.get("max_tokens", 4096),
        )
        rules_file = paths["rules"] + "/capability-open-access-rules.json"
        self.rule_engine = RuleEngine(rules_file)
        self.generator = Generator(self.llm)

    def review(self, md_text: str) -> dict[str, Any]:
        """对一份方案 Markdown 执行完整审查，返回分级意见。"""
        parsed = parse_solution(md_text)
        hard_hits = self.rule_engine.hard_check(md_text)
        rules_slim = self.rule_engine.all_rules_for_prompt()
        # 经验注入：加载硬检查命中维度的审查经验，供 LLM 参考
        relevant_dims = sorted({h["dimension"] for h in hard_hits if h.get("dimension")})
        experience = load_experience(relevant_dims) if relevant_dims else ""
        llm_opinion = self.generator.generate(md_text, rules_slim, hard_hits, experience)

        # 合并：硬检查结果 + LLM 意见
        merged = self._merge(hard_hits, llm_opinion)
        merged["meta"] = {
            "title": parsed["meta"]["title"],
            "char_count": parsed.get("char_count", len(md_text)),
            "has_mermaid": parsed["meta"]["has_mermaid"],
            "rule_pack": self.rule_engine.rule_pack["rule_pack"]["name"],
        }
        return merged

    def _merge(self, hard_hits: list[dict], llm_opinion: dict) -> dict:
        """合并硬检查命中的问题与 LLM 意见，去重（按 rule_id）。"""
        issues: list[dict] = []
        seen: set[str] = set()

        # 硬检查结果（确定性，优先）
        for h in hard_hits:
            rid = h["rule_id"]
            if rid not in seen:
                seen.add(rid)
                issues.append({
                    "rule_id": rid,
                    "dimension": h["dimension"],
                    "severity": h["severity"],
                    "title": h["name"],
                    "description": h.get("description", ""),
                    "evidence": h.get("evidence", []),
                    "suggestion": h.get("suggestion", ""),
                    "source": "rule",
                })

        # LLM 意见（语义判断）
        for issue in llm_opinion.get("issues", []):
            rid = issue.get("rule_id", "")
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            issue["source"] = "llm"
            issues.append(issue)

        return {
            "overall_verdict": llm_opinion.get("overall_verdict", "建议整改"),
            "summary_points": llm_opinion.get("summary_points", []),
            "issues": issues,
        }
