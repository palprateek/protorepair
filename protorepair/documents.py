"""Local document ingestion for ProtoRepair.

The reader is deliberately separate from the checker: it turns PDFs, DOCX,
plain text, Markdown, LaTeX, and images into a conservative text stream plus
table/figure metadata.  OCR and PDF rendering use local tools (Tesseract and
Poppler) when available; the core checks remain offline and deterministic.

The extracted text keeps page and table/figure markers so the optional Gemini
extraction path can use the same source text.  Figure/chart pixels are not
digitized; captions and OCR labels are retained as visual evidence.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 30 * 1024 * 1024
MAX_PAGES = 50
MAX_CHARS = 250_000
MAX_FIGURES = 30

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".markdown",
    ".tex",
    ".latex",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
}
SUPPORTED_LABEL = "PDF, DOCX, TXT, Markdown, LaTeX, PNG/JPG/TIFF"


class DocumentError(ValueError):
    """A user-facing document ingestion error."""


@dataclass
class TableBlock:
    page: int | None
    number: int
    rows: list[list[str]]
    caption: str = ""
    method: str = "table"

    def markdown(self) -> str:
        rows = [row for row in self.rows if any(cell.strip() for cell in row)]
        if not rows:
            return ""
        width = max(len(row) for row in rows)
        padded = [row + [""] * (width - len(row)) for row in rows]
        header = padded[0]
        body = padded[1:]
        lines = [
            "| " + " | ".join(_md_cell(cell) for cell in header) + " |",
            "|" + "|".join("---" for _ in range(width)) + "|",
        ]
        lines.extend("| " + " | ".join(_md_cell(cell) for cell in row) + " |" for row in body)
        return "\n".join(lines)

    def text(self) -> str:
        label = f"[TABLE {self.number}"
        if self.page is not None:
            label += f" · page {self.page}"
        label += f" · {self.method}]"
        out = [label]
        if self.caption:
            out.append(f"Caption: {self.caption}")
        md = self.markdown()
        if md:
            out.append(md)
        return "\n".join(out)


@dataclass
class FigureBlock:
    page: int | None
    number: int
    caption: str = ""
    ocr_text: str = ""
    method: str = "embedded"

    def text(self) -> str:
        label = f"[FIGURE {self.number}"
        if self.page is not None:
            label += f" · page {self.page}"
        label += f" · {self.method}]"
        out = [label]
        if self.caption:
            out.append(f"Caption: {self.caption}")
        if self.ocr_text:
            out.append("Visual OCR: " + self.ocr_text.replace("\n", " ").strip())
        return "\n".join(out)


@dataclass
class DocumentExtraction:
    filename: str
    kind: str
    text: str
    pages: int = 0
    tables: list[TableBlock] = field(default_factory=list)
    figures: list[FigureBlock] = field(default_factory=list)
    used_ocr: bool = False
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Small JSON-safe provenance record for reports and the UI."""
        return {
            "filename": self.filename,
            "kind": self.kind,
            "pages": self.pages,
            "tables": len(self.tables),
            "figures": len(self.figures),
            "ocr": self.used_ocr,
            "characters": len(self.text),
            "warnings": list(self.warnings),
            "table_previews": [t.markdown()[:1200] for t in self.tables[:3]],
            "figure_captions": [f.caption for f in self.figures[:5] if f.caption],
        }


