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
    status = "needs_review" if extracted.confidence < 0.85 else "reviewed"

    invoice = Invoice(
        supplier=extracted.supplier,
        invoice_number=extracted.invoice_number,
        invoice_date=extracted.invoice_date,
        project=extracted.project,
        currency=extracted.currency,
        total_amount=extracted.total_amount,
        extraction_confidence=extracted.confidence,
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


@app.get("/api/invoices/{invoice_id}")
def get_invoice(invoice_id: int, db: Session = Depends(get_db)) -> dict:
    invoice = get_invoice_or_404(db, invoice_id)
    return invoice_to_dict(invoice)


@app.put("/api/invoices/{invoice_id}/review")
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)) -> dict:
    invoice = get_invoice_or_404(db, invoice_id)
    invoice.supplier = payload.supplier
    invoice.invoice_number = payload.invoice_number
    invoice.invoice_date = payload.invoice_date
    invoice.project = payload.project
    invoice.currency = payload.currency
    invoice.status = payload.status or "reviewed"

    db.query(LineItem).filter(LineItem.invoice_id == invoice.id).delete(synchronize_session=False)
    for item in payload.line_items:
        total = item.total if item.total is not None else round(item.qty * item.price, 2)
        db.add(
            LineItem(
                invoice_id=invoice.id,
                item=item.item,
                qty=item.qty,
                price=item.price,
                total=round(total, 2),
                category=item.category or "Uncategorized",
                confidence=item.confidence,
            )
        )

    db.commit()
    invoice = get_invoice_or_404(db, invoice.id)
    invoice = regenerate_outputs(db, invoice)
    return invoice_to_dict(invoice)


@app.get("/api/invoices/{invoice_id}/pdf")
def download_pdf(invoice_id: int, db: Session = Depends(get_db)) -> FileResponse:
    invoice = get_invoice_or_404(db, invoice_id)
    path = resolve_path(invoice.pdf_path)
    if not invoice.pdf_path or not path.exists():
        invoice = regenerate_outputs(db, invoice)
        path = resolve_path(invoice.pdf_path)
    filename = f"{safe_filename(invoice.invoice_number or 'invoice')}.pdf"
    return FileResponse(path, media_type="application/pdf", filename=filename)


@app.get("/api/invoices/{invoice_id}/excel")
def download_excel(invoice_id: int, db: Session = Depends(get_db)) -> FileResponse:
    invoice = get_invoice_or_404(db, invoice_id)
    path = resolve_path(invoice.excel_path)
    if not invoice.excel_path or not path.exists():
        invoice = regenerate_outputs(db, invoice)
        path = resolve_path(invoice.excel_path)
    filename = f"{safe_filename(invoice.invoice_number or 'invoice')}.xlsx"
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


def _money(value) -> float:
    return round(float(value or 0), 2)


def dashboard_total_spend(db: Session) -> dict:
    total = db.query(func.coalesce(func.sum(LineItem.total), 0)).scalar()
    return {"total_spend": _money(total)}


def dashboard_spend_by_category(db: Session) -> list[dict]:
    total_expr = func.coalesce(func.sum(LineItem.total), 0).label("total")
    rows = (
        db.query(LineItem.category, total_expr)
        .group_by(LineItem.category)
        .order_by(desc(total_expr))
        .all()
    )
    return [{"category": category or "Uncategorized", "total": _money(total)} for category, total in rows]


def dashboard_top_items(db: Session) -> list[dict]:
    qty_expr = func.coalesce(func.sum(LineItem.qty), 0).label("qty")
    total_expr = func.coalesce(func.sum(LineItem.total), 0).label("total")
    rows = (
        db.query(
            LineItem.item,
            qty_expr,
            total_expr,
        )
        .group_by(LineItem.item)
        .order_by(desc(total_expr))
        .limit(10)
        .all()
    )
    return [{"item": item or "Unknown", "qty": _money(qty), "total": _money(total)} for item, qty, total in rows]


def dashboard_top_suppliers(db: Session) -> list[dict]:
    count_expr = func.count(Invoice.id).label("invoice_count")
    total_expr = func.coalesce(func.sum(LineItem.total), 0).label("total")
    rows = (
        db.query(
            Invoice.supplier,
            count_expr,
            total_expr,
        )
        .join(LineItem, LineItem.invoice_id == Invoice.id)
        .group_by(Invoice.supplier)
        .order_by(desc(total_expr))
        .limit(10)
        .all()
    )
    return [
        {"supplier": supplier or "Unknown", "invoice_count": int(count), "total": _money(total)}
        for supplier, count, total in rows
    ]


def dashboard_monthly_spend(db: Session) -> list[dict]:
    month_expr = func.substr(Invoice.invoice_date, 1, 7)
    total_expr = func.coalesce(func.sum(LineItem.total), 0).label("total")
    rows = (
        db.query(month_expr.label("month"), total_expr)
        .join(LineItem, LineItem.invoice_id == Invoice.id)
        .group_by(month_expr)
        .order_by(month_expr)
        .all()
    )
    return [{"month": month or "Unknown", "total": _money(total)} for month, total in rows]


@app.get("/api/dashboard/total-spend")
def total_spend(db: Session = Depends(get_db)) -> dict:
    return dashboard_total_spend(db)


@app.get("/api/dashboard/spend-by-category")
def spend_by_category(db: Session = Depends(get_db)) -> list[dict]:
    return dashboard_spend_by_category(db)


@app.get("/api/dashboard/top-items")
def top_items(db: Session = Depends(get_db)) -> list[dict]:
    return dashboard_top_items(db)


@app.get("/api/dashboard/top-suppliers")
def top_suppliers(db: Session = Depends(get_db)) -> list[dict]:
    return dashboard_top_suppliers(db)


@app.get("/api/dashboard/monthly-spend")
def monthly_spend(db: Session = Depends(get_db)) -> list[dict]:
    return dashboard_monthly_spend(db)


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)) -> dict:
    return {
        **dashboard_total_spend(db),
        "spend_by_category": dashboard_spend_by_category(db),
        "top_items": dashboard_top_items(db),
        "top_suppliers": dashboard_top_suppliers(db),
        "monthly_spend": dashboard_monthly_spend(db),
    }
