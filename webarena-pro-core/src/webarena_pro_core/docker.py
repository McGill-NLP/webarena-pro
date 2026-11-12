from __future__ import annotations

import logging
import os
import platform
import time
from collections.abc import Mapping
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Literal

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from requests.exceptions import ConnectionError, Timeout

from .runtime_locks import docker_lifecycle_slot, docker_timeout, runtime_lock

logger = logging.getLogger(__name__)
LIFECYCLE_ATTEMPTS = 8


class _LifecyclePending(RuntimeError):
	pass


def _retryable_lifecycle_error(error: Exception) -> bool:
	if isinstance(error, ImageNotFound):
		return False
	if isinstance(error, (_LifecyclePending, NotFound, Timeout)):
		return True
	message = str(error).lower()
	if isinstance(error, ConnectionError):
		return any(part in message for part in ("timed out", "connection reset", "connection aborted"))
	return (
		isinstance(error, APIError)
		and error.status_code == 409
		and (
			("container name" in message and "already in use" in message)
			or any(part in message for part in (
				"removal of container", "removal is already in progress",
				"marked for removal", "already started", "is not running",
			))
		)
	)


def _retry_lifecycle(operation: Callable[[], Any], *, action: str, name: str) -> Any:
	for attempt in range(1, LIFECYCLE_ATTEMPTS + 1):
		try:
			return operation()
		except Exception as error:
			if not _retryable_lifecycle_error(error):
				raise
			if attempt == LIFECYCLE_ATTEMPTS:
				raise RuntimeError(
					f"Docker {action} for container {name!r} failed after {attempt} attempts "
					f"(request timeout={docker_timeout():g}s): {error}"
				) from error
			logger.warning(
				"Docker %s for %s raced with lifecycle work (attempt %d/%d): %s; reconciling state",
				action, name, attempt, LIFECYCLE_ATTEMPTS, error,
			)
			time.sleep(min(0.5 * 2 ** (attempt - 1), 4))


def _coordinated_lifecycle(method):
	@wraps(method)
	def coordinated(self, *args, **kwargs):
		name = kwargs.get("name") or args[0]
		# Wait for the container first, without consuming a global permit.
		with runtime_lock(f"container:{name}"), docker_lifecycle_slot():
			return method(self, *args, **kwargs)
	return coordinated


DOCKER_PLATFORM_ENV_VAR = "WP_DOCKER_PLATFORM"
DOCKER_FALLBACK_PLATFORM_ENV_VAR = "WP_DOCKER_FALLBACK_PLATFORM"
DEFAULT_ARM_FALLBACK_PLATFORM = "linux/amd64"


def configured_docker_platform() -> str | None:
	value = (
		os.environ.get(DOCKER_PLATFORM_ENV_VAR)
		or os.environ.get("DOCKER_DEFAULT_PLATFORM")
		or ""
	).strip()
	return value or None


def default_fallback_docker_platform() -> str | None:
	overridden = os.environ.get(DOCKER_FALLBACK_PLATFORM_ENV_VAR)
	if overridden is not None:
		return overridden.strip() or None

	machine = platform.machine().lower()
	if machine in {"arm64", "aarch64"}:
		return DEFAULT_ARM_FALLBACK_PLATFORM
	return None


def _is_platform_manifest_error(error: Exception) -> bool:
	message = str(error).lower()
	return (
		"no matching manifest" in message
		or "no match for platform" in message
		or "not found for platform" in message
	)


@dataclass
class ContainerInfo:
	name: str
	status: str
	health: str = "unknown"


@dataclass(frozen=True)
class ImagePullResult:
	status: Literal["pulled", "updated", "already-current"]
	platform: str | None


