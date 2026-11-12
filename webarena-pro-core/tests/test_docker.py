from types import SimpleNamespace

import pytest
from docker.errors import APIError, ImageNotFound, NotFound

from webarena_pro_core.docker import DockerContainerManager, ImagePullResult


@pytest.fixture(autouse=True)
def isolated_docker_platform(monkeypatch):
    monkeypatch.delenv("WP_DOCKER_PLATFORM", raising=False)
    monkeypatch.delenv("DOCKER_DEFAULT_PLATFORM", raising=False)
    monkeypatch.setenv("WP_DOCKER_FALLBACK_PLATFORM", "")


class FakeImageCollection:
    def __init__(self, *, available=False, image_id="sha256:old"):
        self.available = available
        self.image_id = image_id

    def get(self, image):
        if not self.available:
            raise ImageNotFound("missing")
        return SimpleNamespace(id=self.image_id)


class FakeDockerAPI:
    def __init__(
        self, images, *, first_pull_error=None, first_pull_events=None,
        events=None, pulled_id="sha256:new",
    ):
        self.images = images
        self.first_pull_error = first_pull_error
        self.first_pull_events = first_pull_events
        self.events = events or [{"status": "Download complete"}]
        self.pulled_id = pulled_id
        self.pulls = []

    def pull(self, image, *, stream, decode, **kwargs):
        assert stream is True
        assert decode is True
        self.pulls.append((image, kwargs))
        if len(self.pulls) == 1 and self.first_pull_error is not None:
            raise self.first_pull_error
        events = self.first_pull_events if len(self.pulls) == 1 else None
        yield from self.events if events is None else events
        self.images.available = True
        self.images.image_id = self.pulled_id


class FakeContainer:
    name = "jobportal"
    status = "running"
    attrs = {"State": {}}

    def reload(self):
        pass


class FakeContainerCollection:
    def __init__(self):
        self.runs = []

    def get(self, name):
        raise NotFound("missing")

    def run(self, **kwargs):
        self.runs.append(kwargs)
        return FakeContainer()


class FakeDockerClient:
    def __init__(self, images, **pull_options):
        self.images = images
        self.api = FakeDockerAPI(images, **pull_options)
        self.containers = FakeContainerCollection()


def make_manager(client):
    manager = DockerContainerManager.__new__(DockerContainerManager)
    manager.client = client
    return manager


def test_missing_image_retries_amd64_when_arm_manifest_is_missing(monkeypatch):
    monkeypatch.delenv("WP_DOCKER_PLATFORM", raising=False)
    monkeypatch.delenv("DOCKER_DEFAULT_PLATFORM", raising=False)
    monkeypatch.setenv("WP_DOCKER_FALLBACK_PLATFORM", "linux/amd64")
    client = FakeDockerClient(
        FakeImageCollection(),
        first_pull_error=APIError("no matching manifest for linux/arm64/v8"),
    )
    manager = make_manager(client)

    manager.ensure_container_running(name="jobportal", image="webarenapro/jobportal:latest")

    assert client.api.pulls == [
        ("webarenapro/jobportal:latest", {}),
        ("webarenapro/jobportal:latest", {"platform": "linux/amd64"}),
    ]
    assert client.containers.runs[0]["platform"] == "linux/amd64"


def test_explicit_platform_is_used_for_pull_and_run(monkeypatch):
    monkeypatch.setenv("WP_DOCKER_PLATFORM", "linux/amd64")
    client = FakeDockerClient(FakeImageCollection())
    manager = make_manager(client)

    manager.ensure_container_running(name="mattermost", image="webarenapro/mattermost:latest")

    assert client.api.pulls == [
        ("webarenapro/mattermost:latest", {"platform": "linux/amd64"}),
    ]
    assert client.containers.runs[0]["platform"] == "linux/amd64"


def test_existing_local_image_runs_without_platform_override(monkeypatch):
    monkeypatch.delenv("WP_DOCKER_PLATFORM", raising=False)
    monkeypatch.delenv("DOCKER_DEFAULT_PLATFORM", raising=False)
    client = FakeDockerClient(FakeImageCollection(available=True))
    manager = make_manager(client)

    manager.ensure_container_running(name="x-lite", image="webarenapro/x-lite:latest")

    assert client.api.pulls == []
    assert "platform" not in client.containers.runs[0]


@pytest.mark.parametrize(
    ("available", "local_id", "status"),
    [
        (False, "sha256:old", "pulled"),
        (True, "sha256:old", "updated"),
        (True, "sha256:new", "already-current"),
    ],
)
def test_explicit_pull_always_checks_registry_and_compares_image_ids(available, local_id, status):
    client = FakeDockerClient(FakeImageCollection(available=available, image_id=local_id))
    manager = make_manager(client)

    result = manager.pull_image("webarenapro/nextcloud:latest")

    assert result == ImagePullResult(status=status, platform=None)
    assert client.api.pulls == [("webarenapro/nextcloud:latest", {})]
    assert client.images.image_id == "sha256:new"


