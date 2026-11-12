# Evaluator image release checks

An application source route does not establish that a published image contains it.
Before releasing MyDrive, YT-lite, Notion or Travelmap images, run the following
compatibility gate on the image that will actually be deployed. It is a read-only
check; it does not create, reset or stop containers.

1. Build the site's Dockerfile from the release revision. The Dockerfiles assert
   that `/api/eval/state` is registered or compiled into the application. Use a
   new local tag; do not overwrite an image used by running workers. For
   YT-lite, also require every seeded video and thumbnail to be present; a
   successful downloader exit alone does not prove that assets were fetched.
2. Start a dedicated, seeded container with a fresh `WP_EVAL_TOKEN`, bounded CPU
   and memory, and a random loopback host port. Use a fresh volume if the site
   requires one. Keep the token out of agent browser state and command output.
3. Run the gate from the checkout with Core's evaluation dependencies available:

   ```bash
   cd webarena-pro-core
   uv run --locked --group dev python scripts/check_eval_endpoints.py \
     --site mydrive=http://127.0.0.1:32768 \
     --image mydrive=sha256:<local-image-ID> \
     --output /tmp/mydrive-evaluator-gate.json
   ```

   Set `WP_EVAL_TOKEN` in the command environment to the same value as the
   dedicated container. Replace the example port and image ID with values from
   `docker port` and `docker image inspect`. Multiple `--site` / `--image` pairs
   can check the four sites together when the test containers use one token.
   Running without these options prints the current contract inventory only.
4. Require exit status zero before releasing. After publication, resolve and pull
   the immutable platform digest, start another isolated container from that
   reference and repeat the gate. Record the digest, source revision and report;
   a successful source build alone does not verify the registry artifact.
5. Remove only the containers, volumes and networks created for these checks.

The gate requires HTTP 403 for missing and incorrect tokens, HTTP 200 for the
correct token, and the tables and row fields consumed by the evaluator. It checks
seed data, nested Notion database shapes, and readable content for small active
MyDrive text files. It executes every active Test and Dev predicate for these APIs
against the response and a positive deterministic seed probe. Incomplete tasks
may correctly fail their predicates on fresh seed data; HTTP errors, missing
schemas, unsupported predicates and exceptions fail the gate. It never calls an
LLM judge. Reports contain no token or backend response body.

## Published releases, 2026-11-05

