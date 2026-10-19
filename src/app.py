"""FastAPI 入口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ledger_store
from .config import ROOT_DIR, load_config
from .reviewer.evaluator import MOCK_AI, Evaluator, load_golden_set
from .reviewer.orchestrator import Orchestrator
from .reviewer.retriever import list_experiences

app = FastAPI(title="技术方案 AI 审查工具", version="0.1.0")
app.mount("/data", StaticFiles(directory=str(ROOT_DIR / "data")), name="data")

cfg = load_config()
orchestrator = Orchestrator(cfg)


class ReviewRequest(BaseModel):
    markdown: str


@app.get("/health")
def health():
    return {"status": "ok", "model": cfg["llm"]["model"]}


@app.get("/", response_class=HTMLResponse)
def index():
    html = (ROOT_DIR / "web" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.post("/api/review")
def review(req: ReviewRequest):
    if not req.markdown.strip():
        return {"error": "方案内容为空"}
    return orchestrator.review(req.markdown)


# ---------- 数据运营 / 台账 ----------

@app.get("/api/ledger/stats")
def ledger_stats():
    return ledger_store.get_stats()


@app.get("/api/ledger/services")
def ledger_services():
    return ledger_store.build_service_ledger()


@app.get("/api/ledger/solutions")
def ledger_solutions():
    return ledger_store.build_solution_ledger()


# ---------- 评测 ----------

@app.get("/api/eval/run")
def eval_run():
    golden = load_golden_set()
    ev = Evaluator()
    return ev.run(golden, use_llm=False, mock_ai=MOCK_AI)


# ---------- 审查经验库 ----------

@app.get("/api/knowledge/experiences")
def knowledge_experiences():
    return list_experiences()
