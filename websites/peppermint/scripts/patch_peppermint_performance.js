#!/usr/bin/env node
/**
 * Narrow Peppermint's ticket-list payloads and repair compiled list pagination.
 *
 * The upstream production image includes compiled API/client output but not the
 * full client source tree. This deterministic build-time patch is deliberately
 * limited to the three ticket list bundles, the internal-user page, and the
 * repeated Prisma list select. Single-ticket responses still include
 * descriptions, comments, and files.
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const appsRoot = process.argv[2] || "/apps";
const pageSize = 50;

function replaceExactly(source, before, after, expected, label) {
  const count = source.split(before).length - 1;
  if (count !== expected) {
    throw new Error(`${label}: expected ${expected} matches, found ${count}`);
  }
  return source.split(before).join(after);
}

function findMatchingParen(source, openIndex) {
  let depth = 0;
  let quote = null;
  let escaped = false;

  for (let index = openIndex; index < source.length; index += 1) {
    const char = source[index];

    if (quote !== null) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        quote = null;
      }
      continue;
    }

    if (char === '"' || char === "'" || char === "`") {
      quote = char;
    } else if (char === "(") {
      depth += 1;
    } else if (char === ")") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }

  throw new Error(`No matching parenthesis found at offset ${openIndex}`);
}

function patchApi() {
  const apiPath = path.join(appsRoot, "api/dist/controllers/ticket.js");
  let source = fs.readFileSync(apiPath, "utf8");

  const fullTicketInclude = `            include: {
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

  const listTicketSelect = `            select: {
                id: true,
                Number: true,
                name: true,
                title: true,
                createdAt: true,
                updatedAt: true,
                isComplete: true,
                priority: true,
                status: true,
                type: true,
                locked: true,
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

  source = replaceExactly(
    source,
    fullTicketInclude,
    listTicketSelect,
    7,
    "ticket API list projections",
  );
  fs.writeFileSync(apiPath, source);
}

function ticketPageBundles() {
  const pagesRoot = path.join(appsRoot, "client/.next/static/chunks/pages");
  const issueDirectory = path.join(pagesRoot, "issues");
  const allPage = fs
    .readdirSync(pagesRoot)
    .filter((name) => /^issues-[a-f0-9]+\.js$/.test(name))
    .map((name) => path.join(pagesRoot, name));
  const statePages = fs
    .readdirSync(issueDirectory)
    .filter((name) => /^(?:open|closed)-[a-f0-9]+\.js$/.test(name))
    .map((name) => path.join(issueDirectory, name));
  return [...allPage, ...statePages];
}

function paginationToolbar(filteredVariable) {
  return `(0,r.jsxs)("div",{key:"ticket-pagination",className:"sticky top-0 z-10 flex items-center justify-between border-b bg-background px-6 py-2 text-xs",children:[(0,r.jsx)("button",{type:"button",className:"rounded border px-3 py-1 disabled:opacity-40",disabled:currentPage<=1,onClick:()=>setPageIndex(e=>Math.max(1,Math.min(e,pageCount)-1)),children:"Previous"}),(0,r.jsxs)("span",{children:["Page ",currentPage," of ",pageCount," · ",${filteredVariable}.length," tickets"]}),(0,r.jsx)("button",{type:"button",className:"rounded border px-3 py-1 disabled:opacity-40",disabled:currentPage>=pageCount,onClick:()=>setPageIndex(e=>Math.min(pageCount,e+1)),children:"Next"})]})`;
}

function filesBelow(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name);
    return entry.isDirectory() ? filesBelow(entryPath) : [entryPath];
  });
}

function cacheBustBundles(bundles, suffix) {
  const nextRoot = path.join(appsRoot, "client/.next");
  const referenceFiles = filesBelow(nextRoot).filter(
    (file) =>
      file.endsWith(".json") ||
      file.endsWith(".html") ||
      /[/\\]static[/\\][^/\\]+[/\\]_(build|ssg)Manifest\.js$/.test(file),
  );

  for (const bundlePath of bundles) {
    const oldName = path.basename(bundlePath);
    const newName = oldName.replace(/\.js$/, `.${suffix}.js`);
    let references = 0;

    for (const referencePath of referenceFiles) {
      const source = fs.readFileSync(referencePath, "utf8");
      if (!source.includes(oldName)) continue;
      references += source.split(oldName).length - 1;
      fs.writeFileSync(referencePath, source.split(oldName).join(newName));
    }

    if (references === 0) {
      throw new Error(`${oldName}: no Next.js manifest or HTML references found`);
    }
    fs.renameSync(bundlePath, path.join(path.dirname(bundlePath), newName));
  }
}

function validateClientBuildManifests() {
  const nextRoot = path.join(appsRoot, "client/.next");
  const manifests = filesBelow(path.join(nextRoot, "static")).filter(
    (file) => path.basename(file) === "_buildManifest.js",
  );
  if (manifests.length === 0) {
    throw new Error("No Next.js client build manifest found");
  }

  for (const manifestPath of manifests) {
    // Evaluate Next's generated manifest so shared assets factored into
    // function arguments are checked along with each route's own chunks.
    const context = { self: {} };
    vm.runInNewContext(fs.readFileSync(manifestPath, "utf8"), context, {
      filename: manifestPath,
      timeout: 1000,
    });
    const assets = Object.values(context.self.__BUILD_MANIFEST)
      .filter(Array.isArray)
      .flat()
      .filter((asset) => typeof asset === "string" && asset.startsWith("static/"));
    for (const asset of new Set(assets)) {
      if (!fs.existsSync(path.join(nextRoot, asset))) {
        throw new Error(
          `${path.relative(nextRoot, manifestPath)}: missing Next.js asset ${asset}`,
        );
      }
    }
  }
}

function patchUserPagination() {
  const staticDirectory = path.join(
    appsRoot,
    "client/.next/static/chunks/pages/admin/users",
  );
  const staticBundles = fs
    .readdirSync(staticDirectory)
    .filter((name) => /^internal-[a-f0-9]+\.js$/.test(name))
    .map((name) => path.join(staticDirectory, name));
  if (staticBundles.length !== 1) {
    throw new Error(
      `Expected 1 internal-user client bundle, found ${staticBundles.length}`,
    );
  }

  const serverBundle = path.join(
    appsRoot,
    "client/.next/server/pages/admin/users/internal.js",
  );
  for (const bundlePath of [...staticBundles, serverBundle]) {
    let source = fs.readFileSync(bundlePath, "utf8");
    source = replaceExactly(
      source,
      ".legnth>10",
      ".length>10",
      1,
      `${path.basename(bundlePath)} user pagination typo`,
    );
    source = replaceExactly(
      source,
      "initialState:{pageIndex:0}",
      "initialState:{pageIndex:0,pageSize:100}",
      1,
      `${path.basename(bundlePath)} user default page size`,
    );
    source = replaceExactly(
      source,
      "children:[10,20,30,40,50].map",
      "children:[10,20,30,40,50,100].map",
      1,
      `${path.basename(bundlePath)} user page-size options`,
    );
    fs.writeFileSync(bundlePath, source);
  }
  cacheBustBundles(staticBundles, "users100all");
}

function patchClientBundle(bundlePath) {
  let source = fs.readFileSync(bundlePath, "utf8");

  source = replaceExactly(
    source,
    "refetchInterval:5e3",
    "refetchInterval:3e4",
    1,
    `${path.basename(bundlePath)} refresh interval`,
  );

  const filterMatch = source.match(/([A-Z])=s\?s\.tickets\.filter\(/);
  if (!filterMatch) {
    throw new Error(`${path.basename(bundlePath)}: filtered ticket variable not found`);
  }
  const filteredVariable = filterMatch[1];
  const filterEndMarker = "}):[],";
  const filterEnd = source.indexOf(filterEndMarker, filterMatch.index);
  if (filterEnd < 0) {
    throw new Error(`${path.basename(bundlePath)}: end of ticket filter not found`);
  }

  const paginationState = `[pageIndex,setPageIndex]=(0,i.useState)(1),pageSize=${pageSize},pageCount=Math.max(1,Math.ceil(${filteredVariable}.length/pageSize)),currentPage=Math.min(pageIndex,pageCount),pageTickets=${filteredVariable}.slice((currentPage-1)*pageSize,currentPage*pageSize),`;
  const stateInsertion = filterEnd + filterEndMarker.length;
  source =
    source.slice(0, stateInsertion) +
    paginationState +
    source.slice(stateInsertion);

  const rowMapPrefix = `${filteredVariable}.length>0?${filteredVariable}.map(`;
  const rowMapStart = source.indexOf(rowMapPrefix, stateInsertion);
  if (rowMapStart < 0) {
    throw new Error(`${path.basename(bundlePath)}: ticket row map not found`);
  }
  const mapOpenParen = rowMapStart + rowMapPrefix.length - 1;
  const mapCloseParen = findMatchingParen(source, mapOpenParen);
  const paginatedPrefix = `${filteredVariable}.length>0?[${paginationToolbar(filteredVariable)},...pageTickets.map(`;

  source =
    source.slice(0, rowMapStart) +
    paginatedPrefix +
    source.slice(mapOpenParen + 1, mapCloseParen + 1) +
    "]" +
    source.slice(mapCloseParen + 1);

  fs.writeFileSync(bundlePath, source);
}

patchApi();

const bundles = ticketPageBundles();
if (bundles.length !== 3) {
  throw new Error(`Expected 3 ticket list bundles, found ${bundles.length}`);
}
for (const bundle of bundles) patchClientBundle(bundle);
cacheBustBundles(bundles, "paged50");
patchUserPagination();
validateClientBuildManifests();

console.log(
  `Peppermint performance patch applied: ${pageSize} rows/page, ` +
  "30 second refresh, compact ticket payloads, working user pagination.",
);
