#!/bin/bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

EXPECTED_FILES_PER_USER=5000
EXPECTED_ROOT_WORK_FILES_PER_USER=6
EXPECTED_MANAGED_FOLDERS_PER_USER=20
EXPECTED_REAL_DOCUMENTS_PER_USER=100
EXPECTED_FINANCIAL_SOURCES_PER_USER=1
EXPECTED_FINANCIAL_DERIVATIVES_PER_USER=20
EXPECTED_DATASET_ORDERS_PER_USER=160
EXPECTED_DATASET_INVOICES_PER_USER=120
EXPECTED_DATASET_PLOTS_PER_USER=157
EXPECTED_SYNTHETIC_INVOICES_PER_USER=40
EXPECTED_INVOICE_PDFS_PER_USER=348
EXPECTED_PURCHASE_ORDERS_PER_USER=292
EXPECTED_PURCHASE_ORDER_YEARS='2022:42,2023:57,2024:76,2025:68,2026:49'
EXPECTED_PURCHASE_REQUISITION_PDFS_PER_USER=146
EXPECTED_PURCHASE_REQUISITION_DOCX_PER_USER=146
EXPECTED_VENDOR_ASSESSMENT_PDFS_PER_USER=20
EXPECTED_VENDOR_ASSESSMENT_DOCX_PER_USER=20
EXPECTED_VENDOR_NOTES_PER_USER=40
EXPECTED_VENDOR_MASTERS_PER_USER=8
EXPECTED_PROCUREMENT_FILES_PER_USER=672
EXPECTED_TIMESHEETS_PER_USER=54
EXPECTED_TIMESHEET_YEARS='2022:12,2023:12,2024:12,2025:12,2026:6'
EXPECTED_2026_TIMESHEET_MONTHS='1,2,3,4,5,6'
EXPECTED_TIMESHEET_WORKER_CATEGORIES=6
EXPECTED_CONTACTS_PER_USER=100
EXPECTED_EVENTS_PER_USER=50
EXPECTED_RECURRING_EVENTS_PER_USER=8
EXPECTED_ONE_TIME_EVENTS_PER_USER=42
EXPECTED_BUSY_DAYS_PER_USER=12
EXPECTED_NOTIFICATIONS_PER_USER=12
EXPECTED_TALK_MESSAGES=425
EXPECTED_TALK_THREADS=54
EXPECTED_TALK_REPLIES=363
TOKEN_FILE="/var/www/html/data/.webarena-talk-tokens.tsv"
ROOMS_FILE="/generated-seed/talk/rooms.tsv"
UNREAD_FILE="/generated-seed/talk/unread.tsv"
NOTIFICATIONS_FILE="/generated-seed/notifications/notifications.tsv"

assert_equal() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [ "$actual" -ne "$expected" ]; then
    echo "ERROR: ${label} is ${actual}; expected ${expected}" >&2
    exit 1
  fi
  echo "Verified ${label}: ${actual}"
}

assert_at_least() {
  local actual="$1"
  local minimum="$2"
  local label="$3"
  if [ "$actual" -lt "$minimum" ]; then
    echo "ERROR: ${label} is ${actual}; expected at least ${minimum}" >&2
    exit 1
  fi
  echo "Verified ${label}: ${actual}"
}

assert_string_equal() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [ "$actual" != "$expected" ]; then
    echo "ERROR: ${label} is '${actual}'; expected '${expected}'" >&2
    exit 1
  fi
  echo "Verified ${label}: ${actual}"
}

count_dav_content_type() {
  local user="$1"
  local url="$2"
  local content_type="$3"
  local response
  response="$(curl --fail-with-body --silent --show-error \
    -u "${user}:agentpass" -X PROPFIND -H 'Depth: 1' "$url")"
  printf '%s' "$response" | grep -Eo "<d:getcontenttype>${content_type}[^<]*" | wc -l | tr -d ' '
}

echo "Verifying Nextcloud seed counts..."

