import os

import pytest

from webarena_pro_bgym.queue_client import QueueClient


@pytest.mark.parametrize("response", [b"", b"not json\n", b'{"ok":true}',
    b'{"ok":false,"error":"rejected"}\n', b'{"ok":true,"task_id":"bad"}\n'])
def test_client_rejects_disconnected_or_malformed_coordinator(response):
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    client = QueueClient(request_write, response_read)
    try:
        os.write(response_write, response)
        os.close(response_write)
        with pytest.raises(RuntimeError):
            client.claim()
        assert not os.get_inheritable(request_write)
        assert not os.get_inheritable(response_read)
    finally:
        client.close()
        os.close(request_read)


def test_client_reports_closed_request_pipe():
    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    client = QueueClient(request_write, response_read)
    os.close(request_read)
    try:
        with pytest.raises(RuntimeError, match="disconnected"):
            client.claim()
    finally:
        client.close()
        os.close(response_write)


@pytest.mark.parametrize("lookahead", [False, True])
def test_claim_retains_retry_metadata_and_clears_it_on_empty_reply(lookahead):
    import json

    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    client = QueueClient(request_write, response_read)
    metadata = {"task_id": 7, "retry_count": 2, "full_retry": False, "resume_worker_id": "previous"}
    try:
        os.write(response_write, (json.dumps({"ok": True, **metadata}) + "\n").encode())
        assert client.claim(lookahead=lookahead) == 7
        assert client.last_claim == metadata
        assert json.loads(os.read(request_read, 4096)) == {"action": "claim", "lookahead": lookahead}
        os.write(response_write, b'{"ok":true,"task_id":null}\n')
        assert client.claim(lookahead=lookahead) is None
        assert client.last_claim is None
    finally:
        client.close()
        os.close(request_read)
        os.close(response_write)


@pytest.mark.parametrize("invalid", [
    {"retry_count": None}, {"retry_count": True}, {"retry_count": -1},
    {"retry_count": 1.5}, {"full_retry": 1}, {"full_retry": None},
    {"resume_worker_id": 8}, {"resume_worker_id": ""},
])
def test_client_rejects_invalid_claim_retry_metadata(invalid):
    import json

    request_read, request_write = os.pipe()
    response_read, response_write = os.pipe()
    client = QueueClient(request_write, response_read)
    response = {"ok": True, "task_id": 7, "retry_count": 1,
                "full_retry": False, "resume_worker_id": "previous", **invalid}
    try:
        os.write(response_write, (json.dumps(response) + "\n").encode())
        with pytest.raises(RuntimeError, match="retry metadata"):
            client.claim()
        assert client.last_claim is None
    finally:
        client.close()
        os.close(request_read)
        os.close(response_write)
