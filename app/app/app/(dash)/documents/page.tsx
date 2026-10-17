import type { Metadata } from "next";
import View from "@/components/dashboard/pages/Documents";

export const metadata: Metadata = { title: "Documents & ingest · Vesper" };

export default function Page() {
  return <View />;
}
