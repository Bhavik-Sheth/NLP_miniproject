"use client";

// Field-schema loading, normalisation and validation for the onboarding flows.
// Source of truth: GET /api/onboarding/schema (W2, data/onboarding_schema.json).
// If the backend hasn't loaded that router we use schema.fallback.json — a snapshot of
// data/onboarding_schema.json copied into this folder (Turbopack won't import outside app/).
import { useEffect, useState } from "react";
import {
  ApiError,
  tenancyApi,
  type FieldOption,
  type OnboardingSchema,
  type ProfileValues,
  type SchemaField,
  type SchemaStep,
} from "@/lib/api-tenancy";
import fallbackJson from "./schema.fallback.json";

export type SchemaSource = "api" | "fallback";

// ---------- normalisation ----------

export function optionValue(o: FieldOption): string {
  return typeof o === "string" ? o : String(o.value);
}
export function optionLabel(o: FieldOption): string {
  return typeof o === "string" ? o : o.label ?? String(o.value);
}

function isSchema(x: unknown): x is OnboardingSchema {
  const s = x as OnboardingSchema;
  return !!s && Array.isArray(s.org?.steps) && Array.isArray(s.project?.steps);
}

/** Accepts the plain contract shape, or {schema:{…}}. Drops steps with no fields. */
export function normalizeSchema(raw: unknown): OnboardingSchema | null {
  const s = (raw as { schema?: unknown })?.schema ?? raw;
  if (!isSchema(s)) return null;
  const clean = (steps: SchemaStep[]) =>
    steps
      .filter((st) => Array.isArray(st.fields) && st.fields.length)
      .map((st, i) => ({ ...st, id: st.id || `step-${i}`, title: st.title || `Step ${i + 1}` }));
  return { ...s, org: { steps: clean(s.org.steps) }, project: { steps: clean(s.project.steps) } };
}

export const FALLBACK_SCHEMA: OnboardingSchema = normalizeSchema(fallbackJson)!;

export function useOnboardingSchema() {
  const [state, setState] = useState<{
    schema: OnboardingSchema | null;
    source: SchemaSource | null;
    notice: string | null;
  }>({ schema: null, source: null, notice: null });

  useEffect(() => {
    let alive = true;
    tenancyApi
      .schema()
      .then((raw) => {
        if (!alive) return;
        const s = normalizeSchema(raw);
        setState(
          s
            ? { schema: s, source: "api", notice: null }
            : { schema: FALLBACK_SCHEMA, source: "fallback", notice: "The backend schema had an unexpected shape; using the bundled copy." },
        );
      })
      .catch((e: ApiError) => {
        if (!alive) return;
        const why =
          e.status === 404
            ? "The onboarding API isn't loaded on the backend yet — restart it once the tenancy router is in place."
            : e.status === 0
              ? "The Vesper backend isn't reachable."
              : `Schema request failed (${e.status}).`;
        setState({ schema: FALLBACK_SCHEMA, source: "fallback", notice: `${why} Showing the bundled form; saving needs the backend.` });
      });
    return () => {
      alive = false;
    };
  }, []);

  return state;
}

// ---------- validation ----------

const BUILTIN: Record<string, { re: RegExp; msg: string }> = {
  email: { re: /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/, msg: "Enter a valid email address." },
  phone: { re: /^\+?[0-9 ()-]{10,16}$/, msg: "10-digit mobile, optionally with +91." },
  gstin: { re: /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/, msg: "15-character GSTIN, e.g. 05AABCU9603R1ZM." },
  pan: { re: /^[A-Z]{5}[0-9]{4}[A-Z]$/, msg: "10-character PAN, e.g. AABCU9603R." },
  pincode: { re: /^[1-9][0-9]{5}$/, msg: "6-digit PIN code." },
};

export function isEmpty(v: unknown): boolean {
  if (v == null) return true;
  if (typeof v === "string") return v.trim() === "";
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object") {
    const g = v as { lat?: unknown; lng?: unknown };
    if ("lat" in g || "lng" in g) return (g.lat == null || g.lat === "") && (g.lng == null || g.lng === "");
  }
  return false;
}

