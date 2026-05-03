import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, selectinload

from app.database import get_db, init_db
from app.excel import generate_invoice_excel
from app.models import Invoice, LineItem
from app.ocr_ai import InvoiceExtractor
from app.pdf import generate_invoice_pdf
from app.schemas import InvoiceUpdate
from app.storage import generated_file, resolve_path, safe_filename, save_upload_file


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Invoice Processing API", version="1.0.0", lifespan=lifespan)

cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = (
        db.query(Invoice)
        .options(selectinload(Invoice.line_items))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def line_item_to_dict(line_item: LineItem) -> dict:
    return {
        "id": line_item.id,
        "item": line_item.item,
        "qty": line_item.qty,
        "price": line_item.price,
        "total": line_item.total,
        "category": line_item.category,
        "confidence": line_item.confidence,
        "low_confidence": line_item.confidence < 0.75,
    }


def invoice_to_dict(invoice: Invoice) -> dict:
    return {
        "id": invoice.id,
        "supplier": invoice.supplier,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "project": invoice.project,
        "currency": invoice.currency,
        "total_amount": invoice.total_amount,
        "extraction_confidence": invoice.extraction_confidence,
        "status": invoice.status,
        "original_filename": invoice.original_filename,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "line_items": [line_item_to_dict(item) for item in invoice.line_items],
        "pdf_url": f"/api/invoices/{invoice.id}/pdf",
        "excel_url": f"/api/invoices/{invoice.id}/excel",
    }


def regenerate_outputs(db: Session, invoice: Invoice) -> Invoice:
    invoice.total_amount = round(sum(item.total for item in invoice.line_items), 2)
    invoice.pdf_path = generated_file(invoice.id, "pdf")
    invoice.excel_path = generated_file(invoice.id, "xlsx")

    generate_invoice_pdf(invoice, resolve_path(invoice.pdf_path))
    generate_invoice_excel(invoice, resolve_path(invoice.excel_path))

    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return get_invoice_or_404(db, invoice.id)


@app.get("/")
def root() -> dict:
    return {"status": "ok", "service": "invoice-processing-api"}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/invoices/upload")
def upload_invoice(
    file: UploadFile = File(...),
    project: str = Form(default=""),
    db: Session = Depends(get_db),
) -> dict:
    stored_filename, processing_path = save_upload_file(file)

    extractor = InvoiceExtractor()
    extracted = extractor.extract(processing_path, file.content_type, project)

    status = "needs_review"

    invoice = Invoice(
        supplier=extracted.supplier,
        invoice_number=extracted.invoice_number,
        invoice_date=extracted.invoice_date,
        project=project,
        currency="EUR",
        total_amount=0,
        extraction_confidence=0.5,
        original_filename=file.filename or stored_filename,
        stored_filename=stored_filename,
        original_path=processing_path,
        status=status,
    )

    db.add(invoice)
    db.flush()

    for item in extracted.line_items:
        db.add(
            LineItem(
                invoice_id=invoice.id,
                item=item.item,
                qty=item.qty,
                price=item.price,
                total=item.total,
                category=item.category,
                confidence=item.confidence,
            )
        )

    db.commit()

    invoice = get_invoice_or_404(db, invoice.id)
    invoice = regenerate_outputs(db, invoice)

    return invoice_to_dict(invoice)


@app.get("/api/invoices")
def list_invoices(db: Session = Depends(get_db)) -> list[dict]:
    invoices = (
        db.query(Invoice)
        .options(selectinload(Invoice.line_items))
        .order_by(desc(Invoice.created_at))
        .all()
    )
    return [invoice_to_dict(invoice) for invoice in invoices]


# ✅ DELETE ENDPOINT ADDED HERE
@app.delete("/api/invoices/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    db.delete(invoice)
    db.commit()

    return {"success": True}


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict:
    invoice = get_invoice_or_404(db, invoice_id)
    return invoice_to_dict(invoice)
