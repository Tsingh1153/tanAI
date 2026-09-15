#!/usr/bin/env python3
"""Ingest the bundled finance corpus into tanAI as global RAG documents.

Run once while the backend is running:

    cd backend && source .venv/bin/activate
    python ../scripts/seed_corpus.py

Idempotent: files already indexed (matched by filename) are skipped. Seeded
documents are global — available in every chat when "Documents" is enabled — so
they ground the finance personas out of the box.
"""

from __future__ import annotations

from pathlib import Path

import httpx

API = "http://localhost:8000"
CORPUS = Path(__file__).resolve().parent.parent / "backend/corpus/finance"


def main() -> int:
    files = sorted(CORPUS.glob("*.md"))
    if not files:
        print(f"No corpus files found in {CORPUS}")
        return 1

    with httpx.Client(base_url=API, timeout=180, trust_env=False) as client:
        try:
            existing = {d["filename"] for d in client.get("/api/documents").json()}
        except httpx.HTTPError as exc:
            print(f"Could not reach tanAI at {API}. Is the backend running? ({exc})")
            return 1

        seeded = 0
        for path in files:
            if path.name in existing:
                print(f"skip  {path.name} (already indexed)")
                continue
            with path.open("rb") as fh:
                resp = client.post(
                    "/api/documents",
                    files={"file": (path.name, fh, "text/markdown")},
                )
            if resp.status_code == 200 and resp.json().get("status") == "ready":
                print(f"ok    {path.name}")
                seeded += 1
            else:
                print(f"FAIL  {path.name}: {resp.status_code} {resp.text[:200]}")

    print(f"\nSeeded {seeded} document(s). Enable 'Documents' in a chat to use them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
