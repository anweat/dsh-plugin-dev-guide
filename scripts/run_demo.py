"""端到端演示脚本。

用法：
  python scripts/run_demo.py            # 完整审查（含 LLM，消耗 token）
  python scripts/run_demo.py --skip-llm # 只跑解析 + 规则硬检查（零 token）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import get_paths, load_config  # noqa: E402
from src.parser.markdown_parser import parse_solution  # noqa: E402
from src.reviewer.rule_engine import RuleEngine  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-llm", action="store_true", help="跳过 LLM 调用，只跑零 token 部分")
    args = parser.parse_args()

    cfg = load_config()
    md = (ROOT / "data" / "seed-solution.md").read_text(encoding="utf-8")

    # 步骤 1：零 token 验证
    parsed = parse_solution(md)
    print("=" * 60)
    print("【解析结果】")
    print(f"  标题: {parsed['meta']['title']}")
    print(f"  章节数: {len(parsed['sections'])}")
    print(f"  表格数: {len(parsed['tables'])}")
    print(f"  Mermaid 块: {len(parsed['mermaid'])}")
    print(f"  资源变更表: {'已识别' if parsed['resource_changes'] else '未识别'}")
    print(f"  接口数: {len(parsed['interfaces'])}")

    paths = get_paths(cfg)
    engine = RuleEngine(paths["rules"] + "/capability-open-access-rules.json")
    hard_hits = engine.hard_check(md)
    print("=" * 60)
    print(f"【规则硬检查】（零 token，命中 {len(hard_hits)} 条）")
    for h in hard_hits:
        print(f"  [{h['severity']:>7}] {h['rule_id']} {h['name']}")

    if args.skip_llm:
        return

    # 步骤 2：完整审查（调 LLM）
    from src.reviewer.orchestrator import Orchestrator  # noqa: E402
    print("=" * 60)
    print("【LLM 综合审查】调用中...")
    orch = Orchestrator(cfg)
    result = orch.review(md)
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
