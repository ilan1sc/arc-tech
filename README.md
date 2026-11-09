# arc-tech — Operation SwissLink demo (fictional)

Three independent engines with shared JSON contracts, running on the DGX Spark with local Ollama models.

| Folder | PRD | What it does |
|---|---|---|
| `engine1_explore/` | PRD 1 v0.3 | GitHub + GitLab discovery → bounded inspection at a pinned commit → Software Capability Passport → judge → hard-gate + weighted ranking |
| `engine2_architect/` | PRD 2 v0.3 | SRS → requirements + open questions → capability tree → **one** logical architecture → deterministic validation → Mermaid → controlled revisions with diff |
| `engine3_optimize/` | PRD 3 v0.2 | Orchestrates 1+2, Build/Buy/Reuse per component, hours & money (editable rate), Pareto shortlist, chat iterations |
| `shared/` | — | Pydantic contracts (`schemas.py`, passport = Drive schema + PRD 1 extensions), Ollama client + cache, independent judge, JSON store |
| `app/` | — | Streamlit UI (5 pages) |

## Run
```bash
cd ~/Documents/elbit/arc-tech
./run_app.sh                    # live: Ollama + GitHub/GitLab   → http://spark-516b:8501
ARC_OFFLINE=1 ./run_app.sh      # demo fallback: replay cache only, no LLM, no network
.venv/bin/python -m pytest -q   # acceptance tests (deterministic)
.venv/bin/python explore_all.py 2   # batch Engine 1 over all components (fills cache)
```
Env: `ARC_MODEL` (default `qwen3.6:35b-a3b-q8_0`), `ARC_JUDGE_MODEL`, `ARC_EMBED_MODEL` (`nomic-embed-text`).
GitHub goes through the machine's `gh` login (token never read by the app).

## Five-minute demo
1. **Requirements** — SRS → 40 requirements, open questions (missing numbers, push-service contradiction), capability tree, traceability.
2. **Exploration** — ad-hoc "GPS tracking" matched to the tracking component → passport with evidence status per capability; missing *persistent history* shows as a gap.
3. **Architecture** — one architecture, component detail panel, overlay none / hours / money (same node & edge ids).
4. **Optimizer** — A Balanced / B Max reuse / C Build-heavy; per-component + per-architecture tables; change hourly rate → money changes, hours don't.
5. **Chat** — "Too expensive; maximize reuse" → new iteration with deltas. "Offline only" → Engine 2 v2 + diff, non-compliant candidates flagged.

## Rules enforced
Unknown ≠ 0 · evidence refs must resolve to inspected files (else downgraded) · strong-copyleft excluded with visible reason (SL-DEP-02) ·
no vendor names in components · no schedules/headcount · all versions kept · human architect approves.

Note: Ollama's strict JSON-schema mode crashes on this box with long prompts; we use JSON mode + schema in prompt + Pydantic retries.