def _md_cell(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text.replace("|", r"\|")


def _clean_rows(rows: list[list[Any]] | None) -> list[list[str]]:
    out: list[list[str]] = []
    for row in rows or []:
        cells = [_md_cell(cell) for cell in (row or [])]
        if any(cells):
            out.append(cells)
    return out


def _is_probable_table(rows: list[list[str]]) -> bool:
    if len(rows) < 2 or max((len(r) for r in rows), default=0) < 2:
        return False
    # Avoid turning ordinary wrapped prose with occasional double spaces into
    # a table.  A table needs at least one short cell or a numeric cell.
    has_short = any(any(len(c) <= 24 for c in row) for row in rows)
    has_number = any(any(re.search(r"\d", c) for c in row) for row in rows)
    return has_short and has_number


def _layout_tables(lines: list[str]) -> list[list[list[str]]]:
    """Best-effort table recovery for borderless PDFs and OCR layouts."""
    groups: list[list[list[str]]] = []
    current: list[list[str]] = []

    def flush() -> None:
        nonlocal current
        if _is_probable_table(current):
            groups.append(current)
        current = []

    for line in lines:
        raw = line.rstrip()
        if not raw.strip():
            # PDF layout text often inserts a blank line between table rows.
            # Keep the current candidate open; a non-table line closes it.
            continue
        cells = [c.strip() for c in re.split(r"\t+|\s{2,}", raw.strip()) if c.strip()]
        if len(cells) >= 2 and len(cells) <= 12:
            current.append(cells)
        else:
            flush()
    flush()
    return groups


def _captions(lines: list[str], words: tuple[str, ...]) -> list[str]:
    pattern = re.compile(r"^\s*(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.I)
    return [line.strip() for line in lines if pattern.match(line.strip())]


def _find_caption(lines: list[str], words: tuple[str, ...], index: int) -> str:
    found = _captions(lines, words)
    return found[index] if index < len(found) else ""


def _table_block(rows: list[list[Any]], page: int | None, number: int, caption: str = "", method: str = "table") -> TableBlock | None:
    clean = _clean_rows(rows)
    if len(clean) < 1 or max((len(r) for r in clean), default=0) < 2:
        return None
    return TableBlock(page=page, number=number, rows=clean, caption=caption, method=method)


def _ocr_image(image: Any) -> tuple[str, str | None]:
    """Return (text, warning).  OCR is optional and never blocks text PDFs."""
    try:
        import pytesseract

        text = pytesseract.image_to_string(image, config="--psm 6")
        return text.strip(), None
    except Exception as exc:
        return "", f"OCR unavailable: {exc}"


def _render_pdf_page(data: bytes, page: int) -> tuple[Any | None, str | None]:
    try:
        from pdf2image import convert_from_bytes

        images = convert_from_bytes(data, dpi=200, first_page=page, last_page=page, fmt="png", thread_count=1)
        return (images[0] if images else None), None
    except Exception as exc:
        return None, f"PDF rendering/OCR unavailable: {exc}"


def _normalize_layout(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.splitlines()]
    out: list[str] = []
    blank = 0
    for line in lines:
        if line.strip():
            out.append(line)
            blank = 0
        else:
            blank += 1
            if blank <= 1:
                out.append("")
    return "\n".join(out).strip()


def _normalize_math(text: str) -> str:
    """Convert common LaTeX/rendered math unit spellings to parser-friendly text."""
    text = text.replace("\u00a0", " ").replace("−", "-").replace("\u2212", "-")
    text = text.replace("μ", "µ")
    # cm^{-2}, cm^-2, cm**-2, cm² -> cm²
    text = re.sub(r"\bcm\s*(?:\^|\*\*)\s*\{?\s*-\s*2\}?", "cm²", text, flags=re.I)
    text = re.sub(r"\bcm\s*(?:\^|\*\*)\s*\{?\s*2\}?", "cm²", text, flags=re.I)
    text = re.sub(r"\bcm\s*2\b", "cm²", text, flags=re.I)
    # mg cm^-2 / mAh cm^-2 -> mg/cm² / mAh/cm²
    text = re.sub(r"\b(mg|mAh|mA)\s+cm²(?=\s|$|[,.;])", r"\1/cm²", text, flags=re.I)
    text = re.sub(r"\b(mg|mAh|mA)\s*/\s*cm\s*(?:\^|\*\*)\s*\{?\s*2\s*\}?", r"\1/cm²", text, flags=re.I)
    # Keep prose readable when pylatexenc glues a unit to the next word.
    text = re.sub(r"(\d(?:\.\d+)?\s*(?:mg|mAh|mA|µL|mL|µm|mm|M|ppm)(?:/cm²|/g)?)(?=[A-Za-z])", r"\1 ", text)
    # Normalize common micro/litre spellings.
    text = re.sub(r"\b(um|μm|µm)\b", "µm", text)
    text = re.sub(r"\b(uL|μL|µL)\b", "µL", text)
    text = re.sub(r"\bmA\s+h\b", "mAh", text)
    text = text.replace("µ litre", "µL").replace("µlitre", "µL")
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def _si_replacements(text: str) -> str:
    # siunitx commands are common in LaTeX protocols.  Convert the simple
    # forms before handing the rest to pylatexenc.
    def si(match: re.Match) -> str:
        value, unit = match.group(1), match.group(2)
        return f"{value} {unit}"

    text = re.sub(r"\\SI\s*\{([^{}]+)\}\s*\{([^{}]+)\}", si, text)
    text = re.sub(r"\\SIrange\s*\{([^{}]+)\}\s*\{([^{}]+)\}\s*\{([^{}]+)\}", lambda m: f"{m.group(1)}–{m.group(2)} {m.group(3)}", text)
    text = re.sub(r"\\num\s*\{([^{}]+)\}", r"\1", text)
    text = re.sub(r"\\si\s*\{([^{}]+)\}", r"\1", text)
    text = text.replace(r"\micro", "µ").replace(r"\milli", "m")
    text = text.replace(r"\litre", "L").replace(r"\liter", "L")
    text = text.replace(r"\meter", "m").replace(r"\metre", "m")
    text = text.replace(r"\degree", "°").replace(r"\celsius", "°C")
    return text


def _latex_to_text(source: str) -> str:
    prepared = _si_replacements(source)
    try:
        from pylatexenc.latex2text import LatexNodes2Text

        text = LatexNodes2Text(math_mode="text").latex_to_text(prepared)
    except Exception:
        # Keep the document usable if the optional LaTeX helper is absent.
        text = prepared
        text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", text)
        text = text.replace("{", " ").replace("}", " ")
    return _normalize_math(text)


def _latex_tabulars(source: str, tables: list[TableBlock]) -> str:
    pattern = re.compile(
        r"\\begin\{(tabular\*?|tabularx|longtable)\}(?:\[[^\]]*\])?(?:\{[^{}]*\})?(.*?)\\end\{\1\}",
        re.S,
    )

    def repl(match: re.Match) -> str:
        body = match.group(2)
        rows: list[list[str]] = []
        for raw_row in re.split(r"\\\\", body):
            raw_row = re.sub(r"\\(?:hline|toprule|midrule|bottomrule|cline\{[^}]*\})", " ", raw_row)
            raw_row = raw_row.strip()
            if not raw_row:
                continue
            cells = [_latex_to_text(cell.strip()) for cell in raw_row.split("&")]
            if any(cells):
                rows.append(cells)
        block = _table_block(rows, None, len(tables) + 1, method="latex-tabular")
        if block:
            tables.append(block)
            return "\n\n"
        return "\n"

    return pattern.sub(repl, source)


def _strip_latex_comments(source: str) -> str:
    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in source.splitlines())


def _extract_latex(data: bytes) -> DocumentExtraction:
    source = _decode(data)
    source = _strip_latex_comments(source)
    source = re.sub(r"\\(?:sub)*section\*?\s*\{([^{}]*)\}", lambda m: "\n" + m.group(1) + "\n", source)
    source = re.sub(r"\\title\s*\{([^{}]*)\}", lambda m: "\n" + m.group(1) + "\n", source)
    tables: list[TableBlock] = []
    source = _latex_tabulars(source, tables)
    text = _normalize_layout(_latex_to_text(source))
    warnings: list[str] = []
    if not text:
        warnings.append("No text found in LaTeX source.")
    for table in tables:
        text += "\n\n" + table.text()
    figures: list[FigureBlock] = []
    for caption in _captions(text.splitlines(), ("figure", "fig.", "chart", "graph")):
        figures.append(FigureBlock(None, len(figures) + 1, caption=caption, method="latex-caption"))
    return DocumentExtraction(
        filename="",
        kind="latex",
        text=_limit_text(text, warnings),
        pages=0,
        tables=tables,
        figures=figures,
        warnings=warnings,
    )


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _read_markdown_tables(text: str) -> list[TableBlock]:
    tables: list[TableBlock] = []
    current: list[list[str]] = []

    def flush() -> None:
        nonlocal current
        if len(current) >= 2 and max((len(r) for r in current), default=0) >= 2:
            block = _table_block(current, None, len(tables) + 1, method="markdown")
            if block:
                tables.append(block)
        current = []

    for line in text.splitlines():
        if "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            current.append(cells)
        elif current:
            flush()
    flush()
    return tables


def _extract_text(data: bytes, suffix: str) -> DocumentExtraction:
    text = _normalize_layout(_decode(data))
    warnings: list[str] = []
    tables = _read_markdown_tables(text) if suffix in {".md", ".markdown"} else []
    if not text:
        warnings.append("No text found in the document.")
    for table in tables:
        text += "\n\n" + table.text()
    return DocumentExtraction(
        filename="",
        kind="text",
        text=_limit_text(text, warnings),
        pages=0,
        tables=tables,
        warnings=warnings,
    )


def _omml_text(element: Any) -> str:
    math_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
    parts = [node.text for node in element.iter() if node.tag.startswith(math_ns) and node.tag.endswith("}t") and node.text]
    return "".join(parts).strip()


def _extract_docx(data: bytes) -> DocumentExtraction:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except Exception as exc:
        raise DocumentError("DOCX support requires python-docx. Install the requirements first.") from exc

    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentError(f"Could not read DOCX: {exc}") from exc

    blocks: list[str] = []
    tables: list[TableBlock] = []
    figures: list[FigureBlock] = []
    warnings: list[str] = []
    seen_images: set[str] = set()

    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, doc)
            text = paragraph.text.strip()
            math = _omml_text(child)
            if math and math not in text:
                text = f"{text} {math}".strip()
            if text:
                blocks.append(_normalize_math(text))
        elif tag == "tbl":
            table = Table(child, doc)
            rows: list[list[str]] = []
            for row in table.rows:
                cells = []
                for cell in row.cells:
                    value = cell.text.strip()
                    math = _omml_text(cell._tc)
                    if math and math not in value:
                        value = f"{value} {math}".strip()
                    cells.append(_normalize_math(value))
                rows.append(cells)
            block = _table_block(rows, None, len(tables) + 1, method="docx-table")
            if block:
                tables.append(block)
                blocks.append(block.text())

    try:
        for rel in doc.part.rels.values():
            if not rel.reltype.endswith("/image"):
                continue
            blob = rel.target_part.blob
            if not blob or len(seen_images) >= MAX_FIGURES:
                continue
            import hashlib

            digest = hashlib.sha256(blob).hexdigest()
            if digest in seen_images:
                continue
            seen_images.add(digest)
            try:
                from PIL import Image

                image = Image.open(io.BytesIO(blob)).convert("RGB")
                ocr, warning = _ocr_image(image)
            except Exception as exc:
                ocr, warning = "", f"Could not OCR DOCX image: {exc}"
            if warning:
                warnings.append(warning)
            caption = _find_caption(blocks, ("figure", "fig.", "chart", "graph"), len(figures))
            figure = FigureBlock(None, len(figures) + 1, caption=caption, ocr_text=ocr, method="docx-image")
            figures.append(figure)
            blocks.append(figure.text())
    except Exception as exc:
        warnings.append(f"Could not inspect DOCX images: {exc}")

    known_captions = {f.caption for f in figures if f.caption}
    for caption in _captions(blocks, ("figure", "fig.", "chart", "graph")):
        if caption and caption not in known_captions:
            figures.append(FigureBlock(None, len(figures) + 1, caption=caption, method="docx-caption"))
            known_captions.add(caption)

    text = _normalize_layout("\n\n".join(blocks))
    if not text:
        warnings.append("No text found in DOCX.")
    return DocumentExtraction(
        filename="",
        kind="docx",
        text=_limit_text(text, warnings),
        pages=0,
        tables=tables,
        figures=figures,
        used_ocr=any(f.ocr_text for f in figures),
        warnings=warnings,
    )


