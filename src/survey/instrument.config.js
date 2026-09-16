// Anticipated Trust instrument — adapted from TOAST (Wojton, Porter, Lane,
// Bieber & Madhavan, 2020). Prospective rewording BREAKS the original
// psychometric validation. Always label output "anticipated trust (adapted
// TOAST)", never "TOAST score". Citation confidence: moderate-high.
//
// This is fixed, single-instrument content by design (PRD §4). The `version`
// is stamped onto every stored response so wording changes never silently
// pollute pooled analysis.

export const INSTRUMENT_VERSION = 'anticipated-trust-1.0.0';

export const LIKERT = {
  min: 1,
  max: 7,
  labels: [
    'Strongly disagree',
    'Disagree',
    'Somewhat disagree',
    'Neither agree nor disagree',
    'Somewhat agree',
    'Agree',
    'Strongly agree',
  ],
};

// Stem shown verbatim above the items. Placeholders filled per study via the
// URL params (exposureVerb + systemName + purpose) when present.
export const STEM_TEMPLATE =
  'You have just {exposureVerb} {systemName}, a system intended to {purpose}. ' +
  'Based only on what you have seen so far, rate how much you agree with each ' +
  'statement. There are no right answers — we want your honest expectation, ' +
  'including where you feel unsure.';

export const STEM_DEFAULTS = {
  exposureVerb: 'seen a demo of',
  systemName: 'this system',
  purpose: 'help you accomplish a task',
};

// Section A — exposure check. Single-select, gates interpretation.
export const EXPOSURE_OPTIONS = [
  { value: 'spec', label: 'A written description or spec' },
  { value: 'mockups', label: 'Static screens / mockups' },
  { value: 'demo', label: 'A demo video / walkthrough' },
  { value: 'prototype', label: 'Used a working prototype myself' },
];

export const EXPOSURE_VALUES = EXPOSURE_OPTIONS.map((o) => o.value);

// Section B — core items. subscale: U = Understanding, P = Performance.
// Labels are INTERNAL ONLY — never rendered on the respondent's copy.
export const CORE_ITEMS = [
  { id: 'q1', subscale: 'U', text: 'I understand what the system is intended to do.' },
  { id: 'q2', subscale: 'P', text: 'I expect the system would help me achieve my goals.' },
  { id: 'q3', subscale: 'U', text: 'I understand the limitations the system would have.' },
  { id: 'q4', subscale: 'U', text: 'I understand the capabilities the system would have.' },
  { id: 'q5', subscale: 'P', text: 'I expect the system would perform consistently.' },
  { id: 'q6', subscale: 'P', text: 'I expect the system would perform the way it should.' },
  { id: 'q7', subscale: 'P', text: 'I would feel comfortable relying on the information the system provides.' },
  { id: 'q8', subscale: 'U', text: 'I understand how the system would carry out its tasks.' },
  {
    id: 'q9',
    subscale: 'P',
    text: 'I expect I would rarely be surprised by how the system responds.',
    weak_if_no_interaction: true, // see scoring rule S4
  },
];

// Section C — diagnostics. Excluded from the trust score.
export const DIAGNOSTIC_ITEMS = [
  {
    id: 'q10',
    type: 'certainty',
    scale: 'likert',
    text: 'I feel confident in the judgments I just made, given how much I have seen of the system.',
  },
  {
    id: 'q11',
    type: 'sufficiency',
    scale: 'likert',
    text: 'I had enough information to fairly evaluate this system.',
  },
  {
    id: 'q12',
    type: 'basis',
    scale: 'text',
    text: 'What did you base your trust (or distrust) mostly on?',
  },
];

// Which core items feed each subscale (source of truth for scoring).
export const UNDERSTANDING_ITEMS = ['q1', 'q3', 'q4', 'q8'];
export const PERFORMANCE_ITEMS = ['q2', 'q5', 'q6', 'q7', 'q9'];
export const ALL_CORE_ITEMS = CORE_ITEMS.map((i) => i.id);
export const LIKERT_ITEMS = [...ALL_CORE_ITEMS, 'q10', 'q11'];

export function buildStem(overrides = {}) {
  const v = { ...STEM_DEFAULTS, ...overrides };
  return STEM_TEMPLATE.replace('{exposureVerb}', v.exposureVerb)
    .replace('{systemName}', v.systemName)
    .replace('{purpose}', v.purpose);
}
