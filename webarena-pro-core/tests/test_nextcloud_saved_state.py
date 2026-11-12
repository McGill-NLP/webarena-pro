"""Exercise the shipped task DAGs against HTTP-shaped saved-state evidence."""
import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
import requests

from webarena_pro_core.eval import dag
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, NodeResult, parse_eval_dag
from webarena_pro_core.eval.nextcloud_saved_state import NextcloudSavedStateEvaluator
from webarena_pro_core.eval.snapshot import Snapshot, build_snapshot_bundle
from webarena_pro_core.eval.tiered import TieredRubricEvaluator
from webarena_pro_core.task import WebArenaProTaskConfig


CONFIG = Path(__file__).parents[1] / "src/webarena_pro_core/config"
TASKS = {t["task_id"]: t for t in json.loads((CONFIG / "nextcloud.raw.json").read_text())}
CHARLIE = ["betty.hall", "daniel.brooks", "barbara.thomas", "alex.smith"]
SAFARI = ["susan.white", "matthew.walker", "robert.brown"]
USER = "maya.patel"
SOURCES = ["safari/AfricansafariAug2014-025.jpg", "safari/Elephantsafari.jpg", "safari/SafariMusicLoop.mp3"]
FOLDER = "Trips/Photos & music"


def response(data, status=200, **headers):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps({"ocs": {"meta": {"status": "ok", "statuscode": 200}, "data": data}}).encode()
    result.headers.update(headers)
    return result


def message(message_id, token, system, objects):
    return {"id": message_id, "token": token, "actorType": "users", "actorId": USER,
            "systemMessage": system, "messageType": "system" if system else "comment",
            "messageParameters": objects, "message": "", "timestamp": 90}


