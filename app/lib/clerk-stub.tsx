// Static demo build only (STATIC_DEMO=1): stands in for @clerk/nextjs so the exported site needs
// no Clerk keys, no auth backend and makes no network calls. Never used by the real app.
import type { ReactNode } from "react";

const noop = async () => undefined;

export const useAuth = () => ({
  getToken: async () => null,
  userId: "local-demo",
  orgId: "org_local_demo",
  isLoaded: true,
  isSignedIn: true,
});
export const useUser = () => ({
  user: {
    id: "local-demo",
    fullName: "Site Engineer",
    firstName: "Site",
    lastName: "Engineer",
    primaryEmailAddress: { emailAddress: "engineer@vesper.local" },
    imageUrl: "",
  },
  isLoaded: true,
  isSignedIn: true,
});
export const useClerk = () => ({ setActive: noop, signOut: noop, openSignIn: noop, session: null });
export const useOrganization = (_opts?: unknown) => ({
  organization: { id: "org_local_demo", name: "Vesper Demo" },
  memberships: null,
  isLoaded: true,
});
export const useOrganizationList = (_opts?: unknown) => ({
  isLoaded: true,
  createOrganization: async () => ({ id: "org_local_demo" }),
  setActive: noop,
  userMemberships: { data: [], isLoading: false, hasNextPage: false, fetchNext: noop },
});
export const UserButton = (_props?: unknown) => null;
export const OrganizationSwitcher = (_props?: unknown) => null;
export const SignIn = () => null;
export const SignUp = () => null;
export const SignedIn = ({ children }: { children?: ReactNode }) => children ?? null;
export const SignedOut = (_props: { children?: ReactNode }) => null;
export const ClerkProvider = ({ children }: { children: ReactNode }) => children;
