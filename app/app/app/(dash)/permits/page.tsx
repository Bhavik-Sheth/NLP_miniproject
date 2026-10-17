import type { Metadata } from "next";
import { Permits as View } from "@/components/dashboard/pages/SiteTables";

export const metadata: Metadata = { title: "Permits & hold points · Vesper" };

export default function Page() {
  return <View />;
}