/** values = the whole step/profile, for cross-field rules (afterField). */
export function validateField(field: SchemaField, value: unknown, values: ProfileValues = {}): string | null {
  const v = field.validation ?? {};
  const min = v.min ?? field.min;
  const max = v.max ?? field.max;
  const pattern = v.pattern ?? field.pattern;

  if (field.type === "toggle") return null;
  if (field.type === "repeater") {
    const rows = Array.isArray(value) ? (value as ProfileValues[]) : [];
    if (field.required && rows.length === 0) return `Add at least one ${(field.label || "item").toLowerCase()}.`;
    if (v.minItems && rows.length < v.minItems) return `Add at least ${v.minItems}.`;
    if (v.maxItems && rows.length > v.maxItems) return `At most ${v.maxItems} allowed.`;
    for (let i = 0; i < rows.length; i++)
      for (const sub of field.fields ?? []) {
        const err = validateField(sub, rows[i]?.[sub.key], rows[i] ?? {});
        if (err) return `Row ${i + 1} · ${sub.label}: ${err}`;
      }
    return null;
  }
  if (isEmpty(value)) return field.required ? "Required." : null;

  if (field.type === "number" || field.type === "currency") {
    const n = Number(value);
    if (!Number.isFinite(n)) return "Enter a number.";
    if (min != null && n < min) return `Must be ${min} or more.`;
    if (max != null && n > max) return `Must be ${max} or less.`;
    return null;
  }

  if (field.type === "geo") {
    const g = value as { lat?: unknown; lng?: unknown };
    const lat = Number(g.lat);
    const lng = Number(g.lng);
    if (g.lat === "" || g.lng === "" || g.lat == null || g.lng == null) return "Enter both latitude and longitude.";
    if (!(lat >= -90 && lat <= 90) || !(lng >= -180 && lng <= 180)) return "Latitude −90…90, longitude −180…180.";
    return null;
  }

  if (field.type === "date") {
    const s = String(value);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || Number.isNaN(Date.parse(s))) return "Use a valid date.";
    if (v.afterField) {
      const other = values[v.afterField];
      if (typeof other === "string" && other && s < other) return "Must be on or after the start date.";
    }
    return null;
  }

  if (Array.isArray(value)) {
    if (v.minItems && value.length < v.minItems) return `Choose at least ${v.minItems}.`;
    if (v.maxItems && value.length > v.maxItems) return `Choose at most ${v.maxItems}.`;
    return null;
  }

  if (typeof value === "string") {
    const s = value.trim();
    if (v.minLength && s.length < v.minLength) return `At least ${v.minLength} characters.`;
    if (v.maxLength && s.length > v.maxLength) return `At most ${v.maxLength} characters.`;
    if (pattern) {
      try {
        if (!new RegExp(pattern).test(s)) return v.message ?? BUILTIN[field.type]?.msg ?? "Not in the expected format.";
      } catch {
        /* invalid regex in schema — skip */
      }
    } else if (BUILTIN[field.type] && !BUILTIN[field.type].re.test(s)) {
      return BUILTIN[field.type].msg;
    }
  }
  return null;
}

export function validateStep(step: SchemaStep, values: ProfileValues): Record<string, string> {
  const errs: Record<string, string> = {};
  for (const f of step.fields) {
    const e = validateField(f, values[f.key], values);
    if (e) errs[f.key] = e;
  }
  return errs;
}

export function defaultsFor(steps: SchemaStep[]): ProfileValues {
  const out: ProfileValues = {};
  for (const st of steps)
    for (const f of st.fields) {
      if (f.default !== undefined) out[f.key] = f.default;
      else if (f.type === "toggle") out[f.key] = false;
    }
  return out;
}

/** Coerce answers to the stored shape (notes in the schema) and pull out File objects to upload later. */
export function splitFiles(steps: SchemaStep[], values: ProfileValues) {
  const profile: ProfileValues = {};
  const files: { field: SchemaField; files: File[] }[] = [];
  const byKey = new Map<string, SchemaField>();
  for (const st of steps) for (const f of st.fields) byKey.set(f.key, f);

  for (const [k, raw] of Object.entries(values)) {
    const f = byKey.get(k);
    if (!f) continue; // stale draft keys
    if (f.type === "file") {
      const list = (Array.isArray(raw) ? raw : []).filter((x): x is File => typeof File !== "undefined" && x instanceof File);
      if (list.length) files.push({ field: f, files: list });
      continue; // file refs {name, docId} are PATCHed after upload
    }
    if (isEmpty(raw) && f.type !== "toggle") continue;
    if (f.type === "number" || f.type === "currency") profile[k] = Number(raw);
    else if (f.type === "geo") {
      const g = raw as { lat: unknown; lng: unknown };
      profile[k] = { lat: Number(g.lat), lng: Number(g.lng) };
    } else if (f.type === "gstin" || f.type === "pan") profile[k] = String(raw).trim().toUpperCase();
    else if (typeof raw === "string") profile[k] = raw.trim();
    else profile[k] = raw;
  }
  return { profile, files };
}

export function voiceReason(f: SchemaField): string {
  if (typeof f.usedByVoice === "string" && f.usedByVoice.trim()) return f.usedByVoice;
  if (f.memoryHint) return `Becomes project memory for Vesper's voice checks. ${f.memoryHint}`;
  return "Vesper checks spoken site observations against this answer before anything is logged.";
}

export function isVoiceField(f: SchemaField) {
  return f.usedByVoice === true || (typeof f.usedByVoice === "string" && f.usedByVoice.length > 0);
}

/** Ingest category for a file field, derived from key when the schema doesn't say. */
export function fileCategory(f: SchemaField): string {
  if (f.category) return f.category;
  const m = f.memoryHint?.match(/category\s+([a-z_]+)/i);
  if (m) return m[1];
  const k = f.key.toLowerCase();
  if (k.includes("drawing")) return "drawing_register";
  if (k.includes("boq")) return "boq";
  if (k.includes("itp")) return "itp";
  if (k.includes("spec")) return "spec";
  if (k.includes("contract")) return "contract";
  return "other";
}
