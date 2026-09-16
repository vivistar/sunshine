import { describe, it, expect } from 'vitest';
import {
  scoreResponse,
  aggregate,
  aggregateByGroup,
  exposureDistributionsDiffer,
  _internals,
} from './scoring';

// A fully-answered response helper.
function resp(overrides = {}) {
  return {
    q1: 5, q2: 5, q3: 5, q4: 5, q5: 5, q6: 5, q7: 5, q8: 5, q9: 5,
    q10: 5, q11: 5, exposure: 'demo',
    ...overrides,
  };
}

describe('helpers', () => {
  it('mean and sample sd', () => {
    expect(_internals.mean([2, 4, 6])).toBe(4);
    // sd of [2,4,6] with n-1: sqrt(((4)+(0)+(4))/2)=sqrt(4)=2
    expect(_internals.std([2, 4, 6])).toBe(2);
    expect(_internals.std([5])).toBeNull();
  });
  it('rejects invalid likert', () => {
    expect(_internals.isValidLikert(0)).toBe(false);
    expect(_internals.isValidLikert(8)).toBe(false);
    expect(_internals.isValidLikert(3.5)).toBe(false);
    expect(_internals.isValidLikert(4)).toBe(true);
  });
});

describe('S1 Understanding = mean(q1,q3,q4,q8)', () => {
  it('worked example: 6,4,2,4 -> 4', () => {
    const s = scoreResponse(resp({ q1: 6, q3: 4, q4: 2, q8: 4 }));
    expect(s.understanding).toBe(4); // (6+4+2+4)/4
  });
});

describe('S2 Performance = mean(q2,q5,q6,q7,q9)', () => {
  it('worked example: 1,2,3,4,5 -> 3', () => {
    const s = scoreResponse(resp({ q2: 1, q5: 2, q6: 3, q7: 4, q9: 5 }));
    expect(s.performance).toBe(3); // (1+2+3+4+5)/5
  });
});

describe('S3 Overall = mean(q1..q9)', () => {
  it('all 5 -> 5', () => {
    expect(scoreResponse(resp()).overall).toBe(5);
  });
  it('worked example mixed', () => {
    const s = scoreResponse(
      resp({ q1: 1, q2: 2, q3: 3, q4: 4, q5: 5, q6: 6, q7: 7, q8: 1, q9: 8 - 1 })
    );
    // 1+2+3+4+5+6+7+1+7 = 36 / 9 = 4
    expect(s.overall).toBe(4);
  });
});

describe('S4 drop_q9_for_low_exposure', () => {
  it('drops q9 from P only when toggle on AND exposure is spec/mockups', () => {
    const r = resp({ q2: 4, q5: 4, q6: 4, q7: 4, q9: 1, exposure: 'spec' });
    const off = scoreResponse(r, { dropQ9ForLowExposure: false });
    expect(off.performance).toBe((4 + 4 + 4 + 4 + 1) / 5); // 3.4
    expect(off.q9Dropped).toBe(false);

    const on = scoreResponse(r, { dropQ9ForLowExposure: true });
    expect(on.performance).toBe(4); // q9 excluded -> mean of four 4s
    expect(on.q9Dropped).toBe(true);
  });
  it('does NOT drop q9 for high exposure even when toggle on', () => {
    const r = resp({ q2: 4, q5: 4, q6: 4, q7: 4, q9: 1, exposure: 'prototype' });
    const on = scoreResponse(r, { dropQ9ForLowExposure: true });
    expect(on.performance).toBe((4 + 4 + 4 + 4 + 1) / 5);
    expect(on.q9Dropped).toBe(false);
  });
});

describe('S5 missing data -> null subscale, no imputation', () => {
  it('missing q3 nulls Understanding but Performance survives', () => {
    const s = scoreResponse(resp({ q3: undefined }));
    expect(s.understanding).toBeNull();
    expect(s.performance).toBe(5);
    expect(s.overall).toBeNull();
    expect(s.complete).toBe(false);
  });
  it('aggregate excludes nulls and counts incompletes', () => {
    const agg = aggregate([resp(), resp({ q3: undefined }), resp()]);
    expect(agg.understanding.n).toBe(2); // one excluded
    expect(agg.excludedIncomplete).toBe(1);
    expect(agg.performance.n).toBe(3); // performance intact for all
  });
});

describe('S6 diagnostics never fold into trust score', () => {
  it('extreme q10/q11 do not move U/P/overall', () => {
    const s = scoreResponse(resp({ q10: 1, q11: 7 }));
    expect(s.understanding).toBe(5);
    expect(s.performance).toBe(5);
    expect(s.overall).toBe(5);
  });
  it('aggregate reports certainty/sufficiency separately', () => {
    const agg = aggregate([resp({ q10: 2, q11: 6 }), resp({ q10: 4, q11: 4 })]);
    expect(agg.certainty.mean).toBe(3);
    expect(agg.sufficiency.mean).toBe(5);
  });
});

describe('S7 straight-lining flag', () => {
  it('flags identical q1..q9', () => {
    expect(scoreResponse(resp({})).straightLined).toBe(true); // all 5s
  });
  it('does not flag varied answers', () => {
    expect(scoreResponse(resp({ q1: 4 })).straightLined).toBe(false);
  });
  it('aggregate counts straight-liners', () => {
    const agg = aggregate([resp(), resp({ q1: 1 }), resp()]);
    expect(agg.straightLinedCount).toBe(2);
  });
});

describe('aggregateByGroup', () => {
  it('splits by condition', () => {
    const rows = [
      resp({ condition: 'A', q1: 6, q3: 6, q4: 6, q8: 6 }),
      resp({ condition: 'B', q1: 2, q3: 2, q4: 2, q8: 2 }),
    ];
    const groups = aggregateByGroup(rows, 'condition');
    expect(groups.map((g) => g.key)).toEqual(['A', 'B']);
    expect(groups[0].understanding.mean).toBe(6);
    expect(groups[1].understanding.mean).toBe(2);
  });
});

describe('exposureDistributionsDiffer', () => {
  it('true when arms have very different exposure mixes', () => {
    const arms = [
      { exposureCounts: { demo: 10 } },
      { exposureCounts: { spec: 10 } },
    ];
    expect(exposureDistributionsDiffer(arms)).toBe(true);
  });
  it('false when mixes match', () => {
    const arms = [
      { exposureCounts: { demo: 5, spec: 5 } },
      { exposureCounts: { demo: 6, spec: 6 } },
    ];
    expect(exposureDistributionsDiffer(arms)).toBe(false);
  });
});
