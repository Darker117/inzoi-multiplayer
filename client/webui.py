"""Tiny local HTTP API for the in-game panel (ui/mp in the mod). The game's UI can only reach the companion with
XMLHttpRequest to 127.0.0.1, so every call is a POST with a JSON body and every answer is HTTP 200 + JSON
(Gameface drops the body of non-2xx answers; errors come back as {"error": "..."}).

Runs inside the companion's asyncio loop; `routes` maps a path to an async function(body: dict) -> dict.
"""
import asyncio
import json
import logging

log = logging.getLogger("webui")
PORT = 24243


async def serve(routes: dict, host: str = "127.0.0.1", port: int = PORT):
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            lines = head.decode("latin-1").split("\r\n")
            method, path = lines[0].split(" ")[:2]
            headers = {k.strip().lower(): v.strip() for k, v in (l.split(":", 1) for l in lines[1:] if ":" in l)}
            size = int(headers.get("content-length") or 0)
            raw = await reader.readexactly(size) if size else b""
            if method == "OPTIONS":
                out = {}
            else:
                fn = routes.get(path.split("?")[0])
                if fn is None:
                    out = {"error": f"no such call {path}"}
                else:
                    try:
                        out = await fn(json.loads(raw) if raw.strip() else {})
                    except Exception as e:                              # noqa: BLE001 - the panel shows it
                        log.exception("ui call %s failed", path)
                        out = {"error": str(e)}
            data = json.dumps(out, ensure_ascii=False).encode()
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n"
                         b"Access-Control-Allow-Origin: *\r\nAccess-Control-Allow-Headers: Content-Type\r\n"
                         b"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\nConnection: close\r\n"
                         + f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
            await writer.drain()
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, ValueError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, host, port)
    log.info("in-game panel API on http://%s:%d", host, port)
    return server
