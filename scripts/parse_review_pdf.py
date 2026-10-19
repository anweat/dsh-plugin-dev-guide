"""技术审核意见单解析脚本（评测集构建的核心）。

将 PDF 意见单解析为结构化记录，统计结论分布与审查维度覆盖度，
验证「历史意见 → 黄金标准」的映射可行性。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PDF_PATH = Path(r"C:\Users\zhito\Documents\SGCCIGW_data\Profiles\6A516234AFD76AAFB2B783E69B6204A6\Cache\chat\file\202608\技术审核意见单（8月3日-7日）.pdf")

# 审查维度关键词映射（与规则包 8 维度对齐）
DIM_KEYWORDS = {
    "容量与性能": ["业务量", "增长量", "预估", "并发", "压测", "扩容", "性能", "数据量"],
    "安全与合规": ["加密", "防护", "风控", "合规", "安全", "鉴权", "授权", "脱敏"],
    "接口与边界": ["接口", "文档", "参数", "返回", "边界", "异常", "重试", "幂等", "入参", "传输数据"],
    "渠道管控": ["渠道"],
    "数据同步": ["同步", "异步", "推送逻辑", "数据推送"],
    "可配置化": ["配置", "定时任务", "执行规则"],
    "埋点监控": ["埋点", "监控", "日志"],
    "文档完整性": ["时序图", "链路图", "技术描述", "改造逻辑", "原因", "展示规则", "提示语", "判断逻辑"],
}


def classify(opinion: str) -> str:
    if "不通过" in opinion:
        return "不通过"
    if "建议整改" in opinion:
        return "建议整改"
    return "通过"


def split_points(opinion: str) -> list[str]:
    """拆出意见正文里的 (1)(2)(3)... 各条。"""
    body = re.sub(r"^意见[：:]?", "", opinion).strip()
    points = re.findall(r"[(（]\d+[)）](.*?)(?=[(（]\d+[)）]|$)", body, flags=re.DOTALL)
    return [p.strip().replace("\n", "") for p in points if p.strip()]


def parse_pdf(path: Path) -> list[dict]:
    records: list[dict] = []
    pdf = pdfplumber.open(str(path))
    for page in pdf.pages:
        text = page.extract_text() or ""
        m = re.search(r"方案编号[：:]\s*(\S+)", text)
        pno = m.group(1) if m else ""
        tables = page.extract_tables()
        if not tables:
            continue
        d: dict[str, str] = {}
        for row in tables[0]:
            if row and len(row) >= 2:
                d[(row[0] or "").strip()] = (row[1] or "").strip()
        records.append({
            "solution_id": pno,
            "title": d.get("议题名称", "").replace("\n", ""),
            "review_form": d.get("审核形式", ""),
            "product_line": d.get("需求产品线", ""),
            "biz_type": d.get("归属业务类", ""),
            "opinion": d.get("审核意见", ""),
            "verdict": classify(d.get("审核意见", "")),
            "points": split_points(d.get("审核意见", "")),
        })
    pdf.close()
    return records


def main() -> None:
    records = parse_pdf(PDF_PATH)
    print(f"总方案数: {len(records)}")

    verdicts = Counter(r["verdict"] for r in records)
    print(f"结论分布: {dict(verdicts)}")

    # 只统计整改/不通过的方案，分析维度覆盖
    dim_counter: Counter = Counter()
    for r in records:
        if r["verdict"] == "通过":
            continue
        op = r["opinion"]
        for dim, kws in DIM_KEYWORDS.items():
            if any(k in op for k in kws):
                dim_counter[dim] += 1

    print("\n整改/不通过方案（{} 个）的维度分布:".format(sum(1 for r in records if r["verdict"] != "通过")))
    for dim, cnt in dim_counter.most_common():
        print(f"  {dim}: {cnt}")

    # 输出结构化记录（供评测集建设）
    out = ROOT / "data" / "eval" / "review_records.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已输出结构化记录到: {out}")


if __name__ == "__main__":
    main()
