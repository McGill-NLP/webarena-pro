---
title: Xxlite
emoji: 🐦
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Xxlite

A benchmark-friendly X/Twitter-like environment with profile, follow, bookmarks, chat, explore, notifications, deterministic seed data, and a reset endpoint.

## Data summary

X-lite now uses a hybrid seed: the original deterministic benchmark fixtures are kept for task correctness, and a larger real-world social feed is added at Docker build time. The imported feed comes from a compact cache derived from `Roronotalt/bluesky-ten-million`; it contains 2,000 simple-random-sampled root posts with no image or video media, plus every available descendant reply for those selected roots.

The build process expands that compact cache into local X-lite users, posts, reply trees, views, likes, reposts, and bookmarks. External usernames are replaced with deterministic local handles, original post timestamps and reply parent relationships are preserved, and root posts keep full descendant counts for realistic reply totals and feed ranking.

Task integrity is preserved by keeping `data/seed.json` as the canonical task fixture and generating a separate `data/seed.generated.json` during image build. The importer retains task-critical synthetic accounts, posts, follows, messages, reactions, quote posts, and bookmarks, while pruning only nonessential filler so existing intents, hints, and rubrics remain feasible.

## Seeded accounts

All seeded users use the same password:

- Password: password123

High-signal accounts for benchmark tasks:

- Username: techvalueinvestor
	- Display name: Maya Chen
	- Profile: Finance investor focused on tech markets
- Username: airescientist
	- Display name: Dr. Arjun Rao
	- Profile: AI research scientist

Additional seeded pages:

- 40 page-style accounts across science, tech, and politics topics
- These are suitable for feed, search, follow, like, retweet, quote, and bookmark tasks

## Seeded content snapshot

X-lite combines a small deterministic task seed with a larger build-time social feed import. `data/seed.json` remains the canonical source for benchmark-critical accounts, posts, follows, messages, likes, bookmarks, reposts, and quote posts. The larger feed is generated during the Docker image build by `scripts/build_real_world_seed.py`, which writes `data/seed.generated.json`. At runtime the app prefers `data/seed.generated.json` when it exists and falls back to `data/seed.json` otherwise.

The build-time import uses a compact cache derived from `Roronotalt/bluesky-ten-million` (`https://huggingface.co/datasets/Roronotalt/bluesky-ten-million`, MIT license). Instead of rescanning the full 10M-row dataset during every image build, the repo stores:

- `data/bluesky_srs_2000_roots.txt`: the pinned 2,000 sampled root post URIs.
- `data/bluesky_srs_2000_trees.jsonl.gz`: the sampled roots plus their full descendant reply trees.

The current cache contains 55,444 Bluesky rows: 2,000 simple-random-sampled root posts with no image or video media, plus 53,444 descendant replies. The SRS is taken after filtering the root pool to original posts that have text and do not require image or video assets. Links are allowed, but root posts with image/video embeds are excluded so the UI does not depend on unavailable media files. Once the 2,000 roots are selected, the importer brings in every available descendant row for those roots with no reply-depth cap. Replies preserve their immediate parent relationships, so replies to replies render as threaded conversations rather than flat comment lists. Original source timestamps are preserved.

The data flow is:

1. Start from the cached list of selected root URIs.
2. Read the compact tree cache and group each imported row under its selected root.
3. Create a local X-lite user for every imported author.
4. Insert root posts and replies into the same `tweets` table used by normal app content.
5. Store imported reply totals on root posts in `source_reply_count`.
6. Deterministically sample views, likes, reposts, and bookmarks from each post's reply volume so high-discussion posts tend to rank higher without changing the selected sample.
7. Write the final merged seed to `data/seed.generated.json`.

During import, each external author is mapped to a deterministic local X-lite account. Public usernames and display names are generated locally so the app does not expose source handles directly, while internal source IDs remain stable enough for deterministic rebuilds. X-lite stores actual per-user interaction rows for likes, reposts, and bookmarks rather than only aggregate counters. Root posts keep their imported descendant totals in `source_reply_count`; views and engagement are then deterministically sampled from those counts so the home feed has realistic ranking pressure without changing the underlying reply tree. The generated seed is ignored by git; the repository keeps the compact input cache and rebuild scripts, while the large expanded JSON/database artifacts are produced during image build.

## Task integrity

The benchmark tasks still depend on deterministic seeded content. To preserve those tasks while adding the larger feed:

