#!/usr/bin/env python3
"""Build topic-focused Mattermost channels from the public Slack XML corpus.

The input is the "Software-related Slack Chats with Disentangled
Conversations" dataset. Message text is copied verbatim. Dataset participant
names are deterministically mapped onto the seeded Engineering users because
the source identities are anonymized and do not exist in Mattermost.

The output is a supplemental seed file: it contains the existing users and
teams, but only the 24 new channels and their imported conversations. This
makes it safe to apply to an already-seeded Mattermost instance without
duplicating the original channel conversations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


MAX_MESSAGE_CHARS = 16_000


@dataclass(frozen=True)
class Topic:
    community: str
    name: str
    display_name: str
    purpose: str
    keywords: tuple[str, ...]


TOPICS = (
    Topic(
        "pythondev",
        "python-web-services",
        "Python Web Services",
        "Python web frameworks, APIs, HTTP services, and server-side development.",
        (
            "django", "flask", "pyramid", "bottle", "wsgi", "asgi", "jinja",
            "web app", "web server", "rest api", "http request", "endpoint",
            "middleware", "gunicorn", "uwsgi", "fastapi", "aiohttp",
        ),
    ),
    Topic(
        "pythondev",
        "python-data-science",
        "Python Data Science",
        "Python data analysis, scientific computing, visualization, and ML.",
        (
            "pandas", "numpy", "scipy", "matplotlib", "dataframe", "jupyter",
            "notebook", "scikit", "sklearn", "tensorflow", "keras", "machine learning",
            "data science", "seaborn", "csv", "array", "plot", "statistics",
        ),
    ),
    Topic(
        "pythondev",
        "python-packaging",
        "Python Packaging & Environments",
        "Python packages, dependency management, installation, and environments.",
        (
            "pip", "virtualenv", "venv", "conda", "setuptools", "requirements.txt",
            "setup.py", "pyproject", "wheel", "pypi", "package", "dependency",
            "dependencies", "install", "poetry", "pipenv", "environment",
        ),
    ),
    Topic(
        "pythondev",
        "python-async-concurrency",
        "Python Async & Concurrency",
        "Async IO, threads, processes, queues, and concurrent Python systems.",
        (
            "asyncio", "async ", "await ", "coroutine", "event loop", "thread",
            "threading", "multiprocessing", "concurrent", "concurrency", "celery",
            "queue", "future", "gevent", "twisted", "parallel",
        ),
    ),
    Topic(
        "pythondev",
        "python-testing",
        "Python Testing",
        "Python test design, fixtures, mocking, coverage, linting, and type checks.",
        (
            "pytest", "unittest", "test case", "test suite", "fixture", "mock",
            "coverage", "tox", "assert", "hypothesis", "mypy", "pylint", "flake8",
            "lint", "type check", "testing", "tests",
        ),
    ),
    Topic(
        "pythondev",
        "python-language",
        "Python Language",
        "Python syntax, object model, functions, modules, and language behavior.",
        (
            "decorator", "generator", "iterator", "comprehension", "metaclass",
            "context manager", "__init__", "class ", "function", "exception",
            "import ", "module", "attribute", "method", "lambda", "dictionary",
            "list ", "tuple", "python",
        ),
    ),
    Topic(
        "clojurians",
        "clojurescript-frontend",
        "ClojureScript Frontend",
        "ClojureScript, browser applications, React wrappers, and frontend tooling.",
        (
            "clojurescript", "cljs", "reagent", "re-frame", "figwheel", "shadow-cljs",
            "shadow cljs", "javascript", "react", "browser", "frontend", "front-end",
            "npm", "webpack", "dom", "node.js", "nodejs",
        ),
    ),
    Topic(
        "clojurians",
        "clojure-web-services",
        "Clojure Web Services",
        "Clojure HTTP servers, web frameworks, routing, APIs, and middleware.",
        (
            "ring", "compojure", "luminus", "pedestal", "http", "web server",
            "web app", "request", "response", "middleware", "route", "router",
            "servlet", "endpoint", "rest api", "reitit", "aleph",
        ),
    ),
    Topic(
        "clojurians",
        "clojure-data-systems",
        "Clojure Data Systems",
        "Databases, queries, schemas, serialization, and data processing in Clojure.",
        (
            "datomic", "database", "postgres", "sql", "jdbc", "query", "datalog",
            "schema", "transaction", "datascript", "mongo", "redis", "json", "edn",
            "transit", "dataset", "data ",
        ),
    ),
    Topic(
        "clojurians",
        "clojure-build-tools",
        "Clojure Build Tools",
        "Clojure dependencies, builds, packaging, classpaths, and project tooling.",
        (
            "lein", "leiningen", "deps.edn", "tools.deps", "boot", "classpath",
            "dependency", "dependencies", "maven", "jar", "project.clj", "clj -",
            "package", "install", "repository", "artifact", "build",
        ),
    ),
    Topic(
        "clojurians",
        "clojure-concurrency",
        "Clojure Concurrency",
        "core.async, channels, state coordination, parallelism, and concurrency.",
        (
            "core.async", "go block", "channel", "alts!", "atom", "agent", "future",
            "promise", "thread", "concurrent", "concurrency", "parallel", "locking",
            "transaction", "ref ", "stm", "async",
        ),
    ),
    Topic(
        "clojurians",
        "clojure-language",
        "Clojure Language",
        "Clojure functions, macros, sequences, protocols, namespaces, and idioms.",
        (
            "macro", "transducer", "sequence", "lazy", "protocol", "multimethod",
            "namespace", "function", "defn", "let ", "spec", "keyword", "vector",
            "map ", "reduce", "clojure", "repl",
        ),
    ),
    Topic(
        "elmlang",
        "elm-architecture",
        "Elm Architecture",
        "The Elm Architecture, application state, commands, and subscriptions.",
        (
            "model", "update", "view", "the elm architecture", "tea", "msg",
            "message", "command", "cmd", "subscription", "subscriptions", "program",
            "init", "state", "architecture",
        ),
    ),
    Topic(
        "elmlang",
        "elm-ui-styling",
        "Elm UI & Styling",
        "Elm user interfaces, HTML, CSS, forms, layout, and visual components.",
        (
            "elm-ui", "html", "css", "style", "layout", "element", "button", "form",
            "input", "view", "attribute", "class", "flex", "grid", "svg", "modal",
            "component", "design",
        ),
    ),
    Topic(
        "elmlang",
        "elm-http-json",
        "Elm HTTP & JSON",
        "Elm HTTP requests, APIs, JSON decoding, encoding, and remote data.",
        (
            "http", "request", "response", "json", "decoder", "decode", "encoder",
            "encode", "api", "graphql", "websocket", "remote data", "fetch", "ajax",
            "endpoint", "server", "url",
        ),
    ),
    Topic(
        "elmlang",
        "elm-routing",
        "Elm Routing & Navigation",
        "Elm URLs, routers, navigation, pages, and single-page applications.",
        (
            "route", "router", "routing", "navigation", "navigate", "url", "browser.history",
            "browser.application", "location", "history", "page", "single page", "spa",
            "path", "link", "fragment",
        ),
    ),
    Topic(
        "elmlang",
        "elm-build-tools",
        "Elm Build Tools",
        "Elm packages, dependencies, compilers, builds, and JavaScript integration.",
        (
            "elm-package", "elm.json", "package", "dependency", "dependencies", "npm",
            "webpack", "compile", "compiler", "build", "install", "version", "upgrade",
            "elm make", "elm reactor", "javascript", "port",
        ),
    ),
    Topic(
        "elmlang",
        "elm-language",
        "Elm Language",
        "Elm types, functions, records, collections, modules, and language semantics.",
        (
            "type alias", "union type", "maybe", "result", "function", "record",
            "list", "tuple", "pattern match", "case ", "module", "import", "map",
            "fold", "lambda", "elm", "type ",
        ),
    ),
    Topic(
        "racket",
        "racket-macros",
        "Racket Macros",
        "Racket macros, syntax objects, expansion, and language extension.",
        (
            "macro", "syntax-rules", "syntax-case", "syntax/parse", "syntax parse",
            "transformer", "expand", "expander", "datum->syntax", "quasisyntax",
            "define-syntax", "reader", "language extension", "syntax", "#lang",
            "quasiquote", "unquote", "hygien", "template", "pattern",
        ),
    ),
    Topic(
        "racket",
        "racket-gui-graphics",
        "Racket GUI & Graphics",
        "Racket desktop interfaces, drawing, images, games, and visual programs.",
        (
            "racket/gui", "gui", "frame%", "canvas", "pict", "image", "drawing",
            "graphics", "2htdp/image", "big-bang", "universe", "game", "window",
            "bitmap", "render", "animation", "draw", "color", "widget", "panel",
            "editor", "plot", "mouse", "keyboard", "screen", "visual",
        ),
    ),
    Topic(
        "racket",
        "racket-data-structures",
        "Racket Data Structures",
        "Lists, vectors, hashes, sequences, streams, trees, and collection processing.",
        (
            "list", "vector", "hash", "sequence", "stream", "set ", "map ",
            "fold", "tree", "dictionary", "pair", "cons", "car ", "cdr", "append",
            "sort", "filter", "collection", "immutable", "mutable",
        ),
    ),
    Topic(
        "racket",
        "racket-web-services",
        "Racket Web Services",
        "Racket web servers, servlets, HTTP applications, HTML, and APIs.",
        (
            "web-server", "web server", "servlet", "http", "request", "response",
            "html", "xexpr", "url", "web app", "api", "endpoint", "dispatch-rules",
            "send/suspend", "server", "database",
        ),
    ),
    Topic(
        "racket",
        "racket-packages",
        "Racket Packages & Tooling",
        "Racket packages, documentation, testing, installation, and command-line tools.",
        (
            "raco", "package", "pkg", "install", "scribble", "documentation", "docs",
            "rackunit", "test", "collection", "planet", "dependency", "build", "compile",
            "command line", "library", "module path",
        ),
    ),
    Topic(
        "racket",
        "racket-language",
        "Racket Language",
        "Racket functions, modules, structures, contracts, and language semantics.",
        (
            "lambda", "function", "struct", "module", "require",
            "provide", "recursion", "define", "match", "parameter", "continuation",
            "racket", "scheme",
        ),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path, help="Path to the cloned Slack dataset")
    parser.add_argument(
        "--base-seed",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "seed_data.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "slack_channel_seed.json",
    )
    parser.add_argument("--messages-per-channel", type=int, default=1_000)
    parser.add_argument("--analyze-only", action="store_true")
    return parser.parse_args()


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def keyword_score(text: str, topic: Topic) -> int:
    return sum(text.count(keyword) for keyword in topic.keywords)


def parse_community_conversations(dataset_root: Path, community: str):
    data_dir = dataset_root / "data" / community
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Missing dataset community directory: {data_dir}")

    for xml_path in sorted(data_dir.rglob("*.xml")):
        conversations: dict[str, list[dict[str, str]]] = defaultdict(list)
        for _, element in ET.iterparse(xml_path, events=("end",)):
            if element.tag != "message":
                continue
            conversation_id = element.attrib.get("conversation_id", "")
            text = element.findtext("text") or ""
            timestamp = element.findtext("ts") or ""
            source_user = element.findtext("user") or "Unknown"
            if conversation_id and text.strip() and len(text) <= MAX_MESSAGE_CHARS:
                conversations[conversation_id].append(
                    {"timestamp": timestamp, "source_user": source_user, "text": text}
                )
            element.clear()

        for conversation_id, messages in conversations.items():
            messages.sort(key=lambda message: message["timestamp"])
            yield f"{xml_path.relative_to(dataset_root)}:{conversation_id}", messages


def assign_conversations(dataset_root: Path):
    assigned: dict[str, list[tuple[int, str, list[dict[str, str]]]]] = defaultdict(list)
    for community in sorted({topic.community for topic in TOPICS}):
        topics = [topic for topic in TOPICS if topic.community == community]
        for source_id, messages in parse_community_conversations(dataset_root, community):
            searchable = normalized_text("\n".join(message["text"] for message in messages))
            scored = [(keyword_score(searchable, topic), topic) for topic in topics]
            best_score, best_topic = max(scored, key=lambda item: (item[0], item[1].name))
            if best_score > 0:
                assigned[best_topic.name].append((best_score, source_id, messages))

    for topic in TOPICS:
        assigned[topic.name].sort(key=lambda item: (-item[0], item[1]))
    return assigned


def mapped_user(source_user: str, usernames: list[str]) -> str:
    digest = hashlib.sha256(source_user.encode("utf-8")).digest()
    return usernames[int.from_bytes(digest[:4], "big") % len(usernames)]


def select_conversations(conversations, target_message_count: int):
    selected = []
    message_count = 0
    for score, source_id, messages in conversations:
        if message_count >= target_message_count:
            break
        selected.append((score, source_id, messages))
        message_count += len(messages)
    return selected, message_count


def build_seed(base_seed: dict, assigned, target_message_count: int) -> tuple[dict, dict]:
    engineering_team = next(team for team in base_seed["teams"] if team["name"] == "engineering")
    usernames = list(engineering_team["members"])
    channels = []
    conversations: dict[str, list[dict]] = {}
    stats = {}

    for topic in TOPICS:
        selected, message_count = select_conversations(
            assigned[topic.name], target_message_count
        )
        if message_count < target_message_count:
            raise RuntimeError(
                f"{topic.name} has only {message_count} classified messages; "
                f"target is {target_message_count}"
            )

        channels.append(
            {
                "name": topic.name,
                "display_name": topic.display_name,
                "purpose": topic.purpose,
                "header": (
                    "Imported verbatim from the Software-related Slack Chats with "
                    "Disentangled Conversations dataset."
                ),
                "type": "O",
            }
        )

        channel_posts = []
        for _, source_id, messages in selected:
            root = {
                "user": mapped_user(messages[0]["source_user"], usernames),
                "message": messages[0]["text"],
                "source": source_id,
            }
            if len(messages) > 1:
                root["replies"] = [
                    {
                        "user": mapped_user(message["source_user"], usernames),
                        "message": message["text"],
                    }
                    for message in messages[1:]
                ]
            channel_posts.append(root)
        conversations[topic.name] = channel_posts
        stats[topic.name] = {
            "conversations": len(selected),
            "messages": message_count,
            "classified_messages": sum(
                len(messages) for _, _, messages in assigned[topic.name]
            ),
        }

    seed = {
        "admin": base_seed["admin"],
        "users": base_seed["users"],
        "teams": base_seed["teams"],
        "channels": {"engineering": channels},
        "conversations": {"engineering": conversations},
        "direct_messages": [],
        "group_messages": [],
        "dataset_provenance": {
            "name": "Software-related Slack Chats with Disentangled Conversations",
            "repository": (
                "https://github.com/preethac/"
                "Software-related-Slack-Chats-with-Disentangled-Conversations"
            ),
            "message_text_policy": "verbatim",
            "participant_mapping": "deterministic mapping to seeded Engineering users",
            "channel_count": len(TOPICS),
            "target_messages_per_channel": target_message_count,
            "stats": stats,
        },
    }
    return seed, stats


def print_stats(assigned, selected_stats: dict | None = None):
    print(f"{'channel':30} {'classified':>12} {'selected':>10} {'threads':>9}")
    print("-" * 67)
    for topic in TOPICS:
        classified = sum(len(messages) for _, _, messages in assigned[topic.name])
        if selected_stats:
            selected = selected_stats[topic.name]["messages"]
            threads = selected_stats[topic.name]["conversations"]
        else:
            selected = 0
            threads = len(assigned[topic.name])
        print(f"{topic.name:30} {classified:12,d} {selected:10,d} {threads:9,d}")


def main() -> int:
    args = parse_args()
    dataset_root = args.dataset_root.resolve()
    base_seed = json.loads(args.base_seed.read_text())
    assigned = assign_conversations(dataset_root)

    if args.analyze_only:
        print_stats(assigned)
        return 0

    seed, stats = build_seed(base_seed, assigned, args.messages_per_channel)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n")
    print_stats(assigned, stats)
    print(f"\nWrote {args.output} ({args.output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
