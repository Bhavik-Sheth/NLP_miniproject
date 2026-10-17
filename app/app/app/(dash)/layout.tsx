import type { Metadata } from "next";
import Shell from "@/components/dashboard/Shell";
import Gate from "@/components/dashboard/Gate";

export const metadata: Metadata = { title: "Vesper — Dashboard" };

// Laptop dashboard. `.vs-theme` opts this subtree into the light/dark design tokens.
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="vs-theme min-h-dvh">
      <Gate>
        <Shell>{children}</Shell>
      </Gate>
    </div>
  );
}
