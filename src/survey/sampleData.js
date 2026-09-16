// Example data so the dashboard is never an empty shell on first load (PRD §5.5).
// These are illustrative, clearly-labeled example rows, NOT real responses.
import { INSTRUMENT_VERSION } from './instrument.config';

function make(id, study, condition, exposure, u, p, q10, q11, q12) {
  // u/p arrays map to the item ids; keep them explicit for realism.
  return {
    response_id: `example-${id}`,
    instrument_version: INSTRUMENT_VERSION,
    study,
    condition,
    exposure,
    q1: u[0], q3: u[1], q4: u[2], q8: u[3],
    q2: p[0], q5: p[1], q6: p[2], q7: p[3], q9: p[4],
    q10, q11, q12,
    submitted_at: new Date(Date.UTC(2026, 8, 10, 12, id)).toISOString(),
    source: 'import',
    tags: '',
  };
}

// Study "onboarding-agent": demo-A (high P, low U — the decision-relevant
// over-trust pattern) vs demo-B (balanced).
export const EXAMPLE_RESPONSES = [
  make(1, 'onboarding-agent', 'demo-A', 'demo', [3, 2, 3, 2], [6, 6, 7, 6, 6], 5, 4,
    'It looked polished and confident in the walkthrough.'),
  make(2, 'onboarding-agent', 'demo-A', 'demo', [2, 3, 2, 3], [7, 6, 6, 7, 5], 6, 3,
    'The demo made it seem capable, though I am not sure how it works.'),
  make(3, 'onboarding-agent', 'demo-A', 'demo', [3, 3, 2, 2], [6, 7, 6, 6, 6], 5, 4,
    'Slick UI. Trusted the presenter more than the system really.'),
  make(4, 'onboarding-agent', 'demo-A', 'mockups', [2, 2, 3, 2], [6, 6, 6, 5, 6], 4, 3,
    'Only saw screens, but they looked well thought out.'),
  make(5, 'onboarding-agent', 'demo-B', 'demo', [5, 5, 6, 5], [5, 5, 6, 5, 5], 6, 6,
    'They explained the limitations up front, which I appreciated.'),
  make(6, 'onboarding-agent', 'demo-B', 'demo', [6, 5, 5, 6], [5, 6, 5, 5, 6], 6, 6,
    'Clear about what it can and cannot do. Felt honest.'),
  make(7, 'onboarding-agent', 'demo-B', 'prototype', [6, 6, 6, 5], [6, 5, 6, 6, 5], 7, 6,
    'Tried it myself; behaved as described.'),
  make(8, 'onboarding-agent', 'demo-B', 'prototype', [5, 6, 5, 6], [6, 6, 5, 6, 6], 6, 7,
    'Hands-on made a big difference in understanding it.'),
];
