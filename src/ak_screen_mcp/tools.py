"""Discoverable MCP tools backed by the editor's actual command registry."""
import base64
import json
from pathlib import Path
import tempfile

from .bridge import BridgeError


def tool(name, description, properties=None, required=(), read_only=False):
    return dict(name=name, description=description,
                inputSchema=dict(type="object", properties=properties or {}, required=list(required), additionalProperties=False),
                annotations=dict(readOnlyHint=read_only, destructiveHint=not read_only, openWorldHint=False))


STRING = {"type": "string"}
OBJECT = {"type": "object"}
TOOLS = [
    tool("command_list", "Discover current command IDs, parameter docs and enabled state. Do this before using unfamiliar commands.", {"filter": STRING, "enabled_only": {"type": "boolean"}}, read_only=True),
    tool("command_run", "Execute one real editor command. Edits use the editor's undo history; inspect IDs first.", {"id": STRING, "params": OBJECT}, ("id",)),
    tool("command_batch", "Execute up to 50 commands in order, stopping at the first error. Each edit is its own undo step; this is not an atomic transaction.", {"steps": {"type": "array", "maxItems": 50, "items": {"type": "object", "properties": {"id": STRING, "params": OBJECT}, "required": ["id"], "additionalProperties": False}}}, ("steps",)),
    tool("doc_inspect", "Inspect the project and active sequence, including current object IDs.", read_only=True),
    tool("ui_inspect", "Inspect the editor UI and automation IDs. No desktop input is injected.", read_only=True),
    tool("ui_elements", "Find editor controls by an automation ID prefix.", {"prefix": STRING}, read_only=True),
    tool("ui_control", "Operate the editor's own UI with discovered IDs: click, drag, key, type, panel.show, panel.close, set or playback.", {"action": {"type": "string", "enum": ["click", "drag", "key", "type", "panel.show", "panel.close", "set", "playback"]}, "params": OBJECT}, ("action", "params")),
    tool("render_preview", "Return a PNG of the current Program monitor, or an editor panel. Captures only the editor, when requested.", {"panel": STRING}, read_only=True),
    tool("undo", "Undo one editor operation. A batch may require several undo operations."),
]


class Tools:
    def __init__(self, bridge):
        self.bridge = bridge

    def call(self, name, arguments):
        if not isinstance(arguments, dict):
            raise BridgeError("Tool arguments must be an object")
        if name == "command_list":
            commands = self.bridge.call("engine.commands")
            query = arguments.get("filter", "")
            if not isinstance(query, str):
                raise BridgeError("filter must be a string")
            return [command for command in commands if (not arguments.get("enabled_only") or command.get("enabled"))
                    and query.lower() in (command.get("id", "") + " " + command.get("label", "")).lower()]
        if name == "command_run":
            return self.bridge.execute(arguments.get("id"), arguments.get("params", {}))
        if name == "command_batch":
            steps = arguments.get("steps")
            if not isinstance(steps, list) or not 1 <= len(steps) <= 50 or any(not isinstance(step, dict) or not isinstance(step.get("id"), str) or not isinstance(step.get("params", {}), dict) for step in steps):
                raise BridgeError("Expected 1–50 {id, params?} commands")
            results = []
            for index, step in enumerate(steps):
                try:
                    results.append(dict(ok=True, result=self.bridge.execute(step["id"], step.get("params", {}))))
                except BridgeError as error:
                    return dict(completed=index, failed=1, results=results + [dict(ok=False, error=str(error))])
            return dict(completed=len(results), failed=0, results=results)
        if name == "doc_inspect":
            project = self.bridge.execute("project.inspect")
            try:
                sequence = self.bridge.execute("sequence.inspect")
            except BridgeError:
                sequence = None
            return dict(project=project, sequence=sequence)
        if name == "ui_inspect":
            return self.bridge.call("ui.inspect")
        if name == "ui_elements":
            return self.bridge.call("ui.elements", arguments)
        if name == "ui_control":
            allowed = {"click", "drag", "key", "type", "panel.show", "panel.close", "set", "playback"}
            if arguments.get("action") not in allowed:
                raise BridgeError("Unsupported UI action")
            return self.bridge.call("ui." + arguments["action"], arguments.get("params", {}))
        if name == "render_preview":
            panel = arguments.get("panel", "Program")
            if not isinstance(panel, str) or len(panel) > 80:
                raise BridgeError("Invalid panel name")
            with tempfile.TemporaryDirectory(prefix="ak-screen-mcp-") as directory:
                target = Path(directory) / "preview.png"
                result = self.bridge.call("ui.screenshot", {"path": str(target), "panel": panel})
                if not isinstance(result, dict) or Path(result.get("path", "")).resolve() != target.resolve():
                    raise BridgeError("The editor did not return the requested preview file")
                if not target.is_file() or target.stat().st_size > 8 * 1024 * 1024:
                    raise BridgeError("Preview missing or larger than 8 MiB")
                image = target.read_bytes()
                if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                    raise BridgeError("The editor preview is not a PNG")
                return {"content": [{"type": "image", "mimeType": "image/png", "data": base64.b64encode(image).decode("ascii")}], "isError": False}
        if name == "undo":
            return self.bridge.execute("edit.undo")
        raise BridgeError("Unknown tool: " + str(name))


def content(value):
    if isinstance(value, dict) and "content" in value and "isError" in value:
        return value
    return {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
            "isError": isinstance(value, dict) and bool(value.get("failed"))}
