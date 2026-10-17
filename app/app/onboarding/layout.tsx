import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Set up Vesper",
  description: "Create your organization and first project so Vesper can verify site observations.",
};

export default function OnboardingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
