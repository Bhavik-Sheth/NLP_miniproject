import { Suspense } from "react";
import InviteAccept from "@/components/onboarding/InviteAccept";

export default function OnboardingInvitePage() {
  return (
    <Suspense fallback={null}>
      <InviteAccept />
    </Suspense>
  );
}
