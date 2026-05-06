from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any


RUNS_DIR = Path("runs")
INDEX_FILE = RUNS_DIR / "index.json"


def _now_id() -> str:
    # Sortable id, good enough for local history.
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def _ensure_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _read_index() -> list[dict[str, Any]]:
    _ensure_dirs()
    if not INDEX_FILE.exists():
        return []
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_index(items: list[dict[str, Any]]) -> None:
    _ensure_dirs()
    INDEX_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def save_run(*, result_dict: dict[str, Any], title: str | None = None) -> str:
    """
    Persist a run as JSON without binary payloads.
    Pass in a dict (typically PipelineResult.model_dump()).
    """
    _ensure_dirs()
    run_id = _now_id()
    path = RUNS_DIR / f"{run_id}.json"

    payload = {
        "run_id": run_id,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "title": title or "",
        "result": result_dict,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    index = _read_index()
    index.insert(
        0,
        {
            "run_id": run_id,
            "created_at": payload["created_at"],
            "title": payload["title"],
            "path": str(path.as_posix()),
        },
    )
    # Keep index bounded.
    _write_index(index[:200])
    return run_id


def list_runs() -> list[dict[str, Any]]:
    return _read_index()


def load_run(run_id: str) -> dict[str, Any] | None:
    _ensure_dirs()
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

