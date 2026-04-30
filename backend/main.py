import os
import uuid
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PDF Converter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict to your domain in production
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

SUPPORTED_EXTENSIONS = {
    ".docx", ".doc", ".odt", ".rtf",
    ".pptx", ".ppt", ".odp",
    ".xlsx", ".xls", ".ods",
    ".html", ".htm", ".txt", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".svg",
}

OUTPUT_DIR = Path(tempfile.gettempdir()) / "pdf_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/convert")
async def convert_to_pdf(file: UploadFile = File(...)):
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
