from dataclasses import dataclass
from typing import List, Optional
import re

import pytesseract
from PIL import Image, ImageOps


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
    line_items: List[ExtractedLineItem]


class InvoiceExtractor:
    def __init__(self):
        pass

    def extract_text(self, file_path: str, content_type: str | None) -> str:
        try:
            if content_type and "pdf" in content_type.lower():
                print("OCR FAILED: PDF uploads are not supported yet.")
                return ""

            image = Image.open(file_path)
            image = ImageOps.exif_transpose(image)

            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")

            text = pytesseract.image_to_string(image)

            print("OCR TEXT START ----------------")
            print(text)
            print("OCR TEXT END ----------------")

            return text or ""

        except Exception as error:
            print("OCR FAILED:", error)
            return ""

    def clean_lines(self, raw_text: str) -> list[str]:
        lines = []

        for line in raw_text.split("\n"):
            cleaned = " ".join(line.strip().split())

            if len(cleaned) >= 4:
                lines.append(cleaned)

        return lines

    def guess_supplier(self, lines: list[str]) -> str:
        if not lines:
            return "Unknown supplier"

        # Usually supplier is near the top of an invoice.
        for line in lines[:8]:
            lower = line.lower()

            if any(word in lower for word in ["invoice", "date", "vat", "tel", "email", "page"]):
                continue

            if len(line) >= 5:
                return line

        return lines[0]

    def guess_invoice_number(self, lines: list[str]) -> str:
        patterns = [
            r"(?:invoice|inv|doc|receipt)\s*(?:no|number|#)?\s*[:\-]?\s*([A-Z0-9\-\/]+)",
            r"\bINV[-\s]?[A-Z0-9\-\/]+\b",
        ]

        for line in lines:
            for pattern in patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(1) if match.groups() else match.group(0)

        return ""

    def guess_date(self, lines: list[str]) -> str:
        date_patterns = [
            r"\b(\d{4}-\d{2}-\d{2})\b",
            r"\b(\d{2}/\d{2}/\d{4})\b",
            r"\b(\d{2}-\d{2}-\d{4})\b",
            r"\b(\d{2}\.\d{2}\.\d{4})\b",
        ]

        for line in lines:
            for pattern in date_patterns:
                match = re.search(pattern, line)
                if match:
                    value = match.group(1)

                    # Convert common formats to YYYY-MM-DD where possible.
                    if "/" in value:
                        day, month, year = value.split("/")
                        return f"{year}-{month}-{day}"

                    if "." in value:
                        day, month, year = value.split(".")
                        return f"{year}-{month}-{day}"

                    if "-" in value and value[2] == "-":
                        day, month, year = value.split("-")
                        return f"{year}-{month}-{day}"

                    return value

        return ""

    def guess_currency(self, raw_text: str) -> str:
        text = raw_text.upper()

        if "€" in text or "EUR" in text:
            return "EUR"

        if "£" in text or "GBP" in text:
            return "GBP"

        if "$" in text or "USD" in text:
            return "USD"

        return "EUR"

    def parse_number(self, value: str) -> float:
        try:
            value = value.replace(",", ".")
            return float(value)
        except Exception:
            return 0.0

    def guess_total_amount(self, lines: list[str]) -> float:
        total_candidates = []

        for line in lines:
            lower = line.lower()

            if any(word in lower for word in ["total", "amount due", "balance due", "grand total"]):
                numbers = re.findall(r"\d+(?:[.,]\d{1,2})?", line)

                if numbers:
                    total_candidates.append(self.parse_number(numbers[-1]))

        if total_candidates:
            return max(total_candidates)

        return 0.0

    def guess_category(self, text: str) -> str:
        lower = text.lower()

        plumbing_words = [
            "pipe",
            "elbow",
            "bend",
            "valve",
            "drain",
            "trap",
            "waste",
            "ppr",
            "pvc",
            "copper",
            "fitting",
            "bush",
            "reducer",
            "hopper",
        ]

        electrical_words = [
            "conduit",
            "cable",
            "socket",
            "switch",
            "breaker",
            "mcb",
            "rcd",
            "terminal",
            "box",
            "trunking",
            "db",
            "connector",
        ]

        fixing_words = [
            "screw",
            "bolt",
            "nut",
            "washer",
            "clip",
            "plug",
            "anchor",
            "fixing",
        ]

        if any(word in lower for word in plumbing_words):
            return "Plumbing"

        if any(word in lower for word in electrical_words):
            return "Electrical"

        if any(word in lower for word in fixing_words):
            return "Fixings"

        return "Unknown"

    def extract_line_items(self, lines: list[str]) -> list[ExtractedLineItem]:
        line_items = []

        skip_words = [
            "invoice",
            "receipt",
            "date",
            "subtotal",
            "sub total",
            "vat",
            "tax",
            "grand total",
            "total due",
            "amount due",
            "tel",
            "email",
            "address",
            "page",
        ]

        for line in lines:
            lower = line.lower()

            if any(word in lower for word in skip_words):
                continue

            has_letters = bool(re.search(r"[A-Za-z]", line))
            if not has_letters:
                continue

            numbers = re.findall(r"\d+(?:[.,]\d{1,2})?", line)

            qty = 1.0
            price = 0.0
            total = 0.0
            confidence = 0.45

            if len(numbers) >= 3:
                qty = self.parse_number(numbers[-3])
                price = self.parse_number(numbers[-2])
                total = self.parse_number(numbers[-1])
                confidence = 0.6
            elif len(numbers) == 2:
                price = self.parse_number(numbers[-2])
                total = self.parse_number(numbers[-1])
                confidence = 0.5

            line_items.append(
                ExtractedLineItem(
                    item=line,
                    qty=qty,
                    price=price,
                    total=total,
                    category=self.guess_category(line),
                    confidence=confidence,
                )
            )

        if not line_items:
            line_items.append(
                ExtractedLineItem(
                    item="OCR did not find readable line items - please review manually",
                    qty=1,
                    price=0,
                    total=0,
                    category="Unknown",
                    confidence=0.1,
                )
            )

        return line_items

    def extract_structured_data(self, raw_text: str, project: str) -> ExtractedInvoice:
        lines = self.clean_lines(raw_text)

        if not lines:
            return ExtractedInvoice(
                supplier="Unknown supplier",
                invoice_number="",
                invoice_date="",
                project=project or "General",
                currency="EUR",
                total_amount=0.0,
                confidence=0.1,
                line_items=[
                    ExtractedLineItem(
                        item="OCR failed - please enter invoice manually",
                        qty=1,
                        price=0,
                        total=0,
                        category="Unknown",
                        confidence=0.1,
                    )
                ],
            )

        supplier = self.guess_supplier(lines)
        invoice_number = self.guess_invoice_number(lines)
        invoice_date = self.guess_date(lines)
        currency = self.guess_currency(raw_text)
        total_amount = self.guess_total_amount(lines)
        line_items = self.extract_line_items(lines)

        if total_amount <= 0:
            total_amount = round(sum(item.total for item in line_items), 2)

        confidence = 0.55

        if supplier and supplier != "Unknown supplier":
            confidence += 0.1

        if invoice_date:
            confidence += 0.1

        if invoice_number:
            confidence += 0.1

        if line_items:
            confidence += 0.1

        confidence = min(confidence, 0.85)

        return ExtractedInvoice(
            supplier=supplier,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            project=project or "General",
            currency=currency,
            total_amount=round(total_amount or 0, 2),
            confidence=confidence,
            line_items=line_items,
        )

    def extract(self, file_path: str, content_type: str | None, project: str) -> ExtractedInvoice:
        raw_text = self.extract_text(file_path, content_type)

        if not raw_text or len(raw_text.strip()) < 10:
            print("WARNING: OCR returned little or no text")

        return self.extract_structured_data(raw_text, project)
