import type { Metadata } from "next";
import View from "@/components/dashboard/pages/Scenarios";

export const metadata: Metadata = { title: "Scenarios · Vesper" };

export default function Page() {
  return <View />;
}
