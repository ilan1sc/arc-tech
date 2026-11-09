"""Versioned JSON persistence (no DB). data/store/<kind>/<id>/v<N>.json"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "store"
T = TypeVar("T", bound=BaseModel)


def _dir(kind: str, obj_id: str) -> Path:
    d = STORE / kind / obj_id.replace("/", "_")
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(kind: str, obj_id: str, obj: BaseModel, version: int | None = None) -> Path:
    d = _dir(kind, obj_id)
    name = f"v{version}.json" if version is not None else "latest.json"
    p = d / name
    p.write_text(obj.model_dump_json(indent=2))
    return p


def load(kind: str, obj_id: str, model: type[T], version: int | None = None) -> T | None:
    d = STORE / kind / obj_id.replace("/", "_")
    if not d.exists():
        return None
    if version is None:
        files = sorted(d.glob("v*.json"), key=lambda p: int(p.stem[1:]))
        p = files[-1] if files else d / "latest.json"
    else:
        p = d / f"v{version}.json"
    return model.model_validate_json(p.read_text()) if p.exists() else None


def versions(kind: str, obj_id: str) -> list[int]:
    d = STORE / kind / obj_id.replace("/", "_")
    return sorted(int(p.stem[1:]) for p in d.glob("v*.json")) if d.exists() else []


def list_ids(kind: str) -> list[str]:
    d = STORE / kind
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


def save_raw(name: str, data) -> Path:
    p = STORE / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, default=str))
    return p


def load_raw(name: str, default=None):
    p = STORE / name
    return json.loads(p.read_text()) if p.exists() else default
