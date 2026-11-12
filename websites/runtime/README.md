# Restore fast startup after a dataset image update

The runtime targets apply the current startup and reset code to an already
populated website image. They keep the application's existing data and assets.
Use them when an updated dataset was published with an older Dockerfile or
entrypoint.

Runtime targets are available for `erp-next`, `firefly`,
`flight-search`, `immich`, `jobportal`, `mattermost`, `metabase`,
`mydrive`, `password-manager`, `penpot`, and `travelmap`.

From the `websites` directory:

```bash
docker build -f runtime/Dockerfile \
  --target erp-next \
  --build-arg BASE_IMAGE='your-registry/erp-next@sha256:YOUR_PLATFORM_MANIFEST_DIGEST' \
  -t webarenapro/erp-next:fast .
```

Use the digest for the populated image you intend to preserve. A mutable
`latest` tag can resolve to different content at build time. For a local-only
image, push it to a local registry and use the digest reported by `docker push`.
When Docker reports that only one platform was pushed, use the **new pushed
digest**, rather than the local multi-platform index digest.

The ERPNext target performs its existing site setup and seed import once
during the build. Immich preloads its existing database, media, and model-cache
archives. MyDrive initializes its existing PostgreSQL and MinIO seed once.
Firefly and Mattermost package their existing databases as reset snapshots.
Metabase retains its populated H2 database and restores the faster JVM flags.
Metabase and Penpot also bake class-data-sharing caches for their exact JRE and
application JAR. Cache preparation restores the original database/assets before
the build finishes; it does not replace the dataset.

TravelMap snapshots its fully populated SQLite catalog. JobPortal runs the
base image's initializer once and snapshots the resulting database, preserving
that image's dataset imports. Their reset endpoints use SQLite's transactional
backup API to restore the snapshot, avoiding repeated data generation.
Password Manager and Flight Search receive the current reset handlers.

The full source Dockerfiles also preseed ERPNext, Nextcloud, Immich, MyDrive,
TravelMap, and JobPortal. Use those when intentionally rebuilding application
code and datasets together.

## Verify before changing the deployed tag

From the repository root, with the images already local:

```bash
uv run --project webarena-pro-core python webarena-pro-core/scripts/benchmark_resets.py erp-next \
  --image erp-next=webarenapro/erp-next:fast \
  --resets 2 --output /tmp/erp-next-reset-report.jsonl

uv run --project webarena-pro-core python webarena-pro-core/scripts/benchmark_resets.py all \
  --output /tmp/website-reset-report.jsonl
```

The command clears inherited benchmark destinations, uses random container
names and separate loopback ports, refuses port collisions, and removes only
containers created by that audit. It does not pull images. Each report records
the image ID, initial start, episode reset, and literal Docker restart times.
An error is recorded as a failure, not a successful timing.

An episode reset restores seed state. A literal Docker restart retains the
container's writable layer and measures shutdown plus startup; it is a separate
metric from the reset times in the documentation.
