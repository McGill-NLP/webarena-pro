const SEED_DATE = new Date("2026-01-01T00:00:00.000Z");

const PROJECT_STATUSES = ["Backlog", "In Progress", "In Review", "Done"] as const;
const PROJECT_OWNERS = ["Demo", "Alex", "Alice"] as const;
const PROJECT_AREAS = ["Mobile", "Growth", "Reliability", "Payments", "Collaboration"] as const;

const TASK_STATUSES = ["Not Started", "In Progress", "In Review", "Blocked", "Done"] as const;
const TASK_PRIORITIES = ["P0", "P1", "P2"] as const;
const TASK_ASSIGNEES = [
  "demo@webarena.local",
  "alex@webarena.local",
  "alice@webarena.local",
  "mina@webarena.local",
] as const;
const TASK_PROJECTS = ["Mobile Onboarding Revamp", "Billing Reliability", "Comment Platform Upgrade"] as const;

export const TRAVEL_DESTINATIONS = [
  "Busan",
  "Gyeongju",
  "Sapporo",
  "Jeju",
  "Osaka",
  "Tokyo",
  "Kyoto",
  "Fukuoka",
  "Taipei",
  "Hanoi",
  "Bali",
  "Singapore",
] as const;

export const TRAVEL_CATEGORIES = [
  "Transport",
  "Accommodation",
  "Food",
  "Activities",
  "Shopping",
  "Local Transit",
] as const;

type TravelDestination = (typeof TRAVEL_DESTINATIONS)[number];
type TravelCategory = (typeof TRAVEL_CATEGORIES)[number];

type PageBase = {
  id: string;
  workspaceId: string;
  createdById: string;
  title: string;
  type: "document";
  accessLevel: "workspace";
  icon: string | null;
  parentPageId: string | null;
};

type BlockSeed = {
  id: string;
  pageId: string;
  type:
    | "paragraph"
    | "heading_1"
    | "heading_2"
    | "heading_3"
    | "bulleted_list_item"
    | "numbered_list_item"
    | "todo"
    | "toggle"
    | "quote"
    | "divider"
    | "callout"
    | "code";
  contentText: string;
  position: number;
  checked?: boolean;
  propsJson?: unknown;
};

type DatabaseRowSeed = {
  id: string;
  databaseId: string;
  title: string;
  position: number;
};

type DatabaseCellSeed = {
  id: string;
  rowId: string;
  propertyId: string;
  valueJson: unknown;
};

type WorkspaceTabSeed = {
  id: string;
  membershipId: string;
  pageId: string;
  position: number;
};

type CommentSeed = {
  id: string;
  pageId: string;
  authorId: string;
  parentCommentId?: string | null;
  content: string;
};

type CommentMentionSeed = {
  id: string;
  commentId: string;
  userId: string;
};

type ShareLinkSeed = {
  id: string;
  token: string;
  pageId: string;
  createdById: string;
  isActive: boolean;
};

type PagePermissionSeed = {
  id: string;
  pageId: string;
  userId: string;
  role: "editor" | "commenter" | "viewer";
};

type AttachmentSeed = {
  id: string;
  pageId: string;
  uploadedById: string;
  fileName: string;
  fileUrl: string;
  mimeType: string;
  sizeBytes: number;
};

