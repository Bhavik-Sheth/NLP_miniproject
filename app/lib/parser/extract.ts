// Deterministic Hinglish entity extractor. No network, no LLM. Unit-tested in tests/parser.test.ts.
import { devanagariToLatin, normalizeNumbers } from "./numbers";

export type SlotSource = "parser" | "llm" | "inferred" | "db" | "user_confirmed";
export interface Slot<T> {
  value: T;
  confidence: number; // 0..1 ; < LOW_CONFIDENCE must be voice-confirmed before logging
  source: SlotSource;
  raw?: string;
}
export const LOW_CONFIDENCE = 0.7;

export type Decision = "log_observation" | "raise_rfi" | "raise_ncr" | "stop_work" | "cancel";

export interface Extraction {
  normalized: string;
  grid?: Slot<string>;
  negatedGrids: string[];
  level?: Slot<string>;
  zone?: Slot<string>;
  element?: Slot<string>;
  attribute?: Slot<string>;
  value?: Slot<number>;
  unit?: Slot<string>;
  negatedValues: number[];
  drawingNumber?: Slot<string>; // 'A-102' (or '102' when the letter was not heard)
  revisionClaimed?: Slot<string>; // 'R3'
  drawingValueClaimed?: Slot<number>;
  activity?: Slot<string>; // hot_work | pour | height | excavation
  defect?: Slot<string>;
  decision?: Decision;
  rfiDeclined: boolean;
  affirm: boolean;
  deny: boolean;
  isCorrection: boolean;
}

// ---------------------------------------------------------------- helpers
const LETTER_WORDS: Record<string, string> = {
  a: "A", ay: "A", ae: "A", bee: "B", be: "B", b: "B", bi: "B", c: "C", see: "C", sea: "C", si: "C", cee: "C",
  d: "D", dee: "D", di: "D", e: "E", ee: "E", f: "F", ef: "F", eff: "F", g: "G", gee: "G", jee: "G", h: "H", aitch: "H", ech: "H",
};
const SMALL_NUM_WORDS: Record<string, number> = {
  one: 1, two: 2, to: 2, too: 2, three: 3, four: 4, for: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, ek: 1, do: 2, teen: 3, tin: 3, char: 4, chaar: 4, paanch: 5, panch: 5, chhe: 6, chhah: 6,
  saat: 7, aath: 8, nau: 9, das: 10, gyarah: 11, barah: 12,
};
const ORDINALS: Record<string, number> = {
  first: 1, second: 2, third: 3, fourth: 4, fifth: 5, sixth: 6, seventh: 7, eighth: 8, ninth: 9, tenth: 10, eleventh: 11, twelfth: 12,
  pehli: 1, pahli: 1, pehla: 1, pehle: 1, doosri: 2, dusri: 2, dusra: 2, doosra: 2, doosre: 2, dusre: 2,
  teesri: 3, tisri: 3, teesra: 3, teesre: 3, tisre: 3, chauthi: 4, chautha: 4, chauthe: 4, paanchvi: 5, panchvi: 5,
  paanchve: 5, chhathi: 6, chhathe: 6, saatvi: 7, satvi: 7, aathvi: 8, nauvi: 9, dasvi: 10,
};

interface Mention<T> { value: T; start: number; end: number; confidence: number; raw: string }

function mask(s: string, start: number, end: number, ch = "#"): string {
  return s.slice(0, start) + ch.repeat(end - start) + s.slice(end);
}

/** English negation precedes ("not C-5"), Hindi negation follows ("C-5 nahi"). */
function isNegated(text: string, start: number, end: number): boolean {
  const before = text.slice(Math.max(0, start - 14), start);
  const after = text.slice(end, end + 12);
  if (/\b(not|na ki|instead of|nahi ki)\s*[,:]?\s*$/.test(before)) return true;
  if (/^\s*[,]?\s*(nahi|nahin|nai|galat|wrong)\b/.test(after)) {
    // "C-5 nahi, C-6" → negated. But "... 180 mm nahi hai" is also a negation. Fine.
    return true;
  }
  return false;
}

