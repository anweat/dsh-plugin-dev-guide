"""评测演示脚本。

用法：
  python scripts/run_eval.py             # mock AI 输出跑评测（零 token，验证指标计算）
  python scripts/run_eval.py --use-llm   # 真实 LLM 审查跑评测（消耗 token）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.reviewer.evaluator import Evaluator, load_golden_set  # noqa: E402

# mock AI 输出（模拟审查检出结果，故意含 TP/FP/FN，用于验证指标计算）
MOCK_AI = {
    "gs-001": [{"rule_id": "INT-001"}, {"rule_id": "DOC-001"}, {"rule_id": "SEC-001"}],  # 多报 SEC-001
    "gs-002": [{"rule_id": "CAP-001"}],  # 漏报 INT-002
    "gs-003": [{"rule_id": "INT-002"}, {"rule_id": "INT-001"}],  # 多报 INT-001
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-llm", action="store_true", help="用真实 LLM 审查（消耗 token）")
    args = parser.parse_args()

    golden = load_golden_set()
    ev = Evaluator()

    if args.use_llm:
        from src.config import load_config  # noqa: E402
        from src.reviewer.orchestrator import Orchestrator  # noqa: E402
        cfg = load_config()
        ev.orchestrator = Orchestrator(cfg)
        result = ev.run(golden, use_llm=True)
    else:
        result = ev.run(golden, use_llm=False, mock_ai=MOCK_AI)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
