"""
---------------------------------------------------------------------------
PortSwitch MCP server - DEBUG entry point
---------------------------------------------------------------------------
The normal server plus the internal helpers exposed as tools,
so you can call them one by one in the MCP Inspector.

Run:   uv run mcp dev src/portswitch/debug_server.py
Never register this file in .mcp.json - agents should only see server.py.
"""

from server import _is_free, _owner, _project_containers, _project_ports, _running_containers, mcp

for helper in (_running_containers, _owner, _project_ports, _project_containers, _is_free):
    mcp.tool()(helper)


@mcp.tool()
def ping() -> str:
    """Check that the PortSwitch server is connected. Returns 'pong'."""
    return "pong"
