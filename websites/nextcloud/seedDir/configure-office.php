<?php
// Run as www-data after runtime trusted domains and public URL are configured.
require '/var/www/html/lib/base.php';
$config = \OC::$server->get(\OCP\IConfig::class);
$public = rtrim($argv[1], '/');
$external = getenv('WP_COLLABORA_URL');
$app = is_dir('/var/www/html/custom_apps/richdocumentscode_arm64')
    ? 'richdocumentscode_arm64' : 'richdocumentscode';
if ($external) {
    $wopi = rtrim(getenv('WP_COLLABORA_INTERNAL_URL') ?: $external, '/');
    $callback = rtrim(getenv('WP_NEXTCLOUD_CALLBACK_URL') ?: $public, '/');
} else {
    $wopi = "$public/custom_apps/$app/proxy.php?req=";
    $callback = 'http://localhost';
}
$config->setAppValue('richdocuments', 'wopi_url', $wopi);
$config->setAppValue('richdocuments', 'wopi_callback_url', $callback);
// activate-config derives this from discovery once Apache is available.
$config->setAppValue('richdocuments', 'public_wopi_url', $external ?: $public);
if (class_exists(\OCA\RichDocumentsCODE\HostConfig::class)) {
    \OC::$server->get(\OCA\RichDocumentsCODE\HostConfig::class)->update();
}
