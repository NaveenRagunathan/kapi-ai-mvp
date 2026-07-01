const BASE = 'http://localhost:8000';

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = text;
    try { detail = JSON.parse(text).detail || text; } catch {}
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function ingestPortfolioText(text, sessionId = null) {
  return request('/api/portfolio/ingest', {
    method: 'POST',
    body: JSON.stringify({ text, session_id: sessionId }),
  });
}

export async function ingestPortfolioFile(file, sessionId = null) {
  const form = new FormData();
  form.append('file', file);
  if (sessionId) form.append('session_id', sessionId);
  const res = await fetch(`${BASE}/api/portfolio/ingest/file`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = text;
    try { detail = JSON.parse(text).detail || text; } catch {}
    throw new ApiError(res.status, detail || 'Upload failed');
  }
  return res.json();
}

export async function sendChatMessage(sessionId, message) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export async function getCorrelationMatrix(sessionId) {
  return request(`/api/portfolio/correlation/${sessionId}`);
}

export async function getSession(sessionId) {
  return request(`/api/session/${sessionId}`);
}
