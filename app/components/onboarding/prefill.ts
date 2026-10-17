// Realistic sample answers for the onboarding wizards ("Prefill sample site"). Values match the
// option values in data/onboarding_schema.json. Each call picks one Indian construction site and
// adds a short suffix to codes so repeated demo projects don't collide.
import type { ProfileValues } from "@/lib/api-tenancy";

const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (days: number) => iso(new Date(Date.now() + days * 86_400_000));
const suffix = () => Math.random().toString(36).slice(2, 5).toUpperCase();

type Site = { org: ProfileValues; project: ProfileValues };

const SITES: Array<() => Site> = [
  () => ({
    org: {
      legalName: "Deccan Buildcon Private Limited",
      brandName: "Deccan Buildcon",
      companyType: "contractor",
      gstin: "27AAECD4821K1Z3",
      pan: "AAECD4821K",
      companySize: "201-1000",
      website: "https://deccanbuildcon.example.in",
      registeredAddress: "4th Floor, Kalpataru Square, Senapati Bapat Road",
      city: "Pune",
      state: "Maharashtra",
      pincode: "411016",
      primaryContactName: "Rohit Kulkarni",
      primaryContactEmail: "rohit.kulkarni@deccanbuildcon.example.in",
      primaryContactPhone: "+91 98220 41736",
      workingLanguages: ["English", "Hindi", "Marathi", "Hinglish"],
    },
    project: {
      name: "Nashik Civil Hospital — 300-bed Super Speciality Block",
      code: `NSK-HSP-${suffix()}`,
      projectType: "hospital",
      workScope: "new",
      description:
        "G+7 RCC framed super speciality block with 2-level basement, OT complex on L3, ICU on L4, helipad on terrace. Includes staff quarters (G+4) and a 1.2 ML sump.",
      builtUpArea: 42500,
      status: "active",
      currentPhase: "superstructure",
      siteAddress: "Civil Hospital Campus, Trimbak Road, near Old CBS",
      city: "Nashik",
      district: "Nashik",
      state: "Maharashtra",
      pincode: "422002",
      geo: { lat: 20.0059, lng: 73.7749 },
      seismicZone: "III",
      basicWindSpeed: "39",
      exposureCondition: "moderate",
      soilType: "medium",
      safeBearingCapacity: 250,
      monsoonMonths: ["Jun", "Jul", "Aug", "Sep"],
      siteAccessNotes: "Single gate on Trimbak Road; heavy vehicles only 10 pm–6 am. Hospital OPD stays live — no crane swing over the east wing.",
      clientName: "Public Works Department, Government of Maharashtra",
      contractType: "item_rate",
      contractConditions: "state_pwd",
      contractValue: 1865000000,
      agreementNumber: "PWD/NSK/B-1/2025-26/14",
      loaDate: addDays(-240),
      startDate: addDays(-210),
      scheduledCompletion: addDays(520),
      dlpMonths: 24,
      ldClause: "0.05% of contract value per week of delay, capped at 10%.",
      mobilisationAdvancePct: 5,
      retentionPct: 5,
      performanceGuaranteePct: 3,
      priceEscalation: true,
      stakeholders: [
        { role: "client_rep", company: "PWD Nashik Division", person: "S. R. Patil, Executive Engineer", scope: "Employer's representative", phone: "+91 94221 55310", email: "ee.nashik@pwd.example.gov.in" },
        { role: "pmc", company: "Tandon Infra Consultants", person: "Meera Joshi", scope: "Project management & QA audit", phone: "+91 98905 22871", email: "meera.joshi@tandoninfra.example.in" },
        { role: "architect", company: "Studio Kshitij Architects", person: "Aniket Deshpande", scope: "Architecture & hospital planning", phone: "+91 98230 66142", email: "aniket@kshitij.example.in" },
        { role: "structural", company: "Sthapatya Structural Engineers", person: "Dr. V. N. Rao", scope: "Structural design, drawing approvals", phone: "+91 98811 43027", email: "vnrao@sthapatya.example.in" },
        { role: "mep", company: "AirCare MEP Consultants", person: "Farhan Shaikh", scope: "HVAC, medical gases, electrical", phone: "+91 97640 19835", email: "farhan@aircare.example.in" },
        { role: "testing_lab", company: "Nashik Materials Testing Lab (NABL)", person: "Priya Gaikwad", scope: "Cube, steel, soil tests", phone: "+91 90110 77412", email: "lab@nmtl.example.in" },
      ],
      siteLeadName: "Amit Bhosale",
      siteLeadPhone: "+91 98501 33927",
      siteLeadEmail: "amit.bhosale@deccanbuildcon.example.in",
      team: [
        { name: "Amit Bhosale", role: "project_manager", phone: "+91 98501 33927", email: "amit.bhosale@deccanbuildcon.example.in", canLogObservations: true },
        { name: "Sneha Pawar", role: "qaqc", phone: "+91 88888 21406", email: "sneha.pawar@deccanbuildcon.example.in", canLogObservations: true },
        { name: "Imran Khan", role: "site_engineer", phone: "+91 90496 55012", email: "imran.khan@deccanbuildcon.example.in", canLogObservations: true },
        { name: "Rajesh Yadav", role: "hse", phone: "+91 77200 81934", email: "rajesh.yadav@deccanbuildcon.example.in", canLogObservations: true },
        { name: "Sunil Jadhav", role: "foreman", phone: "+91 98600 47218", email: "", canLogObservations: false },
      ],
      blocks: [
        { name: "Super Speciality Block", code: "SSB", levels: "B2, B1, GF, L1–L7, Terrace", structuralSystem: "rcc_frame" },
        { name: "Staff Quarters", code: "SQ", levels: "GF, L1–L4", structuralSystem: "rcc_frame" },
      ],
      levelNaming: "B2, B1, GF, L1…L7, TR",
      gridScheme: "Letters A–M east–west, numbers 1–14 north–south; columns named like C-7 or E-1",
      zones: "Zone A (OPD side), Zone B (OT/ICU), Zone C (services core)",
      keyElements: ["raft", "column", "beam", "slab", "shear_wall", "retaining_wall", "staircase", "lift_core", "water_tank"],
      governingCodes: ["IS 456", "IS 1893", "IS 13920", "IS 875", "IS 1786", "IS 10262", "SP 34", "NBC 2016"],
      concreteGrades: [
        { element: "Raft & retaining wall", grade: "M35" },
        { element: "Columns & shear walls", grade: "M30" },
        { element: "Beams & slabs", grade: "M25" },
        { element: "PCC", grade: "M15" },
      ],
      steelGrade: "Fe500D",
      nominalCover: [
        { element: "Footing / raft", coverMm: 50 },
        { element: "Column", coverMm: 40 },
        { element: "Beam", coverMm: 30 },
        { element: "Slab", coverMm: 25 },
      ],
      tolerances: "Cover +10/−5 mm; slab thickness +10/−5 mm; column plumb 1 in 1000 max 20 mm; rebar spacing ±10 mm.",
      cementType: ["OPC 53", "PPC"],
      concreteSource: "rmc",
      admixtures: "PCE-based superplasticiser, retarder for slab pours in summer",
      curingDays: 10,
      strippingTimes: "Vertical faces 24 h; slab soffit props 7 days; beam soffit props 14 days (IS 456 Cl. 11.3.1).",
      drawingConvention: "SSB-STR-L3-201 (block-discipline-level-sheet)",
      disciplineCodes: "ARC, STR, MEP, HVAC, PLB, ELE, FIR",
      revisionScheme: "R0",
      drawingStatuses: ["For Approval", "For Construction", "As Built", "Superseded"],
      rfiNumbering: "RFI-SSB-###",
      ncrNumbering: "NCR-SSB-###",
      siteInstructionNumbering: "SI-###",
      cdeTool: "acc",
      reraNumber: "",
      approvals: [
        { type: "building_permit", number: "NMC/BP/2025/0871", authority: "Nashik Municipal Corporation", validFrom: addDays(-300), validTo: addDays(795) },
        { type: "environmental_clearance", number: "SEIAA-MH/EC/2025/112", authority: "SEIAA Maharashtra", validFrom: addDays(-280), validTo: addDays(2000) },
        { type: "fire_noc", number: "NMC/FIRE/PROV/2025/209", authority: "Nashik Fire Brigade", validFrom: addDays(-260), validTo: addDays(470) },
        { type: "bocw", number: "MH/BOCW/NSK/2025/3321", authority: "Maharashtra BOCW Welfare Board", validFrom: addDays(-230), validTo: addDays(500) },
        { type: "labour_licence", number: "CLRA/NSK/2025/1177", authority: "Assistant Labour Commissioner, Nashik", validFrom: addDays(-225), validTo: addDays(140) },
      ],
      holdPoints: [
        { activity: "Pre-pour inspection of slab reinforcement & cover", releasedBy: "PMC QA engineer", type: "hold" },
        { activity: "Raft waterproofing before PCC protection", releasedBy: "PMC + waterproofing vendor", type: "hold" },
        { activity: "Cube casting at pour", releasedBy: "Testing lab", type: "witness" },
        { activity: "Formwork & staging for OT slab (L3)", releasedBy: "Structural consultant", type: "hold" },
      ],
      testingLab: "Nashik Materials Testing Lab (NABL accredited)",
      checklistTemplates: ["QC-CON-CHK-001", "QC-CON-CHK-002", "QC-CEM-CHK-001", "QC-AGG-CHK-001", "QC-FIR-CHK-001"],
      permitTypes: ["hot_work", "height", "excavation", "lifting", "electrical"],
      hseOfficerName: "Rajesh Yadav",
      hseOfficerPhone: "+91 77200 81934",
      nearestHospital: "Civil Hospital Nashik casualty (on campus, 300 m)",
      emergencyContacts: [
        { label: "Ambulance", phone: "108" },
        { label: "Fire brigade", phone: "101" },
        { label: "Site HSE officer", phone: "+91 77200 81934" },
      ],
      milestones: [
        { name: "Raft & basement complete", plannedDate: addDays(-60), paymentLinkedPct: 15 },
        { name: "Superstructure L4 slab cast", plannedDate: addDays(45), paymentLinkedPct: 20 },
        { name: "Structure topped out", plannedDate: addDays(170), paymentLinkedPct: 20 },
        { name: "MEP first fix & OT modules", plannedDate: addDays(360), paymentLinkedPct: 25 },
        { name: "Commissioning & handover", plannedDate: addDays(520), paymentLinkedPct: 20 },
      ],
      workingHours: "08:00–18:00, concrete pours may run to 23:00 with PMC approval",
      shifts: "double",
      weeklyOff: "Sunday",
      holidays: "Republic Day, Holi, Gudi Padwa, Independence Day, Ganesh Chaturthi, Diwali (3 days)",
      siteLanguages: ["Hinglish", "Marathi", "Hindi", "English"],
      replyLanguage: "en-IN",
      units: "metric",
      strictness: "strict",
      dimensionTolerancePct: 5,
      requireConfirmBeforeLog: true,
      dailySummaryEmail: true,
    },
  }),
  () => ({
    org: {
      legalName: "Gangotri Infraprojects Limited",
      brandName: "Gangotri Infra",
      companyType: "contractor",
      gstin: "09AAFCG7315M1ZQ",
      pan: "AAFCG7315M",
      companySize: "1000+",
      website: "https://gangotriinfra.example.in",
      registeredAddress: "Plot 22, Vibhuti Khand, Gomti Nagar",
      city: "Lucknow",
      state: "Uttar Pradesh",
      pincode: "226010",
      primaryContactName: "Neha Srivastava",
      primaryContactEmail: "neha.srivastava@gangotriinfra.example.in",
      primaryContactPhone: "+91 94150 28374",
      workingLanguages: ["English", "Hindi", "Hinglish"],
    },
    project: {
      name: "Ghaghara River Bridge on SH-30 (4-lane, 620 m)",
      code: `GHG-BRG-${suffix()}`,
      projectType: "bridge",
      workScope: "new",
      description:
        "620 m 4-lane PSC box-girder bridge, 16 spans of 38.75 m on pile foundations (1.2 m dia), with 1.8 km approaches and RE walls.",
      builtUpArea: 0,
      status: "active",
      currentPhase: "substructure",
      siteAddress: "SH-30 crossing near Elgin Bridge, Barabanki side",
      city: "Barabanki",
      district: "Barabanki",
      state: "Uttar Pradesh",
      pincode: "225001",
      geo: { lat: 26.9322, lng: 81.4383 },
      seismicZone: "IV",
      basicWindSpeed: "47",
      exposureCondition: "severe",
      soilType: "soft",
      safeBearingCapacity: 80,
      monsoonMonths: ["Jun", "Jul", "Aug", "Sep", "Oct"],
      siteAccessNotes: "River works stop when gauge crosses 106.0 m (danger level). Night barge movement not permitted.",
      clientName: "UP State Bridge Corporation Ltd",
      contractType: "epc",
      contractConditions: "morth_epc",
      contractValue: 3120000000,
      agreementNumber: "UPSBC/EPC/SH30/2025/03",
      loaDate: addDays(-400),
      startDate: addDays(-360),
      scheduledCompletion: addDays(600),
      dlpMonths: 60,
      ldClause: "0.05% of contract price per day of delay on each milestone, capped at 10% of contract price.",
      mobilisationAdvancePct: 10,
      retentionPct: 6,
      performanceGuaranteePct: 5,
      priceEscalation: true,
      stakeholders: [
        { role: "client_rep", company: "UPSBC Lucknow", person: "A. K. Verma, Project Manager", scope: "Authority engineer liaison", phone: "+91 94154 60821", email: "pm.sh30@upsbc.example.gov.in" },
        { role: "pmc", company: "Rites-style Authority Engineer JV", person: "Col. (Retd.) P. S. Negi", scope: "Authority engineer", phone: "+91 98390 11274", email: "ae.sh30@aejv.example.in" },
        { role: "structural", company: "Bharat Bridge Design Consultants", person: "Kavita Menon", scope: "GAD, PSC design, pile design", phone: "+91 99101 55806", email: "kavita@bbdc.example.in" },
        { role: "geotech", company: "Terra Geotechnics", person: "Dr. Alok Mishra", scope: "Bore logs, pile load tests", phone: "+91 94500 37712", email: "alok@terrageo.example.in" },
        { role: "testing_lab", company: "UP Highway Research Lab", person: "Sanjay Tiwari", scope: "Materials testing", phone: "+91 90268 44190", email: "lab@uphrl.example.in" },
      ],
      siteLeadName: "Vikram Singh Chauhan",
      siteLeadPhone: "+91 98391 72045",
      siteLeadEmail: "vikram.chauhan@gangotriinfra.example.in",
      team: [
        { name: "Vikram Singh Chauhan", role: "project_manager", phone: "+91 98391 72045", email: "vikram.chauhan@gangotriinfra.example.in", canLogObservations: true },
        { name: "Pooja Dubey", role: "qaqc", phone: "+91 88400 61239", email: "pooja.dubey@gangotriinfra.example.in", canLogObservations: true },
        { name: "Mohd. Arif", role: "surveyor", phone: "+91 97956 30127", email: "arif@gangotriinfra.example.in", canLogObservations: true },
        { name: "Deepak Rawat", role: "hse", phone: "+91 70070 25581", email: "deepak.rawat@gangotriinfra.example.in", canLogObservations: true },
      ],
      blocks: [
        { name: "Main bridge", code: "MB", levels: "Pile, pile cap, pier P1–P15, pier cap, superstructure", structuralSystem: "pt" },
        { name: "Approaches", code: "AP", levels: "Ch 0+000 to 1+800", structuralSystem: "rcc_frame" },
      ],
      levelNaming: "Pile cap (PC), pier (P), pier cap (PCAP), deck (DK)",
      gridScheme: "Piers P1–P15 and abutments A1/A2; piles named P7-PL3",
      zones: "Barabanki bank, river channel, Ayodhya bank",
      chainageFormat: "Ch 1+245.500",
      keyElements: ["pile", "pile_cap", "pier", "girder", "retaining_wall"],
      governingCodes: ["IS 456", "IS 1893", "IS 1786", "IS 2502", "MoRTH"],
      concreteGrades: [
        { element: "Piles & pile caps", grade: "M35" },
        { element: "Piers & pier caps", grade: "M40" },
        { element: "PSC box girder", grade: "M50" },
      ],
      steelGrade: "Fe500D",
      nominalCover: [
        { element: "Pile", coverMm: 75 },
        { element: "Pile cap", coverMm: 75 },
        { element: "Pier", coverMm: 50 },
        { element: "Box girder", coverMm: 40 },
      ],
      tolerances: "Pile position ±75 mm, verticality 1 in 150; pier plumb 1 in 500; cover +10/−0 mm.",
      cementType: ["OPC 53", "PSC"],
      concreteSource: "batching_plant",
      admixtures: "PCE superplasticiser; corrosion-inhibiting admixture in splash zone",
      curingDays: 14,
      strippingTimes: "Pier shutters 48 h; girder soffit only after stressing.",
      drawingConvention: "SH30-GHG-STR-P07-004",
      disciplineCodes: "GEN, STR, GEO, HYD, RDW",
      revisionScheme: "R0",
      drawingStatuses: ["For Approval", "Good For Construction", "As Built", "Superseded"],
      rfiNumbering: "RFI-GHG-####",
      ncrNumbering: "NCR-GHG-####",
      siteInstructionNumbering: "AE-SI-###",
      cdeTool: "none",
      approvals: [
        { type: "environmental_clearance", number: "MoEF/UP/BR/2025/41", authority: "SEIAA Uttar Pradesh", validFrom: addDays(-420), validTo: addDays(1400) },
        { type: "labour_licence", number: "CLRA/BBK/2025/088", authority: "Deputy Labour Commissioner, Barabanki", validFrom: addDays(-350), validTo: addDays(15) },
        { type: "bocw", number: "UP/BOCW/BBK/2025/1942", authority: "UP BOCW Board", validFrom: addDays(-340), validTo: addDays(390) },
      ],
      holdPoints: [
        { activity: "Pile bore depth & founding strata confirmation", releasedBy: "Authority engineer + geotech", type: "hold" },
        { activity: "Cage lowering & tremie concreting of piles", releasedBy: "Authority engineer", type: "witness" },
        { activity: "PSC cable profile check before girder pour", releasedBy: "Design consultant", type: "hold" },
        { activity: "Stressing sequence & elongation record", releasedBy: "Authority engineer", type: "hold" },
      ],
      testingLab: "UP Highway Research Lab",
      checklistTemplates: ["QC-CON-CHK-001", "QC-CON-CHK-003", "QC-BRG-CHK-001", "QC-AGG-CHK-001"],
      permitTypes: ["excavation", "lifting", "height", "hot_work", "confined_space"],
      hseOfficerName: "Deepak Rawat",
      hseOfficerPhone: "+91 70070 25581",
      nearestHospital: "District Hospital Barabanki (9 km)",
      emergencyContacts: [
        { label: "Ambulance", phone: "108" },
        { label: "River police", phone: "112" },
        { label: "Site HSE officer", phone: "+91 70070 25581" },
      ],
      milestones: [
        { name: "All piles complete", plannedDate: addDays(20), paymentLinkedPct: 20 },
        { name: "Substructure P1–P15 complete", plannedDate: addDays(200), paymentLinkedPct: 25 },
        { name: "Superstructure spans launched", plannedDate: addDays(430), paymentLinkedPct: 30 },
        { name: "Wearing coat, crash barriers, handover", plannedDate: addDays(600), paymentLinkedPct: 25 },
      ],
      workingHours: "07:00–19:00; river works daylight only",
      shifts: "double",
      weeklyOff: "None",
      holidays: "Holi, Independence Day, Chhath (river bank closure), Diwali",
      siteLanguages: ["Hindi", "Hinglish", "English"],
      replyLanguage: "en-IN",
      units: "metric",
      strictness: "strict",
      dimensionTolerancePct: 5,
      requireConfirmBeforeLog: true,
      dailySummaryEmail: true,
    },
  }),
];

