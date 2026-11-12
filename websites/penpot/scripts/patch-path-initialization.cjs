#!/usr/bin/env node
// Penpot 2.14.1's path position-stream consumes the mouse-position subject's
// initial nil value. Selecting Path before entering the viewport consequently
// creates {:x nil :y nil} and crashes path-preview*. Filter that initial value
// before snapping, previewing, or combining it with a mouse-down event.
//
// Equivalent upstream change in frontend/src/app/main/data/workspace/path/streams.cljs:
//   (->> ms/mouse-position (rx/filter some?) (rx/map to-pixel-snap) ...)
// We consume the pinned upstream frontend image, so apply this narrow change
// to its compiled bundle. Reject unfamiliar bundles instead of silently shipping
// an unpatched image after an upstream upgrade.
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const root = process.argv[2] || '/var/www/app';
const filename = path.join(root, 'js/shared.js');
const source = fs.readFileSync(filename, 'utf8');
const declaration = '$app$main$data$workspace$path$streams$position_stream$$=function(';
const input = '$APP.$app$main$streams$mouse_position$$';
const filtered = `$APP.$beicon$v2$core$filter$$($APP.$cljs$core$some_QMARK_$$,${input})`;
const start = source.indexOf(declaration);
const end = source.indexOf('\n$app$', start + declaration.length);
if (start < 0 || end < 0 || source.indexOf(declaration, start + 1) !== -1) {
  throw new Error('Unsupported Penpot bundle: expected one path position-stream');
}
const original = source.slice(start, end);
if (original.split(input).length !== 2 || !original.includes('streams$to_pixel_snap$$')) {
  throw new Error('Unsupported Penpot path position-stream: expected one mouse input');
}
// Use a callback: a replacement string would interpret the compiler's $$ names.
const updated = original.includes(filtered) ? original : original.replace(input, () => filtered);
const result = source.slice(0, start) + updated + source.slice(end);
if (result !== source) fs.writeFileSync(filename, result);

// Keep any precompressed variants consistent with the patched bundle.
for (const [extension, compress] of [
  ['.gz', zlib.gzipSync],
  ['.br', zlib.brotliCompressSync],
]) {
  if (fs.existsSync(filename + extension)) {
    fs.writeFileSync(filename + extension, compress(Buffer.from(result)));
  }
}
console.log(result === source ? 'Penpot path initialization already patched' : 'Patched Penpot path initialization');
