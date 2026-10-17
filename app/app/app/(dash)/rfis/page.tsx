import type { Metadata } from "next";
import { Rfis as View } from "@/components/dashboard/pages/SiteTables";

export const metadata: Metadata = { title: "RFIs · Vesper" };

export default function Page() {
  return <View />;
}
