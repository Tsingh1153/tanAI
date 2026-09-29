"""Frozen entry point for the packaged desktop app.

PyInstaller bundles this into a single self-contained executable so the shipped
app needs no Python installed. It just serves the FastAPI app with uvicorn in
this process (no reload, no worker subprocesses).
"""

from __future__ import annotations

import multiprocessing
import os

import uvicorn

from app.main import app


def main() -> None:
    host = os.environ.get("LOCALMIND_HOST", "127.0.0.1")
    port = int(os.environ.get("LOCALMIND_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    # Safe no-op in a single-process server; guards against fork issues if a
    # dependency ever spawns a child in the frozen build.
    multiprocessing.freeze_support()
    main()
