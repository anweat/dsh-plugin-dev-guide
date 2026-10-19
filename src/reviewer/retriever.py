"""经验检索器：按维度加载 knowledge/ 下的审查经验 Markdown。

文件即数据库：经验存为 Markdown，随时人工修改，检索时按维度加载对应文件。
"""
from __future__ import annotations

from pathlib import Path

from ..config import ROOT_DIR

KNOWLEDGE_DIR = ROOT_DIR / "knowledge"

# 维度 -> 经验文件名（文件名即维度，人工可增删）
DIM_FILES: dict[str, str] = {
    "capacity": "capacity.md",
    "security": "security.md",
    "interface": "interface.md",
    "channel": "channel.md",
    "data_sync": "data_sync.md",
    "config": "config.md",
    "monitoring": "monitoring.md",
    "documentation": "documentation.md",
}


def load_experience(dimensions: list[str]) -> str:
    """加载指定维度的经验文本，拼接返回。未找到的维度跳过。"""
    texts: list[str] = []
    for dim in dimensions:
        fname = DIM_FILES.get(dim)
        if not fname:
            continue
        p = KNOWLEDGE_DIR / fname
        if p.exists():
            texts.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(texts)


def list_experiences() -> list[dict]:
    """列出全部经验文件及其维度。"""
    result: list[dict] = []
    for dim, fname in DIM_FILES.items():
        p = KNOWLEDGE_DIR / fname
        if p.exists():
            result.append({"dimension": dim, "file": fname, "chars": len(p.read_text(encoding="utf-8"))})
    return result
