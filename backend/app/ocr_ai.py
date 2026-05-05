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

    def clean_lines(self, raw_text: str) -> list[str]:
        cleaned_lines = []

        for line in raw_text.split("\n"):
            cleaned = " ".join(line.strip().split())

            if len(cleaned) > 5:
                cleaned_lines.append(cleaned)

        return cleaned_lines

    def money_matches(self, text: str):
        return list(re.finditer(r"\d+(?:[,.]\d{2})", text))

    def parse_number(self, value: str) -> float:
        try:
            return float(str(value).replace(",", "."))
        except:
            return 0.0

    def close_money(self, left: float, right: float) -> bool:
        return abs(left - right) <= max(0.05, abs(right) * 0.01)

    def clean_supplier(self, supplier: str, raw_text: str = "") -> str:
        combined = f"{supplier} {raw_text}".lower()

        if "master enterprise" in combined:
            return "Master Enterprise Company Limited"

        cleaned = supplier.strip()
        cleaned = re.sub(r"^[^A-Za-z]+", "", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

        return cleaned or "Unknown"

    def extract_supplier(self, cleaned_lines: list[str], raw_text: str) -> str:
        raw_lower = raw_text.lower()

        if "master enterprise" in raw_lower:
            return "Master Enterprise Company Limited"

        supplier = "Unknown"

        for line in cleaned_lines[:20]:
            lower = line.lower()

            if any(keyword in lower for keyword in [
                "limited", "ltd", "company", "enterprise", "supplies", "hardware"
            ]):
                supplier = line
                break

        if supplier == "Unknown" and cleaned_lines:
            supplier = cleaned_lines[0]

        return self.clean_supplier(supplier, raw_text)

    def extract_invoice_number(self, raw_text: str) -> Optional[str]:
        match = re.search(r"\bINV[\s-]*\d+\b", raw_text, re.IGNORECASE)

        if match:
            return re.sub(r"[\s-]+", "", match.group(0)).upper()

        return None

    def extract_invoice_date(self, raw_text: str) -> Optional[str]:
        match = re.search(r"\b\d{2}/\d{2}/\d{4}\b", raw_text)

        if match:
            return match.group(0)

        return None

    def extract_grand_total(self, raw_text: str) -> Optional[float]:
        patterns = [
            r"grand\s+total[^\d]*(\d+(?:[,.]\d{2}))",
            r"total\s+inc\s+vat[^\d]*(\d+(?:[,.]\d{2}))",
            r"total\s+due[^\d]*(\d+(?:[,.]\d{2}))",
            r"amount\s+due[^\d]*(\d+(?:[,.]\d{2}))",
        ]

        for pattern in patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)

            if match:
                return self.parse_number(match.group(1))

        return None

    def clean_item_description(self, line: str) -> str:
        money_values = self.money_matches(line)

        if not money_values:
            return line.strip()

        first_money_index = money_values[0].start()
        description = line[:first_money_index].strip()

        description = re.sub(r"\s{2,}", " ", description)
        description = re.sub(r"[\s|:;-]+$", "", description)

        return description.strip()

    def extract_price_qty_total(self, line: str) -> tuple[float, float, float, float]:
        qty = 1.0
        price = 0.0
        total = 0.0
        confidence = 0.5

        money_values = [self.parse_number(match.group(0)) for match in self.money_matches(line)]

        def is_wholeish(value: float) -> bool:
            return abs(value - round(value)) < 0.001

        # Master Enterprise layout:
        # Qty | Unit Price | Total excl VAT | RRP
        # Example:
        # 3.00 3.91 11.73 5.26
        # 1.00 2.76 2.76 3.73
        if len(money_values) >= 4:
            qty = money_values[-4]
            price = money_values[-3]
            total = money_values[-2]
            confidence = 0.9
            return round(qty, 2), round(price, 2), round(total, 2), confidence

        if len(money_values) == 3:
            first, second, third = money_values

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

        if len(money_values) == 2:
            first, second = money_values

            if is_wholeish(first) and first <= 500:
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

        if total == 0 and price > 0:
            total = price

        return qty, price, total, confidence

    def guess_category(self, text: str) -> str:
        lower = text.lower()

        plumbing_words = [
            "pipe",
            "pipes",
            "d/pipe",
            "drain",
            "floor drain",
            "hopper",
            "easybend",
            "bend",
            "elbow",
            "valve",
            "trap",
            "waste",
            "ppr",
            "pvc",
            "copper",
            "fitting",
            "fittings",
            "reducer",
            "bush",
        ]

        electrical_words = [
            "cable",
            "c/clip",
            "cable clip",
            "clip round",
            "conduit",
            "socket",
            "switch",
            "terminal",
            "connector",
            "connectors",
            "wire",
            "wiring",
            "mcb",
            "rcd",
            "breaker",
            "db",
            "trunking",
            "tee box",
            "u box",
            "box",
        ]

        fixing_words = [
            "screw",
            "screws",
            "bolt",
            "nut",
            "washer",
            "plug",
            "anchor",
            "fixing",
            "galvanised",
        ]

        if any(word in lower for word in plumbing_words):
            return "Plumbing"

        if any(word in lower for word in electrical_words):
            return "Electrical"

        if any(word in lower for word in fixing_words):
            return "Fixings"

        return "Unknown"

    def is_admin_line(self, line: str) -> bool:
        lower = line.lower()

        admin_keywords = [
            "invoice",
            "vat",
            "v.a.t",
            "total",
            "grand total",
            "total exc",
            "total inc",
            "discount",
            "tel",
            "mob",
            "email",
            "@",
            "reg",
            "client",
            "date",
            "page",
            "address",
            "operator",
            "reference",
            "remarks",
            "signature",
            "credit period",
            "returns",
            "bank details",
            "iban",
            "swift",
            "id card",
            "name in block",
            "contact number",
            "item code",
            "item description",
            "quantity",
            "unit price",
            "disc",
            "rrp",
        ]

        if any(keyword in lower for keyword in admin_keywords):
            return True

        return bool(re.fullmatch(r"[\d\s.,:/\\€$£+-]+", line))

    def looks_like_item(self, line: str) -> bool:
        if self.is_admin_line(line):
            return False

        money_values = self.money_matches(line)

        if len(money_values) < 2:
            return False

        letters = re.sub(r"[^A-Za-z]", "", line)

        if len(letters) < 3:
            return False

        qty, price, total, _ = self.extract_price_qty_total(line)

        if qty <= 0 or price < 0 or total <= 0:
            return False

        return True

    def extract_line_items_from_single_lines(self, cleaned_lines: list[str]) -> list[ExtractedLineItem]:
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

        return line_items

    def extract_line_items_from_compact_text(self, raw_text: str) -> list[ExtractedLineItem]:
        normalized = " ".join(raw_text.split())
        line_items = []

        row_pattern = re.compile(
            r"(?P<code>[A-Z0-9][A-Z0-9\-\/]{2,})\s+"
            r"(?P<desc>[A-Za-z][A-Za-z0-9\s\/\.\-\(\)\"']{3,}?)\s+"
            r"(?P<qty>\d{1,4}(?:[,.]\d{2}))\s+"
            r"(?P<price>\d{1,6}(?:[,.]\d{2}))\s+"
            r"(?P<total>\d{1,6}(?:[,.]\d{2}))"
            r"(?:\s+\d{1,6}(?:[,.]\d{2}))?",
            re.IGNORECASE,
        )

        for match in row_pattern.finditer(normalized):
            code = match.group("code").strip()
            desc = match.group("desc").strip()

            item_text = f"{code} {desc}"
            item_text = re.sub(r"\s{2,}", " ", item_text).strip()

            if self.is_admin_line(item_text):
                continue

            qty = self.parse_number(match.group("qty"))
            price = self.parse_number(match.group("price"))
            total = self.parse_number(match.group("total"))

            if qty <= 0 or price <= 0 or total <= 0:
                continue

            line_items.append(
                ExtractedLineItem(
                    item=item_text,
                    qty=round(qty, 2),
                    price=round(price, 2),
                    total=round(total, 2),
                    category=self.guess_category(item_text),
                    confidence=0.9,
                )
            )

        return line_items

    def deduplicate_line_items(self, line_items: list[ExtractedLineItem]) -> list[ExtractedLineItem]:
        deduped = []
        seen = set()

        for item in line_items:
            key = (
                item.item.lower().strip(),
                round(item.qty, 2),
                round(item.price, 2),
                round(item.total, 2),
            )

            if key in seen:
                continue

            seen.add(key)
            deduped.append(item)

        return deduped

    def extract_structured_data(self, raw_text: str) -> ExtractedInvoice:
        cleaned_lines = self.clean_lines(raw_text)

        supplier = self.extract_supplier(cleaned_lines, raw_text)
        invoice_number = self.extract_invoice_number(raw_text)
        date = self.extract_invoice_date(raw_text)
        grand_total = self.extract_grand_total(raw_text)

        line_items = self.extract_line_items_from_single_lines(cleaned_lines)

        if not line_items:
            line_items = self.extract_line_items_from_compact_text(raw_text)

        line_items = self.deduplicate_line_items(line_items)

        invoice_total = (
            round(grand_total, 2)
            if grand_total is not None
            else round(sum(item.total for item in line_items), 2)
            if line_items
            else None
        )

        print("DETECTED SUPPLIER:", supplier)
        print("DETECTED INVOICE NUMBER:", invoice_number)
        print("DETECTED DATE:", date)
        print("DETECTED TOTAL:", invoice_total)
        print("DETECTED ITEMS:", len(line_items))

        for item in line_items[:10]:
            print(item)

        return ExtractedInvoice(
            supplier=supplier,
            invoice_number=invoice_number,
            date=date,
            total=invoice_total,
            line_items=line_items,
        )

    def extract(self, file_path: str, content_type: str | None, project: str):
        raw_text = self.extract_text(file_path, content_type)

        if not raw_text or len(raw_text.strip()) < 10:
            print("WARNING: OCR returned little or no text")

        return self.extract_structured_data(raw_text)
