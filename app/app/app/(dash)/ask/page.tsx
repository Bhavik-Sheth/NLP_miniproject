import type { Metadata } from "next";
import View from "@/components/dashboard/pages/AskMemory";

export const metadata: Metadata = { title: "Ask memory · Vesper" };

export default function Page() {
  return <View />;
}