// The org and project wizards are separate pages, so the chosen site is kept in sessionStorage:
// prefilling the org picks the next site, and the project wizard then prefills the same site.
const KEY = "vesper-prefill-site";

function stored(): number | null {
  try {
    const v = sessionStorage.getItem(KEY);
    return v === null ? null : Number(v) % SITES.length;
  } catch {
    return null;
  }
}

function remember(i: number) {
  try {
    sessionStorage.setItem(KEY, String(i));
  } catch {
    /* private mode */
  }
}

/** Org prefill rotates to the next sample site on every click. */
export function prefillOrg(): ProfileValues {
  const prev = stored();
  const i = prev === null ? Math.floor(Math.random() * SITES.length) : (prev + 1) % SITES.length;
  remember(i);
  return SITES[i]().org;
}

/** Project prefill uses the site chosen for the org; a second click rotates to another site. */
export function prefillProject(): ProfileValues {
  const key = `${KEY}:project-used`;
  let i = stored();
  let used = false;
  try {
    used = sessionStorage.getItem(key) === String(i);
  } catch {
    /* ignore */
  }
  if (i === null || used) {
    i = i === null ? Math.floor(Math.random() * SITES.length) : (i + 1) % SITES.length;
    remember(i);
  }
  try {
    sessionStorage.setItem(key, String(i));
  } catch {
    /* ignore */
  }
  return SITES[i]().project;
}

/** Every sample, for tests. */
export const allSamples = (): Site[] => SITES.map((s) => s());