function findAll(re: RegExp, s: string): RegExpExecArray[] {
  const out: RegExpExecArray[] = [];
  const g = new RegExp(re.source, re.flags.includes("g") ? re.flags : re.flags + "g");
  let m: RegExpExecArray | null;
  while ((m = g.exec(s))) { out.push(m); if (m[0].length === 0) g.lastIndex++; }
  return out;
}

/** Choose the effective mention: the last non-negated one (corrections come later in speech). */
function pick<T>(ms: Mention<T>[], text: string): { chosen?: Mention<T>; negated: Mention<T>[] } {
  const negated = ms.filter((m) => isNegated(text, m.start, m.end));
  const positive = ms.filter((m) => !negated.includes(m));
  return { chosen: positive[positive.length - 1], negated };
}

export function normalizeText(raw: string): string {
  let t = devanagariToLatin(raw).toLowerCase();
  t = t.replace(/[“”"']/g, "").replace(/[—–]/g, ", ").replace(/\.\.\./g, ", ").replace(/\s+/g, " ");
  // join spelled units: "m m" → mm
  t = t.replace(/\bm\s?m\b/g, "mm").replace(/\bmilli?\s?meters?\b|\bmilli?\s?metres?\b|\bmili\b|\bmilli\b/g, "mm");
  t = t.replace(/\bcenti\s?meters?\b|\bcenti\s?metres?\b|\bcenti\b/g, "cm");
  return normalizeNumbers(t);
}

// ---------------------------------------------------------------- main
export function extract(raw: string): Extraction {
  const normalized = normalizeText(raw);
  let work = normalized; // progressively masked
  const ex: Extraction = {
    normalized, negatedGrids: [], negatedValues: [], rfiDeclined: false, affirm: false, deny: false, isCorrection: false,
  };

  ex.isCorrection = /\b(wait|sorry|galti|galat|actually|matlab|i mean|correction|nahi nahi|no no|not|sahi wala|oh no)\b/.test(normalized);

  // --- grade (M25) before grids/drawings
  const grade = /\bm\s?-?(15|20|25|30|35|40|45|50)\b(?!\s*(mm|cm))/.exec(work);
  if (grade) {
    ex.attribute = { value: "grade", confidence: 0.9, source: "parser", raw: grade[0] };
    ex.value = { value: Number(grade[1]), confidence: 0.9, source: "parser", raw: grade[0] };
    ex.unit = { value: "MPa", confidence: 0.9, source: "parser" };
    work = mask(work, grade.index, grade.index + grade[0].length);
  }

  // --- drawing numbers: A-102, "a 102", S-301, "drawing 102"
  const dwgMentions: Mention<string>[] = [];
  for (const m of findAll(/\b([a-z])\s?-?\s?(\d{3})\b/, work)) {
    const explicit = /[a-z]-\d/.test(m[0]) || /^[a-z]\d/.test(m[0]);
    dwgMentions.push({ value: `${m[1].toUpperCase()}-${m[2]}`, start: m.index, end: m.index + m[0].length, confidence: explicit ? 0.95 : 0.85, raw: m[0] });
  }
  for (const m of findAll(/\b(drawing|dwg|drg)\s*(?:no\.?|number|num)?\s*(\d{3})\b/, work)) {
    const s = m.index + m[0].length - m[2].length;
    if (!dwgMentions.some((d) => d.start <= s && d.end >= s)) dwgMentions.push({ value: m[2], start: s, end: m.index + m[0].length, confidence: 0.6, raw: m[0] });
  }
  {
    const { chosen } = pick(dwgMentions, work);
    if (chosen) ex.drawingNumber = { value: chosen.value, confidence: chosen.confidence, source: "parser", raw: chosen.raw };
    for (const d of dwgMentions) work = mask(work, d.start, d.end);
  }

  // --- revisions: Rev 3, R3, R-3, revision 3 ("rev teen" already normalised to digits)
  const revMentions: Mention<string>[] = [];
  for (const m of findAll(/\b(?:rev(?:ision)?|r)\s?\.?\s?-?\s?(\d{1,2})\b/, work)) {
    revMentions.push({ value: `R${Number(m[1])}`, start: m.index, end: m.index + m[0].length, confidence: /^r\d/.test(m[0]) || /rev/.test(m[0]) ? 0.95 : 0.85, raw: m[0] });
  }
  {
    const { chosen } = pick(revMentions, work);
    if (chosen) ex.revisionClaimed = { value: chosen.value, confidence: chosen.confidence, source: "parser", raw: chosen.raw };
    for (const r of revMentions) work = mask(work, r.start, r.end);
  }

  // --- levels
  const lvlMentions: Mention<string>[] = [];
  for (const m of findAll(/\b(?:l|level|lvl|floor|manzil|tal)\s?-?\s?(\d{1,2})\b/, work))
    lvlMentions.push({ value: `L${Number(m[1])}`, start: m.index, end: m.index + m[0].length, confidence: 0.95, raw: m[0] });
  for (const m of findAll(/\b(\d{1,2})\s?(?:st|nd|rd|th)?\s+(?:floor|level|manzil|slab)\b/, work))
    lvlMentions.push({ value: `L${Number(m[1])}`, start: m.index, end: m.index + m[0].length, confidence: 0.9, raw: m[0] });
  const ordRe = new RegExp(`\\b(${Object.keys(ORDINALS).join("|")})\\s+(floor|level|manzil|mala|maala|tal|slab)\\b`);
  for (const m of findAll(ordRe, work))
    lvlMentions.push({ value: `L${ORDINALS[m[1]]}`, start: m.index, end: m.index + m[0].length, confidence: 0.9, raw: m[0] });
  if (/\bground floor\b/.test(work)) {
    const m = /\bground floor\b/.exec(work)!;
    lvlMentions.push({ value: "L0", start: m.index, end: m.index + m[0].length, confidence: 0.9, raw: m[0] });
  }
  {
    lvlMentions.sort((a, b) => a.start - b.start);
    const { chosen } = pick(lvlMentions, work);
    if (chosen) ex.level = { value: chosen.value, confidence: chosen.confidence, source: "parser", raw: chosen.raw };
    for (const l of lvlMentions) work = mask(work, l.start, l.end);
  }

  // --- zone
  const zm = /\bzone\s?-?\s?(a|b|c|d|e|ay|bee|be|see|si|dee)\b/.exec(work);
  if (zm) {
    ex.zone = { value: `Zone ${LETTER_WORDS[zm[1]] ?? zm[1].toUpperCase()}`, confidence: zm[1].length === 1 ? 0.95 : 0.75, source: "parser", raw: zm[0] };
    work = mask(work, zm.index, zm.index + zm[0].length);
  }

  // --- grids: C-5 / C5 / C 5 / C/5 ; spoken "see five" / "si paanch"
  const gridMentions: Mention<string>[] = [];
  for (const m of findAll(/\b([a-h])\s?([-/])?\s?(\d{1,2})\b(?!\s?(mm|cm|m|mpa)\b)(?!\d)/, work)) {
    const form = m[0];
    const conf = /^[a-h][-/]\d/.test(form) || /^[a-h]\d/.test(form) ? 0.95 : 0.85;
    // a bare "a 5" is too risky without grid context
    if (m[1] === "a" && !/[-/]/.test(form) && !/(column|grid|line|kolam)\s*$/.test(work.slice(0, m.index))) continue;
    gridMentions.push({ value: `${m[1].toUpperCase()}-${Number(m[3])}`, start: m.index, end: m.index + form.length, confidence: conf, raw: form });
  }
  const letterAlt = Object.keys(LETTER_WORDS).filter((k) => k.length > 1).join("|");
  const numAlt = Object.keys(SMALL_NUM_WORDS).join("|");
  for (const m of findAll(new RegExp(`\\b(${letterAlt})\\s?-?\\s?(${numAlt}|\\d{1,2})\\b(?!\\s?(mm|cm|m)\\b)`), work)) {
    if (gridMentions.some((g) => g.start <= m.index && g.end > m.index)) continue;
    const n = /^\d+$/.test(m[2]) ? Number(m[2]) : SMALL_NUM_WORDS[m[2]];
    const ctx = /(column|grid|line|kolam|pe|par|at|on)\s*$/.test(work.slice(0, m.index));
    gridMentions.push({ value: `${LETTER_WORDS[m[1]]}-${n}`, start: m.index, end: m.index + m[0].length, confidence: ctx ? 0.6 : 0.5, raw: m[0] });
  }
  {
    gridMentions.sort((a, b) => a.start - b.start);
    const { chosen, negated } = pick(gridMentions, work);
    if (chosen) ex.grid = { value: chosen.value, confidence: chosen.confidence, source: "parser", raw: chosen.raw };
    ex.negatedGrids = negated.map((n) => n.value).filter((v) => v !== chosen?.value);
    if (ex.negatedGrids.length) ex.isCorrection = true;
    for (const g of gridMentions) work = mask(work, g.start, g.end);
  }

  // --- element
  const el: [RegExp, string][] = [
    [/\b(column|columns|colum|coloumn|kolam|kalam|khamba|stambh)\b/, "column"],
    [/\b(beam|beams|bim)\b/, "beam"],
    [/\b(slab|chhat|chat|lenter|linter)\b/, "slab"],
    [/\b(footing|footings|foundation|neev|raft)\b/, "footing"],
    [/\b(wall|deewar|diwar)\b/, "wall"],
  ];
  const elHits = el.map(([re, v]) => ({ m: re.exec(work), v })).filter((x) => x.m);
  if (elHits.length) {
    elHits.sort((a, b) => a.m!.index - b.m!.index);
    // "column line C-5" names a grid, but still implies element column
    ex.element = { value: elHits[0].v, confidence: 0.9, source: "parser", raw: elHits[0].m![0] };
  }

  // --- attribute
  if (!ex.attribute) {
    const at: [RegExp, string][] = [
      [/\b(stirrups?|rings?|ties?|lateral ties)\s*(ka|ki|ke)?\s*(dia|diameter|sariya|size)\b|\btie[_ ]dia\b/, "tie_dia"],
      [/\b(stirrups?|rings?|ties|lateral ties)\b(\s+(ki|ka))?\s*(spacing|doori|duri|gap|c\/c)?/, "stirrup_spacing"],
      [/\b(spacing|doori|duri|c\/c|centre to centre|center to center)\b/, "rebar_spacing"],
      [/\b(clear cover|cover|kavar)\b/, "cover"],
      [/\b(thickness|motai|thick|depth|mota)\b/, "thickness"],
      [/\b(dia|diameter|bar size|sariya ka size|sariye ka size|sutar|sooter)\b/, "rebar_dia"],
      [/\b(bar count|number of bars|kitne bar|bars count)\b/, "bar_count"],
      [/\bgrade\b/, "grade"],
      [/\bsize\b/, "size"],
    ];
    for (const [re, v] of at) {
      const m = re.exec(work);
      if (m) {
        // bare "stirrup" alone (no spacing word) is still stirrup spacing in site talk
        ex.attribute = { value: v, confidence: 0.9, source: "parser", raw: m[0] };
        break;
      }
    }
  }

  // --- activity (permits / hold points)
  const act: [RegExp, string][] = [
    [/\b(hot work|hotwork|welding|weld|welder|gas cutting|cutting|grinding|grinder|brazing|kataai)\b/, "hot_work"],
    [/\b(pour|pouring|casting|cast|concreting|concrete daal\w*|dhalai|dhalaai|dhalayi|dhaal\w*)\b/, "pour"],
    [/\b(scaffold\w*|height work|work at height|uchai)\b/, "height"],
    [/\b(excavation|khudai|digging)\b/, "excavation"],
  ];
  for (const [re, v] of act) {
    const m = re.exec(work);
    if (m) { ex.activity = { value: v, confidence: 0.9, source: "parser", raw: m[0] }; break; }
  }

  // --- defects (qualitative observations)
  const df = /\b(honeycomb\w*|crack\w*|daraar|leak\w*|seepage|spalling|exposed (rebar|bar|sariya)|segregation|bulging)\b/.exec(work);
  if (df) ex.defect = { value: df[1].replace(/\w*$/, (w) => w), confidence: 0.9, source: "parser", raw: df[0] };

  // --- numbers (after masking grids/drawings/revs/levels)
  interface NumM extends Mention<number> { unit?: string; drawingClause: boolean }
  const nums: NumM[] = [];
  // clause boundaries for "drawing says X" detection
  const clauseBreaks = [0];
  for (const m of findAll(/,|;|\bbut\b|\blekin\b|\bjabki\b|\bwhereas\b|\bwhile\b|\baur\b|\bmagar\b|\bpar drawing\b/, normalized)) clauseBreaks.push(m.index);
  clauseBreaks.push(normalized.length);
  const clauseOf = (pos: number) => {
    let s = 0, e = normalized.length;
    for (const b of clauseBreaks) { if (b <= pos) s = b; else { e = b; break; } }
    return normalized.slice(s, e);
  };
  const DRAWING_REF = /(drawing|dwg|drg|\brev\b|revision|\br\s?\d|\b[a-z]-?\s?\d{3}\b|as per|ke hisaab|ke hisab|according)/;
  const DRAWING_SAYS = /(dikh|dikha|likha|diya|given|shows?|says?|mentioned|specified|chahiye|hona|should|required|bataya|mein hai|me hai|mein \d|me \d|main \d)/;
  for (const m of findAll(/(?<![\w#-])(\d+(?:\.\d+)?)\s?(mm|cm|m|mpa|nos)?\b(?!\s?(st|nd|rd|th)\b)/, work)) {
    const clause = clauseOf(m.index);
    const drawingClause = DRAWING_REF.test(clause) && DRAWING_SAYS.test(clause);
    nums.push({
      value: Number(m[1]), unit: m[2], start: m.index, end: m.index + m[0].length, raw: m[0],
      confidence: m[2] ? 0.95 : 0.8, drawingClause,
    });
  }
  const obsNums = nums.filter((n) => !n.drawingClause);
  const dwgNums = nums.filter((n) => n.drawingClause);
  {
    const { chosen, negated } = pick(obsNums, work);
    ex.negatedValues = negated.map((n) => n.value).filter((v) => v !== chosen?.value);
    if (ex.negatedValues.length) ex.isCorrection = true;
    if (chosen && !ex.value) {
      let v = chosen.value;
      let unit = chosen.unit;
      if (unit === "cm") { v = v * 10; unit = "mm"; }
      ex.value = { value: v, confidence: chosen.confidence, source: "parser", raw: chosen.raw };
      if (unit) ex.unit = { value: unit === "mpa" ? "MPa" : unit, confidence: 0.95, source: "parser" };
    }
    const dchosen = pick(dwgNums, work).chosen;
    if (dchosen) {
      let v = dchosen.value;
      if (dchosen.unit === "cm") v = v * 10;
      ex.drawingValueClaimed = { value: v, confidence: dchosen.confidence, source: "parser", raw: dchosen.raw };
      // if the user only said the drawing value (no separate observation), don't invent an observed value
    }
  }

  // --- decisions
  const decisions: { d: Decision; pos: number }[] = [];
  const rfiNeg = /\brfi\b\s*(ki\s*)?(nahi|nahin|mat|na|not needed|nahi chahiye|ki zarurat nahi|ki zaroorat nahi)|\b(no|don'?t|do not|dont)\s+(raise\s+)?(an?\s+)?rfi\b/.exec(normalized);
  if (rfiNeg) ex.rfiDeclined = true;
  const rfiPos = /\b(raise|create|file|open|log|bhejo|daalo|dalo)\s+(an?\s+)?rfi\b|\brfi\b\s*(raise|bhej|daal|dal|bana|create|file|open|kar|chahiye|karo|kar do)/.exec(normalized);
  if (rfiPos && !rfiNeg) decisions.push({ d: "raise_rfi", pos: rfiPos.index });
  const ncr = /\bncr\b|non[- ]?conformance/.exec(normalized);
  if (ncr && !/\bncr\s*(nahi|mat|na)\b|\bno ncr\b/.test(normalized)) decisions.push({ d: "raise_ncr", pos: ncr.index });
  const stop = /\b(kaam|kam|work)\s*(ko\s*)?(rok|rok do|roko|band|stop|halt)|\bstop (the )?work\b|\bstop karo\b|\brok do\b|\broko\b|\bband karo\b|\bhalt\b/.exec(normalized);
  if (stop) decisions.push({ d: "stop_work", pos: stop.index });
  const cancel = /\b(cancel|rehne do|rahne do|chhod do|chod do|chhodo|chodo|discard|abort|mat karo|nevermind|never mind)\b/.exec(normalized);
  if (cancel) decisions.push({ d: "cancel", pos: cancel.index });
  const log = /\blog\s*(kar|karo|kardo|kar do|it|this|karna|karein|kijiye|observation)\b|\b(observation|entry)\s*(log|save|darj|record)\b|\b(record|save|darj|note)\s*(kar|karo|kar do|it)\b|\blog observation\b|^log$|\bhaan,? log\b|\blog\b[.!]?$/.exec(normalized);
  if (log && !/\blog\s*(mat|nahi|na)\b|\bdon'?t log\b|\bdo not log\b/.test(normalized)) decisions.push({ d: "log_observation", pos: log.index });
  if (decisions.length) {
    decisions.sort((a, b) => a.pos - b.pos);
    ex.decision = decisions[decisions.length - 1].d;
    // explicit safety decisions outrank "log" if both appear ("kaam rok do aur NCR")
    const set = new Set(decisions.map((x) => x.d));
    if (set.has("stop_work")) ex.decision = "stop_work";
    if (set.has("cancel") && set.size === 1) ex.decision = "cancel";
  }

  // --- yes / no
  ex.affirm = /^(haan|han|haa|ha|ji|jee|yes|yeah|yep|yup|sahi|correct|theek|thik|ok|okay|bilkul|confirm\w*|right|done|haanji|hanji)\b/.test(normalized)
    || /\b(sahi hai|correct hai|confirm hai|confirmed|haan ji|haan sahi|bilkul sahi|that'?s right|yes correct)\b/.test(normalized);
  ex.deny = /^(nahi|nahin|nai|na|no|nope|galat|wrong)\b/.test(normalized) || /\b(galat hai|wrong hai|sahi nahi|not correct)\b/.test(normalized);
  if (ex.deny) ex.affirm = false;

  return ex;
}

/** Slots that were extracted (for UI chips). */
export function chips(ex: Extraction): { kind: string; label: string; confidence: number }[] {
  const out: { kind: string; label: string; confidence: number }[] = [];
  const add = (kind: string, s?: Slot<string | number>, fmt?: (v: string | number) => string) => {
    if (s) out.push({ kind, label: fmt ? fmt(s.value) : String(s.value), confidence: s.confidence });
  };
  add("grid", ex.grid); add("level", ex.level); add("zone", ex.zone); add("element", ex.element);
  add("attribute", ex.attribute); add("value", ex.value, (v) => `${v}${ex.unit ? " " + ex.unit.value : ""}`);
  add("drawing", ex.drawingNumber); add("revision", ex.revisionClaimed);
  add("drawing says", ex.drawingValueClaimed, (v) => `${v}`); add("activity", ex.activity); add("defect", ex.defect);
  if (ex.decision) out.push({ kind: "decision", label: ex.decision, confidence: 1 });
  return out;
}