class SavedState:
    def __init__(self):
        self.users = {uid: {"displayname": uid.replace(".", " ").title()}
                      for uid in [USER, *CHARLIE, *SAFARI]}
        self.rooms = [{"token": "charlie", "type": 2, "displayName": "Weekly planning"},
                      {"token": "safari", "type": 3, "displayName": "Trip discussion"}]
        self.participants = {"charlie": [USER, *CHARLIE], "safari": [USER, *SAFARI]}
        self.messages = {
            "charlie": [message(12, "charlie", "object_shared", {"object": {"type": "talk-poll", "id": "7"}})],
            "safari": [message(15, "safari", "file_shared", {"file": {"type": "file", "id": "55"}})],
        }
        for token in self.messages:
            self.messages[token].append(message(1 if token == "charlie" else 2, token, "conversation_created", {}))
        self.messages["charlie"].append(message(13, "charlie", "poll_voted", {"poll": {"type": "talk-poll", "id": "7"}}))
        reaction = message(14, "charlie", "reaction", {})
        reaction.update(message="✅", parent={"id": 12}, timestamp=100)
        self.messages["charlie"].append(reaction)
        self.poll = {"id": 7, "options": ["10:00 a.m.", "14:00", "5 PM"], "votedSelf": [0, 1, 2]}
        self.reactions = {"✅": [{"actorType": "users", "actorId": USER, "timestamp": 100}]}
        self.other_polls = {}
        self.other_reactions = {}
        self.rooms_before = {}
        self.bytes = dict(zip(SOURCES, [b"bird image", b"elephant image", b"safari music"]))
        self.before = {"safari": {"type": "dir", "etag": "folder-before", "file_id": "1"},
                       "Trips": {"type": "dir", "etag": "parent-before", "file_id": "2"}}
        for i, path in enumerate(SOURCES):
            self.before[path] = {"type": "file", "etag": f"source-{i}", "size": len(self.bytes[path]), "file_id": str(10 + i)}
        self.after = copy.deepcopy(self.before)
        self.after[FOLDER] = {"type": "dir", "etag": "created", "file_id": "55"}
        for i, path in enumerate(SOURCES):
            target = f"{FOLDER}/renamed-{i}"
            self.bytes[target] = self.bytes[path]
            self.after[target] = {"type": "file", "etag": f"copy-{i}", "size": len(self.bytes[target]), "file_id": str(60 + i)}
        self.shares = [{"path": "/" + FOLDER, "item_type": "folder", "uid_owner": USER,
                        "permissions": 1, "share_type": 10, "share_with": "safari", "file_source": 55}]
        self.requests = []
        self.errors = {}

    def context(self, task_id):
        return EvalContext(task_config=TASKS[task_id], last_action="react('checkmark project-safari')",
                           task_start_time_ms=80000,
                           baselines={"safari_files": build_snapshot_bundle(Snapshot(self.before), Snapshot(self.after)),
                                      "task_rooms": build_snapshot_bundle(Snapshot(self.rooms_before),
                                          Snapshot({r["token"]: r for r in self.rooms}))})

    def send(self, backend, spec, context):
        assert spec["method"] == "GET"
        assert spec["auth_site"] == "nextcloud"
        parsed = urlsplit(spec["url"].replace("__NEXTCLOUD__", "http://worker.nextcloud"))
        path, query = parsed.path, parse_qs(parsed.query)
        self.requests.append((path, query, spec["auth_user"]))
        if path in self.errors:
            return self.errors[path]
        if path == "/ocs/v2.php/cloud/users/details":
            assert spec["auth_user"] == "admin"
            offset, limit = int(query["offset"][0]), int(query["limit"][0])
            return response({"users": dict(list(self.users.items())[offset:offset + limit])})
        assert spec["auth_user"] == USER
        if path == "/ocs/v2.php/apps/spreed/api/v4/room":
            return response(self.rooms)
        if path.endswith("/participants"):
            return response([{"actorType": "users", "actorId": uid} for uid in self.participants[path.split("/")[-2]]])
        if "/chat/" in path:
            assert query["setReadMarker"] == ["0"] and query["noStatusUpdate"] == ["1"]
            assert query["markNotificationsAsRead"] == ["0"]
            cursor = int(query["lastKnownMessageId"][0])
            history = self.messages[path.split("/")[-1]]
            batch = sorted([m for m in history if not cursor or m["id"] < cursor], key=lambda m: -m["id"])[:200]
            return response(batch, **{"X-Chat-Last-Given": str(min(m["id"] for m in batch))}) if batch else response([], 304)
        if "/poll/" in path:
            return response(self.poll if path.endswith("/charlie/7") else self.other_polls[path.rsplit("/", 1)[-1]])
        if "/reaction/" in path:
            return response(self.reactions if path.endswith("/charlie/12") else self.other_reactions[path.rsplit("/", 1)[-1]])
        if path == "/ocs/v2.php/apps/files_sharing/api/v1/shares":
            return response(self.shares)
        if path.startswith("/remote.php/dav/files/"):
            filename = unquote(path.removeprefix(f"/remote.php/dav/files/{USER}/"))
            result = requests.Response()
            result.status_code = 200
            result._content = self.bytes[filename]
            result.headers["ETag"] = '"' + self.after[filename]["etag"] + '"'
            return result
        pytest.fail(f"unexpected evidence request: {path}")


@pytest.fixture
def saved(monkeypatch):
    state = SavedState()
    monkeypatch.setattr(BackendStateEvaluator, "_send", lambda backend, spec, context: state.send(backend, spec, context))
    def no_judge(*args):
        pytest.fail("a definitive saved-state verdict must not call the judge")
    monkeypatch.setattr(dag._REGISTRY["llm_judge"], "evaluate", no_judge)
    return state


def node_config(task_id, node_id):
    return next(n["eval_config"] for n in TASKS[task_id]["eval"]["nodes"] if n["id"] == node_id)


def grade(saved, task_id, node_id):
    return TieredRubricEvaluator().evaluate(node_config(task_id, node_id), saved.context(task_id))