for user in maya.patel daniel.brooks; do
  file_count="$(find "/var/www/html/data/${user}/files" -type f | wc -l | tr -d ' ')"
  contact_count="$(count_dav_content_type "$user" "http://127.0.0.1/remote.php/dav/addressbooks/users/${user}/contacts/" 'text/vcard')"
  event_count="$(count_dav_content_type "$user" "http://127.0.0.1/remote.php/dav/calendars/${user}/personal/" 'text/calendar')"
  assert_equal "$file_count" "$EXPECTED_FILES_PER_USER" "${user} files"
  assert_equal "$contact_count" "$EXPECTED_CONTACTS_PER_USER" "${user} contacts"
  assert_equal "$event_count" "$EXPECTED_EVENTS_PER_USER" "${user} calendar events"
  test ! -e "/var/www/html/data/${user}/files/Customer Support"

  root_work_file_count="$(find "/var/www/html/data/${user}/files" -maxdepth 1 -type f | wc -l | tr -d ' ')"
  read -r root_manifest_count root_hash_mismatches root_link_errors < <(
    php -r '
      $owner = $argv[1];
      $count = $hashMismatches = $linkErrors = 0;
      $records = [];
      foreach (file("/generated-seed/provenance/manifest.jsonl", FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $record = json_decode($line, true);
        if (($record["entity_type"] ?? "") === "file" && ($record["owner"] ?? "") === $owner) {
          $records[] = $record;
        }
      }
      foreach ($records as $record) {
        if (($record["root_work_file"] ?? false) !== true) continue;
        $count++;
        if (str_contains($record["path"], "/")) $linkErrors++;
        $path = "/var/www/html/data/{$owner}/files/" . $record["path"];
        if (!is_file($path) || hash_file("sha256", $path) !== $record["sha256"]) $hashMismatches++;
        if (($record["document_type"] ?? "") !== "Purchase Order Reference Copy") continue;
        $matches = array_values(array_filter($records, fn($candidate) =>
          ($candidate["document_type"] ?? "") === "Purchase Order"
          && ($candidate["document_id"] ?? "") === ($record["related_purchase_order"] ?? "")
          && ($candidate["path"] ?? "") === ($record["original_path"] ?? "")
        ));
        if (count($matches) !== 1 || ($matches[0]["sha256"] ?? "") !== $record["sha256"]) $linkErrors++;
      }
      echo "$count $hashMismatches $linkErrors", PHP_EOL;
    ' "$user"
  )
  assert_equal "$root_work_file_count" "$EXPECTED_ROOT_WORK_FILES_PER_USER" "${user} files visible at the All files root"
  assert_equal "$root_manifest_count" "$EXPECTED_ROOT_WORK_FILES_PER_USER" "${user} root work-file manifest records"
  assert_equal "$root_hash_mismatches" 0 "${user} root work-file hash mismatches"
  assert_equal "$root_link_errors" 0 "${user} root work-file linkage errors"

  read -r managed_folder_count managed_folder_min managed_folder_max managed_folder_errors < <(
    php -r '
      $owner = $argv[1];
      $targets = json_decode(file_get_contents("/generated-seed/managed_folder_counts.json"), true)[$owner] ?? [];
      $errors = 0;
      $counts = [];
      foreach ($targets as $folder => $expected) {
        $root = "/var/www/html/data/{$owner}/files/{$folder}";
        $actual = 0;
        if (is_dir($root)) {
          $iterator = new RecursiveIteratorIterator(
            new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS)
          );
          foreach ($iterator as $entry) if ($entry->isFile()) $actual++;
        }
        $counts[] = $actual;
        if ($expected < 100 || $expected > 400 || $actual !== $expected) $errors++;
      }
      echo count($targets), " ", min($counts), " ", max($counts), " $errors", PHP_EOL;
    ' "$user"
  )
  assert_equal "$managed_folder_count" "$EXPECTED_MANAGED_FOLDERS_PER_USER" "${user} managed business folders"
  assert_at_least "$managed_folder_min" 100 "${user} smallest managed-folder document count"
  assert_equal "$managed_folder_errors" 0 "${user} managed-folder distribution errors (maximum observed ${managed_folder_max})"

  read -r real_document_count real_document_hash_mismatches < <(
    php -r '
      $owner = $argv[1];
      $manifestPath = "/generated-seed/provenance/manifest.jsonl";
      $count = $mismatches = 0;
      foreach (file($manifestPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $record = json_decode($line, true);
        if (($record["entity_type"] ?? "") !== "file"
            || ($record["owner"] ?? "") !== $owner
            || ($record["source"] ?? "") !== "retained-open-document") {
          continue;
        }
        $count++;
        $path = "/var/www/html/data/{$owner}/files/" . $record["path"];
        if (!is_file($path) || hash_file("sha256", $path) !== $record["sha256"]) $mismatches++;
      }
      echo "$count $mismatches", PHP_EOL;
    ' "$user"
  )
  assert_equal "$real_document_count" "$EXPECTED_REAL_DOCUMENTS_PER_USER" "${user} retained real documents"
  assert_equal "$real_document_hash_mismatches" 0 "${user} retained real-document hash mismatches"

  read -r financial_source_count financial_derivative_count dataset_order_count dataset_invoice_count dataset_plot_count dataset_link_errors synthetic_invoice_count invoice_template_count purchase_order_count purchase_order_template_count purchase_order_years financial_hash_mismatches < <(
    php -r '
      $owner = $argv[1];
      $sourceCount = $derivativeCount = $syntheticInvoiceCount = $purchaseOrderCount = $mismatches = $linkErrors = 0;
      $templates = $purchaseOrderTemplates = $purchaseOrderYears = [];
      $datasetOrders = $datasetInvoices = $datasetPlots = [];
      foreach (file("/generated-seed/provenance/manifest.jsonl", FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $record = json_decode($line, true);
        if (($record["entity_type"] ?? "") !== "file" || ($record["owner"] ?? "") !== $owner) continue;
        $source = $record["source"] ?? "";
        if ($source === "open-dataset-source") $sourceCount++;
        elseif ($source === "derived-open-dataset-document") $derivativeCount++;
        elseif ($source === "derived-open-dataset-order") $datasetOrders[$record["document_id"]] = $record;
        elseif ($source === "derived-open-dataset-invoice") $datasetInvoices[] = $record;
        elseif ($source === "derived-open-dataset-plot") $datasetPlots[] = $record;
        elseif ($source === "generated" && isset($record["invoice_template"])) {
          $syntheticInvoiceCount++;
          $templates[$record["invoice_template"]] = true;
        }
        elseif (isset($record["purchase_order_template"])) {
          $purchaseOrderCount++;
          $purchaseOrderTemplates[$record["purchase_order_template"]] = true;
          $year = (string)$record["purchase_order_year"];
          $purchaseOrderYears[$year] = ($purchaseOrderYears[$year] ?? 0) + 1;
        }
        else continue;
        $path = "/var/www/html/data/{$owner}/files/" . $record["path"];
        if (!is_file($path) || hash_file("sha256", $path) !== $record["sha256"]) $mismatches++;
      }
      foreach ($datasetInvoices as $invoice) {
        $order = $datasetOrders[$invoice["related_order_document_id"]] ?? null;
        if (!$order
            || ($order["path"] ?? "") !== ($invoice["related_order_path"] ?? "")
            || ($order["source_record_id"] ?? "") !== ($invoice["source_record_id"] ?? "")) $linkErrors++;
      }
      foreach ($datasetPlots as $plot) {
        foreach ($plot["related_order_document_ids"] ?? [] as $orderId) {
          if (!isset($datasetOrders[$orderId])) $linkErrors++;
        }
      }
      ksort($purchaseOrderYears);
      $yearParts = [];
      foreach ($purchaseOrderYears as $year => $count) $yearParts[] = "$year:$count";
      echo "$sourceCount $derivativeCount ", count($datasetOrders), " ", count($datasetInvoices),
        " ", count($datasetPlots), " $linkErrors $syntheticInvoiceCount ", count($templates),
        " $purchaseOrderCount ", count($purchaseOrderTemplates), " ", implode(",", $yearParts), " $mismatches", PHP_EOL;
    ' "$user"
  )
  assert_equal "$financial_source_count" "$EXPECTED_FINANCIAL_SOURCES_PER_USER" "${user} open financial source records"
  assert_equal "$financial_derivative_count" "$EXPECTED_FINANCIAL_DERIVATIVES_PER_USER" "${user} derived open financial documents"
  assert_equal "$dataset_order_count" "$EXPECTED_DATASET_ORDERS_PER_USER" "${user} dataset-derived customer orders"
  assert_equal "$dataset_invoice_count" "$EXPECTED_DATASET_INVOICES_PER_USER" "${user} dataset-derived invoices"
  assert_equal "$dataset_plot_count" "$EXPECTED_DATASET_PLOTS_PER_USER" "${user} dataset-derived order plots"
  assert_equal "$dataset_link_errors" 0 "${user} dataset order/invoice/plot linkage errors"
  assert_equal "$synthetic_invoice_count" "$EXPECTED_SYNTHETIC_INVOICES_PER_USER" "${user} templated synthetic invoices"
  assert_equal "$invoice_template_count" 5 "${user} distinct synthetic invoice templates"
  assert_equal "$purchase_order_count" "$EXPECTED_PURCHASE_ORDERS_PER_USER" "${user} synthetic purchase orders"
  assert_equal "$purchase_order_template_count" 5 "${user} distinct purchase-order templates"
  assert_string_equal "$purchase_order_years" "$EXPECTED_PURCHASE_ORDER_YEARS" "${user} purchase orders by year"
  assert_equal "$financial_hash_mismatches" 0 "${user} open financial-document hash mismatches"

  invoice_pdf_count="$(find "/var/www/html/data/${user}/files/Finance/Invoices" -maxdepth 1 -type f -name '*.pdf' | wc -l | tr -d ' ')"
  nested_invoice_directory_count="$(find "/var/www/html/data/${user}/files/Finance/Invoices" -mindepth 1 -type d | wc -l | tr -d ' ')"
  midd_file_count="$(find "/var/www/html/data/${user}/files" -iname '*midd*' | wc -l | tr -d ' ')"
  assert_equal "$invoice_pdf_count" "$EXPECTED_INVOICE_PDFS_PER_USER" "${user} flat invoice PDFs"
  assert_equal "$nested_invoice_directory_count" 0 "${user} nested invoice directories"
  assert_equal "$midd_file_count" 0 "${user} MIDD files"
  test ! -e "/var/www/html/data/${user}/files/Finance/Customer Invoices"

  purchase_order_pdf_count="$(find "/var/www/html/data/${user}/files/Procurement/Purchase Orders" -type f -name '*.pdf' | wc -l | tr -d ' ')"
  purchase_order_other_count="$(find "/var/www/html/data/${user}/files/Procurement/Purchase Orders" -type f ! -name '*.pdf' | wc -l | tr -d ' ')"
  assert_equal "$purchase_order_pdf_count" "$EXPECTED_PURCHASE_ORDERS_PER_USER" "${user} purchase-order PDFs"
  assert_equal "$purchase_order_other_count" 0 "${user} non-PDF purchase orders"

  purchase_requisition_pdf_count="$(find "/var/www/html/data/${user}/files/Procurement/Purchase Requisitions" -type f -name '*.pdf' | wc -l | tr -d ' ')"
  purchase_requisition_docx_count="$(find "/var/www/html/data/${user}/files/Procurement/Purchase Requisitions" -type f -name '*.docx' | wc -l | tr -d ' ')"
  purchase_requisition_other_count="$(find "/var/www/html/data/${user}/files/Procurement/Purchase Requisitions" -type f ! \( -name '*.pdf' -o -name '*.docx' \) | wc -l | tr -d ' ')"
  vendor_assessment_pdf_count="$(find "/var/www/html/data/${user}/files/Procurement/Vendor Assessments" -type f -name '*.pdf' | wc -l | tr -d ' ')"
  vendor_assessment_docx_count="$(find "/var/www/html/data/${user}/files/Procurement/Vendor Assessments" -type f -name '*.docx' | wc -l | tr -d ' ')"
  vendor_assessment_other_count="$(find "/var/www/html/data/${user}/files/Procurement/Vendor Assessments" -type f ! \( -name '*.pdf' -o -name '*.docx' \) | wc -l | tr -d ' ')"
  vendor_note_count="$(find "/var/www/html/data/${user}/files/Procurement/Vendor Notes" -type f -name '*.txt' | wc -l | tr -d ' ')"
  vendor_note_other_count="$(find "/var/www/html/data/${user}/files/Procurement/Vendor Notes" -type f ! -name '*.txt' | wc -l | tr -d ' ')"
  vendor_master_count="$(find "/var/www/html/data/${user}/files/Procurement/Vendor Master Data" -type f -name '*.docx' | wc -l | tr -d ' ')"
  vendor_master_other_count="$(find "/var/www/html/data/${user}/files/Procurement/Vendor Master Data" -type f ! -name '*.docx' | wc -l | tr -d ' ')"
  procurement_file_count="$(find "/var/www/html/data/${user}/files/Procurement" -type f | wc -l | tr -d ' ')"
  assert_equal "$purchase_requisition_pdf_count" "$EXPECTED_PURCHASE_REQUISITION_PDFS_PER_USER" "${user} purchase-requisition PDFs"
  assert_equal "$purchase_requisition_docx_count" "$EXPECTED_PURCHASE_REQUISITION_DOCX_PER_USER" "${user} purchase-requisition DOCX files"
  assert_equal "$purchase_requisition_other_count" 0 "${user} purchase requisitions in other formats"
  assert_equal "$vendor_assessment_pdf_count" "$EXPECTED_VENDOR_ASSESSMENT_PDFS_PER_USER" "${user} vendor-assessment PDFs"
  assert_equal "$vendor_assessment_docx_count" "$EXPECTED_VENDOR_ASSESSMENT_DOCX_PER_USER" "${user} vendor-assessment DOCX files"
  assert_equal "$vendor_assessment_other_count" 0 "${user} vendor assessments in other formats"
  assert_equal "$vendor_note_count" "$EXPECTED_VENDOR_NOTES_PER_USER" "${user} vendor notes"
  assert_equal "$vendor_note_other_count" 0 "${user} vendor notes in other formats"
  assert_equal "$vendor_master_count" "$EXPECTED_VENDOR_MASTERS_PER_USER" "${user} vendor-master DOCX files"
  assert_equal "$vendor_master_other_count" 0 "${user} vendor master records in other formats"
  assert_equal "$procurement_file_count" "$EXPECTED_PROCUREMENT_FILES_PER_USER" "${user} linked procurement files"

  read -r procurement_consistency_errors procurement_hash_mismatches < <(
    php -r '
      $owner = $argv[1];
      $errors = $hashMismatches = 0;
      $orders = $requisitions = $assessments = $notes = $masters = [];
      foreach (file("/generated-seed/provenance/manifest.jsonl", FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $record = json_decode($line, true);
        if (($record["entity_type"] ?? "") !== "file"
            || ($record["owner"] ?? "") !== $owner
            || !str_starts_with($record["path"] ?? "", "Procurement/")) continue;
        $path = "/var/www/html/data/{$owner}/files/" . $record["path"];
        if (!is_file($path) || hash_file("sha256", $path) !== $record["sha256"]) $hashMismatches++;
        $type = $record["document_type"] ?? "";
        if ($type === "Purchase Order") $orders[$record["document_id"]] = $record;
        elseif ($type === "Purchase Requisition") $requisitions[$record["related_purchase_order"]][] = $record;
        elseif ($type === "Vendor Assessment") $assessments[$record["vendor_id"] . "|" . $record["assessment_year"]] = $record;
        elseif ($type === "Vendor Review Note") $notes[$record["vendor_id"] . "|" . $record["review_year"]] = $record;
        elseif ($type === "Vendor Master Record") $masters[$record["vendor_id"]] = $record;
        else $errors++;
      }

      $consistentFields = ["subject", "procurement_record_key", "vendor_id", "order_total", "cost_center", "project", "requested_by", "line_item_skus"];
      $annual = $lifetime = [];
      foreach ($orders as $orderId => $order) {
        if (count($requisitions[$orderId] ?? []) !== 1) {
          $errors++;
        } else {
          $requisition = $requisitions[$orderId][0];
          if (($order["related_requisition"] ?? null) !== ($requisition["document_id"] ?? null)) $errors++;
          foreach ($consistentFields as $field) {
            if (($order[$field] ?? null) !== ($requisition[$field] ?? null)) $errors++;
          }
        }
        $annualKey = $order["vendor_id"] . "|" . $order["purchase_order_year"];
        if (!isset($annual[$annualKey])) $annual[$annualKey] = ["ids" => [], "count" => 0, "total" => 0.0];
        if (!isset($lifetime[$order["vendor_id"]])) $lifetime[$order["vendor_id"]] = ["ids" => [], "count" => 0, "total" => 0.0];
        $annual[$annualKey]["ids"][] = $orderId;
        $annual[$annualKey]["count"]++;
        $annual[$annualKey]["total"] += (float)$order["order_total"];
        $lifetime[$order["vendor_id"]]["ids"][] = $orderId;
        $lifetime[$order["vendor_id"]]["count"]++;
        $lifetime[$order["vendor_id"]]["total"] += (float)$order["order_total"];
      }
      foreach ($requisitions as $orderId => $linked) if (!isset($orders[$orderId]) || count($linked) !== 1) $errors++;

      foreach ($annual as $key => $summary) {
        $assessment = $assessments[$key] ?? null;
        $note = $notes[$key] ?? null;
        if (!$assessment || !$note) {
          $errors++;
          continue;
        }
        $expectedIds = $summary["ids"];
        $actualIds = $assessment["related_purchase_orders"] ?? [];
        sort($expectedIds);
        sort($actualIds);
        if ($expectedIds !== $actualIds
            || (int)$assessment["purchase_order_count"] !== $summary["count"]
            || abs((float)$assessment["purchase_order_total"] - round($summary["total"], 2)) > 0.001) $errors++;
        if (($note["related_assessment"] ?? null) !== ($assessment["document_id"] ?? null)
            || (int)$note["purchase_order_count"] !== $summary["count"]
            || abs((float)$note["purchase_order_total"] - round($summary["total"], 2)) > 0.001) $errors++;
      }
      if (count($assessments) !== count($annual) || count($notes) !== count($annual)) $errors++;

      foreach ($lifetime as $vendorId => $summary) {
        $master = $masters[$vendorId] ?? null;
        if (!$master) {
          $errors++;
          continue;
        }
        $expectedIds = $summary["ids"];
        $actualIds = $master["related_purchase_orders"] ?? [];
        sort($expectedIds);
        sort($actualIds);
        if ($expectedIds !== $actualIds
            || (int)$master["purchase_order_count"] !== $summary["count"]
            || abs((float)$master["purchase_order_total"] - round($summary["total"], 2)) > 0.001) $errors++;
      }
      if (count($masters) !== count($lifetime)) $errors++;
      echo "$errors $hashMismatches", PHP_EOL;
    ' "$user"
  )
  assert_equal "$procurement_consistency_errors" 0 "${user} procurement cross-folder consistency errors"
  assert_equal "$procurement_hash_mismatches" 0 "${user} procurement hash mismatches"

  read -r timesheet_manifest_count timesheet_years timesheet_2026_months timesheet_category_mismatches timesheet_hash_mismatches < <(
    php -r '
      $owner = $argv[1];
      $count = $categoryMismatches = $hashMismatches = 0;
      $years = $months2026 = [];
      foreach (file("/generated-seed/provenance/manifest.jsonl", FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $record = json_decode($line, true);
        if (($record["entity_type"] ?? "") !== "file"
            || ($record["owner"] ?? "") !== $owner
            || ($record["document_type"] ?? "") !== "Monthly Timesheet") continue;
        $count++;
        $year = (string)$record["timesheet_year"];
        $years[$year] = ($years[$year] ?? 0) + 1;
        if ($year === "2026") $months2026[] = (int)$record["timesheet_month"];
        if (count($record["worker_categories"] ?? []) !== (int)$argv[2]) $categoryMismatches++;
        $path = "/var/www/html/data/{$owner}/files/" . $record["path"];
        if (!is_file($path) || hash_file("sha256", $path) !== $record["sha256"]) $hashMismatches++;
      }
      ksort($years);
      sort($months2026);
      $yearParts = [];
      foreach ($years as $year => $yearCount) $yearParts[] = "$year:$yearCount";
      echo "$count ", implode(",", $yearParts), " ", implode(",", $months2026),
        " $categoryMismatches $hashMismatches", PHP_EOL;
    ' "$user" "$EXPECTED_TIMESHEET_WORKER_CATEGORIES"
  )
  timesheet_xlsx_count="$(find "/var/www/html/data/${user}/files/People/Timesheets" -type f -name '*.xlsx' | wc -l | tr -d ' ')"
  timesheet_other_count="$(find "/var/www/html/data/${user}/files/People/Timesheets" -type f ! -name '*.xlsx' | wc -l | tr -d ' ')"
  assert_equal "$timesheet_manifest_count" "$EXPECTED_TIMESHEETS_PER_USER" "${user} monthly timesheet manifest records"
  assert_string_equal "$timesheet_years" "$EXPECTED_TIMESHEET_YEARS" "${user} timesheets by year"
  assert_string_equal "$timesheet_2026_months" "$EXPECTED_2026_TIMESHEET_MONTHS" "${user} 2026 timesheet months"
  assert_equal "$timesheet_category_mismatches" 0 "${user} timesheets with incorrect worker-category coverage"
  assert_equal "$timesheet_hash_mismatches" 0 "${user} timesheet hash mismatches"
  assert_equal "$timesheet_xlsx_count" "$EXPECTED_TIMESHEETS_PER_USER" "${user} XLSX timesheets"
  assert_equal "$timesheet_other_count" 0 "${user} non-XLSX timesheets"

  calendar_payload="$(curl --fail-with-body --silent --show-error \
    -u "${user}:agentpass" -X REPORT -H 'Depth: 1' \
    -H 'Content-Type: application/xml; charset=utf-8' \
    --data '<?xml version="1.0"?><cal:calendar-query xmlns:d="DAV:" xmlns:cal="urn:ietf:params:xml:ns:caldav"><d:prop><cal:calendar-data/></d:prop><cal:filter><cal:comp-filter name="VCALENDAR"><cal:comp-filter name="VEVENT"/></cal:comp-filter></cal:filter></cal:calendar-query>' \
    "http://127.0.0.1/remote.php/dav/calendars/${user}/personal/")"
  read -r recurring_count one_time_count busy_day_count max_meetings_per_day explicit_timezone_count before_nine_count earliest_start < <(
    printf '%s' "$calendar_payload" | php -r '
      $payload = stream_get_contents(STDIN);
      preg_match_all("/BEGIN:VEVENT(.*?)END:VEVENT/s", $payload, $eventBlocks);
      $recurring = $oneTime = $explicitTimezone = $beforeNine = 0;
      $days = [];
      $startTimes = [];
      foreach ($eventBlocks[1] as $event) {
        if (str_contains($event, "RRULE:")) $recurring++; else $oneTime++;
        if (preg_match("/DTSTART;TZID=America\\/Toronto:(\\d{8})T(\\d{6})/", $event, $start)) {
          $explicitTimezone++;
          $days[$start[1]] = ($days[$start[1]] ?? 0) + 1;
          $time = (int)substr($start[2], 0, 4);
          $startTimes[] = $time;
          if ($time < 900) $beforeNine++;
        }
      }
      $busy = count(array_filter($days, static fn ($count) => $count >= 4));
      $maximum = $days ? max($days) : 0;
      $earliest = $startTimes ? min($startTimes) : 0;
      echo $recurring, " ", $oneTime, " ", $busy, " ", $maximum, " ", $explicitTimezone, " ", $beforeNine, " ", $earliest, PHP_EOL;
    '
  )
  assert_equal "$recurring_count" "$EXPECTED_RECURRING_EVENTS_PER_USER" "${user} recurring calendar series"
  assert_equal "$one_time_count" "$EXPECTED_ONE_TIME_EVENTS_PER_USER" "${user} one-time calendar meetings"
  assert_at_least "$busy_day_count" "$EXPECTED_BUSY_DAYS_PER_USER" "${user} business days with at least four meetings"
  assert_at_least "$max_meetings_per_day" 4 "${user} maximum meetings on one day"
  assert_equal "$explicit_timezone_count" "$EXPECTED_EVENTS_PER_USER" "${user} meetings using America/Toronto local time"
  assert_equal "$before_nine_count" 0 "${user} meetings starting before 9:00 AM"
  assert_equal "$earliest_start" 900 "${user} earliest local meeting start (HHMM)"

  read -r cross_service_errors support_contact_count < <(
    php -r '
      $owner = $argv[1];
      $errors = 0;
      $files = $contacts = $events = [];
      foreach (file("/generated-seed/provenance/manifest.jsonl", FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $record = json_decode($line, true);
        if (($record["owner"] ?? "") !== $owner) continue;
        if (($record["entity_type"] ?? "") === "file") $files[$record["path"]] = $record;
        elseif (($record["entity_type"] ?? "") === "contact") $contacts[$record["uid"]] = $record;
        elseif (($record["entity_type"] ?? "") === "calendar_event") $events[] = $record;
      }
      $supportNames = ["Sarah Chen", "Priya Nair", "Marcus Johnson", "Leon Greene"];
      $contactNames = array_column($contacts, "display_name");
      $supportCount = count(array_intersect($supportNames, $contactNames));
      if ($supportCount !== 4 || count($events) !== 50) $errors++;
      $customers = $projects = $vendors = $teams = [];
      foreach ($events as $event) {
        $fileRecord = $files[$event["related_file"]] ?? null;
        if (!$fileRecord || ($fileRecord["sha256"] ?? "") !== ($event["related_file_sha256"] ?? "")) $errors++;
        $attendees = $event["attendee_contact_uids"] ?? [];
        if (count($attendees) !== 3) $errors++;
        foreach ($attendees as $uid) if (!isset($contacts[$uid])) $errors++;
        $ics = file_get_contents("/generated-seed/calendars/{$owner}/" . $event["uid"] . ".ics");
        if (substr_count($ics, "ATTENDEE;CN=") !== 3 || !str_contains($ics, $event["related_file"])) $errors++;
        $customers[$event["related_customer"]] = true;
        $projects[$event["related_project"]] = true;
        $vendors[$event["related_vendor"]] = true;
        $teams[$event["related_team"]] = true;
      }
      if (count($customers) !== 10 || count($projects) !== 10 || count($vendors) !== 8 || count($teams) !== 8) $errors++;
      echo "$errors $supportCount", PHP_EOL;
    ' "$user"
  )
  assert_equal "$cross_service_errors" 0 "${user} Files/Contacts/Calendar consistency errors"
  assert_equal "$support_contact_count" 4 "${user} Talk participant contacts"
done

for required_document in \
  'Marketing Assistant Resume.docx' \
  'Marketing Assistant Resume-2.docx' \
  'Marketing Assistant Resume.pdf' \
  'chloroplastmarketingstrategy.docx' \
  'clientmeetingmemo.docx' \
  'clientmeetingmemo.pdf' \
  'sample essay.docx'; do
  test -f "/var/www/html/data/maya.patel/files/documents/${required_document}"
done

contact_payload="$(curl --fail-with-body --silent --show-error \
  -u 'maya.patel:agentpass' -X REPORT -H 'Depth: 1' \
  -H 'Content-Type: application/xml; charset=utf-8' \
  --data '<?xml version="1.0"?><card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><card:address-data/></d:prop></card:addressbook-query>' \
  'http://127.0.0.1/remote.php/dav/addressbooks/users/maya.patel/contacts/')"
grep -q 'FN:Leon Greene' <<< "$contact_payload"
grep -q 'NICKNAME:Leon Green' <<< "$contact_payload"
grep -q 'leon@cedarstone.test' <<< "$contact_payload"
grep -q '9999999999' <<< "$contact_payload"

talk_total=0
talk_maya=0
talk_daniel=0
talk_sarah=0
talk_priya=0
talk_marcus=0
talk_leon=0
talk_threads=0
talk_replies=0
project_alpha_count=0

while IFS=$'\t' read -r room token; do
  response="$(curl --fail-with-body --silent --show-error \
    -u 'maya.patel:agentpass' \
    -H 'OCS-APIRequest: true' \
    -H 'Accept: application/json' \
    "http://127.0.0.1/ocs/v2.php/apps/spreed/api/v1/chat/${token}?lookIntoFuture=1&setReadMarker=0&limit=200")"
  read -r room_total room_maya room_daniel room_sarah room_priya room_marcus room_leon room_threads room_replies < <(
    printf '%s' "$response" | php -r '
      $payload = json_decode(stream_get_contents(STDIN), true);
      $rows = $payload["ocs"]["data"] ?? [];
      $counts = ["maya.patel" => 0, "daniel.brooks" => 0, "sarah" => 0, "priya" => 0, "marcus" => 0, "leon" => 0];
      $total = $threads = $replies = 0;
      foreach ($rows as $row) {
        $actor = $row["actorId"] ?? "";
        if (($row["messageType"] ?? "") === "comment" && array_key_exists($actor, $counts)) {
          $total++;
          $counts[$actor]++;
          if (!empty($row["parent"])) $replies++;
          if (!empty($row["threadTitle"]) && (int)($row["threadId"] ?? 0) === (int)($row["id"] ?? -1)) $threads++;
        }
      }
      echo $total, " ", implode(" ", $counts), " $threads $replies", PHP_EOL;
    '
  )
  talk_total=$((talk_total + room_total))
  talk_maya=$((talk_maya + room_maya))
  talk_daniel=$((talk_daniel + room_daniel))
  talk_sarah=$((talk_sarah + room_sarah))
  talk_priya=$((talk_priya + room_priya))
  talk_marcus=$((talk_marcus + room_marcus))
  talk_leon=$((talk_leon + room_leon))
  talk_threads=$((talk_threads + room_threads))
  talk_replies=$((talk_replies + room_replies))

  participant_response="$(curl --fail-with-body --silent --show-error \
    -u 'maya.patel:agentpass' \
    -H 'OCS-APIRequest: true' \
    -H 'Accept: application/json' \
    "http://127.0.0.1/ocs/v2.php/apps/spreed/api/v4/room/${token}/participants")"
  actual_participants="$(printf '%s' "$participant_response" | php -r '
    $payload = json_decode(stream_get_contents(STDIN), true);
    $ids = [];
    foreach (($payload["ocs"]["data"] ?? []) as $participant) {
      if (($participant["actorType"] ?? "") === "users") $ids[] = $participant["actorId"];
    }
    sort($ids);
    echo implode(",", $ids);
  ')"
  expected_participants="$(awk -F '\t' -v room="$room" '$1 == room {print $2; exit}' "$ROOMS_FILE" | tr ',' '\n' | sort | paste -sd, -)"
  assert_string_equal "$actual_participants" "$expected_participants" "${room} Talk participants"

  if [ "$room" = "Project Alpha" ]; then
    project_alpha_count="$room_total"
    grep -q 'client meeting got moved to next Thursday' <<< "$response"
  fi
done < "$TOKEN_FILE"

assert_equal "$talk_total" "$EXPECTED_TALK_MESSAGES" "authored Talk messages"
assert_equal "$talk_maya" 178 "Talk messages authored by Maya Patel"
assert_equal "$talk_daniel" 167 "Talk messages authored by Daniel Brooks"
assert_equal "$talk_sarah" 20 "Talk messages authored by sarah"
assert_equal "$talk_priya" 20 "Talk messages authored by priya"
assert_equal "$talk_marcus" 20 "Talk messages authored by marcus"
assert_equal "$talk_leon" 20 "Talk messages authored by leon"
assert_equal "$talk_threads" "$EXPECTED_TALK_THREADS" "Talk thread roots"
assert_equal "$talk_replies" "$EXPECTED_TALK_REPLIES" "threaded Talk replies"
assert_equal "$project_alpha_count" 8 "Project Alpha canonical messages"

while IFS=$'\t' read -r user room expected_unread; do
  [ -n "$user" ] || continue
  room_response="$(curl --fail-with-body --silent --show-error \
    -u "${user}:agentpass" \
    -H 'OCS-APIRequest: true' \
    -H 'Accept: application/json' \
    'http://127.0.0.1/ocs/v2.php/apps/spreed/api/v4/room')"
  actual_unread="$(printf '%s' "$room_response" | php -r '
    $roomName = $argv[1];
    $payload = json_decode(stream_get_contents(STDIN), true);
    foreach (($payload["ocs"]["data"] ?? []) as $room) {
      if (($room["displayName"] ?? "") === $roomName) {
        echo (int)($room["unreadMessages"] ?? 0);
        exit;
      }
    }
    echo -1;
  ' "$room")"
  assert_equal "$actual_unread" "$expected_unread" "${user} unread messages in ${room}"
done < "$UNREAD_FILE"

for user in maya.patel daniel.brooks; do
  notification_response="$(curl --fail-with-body --silent --show-error \
    -u "${user}:agentpass" \
    -H 'OCS-APIRequest: true' \
    -H 'Accept: application/json' \
    'http://127.0.0.1/ocs/v2.php/apps/notifications/api/v2/notifications?format=json')"
  read -r notification_count notification_errors < <(
    printf '%s' "$notification_response" | php -r '
      $user = $argv[1];
      $expected = [];
      foreach (file($argv[2], FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $row = str_getcsv($line, "\t");
        if (($row[0] ?? "") === $user) {
          $expected[$row[1]] = ["subject" => $row[2], "message" => $row[3]];
        }
      }
      $payload = json_decode(stream_get_contents(STDIN), true);
      $actual = [];
      foreach (($payload["ocs"]["data"] ?? []) as $notification) {
        if (($notification["object_type"] ?? "") !== "webarena_seed") continue;
        $actual[$notification["object_id"]] = [
          "subject" => $notification["subject"] ?? "",
          "message" => $notification["message"] ?? "",
        ];
      }
      $errors = count($actual) === count($expected) ? 0 : 1;
      foreach ($expected as $objectId => $content) {
        if (($actual[$objectId] ?? null) !== $content) $errors++;
      }
      echo count($actual), " $errors", PHP_EOL;
    ' "$user" "$NOTIFICATIONS_FILE"
  )
  assert_equal "$notification_count" "$EXPECTED_NOTIFICATIONS_PER_USER" "${user} business notifications"
  assert_equal "$notification_errors" 0 "${user} notification content errors"
done

read -r talk_link_count talk_link_errors < <(
  php -r '
    $files = $messages = [];
    foreach (file("/generated-seed/provenance/manifest.jsonl", FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
      $record = json_decode($line, true);
      if (($record["entity_type"] ?? "") === "file") $files[$record["owner"] . "|" . $record["path"]] = $record;
      elseif (($record["entity_type"] ?? "") === "talk_message") $messages[] = $record;
    }
    $errors = 0;
    foreach ($messages as $message) {
      $links = $message["related_files"] ?? [];
      if (count($links) !== 2) {
        $errors++;
        continue;
      }
      foreach ($links as $owner => $link) {
        $file = $files[$owner . "|" . ($link["path"] ?? "")] ?? null;
        if (!$file || ($file["sha256"] ?? "") !== ($link["sha256"] ?? "")) $errors++;
      }
    }
    echo count($messages), " $errors", PHP_EOL;
  '
)
assert_equal "$talk_link_count" "$EXPECTED_TALK_MESSAGES" "Talk messages with cross-service file links"
assert_equal "$talk_link_errors" 0 "Talk/File consistency errors"

echo "Nextcloud seed verification passed."