def _extract_image(data: bytes) -> DocumentExtraction:
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise DocumentError(f"Could not read image: {exc}") from exc
    ocr, warning = _ocr_image(image)
    warnings = [warning] if warning else []
    figure = FigureBlock(None, 1, caption="Uploaded image", ocr_text=ocr, method="image-ocr")
    text = figure.text()
    if not ocr:
        warnings.append("No OCR text found in the image.")
    return DocumentExtraction(
        filename="",
        kind="image",
        text=_limit_text(text, warnings),
        pages=1,
        figures=[figure],
        used_ocr=bool(ocr),
        warnings=warnings,
    )


def _extract_pdf(data: bytes) -> DocumentExtraction:
    try:
        import pdfplumber
    except Exception as exc:
        raise DocumentError("PDF support requires pdfplumber. Install the requirements first.") from exc

    warnings: list[str] = []
    tables: list[TableBlock] = []
    figures: list[FigureBlock] = []
    page_chunks: list[str] = []
    used_ocr = False
    total_pages = 0
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:
        raise DocumentError(f"Could not read PDF: {exc}") from exc

    try:
        total_pages = len(pdf.pages)
        if total_pages > MAX_PAGES:            warnings.append(f"Only the first {MAX_PAGES} of {total_pages} pages were read.")
        for page_no, page in enumerate(pdf.pages[:MAX_PAGES], start=1):
            try:
                raw = page.extract_text(layout=True, x_tolerance=2, y_tolerance=3) or ""
            except TypeError:
                raw = page.extract_text() or ""
            except Exception as exc:
                raw = ""
                warnings.append(f"Page {page_no} text extraction failed: {exc}")
            raw = _normalize_layout(raw)
            page_lines = raw.splitlines()
            page_tables: list[TableBlock] = []
            try:
                extracted = page.extract_tables() or []
            except Exception as exc:
                extracted = []
                warnings.append(f"Page {page_no} table extraction failed: {exc}")
            for rows in extracted:
                block = _table_block(
                    rows,
                    page_no,
                    len(tables) + 1,
                    caption=_find_caption(page_lines, ("table",), len(page_tables)),
                    method="pdf-table",
                )
                if block:
                    page_tables.append(block)
                    tables.append(block)
            if not page_tables:
                for rows in _layout_tables(page_lines):
                    block = _table_block(
                        rows,
                        page_no,
                        len(tables) + 1,
                        caption=_find_caption(page_lines, ("table",), len(page_tables)),
                        method="pdf-layout",
                    )
                    if block:
                        page_tables.append(block)
                        tables.append(block)

            compact = re.sub(r"\s+", "", raw)
            page_image = None
            page_ocr = ""
            if len(compact) < 40:
                page_image, render_warning = _render_pdf_page(data, page_no)
                if render_warning:
                    warnings.append(render_warning)
                if page_image is not None:
                    page_ocr, ocr_warning = _ocr_image(page_image)
                    if ocr_warning:
                        warnings.append(ocr_warning)
                    if page_ocr:
                        used_ocr = True
                        raw = (raw + "\n[OCR page]\n" + page_ocr).strip()
                        page_lines = raw.splitlines()
                        # Scanned pages can still contain a tabular layout; keep
                        # a best-effort Markdown copy for the reader.
                        for rows in _layout_tables(page_lines):
                            block = _table_block(
                                rows,
                                page_no,
                                len(tables) + 1,
                                method="ocr-layout",
                            )
                            if block:
                                page_tables.append(block)
                                tables.append(block)
            elif page.images and len(figures) < MAX_FIGURES:
                page_image, render_warning = _render_pdf_page(data, page_no)
                if render_warning:
                    warnings.append(render_warning)
                if page_image is not None:
                    scale_x = page_image.width / max(float(page.width), 1.0)
                    scale_y = page_image.height / max(float(page.height), 1.0)
                    for image in page.images:
                        if len(figures) >= MAX_FIGURES:
                            break
                        try:
                            x0, top = float(image.get("x0", 0)), float(image.get("top", 0))
                            x1, bottom = float(image.get("x1", 0)), float(image.get("bottom", 0))
                            left, upper = max(0, int(x0 * scale_x)), max(0, int(top * scale_y))
                            right, lower = min(page_image.width, int(x1 * scale_x)), min(page_image.height, int(bottom * scale_y))
                            if right - left < 40 or lower - upper < 40:
                                continue
                            crop = page_image.crop((left, upper, right, lower))
                            ocr, ocr_warning = _ocr_image(crop)
                            if ocr_warning:
                                warnings.append(ocr_warning)
                            if ocr:
                                used_ocr = True
                            caption = _find_caption(page_lines, ("figure", "fig.", "chart", "graph"), len(figures))
                            figure = FigureBlock(
                                page_no,
                                len(figures) + 1,
                                caption=caption,
                                ocr_text=ocr,
                                method="pdf-image",
                            )
                            figures.append(figure)
                        except Exception as exc:
                            warnings.append(f"Page {page_no} figure extraction failed: {exc}")

            # Keep figure/chart captions even when the graphic is vector-only
            # (and therefore has no embedded image stream to OCR).
            known_captions = {f.caption for f in figures if f.page == page_no}
            for caption in _captions(page_lines, ("figure", "fig.", "chart", "graph")):
                if caption and caption not in known_captions:
                    figures.append(FigureBlock(page_no, len(figures) + 1, caption=caption, method="pdf-caption"))
                    known_captions.add(caption)

            chunk = [f"===== PAGE {page_no} ====="]
            if raw:
                chunk.append(raw)
            for block in page_tables:
                chunk.append(block.text())
            for figure in figures:
                if figure.page == page_no and figure.text() not in "\n".join(chunk):
                    chunk.append(figure.text())
            page_chunks.append("\n\n".join(chunk))
    finally:
        pdf.close()

    text = _normalize_layout("\n\n".join(page_chunks))
    if not text:
        warnings.append("No extractable text or OCR text found in the PDF.")
    return DocumentExtraction(
        filename="",
        kind="pdf",
        text=_limit_text(text, warnings),
        pages=min(total_pages, MAX_PAGES),
        tables=tables,
        figures=figures,
        used_ocr=used_ocr,
        warnings=warnings,
    )


