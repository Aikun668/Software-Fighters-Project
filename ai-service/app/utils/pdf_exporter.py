import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:
    from fpdf import FPDF
    _FPDF_AVAILABLE = True
except ImportError:
    _FPDF_AVAILABLE = False
    logger.warning("fpdf2 not installed. Run: pip install fpdf2")


@dataclass(frozen=True)
class PDFTheme:
    primary: tuple = field(default_factory=lambda: (26, 86, 219))
    secondary: tuple = field(default_factory=lambda: (55, 65, 81))
    accent: tuple = field(default_factory=lambda: (232, 106, 23))
    white: tuple = field(default_factory=lambda: (255, 255, 255))
    black: tuple = field(default_factory=lambda: (26, 26, 26))
    gray: tuple = field(default_factory=lambda: (107, 114, 128))
    light_gray: tuple = field(default_factory=lambda: (240, 243, 248))
    code_bg: tuple = field(default_factory=lambda: (40, 44, 52))
    green: tuple = field(default_factory=lambda: (34, 197, 94))
    red: tuple = field(default_factory=lambda: (239, 68, 68))


THEME = PDFTheme()


class PDFExporter:
    _UNICODE_FONT_ADDED = False

    def __init__(self, title: str = "AI 学习资源"):
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(True, margin=15)
        self._register_unicode_font()
        self.pdf.add_page()
        self.title = title
        self._font_body = "Helvetica"
        self._add_title_page()

    def _register_unicode_font(self):
        if PDFExporter._UNICODE_FONT_ADDED:
            return
        font_dirs = [
            str(PROJECT_ROOT / "fonts" / "NotoSansCJK-Regular.ttc"),
            str(PROJECT_ROOT / "fonts" / "wqy-zenhei.ttc"),
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for path in font_dirs:
            if os.path.exists(path):
                self.pdf.add_font("CJK", "", path, uni=True)
                self.pdf.add_font("CJK", "B", path, uni=True)
                self._font_body = "CJK"
                PDFExporter._UNICODE_FONT_ADDED = True
                logger.info(f"PDF using Unicode font: {path}")
                return
        logger.warning("No CJK font found; PDF may not render Chinese characters")

    def _add_title_page(self):
        self.pdf.set_fill_color(*THEME.primary)
        self.pdf.rect(0, 0, self.pdf.w, 50, "F")
        self.pdf.set_font(self._font_body, "B", 24)
        self.pdf.set_text_color(*THEME.white)
        self.pdf.set_y(15)
        self.pdf.cell(0, 10, self.title, align="C")
        self.pdf.ln(30)

    def add_section(self, heading: str, content: str):
        self.pdf.set_fill_color(*THEME.primary)
        self.pdf.set_text_color(*THEME.white)
        self.pdf.set_font(self._font_body, "B", 14)
        self.pdf.cell(0, 8, f"  {heading}", fill=True)
        self.pdf.ln(12)
        self._add_markdown_text(content)

    def add_code_block(self, heading: str, content: str, language: str = ""):
        self.pdf.set_font(self._font_body, "B", 12)
        self.pdf.set_text_color(*THEME.black)
        self.pdf.cell(0, 8, heading)
        self.pdf.ln(10)
        code = self._extract_code(content)
        self.pdf.set_fill_color(*THEME.code_bg)
        self.pdf.set_text_color(*THEME.white)
        self.pdf.set_font(self._font_body, "", 9)
        y_start = self.pdf.get_y()
        for line in code.split("\n")[:40]:
            if self.pdf.get_y() > self.pdf.h - 25:
                self.pdf.add_page()
            self.pdf.cell(0, 4, line[:100], fill=True)
            self.pdf.ln(4)
        self.pdf.set_fill_color(*THEME.light_gray)
        self.pdf.rect(0, y_start, 3, self.pdf.get_y() - y_start, "F")
        self.pdf.ln(6)

    def add_callout(self, heading: str, content: str):
        self.pdf.set_fill_color(*THEME.light_gray)
        self.pdf.set_text_color(*THEME.secondary)
        self.pdf.set_font(self._font_body, "BI", 12)
        self.pdf.cell(0, 8, f"  {heading}")
        self.pdf.ln(10)
        self.pdf.set_font(self._font_body, "", 11)
        self.pdf.set_text_color(*THEME.black)
        for line in content.split("\n"):
            self.pdf.cell(0, 6, f"  {line[:120]}")
            self.pdf.ln(6)
        self.pdf.ln(4)

    def add_table_block(self, heading: str, content: str):
        self.pdf.set_font(self._font_body, "B", 12)
        self.pdf.set_text_color(*THEME.black)
        self.pdf.cell(0, 8, heading)
        self.pdf.ln(10)
        lines = content.strip().split("\n")
        rows = [l for l in lines if "|" in l and not l.strip().startswith("|-")]
        if not rows:
            return
        headers = [c.strip() for c in rows[0].split("|") if c.strip()]
        col_w = (self.pdf.w - 20) / max(len(headers), 1)
        self.pdf.set_font(self._font_body, "B", 10)
        self.pdf.set_fill_color(*THEME.primary)
        self.pdf.set_text_color(*THEME.white)
        for h in headers:
            self.pdf.cell(col_w, 8, h, border=1, fill=True, align="C")
        self.pdf.ln()
        self.pdf.set_font(self._font_body, "", 10)
        self.pdf.set_text_color(*THEME.black)
        for row in rows[1:]:
            cols = [c.strip() for c in row.split("|") if c.strip()]
            for c in cols[:len(headers)]:
                self.pdf.cell(col_w, 7, c[:30], border=1, align="L")
            self.pdf.ln()
        self.pdf.ln(6)

    def add_mindmap(self, heading: str, content: str):
        import json
        self.pdf.set_font(self._font_body, "B", 12)
        self.pdf.set_text_color(*THEME.black)
        self.pdf.cell(0, 8, heading)
        self.pdf.ln(10)
        self.pdf.set_font(self._font_body, "", 11)
        try:
            data = json.loads(content) if isinstance(content, str) else content
            nodes = data.get("nodes", [])
            for n in nodes[:15]:
                name = n.get("name", "") if isinstance(n, dict) else str(n)
                self.pdf.cell(0, 6, f"  - {name}")
                self.pdf.ln(6)
        except (json.JSONDecodeError, TypeError):
            for line in content.split("\n")[:20]:
                self.pdf.cell(0, 6, f"  {line[:120]}")
                self.pdf.ln(6)
        self.pdf.ln(4)

    def _add_markdown_text(self, text: str):
        lines = text.split("\n")
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                self.pdf.ln(4)
                continue
            if line_stripped.startswith("## "):
                self.pdf.set_font(self._font_body, "B", 13)
                self.pdf.set_text_color(*THEME.black)
                self.pdf.cell(0, 8, line_stripped[3:])
                self.pdf.ln(10)
            elif line_stripped.startswith("##"):
                self.pdf.set_font(self._font_body, "B", 12)
                self.pdf.set_text_color(*THEME.secondary)
                self.pdf.cell(0, 7, line_stripped.lstrip("#").strip())
                self.pdf.ln(9)
            elif line_stripped.startswith("- ") or line_stripped.startswith("* "):
                self.pdf.set_font(self._font_body, "", 11)
                self.pdf.set_text_color(*THEME.black)
                self.pdf.cell(0, 6, f"  - {self._strip_markdown(line_stripped[2:])}")
                self.pdf.ln(6)
            else:
                self.pdf.set_font(self._font_body, "", 11)
                self.pdf.set_text_color(*THEME.black)
                self.pdf.multi_cell(0, 6, self._strip_markdown(line_stripped))
        self.pdf.ln(4)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"\*(.*?)\*", r"\1", text)
        text = re.sub(r"`(.*?)`", r"\1", text)
        return text

    @staticmethod
    def _extract_code(content: str) -> str:
        match = re.search(r"```(?:\w+)?\n(.*?)```", content, re.DOTALL)
        if match:
            return match.group(1)
        return content

    def save(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(output_path)
        logger.info(f"PDF exported to {output_path}")
        return output_path


def export_to_pdf(content_blocks: list[dict], output_path: str, title: str = "AI 学习资源") -> str:
    if not _FPDF_AVAILABLE:
        raise ImportError("fpdf2 is required for PDF export. Run: pip install fpdf2")

    exporter = PDFExporter(title=title)
    for block in content_blocks:
        btype = block.get("type", "text")
        heading = block.get("heading", "")
        content = block.get("content", "")

        if btype == "section":
            exporter.add_section(heading, content)
        elif btype == "code":
            exporter.add_code_block(heading, content)
        elif btype == "callout":
            exporter.add_callout(heading, content)
        elif btype == "table":
            exporter.add_table_block(heading, content)
        elif btype in ("mindmap", "mermaid", "flash_cards"):
            exporter.add_mindmap(heading, content)
        else:
            exporter.add_callout(heading, content)

    return exporter.save(output_path)
