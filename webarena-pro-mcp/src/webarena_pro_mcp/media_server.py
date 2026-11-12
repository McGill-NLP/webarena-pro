"""Independent stdio MCP server for media registered in one worker's browser."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import sys
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from .artifacts import atomic_json, safe_error
from .browser_identity import BrowserIdentityError, IDENTITY_SCHEMA, browser_document_kind, resolve_page, verify_identity
from .media_policy import (
    MAX_ATTACHMENT_BYTES,
    MAX_CACHE_BYTES,
    MAX_FRAMES,
    MAX_TRANSCRIBE_SECONDS,
    MAX_SOURCE_BYTES,
    MediaSettings,
    schemas,
    validate,
)
from .tool_policy import PolicyError, URLPolicy, origin

DISCOVER = """() => Array.from(document.querySelectorAll('audio,video')).map((el,index) => ({
  index, kind:el.tagName.toLowerCase(), src:el.currentSrc || el.src || el.querySelector('source[src]')?.src || '',
  title:el.getAttribute('aria-label') || el.getAttribute('title') || '',
  duration:Number.isFinite(el.duration) ? el.duration : null
})).filter(m => m.src)"""
BLOB = """async url => {
 const response=await fetch(url);
 if(!response.ok)throw Error('Could not fetch blob media');
 return {reader:response.body.getReader(), pending:null, offset:0};
}"""
BLOB_CHUNK = """async state => {
 if(!state.pending || state.offset===state.pending.length) {
   const {value,done}=await state.reader.read();
   if(done)return null;
   state.pending=value; state.offset=0;
 }
 const chunk=state.pending.subarray(state.offset,state.offset+65536); state.offset+=chunk.length;
 let text='';for(let i=0;i<chunk.length;i+=8192)text+=String.fromCharCode(...chunk.subarray(i,i+8192));
 return btoa(text);
}"""



def display_url(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


class MediaPagePolicyError(PolicyError):
    """A sanitized stage/category diagnosis for a rejected inventory page."""

    def __init__(self, error):
        self.category = {
            "URL is outside the selected task websites": "outside_task_origins",
            "Reset/evaluator endpoint is private": "private_endpoint",
            "Direct navigation to application APIs is not a UI action": "application_api",
            "Ambiguous URL path": "ambiguous_path",
            "Malformed URL": "malformed_url",
        }.get(str(error), "unsupported_or_invalid_url")
        super().__init__(f"Media inventory rejected page_url ({self.category})")


class MediaEngine:
    def __init__(self, config):
        self.settings = MediaSettings(**config["settings"])
        self.policy = URLPolicy(config["urls"], config["blocked_paths"])
        self.root = Path(config["directory"])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.endpoint = config["endpoint"]
        self.runtime = None
        self.entries = {}

    async def start(self):
        from playwright.async_api import async_playwright

        self.runtime = await async_playwright().start()
        try:
            # Preserve the supervisor's download directory and browser settings.
            self.browser = await self.runtime.chromium.connect_over_cdp(self.endpoint, no_defaults=True)
            self.context = self.browser.contexts[0]
            self.cdp = await self.browser.new_browser_cdp_session()
        except BaseException:
            await self.close()
            raise

    async def close(self):
        # Disconnect this client; the supervisor owns the actual browser.
        if self.runtime:
            await self.runtime.stop()
            self.runtime = None

    def source_allowed(self, url, frame):
        if url.startswith("blob:"):
            self.policy.check(url[5:])
            if origin(url[5:]) != origin(frame.url):
                raise PolicyError("Blob media must belong to its registered frame")
        else:
            self.policy.check(url)

    async def discover(self, identity):
        self.entries = {}
        self.inventory_diagnostic = None
        page = await resolve_page(self.context, identity)
        url = identity["url"]
        if kind := browser_document_kind(url):
            await verify_identity(page, identity)
            self.inventory_diagnostic = {"status": "no_media", "stage": "page_url", "url_category": kind}
            return []
        try:
            self.policy.check(url, navigation=True)
        except PolicyError as exc:
            raise MediaPagePolicyError(exc) from None
        result = []
        for frame_index, frame in enumerate(page.frames):
            try:
                self.policy.check(frame.url, navigation=True)
            except PolicyError:
                continue
            try:
                discovered = await frame.evaluate(DISCOVER)
            except Exception:
                # A navigation can destroy the JS context between policy check
                # and inventory. Retry only after the identity guard confirms
                # the main document changed; detached child frames have no media.
                await verify_identity(page, identity)
                if frame.is_detached():
                    continue
                raise
            for media in discovered:
                try:
                    self.source_allowed(media["src"], frame)
                except PolicyError:
                    continue
                source_identity = [identity, frame_index, frame.url, media["index"], media["src"]]
                ref = "m" + hashlib.sha256(json.dumps(source_identity).encode()).hexdigest()[:24]
                self.entries[ref] = (frame, media, frame.url)
                result.append(
                    {
                        "ref": ref,
                        "kind": media["kind"],
                        "src": display_url(media["src"]),
                        "title": media["title"],
                        "duration": media["duration"],
                    }
                )
        await verify_identity(page, identity)
        return result

    async def resolve(self, ref):
        if ref not in self.entries:
            raise PolicyError("Unknown/stale media reference; inspect the current browser observation")
        frame, media, frame_url = self.entries[ref]
        if (
            frame.is_detached()
            or frame.url != frame_url
            or not any(
                item["index"] == media["index"] and item["src"] == media["src"]
                for item in await frame.evaluate(DISCOVER)
            )
        ):
            raise PolicyError("Media source changed; inspect the current browser observation")
        self.source_allowed(media["src"], frame)
        return frame, media

    def prune_sources(self, keep):
        """Bound retained sources and derived clips by both count and disk bytes."""
        directories = sorted(
            (path for path in (self.root / "sources").iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
        )
        sizes = {path: sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
                 for path in directories}
        count, total = len(directories), sum(sizes.values())
        for path in directories:
            if count <= 8 and total <= MAX_CACHE_BYTES:
                break
            if path != keep:
                shutil.rmtree(path)
                count -= 1
                total -= sizes[path]
        # Repeated watch variants can fill even the retained source's derived
        # cache. Evict those files too; the validated source itself is <=512 MiB.
        for path in sorted((p for p in keep.iterdir() if p.name != "source.media"),
                           key=lambda p: p.stat().st_mtime):
            if total <= MAX_CACHE_BYTES:
                break
            size = (sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
                    if path.is_dir() else path.stat().st_size)
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            total -= size

    async def fetch(self, ref):
        """Stream validated hops into a local source, never buffering the file."""
        import httpx
        from webarena_pro_media.cache import MediaSource

        frame, media = await self.resolve(ref)
        url = media["src"]
        sources = self.root / "sources"
        sources.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(prefix=".fetch-", dir=sources)
        temporary = Path(temporary)
        digest, size, prefix = hashlib.sha256(), 0, bytearray()
        try:
            with os.fdopen(descriptor, "wb") as output:
                def write(chunk):
                    nonlocal size
                    size += len(chunk)
                    if size > MAX_SOURCE_BYTES:
                        raise PolicyError("Media source exceeds the 512 MiB download limit")
                    prefix.extend(chunk[:max(0, 16 - len(prefix))])
                    digest.update(chunk)
                    output.write(chunk)

                async with asyncio.timeout(self.settings.timeout):
                    if url.startswith("blob:"):
                        reader = await frame.evaluate_handle(BLOB, url)
                        try:
                            while (chunk := await reader.evaluate(BLOB_CHUNK)) is not None:
                                write(base64.b64decode(chunk, validate=True))
                        finally:
                            try:
                                await reader.evaluate("state => state.reader.cancel()")
                            finally:
                                await reader.dispose()
                    else:
                        async with httpx.AsyncClient(
                            trust_env=False, follow_redirects=False,
                            timeout=httpx.Timeout(30, connect=10),
                        ) as session:
                            for _ in range(6):
                                self.policy.check(url)
                                # Query cookies only after validating this hop. Never forward
                                # response cookies or credentials to a redirect destination.
                                session.cookies.clear()
                                cookies = await self.context.cookies([url])
                                headers = {"Cookie": "; ".join(f"{c['name']}={c['value']}" for c in cookies)}
                                async with session.stream("GET", url, headers=headers) as response:
                                    if response.is_redirect:
                                        url = urljoin(url, response.headers["Location"])
                                        continue
                                    response.raise_for_status()
                                    content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
                                    if content_type not in {"application/octet-stream", "application/ogg"} and not content_type.startswith(("audio/", "video/")):
                                        raise PolicyError("Registered source did not return audio/video")
                                    if int(response.headers.get("Content-Length", 0)) > MAX_SOURCE_BYTES:
                                        raise PolicyError("Media source exceeds the 512 MiB download limit")
                                    async for chunk in response.aiter_bytes(65536):
                                        write(chunk)
                                    break
                            else:
                                raise PolicyError("Too many media redirects")
            # Exclude playlists/documents and decoder-side network fetches.
            known = (
                prefix.startswith((b"RIFF", b"ID3", b"OggS", b"fLaC", b"\x1a\x45\xdf\xa3"))
                or prefix[4:8] == b"ftyp"
                or (len(prefix) > 2 and prefix[0] == 255 and prefix[1] & 224 == 224)
            )
            if not known or not size:
                raise PolicyError("Unsupported media container; streaming playlists are not supported")
            version = digest.hexdigest()
            source_dir = sources / version
            source_dir.mkdir(exist_ok=True, mode=0o700)
            path = source_dir / "source.media"
            temporary.replace(path)
            source_dir.touch()
            self.prune_sources(source_dir)
            return MediaSource(path, version, size, {}), media
        finally:
            temporary.unlink(missing_ok=True)

    async def perform(self, name, arguments):
        from webarena_pro_media.async_api import (
            extract_media_clip,
            extract_video_frames,
            extract_watch_clip,
            transcribe_audio,
        )
        from webarena_pro_media.async_api import _offload
        from webarena_pro_media.video import probe_video_duration

        args = validate(name, arguments, self.settings)
        source, media = await self.fetch(args["ref"])
        digest = source.version
        start, end = args["start_seconds"], args["end_seconds"]
        if name == "media_transcribe":
            duration = await _offload(probe_video_duration, source.path)
            if duration is None or not math.isfinite(duration) or duration <= start:
                raise PolicyError("Cannot determine a usable audio/video duration")
            end = min(end, duration) if end is not None else duration
            if end - start > MAX_TRANSCRIBE_SECONDS:
                raise PolicyError("Transcription intervals cannot exceed one hour; select a shorter range")
        metadata = {
            "ref": args["ref"],
            "source_sha256": digest,
            "source_url": display_url(media["src"]),
            "requested_start": args["start_seconds"],
            "requested_end": args["end_seconds"],
            "tool": name,
        }
        content = []
        if name == "media_listen":
            clip = await extract_media_clip(media["src"], start, end, n_frames=0, source=source)
            metadata.update({k: v for k, v in clip.items() if k not in {"audio_b64", "frames", "url"}})
            content.append({"type": "audio", "mimeType": "audio/wav", "data": clip["audio_b64"]})
        elif name == "media_transcribe":
            audit_path = self.root / ("transcription-" + os.urandom(8).hex() + ".json")
            audit = {**metadata, "phase": "pending", "backend": self.settings.transcription,
                     "model": "whisper-1" if self.settings.transcription == "api" else "local", "chunks": []}
            atomic_json(audit_path, audit)
            transcripts = []
            try:
                # Balance the chunks so a tiny final remainder is not sent alone.
                count = max(1, math.ceil((end - start) / 60))
                for index in range(count):
                    chunk_start = start + (end - start) * index / count
                    chunk_end = start + (end - start) * (index + 1) / count
                    clip = await extract_media_clip(media["src"], chunk_start, chunk_end, n_frames=0, source=source)
                    wav = base64.b64decode(clip["audio_b64"])
                    wav_digest = hashlib.sha256(wav).hexdigest()
                    wav_path = self.root / "attachments" / wav_digest
                    wav_path.parent.mkdir(exist_ok=True, mode=0o700)
                    wav_path.write_bytes(wav)
                    audit["audio_sha256"] = wav_digest
                    chunk_audit = {"start": clip.get("start", chunk_start), "end": clip.get("end", chunk_end),
                                   "audio_sha256": wav_digest, "phase": "pending"}
                    audit["chunks"].append(chunk_audit)
                    atomic_json(audit_path, audit)
                    if self.settings.transcription == "local":
                        transcript = await transcribe_audio(wav, use_api=False)
                    else:
                        from openai import AsyncOpenAI

                        key = os.environ.get("WEBARENA_PRO_ASR_API_KEY")
                        if not key:
                            raise RuntimeError("Set WEBARENA_PRO_ASR_API_KEY or select local/disabled transcription")
                        async with AsyncOpenAI(
                            api_key=key, base_url=os.environ.get("WEBARENA_PRO_ASR_BASE_URL"),
                            max_retries=0, timeout=self.settings.timeout,
                        ) as client:
                            transcript = (await client.audio.transcriptions.create(
                                model="whisper-1", file=("audio.wav", wav, "audio/wav"),
                            )).text
                    transcripts.append(transcript)
                    chunk_audit.update(phase="returned", transcript=transcript)
                    atomic_json(audit_path, audit)
                transcript = "\n".join(text for text in transcripts if text.strip())
                metadata.update(transcript=transcript, start=start, end=end,
                                status="transcribed" if transcript.strip() else "no_speech")
                atomic_json(audit_path, {**audit, "phase": "returned", "transcript": transcript})
            except Exception as exc:
                atomic_json(audit_path, {**audit, "phase": "error", "error": safe_error(exc)})
                raise
        elif name == "media_extract_frames":
            frames = await extract_video_frames(
                media["src"], args.get("n_frames", 5), start, -1 if end is None else end, width=768, source=source
            )
            if not frames or any(not frame["image_b64"] for frame in frames):
                raise RuntimeError("Frame extraction failed; no complete observation was produced")
            metadata.update(representation="sampled_images", timestamps=[f["timestamp"] for f in frames])
            content.extend(
                {"type": "image", "mimeType": "image/jpeg", "data": f["image_b64"]} for f in frames
            )
        else:
            clip = await extract_watch_clip(
                media["src"],
                start,
                end,
                mode=args.get("mode", "overview"),
                include_audio=args.get("include_audio", False),
                max_frames=args.get("max_frames", MAX_FRAMES),
                fps=args.get("fps", 1),
                max_input_tokens=131072,
                source=source,
            )
            metadata.update({k: v for k, v in clip.items() if k not in {"video_b64", "frames", "url"}})
            frames = clip.get("frames", [])
            metadata["timestamps"] = [f["timestamp"] for f in frames]
            content.extend(
                {"type": "image", "mimeType": "image/jpeg", "data": f["image_b64"]} for f in frames
            )
            if clip.get("video_b64"):
                content.append(
                    {
                        "type": "resource",
                        "resource": {
                            "uri": "webarena-media://clip/"
                            + hashlib.sha256(base64.b64decode(clip["video_b64"])).hexdigest(),
                            "mimeType": "video/mp4",
                            "blob": clip["video_b64"],
                        },
                    }
                )
        size = sum(len(base64.b64decode(item.get("data") or item["resource"]["blob"])) for item in content)
        if size > MAX_ATTACHMENT_BYTES:
            raise PolicyError("Media attachments exceed 8 MiB; select a smaller interval/fewer frames")
        for item in content:
            blob = base64.b64decode(item.get("data") or item["resource"]["blob"])
            artifact = self.root / "attachments" / hashlib.sha256(blob).hexdigest()
            artifact.parent.mkdir(exist_ok=True, mode=0o700)
            artifact.write_bytes(blob)
        content.insert(0, {"type": "text", "text": json.dumps(metadata, ensure_ascii=False)})
        self.prune_sources(source.path.parent)
        return {"content": content, "structuredContent": metadata, "isError": False}


async def serve(config, *, profile="standard"):
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import CallToolResult, ListToolsResult, Tool

    settings = MediaSettings(**config["settings"])
    if settings.profile != profile:
        raise ValueError(f"The {profile} media server cannot serve the {settings.profile} profile")
    engine = MediaEngine(config)
    await engine.start()
    lock = asyncio.Lock()
    definitions = schemas(engine.settings)
    definitions["media_inventory"] = {
        "name": "media_inventory",
        "inputSchema": {
            "type": "object",
            "properties": {"identity": IDENTITY_SCHEMA},
            "required": ["identity"],
            "additionalProperties": False,
        },
    }

    async def list_tools(_context, _params):
        return ListToolsResult(tools=[Tool.model_validate(tool) for tool in definitions.values()])

    async def dispatch(name, args):
        from jsonschema import validate as check_schema

        try:
            if name not in definitions:
                raise PolicyError("Unknown media MCP tool")
            check_schema(args, definitions[name]["inputSchema"])
            if name == "media_inventory":
                result = {"sources": await engine.discover(**args)}
                if engine.inventory_diagnostic:
                    result["diagnostic"] = engine.inventory_diagnostic
            else:
                return await engine.perform(name, args)
            return {"content": [{"type": "text", "text": json.dumps(result)}], "structuredContent": result}
        except Exception as exc:
            details = {}
            if isinstance(exc, BrowserIdentityError):
                details = {"error_code": "browser_identity_changed"}
            elif isinstance(exc, MediaPagePolicyError):
                details = {"error_code": "page_url_policy", "stage": "page_url", "url_category": exc.category}
            return {"content": [{"type": "text", "text": safe_error(exc)}],
                    "isError": True, "structuredContent": details}

    async def call_tool(_context, params):
        async with lock:
            result = await dispatch(params.name, params.arguments or {})
        return CallToolResult.model_validate(result)

    server = Server(
        settings.server_name,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
        get_tool_input_schema=lambda name: definitions.get(name, {}).get("inputSchema"),
    )
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    finally:
        async with lock:
            await engine.close()


def main(*, profile="standard"):
    os.umask(0o077)
    if len(sys.argv) != 2:
        suffix = "-omni" if profile == "omni" else ""
        raise SystemExit(f"Usage: webarena-pro-media-mcp{suffix} <private-worker-config.json>")
    asyncio.run(serve(json.loads(Path(sys.argv[1]).read_text()), profile=profile))


def omni_main():
    main(profile="omni")


if __name__ == "__main__":
    main()
