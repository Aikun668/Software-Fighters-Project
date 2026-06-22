"""Export content_blocks to Word DOCX with rich formatting.

Architecture: python-docx for document structure + docxtpl RichText/Listing
helpers for inline formatting. Mirrors ppt_exporter.py pattern.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from docx import Document
    from docx.shared import Pt, Inches, Cm, RGBColor, Emu
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.style import WD_STYLE_TYPE
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    logger.error("python-docx not installed. Run: pip install docxtpl")
    raise


# ═══════════════════════════════════════════════════════════════
# Theme
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DocxTheme:
    primary: RGBColor = field(default_factory=lambda: RGBColor(0x1A, 0x56, 0xDB))
    secondary: RGBColor = field(default_factory=lambda: RGBColor(0x37, 0x41, 0x51))
    accent: RGBColor = field(default_factory=lambda: RGBColor(0xE8, 0x6A, 0x17))
    white: RGBColor = field(default_factory=lambda: RGBColor(0xFF, 0xFF, 0xFF))
    black: RGBColor = field(default_factory=lambda: RGBColor(0x1A, 0x1A, 0x1A))
    gray: RGBColor = field(default_factory=lambda: RGBColor(0x6B, 0x72, 0x80))
    light_gray: RGBColor = field(default_factory=lambda: RGBColor(0xF0, 0xF3, 0xF8))
    code_bg: RGBColor = field(default_factory=lambda: RGBColor(0x28, 0x2C, 0x34))
    code_fg: RGBColor = field(default_factory=lambda: RGBColor(0xAB, 0xB2, 0xBF))
    green: RGBColor = field(default_factory=lambda: RGBColor(0x22, 0xC5, 0x5E))
    red: RGBColor = field(default_factory=lambda: RGBColor(0xEF, 0x44, 0x44))

    body_font: str = "Microsoft YaHei"
    code_font: str = "Consolas"
    title_size: Pt = field(default_factory=lambda: Pt(24))
    heading_size: Pt = field(default_factory=lambda: Pt(16))
    subheading_size: Pt = field(default_factory=lambda: Pt(13))
    body_size: Pt = field(default_factory=lambda: Pt(11))
    code_size: Pt = field(default_factory=lambda: Pt(9))
    callout_size: Pt = field(default_factory=lambda: Pt(11))


THEME = DocxTheme()

_INLINE_SPANS = re.compile(
    r'(\*\*(?P<bold>.+?)\*\*|'
    r'\*(?P<italic>.+?)\*|'
    r'`(?P<code>.+?)`|'
    r'\[(?P<link_text>.+?)\]\((?P<link_url>.+?)\))'
)


@dataclass(frozen=True)
class TextRun:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    link_url: str = ""
    color: RGBColor | None = None
    font_size: Pt | None = None


# ═══════════════════════════════════════════════════════════════
# Markdown inline parser (reused from ppt_exporter)
# ═══════════════════════════════════════════════════════════════

def _parse_inline_markdown(text: str) -> list[TextRun]:
    runs: list[TextRun] = []
    pos = 0
    for m in _INLINE_SPANS.finditer(text):
        if m.start() > pos:
            plain = text[pos:m.start()]
            if plain.strip():
                runs.append(TextRun(text=plain))
        if m.group('bold'):
            runs.append(TextRun(text=m.group('bold'), bold=True))
        elif m.group('italic'):
            runs.append(TextRun(text=m.group('italic'), italic=True))
        elif m.group('code'):
            runs.append(TextRun(text=m.group('code'), code=True))
        elif m.group('link_text'):
            runs.append(TextRun(text=m.group('link_text'), link_url=m.group('link_url') or ""))
        pos = m.end()
    if pos < len(text):
        remaining = text[pos:]
        if remaining.strip():
            runs.append(TextRun(text=remaining))
    return runs


# ═══════════════════════════════════════════════════════════════
# Paragraph builders
# ═══════════════════════════════════════════════════════════════

def _set_paragraph_spacing(paragraph, before: int = 0, after: int = 0):
    pf = paragraph.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)


def _add_formatted_paragraph(doc, text: str, font_size: Pt | None = None,
                              bold: bool = False, color: RGBColor | None = None,
                              alignment=None):
    """Add a paragraph with inline markdown formatting."""
    runs = _parse_inline_markdown(text)
    p = doc.add_paragraph()
    if alignment is not None:
        p.alignment = alignment
    for r in runs:
        run = p.add_run(r.text)
        if r.code:
            run.font.name = THEME.code_font
            run.font.size = r.font_size or THEME.code_size
            run.font.color.rgb = THEME.accent
        else:
            run.font.name = THEME.body_font
            run.font.size = r.font_size or font_size or THEME.body_size
            run.font.color.rgb = r.color or color or THEME.black
            run.font.bold = r.bold or bold
            run.font.italic = r.italic
    return p


def _add_heading_paragraph(doc, text: str, level: int = 1):
    """Add a styled heading paragraph."""
    p = doc.add_paragraph()
    _set_paragraph_spacing(p, before=18 if level == 1 else 12, after=6)
    run = p.add_run(text)
    run.font.name = THEME.body_font
    size_map = {1: THEME.heading_size, 2: THEME.subheading_size}
    run.font.size = size_map.get(level, THEME.body_size)
    run.font.bold = True
    run.font.color.rgb = THEME.primary if level <= 1 else THEME.secondary
    return p


def _add_code_block(doc, code: str, language: str = ""):
    """Add a syntax-highlighted code block with dark background."""
    # Clean code content
    if code.startswith('```'):
        lines = code.split('\n')
        if lines[0].startswith('```'):
            language = language or lines[0][3:].strip()
            lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        code = '\n'.join(lines)

    # Language badge paragraph
    if language:
        badge = doc.add_paragraph()
        _set_paragraph_spacing(badge, before=12, after=0)
        badge_run = badge.add_run(f" {language.upper()} ")
        badge_run.font.name = THEME.code_font
        badge_run.font.size = Pt(8)
        badge_run.font.color.rgb = THEME.white
        badge_run.font.bold = True
        _set_run_background(badge_run, THEME.primary)

    # Code paragraph
    for i, line in enumerate(code.split('\n')):
        p = doc.add_paragraph()
        _set_paragraph_spacing(p, before=0, after=0)
        p.paragraph_format.line_spacing = Pt(14)
        _set_paragraph_background(p, THEME.code_bg)
        run = p.add_run(line if line else ' ')
        run.font.name = THEME.code_font
        run.font.size = THEME.code_size
        run.font.color.rgb = THEME.code_fg
    return True


def _add_callout_block(doc, heading: str, content: str):
    """Add a visually distinct callout/card block."""
    # Heading with accent color
    p_head = doc.add_paragraph()
    _set_paragraph_spacing(p_head, before=16, after=4)
    icon = p_head.add_run("▎")
    icon.font.color.rgb = THEME.accent
    icon.font.size = Pt(14)
    title_run = p_head.add_run(heading)
    title_run.font.name = THEME.body_font
    title_run.font.size = THEME.callout_size
    title_run.font.bold = True
    title_run.font.color.rgb = THEME.secondary

    # Content — split by newlines, each line gets light background
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        p_body = doc.add_paragraph()
        _set_paragraph_spacing(p_body, before=0, after=2)
        _set_paragraph_background(p_body, THEME.light_gray)
        p_body.paragraph_format.left_indent = Inches(0.3)
        p_body.paragraph_format.right_indent = Inches(0.2)
        runs = _parse_inline_markdown(line)
        for r in runs:
            run = p_body.add_run(r.text)
            run.font.name = THEME.code_font if r.code else THEME.body_font
            run.font.size = r.font_size or THEME.body_size
            run.font.color.rgb = THEME.accent if r.code else THEME.black
            run.font.bold = r.bold
            run.font.italic = r.italic


# ═══════════════════════════════════════════════════════════════
# Helpers for paragraph/run background shading
# ═══════════════════════════════════════════════════════════════

def _set_paragraph_background(paragraph, color: RGBColor):
    """Set paragraph-level background color via XML."""
    pPr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), str(color))
    pPr.append(shd)


def _set_run_background(run, color: RGBColor):
    """Set run-level background color via XML."""
    rPr = run._r.get_or_add_rPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), str(color))
    rPr.append(shd)


# ═══════════════════════════════════════════════════════════════
# Block-level markdown renderer
# ═══════════════════════════════════════════════════════════════

_HEADING_RE = re.compile(r'^(#{1,4})\s+(.+)$')
_LIST_ITEM_RE = re.compile(r'^(\s*)[-*+]\s+(.+)$')
_FENCE_START_RE = re.compile(r'^```(\w*)\s*$')


def _render_content_to_docx(doc, content: str):
    """Parse block-level markdown and add formatted paragraphs to doc.

    Handles: ### headings, - bullet lists, ``` fenced code blocks,
    regular paragraphs with inline markdown.
    """
    lines = content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip empty lines
        if not line.strip():
            i += 1
            continue

        # Fenced code block
        fence_m = _FENCE_START_RE.match(line)
        if fence_m:
            language = fence_m.group(1)
            code_lines = []
            i += 1
            while i < len(lines):
                if _FENCE_START_RE.match(lines[i]):
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            _add_code_block(doc, '\n'.join(code_lines), language)
            continue

        # Markdown heading
        heading_m = _HEADING_RE.match(line)
        if heading_m:
            level = len(heading_m.group(1))
            text = heading_m.group(2)
            _add_heading_paragraph(doc, text, level=min(level, 2))
            i += 1
            continue

        # Unordered list item
        list_m = _LIST_ITEM_RE.match(line)
        if list_m:
            item_text = list_m.group(2)
            p = doc.add_paragraph()
            _set_paragraph_spacing(p, before=2, after=2)
            p.paragraph_format.left_indent = Inches(0.3)
            bullet = p.add_run('• ')
            bullet.font.name = THEME.body_font
            bullet.font.size = THEME.body_size
            bullet.font.color.rgb = THEME.accent
            for r in _parse_inline_markdown(item_text):
                run = p.add_run(r.text)
                run.font.name = THEME.code_font if r.code else THEME.body_font
                run.font.size = r.font_size or THEME.body_size
                run.font.color.rgb = THEME.accent if r.code else THEME.black
                run.font.bold = r.bold
                run.font.italic = r.italic
            i += 1
            continue

        # Regular paragraph
        _add_formatted_paragraph(doc, line)
        i += 1


# ═══════════════════════════════════════════════════════════════
# Main export entry point
# ═══════════════════════════════════════════════════════════════

def export_to_docx(
    content_blocks: list[dict],
    output_path: str,
    title: str = "AI 学习资源",
    sub_type: str = "overview",
) -> str:
    """Convert content_blocks to a formatted .docx file.

    Block types:
      - section: heading + body text with inline markdown
      - code:    dark-background code block
      - callout: prominent callout card
      - text/mindmap/mermaid/flash_cards/error: plain text fallback
    """
    doc = Document()

    # ── Page setup ──
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)

    # ── Default style ──
    style = doc.styles['Normal']
    style.font.name = THEME.body_font
    style.font.size = THEME.body_size
    style.font.color.rgb = THEME.black

    # ── Title ──
    _add_title_page(doc, title, sub_type)

    # ── Body blocks ──
    for block in content_blocks:
        block_type = block.get("type", "text")
        heading = str(block.get("heading", ""))
        content = str(block.get("content", ""))

        if not content and not heading:
            continue

        try:
            if block_type == "section":
                if heading:
                    _add_heading_paragraph(doc, heading, level=1)
                _render_content_to_docx(doc, content)

            elif block_type == "code":
                if heading:
                    _add_heading_paragraph(doc, heading, level=2)
                _add_code_block(doc, content)

            elif block_type == "callout":
                _add_callout_block(doc, heading, content)

            elif block_type == "error":
                _add_callout_block(doc, heading or "提示", content)

            else:
                # Generic text fallback
                if heading:
                    _add_heading_paragraph(doc, heading, level=2)
                _add_formatted_paragraph(doc, content)

        except Exception as exc:
            logger.error(f"Failed to export block type={block_type}: {exc}")

    # ── Footer ──
    _add_footer(doc, title)

    # ── Save ──
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    logger.info(f"DOCX exported to {output_path}, {len(content_blocks)} blocks")
    return output_path


def _add_title_page(doc, title: str, sub_type: str):
    """Add a professional title/cover section."""
    # Spacer
    spacer = doc.add_paragraph()
    _set_paragraph_spacing(spacer, before=100, after=0)

    # Title
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(p_title, before=0, after=12)
    run = p_title.add_run(title)
    run.font.name = THEME.body_font
    run.font.size = THEME.title_size
    run.font.bold = True
    run.font.color.rgb = THEME.primary

    # Subtitle
    sub_label = "技术速览" if sub_type == "overview" else "实战攻略"
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(p_sub, before=0, after=24)
    run = p_sub.add_run(f"AI 智能学习系统 · {sub_label}")
    run.font.name = THEME.body_font
    run.font.size = Pt(12)
    run.font.color.rgb = THEME.gray

    # Separator line
    p_sep = doc.add_paragraph()
    p_sep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_paragraph_spacing(p_sep, before=0, after=24)
    run = p_sep.add_run("─" * 50)
    run.font.name = THEME.body_font
    run.font.size = Pt(8)
    run.font.color.rgb = THEME.light_gray


def _add_footer(doc, title: str):
    """Add a footer note."""
    p_sep = doc.add_paragraph()
    _set_paragraph_spacing(p_sep, before=30, after=6)
    p_sep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_sep.add_run("─" * 50)
    run.font.size = Pt(8)
    run.font.color.rgb = THEME.gray

    p_footer = doc.add_paragraph()
    p_footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_footer.add_run(f"由 AI 智能学习系统生成 · {title}")
    run.font.name = THEME.body_font
    run.font.size = Pt(9)
    run.font.color.rgb = THEME.gray
    run.italic = True
