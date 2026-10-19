"""台账数据层（文件即数据库）。

本地文件是唯一数据源：data/ledger/services.json（微服务台账）、
data/ledger/solutions.json（技术方案 + 各自的变更记录）。
「方案 ↔ 微服务」双向关系由 solutions.json 的 changes 实时聚合，不冗余存储。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import ROOT_DIR

LEDGER_DIR = ROOT_DIR / "data" / "ledger"


def _read(name: str) -> Any:
    with open(LEDGER_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def load_services() -> list[dict]:
    return _read("services.json")["services"]


def load_solutions() -> list[dict]:
    return _read("solutions.json")["solutions"]


def _service_map() -> dict[str, dict]:
    return {s["id"]: s for s in load_services()}


def build_service_ledger() -> list[dict]:
    """微服务台账，附加从方案聚合的变更历史与统计。"""
    services = load_services()
    solutions = load_solutions()
    for svc in services:
        history: list[dict] = []
        for sol in solutions:
            for ch in sol["changes"]:
                if ch["service_id"] == svc["id"]:
                    history.append({
                        "solution_id": sol["id"],
                        "solution_title": sol["title"],
                        "change_type": ch["change_type"],
                        "submitted_at": sol["submitted_at"],
                        "status": sol["status"],
                        "verdict": sol["verdict"],
                    })
        history.sort(key=lambda x: x["submitted_at"], reverse=True)
        svc["change_count"] = len(history)
        svc["last_change_at"] = history[0]["submitted_at"] if history else None
        svc["history"] = history
    return services


def build_solution_ledger() -> list[dict]:
    """技术方案列表，附加变更微服务的展示信息。"""
    solutions = load_solutions()
    smap = _service_map()
    for sol in solutions:
        sol["change_count"] = len(sol["changes"])
        for ch in sol["changes"]:
            svc = smap.get(ch["service_id"], {})
            ch["service_display_name"] = svc.get("display_name", "")
            ch["network_position"] = svc.get("network_position", "")
    return solutions


def get_stats() -> dict:
    """统计卡片数据。"""
    services = load_services()
    solutions = load_solutions()
    total_changes = sum(len(s["changes"]) for s in solutions)
    changed_ids: set[str] = set()
    for s in solutions:
        for ch in s["changes"]:
            changed_ids.add(ch["service_id"])
    return {
        "service_count": len(services),
        "solution_count": len(solutions),
        "change_count": total_changes,
        "changed_service_count": len(changed_ids),
    }
