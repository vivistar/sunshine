// Frontend data layer talking to the Vercel serverless API (Postgres-backed).
// The passcode is sent as a header and checked server-side; it is never a
// build-time/client-exposed secret.

async function req(path, { method = 'GET', passcode, body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (passcode) headers['x-survey-passcode'] = passcode;
  const res = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    // non-JSON (e.g. 404 HTML when API not deployed locally)
  }
  if (!res.ok) {
    const err = new Error(data?.error || `Request failed (${res.status})`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

// Public: submit one completed response.
export function submitResponse(response) {
  return req('/api/responses', { method: 'POST', body: response });
}

// Researcher: list responses (optionally by study).
export function fetchResponses(passcode, study) {
  const qs = study ? `?study=${encodeURIComponent(study)}` : '';
  return req(`/api/responses${qs}`, { passcode });
}

// Researcher: bulk import validated rows.
export function importResponses(passcode, rows) {
  return req('/api/import', { method: 'POST', passcode, body: { rows } });
}

// Researcher: set q12 tags for a response.
export function saveTags(passcode, response_id, tags) {
  return req('/api/tags', { method: 'POST', passcode, body: { response_id, tags } });
}

// Researcher: clear responses (all, or one study).
export function clearRemote(passcode, study) {
  const qs = study ? `?study=${encodeURIComponent(study)}` : '';
  return req(`/api/responses${qs}`, { method: 'DELETE', passcode });
}
