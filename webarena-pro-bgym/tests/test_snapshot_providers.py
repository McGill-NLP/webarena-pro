import json
from xml.etree.ElementTree import ParseError

import pytest
import requests
from fsspec.spec import AbstractFileSystem

from webarena_pro_core.eval.providers import (
    activity,
    caldav,
    carddav,
    metabase_cards,
    metabase_common,
    metabase_dashboards,
    metabase_timeline_events,
    ocs_users,
    talk,
    webdav,
)


PROVIDERS = [
    (activity.ActivityLogProvider, "nextcloud"),
    (carddav.CardDAVContactsProvider, "nextcloud"),
    (caldav.CalDAVEventsProvider, "nextcloud"),
    (talk.TalkRoomsProvider, "nextcloud"),
    (ocs_users.OCSUsersProvider, "nextcloud"),
    (metabase_cards.MetabaseCardsProvider, "metabase"),
    (metabase_dashboards.MetabaseDashboardsProvider, "metabase"),
    (metabase_timeline_events.MetabaseTimelineEventsProvider, "metabase"),
]


def response(status=200, body=""):
    result = requests.Response()
    result.status_code = status
    result._content = body.encode()
    result.url = "http://example.test/api"
    return result


def ocs_body(data, status="ok", code=200):
    return json.dumps(
        {"ocs": {"meta": {"status": status, "statuscode": code}, "data": data}}
    )


@pytest.fixture
def mock_http(monkeypatch):
    for module in (activity, carddav, caldav, talk, webdav):
        monkeypatch.setattr(module, "_get_auth", lambda *args: ("user", "password"))
    monkeypatch.setattr(
        ocs_users, "_get_admin_auth", lambda *args: ("user", "password")
    )
    monkeypatch.setattr(metabase_common, "session_token", lambda *args: "test-session")

    def install(result):
        def request(*args, **kwargs):
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(requests, "get", request)
        monkeypatch.setattr(requests, "request", request)

    return install


@pytest.mark.parametrize("provider,site", PROVIDERS)
@pytest.mark.parametrize("status", [401, 404, 500])
def test_http_failures_are_not_empty_snapshots(mock_http, provider, site, status):
    mock_http(response(status, "unavailable"))

    with pytest.raises(requests.HTTPError):
        provider().fetch(site, {"user": "test"})


@pytest.mark.parametrize("provider,site", PROVIDERS)
def test_transport_failures_propagate(mock_http, provider, site):
    mock_http(requests.ConnectionError("offline"))

    with pytest.raises(requests.ConnectionError, match="offline"):
        provider().fetch(site, {"user": "test"})


@pytest.mark.parametrize("provider,site", PROVIDERS)
def test_malformed_responses_are_not_empty_snapshots(mock_http, provider, site):
    mock_http(response(200, "not a valid response"))

    with pytest.raises((ValueError, ParseError)):
        provider().fetch(site, {"user": "test"})


@pytest.mark.parametrize("provider,site", PROVIDERS)
def test_successful_empty_collections_remain_valid(mock_http, provider, site):
    if provider in {carddav.CardDAVContactsProvider, caldav.CalDAVEventsProvider}:
        result = response(207, '<d:multistatus xmlns:d="DAV:"/>')
    elif site == "metabase":
        result = response(200, "[]")
    else:
        result = response(
            200,
            ocs_body({"users": []} if provider is ocs_users.OCSUsersProvider else []),
        )
    mock_http(result)

    snapshot = provider().fetch(site, {"user": "test"})

    assert snapshot.entries == {}
    assert snapshot.error is None


@pytest.mark.parametrize("status", [204, 304])
def test_documented_empty_activity_statuses(mock_http, status):
    mock_http(response(status))

    snapshot = activity.ActivityLogProvider().fetch("nextcloud", {"user": "test"})

    assert snapshot.entries == {}
    assert snapshot.error is None