- The task seed in `data/seed.json` is not rewritten by the import process.
- `scripts/build_real_world_seed.py` starts from the original deterministic seed, then merges the imported feed into a generated copy.
- Task-relevant synthetic posts, profiles, follows, messages, reactions, quote posts, and bookmarks are preserved so existing intents, hints, and rubrics remain feasible.
- Nonessential synthetic feed filler is pruned, preventing the imported feed from burying task-critical posts while still leaving a realistic timeline.
- Imported replies are not treated as top-level home-feed posts. The main feed shows roots and quote posts first, while reply trees remain available from each post detail page.
- Mentioned accounts are created deterministically during seeding, so posts containing `@username` links remain navigable.
- Reply counts shown in the UI use full descendant totals for imported roots, so task-visible conversation metrics stay consistent with the imported trees.
- The generated database is built into the Docker image with `scripts/build_seed_database.py`, which keeps container startup fast and deterministic.
- The `/reset` endpoint rebuilds from the generated seed when present, so tests start from the same data state after each reset.

The result is a larger, more realistic social feed for browsing tasks while the original task fixtures remain present and stable.

Example build with Kaggle credentials:

```bash
docker build \
	--secret id=kaggle_json,src="$HOME/.kaggle/kaggle.json" \
	-t x-lite-real-seed .
```

## Reset data

- Endpoint: GET /reset
- Effect: Removes the local sqlite database and rebuilds from the generated seed when present, otherwise `data/seed.json`

## Bounded message browsing

`/messages` renders at most 20 existing conversations, 20 group chats, 20 new-DM recipients, and 20 group-member candidates per page. Previously the group creation form rendered every account as a checkbox, including all imported feed authors. Search finds names, usernames (with or without `@`), and conversation message text; pagination keeps every result reachable. The group member picker searches separately and preserves checked members, group name, and initial message when searching or changing pages. Selected members remain visible and can be unchecked; selection is not restricted to one page. These controls use ordinary links and forms and remain available in the accessibility tree without client-side JavaScript.

Direct and group conversations display the latest 50 messages in chronological order. Older/newer links and conversation search expose the full history. Sending a message returns to the latest page. Opening a direct conversation retains the existing read-on-open behavior. No seeded users, messages, or task fixtures are removed.

Run regression tests from this directory:

```bash
python -m unittest discover -s tests -v
# Include real Chromium form submissions (requires Playwright and its Chromium):
X_LITE_BROWSER_TESTS=1 python -m unittest discover -s tests -v
```

The `test-webarena-pro-bgym.yml` workflow runs both server and browser tests as
steps in the BrowserGym check, reusing its Playwright 1.44 Chromium installation.
They cover bounded lists, later-page recipients/conversations/groups, search,
older message access, reply redirects, group privacy, and selecting/removing
members across searches and pages while preserving the draft.

### Observation measurements

Measured locally on macOS with Python 3.12.13, BrowserGym Core 0.14.3, Playwright 1.44.0, Chromium 125.0.6422.26, and a 1280 × 720 viewport. Both versions used the same SQLite database generated from the Docker build's cached Bluesky inputs with the canonical task seed preserved (`X_LITE_PRUNE_ORIGINAL_SEED=0`): 26,654 users and 56,414 tweets. The account was `techvalueinvestor`, visiting `/messages`; Tailwind styles were loaded. “Before” is commit `241acecdc80467dd6ef4c77d9a160d5ee6d914dd`.

| Measurement | Before | After |
| --- | ---: | ---: |
| DOM elements (`document.querySelectorAll('*')`) | 133,476 | 325 |
| BrowserGym element marking | 0.778 s | 0.047 s |
| BrowserGym DOM snapshot | 7.153 s | 0.013 s |
| BrowserGym merged accessibility tree | 94.479 s | 0.023 s |
| Accessibility tree nodes | 293,583 | 649 |

These are single local samples of the actual BrowserGym extraction functions, not a complete Docker benchmark-agent evaluation or a timing guarantee. The resulting DOM size is the deterministic regression target; timings depend on hardware and Chromium. No runner timeout was increased.

To reproduce against an already generated/seeded database, install `browsergym-core==0.14.3` and its Playwright Chromium, then run this script from either checkout using the same database:

```bash
python scripts/benchmark_messages.py --database /path/to/seeded/database.db --output /tmp/messages-after.json
python scripts/benchmark_messages.py --app-dir /path/to/before/websites/x-lite --database /path/to/seeded/database.db --output /tmp/messages-before.json
```

The script does not initialize or reset the database. It signs a local session for the selected account, starts a temporary localhost server, waits for the entire page to finish loading, and runs BrowserGym's `_pre_extract`, `extract_dom_snapshot`, and `extract_merged_axtree` in sequence. Waiting for full page load matters: network-idle alone can occur while the old large page is still being parsed.

## Relevant people

The right sidebar suggests up to three existing accounts that the signed-in user
does not already follow. Each profile link opens that account and each **Follow**
button submits the same follow action used by the Follow page. A successful follow
removes that account from the suggestions. Guests and users who already follow
every other account do not see the widget.

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.
