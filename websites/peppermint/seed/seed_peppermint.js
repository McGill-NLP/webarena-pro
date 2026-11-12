#!/usr/bin/env node
/**
 * Peppermint seeder — runs INSIDE the container via docker exec.
 * Uses Node 18 built-in fetch; no external dependencies needed.
 *
 * Usage (from seed-local.sh):
 *   docker cp seed/seed_peppermint.js <container>:/tmp/seed_peppermint.js
 *   docker cp seed_data.json           <container>:/tmp/seed_data.json
 *   docker exec <container> node /tmp/seed_peppermint.js
 */

const fs = require("fs");

const BASE_URL = process.env.PEPPERMINT_URL || "http://127.0.0.1:5003";
const ADMIN_EMAIL = process.env.ADMIN_EMAIL || "admin@admin.com";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "1234";
const DATA_FILE = process.env.SEED_DATA_FILE || "/tmp/seed_data.json";
const EXPANSION_FILES = (process.env.SEED_EXPANSION_FILES || "")
  .split(":")
  .map(value => value.trim())
  .filter(Boolean);

const baseData = JSON.parse(fs.readFileSync(DATA_FILE, "utf8"));
const data = {
  ...baseData,
  clients: [...(baseData.clients ?? [])],
  users: [...(baseData.users ?? [])],
  tickets: [...(baseData.tickets ?? [])],
};