@pytest.mark.parametrize(
    "provider",
    [activity.ActivityLogProvider, talk.TalkRoomsProvider, ocs_users.OCSUsersProvider],
)
@pytest.mark.parametrize(
    "body", [ocs_body([], "failure", 996), "{}", "null", ocs_body(None)]
)
def test_ocs_errors_and_missing_data_propagate(mock_http, provider, body):
    mock_http(response(200, body))

    with pytest.raises(ValueError):
        provider().fetch("nextcloud", {"user": "test"})


@pytest.mark.parametrize(
    "provider",
    [
        metabase_cards.MetabaseCardsProvider,
        metabase_dashboards.MetabaseDashboardsProvider,
        metabase_timeline_events.MetabaseTimelineEventsProvider,
    ],
)
def test_metabase_error_objects_are_not_empty_listings(mock_http, provider):
    mock_http(response(200, '{"error": "unavailable"}'))

    with pytest.raises(ValueError, match="not a list"):
        provider().fetch("metabase", {})


@pytest.mark.parametrize(
    "provider,body",
    [
        (metabase_cards.MetabaseCardsProvider, "[{}]"),
        (metabase_cards.MetabaseCardsProvider, "[null]"),
        (metabase_dashboards.MetabaseDashboardsProvider, "[{}]"),
        (metabase_timeline_events.MetabaseTimelineEventsProvider, '[{"id": 1}]'),
        (
            metabase_timeline_events.MetabaseTimelineEventsProvider,
            '[{"id": 1, "events": [{}]}]',
        ),
        (activity.ActivityLogProvider, ocs_body([{}])),
        (talk.TalkRoomsProvider, ocs_body([{}])),
    ],
)
def test_missing_record_identifiers_are_not_silently_omitted(mock_http, provider, body):
    mock_http(response(200, body))
    site = (
        "nextcloud"
        if provider in {activity.ActivityLogProvider, talk.TalkRoomsProvider}
        else "metabase"
    )

    with pytest.raises(ValueError):
        provider().fetch(site, {"user": "test"})


@pytest.mark.parametrize(
    "provider,site,body,entry_id",
    [
        (
            activity.ActivityLogProvider,
            "nextcloud",
            ocs_body([{"activity_id": 1}]),
            "1",
        ),
        (talk.TalkRoomsProvider, "nextcloud", ocs_body([{"token": "room"}]), "room"),
        (
            ocs_users.OCSUsersProvider,
            "nextcloud",
            ocs_body({"users": ["alice"]}, code=100),
            "alice",
        ),
        (metabase_cards.MetabaseCardsProvider, "metabase", '[{"id": 1}]', "card/1"),
        (
            metabase_timeline_events.MetabaseTimelineEventsProvider,
            "metabase",
            '[{"id": 1, "events": [{"id": 2}]}]',
            "event/2",
        ),
    ],
)
def test_successful_records_remain_available(mock_http, provider, site, body, entry_id):
    mock_http(response(200, body))

    snapshot = provider().fetch(site, {"user": "test"})

    assert set(snapshot.entries) == {entry_id}
    assert snapshot.error is None


@pytest.mark.parametrize("detail", [[], {"error": "unavailable"}, {"id": 1}])
def test_metabase_dashboard_incomplete_detail_is_unavailable(monkeypatch, detail):
    monkeypatch.setattr(
        metabase_dashboards,
        "api_get",
        lambda site, path: [{"id": 1}] if path == "/api/dashboard" else detail,
    )

    with pytest.raises(ValueError):
        metabase_dashboards.MetabaseDashboardsProvider().fetch("metabase", {})


def test_metabase_dashboard_successful_detail(monkeypatch):
    monkeypatch.setattr(
        metabase_dashboards,
        "api_get",
        lambda site, path: (
            [{"id": 1}] if path == "/api/dashboard" else {"id": 1, "dashcards": []}
        ),
    )

    snapshot = metabase_dashboards.MetabaseDashboardsProvider().fetch("metabase", {})

    assert set(snapshot.entries) == {"dashboard/1"}
    assert snapshot.entries["dashboard/1"]["card_count"] == 0


