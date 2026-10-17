import type { Metadata } from "next";
import { Drawings as View } from "@/components/dashboard/pages/SiteTables";

export const metadata: Metadata = { title: "Drawings · Vesper" };

export default function Page() {
  return <View />;
}
