#!/bin/bash
# Launch the MCP server (port 8001) and the mcpo OpenAPI proxy (port 8000).
# OpenWebUI connects to mcpo on 8000 as an *OpenAPI* tool server.
#   URL:  http://host.docker.internal:8000
set -e

BIN="$HOME/Library/Python/3.14/bin"
cd "$(dirname "$0")"

# 1. Start the MCP server in the background on 8001.
python3 mcp_server.py &
MCP_PID=$!
echo "mcp_server.py running (pid $MCP_PID) on :8001"

# Stop the MCP server when mcpo exits / this script is interrupted.
trap 'kill $MCP_PID 2>/dev/null' EXIT

# Give the MCP server a moment to bind its port.
sleep 2

# 2. Start mcpo on 8000, proxying the streamable-http MCP server to OpenAPI.
"$BIN/mcpo" --port 8000 --server-type streamable-http -- http://localhost:8001/mcp
