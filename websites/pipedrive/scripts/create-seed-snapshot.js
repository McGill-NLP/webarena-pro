const Database = require("better-sqlite3");
const path = require("path");
const fs = require("fs");

const dataDir = path.join(process.cwd(), "data");
const srcDb = path.join(dataDir, "crm.db");
const dstDb = path.join(dataDir, "crm.seed.db");

async function main() {
  if (!fs.existsSync(srcDb)) {
    throw new Error(`Source DB not found: ${srcDb}`);
  }

  const db = new Database(srcDb);
  try {
    // Flush WAL changes to the main DB before snapshotting.
    db.pragma("wal_checkpoint(TRUNCATE)");

    if (fs.existsSync(dstDb)) {
      fs.rmSync(dstDb, { force: true });
    }

    await db.backup(dstDb);
    console.log("[build] Created seed snapshot:", dstDb);
  } finally {
    db.close();
  }
}

main().catch((err) => {
  console.error("[build] Failed to create seed snapshot:", err);
  process.exit(1);
});