for (const expansionFile of EXPANSION_FILES) {
  const expansion = JSON.parse(fs.readFileSync(expansionFile, "utf8"));
  const clients = expansion.clients ?? [];
  const users = expansion.users ?? [];
  const tickets = expansion.tickets ?? [];
  data.clients.push(...clients);
  data.users.push(...users);
  data.tickets.push(...tickets);
  console.log(
    `Loaded ${clients.length} additive clients, ${users.length} additive users, ` +
    `and ${tickets.length} additive tickets ` +
    `from ${expansionFile}`,
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function api(method, path, token, body) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json;
  try { json = JSON.parse(text); } catch { json = {}; }
  return { ok: res.ok, status: res.status, json, text };
}

async function login(email, password) {
  const r = await api("POST", "/api/v1/auth/login", null, { email, password });
  if (r.ok) {
    let tokenUserId = null;
    try {
      const payloadB64 = String(r.json.token || "").split(".")[1];
      if (payloadB64) {
        const payload = JSON.parse(Buffer.from(payloadB64, "base64url").toString("utf8"));
        tokenUserId = payload?.data?.id ?? null;
      }
    } catch {}

    return {
      token: r.json.token,
      user: r.json.user ?? null,
      userId: r.json.user?.id ?? tokenUserId,
    };
  }
  console.error(`  LOGIN FAILED ${r.status}: ${r.text.slice(0, 120)}`);
  return null;
}

async function waitForApi(maxWait = 120) {
  console.log(`Waiting for API at ${BASE_URL} ...`);
  const deadline = Date.now() + maxWait * 1000;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`${BASE_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: ADMIN_EMAIL, password: ADMIN_PASSWORD }),
        signal: AbortSignal.timeout(5000),
      });
      if (r.status < 500) { console.log("  API is up."); return true; }
    } catch {}
    process.stdout.write(".");
    await new Promise(r => setTimeout(r, 3000));
  }
  console.error(`\nERROR: API not ready after ${maxWait}s`);
  return false;
}

function richText(text) {
  return [{
    type: "text",
    text,
    styles: {},
  }];
}

function ticketDetailBlocks(value) {
  const text = String(value ?? "").replace(/\r\n?/g, "\n");
  const blocks = [];

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;

    const numbered = line.match(/^\d+\.\s+(.+)$/);
    const bulleted = line.match(/^[-*]\s+(.+)$/);
    const heading = line.length <= 120 && /^[^:]+:$/.test(line);

    if (heading) {
      blocks.push({
        type: "heading",
        props: {
          textColor: "default",
          backgroundColor: "default",
          textAlignment: "left",
          level: 2,
        },
        content: richText(line.slice(0, -1)),
        children: [],
      });
    } else if (numbered || bulleted) {
      blocks.push({
        type: numbered ? "numberedListItem" : "bulletListItem",
        props: {
          textColor: "default",
          backgroundColor: "default",
          textAlignment: "left",
        },
        content: richText((numbered || bulleted)[1]),
        children: [],
      });
    } else {
      blocks.push({
        type: "paragraph",
        props: {
          textColor: "default",
          backgroundColor: "default",
          textAlignment: "left",
        },
        content: richText(line),
        children: [],
      });
    }
  }

  return blocks.length > 0 ? blocks : [{
    type: "paragraph",
    props: {
      textColor: "default",
      backgroundColor: "default",
      textAlignment: "left",
    },
    content: [],
    children: [],
  }];
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  if (!await waitForApi()) process.exit(1);

  // Extra pause for Prisma to finish seeding
  await new Promise(r => setTimeout(r, 5000));

  // ── Login as admin ──────────────────────────────────────────────────────
  console.log(`\nLogging in as ${ADMIN_EMAIL}...`);
  let adminLogin = await login(ADMIN_EMAIL, ADMIN_PASSWORD);
  if (!adminLogin) {
    await new Promise(r => setTimeout(r, 10000));
    adminLogin = await login(ADMIN_EMAIL, ADMIN_PASSWORD);
  }
  if (!adminLogin) { console.error("Failed to login as admin. Exiting."); process.exit(1); }
  const adminToken = adminLogin.token;
  console.log("  OK");

  const adminId = adminLogin.userId ?? null;

  const userTokens = { [ADMIN_EMAIL]: adminToken };
  const userIds    = { [ADMIN_EMAIL]: adminId };
  const userNames  = { [ADMIN_EMAIL]: adminLogin.user?.name ?? "Admin" };
  const userProfiles = {
    [ADMIN_EMAIL]: {
      id: adminId,
      name: adminLogin.user?.name ?? "Admin",
      email: ADMIN_EMAIL,
      role: "admin",
    },
  };

  // ── Create users ────────────────────────────────────────────────────────
  console.log(`\nCreating ${data.users.length} users...`);
  for (const u of data.users) {
    const r = await api("POST", "/api/v1/auth/user/register", adminToken, {
      name: u.name, email: u.email, password: u.password, admin: u.admin ?? false,
    });
    if (r.ok) {
      const uid = r.json.id ?? r.json.user?.id;
      userIds[u.email] = uid;
      userNames[u.email] = u.name;
      console.log(`  Created: ${u.email} (id=${uid})`);
    } else {
      console.log(`  Skipped (may exist): ${u.email} — ${r.status}`);
    }
    const userLogin = await login(u.email, u.password);
    if (!userLogin) throw new Error(`Unable to log in seeded user ${u.email}`);
    userTokens[u.email] = userLogin.token;
    if (userLogin.userId) userIds[u.email] = userLogin.userId;
    if (userLogin.user?.name) userNames[u.email] = userLogin.user.name;
    userProfiles[u.email] = {
      id: userLogin.userId,
      name: userLogin.user?.name ?? u.name,
      email: u.email,
      role: userLogin.user?.isAdmin ? "admin" : "user",
    };
  }

  // ── Create clients ──────────────────────────────────────────────────────
  console.log(`\nCreating ${data.clients.length} clients...`);
  for (const client of data.clients) {
    const r = await api("POST", "/api/v1/client/create", adminToken, {
      name: client.name,
      email: client.email,
      number: client.number,
      contactName: client.contactName,
    });
    if (r.ok) {
      console.log(`  Created client: ${client.name}`);
    } else {
      console.log(`  Skipped client (may exist): ${client.email} — ${r.status}`);
    }
  }

  const clientResult = await api("GET", "/api/v1/clients/all", adminToken);
  if (!clientResult.ok) {
    throw new Error(`Unable to load seeded clients: ${clientResult.status}`);
  }
  const clientRows = Array.isArray(clientResult.json)
    ? clientResult.json
    : clientResult.json.clients ?? clientResult.json.data ?? [];
  const clientIds = Object.fromEntries(
    clientRows.filter(client => client.email).map(client => [client.email, client.id]),
  );
  for (const client of data.clients) {
    if (!clientIds[client.email]) {
      throw new Error(`Unable to resolve seeded client ${client.email}`);
    }
  }

  // ── Create tickets ──────────────────────────────────────────────────────
  console.log(`\nCreating ${data.tickets.length} tickets...`);
  for (const t of data.tickets) {
    const assignedEmail = t.assignedTo;
    if (assignedEmail && !userIds[assignedEmail]) {
      throw new Error(`Unknown assigned user ${assignedEmail} for ticket '${t.title}'`);
    }
    const engineer =
      assignedEmail && userIds[assignedEmail]
        ? { id: userIds[assignedEmail], name: userNames[assignedEmail] ?? assignedEmail }
        : undefined;
    const creatorEmail = t.createdByEmail;
    if (creatorEmail && !userProfiles[creatorEmail]?.id) {
      throw new Error(`Unknown creator ${creatorEmail} for ticket '${t.title}'`);
    }
    const createdBy = creatorEmail ? userProfiles[creatorEmail] : undefined;
    const clientEmail = t.clientEmail;
    if (clientEmail && !clientIds[clientEmail]) {
      throw new Error(`Unknown client ${clientEmail} for ticket '${t.title}'`);
    }

    const body = {
      title:    t.title,
      name:     t.title,
      // The API JSON-stringifies this field. Imported plain text therefore
      // needs to be submitted as native BlockNote blocks; submitting a string
      // makes escaped newlines appear literally in the ticket editor.
      detail:   t.source ? ticketDetailBlocks(t.detail) : t.detail,
      priority: t.priority ?? "low",
      type:     t.type ?? "support",
      ...(engineer ? { engineer } : {}),
      ...(createdBy ? { createdBy } : {}),
      ...(clientEmail ? { company: clientIds[clientEmail] } : {}),
    };

    const r = await api("POST", "/api/v1/ticket/create", adminToken, body);
    if (!r.ok) {
      console.log(`  FAILED '${t.title.slice(0, 45)}': ${r.status} ${r.text.slice(0, 80)}`);
      continue;
    }
    const ticketId = r.json.id;
    console.log(`  Ticket: '${t.title.slice(0, 45)}' (id=${ticketId})`);

    // Update status
    const status = t.status ?? "needs_support";
    if (status !== "needs_support") {
      const sr = await api("PUT", "/api/v1/ticket/update", adminToken, { id: ticketId, status });
      if (!sr.ok) {
        await api("PUT", "/api/v1/ticket/status/update", adminToken, { id: ticketId, status });
      }
    }

    // Add comments
    for (const c of t.comments ?? []) {
      const commenterEmail = c.userEmail ?? ADMIN_EMAIL;
      const tok = userTokens[commenterEmail];
      if (!tok) {
        throw new Error(`Unknown commenter ${commenterEmail} for ticket '${t.title}'`);
      }
      const cr = await api("POST", "/api/v1/ticket/comment", tok, {
        id: ticketId, text: c.text, public: c.public ?? false,
      });
      if (!cr.ok) console.log(`    Comment failed: ${cr.status} ${cr.text.slice(0, 80)}`);
    }

    // Peppermint stores workflow status and open/closed state independently.
    // Existing seed tickets intentionally omit isComplete and retain their
    // original behavior. Additive imports may explicitly close resolved items.
    if (t.isComplete === true) {
      const closeResult = await api(
        "PUT",
        "/api/v1/ticket/status/update",
        adminToken,
        { id: ticketId, status: true },
      );
      if (!closeResult.ok) {
        console.log(`    Close failed: ${closeResult.status} ${closeResult.text.slice(0, 80)}`);
      }
    }
  }

  console.log("\nSeeding complete!");
}

main().catch(e => { console.error(e); process.exit(1); });
