"""配置加载模块。支持 config.yaml + 环境变量覆盖（LLM_API_KEY 等）。"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_config(path: Path | None = None) -> dict:
    """加载 config.yaml，返回 dict。环境变量可覆盖敏感字段。"""
    cfg_path = path or (ROOT_DIR / "config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # 环境变量覆盖（优先）
    api_key = os.environ.get("LLM_API_KEY")
    if api_key:
        cfg.setdefault("llm", {})["api_key"] = api_key

    base_url = os.environ.get("LLM_BASE_URL")
    if base_url:
        cfg.setdefault("llm", {})["base_url"] = base_url

    model = os.environ.get("LLM_MODEL")
    if model:
        cfg.setdefault("llm", {})["model"] = model

    return cfg


def get_paths(cfg: dict) -> dict:
    """将 paths 中的相对路径解析为绝对路径。"""
    paths = cfg.get("paths", {})
    return {k: str(ROOT_DIR / v) if not Path(v).is_absolute() else v for k, v in paths.items()}
