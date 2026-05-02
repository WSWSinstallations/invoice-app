import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


logger = logging.getLogger(__name__)
EXIF_ORIENTATION_TAG = 274
EXIF_ROTATIONS = {
    3: 180,
    6: 90,
    8: 270,
}


@dataclass(frozen=True)
class PreparedImage:
    processing_path: Path
    original_path: Path
    rotation_degrees: int
    orientation_source: str
    is_image: bool


def prepare_image_for_processing(original_path: Path, corrected_dir: Path) -> PreparedImage:
    if original_path.suffix.lower() not in IMAGE_EXTENSIONS:
        return PreparedImage(
            processing_path=original_path,
            original_path=original_path,
            rotation_degrees=0,
            orientation_source="not_applicable",
            is_image=False,
        )

    corrected_dir.mkdir(parents=True, exist_ok=True)
    corrected_path = corrected_dir / _corrected_filename(original_path)

    try:
        with Image.open(original_path) as image:
            exif_rotation = _detect_exif_rotation(image)
            if exif_rotation is not None:
                corrected = ImageOps.exif_transpose(image)
                rotation = exif_rotation
                source = "exif"
            else:
                osd_rotation = _detect_osd_rotation(image)
                rotation = osd_rotation or 0
                source = "tesseract_osd" if osd_rotation is not None else "none"
                # Tesseract OSD reports the clockwise correction angle; Pillow uses
                # counter-clockwise positive angles, so apply the inverse.
                corrected = image.rotate(-rotation, expand=True) if rotation else image.copy()

            _save_corrected_image(corrected, corrected_path)
            return PreparedImage(
                processing_path=corrected_path,
                original_path=original_path,
                rotation_degrees=rotation,
                orientation_source=source,
                is_image=True,
            )
    except Exception as exc:
        logger.warning("Image orientation correction failed for %s: %s", original_path, exc)
        return PreparedImage(
            processing_path=original_path,
            original_path=original_path,
            rotation_degrees=0,
            orientation_source="failed",
            is_image=True,
        )


def _detect_exif_rotation(image: Image.Image) -> int | None:
    try:
        orientation = image.getexif().get(EXIF_ORIENTATION_TAG)
    except Exception:
        orientation = None

    if orientation is None:
        return None
    return EXIF_ROTATIONS.get(int(orientation), 0)


def _detect_osd_rotation(image: Image.Image) -> int | None:
    try:
        import pytesseract
        from pytesseract import Output

        osd = pytesseract.image_to_osd(image, output_type=Output.DICT)
        rotation = int(osd.get("rotate", 0)) % 360
        if rotation in {90, 180, 270}:
            return rotation
        return 0
    except Exception as exc:
        logger.info("Tesseract orientation detection did not return a rotation: %s", exc)
        return None


def _save_corrected_image(image: Image.Image, path: Path) -> None:
    suffix = path.suffix.lower()
    save_kwargs = {}

    if suffix in {".jpg", ".jpeg"}:
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        save_kwargs.update({"quality": 95, "optimize": True})
    elif suffix == ".png" and image.mode == "P":
        image = image.convert("RGBA")

    image.save(path, **save_kwargs)


def _corrected_filename(original_path: Path) -> str:
    suffix = original_path.suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".jpg"
    return f"{original_path.stem}-corrected{suffix}"
