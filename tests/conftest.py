"""Shared fixtures and Docker JSON factories for PortSwitch unit tests."""

import json
import pytest

from portswitch import server


@pytest.fixture(autouse=True)
def clear_identified_conflicts():
    """Ensure session-scoped conflict allowlist is isolated per test."""
    server._identified_conflict_folders.clear()
    yield
    server._identified_conflict_folders.clear()


def make_container(
    *,
    cid: str = "abc123def456",
    name: str = "old-project-db-1",
    compose_project: str | None = "old-project",
    working_dir: str | None = "/work/old-project",
    host_ports: list[int] | None = None,
    mounts: list[dict] | None = None,
) -> dict:
    """Build a minimal `docker inspect` container JSON object."""
    labels: dict[str, str] = {}
    if compose_project is not None:
        labels["com.docker.compose.project"] = compose_project
    if working_dir is not None:
        labels["com.docker.compose.project.working_dir"] = working_dir

    ports_map: dict[str, list[dict]] = {}
    for p in host_ports or []:
        ports_map[f"{p}/tcp"] = [{"HostIp": "0.0.0.0", "HostPort": str(p)}]

    return {
        "Id": cid,
        "Name": f"/{name}",
        "Config": {"Labels": labels},
        "NetworkSettings": {"Ports": ports_map},
        "Mounts": mounts or [],
    }


def make_compose_config(*ports: int | str) -> str:
    """Build a minimal `docker compose config --format json` payload."""
    return json.dumps({
        "services": {
            "app": {
                "ports": [{"published": str(p), "target": 8000} for p in ports],
            }
        }
    })
