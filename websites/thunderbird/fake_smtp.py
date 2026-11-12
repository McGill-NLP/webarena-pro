#!/usr/bin/env python3
"""Tiny fake SMTP server for the WebArena-Pro Thunderbird site.

The benchmark site must simulate email sending, not relay mail to the
internet. This server accepts SMTP submissions from Roundcube, delivers local
techcorp.local recipients into the seeded Maildir tree, and treats all other
recipients as successfully sent no-ops.
"""

from __future__ import annotations

import os
import re
import socketserver
import sys
import subprocess


HOST = os.environ.get("FAKE_SMTP_HOST", "127.0.0.1")
PORT = int(os.environ.get("FAKE_SMTP_PORT", "25"))
LOCAL_DOMAIN = os.environ.get("FAKE_SMTP_LOCAL_DOMAIN", "techcorp.local").lower()
MAILDIR_BASE = os.environ.get("MAILDIR_BASE", "/var/vmail")
MAX_MESSAGE_BYTES = int(os.environ.get("FAKE_SMTP_MAX_MESSAGE_BYTES", str(10 * 1024 * 1024)))

ADDRESS_RE = re.compile(r"<([^>]+)>")


def parse_address(value: str) -> str:
    match = ADDRESS_RE.search(value)
    if match:
        value = match.group(1)
    elif ":" in value:
        value = value.split(":", 1)[1]

    return value.strip().strip("<>").lower()


def maildir_for(address: str) -> str | None:
    if "@" not in address:
        return None

    local, domain = address.rsplit("@", 1)
    if domain.lower() != LOCAL_DOMAIN:
        return None

    maildir = os.path.join(MAILDIR_BASE, domain, local, "Maildir")
    if not os.path.isdir(maildir):
        return None

    return maildir


def deliver_to_maildir(recipient: str, message: bytes, sender: str = "") -> bool:
    if not maildir_for(recipient):
        return False

    # LDA applies the user's active Sieve script before writing the Maildir.
    # Keep the address as an argv value (never a shell command), and propagate
    # failures so SMTP does not claim success after losing a local message.
    subprocess.run(
        ["/usr/lib/dovecot/dovecot-lda", "-d", recipient, "-f", sender],
        input=message,
        check=True,
        timeout=30,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return True


def log(message: str) -> None:
    print(message, flush=True)


class FakeSMTPHandler(socketserver.StreamRequestHandler):
    timeout = 60

    def setup(self) -> None:
        super().setup()
        self.mail_from = ""
        self.recipients: list[str] = []

    def reply(self, code: int, message: str | list[str]) -> None:
        lines = [message] if isinstance(message, str) else message
        for index, line in enumerate(lines):
            separator = "-" if index < len(lines) - 1 else " "
            self.wfile.write(f"{code}{separator}{line}\r\n".encode("ascii"))

    def handle(self) -> None:
        self.reply(220, f"{LOCAL_DOMAIN} ESMTP WebArena fake mailer")

        while True:
            raw = self.rfile.readline(4096)
            if not raw:
                return

            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line:
                continue

            command, _, argument = line.partition(" ")
            command = command.upper()

            if command in {"EHLO", "HELO"}:
                self.reply(250, [LOCAL_DOMAIN, "8BITMIME", f"SIZE {MAX_MESSAGE_BYTES}", "HELP"])
            elif command == "AUTH":
                self.reply(235, "2.7.0 Authentication accepted")
            elif command == "MAIL":
                self.mail_from = parse_address(argument)
                self.recipients = []
                self.reply(250, "2.1.0 Sender accepted")
            elif command == "RCPT":
                recipient = parse_address(argument)
                if recipient:
                    self.recipients.append(recipient)
                self.reply(250, "2.1.5 Recipient accepted")
            elif command == "DATA":
                self.handle_data()
            elif command == "RSET":
                self.mail_from = ""
                self.recipients = []
                self.reply(250, "2.0.0 Reset")
            elif command == "NOOP":
                self.reply(250, "2.0.0 OK")
            elif command == "QUIT":
                self.reply(221, "2.0.0 Bye")
                return
            elif command == "STARTTLS":
                self.reply(454, "4.7.0 TLS is not available in the fake mailer")
            else:
                self.reply(502, "5.5.2 Command not implemented")

    def handle_data(self) -> None:
        if not self.recipients:
            self.reply(503, "5.5.1 Need RCPT command")
            return

        self.reply(354, "End data with <CR><LF>.<CR><LF>")
        chunks: list[bytes] = []
        total = 0
        too_large = False

        while True:
            raw = self.rfile.readline(4096)
            if not raw:
                return
            if raw in {b".\r\n", b".\n"}:
                break
            if raw.startswith(b".."):
                raw = raw[1:]
            total += len(raw)
            if total > MAX_MESSAGE_BYTES:
                too_large = True
                continue
            chunks.append(raw)

        if too_large:
            self.reply(552, "5.3.4 Message size exceeds fixed limit")
            return

        message = b"".join(chunks)
        try:
            delivered = [recipient for recipient in self.recipients if deliver_to_maildir(recipient, message, self.mail_from)]
        except (subprocess.SubprocessError, OSError) as error:
            log(f"local delivery failed: {error}")
            self.reply(451, "4.3.0 Local delivery temporarily unavailable")
            self.mail_from = ""
            self.recipients = []
            return
        external = [recipient for recipient in self.recipients if recipient not in delivered]

        log(
            "accepted message "
            f"from={self.mail_from or '<>'} delivered={delivered or []} external_noop={external or []}"
        )

        self.mail_from = ""
        self.recipients = []
        self.reply(250, "2.0.0 Message accepted for fake delivery")


class ThreadingSMTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


def main() -> int:
    with ThreadingSMTPServer((HOST, PORT), FakeSMTPHandler) as server:
        log(f"fake SMTP listening on {HOST}:{PORT}, local domain {LOCAL_DOMAIN}")
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
