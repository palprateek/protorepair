"""Document-ingestion tests: PDF, DOCX, LaTeX, OCR, and tables."""
from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

from protorepair.documents import DocumentError, extract_document
from protorepair.parser import normalize_units_text, parse_text
from protorepair.pipeline import run_pipeline


def _sample_docx_bytes() -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading("NMC811 protocol", level=1)
    doc.add_paragraph(
        "1. Mix 95 wt% NMC811, 3 wt% Super C65 carbon black, and 2 wt% PVDF in NMP."
    )
    doc.add_paragraph(
        "2. Coat to a total dry loading of 21 mg/cm², corresponding to ~2.0 mAh/cm² at 200 mAh/g."
    )
    table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "Material"
    table.cell(0, 1).text = "wt%"
    table.cell(0, 2).text = "Water ppm"
    table.cell(1, 0).text = "NMC811"
    table.cell(1, 1).text = "95"
    table.cell(1, 2).text = "200"
    doc.add_paragraph("Figure 1. Capacity versus cycle number for the NMC811 cathode.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _sample_pdf_bytes() -> bytes | None:
    pytest.importorskip("reportlab")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter)
    styles = getSampleStyleSheet()
    rows = [["Material", "wt%", "Water ppm"], ["NMC811", "95", "200"]]
    table = Table(rows)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    story = [
        Paragraph("NMC811 protocol", styles["Title"]),
        Paragraph(
            "1. Mix 95 wt% NMC811, 3 wt% Super C65 carbon black, and 2 wt% PVDF in NMP.",
            styles["BodyText"],
        ),
        Paragraph(
            "2. Coat to a total dry loading of 21 mg/cm², corresponding to ~2.0 mAh/cm² at 200 mAh/g.",
            styles["BodyText"],
        ),
        Spacer(1, 8),
        table,
        Spacer(1, 8),
        Paragraph("Figure 1. Capacity versus cycle number.", styles["BodyText"]),
    ]
    doc.build(story)
    return buf.getvalue()


def test_docx_reader_extracts_tables_and_caption():
    d = extract_document("protocol.docx", _sample_docx_bytes())
    assert d.kind == "docx"
    assert "21 mg/cm²" in d.text
    assert len(d.tables) == 1
    assert "NMC811" in d.tables[0].markdown()
    assert d.figures and "Capacity versus cycle number" in d.figures[0].caption


def test_tex_reader_normalizes_siunitx_tables_and_equation_text():
    tex = r"""
    \documentclass{article}
    \begin{document}
    \section{NMC811 protocol}
    1. Mix 95 wt\% NMC811, 3 wt\% Super C65, and 2 wt\% PVDF in NMP.
    2. Coat to \SI{21}{mg/cm^2}, corresponding to \SI{2.0}{mAh/cm^2} at \SI{200}{mAh/g}.
    \begin{tabular}{lll}
    Material & wt\% & Water ppm \\
    \hline
    NMC811 & 95 & 200 \\
    Carbon & 3 & 500 \\
    PVDF & 2 & 2000 \\
    \end{tabular}
    Figure 1. Capacity versus cycle number.
    \end{document}
    """
    d = extract_document("protocol.tex", tex.encode())
    assert d.kind == "latex"
    assert "21 mg/cm²" in d.text
    assert "200 mAh/g" in d.text
    assert d.tables and "Carbon" in d.tables[0].markdown()
    assert d.figures and "Capacity" in d.figures[0].caption
    recipe = parse_text(d.text)
    assert recipe.composition.nmc811_wt == 95
    assert recipe.electrode.total_loading_mg_cm2 == 21
    assert recipe.electrode.areal_capacity_mAh_cm2 == 2.0


def test_pdf_reader_extracts_text_table_and_figure_caption():
    data = _sample_pdf_bytes()
    if data is None:
        pytest.skip("reportlab unavailable")
    d = extract_document("protocol.pdf", data)
    assert d.kind == "pdf"
    assert d.pages == 1
    assert "21 mg/cm²" in d.text
    assert any("NMC811" in table.markdown() for table in d.tables)
    assert any("Capacity versus cycle number" in f.caption for f in d.figures)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_image_reader_uses_ocr():
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1200, 240), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    draw.text((30, 40), "NMC811 95 wt%", fill="black", font=font)
    draw.text((30, 120), "21 mg/cm2 at 200 mAh/g", fill="black", font=font)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    d = extract_document("scan.png", buf.getvalue())
    assert d.kind == "image"
    assert d.used_ocr is True
    assert "NMC811" in d.text


