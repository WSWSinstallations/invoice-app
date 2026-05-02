from __future__ import annotations

import os
from hashlib import sha1
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class ExtractedLineItem:
    item: str
    qty: float
    price: float
    total: float
    category: str
    confidence: float


@dataclass
class ExtractedInvoice:
    supplier: str
    invoice_number: str
    invoice_date: str
    project: str
    currency: str
    total_amount: float
    confidence: float
    line_items: list[ExtractedLineItem] = field(default_factory=list)
    raw_text: str = ""


class InvoiceExtractor:
    """OCR + AI extraction boundary.

    The app ships with a deterministic placeholder so it can run anywhere.
    To integrate a real provider, use `extract_text` for OCR and replace
    `extract_structured_data` with a call that returns the same dataclass shape.
    """

    def __init__(self) -> None:
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.ai_model = os.getenv("AI_MODEL", "gpt-4.1-mini")
        self.ocr_provider = os.getenv("OCR_PROVIDER", "placeholder")

    def extract(self, file_path: str, content_type: str | None, project: str = "") -> ExtractedInvoice:
        raw_text = self.extract_text(file_path, content_type)
        return self.extract_structured_data(raw_text, file_path, project)

    def extract_text(self, file_path: str, content_type: str | None) -> str:
        file_name = Path(file_path).name
        return (
            f"Placeholder OCR output for {file_name}. "
            "Set OCR_PROVIDER and OPENAI_API_KEY to connect a real OCR/AI pipeline."
        )

    def extraction_prompt(self, raw_text: str) -> dict:
        return {
            "model": self.ai_model,
            "task": "Extract supplier, invoice number, date, project, currency, and line items.",
            "schema": {
                "supplier": "string",
                "invoice_number": "string",
                "invoice_date": "YYYY-MM-DD",
                "project": "string",
                "currency": "string",
                "line_items": [
                    {
                        "item": "string",
                        "qty": "number",
                        "price": "number",
                        "total": "number",
                        "category": "string",
                        "confidence": "0-1 number",
                    }
                ],
            },
            "raw_text": raw_text,
        }

    def extract_structured_data(self, raw_text: str, file_path: str, project: str) -> ExtractedInvoice:
        stem = Path(file_path).stem.replace("_", " ").strip()
        supplier_guess = " ".join(part.capitalize() for part in stem.split()[:2]) or "Unknown Supplier"
        invoice_number = f"INV-{int(sha1(stem.encode()).hexdigest()[:8], 16) % 100000:05d}"
        line_items = [
            ExtractedLineItem(
                item="Professional services",
                qty=1,
                price=120.00,
                total=120.00,
                category="Services",
                confidence=0.91,
            ),
            ExtractedLineItem(
                item="Materials or supplies",
                qty=2,
                price=18.50,
                total=37.00,
                category="Materials",
                confidence=0.62,
            ),
        ]
        total = round(sum(item.total for item in line_items), 2)

        return ExtractedInvoice(
            supplier=supplier_guess,
            invoice_number=invoice_number,
            invoice_date=date.today().isoformat(),
            project=project or os.getenv("DEFAULT_PROJECT", "General"),
            currency=os.getenv("DEFAULT_CURRENCY", "EUR"),
            total_amount=total,
            confidence=0.74,
            line_items=line_items,
            raw_text=raw_text,
        )
