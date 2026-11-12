<?php
// Roundcube configuration for WebArena Thunderbird container

// Database: SQLite (no external DB needed)
$config['db_dsnw'] = 'sqlite:////var/lib/roundcube/roundcube.db?mode=0646';

// IMAP server (Dovecot running locally)
$config['default_host'] = '127.0.0.1';
$config['default_port'] = 143;
$config['imap_auth_type'] = 'LOGIN';
$config['imap_delimiter'] = '/';

// Fake SMTP server (runs in this container). It accepts messages without
// external network delivery and writes techcorp.local recipients to Maildir.
$config['smtp_host'] = '127.0.0.1:25';
$config['smtp_user'] = '';
$config['smtp_pass'] = '';
$config['smtp_auth_type'] = '';

// Application
$config['product_name'] = 'TechCorp Webmail';
$config['support_url'] = '';
$config['skin'] = 'elastic';
$config['webarena_thread_index'] = '/var/lib/roundcube/thread-index.json.gz';
$config['default_list_mode'] = 'threads';

// Encryption key (static for reproducible container)
$config['des_key'] = 'webarena-thunderbird-2026-key!!';

// Plugins to enable
$config['plugins'] = ['archive', 'zipdownload', 'managesieve', 'webarena_reply'];

// Disable installer after setup
$config['enable_installer'] = false;

// Session
$config['session_lifetime'] = 120;
$config['login_autocomplete'] = 2;

// Default folders matching Dovecot config
$config['sent_mbox'] = 'Sent';
$config['trash_mbox'] = 'Trash';
$config['drafts_mbox'] = 'Drafts';
$config['junk_mbox'] = 'Junk';

// Auto-create missing special folders
$config['create_default_folders'] = true;

// Show all subfolders in folder list
$config['subscribe_on_create'] = true;

// Display settings
$config['draft_autosave'] = 60;
$config['max_message_size'] = '10M';
$config['mime_param_folding'] = 0;

// Pagination
$config['pagesize'] = 50;

// Allow plain-text auth since everything is local
$config['imap_force_caps'] = false;
$config['imap_skip_ns_check'] = true;

// Log to file
$config['log_driver'] = 'file';
$config['log_dir'] = '/var/log/roundcube/';
$config['temp_dir'] = '/var/lib/roundcube/temp/';

// ManageSieve shares the authenticated IMAP user's credentials.
$config['managesieve_host'] = '127.0.0.1';
$config['managesieve_port'] = 4190;
$config['managesieve_usetls'] = false;
