import base64
import io
import logging
import re
import zipfile
from pathlib import PurePosixPath

from app.utils.file_validator import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    CorruptFileError,
    UnsupportedFileError,
)

try:
    import fitz
except ImportError:
    fitz = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

try:
    from pptx import Presentation as PptxPresentation
except ImportError:
    PptxPresentation = None

logger = logging.getLogger(__name__)

MAX_CHARS_PER_DOC = 200_000
MAX_CHARS_TOTAL = 150_000
TRUNCATION_MARK = "\n…[内容过长，已截断]"

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm",
    ".py", ".java", ".cpp", ".c", ".h", ".js", ".ts", ".jsx", ".tsx",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
}


def _ext(filename: str) -> str:
    return PurePosixPath(filename or "").suffix.lower()


def _truncate(text: str, max_length: int = MAX_CHARS_PER_DOC) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + TRUNCATION_MARK


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_file(filename: str, data_base64: str) -> str:
    if not data_base64:
        return ""

    try:
        data = base64.b64decode(data_base64)
    except Exception:
        logger.warning(f"Failed to base64 decode {filename}")
        return ""

    if len(data) > MAX_FILE_SIZE:
        return f"[文件过大: {filename}]"

    ext = _ext(filename)
    if ext not in ALLOWED_EXTENSIONS and ext not in TEXT_EXTENSIONS:
        return f"[不支持的文件格式: {filename}]"

    try:
        if ext == ".pdf":
            text = _parse_pdf(data, filename)
        elif ext == ".docx":
            text = _parse_docx(data, filename)
        elif ext == ".xlsx":
            text = _parse_xlsx(data, filename)
        elif ext == ".pptx":
            text = _parse_pptx(data, filename)
        elif ext in TEXT_EXTENSIONS:
            text = _decode_text(data)
        else:
            return f"[不支持的文件格式: {filename}]"
    except Exception as e:
        logger.warning(f"Failed to parse {filename}: {e}")
        return f"[文件解析失败: {filename}]"

    if not text.strip():
        return f"[文件无文本内容: {filename}]"

    return _truncate(text)


def parse_batch(files: list[dict]) -> list[tuple[str, str]]:
    results = []
    total_chars = 0

    for f in files[:5]:
        filename = f.get("filename", "")
        data = f.get("data", "")
        text = parse_file(filename, data)

        if total_chars + len(text) > MAX_CHARS_TOTAL:
            remaining = MAX_CHARS_TOTAL - total_chars
            if remaining > 100:
                text = text[:remaining] + TRUNCATION_MARK
                results.append((filename, text))
            break

        results.append((filename, text))
        total_chars += len(text)

    return results


def _parse_pdf(data: bytes, filename: str) -> str:
    if fitz is not None:
        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                pages = [
                    f"--- Page {i} ---\n{page.get_text() or ''}"
                    for i, page in enumerate(doc, 1)
                ]
            return "\n\n".join(pages)
        except Exception as e:
            logger.info(f"pymupdf failed on {filename}: {e}")

    if PdfReader is None:
        raise CorruptFileError(f"{filename}: no PDF reader available")

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [
            f"--- Page {i} ---\n{page.extract_text() or ''}"
            for i, page in enumerate(reader.pages, 1)
        ]
        return "\n\n".join(pages)
    except Exception as e:
        raise CorruptFileError(f"{filename}: failed to read PDF ({e})")


def _parse_docx(data: bytes, filename: str) -> str:
    primary_error = None
    primary_text = ""

    if DocxDocument is not None:
        try:
            doc = DocxDocument(io.BytesIO(data))
            paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
            primary_text = "\n\n".join(paragraphs)
        except Exception as e:
            primary_error = e
            logger.info(f"python-docx failed on {filename}: {e}")

    fallback = _parse_docx_ooxml(data, filename)
    if fallback.strip() and (not primary_text.strip() or len(fallback) > len(primary_text) * 1.2):
        return fallback
    if primary_text.strip():
        return primary_text

    if DocxDocument is None:
        raise CorruptFileError(f"{filename}: python-docx not installed")
    if primary_error is not None:
        raise CorruptFileError(f"{filename}: failed to open DOCX ({primary_error})")
    return ""


def _parse_docx_ooxml(data: bytes, filename: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
            text = re.sub(r"<[^>]+>", "", xml)
            text = re.sub(r"\n\s*\n", "\n\n", text)
            return text.strip()
    except Exception:
        return ""


def _parse_xlsx(data: bytes, filename: str) -> str:
    if load_workbook is None:
        return _parse_xlsx_ooxml(data, filename)

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        logger.info(f"openpyxl failed on {filename}: {e}")
        fallback = _parse_xlsx_ooxml(data, filename)
        if fallback.strip():
            return fallback
        raise CorruptFileError(f"{filename}: failed to open XLSX ({e})")

    try:
        sheets = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                row_text = "\t".join(str(cell) if cell is not None else "" for cell in row)
                if row_text.strip():
                    rows.append(row_text)
            if rows:
                sheets.append(f"--- Sheet: {sheet_name} ---\n" + "\n".join(rows))
        return "\n\n".join(sheets)
    except Exception as e:
        raise CorruptFileError(f"{filename}: failed to read XLSX ({e})")


def _parse_xlsx_ooxml(data: bytes, filename: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            shared_strings = {}
            if "xl/sharedStrings.xml" in zf.namelist():
                ss_xml = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
                ss_text = re.sub(r"<[^>]+>", " ", ss_xml)
                shared_strings = {i: s.strip() for i, s in enumerate(ss_text.split()) if s.strip()}

            sheets = []
            for name in zf.namelist():
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    sheet_xml = zf.read(name).decode("utf-8", errors="replace")
                    sheet_text = re.sub(r"<[^>]+>", " ", sheet_xml)
                    sheet_text = re.sub(r"\s+", " ", sheet_text).strip()
                    if sheet_text:
                        sheets.append(f"--- {name} ---\n{sheet_text}")
            return "\n\n".join(sheets)
    except Exception:
        return ""


def _parse_pptx(data: bytes, filename: str) -> str:
    if PptxPresentation is not None:
        try:
            prs = PptxPresentation(io.BytesIO(data))
            slides = []
            for i, slide in enumerate(prs.slides, 1):
                texts = []
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        texts.append(shape.text.strip())
                if texts:
                    slides.append(f"--- Slide {i} ---\n" + "\n".join(texts))
            return "\n\n".join(slides)
        except Exception as e:
            logger.info(f"python-pptx failed on {filename}: {e}")

    fallback = _parse_pptx_ooxml(data, filename)
    if fallback.strip():
        return fallback

    if PptxPresentation is None:
        raise CorruptFileError(f"{filename}: python-pptx not installed")
    return ""


def _parse_pptx_ooxml(data: bytes, filename: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            slides = []
            for name in sorted(zf.namelist()):
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    slide_xml = zf.read(name).decode("utf-8", errors="replace")
                    slide_text = re.sub(r"<[^>]+>", " ", slide_xml)
                    slide_text = re.sub(r"\s+", " ", slide_text).strip()
                    if slide_text:
                        slides.append(f"--- {name} ---\n{slide_text}")
            return "\n\n".join(slides)
    except Exception:
        return ""


def format_file_context(parsed_files: list[tuple[str, str]]) -> str:
    if not parsed_files:
        return ""

    parts = ["### 用户上传了 {} 个文件 ###".format(len(parsed_files))]
    for filename, text in parsed_files:
        parts.append(f"[文件: {filename}]\n{text}")

    return "\n\n".join(parts)