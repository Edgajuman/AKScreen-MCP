"""MCP stdio transport, independent of an agent vendor. No online service is started."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from . import __version__
from .bridge import Bridge, BridgeError, MAX_REQUEST
from .tools import TOOLS, Tools, content

PROTOCOLS = {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
INSTRUCTIONS = "Control the running AK Screen editor locally. Discover IDs and parameter docs with command_list; inspect with doc_inspect. Edits have undo history. Batch edits are sequential, not atomic. Use render_preview only when visual verification is needed. Never repeat an uncertain timed-out mutation before inspecting the project. The original 2.4.0 release does not enable this authenticated bridge; use a build containing the agent-control update."


def handle(request, tools):
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
        return {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None, "error": {"code": -32600, "message": "Invalid request"}}
    if "id" not in request:
        return None
    response = dict(jsonrpc="2.0", id=request["id"])
    method, params = request["method"], request.get("params", {})
    if not isinstance(params, dict):
        return dict(response, error={"code": -32602, "message": "params must be an object"})
    if method == "initialize":
        protocol = params.get("protocolVersion")
        result = dict(protocolVersion=protocol if protocol in PROTOCOLS else "2025-11-25",
                      serverInfo=dict(name="ak-screen-mcp", version=__version__), capabilities={"tools": {}}, instructions=INSTRUCTIONS)
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            result = content(tools.call(params.get("name"), params.get("arguments", {})))
        except (BridgeError, ValueError, TypeError, OSError, RecursionError) as error:
            result = {"content": [{"type": "text", "text": str(error)[:3000]}], "isError": True}
    else:
        return dict(response, error={"code": -32601, "message": "Method not found"})
    return dict(response, result=result)


def serve(tools, incoming, outgoing):
    while True:
        line = incoming.readline(MAX_REQUEST + 1)
        if not line:
            return
        if len(line) > MAX_REQUEST:
            outgoing.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Request too large"}}) + "\n")
            outgoing.flush()
            return
        try:
            request = json.loads(line)
            response = handle(request, tools)
        except (ValueError, UnicodeError, RecursionError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON"}}
        if response is not None:
            outgoing.write(json.dumps(response, ensure_ascii=True, allow_nan=False) + "\n")
            outgoing.flush()


def main():
    parser = argparse.ArgumentParser(description="AK Screen MCP local stdio bridge")
    parser.add_argument("--port", type=int, default=9876)
    parser.add_argument("--launch", type=Path, help="Start this AKScreen executable with an isolated session token")
    args = parser.parse_args()
    token = os.environ.get("AKSCREEN_CONTROL_TOKEN", "")
    child = None
    if args.launch:
        token = secrets.token_urlsafe(32)
    try:
        bridge = Bridge(args.port, token)
        if args.launch:
            executable = args.launch.resolve(strict=True)
            if not executable.is_file():
                raise ValueError("--launch must name an executable file")
            environment = dict(os.environ, AKSCREEN_CONTROL_TOKEN=token)
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
            child = subprocess.Popen([str(executable), "--control", str(args.port)], env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        if child:
            deadline = time.monotonic() + 60
            while True:
                if child.poll() is not None:
                    raise BridgeError("AK Screen exited before local control became available. Install a compatible agent-control build.")
                try:
                    bridge.call("ui.inspect")
                    break
                except BridgeError:
                    if time.monotonic() > deadline:
                        raise BridgeError("The editor did not enable its bridge. Check the app version and port.")
                    time.sleep(0.25)
        serve(Tools(bridge), sys.stdin.buffer, sys.stdout)
    except (BridgeError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    # The editor intentionally survives an agent disconnect; unsaved work is never killed.


if __name__ == "__main__":
    main()
