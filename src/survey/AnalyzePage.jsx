import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  aggregate,
  aggregateByGroup,
  exposureDistributionsDiffer,
  scoreResponse,
} from './scoring';
import { EXPOSURE_OPTIONS, DIAGNOSTIC_ITEMS } from './instrument.config';
import {
  getResponses,
  addResponses,
  clearResponses,
  getTags,
  setTagsForResponse,
} from './storage';
import { EXAMPLE_RESPONSES } from './sampleData';
import { parseResponsesCsv, responsesToCsv, downloadCsv } from './csv';

const fmt = (v, d = 2) => (v == null ? '—' : v.toFixed(d));

// Client-side gate ONLY. With a static SPA there is no server to check a
// secret, so this is a soft gate, not a security boundary. Anyone determined
// can read the data in their own browser's storage. For a real access boundary,
// move responses to a server datastore and check the passphrase server-side.
const PASSCODE = import.meta.env.VITE_SURVEY_PASSCODE || 'sunshine';

function StatCard({ label, agg, accent }) {
  return (
    <div className="rounded-xl border border-white/15 bg-white/5 p-4">
      <p className="text-white/40 text-xs uppercase tracking-widest">{label}</p>
      <p className={`text-3xl font-light mt-1 ${accent || 'text-white'}`}>
        {fmt(agg.mean)}
        <span className="text-sm text-white/40"> / 7</span>
      </p>
      <p className="text-white/40 text-xs mt-1">
        n={agg.n} · SD {fmt(agg.sd)}
      </p>
    </div>
  );
}

// U-vs-P scatter: surfaces "high P, low U" over-trust quadrant (PRD §5.5).
function UvsPPlot({ arms }) {
  const size = 260;
  const pad = 34;
  const scale = (v) => pad + ((v - 1) / 6) * (size - 2 * pad);
  const palette = ['#38bdf8', '#f59e0b', '#a78bfa', '#34d399', '#f472b6'];

  return (
    <div className="rounded-xl border border-white/15 bg-white/5 p-4">
      <p className="text-white/40 text-xs uppercase tracking-widest mb-1">
        Understanding vs. Performance
      </p>
      <p className="text-white/50 text-xs mb-3">
        Top-right of the diagonal = expected performance outruns understanding
        (possible over-trust on thin understanding).
      </p>
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[320px] mx-auto" role="img"
        aria-label="Scatter of understanding versus performance means per condition">
        {/* over-trust region shading (P > U) */}
        <polygon
          points={`${pad},${size - pad} ${size - pad},${pad} ${pad},${pad}`}
          fill="#f59e0b" opacity="0.08"
        />
        <line x1={pad} y1={size - pad} x2={size - pad} y2={pad}
          stroke="#ffffff" strokeOpacity="0.2" strokeDasharray="4 4" />
        {/* axes */}
        <line x1={pad} y1={size - pad} x2={size - pad} y2={size - pad} stroke="#ffffff" strokeOpacity="0.3" />
        <line x1={pad} y1={pad} x2={pad} y2={size - pad} stroke="#ffffff" strokeOpacity="0.3" />
        <text x={size / 2} y={size - 6} fill="#ffffff" fillOpacity="0.5" fontSize="9" textAnchor="middle">
          Understanding (1–7)
        </text>
        <text x={10} y={size / 2} fill="#ffffff" fillOpacity="0.5" fontSize="9" textAnchor="middle"
          transform={`rotate(-90 10 ${size / 2})`}>
          Performance (1–7)
        </text>
        {[1, 4, 7].map((t) => (
          <g key={t}>
            <text x={scale(t)} y={size - pad + 12} fill="#ffffff" fillOpacity="0.4" fontSize="8" textAnchor="middle">{t}</text>
            <text x={pad - 6} y={size - scale(t) + 3} fill="#ffffff" fillOpacity="0.4" fontSize="8" textAnchor="end">{t}</text>
          </g>
        ))}
        {arms.map((a, i) =>
          a.understanding.mean != null && a.performance.mean != null ? (
            <g key={a.key}>
              <circle cx={scale(a.understanding.mean)} cy={size - scale(a.performance.mean)}
                r="6" fill={palette[i % palette.length]} fillOpacity="0.85" />
              <text x={scale(a.understanding.mean) + 9} y={size - scale(a.performance.mean) + 3}
                fill="#ffffff" fillOpacity="0.8" fontSize="9">{a.key}</text>
            </g>
          ) : null
        )}
      </svg>
    </div>
  );
}

