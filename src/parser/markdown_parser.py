"""Markdown 技术方案解析器。

将技术方案 Markdown 解析为结构化对象，供规则引擎与 LLM 审查使用。
设计目标：确定性解析（零 token），结构不规整时由 LLM 兜底抽取。
"""
from __future__ import annotations

import re
from typing import Any


def parse_sections(md: str) -> list[dict]:
    """按 Markdown 标题切分章节，返回 [{level, title, content}]。"""
    lines = md.split("\n")
    sections: list[dict] = []
    current: dict | None = None

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            if current is not None:
                sections.append(current)
            current = {
                "level": len(m.group(1)),
                "title": m.group(2).strip(),
                "content": "",
            }
        elif current is not None:
            current["content"] += line + "\n"

    if current is not None:
        sections.append(current)
    return sections


def extract_tables(md: str) -> list[dict]:
    """提取所有 Markdown 表格，返回 [{header: [...], rows: [[...]]}]。"""
    tables: list[dict] = []
    # 表格块：表头行 + 分隔行(---) + 数据行
    lines = md.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < n and re.match(r"^\|?[\s:|-]+\|?$", lines[i + 1].strip()):
            header = _split_row(line)
            rows: list[list[str]] = []
            j = i + 2
            while j < n and lines[j].strip().startswith("|"):
                rows.append(_split_row(lines[j]))
                j += 1
            tables.append({"header": header, "rows": rows})
            i = j
        else:
            i += 1
    return tables


def _split_row(line: str) -> list[str]:
    """拆分表格行，去掉首尾 | 与空单元格两侧空格。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def extract_mermaid(md: str) -> list[str]:
    """提取所有 Mermaid 代码块内容。"""
    return re.findall(r"```mermaid\s*\n(.*?)```", md, flags=re.DOTALL)


def extract_resource_changes(md: str) -> dict | None:
    """识别资源变更表（表头含「资源名称」「变更类型」等）。返回 {columns, rows}。"""
    for t in extract_tables(md):
        header = "".join(t["header"])
        if "资源名称" in header and ("变更类型" in header or "内外网" in header):
            return {"columns": t["header"], "rows": [dict(zip(t["header"], r)) for r in t["rows"]]}
    return None


def extract_interfaces(md: str) -> list[dict]:
    """提取接口信息（接口名称 / 地址 / 描述等），覆盖表格与行内两种形式。"""
    interfaces: list[dict] = []
    interface_keys = ("接口名称", "接口地址", "接口描述", "调用端", "服务端", "通讯方式")
    # 1. 从键值对表格中提取（如 | 接口地址 | emss-... |）
    for t in extract_tables(md):
        for row in t["rows"]:
            if len(row) >= 2 and row[0] in interface_keys:
                interfaces.append({"keyword": row[0], "value": row[1]})
    # 2. 从行内文本提取（如 请求 URL：/api/xxx）
    for m in re.finditer(r"(请求\s*URL|接口地址)[：:\s]*([^\s|，,。]+)", md):
        interfaces.append({"keyword": m.group(1), "value": m.group(2)})
    return interfaces


def parse_solution(md: str) -> dict[str, Any]:
    """解析技术方案，返回结构化对象。"""
    sections = parse_sections(md)
    return {
        "meta": {
            "title": _guess_title(sections),
            "format": "markdown",
            "has_mermaid": len(extract_mermaid(md)) > 0,
        },
        "sections": sections,
        "tables": extract_tables(md),
        "mermaid": extract_mermaid(md),
        "resource_changes": extract_resource_changes(md),
        "interfaces": extract_interfaces(md),
        "raw_text": md,
        "char_count": len(md),
    }


def _guess_title(sections: list[dict]) -> str:
    """从最高级别标题猜测方案名。"""
    if sections:
        return sections[0]["title"]
    return "未命名方案"
