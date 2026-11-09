"""Local Ollama client with structured (JSON-schema) output and a disk cache.

Every successful response is cached under data/cache/llm/<hash>.json, so the
demo can replay with ARC_OFFLINE=1 (no LLM, no network).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "cache" / "llm"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("ARC_MODEL", "qwen3.6:35b-a3b-q8_0")
JUDGE_MODEL = os.getenv("ARC_JUDGE_MODEL", MODEL)
EMBED_MODEL = os.getenv("ARC_EMBED_MODEL", "nomic-embed-text")
NUM_CTX = int(os.getenv("ARC_NUM_CTX", "32768"))

T = TypeVar("T", bound=BaseModel)

# Model per role; the UI's model selectors write here (single-presenter demo: process-wide setting).
MODELS: dict[str, str] = {"engine1": MODEL, "engine2": MODEL, "engine3": MODEL, "judge": JUDGE_MODEL}
ROLE_LABELS = {"engine1": "Engine 1 · Exploration", "engine2": "Engine 2 · Architecture",
               "engine3": "Engine 3 · Optimizer", "judge": "Independent judge"}


def model_for(role: str | None) -> str:
    return MODELS.get(role or "", MODEL)


def available_models() -> list[str]:
    try:
        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5).json()
        return sorted(m["name"] for m in tags.get("models", []) if "embed" not in m["name"] and ":cloud" not in m["name"])
    except Exception:  # noqa: BLE001
        return sorted(set(MODELS.values()))


class LLMUnavailable(RuntimeError):
    pass


def offline() -> bool:
    return os.getenv("ARC_OFFLINE", "0") == "1"


def _key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _cache_path(kind: str, key: str) -> Path:
    p = CACHE_DIR / kind
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{key}.json"


def chat_json(system: str, user: str, schema: type[T], *, model: str | None = None,
              temperature: float = 0.2, retries: int = 2, use_cache: bool = True,
              tag: str = "", role: str | None = None) -> T:
    """Ask the model for JSON that validates against `schema` (Pydantic). `role` picks the per-engine model."""
    model = model or model_for(role)
    json_schema = schema.model_json_schema()
    key = _key(model, system, user, json_schema, temperature)
    path = _cache_path("chat", key)
    if use_cache and path.exists():
        return schema.model_validate_json(json.loads(path.read_text())["content"])
    if offline():
        raise LLMUnavailable(f"ARC_OFFLINE=1 and no cached response for {schema.__name__} {tag}")

    # Strict grammar mode (format=<schema>) crashes this Ollama/CUDA build on long prompts, so by default we use
    # JSON mode + schema in the prompt + Pydantic validation with corrective retries. ARC_STRICT_SCHEMA=1 re-enables it.
    strict = os.getenv("ARC_STRICT_SCHEMA", "0") == "1"
    sys_full = system + ("" if strict else "\n\nReturn ONLY a JSON object that validates against this JSON Schema:\n" + json.dumps(json_schema))
    messages = [{"role": "system", "content": sys_full}, {"role": "user", "content": user}]
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        t0 = time.time()
        r = None
        for net_try in range(4):   # Ollama returns 500 while (re)loading a model under memory pressure
            try:
                r = httpx.post(f"{OLLAMA_URL}/api/chat", timeout=1800, json={
                    "model": model, "messages": messages, "stream": False, "think": False, "keep_alive": "60m",
                    "format": json_schema if strict else "json",
                    "options": {"temperature": temperature, "num_ctx": NUM_CTX},
                })
                r.raise_for_status()
                break
            except httpx.HTTPError as e:
                if net_try == 3:
                    body = getattr(getattr(e, "response", None), "text", "")[:300]
                    raise LLMUnavailable(f"Ollama call failed: {e} {body}") from e
                time.sleep(10 * (net_try + 1))
        content = r.json()["message"]["content"]
        try:
            obj = schema.model_validate_json(content)
        except ValidationError as e:
            last_err = e
            messages += [{"role": "assistant", "content": content},
                         {"role": "user", "content": f"That JSON failed validation:\n{e}\nReturn corrected JSON only."}]
            continue
        path.write_text(json.dumps({"model": model, "tag": tag, "schema": schema.__name__,
                                    "seconds": round(time.time() - t0, 1), "content": content}))
        return obj
    raise LLMUnavailable(f"{schema.__name__}: no valid JSON after {retries + 1} attempts: {last_err}")


def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    model = model or EMBED_MODEL
    key = _key(model, texts)
    path = _cache_path("embed", key)
    if path.exists():
        return json.loads(path.read_text())
    if offline():
        raise LLMUnavailable("ARC_OFFLINE=1 and no cached embedding")
    r = httpx.post(f"{OLLAMA_URL}/api/embed", json={"model": model, "input": texts}, timeout=300)
    r.raise_for_status()
    vecs = r.json()["embeddings"]
    path.write_text(json.dumps(vecs))
    return vecs


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


def health() -> dict:
    if offline():
        return {"ok": False, "mode": "offline (cache replay)", "model": MODEL}
    try:
        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5).json()
        names = {m["name"] for m in tags.get("models", [])}
        return {"ok": MODEL in names, "mode": "live", "model": MODEL, "judge": JUDGE_MODEL,
                "embed": EMBED_MODEL, "available": sorted(names)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mode": "unreachable", "error": str(e), "model": MODEL}
