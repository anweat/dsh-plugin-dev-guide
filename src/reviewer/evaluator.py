"""评测器：量化 AI 审查质量（precision / recall / F1）。

对齐粒度：rule_id（AI 检出与黄金标准都映射到 rule_id 再比对）。
职责：只做「对齐 + 指标计算」，不关心 AI 输出来源（LLM 或 mock）。
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..config import ROOT_DIR

EVAL_DIR = ROOT_DIR / "data" / "eval"

SEVERITY_WEIGHT = {"blocker": 3, "major": 2, "minor": 1}

# 演示用 mock AI 输出（模拟审查检出结果，含 TP/FP/FN，软著演示与评测验证共用）
MOCK_AI: dict[str, list[dict]] = {
    "gs-001": [{"rule_id": "INT-001"}, {"rule_id": "DOC-001"}, {"rule_id": "SEC-001"}],  # 多报 SEC-001
    "gs-002": [{"rule_id": "CAP-001"}],  # 漏报 INT-002
    "gs-003": [{"rule_id": "INT-002"}, {"rule_id": "INT-001"}],  # 多报 INT-001
}


def _rule_dim_map() -> dict[str, str]:
    """从规则包加载 rule_id -> dimension 映射（用于 FP 维度归类）。"""
    with open(ROOT_DIR / "rules" / "capability-open-access-rules.json", "r", encoding="utf-8") as f:
        pack = json.load(f)
    return {c["id"]: c["dimension"] for c in pack["rule_pack"]["checks"]}


def load_golden_set(path: Path | None = None) -> list[dict]:
    p = path or (EVAL_DIR / "golden_set.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)["golden_set"]


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


def align(ai_rule_ids: set[str], gt_issues: list[dict]) -> tuple[set, set, set, list]:
    """对齐单个方案：返回 (tp_ids, fp_ids, fn_issues, fp_issues)。"""
    gt_map = {g["rule_id"]: g for g in gt_issues}
    gt_ids = set(gt_map.keys())
    tp = ai_rule_ids & gt_ids
    fp = ai_rule_ids - gt_ids
    fn = gt_ids - ai_rule_ids
    fn_issues = [gt_map[r] for r in fn]
    fp_issues = [{"rule_id": r} for r in fp]
    return tp, fp, fn_issues, fp_issues


def evaluate(golden_set: list[dict], ai_outputs: dict[str, list[dict]]) -> dict:
    """评测主入口。

    ai_outputs: {solution_id: [ {rule_id, ...}, ... ]}（AI 检出的问题列表）
    """
    # 整体统计
    tp_total = fp_total = fn_total = 0
    # 维度级统计
    dim_stat: dict[str, dict] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    # 加权召回分子/分母
    weighted_hit = weighted_total = 0
    false_negatives: list[dict] = []
    false_positives: list[dict] = []
    rule_dim = _rule_dim_map()

    for item in golden_set:
        sid = item["id"]
        gt = item["ground_truth"]
        ai_issues = ai_outputs.get(sid, [])
        ai_ids = {i["rule_id"] for i in ai_issues if i.get("rule_id")}

        tp, fp, fn_issues, fp_issues = align(ai_ids, gt)

        tp_total += len(tp)
        fp_total += len(fp)
        fn_total += len(fn_issues)

        # 维度级
        for g in gt:
            dim = g.get("dimension", "unknown")
            if g["rule_id"] in tp:
                dim_stat[dim]["tp"] += 1
            elif g["rule_id"] in ai_ids:
                pass
            else:
                dim_stat[dim]["fn"] += 1
        for r in ai_ids:
            if r in fp:
                dim_stat[rule_dim.get(r, "unknown")]["fp"] += 1

        # 加权召回
        for g in gt:
            w = SEVERITY_WEIGHT.get(g.get("severity", "major"), 2)
            weighted_total += w
            if g["rule_id"] in tp:
                weighted_hit += w

        # 明细
        for fn in fn_issues:
            false_negatives.append({"solution_id": sid, **fn})
        for fp in fp_issues:
            false_positives.append({"solution_id": sid, **fp})

    overall = _prf(tp_total, fp_total, fn_total)
    by_dimension = {d: _prf(s["tp"], s["fp"], s["fn"]) for d, s in dim_stat.items()}
    weighted_recall = round(weighted_hit / weighted_total, 3) if weighted_total else 0.0

    return {
        "overall": {**overall, "weighted_recall": weighted_recall},
        "by_dimension": by_dimension,
        "counts": {"tp": tp_total, "fp": fp_total, "fn": fn_total},
        "false_negatives": false_negatives,
        "false_positives": false_positives,
    }


class Evaluator:
    """封装：跑评测（可接 LLM 或 mock 输出）+ 指标计算。"""

    def __init__(self, orchestrator=None):
        self.orchestrator = orchestrator

    def run(self, golden_set: list[dict], use_llm: bool = False,
            mock_ai: dict[str, list[dict]] | None = None) -> dict:
        ai_outputs: dict[str, list[dict]] = {}
        if use_llm:
            assert self.orchestrator is not None, "需传入 orchestrator"
            for item in golden_set:
                opinion = self.orchestrator.review(item["solution_md"])
                ai_outputs[item["id"]] = opinion.get("issues", [])
        elif mock_ai is not None:
            ai_outputs = mock_ai
        else:
            # 无 AI 输出时，全部视为未检出（召回率为 0）
            ai_outputs = {item["id"]: [] for item in golden_set}
        return evaluate(golden_set, ai_outputs)