YT-lite, Notion, and Travelmap were built from clean current-main revision
`eeab587b0420976f43ff7f8348d324c76bbd50ee` and published as `latest` and
`main-eeab587b-20261105`. These releases supersede the failing image digests in
the October audit below. Evidence is recorded in
[issue #80](https://github.com/webarena-pro/webarena-pro/issues/80).

| Image | Platform | Immutable platform manifest |
| --- | --- | --- |
| `webarenapro/yt-lite` | `linux/amd64` | `sha256:fb976da6f903f18ed9dee3a9f81e91f5513da4ebce5165899f53bdee63515a78` |
| `webarenapro/notion` | `linux/amd64` | `sha256:b174f824cfa2550c4e75c7ac13187f5e6d8f05bcb8918cbaea87d48a024bc4b4` |
| `webarenapro/travelmap` | `linux/amd64` | `sha256:4be8d8d26e4acff94c1880ac4fd1adfbb6f77f37047e4d2039db084cf36e5e9c` |
| `webarenapro/travelmap` | `linux/arm64` | `sha256:d1fdac742885bbafca7b4596d6ca7abf182491f9eda1304f92381da9ba3227c4` |

All 19 release-gate regression tests passed on GCP.
The authenticated release gate passed against local builds and fresh isolated
seeded containers started from pulled Docker Hub platform digests. Missing and
incorrect tokens returned 403; matching tokens returned 200. Required tables and
populated-row fields passed schema validation. All 166 current Test and Dev
predicates for these sites executed without errors: YT-lite 57, Notion 80, and
Travelmap 29 on each architecture. Positive deterministic seed probes passed.
False task predicates on fresh seed data are expected; this does not claim that
an agent completed every task.

Representative active nodes changed from conclusive failure before the
application action to a Tier 0 pass afterward, with zero judge calls:

- YT-lite 288/r1: sign in as the seeded user and open recipe video fv238.
- Notion 177/r1: create New Commers through the authenticated page API.
- Travelmap 249/r3: sign in as Avery and cancel BKG-2001 through the normal form endpoint.

YT-lite used its complete current-main Dockerfile and fetched all 1,419 videos
and 1,419 thumbnails. Its duration-filter regression passed inside the image;
both task-112 recipe pages and their served video assets were checked. An initial
build with an expired dataset credential returned zero assets without an error.
That image failed the media check and was never published. The full build was
repeated without cache using an existing valid credential.

All builds and live validation ran on GCP. Travelmap arm64 ran under QEMU on the
amd64 host with a recorded 600-second HTTP timeout because its large state
response exceeded the normal timeout under emulation. Authentication, schema,
and predicate assertions were unchanged. Native-ARM performance was not tested.
The task-transition probes above ran on amd64.

The inventory was recomputed from the clean release checkout: 138 Test site-node
contracts / 144 strategies and 20 Dev contracts / 20 strategies, covering 322
predicates across all four sites. MyDrive accounts for the other 156 predicates
and was already released and pull-verified on both architectures on November 4
in [PR #144](https://github.com/webarena-pro/webarena-pro/pull/144). Its latest
index remains `sha256:b7348a91c5802fa5ce2add562e1fcc2de0d8cac55a59935af7ab284c3550ebee`.

All 39 preexisting GCP containers retained their
status, start time, restart count, and image. Test containers and the temporary
ARM emulation registration were removed. Existing deployments were not
recreated; old containers must be recreated after pulling the release.
Previous indexes remain available under the recorded
`before-issue80-20261105-*` rollback tags.


## Inventory and registry audit, 2026-10-27

At source revision `46599d16fb71bcbe5a36196813e075dec571ef33`, the four sites use
`eval_state` exclusively. None uses `eval_state_table`. Cross-site strategies are
counted against their explicit target site rather than the task's primary site.
Some nodes contain multiple probes, so node and strategy counts differ.

| Site | Test tasks | Test nodes | Test strategies | Test predicates | Dev nodes / strategies | Dev predicates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| MyDrive | 13 | 35 | 40 | 140 | 9 / 9 | 16 |
| YT-lite | 34 | 47 | 47 | 50 | 5 / 5 | 7 |
| Notion | 23 | 39 | 40 | 79 | 1 / 1 | 1 |
| Travelmap | 11 | 17 | 17 | 21 | 5 / 5 | 8 |
| Total site contracts | 81 | 138 | 144 | 290 | 20 / 20 | 32 |

These are site-contract totals, not a count of unique cross-site tasks. The gate
recomputes the inventory from all 300 Test and 100 Dev task DAGs on every run.

Fresh Docker Hub pulls of the following Linux/amd64 digests all returned **404**
for `/api/eval/state`, including with a matching `WP_EVAL_TOKEN` and `X-Eval-Token`.
All four routes already existed in source. The reported failure is reproducible
as an outdated released image, not a token rejection. No image was published as
part of this October audit. The November release and fresh-pull verification
recorded above supersede this historical failure.

| Image repository | Verified Linux/amd64 manifest digest |
| --- | --- |
| `webarenapro/mydrive` | `sha256:40f592929827f9b737065a63c504adec068d1c95f95aa4160e93a24e2619c802` |
| `webarenapro/yt-lite` | `sha256:13391484f3188318b88bd7c8050d1d61f687f6a7e392ff9031144a7430ed0a0a` |
| `webarenapro/notion` | `sha256:67b2662cb5b8d03024ada2a574a3402e505370c268cfcbaec1f5f3ec8258b700` |
| `webarenapro/travelmap` | `sha256:527ba8347d52f5922eb0e97b31a8fa29a8bdccf4d09ffe52f60dde2920d32e06` |


MyDrive's build previously fetched an unversioned MinIO binary from `dl.min.io`,
which now returns HTTP 410. The Dockerfile uses the official GitHub asset for
[MinIO RELEASE.2025-09-07T16-13-09Z](https://github.com/minio/minio/releases/tag/RELEASE.2025-09-07T16-13-09Z)
with an architecture-specific pinned SHA256. Both amd64 and arm64 assets were
checked against upstream checksums; only amd64 was executed in this audit.

## Source-image validation

The read-only gate passed against clean source builds of MyDrive, Notion and
Travelmap. For YT-lite, a temporary validation image copied current application,
template and seed source onto the freshly pulled immutable image listed above,
retaining its existing video/thumbnail assets. Its full media-download build was
not run because the gated Hugging Face dataset requires unavailable credentials.
This overlay verifies the source route and schema, not a fresh media rebuild or
newly published image. Runtime source hashes were checked against the checkout;
MyDrive's installed compiled route also matched the current builder output.

| Site | Local validation image ID | Predicates executed |
| --- | --- | ---: |
| MyDrive, clean build | `sha256:cd1b7f92b551808f5aeb4fa91900eb4acf7e8085989307f923a08a14047c7374` | 156 |
| Notion, clean build | `sha256:54f2a38d2f3f60cd95100dee2c9aaa1df51a72f53c23cf63817227cb6f1d57a0` | 80 |
| Travelmap, clean build | `sha256:57c68523f1b4f1fcd980069a9b7c2f16028149214878b8af76b152496f772e21` | 29 |
| YT-lite, source overlay | `sha256:e1aefc1e1335333e17af9bfa30a910a63fd6baacc8fc8cfc0cd446a1f309dce9` | 57 |

All four returned 403 for absent/wrong request tokens and 200 for the matching
token, passed the complete populated-row schema checks and a positive deterministic
seed probe. Executing the 322 task predicates does not mean the fresh seed
completed those tasks; false predicates are expected before an agent acts. Both
YT-lite recipe URLs used by task 112 rendered the intended video title.

The MyDrive image above was built with the pinned download step at source commit
`f704c95`. A subsequent Dockerfile compatibility adjustment derives architecture
from `dpkg --print-architecture` when the legacy Docker-py builder does not supply
`TARGETARCH`. That branch and the explicit amd64/arm64 and unsupported-architecture
branches were checked separately in a capped, isolated container; the full image
was not rebuilt again after that build-only adjustment. Its selected amd64 binary
and all application source remain identical to the tested image.

## Task 112 video link contract

YT-lite serves recipe videos at `/watch/<video_id>` and its templates generate
that path. It does not serve the YouTube-style `/watch?v=<video_id>` path. Task 112
r2 accepts links on the current configured YT-lite origin to `/watch/fv238` or `/watch/fv337`, including
worker hostnames, direct ports, Markdown links, query parameters and fragments.
The structured link check resolves `__YT-LITE__` from the current deployment URL
at evaluation time. Unknown placeholders are inconclusive configuration errors.
It checks actual Markdown destinations or bare URLs and rejects unrelated origins,
the old malformed `watch?/` form, wrong IDs, ID prefixes/suffixes, code, images, and
misleading labels. The check is scoped to current-execution posts by the task user
in the requested Mattermost channel, and
the regression exercises the full r2 DAG without a judge call.
