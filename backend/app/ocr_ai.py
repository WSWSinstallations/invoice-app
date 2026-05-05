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

    def money_matches(self, text: str):
        return list(re.finditer(r"\d+(?:\.\d{2})", text))

    def parse_number(self, value: str) -> float:
        try:
            return float(value)
        except:
            return 0.0

    def clean_item_description(self, line: str) -> str:
        money_values = self.money_matches(line)

        if not money_values:
            return line.strip()

        first_money_index = money_values[0].start()
        description = line[:first_money_index].strip()

        description = re.sub(r"\s{2,}", " ", description).strip()

        return description or line.strip()

    def extract_price_qty_total(self, line: str) -> tuple[float, float, float, float]:
        qty = 1.0
        price = 0.0
        total = 0.0
        confidence = 0.5

        money_values = [self.parse_number(match.group(0)) for match in self.money_matches(line)]

        def is_wholeish(value: float) -> bool:
            return abs(value - round(value)) < 0.001

        # Qty | Unit Price | Total excl VAT | RRP
        if len(money_values) >= 4:
            qty = money_values[-4]
            price = money_values[-3]
            total = money_values[-2]
            confidence = 0.9
            return round(qty, 2), round(price, 2), round(total, 2), confidence

        if len(money_values) == 3:
            first, second, third = money_values

            if abs((first * second) - third) < 0.05:
                qty = first
                price = second
                total = third
            else:
                price = first
                total = second
                qty = round(total / price, 2) if price > 0 else 1.0

            confidence = 0.85
            return round(qty, 2), round(price, 2), round(total, 2), confidence

        if len(money_values) == 2:
            first, second = money_values

            if is_wholeish(first) and first <= 100:
                qty = first
                price = second
                total = round(qty * price, 2)
            else:
                price = first
                total = second
                qty = round(total / price, 2) if price > 0 else 1.0

            confidence = 0.75
            return round(qty, 2), round(price, 2), round(total, 2), confidence

        if len(money_values) == 1:
            total = money_values[0]
            confidence = 0.55
            return qty, price, round(total, 2), confidence

        return qty, price, total, confidence

    def guess_category(self, text: str) -> str:
        lower = text.lower()

        if "cable clip" in lower or "c/clip" in lower:
            return "Electrical"

        plumbing_words = [
            "pipe", "pipes", "elbow", "bend", "valve", "drain",
            "trap", "waste", "ppr", "pvc", "copper", "fitting"
        ]

        electrical_words = [
            "conduit", "cable", "socket", "switch", "terminal", "connector"
        ]

        fixing_words = [
            "screw", "bolt", "nut", "washer", "clip", "plug"
        ]

        if any(word in lower for word in plumbing_words):
            return "Plumbing"

        if any(word in lower for word in electrical_words):
            return "Electrical"

        if any(word in lower for word in fixing_words):
            return "Fixings"

        return "Unknown"
        
    def looks_like_item(self, line: str) -> bool:
        money_values = self.money_matches(line)
        
        if len(money_values) < 2:
        return False
        
        lower = line.lower()
        
        if any(keyword in lower for keyword in [
        "invoice", "vat", "total", "tel", "mob", "email", "reg", "client"
        ]):
            return False
            
        return True

    def extract_structured_data(self, raw_text: str) -> ExtractedInvoice:
        lines = raw_text.split("\n")

        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if len(line) > 5:
                cleaned_lines.append(line)

        line_items = []

        for line in cleaned_lines:
            if not self.looks_like_item(line):
                continue
            description = self.clean_item_description(line)
            qty, price, total, confidence = self.extract_price_qty_total(line)
            category = self.guess_category(description)

            line_items.append(
                ExtractedLineItem(
                    item=description,
                    qty=qty,
                    price=price,
                    total=total,
                    category=category,
                    confidence=confidence,
                )
            )

        supplier = cleaned_lines[0] if cleaned_lines else "Unknown"

        invoice_number = None
        invoice_number_match = re.search(r"\bINV[\s-]*\d+\b", raw_text, re.IGNORECASE)
        if invoice_number_match:
            invoice_number = re.sub(r"\s+", "", invoice_number_match.group(0)).upper()

        grand_total = None
        grand_total_match = re.search(r"grand\s+total[^\d]*(\d+(?:\.\d{2}))", raw_text, re.IGNORECASE)
        if grand_total_match:
            grand_total = self.parse_number(grand_total_match.group(1))

        invoice_total = grand_total if grand_total is not None else round(sum(item.total for item in line_items), 2)

        return ExtractedInvoice(
            supplier=supplier,
            invoice_number=invoice_number,
            date=None,
            total=invoice_total,
            line_items=line_items,
        )

    def extract(self, file_path: str, content_type: str | None, project: str):
        raw_text = self.extract_text(file_path, content_type)

        if not raw_text or len(raw_text.strip()) < 10:
            print("WARNING: OCR returned little or no text")

        return self.extract_structured_data(raw_text)
