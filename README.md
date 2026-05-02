# Invoice Processing App

Complete FastAPI + React invoice processing starter, ready to push to GitHub and deploy as two services:

- Backend on Railway from `backend/`
- Frontend on Vercel from `frontend/`

## Folder Structure

```text
.
├── backend
│   ├── app
│   │   ├── __init__.py
│   │   ├── database.py
│   │   ├── excel.py
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── ocr_ai.py
│   │   ├── pdf.py
│   │   ├── schemas.py
│   │   └── storage.py
│   ├── data
│   │   └── .gitkeep
│   ├── generated
│   │   └── .gitkeep
│   ├── uploads
│   │   └── .gitkeep
│   ├── .env.example
│   ├── Procfile
│   └── requirements.txt
├── frontend
│   ├── src
│   │   ├── api.js
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   ├── vercel.json
│   └── vite.config.js
├── .gitignore
└── README.md
```

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API runs at `http://localhost:8000`.

Key endpoints:

- `POST /api/invoices/upload`
- `GET /api/invoices`
- `GET /api/invoices/{id}`
- `PUT /api/invoices/{id}/review`
- `GET /api/invoices/{id}/pdf`
- `GET /api/invoices/{id}/excel`
- `GET /api/dashboard`
- `GET /api/dashboard/total-spend`
- `GET /api/dashboard/spend-by-category`
- `GET /api/dashboard/top-items`
- `GET /api/dashboard/top-suppliers`
- `GET /api/dashboard/monthly-spend`

## Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Frontend runs at `http://localhost:5173`.

## Environment Variables

Backend:

```text
CORS_ORIGINS=http://localhost:5173,https://your-vercel-app.vercel.app
INVOICE_DB_PATH=data/invoices.db
OPENAI_API_KEY=
AI_MODEL=gpt-4.1-mini
OCR_PROVIDER=placeholder
DEFAULT_PROJECT=General
DEFAULT_CURRENCY=EUR
```

Frontend:

```text
VITE_API_URL=https://your-railway-backend.up.railway.app
```

## Railway Backend

1. Create a Railway service from this GitHub repo.
2. Set the service root directory to `backend`.
3. Add the backend environment variables.
4. Deploy. Railway will use `backend/Procfile`.

For persistent SQLite storage, attach a Railway volume and set `INVOICE_DB_PATH` to a path inside that mounted volume.

## Vercel Frontend

1. Create a Vercel project from this GitHub repo.
2. Set the root directory to `frontend`.
3. Add `VITE_API_URL` with the Railway backend URL.
4. Deploy.

## Automatic Image Orientation

Image uploads are corrected before OCR or PDF generation. The backend saves the original upload under `uploads/original`, detects orientation from EXIF data when available, falls back to Tesseract OSD when EXIF is unavailable, and writes an upright working copy under `uploads/corrected`. The corrected path is used automatically by OCR, AI extraction, and the generated PDF.

## OCR + AI Integration

`backend/app/ocr_ai.py` is the integration boundary. The app currently returns placeholder structured data with confidence values, so upload/review/export/dashboard work immediately. Replace `extract_text` and `extract_structured_data` with calls to your OCR and AI provider while keeping the returned dataclass shape the same.

