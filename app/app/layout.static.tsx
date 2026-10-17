// Root layout for the static demo export (STATIC_DEMO=1, pageExtensions static.tsx): the same
// shell as app/layout.tsx minus Clerk, so the deployed demo carries no keys.
import type { Metadata, Viewport } from "next";
import { Inter, Instrument_Serif, Geist_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const instrumentSerif = Instrument_Serif({ variable: "--font-instrument-serif", subsets: ["latin"], weight: "400", style: "italic" });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Vesper.ai — Live demo",
  description: "A replay of the Vesper voice console: answers from the record, spoken contradictions, blockers and a voiceprint-gated log — with real Rime audio.",
  icons: { icon: "/brand/vesper-mark.png" },
};

export const viewport: Viewport = { themeColor: "#000000", width: "device-width", initialScale: 1, maximumScale: 1, viewportFit: "cover" };

// Same no-flash theme resolution as app/layout.tsx (only .vs-theme surfaces use it).
const THEME_SCRIPT = `(function(){var d=document.documentElement;try{var p=localStorage.getItem("vesper-theme");if(p!=="light"&&p!=="dark")p="system";var t=p==="system"?(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark"):p;d.setAttribute("data-theme",t);d.setAttribute("data-theme-pref",p)}catch(e){d.setAttribute("data-theme","dark")}})()`;

export default function StaticLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning className={`${inter.variable} ${instrumentSerif.variable} ${geistMono.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col bg-black text-white selection:bg-white/20 selection:text-white">{children}</body>
    </html>
  );
}
