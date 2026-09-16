// Scoring engine — pure, side-effect-free (PRD §5.4).
// Usable headless: import CSV rows -> get scores, independent of the UI.
//
// Output is "anticipated trust (adapted TOAST)", never a validated TOAST score.

import {
  UNDERSTANDING_ITEMS,
  PERFORMANCE_ITEMS,
  ALL_CORE_ITEMS,
} from './instrument.config';

const LOW_EXPOSURE = new Set(['spec', 'mockups']);

function mean(nums) {
  if (nums.length === 0) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function std(nums) {
  // Sample standard deviation (n-1). null for n < 2.
  if (nums.length < 2) return null;
  const m = mean(nums);
  const variance =
    nums.reduce((acc, x) => acc + (x - m) ** 2, 0) / (nums.length - 1);
  return Math.sqrt(variance);
}

function isValidLikert(v) {
  return Number.isInteger(v) && v >= 1 && v <= 7;
}

// Collect valid item values for a response; returns null if ANY listed item
// is missing/invalid (S5: do not impute — null the subscale).
function collectItems(response, itemIds) {
  const out = [];
  for (const id of itemIds) {
    const v = response[id];
    if (!isValidLikert(v)) return null;
    out.push(v);
  }
  return out;
}

/**
 * Score a single response.
 * @param {object} response - row with q1..q9 (q10/q11 diagnostics), exposure.
 * @param {object} options
 * @param {boolean} options.dropQ9ForLowExposure - S4 toggle.
 * @returns {{understanding, performance, overall, q9Dropped, straightLined, complete}}
 */
export function scoreResponse(response, options = {}) {
  const { dropQ9ForLowExposure = false } = options;

  // S1 Understanding: mean of q1, q3, q4, q8.
  const uVals = collectItems(response, UNDERSTANDING_ITEMS);

  // S4: optionally drop q9 from Performance for low-exposure responses.
  let perfItems = PERFORMANCE_ITEMS;
  let q9Dropped = false;
  if (dropQ9ForLowExposure && LOW_EXPOSURE.has(response.exposure)) {
    perfItems = PERFORMANCE_ITEMS.filter((id) => id !== 'q9');
    q9Dropped = true;
  }

  // S2 Performance: mean of q2, q5, q6, q7, q9 (or 4 items if q9 dropped).
  const pVals = collectItems(response, perfItems);

  // S3 Overall: mean of q1..q9.
  const allVals = collectItems(response, ALL_CORE_ITEMS);

  // S7 Straight-lining: identical answer across all of q1..q9 (needs all present).
  let straightLined = false;
  if (allVals) {
    straightLined = allVals.every((v) => v === allVals[0]);
  }

  return {
    understanding: uVals ? mean(uVals) : null,
    performance: pVals ? mean(pVals) : null,
    overall: allVals ? mean(allVals) : null,
    q9Dropped,
    straightLined,
    complete: Boolean(allVals),
  };
}

/**
 * Aggregate scored responses into subscale summaries.
 * @param {object[]} responses
 * @param {object} options - passed to scoreResponse.
 * @returns {object} { n, understanding:{mean,sd,n}, performance:{...},
 *   overall:{...}, certainty:{...}, sufficiency:{...}, excludedIncomplete,
 *   straightLinedCount, q9AppliedCount, exposureCounts }
 */
export function aggregate(responses, options = {}) {
  const scored = responses.map((r) => ({ r, s: scoreResponse(r, options) }));

  const uScores = [];
  const pScores = [];
  const oScores = [];
  const certainty = [];
  const sufficiency = [];
  let excludedIncomplete = 0;
  let straightLinedCount = 0;
  let q9AppliedCount = 0;
  const exposureCounts = {};

  for (const { r, s } of scored) {
    if (!s.complete) excludedIncomplete += 1;
    if (s.straightLined) straightLinedCount += 1;
    if (s.q9Dropped) q9AppliedCount += 1;
    if (s.understanding != null) uScores.push(s.understanding);
    if (s.performance != null) pScores.push(s.performance);
    if (s.overall != null) oScores.push(s.overall);
    if (isValidLikert(r.q10)) certainty.push(r.q10);
    if (isValidLikert(r.q11)) sufficiency.push(r.q11);
    const e = r.exposure || 'unknown';
    exposureCounts[e] = (exposureCounts[e] || 0) + 1;
  }

  const summarize = (arr) => ({
    mean: mean(arr),
    sd: std(arr),
    n: arr.length,
  });

  return {
    n: responses.length,
    understanding: summarize(uScores),
    performance: summarize(pScores),
    overall: summarize(oScores),
    certainty: summarize(certainty),
    sufficiency: summarize(sufficiency),
    excludedIncomplete,
    straightLinedCount,
    q9AppliedCount,
    exposureCounts,
  };
}

/**
 * Group responses by a key (e.g. "condition") and aggregate each group.
 * @returns {object[]} [{ key, ...aggregate }]
 */
export function aggregateByGroup(responses, groupKey, options = {}) {
  const groups = new Map();
  for (const r of responses) {
    const k = r[groupKey] ?? '(none)';
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(r);
  }
  return [...groups.entries()]
    .map(([key, rows]) => ({ key, ...aggregate(rows, options) }))
    .sort((a, b) => String(a.key).localeCompare(String(b.key)));
}

// Compare exposure distributions across arms; returns true if they differ
// enough to warrant a warning (any exposure's share differs by > 20 points).
export function exposureDistributionsDiffer(arms) {
  const shares = arms.map((arm) => {
    const total = Object.values(arm.exposureCounts).reduce((a, b) => a + b, 0);
    const dist = {};
    for (const [k, v] of Object.entries(arm.exposureCounts)) {
      dist[k] = total ? v / total : 0;
    }
    return dist;
  });
  const allKeys = new Set(shares.flatMap((d) => Object.keys(d)));
  for (const key of allKeys) {
    const vals = shares.map((d) => d[key] || 0);
    if (Math.max(...vals) - Math.min(...vals) > 0.2) return true;
  }
  return false;
}

export const _internals = { mean, std, isValidLikert };
