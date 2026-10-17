"use client";

// Dev-only visual preview of the onboarding screens (proxy.ts leaves this route public outside
// production). ?view=org | project | success | ingest | invite
import { Suspense } from "react";
import { notFound, useSearchParams } from "next/navigation";
import OrgOnboarding from "@/components/onboarding/OrgOnboarding";
import ProjectOnboarding, { ProjectSuccess } from "@/components/onboarding/ProjectOnboarding";
import { IngestPanel } from "@/components/onboarding/IngestPanel";
import { OnboardingShell } from "@/components/onboarding/primitives";

function Preview() {
  const view = useSearchParams().get("view") ?? "org";
  if (process.env.NODE_ENV === "production") notFound();
  if (view === "project") return <ProjectOnboarding />;
  if (view === "success")
    return (
      <ProjectSuccess
        res={{ project: { id: "prj_preview", name: "Pithoragarh District Hospital", code: "PDH-01", type: "hospital", city: "Pithoragarh" }, memory: { status: "queued" } }}
        uploads={[
          { key: "drawingRegister", label: "Current drawing register", name: "PDH-drawing-register-R3.xlsx", status: "linked" },
          { key: "boqFile", label: "Bill of quantities (BOQ)", name: "BOQ_civil.xlsx", status: "uploading" },
        ]}
      />
    );
  if (view === "ingest")
    return (
      <OnboardingShell>
        <div className="py-10">
          <IngestPanel projectId="P1" />
        </div>
      </OnboardingShell>
    );
  return <OrgOnboarding />;
}

export default function OnboardingPreviewPage() {
  return (
    <Suspense fallback={null}>
      <Preview />
    </Suspense>
  );
}
