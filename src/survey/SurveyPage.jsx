import { useMemo, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import {
  CORE_ITEMS,
  DIAGNOSTIC_ITEMS,
  EXPOSURE_OPTIONS,
  LIKERT,
  INSTRUMENT_VERSION,
  buildStem,
} from './instrument.config';
import { saveResponse } from './storage';
import { submitResponse } from './api';
import { responsesToCsv, downloadCsv } from './csv';
import { scoreResponse } from './scoring';

function LikertRow({ id, text, value, onChange, invalid }) {
  const name = `item-${id}`;
  return (
    <fieldset
      className={`rounded-xl border p-4 transition-colors ${
        invalid ? 'border-red-400/70 bg-red-500/5' : 'border-white/15 bg-white/5'
      }`}
    >
      <legend className="sr-only">{text}</legend>
      <p className="text-white/90 text-base mb-3">{text}</p>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={text}>
        {Array.from({ length: LIKERT.max }, (_, i) => i + 1).map((n) => {
          const selected = value === n;
          return (
            <label
              key={n}
              className={`flex-1 min-w-[40px] cursor-pointer rounded-lg border px-2 py-2 text-center text-sm transition-colors ${
                selected
                  ? 'border-white bg-white text-slate-900 font-semibold'
                  : 'border-white/25 text-white/80 hover:border-white/60'
              }`}
              title={LIKERT.labels[n - 1]}
            >
              <input
                type="radio"
                name={name}
                value={n}
                checked={selected}
                onChange={() => onChange(id, n)}
                className="sr-only"
              />
              {n}
            </label>
          );
        })}
      </div>
      <div className="flex justify-between text-[11px] text-white/40 mt-2">
        <span>1 · {LIKERT.labels[0]}</span>
        <span>{LIKERT.labels[LIKERT.max - 1]} · {LIKERT.max}</span>
      </div>
      {invalid && (
        <p className="text-red-300 text-xs mt-2">Please select a rating.</p>
      )}
    </fieldset>
  );
}

export default function SurveyPage() {
  const [params] = useSearchParams();
  const study = params.get('study') || '';
  const condition = params.get('condition') || '';

  const stem = useMemo(
    () =>
      buildStem({
        exposureVerb: params.get('exposureVerb') || undefined,
        systemName: params.get('system') || undefined,
        purpose: params.get('purpose') || undefined,
      }),
    [params]
  );

  const [answers, setAnswers] = useState({});
  const [exposure, setExposure] = useState('');
  const [q12, setQ12] = useState('');
  const [errors, setErrors] = useState({});
  const [done, setDone] = useState(false);

  const setAnswer = (id, n) => {
    setAnswers((a) => ({ ...a, [id]: n }));
    setErrors((e) => ({ ...e, [id]: false }));
  };

  const likertDiagnostics = DIAGNOSTIC_ITEMS.filter((d) => d.scale === 'likert');

  function validate() {
    const e = {};
    if (!exposure) e.exposure = true;
    for (const item of CORE_ITEMS) if (!answers[item.id]) e[item.id] = true;
    for (const d of likertDiagnostics) if (!answers[d.id]) e[d.id] = true;
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  const [submitting, setSubmitting] = useState(false);
  const [offlineSaved, setOfflineSaved] = useState(false);
  const [lastResponse, setLastResponse] = useState(null);

  async function handleSubmit(ev) {
    ev.preventDefault();
    if (!validate()) {
      const first = document.querySelector('[data-invalid="true"]');
      first?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    const response = {
      response_id: crypto.randomUUID(),
      instrument_version: INSTRUMENT_VERSION,
      study,
      condition,
      exposure,
      ...CORE_ITEMS.reduce((o, it) => ({ ...o, [it.id]: answers[it.id] }), {}),
      q10: answers.q10,
      q11: answers.q11,
      q12: q12.trim(),
      submitted_at: new Date().toISOString(),
      source: 'web',
      tags: '',
    };

    setSubmitting(true);
    try {
      await submitResponse(response);
    } catch {
      // Backend unreachable (e.g. local dev without DB) — keep the response in
      // this browser so it isn't lost; it can be exported to CSV and imported.
      saveResponse(response);
      setOfflineSaved(true);
    } finally {
      setSubmitting(false);
      setLastResponse(response);
      setDone(true);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  if (done) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-900 via-purple-900 to-slate-900 flex items-center justify-center px-6">
        <div className="max-w-md text-center">
          <div className="text-5xl mb-4">✦</div>
          <h1 className="font-display text-white text-3xl mb-3">Thank you</h1>
          <p className="text-white/70 mb-6">
            Your response has been recorded. There are no right answers — thank
            you for sharing your honest expectations.
          </p>
          {offlineSaved && (
            <p className="text-amber-200/80 text-xs mb-6">
              The server was unreachable, so your response was saved in this
              browser instead. You can export it as CSV below and send it to the
              researcher to import.
            </p>
          )}
          {offlineSaved && (
            <button
              onClick={() =>
                downloadCsv(
                  `survey-${study || 'responses'}.csv`,
                  responsesToCsv(
                    lastResponse ? [lastResponse] : [],
                    (r) => scoreResponse(r)
                  )
                )
              }
              className="text-white/70 underline text-sm hover:text-white"
            >
              Download my response (CSV)
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-900 via-purple-900 to-slate-900 py-10 px-5">
      <form onSubmit={handleSubmit} className="max-w-2xl mx-auto" noValidate>
        <header className="mb-8">
          <Link to="/" className="text-white/40 text-xs uppercase tracking-widest hover:text-white/70">
            ← Sunshine
          </Link>
          <h1 className="font-display text-white text-2xl mt-2 mb-4">
            Anticipated Trust Survey
          </h1>
          <p className="text-white/80 leading-relaxed">{stem}</p>
          {(study || condition) && (
            <p className="text-white/30 text-xs mt-3">
              {study && <>Study: {study}</>} {condition && <>· Condition: {condition}</>}
            </p>
          )}
        </header>

        {/* Section A — exposure */}
        <section className="mb-6" data-invalid={errors.exposure ? 'true' : 'false'}>
          <h2 className="text-white/50 text-xs uppercase tracking-widest font-medium mb-3">
            How much of the system have you seen?
          </h2>
          <div
            className={`rounded-xl border p-2 ${
              errors.exposure ? 'border-red-400/70 bg-red-500/5' : 'border-white/15 bg-white/5'
            }`}
            role="radiogroup"
            aria-label="How much of the system have you seen?"
          >
            {EXPOSURE_OPTIONS.map((opt) => (
              <label
                key={opt.value}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-white/5"
              >
                <input
                  type="radio"
                  name="exposure"
                  value={opt.value}
                  checked={exposure === opt.value}
                  onChange={() => {
                    setExposure(opt.value);
                    setErrors((e) => ({ ...e, exposure: false }));
                  }}
                  className="accent-white w-4 h-4"
                />
                <span className="text-white/90 text-sm">{opt.label}</span>
              </label>
            ))}
          </div>
          {errors.exposure && (
            <p className="text-red-300 text-xs mt-2">Please choose one.</p>
          )}
        </section>

        {/* Section B — core items */}
        <section className="space-y-3 mb-6">
          <h2 className="text-white/50 text-xs uppercase tracking-widest font-medium">
            Your expectations
          </h2>
          {CORE_ITEMS.map((item) => (
            <div key={item.id} data-invalid={errors[item.id] ? 'true' : 'false'}>
              <LikertRow
                id={item.id}
                text={item.text}
                value={answers[item.id]}
                onChange={setAnswer}
                invalid={errors[item.id]}
              />
            </div>
          ))}
        </section>

        {/* Section C — diagnostics */}
        <section className="space-y-3 mb-8">
          <h2 className="text-white/50 text-xs uppercase tracking-widest font-medium">
            A few final questions
          </h2>
          {likertDiagnostics.map((d) => (
            <div key={d.id} data-invalid={errors[d.id] ? 'true' : 'false'}>
              <LikertRow
                id={d.id}
                text={d.text}
                value={answers[d.id]}
                onChange={setAnswer}
                invalid={errors[d.id]}
              />
            </div>
          ))}
          <div className="rounded-xl border border-white/15 bg-white/5 p-4">
            <label htmlFor="q12" className="block text-white/90 text-base mb-3">
              {DIAGNOSTIC_ITEMS.find((d) => d.id === 'q12').text}
              <span className="text-white/40 text-sm"> (optional)</span>
            </label>
            <textarea
              id="q12"
              value={q12}
              onChange={(e) => setQ12(e.target.value)}
              rows={3}
              className="w-full rounded-lg bg-slate-900/50 border border-white/20 text-white p-3 text-sm focus:border-white/60 focus:outline-none"
              placeholder="Optional — a sentence or two is plenty."
            />
          </div>
        </section>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-xl bg-white text-slate-900 font-semibold py-3.5 hover:bg-white/90 transition-colors disabled:opacity-60"
        >
          {submitting ? 'Submitting…' : 'Submit'}
        </button>
        <p className="text-white/30 text-xs mt-4 text-center">
          Anticipated trust (adapted TOAST). Your answers are anonymous.
        </p>
      </form>
    </div>
  );
}