@pytest.mark.parametrize("task_id", ["159", "165", "176"])
def test_complete_tasks_pass_all_nodes_at_tier_zero(saved, task_id):
    score, nodes = DAGEvaluator(parse_eval_dag(TASKS[task_id]["eval"])).evaluate(saved.context(task_id))
    assert score == 1
    assert all("decided_by=T0:nextcloud_saved_state" in node["reason"] for node in nodes.values())


@pytest.mark.parametrize("task_id,room,missing", [("159", "charlie", CHARLIE[-1]), ("165", "charlie", USER), ("176", "safari", SAFARI[-1])])
def test_matching_title_cannot_substitute_for_participants(saved, task_id, room, missing):
    saved.rooms[0]["displayName"] = "Project Charlie"
    saved.participants[room].remove(missing)
    result = grade(saved, task_id, "r3" if task_id == "176" else "r1")
    assert not result.passed and "T0:nextcloud_saved_state=FAIL" in result.reason


@pytest.mark.parametrize("task_id", ["159", "165"])
@pytest.mark.parametrize("failure", ["wrong_time", "duplicate_option", "extra_option", "missing_vote", "other_reactor", "wrong_emoji", "typed_poll", "wrong_room"])
def test_poll_failures_are_authoritative(saved, task_id, failure):
    node = "r2"
    if failure == "wrong_time": saved.poll["options"][1] = "3 PM"
    elif failure == "duplicate_option": saved.poll["options"][1] = "10 AM"
    elif failure == "extra_option": saved.poll["options"].append("7 PM")
    elif failure == "missing_vote": saved.poll["votedSelf"] = [0, 2]; node = "r3"
    elif failure == "other_reactor": saved.reactions["✅"][0]["actorId"] = CHARLIE[0]; node = "r4"
    elif failure == "wrong_emoji": saved.reactions = {"👍": saved.reactions["✅"]}; node = "r4"
    elif failure == "typed_poll": saved.messages["charlie"][0]["systemMessage"] = ""
    elif failure == "wrong_room": saved.participants["charlie"] = [USER, *SAFARI]
    assert not grade(saved, task_id, node).passed


def test_pagination_finds_old_poll_and_resolves_users_beyond_first_page(saved):
    saved.users = {**{f"filler-{i}": {"displayname": f"Filler {i}"} for i in range(200)}, **saved.users}
    saved.messages["charlie"].extend(message(i, "charlie", "", {}) for i in range(20, 225))
    assert grade(saved, "159", "r2").passed
    assert any(q.get("offset") == ["200"] for _, q, _ in saved.requests)
    assert any(q.get("lastKnownMessageId") not in (None, ["0"]) for _, q, _ in saved.requests)


@pytest.mark.parametrize("failure", ["preexisting", "three_arbitrary", "one_wrong", "moved_original", "split_folders", "wrong_room", "wrong_folder", "wrong_file_id", "no_message", "no_share", "typed_name", "unreadable_share"])
def test_safari_false_positives_are_rejected(saved, failure):
    node = "r2"
    if failure == "preexisting": saved.before[FOLDER] = saved.after[FOLDER]; node = "r1"
    elif failure in {"three_arbitrary", "one_wrong"}:
        for i in (range(3) if failure == "three_arbitrary" else [1]):
            saved.bytes[f"{FOLDER}/renamed-{i}"] = b"x" * saved.after[f"{FOLDER}/renamed-{i}"]["size"]
    elif failure == "moved_original": del saved.after[SOURCES[0]]
    elif failure == "split_folders":
        saved.after["other"] = {"type": "dir", "etag": "new", "file_id": "100"}
        saved.after["other/elephant"] = saved.after.pop(f"{FOLDER}/renamed-1")
        saved.bytes["other/elephant"] = saved.bytes.pop(f"{FOLDER}/renamed-1")
    else:
        node = "r4"
        if failure == "wrong_room": saved.shares[0]["share_with"] = "charlie"
        elif failure == "wrong_folder": saved.shares[0]["path"] = "/safari"
        elif failure == "wrong_file_id": saved.messages["safari"][0]["messageParameters"]["file"]["id"] = "99"
        elif failure == "no_message": saved.messages["safari"].pop(0)
        elif failure == "no_share": saved.shares = []
        elif failure == "typed_name": saved.messages["safari"][0]["systemMessage"] = ""; saved.messages["safari"][0]["message"] = FOLDER
        elif failure == "unreadable_share": saved.shares[0]["permissions"] = 0
    assert not grade(saved, "176", node).passed


