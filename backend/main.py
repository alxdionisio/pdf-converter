import base64
import hashlib
import hmac
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from hash_password import scrypt_hash

logger = logging.getLogger("pdf_converter")

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 Mo
MAX_CONCURRENT_CONVERSIONS = 2
MIN_SECRET_LENGTH = 32
PLACEHOLDER_SECRET = "replace-with-a-long-random-secret"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".svg"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | {
    ".docx", ".doc", ".odt", ".rtf",
    ".pptx", ".ppt", ".odp",
    ".xlsx", ".xls", ".ods",
    ".html", ".htm", ".txt", ".csv",
}


def _load_users(raw: str) -> dict[str, tuple[bytes, bytes]]:
    """Parse "login:salt_hex:hash_hex,login2:..." (entries from hash_password.py)."""
    users = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        try:
            login, salt_hex, hash_hex = entry.split(":")
            users[login.strip()] = (bytes.fromhex(salt_hex), bytes.fromhex(hash_hex))
        except ValueError as exc:
            raise RuntimeError(
                "AUTH_USERS: each entry must be login:salt:hash — generate it with hash_password.py"
            ) from exc
    return users


# ponytail: comptes en env — vraie table users si gestion runtime
AUTH_USERS = _load_users(os.getenv("AUTH_USERS", ""))
AUTH_TOKEN_SECRET = os.getenv("AUTH_TOKEN_SECRET", "")
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# Fail closed: never start with a missing, short or published secret
if len(AUTH_TOKEN_SECRET) < MIN_SECRET_LENGTH or AUTH_TOKEN_SECRET == PLACEHOLDER_SECRET:
    raise RuntimeError(
        f"AUTH_TOKEN_SECRET must be a random string of at least {MIN_SECRET_LENGTH} characters "
        "(generate one with: openssl rand -hex 32)"
    )
if not AUTH_USERS:
    raise RuntimeError("AUTH_USERS is empty — generate an entry with hash_password.py")

DUMMY_SALT = os.urandom(16)  # unknown logins cost the same as known ones
CONVERT_SLOTS = threading.BoundedSemaphore(MAX_CONCURRENT_CONVERSIONS)
LOGIN_ATTEMPTS_PER_MINUTE = 5
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_LOCK = threading.Lock()

app = FastAPI(title="PDF Converter API", docs_url=None, redoc_url=None, openapi_url=None)

# Only needed when the frontend is served from another origin (VITE_API_URL)
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["POST", "GET"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition"],
    )


class LoginRequest(BaseModel):
    username: str
    password: str


