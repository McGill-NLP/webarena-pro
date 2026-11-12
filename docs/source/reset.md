# Website Reset

WebArena-Pro resets websites before tasks so each agent episode starts from a
known seed state. The shared reset contract lives in
`webarena_pro_core.state_reset` and is reused by the AgentLab/BrowserGym
integration.

This page documents the reset backends, the current `auto` policy, the reset
mechanism used by each website, and local timing results. The historical
June/July measurements are retained below. See the
[evaluator image release checks](evaluator-images.md) for published image
releases and their validation evidence.

## Reset Entry Points

Use the package-level API when you need to reset a site from Python:

```python
from webarena_pro_core.state_reset import (
    recreate_site_container,
    reset_site,
    reset_site_container,
    restore_site_state,
)

reset_site("nextcloud")
restore_site_state("travelmap")
recreate_site_container("penpot")
```

`reset_site(site)` is the broad package API for reset-supported sites. It uses
the current core policy to choose either in-place state restore or container
recreation, bootstraps missing worker containers, and returns only after the
site readiness and packaged snapshot checks succeed.

`restore_site_state(site)` is stricter: it only runs the in-place restore
contract and raises if the site does not advertise one. This remains available
for sites whose default `auto` backend is now container recreation. It is a
low-level operation and does not perform readiness polling by itself.

`recreate_site_container(site)` forces a fresh container from the seed image.
It accepts any site registered in `WEBSITES_IMAGES`, including sites that are
not exposed through `reset_site(site)`. Use `reset_site_container(site)` when
the caller also needs to wait for the site and its reset snapshot to be ready.

## Backend Options

AgentLab/BrowserGym uses these reset environment variables:

```bash
WP_RESET_CONTAINER_PER_TASK=1
WP_RESET_BACKEND=auto
```

`WP_RESET_CONTAINER_PER_TASK` controls whether task setup resets selected
websites. It defaults to enabled. Set it to `0`, `false`, or `no` to reuse the
current site state across tasks.

`WP_RESET_BACKEND` selects the concrete reset backend:

| Value | Meaning |
|---|---|
| `auto` | Default. Use the fastest known safe backend for the site. Most sites use in-place state restore; selected sites use container recreation because it benchmarks faster than their restore script or endpoint. |
| `state`, `http`, `restore`, `app` | Force in-place state restore. This uses an HTTP reset endpoint or a Docker-exec reset script. |
| `container`, `docker` | Force stop/remove/recreate from the seed image. |
| `none`, `noop`, `off` | Skip reset. |

The current `auto` policy is:

1. If the site is in `CONTAINER_PREFERRED_RESET_SITES`, recreate the container.
2. Otherwise, if the site has a state restore contract, use state restore.
3. Otherwise, recreate the container.

The current container-preferred set is:

```text
acidwave, immich, metabase, penpot, peppermint, thunderbird, x-lite
```

These sites still have in-place restore contracts. They are routed to container
recreation by default because local measurements showed container boot is
faster or comparable to their reset path.

## Mattermost Calls networking

The shared runtime enables the bundled Calls plugin and publishes container port
8443 over both UDP and TCP. Calls media connects directly to the container's
published host port; HTTP and WebSocket traffic continue through the configured
website URL and nginx proxy. Media bindings are therefore present in both
subdomain and direct-port URL modes.

By default, Calls advertises `127.0.0.1:8443` for a browser running on the Docker
host, including Docker Desktop. BrowserGym assigns each worker a different
media port: worker `w3` uses 8446 for both protocols. Reassignment to another
worker slot also moves its media port. Reset fails on an occupied Mattermost
port instead of removing an unrelated container.

Set `WP_MATTERMOST_CALLS_HOST_PORT` to change the base media port before starting
a run. For a browser on another machine, also set `WP_MATTERMOST_CALLS_HOST` to
the Docker host address reachable by that browser and provide access to the
worker media ports. Keep the existing HTTPS website/proxy configuration for
remote browsers; changing the media address does not change HTTP routing.
For example:

```bash
WP_MATTERMOST_CALLS_HOST=192.0.2.20
WP_MATTERMOST_CALLS_HOST_PORT=18443
```