def test_public_folder_link_sent_to_correct_group_passes(saved):
    saved.shares[0].update(share_type=3, url="http://worker.nextcloud/s/secret", password=None, expiration=None)
    saved.messages["safari"][0] = message(15, "safari", "", {})
    saved.messages["safari"][0]["message"] = "Here are the files: http://worker.nextcloud/s/secret"
    assert grade(saved, "176", "r4").passed


def test_renaming_an_existing_folder_is_not_creating_a_new_one(saved):
    saved.before["old-name"] = dict(saved.after[FOLDER])
    assert not grade(saved, "176", "r1").passed


def test_moving_an_existing_duplicate_is_not_copying(saved):
    saved.before["old-bird-copy"] = dict(saved.after[f"{FOLDER}/renamed-0"])
    assert not grade(saved, "176", "r2").passed


@pytest.mark.parametrize("task_id,node_id,score", [("159", "r3", .5), ("165", "r4", .75), ("176", "r2", .5)])
def test_saved_failures_preserve_partial_credit(saved, task_id, node_id, score):
    if task_id == "176":
        saved.bytes[f"{FOLDER}/renamed-0"] = b"x" * saved.after[f"{FOLDER}/renamed-0"]["size"]
    elif node_id == "r3":
        saved.poll["votedSelf"] = [0, 1]
    else:
        saved.reactions = {}
    actual, nodes = DAGEvaluator(parse_eval_dag(TASKS[task_id]["eval"])).evaluate(saved.context(task_id))
    assert actual == pytest.approx(score)
    assert not nodes[node_id]["passed"]


@pytest.mark.parametrize("task_id,node_id,failure", [
    ("159", "r1", "auth"), ("159", "r1", "ocs_error"), ("159", "r1", "malformed"),
    ("159", "r1", "ambiguous_name"), ("159", "r1", "missing_identity"),
    ("159", "r2", "unfamiliar_time"), ("159", "r2", "truncated_history"),
    ("159", "r3", "missing_votes"), ("159", "r4", "missing_reaction_api"),
    ("176", "r2", "source_changed"), ("176", "r2", "missing_source"),
    ("176", "r2", "stale_bytes"), ("176", "r2", "missing_size"),
])
def test_unavailable_or_ambiguous_evidence_reaches_judge(saved, monkeypatch, task_id, node_id, failure):
    room_path = "/ocs/v2.php/apps/spreed/api/v4/room"
    if failure == "auth": saved.errors[room_path] = response([], 403)
    elif failure == "ocs_error":
        bad = response([]); bad._content = b'{"ocs":{"meta":{"status":"failure","statuscode":997},"data":[]}}'
        saved.errors[room_path] = bad
    elif failure == "malformed": saved.errors[room_path] = response({})
    elif failure == "ambiguous_name": saved.users["betty.other"] = {"displayname": "Betty Other"}
    elif failure == "missing_identity": del saved.users[CHARLIE[0]]
    elif failure == "unfamiliar_time": saved.poll["options"][1] = "two in the afternoon"
    elif failure == "truncated_history":
        saved.errors["/ocs/v2.php/apps/spreed/api/v1/chat/charlie"] = response([message(999, "charlie", "", {})])
    elif failure == "missing_votes": del saved.poll["votedSelf"]
    elif failure == "missing_reaction_api": saved.errors["/ocs/v2.php/apps/spreed/api/v1/reaction/charlie/12"] = response([], 404)
    elif failure == "source_changed": saved.after[SOURCES[0]]["etag"] = "edited"
    elif failure == "missing_source": del saved.before[SOURCES[0]]
    elif failure == "missing_size": saved.after[f"{FOLDER}/renamed-0"]["size"] = None
    elif failure == "stale_bytes":
        bad = response(None); bad._content = saved.bytes[f"{FOLDER}/renamed-0"]; bad.headers["ETag"] = '"new-version"'
        saved.errors[f"/remote.php/dav/files/{USER}/Trips/Photos%20%26%20music/renamed-0"] = bad
    judged = []
    def judge(config, context):
        judged.append(config)
        return NodeResult(True, "scripted fallback")
    monkeypatch.setattr(dag._REGISTRY["llm_judge"], "evaluate", judge)
    result = grade(saved, task_id, node_id)
    assert result.passed and len(judged) == 1
    assert "INCONCLUSIVE" in result.reason


