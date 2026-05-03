import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps


try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception as error:
    print(f"HEIC support not available: {error}")


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}

HEIC_EXTENSIONS = {".heic", ".heif"}

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
            image = ImageOps.exif_transpose(image)

            rotation = 0
            source = "none"

            exif_rotation = _detect_exif_rotation(image)
            if exif_rotation is not None:
                rotation = exif_rotation
                source = "exif"

            else:
                osd_rotation = _detect_osd_rotation(image)
                if osd_rotation is not None:
                    rotation = osd_rotation
                    source = "tesseract_osd"

                    if rotation:
                        image = image.rotate(-rotation, expand=True)

            # Final fallback for phone photos:
            # most invoices/receipts should be portrait.
            if image.width > image.height:
                image = image.rotate(90, expand=True)
                rotation = 90
                source = "portrait_fallback"

            _save_corrected_image(image, corrected_path)

            print(
                f"IMAGE PREPARED: original={original_path}, corrected={corrected_path}, "
                f"rotation={rotation}, source={source}"
            )

            return PreparedImage(
                processing_path=corrected_path,
                original_path=original_path,
                rotation_degrees=rotation,
                orientation_source=source,
                is_image=True,
            )

    except Exception as exc:
        logger.warning("Image orientation correction failed for %s: %s", original_path, exc)
        print(f"IMAGE ORIENTATION FAILED: {original_path} -> {exc}")

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

        image_for_osd = image

        if image_for_osd.mode not in {"RGB", "L"}:
            image_for_osd = image_for_osd.convert("RGB")

        osd = pytesseract.image_to_osd(image_for_osd, output_type=Output.DICT)
        rotation = int(osd.get("rotate", 0)) % 360

        if rotation in {90, 180, 270}:
            return rotation

        return 0

    except Exception as exc:
        logger.info("Tesseract orientation detection did not return a rotation: %s", exc)
        print(f"TESSERACT OSD FAILED: {exc}")
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

    # Convert HEIC/HEIF to JPG so OCR, PDF rendering, and browsers handle it better.
    if suffix in HEIC_EXTENSIONS:
        suffix = ".jpg"

    if suffix not in IMAGE_EXTENSIONS:
        suffix = ".jpg"

    return f"{original_path.stem}-corrected{suffix}"
