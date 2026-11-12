"""Read-only Nextcloud contracts for Talk polls and copied-folder shares.

Use account IDs, native poll/reaction objects, file bytes, and share targets.
Unavailable/ambiguous evidence is inconclusive; a complete negative is final.
API contracts: https://nextcloud-talk.readthedocs.io/en/latest/{participant,poll,chat,reaction}/
"""
from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import quote, unquote, urlencode, urlsplit

from webarena_pro_core.eval.backend_state import BackendStateEvaluator


class NextcloudSavedStateEvaluator:
    def evaluate(self, config, context):
        from webarena_pro_core.eval.dag import NodeResult

        try:
            # Per-evaluation state only: never reuse evidence across runs/slots.
            evidence = _Evidence(config, context)
            passed, reason = evidence.evaluate()
            return NodeResult(passed, reason)
        except Exception as error:
            return NodeResult(False, f"Nextcloud evidence unavailable: {type(error).__name__}: {error}",
                              inconclusive=True)


class NextcloudReactionUIEvaluator(NextcloudSavedStateEvaluator):
    """Pass-only DOM fallback, still bound to native group/poll/vote evidence."""

    def evaluate(self, config, context):
        return super().evaluate({**config, "criterion": "reaction", "reaction_ui": True}, context)


class _Evidence:
    def __init__(self, config, context):
        self.config = config
        self.context = context
        self.user = config["user"]
        self.backend = BackendStateEvaluator()
        self.hashes = {}
        self.uncertain_rooms = False
        self.history = {}

    def get(self, path, *, admin=False, query=None):
        if query:
            path += "?" + urlencode(query)
        return self.backend._send({
            "method": "GET", "url": "__NEXTCLOUD__" + path,
            "auth_site": "nextcloud", "auth_user": "admin" if admin else self.user,
            "headers": {"OCS-APIRequest": "true", "Accept": "application/json"},
        }, self.context)

    def ocs(self, path, **kwargs):
        from webarena_pro_core.eval.providers.ocs import response_data

        return response_data(self.get("/ocs/v2.php/" + path, **kwargs))

    def evaluate(self):
        criterion = self.config["criterion"]
        if criterion in {"new_folder", "copied_files", "folder_share"}:
            folders = self.new_folders()
            if criterion == "new_folder":
                return bool(folders), f"new destination folders: {sorted(folders)}"
            folders = self.copied_folders(folders)
            if criterion == "copied_files" or not folders:
                return bool(folders), f"new folders containing the requested copies: {sorted(folders)}"
            rooms = self.matching_rooms()
            return self.folder_shared(folders, rooms), "saved folder share to the requested participants"

        rooms = self.matching_rooms()
        if criterion == "group":
            if not rooms and self.uncertain_rooms:
                raise ValueError("group creation or non-user participant identity could not be verified")
            return bool(rooms), f"groups with all requested account IDs: {rooms}"
        if criterion not in {"poll", "votes", "reaction"}:
            raise ValueError(f"unknown criterion {criterion}")
        unknown = False
        for token in rooms:
            for message in self.messages(token):
                if message["systemMessage"] != "object_shared":
                    continue
                objects = _objects(message["messageParameters"])
                for obj in objects:
                    if obj.get("type") != "talk-poll":
                        continue
                    poll = self.ocs(f"apps/spreed/api/v1/poll/{quote(token, safe='')}/{_id(obj['id'])}")
                    if str(poll["id"]) != str(obj["id"]):
                        raise ValueError("poll identity mismatch")
                    options = poll["options"]
                    if not isinstance(options, list) or not all(isinstance(s, str) for s in options):
                        raise ValueError("malformed poll options")
                    if len(options) != len(self.config["times"]):
                        continue
                    times = [_time_minutes(option) for option in options]
                    if None in times:
                        unknown = True
                        continue
                    if sorted(times) != sorted(self.config["times"]):
                        continue
                    if criterion == "poll":
                        return True, f"native poll {poll['id']} in group {token} has the requested options"
                    # Cumulative predicates bind the reaction to the very poll
                    # with all three votes, rather than combining two polls.
                    votes = poll["votedSelf"]
                    if not isinstance(votes, list) or not all(type(v) is int for v in votes):
                        raise ValueError("malformed current-user votes")
                    if set(votes) != set(range(len(options))):
                        continue
                    if criterion == "votes":
                        return True, f"current user voted for every option of poll {poll['id']} in {token}"
                    if self.config.get("reaction_ui"):
                        reactions = {"✅": self.reaction_events(token, message)}
                    else:
                        reactions = self.ocs(f"apps/spreed/api/v1/reaction/{quote(token, safe='')}/{_id(message['id'])}")
                    if not isinstance(reactions, dict):
                        raise ValueError("malformed reactions")
                    for reaction in _records(reactions.get("✅", [])):
                        if reaction["actorType"] != "users" or reaction["actorId"] != self.user:
                            continue
                        if not self.reaction_after_votes(token, poll, message, reaction):
                            continue
                        if self.config.get("reaction_ui") and not self.visible_self_reaction(token, message):
                            continue
                        return True, f"current user's checkmark follows all votes on poll {poll['id']} (message {message['id']}) in {token}"
        if unknown or self.uncertain_rooms:
            raise ValueError("poll wording, group creation, or participant identity needs further evidence")
        return False, f"no saved {criterion} matches in the requested groups"

    def matching_rooms(self):
        bundle = self.context.baselines.get(self.config["room_baseline_ref"])
        if not bundle or bundle.get("error") or bundle.get("diff") is None:
            raise ValueError("complete before/after conversation snapshots are required")
        if bundle["baseline"].error or bundle["current"].error:
            raise ValueError("conversation snapshot failed")
        before = bundle["baseline"].entries
        start = self.context.task_start_time_ms
        if type(start) is not int or start <= 0:
            raise ValueError("task start time is required to verify group creation")
        # Resolve prompt names against the complete account directory, not chat
        # titles or mutable participant labels. Ambiguous first names escalate.
        users = {}
        for offset in range(0, 20000, 200):
            batch = self.ocs("cloud/users/details", admin=True,
                             query={"limit": 200, "offset": offset})["users"]
            if batch == []:  # PHP may encode the empty associative array as [].
                batch = {}
            if not isinstance(batch, dict) or set(batch) & set(users):
                raise ValueError("malformed or non-advancing user directory")
            users.update(batch)
            if len(batch) < 200:
                break
        else:
            raise ValueError("user directory exceeds pagination limit")
        expected = {self.user}
        for name in self.config["participants"]:
            matches = []
            for uid, details in users.items():
                display = details.get("displayname", details.get("display-name"))
                if not isinstance(display, str) or not display.strip():
                    raise ValueError("user directory lacks display names")
                labels = {uid.casefold(), display.strip().casefold(), display.split()[0].casefold()}
                if name.casefold() in labels:
                    matches.append(uid)
            if len(matches) != 1:
                raise ValueError(f"participant {name!r} does not resolve to one account")
            expected.add(matches[0])
        if len(expected) != len(self.config["participants"]) + 1:
            raise ValueError("participant names resolve to duplicate accounts")

        matches = []
        for room in _records(self.ocs("apps/spreed/api/v4/room")):
            if room["type"] not in {2, 3}:  # private/public group; exclude DMs
                continue
            token = room["token"]
            if token in before:
                continue
            participants = _records(self.ocs(f"apps/spreed/api/v4/room/{quote(token, safe='')}/participants"))
            ids = {p["actorId"] for p in participants if p["actorType"] == "users"}
            if expected <= ids:
                # A newly visible room could be an invitation to an old group.
                # Also require the current user's native creation event.
                created = [m for m in self.messages(token) if m["systemMessage"] == "conversation_created"]
                if not created:
                    self.uncertain_rooms = True
                elif any(m["actorType"] == "users" and m["actorId"] == self.user
                         and _timestamp(m) >= start / 1000 for m in created):
                    matches.append(token)
                elif any(_timestamp(m) == start // 1000 for m in created):
                    # Native timestamps have second precision.
                    self.uncertain_rooms = True
            elif any(p["actorType"] != "users" for p in participants):
                self.uncertain_rooms = True
        return matches

    def messages(self, token):
        if token not in self.history:
            self.history[token] = list(self.fetch_messages(token))
        return self.history[token]

    def fetch_messages(self, token):
        from webarena_pro_core.eval.providers.ocs import response_data

        # Read history without changing read markers, status, or notifications.
        cursor = 0
        for _ in range(100):
            response = self.get(f"/ocs/v2.php/apps/spreed/api/v1/chat/{quote(token, safe='')}", query={
                "lookIntoFuture": 0, "limit": 200, "lastKnownMessageId": cursor,
                "includeLastKnown": 0, "setReadMarker": 0, "noStatusUpdate": 1,
                "markNotificationsAsRead": 0,
            })
            if response.status_code == 304:
                return
            batch = _records(response_data(response))
            for message in batch:
                if message["token"] != token:
                    raise ValueError("chat message belongs to a different conversation")
                yield message
            if not batch:
                return
            # Even a short page can have more history (visibility/filtering).
            next_cursor = int(response.headers["X-Chat-Last-Given"])
            if next_cursor <= 0 or (cursor and next_cursor >= cursor):
                raise ValueError("chat history cursor did not advance")
            cursor = next_cursor
        raise ValueError("chat history exceeds pagination limit")

    def reaction_events(self, token, message):
        return [m for m in self.messages(token)
                if m["systemMessage"] == "reaction" and m["message"] == "✅"
                and str(m.get("parent", {}).get("id")) == str(message["id"])
                and m["actorType"] == "users" and m["actorId"] == self.user]

    def reaction_after_votes(self, token, poll, message, reaction):
        votes = [m for m in self.messages(token)
                 if m["systemMessage"] == "poll_voted" and m["actorType"] == "users"
                 and m["actorId"] == self.user
                 and any(o.get("type") == "talk-poll" and str(o.get("id")) == str(poll["id"])
                         for o in _objects(m["messageParameters"]))]
        if not votes:
            raise ValueError("vote history unavailable; reaction order cannot be established")
        last_vote = max(votes, key=lambda m: int(_id(m["id"])))
        vote_time, reaction_time = _timestamp(last_vote), _timestamp(reaction)
        if reaction_time != vote_time:
            return reaction_time > vote_time
        # Resolve equal-second timestamps only with native event ordering.
        events = [m for m in self.reaction_events(token, message) if _timestamp(m) == reaction_time]
        if not events:
            raise ValueError("same-second reaction order needs the native reaction event")
        return max(int(_id(m["id"])) for m in events) > int(_id(last_vote["id"]))

    def visible_self_reaction(self, token, message):
        from webarena_pro_core.eval.defaults import deployed_website_urls

        from webarena_pro_core.eval.ui_evidence import UIProbe, require_ui_evidence

        evidence = require_ui_evidence(self.context)
        current, base = urlsplit(evidence.url), urlsplit(deployed_website_urls()["nextcloud"])
        if (current.scheme, current.netloc) != (base.scheme, base.netloc):
            return False
        if unquote(current.path).rstrip("/") not in {
            base.path.rstrip("/") + "/call/" + token,
            base.path.rstrip("/") + "/index.php/call/" + token,
        }:
            return False
        reactions = evidence.result(UIProbe(kind="nextcloud_reactions")).reactions
        return any(
            item.message_id == _id(message["id"]) and item.selected and item.text.strip() == "✅"
            for item in reactions
        )

    def new_folders(self):
        bundle = self.context.baselines.get(self.config["baseline_ref"])
        if not bundle or bundle.get("error") or bundle.get("diff") is None:
            raise ValueError("complete before/after file snapshots are required")
        self.before = bundle["baseline"].entries
        self.after = bundle["current"].entries
        if bundle["baseline"].error or bundle["current"].error:
            raise ValueError("file snapshot failed")
        self.before_ids = {_id(attrs["file_id"]) for attrs in self.before.values()}
        for attrs in self.after.values():
            _id(attrs["file_id"])
        return {p for p, attrs in self.after.items()
                if attrs["type"] == "dir" and str(attrs["file_id"]) not in self.before_ids}

    def copied_folders(self, folders):
        # Source identities come from the shipped Safari asset manifest. Music
        # alternatives are intentional: the prompt does not specify a track.
        groups = []
        for alternatives in self.config["source_files"]:
            paths = [p for p in self.before if p.casefold() in {s.casefold() for s in alternatives}
                     and self.before[p]["type"] == "file"]
            if not paths:
                raise ValueError("requested Safari source is absent from the baseline")
            surviving = []
            for path in paths:
                if path not in self.after or self.after[path]["type"] != "file":
                    continue
                original, current = self.before[path], self.after[path]
                if str(original["file_id"]) != str(current["file_id"]):
                    continue
                if not original.get("etag") or not current.get("etag"):
                    raise ValueError("source version unavailable")
                if original["etag"] != current["etag"]:
                    raise ValueError("source changed since baseline; copy identity is uncertain")
                if type(current.get("size")) is not int:
                    raise ValueError("source size unavailable")
                surviving.append(path)
            if not surviving:
                return set()  # originals were moved/deleted, not copied
            groups.append(surviving)
        valid = set()
        for folder in folders:
            children = [p for p, attrs in self.after.items()
                        if attrs["type"] == "file" and str(PurePosixPath(p).parent) == folder
                        and str(attrs["file_id"]) not in self.before_ids]
            if len(children) < len(groups):
                continue
            if len(children) > 200:
                raise ValueError("destination exceeds file verification limit")
            if any(type(self.after[p].get("size")) is not int for p in children):
                raise ValueError("destination file size unavailable")
            matched = []
            for sources in groups:
                copies = {target for target in children for source in sources
                          if self.after[target].get("size") == self.after[source].get("size")
                          and self.file_hash(target) == self.file_hash(source)}
                matched.append(copies)
            # Distinct destination files must satisfy the three requested roles.
            if _distinct_matches(matched):
                valid.add(folder)
        return valid

    def file_hash(self, path):
        if path not in self.hashes:
            size = self.after[path].get("size")
            if type(size) is not int or size < 0 or size > 64 * 1024 * 1024:
                raise ValueError("file size unavailable or exceeds verification limit")
            response = self.get(f"/remote.php/dav/files/{quote(self.user, safe='')}/{quote(path, safe='/')}")
            if response.status_code != 200 or len(response.content) != size:
                raise ValueError("file bytes unavailable or changed during verification")
            etag = response.headers.get("ETag", "").strip('"')
            if not etag or etag != self.after[path].get("etag"):
                raise ValueError("file version differs from current snapshot")
            self.hashes[path] = hashlib.sha256(response.content).digest()
        return self.hashes[path]

    def folder_shared(self, folders, rooms):
        shares = _records(self.ocs("apps/files_sharing/api/v1/shares"))
        candidates = [s for s in shares if s["path"].lstrip("/") in folders
                      and s["item_type"] == "folder" and s["uid_owner"] == self.user
                      and str(s["file_source"]) == str(self.after[s["path"].lstrip("/")]["file_id"])
                      and int(s["permissions"]) & 1]
        for token in rooms:
            native = {str(s["file_source"]) for s in candidates
                      if int(s["share_type"]) == 10 and s["share_with"] == token and not s.get("expiration")}
            links = {s["url"] for s in candidates if int(s["share_type"]) == 3
                     and not s.get("password") and not s.get("expiration")}
            for message in self.messages(token):
                if message["actorType"] != "users" or message["actorId"] != self.user:
                    continue
                if message["systemMessage"] == "file_shared":
                    for obj in _objects(message["messageParameters"]):
                        if obj.get("type") == "file" and str(obj["id"]) in native:
                            return True
                if not message["systemMessage"] and message["messageType"] == "comment":
                    urls = {u.rstrip(".,;!?)") for u in re.findall(r'https?://[^\s<>"\]]+', message["message"])}
                    if urls & links:
                        return True
        # Password/expiry/link variants may need semantic evidence about access.
        if self.uncertain_rooms or any(int(s["share_type"]) == 3 or s.get("expiration") for s in candidates):
            raise ValueError("link access, expiry, or non-user participants could not be fully verified")
        return False


def _records(value):
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ValueError("expected an array of evidence objects")
    return value


def _objects(value):
    if value == []:
        return []
    if not isinstance(value, dict) or not all(isinstance(obj, dict) for obj in value.values()):
        raise ValueError("malformed rich message objects")
    return value.values()


def _id(value):
    if not re.fullmatch(r"[1-9][0-9]*", str(value)):
        raise ValueError("invalid saved object ID")
    return str(value)


def _timestamp(message):
    value = message["timestamp"]
    if type(value) is not int or value <= 0:
        raise ValueError("invalid native event timestamp")
    return value


def _time_minutes(value):
    value = value.casefold().replace(".", "").strip()
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value)
    if not match:
        return None
    hour, minute, period = int(match[1]), int(match[2] or 0), match[3]
    if minute > 59 or (period and not 1 <= hour <= 12) or (not period and hour > 23):
        return None
    if period:
        hour = hour % 12 + (12 if period == "pm" else 0)
    return 60 * hour + minute


def _distinct_matches(groups, used=frozenset()):
    return not groups or any(_distinct_matches(groups[1:], used | {item})
                             for item in groups[0] - used)