@pytest.mark.parametrize("phase", ["missing", "baseline", "current"])
def test_missing_or_failed_snapshots_are_not_an_empty_file_tree(saved, phase):
    context = saved.context("176")
    if phase == "missing": context.baselines = {}
    else: context.baselines["safari_files"][phase].error = "backend unavailable"
    config = node_config("176", "r1")["strategies"][0]["config"]
    result = NextcloudSavedStateEvaluator().evaluate(config, context)
    assert result.inconclusive and not result.passed


def test_webdav_snapshot_includes_directories_when_requested(monkeypatch):
    from webarena_pro_core.eval.providers import webdav
    calls = []
    monkeypatch.setenv("WP_NEXTCLOUD_URL", "http://active-worker.nextcloud")
    class Files:
        def __init__(self, url, **kwargs):
            assert url == f"http://active-worker.nextcloud/remote.php/dav/files/{USER}/"
        def find(self, path, **kwargs):
            calls.append(kwargs)
            return {"trip": {"type": "directory", "etag": "folder"},
                    "trip/bird.jpg": {"type": "file", "etag": "file", "size": 8}}
    monkeypatch.setattr(webdav, "WebdavFileSystem", Files)
    result = webdav.WebDAVFilesProvider().fetch("nextcloud", {"user": USER, "include_dirs": True})
    assert calls == [{"detail": True, "on_error": "raise", "withdirs": True}]
    assert result.entries["trip"]["type"] == "dir"


@pytest.mark.parametrize("valid_ids", [True, False])
def test_real_webdav_parser_preserves_stable_ids_or_reports_unavailable(monkeypatch, valid_ids):
    import httpx
    from webarena_pro_core.eval.providers import webdav

    prefix = f"/remote.php/dav/files/{USER}"
    def resource(path, identity, directory):
        resource_type = "<d:collection/>" if directory else ""
        file_id = f"<oc:fileid>{identity}</oc:fileid>" if valid_ids else ""
        return (
            f"<d:response><d:href>{prefix}/{path}</d:href><d:propstat><d:prop>"
            f"<d:resourcetype>{resource_type}</d:resourcetype><d:getetag>version-{identity}</d:getetag>"
            f"<d:getcontentlength>8</d:getcontentlength>{file_id}</d:prop>"
            "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>"
        )
    def transport(request):
        assert request.method == "PROPFIND"
        assert b"oc:fileid" in request.content
        path = request.url.path.removeprefix(prefix).strip("/")
        entries = (resource("", 1, True) + resource("trip", 2, True) if not path
                   else resource("trip", 2, True) + resource("trip/bird.jpg", 3, False))
        return httpx.Response(207, text='<d:multistatus xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
                              + entries + '</d:multistatus>')
    client = webdav._IdentityClient
    monkeypatch.setattr(webdav, "_IdentityClient", lambda *args, **kwargs: client(
        *args, **kwargs, transport=httpx.MockTransport(transport), retry=False))
    params = {"user": USER, "include_dirs": True, "include_ids": True}
    if not valid_ids:
        with pytest.raises(ValueError, match="stable file ID"):
            webdav.WebDAVFilesProvider().fetch("nextcloud", params)
    else:
        snapshot = webdav.WebDAVFilesProvider().fetch("nextcloud", params)
        assert snapshot.entries == {
            "trip": {"type": "dir", "etag": "version-2", "size": 8, "file_id": "2"},
            "trip/bird.jpg": {"type": "file", "etag": "version-3", "size": 8, "file_id": "3"},
        }


