from typing import Optional

from pydantic import BaseModel, Field


class LineItemInput(BaseModel):
    id: Optional[int] = None
    item: str = ""
    qty: float = Field(default=1, ge=0)
    price: float = Field(default=0, ge=0)
    total: Optional[float] = Field(default=None, ge=0)
    category: str = "Uncategorized"
    confidence: float = Field(default=1, ge=0, le=1)


class InvoiceUpdate(BaseModel):
    supplier: str = ""
    invoice_number: str = ""
    invoice_date: str = ""
    project: str = ""
    currency: str = "EUR"
    status: str = "reviewed"
    line_items: list[LineItemInput] = []

