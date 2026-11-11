"""
=====================
PortSwitch MCP server
=====================
- talks to Claude Code over stdin/stdout
- use logging for debug output
"""
import subprocess
import logging
import json

from mcp.server import MCPServer

# setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("portswitch")

# setup MCP
mcp = MCPServer("portswitch")


@mcp.tool()
def ping() -> str:
    """Check that the PortSwitch server is connected. Returns 'pong'."""
    log.info("ping called")
    return "pong"


def _running_containers() -> list[dict]:
    ids = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True, check=True).stdout.split()
    if not ids:
        return []
    out = subprocess.run(["docker", "inspect", *ids], capture_output=True, text=True, check=True).stdout
    return json.loads(out)

@mcp.tool()
def port_owner(port: int) -> str:
    """Find which Docker container and which project folder is using a host port.
    Use this when a project fails to start with 'port is already allocated'
    or 'address already in use'."""
    for c in _running_containers():
        for bindings in (c["NetworkSettings"]["Ports"] or {}).values():
            for b in bindings or []:
                if b.get("HostPort") == str(port):
                    labels = c["Config"]["Labels"] or {}
                    return json.dumps({
                        "port": port,
                        "container": c["Name"].lstrip("/"),
                        "compose_project": labels.get("com.docker.compose.project"),
                        "project_folder": labels.get("com.docker.compose.project.working_dir"),
                    })
    return json.dumps({"port": port, "held_by": None, "note": "No running Docker container uses this port."})


def main() -> None:
    mcp.run()  # stdio transport by default


if __name__ == "__main__":
    main()
