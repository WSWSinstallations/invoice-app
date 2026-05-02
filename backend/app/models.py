from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    supplier: Mapped[str] = mapped_column(String, default="")
    invoice_number: Mapped[str] = mapped_column(String, default="")
    invoice_date: Mapped[str] = mapped_column(String, default="")
    project: Mapped[str] = mapped_column(String, default="")
    currency: Mapped[str] = mapped_column(String, default="EUR")
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    original_filename: Mapped[str] = mapped_column(String, default="")
    stored_filename: Mapped[str] = mapped_column(String, default="")
    original_path: Mapped[str] = mapped_column(String, default="")
    pdf_path: Mapped[str] = mapped_column(String, default="")
    excel_path: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="needs_review")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    line_items: Mapped[list["LineItem"]] = relationship(
        "LineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="LineItem.id",
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    item: Mapped[str] = mapped_column(String, default="")
    qty: Mapped[float] = mapped_column(Float, default=1.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    category: Mapped[str] = mapped_column(String, default="Uncategorized")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="line_items")

