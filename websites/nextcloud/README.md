# WebArena-Pro-NextCloudWebsite

Build the image and start the single-container environment:

```bash
docker compose up --build -d
```

Nextcloud is available at `http://localhost:8080`. Set
`WP_NEXTCLOUD_HOST_PORT` and `WP_NEXTCLOUD_URL` for another public port or URL.
Spreadsheet editing uses **bundled Collabora CODE 26.4.502**, installed at build
time from checksum-verified x86-64/ARM64 release archives. There is no separate
Office port, manual service, or runtime app download in the default deployment.
The editor stays on the selected worker's Nextcloud origin, including its
`.localhost` hostname and port, and its callback stays inside that container.

**Image compatibility:** deploy an updated `webarenapro/nextcloud` image together
with the Core readiness change. Images published before bundled Office support
lack the office service and `/webarena-office-health.php`. Core rejects those
images as not ready instead of starting a task without spreadsheet support.
When upgrading Core, pull the updated image (or build this directory locally)
and recreate the Nextcloud containers before running tasks. Updating Core alone
does not replace an existing container's image.

Office discovery and capabilities are verified at startup and after every state
reset before `/webarena-office-health.php` returns `office-ready`. Login is also
still checked. Startup has a 180-second bound, including each activation process;
failures appear in `/tmp/webarena-office-startup.log` and container logs. Reset
stops the old CODE process before restoring the seeded database and files, then
reconfigures and starts it. A spreadsheet created during a task is removed by
reset, and a fresh one can be created afterward.

Allow approximately two CPU cores and 1 GiB plus 100 MiB per active editor for
CODE, in addition to Nextcloud. Each worker owns its service, so account for this
when choosing worker count. The bundled app extracts its AppImage without FUSE
or privileged container capabilities. Its first start can be slower.

An existing external Office service is optional: set `WP_COLLABORA_URL` to its
browser URL, `WP_COLLABORA_INTERNAL_URL` if Nextcloud must use another address,
and `WP_NEXTCLOUD_CALLBACK_URL` if Office needs a separate Nextcloud callback.
The default callback for an external service is the configured public Nextcloud
URL. Those URLs must be reachable from their respective clients; HTTPS public
URLs require a real reachable TLS proxy. HTTP worker hostnames are routed back
to their own container for CODE self-requests. The external service must also
be allowed by the agent's configured browser policy if it uses another origin.

How to use:

- The website is pre-seeded for the fictional company Cedarstone Analytics, with Maya Patel, Daniel Brooks, four supporting Talk users, and an admin account.
- We recommend using the Maya Patel and Daniel Brooks accounts for testing and development.
- The admin account is username: admin, password: admin
- Maya Patel: username `maya.patel`, password `agentpass`, email `maya.patel@cedarstone.test`
- Daniel Brooks: username `daniel.brooks`, password `agentpass`, email `daniel.brooks@cedarstone.test`
- The supporting Talk usernames are sarah, priya, marcus, and leon; each uses password: agentpass

The fresh-volume image contains 10,000 populated business files, split evenly between maya.patel and daniel.brooks. Twenty managed categories per user contain irregular totals between 126 and 348 documents. The corpus includes 200 unmodified open-source documents, 696 invoice PDFs, 584 purchase-order PDFs with matching requisitions, annual vendor assessments and notes, 16 readable DOCX vendor masters, 108 monthly timesheets, 360 authentic dataset-derived customer-order workbooks, and 314 SVG order plots. Six varied current work files appear directly at each user's `All files` root. The original 100,000-row order workbook is retained for both agents. It also contains 200 contacts (100 per agent), 100 calendar resources, 24 business notifications, and 425 authored Talk messages with validated cross-service links to contacts and files. See [DATASET_CARD.md](DATASET_CARD.md) for provenance, licensing, generation, and reset instructions.

### Preseeded startup and reset validation

The preseeded entrypoint and `webarena-reset-state` restore `www-data` ownership
of `config/` and `data/`, apply the runtime public URL, and regenerate `.htaccess`
as `www-data`. A regeneration error fails startup/reset with the `occ` output and
an actionable message. The image healthcheck probes `/login` and the Office readiness endpoint;
`/status.php` alone can succeed while Apache rewrite rules are missing. A narrowly
scoped Apache alias serves Office readiness outside Nextcloud's PHP front-controller
allowlist and survives `.htaccess` regeneration during reset.

Build and run the opt-in Docker regression suite from the repository root:

```bash
docker build -t nextcloud-runtime-test websites/nextcloud
uv run --project webarena-pro-core python websites/nextcloud/tests/test_runtime.py \
  --image nextcloud-runtime-test
```

The suite creates and removes its own container and empty `volume-nocopy` volume,
uses a random loopback port, and calls the runner's actual HTTP readiness probe.
It covers clean-volume startup, reset with a root-owned snapshot, missing rewrite
rules, external host/port configuration, and regeneration failures. It never
starts the shared benchmark proxy. Publishing a rebuilt image is a separate
release step; changing these source files does not update existing Docker tags.

### Text editor browser regression

The login healthcheck cannot establish that the Text editor initialized. Run the
opt-in browser test against an already-pulled published image or a local build:

```bash
uv run --project webarena-pro-bgym python websites/nextcloud/tests/test_text_editor.py \
  --image webarenapro/nextcloud:latest --evidence-dir /tmp/nextcloud-text-evidence
```

Install Chromium with `uv run --project webarena-pro-bgym python -m playwright
install chromium` first. The test creates its own random loopback port, worker-like
`.localhost` origin, 3 GiB / 1.5 CPU container, and empty volume. It creates a
Markdown file through **New > New text file**, waits at most 30 seconds for a
usable editor, types text, uses **Save document**, closes the viewer, checks its saved WebDAV
contents, and reopens it. It
repeats that flow after the image's actual reset command and verifies that the
pre-reset file disappeared. Only its labeled container and volume are removed.
No existing deployment, shared proxy, or model API is used.

The evidence directory records image digest, Chromium version, reset output,
browser exceptions, failed HTTP requests (without query strings), screenshots,
and bounded server logs. On editor startup timeout, inspect those artifacts
instead of waiting through an entire agent step budget. Evidence may contain
benchmark file text and should be kept with the private run artifacts.

The image patches Nextcloud 32.0.12's template-picker startup race: file creation
now waits for the picker component to load before mounting and opening it. The
patch fails the build if an upstream bundle changes and must be reviewed when
upgrading Nextcloud. This addresses a reproduced cold-start error on Chromium
125 and 148; it does not establish the cause of the original report's
16-worker loading-placeholder hang.

### Office regression

Build the image above, install Chromium, then run the opt-in suite from the
repository root:

```bash
uv run --project webarena-pro-bgym python websites/nextcloud/tests/test_office.py \
  --image nextcloud-runtime-test --evidence-dir /tmp/nextcloud-office-evidence
```

The suite uses its own labeled 3 GiB / 1.5 CPU container, empty volume and random
loopback port. It creates a spreadsheet through the New menu, edits a cell,
checks the actual XLSX contents through WebDAV and reopens it, then repeats
creation/editing after reset. It also retains the filesystem/reset regressions
and checks all three effective Office URLs after native activation and reset.
External URL persistence is checked using the local service for discovery;
a separately hosted external Office deployment is not part of this smoke test.
