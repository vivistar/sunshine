// Update manual q12 tags for a response (researcher-only).
import { sql } from '@vercel/postgres';
import { ensureSchema } from './_lib/db.js';
import { checkAuth, readJsonBody } from './_lib/validate.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const auth = checkAuth(req);
  if (!auth.ok) return res.status(auth.status).json({ error: auth.error });

  try {
    await ensureSchema();
    const body = await readJsonBody(req);
    const id = String(body.response_id || '').trim();
    if (!id) return res.status(400).json({ error: 'response_id required' });
    const tags = Array.isArray(body.tags) ? body.tags.join(',') : String(body.tags || '');
    await sql`UPDATE responses SET tags = ${tags} WHERE response_id = ${id}`;
    return res.status(200).json({ ok: true });
  } catch (err) {
    return res.status(500).json({ error: 'Server error', detail: String(err?.message || err) });
  }
}
