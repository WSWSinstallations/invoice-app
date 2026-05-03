from dataclasses import dataclass
from typing import List
import re

import pytesseract
from PIL import Image, ImageOps


try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception as error:
    print(f"HEIC support not available in OCR module: {error}")


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
            print(f"OCR FILE PATH: {file_path}")
            print(f"OCR CONTENT TYPE: {content_type}")

            if content_type and "pdf" in content_type.lower():
                print("OCR FAILED: PDF uploads are not supported yet.")
                return ""

            image = Image.open(file_path)
            image = ImageOps.exif_transpose(image)

            if image.width > image.height:
                image = image.rotate(90, expand=True)

            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")

            print(f"OCR IMAGE SIZE: {image.size}")
            print(f"OCR IMAGE MODE: {image.mode}")

            text = pytesseract.image_to_string(image)

            if not text or len(text.strip()) < 10:
                print("OCR TEXT SHORT - RETRYING WITH PSM 6")
                text = pytesseract.image_to_string(image, config="--psm 6")

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

    def is_admin_line(self, line: str) -> bool:
        lower = line.lower()

        admin_words = [
            "master enterprise company",
            "ammonry",
            "malta",
            "for all kinds of",
            "electrical cables & wiring accessories",
            "water drain pipes",
            "v.a.t",
            "vat",
            "reg no",
            "reg. no",
            "exemption",
            "tel",
            "email",
            "@",
            "invoice",
            "receipt",
            "date",
            "page",
            "address",
            "customer",
            "supplier",
            "company limited",
            "limited",
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
        ]

        return any(word in lower for word in admin_words)

    def guess_supplier(self, lines: list[str]) -> str:
        if not lines:
            return "Unknown supplier"

        for line in lines[:12]:
            lower = line.lower()

            if "master enterprise" in lower:
                return "Master Enterprise Company Limited"

        for line in lines[:10]:
            lower = line.lower()

            if self.is_admin_line(line):
                if "master enterprise" not in lower:
                    continue

            if len(line) >= 5:
                return line

        return "Unknown supplier"

    def valid_invoice_candidate(self, value: str) -> bool:
        value = value.strip().strip(":").strip("-").strip()

        if not value:
            return False

        banned = {
            "date",
            "invoice",
            "number",
            "no",
            "page",
            "vat",
            "total",
            "customer",
            "supplier",
        }

        if value.lower() in banned:
            return False

        # Invoice numbers usually contain at least one digit.
        return any(char.isdigit() for char in value)

    def guess_invoice_number(self, lines: list[str]) -> str:
        label_patterns = [
            r"(?:invoice\s*(?:no|number|#)|inv\s*(?:no|number|#)|doc\s*(?:no|number|#)|receipt\s*(?:no|number|#))\s*[:\-]?\s*([A-Z0-9\-\/]+)",
            r"\b(INV[-\s]?[A-Z0-9\-\/]+)\b",
        ]

        for line in lines:
            for pattern in label_patterns:
                match = re.search(pattern, line, re.IGNORECASE)

                if not match:
                    continue

                candidate = match.group(1).strip()

                if self.valid_invoice_candidate(candidate):
                    return candidate

        # Fallback: look for any token that looks like a document number.
        for line in lines[:20]:
            tokens = re.findall(r"\b[A-Z]{0,4}\d{3,}[A-Z0-9\-\/]*\b", line.upper())

            for token in tokens:
                if self.valid_invoice_candidate(token):
                    return token

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

                if not match:
                    continue

                value = match.group(1)

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

    def money_matches(self, line: str):
        return list(re.finditer(r"(?<![A-Za-z])\d{1,6}[.,]\d{2}(?![A-Za-z])", line))

    def standalone_numbers_before(self, text: str) -> list[str]:
        return re.findall(r"(?<![A-Za-z])\b\d+(?:[.,]\d+)?\b(?![A-Za-z])", text)

    def guess_total_amount(self, lines: list[str]) -> float:
        total_candidates = []

        for line in lines:
            lower = line.lower()

            if any(word in lower for word in ["grand total", "total", "amount due", "balance due"]):
                money_values = self.money_matches(line)

                if money_values:
                    total_candidates.append(self.parse_number(money_values[-1].group(0)))
                    continue

                numbers = re.findall(r"\d+(?:[.,]\d{1,2})?", line)

                if numbers:
                    total_candidates.append(self.parse_number(numbers[-1]))

        if total_candidates:
            return max(total_candidates)

        return 0.0

    def guess_category(self, text: str) -> str:
    lower = text.lower()

    # Specific overrides first
    if "cable clip" in lower or "c/clip" in lower:
        return "Electrical"

    plumbing_words = [
        "pipe",
        "pipes",
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
        "fittings",
        "bush",
        "reducer",
        "hopper",
        "floor drain",
        "easybend",
    ]

    electrical_words = [
        "conduit",
        "cable",
        "cables",
        "socket",
        "switch",
        "breaker",
        "mcb",
        "rcd",
        "terminal",
        "terminal box",
        "tee box",
        "u box",
        "trunking",
        "db",
        "connector",
        "connectors",
        "wiring",
    ]

    fixing_words = [
        "screw",
        "screws",
        "bolt",
        "nut",
        "washer",
        "clip",
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

    def clean_item_description(self, line: str) -> str:
    money_values = self.money_matches(line)

    if not money_values:
        return line.strip()

    first_money_index = money_values[0].start()
    description = line[:first_money_index].strip()

    # Keep pack information like "pkt. of 1" or "pkt. of 100".
    # Do not remove trailing numbers because they may be part of the product description.
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

    # Master Enterprise layout:
    # Quantity | Unit Price | Total excl VAT | RRP
    # Example:
    # 3.00 3.91 11.73 5.26
    # 1.00 2.76 2.76 3.73
    if len(money_values) >= 4:
        qty = money_values[-4]
        price = money_values[-3]
        total = money_values[-2]
        confidence = 0.9
        return round(qty, 2), round(price, 2), round(total, 2), confidence

    # Sometimes OCR misses the quantity but reads:
    # Unit Price | Total excl VAT | RRP
    # Example:
    # 2.76 2.76 3.73
    if len(money_values) == 3:
        first, second, third = money_values

        # If the third value matches first * second, treat as Qty | Unit | Total.
        if abs((first * second) - third) < 0.05:
            qty = first
            price = second
            total = third
        else:
            # Otherwise treat as Unit | Total | RRP and ignore RRP.
            price = first
            total = second

            if price > 0:
                qty = round(total / price, 2)
            else:
                qty = 1.0

        confidence = 0.85
        return round(qty, 2), round(price, 2), round(total, 2), confidence

    # Sometimes OCR reads only:
    # Quantity | Unit Price
    # Example:
    # 3.00 3.91
    # In that case calculate the line total.
    if len(money_values) == 2:
        first, second = money_values

        if is_wholeish(first) and first <= 100:
            qty = first
            price = second
            total = round(qty * price, 2)
        else:
            price = first
            total = second

            if price > 0:
                qty = round(total / price, 2)
            else:
                qty = 1.0

        confidence = 0.75
        return round(qty, 2), round(price, 2), round(total, 2), confidence

    if len(money_values) == 1:
        total = money_values[0]
        confidence = 0.55
        return qty, price, round(total, 2), confidence

    return qty, price, total, confidence

    def extract_line_items(self, lines: list[str]) -> list[ExtractedLineItem]:
        line_items = []

        for line in lines:
            if not self.looks_like_item(line):
                continue

            description = self.clean_item_description(line)
            qty, price, total, confidence = self.extract_price_qty_total(line)

            line_items.append(
                ExtractedLineItem(
                    item=description,
                    qty=qty,
                    price=price,
                    total=total,
                    category=self.guess_category(description),
                    confidence=confidence,
                )
            )

        if not line_items:
            line_items.append(
                ExtractedLineItem(
                    item="OCR found text but no clear line items - please review manually",
                    qty=1,
                    price=0,
                    total=0,
                    category="Unknown",
                    confidence=0.2,
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

        calculated_total = round(sum(item.total for item in line_items), 2)

        if total_amount <= 0 and calculated_total > 0:
            total_amount = calculated_total

        confidence = 0.45

        if supplier and supplier != "Unknown supplier":
            confidence += 0.1

        if invoice_date:
            confidence += 0.1

        if invoice_number:
            confidence += 0.1

        if line_items and line_items[0].confidence > 0.2:
            confidence += 0.15

        if total_amount > 0:
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
