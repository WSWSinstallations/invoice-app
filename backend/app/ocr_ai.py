from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

import pytesseract
from PIL import Image


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
    supplier: Optional[str]
    invoice_number: Optional[str]
    date: Optional[str]
    total: Optional[float]
    line_items: List[ExtractedLineItem]


class InvoiceExtractor:
    NON_ITEM_KEYWORDS = (
        "invoice",
        "receipt",
        "date",
        "page",
        "customer",
        "supplier",
        "address",
        "tel",
        "email",
        "@",
        "vat",
        "v.a.t",
        "reg no",
        "reg. no",
        "subtotal",
        "sub total",
        "grand total",
        "total due",
        "amount due",
        "balance due",
        "payment",
        "terms",
        "description",
        "quantity",
        "unit price",
        "price total",
        "total excl",
        "rrp",
    )

    def extract_text(self, file_path: str, content_type: str | None) -> str:
        try:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img)

            print("OCR TEXT START ----------------")
            print(text)
            print("OCR TEXT END ----------------")

            return text

        except Exception as e:
            print("OCR FAILED:", e)
            return ""

    def clean_lines(self, raw_text: str) -> list[str]:
        cleaned_lines = []

        for line in raw_text.split("\n"):
            cleaned = " ".join(line.strip().split())

            if len(cleaned) > 5:
                cleaned_lines.append(cleaned)

        return cleaned_lines

    def money_matches(self, text: str):
        return list(re.finditer(r"(?<![A-Za-z])\d{1,6}(?:[,.]\d{2})(?![A-Za-z])", text))

    def parse_number(self, value: str) -> float:
        try:
            return float(value.replace(",", "."))
        except (TypeError, ValueError):
            return 0.0

    def close_money(self, left: float, right: float) -> bool:
        return abs(left - right) <= max(0.05, abs(right) * 0.01)

    def column_numbers(self, line: str) -> list[float]:
        money_values = self.money_matches(line)
        numbers = [self.parse_number(match.group(0)) for match in money_values]

        if len(numbers) >= 4:
            return numbers[-4:]

        return numbers

    def clean_item_description(self, line: str) -> str:
        money_values = self.money_matches(line)

        if not money_values:
            return line.strip()

        first_money_index = money_values[0].start()
        description = line[:first_money_index].strip()

        description = re.sub(r"\s{2,}", " ", description)
        description = re.sub(r"[\s|:;-]+$", "", description).strip()

        return description or line.strip()

    def is_admin_line(self, line: str) -> bool:
        lower = line.lower()

        if any(keyword in lower for keyword in self.NON_ITEM_KEYWORDS):
            return True

        return bool(re.fullmatch(r"[\d\s.,:/\\€$£+-]+", line))

    def looks_like_item(self, line: str) -> bool:
        if self.is_admin_line(line):
            return False

        money_values = self.money_matches(line)
        if len(money_values) < 2:
            return False

        description = self.clean_item_description(line)
        letters = re.sub(r"[^A-Za-z]", "", description)

        if len(letters) < 2:
            return False

        qty, price, total, _ = self.extract_price_qty_total(line)

        return qty > 0 and price > 0 and total > 0

    def extract_price_qty_total(self, line: str) -> tuple[float, float, float, float]:
        qty = 1.0
        price = 0.0
        total = 0.0
        confidence = 0.5

        numbers = self.column_numbers(line)

        # Qty | Unit Price | Total excl VAT | RRP
        if len(numbers) >= 4:
            qty = numbers[-4]
            price = numbers[-3]
            total = numbers[-2]
            confidence = 0.9
            return round(qty, 2), round(price, 2), round(total, 2), confidence

        if len(numbers) == 3:
            first, second, third = numbers

            if self.close_money(first * second, third):
                qty = first
                price = second
                total = third
            else:
                price = first
                total = second
                qty = round(total / price, 2) if price > 0 else 1.0

            confidence = 0.85
            return round(qty, 2), round(price, 2), round(total, 2), confidence

        if len(numbers) == 2:
            first, second = numbers

            if first > 0 and second >= first:
                price = first
                total = second
                qty = round(total / price, 2)
            else:
                qty = first
                price = second
                total = round(qty * price, 2)

            confidence = 0.7
            return round(qty, 2), round(price, 2), round(total, 2), confidence

        return qty, price, total, confidence

    def guess_category(self, text: str) -> str:
        lower = text.lower()

        if "cable clip" in lower or "c/clip" in lower:
            return "Electrical"

        if any(word in lower for word in ["pipe", "drain", "pvc", "fitting"]):
            return "Plumbing"

        if any(word in lower for word in ["cable", "socket", "switch"]):
            return "Electrical"

        if any(word in lower for word in ["screw", "bolt", "clip"]):
            return "Fixings"

        return "Unknown"

    def extract_structured_data(self, raw_text: str) -> ExtractedInvoice:
        cleaned_lines = self.clean_lines(raw_text)

        # --- Metadata extraction ---
        invoice_number = None
        date = None
        total = None

        for line in cleaned_lines:
            lower = line.lower()

            if "invoice number" in lower:
                match = re.search(r"inv[\w\d]+", line, re.IGNORECASE)
                if match:
                    invoice_number = match.group(0)

            if "invoice date" in lower:
                match = re.search(r"\d{2}/\d{2}/\d{4}", line)
                if match:
                    date = match.group(0)

            if "grand total" in lower:
                nums = self.money_matches(line)
                if nums:
                    total = self.parse_number(nums[-1].group(0))

        line_items = []

        for line in cleaned_lines:
            if not self.looks_like_item(line):
                continue

            description = self.clean_item_description(line)
            qty, price, item_total, confidence = self.extract_price_qty_total(line)
            category = self.guess_category(description)

            line_items.append(
                ExtractedLineItem(
                    item=description,
                    qty=qty,
                    price=price,
                    total=item_total,
                    category=category,
                    confidence=confidence,
                )
            )

        supplier = cleaned_lines[0] if cleaned_lines else "Unknown"

        return ExtractedInvoice(
            supplier=supplier,
            invoice_number=invoice_number,
            date=date,
            total=total,
            line_items=line_items,
        )

    def extract(self, file_path: str, content_type: str | None, project: str):
        raw_text = self.extract_text(file_path, content_type)

        if not raw_text or len(raw_text.strip()) < 10:
            print("WARNING: OCR returned little or no text")

        return self.extract_structured_data(raw_text)