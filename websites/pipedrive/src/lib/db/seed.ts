import Database from "better-sqlite3";
import bcrypt from "bcryptjs";
import path from "path";
import fs from "fs";

const dataDir = path.join(process.cwd(), "data");
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

const db = new Database(path.join(dataDir, "crm.db"));
db.pragma("journal_mode = WAL");

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    domain TEXT,
    industry TEXT,
    size TEXT,
    website TEXT,
    phone TEXT,
    address TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    company_id INTEGER,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    job_title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS pipelines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS pipeline_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    probability INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    pipeline_id INTEGER NOT NULL,
    stage_id INTEGER NOT NULL,
    contact_id INTEGER,
    company_id INTEGER,
    title TEXT NOT NULL,
    value REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open',
    position INTEGER NOT NULL DEFAULT 0,
    expected_close_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    deal_id INTEGER,
    contact_id INTEGER,
    company_id INTEGER,
    type TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT,
    due_date TEXT,
    is_done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );
`);

const now = new Date().toISOString();
const passwordHash = bcrypt.hashSync("admin123", 10);

// Wipe all existing data for the admin user so re-running the seed is safe.
const existingUser = db.prepare("SELECT id FROM users WHERE email = ?").get("admin@local.host") as { id: number } | undefined;
if (existingUser) {
  const uid = existingUser.id;
  db.prepare("DELETE FROM activities WHERE user_id = ?").run(uid);
  db.prepare("DELETE FROM deals WHERE user_id = ?").run(uid);
  const oldPipelines = db.prepare("SELECT id FROM pipelines WHERE user_id = ?").all(uid) as { id: number }[];
  for (const p of oldPipelines) {
    db.prepare("DELETE FROM pipeline_stages WHERE pipeline_id = ?").run(p.id);
  }
  db.prepare("DELETE FROM pipelines WHERE user_id = ?").run(uid);
  db.prepare("DELETE FROM contacts WHERE user_id = ?").run(uid);
  db.prepare("DELETE FROM companies WHERE user_id = ?").run(uid);
  db.prepare("DELETE FROM users WHERE id = ?").run(uid);
}

db.prepare("INSERT INTO users (email, password, name, created_at) VALUES (?, ?, ?, ?)").run("admin@local.host", passwordHash, "Alex Johnson", now);

const userId = (db.prepare("SELECT id FROM users WHERE email = ?").get("admin@local.host") as { id: number }).id;

// ---- Companies (50) ----
const companyData = [
  ["TechCorp Inc.", "techcorp.io", "Technology", "50-200", "https://techcorp.io", "+1-415-555-0101", "123 Market St, San Francisco, CA"],
  ["Global Solutions Ltd.", "globalsolutions.com", "Consulting", "200-500", "https://globalsolutions.com", "+1-212-555-0202", "456 5th Ave, New York, NY"],
  ["StartupXYZ", "startupxyz.co", "Technology", "1-10", "https://startupxyz.co", "+1-512-555-0303", "789 Congress Ave, Austin, TX"],
  ["Enterprise Partners", "enterprisepartners.com", "Finance", "500+", "https://enterprisepartners.com", "+1-312-555-0404", "321 LaSalle St, Chicago, IL"],
  ["Bright Horizons Analytics", "brightanalytics.com", "Analytics", "50-200", "https://brightanalytics.com", "+1-650-555-0505", "500 El Camino Real, Palo Alto, CA"],
  ["Nexus Dynamics", "nexusdynamics.io", "Technology", "10-50", "https://nexusdynamics.io", "+1-206-555-0606", "100 Pike St, Seattle, WA"],
  ["Apex Financial Group", "apexfinancial.com", "Finance", "200-500", "https://apexfinancial.com", "+1-617-555-0707", "1 Federal St, Boston, MA"],
  ["Vantage Retail Corp", "vantageretail.com", "Retail", "500+", "https://vantageretail.com", "+1-214-555-0808", "1000 Commerce St, Dallas, TX"],
  ["Pinnacle Healthcare", "pinnaclehc.com", "Healthcare", "200-500", "https://pinnaclehc.com", "+1-305-555-0909", "200 Brickell Ave, Miami, FL"],
  ["Cascade Logistics", "cascadelogistics.net", "Logistics", "50-200", "https://cascadelogistics.net", "+1-503-555-1010", "300 NW 6th Ave, Portland, OR"],
  ["Summit Media Group", "summitmedia.com", "Media", "10-50", "https://summitmedia.com", "+1-310-555-1111", "8000 Sunset Blvd, Los Angeles, CA"],
  ["Ironclad Security", "ironclaadsec.com", "Security", "10-50", "https://ironclaadsec.com", "+1-703-555-1212", "1600 Wilson Blvd, Arlington, VA"],
  ["BlueSky Software", "blueskysoft.io", "Technology", "50-200", "https://blueskysoft.io", "+1-415-555-1313", "555 Mission St, San Francisco, CA"],
  ["Redwood Capital", "redwoodcap.com", "Finance", "50-200", "https://redwoodcap.com", "+1-415-555-1414", "100 California St, San Francisco, CA"],
  ["Momentum Marketing", "momentummarketing.com", "Marketing", "10-50", "https://momentummarketing.com", "+1-646-555-1515", "220 E 42nd St, New York, NY"],
  ["Orbit Technologies", "orbittech.io", "Technology", "10-50", "https://orbittech.io", "+1-512-555-1616", "500 W 2nd St, Austin, TX"],
  ["Horizon Renewable Energy", "horizonre.com", "Energy", "200-500", "https://horizonre.com", "+1-303-555-1717", "1700 Lincoln St, Denver, CO"],
  ["CloudNine SaaS", "cloudninesaas.com", "Technology", "50-200", "https://cloudninesaas.com", "+1-408-555-1818", "400 N 1st St, San Jose, CA"],
  ["Atlas Consulting Group", "atlasconsulting.com", "Consulting", "50-200", "https://atlasconsulting.com", "+1-202-555-1919", "1300 Pennsylvania Ave, Washington, DC"],
  ["DataStream Analytics", "datastreamanalytics.com", "Analytics", "10-50", "https://datastreamanalytics.com", "+1-206-555-2020", "600 1st Ave, Seattle, WA"],
  ["Spartan Manufacturing", "spartanmfg.com", "Manufacturing", "500+", "https://spartanmfg.com", "+1-313-555-2121", "1 Spartan Way, Detroit, MI"],
  ["Greenfield Biotech", "greenfieldbio.com", "Biotech", "10-50", "https://greenfieldbio.com", "+1-858-555-2222", "9000 Torrey Pines Rd, San Diego, CA"],
  ["Velocity Ventures", "velocityvc.com", "Finance", "1-10", "https://velocityvc.com", "+1-415-555-2323", "4 Embarcadero Ctr, San Francisco, CA"],
  ["Titan Telecom", "titantelecom.net", "Telecom", "500+", "https://titantelecom.net", "+1-404-555-2424", "75 5th St NW, Atlanta, GA"],
  ["Northstar Education", "northstaredu.org", "Education", "200-500", "https://northstaredu.org", "+1-651-555-2525", "225 Smith Ave S, St. Paul, MN"],
  ["Cerulean Cybersecurity", "cerueleancyber.com", "Security", "10-50", "https://cerueleancyber.com", "+1-512-555-2626", "700 Lavaca St, Austin, TX"],
  ["Quantum Dynamics Corp", "quantumdynamics.com", "Technology", "50-200", "https://quantumdynamics.com", "+1-617-555-2727", "1 Cambridge Ctr, Cambridge, MA"],
  ["Falcon Aerospace", "falconaero.com", "Aerospace", "500+", "https://falconaero.com", "+1-310-555-2828", "2000 E Imperial Hwy, El Segundo, CA"],
  ["Sterling Insurance", "sterlinginsurance.com", "Insurance", "200-500", "https://sterlinginsurance.com", "+1-860-555-2929", "100 Constitution Plaza, Hartford, CT"],
  ["Pacific Trade Co.", "pacifictrade.co", "Trade", "50-200", "https://pacifictrade.co", "+1-808-555-3030", "1001 Bishop St, Honolulu, HI"],
  ["Meridian Law Group", "meridianlaw.com", "Legal", "10-50", "https://meridianlaw.com", "+1-212-555-3131", "375 Park Ave, New York, NY"],
  ["NovaBuild Construction", "novabuild.com", "Construction", "200-500", "https://novabuild.com", "+1-602-555-3232", "2800 N Central Ave, Phoenix, AZ"],
  ["Prism Design Studio", "prismdesign.io", "Design", "1-10", "https://prismdesign.io", "+1-503-555-3333", "817 SW 2nd Ave, Portland, OR"],
  ["Zenith Pharmaceuticals", "zenithpharma.com", "Pharma", "500+", "https://zenithpharma.com", "+1-201-555-3434", "1 Zenith Plaza, Newark, NJ"],
  ["Anchor Real Estate", "anchorrealestate.com", "Real Estate", "50-200", "https://anchorrealestate.com", "+1-786-555-3535", "701 Brickell Ave, Miami, FL"],
  ["Ember AI", "emberai.io", "Technology", "1-10", "https://emberai.io", "+1-415-555-3636", "149 New Montgomery St, San Francisco, CA"],
  ["Tidal Wave Media", "tidalwavemedia.com", "Media", "10-50", "https://tidalwavemedia.com", "+1-323-555-3737", "6000 W Sunset Blvd, Hollywood, CA"],
  ["Granite Bank", "granitebank.com", "Finance", "500+", "https://granitebank.com", "+1-603-555-3838", "1 Granite Sq, Manchester, NH"],
  ["Solar Path Energy", "solarpathsenergy.com", "Energy", "10-50", "https://solarpathsenergy.com", "+1-520-555-3939", "100 N Stone Ave, Tucson, AZ"],
  ["Nimbus Cloud Services", "nimbuscloud.io", "Technology", "50-200", "https://nimbuscloud.io", "+1-737-555-4040", "201 W 5th St, Austin, TX"],
  ["Cardinal Health Systems", "cardinalhealth.com", "Healthcare", "500+", "https://cardinalhealth.com", "+1-614-555-4141", "7000 Cardinal Pl, Dublin, OH"],
  ["Flux Robotics", "fluxrobotics.io", "Robotics", "10-50", "https://fluxrobotics.io", "+1-412-555-4242", "4516 Henry St, Pittsburgh, PA"],
  ["Coastal Shipping Lines", "coastalshipping.com", "Logistics", "200-500", "https://coastalshipping.com", "+1-504-555-4343", "1200 Port of New Orleans Pl, New Orleans, LA"],
  ["Vertex Gaming", "vertexgaming.com", "Gaming", "50-200", "https://vertexgaming.com", "+1-425-555-4444", "333 108th Ave NE, Bellevue, WA"],
  ["Ironwood Furniture", "ironwoodfurniture.com", "Retail", "10-50", "https://ironwoodfurniture.com", "+1-919-555-4545", "2000 Highwoods Blvd, Raleigh, NC"],
  ["Strata Fintech", "stratafintech.com", "Fintech", "10-50", "https://stratafintech.com", "+1-646-555-4646", "11 Wall St, New York, NY"],
  ["Compass Recruiting", "compassrecruiting.com", "HR", "10-50", "https://compassrecruiting.com", "+1-312-555-4747", "225 W Randolph St, Chicago, IL"],
  ["Radiant Solar", "radiantsolar.com", "Energy", "50-200", "https://radiantsolar.com", "+1-702-555-4848", "300 S 4th St, Las Vegas, NV"],
  ["Lynx Cybersecurity", "lynxcyber.com", "Security", "50-200", "https://lynxcyber.com", "+1-512-555-4949", "600 Congress Ave, Austin, TX"],
  ["Phoenix Logistics Hub", "phoenixlogistics.com", "Logistics", "200-500", "https://phoenixlogistics.com", "+1-480-555-5050", "2400 E Camelback Rd, Phoenix, AZ"],
];

const insertCompany = db.prepare(
  "INSERT INTO companies (user_id, name, domain, industry, size, website, phone, address, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
);
for (const [name, domain, industry, size, website, phone, address] of companyData) {
  insertCompany.run(userId, name, domain, industry, size, website, phone, address, now, now);
}

const companies = db.prepare("SELECT id, name FROM companies WHERE user_id = ?").all(userId) as { id: number; name: string }[];
const companyIds = companies.map((c) => c.id);
const companyByName = Object.fromEntries(companies.map((c) => [c.name, c.id]));

// ---- Contacts (60) ----
const firstNames = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "William", "Barbara",
  "David", "Susan", "Richard", "Jessica", "Joseph", "Sarah", "Thomas", "Karen", "Charles", "Lisa",
  "Christopher", "Nancy", "Daniel", "Betty", "Matthew", "Margaret", "Anthony", "Sandra", "Mark", "Ashley",
  "Donald", "Emily", "Paul", "Kimberly", "Andrew", "Donna", "Joshua", "Michelle", "Kenneth", "Carol",
  "Kevin", "Amanda", "Brian", "Melissa", "George", "Deborah", "Timothy", "Stephanie", "Ronald", "Rebecca",
  "Edward", "Sharon", "Jason", "Laura", "Jeffrey", "Cynthia", "Ryan", "Kathleen", "Jacob", "Amy"];

const lastNames = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
  "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
  "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
  "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
  "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts",
  "Gomez", "Phillips", "Evans", "Turner", "Diaz", "Parker", "Cruz", "Edwards", "Collins", "Reyes"];

const jobTitles = ["CEO", "CTO", "CFO", "VP of Sales", "VP of Marketing", "Product Manager", "Sales Director",
  "Account Executive", "Business Development Manager", "Operations Manager", "Engineering Manager",
  "Head of Finance", "Partner", "Director of IT", "CMO", "COO", "Procurement Manager", "HR Director"];

const insertContact = db.prepare(
  "INSERT INTO contacts (user_id, company_id, first_name, last_name, email, phone, job_title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
);

for (let i = 0; i < 60; i++) {
  const fn = firstNames[i];
  const ln = lastNames[i];
  const companyId = companyIds[i % companyIds.length];
  const company = companies.find((c) => c.id === companyId)!;
  const domain = companyData[companyIds.indexOf(companyId) % companyData.length]?.[1] ?? "example.com";
  const email = `${fn.toLowerCase()}.${ln.toLowerCase()}@${domain}`;
  const phone = `+1-${String(200 + i).padStart(3, "0")}-555-${String(1000 + i).padStart(4, "0")}`;
  const title = jobTitles[i % jobTitles.length];
  insertContact.run(userId, companyId, fn, ln, email, phone, title, now, now);
}

const contacts = db.prepare("SELECT id, first_name, last_name FROM contacts WHERE user_id = ?").all(userId) as { id: number; first_name: string; last_name: string }[];
const contactIds = contacts.map((c) => c.id);

// ---- Pipeline ----
const insertPipeline = db.prepare(
  "INSERT INTO pipelines (user_id, name, created_at) VALUES (?, ?, ?)"
);
insertPipeline.run(userId, "Sales Pipeline", now);
const pipeline = db.prepare("SELECT id FROM pipelines WHERE user_id = ? AND name = ?").get(userId, "Sales Pipeline") as { id: number };
const pipelineId = pipeline.id;

const insertStage = db.prepare(
  "INSERT INTO pipeline_stages (pipeline_id, name, probability, position, created_at) VALUES (?, ?, ?, ?, ?)"
);
insertStage.run(pipelineId, "Lead", 10, 0, now);
insertStage.run(pipelineId, "Qualified", 25, 1, now);
insertStage.run(pipelineId, "Proposal", 50, 2, now);
insertStage.run(pipelineId, "Negotiation", 75, 3, now);
insertStage.run(pipelineId, "Closed Won", 100, 4, now);

const stages = db.prepare("SELECT id, name FROM pipeline_stages WHERE pipeline_id = ?").all(pipelineId) as { id: number; name: string }[];
const stageByName = Object.fromEntries(stages.map((s) => [s.name, s.id]));
const stageIds = stages.map((s) => s.id);

// ---- Deals (110) spread from Jan 2024 → Apr 2026 ----
const SEED_START = new Date("2024-01-01T00:00:00.000Z");
const SEED_END   = new Date("2026-04-30T00:00:00.000Z");
const SPAN_DAYS  = Math.floor((SEED_END.getTime() - SEED_START.getTime()) / 86400000); // ~850

function addDays(base: Date, days: number): Date {
  const d = new Date(base);
  d.setDate(d.getDate() + days);
  return d;
}

function isoAt(dayOffset: number, extra = 0): string {
  const d = addDays(SEED_START, dayOffset + extra);
  return d > SEED_END ? SEED_END.toISOString() : d.toISOString();
}

// Status distribution: old deals (low i) → mostly won/lost; recent (high i) → open
function dealStatus(i: number): "open" | "won" | "lost" {
  if (i < 30) {
    // Jan–Jul 2024: mostly resolved
    return (["won","won","lost","won","lost","won","won","lost","won","lost"] as const)[i % 10];
  }
  if (i < 65) {
    // Jul 2024–Mar 2025: mixed
    return (["won","open","lost","open","open","won","lost","open"] as const)[i % 8];
  }
  if (i < 85) {
    // Mar–Nov 2025: leaning open
    return (["open","open","open","won","open","lost","open","open"] as const)[i % 8];
  }
  // Nov 2025–Apr 2026: all open
  return "open";
}

const dealTitles = [
  "Enterprise License Agreement", "Platform Subscription Renewal", "Professional Services Package",
  "API Integration Project", "Cloud Migration Contract", "Security Audit Service",
  "Annual Support Contract", "Custom Development Agreement", "Data Analytics Solution",
  "Marketing Automation Setup", "CRM Implementation", "ERP Integration",
  "Mobile App Development", "SaaS Onboarding Package", "Consulting Retainer",
  "Network Infrastructure Upgrade", "Staff Augmentation Deal", "Training Program",
  "Managed Services Contract", "Digital Transformation Initiative",
];

const insertDeal = db.prepare(
  "INSERT INTO deals (user_id, pipeline_id, stage_id, contact_id, company_id, title, value, status, position, expected_close_date, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
);

const openStageCount = stageIds.length - 1; // exclude "Closed Won"
const stagePositions: Record<number, number> = {};
for (const sid of stageIds) stagePositions[sid] = 0;

for (let i = 0; i < 110; i++) {
  const status   = dealStatus(i);
  const baseDayOffset = Math.floor((i / 110) * SPAN_DAYS);
  const createdAt = isoAt(baseDayOffset);

  const stageId = status === "won"
    ? stageByName["Closed Won"]
    : stageIds[i % openStageCount];

  const contactId = contactIds[i % contactIds.length];
  const companyId = companyIds[i % companyIds.length];
  const company   = companies.find((c) => c.id === companyId)!;
  const title     = `${company.name} - ${dealTitles[i % dealTitles.length]}`;
  const value     = Math.round((5000 + (i * 1973) % 120000) / 100) * 100;

  let expectedCloseDate: string | null;
  let updatedAt: string;

  if (status === "won") {
    // Closed 20–100 days after creation
    const daysToClose = 20 + (i * 17) % 81;
    updatedAt = isoAt(baseDayOffset, daysToClose);
    expectedCloseDate = null;
  } else if (status === "lost") {
    // Lost 10–60 days after creation
    const daysToLose = 10 + (i * 13) % 51;
    updatedAt = isoAt(baseDayOffset, daysToLose);
    expectedCloseDate = null;
  } else {
    // Open: expected close 30–180 days after creation (some overdue, some future)
    const daysToClose = 30 + (i * 23) % 151;
    expectedCloseDate = addDays(SEED_START, baseDayOffset + daysToClose).toISOString().split("T")[0];
    updatedAt = createdAt;
  }

  const pos = stagePositions[stageId]++;
  insertDeal.run(
    userId, pipelineId, stageId, contactId, companyId,
    title, value, status, pos,
    expectedCloseDate, createdAt, updatedAt
  );
}

// ---- Activities (50) spread across the same period ----
const activityTypes = ["call", "email", "meeting", "task"];
const activitySubjects = [
  "Initial discovery call", "Send pricing proposal", "Follow up on demo", "Contract review meeting",
  "Onboarding kickoff", "Quarterly business review", "Technical requirements call", "Negotiate terms",
  "Send case study", "Schedule product demo", "Check in after trial", "Renewal discussion",
  "Introduction email", "Upsell opportunity review", "Executive sponsor meeting",
];

const dealRows = db.prepare("SELECT id FROM deals WHERE user_id = ?").all(userId) as { id: number }[];
const dealIdList = dealRows.map((d) => d.id);

const insertActivity = db.prepare(
  "INSERT INTO activities (user_id, deal_id, contact_id, company_id, type, subject, description, due_date, is_done, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
);

const TODAY = new Date();

for (let i = 0; i < 50; i++) {
  const dealId    = dealIdList[i % dealIdList.length];
  const contactId = contactIds[i % contactIds.length];
  const companyId = companyIds[i % companyIds.length];
  const type      = activityTypes[i % activityTypes.length];
  const subject   = activitySubjects[i % activitySubjects.length];

  // Spread activity dates across seed period + a bit beyond
  const baseDayOffset = Math.floor((i / 50) * (SPAN_DAYS + 60));
  const actDate = addDays(SEED_START, baseDayOffset);
  const isPast  = actDate < TODAY;
  // Past activities: mostly done (every 4th still open); future: all pending
  const isDone  = isPast ? (i % 4 !== 0 ? 1 : 0) : 0;
  const dueDate      = actDate.toISOString().split("T")[0];
  const actCreatedAt = actDate.toISOString();

  insertActivity.run(
    userId, dealId, contactId, companyId,
    type, subject, null, dueDate, isDone,
    actCreatedAt, actCreatedAt
  );
}

console.log("Database seeded successfully.");
db.close();
