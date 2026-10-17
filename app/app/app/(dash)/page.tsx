import type { Metadata } from "next";
import View from "@/components/dashboard/pages/Overview";

export const metadata: Metadata = { title: "Overview · Vesper" };

export default function Page() {
  return <View />;
}