@pytest.mark.parametrize("task_id", ["159", "165", "176"])
def test_task_loading_and_tier_zero_policy(task_id):
    task = TASKS[task_id]
    WebArenaProTaskConfig.from_raw_task(task, container_name="nextcloud-test")
    assert not any(t["task_id"] == task_id for t in json.loads((CONFIG / "splits/dev.json").read_text())["tasks"])
    for node in task["eval"]["nodes"]:
        strategies = node["eval_config"]["strategies"]
        deterministic, judge = strategies[0], strategies[-1]
        assert "weight" not in node
        assert node["eval_config"]["rubric"] == judge["config"]["rubric"]
        if task_id in {"159", "165"} and node["id"] == "r4":
            assert strategies[1]["type"] == "nextcloud_reaction_ui"
            assert strategies[1]["tier"] == 1 and strategies[1]["trust"] == "pass_only"
        else:
            assert len(strategies) == 2
        assert deterministic["type"] == "nextcloud_saved_state"
        assert deterministic["tier"] == 0 and deterministic["trust"] == "both"
        assert judge["type"] == "llm_judge"
        if task_id == "176" and node["id"] in {"r2", "r4"}:
            for group in deterministic["config"]["source_files"]:
                assert all(Path(source).name in judge["config"]["rubric"] for source in group)


@pytest.mark.parametrize('task_id,token,node_id', [('159', 'charlie', 'r1'), ('165', 'charlie', 'r1'), ('176', 'safari', 'r3')])
@pytest.mark.parametrize('failure', ['baseline_room', 'old_invitation', 'other_creator'])
def test_group_must_be_created_by_current_user_during_task(saved, task_id, token, node_id, failure):
    creation = next(m for m in saved.messages[token] if m['systemMessage'] == 'conversation_created')
    if failure == 'baseline_room':
        saved.rooms_before[token] = {'type': 2}
    elif failure == 'old_invitation':
        creation['timestamp'] = 70
    else:
        creation['actorId'] = CHARLIE[0]
    result = grade(saved, task_id, node_id)
    assert not result.passed and 'decided_by=T0:nextcloud_saved_state' in result.reason


@pytest.mark.parametrize('failure', ['missing_creation', 'missing_baseline', 'failed_baseline', 'failed_current', 'missing_start', 'same_second'])
def test_unknown_group_creation_escalates(saved, monkeypatch, failure):
    context = saved.context('159')
    if failure == 'missing_creation':
        saved.messages['charlie'] = [m for m in saved.messages['charlie'] if m['systemMessage'] != 'conversation_created']
    elif failure == 'missing_baseline':
        del context.baselines['task_rooms']
    elif failure in {'failed_baseline', 'failed_current'}:
        context.baselines['task_rooms'][failure.removeprefix('failed_')].error = 'unavailable'
    elif failure == 'missing_start':
        context.task_start_time_ms = None
    else:
        context.task_start_time_ms = 90100
    judged = []
    monkeypatch.setattr(dag._REGISTRY['llm_judge'], 'evaluate', lambda c, ctx: judged.append(c) or NodeResult(False, 'no creation evidence'))
    result = TieredRubricEvaluator().evaluate(node_config('159', 'r1'), context)
    assert not result.passed and len(judged) == 1
    assert 'T0:nextcloud_saved_state=INCONCLUSIVE' in result.reason


@pytest.mark.parametrize('reaction_time,expected', [(89, False), (90, True), (91, True)])
def test_reaction_must_follow_last_vote(saved, reaction_time, expected):
    saved.reactions['✅'][0]['timestamp'] = reaction_time
    saved.messages['charlie'][-1]['timestamp'] = reaction_time
    assert grade(saved, '165', 'r4').passed is expected


