"""
Run this file to start the MCP server (normally launched automatically
by client_gemini.py as a subprocess).
 
    python server.py          # manual launch for debugging
    python client_gemini.py   # normal usage (auto-launches this server)
"""

from __future__ import annotations

import sys

from fastmcp import FastMCP
from modules import register_all

from modules.seq_basics._plumbing import resolve

mcp = FastMCP(
    "BioE234 MCP Starter",
    instructions="Starter MCP server for BioE234."
)

# stdout is reserved for MCP stdio transport — never print to stdout here.
print("[server] Starting BioE234 MCP server...", file=sys.stderr)

register_all(mcp)

print("[server] All modules registered. Server ready.", file=sys.stderr)


if __name__ == "__main__":
    mcp.run(transport="stdio")
