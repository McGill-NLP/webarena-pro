<?php
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Nextcloud 32.0.12 apps/files/src/newMenu/newFromTemplate.ts mounts an async
// TemplatePicker component but exposes open() before its ref exists. Fast
// creation on a cold Files page therefore throws instead of opening the file.
// Load the same lazy chunk before mounting the picker. This pinned-bundle
// patch fails the image build if a Nextcloud upgrade changes the target code.
declare(strict_types=1);

if ($argc !== 2 || !is_file($argv[1])) {
    fwrite(STDERR, "Usage: php fix-template-picker.php /path/to/files-init.js\n");
    exit(2);
}
$path = $argv[1];
$source = file_get_contents($path);
$before = 'Ls=(0,c.$V)(()=>Promise.all([t.e(4208),t.e(3973)]).then(t.bind(t,93973)));let Us=null;const _s=async e=>{';
$after = 'LsLoader=()=>Promise.all([t.e(4208),t.e(3973)]).then(t.bind(t,93973));let Us=null;const _s=async e=>{const Ls=(await LsLoader()).default;';
if (substr_count($source, $after) === 1 && !str_contains($source, $before)) {
    exit(0);
}
if (substr_count($source, $before) !== 1) {
    fwrite(STDERR, "Unsupported Nextcloud template-picker bundle; review the pinned compatibility patch.\n");
    exit(1);
}
$patched = str_replace($before, $after, $source);
if (file_put_contents($path, $patched) === false) {
    throw new RuntimeException("Could not write patched template-picker bundle");
}
