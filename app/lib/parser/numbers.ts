// Spoken-number normalisation for Hinglish (romanised Hindi + English + Devanagari).
// normalizeNumbers() rewrites number-word phrases into digits *only* where context makes them numeric
// (a unit follows, a multiplier like "sau"/"hundred" is present, or a numeric keyword precedes),
// so "log kar do" never becomes "log kar 2".

const HI_UNITS: Record<string, number> = {
  shunya: 0, sifar: 0, ek: 1, do: 2, teen: 3, tin: 3, char: 4, chaar: 4, chār: 4, paanch: 5, panch: 5, paach: 5,
  chhe: 6, chhah: 6, chah: 6, chhai: 6, che: 6, saat: 7, sat: 7, aath: 8, ath: 8, nau: 9, das: 10, dus: 10,
  gyarah: 11, gyara: 11, barah: 12, bara: 12, terah: 13, tera: 13, chaudah: 14, chauda: 14, pandrah: 15, pandra: 15,
  solah: 16, sola: 16, satrah: 17, satra: 17, atharah: 18, athara: 18, unnis: 19, unees: 19, bees: 20, bis: 20,
  ikkis: 21, bais: 22, baees: 22, teis: 23, chaubis: 24, pachchis: 25, pachis: 25, chhabbis: 26, sattais: 27,
  atthais: 28, untis: 29, untees: 29, tees: 30, tis: 30, ikattis: 31, ektees: 31, battis: 32, taintis: 33, chauntis: 34,
  paintis: 35, pentis: 35, chhattis: 36, saintis: 37, adtis: 38, artis: 38, untalis: 39, chalis: 40, chaalis: 40, chalees: 40,
  iktalis: 41, bayalis: 42, taintalis: 43, chawalis: 44, chauvalis: 44, paintalis: 45, chhiyalis: 46, saintalis: 47,
  adtalis: 48, unchas: 49, pachas: 50, pachaas: 50, ikyavan: 51, bavan: 52, tirpan: 53, chauvan: 54, pachpan: 55,
  chhappan: 56, sattavan: 57, atthavan: 58, unsath: 59, saath: 60, sath: 60, iksath: 61, basath: 62, tirsath: 63,
  chausath: 64, painsath: 65, chhiyasath: 66, sadsath: 67, adsath: 68, unhattar: 69, sattar: 70, ikhattar: 71,
  bahattar: 72, tihattar: 73, chauhattar: 74, pachhattar: 75, chhihattar: 76, sathattar: 77, athattar: 78, unasi: 79,
  assi: 80, asi: 80, ikyasi: 81, bayasi: 82, tirasi: 83, chaurasi: 84, pachasi: 85, chhiyasi: 86, sattasi: 87,
  athasi: 88, nawasi: 89, nabbe: 90, nabbey: 90, ikyanve: 91, banve: 92, tiranve: 93, chauranve: 94, pachanve: 95,
  chhiyanve: 96, sattanve: 97, atthanve: 98, ninyanve: 99,
};

const EN_UNITS: Record<string, number> = {
  zero: 0, oh: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19,
};
const EN_TENS: Record<string, number> = {
  twenty: 20, thirty: 30, forty: 40, fourty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90,
};
const HUNDRED = new Set(["sau", "so", "hundred", "saw"]);
const THOUSAND = new Set(["hazaar", "hazar", "thousand"]);

