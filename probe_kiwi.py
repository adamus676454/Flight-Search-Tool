#!/usr/bin/env python3
"""Probe Kiwi MCP server to discover protocol and tool schemas."""
import requests
import json

MCP_URL = "https://mcp.kiwi.com"

session = requests.Session()
session.headers.update({
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
})

# Step 1: Initialize
print("=== INITIALIZE ===")
init_payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "azair-extended", "version": "0.1.0"}
    }
}
resp = session.post(MCP_URL, json=init_payload, timeout=15)
print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('Content-Type', '')}")
mcp_session = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
print(f"Mcp-Session-Id: {mcp_session}")

ct = resp.headers.get("Content-Type", "")
if "text/event-stream" in ct:
    print("SSE response:")
    for line in resp.text.splitlines():
        print(f"  {line}")
        if line.startswith("data: "):
            data = json.loads(line[6:])
            print(f"  PARSED: {json.dumps(data, indent=2)}")
else:
    print(f"JSON response: {json.dumps(resp.json(), indent=2)}")

# Add session header if present
if mcp_session:
    session.headers["Mcp-Session-Id"] = mcp_session

# Step 2: Send initialized notification
print("\n=== INITIALIZED NOTIFICATION ===")
notif_payload = {
    "jsonrpc": "2.0",
    "method": "notifications/initialized",
    "params": {}
}
resp2 = session.post(MCP_URL, json=notif_payload, timeout=15)
print(f"Status: {resp2.status_code}")

# Step 3: List tools
print("\n=== TOOLS/LIST ===")
tools_payload = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
}
resp3 = session.post(MCP_URL, json=tools_payload, timeout=15)
print(f"Status: {resp3.status_code}")
print(f"Content-Type: {resp3.headers.get('Content-Type', '')}")

ct3 = resp3.headers.get("Content-Type", "")
if "text/event-stream" in ct3:
    print("SSE response:")
    for line in resp3.text.splitlines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            print(json.dumps(data, indent=2))
else:
    print(json.dumps(resp3.json(), indent=2))
