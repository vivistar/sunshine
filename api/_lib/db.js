// Schema + insert helpers shared across API routes.
import { sql } from '@vercel/postgres';
import { LIKERT_ITEMS } from './validate.js';

export async function ensureSchema() {
  await sql`
    CREATE TABLE IF NOT EXISTS responses (
      response_id        text PRIMARY KEY,
      instrument_version text NOT NULL,
      study              text NOT NULL DEFAULT '',
      condition          text NOT NULL DEFAULT '',
      exposure           text NOT NULL,
      q1 int, q2 int, q3 int, q4 int, q5 int, q6 int, q7 int, q8 int, q9 int,
      q10 int, q11 int,
      q12                text NOT NULL DEFAULT '',
      submitted_at       timestamptz NOT NULL DEFAULT now(),
      source             text NOT NULL DEFAULT 'web',
      tags               text NOT NULL DEFAULT ''
    );
  `;
  await sql`CREATE INDEX IF NOT EXISTS responses_study_idx ON responses (study);`;
}

// Upsert one validated row (dedupe by response_id).
export async function upsertResponse(r) {
  await sql`
    INSERT INTO responses (
      response_id, instrument_version, study, condition, exposure,
      q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, q11, q12,
      submitted_at, source, tags
    ) VALUES (
      ${r.response_id}, ${r.instrument_version}, ${r.study}, ${r.condition}, ${r.exposure},
      ${r.q1}, ${r.q2}, ${r.q3}, ${r.q4}, ${r.q5}, ${r.q6}, ${r.q7}, ${r.q8}, ${r.q9},
      ${r.q10}, ${r.q11}, ${r.q12},
      ${r.submitted_at}, ${r.source}, ${r.tags}
    )
    ON CONFLICT (response_id) DO UPDATE SET
      instrument_version = EXCLUDED.instrument_version,
      study = EXCLUDED.study, condition = EXCLUDED.condition,
      exposure = EXCLUDED.exposure,
      q1=EXCLUDED.q1, q2=EXCLUDED.q2, q3=EXCLUDED.q3, q4=EXCLUDED.q4,
      q5=EXCLUDED.q5, q6=EXCLUDED.q6, q7=EXCLUDED.q7, q8=EXCLUDED.q8,
      q9=EXCLUDED.q9, q10=EXCLUDED.q10, q11=EXCLUDED.q11, q12=EXCLUDED.q12,
      submitted_at = EXCLUDED.submitted_at, source = EXCLUDED.source,
      tags = EXCLUDED.tags;
  `;
}

export { LIKERT_ITEMS };
