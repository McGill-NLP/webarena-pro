#!/usr/bin/env python3
"""Run inside a disposable Thunderbird container; exercises real mail delivery.

    docker exec -i thunderbird-test python3 < tests/smoke_sieve.py

Creates and removes a temporary active Sieve script for seed user Alice.
"""
import base64
from email.message import EmailMessage
import imaplib
import json
import smtplib
import socket
import uuid

user = 'alice@techcorp.local'
password = 'User@Secure123'
marker = 'Sieve regression ' + uuid.uuid4().hex
script_name = 'webarena-regression'

connection = socket.create_connection(('127.0.0.1', 4190), timeout=15)
stream = connection.makefile('rwb', buffering=0)

def response():
    lines = []
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError('ManageSieve connection closed')
        lines.append(line.decode())
        if line.startswith((b'OK', b'NO', b'BYE')):
            assert line.startswith(b'OK'), lines
            return ''.join(lines)

def command(value):
    stream.write(value.encode() + b'\r\n')
    return response()

capabilities = response()
assert 'fileinto' in capabilities, capabilities
credentials = base64.b64encode(('\0' + user + '\0' + password).encode()).decode()
command('AUTHENTICATE "PLAIN" "' + credentials + '"')
script = ('require ["fileinto", "envelope"];\n'
          'if allof (header :is "Subject" "' + marker + '", '
          'envelope :is "from" "bob@techcorp.local") { fileinto "Work"; stop; }\n')
stream.write(f'PUTSCRIPT "{script_name}" {{{len(script.encode())}+}}\r\n'.encode() + script.encode() + b'\r\n')
response()
assert marker in command('GETSCRIPT "' + script_name + '"')
command('SETACTIVE "' + script_name + '"')

message = EmailMessage()
message['Subject'] = marker
message['From'] = 'bob@techcorp.local'
message['To'] = user
message.set_content('A saved filter should route this message to Work.')
with smtplib.SMTP('127.0.0.1', 25, timeout=40) as smtp:
    smtp.send_message(message)
with imaplib.IMAP4('127.0.0.1') as imap:
    imap.login(user, password)
    assert imap.select('Work')[0] == 'OK'
    result, data = imap.search(None, 'HEADER', 'Subject', '"' + marker + '"')
    assert result == 'OK' and data[0], (result, data)
    for uid in data[0].split():
        imap.store(uid, '+FLAGS', '(\\Deleted)')
    imap.expunge()
    imap.select('INBOX')
    result, data = imap.search(None, 'HEADER', 'Subject', '"' + marker + '"')
    assert result == 'OK' and not data[0], (result, data)
command('SETACTIVE ""')
command('DELETESCRIPT "' + script_name + '"')
command('LOGOUT')
print(json.dumps({'script_saved': True, 'fileinto_advertised': True,
                  'envelope_sender_preserved': True, 'delivered_to_Work_only': True}))
