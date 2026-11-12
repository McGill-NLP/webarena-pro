<?php
header('Content-Type: text/plain');
header('Cache-Control: no-store');
$ready = @file_get_contents('/tmp/webarena-office.ready');
$alive = true;
if (trim($ready ?: '') === 'bundled') {
    $pid = (int)@file_get_contents('/tmp/richdocumentscode-33/coolwsd.pid');
    $alive = $pid > 0 && @posix_kill($pid, 0)
        && trim(@file_get_contents("/proc/$pid/comm") ?: '') === 'coolwsd'
        && !preg_match('/^\d+ \(.*\) Z /', @file_get_contents("/proc/$pid/stat") ?: '');
}
if ($ready !== false && $alive) {
    echo "office-ready\n";
} else {
    http_response_code(503);
    echo is_file('/tmp/webarena-office.failed')
        ? "Office startup failed; inspect /tmp/webarena-office-startup.log\n"
        : "Office startup pending\n";
}
