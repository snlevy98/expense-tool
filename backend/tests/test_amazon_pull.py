"""
Tests for POST /amazon/pull-and-import (the scraper trigger endpoint).

These don't need a database: every path exercised here fails (or validates)
before touching the DB, so `db=None` is safe when calling the handler directly.
Required settings env vars are stubbed so importing the app doesn't blow up on a
machine without a real .env.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

import pytest

from app.routers import amazon


class _FakeProc:
    """Stand-in for an asyncio subprocess that exits non-zero."""

    def __init__(self, returncode=1, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        pass

    async def wait(self):
        return self.returncode


async def test_pull_cleans_temp_file_when_scraper_fails(monkeypatch):
    """A failing scraper must still leave no temp CSV behind (finally cleanup)."""
    captured = {}

    async def fake_exec(*cmd, stdout=None, stderr=None):
        # The endpoint passes "--output <tmp>"; grab the path it created.
        captured["path"] = cmd[cmd.index("--output") + 1]
        assert os.path.exists(captured["path"])  # NamedTemporaryFile created it
        return _FakeProc(returncode=1, stderr=b"boom: invalid --months value")

    monkeypatch.setattr(amazon.asyncio, "create_subprocess_exec", fake_exec)

    body = amazon.PullAndImportRequest(months=3)
    with pytest.raises(amazon.HTTPException) as exc_info:
        await amazon.pull_and_import(body, db=None, auth={})

    assert exc_info.value.status_code == 502
    assert "boom" in exc_info.value.detail
    assert captured["path"]
    assert not os.path.exists(captured["path"]), "temp file was not cleaned up"


async def test_pull_rejects_months_and_year_together():
    body = amazon.PullAndImportRequest(months=3, year=2025)
    with pytest.raises(amazon.HTTPException) as exc_info:
        await amazon.pull_and_import(body, db=None, auth={})
    assert exc_info.value.status_code == 400


def test_pull_requires_auth():
    """Unauthenticated requests must be rejected before reaching the handler."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/amazon/pull-and-import", json={"months": 3})
    # HTTPBearer rejects a missing token with 403; an invalid one yields 401.
    # Either way the request never reaches the scraper.
    assert resp.status_code in (401, 403)