@pytest.mark.skipif(
    shutil.which("tesseract") is None or shutil.which("pdftoppm") is None,
    reason="tesseract/poppler not installed",
)
def test_scanned_pdf_uses_ocr():
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1200, 500), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=44)
    draw.text((40, 60), "NMC811 95 wt%", fill="black", font=font)
    draw.text((40, 160), "21 mg/cm2 at 200 mAh/g", fill="black", font=font)
    draw.text((40, 260), "Electrolyte 80 uL", fill="black", font=font)
    buf = io.BytesIO()
    image.save(buf, format="PDF")
    d = extract_document("scan.pdf", buf.getvalue())
    assert d.kind == "pdf"
    assert d.pages == 1
    assert d.used_ocr is True
    assert "NMC811" in d.text


def test_parser_normalizes_latex_style_units_and_keeps_source_text():
    text = "1. Coat to a total dry loading of 21 mg cm^-2 at 200 mA h/g.\n2. Dry at 80 C."
    recipe = parse_text(text)
    assert recipe.text == text
    assert recipe.electrode.total_loading_mg_cm2 == 21
    assert recipe.electrode.specific_capacity_mAh_g == 200
    assert "mg/cm²" in normalize_units_text(text)


def test_document_metadata_flows_to_export():
    d = extract_document("protocol.docx", _sample_docx_bytes())
    result = run_pipeline(text=d.text, source_document=d.summary())
    assert result.source_document["filename"] == "protocol.docx"
    assert result.source_document["tables"] == 1


def test_table_only_docx_feeds_composition_and_water_checks():
    from docx import Document

    doc = Document()
    table = doc.add_table(rows=4, cols=3)
    for i, row in enumerate(
        [
            ["Material", "wt%", "Water ppm"],
            ["NMC811", "95", "200"],
            ["Carbon", "3", "500"],
            ["PVDF", "2", "2000"],
        ]
    ):
        for j, value in enumerate(row):
            table.cell(i, j).text = value
    buf = io.BytesIO()
    doc.save(buf)
    d = extract_document("table-only.docx", buf.getvalue())
    result = run_pipeline(text=d.text)
    assert result.recipe.composition.nmc811_wt == 95
    assert result.recipe.composition.carbon_wt == 3
    assert result.recipe.composition.binder_wt == 2
    assert result.recipe.water_ppm == {"NMC811": 200, "carbon": 500, "PVDF": 2000}
    assert "C1 water values" not in result.recipe.missing_fields


def test_parameter_table_feeds_loading_and_volume():
    from docx import Document

    doc = Document()
    table = doc.add_table(rows=5, cols=2)
    rows = [
        ["Parameter", "Value"],
        ["Total dry loading", "21 mg/cm²"],
        ["Areal capacity", "2.0 mAh/cm²"],
        ["Specific capacity", "200 mAh/g"],
        ["Electrolyte volume", "80 µL"],
    ]
    for i, row in enumerate(rows):
        for j, value in enumerate(row):
            table.cell(i, j).text = value
    buf = io.BytesIO()
    doc.save(buf)
    d = extract_document("parameters.docx", buf.getvalue())
    result = run_pipeline(text=d.text)
    assert result.recipe.electrode.total_loading_mg_cm2 == 21
    assert result.recipe.electrode.areal_capacity_mAh_cm2 == 2.0
    assert result.recipe.electrode.specific_capacity_mAh_g == 200
    assert result.recipe.electrolyte.volume_uL == 80


def test_unsupported_document_error():
    with pytest.raises(DocumentError):
        extract_document("protocol.xlsx", b"not a spreadsheet")


def test_cli_document_path(tmp_path, capsys):
    from protorepair.cli import main

    path = tmp_path / "protocol.docx"
    path.write_bytes(_sample_docx_bytes())
    assert main(["--document", str(path), "--json"]) == 0
    out = capsys.readouterr().out
    assert '"source_document"' in out
    assert '"filename": "protocol.docx"' in out
