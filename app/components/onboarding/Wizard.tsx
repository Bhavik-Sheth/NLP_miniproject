"use client";

// Generic schema-driven multi-step wizard: left-rail stepper, per-step validation, localStorage
// autosave, keyboard navigation, review step, server field-error mapping.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { FieldError, ProfileValues, SchemaField, SchemaStep } from "@/lib/api-tenancy";
import { Field, fmtBytes } from "./FieldRenderer";
import { defaultsFor, isEmpty, isVoiceField, optionLabel, optionValue, validateStep } from "./schema";
import { Callout, Kbd, OIcon, Spin } from "./primitives";

export type WizardProps = {
  eyebrow: string;
  steps: SchemaStep[];
  storageKey: string;
  submitLabel: string;
  intro?: ReactNode;
  onSubmit: (values: ProfileValues) => Promise<void>;
  /** errors from the server keyed by field key */
  serverErrors?: FieldError[];
  submitError?: string | null;
  notice?: ReactNode;
  /** prefill (under any saved draft) */
  initialValues?: ProfileValues;
  /** "Prefill sample site" — returns a complete realistic answer set */
  samplePrefill?: () => ProfileValues;
};

const REVIEW = "__review";

function loadDraft(key: string, steps: SchemaStep[]): { values: ProfileValues; step: number; savedAt: number | null } {
  const base = defaultsFor(steps);
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const d = JSON.parse(raw) as { values?: ProfileValues; step?: number; savedAt?: number };
      return { values: { ...base, ...(d.values ?? {}) }, step: Math.min(d.step ?? 0, steps.length), savedAt: d.savedAt ?? null };
    }
  } catch {
    /* ignore */
  }
  return { values: base, step: 0, savedAt: null };
}