@pytest.mark.parametrize(
    "pull_options",
    [
        {"first_pull_error": APIError("registry unavailable")},
        {"events": [{"status": "Pulling"}, {"error": "registry unavailable"}]},
        {"events": [{"errorDetail": {"message": "registry unavailable"}}]},
    ],
)
def test_explicit_pull_reports_registry_errors_even_with_cached_image(monkeypatch, pull_options):
    monkeypatch.setenv("WP_DOCKER_FALLBACK_PLATFORM", "linux/amd64")
    client = FakeDockerClient(FakeImageCollection(available=True), **pull_options)
    manager = make_manager(client)

    with pytest.raises(APIError, match="registry unavailable"):
        manager.pull_image("webarenapro/nextcloud:latest")

    assert client.api.pulls == [("webarenapro/nextcloud:latest", {})]
    assert client.images.image_id == "sha256:old"


@pytest.mark.parametrize("variable", ["WP_DOCKER_PLATFORM", "DOCKER_DEFAULT_PLATFORM"])
def test_explicit_pull_honors_requested_platform_with_cached_image(monkeypatch, variable):
    monkeypatch.setenv(variable, "linux/amd64")
    client = FakeDockerClient(FakeImageCollection(available=True))

    result = make_manager(client).pull_image("webarenapro/nextcloud:latest")

    assert result == ImagePullResult(status="updated", platform="linux/amd64")
    assert client.api.pulls == [
        ("webarenapro/nextcloud:latest", {"platform": "linux/amd64"}),
    ]


def test_explicit_pull_falls_back_after_streamed_manifest_error(monkeypatch):
    monkeypatch.setenv("WP_DOCKER_FALLBACK_PLATFORM", "linux/amd64")
    client = FakeDockerClient(
        FakeImageCollection(available=True),
        first_pull_events=[{"error": "no matching manifest for linux/arm64/v8"}],
    )

    result = make_manager(client).pull_image("webarenapro/nextcloud:latest")

    assert result == ImagePullResult(status="updated", platform="linux/amd64")
    assert client.api.pulls == [
        ("webarenapro/nextcloud:latest", {}),
        ("webarenapro/nextcloud:latest", {"platform": "linux/amd64"}),
    ]


@pytest.mark.parametrize(
    ("configured", "fallback"),
    [("linux/arm64", "linux/amd64"), (None, "")],
)
def test_explicit_pull_does_not_override_requested_platform_or_disabled_fallback(
    monkeypatch, configured, fallback,
):
    if configured:
        monkeypatch.setenv("WP_DOCKER_PLATFORM", configured)
    monkeypatch.setenv("WP_DOCKER_FALLBACK_PLATFORM", fallback)
    client = FakeDockerClient(
        FakeImageCollection(available=True),
        first_pull_error=APIError("no matching manifest for linux/arm64/v8"),
    )

    with pytest.raises(APIError, match="no matching manifest"):
        make_manager(client).pull_image("webarenapro/nextcloud:latest")

    options = {"platform": configured} if configured else {}
    assert client.api.pulls == [("webarenapro/nextcloud:latest", options)]


def test_explicit_pull_propagates_fallback_failure(monkeypatch):
    monkeypatch.setenv("WP_DOCKER_FALLBACK_PLATFORM", "linux/amd64")
    client = FakeDockerClient(
        FakeImageCollection(available=True),
        first_pull_error=APIError("no matching manifest for linux/arm64/v8"),
        events=[{"error": "registry unavailable"}],
    )

    with pytest.raises(APIError, match="registry unavailable"):
        make_manager(client).pull_image("webarenapro/nextcloud:latest")

    assert len(client.api.pulls) == 2
    assert client.images.image_id == "sha256:old"


def test_reset_container_applies_run_hooks_and_site_options():
    client = FakeDockerClient(FakeImageCollection(available=True))
    manager = make_manager(client)
    started = []

    manager.reset_container(
        name="penpot",
        image="webarenapro/penpot:latest",
        ports={"9001/tcp": 9001},
        volumes={"/tmp/config": {"bind": "/config", "mode": "ro"}},
        run_options={
            "entrypoint": "/usr/bin/supervisord",
            "command": ["-c", "/etc/supervisor/supervisord.conf"],
        },
        post_start=lambda container: started.append(container),
    )

    assert client.containers.runs == [
        {
            "image": "webarenapro/penpot:latest",
            "name": "penpot",
            "detach": True,
            "environment": None,
            "ports": {"9001/tcp": 9001},
            "labels": None,
            "network": None,
            "volumes": {"/tmp/config": {"bind": "/config", "mode": "ro"}},
            "entrypoint": "/usr/bin/supervisord",
            "command": ["-c", "/etc/supervisor/supervisord.conf"],
        }
    ]
    assert len(started) == 1
    assert started[0].name == "jobportal"


def test_start_container_applies_site_run_hooks():
    client = FakeDockerClient(FakeImageCollection(available=True))
    manager = make_manager(client)
    started = []
    manager.ensure_container_running(
        name="jobportal", image="webarenapro/jobportal:latest",
        volumes={"/tmp/config": {"bind": "/config", "mode": "ro"}},
        run_options={"init": True}, post_start=started.append,
    )
    assert client.containers.runs[0]["init"] is True
    assert client.containers.runs[0]["volumes"]["/tmp/config"]["bind"] == "/config"
    assert len(started) == 1
