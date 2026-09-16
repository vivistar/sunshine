// Bulk CSV import (researcher-only). Validates each row, upserts valid ones
// tagged source=import, and reports rejects with reasons (PRD §5.3).
import { ensureSchema, upsertResponse } from './_lib/db.js';
import { checkAuth, validateResponse, readJsonBody } from './_lib/validate.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const auth = checkAuth(req);
  if (!auth.ok) return res.status(auth.status).json({ error: auth.error });

  try {
    await ensureSchema();
    const body = await readJsonBody(req);
    const rows = Array.isArray(body.rows) ? body.rows : [];

    const rejected = [];
    let added = 0;
    for (let i = 0; i < rows.length; i++) {
      // Imports may carry missing Likert values (subscale nulled at scoring
      // time), so completeness is not required here — ranges/enum still are.
      const { value, reasons } = validateResponse(
        { ...rows[i], source: 'import' },
        { requireComplete: false }
      );
      if (reasons) {
        rejected.push({ row: i + 1, reasons });
      } else {
        await upsertResponse(value);
        added += 1;
      }
    }
    return res.status(200).json({ added, rejected });
  } catch (err) {
    return res.status(500).json({ error: 'Server error', detail: String(err?.message || err) });
  }
}
