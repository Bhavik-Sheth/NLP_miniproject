import type { Metadata } from "next";
import { Team as View } from "@/components/dashboard/pages/TeamSettings";

export const metadata: Metadata = { title: "Team · Vesper" };

export default function Page() {
  return <View />;
}