Native `MM_CALLS_ICE_HOST_OVERRIDE` and `MM_CALLS_ICE_HOST_PORT_OVERRIDE`
environment values take precedence for advertising an address behind additional
NAT or routing. These explicit values are used as supplied; advanced deployments
must route each worker's advertised port to its distinct published port.
Explicit `MM_CALLS_UDP_SERVER_ADDRESS` and `MM_CALLS_TCP_SERVER_ADDRESS` bind
addresses are forwarded unchanged; otherwise the image selects its container
network interface. See the
[Mattermost Calls deployment guide](https://docs.mattermost.com/deployment-guide/calls/calls-deployment-guide).

The call task can join muted when no microphone is available. The adapters do
not grant microphone access or enable real audio capture automatically.

## State Restore Methods

Core has two in-place restore mechanisms.

HTTP reset endpoints are used when the running website exposes a reset route:

| Site | Endpoint contract | Current `auto` backend |
|---|---|---|
| `acidwave` | `POST /api/reset` | container |
| `flight-search` | `POST /api/reset` | state |
| `jobportal` | `POST /api/reset` | state |
| `minerva-lite` | `GET /reset` | state |
| `mydrive` | `POST /api/dev/reset` | state |
| `notion` | `POST /api/reset` | state |
| `password-manager` | `POST /api/reset` | state |
| `travelmap` | `POST /api/reset`, then `POST /reset` fallback | state |
| `x-lite` | `GET /reset` | container |

Docker-exec restore is used when reset code is packaged inside the running
container:

| Site | Docker-exec contract | Current `auto` backend |
|---|---|---|
| `erp-next` | `bash /usr/local/bin/webarena-reset-state` | state |
| `firefly` | `bash /usr/local/bin/webarena-reset-state` | state |
| `immich` | `bash /usr/local/bin/webarena-reset-state` | container |
| `mattermost` | `bash /usr/local/bin/webarena-reset-state` | state |
| `metabase` | `bash /usr/local/bin/webarena-reset-state` | container |
| `nextcloud` | `bash /usr/local/bin/webarena-reset-state` | state |
| `penpot` | `bash -lc 'bash /usr/local/bin/webarena-reset-state'` | container |
| `peppermint` | `bash /usr/local/bin/webarena-reset-state` | container |
| `pipedrive` | `node scripts/restore-seed-if-empty.js` in `/app` | state |
| `thunderbird` | `bash /usr/local/bin/webarena-reset-state` | container |
| `yt-lite` | inline Python seed restore in `/app` | state |

Docker-exec restore needs Docker access on the machine hosting the environment
containers.

## Package Support

The package-level `reset_site(site)` API supports these 20 sites:

```text
acidwave, erp-next, firefly, flight-search, immich, jobportal, mattermost,
metabase, minerva-lite, mydrive, nextcloud, notion, password-manager, penpot,
peppermint, pipedrive, thunderbird, travelmap, x-lite, yt-lite
```

## Current Auto Backend By Website

| Website | Current `auto` backend | State restore contract | Notes |
|---|---|---|---|
| `acidwave` | container | HTTP endpoint | Container path is preferred by policy. |
| `erp-next` | state | Docker exec | Uses packaged seed snapshot restore. |
| `firefly` | state | Docker exec | Uses packaged reset script. |
| `flight-search` | state | HTTP endpoint | Fast reset endpoint. |
| `immich` | container | Docker exec | Container path is preferred by policy. |
| `jobportal` | state | HTTP endpoint | Reset endpoint plus readiness probe. |
| `mattermost` | state | Docker exec | Container start is much slower than reset. |
| `metabase` | container | Docker exec | Container path is preferred by policy. |
| `minerva-lite` | state | HTTP endpoint | Fast reset endpoint. |
| `mydrive` | state | HTTP endpoint | Reset endpoint is much faster than start. |
| `nextcloud` | state | Docker exec | Uses packaged reset snapshot. |
| `notion` | state | HTTP endpoint | Fast reset endpoint. |
| `password-manager` | state | HTTP endpoint | Near-instant reset endpoint. |
| `penpot` | container | Docker exec | Container path is preferred by policy. |
| `peppermint` | container | Docker exec | Container path is preferred by policy. |
| `pipedrive` | state | Docker exec | Node seed restore. |
| `thunderbird` | container | Docker exec | Container path is preferred by policy. |
| `travelmap` | state | HTTP endpoint | Endpoint fallback chain. |
| `x-lite` | container | HTTP endpoint | Container path is preferred by policy. |
| `yt-lite` | state | Docker exec | Supported but not included in the timing table below. |

## Reset Effects By Website

Container recreation stops and removes the current website container, then
starts a new container from the seed image. That discards all changes in the
container writable layer, including server-side databases and uploaded files
stored inside the container. It does not clear browser cookies, local storage,
or an already-open browser context; task setup handles browser login separately
when a task requires a specific user.

Container removal also deletes attached anonymous Docker volumes, including
volumes declared by the image, so repeated resets do not leave those volumes
behind. This applies to stop, reset, replacement, and port-conflict cleanup, as
well as reverse-proxy replacement. Named volumes and host bind mounts are
preserved by Docker's container-removal contract; no global volume pruning is
performed. Previously orphaned volumes are not cleaned up retroactively.

For sites whose current `auto` backend is `container`, the container recreation
behavior above is the default reset. Some of those sites still expose a state
restore contract, which can be forced with `WP_RESET_BACKEND=state`.

| Website | Current `auto` effect | Forced state restore effect, when available |
|---|---|---|
| `acidwave` | Recreates the container from the seed image. | `POST /api/reset` truncates `user_favorites`, `playlist_songs`, `playlists`, `songs`, `albums`, and `artists` with identity reset, then reruns the seed SQL. |
| `erp-next` | Runs the packaged Docker-exec restore script. | Restores site public/private files, cleanly stops MariaDB, restores its baked physical data snapshot, restarts MariaDB, and clears the dedicated Redis cache/queues. Older images without a physical snapshot fall back to importing the SQL dump. |
| `firefly` | Runs the packaged Docker-exec restore script. | Stops MariaDB, replaces the MySQL data directory with the seed snapshot, restarts MariaDB, and fixes application storage ownership. |
| `flight-search` | Calls the HTTP reset endpoint. | Clears the in-memory confirmed-bookings list. The deterministic flight search and pricing data is not rebuilt because it is generated from seed data at runtime. |
| `immich` | Recreates the container from the seed image. | The forced Docker-exec script stops Immich services, Redis, and PostgreSQL; clears PostgreSQL data, uploads, and cache directories; reinitializes PostgreSQL, imports the seed dump, restores upload data and ML cache, then restarts services. |
| `jobportal` | Calls the HTTP reset endpoint. | Restores the complete SQLite seed snapshot baked into the image, including its expanded dataset. Source checkouts without a snapshot rebuild the demo and imported seed data. |
| `mattermost` | Runs the packaged Docker-exec restore script. | Stops PostgreSQL, restores the PostgreSQL data directory and Mattermost file data from snapshots, then restarts PostgreSQL. |
| `metabase` | Recreates the container from the seed image. | The forced Docker-exec script stops Metabase and PostgreSQL, restores the sample PostgreSQL data and Metabase application database snapshots, removes stale H2 lock/trace files, then restarts the services. |
| `minerva-lite` | Calls the HTTP reset endpoint. | Deletes the SQLite database file, recreates the schema, and reseeds accounts, profiles, programs, courses, and enrolments. |
| `mydrive` | Calls the HTTP reset endpoint. | Recreates the seeded agent users. For those users it deletes share, file, folder, and user database rows, then recreates users and uploads seed files from `Media/` into S3 and the database. The endpoint does not explicitly purge orphaned S3 objects. |
| `nextcloud` | Runs the packaged Docker-exec restore script. | Restores the seeded `config` and `data` directories with `rsync --delete`, uses the baked `custom_apps` snapshot through a symlink, and updates runtime URL/trusted-domain settings directly in the Nextcloud config. |
| `notion` | Calls the HTTP reset endpoint. | Deletes all Prisma application tables, including users, workspaces, pages, blocks, databases, comments, attachment metadata, and share links, then recreates the deterministic seed workspace. Physical files under the upload directory are not deleted. |
| `password-manager` | Calls the HTTP reset endpoint. | Clears the in-memory vault store and recreates the seed user `agent1` with the seeded vault items. |
| `penpot` | Recreates the container from the seed image. | The forced Docker-exec script stops Penpot services, reinitializes PostgreSQL from the seed database dump, restores asset files when present, then restarts PostgreSQL, Redis, backend, exporter, and nginx. |
| `peppermint` | Recreates the container from the seed image. | The forced Docker-exec script stops Peppermint services, reinitializes PostgreSQL from the seed database dump, then restarts PostgreSQL, the API, and the client. |
| `pipedrive` | Runs the packaged Docker-exec restore script. | Force-copies the seed SQLite CRM database over the live database and removes SQLite WAL/SHM sidecar files. |
| `thunderbird` | Recreates the container from the seed image. | The forced Docker-exec script stops mail and web services, restores the `/var/vmail` maildir snapshot, deletes the Roundcube SQLite database plus temp/session data, then restarts fake SMTP, Dovecot, PHP-FPM, and nginx. |
| `travelmap` | Calls the HTTP reset endpoint. | Restores the complete SQLite seed snapshot using the SQLite backup API. Source checkouts without a snapshot rebuild the catalog, users, listings, reviews, bookings, wishlists, message threads, tasks, and availability data. |
| `x-lite` | Recreates the container from the seed image. | `GET /reset` deletes the SQLite database file and reinitializes it from the schema plus `data/seed.json`. |
| `yt-lite` | Runs an inline Docker-exec Python restore. | Deletes the SQLite database and WAL/SHM files, removes uploaded videos and thumbnails that are not part of the seed dataset, then reruns `init_db()`. |

## Updating Website Images

Application fixes, seed data, and reset fast paths are image contents. Checking
out newer orchestration code does not update an installed image or an existing
container. For a published image update, pull the selected site's image and
then recreate its container. For example, starting at the repository root:

```bash
cd webarena-pro-bgym
uv run webarena-pro env pull notion
uv run webarena-pro env restart notion
```

`env pull` refreshes the local registry tag; running containers keep their
original image. `env start` can reuse an existing container, so it does not
apply an image update by itself. `env restart` stops, removes, and recreates
the targeted container from the local image, discarding its mutable state.
A literal `docker restart` keeps the same container and image.

Run the upgrade when no task is using that site, with the same namespace and
URL settings used to create it. The commands target the container selected by
those settings; they do not replace every isolated worker's container. See
[published evaluator image releases](evaluator-images.md) for the recorded
tags, immutable digests, and compatibility checks.

When preparing your own dataset image, build the current website Dockerfile
or apply the appropriate
[runtime image target](https://github.com/McGill-NLP/webarena-pro/blob/main/websites/runtime/README.md)
to the intended populated image.
Keep the complete seed data while moving its import to build time.

TravelMap and JobPortal bake a complete SQLite snapshot. MyDrive bakes its
PostgreSQL and MinIO seed. These images skip repeated initialization on start
and retain the same reset semantics for agent episodes.

Recheck the actual local image with the isolated benchmark command, from the
repository root:

```bash
uv run --project webarena-pro-core python webarena-pro-core/scripts/benchmark_resets.py all \
  --resets 2 --output /tmp/website-reset-report.jsonl
```

## Timing Methodology

The timing runs measured the task reset/bootstrap helpers used by CUBE and
AgentLab/BrowserGym with `WP_RESET_BACKEND=auto`.

Definitions:

| Metric | Meaning |
|---|---|
| Start | The site container was absent. The framework helper was timed until it returned ready. |
| Reset | The same framework helper was called again while the container was already running. |

Images were already local before timing. The runner did not explicitly time
`docker pull`. These numbers are local-machine measurements, so use them as
policy evidence and regression baselines rather than portable performance
guarantees.

Source reports:

```text
startup-reports/start-reset-cube-agentlab-20260623-130026.md
startup-reports/start-reset-preferred-container-20260623-132444.md
startup-reports/start-reset-preferred-container-extra-20260623-132732.md
```

The main 20260623-130026 run measured all core websites except `immich` and
`yt-lite`. Later reports remeasured the sites moved to the container-preferred
policy. The table below reflects the current policy by using those later
measurements for container-preferred sites. The `nextcloud` row uses a local
core remeasurement from 2026-07-20 after moving API seeding to build time,
dropping the inherited `/var/www/html` Docker volume, and switching reset-time
URL configuration away from repeated `occ` calls.

## Historical Timing Results

The historical Penpot measurements below only waited for its static frontend.
They did not measure usable backend readiness and are not a backend startup
target. Current core and CLI probes wait for the backend profile endpoint.


| Site | Auto backend | Cube start | Cube reset | AgentLab start | AgentLab reset |
|---|---|---:|---:|---:|---:|
| `password-manager` | state | 1.78s | 0.01s | 1.75s | 0.00s |
| `nextcloud` | state | 4.64s | 1.30s | 4.64s | 1.30s |
| `flight-search` | state | 1.82s | 0.00s | 1.82s | 0.00s |
| `firefly` | state | 19.92s | 5.81s | 21.38s | 5.79s |
| `travelmap` | state | 1.88s | 3.16s | 1.91s | 3.09s |
| `jobportal` | state | 7.80s | 4.42s | 7.78s | 4.47s |
| `thunderbird` | container | 1.87s | 1.97s | 1.86s | 2.11s |
| `mattermost` | state | 21.38s | 1.47s | 21.36s | 1.55s |
| `metabase` | container | 24.61s | 20.27s | 20.19s | 21.67s |
| `mydrive` | state | 20.19s | 0.63s | 21.66s | 0.63s |
| `notion` | state | 3.63s | 0.75s | 3.64s | 0.79s |
| `x-lite` | container | 1.77s | 1.90s | 1.85s | 1.92s |
| `minerva-lite` | state | 1.76s | 1.42s | 1.78s | 1.44s |
| `acidwave` | container | 1.81s | 2.02s | 1.86s | 1.97s |
| `peppermint` | container | 4.95s | 3.50s | 3.26s | 3.41s |
| `penpot` | container | 1.77s | 1.88s | 1.72s | 1.85s |
| `pipedrive` | state | 1.86s | 0.08s | 1.90s | 0.10s |
| `erp-next` | state | 4.99s | 5.61s | 6.04s | 6.59s |

`yt-lite` is omitted from this timing table because it was excluded from the
timing run. A later Immich measurement with the preloaded image and
container-preferred reset measured `12.04s` from reset call to
`/api/server/ping` readiness.

## Interpreting The Results

State restore is usually best when the reset path is a small HTTP endpoint or
when the container has expensive startup. Good examples are `password-manager`,
`flight-search`, `mattermost`, `mydrive`, `notion`, and `pipedrive`.

`nextcloud` is state-restore preferred. Its image is preseeded at build time,
does not inherit the upstream `/var/www/html` Docker volume, and symlinks the
large `custom_apps` tree from the baked reset snapshot. Startup avoids the
runtime API seed and Docker's volume-copy tax, while task-to-task reset only
rsyncs mutable `config` and `data`.

Container recreation is better when the app image starts faster than the
in-place reset script. This is why `immich`, `penpot`, `peppermint`,
`thunderbird`, and `x-lite` are container-preferred. `metabase` is still around
20 seconds in the historical run, but this avoids the
even slower state-reset path observed in the original timing run.

`acidwave` is effectively a tie in the measured runs. It currently remains in
the container-preferred set so auto behavior is consistent with the latest
measurement pass.

## URL Targeting

For HTTP reset, core resolves the target URL from the same URL settings used by
normal tasks:

- Explicit `WP_<SITE>_URL`, such as `WP_NEXTCLOUD_URL`.
- Subdomain proxy mode, using a local proxy URL plus the appropriate `Host`
  header.
- Direct port mode from `WP_URL_MODE=port` and `WP_<SITE>_HOST_PORT`.

Reset tokens can be supplied per site:

```bash
WP_TRAVELMAP_RESET_TOKEN=secret
```

or shared across sites:

```bash
WP_RESET_TOKEN=secret
```

Site-specific tokens take precedence over the shared token.

## Worker Bootstrap

AgentLab/BrowserGym can run tasks in isolated worker slots. The first
task on a fresh worker may point at a worker-specific container that does not
exist yet. When in-place restore fails with an availability-style error, core
bootstraps that worker by recreating the container once. Later tasks on the
same worker use the backend selected by `WP_RESET_BACKEND`.

## Diagnosing Reset Readiness

### Concurrent lifecycle operations

Core serializes changes to each container name and limits heavy lifecycle and
state-restore work across processes. The defaults are:

| Variable | Default | Purpose |
|---|---|---|
| `WP_DOCKER_TIMEOUT_SECONDS` | `300` | Docker client request timeout in seconds. |
| `WP_DOCKER_LIFECYCLE_SLOTS` | `4` | Maximum concurrent heavy lifecycle/restore operations. |
| `WP_DOCKER_LOCK_TIMEOUT_SECONDS` | `1200` | Maximum wait to acquire a runtime lock, in seconds. |
| `WP_RUNTIME_LOCK_DIR` | A user-scoped directory under the system temporary directory | Shared lock-file location. |

Workers sharing a Docker runtime must use the same lock directory and slot
count. Nested calls reuse their permit, and the operating system releases
locks when a worker exits. Do not delete lock files while workers are running.
Readiness polling runs outside the lifecycle permit pool. Container creation,
start, and removal reconcile expected timeout/removal/name-conflict races with
up to eight attempts and a backoff capped at four seconds. Persistent failures
still raise diagnostic errors. These limits are configurable for the host's
capacity and do not guarantee a particular reset duration.

Nginx refreshes are serialized across callers. Discovery excludes stopped,
paused, restarting, and network-detached containers. Configuration validation
and bounded reload retries expose persistent configuration errors rather than
silently suppressing them. Website upstream names resolve at request time
through Docker's embedded DNS (`127.0.0.11`, five-second cache validity and
resolver timeout), so a container disappearing during reload does not prevent
the proxy from applying its configuration. Requests to an unavailable backend
can still fail until it is ready. Custom proxy names have separate configuration
directories; the default proxy retains its existing configuration mount.

### Readiness evidence

The task's `sites` list determines which sites BrowserGym resets and awaits.
The first entry is the primary website used to label and start the task; it
does not imply that the task uses only that website. For example, Test task
`111` is labelled Mattermost but declares `mattermost`, `firefly`,
`flight-search`, and `x-lite`: its goal includes counting DEN–LAS flights and
posting the combined findings. This list is present in both the reported
`460e02fd` revision and current task configuration. Waiting for Flight Search
is therefore required for that task.

Prewarming prepares the next task's declared sites on a separate runtime
slot. Task setup rechecks those sites after consuming a matching prewarm
marker; a failed prewarm or a stale marker takes the synchronous reset path.
Other sites allocated in the worker environment are not implicitly included.

Core readiness logs distinguish `state_restore`, `container_recreate`,
`http_readiness`, and `reset_snapshot`, with elapsed phase times. HTTP timeout
errors include the expected container and image, the URL and proxy `Host`
header, the required response sentinel, attempt count, and last failure.
Flight Search checks `GET /api/health` for `"status":"ok"`; that backend
endpoint reads the route graph after startup initializes it and is exempt
from the passkey middleware. A static HTML response alone is insufficient.
Snapshot failures propagate as their own phase instead of being retried and
reported as HTTP failures. Polling uses a monotonic clock and caps each HTTP
request timeout and retry sleep by the remaining HTTP wait budget.

For a timeout, use the container name from that error to inspect the same
runtime slot (substitute the reported name):

```bash
docker inspect flight-search-w3 --format '{{json .State}}'
docker logs --tail 100 flight-search-w3
```

Check its exit status, OOM status, startup errors, and the probe URL/Host
against the slot's assigned URL. Retain these details and phase timings when
reporting a failure. The task 111 timeout reported in
[issue #52](https://github.com/webarena-pro/webarena-pro/issues/52) has not been
reproduced by the regression tests: they verify task selection, readiness
responses, and reset/prewarm transitions with mocked services. They do not
establish the cause of the original 240-second timeout under six workers.