def _sign_token(payload: str) -> str:
    signature = hmac.new(
        AUTH_TOKEN_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")


def _create_token(username: str) -> str:
    payload = json.dumps(
        {"sub": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS},
        separators=(",", ":"),
    )
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8").rstrip("=")
    signature_b64 = _sign_token(payload_b64)
    return f"{payload_b64}.{signature_b64}"


def _decode_token(token: str) -> dict:
    payload_b64, _, signature = token.partition(".")
    expected = _sign_token(payload_b64)
    if not hmac.compare_digest(signature.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Token invalide")

    try:
        padded_payload = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_payload))
        expires_at = int(payload["exp"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Token invalide") from exc
    if expires_at < int(time.time()):
        raise HTTPException(status_code=401, detail="Session expirée")
    return payload


def _require_auth(request: Request) -> None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise")
    token = auth_header.split(" ", 1)[1].strip()
    payload = _decode_token(token)
    if payload.get("sub") not in AUTH_USERS:
        raise HTTPException(status_code=401, detail="Token invalide")


def _check_login_rate(client_ip: str) -> None:
    """Allow LOGIN_ATTEMPTS_PER_MINUTE attempts per IP, even without nginx in front."""
    now = time.monotonic()
    with LOGIN_LOCK:
        # ponytail: crude memory cap if someone sprays many IPs — use a TTL cache if it bites
        if len(LOGIN_ATTEMPTS) > 10_000:
            LOGIN_ATTEMPTS.clear()
        recent = [t for t in LOGIN_ATTEMPTS.get(client_ip, []) if now - t < 60]
        if len(recent) >= LOGIN_ATTEMPTS_PER_MINUTE:
            LOGIN_ATTEMPTS[client_ip] = recent
            raise HTTPException(status_code=429, detail="Trop de tentatives, réessayez dans une minute.")
        LOGIN_ATTEMPTS[client_ip] = [*recent, now]


@app.post("/auth/login")
def login(body: LoginRequest, request: Request) -> dict[str, str]:
    # X-Real-IP is set by nginx (Docker) or the Railway edge; spoofable only when
    # the backend is reached with no proxy at all
    _check_login_rate(request.headers.get("x-real-ip") or getattr(request.client, "host", "unknown"))
    salt, expected_hash = AUTH_USERS.get(body.username, (DUMMY_SALT, b""))
    if not hmac.compare_digest(scrypt_hash(body.password, salt), expected_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides")
    return {"token": _create_token(body.username)}


@app.get("/auth/verify", status_code=204)
def verify(request: Request) -> None:
    """Used by nginx auth_request to reject anonymous uploads before reading them."""
    _require_auth(request)


@app.middleware("http")
async def guard_convert(request: Request, call_next):
    # Runs before the body is read: no auth or no declared size means no upload
    if request.method == "POST" and request.url.path == "/convert":
        try:
            _require_auth(request)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        content_length = request.headers.get("content-length", "")
        if not content_length.isdecimal():
            return JSONResponse(status_code=411, content={"detail": "En-tête Content-Length requis"})
        if int(content_length) > MAX_UPLOAD_SIZE:
            return JSONResponse(status_code=413, content={"detail": "Fichier trop volumineux (max 100 Mo)"})
    return await call_next(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Sync handler on purpose: FastAPI runs it in a worker thread, so a conversion
# no longer freezes /health and /auth/login.
@app.post("/convert")
def convert_to_pdf(file: Annotated[UploadFile, File()]) -> FileResponse:
    original_name = Path(file.filename or "")
    ext = original_name.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : {ext}. Formats acceptés : {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if not CONVERT_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="Serveur occupé, réessayez dans un instant.")

    # One directory per job: a single rmtree removes input, output and leftovers
    job_dir = Path(tempfile.mkdtemp(prefix="pdfconv_"))
    input_path = job_dir / f"input{ext}"
    output_path = job_dir / "input.pdf"
    try:
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        if ext in IMAGE_EXTENSIONS:
            _convert_image_to_pdf(input_path, output_path)
        else:
            _convert_with_libreoffice(input_path, output_path)

        if not output_path.exists():
            raise RuntimeError("no PDF produced")
    except Exception as exc:
        # Details stay in the server log: they contain paths and tool output
        logger.exception("Conversion failed")
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="La conversion a échoué.") from exc
    finally:
        CONVERT_SLOTS.release()

    return FileResponse(
        path=str(output_path),
        media_type="application/pdf",
        filename=f"{original_name.stem or 'document'}.pdf",
        background=BackgroundTask(shutil.rmtree, job_dir, ignore_errors=True),
    )


def _convert_with_libreoffice(input_path: Path, output_path: Path) -> None:
    """Convert document using LibreOffice headless (writes <input stem>.pdf in outdir)."""
    # ponytail: on timeout only the launcher is killed, soffice.bin may linger until it
    # finishes — kill the process group if that ever shows up in practice
    result = subprocess.run(
        [
            "libreoffice",
            # Private profile per job: concurrent instances cannot share one
            f"-env:UserInstallation=file://{input_path.parent}/profile",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_path.parent),
            str(input_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice error: {result.stderr}")


def _convert_image_to_pdf(input_path: Path, output_path: Path) -> None:
    """Convert image to PDF using ImageMagick."""
    # Explicit "format:" prefix so the coder follows the extension, not the file content
    result = subprocess.run(
        ["convert", f"{input_path.suffix[1:]}:{input_path}", str(output_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        # Fallback: use LibreOffice for SVG/images it supports
        _convert_with_libreoffice(input_path, output_path)
