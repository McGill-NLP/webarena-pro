const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const patch = path.join(__dirname, '../scripts/patch-new-ticket-redirect.cjs');

test('patches both render paths and all immutable chunk references', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'peppermint-new-'));
  try {
    const root = path.join(dir, 'client/.next');
    for (const folder of ['static/chunks/pages', 'server/pages', 'static/build']) fs.mkdirSync(path.join(root, folder), {recursive: true});
    fs.writeFileSync(path.join(root, 'static/chunks/pages/new-ab12.js'), 'router.push("/tickets");');
    fs.writeFileSync(path.join(root, 'server/pages/new.js'), 'router.push("/tickets");');
    for (const file of ['build-manifest.json', 'server/pages/new.html', 'static/build/_buildManifest.js']) fs.writeFileSync(path.join(root, file), '"static/chunks/pages/new-ab12.js"');
    execFileSync(process.execPath, [patch, dir]);
    const [chunk] = fs.readdirSync(path.join(root, 'static/chunks/pages'));
    assert.notEqual(chunk, 'new-ab12.js');
    assert.match(fs.readFileSync(path.join(root, 'static/chunks/pages', chunk), 'utf8'), /push\("\/issues"\)/);
    assert.match(fs.readFileSync(path.join(root, 'server/pages/new.js'), 'utf8'), /push\("\/issues"\)/);
    for (const file of ['build-manifest.json', 'server/pages/new.html', 'static/build/_buildManifest.js']) assert.ok(fs.readFileSync(path.join(root, file), 'utf8').includes(chunk));
    assert.throws(() => execFileSync(process.execPath, [patch, dir], {stdio: 'pipe'}), /Command failed/);
  } finally { fs.rmSync(dir, {recursive: true, force: true}); }
});
