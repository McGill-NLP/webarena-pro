<?php
/**
 * Read-only evaluation API for the WebArena-Pro evaluator.
 *
 * Exposes a user's mailbox state (folders, messages, flags) as JSON so mail
 * tasks can be graded deterministically instead of relying on an LLM judge.
 * It connects to the local Dovecot IMAP server (the maildir itself is only
 * readable by the vmail user, so IMAP is used rather than direct file access).
 *
 * Strictly read-only. Gated by a secret token (WP_EVAL_TOKEN) that the agent
 * under test never sees, so it cannot read answers. Disabled (403) when
 * WP_EVAL_TOKEN is unset. Served by the existing nginx + php-fpm on port 80.
 *
 * Usage:  GET /api/eval/state.php?user=alice@techcorp.local
 *         header  X-Eval-Token: <WP_EVAL_TOKEN>
 */

header('Content-Type: application/json');

$token = getenv('WP_EVAL_TOKEN');
$provided = $_SERVER['HTTP_X_EVAL_TOKEN'] ?? '';
if (!$token || !hash_equals($token, $provided)) {
    http_response_code(403);
    echo json_encode(['error' => 'forbidden']);
    exit;
}

$user = $_GET['user'] ?? '';
if ($user === '') {
    http_response_code(400);
    echo json_encode(['error' => 'missing ?user']);
    exit;
}

// Seed users share one password; overridable via env for other deployments.
$password = getenv('WP_EVAL_IMAP_PASSWORD') ?: 'User@Secure123';
$server = '{127.0.0.1:143/imap/notls/norsh}';

function decode_mime_header_value($value) {
    $decoded = '';
    foreach (imap_mime_header_decode($value ?: '') as $part) {
        $decoded .= $part->text ?? '';
    }
    return $decoded;
}

$mbox = @imap_open($server . 'INBOX', $user, $password, OP_READONLY);
if (!$mbox) {
    http_response_code(502);
    echo json_encode(['error' => 'imap_open failed', 'detail' => imap_last_error()]);
    exit;
}

$out = ['user' => $user, 'folders' => [], 'address_book' => ['count' => 0, 'contacts' => []]];
$boxes = imap_list($mbox, $server, '*') ?: [];
foreach ($boxes as $box) {
    $folder = preg_replace('/^.*}/', '', $box);
    if (!@imap_reopen($mbox, $box, OP_READONLY)) {
        continue;
    }
    $n = imap_num_msg($mbox);
    $messages = [];
    for ($i = 1; $i <= $n; $i++) {
        $h = imap_headerinfo($mbox, $i);
        $overview_rows = imap_fetch_overview($mbox, (string) $i, 0);
        $status = $overview_rows[0] ?? null;
        if (!$h || !$status) {
            continue;
        }
        $body = imap_body($mbox, $i, FT_PEEK);  // FT_PEEK: don't set \Seen
        // Decode the transfer encoding (Roundcube sends quoted-printable for
        // wrapped/non-ASCII text, which splits words with "=\r\n") and fold
        // whitespace so verifiers can match phrases across line wraps.
        $structure = @imap_fetchstructure($mbox, $i);
        $encoding = (int) ($structure->encoding ?? 0);
        if ($structure && (int) ($structure->type ?? 0) === 1) {  // multipart: first part
            $part = @imap_fetchbody($mbox, $i, '1', FT_PEEK);
            if ($part !== false && $part !== '') {
                $body = $part;
                $encoding = (int) ($structure->parts[0]->encoding ?? 0);
            }
        }
        if ($encoding === 4) {
            $body = imap_qprint($body);
        } elseif ($encoding === 3) {
            $body = imap_base64($body);
        }
        $body = preg_replace('/\s+/', ' ', $body ?? '');
        $messages[] = [
            'subject'  => decode_mime_header_value($h->subject ?? ''),
            'from'     => $h->fromaddress ?? '',
            'to'       => $h->toaddress ?? '',
            'cc'       => $h->ccaddress ?? '',
            'bcc'      => $h->bccaddress ?? '',
            'date'     => $h->date ?? '',
            // Overview booleans reliably distinguish \Seen from \Recent;
            // imap_headerinfo()'s Unseen property is absent on some servers.
            'seen'     => (bool) ($status->seen ?? false),
            'recent'   => (bool) ($status->recent ?? false),
            'flagged'  => (bool) ($status->flagged ?? false),
            'answered' => (bool) ($status->answered ?? false),
            'draft'    => (bool) ($status->draft ?? false),
            'deleted'  => (bool) ($status->deleted ?? false),
            'message_id' => trim($status->message_id ?? $h->message_id ?? ''),
            'body'     => mb_substr(trim($body), 0, 2000),
        ];
    }
    $out['folders'][$folder] = $messages;
}
imap_close($mbox);

// Contacts are required to grade the add-contact/Bcc tasks. This uses the
// same token-gated, read-only endpoint and opens SQLite in read-only mode.
try {
    $db = new SQLite3('/var/lib/roundcube/roundcube.db', SQLITE3_OPEN_READONLY);
    $statement = $db->prepare(
        'SELECT c.name, c.email, c.firstname, c.surname '
        . 'FROM contacts c JOIN users u ON u.user_id = c.user_id '
        . 'WHERE u.username = :username AND c.del = 0 ORDER BY c.name, c.email'
    );
    $statement->bindValue(':username', $user, SQLITE3_TEXT);
    $result = $statement->execute();
    while ($contact = $result->fetchArray(SQLITE3_ASSOC)) {
        $out['address_book']['contacts'][] = $contact;
    }
    $out['address_book']['count'] = count($out['address_book']['contacts']);
    $result->finalize();
    $statement->close();
    $db->close();
} catch (Throwable $error) {
    $out['address_book']['error'] = $error->getMessage();
}

echo json_encode($out);