def test_same_second_reaction_before_vote_fails(saved):
    saved.reactions['✅'][0]['timestamp'] = 90
    saved.messages['charlie'][-1].update(timestamp=90, id=11)
    assert not grade(saved, '159', 'r4').passed


def test_later_revote_invalidates_earlier_checkmark(saved):
    vote = message(16, 'charlie', 'poll_voted', {'poll': {'type': 'talk-poll', 'id': '7'}})
    vote['timestamp'] = 101
    saved.messages['charlie'].append(vote)
    assert not grade(saved, '165', 'r4').passed


@pytest.mark.parametrize('failure', ['missing_vote_event', 'other_poll_vote', 'other_user_vote', 'same_second_without_event', 'missing_timestamp'])
def test_unprovable_reaction_order_escalates(saved, monkeypatch, failure):
    vote = next(m for m in saved.messages['charlie'] if m['systemMessage'] == 'poll_voted')
    if failure == 'missing_vote_event':
        saved.messages['charlie'].remove(vote)
    elif failure == 'other_poll_vote':
        vote['messageParameters']['poll']['id'] = '8'
    elif failure == 'other_user_vote':
        vote['actorId'] = CHARLIE[0]
    elif failure == 'same_second_without_event':
        saved.reactions['✅'][0]['timestamp'] = 90
        saved.messages['charlie'].pop()
    else:
        del saved.reactions['✅'][0]['timestamp']
    judged = []
    monkeypatch.setattr(dag._REGISTRY['llm_judge'], 'evaluate', lambda c, ctx: judged.append(c) or NodeResult(False, 'no order evidence'))
    result = grade(saved, '165', 'r4')
    assert not result.passed and len(judged) == 1
    assert 'T0:nextcloud_saved_state=INCONCLUSIVE' in result.reason


@pytest.mark.parametrize('second_has_votes', [False, True])
@pytest.mark.parametrize('separate_room', [False, True])
def test_votes_and_reaction_must_belong_to_one_poll(saved, second_has_votes, separate_room):
    saved.reactions = {}
    token = 'second' if separate_room else 'charlie'
    if separate_room:
        saved.rooms.append({'token': token, 'type': 2})
        saved.participants[token] = [USER, *CHARLIE]
        saved.messages[token] = [message(3, token, 'conversation_created', {})]
    saved.messages[token].extend([
        message(20, token, 'object_shared', {'object': {'type': 'talk-poll', 'id': '8'}}),
        message(21, token, 'poll_voted', {'poll': {'type': 'talk-poll', 'id': '8'}}),
    ])
    saved.other_polls['8'] = {**saved.poll, 'id': 8, 'votedSelf': [0, 1, 2] if second_has_votes else [0]}
    saved.other_reactions['20'] = {'✅': [{'actorType': 'users', 'actorId': USER, 'timestamp': 100}]}
    score, nodes = DAGEvaluator(parse_eval_dag(TASKS['159']['eval'])).evaluate(saved.context('159'))
    assert nodes['r3']['passed']
    assert nodes['r4']['passed'] is second_has_votes
    assert score == (1 if second_has_votes else .75)


def reaction_evidence(route, message_id=12, own=True, emoji='✅', hidden=False, in_history=True):
    from webarena_pro_core.eval.ui_evidence import UIEvidence, UIEvidencePlan, UIProbe, UIProbeResult

    probe = UIProbe(kind="nextcloud_reactions")
    records = [] if hidden or not in_history else [dict(message_id=str(message_id), text=emoji, selected=own)]
    return UIEvidence(evaluation_id="fixture", captured_at=1.0, url=route, status="ok",
                      plan_sha256=UIEvidencePlan(probes=[probe]).sha256,
                      results={probe.key: UIProbeResult(probe=probe, status="ok", reactions=records)})


