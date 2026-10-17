import type { Metadata } from "next";
import View from "@/components/dashboard/pages/MemoryLayer";

export const metadata: Metadata = { title: "Memory layer · Vesper" };

export default function Page() {
  return <View />;
}