export default function AnalyzePage() {
  const [authed, setAuthed] = useState(false);
  const [pass, setPass] = useState('');

  const [responses, setResponses] = useState(() => {
    const stored = getResponses();
    return stored.length ? stored : EXAMPLE_RESPONSES;
  });
  const [usingExamples, setUsingExamples] = useState(getResponses().length === 0);
  const [tagsMap, setTagsMap] = useState(getTags());
  const [dropQ9, setDropQ9] = useState(false);

  const fileRef = useRef(null);
  const [importReport, setImportReport] = useState(null);

  // Filters
  const [studyFilter, setStudyFilter] = useState('');
  const [exposureFilter, setExposureFilter] = useState('all');
  const [certaintyMin, setCertaintyMin] = useState(1);

  const studies = useMemo(
    () => [...new Set(responses.map((r) => r.study).filter(Boolean))],
    [responses]
  );

  const activeStudy = studyFilter || studies[0] || '';

  const filtered = useMemo(() => {
    return responses.filter((r) => {
      if (activeStudy && r.study !== activeStudy) return false;
      if (exposureFilter !== 'all' && r.exposure !== exposureFilter) return false;
      if (Number(r.q10) < certaintyMin) return false;
      return true;
    });
  }, [responses, activeStudy, exposureFilter, certaintyMin]);

  const opts = { dropQ9ForLowExposure: dropQ9 };
  const overall = useMemo(() => aggregate(filtered, opts), [filtered, dropQ9]);
  const byCondition = useMemo(
    () => aggregateByGroup(filtered, 'condition', opts),
    [filtered, dropQ9]
  );
  const exposureMismatch =
    byCondition.length >= 2 && exposureDistributionsDiffer(byCondition);

  function handleImport(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const { valid, rejected } = parseResponsesCsv(String(reader.result));
      if (valid.length) {
        const merged = addResponses(valid);
        setResponses(merged);
        setUsingExamples(false);
      }
      setImportReport({ added: valid.length, rejected });
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  function handleExport() {
    downloadCsv(
      `survey-${activeStudy || 'all'}-export.csv`,
      responsesToCsv(filtered, (r) => scoreResponse(r, opts))
    );
  }

  function loadExamples() {
    setResponses(EXAMPLE_RESPONSES);
    setUsingExamples(true);
  }

  function reset() {
    clearResponses();
    setResponses(EXAMPLE_RESPONSES);
    setUsingExamples(true);
    setImportReport(null);
  }

  function updateTags(responseId, raw) {
    const tags = raw.split(',').map((t) => t.trim()).filter(Boolean);
    const map = setTagsForResponse(responseId, tags);
    setTagsMap({ ...map });
  }

  if (!authed) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex items-center justify-center px-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setAuthed(pass === PASSCODE);
          }}
          className="max-w-sm w-full"
        >
          <Link to="/" className="text-white/40 text-xs uppercase tracking-widest hover:text-white/70">
            ← Sunshine
          </Link>
          <h1 className="font-display text-white text-2xl mt-3 mb-2">Analysis Dashboard</h1>
          <p className="text-white/50 text-sm mb-5">
            Researcher access. Enter the passphrase.
          </p>
          <input
            type="password"
            value={pass}
            onChange={(e) => setPass(e.target.value)}
            placeholder="Passphrase"
            className="w-full rounded-xl bg-white/5 border border-white/20 text-white p-3 mb-3 focus:border-white/60 focus:outline-none"
            autoFocus
          />
          {pass && pass !== PASSCODE && (
            <p className="text-red-300 text-xs mb-3">Incorrect passphrase.</p>
          )}
          <button className="w-full rounded-xl bg-white text-slate-900 font-semibold py-3 hover:bg-white/90">
            Enter
          </button>
          <p className="text-white/25 text-[11px] mt-4 leading-relaxed">
            Note: this is a client-side gate on a static site, not a security
            boundary. Set <code>VITE_SURVEY_PASSCODE</code> at build time to change
            it. For enforced access control, responses must move to a server store.
          </p>
        </form>
      </div>
    );
  }

  const q12Rows = filtered.filter((r) => (r.q12 || '').trim());

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 py-8 px-5">
      <div className="max-w-5xl mx-auto">
        <header className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div>
            <Link to="/" className="text-white/40 text-xs uppercase tracking-widest hover:text-white/70">
              ← Sunshine
            </Link>
            <h1 className="font-display text-white text-2xl mt-1">Analysis Dashboard</h1>
            <p className="text-amber-300/80 text-xs mt-1">
              Anticipated trust (adapted TOAST) — not a validated TOAST score.
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => fileRef.current?.click()}
              className="rounded-lg border border-white/25 text-white/90 text-sm px-3 py-2 hover:bg-white/10">
              Import CSV
            </button>
            <button onClick={handleExport}
              className="rounded-lg border border-white/25 text-white/90 text-sm px-3 py-2 hover:bg-white/10">
              Export CSV
            </button>
            <input ref={fileRef} type="file" accept=".csv,text/csv" onChange={handleImport} className="hidden" />
          </div>
        </header>

        {usingExamples && (
          <div className="rounded-lg border border-amber-400/40 bg-amber-500/10 text-amber-100 text-sm px-4 py-2.5 mb-5">
            Showing <strong>example data</strong> (illustrative, not real responses).
            Import a CSV or collect responses via the survey link to replace it.
          </div>
        )}

        {importReport && (
          <div className="rounded-lg border border-white/20 bg-white/5 text-white/80 text-sm px-4 py-3 mb-5">
            Imported <strong>{importReport.added}</strong> valid row(s).
            {importReport.rejected.length > 0 && (
              <>
                {' '}Rejected <strong>{importReport.rejected.length}</strong>:
                <ul className="mt-1 list-disc list-inside text-red-200 text-xs max-h-32 overflow-auto">
                  {importReport.rejected.slice(0, 20).map((rej, i) => (
                    <li key={i}>Row {rej.row}: {rej.reasons.join('; ')}</li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        {/* Controls */}
        <div className="grid sm:grid-cols-4 gap-3 mb-6">
          <label className="text-sm">
            <span className="text-white/40 text-xs uppercase tracking-widest block mb-1">Study</span>
            <select value={activeStudy} onChange={(e) => setStudyFilter(e.target.value)}
              className="w-full rounded-lg bg-white/5 border border-white/20 text-white p-2">
              {studies.length === 0 && <option value="">(none)</option>}
              {studies.map((s) => <option key={s} value={s} className="bg-slate-800">{s}</option>)}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-white/40 text-xs uppercase tracking-widest block mb-1">Exposure</span>
            <select value={exposureFilter} onChange={(e) => setExposureFilter(e.target.value)}
              className="w-full rounded-lg bg-white/5 border border-white/20 text-white p-2">
              <option value="all" className="bg-slate-800">All</option>
              {EXPOSURE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value} className="bg-slate-800">{o.label}</option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-white/40 text-xs uppercase tracking-widest block mb-1">
              Min certainty (q10): {certaintyMin}
            </span>
            <input type="range" min="1" max="7" value={certaintyMin}
              onChange={(e) => setCertaintyMin(Number(e.target.value))}
              className="w-full accent-sky-400 mt-2" />
          </label>
          <label className="text-sm flex items-end">
            <span className="flex items-center gap-2 text-white/70">
              <input type="checkbox" checked={dropQ9} onChange={(e) => setDropQ9(e.target.checked)}
                className="accent-sky-400 w-4 h-4" />
              Drop q9 (low exposure)
            </span>
          </label>
        </div>

        {/* Overall subscale summary */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
          <StatCard label="Understanding" agg={overall.understanding} accent="text-sky-300" />
          <StatCard label="Performance" agg={overall.performance} accent="text-amber-300" />
          <StatCard label="Overall" agg={overall.overall} />
          <StatCard label="Certainty (q10)" agg={overall.certainty} accent="text-white/80" />
        </div>

        {/* Data-quality warnings */}
        <div className="space-y-2 mb-6 text-sm">
          {dropQ9 && overall.q9AppliedCount > 0 && (
            <p className="text-sky-200/80">
              Item-9 rule applied to {overall.q9AppliedCount} low-exposure response(s):
              Performance averaged over 4 items for those.
            </p>
          )}
          {overall.excludedIncomplete > 0 && (
            <p className="text-white/60">
              {overall.excludedIncomplete} incomplete response(s) excluded from subscale means (not imputed).
            </p>
          )}
          {overall.straightLinedCount > 0 && (
            <p className="text-amber-200/80">
              ⚑ {overall.straightLinedCount} straight-lined response(s) flagged for review (not auto-excluded).
            </p>
          )}
          {overall.sufficiency.mean != null && overall.sufficiency.mean < 4 && (
            <p className="text-red-200/90">
              ⚠ Low sufficiency (mean q11 = {fmt(overall.sufficiency.mean)}): respondents
              felt they lacked information to judge. Interpret scores cautiously.
            </p>
          )}
        </div>

        {/* U-vs-P + by-condition table */}
        <div className="grid md:grid-cols-2 gap-4 mb-6">
          <UvsPPlot arms={byCondition} />
          <div className="rounded-xl border border-white/15 bg-white/5 p-4 overflow-auto">
            <p className="text-white/40 text-xs uppercase tracking-widest mb-3">By condition</p>
            {exposureMismatch && (
              <p className="text-amber-200/90 text-xs mb-3">
                ⚠ Exposure distributions differ across conditions — comparing their
                scores directly may be misleading. Consider filtering to one exposure.
              </p>
            )}
            <table className="w-full text-sm text-white/85">
              <thead className="text-white/40 text-xs uppercase">
                <tr>
                  <th className="text-left font-medium pb-2">Condition</th>
                  <th className="text-right font-medium pb-2">n</th>
                  <th className="text-right font-medium pb-2">U (SD)</th>
                  <th className="text-right font-medium pb-2">P (SD)</th>
                  <th className="text-right font-medium pb-2">Suff.</th>
                </tr>
              </thead>
              <tbody>
                {byCondition.map((c) => (
                  <tr key={c.key} className="border-t border-white/10">
                    <td className="py-2">{c.key}</td>
                    <td className="text-right">{c.n}</td>
                    <td className="text-right text-sky-300">{fmt(c.understanding.mean)} <span className="text-white/30">({fmt(c.understanding.sd)})</span></td>
                    <td className="text-right text-amber-300">{fmt(c.performance.mean)} <span className="text-white/30">({fmt(c.performance.sd)})</span></td>
                    <td className="text-right text-white/60">{fmt(c.sufficiency.mean, 1)}</td>
                  </tr>
                ))}
                {byCondition.length === 0 && (
                  <tr><td colSpan={5} className="py-3 text-white/40">No responses for this filter.</td></tr>
                )}
              </tbody>
            </table>
            <p className="text-white/30 text-[11px] mt-3">
              Descriptive only. No significance test is implied.
            </p>
          </div>
        </div>

        {/* Exposure distribution */}
        <div className="rounded-xl border border-white/15 bg-white/5 p-4 mb-6">
          <p className="text-white/40 text-xs uppercase tracking-widest mb-2">Exposure mix (filtered)</p>
          <div className="flex flex-wrap gap-3 text-sm text-white/80">
            {Object.entries(overall.exposureCounts).map(([k, v]) => (
              <span key={k} className="rounded-lg bg-white/10 px-3 py-1">{k}: {v}</span>
            ))}
          </div>
        </div>

        {/* q12 basis review with tagging */}
        <div className="rounded-xl border border-white/15 bg-white/5 p-4">
          <p className="text-white/40 text-xs uppercase tracking-widest mb-3">
            {DIAGNOSTIC_ITEMS.find((d) => d.id === 'q12').text} — {q12Rows.length} response(s)
          </p>
          <div className="space-y-3 max-h-96 overflow-auto">
            {q12Rows.map((r) => (
              <div key={r.response_id} className="border-t border-white/10 pt-3">
                <p className="text-white/85 text-sm">"{r.q12}"</p>
                <div className="flex flex-wrap items-center gap-2 mt-1.5 text-xs text-white/40">
                  <span>{r.condition || '(no condition)'}</span>
                  <span>· {r.exposure}</span>
                </div>
                <input
                  type="text"
                  defaultValue={(tagsMap[r.response_id] || []).join(', ')}
                  onBlur={(e) => updateTags(r.response_id, e.target.value)}
                  placeholder="add tags (comma-separated)…"
                  className="mt-2 w-full rounded-lg bg-slate-900/50 border border-white/15 text-white/90 text-xs p-2 focus:border-white/50 focus:outline-none"
                />
              </div>
            ))}
            {q12Rows.length === 0 && <p className="text-white/40 text-sm">No open responses for this filter.</p>}
          </div>
        </div>

        <div className="flex justify-between items-center mt-6">
          <button onClick={loadExamples} className="text-white/40 text-xs underline hover:text-white/70">
            Load example data
          </button>
          <button onClick={reset} className="text-red-300/60 text-xs underline hover:text-red-300">
            Clear stored responses
          </button>
        </div>
      </div>
    </div>
  );
}
