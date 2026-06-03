import logging
import re
import unicodedata
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_SIZE = 25 * 1024 * 1024
MAX_FILES_PER_REQUEST = 5

_PDF_MAGIC = b"%PDF-"
_OOXML_MAGIC = b"PK\x03\x04"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"

ALLOWED_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".pptx", ".xlsx",
    ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm",
    ".py", ".java", ".cpp", ".c", ".h", ".js", ".ts", ".jsx", ".tsx",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
}

ALLOWED_IMAGE_TYPES: set[str] = {
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
}


class FileValidationError(ValueError):
    pass


class FileTooLargeError(FileValidationError):
    pass


class UnsupportedFileError(FileValidationError):
    pass


class CorruptFileError(FileValidationError):
    pass


def sanitize_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFC", filename)
    safe_name = normalized.replace("\\", "/").rsplit("/", 1)[-1]
    safe_name = re.sub(r"[\x00-\x1f\x7f]", "", safe_name)
    safe_name = re.sub(r'[<>"/\\|?*]', "_", safe_name)
    stem, ext = PurePosixPath(safe_name).stem, PurePosixPath(safe_name).suffix
    ext = ext.lower()
    safe_name = f"{stem}{ext}"
    if not safe_name or safe_name in (".", "..") or safe_name.strip("_") == "":
        raise FileValidationError("Invalid filename")
    return safe_name


def check_magic(filename: str, data: bytes) -> None:
    ext = PurePosixPath(filename or "").suffix.lower()
    if ext == ".pdf":
        if not data.startswith(_PDF_MAGIC):
            raise CorruptFileError(f"{filename}: invalid PDF header")
    elif ext in {".docx", ".xlsx", ".pptx"}:
        if not data.startswith(_OOXML_MAGIC):
            raise CorruptFileError(f"{filename}: invalid Office file header")


def validate_file(filename: str, data: bytes, mime_type: str = "") -> str:
    safe_name = sanitize_filename(filename)
    ext = PurePosixPath(safe_name).suffix.lower()

    if mime_type.startswith("image/"):
        if mime_type not in ALLOWED_IMAGE_TYPES:
            raise UnsupportedFileError(f"{safe_name}: unsupported image type {mime_type}")
        if len(data) > MAX_FILE_SIZE:
            raise FileTooLargeError(f"{safe_name}: exceeds {MAX_FILE_SIZE // (1024*1024)}MB")
        return safe_name

    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileError(f"{safe_name}: unsupported extension '{ext}'")

    if len(data) > MAX_FILE_SIZE:
        raise FileTooLargeError(
            f"{safe_name}: exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit"
        )

    check_magic(safe_name, data)
    return safe_name


def validate_batch(files: list[tuple[str, bytes, str]]) -> list[str]:
    total_size = sum(len(d) for _, d, _ in files)
    if total_size > MAX_TOTAL_SIZE:
        raise FileTooLargeError(
            f"Total upload size exceeds {MAX_TOTAL_SIZE // (1024*1024)}MB"
        )
    if len(files) > MAX_FILES_PER_REQUEST:
        raise FileValidationError(f"Max {MAX_FILES_PER_REQUEST} files per request")
    return [validate_file(name, data, mime) for name, data, mime in files]