def _limit_text(text: str, warnings: list[str]) -> str:
    if len(text) <= MAX_CHARS:
        return text
    warnings.append(f"Extracted text was truncated to {MAX_CHARS:,} characters.")
    return text[:MAX_CHARS].rstrip() + "\n\n[Text truncated]"


def extract_document(filename: str, data: bytes) -> DocumentExtraction:
    """Read a supported document without network access.

    Raises ``DocumentError`` with an actionable message for unsupported or
    unreadable input.  OCR/rendering warnings are returned rather than raised
    so a text PDF still works when Tesseract or Poppler is unavailable.
    """
    name = Path(filename or "document").name
    suffix = Path(name).suffix.lower()
    if not suffix:
        if data.startswith(b"%PDF"):
            suffix = ".pdf"
        elif data.startswith(b"PK\x03\x04"):
            suffix = ".docx"
        else:
            raise DocumentError(f"Could not determine document type. Supported: {SUPPORTED_LABEL}.")
    if suffix not in SUPPORTED_EXTENSIONS:
        raise DocumentError(f"Unsupported document type {suffix!r}. Supported: {SUPPORTED_LABEL}.")
    if len(data) > MAX_FILE_BYTES:
        raise DocumentError(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    if suffix == ".pdf":
        result = _extract_pdf(data)
    elif suffix == ".docx":
        result = _extract_docx(data)
    elif suffix in {".tex", ".latex"}:
        result = _extract_latex(data)
    elif suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        result = _extract_image(data)
    else:
        result = _extract_text(data, suffix)
    result.filename = name
    result.warnings = list(dict.fromkeys(result.warnings))
    return result
