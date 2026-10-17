import type { Metadata } from "next";
import { Observations as View } from "@/components/dashboard/pages/SiteTables";

export const metadata: Metadata = { title: "Observations · Vesper" };

export default function Page() {
  return <View />;
}
