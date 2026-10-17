import type { Metadata } from "next";
import { Settings as View } from "@/components/dashboard/pages/TeamSettings";

export const metadata: Metadata = { title: "Settings · Vesper" };

export default function Page() {
  return <View />;
}
