// Public POST (submit one response) + researcher GET/DELETE (auth).
import { sql } from '@vercel/postgres';
import { ensureSchema, upsertResponse } from './_lib/db.js';
import { checkAuth, validateResponse, readJsonBody } from './_lib/validate.js';

export default async function handler(req, res) {
  try {
    await ensureSchema();

    if (req.method === 'POST') {
      // Public submission — no auth. Must be a complete web response.
      const body = await readJsonBody(req);
      const { value, reasons } = validateResponse(
        { ...body, source: 'web' },
        { requireComplete: true }
      );
      if (reasons) return res.status(400).json({ error: 'Invalid response', reasons });
      await upsertResponse(value);
      return res.status(201).json({ ok: true, response_id: value.response_id });
    }

    // Everything below requires the researcher passcode.
    const auth = checkAuth(req);
    if (!auth.ok) return res.status(auth.status).json({ error: auth.error });

    if (req.method === 'GET') {
      const study = req.query?.study;
      const { rows } = study
        ? await sql`SELECT * FROM responses WHERE study = ${study} ORDER BY submitted_at`
        : await sql`SELECT * FROM responses ORDER BY submitted_at`;
      return res.status(200).json({ responses: rows });
    }

    if (req.method === 'DELETE') {
      const study = req.query?.study;
      if (study) {
        await sql`DELETE FROM responses WHERE study = ${study}`;
      } else {
        await sql`DELETE FROM responses`;
      }
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: 'Method not allowed' });
  } catch (err) {
    return res.status(500).json({ error: 'Server error', detail: String(err?.message || err) });
  }
}
