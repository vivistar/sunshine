import { describe, it, expect, vi } from 'vitest';
import { parseResponsesCsv, responsesToCsv } from './csv';
import { scoreResponse } from './scoring';

// crypto.randomUUID may be missing in the test env; provide a stub.
if (!globalThis.crypto?.randomUUID) {
  globalThis.crypto = { ...globalThis.crypto, randomUUID: () => 'uuid-' + Math.random() };
}

const goodRow = {
  response_id: 'r1', instrument_version: 'v1', study: 's', condition: 'A',
  exposure: 'demo',
  q1: 5, q2: 5, q3: 5, q4: 5, q5: 5, q6: 5, q7: 5, q8: 5, q9: 5,
  q10: 6, q11: 6, q12: 'because', submitted_at: '2026-01-01T00:00:00.000Z',
  source: 'web', tags: '',
};

describe('CSV round-trip', () => {
  it('export then import yields equivalent scored data', () => {
    const csv = responsesToCsv([goodRow], (r) => scoreResponse(r));
    const { valid, rejected } = parseResponsesCsv(csv);
    expect(rejected).toHaveLength(0);
    expect(valid).toHaveLength(1);
    expect(valid[0].exposure).toBe('demo');
    expect(valid[0].q1).toBe(5);
    expect(scoreResponse(valid[0]).overall).toBe(5);
  });
});

describe('CSV validation', () => {
  it('rejects out-of-range and bad exposure', () => {
    const csv =
      'response_id,study,condition,exposure,q1,q2,q3,q4,q5,q6,q7,q8,q9,q10,q11,q12\n' +
      'r1,s,A,teleport,5,5,5,5,5,5,5,5,5,6,6,x\n' + // bad exposure
      'r2,s,A,demo,9,5,5,5,5,5,5,5,5,6,6,y'; // q1 out of range
    const { valid, rejected } = parseResponsesCsv(csv);
    expect(valid).toHaveLength(0);
    expect(rejected).toHaveLength(2);
    expect(rejected[0].reasons.join()).toMatch(/exposure/);
    expect(rejected[1].reasons.join()).toMatch(/q1=9 out of range/);
  });
});
