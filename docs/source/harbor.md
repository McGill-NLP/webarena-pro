# Harbor integration

For installation through a completed trial and its results, follow
[Run agents with Harbor](running-harbor-agents.md).

Use existing Harbor agents with WebArena-Pro's browser/media tools and Core DAG
grading. The adapter exports native Harbor tasks with Docker Compose website
services, an isolated Streamable HTTP MCP browser service, and a separate
verifier. Harbor controls the agent loop and trial scheduling.

For visual trace inspection, export a new dataset with `--record-screenshots`.
This records private images at the initial state and after completed actions,
without adding agent actions or images to the model's input. Recording adds
latency within the wall-time budget; unavailable captures are labeled rather
than reconstructed. The flag defaults off and does not modify historical runs.

The runtime bundles Core (including autologin and UI evidence), media, MCP, and
the Harbor adapter. Browser setup, UI evidence capture, and media use native
async APIs; Core grading consumes serialized UI facts on a private thread.
Rebuild the runtime and re-export tasks when updating to Core's bundled
autologin and UI evidence helpers.

The default standard media profile exposes transcription, frame extraction, and
JPEG watch overview. `export --native-audio` enables WAV listening and
`--native-video` enables inline MP4 watching independently; either selects the
omni profile. Use only the capabilities supported by the agent and model. `--browser-only` disables media.

The initial target is Docker on Linux. Use the documented Harbor revision with
sidecar artifact collection; cloud providers require separate validation.

From `webarena-pro-harbor/`:

```bash
uv sync --python 3.12 --locked --group dev
uv run --locked webarena-pro-harbor build-runtime
uv run --locked webarena-pro-harbor export --split dev --task 349 \
  --output ./exported/dev
```

Configure the private evaluator token and judge credentials, then use ordinary
Harbor commands with an MCP-capable agent:

```bash
harbor run -p ./exported/dev -a claude-code -m '<your-model>' -e docker -n 1
```

The package README includes [Codex and Claude Code examples](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-harbor/README.md#codex-and-claude-code-examples)
and a [Gemini CLI example](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-harbor/README.md#gemini-cli-with-google-models)
with OpenAI, Anthropic, and Google models, agent/judge credentials, pinned
agent versions, reasoning settings, separate result directories, and full-split
runs.

Each trial creates fresh website/browser state. Agent calls share a server-side
50/100/unlimited action budget. The agent must call `webarena_submit(answer)`;
its final chat response alone is not evaluator input. Grading runs against live
websites before teardown and writes partial credit, success, and available
checkpoint scores. Evaluator credentials, backend access, and grading controls
are not exposed as public agent tools.

See the [complete Harbor guide](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-harbor/README.md)
for supported versions, image pinning, media compatibility, credentials, resource
requirements, artifact formats, and the limits of offline regrading.
