import { describe, expect, it } from "vitest";
import { extract, normalizeText } from "../lib/parser/extract";
import { parseNumberTokens, normalizeNumbers } from "../lib/parser/numbers";

describe("numbers", () => {
  it.each([
    [["ek", "sau", "assi"], 180],
    [["do", "sau"], 200],
    [["one", "eighty"], 180],
    [["one", "fifty"], 150],
    [["one", "hundred", "and", "eighty"], 180],
    [["two", "hundred"], 200],
    [["chalis"], 40],
    [["eighty", "five"], 85],
    [["one", "eighty", "five"], 185],
    [["ek", "sau", "pachas"], 150],
  ])("%j → %d", (toks, v) => {
    expect(parseNumberTokens(toks as string[])?.value).toBe(v);
  });

  it("only converts in numeric context", () => {
    expect(normalizeNumbers("log kar do")).toBe("log kar do");
    expect(normalizeNumbers("spacing ek sau assi mm hai")).toBe("spacing 180 mm hai");
    expect(normalizeNumbers("cover chalis mm")).toBe("cover 40 mm");
    expect(normalizeNumbers("rev teen")).toBe("rev 3");
    expect(normalizeNumbers("one eighty mm")).toBe("180 mm");
  });

  it("handles Devanagari digits and words", () => {
    expect(normalizeText("स्पेसिंग १८० मिमी")).toContain("180 mm");
    expect(normalizeText("एक सौ अस्सी mm")).toContain("180 mm");
  });
});

describe("grids", () => {
  it.each([
    ["C-5 pe spacing 180 mm", "C-5"],
    ["C5 pe spacing 180 mm", "C-5"],
    ["column C 5 pe", "C-5"],
    ["grid C/5", "C-5"],
    ["सी-5 पे spacing", "C-5"],
    ["b-4 pe honeycombing hai", "B-4"],
  ])("%s → %s", (t, g) => {
    expect(extract(t).grid?.value).toBe(g);
  });

  it("spoken letter forms are low confidence", () => {
    const ex = extract("column see five pe spacing one eighty mm");
    expect(ex.grid?.value).toBe("C-5");
    expect(ex.grid!.confidence).toBeLessThan(0.7);
    expect(ex.value?.value).toBe(180);
  });

  it("Devanagari spoken grid", () => {
    const ex = extract("सी पांच पे spacing 180 mm");
    expect(ex.grid?.value).toBe("C-5");
  });
});

describe("levels, drawings, revisions", () => {
  it.each([
    ["L3 pe", "L3"],
    ["level 3", "L3"],
    ["third floor pe", "L3"],
    ["teesri manzil pe", "L3"],
    ["3rd floor", "L3"],
    ["level teen pe", "L3"],
  ])("level %s → %s", (t, l) => expect(extract(t).level?.value).toBe(l));

  it.each([
    ["drawing A-102 Rev 3", "A-102", "R3"],
    ["A 102 R3 mein", "A-102", "R3"],
    ["a102 revision three", "A-102", "R3"],
    ["drawing A-102 rev teen", "A-102", "R3"],
    ["S-301 R-2", "S-301", "R2"],
  ])("%s", (t, d, r) => {
    const ex = extract(t);
    expect(ex.drawingNumber?.value).toBe(d);
    expect(ex.revisionClaimed?.value).toBe(r);
  });

  it("drawing number without letter is low-confidence", () => {
    const ex = extract("drawing ek sau do dekho");
    expect(ex.drawingNumber?.value).toBe("102");
    expect(ex.drawingNumber!.confidence).toBeLessThan(0.7);
  });
});

