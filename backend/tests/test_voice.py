"""Voice (STT) endpoint test.

faster-whisper is an optional dependency and not present in this environment, so
the endpoint must fail gracefully with a clear install message rather than crash.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_voice_test.db",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_transcribe_graceful_without_whisper() -> None:
    with TestClient(app) as client:
        resp = client.post(
            "/api/transcribe",
            files={"file": ("clip.webm", b"not-real-audio", "audio/webm")},
        )
        assert resp.status_code == 503
        assert "not installed" in resp.json()["detail"].lower()
    print("VOICE OK")


if __name__ == "__main__":
    test_transcribe_graceful_without_whisper()