// Devanagari → romanised tokens (numbers + a few domain words the rest of the parser understands)
const DEVANAGARI_WORDS: Record<string, string> = {
  "एक": "ek", "दो": "do", "तीन": "teen", "चार": "char", "पांच": "paanch", "पाँच": "paanch", "छह": "chhe", "छः": "chhe",
  "सात": "saat", "आठ": "aath", "नौ": "nau", "दस": "das", "बीस": "bees", "तीस": "tees", "चालीस": "chalis", "पचास": "pachas",
  "साठ": "saath", "सत्तर": "sattar", "अस्सी": "assi", "नब्बे": "nabbe", "सौ": "sau", "हज़ार": "hazaar", "हजार": "hazaar",
  "पच्चीस": "pachchis", "पैंतीस": "paintis", "पैंतालीस": "paintalis", "पचहत्तर": "pachhattar",
  "सी": "see", "बी": "bee", "ए": "ay", "डी": "dee", "ई": "ee", "एफ": "ef", "जी": "gee", "एच": "aitch",
  "कॉलम": "column", "कालम": "column", "बीम": "beam", "स्लैब": "slab", "मंज़िल": "manzil", "मंजिल": "manzil",
  "तीसरी": "teesri", "चौथी": "chauthi", "दूसरी": "doosri", "पहली": "pehli", "मिमी": "mm", "एमएम": "mm",
  "मिलीमीटर": "mm", "रिवीजन": "revision", "ड्राइंग": "drawing", "नहीं": "nahi", "हां": "haan", "हाँ": "haan",
  "स्पेसिंग": "spacing", "कवर": "cover", "सरिया": "sariya", "पे": "pe", "पर": "par", "है": "hai", "में": "mein",
  "ज़ोन": "zone", "जोन": "zone", "वेल्डिंग": "welding", "ढलाई": "dhalai", "लॉग": "log", "कर": "kar", "रोक": "rok",
};

const DEV_DIGITS = "०१२३४५६७८९";

export function devanagariToLatin(text: string): string {
  let t = text.replace(/[०-९]/g, (d) => String(DEV_DIGITS.indexOf(d)));
  // longest-first so "पैंतालीस" wins over "पैंतीस" prefixes
  const keys = Object.keys(DEVANAGARI_WORDS).sort((a, b) => b.length - a.length);
  for (const k of keys) t = t.split(k).join(` ${DEVANAGARI_WORDS[k]} `);
  return t.replace(/[।]/g, ".").replace(/\s+/g, " ").trim();
}

function unitValue(w: string): number | undefined {
  if (w in EN_UNITS) return EN_UNITS[w];
  if (w in EN_TENS) return EN_TENS[w];
  if (w in HI_UNITS) return HI_UNITS[w];
  if (/^\d+$/.test(w)) return Number(w);
  return undefined;
}
function isNumberWord(w: string): boolean {
  return unitValue(w) !== undefined || HUNDRED.has(w) || THOUSAND.has(w);
}

/** Parse a run of number tokens. Returns value and whether it was "structured" (multi-token / multiplier). */
export function parseNumberTokens(tokens: string[]): { value: number; structured: boolean } | null {
  if (!tokens.length) return null;
  const vals = tokens.map((t) => t.toLowerCase());
  // handle "and"
  const ws = vals.filter((w) => w !== "and");
  if (!ws.every(isNumberWord)) return null;
  let total = 0;
  let current = 0;
  let sawMultiplier = false;
  for (let i = 0; i < ws.length; i++) {
    const w = ws[i];
    if (HUNDRED.has(w)) { current = (current || 1) * 100; sawMultiplier = true; continue; }
    if (THOUSAND.has(w)) { total += (current || 1) * 1000; current = 0; sawMultiplier = true; continue; }
    const v = unitValue(w)!;
    // English "one eighty" / "one fifty" → 1*100 + 80 (a unit 1-9 directly followed by a tens word / teen)
    const next = ws[i + 1];
    if (!sawMultiplier && current === 0 && v >= 1 && v <= 9 && next !== undefined && !HUNDRED.has(next) && !THOUSAND.has(next)) {
      const nv = unitValue(next);
      if (nv !== undefined && nv >= 10 && nv <= 99 && (next in EN_TENS || next in EN_UNITS)) {
        current = v * 100 + nv; i++; sawMultiplier = true;
        // "one eighty five"
        const n2 = ws[i + 1];
        if (n2 && n2 in EN_UNITS && EN_UNITS[n2] < 10 && nv % 10 === 0) { current += EN_UNITS[n2]; i++; }
        continue;
      }
    }
    if (v >= 20 && v % 10 === 0 && v < 100) {
      // "eighty five"
      const n2 = ws[i + 1];
      if (n2 && n2 in EN_UNITS && EN_UNITS[n2] < 10) { current += v + EN_UNITS[n2]; i++; continue; }
    }
    current += v;
  }
  return { value: total + current, structured: sawMultiplier || ws.length > 1 };
}

