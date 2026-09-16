// Shared server-side validation and auth. Files under api/_lib are NOT routed
// by Vercel (underscore prefix), so this is import-only.

export const EXPOSURE_VALUES = ['spec', 'mockups', 'demo', 'prototype'];
export const LIKERT_ITEMS = [
  'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9', 'q10', 'q11',
];
export const INSTRUMENT_VERSION = 'anticipated-trust-1.0.0';

// Server-side passcode gate. Never a client-exposed (VITE_/NEXT_PUBLIC_) var.
export function checkAuth(req) {
  const expected = process.env.SURVEY_PASSCODE;
  if (!expected) return { ok: false, status: 500, error: 'SURVEY_PASSCODE not configured on server' };
  const provided = req.headers['x-survey-passcode'];
  if (provided !== expected) return { ok: false, status: 401, error: 'Unauthorized' };
  return { ok: true };
}

function toIntOrNull(v) {
  if (v === '' || v == null) return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : NaN;
}

// Validate + normalize one response row. Returns { value } or { reasons: [] }.
// Likert items may be null (imports); ranges enforced when present. exposure
// and q1..q9 completeness are required for a valid stored row.
export function validateResponse(raw, { requireComplete = true } = {}) {
  const reasons = [];
  const out = {
    response_id:
      (typeof raw.response_id === 'string' && raw.response_id.trim()) ||
      cryptoRandomId(),
    instrument_version:
      (raw.instrument_version && String(raw.instrument_version).trim()) ||
      INSTRUMENT_VERSION,
    study: raw.study ? String(raw.study).trim() : '',
    condition: raw.condition ? String(raw.condition).trim() : '',
    exposure: raw.exposure ? String(raw.exposure).trim() : '',
    q12: raw.q12 != null ? String(raw.q12) : '',
    submitted_at: raw.submitted_at
      ? String(raw.submitted_at)
      : new Date().toISOString(),
    source: raw.source === 'web' ? 'web' : 'import',
    tags: raw.tags ? String(raw.tags).trim() : '',
  };

  if (!EXPOSURE_VALUES.includes(out.exposure)) {
    reasons.push(`invalid exposure "${out.exposure}"`);
  }

  for (const id of LIKERT_ITEMS) {
    const n = toIntOrNull(raw[id]);
    if (Number.isNaN(n)) {
      reasons.push(`${id} is not an integer`);
    } else if (n != null && (n < 1 || n > 7)) {
      reasons.push(`${id}=${n} out of range 1..7`);
    } else {
      out[id] = n;
    }
  }

  // Completeness for web submissions: q1..q9 + q10/q11 must be present.
  if (requireComplete) {
    for (const id of LIKERT_ITEMS) {
      if (out[id] == null) reasons.push(`${id} is required`);
    }
  }

  if (reasons.length) return { reasons };
  return { value: out };
}

function cryptoRandomId() {
  // Node 18+ has global crypto.randomUUID.
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return 'id-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export async function readJsonBody(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString('utf8');
  return raw ? JSON.parse(raw) : {};
}
