import os
import uuid
import subprocess
import tempfile
import hashlib
import hmac
import base64
import json
import time
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.background import BackgroundTask

app = FastAPI(title="PDF Converter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your domain in production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 Mo

SUPPORTED_EXTENSIONS = {
    ".docx", ".doc", ".odt", ".rtf",
    ".pptx", ".ppt", ".odp",
    ".xlsx", ".xls", ".ods",
    ".html", ".htm", ".txt", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".svg",
}

OUTPUT_DIR = Path(tempfile.gettempdir()) / "pdf_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

AUTH_USERNAME = os.getenv("AUTH_USERNAME")
AUTH_PASSWORD_SHA256 = os.getenv("AUTH_PASSWORD_SHA256")
AUTH_TOKEN_SECRET = os.getenv("AUTH_TOKEN_SECRET")
TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))


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
    if not AUTH_TOKEN_SECRET:
        raise HTTPException(status_code=500, detail="Configuration auth incomplète")
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Token invalide") from exc

    expected = _sign_token(payload_b64)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Token invalide")

    padded_payload = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload_raw = base64.urlsafe_b64decode(padded_payload.encode("utf-8")).decode("utf-8")
    payload = json.loads(payload_raw)
    if payload.get("exp", 0) < int(time.time()):
        raise HTTPException(status_code=401, detail="Session expirée")
    return payload


def _require_auth(request: Request) -> None:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise")
    token = auth_header.split(" ", 1)[1].strip()
    payload = _decode_token(token)
    if payload.get("sub") != AUTH_USERNAME:
        raise HTTPException(status_code=401, detail="Token invalide")


@app.post("/auth/login")
def login(body: LoginRequest):
    if not AUTH_USERNAME or not AUTH_PASSWORD_SHA256 or not AUTH_TOKEN_SECRET:
        raise HTTPException(status_code=500, detail="Configuration auth incomplète")

    candidate_hash = hashlib.sha256(body.password.encode("utf-8")).hexdigest()
    if body.username != AUTH_USERNAME or not hmac.compare_digest(candidate_hash, AUTH_PASSWORD_SHA256):
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    token = _create_token(body.username)
    return {"token": token}


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    if request.method == "POST" and request.url.path == "/convert":
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Fichier trop volumineux (max 100 Mo)"}
            )
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/convert")
async def convert_to_pdf(request: Request, file: UploadFile = File(...)):
    _require_auth(request)
    original_name = Path(file.filename)
    ext = original_name.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format non supporté : {ext}. Formats acceptés : {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    job_id = uuid.uuid4().hex
    input_path = OUTPUT_DIR / f"{job_id}{ext}"
    output_path = OUTPUT_DIR / f"{job_id}.pdf"

    # Save uploaded file
    content = await file.read()
    with open(input_path, "wb") as f:
        f.write(content)

    try:
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".svg"}:
            _convert_image_to_pdf(input_path, output_path)
        else:
            _convert_with_libreoffice(input_path, output_path)

        if not output_path.exists():
            raise HTTPException(status_code=500, detail="La conversion a échoué : fichier PDF non généré.")

        stem = original_name.stem or "document"
        return FileResponse(
            path=str(output_path),
            media_type="application/pdf",
            filename=f"{stem}.pdf",
            headers={"X-Job-Id": job_id},
            background=BackgroundTask(output_path.unlink, missing_ok=True),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de conversion : {str(e)}")
    finally:
        # Clean up input file
        if input_path.exists():
            input_path.unlink(missing_ok=True)


def _convert_with_libreoffice(input_path: Path, output_path: Path):
    """Convert document using LibreOffice headless."""
    result = subprocess.run(
        [
            "libreoffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_path.parent),
            str(input_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice error: {result.stderr}")

    # LibreOffice names output after the input file
    libreoffice_output = output_path.parent / (input_path.stem + ".pdf")
    if libreoffice_output.exists() and libreoffice_output != output_path:
        libreoffice_output.rename(output_path)


def _convert_image_to_pdf(input_path: Path, output_path: Path):
    """Convert image to PDF using ImageMagick."""
    result = subprocess.run(
        ["convert", str(input_path), str(output_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        # Fallback: use LibreOffice for SVG/images it supports
        _convert_with_libreoffice(input_path, output_path)