"""One authenticated local request per connection. Mutations are never retried."""
import json
import socket

MAX_REQUEST = 4 * 1024 * 1024
MAX_RESPONSE = 8 * 1024 * 1024


class BridgeError(Exception):
    pass


class Bridge:
    def __init__(self, port=9876, token="", timeout=65):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if not isinstance(token, str) or not 32 <= len(token) <= 256 or not all(33 <= ord(char) <= 126 for char in token):
            raise ValueError("Set AKSCREEN_CONTROL_TOKEN (32–256 ASCII characters), or use --launch")
        self.port, self._token, self.timeout = port, token, timeout
        self._next_id = 0

    def call(self, method, params=None):
        if not isinstance(method, str) or (params is not None and not isinstance(params, dict)):
            raise BridgeError("A control method and parameter object are required")
        self._next_id += 1
        params = dict(params or {}, _ak_token=self._token)
        request = json.dumps(dict(id=self._next_id, method=method, params=params), allow_nan=False).encode() + b"\n"
        if len(request) > MAX_REQUEST:
            raise BridgeError("Request exceeds the editor's 4 MiB limit")
        sent = False
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=5) as connection:
                connection.settimeout(self.timeout)
                sent = True
                connection.sendall(request)
                with connection.makefile("rb") as stream:
                    data = stream.readline(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE or not data.endswith(b"\n"):
                raise BridgeError("Incomplete or oversized editor response. The command may have completed: inspect the project before retrying.")
            result = json.loads(data)
        except (OSError, ValueError, RecursionError) as error:
            suffix = " The command may have completed: inspect the project before retrying." if sent else " Start a compatible AK Screen build with local control enabled."
            raise BridgeError("Cannot communicate with AK Screen." + suffix) from error
        if not isinstance(result, dict) or result.get("id") != self._next_id:
            raise BridgeError("The editor returned an unexpected response ID")
        if result.get("ok") is not True:
            raise BridgeError(str(result.get("error", "The editor refused the operation"))[:2000])
        return result.get("result")

    def execute(self, command, params=None):
        if not isinstance(command, str) or not 1 <= len(command) <= 160:
            raise BridgeError("A real command ID is required; discover it with command_list")
        if params is not None and not isinstance(params, dict):
            raise BridgeError("Command parameters must be an object")
        params = dict(params or {})
        # Long exports are background jobs. Poll jobs.list instead of repeating an export
        # after the desktop control channel's response deadline.
        if command == "file.exportMedia":
            params["wait"] = False
        return self.call("engine.execute", {"command": command, "params": params})
