"""Optional real form regression: X_LITE_BROWSER_TESTS=1 python -m unittest discover -s websites/x-lite/tests."""

import os
import threading
import unittest

from werkzeug.serving import make_server

from test_messages import MessageFixture, x_lite


@unittest.skipUnless(os.environ.get("X_LITE_BROWSER_TESTS") == "1", "set X_LITE_BROWSER_TESTS=1 and install Playwright Chromium")
class MessageBrowserTests(MessageFixture):
    def setUp(self):
        super().setUp()
        from playwright.sync_api import sync_playwright

        self.server = make_server("127.0.0.1", 0, x_lite.app)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.origin = f"http://127.0.0.1:{self.server.server_port}"
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch()
        self.addCleanup(self.browser.close)
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 720})
        cookie = x_lite.app.session_interface.get_signing_serializer(x_lite.app).dumps({"user_id": "self"})
        self.context.add_cookies([{"name": "session", "value": cookie, "url": self.origin}])
        self.page = self.context.new_page()
        self.page.goto(self.origin + "/messages")

    def click_and_navigate(self, locator):
        with self.page.expect_navigation():
            locator.click()

    def test_member_selection_survives_real_form_navigation_search_and_removal(self):
        page = self.page
        page.get_by_label("Group name", exact=True).fill('Draft & "group"')
        page.get_by_label("Initial message", exact=True).fill("Hello <team>")
        page.get_by_test_id("group-member-checkbox-u000").check()
        self.click_and_navigate(page.get_by_role("button", name="Next members", exact=True))
        self.assertTrue(page.get_by_test_id("group-member-checkbox-u000").is_checked())
        page.get_by_test_id("group-member-checkbox-u020").check()
        self.click_and_navigate(page.get_by_role("button", name="Previous members", exact=True))
        self.assertTrue(page.get_by_test_id("group-member-checkbox-u020").is_checked())
        page.get_by_label("Search group members").fill("person120")
        self.click_and_navigate(page.get_by_role("button", name="Find members", exact=True))
        page.get_by_test_id("group-member-checkbox-u120").check()
        page.get_by_test_id("group-member-checkbox-u000").uncheck()
        self.assertEqual(page.get_by_label("Group name", exact=True).input_value(), 'Draft & "group"')
        self.assertEqual(page.get_by_label("Initial message", exact=True).input_value(), "Hello <team>")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM group_chats").fetchone()[0], 25)
        self.click_and_navigate(page.get_by_role("button", name="Create group chat", exact=True))
        chat_id = page.url.rsplit("/", 1)[1]
        self.assertEqual({row[0] for row in self.db.execute(
            "SELECT user_id FROM group_chat_members WHERE chat_id = ?", (chat_id,))},
            {"self", "u020", "u120"})
        self.assertIn("Hello <team>", page.get_by_test_id("group-message-thread").inner_text())

    def test_people_navigation_search_and_sending_a_new_dm(self):
        page = self.page
        self.click_and_navigate(page.get_by_role("navigation", name="People pages").get_by_role("link", name="Next", exact=True))
        self.assertTrue(page.get_by_test_id("conversation-item-u045").is_visible())
        page.get_by_label("Search people and messages").fill("person120")
        self.click_and_navigate(page.get_by_test_id("messages-search-submit"))
        self.click_and_navigate(page.get_by_test_id("conversation-item-u120"))
        page.get_by_test_id("message-input").fill("Reached beyond the first page")
        self.click_and_navigate(page.get_by_role("button", name="Send message", exact=True))
        self.assertIn("Reached beyond the first page", page.get_by_test_id("message-thread").inner_text())
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM messages WHERE sender_id = 'self' AND receiver_id = 'u120' AND content = ?",
            ("Reached beyond the first page",)).fetchone()[0], 1)

    def test_old_messages_remain_accessible_through_history_links_and_search(self):
        self.db.executemany(
            "INSERT INTO messages (id, sender_id, receiver_id, content, created_at) VALUES (?, 'u120', 'self', ?, '2026-02-01')",
            [(f"old{i:03}", f"History message {i:03}") for i in range(120)],
        )
        self.db.commit()
        page = self.page
        page.goto(self.origin + "/messages/u120")
        self.assertEqual(page.get_by_test_id("message-thread").locator(":scope > div").count(), 50)
        self.click_and_navigate(page.get_by_role("link", name="Older messages", exact=True))
        self.click_and_navigate(page.get_by_role("link", name="Older messages", exact=True))
        self.assertTrue(page.get_by_test_id("message-old000").is_visible())
        self.click_and_navigate(page.get_by_role("link", name="Newer messages", exact=True))
        page.get_by_label("Search this conversation").fill("History message 000")
        self.click_and_navigate(page.get_by_role("button", name="Search messages", exact=True))
        self.assertEqual(page.get_by_test_id("message-thread").locator(":scope > div").count(), 1)
        self.assertTrue(page.get_by_test_id("message-old000").is_visible())


if __name__ == "__main__":
    unittest.main()
