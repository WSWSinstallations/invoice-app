from __future__ import annotations

from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from app.storage import resolve_path


def _draw_wrapped_text(pdf_canvas, text: str, x: float, y: float, max_chars: int = 92) -> float:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        proposed = f"{current} {word}".strip()
        if len(proposed) > max_chars:
            lines.append(current)
            current = word
        else:
            current = proposed
    if current:
        lines.append(current)

    for line in lines:
        pdf_canvas.drawString(x, y, line)
        y -= 13
    return y


def generate_invoice_pdf(invoice, output_path: str | Path) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    pdf.setTitle(f"Invoice {invoice.invoice_number or invoice.id}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(0.7 * inch, height - 0.7 * inch, "Corrected invoice image")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(0.7 * inch, height - 0.95 * inch, invoice.original_filename or "Uploaded invoice")

    source_path = resolve_path(invoice.original_path)
    image_top = height - 1.25 * inch
    image_bottom = 0.65 * inch
    max_width = width - 1.4 * inch
    max_height = image_top - image_bottom

    try:
        with PILImage.open(source_path) as image:
            image_width, image_height = image.size
        scale = min(max_width / image_width, max_height / image_height)
        draw_width = image_width * scale
        draw_height = image_height * scale
        x = (width - draw_width) / 2
        y = image_bottom + (max_height - draw_height) / 2
        pdf.drawImage(
            ImageReader(str(source_path)),
            x,
            y,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            mask="auto",
        )
    except Exception:
        pdf.setFont("Helvetica", 11)
        y = height - 1.6 * inch
        y = _draw_wrapped_text(
            pdf,
            "The corrected invoice image is stored with this invoice, but it could not be rendered in the PDF preview.",
            0.7 * inch,
            y,
        )
        pdf.drawString(0.7 * inch, y - 8, f"Stored file: {invoice.original_path}")

    pdf.showPage()

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(0.7 * inch, height - 0.7 * inch, "Structured invoice data")
    pdf.setFont("Helvetica", 10)
    metadata = [
        ("Supplier", invoice.supplier),
        ("Invoice number", invoice.invoice_number),
        ("Date", invoice.invoice_date),
        ("Project", invoice.project),
        ("Currency", invoice.currency),
        ("Total", f"{invoice.total_amount:.2f}"),
        ("Status", invoice.status),
    ]

    y = height - 1.05 * inch
    for label, value in metadata:
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(0.7 * inch, y, f"{label}:")
        pdf.setFont("Helvetica", 9)
        pdf.drawString(1.75 * inch, y, str(value or ""))
        y -= 14

    table_data = [["Item", "Qty", "Price", "Total", "Category", "Confidence"]]
    visible_items = list(invoice.line_items[:24])
    for line in visible_items:
        table_data.append(
            [
                line.item[:42],
                f"{line.qty:g}",
                f"{line.price:.2f}",
                f"{line.total:.2f}",
                line.category[:18],
                f"{round(line.confidence * 100)}%",
            ]
        )
    if len(invoice.line_items) > len(visible_items):
        table_data.append(["More rows in Excel export", "", "", "", "", ""])

    table = Table(table_data, colWidths=[2.25 * inch, 0.55 * inch, 0.75 * inch, 0.75 * inch, 1.1 * inch, 0.75 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6F4F1")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#102A2A")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B8C9C6")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAF9")]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    table_width, table_height = table.wrapOn(pdf, width - 1.4 * inch, height)
    table.drawOn(pdf, 0.7 * inch, max(0.65 * inch, y - table_height - 12))
    pdf.save()
