<?php

/**
 * Render RFC email conversations across Inbox and Sent, while keeping each
 * item linked to its real IMAP message and native Roundcube reply flow.
 */
class webarena_reply extends rcube_plugin
{
    public $task = 'mail';

    private static $thread_index;

    public function init()
    {
        $rcmail = rcmail::get_instance();

        $this->register_action('plugin.webarena-thread', [$this, 'thread_data']);

        if (in_array($rcmail->action, ['show', 'preview'], true)) {
            $this->include_script('reply.js');
            $this->include_stylesheet($this->local_skin_path() . '/reply.css');
        }
    }

    private function normalize_message_id($value)
    {
        $value = trim((string) $value);
        if (!$value) {
            return '';
        }
        if (preg_match('/<[^>]+>/', $value, $matches)) {
            return $matches[0];
        }
        return '<' . trim($value, '<>') . '>';
    }

    private function message_id_candidates($headers)
    {
        $values = [$headers->messageID, $headers->in_reply_to, $headers->references];
        $result = [];
        foreach ($values as $value) {
            if (preg_match_all('/<[^>]+>/', (string) $value, $matches)) {
                foreach ($matches[0] as $message_id) {
                    $result[] = $message_id;
                }
            }
            else if ($message_id = $this->normalize_message_id($value)) {
                $result[] = $message_id;
            }
        }
        return array_values(array_unique($result));
    }

    private function load_thread_index()
    {
        if (self::$thread_index !== null) {
            return self::$thread_index;
        }

        $rcmail = rcmail::get_instance();
        $path = $rcmail->config->get(
            'webarena_thread_index',
            '/var/lib/roundcube/thread-index.json.gz'
        );
        $compressed = @file_get_contents($path);
        $json = $compressed !== false ? @gzdecode($compressed) : false;
        self::$thread_index = $json !== false ? json_decode($json, true) : null;

        return self::$thread_index;
    }

    private function addresses($value, $charset = null)
    {
        $decoded = rcube_mime::decode_address_list($value, null, true, $charset);
        $result = [];
        foreach ($decoded as $address) {
            $email = isset($address['mailto']) ? trim($address['mailto']) : '';
            $name = isset($address['name']) ? trim($address['name']) : '';
            if ($email || $name) {
                $result[] = [
                    'name' => $name ?: $email,
                    'email' => $email,
                ];
            }
        }
        return $result;
    }

    private function display_body($body)
    {
        $body = str_replace("\0", '', (string) $body);
        $patterns = [
            '/\R\s*On .{3,300} wrote:\s*\R/is',
            '/\R\s*-{2,}\s*Original Message\s*-{2,}\s*\R/is',
            '/\R\s*>.*(?:\R\s*>.*)+/s',
        ];
        $cut = strlen($body);
        foreach ($patterns as $pattern) {
            if (preg_match($pattern, $body, $match, PREG_OFFSET_CAPTURE)) {
                $cut = min($cut, $match[0][1]);
            }
        }
        $body = trim(substr($body, 0, $cut));
        return $body ?: '(No additional reply text.)';
    }

    private function live_message_record($storage, $uid, $folder)
    {
        $headers = $storage->get_message_headers($uid, $folder, true);
        if (!$headers) {
            return null;
        }

        $message_id = $this->normalize_message_id($headers->messageID);
        if (!$message_id) {
            return null;
        }

        $message = new rcube_message($uid, $folder);
        $body = $message->first_text_part();
        $date = rcube_utils::anytodatetime($headers->date);
        $from = $this->addresses($headers->from, $headers->charset);

        return [
            'id' => 'live-' . rawurlencode($folder) . '-' . $uid,
            'message_id' => $message_id,
            'parent_message_id' => $this->normalize_message_id($headers->in_reply_to),
            'depth' => 0,
            'from' => $from ? $from[0] : ['name' => 'Unknown sender', 'email' => ''],
            'to' => $this->addresses($headers->to, $headers->charset),
            'cc' => $this->addresses($headers->cc, $headers->charset),
            'subject' => rcube_mime::decode_header($headers->subject, $headers->charset),
            'date' => $date ? $date->format(DATE_ATOM) : (string) $headers->date,
            'body' => $this->display_body($body),
            'folder' => $folder,
            'uid' => (int) $uid,
            'live' => true,
        ];
    }

