"use client";

// Renders one schema field (and repeaters recursively). Controlled: value + onChange.
import { useId, useMemo, useRef, useState } from "react";
import type { ProfileValues, SchemaField } from "@/lib/api-tenancy";
import { tenancyApi } from "@/lib/api-tenancy";
import { isVoiceField, optionLabel, optionValue, voiceReason } from "./schema";
import { useRecorder } from "./useRecorder";
import { OIcon, Spin, VoiceBadge } from "./primitives";

type Props = {
  field: SchemaField;
  value: unknown;
  onChange: (v: unknown) => void;
  error?: string | null;
  compact?: boolean;
  autoFocus?: boolean;
};

export function Field({ field, value, onChange, error, compact, autoFocus }: Props) {
  const id = useId();
  const helpId = `${id}-help`;
  const errId = `${id}-err`;
  const describedBy = [field.help ? helpId : null, error ? errId : null].filter(Boolean).join(" ") || undefined;
  const common = {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy,
    "aria-required": field.required || undefined,
    autoFocus,
  } as const;

  const isToggle = field.type === "toggle";

  return (
    <div className={`flex flex-col ${compact ? "gap-1.5" : "gap-2"}`} data-field={field.key}>
      {!isToggle && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <label htmlFor={field.type === "multiselect" || field.type === "repeater" || field.type === "geo" ? undefined : id} className="vo-label">
            {field.label}
            {field.required ? <span aria-hidden style={{ color: "var(--vo-danger)" }}>*</span> : <span className="vo-faint text-[11.5px] font-normal">optional</span>}
          </label>
          {isVoiceField(field) && !compact ? <VoiceBadge reason={voiceReason(field)} /> : null}
        </div>
      )}

      <Control field={field} value={value} onChange={onChange} common={common} />

      {field.help && !isToggle ? (
        <p id={helpId} className="vo-faint text-[12.5px] leading-relaxed">
          {field.help}
        </p>
      ) : null}
      {error ? (
        <p id={errId} className="vo-fade text-[12.5px]" style={{ color: "var(--vo-danger)" }}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

type CommonAttrs = {
  id: string;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
  "aria-required"?: boolean;
  autoFocus?: boolean;
};

function Control({ field, value, onChange, common }: { field: SchemaField; value: unknown; onChange: (v: unknown) => void; common: CommonAttrs }) {
  const str = typeof value === "string" || typeof value === "number" ? String(value) : "";
  const v = field.validation ?? {};

  switch (field.type) {
    case "textarea":
      return <DictationTextarea field={field} value={str} onChange={onChange} common={common} />;

    case "number":
      return <input {...common} className="vo-input" type="number" inputMode="decimal" min={v.min} max={v.max} step="any" placeholder={field.placeholder} value={str} onChange={(e) => onChange(e.target.value)} />;

    case "currency":
      return (
        <div className="vo-prefix">
          <span>₹</span>
          <input {...common} className="vo-input" type="text" inputMode="numeric" placeholder={field.placeholder ?? "0"} value={str === "" ? "" : formatINR(str)} onChange={(e) => onChange(e.target.value.replace(/[^\d.]/g, ""))} />
        </div>
      );

    case "date":
      return <input {...common} className="vo-input" type="date" value={str} onChange={(e) => onChange(e.target.value)} />;

    case "email":
      return <input {...common} className="vo-input" type="email" autoComplete="email" placeholder={field.placeholder ?? "name@company.com"} value={str} onChange={(e) => onChange(e.target.value)} />;

    case "phone":
      return <input {...common} className="vo-input" type="tel" autoComplete="tel" inputMode="tel" placeholder={field.placeholder ?? "+91 98xxxxxxxx"} value={str} onChange={(e) => onChange(e.target.value)} />;

    case "gstin":
    case "pan":
      return (
        <input
          {...common}
          className="vo-input font-mono tracking-wider"
          type="text"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={field.type === "gstin" ? 15 : 10}
          placeholder={field.placeholder ?? (field.type === "gstin" ? "05AABCU9603R1ZM" : "AABCU9603R")}
          value={str}
          onChange={(e) => onChange(e.target.value.toUpperCase().replace(/\s/g, ""))}
        />
      );

    case "pincode":
      return <input {...common} className="vo-input font-mono tracking-wider" type="text" inputMode="numeric" maxLength={6} placeholder={field.placeholder ?? "262501"} value={str} onChange={(e) => onChange(e.target.value.replace(/\D/g, ""))} />;

    case "select":
      return (
        <select {...common} className="vo-input" value={str} onChange={(e) => onChange(e.target.value)}>
          <option value="">{field.placeholder ?? "Select…"}</option>
          {(field.options ?? []).map((o) => (
            <option key={optionValue(o)} value={optionValue(o)}>
              {optionLabel(o)}
            </option>
          ))}
        </select>
      );

    case "multiselect":
      return <MultiSelect field={field} value={Array.isArray(value) ? (value as string[]) : []} onChange={onChange} common={common} />;

    case "toggle":
      return <Toggle field={field} value={value === true} onChange={onChange} common={common} />;

    case "geo":
      return <Geo value={(value as { lat?: string | number; lng?: string | number }) ?? {}} onChange={onChange} common={common} />;

    case "file":
      return <FilePicker field={field} value={Array.isArray(value) ? (value as File[]) : []} onChange={onChange} common={common} />;

    case "repeater":
      return <Repeater field={field} value={Array.isArray(value) ? (value as ProfileValues[]) : []} onChange={onChange} />;

    default:
      return <input {...common} className="vo-input" type="text" placeholder={field.placeholder} maxLength={v.maxLength} value={str} onChange={(e) => onChange(e.target.value)} />;
  }
}

function formatINR(raw: string) {
  const [int, dec] = raw.split(".");
  const n = int.replace(/^0+(?=\d)/, "");
  const last3 = n.slice(-3);
  const rest = n.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",");
  return (rest ? `${rest},${last3}` : last3) + (dec !== undefined ? `.${dec}` : "");
}

// ---------- textarea with dictation ----------

function DictationTextarea({ field, value, onChange, common }: { field: SchemaField; value: string; onChange: (v: unknown) => void; common: CommonAttrs }) {
  const rec = useRecorder();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const recording = rec.state === "recording";

  const toggle = async () => {
    setErr(null);
    if (!recording) {
      await rec.start();
      return;
    }
    const blob = await rec.stop();
    if (!blob) return;
    setBusy(true);
    try {
      const { text } = await tenancyApi.stt(blob);
      const t = (text ?? "").trim();
      if (t) onChange(value ? `${value.replace(/\s+$/, "")} ${t}` : t);
      else setErr("Didn't catch anything — try again closer to the mic.");
    } catch (e) {
      setErr(`Dictation failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      rec.reset();
    }
  };

  return (
    <div className="relative">
      <textarea {...common} className="vo-input pr-12" placeholder={field.placeholder} value={value} maxLength={field.validation?.maxLength} onChange={(e) => onChange(e.target.value)} />
      <button
        type="button"
        onClick={toggle}
        disabled={busy || rec.state === "requesting"}
        className="vo-mic absolute right-2 top-2 h-8 w-8"
        data-rec={recording}
        style={{ ["--lvl" as string]: rec.level.toFixed(3) }}
        aria-label={recording ? "Stop dictation" : `Dictate ${field.label}`}
        title={recording ? "Stop and transcribe" : "Dictate with your voice"}
      >
        {busy ? <Spin /> : <OIcon name={recording ? "stop" : "mic"} size={15} />}
      </button>
      {recording ? <p className="vo-fade mt-1.5 text-[12px]" style={{ color: "var(--vo-danger)" }}>Listening… click stop when you&apos;re done.</p> : null}
      {busy ? <p className="vo-fade vo-faint mt-1.5 text-[12px]">Transcribing…</p> : null}
      {err || rec.error ? <p className="mt-1.5 text-[12px]" style={{ color: "var(--vo-warn)" }}>{err ?? rec.error}</p> : null}
    </div>
  );
}

// ---------- multiselect ----------

function MultiSelect({ field, value, onChange, common }: { field: SchemaField; value: string[]; onChange: (v: unknown) => void; common: CommonAttrs }) {
  const opts = field.options ?? [];
  const [q, setQ] = useState("");
  const searchable = opts.length > 14;
  const shown = useMemo(() => (q ? opts.filter((o) => optionLabel(o).toLowerCase().includes(q.toLowerCase())) : opts), [opts, q]);
  const toggle = (val: string) => onChange(value.includes(val) ? value.filter((x) => x !== val) : [...value, val]);
  return (
    <div className="flex flex-col gap-2" role="group" aria-labelledby={undefined} aria-describedby={common["aria-describedby"]} aria-invalid={common["aria-invalid"]}>
      {searchable ? <input className="vo-input" type="search" placeholder={`Filter ${opts.length} options…`} value={q} onChange={(e) => setQ(e.target.value)} aria-label={`Filter ${field.label}`} /> : null}
      <div className={`flex flex-wrap gap-1.5 ${searchable ? "vo-scroll max-h-44 overflow-y-auto pr-1" : ""}`}>
        {shown.map((o) => {
          const val = optionValue(o);
          const on = value.includes(val);
          return (
            <button key={val} type="button" className="vo-chip" aria-pressed={on} onClick={() => toggle(val)}>
              {on ? <OIcon name="check" size={12} /> : null}
              {optionLabel(o)}
            </button>
          );
        })}
        {shown.length === 0 ? <span className="vo-faint text-[12.5px]">No matches.</span> : null}
      </div>
      {value.length ? <span className="vo-faint text-[11.5px]">{value.length} selected</span> : null}
    </div>
  );
}

// ---------- toggle ----------

function Toggle({ field, value, onChange, common }: { field: SchemaField; value: boolean; onChange: (v: unknown) => void; common: CommonAttrs }) {
  return (
    <div className="vo-card flex items-start justify-between gap-4 px-3.5 py-3">
      <div className="min-w-0">
        <label htmlFor={common.id} className="vo-label cursor-pointer">
          {field.label}
          {isVoiceField(field) ? <VoiceBadge reason={voiceReason(field)} /> : null}
        </label>
        {field.help ? <p className="vo-faint mt-1 text-[12.5px]">{field.help}</p> : null}
      </div>
      <button id={common.id} type="button" role="switch" aria-checked={value} className="vo-switch mt-0.5" onClick={() => onChange(!value)} />
    </div>
  );
}

// ---------- geo ----------

function Geo({ value, onChange, common }: { value: { lat?: string | number; lng?: string | number }; onChange: (v: unknown) => void; common: CommonAttrs }) {
  const [locating, setLocating] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const locate = () => {
    if (!navigator.geolocation) return setErr("Location isn't available in this browser.");
    setLocating(true);
    setErr(null);
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLocating(false);
        onChange({ lat: p.coords.latitude.toFixed(6), lng: p.coords.longitude.toFixed(6) });
      },
      (e) => {
        setLocating(false);
        setErr(e.code === 1 ? "Location permission denied — enter coordinates instead." : "Couldn't get a location fix.");
      },
      { enableHighAccuracy: true, timeout: 10000 },
    );
  };
  const lat = value.lat ?? "";
  const lng = value.lng ?? "";
  const hasPoint = lat !== "" && lng !== "" && Number.isFinite(Number(lat)) && Number.isFinite(Number(lng));
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto]">
        <input {...common} className="vo-input font-mono" inputMode="decimal" placeholder="Latitude  29.5829" aria-label="Latitude" value={lat} onChange={(e) => onChange({ ...value, lat: e.target.value })} />
        <input className="vo-input font-mono" inputMode="decimal" placeholder="Longitude  80.2182" aria-label="Longitude" aria-invalid={common["aria-invalid"]} value={lng} onChange={(e) => onChange({ ...value, lng: e.target.value })} />
        <button type="button" className="vo-btn vo-btn-ghost h-10" onClick={locate} disabled={locating}>
          {locating ? <Spin /> : <OIcon name="locate" size={15} />} Use my location
        </button>
      </div>
      {hasPoint ? (
        <a className="vo-faint inline-flex w-fit items-center gap-1.5 text-[12px] underline-offset-2 hover:underline" href={`https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=16/${lat}/${lng}`} target="_blank" rel="noreferrer">
          <OIcon name="pin" size={12} /> Check the pin on OpenStreetMap
        </a>
      ) : null}
      {err ? <p className="text-[12px]" style={{ color: "var(--vo-warn)" }}>{err}</p> : null}
    </div>
  );
}

// ---------- file ----------

function FilePicker({ field, value, onChange, common }: { field: SchemaField; value: File[]; onChange: (v: unknown) => void; common: CommonAttrs }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const add = (list: FileList | null) => {
    if (!list?.length) return;
    const next = [...value];
    for (const f of Array.from(list)) if (!next.some((x) => x.name === f.name && x.size === f.size)) next.push(f);
    onChange(next);
  };
  return (
    <div className="flex flex-col gap-2">
      <div
        role="button"
        tabIndex={0}
        aria-describedby={common["aria-describedby"]}
        className="vo-drop flex items-center gap-3 px-4 py-3.5"
        data-over={over}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.current?.click())}
        onDragOver={(e) => (e.preventDefault(), setOver(true))}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => (e.preventDefault(), setOver(false), add(e.dataTransfer.files))}
      >
        <span className="grid h-9 w-9 flex-none place-items-center rounded-full" style={{ background: "var(--vo-surface-2)", color: "var(--vo-text-2)" }}>
          <OIcon name="upload" size={16} />
        </span>
        <div className="min-w-0 text-[13px]">
          <div>
            Drop file or <span style={{ color: "var(--vo-accent)" }}>browse</span>
          </div>
          <div className="vo-faint text-[12px]">{field.accept ? field.accept.split(",").join(" ") : "Any document"} · uploads after the project is created</div>
        </div>
        <input ref={input} id={common.id} type="file" hidden multiple accept={field.accept} onChange={(e) => (add(e.target.files), (e.target.value = ""))} />
      </div>
      {value.length ? (
        <ul className="flex flex-col gap-1.5">
          {value.map((f, i) => (
            <li key={`${f.name}-${i}`} className="vo-card vo-fade flex items-center gap-2.5 px-3 py-2 text-[13px]">
              <OIcon name="file" size={14} className="vo-faint flex-none" />
              <span className="min-w-0 flex-1 truncate">{f.name}</span>
              <span className="vo-faint font-mono text-[11px]">{fmtBytes(f.size)}</span>
              <button type="button" className="vo-btn vo-btn-quiet vo-btn-icon h-7 w-7" aria-label={`Remove ${f.name}`} onClick={() => onChange(value.filter((_, j) => j !== i))}>
                <OIcon name="x" size={13} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// ---------- repeater ----------

function Repeater({ field, value, onChange }: { field: SchemaField; value: ProfileValues[]; onChange: (v: unknown) => void }) {
  const subs = field.fields ?? [];
  const max = field.validation?.maxItems;
  const singular = field.itemLabel ?? singularize(field.label);
  const update = (i: number, key: string, v: unknown) => onChange(value.map((row, j) => (j === i ? { ...row, [key]: v } : row)));
  const add = () => {
    const row: ProfileValues = {};
    for (const s of subs) if (s.default !== undefined) row[s.key] = s.default;
    onChange([...value, row]);
  };
  return (
    <div className="flex flex-col gap-2.5">
      {value.map((row, i) => (
        <div key={i} className="vo-card vo-enter relative p-3.5 sm:p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="vo-eyebrow">
              {singular} {i + 1}
            </span>
            <button type="button" className="vo-btn vo-btn-quiet vo-btn-icon h-7 w-7" aria-label={`Remove ${singular} ${i + 1}`} onClick={() => onChange(value.filter((_, j) => j !== i))}>
              <OIcon name="trash" size={14} />
            </button>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {subs.map((s) => (
              <div key={s.key} className={s.type === "textarea" || s.type === "multiselect" || s.type === "repeater" ? "sm:col-span-2" : ""}>
                <Field compact field={s} value={row[s.key]} onChange={(v) => update(i, s.key, v)} autoFocus={false} />
              </div>
            ))}
          </div>
        </div>
      ))}
      <button type="button" className="vo-btn vo-btn-ghost w-fit" onClick={add} disabled={max != null && value.length >= max}>
        <OIcon name="plus" size={14} /> Add {singular.toLowerCase()}
      </button>
    </div>
  );
}

function singularize(label: string) {
  const l = label.replace(/\s*\(.*\)\s*$/, "");
  if (/ies$/i.test(l)) return l.replace(/ies$/i, "y");
  if (/s$/i.test(l) && !/ss$/i.test(l)) return l.slice(0, -1);
  return l;
}