function offsetDate(days: number): string {
  const value = new Date(SEED_DATE);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function money(value: number): string {
  return `$${value.toLocaleString("en-US")}`;
}

function pad(index: number): string {
  return String(index).padStart(3, "0");
}

function pick<T>(items: readonly T[], index: number): T {
  return items[index % items.length];
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

// =====================================================================
// TRAVEL: trip purposes per destination (db_travel) + budget items
// =====================================================================

type TripPurpose = {
  suffix: string;
  status: "Planning" | "Booked" | "Complete";
  budget: number;
  monthOffset: number; // days from SEED_DATE
};

const TRIP_PURPOSES: Record<TravelDestination, TripPurpose[]> = {
  Busan: [
    { suffix: "Summer beach getaway", status: "Booked", budget: 1200, monthOffset: 198 },
    { suffix: "Cafe and food weekend", status: "Planning", budget: 540, monthOffset: 90 },
    { suffix: "Photography walk along the coast", status: "Planning", budget: 720, monthOffset: 285 },
  ],
  Gyeongju: [
    { suffix: "Heritage day-trip", status: "Planning", budget: 350, monthOffset: 201 },
    { suffix: "Cherry blossom slow weekend", status: "Booked", budget: 620, monthOffset: 95 },
  ],
  Sapporo: [
    { suffix: "Snow Festival winter trip", status: "Planning", budget: 2100, monthOffset: 395 },
    { suffix: "Summer outdoor circuit (Otaru + Furano)", status: "Planning", budget: 1850, monthOffset: 215 },
    { suffix: "Family reunion holiday week", status: "Planning", budget: 2650, monthOffset: 360 },
  ],
  Jeju: [
    { suffix: "West coast road trip", status: "Complete", budget: 980, monthOffset: 75 },
    { suffix: "Olle hiking week", status: "Planning", budget: 1150, monthOffset: 250 },
    { suffix: "Tangerine harvest visit with parents", status: "Planning", budget: 1320, monthOffset: 320 },
  ],
  Osaka: [
    { suffix: "Food crawl long weekend", status: "Booked", budget: 1450, monthOffset: 165 },
    { suffix: "Universal Studios + Nara day trip", status: "Planning", budget: 1780, monthOffset: 240 },
  ],
  Tokyo: [
    { suffix: "Cherry blossom week", status: "Planning", budget: 2400, monthOffset: 105 },
    { suffix: "Indie bookstore + design shop weekend", status: "Planning", budget: 1850, monthOffset: 220 },
    { suffix: "Conference attendance (NeurIPS satellite)", status: "Booked", budget: 2900, monthOffset: 340 },
  ],
  Kyoto: [
    { suffix: "Temple slow-travel five days", status: "Planning", budget: 2050, monthOffset: 130 },
    { suffix: "Autumn foliage stay", status: "Planning", budget: 2200, monthOffset: 305 },
  ],
  Fukuoka: [
    { suffix: "Yatai food short break", status: "Planning", budget: 1100, monthOffset: 175 },
    { suffix: "Hot spring detour to Yufuin", status: "Planning", budget: 1480, monthOffset: 260 },
  ],
  Taipei: [
    { suffix: "Night market and tea-tasting trip", status: "Booked", budget: 1320, monthOffset: 145 },
    { suffix: "Yangmingshan hiking weekend", status: "Planning", budget: 1180, monthOffset: 280 },
  ],
  Hanoi: [
    { suffix: "Old Quarter food walk", status: "Planning", budget: 1080, monthOffset: 190 },
    { suffix: "Halong Bay overnight extension", status: "Planning", budget: 1490, monthOffset: 295 },
  ],
  Bali: [
    { suffix: "Ubud yoga retreat week", status: "Planning", budget: 1750, monthOffset: 230 },
    { suffix: "Surf and beach trip with friends", status: "Planning", budget: 2050, monthOffset: 320 },
  ],
  Singapore: [
    { suffix: "Stopover gardens + hawker tour", status: "Booked", budget: 1100, monthOffset: 158 },
    { suffix: "Family long weekend with cousins", status: "Planning", budget: 2480, monthOffset: 270 },
  ],
};

const BUDGET_ITEMS_BY_DEST_CAT: Record<TravelDestination, Record<TravelCategory, string[]>> = {
  Busan: {
    Transport: ["KTX Seoul→Busan", "Busan airport limousine bus", "Coastal train ticket bundle"],
    Accommodation: ["Haeundae Beach hotel (3 nights)", "Gwangalli ocean-view Airbnb", "Seomyeon business hotel"],
    Food: ["Jagalchi seafood dinner", "Gwangalli brewery dinner", "Jeonpo cafe street brunch"],
    Activities: ["Songdo Skywalk + cable car", "Beomeosa temple half-day", "Yongdusan Tower at night"],
    Shopping: ["Gukje Market souvenirs", "Jeonpo coffee bean haul", "Shinsegae Centum City gift run"],
    "Local Transit": ["Cashbee top-up for subway", "Beach to BIFF taxi rides", "Ferry to Yeongdo island"],
  },
  Gyeongju: {
    Transport: ["Bus from Busan to Gyeongju", "KTX Singyeongju station transfer", "Return shuttle to Pohang airport"],
    Accommodation: ["Hanok stay near Bomun Lake", "Gyeongju Hilton lake-view room", "Daereungwon-area guesthouse"],
    Food: ["Ssambap set near royal tombs", "Hwangnam-bbang pastry box", "Bomun Lake cafe dinner"],
    Activities: ["Bulguksa + Seokguram combo ticket", "Cheomseongdae night walk pass", "National Museum admission"],
    Shopping: ["Museum gift shop postcards", "Local tea blend tin", "Hanji paper bookmarks"],
    "Local Transit": ["Local bus pass for temple route", "Bicycle rental around Bomun", "Taxi backup for late returns"],
  },
  Sapporo: {
    Transport: ["Round-trip flight Tokyo→Sapporo (CTS)", "JR Hokkaido rail pass (5-day)", "Airport rail card top-up"],
    Accommodation: ["Susukino apartment (4 nights)", "Otaru ryokan side-trip (1 night)", "Furano lodge (2 nights)"],
    Food: ["Menya Saimi ramen lunch", "Sapporo beer garden dinner", "Nijo Market breakfast crawl"],
    Activities: ["Sapporo Snow Festival pass", "Otaru canal tour ticket", "Niseko ski day-pass"],
    Shopping: ["Royce chocolate gift box", "Hokkaido cheese set", "Shiroi Koibito factory souvenirs"],
    "Local Transit": ["Sapporo subway day-pass", "Otaru–Sapporo train segment", "Taxi from station after late dinner"],
  },
  Jeju: {
    Transport: ["Round-trip flight Gimpo→Jeju", "Rental car (3 days, compact)", "Airport-to-city shuttle"],
    Accommodation: ["Aewol pension (3 nights)", "Seongsan ocean-view room (1 night)", "Hyeopjae beach guesthouse"],
    Food: ["Black pork BBQ dinner", "Hallasan trail breakfast box", "Aewol cafe brunch flight"],
    Activities: ["Tangerine farm + oreum hike combo", "Manjanggul lava tube admission", "Seongsan sunrise peak entry"],
    Shopping: ["Citrus jam and tea blends", "Hallabong gift box", "Local craft market finds"],
    "Local Transit": ["Fuel for west-coast loop", "Parking at Seongsan", "Local bus to Hallasan trailhead"],
  },
  Osaka: {
    Transport: ["Direct flight Incheon→Kansai", "Haruka airport express to Namba", "ICOCA card initial top-up"],
    Accommodation: ["Namba boutique hotel (4 nights)", "Umeda business hotel (1 night)", "Tennoji guesthouse buffer"],
    Food: ["Dotonbori takoyaki + kushikatsu crawl", "Kuromon Market lunch run", "Shinsekai izakaya dinner"],
    Activities: ["Universal Studios Japan day pass", "Osaka Aquarium timed entry", "Nara Park day-trip ticket"],
    Shopping: ["Shinsaibashi kitchenware haul", "Den-Den Town stationery run", "Kuromon Market snack pack"],
    "Local Transit": ["Osaka Metro 2-day pass", "Nara Kintetsu return ticket", "Late-night taxi to hotel"],
  },
  Tokyo: {
    Transport: ["Round-trip flight Incheon→Haneda", "Skyliner from Narita", "Shinkansen day-trip to Hakone"],
    Accommodation: ["Asakusa hotel (5 nights)", "Shibuya capsule for one night", "Shinjuku conference hotel"],
    Food: ["Tsukiji breakfast sushi run", "Tonkatsu set dinner in Ueno", "Jimbocho coffee + cake stop"],
    Activities: ["TeamLab Planets timed slot", "Skytree observatory deck", "Ghibli Museum reserved entry"],
    Shopping: ["Jimbocho rare-book hunt", "Akihabara hobby shop run", "Ginza stationery and Itoya stop"],
    "Local Transit": ["Tokyo Metro 72h pass", "Yamanote loop top-up", "Late ride home after dinner in Shibuya"],
  },
  Kyoto: {
    Transport: ["Shinkansen Tokyo→Kyoto", "JR Kansai Wide pass extension", "Kyoto City bus all-day pass"],
    Accommodation: ["Machiya inn near Gion (3 nights)", "Arashiyama riverside ryokan", "Kyoto Station hotel for departure night"],
    Food: ["Kaiseki lunch reservation", "Nishiki Market tasting walk", "Arashiyama tofu set dinner"],
    Activities: ["Fushimi Inari pre-dawn walk", "Kinkakuji + Ryoanji combo", "Geisha district evening tour"],
    Shopping: ["Washi paper and incense", "Tea ware from a Gion shop", "Yatsuhashi sweets gift box"],
    "Local Transit": ["Kyoto bus pass (2-day)", "Taxi backup for Arashiyama late return", "Bicycle rental for temple loop"],
  },
  Fukuoka: {
    Transport: ["Short-haul flight Gimpo→Fukuoka", "Shinkansen detour to Yufuin", "Airport shuttle to Hakata"],
    Accommodation: ["Hakata business hotel (3 nights)", "Yufuin onsen ryokan (1 night)", "Tenjin design hotel"],
    Food: ["Yatai dinner crawl", "Tonkotsu ramen at Ichiran", "Hakata canal-side cafe lunch"],
    Activities: ["Canal City harbor walk", "Yufuin onsen day-pass", "Fukuoka Museum admission"],
    Shopping: ["Tenjin department store gifts", "Hakata-ori textile sampler", "Local pottery from Arita stop"],
    "Local Transit": ["Subway day pass", "JR Yufuin no Mori segment", "Hakata taxi short hop"],
  },
  Taipei: {
    Transport: ["Round-trip flight Incheon→Taoyuan", "Airport MRT into Taipei Main", "High-speed rail to Tainan day-trip"],
    Accommodation: ["Da'an district hotel (4 nights)", "Beitou hot-spring resort (1 night)", "Ximending design hostel"],
    Food: ["Shilin Night Market run", "Yongkang beef noodle lunch", "Din Tai Fung dinner reservation"],
    Activities: ["Beitou hot-spring entry", "Yangmingshan trail bus", "Taipei 101 observatory ticket"],
    Shopping: ["Yongkang area tea tin haul", "Eslite bookstore evening", "Pineapple cake gift boxes"],
    "Local Transit": ["EasyCard top-up for MRT", "Maokong gondola day-pass", "Late-night taxi from Shilin"],
  },
  Hanoi: {
    Transport: ["Round-trip flight Incheon→Noi Bai", "Sleeper bus to Sapa weekend extension", "Halong overnight cruise transfer"],
    Accommodation: ["Old Quarter boutique hotel (4 nights)", "Halong Bay overnight cruise cabin", "Tay Ho lakeside Airbnb"],
    Food: ["Bun cha lunch on Le Van Huu", "Egg coffee tasting flight", "Cha ca grilled fish dinner"],
    Activities: ["Water puppet show ticket", "Hanoi street-food walking tour", "Temple of Literature entry"],
    Shopping: ["Lacquerware gift set", "Handwritten travel notebook", "Silk scarves from Hang Gai"],
    "Local Transit": ["Grab rides across Old Quarter", "Airport transfer Grab Premium", "Local bus to West Lake"],
  },
  Bali: {
    Transport: ["Round-trip flight Incheon→Denpasar", "Private driver airport transfer", "Inter-island ferry to Nusa Penida"],
    Accommodation: ["Ubud villa (4 nights)", "Canggu surf-house (3 nights)", "Seminyak beach hotel last night"],
    Food: ["Babi guling lunch", "Ubud rice-terrace dinner", "Seminyak sunset cocktails"],
    Activities: ["Tegallalang rice terrace walk", "Tirta Empul temple ritual", "Mount Batur sunrise hike"],
    Shopping: ["Ubud market textiles", "Incense and crafts run", "Seminyak boutique resort wear"],
    "Local Transit": ["Private driver day rate", "Scooter rental Canggu", "Ride-hailing to Seminyak"],
  },
  Singapore: {
    Transport: ["Round-trip flight Incheon→Changi", "Changi airport SMRT card", "MRT day-pass top-up"],
    Accommodation: ["Tanjong Pagar hotel (3 nights)", "Sentosa resort weekend stay", "Bugis design hostel buffer"],
    Food: ["Hawker chicken rice at Maxwell", "Lau Pa Sat satay dinner", "Tiong Bahru cafe brunch"],
    Activities: ["Gardens by the Bay admission", "Universal Studios Sentosa", "ArtScience Museum exhibition"],
    Shopping: ["Orchard Road bookshop run", "Mustafa Centre gift haul", "Tiong Bahru market pantry finds"],
    "Local Transit": ["EZ-Link card MRT use", "Sentosa cable-car day-pass", "Cab to Changi early flight"],
  },
};

function buildTravelRows(): { rows: DatabaseRowSeed[]; cells: DatabaseCellSeed[] } {
  const rows: DatabaseRowSeed[] = [];
  const cells: DatabaseCellSeed[] = [];

  let position = 0;
  let rowIndex = 0;
  for (const destination of TRAVEL_DESTINATIONS) {
    for (const purpose of TRIP_PURPOSES[destination]) {
      rowIndex += 1;
      const rowId = `row_travel_scale_${pad(rowIndex)}`;
      const title = `${destination} – ${purpose.suffix}`;
      rows.push({ id: rowId, databaseId: "db_travel", title, position });
      cells.push(
        { id: `cell_${rowId}_status`, rowId, propertyId: "prop_travel_status", valueJson: purpose.status },
        { id: `cell_${rowId}_budget`, rowId, propertyId: "prop_travel_budget", valueJson: money(purpose.budget) },
        { id: `cell_${rowId}_date`, rowId, propertyId: "prop_travel_date", valueJson: offsetDate(purpose.monthOffset) },
      );
      position += 1;
    }
  }
  return { rows, cells };
}

function categoryAmount(destination: TravelDestination, category: TravelCategory, variantIndex: number): number {
  const base: Record<TravelDestination, number> = {
    Busan: 90,
    Gyeongju: 60,
    Sapporo: 180,
    Jeju: 120,
    Osaka: 160,
    Tokyo: 220,
    Kyoto: 175,
    Fukuoka: 130,
    Taipei: 135,
    Hanoi: 95,
    Bali: 200,
    Singapore: 230,
  };
  const categoryFactor: Record<TravelCategory, number> = {
    Transport: 2.4,
    Accommodation: 4.6,
    Food: 1.3,
    Activities: 1.6,
    Shopping: 0.9,
    "Local Transit": 0.4,
  };
  const raw = base[destination] * categoryFactor[category] + variantIndex * 17;
  return Math.round(raw / 5) * 5;
}

function buildTravelBudgetRows(): { rows: DatabaseRowSeed[]; cells: DatabaseCellSeed[] } {
  const rows: DatabaseRowSeed[] = [];
  const cells: DatabaseCellSeed[] = [];

  let position = 10;
  let rowIndex = 0;
  for (const destination of TRAVEL_DESTINATIONS) {
    const itemsByCat = BUDGET_ITEMS_BY_DEST_CAT[destination];
    for (const category of TRAVEL_CATEGORIES) {
      const items = itemsByCat[category];
      for (let variant = 0; variant < items.length; variant += 1) {
        rowIndex += 1;
        const rowId = `row_budget_scale_${pad(rowIndex)}`;
        const title = items[variant];
        const amountValue = categoryAmount(destination, category, variant);
        const paid = (rowIndex % 5) % 4 !== 0;

        rows.push({ id: rowId, databaseId: "db_travel_budget", title, position });
        cells.push(
          { id: `cell_${rowId}_dest`, rowId, propertyId: "prop_budget_destination", valueJson: destination },
          { id: `cell_${rowId}_cat`, rowId, propertyId: "prop_budget_category", valueJson: category },
          { id: `cell_${rowId}_amt`, rowId, propertyId: "prop_budget_amount", valueJson: money(amountValue) },
          { id: `cell_${rowId}_paid`, rowId, propertyId: "prop_budget_paid", valueJson: paid },
        );
        position += 1;
      }
    }
  }
  return { rows, cells };
}

// =====================================================================
// PROJECTS / TASKS scaled rows (kept thematic but more realistic)
// =====================================================================

const PROJECT_TITLES = [
  "Mobile activation copy refresh for the EMEA admin cohort",
  "Enterprise invite flow cleanup before the North America renewal cycle",
  "Workspace template gallery launch for first-time admins",
  "Comment permission rollout for shared workspaces",
  "Audit log export reliability hardening",
  "Billing alert delivery latency reduction",
  "Search index lag mitigation after large workspace imports",
  "Notification batching to reduce inbox fatigue",
  "Mobile push reliability program for Android",
  "iOS deep-link routing parity with web",
  "Self-serve trial extension flow",
  "Partner-led onboarding portal beta",
  "API rate limit clarification across docs and SDKs",
  "Data residency controls for EU customers",
  "Bulk seat provisioning for large organizations",
  "Workspace cleanup tooling for archived members",
  "Incident response runbook automation",
  "Cross-workspace mention permission redesign",
  "Public roadmap publishing automation",
  "Customer education hub IA refresh",
];

function buildProjectRows(): { rows: DatabaseRowSeed[]; cells: DatabaseCellSeed[] } {
  const rows: DatabaseRowSeed[] = [];
  const cells: DatabaseCellSeed[] = [];

  for (let index = 0; index < PROJECT_TITLES.length; index += 1) {
    const title = PROJECT_TITLES[index];
    const rowId = `row_proj_scale_${pad(index + 1)}`;
    const status = pick(PROJECT_STATUSES, index + 1);
    const owner = pick(PROJECT_OWNERS, index);
    const firstArea = pick(PROJECT_AREAS, index);
    const secondArea = pick(PROJECT_AREAS, index + 2);

    rows.push({ id: rowId, databaseId: "db_projects", title, position: index + 3 });
    cells.push(
      { id: `cell_${rowId}_status`, rowId, propertyId: "prop_project_status", valueJson: status },
      { id: `cell_${rowId}_owner`, rowId, propertyId: "prop_project_owner", valueJson: owner },
      {
        id: `cell_${rowId}_area`,
        rowId,
        propertyId: "prop_project_area",
        valueJson: index % 2 === 0 ? [firstArea, secondArea] : [firstArea],
      },
      { id: `cell_${rowId}_ship`, rowId, propertyId: "prop_project_ship", valueJson: offsetDate(40 + index * 7) },
    );
  }
  return { rows, cells };
}

const TASK_TITLES = [
  "Draft EMEA admin onboarding email sequence",
  "Review enterprise invite copy with legal",
  "Validate billing alert thresholds against staging traffic",
  "Prepare QA sign-off note for the billing release",
  "Triage open audit log export bug reports",
  "Confirm push reliability dashboards still work after migration",
  "Refactor deep-link router shared between iOS and web",
  "Document Retry-After behavior in API docs",
  "Update support macros for the new comment permission UI",
  "Cut 1.42 mobile release branch",
  "Verify in-product checklist copy with content design",
  "Audit notification batching defaults for new workspaces",
  "Coordinate weekly status recap for the admin program",
  "Open follow-up tickets from the billing postmortem",
  "Pair with reliability on retry storm playbook",
  "Add screenshot pass to the trial extension docs",
  "Schedule customer council call about audit exports",
  "Compile benchmarks for the search index lag fix",
  "Draft FAQ for cross-workspace mentions",
  "Sync with partner team on portal beta gating",
];

function buildTaskRows(): { rows: DatabaseRowSeed[]; cells: DatabaseCellSeed[] } {
  const rows: DatabaseRowSeed[] = [];
  const cells: DatabaseCellSeed[] = [];

  for (let index = 0; index < TASK_TITLES.length; index += 1) {
    const rowId = `row_task_scale_${pad(index + 1)}`;
    const title = TASK_TITLES[index];
    const status = pick(TASK_STATUSES, index + 2);
    const priority = pick(TASK_PRIORITIES, index + 1);
    const assignee = pick(TASK_ASSIGNEES, index);
    const project = pick(TASK_PROJECTS, index);
    const done = status === "Done";

    rows.push({ id: rowId, databaseId: "db_task_tracker", title, position: index + 7 });
    cells.push(
      { id: `cell_${rowId}_status`, rowId, propertyId: "prop_status", valueJson: status },
      { id: `cell_${rowId}_priority`, rowId, propertyId: "prop_priority", valueJson: priority },
      { id: `cell_${rowId}_assignee`, rowId, propertyId: "prop_assignee", valueJson: [assignee] },
      { id: `cell_${rowId}_project`, rowId, propertyId: "prop_task_project", valueJson: project },
      { id: `cell_${rowId}_done`, rowId, propertyId: "prop_done", valueJson: done },
      { id: `cell_${rowId}_due`, rowId, propertyId: "prop_due", valueJson: offsetDate(20 + index * 4) },
    );
  }
  return { rows, cells };
}

// =====================================================================
// PAGE BUILDER (block factory) — accepts an array of block specs
// =====================================================================

type BlockKind =
  | "h1"
  | "h2"
  | "h3"
  | "p"
  | "ul"
  | "ol"
  | "todo"
  | "todo_done"
  | "toggle"
  | "quote"
  | "callout"
  | "divider";

type BlockInput = { k: BlockKind; t?: string };

function blocksFor(pageId: string, items: BlockInput[]): BlockSeed[] {
  const out: BlockSeed[] = [];
  for (let i = 0; i < items.length; i += 1) {
    const item = items[i];
    const id = `${pageId}_b_${pad(i + 1)}`;
    const text = item.t ?? "";
    if (item.k === "h1") {
      out.push({ id, pageId, type: "heading_1", contentText: text, position: i });
    } else if (item.k === "h2") {
      out.push({ id, pageId, type: "heading_2", contentText: text, position: i });
    } else if (item.k === "h3") {
      out.push({ id, pageId, type: "heading_3", contentText: text, position: i });
    } else if (item.k === "p") {
      out.push({ id, pageId, type: "paragraph", contentText: text, position: i });
    } else if (item.k === "ul") {
      out.push({ id, pageId, type: "bulleted_list_item", contentText: text, position: i });
    } else if (item.k === "ol") {
      out.push({ id, pageId, type: "numbered_list_item", contentText: text, position: i });
    } else if (item.k === "todo") {
      out.push({ id, pageId, type: "todo", contentText: text, checked: false, position: i });
    } else if (item.k === "todo_done") {
      out.push({ id, pageId, type: "todo", contentText: text, checked: true, position: i });
    } else if (item.k === "toggle") {
      out.push({ id, pageId, type: "toggle", contentText: text, position: i, propsJson: { collapsed: false } });
    } else if (item.k === "quote") {
      out.push({ id, pageId, type: "quote", contentText: text, position: i });
    } else if (item.k === "callout") {
      out.push({ id, pageId, type: "callout", contentText: text, position: i, propsJson: { emoji: "💡" } });
    } else if (item.k === "divider") {
      out.push({ id, pageId, type: "divider", contentText: "", position: i });
    }
  }
  return out;
}

// =====================================================================
// RESEARCH LAB — paper notes, lab meetings, reading group, datasets,
// project proposals, and public-domain reading shelf
// =====================================================================

type PageWithBlocks = { page: PageBase; blocks: BlockSeed[] };

function paperPage(args: {
  id: string;
  title: string;
  citation: string;
  motivation: string;
  method: string[];
  results: string[];
  discussion: string;
  todos: { text: string; done?: boolean }[];
  parentPageId: string;
  icon: string;
}): PageWithBlocks {
  const page: PageBase = {
    id: args.id,
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: args.title,
    type: "document",
    accessLevel: "workspace",
    icon: args.icon,
    parentPageId: args.parentPageId,
  };
  const blocks = blocksFor(args.id, [
    { k: "h1", t: args.title },
    { k: "p", t: args.citation },
    { k: "callout", t: "Reading status: notes are working drafts. Quotes are paraphrased unless otherwise marked." },
    { k: "h2", t: "Motivation" },
    { k: "p", t: args.motivation },
    { k: "h2", t: "Method" },
    ...args.method.map((m) => ({ k: "ul" as const, t: m })),
    { k: "h2", t: "Key results" },
    ...args.results.map((r) => ({ k: "ol" as const, t: r })),
    { k: "h2", t: "Discussion and open questions" },
    { k: "p", t: args.discussion },
    { k: "h2", t: "Follow-up reading and tasks" },
    ...args.todos.map((t) => ({ k: t.done ? ("todo_done" as const) : ("todo" as const), t: t.text })),
  ]);
  return { page, blocks };
}

function labMeetingPage(args: {
  id: string;
  date: string;
  attendees: string[];
  agenda: string[];
  discussion: string[];
  decisions: string[];
  followups: { text: string; owner: string; due: string }[];
}): PageWithBlocks {
  const page: PageBase = {
    id: args.id,
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: `Lab Meeting – ${args.date}`,
    type: "document",
    accessLevel: "workspace",
    icon: "📓",
    parentPageId: "page_lab_meetings",
  };
  const blocks = blocksFor(args.id, [
    { k: "h1", t: `Lab Meeting – ${args.date}` },
    { k: "p", t: `Attendees: ${args.attendees.join(", ")}` },
    { k: "h2", t: "Agenda" },
    ...args.agenda.map((a) => ({ k: "ol" as const, t: a })),
    { k: "h2", t: "Discussion" },
    ...args.discussion.map((d) => ({ k: "p" as const, t: d })),
    { k: "h2", t: "Decisions" },
    ...args.decisions.map((d) => ({ k: "ul" as const, t: d })),
    { k: "h2", t: "Follow-ups" },
    ...args.followups.map((f) => ({
      k: "todo" as const,
      t: `${f.text} — owner: ${f.owner}, due ${f.due}`,
    })),
  ]);
  return { page, blocks };
}

function readingGroupPage(args: {
  id: string;
  date: string;
  paperTitle: string;
  paperAuthors: string;
  presenter: string;
  attendees: string[];
  highlights: string[];
  questions: string[];
  next: string;
}): PageWithBlocks {
  const page: PageBase = {
    id: args.id,
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: `Reading Group – ${args.date}`,
    type: "document",
    accessLevel: "workspace",
    icon: "📖",
    parentPageId: "page_reading_group",
  };
  const blocks = blocksFor(args.id, [
    { k: "h1", t: `Reading Group – ${args.date}` },
    { k: "p", t: `Paper: ${args.paperTitle}` },
    { k: "p", t: `Authors: ${args.paperAuthors}` },
    { k: "p", t: `Presenter: ${args.presenter}` },
    { k: "p", t: `Attendees: ${args.attendees.join(", ")}` },
    { k: "h2", t: "Highlights" },
    ...args.highlights.map((h) => ({ k: "ul" as const, t: h })),
    { k: "h2", t: "Open questions" },
    ...args.questions.map((q) => ({ k: "ol" as const, t: q })),
    { k: "h2", t: "Next session" },
    { k: "p", t: args.next },
  ]);
  return { page, blocks };
}

function buildResearchLabPages(): PageWithBlocks[] {
  const out: PageWithBlocks[] = [];

  // page_lab_notes is created in seed.ts; we replace its blocks via a content patch
  // but to keep the structure clean we leave the original blocks in seed.ts and
  // contribute new blocks directly here under a different id. Decision: we don't
  // touch page_lab_notes blocks.

  // ============ 1. Research Library + paper reading notes ============
  const libPage: PageBase = {
    id: "page_research_library",
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: "Research Library",
    type: "document",
    accessLevel: "workspace",
    icon: "🧠",
    parentPageId: null,
  };
  const libBlocks = blocksFor(libPage.id, [
    { k: "h1", t: "Research Library" },
    {
      k: "p",
      t: "A working bibliography for the lab. Each child page is a personal reading note: motivation, method, key results, and follow-ups. We prefer paraphrased notes over copy-pasted abstracts so we can come back later and remember why a paper mattered.",
    },
    { k: "h2", t: "How we use this library" },
    { k: "ul", t: "One note per paper. Reading notes are personal — sign your section if multiple people contribute." },
    { k: "ul", t: "Use the discussion section to record what we still doubt or want to test." },
    { k: "ul", t: "Move papers we present to reading group into the Reading Group log when done." },
    { k: "h2", t: "Active reading list" },
    { k: "ul", t: "Vaswani et al., 2017 — Attention Is All You Need" },
    { k: "ul", t: "Devlin et al., 2019 — BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding" },
    { k: "ul", t: "He et al., 2016 — Deep Residual Learning for Image Recognition (ResNet)" },
    { k: "ul", t: "Krizhevsky et al., 2012 — ImageNet Classification with Deep Convolutional Neural Networks (AlexNet)" },
    { k: "ul", t: "Mikolov et al., 2013 — Efficient Estimation of Word Representations in Vector Space (word2vec)" },
    { k: "h2", t: "Conventions" },
    { k: "p", t: "Citations follow author-year. We tag papers loosely by topic in the page sidebar; the canonical metadata lives in the BibTeX file in the lab repo." },
    { k: "callout", t: "When you finish a paper, add a one-line summary to the reading list above so the front page stays scannable." },
  ]);
  out.push({ page: libPage, blocks: libBlocks });

  out.push(paperPage({
    id: "page_paper_attention",
    title: "Attention Is All You Need (Vaswani et al., 2017)",
    citation: "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention Is All You Need. NeurIPS.",
    motivation:
      "Recurrence in seq2seq models forces sequential computation along the time axis, which makes long-range dependencies expensive to learn and hard to parallelize on modern hardware. The paper asks whether we can replace recurrence and convolution entirely with attention.",
    method: [
      "Encoder–decoder built only from stacked self-attention and position-wise feed-forward layers; no recurrence or convolutions in the main blocks.",
      "Scaled dot-product attention: softmax(Q Kᵀ / √d_k) V, with multi-head attention running several attention computations in parallel and concatenating the outputs.",
      "Sinusoidal positional encodings added to input embeddings to inject token position information.",
      "Residual connections and layer normalization around every sub-layer; learning rate warmup with inverse-square-root decay.",
    ],
    results: [
      "Sets a new state of the art on WMT 2014 English-to-German (28.4 BLEU) and English-to-French (41.8 BLEU) at the time of publication.",
      "Trains noticeably faster than the strongest recurrent baselines because every position can attend in parallel.",
      "Multi-head attention helps the model jointly attend to information from different representation subspaces.",
    ],
    discussion:
      "The paper's biggest practical contribution is removing the bottleneck of sequential computation, which makes hardware utilization much better. Open questions for the lab: how does the architecture behave when sequence length grows past the training distribution, and what is the right way to ablate position encoding choices for our retrieval setup?",
    todos: [
      { text: "Skim the follow-up papers on relative position encodings (Shaw et al., RoPE)." },
      { text: "Re-derive the scaling factor 1/√d_k and write it up for the next reading group." },
      { text: "Compare our internal small-model attention head counts against the paper's recommendations.", done: true },
    ],
    parentPageId: "page_research_library",
    icon: "📄",
  }));

  out.push(paperPage({
    id: "page_paper_bert",
    title: "BERT (Devlin et al., 2019)",
    citation: "Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. NAACL.",
    motivation:
      "Pre-training contextual representations had previously been left-to-right or shallow bidirectional. BERT argues that masked language modeling lets a Transformer encoder learn truly bidirectional context, which transfers well to many downstream tasks with minimal architecture changes.",
    method: [
      "Pre-training on the concatenation of BooksCorpus and English Wikipedia (about 3.3B tokens).",
      "Masked Language Modeling: replace 15% of input tokens with [MASK]/random/unchanged and predict the originals.",
      "Next Sentence Prediction: binary classification whether sentence B follows sentence A in the source corpus.",
      "Fine-tuning: add a small task-specific head and update all parameters end-to-end on the target dataset.",
    ],
    results: [
      "Sets state of the art on GLUE, SQuAD v1.1 and v2.0, and SWAG at publication time.",
      "BERT-Large outperforms BERT-Base by a meaningful margin across nearly all benchmarks, especially on small datasets.",
      "Demonstrates that bidirectional pre-training transfers across a wide span of NLU tasks.",
    ],
    discussion:
      "Subsequent work (RoBERTa, ALBERT, T5) shows that NSP is mostly unhelpful and that pre-training data, batch size, and training length matter more than the original loss design. For our internal use we should treat NSP as optional and benchmark MLM-only carefully.",
    todos: [
      { text: "Reproduce BERT-Base fine-tuning on SST-2 to recalibrate our pipeline." },
      { text: "Compare RoBERTa training recipe notes against our current schedule." },
      { text: "Draft a one-pager on why we keep MLM but drop NSP for the in-house encoder." },
    ],
    parentPageId: "page_research_library",
    icon: "📄",
  }));

  out.push(paperPage({
    id: "page_paper_resnet",
    title: "ResNet (He et al., 2016)",
    citation: "He, K., Zhang, X., Ren, S., & Sun, J. (2016). Deep Residual Learning for Image Recognition. CVPR.",
    motivation:
      "Naively deepening CNNs degrades training and test accuracy even on the training set, which is not just an overfitting issue. The paper proposes that learning residual functions F(x) = H(x) - x is easier than learning H(x) directly.",
    method: [
      "Identity shortcut connections that skip one or more layers and are added to the layer outputs.",
      "Bottleneck blocks (1x1, 3x3, 1x1) used to scale to ResNet-50/101/152 with manageable parameter count.",
      "Batch normalization and ReLU activations after each convolution.",
    ],
    results: [
      "Wins ILSVRC 2015 classification with a 152-layer network at 3.57% top-5 error.",
      "Strong gains on COCO detection and segmentation when used as a backbone.",
      "Demonstrates that depth helps once optimization is no longer bottlenecked by signal degradation.",
    ],
    discussion:
      "The residual idea is now table stakes in deep architectures, including Transformers (every block is a residual block). Open question for our work: how does block placement of residuals interact with our custom layer norm placement?",
    todos: [
      { text: "Trace which residual paths in the in-house vision model differ from the original ResNet block.", done: true },
      { text: "Re-read pre-activation ResNet (He et al., 2016b) to confirm the BN/ReLU ordering rationale." },
    ],
    parentPageId: "page_research_library",
    icon: "📄",
  }));

  out.push(paperPage({
    id: "page_paper_alexnet",
    title: "AlexNet (Krizhevsky et al., 2012)",
    citation: "Krizhevsky, A., Sutskever, I., & Hinton, G. E. (2012). ImageNet Classification with Deep Convolutional Neural Networks. NeurIPS.",
    motivation:
      "Demonstrate that a deep convolutional network trained on enough data and GPU hardware can dramatically outperform classical computer vision pipelines on large-scale image classification.",
    method: [
      "Eight-layer CNN (five convolutional, three fully connected) trained on ImageNet.",
      "ReLU activations to speed up training relative to tanh/sigmoid.",
      "Local response normalization, overlapping max pooling, and dropout in the fully connected layers.",
      "Data augmentation through random crops, horizontal flips, and PCA-based color jitter.",
    ],
    results: [
      "Top-5 error of 15.3% on ILSVRC-2012, a large gap over the second-best entry.",
      "Establishes ReLU + dropout + GPU training as a default recipe for the next several years.",
    ],
    discussion:
      "Many AlexNet design choices have been replaced (LRN out, batch norm in; manual augmentation replaced by AutoAugment; dropout less dominant). What persists is the lesson that scale + simple regularization + hardware acceleration enables surprisingly deep models.",
    todos: [
      { text: "Pull the AlexNet weights through our visualization toolkit to compare with our internal vision model heatmaps." },
    ],
    parentPageId: "page_research_library",
    icon: "📄",
  }));

  out.push(paperPage({
    id: "page_paper_word2vec",
    title: "word2vec (Mikolov et al., 2013)",
    citation: "Mikolov, T., Chen, K., Corrado, G., & Dean, J. (2013). Efficient Estimation of Word Representations in Vector Space.",
    motivation:
      "Earlier neural language models were slow to train. word2vec proposes much shallower architectures (CBOW and Skip-gram) that scale to billions of words and produce surprisingly useful word embeddings.",
    method: [
      "Skip-gram: predict surrounding context words from a center word.",
      "CBOW: predict the center word from a small surrounding context.",
      "Hierarchical softmax or negative sampling instead of full softmax for tractable training.",
      "Subsampling of frequent words to reduce noise from common tokens.",
    ],
    results: [
      "Embeddings exhibit linear relationships such as king − man + woman ≈ queen on analogy benchmarks.",
      "Demonstrates effective training on corpora at the scale of 1.6B words on a single machine.",
    ],
    discussion:
      "The vector arithmetic story has been overstated by popular write-ups; analogy success is fragile and dataset dependent. Still, word2vec set the stage for treating embeddings as a first-class artifact, which leads directly to GloVe, fastText, and contextual embeddings.",
    todos: [
      { text: "Skim the GloVe paper for matrix-factorization framing." },
      { text: "Decide whether our internal lookup-table baseline still benefits from word2vec init." },
    ],
    parentPageId: "page_research_library",
    icon: "📄",
  }));

  // ============ 2. Reading group ============
  const rgHub: PageBase = {
    id: "page_reading_group",
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: "Reading Group",
    type: "document",
    accessLevel: "workspace",
    icon: "📖",
    parentPageId: null,
  };
  const rgHubBlocks = blocksFor(rgHub.id, [
    { k: "h1", t: "Reading Group" },
    { k: "p", t: "Bi-weekly reading group on representation learning, language models, and adjacent topics. We rotate presenters and post notes the same week." },
    { k: "h2", t: "Logistics" },
    { k: "ul", t: "Cadence: every other Saturday, 14:00 KST." },
    { k: "ul", t: "Each session covers one paper. The presenter prepares 25 minutes of notes; we discuss for the rest of the hour." },
    { k: "ul", t: "Notes go under the dated child pages of this hub. Tag open questions so they surface when we revisit topics." },
    { k: "h2", t: "Upcoming sessions" },
    { k: "ol", t: "2026-05-02 — Mixture-of-Experts language modeling, presenter: Demo." },
    { k: "ol", t: "2026-05-16 — Retrieval-augmented generation evaluations, presenter: Alex." },
    { k: "ol", t: "2026-05-30 — Long-context attention variants, presenter: Alice." },
  ]);
  out.push({ page: rgHub, blocks: rgHubBlocks });

  out.push(readingGroupPage({
    id: "page_reading_group_2026_03_14",
    date: "2026-03-14",
    paperTitle: "Attention Is All You Need (Vaswani et al., 2017)",
    paperAuthors: "A. Vaswani, N. Shazeer, N. Parmar, J. Uszkoreit, L. Jones, A. N. Gomez, Ł. Kaiser, I. Polosukhin",
    presenter: "Demo",
    attendees: ["Demo", "Alex", "Alice", "Mina"],
    highlights: [
      "Why scaled dot-product instead of additive attention: matmul saturates GPU compute and the √d_k scaling keeps softmax gradients well-conditioned.",
      "Multi-head attention is interpretable as parallel projections into different subspaces; each head can focus on a different relation.",
      "Positional encoding is sinusoidal, but later work shows learned encodings or relative encodings are competitive.",
    ],
    questions: [
      "How does encoder/decoder cross-attention behave when target sequences are much shorter than source?",
      "What is the right ablation order for head count vs head dimension on our internal small models?",
      "How does the paper's masking interact with batched decoding in inference time?",
    ],
    next: "Mina to lead a session on RoPE and ALiBi as alternatives to sinusoidal positional encodings.",
  }));

  out.push(readingGroupPage({
    id: "page_reading_group_2026_04_18",
    date: "2026-04-18",
    paperTitle: "BERT (Devlin et al., 2019)",
    paperAuthors: "J. Devlin, M.-W. Chang, K. Lee, K. Toutanova",
    presenter: "Alice",
    attendees: ["Demo", "Alex", "Alice"],
    highlights: [
      "MLM forces the model to use bidirectional context but introduces a discrepancy between training (with [MASK]) and downstream use (no [MASK]).",
      "The 80/10/10 masking trick (mask/random/unchanged) is a regularizer against this train/test gap.",
      "RoBERTa later argues that NSP is unnecessary and that data + length + batch size do most of the work.",
    ],
    questions: [
      "Should our in-house pre-training drop NSP entirely?",
      "Is whole-word masking worth the bookkeeping for our tokenizer?",
      "How sensitive is downstream fine-tuning to the LR warmup schedule?",
    ],
    next: "Alex to summarize RoBERTa's training-recipe ablations and bring a head-to-head plot.",
  }));

  // ============ 3. Lab meetings ============
  const lmHub: PageBase = {
    id: "page_lab_meetings",
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: "Lab Meetings",
    type: "document",
    accessLevel: "workspace",
    icon: "📓",
    parentPageId: null,
  };
  const lmHubBlocks = blocksFor(lmHub.id, [
    { k: "h1", t: "Lab Meetings" },
    { k: "p", t: "Weekly lab status meeting. Notes are kept as dated child pages so we can search for past decisions and follow-ups." },
    { k: "h2", t: "Standing agenda" },
    { k: "ol", t: "Round-robin updates: blocked / making progress / shipped." },
    { k: "ol", t: "Cluster status (queue depth, broken nodes, scheduled maintenance)." },
    { k: "ol", t: "Paper or experiment deep-dive (rotates)." },
    { k: "ol", t: "Decisions and follow-ups." },
    { k: "h2", t: "Decision log conventions" },
    { k: "ul", t: "Every decision gets a one-line summary plus the meeting it came from." },
    { k: "ul", t: "Follow-ups always have an owner and a due date — even if it's vague (\"end of next week\")." },
  ]);
  out.push({ page: lmHub, blocks: lmHubBlocks });

  out.push(labMeetingPage({
    id: "page_lab_meeting_2026_04_03",
    date: "2026-04-03",
    attendees: ["Demo (chair)", "Alex", "Alice", "Mina"],
    agenda: [
      "Round-robin status",
      "Cluster availability for the long-context experiment",
      "Reading group rotation for May",
      "Decisions and follow-ups",
    ],
    discussion: [
      "Alex reports that the long-context attention prototype is stable up to 16k tokens but starts to lose the needle-in-a-haystack signal past 24k. The team agrees that the next ablation should isolate position encoding from attention pattern.",
      "Mina raises the cluster scheduling issue: the shared queue stalls multi-node jobs longer than 12 hours. Demo will follow up with the platform team about reserving nodes for our largest runs.",
      "Alice proposes a small detour to evaluate retrieval-augmented baselines on the same long-context tasks for next reading group.",
    ],
    decisions: [
      "Run the long-context ablation with RoPE-vs-ALiBi as the only varying factor; Alex owns it.",
      "Reserve a 4-node block on Saturday and Sunday for the multi-day training run.",
      "Add retrieval-augmented baseline notes to the May 16 reading group.",
    ],
    followups: [
      { text: "Reach out to platform team about cluster reservation", owner: "Demo", due: "2026-04-08" },
      { text: "Share long-context ablation plan in the lab channel", owner: "Alex", due: "2026-04-10" },
      { text: "Compile RAG baseline numbers", owner: "Alice", due: "2026-04-15" },
    ],
  }));

  out.push(labMeetingPage({
    id: "page_lab_meeting_2026_04_17",
    date: "2026-04-17",
    attendees: ["Demo (chair)", "Alex", "Alice", "Mina"],
    agenda: [
      "Round-robin status",
      "Long-context ablation results",
      "Submission planning for the August deadline",
      "Decisions and follow-ups",
    ],
    discussion: [
      "Alex shows the RoPE-vs-ALiBi ablation: RoPE matches ALiBi up to 16k; ALiBi degrades less past 32k but uses different training compute. The group agrees the ablation is informative but not yet conclusive.",
      "Mina has a working data pipeline for the synthetic long-document task; she will present the data design at next week's reading group.",
      "Demo flags that the conference deadline is August 1 and that we should freeze the experimental scope by mid-June.",
    ],
    decisions: [
      "Re-run the RoPE-vs-ALiBi ablation at matched compute and document the protocol.",
      "Set internal scope-freeze date to 2026-06-15.",
      "Mina will lead the synthetic data design write-up.",
    ],
    followups: [
      { text: "Re-run RoPE-vs-ALiBi at matched compute", owner: "Alex", due: "2026-04-30" },
      { text: "Draft synthetic data design doc", owner: "Mina", due: "2026-04-29" },
      { text: "Circulate scope-freeze checklist", owner: "Demo", due: "2026-05-15" },
    ],
  }));

  out.push(labMeetingPage({
    id: "page_lab_meeting_2026_05_01",
    date: "2026-05-01",
    attendees: ["Demo (chair)", "Alex", "Alice"],
    agenda: [
      "Mina out today",
      "Matched-compute ablation results",
      "Manuscript outline draft",
      "Risks for the August deadline",
    ],
    discussion: [
      "Matched-compute results land closer to the original report: ALiBi remains ~1 point ahead at 32k but the gap is narrower than first read.",
      "Alice presents the manuscript outline. The narrative will lead with the long-context evaluation methodology rather than architecture comparisons.",
      "Alex flags two risks: cluster availability in late June and reviewer pushback on synthetic-only evaluation. We sketch fallbacks for both.",
    ],
    decisions: [
      "Adopt the methodology-first manuscript outline.",
      "Prepare a real-document long-context evaluation as a complementary slice.",
      "Block out a writing sprint for the last week of June.",
    ],
    followups: [
      { text: "Source a real-document long-context dataset (think LongBench, ZeroSCROLLS)", owner: "Alex", due: "2026-05-12" },
      { text: "Draft methodology section", owner: "Alice", due: "2026-05-22" },
      { text: "Reserve cluster for writing-sprint plotting", owner: "Demo", due: "2026-06-22" },
    ],
  }));

  // ============ 4. Project proposals ============
  const ppHub: PageBase = {
    id: "page_project_proposals",
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: "Project Proposals",
    type: "document",
    accessLevel: "workspace",
    icon: "📝",
    parentPageId: null,
  };
  const ppHubBlocks = blocksFor(ppHub.id, [
    { k: "h1", t: "Project Proposals" },
    { k: "p", t: "Drafts of project proposals before they become full-blown experiments. Each proposal has motivation, hypothesis, plan, deliverables, and risks." },
    { k: "h2", t: "How to use this page" },
    { k: "ol", t: "Start a child page using the proposal template (motivation → hypothesis → plan → deliverables → risks)." },
    { k: "ol", t: "Discuss in lab meeting before any compute is reserved." },
    { k: "ol", t: "When approved, move to the experiment tracker and link from this hub." },
  ]);
  out.push({ page: ppHub, blocks: ppHubBlocks });

  out.push({
    page: {
      id: "page_proposal_efficient_lm",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "Proposal: Efficient Long-Context LM",
      type: "document",
      accessLevel: "workspace",
      icon: "🧪",
      parentPageId: "page_project_proposals",
    },
    blocks: blocksFor("page_proposal_efficient_lm", [
      { k: "h1", t: "Proposal: Efficient Long-Context LM" },
      { k: "callout", t: "Status: drafting. Target lab review: 2026-05-08." },
      { k: "h2", t: "Motivation" },
      { k: "p", t: "Existing long-context language models either pay quadratic attention costs or rely on heuristics that hurt the needle-in-a-haystack task. We want a recipe that scales to 64k tokens at training time without giving up retrieval quality past 32k." },
      { k: "h2", t: "Hypothesis" },
      { k: "p", t: "Combining ALiBi-style position bias with a small auxiliary retrieval objective during pre-training will preserve long-range recall up to 64k tokens with under 1.3x the compute of a 16k baseline." },
      { k: "h2", t: "Plan" },
      { k: "ol", t: "Reproduce the matched-compute ALiBi baseline at 32k." },
      { k: "ol", t: "Add a synthetic retrieval auxiliary loss on long documents." },
      { k: "ol", t: "Evaluate on the in-house long-context benchmark plus a public benchmark for sanity." },
      { k: "ol", t: "Write up the result with ablations on auxiliary loss weight and document length distribution." },
      { k: "h2", t: "Deliverables" },
      { k: "ul", t: "Pre-trained checkpoint at 7B parameters, 64k context." },
      { k: "ul", t: "Public-benchmark numbers reported at matched compute." },
      { k: "ul", t: "Manuscript draft by 2026-07-15." },
      { k: "h2", t: "Risks" },
      { k: "ul", t: "Cluster availability for multi-day 7B runs." },
      { k: "ul", t: "Synthetic auxiliary loss could overfit to retrieval-style signals." },
      { k: "ul", t: "Reviewer pushback on synthetic-only evaluations — mitigated by adding a real-document slice." },
    ]),
  });

  out.push({
    page: {
      id: "page_proposal_multimodal_eval",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "Proposal: Multimodal Evaluation Benchmark",
      type: "document",
      accessLevel: "workspace",
      icon: "🧪",
      parentPageId: "page_project_proposals",
    },
    blocks: blocksFor("page_proposal_multimodal_eval", [
      { k: "h1", t: "Proposal: Multimodal Evaluation Benchmark" },
      { k: "callout", t: "Status: scoping. Owner: Alice." },
      { k: "h2", t: "Motivation" },
      { k: "p", t: "Public multimodal evaluation suites either bucket too coarsely (one number per task family) or too narrowly (single-domain benchmarks). We want a benchmark that exposes where models fail by skill rather than by dataset." },
      { k: "h2", t: "Hypothesis" },
      { k: "p", t: "A skill-tagged evaluation will reveal that current top-line scores are inflated by reasoning-light items, and that grouping by skill produces a more honest picture of progress." },
      { k: "h2", t: "Plan" },
      { k: "ol", t: "Tag a 5,000-item subset across reasoning, perception, OCR, and instruction-following skills." },
      { k: "ol", t: "Run six open and two proprietary baselines." },
      { k: "ol", t: "Compute per-skill metrics and produce a leaderboard." },
      { k: "h2", t: "Deliverables" },
      { k: "ul", t: "Skill taxonomy + per-item tags." },
      { k: "ul", t: "Public leaderboard with reproducible runs." },
      { k: "h2", t: "Risks" },
      { k: "ul", t: "Annotator disagreement on skill tagging." },
      { k: "ul", t: "Compute budget for proprietary baselines." },
    ]),
  });

  out.push({
    page: {
      id: "page_proposal_synthetic_data",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "Proposal: Synthetic Data Quality Audits",
      type: "document",
      accessLevel: "workspace",
      icon: "🧪",
      parentPageId: "page_project_proposals",
    },
    blocks: blocksFor("page_proposal_synthetic_data", [
      { k: "h1", t: "Proposal: Synthetic Data Quality Audits" },
      { k: "h2", t: "Motivation" },
      { k: "p", t: "Synthetic training data is now a default ingredient. We do not have a shared rubric for spotting degenerate failure modes (mode collapse, hallucinated facts, surface-form copying)." },
      { k: "h2", t: "Hypothesis" },
      { k: "p", t: "A small set of cheap, automated checks (n-gram repetition, entity factuality against a small knowledge base, stylistic diversity) catches more than 80% of the issues we currently catch through manual sampling." },
      { k: "h2", t: "Plan" },
      { k: "ol", t: "Define five automated checks with clear thresholds." },
      { k: "ol", t: "Apply them retroactively to three internal synthetic datasets and compare to manual notes." },
      { k: "ol", t: "Wrap the checks in a small CLI for the data team." },
      { k: "h2", t: "Risks" },
      { k: "ul", t: "Thresholds are dataset-specific; we may end up tuning per dataset rather than producing a universal rubric." },
    ]),
  });

  // ============ 5. Dataset notes ============
  const dsHub: PageBase = {
    id: "page_dataset_notes",
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: "Dataset Notes",
    type: "document",
    accessLevel: "workspace",
    icon: "🗃️",
    parentPageId: null,
  };
  const dsHubBlocks = blocksFor(dsHub.id, [
    { k: "h1", t: "Dataset Notes" },
    { k: "p", t: "Working notes on datasets we touch. Each child page records the dataset's purpose, license, statistics, evaluation protocol, and gotchas." },
    { k: "h2", t: "Conventions" },
    { k: "ul", t: "Always list the license and any redistribution restrictions at the top." },
    { k: "ul", t: "Record splits, version, and any custom subsets we use." },
    { k: "ul", t: "Capture surprises — the kinds of things that bite us on the second use." },
  ]);
  out.push({ page: dsHub, blocks: dsHubBlocks });

  out.push({
    page: {
      id: "page_dataset_imagenet",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "ImageNet (ILSVRC)",
      type: "document",
      accessLevel: "workspace",
      icon: "🖼️",
      parentPageId: "page_dataset_notes",
    },
    blocks: blocksFor("page_dataset_imagenet", [
      { k: "h1", t: "ImageNet (ILSVRC)" },
      { k: "p", t: "ILSVRC is a 1,000-class subset of ImageNet used as the default large-scale image classification benchmark since 2010. We mostly use the 2012 split." },
      { k: "h2", t: "Splits and statistics" },
      { k: "ul", t: "Train: 1.28M images across 1,000 classes." },
      { k: "ul", t: "Validation: 50,000 images (50 per class), used for our internal early stopping." },
      { k: "ul", t: "Test: 100,000 images, labels held out by the organizers historically." },
      { k: "h2", t: "Evaluation protocol" },
      { k: "ol", t: "Top-1 and top-5 accuracy on the validation set." },
      { k: "ol", t: "Center crop at 224×224 after resize-shorter-side to 256." },
      { k: "ol", t: "Test-time augmentation (10-crop) only when comparing to TTA-reported baselines." },
      { k: "h2", t: "Gotchas" },
      { k: "ul", t: "Validation labels were re-mapped after a prior ILSVRC; double-check against the synset mapping you use." },
      { k: "ul", t: "Some class boundaries are noisy (e.g., dog breeds); per-class accuracy can be misleading." },
      { k: "h2", t: "License" },
      { k: "p", t: "Research-only; do not redistribute the raw images. Always link to the official download instructions." },
    ]),
  });

  out.push({
    page: {
      id: "page_dataset_squad",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "SQuAD v1.1 / v2.0",
      type: "document",
      accessLevel: "workspace",
      icon: "📚",
      parentPageId: "page_dataset_notes",
    },
    blocks: blocksFor("page_dataset_squad", [
      { k: "h1", t: "SQuAD v1.1 / v2.0" },
      { k: "p", t: "Reading comprehension dataset built from Wikipedia articles. v1.1 always has an answer in the passage; v2.0 introduces unanswerable questions." },
      { k: "h2", t: "Splits and statistics" },
      { k: "ul", t: "v1.1 train: ~87.6k QAs. Dev: ~10.6k QAs. Test held out." },
      { k: "ul", t: "v2.0 adds ~50k unanswerable questions to train and ~5.9k to dev." },
      { k: "h2", t: "Evaluation" },
      { k: "ol", t: "Exact Match (EM) and macro-averaged F1 over reference answers." },
      { k: "ol", t: "For v2.0, the model must output the empty string for unanswerable questions." },
      { k: "h2", t: "Gotchas" },
      { k: "ul", t: "Different normalization scripts produce slightly different EM/F1 — pin the version." },
      { k: "ul", t: "v2.0 unanswerables are adversarially constructed; behavior here often diverges from v1.1." },
    ]),
  });

  out.push({
    page: {
      id: "page_dataset_glue",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "GLUE / SuperGLUE",
      type: "document",
      accessLevel: "workspace",
      icon: "📊",
      parentPageId: "page_dataset_notes",
    },
    blocks: blocksFor("page_dataset_glue", [
      { k: "h1", t: "GLUE / SuperGLUE" },
      { k: "p", t: "Multi-task NLU benchmarks. GLUE tasks include sentiment (SST-2), paraphrase (MRPC, QQP), inference (MNLI, RTE, QNLI, WNLI), similarity (STS-B), and acceptability (CoLA). SuperGLUE adds harder tasks like BoolQ, CB, COPA, MultiRC, ReCoRD, RTE, and WiC." },
      { k: "h2", t: "Reporting" },
      { k: "ul", t: "Average score across tasks is the headline number." },
      { k: "ul", t: "WNLI is famously brittle on GLUE — many leaderboard entries report 65.1 (the majority class baseline) and explain why in a footnote." },
      { k: "h2", t: "Internal use" },
      { k: "p", t: "We use GLUE as a quick sanity check on encoder pre-training. SuperGLUE is reserved for stronger models — single-task performance below random hurts the average a lot." },
    ]),
  });

  // ============ 6. Open public-domain texts shelf ============
  const otHub: PageBase = {
    id: "page_open_texts",
    workspaceId: "ws_research",
    createdById: "user_demo",
    title: "Reading Shelf — Public-Domain Texts",
    type: "document",
    accessLevel: "workspace",
    icon: "📚",
    parentPageId: null,
  };
  const otHubBlocks = blocksFor(otHub.id, [
    { k: "h1", t: "Reading Shelf — Public-Domain Texts" },
    { k: "p", t: "A small shelf of public-domain readings the lab returns to between papers. The aim is to keep our reading habits broader than benchmarks." },
    { k: "h2", t: "Selection" },
    { k: "ul", t: "Marcus Aurelius — Meditations (translated by George Long; public domain)." },
    { k: "ul", t: "Charles Darwin — On the Origin of Species (1st edition; public domain)." },
    { k: "ul", t: "Isaac Newton — Philosophiæ Naturalis Principia Mathematica (translated by Andrew Motte; public domain)." },
    { k: "h2", t: "Why these texts" },
    { k: "p", t: "Each is a primary source whose phrasing has shaped how later generations talk about its subject. Reading the originals is humbling and often clarifies why later technical language exists." },
  ]);
  out.push({ page: otHub, blocks: otHubBlocks });

  out.push({
    page: {
      id: "page_text_meditations",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "Meditations — Marcus Aurelius",
      type: "document",
      accessLevel: "workspace",
      icon: "🏛️",
      parentPageId: "page_open_texts",
    },
    blocks: blocksFor("page_text_meditations", [
      { k: "h1", t: "Meditations — Marcus Aurelius" },
      { k: "p", t: "The Meditations are private notes Marcus Aurelius wrote to himself during military campaigns in the 170s CE. The English translation by George Long (1862) is in the public domain." },
      { k: "h2", t: "Selected passages (George Long translation, public domain)" },
      { k: "quote", t: "Begin the morning by saying to thyself, I shall meet with the busy-body, the ungrateful, arrogant, deceitful, envious, unsocial. (Book II, 1)" },
      { k: "quote", t: "Time is like a river made up of the events which happen, and a violent stream; for as soon as a thing has been seen, it is carried away, and another comes in its place, and this will be carried away too. (Book IV, 43)" },
      { k: "quote", t: "Look within. Within is the fountain of good, and it will ever bubble up, if thou wilt ever dig. (Book VII, 59)" },
      { k: "h2", t: "Reading note" },
      { k: "p", t: "What I take away on this re-read: most of the book is about the gap between what happens to us and the judgment we add on top. The lab analogy: separating the experimental result from the narrative we attach to it makes both easier to revise." },
      { k: "h2", t: "Cross-references" },
      { k: "ul", t: "Hadot, Pierre — The Inner Citadel: The Meditations of Marcus Aurelius (secondary reading; not in the public domain)." },
      { k: "ul", t: "Epictetus — Discourses (similar Stoic source material; older Long translation is also public domain)." },
    ]),
  });

  out.push({
    page: {
      id: "page_text_origin_species",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "On the Origin of Species — Charles Darwin",
      type: "document",
      accessLevel: "workspace",
      icon: "🐢",
      parentPageId: "page_open_texts",
    },
    blocks: blocksFor("page_text_origin_species", [
      { k: "h1", t: "On the Origin of Species — Charles Darwin" },
      { k: "p", t: "On the Origin of Species was first published in 1859. The first edition is firmly in the public domain. We read the introduction and chapter four (\"Natural Selection\") for this round." },
      { k: "h2", t: "Selected passages (1st edition, 1859, public domain)" },
      { k: "quote", t: "It may be said that natural selection is daily and hourly scrutinising, throughout the world, every variation, even the slightest; rejecting that which is bad, preserving and adding up all that is good. (Chapter IV)" },
      { k: "quote", t: "There is grandeur in this view of life, with its several powers, having been originally breathed into a few forms or into one; and that, whilst this planet has gone cycling on according to the fixed law of gravity, from so simple a beginning endless forms most beautiful and most wonderful have been, and are being, evolved. (Closing sentence)" },
      { k: "h2", t: "Reading note" },
      { k: "p", t: "The book is striking because it argues entirely from accumulated small evidence. The pattern resembles careful empirical work: many small observations supporting a single theoretical move." },
    ]),
  });

  out.push({
    page: {
      id: "page_text_principia",
      workspaceId: "ws_research",
      createdById: "user_demo",
      title: "Principia (Motte translation) — Isaac Newton",
      type: "document",
      accessLevel: "workspace",
      icon: "🪐",
      parentPageId: "page_open_texts",
    },
    blocks: blocksFor("page_text_principia", [
      { k: "h1", t: "Principia (Motte translation) — Isaac Newton" },
      { k: "p", t: "Newton's Philosophiæ Naturalis Principia Mathematica was first published in 1687. We use Andrew Motte's 1729 English translation (public domain)." },
      { k: "h2", t: "The three laws (Motte, public domain)" },
      { k: "quote", t: "Law I: Every body perseveres in its state of rest, or of uniform motion in a right line, unless it is compelled to change that state by forces impressed thereon." },
      { k: "quote", t: "Law II: The alteration of motion is ever proportional to the motive force impressed; and is made in the direction of the right line in which that force is impressed." },
      { k: "quote", t: "Law III: To every action there is always opposed an equal reaction." },
      { k: "h2", t: "Reading note" },
      { k: "p", t: "Newton's prose is famously austere. What is easy to miss is how much definitional work happens before the laws — the careful definitions of mass and force are what let the laws say anything at all." },
    ]),
  });

  return out;
}

// =====================================================================
// WEBARENA HQ — operational documents (moved out of research lab)
// =====================================================================

function buildHQPages(): PageWithBlocks[] {
  const out: PageWithBlocks[] = [];

  // ----- Launch Operations -----
  out.push({
    page: {
      id: "page_launch_ops_hub",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Product Launch Operations",
      type: "document",
      accessLevel: "workspace",
      icon: "🚀",
      parentPageId: null,
    },
    blocks: blocksFor("page_launch_ops_hub", [
      { k: "h1", t: "Product Launch Operations" },
      { k: "p", t: "Hub for the launch operations team. Contains the readiness handbook, the freeze calendar, and the cross-functional checklist we run before any major release." },
      { k: "h2", t: "Standing rituals" },
      { k: "ul", t: "Monday — launch ops sync (30 min): walk through the active readiness checklist." },
      { k: "ul", t: "Wednesday — risk review (45 min): with reliability, support, and customer education." },
      { k: "ul", t: "Friday — launch retro (15 min): only if a launch shipped that week." },
      { k: "h2", t: "Active launches" },
      { k: "ul", t: "Mobile Onboarding Revamp — owner Alice. Status: in review. Target ship: 2026-06-14." },
      { k: "ul", t: "Billing Reliability — owner Alex. Status: in progress. Target ship: 2026-06-07." },
      { k: "ul", t: "Comment Platform Upgrade — owner Demo. Status: in progress. Target ship: 2026-06-21." },
      { k: "h2", t: "Where things live" },
      { k: "ul", t: "Detailed checklist sequencing → Launch Readiness Handbook (child page)." },
      { k: "ul", t: "Active risks and accepted exceptions → Risk Register (in this hub)." },
      { k: "ul", t: "Help center copy and in-app strings → owned by content design; tracked here only by status." },
    ]),
  });

  out.push({
    page: {
      id: "page_launch_readiness_handbook",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Launch Readiness Handbook",
      type: "document",
      accessLevel: "workspace",
      icon: "📘",
      parentPageId: "page_launch_ops_hub",
    },
    blocks: blocksFor("page_launch_readiness_handbook", [
      { k: "h1", t: "Launch Readiness Handbook" },
      { k: "p", t: "A working handbook for launches in the WebArena product. It is intentionally explicit so a new launch lead can run a release without a handover meeting." },
      { k: "h2", t: "Roles" },
      { k: "ul", t: "Launch lead — owns the timeline; convenes the readiness reviews." },
      { k: "ul", t: "Reliability partner — signs off on alerting, dashboards, and rollback plan." },
      { k: "ul", t: "Support partner — owns macros, FAQ, and on-call for the first 48 hours." },
      { k: "ul", t: "Customer education partner — owns help center copy and in-app strings." },
      { k: "h2", t: "Phases" },
      { k: "h3", t: "T-21: scoping freeze" },
      { k: "ul", t: "Final scope locked. New requests go to a follow-up release." },
      { k: "ul", t: "Risk register seeded with at least three risks, each with an owner." },
      { k: "h3", t: "T-14: copy and content lock" },
      { k: "ul", t: "Help center articles drafted and reviewed; legal review if customer-visible terminology changes." },
      { k: "ul", t: "Support macros updated with the launch language." },
      { k: "h3", t: "T-7: dry run" },
      { k: "ul", t: "Walk the launch in staging end-to-end, including the rollback path." },
      { k: "ul", t: "Reliability partner confirms dashboards refresh against staging traffic." },
      { k: "h3", t: "T-1: ship readiness review" },
      { k: "ol", t: "Run the launch readiness checklist top to bottom." },
      { k: "ol", t: "Confirm on-call coverage for the first 48 hours after release." },
      { k: "ol", t: "Document any outstanding exceptions in the risk register, signed by the launch lead." },
      { k: "h3", t: "T+0: ship" },
      { k: "ul", t: "Stagger rollout regions where applicable; default order: internal → 1% → 25% → 100%." },
      { k: "ul", t: "Watch the launch dashboard for 30 minutes after each ramp." },
      { k: "h3", t: "T+1 to T+7: stabilization" },
      { k: "ul", t: "Daily check on dashboards and support inbox; surface anything trending up." },
      { k: "ul", t: "Resolve open exceptions or extend with explicit timeline and owner." },
      { k: "h3", t: "T+7: retro" },
      { k: "ul", t: "Light-weight retro: what worked, what to change, what to add to the handbook." },
      { k: "h2", t: "Risk register conventions" },
      { k: "p", t: "Each risk has: short title, why it could matter, owner, mitigation status (open/mitigated/accepted), and a one-line note on the contingency plan if the mitigation fails." },
      { k: "h2", t: "Common pitfalls observed in past launches" },
      { k: "ul", t: "Help center publishes ahead of in-app strings, leading to mismatched terminology in screenshots." },
      { k: "ul", t: "Macros updated only in English; non-English macros reviewed in the next sprint." },
      { k: "ul", t: "Reliability dashboard saved to a personal workspace and unreachable during the release window." },
      { k: "ul", t: "On-call coverage scheduled per release but not synced to the team calendar." },
      { k: "h2", t: "Templates and links" },
      { k: "ul", t: "Risk register template — copy from the Risk Register section above." },
      { k: "ul", t: "Launch retro template — copy from any past T+7 retro section." },
      { k: "ul", t: "Reliability sign-off template — owned by the reliability team." },
    ]),
  });

  // ----- Customer research hub -----
  out.push({
    page: {
      id: "page_customer_research_hub",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Customer Research Hub",
      type: "document",
      accessLevel: "workspace",
      icon: "🎙️",
      parentPageId: null,
    },
    blocks: blocksFor("page_customer_research_hub", [
      { k: "h1", t: "Customer Research Hub" },
      { k: "p", t: "Working hub for customer research. We keep raw interview notes, synthesis docs, and the live theme tracker in one workspace so PM, design, and marketing all reach for the same evidence." },
      { k: "h2", t: "Active research streams" },
      { k: "ul", t: "Onboarding friction — IT admins (interviews #142–158)." },
      { k: "ul", t: "Billing trust signals — finance ops contacts (interviews #160–172)." },
      { k: "ul", t: "Audit log usage — security and compliance buyers (ongoing)." },
      { k: "h2", t: "Conventions" },
      { k: "ul", t: "Tag interviews with role, account size, and the top three friction moments raised." },
      { k: "ul", t: "Quotes are paraphrased to preserve customer voice without recording verbatim." },
      { k: "ul", t: "Synthesis decks are tied back to interview IDs so we can audit the chain of evidence." },
    ]),
  });

  out.push({
    page: {
      id: "page_customer_interview_digest",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Customer Interview Digest — Q2 2026",
      type: "document",
      accessLevel: "workspace",
      icon: "🗂️",
      parentPageId: "page_customer_research_hub",
    },
    blocks: blocksFor("page_customer_interview_digest", [
      { k: "h1", t: "Customer Interview Digest — Q2 2026" },
      { k: "p", t: "Synthesis of interviews #142 through #172 conducted between mid-March and late April 2026." },
      { k: "h2", t: "Top friction moments" },
      { k: "ol", t: "Approval-heavy provisioning (mentioned in 18 of 31 interviews) — IT admins describe a multi-step approval that frequently stalls a workspace setup for 3–7 business days." },
      { k: "ol", t: "Confusing audit log scope (mentioned in 14 of 31 interviews) — buyers expect activity logs to include comment moderation actions, not only structural changes." },
      { k: "ol", t: "Bulk invite reliability (mentioned in 11 of 31 interviews) — invites larger than 200 users frequently see delayed delivery, prompting workarounds." },
      { k: "h2", t: "Themes by buyer role" },
      { k: "h3", t: "IT admins" },
      { k: "ul", t: "Want a single view of pending setup steps assigned to them and to others." },
      { k: "ul", t: "Repeatedly ask for approval delegation; multiple admins describe being a bottleneck for their org." },
      { k: "h3", t: "Finance ops" },
      { k: "ul", t: "Want billing alerts to support delegation and quiet hours." },
      { k: "ul", t: "Distrust automatic charge events without an itemized preview the day before." },
      { k: "h3", t: "Security and compliance" },
      { k: "ul", t: "Treat audit log completeness as table stakes; gaps trigger procurement re-review." },
      { k: "ul", t: "Ask for region-specific export controls more often than for new features." },
      { k: "h2", t: "Recommended product implications" },
      { k: "ul", t: "Approval delegation in workspace settings — high impact for IT admin segment." },
      { k: "ul", t: "Audit log scope expansion to comment moderation actions — clear procurement-blocker fix." },
      { k: "ul", t: "Bulk invite reliability program — small fix, large NPS win." },
      { k: "h2", t: "Open questions" },
      { k: "ul", t: "How much of the approval pain is policy versus product?" },
      { k: "ul", t: "Is the audit log gap consistent across regions, or specific to EU customers?" },
      { k: "ul", t: "Do bulk invite delays correlate with workspace plan tier?" },
      { k: "h2", t: "Methodology" },
      { k: "p", t: "Semi-structured 45-minute interviews. Scripts evolved each fortnight as themes settled. Notes were tagged in shared spreadsheets and synthesized in pairs to reduce single-rater bias." },
    ]),
  });

  // ----- Incident response hub -----
  out.push({
    page: {
      id: "page_incident_response_hub",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Incident Response Center",
      type: "document",
      accessLevel: "workspace",
      icon: "🚨",
      parentPageId: null,
    },
    blocks: blocksFor("page_incident_response_hub", [
      { k: "h1", t: "Incident Response Center" },
      { k: "p", t: "How the team responds to and writes up incidents that affect WebArena customers. The Incident Chronicle child page is the running log." },
      { k: "h2", t: "Severity definitions" },
      { k: "ul", t: "SEV-1: customer-visible outage of a core surface (sign-in, page load, billing)." },
      { k: "ul", t: "SEV-2: significant degradation that workarounds exist for (slow pages, delayed notifications)." },
      { k: "ul", t: "SEV-3: limited-scope or short-duration issues with no customer escalation expected." },
      { k: "h2", t: "On-call ownership" },
      { k: "ul", t: "Primary: rotating across reliability and platform engineering." },
      { k: "ul", t: "Secondary: paged after 15 minutes if the primary does not acknowledge." },
      { k: "ul", t: "Comms: shared with the support escalation lead during business hours." },
      { k: "h2", t: "Postmortem expectations" },
      { k: "ol", t: "Timeline written within 24 hours of resolution." },
      { k: "ol", t: "Customer-impact summary signed off by the support escalation lead." },
      { k: "ol", t: "Follow-up actions filed and tagged with severity in the engineering tracker." },
    ]),
  });

  out.push({
    page: {
      id: "page_incident_chronicle",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Incident Chronicle",
      type: "document",
      accessLevel: "workspace",
      icon: "📉",
      parentPageId: "page_incident_response_hub",
    },
    blocks: blocksFor("page_incident_chronicle", [
      { k: "h1", t: "Incident Chronicle" },
      { k: "p", t: "Running log of customer-visible reliability incidents. Most recent first." },
      { k: "h2", t: "2026-04-22 — Comment writes returning 429 (SEV-2)" },
      { k: "ul", t: "Detection: support escalation flagged elevated 429 responses for comment_create at 14:08 KST." },
      { k: "ul", t: "Impact: ~6% of comment writes failed for 38 minutes; users could retry successfully." },
      { k: "ul", t: "Root cause: rate limiter was sharing budget between comment_create and reaction_create after a refactor on 04-15." },
      { k: "ul", t: "Mitigation: separated the rate limit budgets and shipped a targeted patch." },
      { k: "ul", t: "Follow-up: better rate limiter integration tests; owner Alex; due 2026-05-09." },
      { k: "h2", t: "2026-04-09 — Billing alert delivery delayed (SEV-2)" },
      { k: "ul", t: "Detection: finance ops customer reported missing daily alert at 09:14 PT." },
      { k: "ul", t: "Impact: alert delivery delayed by up to 4 hours for ~1.2% of customers, three calendar days." },
      { k: "ul", t: "Root cause: background job worker pool exhausted by a stuck retry queue." },
      { k: "ul", t: "Mitigation: drained the queue; added per-job timeout to prevent the same failure mode." },
      { k: "ul", t: "Follow-up: queue-depth alarm threshold review; owner Mina; due 2026-04-30." },
      { k: "h2", t: "2026-03-30 — Search index lag after large workspace import (SEV-3)" },
      { k: "ul", t: "Detection: internal admin noticed stale results when previewing a customer's setup." },
      { k: "ul", t: "Impact: search results lagged actual content by up to 18 minutes for one workspace; not customer-visible." },
      { k: "ul", t: "Root cause: bulk import bypassed the incremental indexing pipeline." },
      { k: "ul", t: "Mitigation: triggered a manual re-index and added a backfill check." },
      { k: "ul", t: "Follow-up: import pipeline contract test with the indexer; owner Alex; due 2026-04-15." },
      { k: "h2", t: "2026-03-12 — Attachment upload failures (SEV-3)" },
      { k: "ul", t: "Detection: support ticket volume spiked at 23:30 PT; reproduced internally within 20 minutes." },
      { k: "ul", t: "Impact: ~0.4% of attachment uploads failed for 1h 40m." },
      { k: "ul", t: "Root cause: storage region failover left a stale endpoint cached in the worker." },
      { k: "ul", t: "Mitigation: forced cache invalidation; added periodic invalidation for region-config caches." },
      { k: "ul", t: "Follow-up: chaos test for storage region failover; owner Alice; due 2026-04-30." },
    ]),
  });

  // ----- Marketing -----
  out.push({
    page: {
      id: "page_marketing_hub",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Marketing Campaign Planning",
      type: "document",
      accessLevel: "workspace",
      icon: "📣",
      parentPageId: null,
    },
    blocks: blocksFor("page_marketing_hub", [
      { k: "h1", t: "Marketing Campaign Planning" },
      { k: "p", t: "Living plan for Q2 marketing. Each campaign has a one-line audience, a measurable goal, and a list of dependencies that block launch." },
      { k: "h2", t: "Q2 campaigns" },
      { k: "h3", t: "1. Admin Adoption Playbook (audience: IT admins at mid-market)" },
      { k: "ul", t: "Goal: 1.5x lift in admin-led activation rate within 4 weeks of launch." },
      { k: "ul", t: "Channels: lifecycle email, in-app announcements, partner webinar." },
      { k: "ul", t: "Dependencies: in-app announcement gating from product, three customer quotes from research hub." },
      { k: "h3", t: "2. Reliability and Governance Webinar (audience: security and compliance buyers)" },
      { k: "ul", t: "Goal: 600 registrations split 60/40 across NA/EMEA." },
      { k: "ul", t: "Dependencies: product to confirm audit log scope expansion; legal review of demo content." },
      { k: "h3", t: "3. Trial-to-Paid Lifecycle Refresh (audience: distributed teams in 7-day trial)" },
      { k: "ul", t: "Goal: +0.8 percentage point conversion at the day-7 boundary." },
      { k: "ul", t: "Dependencies: subject-line A/B framework refresh; coordination with product on day-3 in-product nudge." },
      { k: "h2", t: "Measurement notes" },
      { k: "ul", t: "We attribute admin-led activation to a campaign if the user opens any email asset within 7 days of activating." },
      { k: "ul", t: "Webinar registrations counted post-event for the goal; pre-event we report a leading indicator (registration velocity vs prior campaign)." },
    ]),
  });

  // ----- Sales -----
  out.push({
    page: {
      id: "page_sales_hub",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Sales and Partnership Workspace",
      type: "document",
      accessLevel: "workspace",
      icon: "🤝",
      parentPageId: null,
    },
    blocks: blocksFor("page_sales_hub", [
      { k: "h1", t: "Sales and Partnership Workspace" },
      { k: "p", t: "Live tracking for the top opportunities and partner motions in flight. CRM stays the source of truth for amounts; this page is for context that does not fit a CRM field." },
      { k: "h2", t: "Top opportunities" },
      { k: "h3", t: "Northstar Commerce — admin workflow rollout" },
      { k: "ul", t: "Stage: technical evaluation. Champion: Director of Operations." },
      { k: "ul", t: "Outstanding ask: SAML group claims pass-through. Owner: Demo. ETA: 2026-05-15." },
      { k: "h3", t: "Acme Analytics — QBR preparation" },
      { k: "ul", t: "Stage: post-onboarding expansion review." },
      { k: "ul", t: "QBR scheduled 2026-05-22; agenda owner: Alex." },
      { k: "h3", t: "Helix Health — security review delay" },
      { k: "ul", t: "Stage: legal/security questionnaire." },
      { k: "ul", t: "Blocker: detailed audit log export documentation. Owner: Alice. ETA: 2026-05-09." },
      { k: "h2", t: "Partner motions" },
      { k: "ul", t: "EMEA agency partner enablement — workshop scheduled 2026-05-30." },
      { k: "ul", t: "APAC reseller portal beta — five participants confirmed." },
    ]),
  });

  // ----- Hiring -----
  out.push({
    page: {
      id: "page_hiring_hub",
      workspaceId: "ws_webarena",
      createdById: "user_demo",
      title: "Hiring and Recruiting",
      type: "document",
      accessLevel: "workspace",
      icon: "🧑‍💼",
      parentPageId: null,
    },
    blocks: blocksFor("page_hiring_hub", [
      { k: "h1", t: "Hiring and Recruiting" },
      { k: "p", t: "Active roles and recruiting context that does not belong in the ATS. Calibration notes and process changes live here." },
      { k: "h2", t: "Active roles" },
      { k: "h3", t: "Senior Frontend Engineer (Activation Surfaces)" },
      { k: "ul", t: "Stage: panel interviews. Hiring manager: Alice." },
      { k: "ul", t: "Calibration note: prefer candidates with deep web platform experience over framework specialization." },
      { k: "h3", t: "Reliability Program Manager" },
      { k: "ul", t: "Stage: phone screens. Hiring manager: Alex." },
      { k: "ul", t: "Calibration note: needs incident communications experience as a discriminator." },
      { k: "h3", t: "Customer Research Lead" },
      { k: "ul", t: "Stage: sourcing. Hiring manager: Demo." },
      { k: "ul", t: "Calibration note: comfortable running mixed-methods studies; strong writing samples required." },
      { k: "h2", t: "Process improvements in flight" },
      { k: "ul", t: "Standardizing the take-home prompt across PM and design loops." },
      { k: "ul", t: "Quarterly recalibration of scorecards based on 90-day reviews of recent hires." },
    ]),
  });

  return out;
}

// =====================================================================
// PERSONAL — trip itineraries (per-destination day-by-day)
// =====================================================================

type TripDay = { label: string; bullets: string[] };
type TripDef = { dest: TravelDestination; emoji: string; intro: string; days: TripDay[]; restaurants: string[]; transitNotes: string[] };

function buildTripPages(): PageWithBlocks[] {
  const out: PageWithBlocks[] = [];

  const hub: PageBase = {
    id: "page_trip_itineraries",
    workspaceId: "ws_personal",
    createdById: "user_demo",
    title: "Trip Itineraries",
    type: "document",
    accessLevel: "workspace",
    icon: "🗺️",
    parentPageId: "page_travel_plans",
  };
  const hubBlocks = blocksFor(hub.id, [
    { k: "h1", t: "Trip Itineraries" },
    { k: "p", t: "Detailed day-by-day plans for upcoming trips. Each child page is a draft itinerary with restaurants, activities, and transit notes. The travel database keeps the budget overview; these pages keep the texture of the trip." },
    { k: "h2", t: "Index" },
    { k: "ul", t: "Busan — Summer beach getaway." },
    { k: "ul", t: "Sapporo — Snow Festival winter trip." },
    { k: "ul", t: "Tokyo — Cherry blossom week." },
    { k: "ul", t: "Kyoto — Temple slow-travel five days." },
    { k: "ul", t: "Jeju — West coast road trip." },
    { k: "ul", t: "Taipei — Night market and tea-tasting trip." },
    { k: "ul", t: "Bali — Ubud yoga retreat week." },
  ]);
  out.push({ page: hub, blocks: hubBlocks });

  const trips: TripDef[] = [
    {
      dest: "Busan",
      emoji: "🌊",
      intro: "Three-day beach-and-cafe trip in mid-July. Base in Haeundae, day-trip to Gamcheon and the coastal train.",
      days: [
        { label: "Day 1 — Friday", bullets: [
          "Afternoon KTX from Seoul Station to Busan.",
          "Check in at Haeundae Beach hotel; sunset walk along the boardwalk.",
          "Late seafood dinner at Jagalchi Market.",
        ] },
        { label: "Day 2 — Saturday", bullets: [
          "Morning swim, breakfast at hotel.",
          "Coastal train Haeundae → Songjeong (reserve seats).",
          "Afternoon at Gamcheon Culture Village.",
          "Dinner near Gwangalli for the bridge view.",
        ] },
        { label: "Day 3 — Sunday", bullets: [
          "Morning at Beomeosa temple.",
          "Lunch back in Seomyeon, coffee tour in Jeonpo.",
          "Evening KTX back to Seoul.",
        ] },
      ],
      restaurants: [
        "Jagalchi Market (seafood)",
        "Gwangalli brewery dinner",
        "Jeonpo coffee street brunch",
      ],
      transitNotes: [
        "Top up Cashbee at the airport — the local subway is the easiest way around the beach areas.",
        "The coastal train sells out for weekends; book the Songjeong leg in advance.",
      ],
    },
    {
      dest: "Sapporo",
      emoji: "❄️",
      intro: "Snow Festival winter trip in early February. Five nights in Susukino with day trips to Otaru and one ski day in Niseko.",
      days: [
        { label: "Day 1 — Arrival", bullets: [
          "Evening flight Haneda → Sapporo (CTS).",
          "Airport rail to Sapporo Station; subway to Susukino apartment.",
          "Late ramen dinner at Menya Saimi.",
        ] },
        { label: "Day 2 — Snow Festival main grounds", bullets: [
          "Odori Park snow sculptures from morning to dusk (heavy crowds; arrive early).",
          "Lunch at Nijo Market.",
          "Evening illumination at Susukino site.",
        ] },
        { label: "Day 3 — Otaru day trip", bullets: [
          "JR Hokkaido train to Otaru (~35 min).",
          "Canal walk and glassworks district.",
          "Sushi lunch at one of the alley shops.",
          "Return to Sapporo for dinner at the beer hall.",
        ] },
        { label: "Day 4 — Niseko ski day", bullets: [
          "Bus to Niseko (~3 hr).",
          "Half-day rental and lift pass.",
          "Onsen evening before bus back.",
        ] },
        { label: "Day 5 — Departure", bullets: [
          "Brunch at a Susukino cafe.",
          "Royce chocolate gift run at the station.",
          "Afternoon flight back.",
        ] },
      ],
      restaurants: [
        "Menya Saimi (ramen)",
        "Sapporo Beer Garden (lamb BBQ)",
        "Nijo Market (donburi for breakfast)",
      ],
      transitNotes: [
        "JR pass is worth it once you add the Otaru round-trip and the Niseko bus fare.",
        "Plan station-to-hotel walk in advance — Susukino sidewalks are slippery during festival week.",
      ],
    },
    {
      dest: "Tokyo",
      emoji: "🌸",
      intro: "Six-day cherry blossom trip in early April. Base in Asakusa with day trips to Kamakura and Hakone.",
      days: [
        { label: "Day 1", bullets: [
          "Skyliner from Narita; check in at Asakusa.",
          "Sumida River park walk for first cherry blossom photos.",
          "Tonkatsu dinner near Ueno.",
        ] },
        { label: "Day 2 — Yanaka and Ueno", bullets: [
          "Yanaka Ginza morning walk.",
          "Ueno Park hanami picnic.",
          "Evening Akihabara stroll.",
        ] },
        { label: "Day 3 — Shibuya / Shimokitazawa", bullets: [
          "Shibuya Crossing morning visit.",
          "Vintage shopping in Shimokitazawa.",
          "Late izakaya dinner near Ebisu.",
        ] },
        { label: "Day 4 — Kamakura day trip", bullets: [
          "Train to Kamakura.",
          "Great Buddha + Hasedera temple.",
          "Beach walk before returning.",
        ] },
        { label: "Day 5 — Hakone overnight (optional)", bullets: [
          "Romance Car to Hakone.",
          "Onsen ryokan evening.",
        ] },
        { label: "Day 6 — Departure", bullets: [
          "Brunch in Jimbocho; bookstore stop.",
          "Skyliner back to Narita.",
        ] },
      ],
      restaurants: [
        "Tonkatsu Maisen (Aoyama branch)",
        "Tsukiji breakfast row",
        "Jimbocho cafe + cake stop",
      ],
      transitNotes: [
        "Tokyo Metro 72h pass is the simplest way to cover central Tokyo.",
        "Shinkansen to Hakone runs more often than the Romance Car but is less scenic.",
      ],
    },
    {
      dest: "Kyoto",
      emoji: "⛩️",
      intro: "Five-day temple-focused trip with one slow day in Arashiyama. Stay split between Gion and Arashiyama.",
      days: [
        { label: "Day 1", bullets: [
          "Shinkansen Tokyo → Kyoto.",
          "Gion machiya check-in; evening walk to Yasaka Shrine.",
        ] },
        { label: "Day 2 — Eastern temples", bullets: [
          "Pre-dawn Fushimi Inari hike.",
          "Lunch at Nishiki Market.",
          "Kiyomizu-dera afternoon visit.",
        ] },
        { label: "Day 3 — Western temples", bullets: [
          "Kinkakuji + Ryoanji combo.",
          "Late lunch at a noodle shop in Murasakino.",
        ] },
        { label: "Day 4 — Arashiyama slow day", bullets: [
          "Move to Arashiyama ryokan.",
          "Bamboo grove early morning.",
          "Tofu kaiseki dinner at the inn.",
        ] },
        { label: "Day 5 — Departure", bullets: [
          "Quick coffee at Kyoto Station.",
          "Shinkansen back.",
        ] },
      ],
      restaurants: [
        "Nishiki Market sampler",
        "Arashiyama tofu kaiseki",
        "Kyoto Station tonkatsu set",
      ],
      transitNotes: [
        "Kyoto buses get crowded; use the bus pass but plan the morning bus before 09:00.",
        "Taxi backup for Arashiyama late-night returns.",
      ],
    },
    {
      dest: "Jeju",
      emoji: "🍊",
      intro: "Four-day west-coast road trip with one day on Hallasan trails.",
      days: [
        { label: "Day 1", bullets: [
          "Morning flight to Jeju.",
          "Rental car pickup; drive to Aewol pension.",
          "Sunset at Hyeopjae beach.",
        ] },
        { label: "Day 2 — Coast loop", bullets: [
          "Drive to Hyeopjae and Geumneung beaches.",
          "Tangerine farm visit.",
          "Black pork BBQ dinner.",
        ] },
        { label: "Day 3 — Hallasan trails", bullets: [
          "Pick a short oreum trail (Saebyeol or Geomun).",
          "Picnic lunch.",
          "Onsen recovery in Aewol.",
        ] },
        { label: "Day 4 — Departure", bullets: [
          "Drive back to airport, return rental.",
          "Citrus jam haul before security.",
        ] },
      ],
      restaurants: [
        "Black pork BBQ in Aewol",
        "Aewol cafe brunch flight",
        "Seafood porridge near the harbor",
      ],
      transitNotes: [
        "Fuel stations are sparse along the west coast loop — top up before leaving the city.",
        "Parking at Seongsan is paid; bring small change.",
      ],
    },
    {
      dest: "Taipei",
      emoji: "🍵",
      intro: "Four-day food + hot spring trip. Base in Da'an district.",
      days: [
        { label: "Day 1", bullets: [
          "Airport MRT to Da'an district.",
          "Yongkang street dinner walk (beef noodles).",
        ] },
        { label: "Day 2 — Night market run", bullets: [
          "Daan Forest Park morning walk.",
          "Eslite bookstore afternoon.",
          "Shilin Night Market evening.",
        ] },
        { label: "Day 3 — Beitou hot springs", bullets: [
          "Morning MRT to Beitou.",
          "Hot spring afternoon.",
          "Maokong gondola for sunset tea.",
        ] },
        { label: "Day 4 — Departure", bullets: [
          "Pineapple cake gift box run.",
          "MRT to airport.",
        ] },
      ],
      restaurants: [
        "Yongkang Street beef noodles",
        "Din Tai Fung",
        "Maokong tea house",
      ],
      transitNotes: [
        "EasyCard for everything — works on MRT, buses, and convenience stores.",
        "Yangmingshan trail bus has limited evening returns; check the last bus time before going.",
      ],
    },
    {
      dest: "Bali",
      emoji: "🌴",
      intro: "Seven-day Ubud yoga + Canggu surf trip.",
      days: [
        { label: "Day 1", bullets: [
          "Afternoon arrival; private driver to Ubud.",
          "Villa check-in and balinese tasting dinner.",
        ] },
        { label: "Days 2–4 — Ubud", bullets: [
          "Morning yoga at the villa.",
          "Afternoon visits: Tegallalang, Tirta Empul, Monkey Forest.",
          "Evenings: rice-terrace dinners, market shopping.",
        ] },
        { label: "Day 5 — Move to Canggu", bullets: [
          "Driver transfer to Canggu surf-house.",
          "Late afternoon surf lesson.",
        ] },
        { label: "Day 6 — Surf + sunset", bullets: [
          "Morning surf, beach club afternoon.",
          "Sunset cocktails in Seminyak.",
        ] },
        { label: "Day 7 — Departure", bullets: [
          "Final brunch.",
          "Driver to Denpasar airport.",
        ] },
      ],
      restaurants: [
        "Babi Guling Ibu Oka",
        "Locavore To Go (Ubud)",
        "Seminyak sunset bar",
      ],
      transitNotes: [
        "Negotiate a per-day rate with the private driver if you need them more than two days.",
        "Scooter rentals are easy in Canggu but be careful about insurance coverage.",
      ],
    },
  ];

  for (const trip of trips) {
    const id = `page_trip_${slug(trip.dest)}`;
    const tripBlocks: BlockInput[] = [
      { k: "h1", t: `${trip.emoji} ${trip.dest} — itinerary` },
      { k: "p", t: trip.intro },
      { k: "h2", t: "Day-by-day" },
    ];
    for (const day of trip.days) {
      tripBlocks.push({ k: "h3", t: day.label });
      for (const bullet of day.bullets) tripBlocks.push({ k: "ul", t: bullet });
    }
    tripBlocks.push({ k: "h2", t: "Restaurants to try" });
    for (const r of trip.restaurants) tripBlocks.push({ k: "ul", t: r });
    tripBlocks.push({ k: "h2", t: "Transit notes" });
    for (const t of trip.transitNotes) tripBlocks.push({ k: "ul", t });
    tripBlocks.push({ k: "h2", t: "Outstanding to-dos" });
    tripBlocks.push({ k: "todo", t: "Confirm flights and lodging" });
    tripBlocks.push({ k: "todo", t: "Add line items to the Travel Budget database" });
    tripBlocks.push({ k: "todo", t: "Share this itinerary with travel companions" });

    out.push({
      page: {
        id,
        workspaceId: "ws_personal",
        createdById: "user_demo",
        title: `${trip.dest} – ${TRIP_PURPOSES[trip.dest][0].suffix}`,
        type: "document",
        accessLevel: "workspace",
        icon: trip.emoji,
        parentPageId: "page_trip_itineraries",
      },
      blocks: blocksFor(id, tripBlocks),
    });
  }

  return out;
}

// =====================================================================
// COMMENTS, SHARE LINKS, PERMISSIONS, ATTACHMENTS, WORKSPACE TABS
// =====================================================================

function buildExtras() {
  const comments: CommentSeed[] = [
    {
      id: "comment_scale_001",
      pageId: "page_paper_attention",
      authorId: "user_alex",
      content: "@demo@webarena.local the discussion section nails the open question — let's make this the next reading group revisit when we look at long-context.",
    },
    {
      id: "comment_scale_002",
      pageId: "page_paper_attention",
      authorId: "user_demo",
      parentCommentId: "comment_scale_001",
      content: "Agreed. I'll fold the long-context follow-ups into the May 30 session prep.",
    },
    {
      id: "comment_scale_003",
      pageId: "page_paper_bert",
      authorId: "user_alice",
      content: "Should we drop the NSP discussion since RoBERTa already covers it? Happy to fold the takeaway into a single bullet.",
    },
    {
      id: "comment_scale_004",
      pageId: "page_lab_meeting_2026_04_17",
      authorId: "user_alex",
      content: "Re-running the ablation at matched compute is in flight — expect numbers by Tuesday.",
    },
    {
      id: "comment_scale_005",
      pageId: "page_lab_meeting_2026_04_17",
      authorId: "user_mina",
      content: "Synthetic data design draft will land on the proposal page this week.",
    },
    {
      id: "comment_scale_006",
      pageId: "page_proposal_efficient_lm",
      authorId: "user_alex",
      content: "@alice@webarena.local your matched-compute results should slot directly into the plan section — let's coordinate before the lab review.",
    },
    {
      id: "comment_scale_007",
      pageId: "page_launch_readiness_handbook",
      authorId: "user_alex",
      content: "Adding a bullet under T-1 about explicitly verifying the rollback path in production-mode staging — it bit us on the last release.",
    },
    {
      id: "comment_scale_008",
      pageId: "page_incident_chronicle",
      authorId: "user_demo",
      content: "@alex@webarena.local can you confirm the 04-22 follow-up is filed in the engineering tracker? I want to close the loop in next week's review.",
    },
    {
      id: "comment_scale_009",
      pageId: "page_customer_interview_digest",
      authorId: "user_alice",
      content: "The approval delegation theme is consistent with what marketing heard in the admin webinar. Worth a joint write-up?",
    },
    {
      id: "comment_scale_010",
      pageId: "page_trip_busan",
      authorId: "user_demo",
      content: "Booked the Friday evening KTX. Updating the Travel Budget rows now.",
    },
    {
      id: "comment_scale_011",
      pageId: "page_trip_sapporo",
      authorId: "user_demo",
      content: "Snow Festival lands on Feb 4–11 next year — itinerary day labels assume that window.",
    },
    {
      id: "comment_scale_012",
      pageId: "page_trip_tokyo",
      authorId: "user_demo",
      content: "Cherry blossom forecast is still wide; revisit the day labels two weeks before the trip.",
    },
    {
      id: "comment_scale_013",
      pageId: "page_text_meditations",
      authorId: "user_alex",
      content: "The Hadot reference helped me a lot the first time — happy to lend my copy at the next lab meeting.",
    },
  ];

  const commentMentions: CommentMentionSeed[] = [
    { id: "mention_scale_001", commentId: "comment_scale_001", userId: "user_demo" },
    { id: "mention_scale_002", commentId: "comment_scale_006", userId: "user_alice" },
    { id: "mention_scale_003", commentId: "comment_scale_008", userId: "user_alex" },
  ];

  const shareLinks: ShareLinkSeed[] = [
    { id: "share_scale_001", token: "share_paper_attention", pageId: "page_paper_attention", createdById: "user_demo", isActive: true },
    { id: "share_scale_002", token: "share_reading_group", pageId: "page_reading_group", createdById: "user_demo", isActive: true },
    { id: "share_scale_003", token: "share_trip_sapporo", pageId: "page_trip_sapporo", createdById: "user_demo", isActive: true },
    { id: "share_scale_004", token: "share_launch_handbook", pageId: "page_launch_readiness_handbook", createdById: "user_demo", isActive: true },
    { id: "share_scale_005", token: "share_proposal_efficient_lm", pageId: "page_proposal_efficient_lm", createdById: "user_alex", isActive: true },
  ];

  const pagePermissions: PagePermissionSeed[] = [
    { id: "perm_scale_001", pageId: "page_reading_group", userId: "user_alice", role: "editor" },
    { id: "perm_scale_002", pageId: "page_lab_meetings", userId: "user_alex", role: "editor" },
    { id: "perm_scale_003", pageId: "page_lab_meetings", userId: "user_mina", role: "commenter" },
    { id: "perm_scale_004", pageId: "page_paper_attention", userId: "user_alice", role: "editor" },
    { id: "perm_scale_005", pageId: "page_proposal_efficient_lm", userId: "user_alex", role: "editor" },
    { id: "perm_scale_006", pageId: "page_proposal_multimodal_eval", userId: "user_alice", role: "editor" },
    { id: "perm_scale_007", pageId: "page_launch_readiness_handbook", userId: "user_alex", role: "editor" },
    { id: "perm_scale_008", pageId: "page_incident_chronicle", userId: "user_alice", role: "commenter" },
    { id: "perm_scale_009", pageId: "page_customer_interview_digest", userId: "user_alice", role: "editor" },
    { id: "perm_scale_010", pageId: "page_customer_interview_digest", userId: "user_mina", role: "viewer" },
    { id: "perm_scale_011", pageId: "page_trip_sapporo", userId: "user_alex", role: "viewer" },
  ];

  const attachments: AttachmentSeed[] = [
    {
      id: "attachment_scale_001",
      pageId: "page_paper_attention",
      uploadedById: "user_demo",
      fileName: "attention-is-all-you-need.pdf",
      fileUrl: "/uploads/attention-is-all-you-need.pdf",
      mimeType: "application/pdf",
      sizeBytes: 421133,
    },
    {
      id: "attachment_scale_002",
      pageId: "page_paper_bert",
      uploadedById: "user_demo",
      fileName: "bert-paper.pdf",
      fileUrl: "/uploads/bert-paper.pdf",
      mimeType: "application/pdf",
      sizeBytes: 388210,
    },
    {
      id: "attachment_scale_003",
      pageId: "page_paper_resnet",
      uploadedById: "user_demo",
      fileName: "resnet-paper.pdf",
      fileUrl: "/uploads/resnet-paper.pdf",
      mimeType: "application/pdf",
      sizeBytes: 297441,
    },
    {
      id: "attachment_scale_004",
      pageId: "page_dataset_imagenet",
      uploadedById: "user_demo",
      fileName: "imagenet-readme.txt",
      fileUrl: "/uploads/imagenet-readme.txt",
      mimeType: "text/plain",
      sizeBytes: 12880,
    },
    {
      id: "attachment_scale_005",
      pageId: "page_lab_meeting_2026_04_17",
      uploadedById: "user_alex",
      fileName: "rope-vs-alibi-ablation.png",
      fileUrl: "/uploads/rope-vs-alibi-ablation.png",
      mimeType: "image/png",
      sizeBytes: 154322,
    },
    {
      id: "attachment_scale_006",
      pageId: "page_trip_busan",
      uploadedById: "user_demo",
      fileName: "busan-itinerary-map.png",
      fileUrl: "/uploads/busan-itinerary-map.png",
      mimeType: "image/png",
      sizeBytes: 96214,
    },
    {
      id: "attachment_scale_007",
      pageId: "page_trip_sapporo",
      uploadedById: "user_demo",
      fileName: "sapporo-snow-festival-grounds.png",
      fileUrl: "/uploads/sapporo-snow-festival-grounds.png",
      mimeType: "image/png",
      sizeBytes: 102447,
    },
    {
      id: "attachment_scale_008",
      pageId: "page_launch_readiness_handbook",
      uploadedById: "user_alex",
      fileName: "launch-readiness-checklist.pdf",
      fileUrl: "/uploads/launch-readiness-checklist.pdf",
      mimeType: "application/pdf",
      sizeBytes: 184230,
    },
    {
      id: "attachment_scale_009",
      pageId: "page_incident_chronicle",
      uploadedById: "user_demo",
      fileName: "incident-trend-q2.csv",
      fileUrl: "/uploads/incident-trend-q2.csv",
      mimeType: "text/csv",
      sizeBytes: 5421,
    },
  ];

  const workspaceTabs: WorkspaceTabSeed[] = [
    // demo's research lab tabs — point to the real research pages
    { id: "tab_demo_lab_4", membershipId: "membership_demo_lab", pageId: "page_research_library", position: 0 },
    { id: "tab_demo_lab_5", membershipId: "membership_demo_lab", pageId: "page_reading_group", position: 1 },
    { id: "tab_demo_lab_6", membershipId: "membership_demo_lab", pageId: "page_lab_meetings", position: 2 },
    { id: "tab_demo_lab_7", membershipId: "membership_demo_lab", pageId: "page_project_proposals", position: 3 },
    { id: "tab_demo_lab_8", membershipId: "membership_demo_lab", pageId: "page_paper_attention", position: 4 },
    // demo's HQ tabs — additional ones for the moved hubs
    { id: "tab_demo_hq_5", membershipId: "membership_demo_hq", pageId: "page_launch_ops_hub", position: 4 },
    { id: "tab_demo_hq_6", membershipId: "membership_demo_hq", pageId: "page_incident_response_hub", position: 5 },
    { id: "tab_demo_hq_7", membershipId: "membership_demo_hq", pageId: "page_customer_research_hub", position: 6 },
    // alex
    { id: "tab_alex_3", membershipId: "membership_alex_hq", pageId: "page_launch_readiness_handbook", position: 2 },
    { id: "tab_alex_4", membershipId: "membership_alex_hq", pageId: "page_incident_chronicle", position: 3 },
    // alice
    { id: "tab_alice_1", membershipId: "membership_alice_hq", pageId: "page_team_notes", position: 0 },
    { id: "tab_alice_2", membershipId: "membership_alice_hq", pageId: "page_customer_interview_digest", position: 1 },
    { id: "tab_alice_3", membershipId: "membership_alice_hq", pageId: "page_marketing_hub", position: 2 },
    // mina
    { id: "tab_mina_1", membershipId: "membership_mina_hq", pageId: "page_team_notes", position: 0 },
    { id: "tab_mina_2", membershipId: "membership_mina_hq", pageId: "page_incident_response_hub", position: 1 },
    // demo personal — extras
    { id: "tab_demo_personal_4", membershipId: "membership_demo_personal", pageId: "page_trip_itineraries", position: 3 },
    { id: "tab_demo_personal_5", membershipId: "membership_demo_personal", pageId: "page_trip_sapporo", position: 4 },
  ];

  return { comments, commentMentions, shareLinks, pagePermissions, attachments, workspaceTabs };
}

// =====================================================================
// ENTRY POINT
// =====================================================================

export function buildScaledSeed() {
  const research = buildResearchLabPages();
  const hq = buildHQPages();
  const trips = buildTripPages();
  const allPagesWithBlocks = [...research, ...hq, ...trips];

  const pages = allPagesWithBlocks.map((p) => p.page);
  const blocks = allPagesWithBlocks.flatMap((p) => p.blocks);

  const projectData = buildProjectRows();
  const taskData = buildTaskRows();
  const travelData = buildTravelRows();
  const budgetData = buildTravelBudgetRows();

  const databaseRows = [
    ...projectData.rows,
    ...taskData.rows,
    ...travelData.rows,
    ...budgetData.rows,
  ];
  const databaseCellValues = [
    ...projectData.cells,
    ...taskData.cells,
    ...travelData.cells,
    ...budgetData.cells,
  ];

  const extras = buildExtras();

  return {
    pages,
    blocks,
    databaseRows,
    databaseCellValues,
    workspaceTabs: extras.workspaceTabs,
    comments: extras.comments,
    commentMentions: extras.commentMentions,
    shareLinks: extras.shareLinks,
    pagePermissions: extras.pagePermissions,
    attachments: extras.attachments,
  };
}
