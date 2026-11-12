# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import generate  # noqa: E402


class GenerateSeedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.nextcloud_dir = Path(__file__).resolve().parent.parent
        cls.tempdirs = [tempfile.TemporaryDirectory(), tempfile.TemporaryDirectory()]
        cls.outputs = [Path(tempdir.name) / "seed" for tempdir in cls.tempdirs]
        cls.results = [
            generate.generate_seed(
                cls.nextcloud_dir / "seed_spec.json",
                cls.nextcloud_dir / "media",
                output,
                cls.nextcloud_dir / "seed" / "assets.json",
            )
            for output in cls.outputs
        ]

    @classmethod
    def tearDownClass(cls) -> None:
        for tempdir in cls.tempdirs:
            tempdir.cleanup()

    def test_exact_counts(self) -> None:
        self.assertEqual(generate.USERS, ("maya.patel", "daniel.brooks"))
        spec = json.loads((self.nextcloud_dir / "seed_spec.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {user: spec["talk_users"][user] for user in generate.USERS},
            {"maya.patel": "Maya Patel", "daniel.brooks": "Daniel Brooks"},
        )
        expected = {
            "files": {"maya.patel": 5000, "daniel.brooks": 5000},
            "contacts": {"maya.patel": 100, "daniel.brooks": 100},
            "calendar_events": {"maya.patel": 50, "daniel.brooks": 50},
            "notifications": {"maya.patel": 12, "daniel.brooks": 12},
            "talk_messages": 425,
            "talk_authors": {
                "maya.patel": 178,
                "daniel.brooks": 167,
                "sarah": 20,
                "priya": 20,
                "marcus": 20,
                "leon": 20,
            },
            "talk_threads": 54,
            "talk_replies": 363,
        }
        for key, value in expected.items():
            self.assertEqual(self.results[0][key], value)
        self.assertEqual(self.results[0]["manifest_records"], 10749)

    def test_generation_is_deterministic(self) -> None:
        self.assertEqual(self.results[0]["manifest_sha256"], self.results[1]["manifest_sha256"])
        self.assertEqual(
            (self.outputs[0] / "counts.json").read_bytes(),
            (self.outputs[1] / "counts.json").read_bytes(),
        )

    def test_manifest_covers_every_entity_and_uses_allowed_licenses(self) -> None:
        manifest = [
            json.loads(line)
            for line in (self.outputs[0] / "provenance" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(Counter(row["entity_type"] for row in manifest), {
            "file": 10000,
            "contact": 200,
            "calendar_event": 100,
            "notification": 24,
            "talk_message": 425,
        })
        self.assertLessEqual({row["license"] for row in manifest}, {"Apache-2.0", "CC-BY-4.0", "CC0-1.0"})
        file_keys = [(row["owner"], row["path"]) for row in manifest if row["entity_type"] == "file"]
        self.assertEqual(len(file_keys), len(set(file_keys)))

        real_documents = [row for row in manifest if row.get("source") == "retained-open-document"]
        self.assertEqual(len(real_documents), 200)
        self.assertEqual(Counter(row["owner"] for row in real_documents), {"maya.patel": 100, "daniel.brooks": 100})
        self.assertEqual(Counter(row["license"] for row in real_documents), {"CC-BY-4.0": 160, "Apache-2.0": 40})
        self.assertTrue(all(row["source_revision"] and row["source_url"] for row in real_documents))

        financial_sources = [row for row in manifest if row.get("source") == "open-dataset-source"]
        financial_derivatives = [
            row for row in manifest if row.get("source") == "derived-open-dataset-document"
        ]
        dataset_orders = [row for row in manifest if row.get("source") == "derived-open-dataset-order"]
        dataset_invoices = [row for row in manifest if row.get("source") == "derived-open-dataset-invoice"]
        dataset_plots = [row for row in manifest if row.get("source") == "derived-open-dataset-plot"]
        self.assertEqual(len(financial_sources), 2)
        self.assertEqual(Counter(row["owner"] for row in financial_sources), {"maya.patel": 1, "daniel.brooks": 1})
        self.assertEqual(len(financial_derivatives), 40)
        self.assertEqual(Counter(row["owner"] for row in financial_derivatives), {"maya.patel": 20, "daniel.brooks": 20})
        self.assertEqual(
            Counter(row["source_dataset"] for row in financial_sources + financial_derivatives),
            {"E-Commerce Dataset": 42},
        )
        self.assertTrue(all(row["license"] == "CC-BY-4.0" for row in financial_sources + financial_derivatives))
        self.assertTrue(all(row["synthetic"] is False for row in financial_sources + financial_derivatives))
        self.assertTrue(all(row["transformation"] for row in financial_derivatives))

        self.assertEqual(Counter(row["owner"] for row in dataset_orders), {"maya.patel": 160, "daniel.brooks": 160})
        self.assertEqual(Counter(row["owner"] for row in dataset_invoices), {"maya.patel": 120, "daniel.brooks": 120})
        self.assertEqual(Counter(row["owner"] for row in dataset_plots), {"maya.patel": 157, "daniel.brooks": 157})
        dataset_derivatives = dataset_orders + dataset_invoices + dataset_plots
        self.assertTrue(all(row["license"] == "CC-BY-4.0" for row in dataset_derivatives))
        self.assertTrue(all(row["source_dataset"] == "E-Commerce Dataset" for row in dataset_derivatives))
        self.assertTrue(all(row["transformation"] for row in dataset_derivatives))

        synthetic_invoices = [
            row
            for row in manifest
            if row.get("invoice_template") and row.get("source") == "generated"
        ]
        self.assertEqual(len(synthetic_invoices), 80)
        self.assertEqual(Counter(row["owner"] for row in synthetic_invoices), {"maya.patel": 40, "daniel.brooks": 40})
        self.assertEqual(Counter(row["invoice_template"] for row in synthetic_invoices), {
            template: 16 for template in generate.INVOICE_TEMPLATES
        })
        self.assertTrue(all(row["synthetic"] is True for row in synthetic_invoices))
        self.assertTrue(all(Path(row["path"]).parent.as_posix() == "Finance/Invoices" for row in synthetic_invoices))

    def test_real_open_documents_are_preserved_verbatim(self) -> None:
        catalog = json.loads((self.nextcloud_dir / "seed" / "real_documents.json").read_text(encoding="utf-8"))
        self.assertEqual(len(catalog["documents"]), 200)
        for entry in catalog["documents"]:
            generated = self.outputs[0] / "files" / entry["owner"] / entry["destination_path"]
            bundled = self.nextcloud_dir / "media" / entry["bundled_path"]
            self.assertEqual(generated.read_bytes(), bundled.read_bytes())
            self.assertGreater(generated.stat().st_size, 500)

    def test_orders_and_flat_varied_synthetic_invoices(self) -> None:
        catalog = json.loads((self.nextcloud_dir / "seed" / "financial_documents.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["version"], 2)
        self.assertNotIn("invoice_records", catalog)
        self.assertEqual(set(catalog["sources"]), {"ecommerce-orders"})
        self.assertEqual(len(catalog["order_records"]), 40)
        self.assertEqual(Counter(entry["owner"] for entry in catalog["order_records"]), {"maya.patel": 20, "daniel.brooks": 20})
        self.assertEqual(
            Counter((entry["owner"], entry["line_count"] > 1) for entry in catalog["order_records"]),
            {
                ("maya.patel", False): 10,
                ("maya.patel", True): 10,
                ("daniel.brooks", False): 10,
                ("daniel.brooks", True): 10,
            },
        )

        order_dataset = catalog["order_dataset"]
        bundled_workbook = self.nextcloud_dir / "media" / order_dataset["bundled_path"]
        self.assertEqual(bundled_workbook.stat().st_size, 5_151_356)
        for owner in generate.USERS:
            copied_workbook = self.outputs[0] / "files" / owner / order_dataset["destination_path"]
            self.assertEqual(copied_workbook.read_bytes(), bundled_workbook.read_bytes())

        for entry in catalog["order_records"]:
            workbook = self.outputs[0] / "files" / entry["owner"] / entry["document_destination_path"]
            with zipfile.ZipFile(workbook) as archive:
                worksheet = archive.read("xl/worksheets/sheet1.xml")
            self.assertIn(entry["order_id"].encode(), worksheet)
            self.assertIn(b"10.17632/ggbkd8ck3x.1", worksheet)
            self.assertEqual(worksheet.count(b"<row "), 6 + entry["line_count"])

        manifest = [
            json.loads(line)
            for line in (self.outputs[0] / "provenance" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        for owner in generate.USERS:
            root = self.outputs[0] / "files" / owner
            invoice_dir = root / "Finance" / "Invoices"
            self.assertEqual(len(list(invoice_dir.glob("*.pdf"))), 348)
            self.assertFalse(any(path.is_dir() for path in invoice_dir.iterdir()))
            self.assertFalse(any("MIDD" in path.as_posix() for path in root.rglob("*")))
            self.assertFalse((root / "Finance" / "Invoices" / "Open Dataset Source Records").exists())
            self.assertFalse((root / "Finance" / "Customer Invoices").exists())

            invoice_records = [
                row
                for row in manifest
                if row.get("owner") == owner
                and row.get("invoice_template")
                and row.get("source") == "generated"
            ]
            self.assertEqual(Counter(row["invoice_template"] for row in invoice_records), {
                template: 8 for template in generate.INVOICE_TEMPLATES
            })
            self.assertEqual(len({row["sha256"] for row in invoice_records}), 40)
            for row in invoice_records:
                payload = (root / row["path"]).read_bytes()
                self.assertTrue(payload.startswith(b"%PDF-1.4"))
                self.assertTrue(payload.endswith(b"%%EOF\n"))
                self.assertIn(b"SYNTHETIC RESEARCH FIXTURE", payload)
                self.assertIn(row["invoice_template"].encode(), payload)

            dataset_orders = {
                row["document_id"]: row
                for row in manifest
                if row.get("owner") == owner and row.get("source") == "derived-open-dataset-order"
            }
            dataset_invoices = [
                row
                for row in manifest
                if row.get("owner") == owner and row.get("source") == "derived-open-dataset-invoice"
            ]
            dataset_plots = [
                row
                for row in manifest
                if row.get("owner") == owner and row.get("source") == "derived-open-dataset-plot"
            ]
            self.assertEqual(len(dataset_orders), 160)
            self.assertEqual(len(dataset_invoices), 120)
            self.assertEqual(len(dataset_plots), 157)
            for row in dataset_invoices:
                related_order = dataset_orders[row["related_order_document_id"]]
                self.assertEqual(row["related_order_path"], related_order["path"])
                self.assertEqual(row["source_record_id"], related_order["source_record_id"])
                payload = (root / row["path"]).read_bytes()
                self.assertTrue(payload.startswith(b"%PDF-1.4"))
                self.assertTrue(payload.endswith(b"%%EOF\n"))
            for row in dataset_plots:
                self.assertTrue(set(row["related_order_document_ids"]).issubset(dataset_orders))
                plot = root / row["path"]
                plot_root = generate.ElementTree.fromstring(plot.read_bytes())
                self.assertTrue(plot_root.tag.endswith("svg"))

    def test_yearly_purchase_orders_are_populated_and_use_varied_templates(self) -> None:
        spec = json.loads((self.nextcloud_dir / "seed_spec.json").read_text(encoding="utf-8"))
        expected_by_year = {
            int(year): count for year, count in spec["purchase_orders_per_user_by_year"].items()
        }
        self.assertTrue(all(40 <= count <= 76 for count in expected_by_year.values()))
        self.assertEqual(sum(expected_by_year.values()), 292)

        manifest = [
            json.loads(line)
            for line in (self.outputs[0] / "provenance" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        for owner in generate.USERS:
            root = self.outputs[0] / "files" / owner / "Procurement" / "Purchase Orders"
            purchase_orders = [
                row for row in manifest
                if row.get("owner") == owner and row.get("purchase_order_template")
            ]
            self.assertEqual(len(purchase_orders), 292)
            self.assertEqual(Counter(row["purchase_order_year"] for row in purchase_orders), expected_by_year)
            self.assertEqual(
                {row["purchase_order_template"] for row in purchase_orders},
                set(generate.PURCHASE_ORDER_TEMPLATES),
            )
            self.assertEqual(len({row["path"] for row in purchase_orders}), 292)
            self.assertEqual(len({row["sha256"] for row in purchase_orders}), 292)
            self.assertTrue(all(row["synthetic"] is True for row in purchase_orders))

            for year, expected_count in expected_by_year.items():
                year_dir = root / str(year)
                self.assertEqual(len(list(year_dir.glob("*.pdf"))), expected_count)
                self.assertFalse(any(path.is_dir() for path in year_dir.iterdir()))

            for row in purchase_orders:
                self.assertEqual(Path(row["path"]).parent.name, str(row["purchase_order_year"]))
                payload = (self.outputs[0] / "files" / owner / row["path"]).read_bytes()
                self.assertTrue(payload.startswith(b"%PDF-1.4"))
                self.assertTrue(payload.endswith(b"%%EOF\n"))
                self.assertIn(b"PURCHASE", payload)
                self.assertIn(b"ORDER", payload)
                self.assertIn(b"SUPPLIER", payload)
                self.assertIn(b"ORDER TOTAL", payload)
                self.assertIn(b"SYNTHETIC RESEARCH FIXTURE", payload)
                self.assertIn(row["purchase_order_template"].encode(), payload)
                self.assertIn(row["document_id"].encode(), payload)

    def test_benchmark_names_and_history_are_preserved(self) -> None:
        documents = {path.name for path in (self.outputs[0] / "files" / "maya.patel" / "documents").iterdir()}
        self.assertEqual(documents, set(generate.GENERATED_DOCUMENTS))
        longest = self.outputs[0] / "files" / "maya.patel" / "safari" / "safariloop0S22m2.mp3"
        self.assertTrue(longest.is_file())

        leon = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.outputs[0] / "contacts" / "maya.patel").glob("*.vcf")
        )
        self.assertIn("FN:Leon Greene", leon)
        self.assertIn("NICKNAME:Leon Green", leon)
        self.assertIn("EMAIL;TYPE=INTERNET:leon@cedarstone.test", leon)
        self.assertIn("TEL;TYPE=CELL:9999999999", leon)

        with (self.outputs[0] / "talk" / "messages.tsv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))
        project_alpha = [(author, message) for room, author, _, _, _, message in rows if room == "Project Alpha"]
        self.assertEqual(project_alpha, generate.CANONICAL_MESSAGES)

        additional = [row for row in rows if row[0] in generate.ADDITIONAL_TALK_TOPICS]
        self.assertEqual(Counter(row[0] for row in additional), {
            room: 38 if index < 4 else 37
            for index, room in enumerate(generate.ADDITIONAL_TALK_TOPICS)
        })
        agent_messages = [row for row in additional if row[1] in generate.USERS]
        self.assertEqual(Counter(row[1] for row in agent_messages), {"maya.patel": 78, "daniel.brooks": 67})
        self.assertTrue(all("synthetic checklist" not in row[5] for row in rows))
        self.assertTrue(all(len(row[5]) >= 60 for row in additional))

        self.assertEqual(sum(row[4] != "-" for row in rows), 54)
        self.assertEqual(sum(row[3] != "-" for row in rows), 363)
        key_rooms: dict[str, str] = {}
        for room, _, message_key, reply_to, thread_title, _ in rows:
            if reply_to != "-":
                self.assertEqual(key_rooms[reply_to], room)
                self.assertEqual(thread_title, "-")
            key_rooms[message_key] = room

        with (self.outputs[0] / "talk" / "rooms.tsv").open(encoding="utf-8", newline="") as handle:
            room_rows = list(csv.reader(handle, delimiter="\t"))
        self.assertEqual(len(room_rows), 10)
        self.assertTrue(all(len(participants.split(",")) >= 3 for room, participants in room_rows if room != "Project Alpha"))
        self.assertEqual(dict(room_rows)["Project Alpha"], "maya.patel,daniel.brooks")

        with (self.outputs[0] / "talk" / "unread.tsv").open(encoding="utf-8", newline="") as handle:
            unread_rows = list(csv.reader(handle, delimiter="\t"))
        self.assertEqual(Counter(row[0] for row in unread_rows), {"maya.patel": 3, "daniel.brooks": 3})

        with (self.outputs[0] / "notifications" / "notifications.tsv").open(
            encoding="utf-8", newline=""
        ) as handle:
            notification_rows = list(csv.reader(handle, delimiter="\t"))
        self.assertEqual(
            Counter(row[0] for row in notification_rows),
            {"maya.patel": 12, "daniel.brooks": 12},
        )
        self.assertEqual(len({(row[0], row[1]) for row in notification_rows}), 24)
        self.assertTrue(all(len(row) == 4 and row[2] and row[3] for row in notification_rows))

    def test_business_workspace_is_realistic_and_populated(self) -> None:
        for owner in generate.USERS:
            root = self.outputs[0] / "files" / owner
            self.assertFalse((root / "Synthetic Archive").exists())
            self.assertFalse((root / "Customer Support").exists())
            self.assertNotIn("Customer Support", generate.BUSINESS_FOLDERS)
            self.assertEqual(
                {path.name for path in root.iterdir() if path.is_dir()} & set(generate.BUSINESS_FOLDERS),
                set(generate.BUSINESS_FOLDERS),
            )
            business_files = [
                path
                for folder in generate.BUSINESS_FOLDERS
                for path in (root / folder).rglob("*")
                if path.is_file()
            ]
            self.assertGreater(len(business_files), 4800)
            business_directories = {
                path.parent
                for path in business_files
            }
            generated_business_files = [
                path
                for path in business_files
                if not any(part.startswith("Open Dataset") for part in path.relative_to(root).parts)
            ]
            self.assertLess(len(business_directories), 350)
            self.assertFalse(any(path.name.startswith("record_") for path in business_files))
            joined_paths = "\n".join(path.relative_to(root).as_posix() for path in business_files)
            for keyword in ("Invoice", "Order", "Meeting", "Report", "Presentation", "Project"):
                self.assertIn(keyword, joined_paths)
            self.assertGreaterEqual(
                sum(generate.filename_slug(customer) in joined_paths for customer in generate.CUSTOMERS),
                8,
            )

            for suffix in (".txt", ".md"):
                sample = next(path for path in generated_business_files if path.suffix == suffix)
                content = sample.read_text(encoding="utf-8")
                self.assertGreater(len(content), 900)
                self.assertIn("Document ID", content)
                self.assertIn("Status", content)

            csv_sample = next(path for path in generated_business_files if path.suffix == ".csv")
            with csv_sample.open(encoding="utf-8", newline="") as handle:
                csv_rows = list(csv.reader(handle))
            self.assertGreaterEqual(len(csv_rows), 9)
            self.assertGreaterEqual(len(csv_rows[0]), 6)

            json_sample = next(path for path in (root / "Legal" / "Contracts").glob("*.json"))
            json_payload = json.loads(json_sample.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(json_payload["records"]), 8)
            self.assertGreaterEqual(len(json_payload["details"]), 5)

            docx_sample = next(path for path in generated_business_files if path.suffix == ".docx")
            with zipfile.ZipFile(docx_sample) as archive:
                document_xml = archive.read("word/document.xml")
            self.assertGreater(document_xml.count(b"<w:p>"), 20)
            self.assertGreater(len(document_xml), 2500)

            xlsx_sample = next(path for path in generated_business_files if path.suffix == ".xlsx")
            with zipfile.ZipFile(xlsx_sample) as archive:
                worksheet_xml = archive.read("xl/worksheets/sheet1.xml")
            self.assertGreaterEqual(worksheet_xml.count(b"<row "), 14)

            pptx_sample = next(path for path in generated_business_files if path.suffix == ".pptx")
            with zipfile.ZipFile(pptx_sample) as archive:
                slides = [name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
                slide_text = b"".join(archive.read(name) for name in slides)
            self.assertEqual(len(slides), 5)
            self.assertGreater(len(slide_text), 5000)

            for path in business_files:
                if path.suffix.lower() not in {".txt", ".md", ".csv", ".json"}:
                    continue
                content = path.read_text(encoding="utf-8").lower()
                self.assertFalse({term for term in generate.RESERVED_BULK_TERMS if term in content})

    def test_managed_folder_counts_are_varied_and_total_ten_thousand_files(self) -> None:
        spec = json.loads((self.nextcloud_dir / "seed_spec.json").read_text(encoding="utf-8"))
        targets = spec["managed_folder_targets"]
        self.assertEqual(spec["targets"]["files_per_user"], 5000)
        self.assertEqual(sum(self.results[0]["files"].values()), 10_000)
        self.assertEqual(set(targets), set(generate.USERS))
        for owner in generate.USERS:
            owner_targets = targets[owner]
            self.assertEqual(len(owner_targets), 20)
            self.assertTrue(all(100 <= count <= 400 for count in owner_targets.values()))
            self.assertGreaterEqual(len(set(owner_targets.values())), 15)
            self.assertTrue(all(count % 100 for count in owner_targets.values()))
            root = self.outputs[0] / "files" / owner
            for folder, expected_count in owner_targets.items():
                actual_count = sum(path.is_file() for path in (root / folder).rglob("*"))
                self.assertEqual(actual_count, expected_count, f"{owner}/{folder}")

    def test_contacts_calendars_talk_and_files_share_valid_links(self) -> None:
        manifest = [
            json.loads(line)
            for line in (self.outputs[0] / "provenance" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        files = {
            (row["owner"], row["path"]): row
            for row in manifest
            if row["entity_type"] == "file"
        }
        support_display_names = {"Sarah Chen", "Priya Nair", "Marcus Johnson", "Leon Greene"}
        for owner in generate.USERS:
            contact_rows = [
                row
                for row in manifest
                if row["entity_type"] == "contact" and row["owner"] == owner
            ]
            contacts = {
                row["uid"]: row
                for row in contact_rows
            }
            self.assertEqual(len(contact_rows), 100)
            self.assertEqual(len(contacts), 100)
            self.assertEqual(len({row["email"] for row in contact_rows}), 100)
            self.assertEqual(len({row["phone"] for row in contact_rows}), 100)
            self.assertTrue(
                all(row["email"].endswith(f"@{generate.COMPANY_DOMAIN}") for row in contact_rows)
            )
            for row in contact_rows:
                payload = (self.outputs[0] / "contacts" / owner / f"{row['uid']}.vcf").read_text(
                    encoding="utf-8"
                )
                self.assertIn(f"ORG:{generate.COMPANY_NAME}", payload)
                self.assertNotIn("example.com", payload)
                self.assertNotIn("example.test", payload)
            self.assertTrue(support_display_names.issubset({row["display_name"] for row in contacts.values()}))
            events = [
                row
                for row in manifest
                if row["entity_type"] == "calendar_event" and row["owner"] == owner
            ]
            self.assertEqual(len(events), 50)
            self.assertEqual({row["related_customer"] for row in events}, set(generate.CUSTOMERS))
            self.assertEqual({row["related_project"] for row in events}, set(generate.PROJECTS))
            self.assertEqual({row["related_vendor"] for row in events}, set(generate.VENDORS))
            self.assertEqual({row["related_team"] for row in events}, set(generate.TEAMS))
            for event in events:
                linked_file = files[(event["related_file_owner"], event["related_file"])]
                self.assertEqual(event["related_file_sha256"], linked_file["sha256"])
                self.assertTrue(set(event["attendee_contact_uids"]).issubset(contacts))
                calendar_payload = (
                    self.outputs[0] / "calendars" / owner / f"{event['uid']}.ics"
                ).read_bytes()
                self.assertEqual(calendar_payload.count(b"ATTENDEE;CN="), 3)
                self.assertIn(event["related_file"].encode(), calendar_payload)

        talk_records = [row for row in manifest if row["entity_type"] == "talk_message"]
        self.assertEqual(len(talk_records), 425)
        for message in talk_records:
            self.assertEqual(set(message["related_files"]), set(generate.USERS))
            for owner, linked in message["related_files"].items():
                file_record = files[(owner, linked["path"])]
                self.assertEqual(linked["sha256"], file_record["sha256"])

        notification_records = [
            row for row in manifest if row["entity_type"] == "notification"
        ]
        self.assertEqual(
            Counter(row["owner"] for row in notification_records),
            {"maya.patel": 12, "daniel.brooks": 12},
        )
        known_rooms = {
            *generate.BASELINE_TALK_TOPICS,
            *generate.ADDITIONAL_TALK_TOPICS,
            "Project Alpha",
        }
        for notification in notification_records:
            linked_file = files[(notification["owner"], notification["related_file"])]
            self.assertEqual(notification["related_file_sha256"], linked_file["sha256"])
            self.assertIn(notification["actor"], support_display_names)
            self.assertIn(notification["related_talk_room"], known_rooms)
            self.assertIn(notification["related_file"], notification["message"])

    def test_root_contains_a_varied_current_working_set(self) -> None:
        spec = json.loads((self.nextcloud_dir / "seed_spec.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["root_work_files_per_user"], 6)
        manifest = [
            json.loads(line)
            for line in (self.outputs[0] / "provenance" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        expected_types = {
            "Purchase Order Reference Copy",
            "Project Status Report",
            "Meeting Report",
            "Budget Forecast",
            "Sales Order Register",
            "Operations Review",
        }
        for owner in generate.USERS:
            root = self.outputs[0] / "files" / owner
            root_files = sorted(path for path in root.iterdir() if path.is_file())
            self.assertEqual(len(root_files), 6)
            self.assertEqual(
                Counter(path.suffix for path in root_files),
                {".pdf": 1, ".md": 1, ".docx": 1, ".xlsx": 1, ".csv": 1, ".pptx": 1},
            )
            root_records = [
                row for row in manifest if row.get("owner") == owner and row.get("root_work_file") is True
            ]
            self.assertEqual(len(root_records), 6)
            self.assertEqual({row["document_type"] for row in root_records}, expected_types)
            self.assertTrue(all("/" not in row["path"] for row in root_records))
            self.assertEqual({row["path"] for row in root_records}, {path.name for path in root_files})

            purchase_order_copy = next(
                row for row in root_records if row["document_type"] == "Purchase Order Reference Copy"
            )
            original = next(
                row
                for row in manifest
                if row.get("owner") == owner
                and row.get("document_type") == "Purchase Order"
                and row.get("document_id") == purchase_order_copy["related_purchase_order"]
            )
            self.assertEqual(purchase_order_copy["original_path"], original["path"])
            self.assertEqual(purchase_order_copy["sha256"], original["sha256"])
            self.assertEqual(
                (root / purchase_order_copy["path"]).read_bytes(),
                (root / original["path"]).read_bytes(),
            )

    def test_procurement_documents_are_linked_and_consistent(self) -> None:
        json_document_types = {
            profile["label"] for profile in generate.BUSINESS_DOCUMENT_PROFILES["json"]
        }
        self.assertNotIn("Purchase Requisition", json_document_types)
        self.assertNotIn("Vendor Assessment", json_document_types)
        self.assertNotIn("Vendor Master Record", json_document_types)
        self.assertFalse(
            any(
                profile["area"] == "Procurement"
                for profiles in generate.BUSINESS_DOCUMENT_PROFILES.values()
                for profile in profiles
            )
        )

        manifest = [
            json.loads(line)
            for line in (self.outputs[0] / "provenance" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        for owner in generate.USERS:
            owner_records = [
                row
                for row in manifest
                if row.get("owner") == owner and row.get("path", "").startswith("Procurement/")
            ]
            records_by_type = {
                document_type: [row for row in owner_records if row.get("document_type") == document_type]
                for document_type in (
                    "Purchase Order",
                    "Purchase Requisition",
                    "Vendor Assessment",
                    "Vendor Review Note",
                    "Vendor Master Record",
                )
            }
            self.assertEqual(
                {document_type: len(rows) for document_type, rows in records_by_type.items()},
                {
                    "Purchase Order": 292,
                    "Purchase Requisition": 292,
                    "Vendor Assessment": 40,
                    "Vendor Review Note": 40,
                    "Vendor Master Record": 8,
                },
            )
            self.assertEqual(len(owner_records), 672)

            purchase_orders = {row["document_id"]: row for row in records_by_type["Purchase Order"]}
            requisition_rows = records_by_type["Purchase Requisition"]
            requisitions = {row["related_purchase_order"]: row for row in requisition_rows}
            self.assertEqual(len(requisitions), len(requisition_rows))
            self.assertEqual(set(requisitions), set(purchase_orders))
            self.assertEqual(
                Counter(Path(row["path"]).suffix for row in requisition_rows),
                {".pdf": 146, ".docx": 146},
            )

            consistent_fields = (
                "subject",
                "procurement_record_key",
                "vendor_id",
                "order_total",
                "cost_center",
                "project",
                "requested_by",
                "line_item_skus",
            )
            for purchase_order_id, purchase_order in purchase_orders.items():
                requisition = requisitions[purchase_order_id]
                self.assertEqual(purchase_order["related_requisition"], requisition["document_id"])
                for field in consistent_fields:
                    self.assertEqual(purchase_order[field], requisition[field])

                path = self.outputs[0] / "files" / owner / requisition["path"]
                if path.suffix == ".pdf":
                    payload = path.read_bytes()
                    self.assertTrue(payload.startswith(b"%PDF-1.4"))
                    self.assertTrue(payload.endswith(b"%%EOF\n"))
                else:
                    with zipfile.ZipFile(path) as archive:
                        self.assertIsNone(archive.testzip())
                        payload = archive.read("word/document.xml")
                    self.assertGreater(payload.count(b"<w:p>"), 20)
                self.assertIn(purchase_order_id.encode(), payload)
                self.assertIn(requisition["document_id"].encode(), payload)

            assessments = records_by_type["Vendor Assessment"]
            notes = records_by_type["Vendor Review Note"]
            masters = records_by_type["Vendor Master Record"]
            self.assertEqual(Counter(Path(row["path"]).suffix for row in assessments), {".pdf": 20, ".docx": 20})
            self.assertEqual({Path(row["path"]).suffix for row in notes}, {".txt"})
            self.assertEqual({Path(row["path"]).suffix for row in masters}, {".docx"})
            self.assertEqual(Counter(row["assessment_year"] for row in assessments), {year: 8 for year in range(2022, 2027)})
            self.assertEqual(Counter(row["review_year"] for row in notes), {year: 8 for year in range(2022, 2027)})

            assessment_by_vendor_year = {
                (row["vendor_id"], row["assessment_year"]): row for row in assessments
            }
            note_by_vendor_year = {(row["vendor_id"], row["review_year"]): row for row in notes}
            self.assertEqual(len(assessment_by_vendor_year), 40)
            self.assertEqual(set(note_by_vendor_year), set(assessment_by_vendor_year))
            for vendor_year, assessment in assessment_by_vendor_year.items():
                vendor_id, year = vendor_year
                linked_orders = [
                    row
                    for row in purchase_orders.values()
                    if row["vendor_id"] == vendor_id and row["purchase_order_year"] == year
                ]
                linked_ids = {row["document_id"] for row in linked_orders}
                linked_total = round(sum(row["order_total"] for row in linked_orders), 2)
                self.assertEqual(set(assessment["related_purchase_orders"]), linked_ids)
                self.assertEqual(assessment["purchase_order_count"], len(linked_orders))
                self.assertEqual(assessment["purchase_order_total"], linked_total)

                note = note_by_vendor_year[vendor_year]
                self.assertEqual(note["related_assessment"], assessment["document_id"])
                self.assertEqual(note["purchase_order_count"], len(linked_orders))
                self.assertEqual(note["purchase_order_total"], linked_total)

            master_by_vendor = {row["vendor_id"]: row for row in masters}
            self.assertEqual(set(master_by_vendor), {details["vendor_id"] for details in generate.VENDOR_DETAILS.values()})
            for vendor_id, master in master_by_vendor.items():
                linked_orders = [row for row in purchase_orders.values() if row["vendor_id"] == vendor_id]
                linked_ids = {row["document_id"] for row in linked_orders}
                linked_total = round(sum(row["order_total"] for row in linked_orders), 2)
                self.assertEqual(set(master["related_purchase_orders"]), linked_ids)
                self.assertEqual(master["purchase_order_count"], len(linked_orders))
                self.assertEqual(master["purchase_order_total"], linked_total)

                master_path = self.outputs[0] / "files" / owner / master["path"]
                with zipfile.ZipFile(master_path) as archive:
                    self.assertIsNone(archive.testzip())
                    master_payload = archive.read("word/document.xml")
                self.assertGreater(master_payload.count(b"<w:p>"), 50)
                self.assertIn(f"Vendor Master Record - {vendor_id}".encode(), master_payload)
                self.assertIn(master["subject"].encode(), master_payload)
                self.assertIn(f"Purchase orders: {len(linked_orders)}".encode(), master_payload)
                self.assertIn(f"Lifetime ordered value: ${linked_total:,.2f}".encode(), master_payload)
                for purchase_order_id in linked_ids:
                    self.assertIn(purchase_order_id.encode(), master_payload)
                for year, annual in master["annual_summary"].items():
                    annual_orders = [
                        row for row in linked_orders if row["purchase_order_year"] == int(year)
                    ]
                    self.assertEqual(annual["purchase_order_count"], len(annual_orders))
                    self.assertEqual(
                        annual["purchase_order_total"],
                        round(sum(row["order_total"] for row in annual_orders), 2),
                    )
                    self.assertIn(annual["assessment_id"].encode(), master_payload)
                    self.assertIn(annual["vendor_note_id"].encode(), master_payload)

    def test_monthly_timesheets_cover_every_worker_category_through_june_2026(self) -> None:
        spec = json.loads((self.nextcloud_dir / "seed_spec.json").read_text(encoding="utf-8"))
        expected_by_year = {
            int(year): count for year, count in spec["timesheets_per_user_by_year"].items()
        }
        self.assertEqual(expected_by_year, {2022: 12, 2023: 12, 2024: 12, 2025: 12, 2026: 6})
        expected_categories = tuple(spec["timesheet_worker_categories"])
        self.assertEqual(expected_categories, tuple(generate.TIMESHEET_WORKERS))
        self.assertEqual(len(expected_categories), 6)
        self.assertFalse(
            any(
                profile["label"] == "Team Timesheet"
                for profiles in generate.BUSINESS_DOCUMENT_PROFILES.values()
                for profile in profiles
            )
        )

        manifest = [
            json.loads(line)
            for line in (self.outputs[0] / "provenance" / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        for owner in generate.USERS:
            timesheet_root = self.outputs[0] / "files" / owner / "People" / "Timesheets"
            documents = sorted(path for path in timesheet_root.rglob("*") if path.is_file())
            self.assertEqual(len(documents), 54)
            self.assertEqual({path.suffix.lower() for path in documents}, {".xlsx"})
            self.assertEqual(
                Counter(int(path.parent.name) for path in documents),
                expected_by_year,
            )

            timesheet_records = [
                row
                for row in manifest
                if row.get("owner") == owner and row.get("document_type") == "Monthly Timesheet"
            ]
            self.assertEqual(len(timesheet_records), 54)
            self.assertEqual(Counter(row["timesheet_year"] for row in timesheet_records), expected_by_year)
            self.assertEqual(len({row["sha256"] for row in timesheet_records}), 54)
            self.assertTrue(all(tuple(row["worker_categories"]) == expected_categories for row in timesheet_records))
            self.assertEqual(
                sorted(row["timesheet_month"] for row in timesheet_records if row["timesheet_year"] == 2026),
                [1, 2, 3, 4, 5, 6],
            )

            for row in timesheet_records:
                workbook = self.outputs[0] / "files" / owner / row["path"]
                with zipfile.ZipFile(workbook) as archive:
                    self.assertIsNone(archive.testzip())
                    workbook_xml = archive.read("xl/workbook.xml")
                    worksheet_names = sorted(
                        name
                        for name in archive.namelist()
                        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
                    )
                    self.assertEqual(len(worksheet_names), len(expected_categories))
                    for category in expected_categories:
                        self.assertIn(f'name="{category}"'.encode(), workbook_xml)
                    for category, worksheet_name in zip(expected_categories, worksheet_names):
                        worksheet_xml = archive.read(worksheet_name)
                        self.assertEqual(worksheet_xml.count(b"<row "), 11)
                        self.assertIn(category.encode(), worksheet_xml)
                        self.assertIn(row["subject"].encode(), worksheet_xml)

    def test_calendar_has_multiple_daily_meetings_and_recurrence(self) -> None:
        for owner in generate.USERS:
            starts: Counter[str] = Counter()
            recurrence_rules: list[str] = []
            local_start_times: list[str] = []
            one_time_meetings = 0
            for path in (self.outputs[0] / "calendars" / owner).glob("*.ics"):
                payload = path.read_text(encoding="utf-8")
                self.assertNotIn("METHOD:", payload)
                event = payload.split("BEGIN:VEVENT", 1)[1].split("END:VEVENT", 1)[0]
                lines = event.splitlines()
                start_line = next(line for line in lines if line.startswith("DTSTART"))
                self.assertTrue(start_line.startswith("DTSTART;TZID=America/Toronto:"))
                local_value = start_line.rsplit(":", 1)[1]
                starts[local_value[:8]] += 1
                local_start_times.append(local_value[9:15])
                event_rules = [line.removeprefix("RRULE:") for line in lines if line.startswith("RRULE:")]
                recurrence_rules.extend(event_rules)
                if not event_rules:
                    one_time_meetings += 1
            self.assertGreaterEqual(sum(count >= 4 for count in starts.values()), 12)
            self.assertEqual(min(local_start_times), "090000")
            self.assertTrue(all(start_time >= "090000" for start_time in local_start_times))
            self.assertEqual(len(recurrence_rules), 8)
            self.assertEqual(one_time_meetings, 42)
            self.assertTrue(any(rule.startswith("FREQ=WEEKLY") for rule in recurrence_rules))
            self.assertTrue(any(rule.startswith("FREQ=DAILY") for rule in recurrence_rules))
            self.assertTrue(any(rule.startswith("FREQ=MONTHLY") for rule in recurrence_rules))


if __name__ == "__main__":
    unittest.main()
