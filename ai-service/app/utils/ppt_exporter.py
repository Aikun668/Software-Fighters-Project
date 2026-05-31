"""Export content_blocks to PowerPoint PPTX with rich Markdown formatting.

Architecture (inspired by OpenMAIC's pptxgenjs pipeline, adapted for python-pptx):
  1. Markdown inline parsing → formatted PPTX runs (bold, italic, code, links)
  2. Fenced code blocks → Pygments tokenize → colored PPTX runs
  3. Markdown tables → PPTX table shapes
  4. Multiple professional slide layouts with theming

python-pptx gives us direct lxml XML control, avoiding pptxgenjs wrapper overhead.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Imports that may fail early ──────────────────────────
try:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.oxml.ns import qn, nsmap
except ImportError:
    logger.error("python-pptx not installed. Run: pip install python-pptx")
    raise

try:
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.token import Token
    _PYGMENTS_AVAILABLE = True
except ImportError:
    _PYGMENTS_AVAILABLE = False
    logger.warning("pygments not installed — code blocks will be plain text")


# ═══════════════════════════════════════════════════════════
# Theme
# ═══════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PPTXTheme:
    """Professional color palette and typography for AI learning slides."""
    # Colors
    primary: RGBColor = field(default_factory=lambda: RGBColor(0x1A, 0x56, 0xDB))
    secondary: RGBColor = field(default_factory=lambda: RGBColor(0x37, 0x41, 0x51))
    accent: RGBColor = field(default_factory=lambda: RGBColor(0xE8, 0x6A, 0x17))
    bg_dark: RGBColor = field(default_factory=lambda: RGBColor(0x1E, 0x2D, 0x3D))
    bg_light: RGBColor = field(default_factory=lambda: RGBColor(0xF0, 0xF3, 0xF8))
    white: RGBColor = field(default_factory=lambda: RGBColor(0xFF, 0xFF, 0xFF))
    black: RGBColor = field(default_factory=lambda: RGBColor(0x1A, 0x1A, 0x1A))
    gray: RGBColor = field(default_factory=lambda: RGBColor(0x6B, 0x72, 0x80))
    light_gray: RGBColor = field(default_factory=lambda: RGBColor(0xD0, 0xD5, 0xDD))
    code_bg: RGBColor = field(default_factory=lambda: RGBColor(0x28, 0x2C, 0x34))
    code_fg: RGBColor = field(default_factory=lambda: RGBColor(0xAB, 0xB2, 0xBF))
    green: RGBColor = field(default_factory=lambda: RGBColor(0x22, 0xC5, 0x5E))
    red: RGBColor = field(default_factory=lambda: RGBColor(0xEF, 0x44, 0x44))
    yellow: RGBColor = field(default_factory=lambda: RGBColor(0xF5, 0x9E, 0x0B))

    # Fonts
    title_font: str = "Microsoft YaHei"
    body_font: str = "Microsoft YaHei"
    code_font: str = "Consolas"

    # Font sizes (in Pt)
    title_size: Pt = field(default_factory=lambda: Pt(36))
    subtitle_size: Pt = field(default_factory=lambda: Pt(18))
    heading_size: Pt = field(default_factory=lambda: Pt(28))
    subheading_size: Pt = field(default_factory=lambda: Pt(20))
    body_size: Pt = field(default_factory=lambda: Pt(16))
    small_size: Pt = field(default_factory=lambda: Pt(13))
    code_size: Pt = field(default_factory=lambda: Pt(11))
    callout_size: Pt = field(default_factory=lambda: Pt(18))


THEME = PPTXTheme()
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# ── Slide layout indices ─────────────────────────────────
LAYOUT_TITLE = 0
LAYOUT_CONTENT = 1
LAYOUT_BLANK = 6


# ═══════════════════════════════════════════════════════════
# Inline Markdown Parser
# ═══════════════════════════════════════════════════════════

_INLINE_SPANS = re.compile(
    r'(\*\*(?P<bold>.+?)\*\*|'          # **bold**
    r'\*(?P<italic>.+?)\*|'             # *italic*
    r'`(?P<code>.+?)`|'                  # `inline code`
    r'\[(?P<link_text>.+?)\]\((?P<link_url>.+?)\))'  # [text](url)
)


@dataclass(frozen=True)
class TextRun:
    """A formatted text segment."""
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    link_url: str = ""
    color: RGBColor | None = None
    font_size: Pt | None = None


def _parse_inline_markdown(text: str) -> list[TextRun]:
    """Parse Markdown inline formatting into styled TextRun objects."""
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
            runs.append(TextRun(
                text=m.group('link_text'),
                link_url=m.group('link_url') or "",
            ))

        pos = m.end()

    if pos < len(text):
        remaining = text[pos:]
        if remaining.strip():
            runs.append(TextRun(text=remaining))

    return runs


# ═══════════════════════════════════════════════════════════
# Block-level Markdown Structures
# ═══════════════════════════════════════════════════════════

_FENCE_RE = re.compile(r'^```(\w*)\s*\n(.*?)```', re.DOTALL | re.MULTILINE)
_HEADING_RE = re.compile(r'^(#{1,4})\s+(.+)$', re.MULTILINE)
_LIST_ITEM_RE = re.compile(r'^(\s*)[-*+]\s+(.+)$', re.MULTILINE)
_ORDERED_LIST_RE = re.compile(r'^(\s*)\d+\.\s+(.+)$', re.MULTILINE)
_TABLE_ROW_RE = re.compile(r'^\|(.+)\|$', re.MULTILINE)
_TABLE_SEP_RE = re.compile(r'^\|[\s\-:|]+\|$')


def _is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEP_RE.match(line))


def _parse_table_row(line: str) -> list[str]:
    """Parse a markdown table row into cell values."""
    return [cell.strip() for cell in line.strip('|').split('|')]


def _extract_code_blocks(text: str) -> list[dict]:
    """Extract fenced code blocks with language info from text."""
    blocks = []
    for m in _FENCE_RE.finditer(text):
        blocks.append({
            "language": m.group(1) or "text",
            "code": m.group(2).strip(),
            "span": (m.start(), m.end()),
        })
    return blocks


# ═══════════════════════════════════════════════════════════
# Syntax Highlighting
# ═══════════════════════════════════════════════════════════

# Pygments token → (color, bold, italic) mapping for One Dark theme
_TOKEN_STYLE_MAP = {
    Token.Keyword: (RGBColor(0xC6, 0x78, 0xDD), True, False),
    Token.Keyword.Constant: (RGBColor(0xD1, 0x9A, 0x66), False, False),
    Token.Keyword.Declaration: (RGBColor(0xC6, 0x78, 0xDD), False, False),
    Token.Keyword.Namespace: (RGBColor(0xC6, 0x78, 0xDD), False, False),
    Token.Keyword.Type: (RGBColor(0xE5, 0xC0, 0x7B), False, False),
    Token.Name.Builtin: (RGBColor(0xE5, 0xC0, 0x7B), False, False),
    Token.Name.Function: (RGBColor(0x61, 0xAF, 0xEF), False, False),
    Token.Name.Class: (RGBColor(0xE5, 0xC0, 0x7B), False, False),
    Token.Name.Decorator: (RGBColor(0x61, 0xAF, 0xEF), False, False),
    Token.Name.Exception: (RGBColor(0xE5, 0xC0, 0x7B), False, False),
    Token.String: (RGBColor(0x98, 0xC3, 0x79), False, False),
    Token.String.Doc: (RGBColor(0x98, 0xC3, 0x79), False, True),
    Token.String.Escape: (RGBColor(0x56, 0xB6, 0xC2), False, False),
    Token.Number: (RGBColor(0xD1, 0x9A, 0x66), False, False),
    Token.Operator: (RGBColor(0xAB, 0xB2, 0xBF), False, False),
    Token.Punctuation: (RGBColor(0xAB, 0xB2, 0xBF), False, False),
    Token.Comment: (RGBColor(0x5C, 0x63, 0x70), False, True),
    Token.Comment.Special: (RGBColor(0x5C, 0x63, 0x70), False, True),
    Token.Generic.Deleted: (RGBColor(0xEF, 0x44, 0x44), False, False),
    Token.Generic.Inserted: (RGBColor(0x22, 0xC5, 0x5E), False, False),
    Token.Generic.Heading: (RGBColor(0xE5, 0xC0, 0x7B), True, False),
    Token.Generic.Subheading: (RGBColor(0xE5, 0xC0, 0x7B), False, False),
}


def _pygments_token_to_style(ttype) -> tuple[RGBColor, bool, bool]:
    """Map a Pygments token type to (color, bold, italic)."""
    # Walk up the token hierarchy to find a match
    current = ttype
    while current is not None and current != Token:
        if current in _TOKEN_STYLE_MAP:
            return _TOKEN_STYLE_MAP[current]
        current = current.parent
    return (THEME.code_fg, False, False)


def _highlight_code(code: str, language: str) -> list[TextRun]:
    """Syntax-highlight code using Pygments. Returns list of styled TextRuns."""
    if not _PYGMENTS_AVAILABLE or not code.strip():
        return [TextRun(text=code, code=True)]

    try:
        lexer = get_lexer_by_name(language, stripall=True)
    except Exception:
        try:
            lexer = guess_lexer(code)
        except Exception:
            return [TextRun(text=code, code=True)]

    try:
        tokens = list(lexer.get_tokens(code))
    except Exception:
        return [TextRun(text=code, code=True)]

    runs: list[TextRun] = []
    buf = ""
    last_style = (THEME.code_fg, False, False)
    has_line_number = False

    for ttype, text in tokens:
        if not text:
            continue

        # Skip Pygments internal newline tokens at end
        if ttype == Token.Text and text == '\n' and not buf:
            continue

        color, bold, italic = _pygments_token_to_style(ttype)
        run = TextRun(text=text, bold=bold, italic=italic, color=color, font_size=THEME.code_size)

        # Merge consecutive same-style runs to reduce PPTX element count
        if runs and not has_line_number and runs[-1].bold == bold and runs[-1].italic == italic and runs[-1].color == color and runs[-1].font_size == THEME.code_size:
            runs[-1] = TextRun(text=runs[-1].text + text, bold=bold, italic=italic, color=color, font_size=THEME.code_size)
        else:
            runs.append(run)
            has_line_number = False

    return runs


# ═══════════════════════════════════════════════════════════
# Slide Builders
# ═══════════════════════════════════════════════════════════

def _set_shape_fill(shape, color: RGBColor):
    """Set solid fill on a shape."""
    shape.fill.solid()
    shape.fill.fore_color.rgb = color


def _add_text_run(paragraph, run_data: TextRun, default_size: Pt | None = None):
    """Add a single formatted run to a paragraph."""
    run = paragraph.add_run()
    run.text = run_data.text

    if run_data.code or run_data.link_url:
        if run_data.code:
            run.font.name = THEME.code_font
            run.font.size = run_data.font_size or THEME.small_size
            run.font.color.rgb = THEME.accent
        elif run_data.link_url:
            run.font.color.rgb = THEME.primary
            run.font.underline = True
            # Register hyperlink in the paragraph
            rPr = run._r.get_or_add_rPr()
            hlink = rPr.makeelement(qn('a:hlinkClick'), {qn('r:id'): ''})
            rPr.append(hlink)
    else:
        run.font.name = THEME.body_font
        run.font.size = run_data.font_size or default_size or THEME.body_size
        run.font.color.rgb = run_data.color or THEME.black
        run.font.bold = run_data.bold
        run.font.italic = run_data.italic


def _add_paragraph_to_tf(text_frame, text: str, level: int = 0, font_size: Pt | None = None):
    """Add a plain text paragraph to a text frame (fallback for non-markdown text)."""
    p = text_frame.add_paragraph()
    p.level = level
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = text
    run.font.name = THEME.body_font
    run.font.size = font_size or THEME.body_size
    run.font.color.rgb = THEME.black
    return p


def _add_formatted_paragraph(text_frame, line: str, font_size: Pt | None = None):
    """Add a line to text_frame with inline markdown formatting."""
    runs = _parse_inline_markdown(line)
    p = text_frame.add_paragraph()
    p.alignment = PP_ALIGN.LEFT

    if not runs:
        # Empty paragraph — add a line break
        p.add_run().text = ""
        return p

    for r in runs:
        _add_text_run(p, r, default_size=font_size)

    return p


def _build_text_frame_content(text_frame, content: str):
    """Parse Markdown content and populate a text_frame with formatted paragraphs.

    Handles: headings (# ## ###), bullet lists (- * +), numbered lists, paragraphs,
    fenced code blocks, and blockquotes.
    """
    # First, extract code blocks so their content isn't parsed as markdown
    code_blocks = _extract_code_blocks(content)
    code_block_map = {cb["span"]: cb for cb in code_blocks}

    fs = THEME.body_size  # default font size
    i = 0
    raw_lines = content.split('\n')

    while i < len(raw_lines):
        line = raw_lines[i]

        # Check if we're inside a code block
        in_code = False
        for (start, end), cb in code_block_map.items():
            line_start_pos = sum(len(l) + 1 for l in raw_lines[:i])
            line_end_pos = line_start_pos + len(line)
            if start <= line_start_pos < end or start < line_end_pos <= end:
                in_code = True
                # Skip internal lines of code blocks (handled separately)
                break

        if in_code:
            i += 1
            continue

        # Empty line → paragraph break
        if not line.strip():
            p = text_frame.add_paragraph()
            p.add_run().text = ""
            p.space_before = Pt(4)
            i += 1
            continue

        # Heading
        heading_m = _HEADING_RE.match(line)
        if heading_m:
            level = len(heading_m.group(1))
            heading_text = heading_m.group(2)
            heading_sizes = {1: THEME.heading_size, 2: THEME.subheading_size, 3: Pt(18), 4: Pt(16)}
            p = text_frame.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            p.space_before = Pt(16 if level <= 2 else 10)
            p.space_after = Pt(6 if level <= 2 else 4)
            run = p.add_run()
            run.text = heading_text
            run.font.name = THEME.body_font
            run.font.size = heading_sizes.get(level, THEME.body_size)
            run.font.bold = True
            run.font.color.rgb = THEME.primary if level <= 2 else THEME.secondary
            i += 1
            continue

        # Unordered list
        list_m = _LIST_ITEM_RE.match(line)
        if list_m:
            indent = len(list_m.group(1)) // 2
            item_text = list_m.group(2)
            p = text_frame.add_paragraph()
            p.level = indent
            p.alignment = PP_ALIGN.LEFT
            p.space_before = Pt(2)
            # Add bullet character
            bullet_run = p.add_run()
            bullet_run.text = "• "
            bullet_run.font.name = THEME.body_font
            bullet_run.font.size = fs
            bullet_run.font.color.rgb = THEME.accent
            # Add formatted content
            for r in _parse_inline_markdown(item_text):
                _add_text_run(p, r, default_size=fs)
            i += 1
            continue

        # Ordered list
        ordered_m = _ORDERED_LIST_RE.match(line)
        if ordered_m:
            indent = len(ordered_m.group(1)) // 2
            item_text = ordered_m.group(2)
            p = text_frame.add_paragraph()
            p.level = indent
            p.alignment = PP_ALIGN.LEFT
            p.space_before = Pt(2)
            # Use actual number (reconstructed from context — simplified to bullet)
            num_run = p.add_run()
            num_run.text = "1. "
            num_run.font.name = THEME.body_font
            num_run.font.size = fs
            num_run.font.color.rgb = THEME.secondary
            for r in _parse_inline_markdown(item_text):
                _add_text_run(p, r, default_size=fs)
            i += 1
            continue

        # Blockquote
        if line.startswith('> '):
            quote_text = line[2:]
            p = text_frame.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            p.space_before = Pt(4)
            # Style: colored left border effect via indentation + accent color
            run = p.add_run()
            run.text = "│ "  # │ vertical bar
            run.font.name = THEME.body_font
            run.font.size = fs
            run.font.color.rgb = THEME.accent
            run.font.bold = True
            for r in _parse_inline_markdown(quote_text):
                _add_text_run(p, r, default_size=fs)
            i += 1
            continue

        # Regular paragraph
        _add_formatted_paragraph(text_frame, line, font_size=fs)
        i += 1


def _add_title_slide(prs, title: str):
    """Add a professional title slide."""
    slide_layout = prs.slide_layouts[LAYOUT_TITLE]
    slide = prs.slides.add_slide(slide_layout)

    # Remove default shapes for clean design
    for shape in list(slide.shapes):
        sp = shape._element
        sp.getparent().remove(sp)

    # Dark background
    bg = slide.background
    _set_shape_fill(bg, THEME.bg_dark)

    # Title text
    left = Inches(1.5)
    top = Inches(2.0)
    width = Inches(10.333)
    height = Inches(1.5)
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = title
    run.font.name = THEME.title_font
    run.font.size = THEME.title_size
    run.font.bold = True
    run.font.color.rgb = THEME.white

    # Subtitle
    top2 = Inches(3.6)
    txBox2 = slide.shapes.add_textbox(left, top2, width, Inches(0.8))
    tf2 = txBox2.text_frame
    tf2.word_wrap = True
    p2 = tf2.paragraphs[0]
    p2.alignment = PP_ALIGN.CENTER
    run2 = p2.add_run()
    run2.text = "AI 智能学习系统"
    run2.font.name = THEME.body_font
    run2.font.size = THEME.subtitle_size
    run2.font.color.rgb = THEME.light_gray

    # Accent line
    line_left = Inches(4.5)
    line_top = Inches(4.5)
    line_width = Inches(4.333)
    line_height = Inches(0.04)
    line_shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE.RECTANGLE
        line_left, line_top, line_width, line_height,
    )
    _set_shape_fill(line_shape, THEME.accent)
    line_shape.line.fill.background()


def _add_section_header_slide(prs, heading: str, subtitle: str = ""):
    """Add a section divider slide with dark background."""
    slide_layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(slide_layout)

    bg = slide.background
    _set_shape_fill(bg, THEME.bg_dark)

    # Heading
    left = Inches(1.5)
    top = Inches(2.5)
    width = Inches(10.333)
    height = Inches(1.2)
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = heading
    run.font.name = THEME.title_font
    run.font.size = THEME.heading_size
    run.font.bold = True
    run.font.color.rgb = THEME.white

    if subtitle:
        top2 = Inches(3.8)
        txBox2 = slide.shapes.add_textbox(left, top2, width, Inches(0.6))
        tf2 = txBox2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.LEFT
        run2 = p2.add_run()
        run2.text = subtitle
        run2.font.name = THEME.body_font
        run2.font.size = THEME.subtitle_size
        run2.font.color.rgb = THEME.light_gray

    # Small accent bar
    bar = slide.shapes.add_shape(1, left, Inches(3.65), Inches(1.5), Inches(0.04))
    _set_shape_fill(bar, THEME.accent)
    bar.line.fill.background()


def _add_content_slide(prs, heading: str, content: str):
    """Build a content slide with markdown formatting."""
    slide_layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(slide_layout)

    # Top accent bar
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, Inches(0.06))
    _set_shape_fill(bar, THEME.primary)
    bar.line.fill.background()

    # Heading
    h_left = Inches(1.2)
    h_top = Inches(0.4)
    h_width = Inches(10.9)
    h_height = Inches(0.7)
    h_box = slide.shapes.add_textbox(h_left, h_top, h_width, h_height)
    h_tf = h_box.text_frame
    h_tf.word_wrap = True
    p = h_tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = heading
    run.font.name = THEME.body_font
    run.font.size = THEME.heading_size
    run.font.bold = True
    run.font.color.rgb = THEME.primary

    # Thin separator
    sep = slide.shapes.add_shape(1, h_left, Inches(1.15), Inches(10.9), Inches(0.015))
    _set_shape_fill(sep, THEME.light_gray)
    sep.line.fill.background()

    # Content text frame
    c_left = Inches(1.2)
    c_top = Inches(1.4)
    c_width = Inches(10.9)
    c_height = Inches(5.6)
    c_box = slide.shapes.add_textbox(c_left, c_top, c_width, c_height)
    c_tf = c_box.text_frame
    c_tf.word_wrap = True
    # Clear default paragraph
    c_tf.paragraphs[0].clear()

    _build_text_frame_content(c_tf, content)

    # Page number area
    _add_page_number(slide)


def _add_code_slide(prs, heading: str, code: str, language: str = ""):
    """Build a syntax-highlighted code slide."""
    slide_layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(slide_layout)

    # Detect language from content if not provided
    if not language and code.startswith("```"):
        lines = code.split('\n')
        if len(lines) > 1:
            language = lines[0].replace('```', '').strip()
            code = '\n'.join(lines[1:]) if len(lines) > 1 else code
    # Strip trailing ```
    if code.strip().endswith("```"):
        code = code.strip()[:-3].strip()

    # Also handle the case where code is in format ```lang\ncode\n```
    fence_match = re.match(r'^```(\w*)\s*\n', code)
    if fence_match:
        language = language or fence_match.group(1)
        code = code[fence_match.end():]
    if code.strip().endswith('```'):
        code = code.strip()[:-3].strip()

    # Top bar
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, Inches(0.06))
    _set_shape_fill(bar, THEME.accent)
    bar.line.fill.background()

    # Heading
    h_left = Inches(1.0)
    h_top = Inches(0.35)
    h_box = slide.shapes.add_textbox(h_left, h_top, Inches(11.3), Inches(0.6))
    h_tf = h_box.text_frame
    h_tf.word_wrap = True
    p = h_tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = heading
    run.font.name = THEME.body_font
    run.font.size = THEME.subheading_size
    run.font.bold = True
    run.font.color.rgb = THEME.secondary

    # Language badge
    if language:
        badge_w = Inches(1.5)
        badge = slide.shapes.add_shape(
            1,  # RECTANGLE
            Inches(11.8), Inches(0.35), badge_w, Inches(0.35),
        )
        _set_shape_fill(badge, THEME.primary)
        badge.line.fill.background()
        badge_tf = badge.text_frame
        badge_tf.word_wrap = False
        bp = badge_tf.paragraphs[0]
        bp.alignment = PP_ALIGN.CENTER
        br = bp.add_run()
        br.text = language.upper()
        br.font.name = THEME.code_font
        br.font.size = Pt(10)
        br.font.color.rgb = THEME.white
        br.font.bold = True

    # Code background box
    code_left = Inches(0.8)
    code_top = Inches(1.1)
    code_w = Inches(11.7)
    code_h = Inches(5.9)
    bg_shape = slide.shapes.add_shape(1, code_left, code_top, code_w, code_h)
    _set_shape_fill(bg_shape, THEME.code_bg)
    bg_shape.line.color.rgb = RGBColor(0x3E, 0x44, 0x52)
    bg_shape.line.width = Pt(0.5)

    # Code text
    text_left = Inches(1.05)
    text_top = Inches(1.25)
    text_w = Inches(11.2)
    text_h = Inches(5.55)
    txBox = slide.shapes.add_textbox(text_left, text_top, text_w, text_h)
    tf = txBox.text_frame
    tf.word_wrap = True
    # Clear default
    tf.paragraphs[0].clear()

    code_runs = _highlight_code(code, language)
    if not code_runs:
        p = tf.add_paragraph()
        p.add_run().text = code
        return

    # Build paragraphs — split on newlines
    current_paragraph = tf.add_paragraph()
    current_paragraph.alignment = PP_ALIGN.LEFT
    current_paragraph.space_before = Pt(0)
    current_paragraph.space_after = Pt(0)

    for r in code_runs:
        # Split on embedded newlines
        parts = r.text.split('\n')
        for j, part in enumerate(parts):
            if j > 0:
                current_paragraph = tf.add_paragraph()
                current_paragraph.alignment = PP_ALIGN.LEFT
                current_paragraph.space_before = Pt(0)
                current_paragraph.space_after = Pt(0)
            if part:
                run = current_paragraph.add_run()
                run.text = part
                run.font.name = THEME.code_font
                run.font.size = r.font_size or THEME.code_size
                run.font.color.rgb = r.color or THEME.code_fg
                run.font.bold = r.bold
                run.font.italic = r.italic

    _add_page_number(slide)


def _add_callout_slide(prs, heading: str, content: str):
    """Build a visually prominent callout slide for key takeaways."""
    slide_layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(slide_layout)

    bg = slide.background
    _set_shape_fill(bg, THEME.bg_light)

    # Accent left border
    border = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.12), SLIDE_H)
    _set_shape_fill(border, THEME.accent)
    border.line.fill.background()

    # Callout card background
    card_left = Inches(1.5)
    card_top = Inches(1.5)
    card_w = Inches(10.3)
    card_h = Inches(4.5)
    card = slide.shapes.add_shape(1, card_left, card_top, card_w, card_h)
    _set_shape_fill(card, THEME.white)
    card.line.color.rgb = THEME.light_gray
    card.line.width = Pt(0.5)
    # Add subtle shadow via offset duplicate (python-pptx shadow workaround)
    card.shadow.inherit = False

    # Callout icon/heading
    h_box = slide.shapes.add_textbox(Inches(1.8), Inches(1.8), Inches(9.7), Inches(0.7))
    h_tf = h_box.text_frame
    h_tf.word_wrap = True
    p = h_tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    icon_run = p.add_run()
    icon_run.text = "⚠ "  # ⚠ warning/exclamation
    icon_run.font.size = Pt(24)
    icon_run.font.color.rgb = THEME.accent
    title_run = p.add_run()
    title_run.text = heading
    title_run.font.name = THEME.body_font
    title_run.font.size = THEME.callout_size
    title_run.font.bold = True
    title_run.font.color.rgb = THEME.secondary

    # Content
    c_box = slide.shapes.add_textbox(Inches(1.8), Inches(2.7), Inches(9.7), Inches(3.0))
    c_tf = c_box.text_frame
    c_tf.word_wrap = True
    c_tf.paragraphs[0].clear()
    _build_text_frame_content(c_tf, content)

    _add_page_number(slide)


def _add_table_slide(prs, heading: str, table_data: str):
    """Build a slide with a PPTX table from markdown table data."""
    slide_layout = prs.slide_layouts[LAYOUT_BLANK]
    slide = prs.slides.add_slide(slide_layout)

    # Top bar
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), SLIDE_W, Inches(0.06))
    _set_shape_fill(bar, THEME.primary)
    bar.line.fill.background()

    # Heading
    h_box = slide.shapes.add_textbox(Inches(1.2), Inches(0.35), Inches(10.9), Inches(0.6))
    h_tf = h_box.text_frame
    h_tf.word_wrap = True
    p = h_tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = heading
    run.font.name = THEME.body_font
    run.font.size = THEME.subheading_size
    run.font.bold = True
    run.font.color.rgb = THEME.primary

    # Parse table rows
    lines = table_data.strip().split('\n')
    rows: list[list[str]] = []
    for line in lines:
        if _TABLE_ROW_RE.match(line) and not _is_table_separator(line):
            rows.append(_parse_table_row(line))

    if not rows:
        # Fallback: show as text
        sep = slide.shapes.add_shape(1, Inches(1.2), Inches(1.1), Inches(10.9), Inches(0.015))
        _set_shape_fill(sep, THEME.light_gray)
        sep.line.fill.background()
        c_box = slide.shapes.add_textbox(Inches(1.2), Inches(1.3), Inches(10.9), Inches(5.5))
        c_tf = c_box.text_frame
        c_tf.word_wrap = True
        c_tf.paragraphs[0].clear()
        _build_text_frame_content(c_tf, table_data)
        return

    num_rows = len(rows)
    num_cols = max(len(r) for r in rows)

    # Normalize rows
    for row in rows:
        while len(row) < num_cols:
            row.append("")

    table_left = Inches(1.0)
    table_top = Inches(1.3)
    table_width = Inches(11.3)
    row_height = Inches(0.45)

    shape = slide.shapes.add_table(num_rows, num_cols, table_left, table_top, table_width, row_height * num_rows)
    table = shape.table

    # Set column widths evenly
    col_width = int(table_width / num_cols)
    for j in range(num_cols):
        table.columns[j].width = col_width

    for i, row_data in enumerate(rows):
        for j, cell_text in enumerate(row_data):
            cell = table.cell(i, j)

            # Determine if header row
            is_header = (i == 0)

            # Clear default text
            cell.text = ""
            tf = cell.text_frame
            tf.word_wrap = True
            tf.margin_left = Pt(8)
            tf.margin_right = Pt(8)
            tf.margin_top = Pt(4)
            tf.margin_bottom = Pt(4)

            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT

            if is_header:
                # Header cell styling
                cell_fill = cell.fill
                cell_fill.solid()
                cell_fill.fore_color.rgb = THEME.primary

                run = p.add_run()
                run.text = cell_text
                run.font.name = THEME.body_font
                run.font.size = Pt(14)
                run.font.bold = True
                run.font.color.rgb = THEME.white
            else:
                # Data cell styling
                if i % 2 == 0:
                    cell_fill = cell.fill
                    cell_fill.solid()
                    cell_fill.fore_color.rgb = RGBColor(0xF5, 0xF7, 0xFA)

                for r in _parse_inline_markdown(cell_text):
                    _add_text_run(p, r, default_size=Pt(13))

    _add_page_number(slide)


def _add_page_number(slide):
    """Hook for future slide numbering. Currently a no-op."""
    pass


# ═══════════════════════════════════════════════════════════
# Main Export Entry Point
# ═══════════════════════════════════════════════════════════

def export_to_pptx(
    content_blocks: list[dict],
    output_path: str,
    title: str = "AI 学习资源",
) -> str:
    """Convert content_blocks to a professionally formatted .pptx file.

    Block types supported:
      - section:   Markdown content with full formatting
      - code:      Syntax-highlighted code block (Pyneighbors)
      - callout:   Prominent callout with accent styling
      - text:      Plain text (legacy)
      - mindmap:   JSON mindmap data rendered as structured text
      - mermaid:   Mermaid diagram syntax displayed as code
      - table:     NEW — Markdown table data

    Returns the output_path on success.
    """
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    # ── Title slide ──
    _add_title_slide(prs, title)

    for block in content_blocks:
        block_type = block.get("type", "text")
        heading = block.get("heading", "")
        content = str(block.get("content", ""))

        if not content and not heading:
            continue

        try:
            if block_type == "section":
                _add_section_header_slide(prs, heading, "核心内容")
                _add_content_slide(prs, heading, content)

            elif block_type == "code":
                # Extract language from content if present
                lang = ""
                code_body = content
                fence_m = re.match(r'^```(\w*)\s*\n', content)
                if fence_m:
                    lang = fence_m.group(1)
                    code_body = content[fence_m.end():]
                    if code_body.strip().endswith('```'):
                        code_body = code_body.strip()[:-3].strip()
                _add_code_slide(prs, heading, code_body, lang)

            elif block_type == "callout":
                _add_callout_slide(prs, heading, content)

            elif block_type == "table":
                _add_table_slide(prs, heading, content)

            elif block_type == "mindmap":
                # Render mindmap JSON as structured text
                try:
                    import json
                    mm = json.loads(content)
                    nodes = mm.get("nodes", [])
                    edges = mm.get("edges", [])
                    display = ""
                    if nodes:
                        display = "**知识节点:**\n" + "\n".join(
                            f"- {n.get('label', n.get('id', '?'))}" for n in nodes
                        )
                    if edges:
                        display += "\n\n**关系:**\n" + "\n".join(
                            f"- {e.get('src', e.get('from', '?'))} → {e.get('dst', e.get('to', '?'))}"
                            for e in edges
                        )
                    if not display:
                        display = content
                except (json.JSONDecodeError, TypeError):
                    display = content
                _add_content_slide(prs, heading, display)

            elif block_type == "mermaid":
                # Display Mermaid diagram as code block (for reference)
                _add_code_slide(prs, heading, content, "mermaid")

            elif block_type == "error":
                _add_callout_slide(prs, heading or "提示", content)

            else:
                # Generic text fallback
                _add_content_slide(prs, heading or "内容", content)

        except Exception as exc:
            logger.error(f"Failed to export block type={block_type}: {exc}")

    # ── Save ──
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_path)
    logger.info(f"PPTX exported to {output_path}, {len(content_blocks)} blocks")
    return output_path
