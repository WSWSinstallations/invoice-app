export const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");

async function parseResponse(response) {
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the status message when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

export function apiUrl(path) {
  return `${API_BASE}${path}`;
}

export async function getDashboard() {
  return parseResponse(await fetch(apiUrl("/api/dashboard")));
}

export async function getInvoices() {
  return parseResponse(await fetch(apiUrl("/api/invoices")));
}

export async function getInvoice(id) {
  return parseResponse(await fetch(apiUrl(`/api/invoices/${id}`)));
}

export async function uploadInvoice(file, project) {
  const body = new FormData();
  body.append("file", file);
  body.append("project", project || "");
  return parseResponse(
    await fetch(apiUrl("/api/invoices/upload"), {
      method: "POST",
      body,
    }),
  );
}

export async function saveInvoiceReview(id, payload) {
  return parseResponse(
    await fetch(apiUrl(`/api/invoices/${id}/review`), {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  );
}

