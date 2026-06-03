import base64
import pytest

from app.utils.file_validator import (
    validate_file,
    validate_batch,
    sanitize_filename,
    FileValidationError,
    FileTooLargeError,
    UnsupportedFileError,
    CorruptFileError,
    MAX_FILE_SIZE,
)
from app.utils.file_parser import (
    parse_file,
    parse_batch,
    _decode_text,
    _truncate,
    MAX_CHARS_PER_DOC,
    MAX_CHARS_TOTAL,
    TRUNCATION_MARK,
)


class TestFileValidator:
    def test_sanitize_filename_basic(self):
        assert sanitize_filename("test.pdf") == "test.pdf"
        assert sanitize_filename("TEST.PDF") == "TEST.pdf"

    def test_sanitize_filename_path_traversal(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"
        assert sanitize_filename("/tmp/test.pdf") == "test.pdf"

    def test_sanitize_filename_invalid(self):
        with pytest.raises(FileValidationError):
            sanitize_filename("")
        with pytest.raises(FileValidationError):
            sanitize_filename("..")

    def test_validate_file_text(self):
        result = validate_file("test.txt", b"hello world", "text/plain")
        assert result == "test.txt"

    def test_validate_file_image(self):
        result = validate_file("test.png", b"\x89PNG\r\n\x1a\n", "image/png")
        assert result == "test.png"

    def test_validate_file_unsupported_image(self):
        with pytest.raises(UnsupportedFileError):
            validate_file("test.bmp", b"BM", "image/bmp")

    def test_validate_file_too_large(self):
        with pytest.raises(FileTooLargeError):
            validate_file("test.txt", b"x" * (MAX_FILE_SIZE + 1), "text/plain")

    def test_validate_file_unsupported_extension(self):
        with pytest.raises(UnsupportedFileError):
            validate_file("test.exe", b"MZ", "application/octet-stream")

    def test_validate_file_pdf_magic(self):
        with pytest.raises(CorruptFileError):
            validate_file("test.pdf", b"NOTPDF", "application/pdf")

    def test_validate_file_docx_magic(self):
        with pytest.raises(CorruptFileError):
            validate_file("test.docx", b"NOTZIP", "application/vnd.openxmlformats")

    def test_validate_batch_success(self):
        files = [
            ("a.txt", b"hello", "text/plain"),
            ("b.txt", b"world", "text/plain"),
        ]
        results = validate_batch(files)
        assert len(results) == 2

    def test_validate_batch_too_many(self):
        files = [(f"{i}.txt", b"x", "text/plain") for i in range(10)]
        with pytest.raises(FileValidationError):
            validate_batch(files)


class TestFileParser:
    def test_decode_text_utf8(self):
        assert _decode_text("hello".encode("utf-8")) == "hello"

    def test_decode_text_gbk(self):
        text = "中文测试"
        assert _decode_text(text.encode("gbk")) == text

    def test_decode_text_latin1(self):
        text = "café"
        assert _decode_text(text.encode("latin-1")) == text

    def test_decode_text_fallback(self):
        binary = b"\xff\xfe"
        result = _decode_text(binary)
        assert result is not None

    def test_truncate_short(self):
        text = "short"
        assert _truncate(text, 100) == "short"

    def test_truncate_long(self):
        text = "a" * 300_000
        result = _truncate(text, MAX_CHARS_PER_DOC)
        assert len(result) <= MAX_CHARS_PER_DOC + len(TRUNCATION_MARK) + 10
        assert TRUNCATION_MARK in result

    def test_parse_file_empty(self):
        result = parse_file("test.txt", "")
        assert result == ""

    def test_parse_file_invalid_base64(self):
        result = parse_file("test.txt", "not-valid-base64!!!")
        assert result == ""

    def test_parse_file_text(self):
        data = base64.b64encode(b"hello world").decode()
        result = parse_file("test.txt", data)
        assert result == "hello world"

    def test_parse_file_markdown(self):
        data = base64.b64encode(b"# Title\n\nContent").decode()
        result = parse_file("test.md", data)
        assert "# Title" in result

    def test_parse_file_csv(self):
        data = base64.b64encode(b"a,b,c\n1,2,3").decode()
        result = parse_file("test.csv", data)
        assert "a,b,c" in result

    def test_parse_file_code(self):
        data = base64.b64encode(b"def hello():\n    pass").decode()
        result = parse_file("test.py", data)
        assert "def hello():" in result

    def test_parse_file_unsupported(self):
        data = base64.b64encode(b"data").decode()
        result = parse_file("test.exe", data)
        assert "不支持的文件格式" in result

    def test_parse_file_too_large(self):
        data = base64.b64encode(b"x" * (MAX_FILE_SIZE + 1)).decode()
        result = parse_file("test.txt", data)
        assert "文件过大" in result

    def test_parse_file_empty_content(self):
        data = base64.b64encode(b"   ").decode()
        result = parse_file("test.txt", data)
        assert "无文本内容" in result

    def test_parse_batch_basic(self):
        files = [
            {"filename": "a.txt", "data": base64.b64encode(b"hello").decode()},
            {"filename": "b.txt", "data": base64.b64encode(b"world").decode()},
        ]
        results = parse_batch(files)
        assert len(results) == 2
        assert results[0][0] == "a.txt"
        assert "hello" in results[0][1]

    def test_parse_batch_truncate_total(self):
        files = [
            {"filename": "a.txt", "data": base64.b64encode(b"x" * 100_000).decode()},
            {"filename": "b.txt", "data": base64.b64encode(b"y" * 100_000).decode()},
        ]
        results = parse_batch(files)
        total = sum(len(text) for _, text in results)
        assert total <= MAX_CHARS_TOTAL + len(TRUNCATION_MARK) + 100

    def test_parse_batch_max_files(self):
        files = [
            {"filename": f"{i}.txt", "data": base64.b64encode(b"x").decode()}
            for i in range(10)
        ]
        results = parse_batch(files)
        assert len(results) <= 5