    private function discover_live_replies($storage, $root_message_id, $known)
    {
        $result = [];
        $rcmail = rcmail::get_instance();
        $folders = array_values(array_unique(array_filter([
            'INBOX',
            $rcmail->config->get('sent_mbox', 'Sent'),
        ])));
        $needle = rcube_imap_generic::escape($root_message_id);
        $criteria = 'OR HEADER References ' . $needle . ' HEADER In-Reply-To ' . $needle;

        foreach ($folders as $folder) {
            $matches = $storage->search_once($folder, $criteria);
            if (!$matches || $matches->is_error()) {
                continue;
            }
            foreach ($matches->get() as $uid) {
                $record = $this->live_message_record($storage, $uid, $folder);
                if ($record && empty($known[$record['message_id']])) {
                    $known[$record['message_id']] = true;
                    $result[] = $record;
                }
            }
        }
        return $result;
    }

    private function resolve_seed_uids($storage, &$messages)
    {
        foreach ($messages as &$message) {
            if (!empty($message['uid'])) {
                continue;
            }
            $criteria = 'HEADER Message-ID '
                . rcube_imap_generic::escape($message['message_id']);
            $matches = $storage->search_once($message['folder'], $criteria);
            $message['uid'] = $matches && !$matches->is_error()
                ? (int) $matches->max()
                : 0;
        }
        unset($message);
    }

    private function order_tree($messages, $root_message_id)
    {
        $by_id = [];
        foreach ($messages as $message) {
            $by_id[$message['message_id']] = $message;
        }

        $children = [];
        foreach ($by_id as $message_id => $message) {
            $parent = $message['parent_message_id'];
            if (!$parent || empty($by_id[$parent]) || $parent === $message_id) {
                if ($message_id !== $root_message_id) {
                    $parent = $root_message_id;
                    $by_id[$message_id]['parent_message_id'] = $parent;
                }
            }
            if ($message_id !== $root_message_id) {
                $children[$parent][] = $message_id;
            }
        }

        foreach ($children as &$child_ids) {
            usort($child_ids, function ($left, $right) use ($by_id) {
                return strcmp($by_id[$left]['date'], $by_id[$right]['date']);
            });
        }
        unset($child_ids);

        $ordered = [];
        $visited = [];
        $walk = function ($message_id, $depth) use (&$walk, &$ordered, &$visited, $by_id, $children) {
            if (isset($visited[$message_id]) || empty($by_id[$message_id])) {
                return;
            }
            $visited[$message_id] = true;
            $message = $by_id[$message_id];
            $message['depth'] = $depth;
            $ordered[] = $message;
            foreach ($children[$message_id] ?? [] as $child_id) {
                $walk($child_id, $depth + 1);
            }
        };
        $walk($root_message_id, 0);

        foreach ($by_id as $message_id => $message) {
            if (!isset($visited[$message_id])) {
                $message['depth'] = 0;
                $ordered[] = $message;
            }
        }
        return $ordered;
    }

    public function thread_data()
    {
        $rcmail = rcmail::get_instance();
        $uid = (int) rcube_utils::get_input_value('_uid', rcube_utils::INPUT_POST);
        $folder = rcube_utils::get_input_string('_mbox', rcube_utils::INPUT_POST);
        $storage = $rcmail->get_storage();
        $current_message = $uid && $folder ? new rcube_message($uid, $folder) : null;
        $headers = $current_message ? $current_message->headers : null;
        $index = $this->load_thread_index();
        $payload = ['message_count' => 0, 'messages' => []];

        if ($headers && $index) {
            $thread_id = null;
            foreach ($this->message_id_candidates($headers) as $candidate) {
                if (isset($index['lookup'][$candidate])) {
                    $thread_id = $index['lookup'][$candidate];
                    break;
                }
            }

            if ($thread_id && isset($index['threads'][$thread_id])) {
                $thread = $index['threads'][$thread_id];
                $messages = $thread['messages'];
                $known = [];
                foreach ($messages as $message) {
                    $known[$message['message_id']] = true;
                }
                $messages = array_merge(
                    $messages,
                    $this->discover_live_replies($storage, $thread['root_message_id'], $known)
                );
                $this->resolve_seed_uids($storage, $messages);
                $messages = $this->order_tree($messages, $thread['root_message_id']);
                $current_id = $this->normalize_message_id($headers->messageID);
                foreach ($messages as &$message) {
                    $message['current'] = $message['message_id'] === $current_id;
                }
                unset($message);
                $payload = [
                    'thread_id' => $thread_id,
                    'root_message_id' => $thread['root_message_id'],
                    'subject' => $thread['subject'],
                    'message_count' => count($messages),
                    'messages' => $messages,
                ];
            }
        }

        $rcmail->output->command('plugin.webarena-thread-data', $payload);
        $rcmail->output->send();
    }
}
