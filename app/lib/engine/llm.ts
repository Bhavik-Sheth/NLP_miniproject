// Optional LLM slot-filler. Only runs when ANTHROPIC_API_KEY is set, only for slots the deterministic
// parser missed, and everything it returns is marked source="llm" with low confidence, so the dialogue
// engine will ask for voice confirmation before any of it can reach field_observations.
import Anthropic from "@anthropic-ai/sdk";
import type { Extraction, Slot } from "../parser/extract";

export type LlmAssist = (text: string, ex: Extraction) => Promise<Partial<Extraction>>;

const LLM_CONFIDENCE = 0.5;

export function makeClaudeAssist(): LlmAssist | undefined {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) return undefined;
  const client = new Anthropic({ apiKey: key, timeout: 2500, maxRetries: 0 });
  const model = process.env.ANTHROPIC_MODEL || "claude-haiku-4-5-20251001";

  return async (text, ex) => {
    const missing = (["grid", "level", "zone", "element", "attribute", "value", "unit", "drawingNumber", "revisionClaimed", "activity"] as const)
      .filter((k) => !ex[k]);
    if (!missing.length) return {};
    try {
      const res = await client.messages.create({
        model,
        max_tokens: 400,
        system:
          "You extract construction-site entities from a noisy Hinglish (Hindi-English) speech transcript. " +
          "Only fill a field if the transcript clearly implies it; otherwise omit it. Never guess numbers.",
        tools: [{
          name: "fill_slots",
          description: "Return the entities found in the transcript.",
          input_schema: {
            type: "object",
            properties: {
              grid: { type: "string", description: "Grid line like C-5" },
              level: { type: "string", description: "Level like L3" },
              zone: { type: "string", description: "Zone like 'Zone B'" },
              element: { type: "string", enum: ["column", "beam", "slab", "footing", "wall"] },
              attribute: { type: "string", enum: ["rebar_spacing", "stirrup_spacing", "cover", "thickness", "rebar_dia", "size", "grade", "bar_count"] },
              value: { type: "number" },
              unit: { type: "string", enum: ["mm", "cm", "m", "MPa", "nos"] },
              drawingNumber: { type: "string", description: "Drawing number like A-102" },
              revisionClaimed: { type: "string", description: "Revision like R3" },
              activity: { type: "string", enum: ["hot_work", "pour", "height", "excavation"] },
            },
            additionalProperties: false,
          },
        }],
        tool_choice: { type: "tool", name: "fill_slots" },
        messages: [{ role: "user", content: `Transcript: ${text}\nFields still missing: ${missing.join(", ")}` }],
      });
      const block = res.content.find((b) => b.type === "tool_use");
      if (!block || block.type !== "tool_use") return {};
      const input = block.input as Record<string, string | number>;
      const out: Partial<Extraction> = {};
      for (const k of missing) {
        const v = input[k];
        if (v === undefined || v === null || v === "") continue;
        (out as Record<string, Slot<string | number>>)[k] = { value: v, confidence: LLM_CONFIDENCE, source: "llm" };
      }
      return out;
    } catch {
      return {}; // degraded mode: parser-only
    }
  };
}
