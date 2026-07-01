"""Entry point for running the Kalpi MCP server standalone.

Run this module directly to start the MCP server in stdio transport mode,
making the portfolio analysis tools available to any MCP-compatible client
(e.g., Claude Desktop, Claude Code).

Usage:
    python mcp_server_runner.py
"""
from app.mcp_server import mcp

if __name__ == "__main__":
    mcp.run()
