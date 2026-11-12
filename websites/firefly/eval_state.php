<?php
/**
 * Read-only evaluation API for the WebArena-Pro evaluator.
 *
 * Exposes Firefly III backend state (accounts, transactions, budgets, piggy
 * banks, bills, tags, categories) as JSON so finance tasks can be graded
 * deterministically instead of relying on an LLM judge. Reads the embedded
 * MariaDB directly; no Laravel bootstrapping.
 *
 * Strictly read-only. Gated by a secret token (WP_EVAL_TOKEN) that the agent
 * under test never sees, so it cannot read answers. Disabled (403) when
 * WP_EVAL_TOKEN is unset. Served by the existing Apache from public/.
 *
 * Usage:  GET /eval_state.php
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

$dsn = sprintf(
    'mysql:host=%s;port=%s;dbname=%s;charset=utf8mb4',
    getenv('DB_HOST') ?: '127.0.0.1',
    getenv('DB_PORT') ?: '3306',
    getenv('DB_DATABASE') ?: 'firefly'
);
try {
    $pdo = new PDO($dsn, getenv('DB_USERNAME') ?: 'firefly', getenv('DB_PASSWORD') ?: '', [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
} catch (PDOException $e) {
    http_response_code(502);
    echo json_encode(['error' => 'db connection failed']);
    exit;
}

$queries = [
    // Journals flattened to one row: type, description, date, amount and the
    // source (amount < 0) / destination (amount > 0) account names.
    'journals' => "
        SELECT tj.id, tt.type, tj.description, DATE(tj.date) AS date, tj.bill_id,
               (SELECT a.name FROM transactions t JOIN accounts a ON a.id = t.account_id
                 WHERE t.transaction_journal_id = tj.id AND t.amount < 0 LIMIT 1) AS source,
               (SELECT a.name FROM transactions t JOIN accounts a ON a.id = t.account_id
                 WHERE t.transaction_journal_id = tj.id AND t.amount > 0 LIMIT 1) AS destination,
               (SELECT t.amount FROM transactions t
                 WHERE t.transaction_journal_id = tj.id AND t.amount > 0 LIMIT 1) AS amount
          FROM transaction_journals tj
          JOIN transaction_types tt ON tt.id = tj.transaction_type_id
         WHERE tj.deleted_at IS NULL",
    'accounts' => "
        SELECT a.id, a.name, at.type, a.virtual_balance
          FROM accounts a JOIN account_types at ON at.id = a.account_type_id
         WHERE a.deleted_at IS NULL",
    'budgets' => "SELECT id, name FROM budgets WHERE deleted_at IS NULL",
    'budget_limits' => "
        SELECT budget_id, DATE(start_date) AS start_date, DATE(end_date) AS end_date, amount
          FROM budget_limits",
    'piggy_banks' => "
        SELECT id, account_id, name, target_amount
          FROM piggy_banks WHERE deleted_at IS NULL",
    'piggy_bank_events' => "
        SELECT piggy_bank_id, transaction_journal_id, amount FROM piggy_bank_events",
    'bills' => "
        SELECT id, name, amount_min, amount_max FROM bills WHERE deleted_at IS NULL",
    'tags' => "SELECT id, tag FROM tags WHERE deleted_at IS NULL",
    'tag_journal' => "SELECT tag_id, transaction_journal_id FROM tag_transaction_journal",
    'categories' => "SELECT id, name FROM categories WHERE deleted_at IS NULL",
    'category_journal' => "SELECT category_id, transaction_journal_id FROM category_transaction_journal",
];

$out = [];
foreach ($queries as $name => $sql) {
    try {
        $out[$name] = $pdo->query($sql)->fetchAll();
    } catch (PDOException $e) {
        $out[$name] = [];
    }
}

echo json_encode($out);
