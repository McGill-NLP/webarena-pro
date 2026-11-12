# Thunderbird Webmail (WebArena-Pro)

Roundcube, Dovecot, and a local-only SMTP simulator in one container. The seed
combines the existing WebArena task fixtures with 5,000 anonymized messages
sampled from one Enron custodian mailbox.

## Quick start

```bash
docker build -t thunderbird-webarena websites/thunderbird
docker run -d --name thunderbird -p 8080:80 thunderbird-webarena
```

Webmail is available at <http://localhost:8080>. Reset it by removing and
recreating the container; all seed state is baked into the image.

## Login accounts

All accounts use the password `User@Secure123`.

| Name | Email | Role |
|---|---|---|
| Alice Chen | `alice@techcorp.local` | Legal Counsel / primary corpus user |
| Bob Martin | `bob@techcorp.local` | Project Manager |
| Carol White | `carol@techcorp.local` | UX Designer |
| David Kim | `david@techcorp.local` | QA Engineer |

The existing four accounts remain valid so benchmark tasks do not lose their
login credentials. Sara Shackleton's source mailbox is anonymized as Alice.

On narrow browser windows, opened messages include visible **Reply** and
**Reply all** buttons below the sender header. This avoids hiding the only
reply controls inside Roundcube's responsive three-dot menu.

When an opened message belongs to a conversation, the reader combines its
Inbox and Sent members into a root-and-replies tree similar to x-lite. Each
card remains a real IMAP email with its own **Open email**, **Reply**, and
**Reply all** actions. The Docker build compiles all 5,000 messages into a
thread index, while RFC `References` and `In-Reply-To` searches add replies
sent after startup to the same view.

## Filters

Settings → Filters connects to a local ManageSieve service. Rules are stored
per account and applied by Dovecot when the local SMTP simulator delivers new
mail. Filter scripts are cleared by the normal container reset. External
recipients still remain simulated, with no internet mail relay.

Validate against a disposable container (the live checks create test filters
and mail):

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
docker exec -i thunderbird-test python3 < tests/smoke_sieve.py
# Requires Python Playwright and Chromium:
python3 tests/smoke_webmail.py --url http://localhost:8080
```

## Corpus seed

The bundled seed assets contain:

- exactly 5,000 sampled corpus messages in Alice's Inbox and Sent folders;
- 1,525 inferred reply links (`In-Reply-To` and `References`) for threading;
- 3,475 compiled root conversations, including 752 multi-message threads;
- 1,311 replies cleaned of pasted parent-message history so each thread is
  displayed as separate messages instead of repeated `Original Message` blocks;
- messages shifted to the recent range May 2025 through July 2026;
- 250 unread recent Inbox messages plus realistic seen/answered flags;
- every generated correspondent address saved in Alice's Roundcube contacts;
- the original 22 small task-fixture scenarios for cross-account benchmarks.

The source is the `shackleton-s` mailbox from the CMU CALO Enron Maildir,
selected using EnronData.org's canonical custodian report. The build script:

1. excludes the duplicate `all_documents` folder and semantically deduplicates
   the remaining messages;
2. takes the newest deterministic 5,000-message slice;
3. replaces header and body email addresses with stable `techcorp.local`
   addresses, including malformed Lotus Notes address forms;
4. replaces observed employee names and quoted-header name variants with
   stable fictional identities;
5. removes exported Outlook/Lotus quoted-history blocks from replies;
6. shifts message dates while preserving ordering and thread relationships.

The original corpus is not required during Docker builds. Only the compressed,
anonymized sample in `seed_assets/` is copied into the image.

## Task compatibility audit

The address book contains 4,510 generated corpus correspondents. Bob and Carol
remain absent from the initial address book because three benchmark tasks ask
Alice to create those contacts; all four original users remain available as
login accounts and mail identities.

Run the read-only seed/config audit after changing fixtures, contacts, or task
rubrics:

```bash
python3 websites/thunderbird/scripts/audit_task_feasibility.py
```

It checks the corpus and contact counts, every task-specific unread/read/folder
fixture, the latest-correspondent ground truth, all 12 native task records, all
24 benchmark tasks that use Thunderbird, and semantic parity between regular
and anonymous config copies.

## Rebuilding the derived assets

Download the CALO archive linked by EnronData.org, extract the selected
custodian, then run:

```bash
python3 websites/thunderbird/scripts/build_enron_seed.py \
  /path/to/maildir/shackleton-s \
  websites/thunderbird/seed_assets
```

The generator uses only Python's standard library and writes deterministic
JSON/JSONL-gzip assets.

## Data attribution

Source documentation: [EnronData.org CALO Enron Email Dataset](http://enrondata.org/en/latest/data/calo-enron-email-dataset/)
and the [CMU Enron Email Dataset](https://www.cs.cmu.edu/~enron/). The container
also carries source and custodian attribution labels.
