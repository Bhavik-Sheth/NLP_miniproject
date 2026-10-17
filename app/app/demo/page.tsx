import type { Metadata } from "next";
import Console from "@/components/Console";

export const metadata: Metadata = {
  title: "Vesper.ai — Live demo",
  description: "Try the Vesper console on recorded engine output: questions, contradictions, blockers and logs.",
};

/** Public, sign-in-free walkthrough of the console on recorded engine output. */
export default function DemoPage() {
  return <Console demo />;
}
