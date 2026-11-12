"""Synchronous worker side of the coordinator's JSON-line pipe protocol."""

from __future__ import annotations

import json
import os

MAX_MESSAGE_BYTES = 65536
REQUEST_FD_ENV = "WP_QUEUE_REQUEST_FD"
RESPONSE_FD_ENV = "WP_QUEUE_RESPONSE_FD"


class QueueClient:
    def __init__(self, request_fd: int, response_fd: int):
        os.set_inheritable(request_fd, False)
        os.set_inheritable(response_fd, False)
        self.writer = os.fdopen(request_fd, "wb", buffering=0)
        self.reader = os.fdopen(response_fd, "rb")
        self.last_claim: dict | None = None

    @classmethod
    def from_environment(cls):
        try:
            return cls(int(os.environ[REQUEST_FD_ENV]), int(os.environ[RESPONSE_FD_ENV]))
        except (KeyError, ValueError) as error:
            raise RuntimeError("Queue worker requires coordinator pipe descriptors") from error

    def _request(self, action: str, **values):
        message = json.dumps({"action": action, **values}).encode() + b"\n"
        if len(message) > MAX_MESSAGE_BYTES:
            raise ValueError("Queue protocol message is too large")
        try:
            offset = 0
            while offset < len(message):
                written = self.writer.write(message[offset:])
                if not written:
                    raise BrokenPipeError("Queue request pipe closed")
                offset += written
            response = self.reader.readline(MAX_MESSAGE_BYTES + 1)
        except (OSError, ValueError) as error:
            raise RuntimeError("Queue coordinator disconnected") from error
        if not response:
            raise RuntimeError("Queue coordinator disconnected")
        if len(response) > MAX_MESSAGE_BYTES or not response.endswith(b"\n"):
            raise RuntimeError("Invalid queue coordinator response")
        try:
            reply = json.loads(response)
        except ValueError as error:
            raise RuntimeError("Invalid queue coordinator response") from error
        if not isinstance(reply, dict) or reply.get("ok") is not True:
            raise RuntimeError(f"Queue coordinator rejected request: {reply}")
        return reply

    def claim(self, *, lookahead: bool = False) -> int | None:
        self.last_claim = None
        reply = self._request("claim", lookahead=lookahead)
        task_id = reply.get("task_id")
        if "task_id" not in reply or (task_id is not None and type(task_id) is not int):
            raise RuntimeError("Invalid task ID from queue coordinator")
        if task_id is not None:
            retry_count = reply.get("retry_count")
            full_retry = reply.get("full_retry")
            resume_worker_id = reply.get("resume_worker_id")
            if (type(retry_count) is not int or retry_count < 0
                    or type(full_retry) is not bool or "resume_worker_id" not in reply
                    or (resume_worker_id is not None
                        and (not isinstance(resume_worker_id, str) or not resume_worker_id))):
                raise RuntimeError("Invalid retry metadata from queue coordinator")
            self.last_claim = {
                "task_id": task_id, "retry_count": retry_count,
                "full_retry": full_retry, "resume_worker_id": resume_worker_id,
            }
        return task_id

    def started(self, task_id: int) -> None:
        # The ACK is sent only after the coordinator fsyncs the started event.
        self._request("started", task_id=task_id)

    def complete(self, task_id: int) -> None:
        self._request("done", task_id=task_id)

    def fail(self, task_id: int, error: str) -> None:
        self._request("failed", task_id=task_id, error=str(error)[:8192])

    def close(self) -> None:
        self.writer.close()
        self.reader.close()
