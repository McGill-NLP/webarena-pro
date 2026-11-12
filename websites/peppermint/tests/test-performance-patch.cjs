const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const { spawnSync } = require("node:child_process");

const patch = path.join(__dirname, "../scripts/patch_peppermint_performance.js");
const chunks = [
  "static/chunks/pages/issues-019e18202bda0a1b.js",
  "static/chunks/pages/issues/open-ab12.js",
  "static/chunks/pages/issues/closed-cd34.js",
  "static/chunks/pages/admin/users/internal-ef56.js",
];
const sharedChunk = "static/chunks/shared-ab12.js";
const stylesheet = "static/css/ab12.css";
const buildManifest = "static/build-id/_buildManifest.js";
const ssgManifest = "static/build-id/_ssgManifest.js";
const referenceFiles = [
  "build-manifest.json",
  "server/pages/issues.html",
  buildManifest,
  ssgManifest,
];

function fixture(t) {
  const apps = fs.mkdtempSync(path.join(os.tmpdir(), "peppermint-performance-"));
  t.after(() => fs.rmSync(apps, { recursive: true, force: true }));
  const next = path.join(apps, "client/.next");
  function write(file, source) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, source);
  }

  const include = `            include: {
                client: {
                    select: { id: true, name: true, number: true },
                },
                assignedTo: {
                    select: { id: true, name: true },
                },
                team: {
                    select: { id: true, name: true },
                },
            },`;
  write(path.join(apps, "api/dist/controllers/ticket.js"), include.repeat(7));
  for (const chunk of chunks.slice(0, 3)) {
    write(
      path.join(next, chunk),
      'const query={refetchInterval:5e3};const T=s?s.tickets.filter(e=>{return e}):[],rows=T.length>0?T.map(e=>render(e)):null;',
    );
  }
  for (const file of [chunks[3], "server/pages/admin/users/internal.js"]) {
    write(
      path.join(next, file),
      "users.legnth>10;const table={initialState:{pageIndex:0},children:[10,20,30,40,50].map(e=>e)};",
    );
  }
  write(path.join(next, sharedChunk), "// unchanged shared chunk");
  write(path.join(next, stylesheet), "body{}");
  write(path.join(next, "build-manifest.json"), JSON.stringify({ pages: chunks }));
  write(
    path.join(next, "server/pages/issues.html"),
    chunks.map(chunk => `<script src="/_next/${chunk}"></script>`).join(""),
  );
  // Next.js factors shared assets into function arguments in this manifest.
  write(
    path.join(next, buildManifest),
    `self.__BUILD_MANIFEST=function(a){return {__rewrites:{beforeFiles:[],afterFiles:[],fallback:[]},"/issues":[a,"${chunks[0]}","${stylesheet}"],"/issues/open":[a,"${chunks[1]}"],"/issues/closed":[a,"${chunks[2]}"],"/admin/users/internal":["${chunks[3]}"],sortedPages:["/issues","/issues/open","/issues/closed","/admin/users/internal"]}}("${sharedChunk}");self.__BUILD_MANIFEST_CB&&self.__BUILD_MANIFEST_CB();`,
  );
  write(
    path.join(next, ssgManifest),
    `self.__SSG_MANIFEST=new Set(["/issues"]);/* ${chunks.join(" ")} */`,
  );
  return { apps, next };
}

function runPatch(apps) {
  return spawnSync(process.execPath, [patch, apps], { encoding: "utf8" });
}

test("renamed ticket and user bundles resolve from browser, server and HTML manifests", t => {
  const { apps, next } = fixture(t);
  const result = runPatch(apps);
  assert.equal(result.status, 0, result.stderr);

  for (const [index, chunk] of chunks.entries()) {
    const renamed = chunk.replace(/\.js$/, index < 3 ? ".paged50.js" : ".users100all.js");
    assert.ok(!fs.existsSync(path.join(next, chunk)), chunk);
    assert.ok(fs.statSync(path.join(next, renamed)).isFile(), renamed);
    for (const file of referenceFiles) {
      const source = fs.readFileSync(path.join(next, file), "utf8");
      assert.ok(!source.includes(chunk), `${file} still references ${chunk}`);
      assert.ok(source.includes(renamed), `${file} is missing ${renamed}`);
    }
  }

  const context = { self: {} };
  vm.runInNewContext(fs.readFileSync(path.join(next, buildManifest), "utf8"), context);
  for (const [route, assets] of Object.entries(context.self.__BUILD_MANIFEST)) {
    if (!route.startsWith("/")) continue;
    for (const asset of assets) assert.ok(fs.statSync(path.join(next, asset)).isFile(), asset);
  }
  assert.equal(fs.readFileSync(path.join(next, sharedChunk), "utf8"), "// unchanged shared chunk");
});

for (const asset of [sharedChunk, stylesheet]) {
  test(`fails the build when the client manifest names a missing asset: ${asset}`, t => {
    const { apps, next } = fixture(t);
    fs.unlinkSync(path.join(next, asset));
    const result = runPatch(apps);
    assert.notEqual(result.status, 0);
    assert.ok(result.stderr.includes(buildManifest), result.stderr);
    assert.ok(result.stderr.includes(asset), result.stderr);
  });
}

test("fails the build when the client build manifest is missing", t => {
  const { apps, next } = fixture(t);
  fs.unlinkSync(path.join(next, buildManifest));
  const result = runPatch(apps);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /No Next\.js client build manifest found/);
});
