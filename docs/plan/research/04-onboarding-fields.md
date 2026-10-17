# 04 — Onboarding fields (W2)

Output: `data/onboarding_schema.json` (served at `GET /api/onboarding/schema`). 3 org steps and 12 project
steps with 92 fields. Profiles are stored flat (`profile[field.key]`). The server also accepts
`{stepId: {...}}` and flattens it.

## How the fields were chosen

| Source | What it contributed |
| --- | --- |
| Procore "Create a New Project" / "Update General Project Information" | Project number/code, stage (-> `status` + `currentPhase`), type, work scope (new / renovation), start and completion dates, address |
| Autodesk Build/Docs "Create a Project" | Start/end dates, project templates (-> checklist templates multiselect) |
| Oracle Aconex "Project Information" / "Start a new project" | Project code, site address, shared reference files (-> drawing register / ITP / BOQ uploads) |
| InfraLens LOA format, CPWD GCC | LOA date, agreement no., contract value, DLP, security deposit (2.5% from RA bills, Clause 1A) and performance guarantee (5%, Clause 1). CPWD has no "retention" as such, which is why both fields exist |
| SiteSetu: retention & DLP in India | Retention release is usually 50% at completion and 50% at the end of DLP, and DLP is given in months |
| Statutory approvals lists (Bricknbolt, GRC India, Shiv Tech, Gharpedia) | Building plan / commencement certificate, EC (SEIAA/MoEFCC over 20,000 sq m), fire NOC (>15 m), SPCB CTE/CTO, CLRA labour licence, BOCW registration, tree cutting, road cutting, AAI height NOC, CGWA |
| RERA | Registration needed above 500 sq m or 8 units, hence `reraNumber` |
| IS 1893 (Part 1):2016 | Seismic zones II–V. BIS published IS 1893:2025 with a new Zone VI in Nov 2025. Later reports say it was withdrawn and the 2016 edition reinstated, so the options stay II–V. Add VI if that changes |
| IS 456:2000 Table 3 / 5 / 16, Cl. 11.3, 13.5.1 | Exposure condition, then minimum grade and nominal cover; formwork stripping times; curing days (7 for OPC, 10 with mineral admixtures) |
| IS 875 Part 3 | Basic wind speeds 33/39/44/47/50/55 m/s |
| InfraLens template library (`data/site.db` templates) | Checklist template ids (QC-CON-CHK-001 pre-pour …) and permit-to-work types (hot work, height, confined space, lifting, excavation, electrical) |

## Required (kept minimal)

- Org: `legalName`, `companyType`, `city`, `state`, `primaryContactName`, `primaryContactEmail`.
- Project: `name`, `code`, `projectType`, `city`, `state`, `clientName`, `startDate`, `siteLeadName`,
  `governingCodes`, `drawingConvention`.

## Conventions for consumers

- `usedByVoice: true` means the field is turned into project prime memory (W1). `memoryHint` explains
  how the agent uses it.
- `optionsSource` (only on `checklistTemplates`) means the options list is a starter set. Any template id
  is accepted, and the UI can load the full list from the template library.
- `default` is a UI pre-fill only. The server does not insert defaults.
- `file` values are `{name, docId?, url?}`. Upload through W1 `/api/ingest/file` first, then store the returned `docId`.
- Validation keys: `pattern`/`message`, `min`/`max`, `minLength`/`maxLength`, `minItems`/`maxItems`,
  `afterField`. The server also checks that GSTIN chars 3–12 equal the PAN.

## URLs

- https://support.procore.com/products/online/user-guide/company-level/portfolio/tutorials/create-a-new-project
- https://support.procore.com/products/online/user-guide/project-level/admin/tutorials/update-general-project-information
- https://help.autodesk.com/view/DOCS/ENU/?guid=Create_Project
- https://help.aconex.com/faqs/what-is-project-information/
- https://help.aconex.com/project-admins/create-a-new-project/
- https://infralens.in/formats/tendering/letter-of-award-loa
- https://sitesetu.app/blog/retention-money-defect-liability-period-construction-india
- https://www.bricknbolt.com/blogs-and-articles/permits-and-legal/commercial-construction-checklist-india-guide
- https://www.grcindia.net/statutory-approvals-in-contruction
- https://www.gharpedia.com/blog/india-construction-rules-and-regulations/
- https://www.clearias.com/new-seismic-zonation-map-of-india/
- https://www.insightsonindia.com/2025/11/29/india-revised-earthquake-design-code-2025/
