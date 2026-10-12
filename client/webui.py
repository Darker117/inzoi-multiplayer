"""Tiny local HTTP API for the in-game panel (ui/mp in the mod) and the servers page (client/page). The game's UI can
only reach the companion with XMLHttpRequest to 127.0.0.1, so every call is a POST with a JSON body and every answer
is HTTP 200 + JSON (Gameface drops the body of non-2xx answers; errors come back as {"error": "..."}).
GET serves the servers page's files (opened in a browser window over the game).

Runs inside the companion's asyncio loop; `routes` maps a path to an async function(body: dict) -> dict.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("webui")
PORT = int(os.environ.get("INZOI_MP_PANEL_PORT") or 24243)      # the in-game panel only knows 24243 (tests: other)
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".woff2": "font/woff2", ".ttf": "font/ttf"}


def page_files() -> dict[str, Path]:
    """URL path -> file of the servers page (client/page; in the exe it's unpacked next to the program's code)."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "page"
    files = {f"/page/{f.relative_to(root).as_posix()}": f for f in root.rglob("*") if f.suffix in TYPES}
    if (root / "servers.html").exists():
        files["/servers"] = root / "servers.html"
    return files


async def serve(routes: dict, static: dict | None = None, host: str = "127.0.0.1", port: int = PORT):
    static = static or {}

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            lines = head.decode("latin-1").split("\r\n")
            method, path = lines[0].split(" ")[:2]
            headers = {k.strip().lower(): v.strip() for k, v in (l.split(":", 1) for l in lines[1:] if ":" in l)}
            size = int(headers.get("content-length") or 0)
            raw = await reader.readexactly(size) if size else b""
            path = path.split("?")[0]
            origin = headers.get("origin", "")
            if origin and not origin.startswith("coui://") and origin not in (f"http://127.0.0.1:{port}",
                                                                              f"http://localhost:{port}"):
                # a web page somewhere else trying to drive the program (kick players, change passwords...): no
                log.warning("refused a call to %s from %s", path, origin)
                writer.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            if method == "GET" and path in static:
                f = static[path]
                data = await asyncio.to_thread(f.read_bytes)
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: " + TYPES[f.suffix].encode() +
                             b"\r\nCache-Control: no-store\r\nConnection: close\r\n" +
                             f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
                await writer.drain()
                return
            if method == "OPTIONS":
                out = {}
            else:
                fn = routes.get(path)
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
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, ValueError, OSError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, host, port)
    log.info("in-game panel API on http://%s:%d", host, port)
    return server