describe("full utterances", () => {
  it("S01 canonical Hinglish utterance", () => {
    const ex = extract("Column line C-5 pe rebar spacing 180 mm hai, drawing A-102 Rev 3 mein 200 mm dikh raha hai.");
    expect(ex.grid?.value).toBe("C-5");
    expect(ex.element?.value).toBe("column");
    expect(ex.attribute?.value).toBe("rebar_spacing");
    expect(ex.value?.value).toBe(180);
    expect(ex.unit?.value).toBe("mm");
    expect(ex.drawingNumber?.value).toBe("A-102");
    expect(ex.revisionClaimed?.value).toBe("R3");
    expect(ex.drawingValueClaimed?.value).toBe(200);
    expect(ex.decision).toBeUndefined();
  });

  it("spoken Hindi value", () => {
    const ex = extract("C-6 pe spacing ek sau assi mili hai");
    expect(ex.value?.value).toBe(180);
    expect(ex.unit?.value).toBe("mm");
  });

  it("cm converts to mm", () => {
    expect(extract("cover 4 cm hai").value?.value).toBe(40);
  });

  it("attributes", () => {
    expect(extract("stirrup spacing 150").attribute?.value).toBe("stirrup_spacing");
    expect(extract("clear cover 40 mm").attribute?.value).toBe("cover");
    expect(extract("slab ki motai 150 mm").attribute?.value).toBe("thickness");
    expect(extract("slab ki motai 150 mm").element?.value).toBe("slab");
    expect(extract("sariya ka size 12 mm").attribute?.value).toBe("rebar_dia");
  });

  it("activities", () => {
    expect(extract("Zone B mein welding shuru kar rahe hain").activity?.value).toBe("hot_work");
    expect(extract("Zone B mein welding shuru kar rahe hain").zone?.value).toBe("Zone B");
    expect(extract("L4 slab ki dhalai shuru karein?").activity?.value).toBe("pour");
    expect(extract("grinding start karo").activity?.value).toBe("hot_work");
  });
});

describe("barge-in corrections", () => {
  it.each([
    ["wait— C-6, not C-5", "C-6", ["C-5"]],
    ["nahi nahi, C-6", "C-6", []],
    ["C-5 nahi, C-6", "C-6", ["C-5"]],
    ["C-6 hai, C-5 nahi", "C-6", ["C-5"]],
    ["sorry, C-6 bola tha maine", "C-6", []],
  ])("%s", (t, g, neg) => {
    const ex = extract(t);
    expect(ex.grid?.value).toBe(g);
    expect(ex.negatedGrids).toEqual(neg);
    expect(ex.isCorrection || ex.deny).toBe(true);
  });

  it("value correction", () => {
    const ex = extract("nahi, 190 mm, 180 nahi");
    expect(ex.value?.value).toBe(190);
    expect(ex.negatedValues).toEqual([180]);
  });
  it("english value correction", () => {
    const ex = extract("wait, 190 not 180");
    expect(ex.value?.value).toBe(190);
  });
});

describe("decisions", () => {
  it.each([
    ["log kar do", "log_observation"],
    ["haan, log karo", "log_observation"],
    ["RFI raise karo", "raise_rfi"],
    ["raise an RFI", "raise_rfi"],
    ["RFI nahi chahiye, bas log kar do", "log_observation"],
    ["NCR raise karo", "raise_ncr"],
    ["kaam rok do", "stop_work"],
    ["stop work", "stop_work"],
    ["cancel", "cancel"],
    ["rehne do", "cancel"],
  ])("%s → %s", (t, d) => expect(extract(t).decision).toBe(d));

  it("rfi declined without decision", () => {
    const ex = extract("RFI nahi chahiye");
    expect(ex.rfiDeclined).toBe(true);
    expect(ex.decision).toBeUndefined();
  });

  it("yes/no", () => {
    expect(extract("haan sahi hai").affirm).toBe(true);
    expect(extract("yes").affirm).toBe(true);
    expect(extract("nahi").deny).toBe(true);
    expect(extract("nahi nahi, C-6").deny).toBe(true);
  });

  it("'do' inside 'log kar do' is not a number", () => {
    const ex = extract("theek hai log kar do");
    expect(ex.value).toBeUndefined();
  });
});
