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

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("portswitch")

mcp = MCPServer("portswitch")


# ---------------------------------------------------------------------------
# Helpers (not visible for agents)
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: str | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout

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

@mcp.tool()
def ping() -> str:
    """Check that the PortSwitch server is connected. Returns 'pong'."""
    return "pong"


@mcp.tool()
def check_conflicts(path: str) -> dict:
    """Call this FIRST when a docker compose project fails to start because a port is
    already in use ('port is already allocated', 'address already in use').
    `path` is the absolute path of the project folder you are trying to start.
    Returns which of its ports are taken and which other project folder holds each one.
    Do not change ports or stop anything before calling this."""

    here = os.path.realpath(path)
    conflicts = []

    for port in _project_ports(path):
        owner = _owner(port)
        if owner is None:
            continue
        folder = owner["project_folder"]
        if folder is None or os.path.realpath(folder) != here:
            conflicts.append({"port": port, **owner})
    
    log.info("check_conflicts(%s): %d conflict(s)", here, len(conflicts))
    
    return {"project": here, "conflicts": conflicts}


@mcp.tool()
def suggest_free_port(port: int) -> dict:
    """Suggest the nearest free host port at or above `port`.
    Use this when the project holding the port must keep running,
    for example another agent's git worktree."""

    for candidate in range(port, port + 100):
        if _is_free(candidate):
            return {"requested": port, "free_port": candidate}
    
    return {"requested": port, "free_port": None}


# ---------------------------------------------------------------------------
# Debug: expose the helpers as tools too (only when PORTSWITCH_DEBUG=1)
# ---------------------------------------------------------------------------

if os.environ.get("PORTSWITCH_DEBUG") == "1":
    for helper in (_running_containers, _owner, _project_ports, _is_free):
        mcp.tool()(helper)


# ---------------------------------------------------------------------------
# Run MCP Server
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()  # stdio transport by default

if __name__ == "__main__":
    main()
