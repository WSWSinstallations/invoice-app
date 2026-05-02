from __future__ import annotations

import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.database import BASE_DIR
from app.image_orientation import prepare_image_for_processing


UPLOAD_DIR = Path("uploads")
ORIGINAL_UPLOAD_DIR = UPLOAD_DIR / "original"
CORRECTED_UPLOAD_DIR = UPLOAD_DIR / "corrected"
GENERATED_DIR = Path("generated")


def ensure_storage_dirs() -> None:
    for directory in (UPLOAD_DIR, ORIGINAL_UPLOAD_DIR, CORRECTED_UPLOAD_DIR, GENERATED_DIR):
        resolve_path(directory).mkdir(parents=True, exist_ok=True)


def resolve_path(relative_path: str | Path) -> Path:
    path = Path(relative_path)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def relative_to_base(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
    return cleaned or "invoice"


def save_upload_file(upload: UploadFile) -> tuple[str, str]:
    ensure_storage_dirs()
    original_name = upload.filename or "invoice"
    stored_name = f"{uuid4().hex}_{safe_filename(original_name)}"
    original_relative_path = ORIGINAL_UPLOAD_DIR / stored_name
    original_target_path = resolve_path(original_relative_path)

    with original_target_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    prepared = prepare_image_for_processing(original_target_path, resolve_path(CORRECTED_UPLOAD_DIR))
    return stored_name, relative_to_base(prepared.processing_path)


def generated_file(invoice_id: int, suffix: str) -> str:
    ensure_storage_dirs()
    return (GENERATED_DIR / f"invoice_{invoice_id}.{suffix}").as_posix()
