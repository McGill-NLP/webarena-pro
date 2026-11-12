const fs = require("fs");
const path = require("path");
const Database = require("better-sqlite3");

const appRoot = process.cwd();
const dataDir = path.join(appRoot, "data");
const liveDbPath = path.join(dataDir, "crm.db");
const seedDbPath = path.join(appRoot, "seed", "crm.db");
const forceRestore = process.env.RESET_TO_SEED_ON_STARTUP === "1";

function copySeed() {
  if (!fs.existsSync(seedDbPath)) {
    console.error("[startup] Seed database snapshot not found at", seedDbPath);
    return;
  }

  fs.mkdirSync(dataDir, { recursive: true });
  fs.copyFileSync(seedDbPath, liveDbPath);

  const walPath = `${liveDbPath}-wal`;
  const shmPath = `${liveDbPath}-shm`;
  if (fs.existsSync(walPath)) fs.rmSync(walPath, { force: true });
  if (fs.existsSync(shmPath)) fs.rmSync(shmPath, { force: true });

  console.log("[startup] Restored crm.db from seed snapshot.");
}

function hasUsableDb() {
  if (!fs.existsSync(liveDbPath)) return false;

  const stats = fs.statSync(liveDbPath);
  // Tiny sqlite files are typically empty/newly-created DBs with no seeded data.
  if (stats.size < 4096) return false;

  try {
    const db = new Database(liveDbPath, { readonly: true });

    // Consider DB usable only if core seeded tables contain records.
    const usersCount = db.prepare("SELECT COUNT(*) AS count FROM users").get().count;
    const dealsCount = db.prepare("SELECT COUNT(*) AS count FROM deals").get().count;

    db.close();
    return usersCount > 0 && dealsCount > 0;
  } catch {
    return false;
  }

}

try {
  if (forceRestore) {
    console.log("[startup] RESET_TO_SEED_ON_STARTUP=1, restoring canonical seed database.");
    copySeed();
  } else if (!hasUsableDb()) {
    copySeed();
  } else {
    console.log("[startup] Existing crm.db detected; keeping current data.");
  }
} catch (error) {
  console.error("[startup] Failed checking/restoring DB:", error);
}
