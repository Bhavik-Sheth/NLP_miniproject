// Deterministic Hinglish reply templates. Two renderings per reply: `text` (display) and `speech`
// (TTS-friendly: units spelled, IDs spaced, dates spoken).
import type { CheckResult, Contradiction, SlotName, Slots } from "./contradictions";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export function spokenDate(iso?: string | null): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}` : iso;
}
const ATTR_HI: Record<string, string> = {
  rebar_spacing: "rebar spacing", stirrup_spacing: "stirrup spacing", cover: "cover", thickness: "thickness",
  rebar_dia: "bar dia", size: "size", grade: "grade", bar_count: "bar count",
};
export const attrLabel = (a?: string) => (a ? ATTR_HI[a] ?? a.replace(/_/g, " ") : "");
const ACT_HI: Record<string, string> = { hot_work: "hot work", pour: "dhalai", height: "height work", excavation: "khudai" };
export const levelLabel = (l?: string | null) => (l ? l.replace(/^L(\d+)$/, "Level $1") : "");

export function locLabel(c: CheckResult, s: Slots): string {
  const loc = c.location;
  if (loc) {
    const head = loc.grid && loc.grid !== "Slab" ? loc.grid : loc.zone ?? (loc.grid === "Slab" ? "Slab" : loc.location_id);
    return loc.grid === "Slab" ? `${levelLabel(loc.level)} slab` : `${head}, ${levelLabel(loc.level)}`;
  }
  return [s.grid?.value ?? s.zone?.value, levelLabel(s.level?.value)].filter(Boolean).join(", ");
}

/** Make a display string speakable. */
export function toSpeech(t: string): string {
  return t
    .replace(/(\d+(?:\.\d+)?)\s?mm\b/g, "$1 millimeter")
    .replace(/±\s?(\d+)/g, "plus minus $1")
    .replace(/\bRFI-0*(\d+)/g, (_m, n) => `R F I ${n}`)
    .replace(/\bNCR\b/g, "N C R")
    .replace(/\bOBS-0*(\d+)/g, (_m, n) => `observation number ${n}`)
    .replace(/\bHWP-0*(\d+)/g, (_m, n) => `H W P ${n}`)
    .replace(/\b([A-Z])-(\d{3})\b/g, "$1 $2")
    .replace(/\b([A-H])-(\d{1,2})\b/g, "$1 $2")
    .replace(/\bR(\d+)\b/g, "revision $1")
    .replace(/\bL(\d+)\b/g, "level $1")
    .replace(/QC-[A-Z]+-[A-Z]+-\d+/g, "checklist")
    .replace(/\bCL-[A-Z0-9-]+/g, "")
    .replace(/—/g, ", ")
    .replace(/\s+/g, " ")
    .trim();
}

export interface Reply { text: string; speech: string }
const R = (text: string): Reply => ({ text, speech: toSpeech(text) });

export function challengeReply(c: CheckResult, s: Slots, prefix = ""): Reply {
  const parts: string[] = [];
  if (prefix) parts.push(prefix);
  const loc = locLabel(c, s);
  const attr = attrLabel(c.attribute ?? s.attribute?.value);
  for (const k of c.contradictions) parts.push(describe(k, c, s, loc, attr));
  const hasDim = c.contradictions.some((k) => k.kind === "dimension_mismatch");
  parts.push(hasDim
    ? "Kya aap observation log karna chahte hain, RFI raise karna chahte hain, ya NCR?"
    : "Kya aap observation log karna chahte hain, ya RFI raise karna chahte hain?");
  return R(parts.join(" "));
}

function describe(k: Contradiction, c: CheckResult, s: Slots, loc: string, attr: string): string {
  const e = k.evidence;
  switch (k.kind) {
    case "revision_mismatch": {
      let t = `Drawing ${e.drawing_number} ki latest revision ${e.revision} hai, jo ${spokenDate(e.issued_on)} ko issue hui thi.`;
      if (e.expected != null) t += ` Usme ${loc} ki ${attr} ${e.expected} ${e.unit ?? "mm"} hai.`;
      if (e.via_rfi) t += ` ${e.via_rfi} ne yeh confirm kiya tha.`;
      if (e.claimed_revision) t += ` ${e.claimed_revision} superseded hai${e.claimed_revision_value != null ? `, usme ${e.claimed_revision_value} tha` : ""}.`;
      if (c.value != null && e.expected != null && !c.contradictions.some((x) => x.kind === "dimension_mismatch")) t += ` Aapka ${c.value} ${c.unit ?? "mm"} latest drawing se match karta hai.`;
      return t;
    }
    case "dimension_mismatch": {
      if (e.claimed != null && c.value != null && e.claimed === c.value)
        return `Dhyan dijiye: ${loc} pe aapne ${attr} ${c.value} ${e.unit ?? "mm"} bola, lekin ${e.drawing_number} ${e.revision} mein ${e.expected} ${e.unit ?? "mm"} hai, tolerance ±${e.tolerance ?? 0}. Yeh ${Math.abs(Number(e.claimed) - Number(e.expected))} ${e.unit ?? "mm"} ka farak hai.${e.code_ref ? ` Reference ${e.code_ref}.` : ""}`;
      return `Aapne drawing mein ${e.claimed} bataya, lekin ${e.drawing_number} ${e.revision} mein ${e.expected} ${e.unit ?? "mm"} hai.`;
    }
    case "unknown_drawing":
      if (e.drawing_id) return `Drawing ${e.drawing_number} is location ke liye applicable nahi hai; ${e.drawing_id.replace("@", " ")} lagu hai, issue ${spokenDate(e.issued_on)}.`;
      return `Drawing ${e.drawing_number} register mein nahi mili.`;
    default:
      return k.detail;
  }
}

export function unknownDrawingReply(k: Contradiction): Reply {
  const cands = (k.evidence.candidates ?? []).slice(0, 4).join(", ");
  return R(`Drawing ${k.evidence.drawing_number} register mein nahi mili. Kripya drawing number dobara bataiye${cands ? ` — register mein ${cands} hain` : ""}. Tab tak kuch log nahi hoga.`);
}

export function missingReply(c: CheckResult, s: Slots): Reply {
  const m = c.missing[0];
  const f = m.evidence.field;
  if (f === "level") {
    const levels = (m.evidence.candidates ?? []).map((id) => levelLabel(id.split(":")[2])).join(" ya ");
    return R(`${s.grid?.value ?? s.zone?.value} kaunse level pe hai — ${levels}?`);
  }
  if (f === "element") return R(`${locLabel(c, s)} pe kaunsa element — ${(m.evidence.candidates ?? []).join(" ya ")}?`);
  if (f === "location_unknown") return R(`${m.evidence.claimed} project register mein nahi mila. Grid line dobara bataiye.`);
  if (f === "location") return R("Location bataiye — kaunsi grid line aur level? Jaise C-5, Level 3.");
  if (f === "attribute") return R(`${locLabel(c, s) || "Wahan"} pe kya check kiya — spacing, cover ya thickness?`);
  if (f === "value") return R(`${attrLabel(c.attribute ?? s.attribute?.value) || "Value"} kitni hai? mm mein bataiye.`);
  return R("Thoda aur detail chahiye. Location, attribute aur value bataiye.");
}

const SLOT_SAY: Partial<Record<SlotName, (s: Slots) => string>> = {
  grid: (s) => `grid ${s.grid?.value}`,
  level: (s) => levelLabel(s.level?.value),
  zone: (s) => `${s.zone?.value}`,
  attribute: (s) => attrLabel(s.attribute?.value),
  value: (s) => `${s.value?.value} ${s.unit?.value ?? "mm"}`,
  drawingNumber: (s) => `drawing ${s.drawingNumber?.value}`,
  element: (s) => `${s.element?.value}`,
  activity: (s) => ACT_HI[s.activity?.value ?? ""] ?? String(s.activity?.value),
};
export function confirmSlotsReply(names: SlotName[], s: Slots, resolvedDrawing?: string): Reply {
  const said = names.map((n) => (n === "drawingNumber" && resolvedDrawing ? `drawing ${resolvedDrawing}` : SLOT_SAY[n]?.(s) ?? n)).join(", ");
  return R(`Awaaz saaf nahi thi. Maine suna: ${said}. Kya yeh sahi hai? Haan ya nahi boliye.`);
}

/** "Fire watcher assigned, distinct from welder (..)" → "Fire watcher assigned"; max 2 items + count. */
function shortList(items?: string[]): string {
  if (!items?.length) return "";
  const short = items.map((i) => i.split(/[,(—;]| - /)[0].trim());
  const head = short.slice(0, 2).join("; ");
  return items.length > 2 ? `${head}, aur ${items.length - 2} aur items` : head;
}

export function blockerReply(c: CheckResult, s: Slots, attempted?: string): Reply {
  const parts: string[] = [];
  if (attempted) parts.push(`${attempted} abhi allowed nahi hai.`);
  parts.push("Ruko.");
  const loc = locLabel(c, s);
  for (const b of c.blockers) {
    if (b.kind === "permit_blocker") {
      if (b.evidence.permit_id) parts.push(`${loc} pe ${ACT_HI[s.activity?.value ?? ""] ?? "kaam"} permit ${b.evidence.permit_id} active hai, lekin mandatory check pending hai: ${shortList(b.evidence.checks)}. Jab tak yeh confirm na ho, ${ACT_HI[s.activity?.value ?? ""] ?? "kaam"} shuru nahi ho sakta.`);
      else parts.push(`${loc} pe ${ACT_HI[s.activity?.value ?? ""] ?? "is kaam"} ke liye koi active permit nahi hai.`);
    } else if (b.kind === "hold_point_blocker") {
      parts.push(`${loc} ka pre-pour checklist ${b.evidence.checklist} ka hold point release nahi hua: ${shortList(b.evidence.items)}. Dhalai shuru nahi ho sakti.`);
    }
  }
  parts.push("Kaam rokna hai, NCR raise karna hai, ya cancel?");
  return R(parts.join(" "));
}

export function readbackReply(c: CheckResult, s: Slots, prefix = ""): Reply {
  const loc = locLabel(c, s);
  const d = c.drawing ? `${c.drawing.drawing_number} ${c.drawing.revision}` : null;
  let t = prefix ? prefix + " " : "";
  if (c.mode === "defect") t += `${loc} pe ${s.element?.value ?? ""} ${s.defect?.value}${d ? `, drawing ${d} se link hoga` : ""}.`;
  else if (c.mode === "activity") t += `${loc} pe ${ACT_HI[s.activity?.value ?? ""]} ke liye koi blocker nahi mila.`;
  else t += `${loc}, ${c.element ?? s.element?.value ?? ""} ${attrLabel(c.attribute)} ${c.value} ${c.unit ?? "mm"}${c.fact && d ? ` — ${d} ke hisaab se sahi hai` : d ? ` — drawing ${d}` : ""}.`;
  t = t.replace(/\s+/g, " ").replace(" ,", ",");
  return R(`${t} Log kar doon?`);
}

export function doneReply(decision: string, obsId?: string, rfiId?: string, drawingLabel?: string): Reply {
  switch (decision) {
    case "log_observation": return R(`Observation ${obsId} log ho gaya${drawingLabel ? `, drawing ${drawingLabel} ke saath link kiya` : ""}.`);
    case "raise_rfi": return R(`${rfiId} raise ho gaya, status Open. Observation ${obsId} usse link kar diya.`);
    case "raise_ncr": return R(`NCR ke liye observation ${obsId} log ho gaya. QA team ko notify kijiye.`);
    case "stop_work": return R(`Kaam rokne ka order ${obsId} log ho gaya. Safety officer ko turant inform kijiye.`);
    case "cancel": return R("Theek hai, cancel kar diya. Kuch log nahi hua.");
    default: return R("Theek hai.");
  }
}

export const REFUSE = {
  confirmFirst: "Pehle confirm kijiye, phir log karunga.",
  clarifyFirst: "Log karne se pehle ek baat:",
  ambiguousYes: "Log karna hai ya RFI raise karna hai? Saaf boliye.",
  rfiDeclined: "Theek hai, RFI nahi. Toh observation log kar doon?",
  nothing: "Main sun raha hoon. Location, attribute aur value boliye — jaise, C-5 pe spacing 180 mm.",
};
export { R as reply };
