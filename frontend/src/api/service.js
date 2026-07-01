const BASE = import.meta.env.VITE_API_BASE_URL || '';

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

export async function ingestPortfolioImages(files, sessionId = null) {
  const form = new FormData();
  for (const file of files) form.append('files', file);
  if (sessionId) form.append('session_id', sessionId);
  const res = await fetch(`${BASE}/api/portfolio/ingest/images`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = text;
    try { detail = JSON.parse(text).detail || text; } catch {}
    throw new ApiError(res.status, detail || 'Screenshot upload failed');
  }
  return res.json();
}

export async function sendChatMessage(sessionId, message) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message }),
  });
}

export async function sendChatMessageStream(sessionId, message, onEvent) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    let detail = text;
    try { detail = JSON.parse(text).detail || text; } catch {}
    throw new Error(detail || `Request failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    let lines = buffer.split('\n');
    buffer = lines.pop();

    for (let line of lines) {
      line = line.trim();
      if (!line) continue;

      if (line.startsWith('event:')) {
        currentEvent = line.replace('event:', '').trim();
      } else if (line.startsWith('data:')) {
        const dataStr = line.replace('data:', '').trim();
        try {
          const data = JSON.parse(dataStr);
          onEvent({ event: currentEvent, data });
        } catch (e) {
          console.error('Failed to parse SSE line data:', dataStr, e);
        }
        currentEvent = '';
      }
    }
  }
}

export async function getCorrelationMatrix(sessionId) {
  return request(`/api/portfolio/correlation/${sessionId}`);
}

export async function getSession(sessionId) {
  return request(`/api/session/${sessionId}`);
}
