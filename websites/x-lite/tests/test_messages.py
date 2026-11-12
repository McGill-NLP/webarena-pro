"""Message paging regressions. Run: python -m unittest discover -s websites/x-lite/tests."""

import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

APP_DIR = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("x_lite_messages_app", APP_DIR / "app.py")
x_lite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = x_lite
spec.loader.exec_module(x_lite)


class Page(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.elements = []
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def matching(self, attr, prefix):
        return [attrs for _, attrs in self.elements if attrs.get(attr, "").startswith(prefix)]

    def input_value(self, name):
        return next(attrs.get("value", "") for tag, attrs in self.elements
                    if tag == "input" and attrs.get("name") == name)


class MessageFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        x_lite.DB_PATH = str(Path(self.temp.name) / "messages.db")
        x_lite.app.config.update(TESTING=True)
        self.db = sqlite3.connect(x_lite.DB_PATH)
        self.addCleanup(self.db.close)
        self.db.executescript((APP_DIR / "schema.sql").read_text())
        self.db.executemany(
            "INSERT INTO users (id, username, display_name) VALUES (?, ?, ?)",
            [("self", "viewer", "Viewer")] +
            [(f"u{i:03}", f"person{i:03}", f"Person {i:03}") for i in range(121)],
        )
        self.db.executemany(
            "INSERT INTO messages (id, sender_id, receiver_id, content, created_at) VALUES (?, ?, 'self', ?, '2026-01-01')",
            [(f"conversation{i:03}", f"u{i:03}", f"Inbox message {i:03}") for i in range(25)],
        )
        self.db.executemany(
            "INSERT INTO group_chats (id, name, created_by, created_at) VALUES (?, ?, 'self', '2026-01-01')",
            [(f"g{i:03}", f"Group {i:03}") for i in range(25)],
        )
        self.db.executemany("INSERT INTO group_chat_members (chat_id, user_id) VALUES (?, 'self')",
                            [(f"g{i:03}",) for i in range(25)])
        self.db.commit()
        self.client = x_lite.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = "self"


class MessagePagingTests(MessageFixture):
    def test_inbox_and_directory_are_bounded_and_all_pages_are_reachable(self):
        page = Page(self.client.get("/messages"))
        self.assertEqual(len(page.matching("data-testid", "group-member-option-")), 20)
        self.assertEqual(len(page.matching("data-testid", "group-conversation-item-")), 20)
        # 20 existing conversations and 20 new recipients.
        self.assertEqual(len(page.matching("data-testid", "conversation-item-")), 40)
        self.assertLess(len(page.elements), 600)
        for key, prefix, expected in [
            ("conversation_page", "conversation-item-u024", 1),
            ("group_page", "group-conversation-item-g024", 1),
            ("user_page", "conversation-item-u045", 1),
        ]:
            next_page = Page(self.client.get(f"/messages?{key}=2"))
            self.assertEqual(len(next_page.matching("data-testid", prefix)), expected)
        # Alias has the same bound; malformed/negative/oversized offsets never error.
        for url in ["/chat", "/messages?user_page=bad", "/messages?user_page=-3",
                    "/messages?endpoint=other&user_id=other",
                    "/messages?user_page=" + "9" * 80]:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_search_finds_people_and_message_content_beyond_first_page(self):
        for query, test_id in [
            ("person120", "conversation-item-u120"),
            ("@person120", "conversation-item-u120"),
            ("Inbox message 024", "conversation-item-u024"),
            ("Group 024", "group-conversation-item-g024"),
        ]:
            page = Page(self.client.get("/messages", query_string={"q": query}))
            self.assertEqual(len(page.matching("data-testid", test_id)), 1)
        page = Page(self.client.get("/messages?q=person"))
        self.assertTrue(any("q=person" in el["href"] and "user_page=2" in el["href"]
                            for el in page.matching("href", "/messages?")))
        # SQL wildcard characters are literal search text.
        self.assertEqual(len(Page(self.client.get("/messages?q=%25")).matching(
            "data-testid", "conversation-item-")), 0)

    def test_group_picker_preserves_selection_and_draft_without_creating_group(self):
        draft = {"name": 'Research & "friends"', "content": "Initial <message>",
                 "member_ids": ["u000"], "member_page": "1", "picker_action": "next"}
        response = self.client.post("/messages/group", data=draft)
        self.assertEqual(response.status_code, 200)
        page = Page(response)
        self.assertEqual(page.input_value("name"), draft["name"])
        self.assertEqual(page.input_value("content"), draft["content"])
        self.assertEqual(page.input_value("member_page"), "2")
        self.assertIn("checked", page.matching("data-testid", "group-member-checkbox-u000")[0])
        self.assertEqual(len(page.matching("data-testid", "group-member-option-")), 21)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM group_chats").fetchone()[0], 25)
        self.assertTrue(all(urlparse(el["href"]).path == "/messages"
                            for el in page.matching("href", "/messages?")))
        draft.update(member_q="@person120", picker_action="search", member_page="2")
        page = Page(self.client.post("/messages/group", data=draft))
        self.assertEqual(page.input_value("member_page"), "1")
        self.assertIn("checked", page.matching("data-testid", "group-member-checkbox-u000")[0])
        self.assertEqual(len(page.matching("data-testid", "group-member-checkbox-u120")), 1)
        draft.update(member_ids=["u000", "u120", "self", "nonexistent"], picker_action="create")
        response = self.client.post("/messages/group", data=draft)
        self.assertEqual(response.status_code, 302)
        chat_id = response.headers["Location"].rsplit("/", 1)[1]
        members = {row[0] for row in self.db.execute(
            "SELECT user_id FROM group_chat_members WHERE chat_id = ?", (chat_id,))}
        self.assertEqual(members, {"self", "u000", "u120"})
        self.assertEqual(self.db.execute("SELECT content FROM group_messages WHERE chat_id = ?",
                                         (chat_id,)).fetchone()[0], draft["content"])

    def test_histories_show_latest_window_and_search_and_page_to_older_messages(self):
        for i in range(120):
            self.db.execute(
                "INSERT INTO messages (id, sender_id, receiver_id, content, created_at) VALUES (?, 'u120', 'self', ?, '2026-02-01')",
                (f"dm{i:03}", f"Direct history {i:03}"))
            self.db.execute(
                "INSERT INTO group_messages (id, chat_id, sender_id, content, created_at) VALUES (?, 'g000', 'self', ?, '2026-02-01')",
                (f"gm{i:03}", f"Group history {i:03}"))
        self.db.commit()
        for url, prefix, search in [("/messages/u120", "dm", "Direct history"),
                                    ("/messages/group/g000", "gm", "Group history")]:
            first = Page(self.client.get(url))
            ids = [el["data-testid"] for el in first.matching("data-testid", "message-" )
                   if el["data-testid"].startswith(f"message-{prefix}")]
            self.assertEqual(ids, [f"message-{prefix}{i:03}" for i in range(70, 120)])
            oldest = Page(self.client.get(url + "?page=3"))
            self.assertEqual(len(oldest.matching("data-testid", f"message-{prefix}")), 20)
            self.assertEqual(len(oldest.matching("data-testid", f"message-{prefix}000")), 1)
            filtered = Page(self.client.get(url, query_string={"q": search + " 000"}))
            self.assertEqual(len(filtered.matching("data-testid", f"message-{prefix}")), 1)
            response = self.client.post(url + "?page=3&q=old", data={"content": "Fresh reply"}, follow_redirects=True)
            self.assertIn("Fresh reply", response.get_data(as_text=True))
        # Preserve the original read-on-open semantics for the conversation.
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM messages WHERE sender_id = 'u120' AND read_at IS NULL").fetchone()[0], 0)

    def test_group_history_access_stays_private(self):
        self.db.execute("DELETE FROM group_chat_members WHERE chat_id = 'g024'")
        self.db.commit()
        self.assertEqual(self.client.get("/messages/group/g024?q=secret&page=2").status_code, 404)
        self.assertEqual(self.client.post("/messages/group/g024", data={"content": "No access"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