@pytest.mark.parametrize('task_id', ['159', '165'])
@pytest.mark.parametrize('options,route,expected', [
    ({}, 'http://worker.nextcloud/call/charlie', True),
    ({}, 'http://worker.nextcloud/index.php/call/charlie', True),
    ({'message_id': 999}, 'http://worker.nextcloud/call/charlie', False),
    ({'own': False}, 'http://worker.nextcloud/call/charlie', False),
    ({'emoji': '👍'}, 'http://worker.nextcloud/call/charlie', False),
    ({'hidden': True}, 'http://worker.nextcloud/call/charlie', False),
    ({'in_history': False}, 'http://worker.nextcloud/call/charlie', False),
    ({}, 'http://worker.nextcloud/call/other', False),
    ({}, 'http://other.nextcloud/call/charlie', False),
])
def test_reaction_tier_one_uses_scoped_captured_ui(saved, monkeypatch, task_id, options, route, expected):
    monkeypatch.setenv('WP_NEXTCLOUD_URL', 'http://worker.nextcloud')
    saved.errors['/ocs/v2.php/apps/spreed/api/v1/reaction/charlie/12'] = response([], 404)
    judged = []
    monkeypatch.setattr(dag._REGISTRY['llm_judge'], 'evaluate', lambda c, ctx: judged.append(c) or NodeResult(False, 'no saved reaction evidence'))
    context = saved.context(task_id)
    context.ui_evidence = reaction_evidence(route, **options)
    result = TieredRubricEvaluator().evaluate(node_config(task_id, 'r4'), context)
    assert result.passed is expected
    assert len(judged) == (0 if expected else 1)
    assert f'decided_by=T{1 if expected else 2}:' in result.reason


@pytest.mark.parametrize('failure', ['no_reaction', 'missing_vote', 'early_reaction', 'preexisting_room', 'revoked_reaction'])
def test_reaction_ui_cannot_bypass_native_requirements(saved, monkeypatch, failure):
    monkeypatch.setenv('WP_NEXTCLOUD_URL', 'http://worker.nextcloud')
    if failure == 'no_reaction': saved.reactions = {}
    elif failure == 'missing_vote': saved.poll['votedSelf'] = [0]
    elif failure == 'early_reaction': saved.reactions['✅'][0]['timestamp'] = 89
    elif failure == 'preexisting_room': saved.rooms_before['charlie'] = {'type': 2}
    else:
        saved.errors['/ocs/v2.php/apps/spreed/api/v1/reaction/charlie/12'] = response([], 404)
        saved.messages['charlie'][-1].update(systemMessage='reaction_deleted', message='Reaction deleted by author')
        monkeypatch.setattr(dag._REGISTRY['llm_judge'], 'evaluate', lambda c, ctx: NodeResult(False, 'reaction revoked'))
    context = saved.context('165')
    context.ui_evidence = reaction_evidence('http://worker.nextcloud/call/charlie')
    result = TieredRubricEvaluator().evaluate(node_config('165', 'r4'), context)
    assert not result.passed
    assert ('decided_by=T2:llm_judge' if failure == 'revoked_reaction' else 'decided_by=T0:nextcloud_saved_state') in result.reason


@pytest.mark.parametrize('duplicate', [False, True])
def test_talk_snapshot_uses_current_worker_and_rejects_duplicate_tokens(monkeypatch, duplicate):
    from webarena_pro_core.eval.providers import talk
    monkeypatch.setenv('WP_NEXTCLOUD_URL', 'http://active-worker.nextcloud')
    def get(url, **kwargs):
        assert url == 'http://active-worker.nextcloud/ocs/v2.php/apps/spreed/api/v4/room'
        return response([{'token': 'room', 'type': 2}] * (2 if duplicate else 1))
    monkeypatch.setattr(talk.requests, 'get', get)
    if duplicate:
        with pytest.raises(ValueError, match='duplicate token'):
            talk.TalkRoomsProvider().fetch('nextcloud', {'user': USER})
    else:
        assert list(talk.TalkRoomsProvider().fetch('nextcloud', {'user': USER}).entries) == ['room']
