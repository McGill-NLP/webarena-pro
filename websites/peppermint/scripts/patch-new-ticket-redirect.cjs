#!/usr/bin/env node
// The upstream image contains compiled Next.js pages. Repair only the success
// navigation in /new and fail the build if that upstream contract changes.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const root = path.join(process.argv[2] || '/apps', 'client/.next');
const pages = path.join(root, 'static/chunks/pages');
const bundles = fs.readdirSync(pages).filter(name => /^new-[a-f0-9]+\.js$/.test(name));
if (bundles.length !== 1) throw new Error(`Expected one /new client bundle, found ${bundles.length}`);
const client = path.join(pages, bundles[0]);
for (const file of [client, path.join(root, 'server/pages/new.js')]) {
  const source = fs.readFileSync(file, 'utf8');
  const before = '.push("/tickets")';
  if (source.split(before).length !== 2) {
    throw new Error(`${file}: expected one post-create /tickets navigation`);
  }
  fs.writeFileSync(file, source.replace(before, '.push("/issues")'));
}

// Next serves hashed chunks with immutable caching. Give the modified chunk
// a new name and update both server manifests and browser build manifests.
const oldName = bundles[0];
const digest = crypto.createHash('sha256').update(fs.readFileSync(client)).digest('hex').slice(0, 16);
const newName = `new-${digest}.js`;
function updateReferences(directory) {
  for (const entry of fs.readdirSync(directory, {withFileTypes: true})) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) updateReferences(file);
    else if (/\.(json|html|js)$/.test(file) && file !== client) {
      const source = fs.readFileSync(file, 'utf8');
      if (source.includes(oldName)) fs.writeFileSync(file, source.split(oldName).join(newName));
    }
  }
}
updateReferences(root);
fs.renameSync(client, path.join(pages, newName));
console.log('Peppermint: new tickets return to /issues');
