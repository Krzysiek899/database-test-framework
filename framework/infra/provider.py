"""
InfraProvider – Context Manager for Docker container lifecycle.

Responsibilities:
  • Pull the requested image (if missing).
  • Start a container with port mapping, env vars, and resource limits.
  • Poll a health-check command until the engine is ready.
  • Stop + remove the container on exit (even on exceptions).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import docker
from docker.errors import NotFound, ImageNotFound, DockerException
from docker.models.containers import Container

logger = logging.getLogger(__name__)

def _get_docker_client() -> docker.DockerClient:
    """Return a Docker client, or raise a human-friendly error."""
    try:
        client = docker.from_env()
        client.ping()          # force an actual round-trip immediately
        return client
    except DockerException as exc:
        short = str(exc)[:43]
        raise RuntimeError("Docker is not reachable".format(error=short)) from exc


class InfraProvider:
    """Manages a single database container through the Docker SDK."""

    def __init__(self, engine_name: str, engine_cfg: Dict[str, Any]) -> None:
        self.engine_name = engine_name
        self.cfg = engine_cfg
        self.client: docker.DockerClient = _get_docker_client()
        self.container: Optional[Container] = None

    # ------------------------------------------------------------------
    # Context-manager interface
    # ------------------------------------------------------------------
    def __enter__(self) -> "InfraProvider":
        self._pull_image()
        self._start_container()
        self._wait_healthy()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.teardown()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def get_host_port(self) -> int:
        """Return the host port mapped to the engine's internal port."""
        return int(self.cfg["host_port"])

    def get_container(self) -> Container:
        assert self.container is not None
        return self.container

    def teardown(self) -> None:
        if self.container is not None:
            name = self.container.name
            try:
                self.container.stop(timeout=5)
                logger.info("Stopped container %s", name)
            except Exception:
                logger.warning("Failed to stop container %s gracefully", name)
            try:
                self.container.remove(force=True)
                logger.info("Removed container %s", name)
            except NotFound:
                pass
            self.container = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _pull_image(self) -> None:
        image = self.cfg["image"]
        try:
            self.client.images.get(image)
            logger.info("Image %s already present", image)
        except ImageNotFound:
            logger.info("Pulling image %s …", image)
            self.client.images.pull(image)
            logger.info("Image %s pulled", image)

    def _start_container(self) -> None:
        image = self.cfg["image"]
        internal_port = self.cfg["port"]
        host_port = self.cfg["host_port"]
        environment = self.cfg.get("environment", {})
        resources = self.cfg.get("resources", {})

        container_name = f"bench_{self.engine_name}"

        # Remove stale container with the same name (if any)
        try:
            old = self.client.containers.get(container_name)
            old.remove(force=True)
        except NotFound:
            pass

        self.container = self.client.containers.run(
            image,
            name=container_name,
            detach=True,
            ports={f"{internal_port}/tcp": host_port},
            environment=environment,
            mem_limit=resources.get("mem_limit"),
            nano_cpus=int(resources.get("cpus", 1) * 1e9),
            remove=False,
        )
        logger.info(
            "Started container %s (%s) on port %s",
            container_name,
            image,
            host_port,
        )

    def _wait_healthy(self) -> None:
        hc = self.cfg.get("healthcheck", {})
        test_cmd = hc.get("test", "true")
        interval = hc.get("interval", 2)
        retries = hc.get("retries", 15)
        start_period_sec = hc.get("start_period_sec", 0)

        assert self.container is not None

        if start_period_sec > 0:
            logger.info("Waiting %d seconds before initiating healthcheck for %s", start_period_sec, self.engine_name)
            time.sleep(start_period_sec)

        for attempt in range(1, retries + 1):
            exit_code, _ = self.container.exec_run(test_cmd)
            if exit_code == 0:
                logger.info(
                    "Engine %s healthy after %d attempt(s)", self.engine_name, attempt
                )
                return
            logger.debug(
                "Healthcheck attempt %d/%d for %s failed",
                attempt,
                retries,
                self.engine_name,
            )
            time.sleep(interval)

        raise RuntimeError(
            f"Engine {self.engine_name} did not become healthy "
            f"after {retries} attempts"
        )
