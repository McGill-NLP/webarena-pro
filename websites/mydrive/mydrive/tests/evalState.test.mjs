import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

// Execute the real route while isolating database/storage dependencies.
const source = fs.readFileSync(new URL("../src/app/api/eval/state/route.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function route(files = []) {
  const calls = [];
  const prisma = Object.fromEntries(Object.entries({
    user: [{ id: "user1", username: "agent1", email: "agent1@test.com" }],
    folder: [], fileObject: files, share: [],
  }).map(([name, rows]) => [name, { findMany: async () => { calls.push(name); return rows; } }]));
  const exports = {};
  vm.runInNewContext(compiled, {
    exports,
    process: { env: { WP_EVAL_TOKEN: "test-token", S3_BUCKET: "files" } },
    TextDecoder,
    require: (name) => {
      if (name === "next/server") return { NextResponse: { json: (body, options) => ({ body, status: options?.status ?? 200 }) } };
      if (name.endsWith("/lib/db")) return { prisma };
      if (name.endsWith("/lib/s3")) return { s3: { send: async () => ({
        Body: { transformToByteArray: async () => new TextEncoder().encode("Saved text") },
      }) } };
      if (name === "@aws-sdk/client-s3") return { GetObjectCommand: class {} };
      throw new Error(`Unexpected dependency: ${name}`);
    },
  });
  return { get: exports.GET, calls };
}

const request = (token) => new Request("http://mydrive/api/eval/state", {
  headers: token ? { "x-eval-token": token } : {},
});

test("snapshot metadata is token protected", async () => {
  const handler = route();
  for (const token of [undefined, "wrong-token"]) {
    const result = await handler.get(request(token));
    assert.equal(result.status, 403);
    assert.equal(result.body.fileSnapshotVersion, undefined);
  }
  assert.equal(handler.calls.length, 0);
});

test("empty collections still advertise the file snapshot contract", async () => {
  const result = await route().get(request("test-token"));
  assert.equal(result.status, 200);
  assert.equal(result.body.fileSnapshotVersion, 1);
  assert.equal(result.body.files.length, 0);
});

test("stable IDs and owner emails survive renames and trash", async () => {
  const original = { id: "file-1", name: "Notes.txt", folderId: null, ownerId: "user1",
    size: 10, mimeType: "text/plain", s3Key: "object-1", inTrash: false };
  const before = (await route([original]).get(request("test-token"))).body.files[0];
  const after = (await route([{ ...original, name: "Different title", inTrash: true }])
    .get(request("test-token"))).body.files[0];
  assert.equal(before.id, "file-1");
  assert.equal(after.id, before.id);
  assert.equal(before.ownerEmail, "agent1@test.com");
  assert.equal(after.ownerEmail, before.ownerEmail);
  assert.equal(before.owner, "agent1"); // Keep the existing evaluator contract.
  assert.equal(before.content, "Saved text");
  assert.equal(after.inTrash, true);
  assert.equal(after.content, undefined);
});