def test_metabase_dashboard_detail_failure_invalidates_whole_snapshot(monkeypatch):
    def api_get(site, path):
        if path == "/api/dashboard":
            return [{"id": 1}, {"id": 2}]
        if path.endswith("/1"):
            return {"id": 1, "name": "Available", "dashcards": []}
        raise requests.HTTPError("503 unavailable")

    monkeypatch.setattr(metabase_dashboards, "api_get", api_get)

    with pytest.raises(requests.HTTPError, match="503"):
        metabase_dashboards.MetabaseDashboardsProvider().fetch("metabase", {})


def test_talk_message_helper_does_not_hide_http_failures(mock_http):
    mock_http(response(500))

    with pytest.raises(requests.HTTPError):
        talk.fetch_talk_messages("nextcloud", "test", "room")


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize(
    "error", [OSError("listing unavailable"), FileNotFoundError("missing collection")]
)
def test_webdav_does_not_omit_failed_directory_listings(
    monkeypatch, mock_http, nested, error
):
    class FailingFilesystem(AbstractFileSystem):
        def ls(self, path, detail=True, **kwargs):
            if nested and path == "/":
                return [{"name": "/folder", "type": "directory", "size": 0}]
            raise error

    monkeypatch.setattr(
        webdav, "WebdavFileSystem", lambda *args, **kwargs: FailingFilesystem()
    )

    with pytest.raises(type(error), match=str(error)):
        webdav.WebDAVFilesProvider().fetch("nextcloud", {"user": "test"})


def test_webdav_successful_empty_listing(monkeypatch, mock_http):
    class EmptyFilesystem(AbstractFileSystem):
        def ls(self, path, detail=True, **kwargs):
            return []

        def isfile(self, path):
            return False

    monkeypatch.setattr(
        webdav, "WebdavFileSystem", lambda *args, **kwargs: EmptyFilesystem()
    )

    assert (
        webdav.WebDAVFilesProvider().fetch("nextcloud", {"user": "test"}).error is None
    )


@pytest.mark.parametrize(
    "provider", [carddav.CardDAVContactsProvider, caldav.CalDAVEventsProvider]
)
def test_dav_resource_errors_inside_multistatus_propagate(mock_http, provider):
    mock_http(
        response(
            207,
            """<d:multistatus xmlns:d="DAV:">
      <d:response><d:propstat><d:prop/>
        <d:status>HTTP/1.1 403 Forbidden</d:status>
      </d:propstat></d:response></d:multistatus>""",
        )
    )

    with pytest.raises(ValueError, match="403 Forbidden"):
        provider().fetch("nextcloud", {"user": "test"})


@pytest.mark.parametrize(
    "provider,namespace,property_name,data,expected",
    [
        (
            carddav.CardDAVContactsProvider,
            "carddav",
            "address-data",
            "BEGIN:VCARD\nVERSION:3.0\nUID:contact-1\nFN:Alice & Bob\nEND:VCARD",
            "contact-1",
        ),
        (
            caldav.CalDAVEventsProvider,
            "caldav",
            "calendar-data",
            "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:event-1\nSUMMARY:Meeting\nEND:VEVENT\nEND:VCALENDAR",
            "event-1",
        ),
    ],
)
def test_dav_valid_records_with_arbitrary_namespace_prefix(
    mock_http, provider, namespace, property_name, data, expected
):
    from xml.sax.saxutils import escape

    body = f"""<d:multistatus xmlns:d="DAV:" xmlns:x="urn:ietf:params:xml:ns:{namespace}">
      <d:response><d:propstat><d:prop><x:{property_name}>{escape(data)}</x:{property_name}></d:prop>
        <d:status>HTTP/1.1 200 OK</d:status>
      </d:propstat></d:response></d:multistatus>"""
    mock_http(response(207, body))

    snapshot = provider().fetch("nextcloud", {"user": "test"})

    assert set(snapshot.entries) == {expected}
    assert snapshot.error is None
