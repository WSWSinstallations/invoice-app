from __future__ import annotations

import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.database import BASE_DIR


UPLOAD_DIR = Path("uploads")
GENERATED_DIR = Path("generated")


def ensure_storage_dirs() -> None:
    resolve_path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    resolve_path(GENERATED_DIR).mkdir(parents=True, exist_ok=True)


def resolve_path(relative_path: str | Path) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    return cleaned or "invoice"


def save_upload_file(upload: UploadFile) -> tuple[str, str]:
    ensure_storage_dirs()
    original_name = upload.filename or "invoice"
    stored_name = f"{uuid4().hex}_{safe_filename(original_name)}"
    relative_path = UPLOAD_DIR / stored_name
    target_path = resolve_path(relative_path)

    with target_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    return stored_name, relative_path.as_posix()


def generated_file(invoice_id: int, suffix: str) -> str:
    ensure_storage_dirs()
    return (GENERATED_DIR / f"invoice_{invoice_id}.{suffix}").as_posix()
