import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hash_password import scrypt_hash

SALT = b"0123456789abcdef"
LOGIN = "alice@example.com"
PASSWORD = "correct horse"
VALID_ENV = {
    "AUTH_TOKEN_SECRET": "t" * 64,
    "AUTH_USERS": f"{LOGIN}:{SALT.hex()}:{scrypt_hash(PASSWORD, SALT).hex()}",
}
os.environ.update(VALID_ENV)

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)
DOCX = {"file": ("rapport.docx", b"fake docx", "application/octet-stream")}


@pytest.fixture(autouse=True)
def _reset_login_limit():
    main.LOGIN_ATTEMPTS.clear()


def _auth() -> dict[str, str]:
    token = client.post("/auth/login", json={"username": LOGIN, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _fake_run(returncode: int, seen: list):
    """Stand-in for subprocess.run: LibreOffice writes input.pdf into --outdir."""
    def run(args, **_kwargs):
        outdir = Path(args[args.index("--outdir") + 1])
        seen.append(outdir)
        if returncode == 0:
            (outdir / "input.pdf").write_bytes(b"%PDF-fake")
        return SimpleNamespace(returncode=returncode, stderr="boom /tmp/secret/path")
    return run


@pytest.mark.parametrize("env", [
    {"AUTH_TOKEN_SECRET": main.PLACEHOLDER_SECRET},
    {"AUTH_TOKEN_SECRET": "short"},
    {"AUTH_USERS": ""},
    {"AUTH_USERS": "your.login@example.com:your_sha256_password_hash"},
])
def test_refuses_to_start_with_unsafe_config(env):
    result = subprocess.run(
        [sys.executable, "-c", "import main"],
        env={**os.environ, **VALID_ENV, **env}, capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "AUTH_" in result.stderr


def test_login():
    assert client.post("/auth/login", json={"username": LOGIN, "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"username": "nobody", "password": PASSWORD}).status_code == 401
    assert client.get("/auth/verify", headers=_auth()).status_code == 204


def test_login_is_rate_limited_per_ip():
    good = {"username": LOGIN, "password": PASSWORD}
    for _ in range(main.LOGIN_ATTEMPTS_PER_MINUTE):
        client.post("/auth/login", json={**good, "password": "wrong"}, headers={"X-Real-IP": "1.2.3.4"})
    assert client.post("/auth/login", json=good, headers={"X-Real-IP": "1.2.3.4"}).status_code == 429
    assert client.post("/auth/login", json=good, headers={"X-Real-IP": "5.6.7.8"}).status_code == 200


def test_rejects_missing_forged_and_expired_tokens(monkeypatch):
    forged_payload = main._create_token(LOGIN).split(".")[0]
    monkeypatch.setattr(main, "AUTH_TOKEN_SECRET", main.PLACEHOLDER_SECRET)
    forged = f"{forged_payload}.{main._sign_token(forged_payload)}"
    monkeypatch.undo()
    monkeypatch.setattr(main, "TOKEN_TTL_SECONDS", -10)
    expired = main._create_token(LOGIN)

    assert client.post("/convert", files=DOCX).status_code == 401
    for token in ["garbage", "a.b", "", forged, expired]:
        headers = {"Authorization": f"Bearer {token}"}
        assert client.post("/convert", files=DOCX, headers=headers).status_code == 401
        assert client.get("/auth/verify", headers=headers).status_code == 401


def test_rejects_unsupported_extension():
    files = {"file": ("virus.exe", b"x", "application/octet-stream")}
    assert client.post("/convert", files=files, headers=_auth()).status_code == 400


def test_converts_and_cleans_up(monkeypatch):
    seen = []
    monkeypatch.setattr(main.subprocess, "run", _fake_run(0, seen))
    res = client.post("/convert", files=DOCX, headers=_auth())
    assert res.status_code == 200
    assert res.content == b"%PDF-fake"
    assert "rapport.pdf" in res.headers["content-disposition"]
    assert not seen[0].exists()


def test_failure_is_generic_and_cleans_up(monkeypatch):
    seen = []
    monkeypatch.setattr(main.subprocess, "run", _fake_run(1, seen))
    res = client.post("/convert", files=DOCX, headers=_auth())
    assert res.status_code == 500
    assert "secret" not in res.text
    assert not seen[0].exists()


def test_busy_server_returns_503():
    headers = _auth()
    for _ in range(main.MAX_CONCURRENT_CONVERSIONS):
        main.CONVERT_SLOTS.acquire()
    try:
        assert client.post("/convert", files=DOCX, headers=headers).status_code == 503
    finally:
        for _ in range(main.MAX_CONCURRENT_CONVERSIONS):
            main.CONVERT_SLOTS.release()
