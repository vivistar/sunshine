// CSV import/export for responses (PRD §5.3). Round-trip safe: exported CSV
// re-imports cleanly. Validates types/ranges and reports rejected rows.

import Papa from 'papaparse';
import { LIKERT_ITEMS, EXPOSURE_VALUES, INSTRUMENT_VERSION } from './instrument.config';

// Canonical column order for export.
export const CSV_COLUMNS = [
  'response_id',
  'instrument_version',
  'study',
  'condition',
  'exposure',
  'q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9',
  'q10', 'q11', 'q12',
  'submitted_at',
  'source',
  'tags',
];

function toIntOrNull(v) {
  if (v === '' || v == null) return null;
  const n = Number(v);
  return Number.isInteger(n) ? n : NaN; // NaN signals invalid
}

/**
 * Parse CSV text into { valid, rejected }.
 * rejected: [{ row, reasons }] with 1-based data row numbers.
 */
export function parseResponsesCsv(text) {
  const { data, errors: parseErrors } = Papa.parse(text.trim(), {
    header: true,
    skipEmptyLines: true,
  });

  const valid = [];
  const rejected = [];

  if (parseErrors.length) {
    for (const e of parseErrors) {
      rejected.push({ row: (e.row ?? 0) + 1, reasons: [e.message] });
    }
  }

  data.forEach((raw, idx) => {
    const rowNum = idx + 1;
    const reasons = [];
    const out = {
      response_id: raw.response_id?.trim() || crypto.randomUUID(),
      instrument_version: raw.instrument_version?.trim() || INSTRUMENT_VERSION,
      study: raw.study?.trim() || '',
      condition: raw.condition?.trim() || '',
      exposure: raw.exposure?.trim() || '',
      q12: raw.q12 ?? '',
      submitted_at: raw.submitted_at?.trim() || new Date().toISOString(),
      source: 'import',
      tags: raw.tags?.trim() || '',
    };

    if (!EXPOSURE_VALUES.includes(out.exposure)) {
      reasons.push(`invalid exposure "${out.exposure}" (expected ${EXPOSURE_VALUES.join('|')})`);
    }

    for (const id of LIKERT_ITEMS) {
      const n = toIntOrNull(raw[id]);
      if (Number.isNaN(n)) {
        reasons.push(`${id} is not an integer`);
      } else if (n != null && (n < 1 || n > 7)) {
        reasons.push(`${id}=${n} out of range 1..7`);
      } else {
        out[id] = n; // int or null (null allowed for imports; scoring handles it)
      }
    }

    if (reasons.length) {
      rejected.push({ row: rowNum, reasons });
    } else {
      valid.push(out);
    }
  });

  return { valid, rejected };
}

/**
 * Serialize responses (and optionally computed scores) to CSV text.
 * If `scoreFn` is provided, appends understanding/performance/overall columns.
 */
export function responsesToCsv(responses, scoreFn = null) {
  const columns = scoreFn
    ? [...CSV_COLUMNS, 'understanding', 'performance', 'overall']
    : CSV_COLUMNS;

  const rows = responses.map((r) => {
    const base = {};
    for (const c of CSV_COLUMNS) base[c] = r[c] ?? '';
    if (scoreFn) {
      const s = scoreFn(r);
      base.understanding = s.understanding ?? '';
      base.performance = s.performance ?? '';
      base.overall = s.overall ?? '';
    }
    return base;
  });

  return Papa.unparse({ fields: columns, data: rows });
}

export function downloadCsv(filename, text) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
