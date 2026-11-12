"""Relevant-people controls must refer to real, followable accounts."""
from test_messages import MessageFixture, Page


class SidebarPeopleTests(MessageFixture):
    def test_suggestions_are_real_bounded_accounts_and_follow_persists(self):
        page = Page(self.client.get('/messages'))
        controls = page.matching('aria-label', 'Follow @')
        self.assertEqual(len(controls), 3)
        links = page.matching('href', '/user/person')
        self.assertTrue(links)
        for link in links:
            self.assertEqual(self.client.get(link['href']).status_code, 200)
        forms = page.matching('action', '/follow/')
        target = forms[0]['action'].rsplit('/', 1)[1]
        self.assertEqual(forms[0]['method'], 'POST')
        response = self.client.post(forms[0]['action'], headers={'Referer': '/messages'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/messages')
        self.assertIsNotNone(self.db.execute(
            'SELECT 1 FROM follows WHERE follower_id=? AND followed_id=?', ('self', target)
        ).fetchone())
        self.assertFalse(any(form['action'] == forms[0]['action'] for form in Page(
            self.client.get('/messages')).matching('action', '/follow/')))
        self.assertNotIn(b'@techcrunch', self.client.get('/messages').data)

    def test_no_self_or_already_followed_accounts_are_suggested(self):
        self.db.execute("INSERT INTO follows (follower_id, followed_id) VALUES ('self', 'u000')")
        self.db.commit()
        forms = Page(self.client.get('/messages')).matching('action', '/follow/')
        self.assertNotIn('/follow/self', [form['action'] for form in forms])
        self.assertNotIn('/follow/u000', [form['action'] for form in forms])

    def test_guest_and_exhausted_suggestions_have_no_widget(self):
        self.db.execute("INSERT INTO follows (follower_id, followed_id) SELECT 'self', id FROM users WHERE id != 'self'")
        self.db.commit()
        self.assertNotIn(b'data-testid="relevant-people"', self.client.get('/messages').data)
        with self.client.session_transaction() as session:
            session.clear()
        self.assertNotIn(b'data-testid="relevant-people"', self.client.get('/login').data)
