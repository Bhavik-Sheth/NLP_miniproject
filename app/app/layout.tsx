import type { Metadata, Viewport } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { Inter, Instrument_Serif, Geist_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
  style: "italic",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || "https://vesper-ai.vercel.app"),
  title: "Vesper.ai — Verify every site observation before it is logged",
  description: "Voice-led construction site intelligence that checks spoken observations against current drawings, RFIs, BOQs and permits before they are logged.",
  keywords: ["construction site voice assistant", "site observation software", "drawing verification", "construction QA", "RFI", "construction AI"],
  openGraph: {
    title: "Vesper.ai — Verify every site observation before it is logged",
    description: "Voice-led construction site intelligence grounded in current drawings, RFIs and permits.",
    images: ["/brand/vesper-mark.png"],
  },
  twitter: {
    card: "summary_large_image",
    title: "Vesper.ai — Verify every site observation before it is logged",
    description: "Voice-led construction site intelligence grounded in current drawings, RFIs and permits.",
    images: ["/brand/vesper-mark.png"],
  },
  manifest: "/manifest.webmanifest",
  icons: {
    icon: "/brand/vesper-mark.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#000000",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
};

// Theme (docs/plan/PLAN.md §6): resolve the saved choice ("light" | "dark" | "system") before
// first paint so the dashboard never flashes. Only surfaces that opt into the design tokens
// (.vs-theme) change; the landing page, /demo and auth stay dark.
const THEME_SCRIPT = `(function(){var d=document.documentElement;try{var p=localStorage.getItem("vesper-theme");if(p!=="light"&&p!=="dark")p="system";var t=p==="system"?(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark"):p;d.setAttribute("data-theme",t);d.setAttribute("data-theme-pref",p)}catch(e){d.setAttribute("data-theme","dark")}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      data-theme="dark"
      suppressHydrationWarning
      className={`${inter.variable} ${instrumentSerif.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <meta name="theme-color" content="#000000" />
        <meta name="color-scheme" content="dark" />
      </head>
      <body className="min-h-full flex flex-col bg-black text-white selection:bg-white/20 selection:text-white">
        {/* The Clerk instance forces an organization; send that session task to our own onboarding
            step instead of Clerk's hosted page. */}
        <ClerkProvider taskUrls={{ "choose-organization": "/onboarding/org" }}>
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