export function Wizard({ eyebrow, steps, storageKey, submitLabel, intro, onSubmit, serverErrors, submitError, notice, initialValues, samplePrefill }: WizardProps) {
  const [values, setValues] = useState<ProfileValues>(() => defaultsFor(steps));
  const [idx, setIdx] = useState(0);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [visited, setVisited] = useState<Set<number>>(new Set([0]));
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const fileKeys = useMemo(() => new Set(steps.flatMap((s) => s.fields.filter((f) => f.type === "file").map((f) => f.key))), [steps]);
  const total = steps.length + 1; // + review
  const isReview = idx === steps.length;
  const step = steps[idx];

  // hydrate draft (client only)
  useEffect(() => {
    const d = loadDraft(storageKey, steps);
    const pre: ProfileValues = {};
    for (const [k, v] of Object.entries(initialValues ?? {})) if (isEmpty(d.values[k]) && !isEmpty(v)) pre[k] = v;
    setValues({ ...d.values, ...pre });
    setIdx(d.step);
    setSavedAt(d.savedAt);
    setVisited(new Set(Array.from({ length: d.step + 1 }, (_, i) => i)));
    setHydrated(true);
    // initialValues is a one-time prefill
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, steps]);

  // autosave (debounced; File objects aren't serialisable — only their names survive a reload)
  useEffect(() => {
    if (!hydrated) return;
    const t = setTimeout(() => {
      const clean: ProfileValues = {};
      for (const [k, v] of Object.entries(values)) if (!fileKeys.has(k)) clean[k] = v;
      const at = Date.now();
      try {
        localStorage.setItem(storageKey, JSON.stringify({ values: clean, step: idx, savedAt: at }));
        setSavedAt(at);
      } catch {
        /* quota / private mode */
      }
    }, 450);
    return () => clearTimeout(t);
  }, [values, idx, hydrated, storageKey, fileKeys]);

  // server errors → field errors, jump to first offending step
  useEffect(() => {
    if (!serverErrors?.length) return;
    const map: Record<string, string> = {};
    // repeater rows come back as "stakeholders[0].email" — attach to the base field
    for (const e of serverErrors) {
      const base = e.key.split(/[.[]/)[0];
      const path = e.key.slice(base.length).replace(/^\[(\d+)\]\.?/, (_, n) => `Row ${Number(n) + 1} · `);
      if (!map[base]) map[base] = path ? `${path}${e.message}` : e.message;
    }
    setErrors(map);
    const first = steps.findIndex((s) => s.fields.some((f) => map[f.key]));
    if (first >= 0) setIdx(first);
  }, [serverErrors, steps]);

  const stepErrors = useMemo(() => steps.map((s) => Object.keys(validateStep(s, values)).length), [steps, values]);

  const setField = useCallback((key: string, v: unknown) => {
    setValues((prev) => ({ ...prev, [key]: v }));
    setErrors((prev) => {
      if (!prev[key]) return prev;
      const n = { ...prev };
      delete n[key];
      return n;
    });
  }, []);

  const go = useCallback(
    (to: number) => {
      const target = Math.max(0, Math.min(total - 1, to));
      setIdx(target);
      setVisited((v) => new Set(v).add(target));
      setErrors({});
      requestAnimationFrame(() => {
        panelRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
        const first = panelRef.current?.querySelector<HTMLElement>("input:not([type=hidden]),textarea,select,button[role=switch],.vo-chip");
        first?.focus({ preventScroll: true });
      });
    },
    [total],
  );

  const next = useCallback(() => {
    if (isReview) return;
    const errs = validateStep(step, values);
    if (Object.keys(errs).length) {
      setErrors(errs);
      requestAnimationFrame(() => {
        const bad = panelRef.current?.querySelector<HTMLElement>(`[data-field="${Object.keys(errs)[0]}"] input, [data-field="${Object.keys(errs)[0]}"] textarea, [data-field="${Object.keys(errs)[0]}"] select, [data-field="${Object.keys(errs)[0]}"] button`);
        bad?.focus();
      });
      return;
    }
    go(idx + 1);
  }, [isReview, step, values, go, idx]);

  const submit = useCallback(async () => {
    const firstBad = stepErrors.findIndex((n) => n > 0);
    if (firstBad >= 0) {
      setIdx(firstBad);
      setErrors(validateStep(steps[firstBad], values));
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(values);
    } finally {
      setSubmitting(false);
    }
  }, [stepErrors, steps, values, onSubmit]);

  // keyboard: ⌘/Ctrl+Enter continue/submit, Alt+←/→ step
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        if (isReview) void submit();
        else next();
      } else if (e.altKey && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        e.preventDefault();
        if (e.key === "ArrowLeft") go(idx - 1);
        else next();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isReview, submit, next, go, idx]);

  const done = steps.filter((_, i) => visited.has(i) && stepErrors[i] === 0 && i !== idx).length;
  const pct = Math.round(((isReview ? steps.length : idx) / steps.length) * 100);

  const applySample = () => {
    if (!samplePrefill) return;
    const sample = samplePrefill();
    const known = new Set(steps.flatMap((s) => s.fields.map((f) => f.key)));
    const picked: ProfileValues = {};
    for (const [k, v] of Object.entries(sample)) if (known.has(k)) picked[k] = v;
    setValues({ ...defaultsFor(steps), ...picked });
    setErrors({});
    setVisited(new Set(Array.from({ length: steps.length + 1 }, (_, i) => i)));
    setIdx(steps.length); // straight to review so the whole profile can be checked at once
  };

  const resetDraft = () => {
    try {
      localStorage.removeItem(storageKey);
    } catch {
      /* ignore */
    }
    setValues(defaultsFor(steps));
    setIdx(0);
    setVisited(new Set([0]));
    setErrors({});
    setSavedAt(null);
  };

  return (
    <div className="grid grid-cols-1 gap-6 pt-6 lg:grid-cols-[260px_minmax(0,1fr)] lg:gap-10 lg:pt-10">
      {/* rail */}
      <aside className="lg:sticky lg:top-20 lg:self-start">
        <div className="vo-eyebrow">{eyebrow}</div>
        <div className="mt-3 flex items-center justify-between text-[12.5px]">
          <span className="vo-muted">
            {isReview ? "Review" : `Step ${idx + 1} of ${steps.length}`}
          </span>
          <span className="vo-faint font-mono">{pct}%</span>
        </div>
        <div className="vo-progress mt-2">
          <i style={{ width: `${Math.max(pct, 3)}%` }} />
        </div>

        {samplePrefill ? (
          <button type="button" className="vo-btn vo-btn-quiet vo-btn-sm mt-3 w-full justify-center" onClick={applySample} data-testid="prefill-sample">
            <OIcon name="sparkle" size={13} /> Prefill sample site
          </button>
        ) : null}

        {/* mobile: compact step picker */}
        <select className="vo-input mt-3 lg:hidden" value={idx} onChange={(e) => go(Number(e.target.value))} aria-label="Jump to step">
          {steps.map((s, i) => (
            <option key={s.id} value={i}>
              {i + 1}. {s.title}
              {visited.has(i) && i < idx && stepErrors[i] ? " — needs attention" : ""}
            </option>
          ))}
          <option value={steps.length}>Review & submit</option>
        </select>

        <nav className="mt-4 hidden flex-col gap-0.5 lg:flex" aria-label="Steps">
          {steps.map((s, i) => {
            const isDone = visited.has(i) && stepErrors[i] === 0 && i < idx;
            const hasErr = visited.has(i) && i < idx && stepErrors[i] > 0;
            return (
              <button key={s.id} type="button" className="vo-step" aria-current={i === idx ? "step" : undefined} data-done={isDone} data-error={hasErr} onClick={() => go(i)}>
                <span className="vo-step-dot">{isDone ? <OIcon name="check" size={12} strokeWidth={2.4} /> : hasErr ? "!" : i + 1}</span>
                <span className="min-w-0 flex-1 truncate">{s.title}</span>
                {s.fields.some(isVoiceField) ? <OIcon name="wave" size={12} className="vo-faint flex-none" aria-label="has voice fields" /> : null}
              </button>
            );
          })}
          <button type="button" className="vo-step" aria-current={isReview ? "step" : undefined} data-done={false} onClick={() => go(steps.length)}>
            <span className="vo-step-dot">
              <OIcon name="sparkle" size={12} />
            </span>
            <span>Review & submit</span>
          </button>
        </nav>

        <div className="vo-faint mt-5 hidden flex-col gap-2 text-[12px] lg:flex">
          <span className="inline-flex items-center gap-1.5">
            <Kbd>⌘</Kbd>
            <Kbd>↵</Kbd> continue
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Kbd>⌥</Kbd>
            <Kbd>←</Kbd>
            <Kbd>→</Kbd> move between steps
          </span>
          <span className="mt-1 inline-flex items-center gap-1.5" aria-live="polite">
            {savedAt ? (
              <>
                <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: "var(--vo-ok)" }} /> Draft saved on this device
              </>
            ) : (
              "Drafts save automatically"
            )}
          </span>
          {savedAt ? (
            <button type="button" className="w-fit underline-offset-2 hover:underline" onClick={resetDraft}>
              Start over
            </button>
          ) : null}
          <span className="sr-only">{done} steps complete</span>
        </div>
      </aside>

      {/* panel */}
      <section ref={panelRef} className="scroll-mt-20">
        {intro && idx === 0 ? <div className="mb-5">{intro}</div> : null}
        {notice ? <div className="mb-4">{notice}</div> : null}

        <div key={isReview ? REVIEW : step.id} className="vo-glass vo-enter p-5 sm:p-8">
          {isReview ? (
            <Review steps={steps} values={values} stepErrors={stepErrors} onEdit={go} />
          ) : (
            <>
              <h2 className="text-[22px] font-semibold tracking-[-0.02em]">{step.title}</h2>
              {step.description ? <p className="vo-muted mt-1.5 max-w-prose text-[14px] leading-relaxed">{step.description}</p> : null}
              <form
                className="mt-7 grid grid-cols-1 gap-x-5 gap-y-6 sm:grid-cols-2"
                noValidate
                onSubmit={(e) => {
                  e.preventDefault();
                  next();
                }}
              >
                {step.fields.map((f, i) => (
                  <div key={f.key} className={spansFull(f) ? "sm:col-span-2" : ""}>
                    <Field field={f} value={values[f.key]} onChange={(v) => setField(f.key, v)} error={errors[f.key]} autoFocus={hydrated && i === 0 && idx > 0} />
                  </div>
                ))}
                <button type="submit" hidden aria-hidden tabIndex={-1} />
              </form>
            </>
          )}

          {submitError && isReview ? (
            <div className="mt-6">
              <Callout tone="danger" title="Couldn't save">
                {submitError}
              </Callout>
            </div>
          ) : null}

          <div className="mt-8 flex flex-col-reverse gap-3 border-t pt-5 sm:flex-row sm:items-center sm:justify-between" style={{ borderColor: "var(--vo-border)" }}>
            <button type="button" className="vo-btn vo-btn-quiet" onClick={() => go(idx - 1)} disabled={idx === 0 || submitting}>
              <OIcon name="arrowLeft" size={15} /> Back
            </button>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center">
              {!isReview && !step.fields.some((f) => f.required) ? (
                <button type="button" className="vo-btn vo-btn-quiet" onClick={() => go(idx + 1)}>
                  Skip for now
                </button>
              ) : null}
              {isReview ? (
                <button type="button" className="vo-btn vo-btn-primary" onClick={() => void submit()} disabled={submitting}>
                  {submitting ? <Spin /> : <OIcon name="check" size={15} />} {submitting ? "Saving…" : submitLabel}
                </button>
              ) : (
                <button type="button" className="vo-btn vo-btn-primary" onClick={next}>
                  {idx === steps.length - 1 ? "Review" : "Continue"} <OIcon name="arrowRight" size={15} />
                </button>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function spansFull(f: SchemaField) {
  return ["textarea", "multiselect", "repeater", "file", "geo", "toggle"].includes(f.type);
}

// ---------- review ----------

function display(f: SchemaField, v: unknown): ReactNode {
  if (f.type === "toggle") return v ? "Yes" : "No";
  if (isEmpty(v)) return null;
  const label = (x: unknown) => {
    const o = (f.options ?? []).find((o) => optionValue(o) === String(x));
    return o ? optionLabel(o) : String(x);
  };
  switch (f.type) {
    case "select":
      return label(v);
    case "multiselect":
      return (v as unknown[]).map(label).join(", ");
    case "currency":
      return `₹${Number(v).toLocaleString("en-IN")}`;
    case "geo": {
      const g = v as { lat: unknown; lng: unknown };
      return `${g.lat}, ${g.lng}`;
    }
    case "date":
      try {
        return new Date(`${v}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
      } catch {
        return String(v);
      }
    case "file":
      return (v as File[]).map((x) => `${x.name} (${fmtBytes(x.size)})`).join(", ");
    case "repeater": {
      const rows = v as ProfileValues[];
      return (
        <ul className="flex flex-col gap-1">
          {rows.map((r, i) => (
            <li key={i} className="truncate">
              {(f.fields ?? [])
                .map((s) => display(s, r[s.key]))
                .filter((x) => x != null && x !== "")
                .map((x) => (typeof x === "string" ? x : ""))
                .filter(Boolean)
                .join(" · ") || `Row ${i + 1}`}
            </li>
          ))}
        </ul>
      );
    }
    default:
      return String(v);
  }
}

function Review({ steps, values, stepErrors, onEdit }: { steps: SchemaStep[]; values: ProfileValues; stepErrors: number[]; onEdit: (i: number) => void }) {
  const allFields = steps.flatMap((s) => s.fields);
  const answered = allFields.filter((f) => f.type !== "toggle" && !isEmpty(values[f.key])).length;
  const voiceFields = allFields.filter(isVoiceField);
  const voiceAnswered = voiceFields.filter((f) => !isEmpty(values[f.key])).length;
  const blocking = stepErrors.reduce((a, b) => a + b, 0);

  return (
    <div>
      <h2 className="text-[22px] font-semibold tracking-[-0.02em]">Review</h2>
      <p className="vo-muted mt-1.5 text-[14px]">Check the details, then save. You can edit any of this later from project settings.</p>

      <div className="mt-6 grid grid-cols-3 gap-2.5">
        {[
          { k: "Answered", v: `${answered}/${allFields.filter((f) => f.type !== "toggle").length}` },
          { k: "Voice context", v: `${voiceAnswered}/${voiceFields.length}` },
          { k: "Needs attention", v: String(blocking), tone: blocking ? "var(--vo-danger)" : "var(--vo-ok)" },
        ].map((s) => (
          <div key={s.k} className="vo-card px-3 py-2.5">
            <div className="vo-faint text-[11px]">{s.k}</div>
            <div className="mt-0.5 font-mono text-[17px]" style={s.tone ? { color: s.tone } : undefined}>
              {s.v}
            </div>
          </div>
        ))}
      </div>

      {voiceAnswered < voiceFields.length ? (
        <p className="vo-faint mt-3 flex items-start gap-1.5 text-[12.5px]">
          <OIcon name="wave" size={13} className="mt-0.5 flex-none" /> The more voice-context fields you fill, the more precisely Vesper can challenge a wrong grid, grade or revision on site.
        </p>
      ) : null}

      <div className="mt-6 flex flex-col gap-3">
        {steps.map((s, i) => {
          const rows = s.fields.map((f) => ({ f, d: display(f, values[f.key]) })).filter((r) => r.d != null && r.d !== "");
          return (
            <div key={s.id} className="vo-card p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className="text-[14px] font-medium">{s.title}</span>
                  {stepErrors[i] ? (
                    <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ color: "var(--vo-danger)", background: "color-mix(in srgb, var(--vo-danger) 12%, transparent)" }}>
                      {stepErrors[i]} to fix
                    </span>
                  ) : null}
                </div>
                <button type="button" className="vo-btn vo-btn-quiet vo-btn-sm" onClick={() => onEdit(i)}>
                  Edit
                </button>
              </div>
              {rows.length ? (
                <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 text-[13px] sm:grid-cols-[minmax(140px,200px)_1fr]">
                  {rows.map(({ f, d }) => (
                    <div key={f.key} className="contents">
                      <dt className="vo-faint flex items-center gap-1.5">
                        {f.label}
                        {isVoiceField(f) ? <OIcon name="wave" size={11} style={{ color: "var(--vo-accent-2)" }} /> : null}
                      </dt>
                      <dd className="min-w-0 break-words">{d}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="vo-faint mt-2 text-[13px]">Nothing entered.</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
