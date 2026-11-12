"""Local recipients pass through Sieve; external recipients remain no-ops."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('fake_smtp', Path(__file__).parents[1] / 'fake_smtp.py')
smtp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smtp)


class DeliveryTests(unittest.TestCase):
    def test_local_recipient_uses_lda(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'techcorp.local/alice/Maildir').mkdir(parents=True)
            with patch.object(smtp, 'MAILDIR_BASE', root), patch.object(smtp.subprocess, 'run') as run:
                self.assertTrue(smtp.deliver_to_maildir('alice@techcorp.local', b'Subject: test\r\n\r\nbody', 'bob@techcorp.local'))
                self.assertEqual(run.call_args.args[0], ['/usr/lib/dovecot/dovecot-lda', '-d', 'alice@techcorp.local', '-f', 'bob@techcorp.local'])
                self.assertEqual(run.call_args.kwargs['input'], b'Subject: test\r\n\r\nbody')
                self.assertTrue(run.call_args.kwargs['check'])

    def test_external_and_unknown_recipients_never_invoke_delivery(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(smtp, 'MAILDIR_BASE', root), patch.object(smtp.subprocess, 'run') as run:
                self.assertFalse(smtp.deliver_to_maildir('nobody@example.org', b'body'))
                self.assertFalse(smtp.deliver_to_maildir('unknown@techcorp.local', b'body'))
                run.assert_not_called()

    def test_failed_lda_does_not_report_success(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, 'techcorp.local/alice/Maildir').mkdir(parents=True)
            with patch.object(smtp, 'MAILDIR_BASE', root), patch.object(smtp.subprocess, 'run', side_effect=subprocess.CalledProcessError(75, 'dovecot-lda')):
                with self.assertRaises(subprocess.CalledProcessError):
                    smtp.deliver_to_maildir('alice@techcorp.local', b'body')


if __name__ == '__main__':
    unittest.main()