class DockerContainerManager:
	def __init__(self) -> None:
		self.client = docker.from_env(timeout=docker_timeout())

	@staticmethod
	def _normalize_container_port(port: str) -> str:
		return port if "/" in port else f"{port}/tcp"

	def _has_expected_port_bindings(
		self,
		*,
		container: Any,
		expected_ports: dict[str, int],
	) -> bool:
		container.reload()
		actual_ports = (
			(container.attrs or {}).get("NetworkSettings", {}).get("Ports", {}) or {}
		)
		if not isinstance(actual_ports, dict):
			return False

		for container_port, expected_host_port in expected_ports.items():
			port_key = self._normalize_container_port(str(container_port))
			bindings = actual_ports.get(port_key)
			if not isinstance(bindings, list) or not bindings:
				return False
			host_port = bindings[0].get("HostPort")
			if str(host_port) != str(expected_host_port):
				return False

		return True

	def _has_expected_labels(
		self,
		*,
		container: Any,
		expected_labels: dict[str, str],
	) -> bool:
		container.reload()
		labels = (container.attrs or {}).get("Config", {}).get("Labels", {}) or {}
		for key, expected_value in expected_labels.items():
			if str(labels.get(key)) != str(expected_value):
				return False
		return True

	def _has_expected_environment(
		self,
		*,
		container: Any,
		expected_environment: dict[str, str],
	) -> bool:
		container.reload()
		raw_environment = (
			(container.attrs or {})
			.get("Config", {})
			.get("Env")
			or []
		)
		environment = {}
		for entry in raw_environment:
			key, _, value = str(entry).partition("=")
			environment[key] = value
		for key, expected_value in expected_environment.items():
			if environment.get(key) != str(expected_value):
				return False
		return True

	def _has_expected_network(
		self,
		*,
		container: Any,
		network: str,
	) -> bool:
		container.reload()
		networks = (
			(container.attrs or {})
			.get("NetworkSettings", {})
			.get("Networks", {})
			or {}
		)
		return network in networks

	def image_architecture(self, image: str) -> str | None:
		try:
			image_obj = self.client.images.get(image)
		except ImageNotFound:
			return None
		architecture = (image_obj.attrs or {}).get("Architecture")
		return str(architecture) if architecture else None

	def build_image(
		self,
		*,
		path: str,
		tag: str,
		log: Callable[[str], None] | None = None,
	) -> str | None:
		if log is None:
			log = lambda msg: None
		log(f"Building local image '{tag}' from {path} ...")
		image, build_logs = self.client.images.build(path=path, tag=tag, rm=True)
		for entry in build_logs:
			stream = entry.get("stream") if isinstance(entry, dict) else None
			if stream:
				line = str(stream).strip()
				if line:
					log(line)
		architecture = (image.attrs or {}).get("Architecture")
		log(f"Built local image '{tag}'.")
		return str(architecture) if architecture else None

	def _has_expected_image(
		self,
		*,
		container: Any,
		image: str,
	) -> bool:
		try:
			image_obj = self.client.images.get(image)
		except ImageNotFound:
			return True

		container.reload()
		expected_id = getattr(image_obj, "id", None) or (image_obj.attrs or {}).get("Id")
		if not expected_id:
			return True
		actual_id = (container.attrs or {}).get("Image")
		return str(actual_id) == str(expected_id)

	def _container_needs_recreate(
		self,
		*,
		container: Any,
		image: str | None,
		environment: dict[str, str] | None,
		ports: dict[str, int] | None,
		labels: dict[str, str] | None,
		network: str | None,
	) -> bool:
		if image and not self._has_expected_image(container=container, image=image):
			return True
		if ports and not self._has_expected_port_bindings(
			container=container,
			expected_ports=ports,
		):
			return True
		if labels and not self._has_expected_labels(
			container=container,
			expected_labels=labels,
		):
			return True
		if environment and not self._has_expected_environment(
			container=container,
			expected_environment=environment,
		):
			return True
		if network and not self._has_expected_network(
			container=container,
			network=network,
		):
			return True
		return False

	def _run_container(
		self,
		*,
		image: str,
		name: str,
		environment: dict[str, str] | None,
		ports: dict[str, int] | None,
		labels: dict[str, str] | None,
		network: str | None,
		platform_name: str | None,
		volumes: dict[str, Any] | None = None,
		run_options: Mapping[str, Any] | None = None,
	) -> Any:
		options: dict[str, Any] = {
			"image": image,
			"name": name,
			"detach": True,
			"environment": environment,
			"ports": ports,
			"labels": labels,
			"network": network,
		}
		if volumes:
			options["volumes"] = volumes
		if platform_name:
			options["platform"] = platform_name
		if run_options:
			reserved = set(options).intersection(run_options)
			if reserved:
				raise ValueError(
					"Container run options cannot override managed fields: "
					+ ", ".join(sorted(reserved))
				)
			options.update(run_options)
		return self.client.containers.run(**options)

	def remove_containers_using_host_ports(
		self,
		*,
		host_ports: set[int],
		except_name: str | None = None,
	) -> None:
		"""Remove containers occupying one of ``host_ports``.

		This is used when a worker-specific container must claim a port left by
		an older local development container.
		"""
		raw_containers = self.client.api.containers(all=True)
		for raw in raw_containers:
			names = raw.get("Names") or []
			name = names[0].lstrip("/") if names else ""
			if not name or name == except_name:
				continue
			ports = raw.get("Ports") or []
			if not any(
				int(port.get("PublicPort") or 0) in host_ports for port in ports
			):
				continue
			container_id = raw.get("Id")
			if not container_id:
				# Never resolve a stale listing by name: a replacement may have
				# claimed that name without owning any of the conflicting ports.
				continue
			try:
				container = self.client.containers.get(container_id)
				container.reload()
				bindings = (container.attrs or {}).get("NetworkSettings", {}).get("Ports") or {}
				if any(
					int(binding.get("HostPort") or 0) in host_ports
					for entries in bindings.values() for binding in (entries or [])
				):
					self._remove_container(container)
			except NotFound:
				continue

	def ensure_image_available(
		self,
		image: str,
		*,
		log: Callable[[str], None] | None = None,
	) -> str | None:
		"""Use the local image when available; otherwise pull it from the registry."""
		try:
			self.client.images.get(image)
			return configured_docker_platform()
		except ImageNotFound:
			pass

		_, platform_name = self._pull_image(image, log=log)
		return platform_name

	def pull_image(
		self,
		image: str,
		*,
		log: Callable[[str], None] | None = None,
	) -> ImagePullResult:
		"""Always check the registry and report whether the local image changed."""
		try:
			previous_id = self.client.images.get(image).id
		except ImageNotFound:
			previous_id = None

		pulled_image, platform_name = self._pull_image(image, log=log)
		if previous_id is None:
			status = "pulled"
		elif previous_id == pulled_image.id:
			status = "already-current"
		else:
			status = "updated"
		return ImagePullResult(status=status, platform=platform_name)

	def _pull_image_for_platform(self, image: str, platform_name: str | None) -> Any:
		pull_options: dict[str, str] = {}
		if platform_name:
			pull_options["platform"] = platform_name
		# The SDK's images.pull() discards stream events, including errors, then
		# inspects the local tag. A failed refresh can therefore look successful
		# when an older image exists. Check every event before inspecting the tag.
		for event in self.client.api.pull(image, stream=True, decode=True, **pull_options):
			error = event.get("error") or (event.get("errorDetail") or {}).get("message")
			if error:
				raise APIError(str(error))
		return self.client.images.get(image)

	def _pull_image(
		self,
		image: str,
		*,
		log: Callable[[str], None] | None = None,
	) -> tuple[Any, str | None]:
		if log is None:
			log = lambda msg: None

		configured_platform = configured_docker_platform()
		if configured_platform:
			log(f"Pulling image '{image}' for {configured_platform} ...")
		else:
			log(f"Pulling image '{image}' ...")

		try:
			return self._pull_image_for_platform(image, configured_platform), configured_platform
		except APIError as error:
			fallback_platform = default_fallback_docker_platform()
			if configured_platform or not fallback_platform or not _is_platform_manifest_error(error):
				raise

			log(
				f"No native image manifest found for '{image}', retrying for {fallback_platform} ..."
			)
			return self._pull_image_for_platform(image, fallback_platform), fallback_platform

	def _to_container_info(self, container: Any) -> ContainerInfo:
		container.reload()
		state = (container.attrs or {}).get("State", {})
		health_state = state.get("Health", {})
		health_status = health_state.get("Status", "unknown")
		return ContainerInfo(
			name=container.name,
			status=container.status,
			health=health_status,
		)

	def get_container_info(self, name: str) -> ContainerInfo:
		container = self.client.containers.get(name)
		return self._to_container_info(container)

	def list_containers(self) -> list[ContainerInfo]:
		containers = self.client.containers.list(all=True)
		return [self._to_container_info(container) for container in containers]

	@_coordinated_lifecycle
	def ensure_container_running(
		self,
		*,
		name: str,
		image: str,
		environment: dict[str, str] | None = None,
		ports: dict[str, int] | None = None,
		labels: dict[str, str] | None = None,
		network: str | None = None,
		volumes: dict[str, Any] | None = None,
		run_options: Mapping[str, Any] | None = None,
		post_start: Callable[[Any], None] | None = None,
		log: Callable[[str], None] | None = None,
	) -> ContainerInfo:
		if log is None:
			log = lambda msg: None

		def reconcile():
			try:
				container = self.client.containers.get(name)
				container.reload()
			except NotFound:
				container = None
			if container is not None:
				if container.status == "removing":
					raise _LifecyclePending("container removal is still in progress")
				if self._container_needs_recreate(
					container=container, image=image, environment=environment,
					ports=ports, labels=labels, network=network,
				):
					log("Container settings are outdated, recreating ...")
					self.ensure_image_available(image, log=log)
					self._remove_container(container)
					container = None
			if container is None:
				platform_name = self.ensure_image_available(image, log=log)
				log("Creating and starting container ...")
				container = self._run_container(
					image=image, name=name, environment=environment,
					ports=ports, labels=labels, network=network,
					platform_name=platform_name, volumes=volumes, run_options=run_options,
				)
			elif container.status != "running":
				log("Container exists but is stopped, starting ...")
				container.start()
			else:
				log("Container already running.")
			return container, self._to_container_info(container)

		container, info = _retry_lifecycle(reconcile, action="ensure running", name=name)
		# Hooks may have their own effects; never replay them after an SDK timeout.
		if post_start is not None:
			post_start(container)
		return info

	@_coordinated_lifecycle
	def reset_container(
		self,
		*,
		name: str,
		image: str,
		environment: dict[str, str] | None = None,
		ports: dict[str, int] | None = None,
		labels: dict[str, str] | None = None,
		network: str | None = None,
		volumes: dict[str, Any] | None = None,
		run_options: Mapping[str, Any] | None = None,
		post_start: Callable[[Any], None] | None = None,
		remove_port_conflicts: bool = False,
		log: Callable[[str], None] | None = None,
	) -> ContainerInfo:
		self.ensure_image_available(image, log=log)
		self.stop_container(name)
		if remove_port_conflicts and ports:
			self.remove_containers_using_host_ports(
				host_ports={int(port) for port in ports.values()}, except_name=name,
			)
		# A timed-out create may have succeeded. Reconcile it instead of removing
		# a freshly created replacement on every retry.
		return self.ensure_container_running(
			name=name, image=image, environment=environment, ports=ports,
			labels=labels, network=network, volumes=volumes,
			run_options=run_options, post_start=post_start, log=log,
		)

	@staticmethod
	def _remove_container(container: Any) -> None:
		def remove():
			try:
				# Retain this object/ID across retries so a replacement that acquires
				# the same name is never removed by an old stop operation.
				# Docker removes anonymous volumes only; named volumes and bind
				# mounts remain intact. Per-task resets must not orphan volumes.
				container.remove(force=True, v=True)
			except NotFound:
				pass
		with docker_lifecycle_slot():
			_retry_lifecycle(remove, action="remove", name=container.name)

	@_coordinated_lifecycle
	def stop_container(self, name: str) -> None:
		def inspect():
			try:
				return self.client.containers.get(name)
			except NotFound:
				return None
		container = _retry_lifecycle(inspect, action="inspect before removal", name=name)
		if container is not None:
			self._remove_container(container)

	def health_check(self, name: str) -> dict[str, str]:
		info = self.get_container_info(name)
		return {
			"name": info.name,
			"status": info.status,
			"health": info.health,
		}

	def get_container_url(
		self,
		*,
		name: str,
		preferred_container_ports: list[str] | None = None,
		host: str = "localhost",
		scheme: str = "http",
	) -> str | None:
		container = self.client.containers.get(name)
		container.reload()
		ports = (container.attrs or {}).get("NetworkSettings", {}).get("Ports", {}) or {}
		if not isinstance(ports, dict) or not ports:
			return None

		ordered_port_keys: list[str] = []
		if preferred_container_ports:
			ordered_port_keys.extend(
				self._normalize_container_port(port)
				for port in preferred_container_ports
			)
		ordered_port_keys.extend(str(port_key) for port_key in ports.keys())

		seen: set[str] = set()
		for port_key in ordered_port_keys:
			if port_key in seen:
				continue
			seen.add(port_key)
			bindings = ports.get(port_key)
			if not isinstance(bindings, list) or not bindings:
				continue
			host_port = bindings[0].get("HostPort")
			if not host_port:
				continue
			return f"{scheme}://{host}:{host_port}"

		return None
