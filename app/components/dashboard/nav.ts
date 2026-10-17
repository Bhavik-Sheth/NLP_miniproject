import type { IconName } from "./icons";

export type NavItem = { href: string; label: string; icon: IconName; keys: string; keywords?: string; id: string };
export type NavGroup = { label: string; items: NavItem[] };

// Keyboard: press G, then the key (Linear-style). Shown in the sidebar on hover and in ⌘K.
export const NAV: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { id: "overview", href: "/app", label: "Overview", icon: "home", keys: "G H", keywords: "home dashboard kpi" },
      { id: "live", href: "/app/live", label: "Live voice", icon: "mic", keys: "G L", keywords: "call talk livekit conversation" },
      { id: "ask", href: "/app/ask", label: "Ask memory", icon: "sparkles", keys: "G A", keywords: "question chat rag" },
    ],
  },
  {
    label: "Knowledge",
    items: [
      { id: "memory", href: "/app/memory", label: "Memory layer", icon: "brain", keys: "G M", keywords: "graph corpora lancedb kuzu search" },
      { id: "documents", href: "/app/documents", label: "Documents & ingest", icon: "file", keys: "G I", keywords: "upload pdf ingest voice note" },
    ],
  },
  {
    label: "Site record",
    items: [
      { id: "observations", href: "/app/observations", label: "Observations", icon: "eye", keys: "G O", keywords: "logs" },
      { id: "drawings", href: "/app/drawings", label: "Drawings", icon: "layers", keys: "G D", keywords: "revisions for construction superseded" },
      { id: "rfis", href: "/app/rfis", label: "RFIs", icon: "help", keys: "G R", keywords: "request for information" },
      { id: "permits", href: "/app/permits", label: "Permits & hold points", icon: "shield", keys: "G P", keywords: "ptw hot work hold point" },
    ],
  },
  {
    label: "Project",
    items: [
      { id: "scenarios", href: "/app/scenarios", label: "Scenarios", icon: "flask", keys: "G S", keywords: "tests eval suite" },
      { id: "team", href: "/app/team", label: "Team", icon: "users", keys: "G T", keywords: "members invite" },
      { id: "settings", href: "/app/settings", label: "Settings", icon: "settings", keys: "G E", keywords: "voice enrol enroll theme profile" },
    ],
  },
];

export const NAV_ITEMS = NAV.flatMap((g) => g.items);

export function activeItem(pathname: string): NavItem {
  const p = pathname.replace(/\/$/, "") || "/app";
  return (
    [...NAV_ITEMS].sort((a, b) => b.href.length - a.href.length).find((i) => p === i.href || (i.href !== "/app" && p.startsWith(i.href))) ??
    NAV_ITEMS[0]
  );
}