const UNIT_AFTER = /^(mm|millimeter|millimetre|millimeters|millimetres|mili|milli|mil|cm|centimeter|centimetre|centi|m|meter|metre|meters|metres|mpa|nos|number|dia)$/;
const NUMERIC_KEYWORDS = new Set([
  "spacing", "cover", "thickness", "motai", "dia", "diameter", "size", "rev", "revision", "r", "grade", "value",
  "drawing", "level", "floor", "tolerance", "doori", "gap",
]);

/**
 * Replace number-word phrases with digits where context says they are numbers.
 * Input must already be lowercased + Devanagari-normalised. Returns rewritten text.
 */
export function normalizeNumbers(text: string): string {
  const tokens = text.split(/(\s+|[,.;!?—–]+)/); // keep separators
  const words: { tok: string; idx: number }[] = [];
  tokens.forEach((tok, idx) => { if (tok.trim() && !/^[,.;!?—–]+$/.test(tok)) words.push({ tok, idx }); });

  const out = [...tokens];
  let i = 0;
  while (i < words.length) {
    const w = words[i].tok.toLowerCase();
    if (!isNumberWord(w) || /^\d+$/.test(w)) { i++; continue; }
    // gather a run of number words (allow "and" inside)
    let j = i;
    const run: string[] = [];
    while (j < words.length) {
      const wj = words[j].tok.toLowerCase();
      if (isNumberWord(wj) && !/^\d+$/.test(wj)) { run.push(wj); j++; continue; }
      if (wj === "and" && run.length && j + 1 < words.length && isNumberWord(words[j + 1].tok.toLowerCase())) { run.push(wj); j++; continue; }
      break;
    }
    const parsed = parseNumberTokens(run);
    const nextWord = words[j]?.tok.toLowerCase() ?? "";
    const prevWords = words.slice(Math.max(0, i - 3), i).map((x) => x.tok.toLowerCase());
    const unitFollows = UNIT_AFTER.test(nextWord);
    const keywordBefore = prevWords.some((p) => NUMERIC_KEYWORDS.has(p));
    const hasMultiplier = run.some((r) => HUNDRED.has(r) || THOUSAND.has(r));
    const englishOnly = run.every((r) => r in EN_UNITS || r in EN_TENS || HUNDRED.has(r) || THOUSAND.has(r) || r === "and");
    // single ambiguous hindi words ("do", "sat", "so", "saw", "tin"...) need strong context
    const ambiguousSingle = run.length === 1 && ["do", "so", "saw", "sat", "tin", "bis", "ath", "che", "asi", "sath", "tis", "oh", "das"].includes(run[0]);
    const accept = parsed && (
      (hasMultiplier && run.length > 1) || unitFollows ||
      (keywordBefore && !ambiguousSingle) || (keywordBefore && ambiguousSingle && (unitFollows || prevWords.slice(-1)[0] !== undefined && NUMERIC_KEYWORDS.has(prevWords.slice(-1)[0]))) ||
      (englishOnly && parsed.structured && run.length > 1)
    );
    if (accept && parsed) {
      out[words[i].idx] = String(parsed.value);
      for (let k = i + 1; k < j; k++) out[words[k].idx] = "";
      // collapse separators between removed words
      for (let k = words[i].idx + 1; k < words[j - 1].idx; k++) if (!tokens[k].trim()) out[k] = "";
    }
    i = j;
  }
  return out.join("").replace(/\s+/g, " ").trim();
}
