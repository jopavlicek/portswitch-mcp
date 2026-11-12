"""
---------------------------------------------------------------------------
PortSwitch MCP server
---------------------------------------------------------------------------
Talks to Claude Code over stdin/stdout, so never print() here.
Use logging (it writes to stderr) for debug output.
"""

import json
import logging
import os
import socket
import subprocess

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("portswitch")

mcp = MCPServer(
    "portswitch",
    instructions=(
        "PortSwitch resolves port conflicts between local Docker Compose projects. "
        "When a project fails to start because a port is already in use: "
        "1) call check_conflicts with the folder of the project you are starting, "
        "2) tell the user which project holds the port, "
        "3) either ask the user and then call stop_project on the other project, "
        "or call suggest_free_port and change only the current project's own port mapping. "
        "Never run `docker compose down`, `down -v`, `docker rm` or `docker volume rm` "
        "to free a port: that can delete another project's data."
    ),
)


# ---------------------------------------------------------------------------
# Helpers (not visible for agents)
# ---------------------------------------------------------------------------

class DockerError(Exception):
    """A docker command failed; the message is safe to show to the agent."""


def _run(cmd: list[str], cwd: str | None = None) -> str:
    try:
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        ).stdout
    except FileNotFoundError as e:
        raise DockerError("Docker CLI not found. Is Docker installed and on PATH?") from e
    except subprocess.CalledProcessError as e:
        raise DockerError(f"`{' '.join(cmd)}` failed: {e.stderr.strip() or e.stdout.strip()}") from e


def _running_containers() -> list[dict]:
    ids = _run(["docker", "ps", "-q"]).split()

    if not ids:
        return []

    return json.loads(_run(["docker", "inspect", *ids]))


def _owner(port: int) -> dict | None:
    """Which running container publishes this host port, and from which folder."""

    for c in _running_containers():
        for bindings in (c["NetworkSettings"]["Ports"] or {}).values():
            for b in bindings or []:
                if b.get("HostPort") == str(port):
                    labels = c["Config"]["Labels"] or {}
                    return {
                        "container": c["Name"].lstrip("/"),
                        "compose_project": labels.get("com.docker.compose.project"),
                        "project_folder": labels.get("com.docker.compose.project.working_dir"),
                    }
    return None


def _project_ports(path: str) -> list[int]:
    """Host ports the compose project in `path` wants (reads docker-compose.yml + .env)."""

    config = json.loads(_run(["docker", "compose", "config", "--format", "json"], cwd=path))
    ports = []

    for service in config.get("services", {}).values():
        for p in service.get("ports", []):
            published = str(p.get("published", ""))
            if published.isdigit():
                ports.append(int(published))

    return ports


def _project_containers(path: str) -> list[dict]:
    """Running containers that docker compose started from the folder `path`."""

    here = os.path.realpath(path)
    found = []

    for c in _running_containers():
        labels = c["Config"]["Labels"] or {}
        folder = labels.get("com.docker.compose.project.working_dir")
        if folder and os.path.realpath(folder) == here:
            found.append({
                "id": c["Id"],
                "container": c["Name"].lstrip("/"),
                "compose_project": labels.get("com.docker.compose.project"),
            })

    return found


def _docker_published_ports() -> set[int]:
    """Host ports published by running containers.

    On Linux with Docker's userland proxy turned off, nothing actually listens on these
    ports, so the bind test in _is_free would wrongly report them as free.
    """
    ports = set()

    for c in _running_containers():
        for bindings in (c["NetworkSettings"]["Ports"] or {}).values():
            for b in bindings or []:
                if str(b.get("HostPort", "")).isdigit():
                    ports.add(int(b["HostPort"]))

    return ports


def _is_free(port: int) -> bool:
    """True if nothing on this machine is listening on the host port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


# ---------------------------------------------------------------------------
# Tools Available for Agents (agent sees name + docstring + parameters)
# ---------------------------------------------------------------------------

@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def check_conflicts(path: str) -> dict:
    """Call this FIRST when a docker compose project fails to start because a port is
    already in use ('port is already allocated', 'address already in use').
    `path` is the absolute path of the project folder you are trying to start.
    Returns which of its ports are taken and which other project folder holds each one.
    Do not change ports or stop anything before calling this."""

    here = os.path.realpath(path)
    conflicts = []

    try:
        for port in _project_ports(path):
            owner = _owner(port)

            if owner is None:
                # Not a Docker container, but something else may still hold the port.
                if not _is_free(port):
                    conflicts.append({
                        "port": port,
                        "container": None,
                        "compose_project": None,
                        "project_folder": None,
                        "note": "Held by a process outside Docker. Do not stop it; use suggest_free_port.",
                    })
                continue

            folder = owner["project_folder"]
            if folder is None or os.path.realpath(folder) != here:
                conflicts.append({"port": port, **owner})
    except DockerError as e:
        return {"project": here, "error": str(e)}

    log.info("check_conflicts(%s): %d conflict(s)", here, len(conflicts))

    return {"project": here, "conflicts": conflicts}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def suggest_free_port(port: int) -> dict:
    """Suggest the nearest free host port at or above `port`.
    Use this when the project holding the port must keep running,
    for example another agent's git worktree.
    Change only the current project's own port mapping, never the other project's."""

    try:
        taken_by_docker = _docker_published_ports()
    except DockerError:
        taken_by_docker = set()  # Docker not reachable: fall back to the bind test alone

    for candidate in range(port, port + 100):
        if candidate not in taken_by_docker and _is_free(candidate):
            return {"requested": port, "free_port": candidate}

    return {"requested": port, "free_port": None}


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False,
))
def stop_project(path: str) -> dict:
    """Stop (pause) every running container of the docker compose project started from
    the folder `path`, to free its ports. This is `docker stop`, not `down`:
    containers, volumes and data are kept, and the project can be resumed later
    with `docker compose start` in that folder.
    `path` is the project_folder returned by check_conflicts.
    Only call this after the user has explicitly agreed to stop that project."""

    here = os.path.realpath(path)

    try:
        containers = _project_containers(here)
        if not containers:
            return {
                "project_folder": here,
                "stopped": [],
                "note": "No running docker compose project was started from this folder. Nothing was stopped.",
            }

        _run(["docker", "stop", *[c["id"] for c in containers]])
    except DockerError as e:
        return {"project_folder": here, "error": str(e)}

    names = [c["container"] for c in containers]
    log.info("stop_project(%s): stopped %s", here, names)

    return {
        "project_folder": here,
        "compose_project": containers[0]["compose_project"],
        "stopped": names,
        "data_kept": True,
        "resume_with": f"cd {here} && docker compose start",
    }


# ---------------------------------------------------------------------------
# Run MCP Server
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()  # stdio transport by default

if __name__ == "__main__":
    main()
