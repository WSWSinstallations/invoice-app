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
    def _init_(self):
        pass
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
    def extract_structured_data(self, raw_text: str) -> ExtractedInvoice:
        lines = raw_text.split("\n")
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if len(line) > 5:
                cleaned_lines.append(line)
        line_items = []
        for line in cleaned_lines:
            line_items.append(
                ExtractedLineItem(
                    item=line,
                    qty=1,
                    price=0,
                    total=0,
                    category="Unknown",
                    confidence=0.5,
                )
            )
        supplier = cleaned_lines[0] if cleaned_lines else "Unknown"
        return ExtractedInvoice(
            supplier=supplier,
            invoice_number=None,
            date=None,
            total=None,
            line_items=line_items,
        )
    def extract(self, file_path: str, content_type: str | None, project: str):
        raw_text = self.extract_text(file_path, content_type)
        if not raw_text or len(raw_text.strip()) < 10:
            print("WARNING: OCR returned little or no text")
        structured = self.extract_structured_data(raw_text)
        return structured
