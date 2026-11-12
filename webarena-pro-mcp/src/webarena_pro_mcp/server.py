"""Public Streamable HTTP MCP; private grading is Unix-socket only."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server import Server
from mcp.types import CallToolResult, ListToolsResult, Tool
from starlette.responses import JSONResponse
from starlette.routing import Route

from .session import open_session


def make_app(episode, *, host="127.0.0.1"):
    async def list_tools(_context, _params):
        return ListToolsResult(tools=[Tool.model_validate(t) for t in episode.tools.values()])

    async def call_tool(_context, params):
        return CallToolResult.model_validate(
            await episode.call(params.name, params.arguments or {})
        )

    async def health(_request):
        return JSONResponse({"ready": True})

    server = Server(
        "webarena-pro",
        version="0.1.0",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        instructions="Use these tools to interact with the task websites. Finish with webarena_submit(answer).",
        get_tool_input_schema=lambda name: episode.tools.get(name, {}).get("inputSchema"),
    )
    return server.streamable_http_app(
        host=host,
        stateless_http=True,
        json_response=True,
        max_request_body_size=256 * 1024,
        custom_starlette_routes=[Route("/health", health)],
    )


@asynccontextmanager
async def control_socket(episode, socket_path: Path):
    socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    async def handle(reader, writer):
        try:
            request = await asyncio.wait_for(reader.readline(), 10)
            if request != b"finalize\n":
                response = {"status": "error", "error": "Unsupported control command"}
            else:
                response = await episode.finalize()
            writer.write(json.dumps({"status": response["status"]}).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle, path=socket_path, limit=1024)
    socket_path.chmod(0o600)
    try:
        async with server:
            yield
    finally:
        socket_path.unlink(missing_ok=True)


async def serve(config_path, directory, socket_path, port, *, host="127.0.0.1"):
    import uvicorn

    os.umask(0o077)
    config = json.loads(Path(config_path).read_text())
    async with open_session(config, Path(directory)) as episode:
        async with control_socket(episode, Path(socket_path)):
            server = uvicorn.Server(
                uvicorn.Config(make_app(episode, host=host), host=host, port=port, access_log=False)
            )
            await server.serve()


async def finalize(socket_path, timeout):
    async with asyncio.timeout(timeout):
        reader, writer = await asyncio.open_unix_connection(socket_path)
        try:
            writer.write(b"finalize\n")
            await writer.drain()
            result = json.loads(await reader.readline())
            if result.get("status") != "graded":
                raise RuntimeError(
                    "Core evaluation failed; inspect the private result.json artifact"
                )
        finally:
            writer.close()
            await writer.wait_closed()
