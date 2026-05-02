import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Camera,
  Download,
  FileSpreadsheet,
  Gauge,
  LayoutDashboard,
  List,
  Plus,
  Save,
  Trash2,
  Upload,
} from "lucide-react";
import {
  API_BASE,
  apiUrl,
  getDashboard,
  getInvoice,
  getInvoices,
  saveInvoiceReview,
  uploadInvoice,
} from "./api";

const CHART_COLORS = ["#0f766e", "#d97706", "#2563eb", "#be123c", "#64748b", "#7c3aed"];

function money(value, currency = "EUR") {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(Number(value || 0));
  } catch {
    return `${Number(value || 0).toFixed(2)} ${currency}`;
  }
}

function numberValue(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function EmptyState({ children }) {
  return <div className="empty-state">{children}</div>;
}

function TopBar() {
  return (
    <header className="top-bar">
      <div>
        <p className="eyebrow">Invoice processing</p>
        <h1>Review, export, report</h1>
      </div>
      <div className="api-pill" title={`API: ${API_BASE}`}>
        API
      </div>
    </header>
  );
}

function Navigation({ view, setView }) {
  const navItems = [
    { id: "upload", label: "Upload", icon: Upload },
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "history", label: "History", icon: List },
  ];

  return (
    <nav className="bottom-nav" aria-label="Primary navigation">
      {navItems.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          className={view === id ? "active" : ""}
          onClick={() => setView(id)}
        >
          <Icon size={19} aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

function UploadScreen({ onInvoiceReady }) {
  const [file, setFile] = useState(null);
  const [project, setProject] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) {
      setPreviewUrl("");
      return undefined;
    }
    const nextUrl = URL.createObjectURL(file);
    setPreviewUrl(nextUrl);
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  async function submit(event) {
    event.preventDefault();
    if (!file) {
      setError("Choose an invoice image or PDF first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const invoice = await uploadInvoice(file, project);
      onInvoiceReady(invoice);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="screen upload-screen">
      <form className="panel upload-panel" onSubmit={submit}>
        <label className="field">
          <span>Project</span>
          <input
            value={project}
            onChange={(event) => setProject(event.target.value)}
            placeholder="General"
            autoComplete="off"
          />
        </label>

        <label className="drop-zone">
          <input
            type="file"
            accept="image/*,application/pdf"
            capture="environment"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
          />
          {previewUrl ? (
            <img src={previewUrl} alt="Selected invoice preview" />
          ) : (
            <span className="camera-mark">
              <Camera size={28} aria-hidden="true" />
            </span>
          )}
          <strong>{file ? file.name : "Select invoice"}</strong>
        </label>

        {error ? <p className="error-text">{error}</p> : null}

        <button className="primary-button" type="submit" disabled={busy}>
          <Upload size={18} aria-hidden="true" />
          <span>{busy ? "Processing" : "Upload invoice"}</span>
        </button>
      </form>
    </section>
  );
}

function ReviewScreen({ invoiceId, initialInvoice, onSaved }) {
  const [invoice, setInvoice] = useState(initialInvoice || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    async function load() {
      if (!invoiceId) return;
      try {
        const freshInvoice = await getInvoice(invoiceId);
        if (active) setInvoice(freshInvoice);
      } catch (err) {
        if (active) setError(err.message);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [invoiceId]);

  const lowConfidenceCount = useMemo(() => {
    if (!invoice) return 0;
    return invoice.line_items.filter((item) => item.low_confidence || item.confidence < 0.75).length;
  }, [invoice]);

  function updateField(field, value) {
    setSaved(false);
    setInvoice((current) => ({ ...current, [field]: value }));
  }

  function updateItem(index, field, value) {
    setSaved(false);
    setInvoice((current) => {
      const lineItems = [...current.line_items];
      const updated = { ...lineItems[index], [field]: value };
      if (field === "qty" || field === "price") {
        updated.total = Number((numberValue(updated.qty) * numberValue(updated.price)).toFixed(2));
      }
      lineItems[index] = updated;
      return { ...current, line_items: lineItems };
    });
  }

  function addItem() {
    setSaved(false);
    setInvoice((current) => ({
      ...current,
      line_items: [
        ...current.line_items,
        {
          item: "",
          qty: 1,
          price: 0,
          total: 0,
          category: "Uncategorized",
          confidence: 1,
        },
      ],
    }));
  }

  function removeItem(index) {
    setSaved(false);
    setInvoice((current) => ({
      ...current,
      line_items: current.line_items.filter((_, itemIndex) => itemIndex !== index),
    }));
  }

  async function save() {
    if (!invoice) return;
    setBusy(true);
    setError("");
    try {
      const payload = {
        supplier: invoice.supplier,
        invoice_number: invoice.invoice_number,
        invoice_date: invoice.invoice_date,
        project: invoice.project,
        currency: invoice.currency,
        status: "reviewed",
        line_items: invoice.line_items.map((item) => ({
          id: item.id,
          item: item.item,
          qty: numberValue(item.qty),
          price: numberValue(item.price),
          total: numberValue(item.total),
          category: item.category || "Uncategorized",
          confidence: numberValue(item.confidence || 1),
        })),
      };
      const updated = await saveInvoiceReview(invoice.id, payload);
      setInvoice(updated);
      setSaved(true);
      onSaved?.(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!invoice) {
    return (
      <section className="screen">
        <EmptyState>{error || "Loading invoice."}</EmptyState>
      </section>
    );
  }

  return (
    <section className="screen review-screen">
      <div className="panel">
        <div className="section-header">
          <div>
            <p className="eyebrow">Review</p>
            <h2>{invoice.original_filename}</h2>
          </div>
          {lowConfidenceCount ? <span className="warning-pill">{lowConfidenceCount} low</span> : <span className="ok-pill">Clean</span>}
        </div>

        <div className="form-grid">
          <label className="field">
            <span>Supplier</span>
            <input value={invoice.supplier || ""} onChange={(event) => updateField("supplier", event.target.value)} />
          </label>
          <label className="field">
            <span>Invoice number</span>
            <input value={invoice.invoice_number || ""} onChange={(event) => updateField("invoice_number", event.target.value)} />
          </label>
          <label className="field">
            <span>Date</span>
            <input type="date" value={invoice.invoice_date || ""} onChange={(event) => updateField("invoice_date", event.target.value)} />
          </label>
          <label className="field">
            <span>Project</span>
            <input value={invoice.project || ""} onChange={(event) => updateField("project", event.target.value)} />
          </label>
        </div>
      </div>

      <div className="line-item-toolbar">
        <h3>Line items</h3>
        <button className="icon-button" type="button" onClick={addItem} title="Add item">
          <Plus size={19} aria-hidden="true" />
        </button>
      </div>

      <div className="items-list">
        {invoice.line_items.map((item, index) => (
          <article className={`item-editor ${item.confidence < 0.75 ? "low-confidence" : ""}`} key={item.id || index}>
            <div className="item-editor-head">
              <span>{item.confidence < 0.75 ? "Low confidence" : "Line item"}</span>
              <button className="ghost-icon" type="button" onClick={() => removeItem(index)} title="Remove item">
                <Trash2 size={18} aria-hidden="true" />
              </button>
            </div>
            <label className="field full">
              <span>Item</span>
              <input value={item.item || ""} onChange={(event) => updateItem(index, "item", event.target.value)} />
            </label>
            <div className="item-number-grid">
              <label className="field">
                <span>Qty</span>
                <input type="number" min="0" step="0.01" value={item.qty} onChange={(event) => updateItem(index, "qty", event.target.value)} />
              </label>
              <label className="field">
                <span>Price</span>
                <input type="number" min="0" step="0.01" value={item.price} onChange={(event) => updateItem(index, "price", event.target.value)} />
              </label>
              <label className="field">
                <span>Total</span>
                <input type="number" min="0" step="0.01" value={item.total} onChange={(event) => updateItem(index, "total", event.target.value)} />
              </label>
            </div>
            <label className="field full">
              <span>Category</span>
              <input value={item.category || ""} onChange={(event) => updateItem(index, "category", event.target.value)} />
            </label>
          </article>
        ))}
      </div>

      {error ? <p className="error-text">{error}</p> : null}
      {saved ? <p className="success-text">Saved.</p> : null}

      <div className="review-actions">
        <button className="primary-button" type="button" onClick={save} disabled={busy}>
          <Save size={18} aria-hidden="true" />
          <span>{busy ? "Saving" : "Save review"}</span>
        </button>
        <a className="secondary-button" href={apiUrl(invoice.pdf_url)} target="_blank" rel="noreferrer">
          <Download size={18} aria-hidden="true" />
          <span>PDF</span>
        </a>
        <a className="secondary-button" href={apiUrl(invoice.excel_url)} target="_blank" rel="noreferrer">
          <FileSpreadsheet size={18} aria-hidden="true" />
          <span>Excel</span>
        </a>
      </div>
    </section>
  );
}

function DashboardScreen({ refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const dashboard = await getDashboard();
        if (active) setData(dashboard);
      } catch (err) {
        if (active) setError(err.message);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [refreshKey]);

  if (error) {
    return (
      <section className="screen">
        <EmptyState>{error}</EmptyState>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="screen">
        <EmptyState>Loading dashboard.</EmptyState>
      </section>
    );
  }

  const hasSpend = data.spend_by_category.length > 0 || data.monthly_spend.length > 0;

  return (
    <section className="screen dashboard-screen">
      <div className="metric-row">
        <div className="metric">
          <Gauge size={20} aria-hidden="true" />
          <span>Total spend</span>
          <strong>{money(data.total_spend)}</strong>
        </div>
      </div>

      {!hasSpend ? (
        <EmptyState>No invoice data yet.</EmptyState>
      ) : (
        <>
          <div className="chart-grid">
            <div className="panel chart-panel">
              <h2>Monthly spend</h2>
              <ResponsiveContainer width="100%" height={230}>
                <LineChart data={data.monthly_spend}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis dataKey="month" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(value) => money(value)} />
                  <Line type="monotone" dataKey="total" stroke="#0f766e" strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className="panel chart-panel">
              <h2>Categories</h2>
              <ResponsiveContainer width="100%" height={230}>
                <PieChart>
                  <Pie data={data.spend_by_category} dataKey="total" nameKey="category" innerRadius={52} outerRadius={86} paddingAngle={3}>
                    {data.spend_by_category.map((entry, index) => (
                      <Cell key={entry.category} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => money(value)} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="panel chart-panel wide">
              <h2>Top suppliers</h2>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={data.top_suppliers}>
                  <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                  <XAxis dataKey="supplier" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <Tooltip formatter={(value) => money(value)} />
                  <Bar dataKey="total" fill="#d97706" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <DataTable
            title="Top items"
            columns={["Item", "Qty", "Total"]}
            rows={data.top_items.map((item) => [item.item, item.qty, money(item.total)])}
          />
          <DataTable
            title="Spend by category"
            columns={["Category", "Total"]}
            rows={data.spend_by_category.map((item) => [item.category, money(item.total)])}
          />
        </>
      )}
    </section>
  );
}

function DataTable({ title, columns, rows }) {
  return (
    <div className="panel table-panel">
      <h2>{title}</h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`${title}-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`${title}-${rowIndex}-${cellIndex}`}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HistoryScreen({ onOpenInvoice, refreshKey }) {
  const [invoices, setInvoices] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const rows = await getInvoices();
        if (active) setInvoices(rows);
      } catch (err) {
        if (active) setError(err.message);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [refreshKey]);

  if (error) {
    return (
      <section className="screen">
        <EmptyState>{error}</EmptyState>
      </section>
    );
  }

  return (
    <section className="screen history-screen">
      {invoices.length === 0 ? (
        <EmptyState>No invoices yet.</EmptyState>
      ) : (
        <div className="history-list">
          {invoices.map((invoice) => (
            <article className="history-row" key={invoice.id}>
              <button type="button" onClick={() => onOpenInvoice(invoice)} className="history-main">
                <span>{invoice.supplier || "Unknown supplier"}</span>
                <strong>{money(invoice.total_amount, invoice.currency)}</strong>
                <small>
                  {invoice.invoice_number || "No number"} · {invoice.invoice_date || "No date"}
                </small>
              </button>
              <a href={apiUrl(invoice.excel_url)} target="_blank" rel="noreferrer" className="ghost-icon" title="Download Excel">
                <FileSpreadsheet size={18} aria-hidden="true" />
              </a>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default function App() {
  const [view, setView] = useState("upload");
  const [invoiceId, setInvoiceId] = useState(null);
  const [invoice, setInvoice] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  function openReview(nextInvoice) {
    setInvoice(nextInvoice);
    setInvoiceId(nextInvoice.id);
    setView("review");
    setRefreshKey((key) => key + 1);
  }

  function handleSaved(updatedInvoice) {
    setInvoice(updatedInvoice);
    setRefreshKey((key) => key + 1);
  }

  return (
    <div className="app-shell">
      <TopBar />
      <main>
        {view === "upload" ? <UploadScreen onInvoiceReady={openReview} /> : null}
        {view === "review" ? <ReviewScreen invoiceId={invoiceId} initialInvoice={invoice} onSaved={handleSaved} /> : null}
        {view === "dashboard" ? <DashboardScreen refreshKey={refreshKey} /> : null}
        {view === "history" ? <HistoryScreen refreshKey={refreshKey} onOpenInvoice={openReview} /> : null}
      </main>
      <Navigation view={view} setView={setView} />
    </div>
  );
}
