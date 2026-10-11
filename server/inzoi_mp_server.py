#!/usr/bin/env python3
"""inZOI Multiplayer server.

A small relay + storage server. Each player's companion app connects here; the server keeps
the list of who is online, relays live Zoi state between players, stores each player's Zoi
profile and house snapshots, and forwards chat, visit invites and interactions. All game logic
lives in the companion apps, so the server never needs updating when a new synced feature is added
(new features ride on the generic "event" message).

Runs anywhere Python 3.9+ runs (Raspberry Pi OS, Linux, Windows, macOS). No extra packages.

    python3 inzoi_mp_server.py                     # port 24242, data in ./data
    python3 inzoi_mp_server.py --port 24242 --password secret --data /var/lib/inzoi-mp

Wire format: one JSON object per line over TCP, UTF-8. Every message has "t" (its type).
See PROTOCOL.md next to this file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import secrets
import signal
import time
from pathlib import Path

VERSION = "0.1.0"
PROTOCOL = 1
MAX_LINE = 32 * 1024 * 1024        # house snapshots can be large
PING_EVERY = 15                    # seconds between keepalives
TIMEOUT = 45                       # drop a client that sent nothing for this long

log = logging.getLogger("inzoi-mp")


def now() -> float:
    return time.time()


class Store:
    """Everything that survives a restart: known players, their Zoi profiles and house snapshots."""

    def __init__(self, root: Path):
        self.root = root
        (root / "houses").mkdir(parents=True, exist_ok=True)
        self.players_file = root / "players.json"
        self.players: dict[str, dict] = self._load(self.players_file, {})

    @staticmethod
    def _load(path: Path, default):
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return default

    @staticmethod
    def _save(path: Path, data) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
        os.replace(tmp, path)

    def player_for_key(self, key: str, name: str) -> dict:
        """Players are identified by a secret key their companion generates once; the id others see is derived."""
        for pid, p in self.players.items():
            if secrets.compare_digest(p["key"], key):
                p["name"] = name
                p["last_seen"] = now()
                self.save_players()
                return {"id": pid, **p}
        pid = "p" + secrets.token_hex(4)
        self.players[pid] = {"key": key, "name": name, "first_seen": now(), "last_seen": now(), "profile": None}
        self.save_players()
        return {"id": pid, **self.players[pid]}

    def save_players(self) -> None:
        self._save(self.players_file, self.players)

    def set_profile(self, pid: str, profile) -> None:
        self.players[pid]["profile"] = profile
        self.save_players()

    def house_path(self, pid: str) -> Path:
        return self.root / "houses" / f"{pid}.json"

    def put_house(self, pid: str, house) -> dict:
        house = house or {}
        meta = {"owner": pid, "updated": now(), "name": house.get("name", ""), "by": house.get("by", ""),
                "lot": house.get("lot", "")}
        self._save(self.house_path(pid), {"meta": meta, "house": house})
        return meta

    def get_house(self, pid: str):
        return self._load(self.house_path(pid), None)

    def list_houses(self) -> list[dict]:
        out = []
        for f in (self.root / "houses").glob("p*.json"):
            d = self._load(f, None)
            if d:
                out.append(d["meta"])
        return out


class Client:
    def __init__(self, server: "Server", reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.server = server
        self.reader = reader
        self.writer = writer
        self.addr = writer.get_extra_info("peername")
        self.id: str | None = None
        self.name = "?"
        self.state: dict | None = None     # last live state (position, animation, ...)
        self.last_heard = now()
        self.closed = False
        self.lock = asyncio.Lock()

    def public(self) -> dict:
        p = self.server.store.players.get(self.id or "", {})
        return {"id": self.id, "name": self.name, "profile": p.get("profile"), "state": self.state,
                "leader": self.server.leader is self}

    async def send(self, msg: dict) -> None:
        if self.closed:
            return
        data = (json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            async with self.lock:
                self.writer.write(data)
                await self.writer.drain()
        except (ConnectionError, OSError):
            await self.close()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.writer.close()
        except Exception:
            pass


class Server:
    def __init__(self, store: Store, password: str = "", max_players: int = 16, motd: str = ""):
        self.store = store
        self.password = password
        self.max_players = max_players
        self.motd = motd
        self.clients: dict[str, Client] = {}
        self.leader: Client | None = None      # whose world clock/weather everyone follows
        self.world: dict | None = None         # latest world state from the leader

    # ------------------------------------------------------------------ plumbing
    async def broadcast(self, msg: dict, exclude: Client | None = None) -> None:
        await asyncio.gather(*(c.send(msg) for c in list(self.clients.values()) if c is not exclude))

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        c = Client(self, reader, writer)
        log.info("connection from %s", c.addr)
        try:
            while not c.closed:
                try:
                    line = await asyncio.wait_for(reader.readline(), TIMEOUT)
                except asyncio.TimeoutError:
                    log.info("%s timed out", c.name)
                    break
                except (ValueError, asyncio.LimitOverrunError):
                    await c.send({"t": "error", "error": "message too large"})
                    break
                if not line:
                    break
                c.last_heard = now()
                try:
                    msg = json.loads(line)
                    if not isinstance(msg, dict):
                        raise ValueError
                except ValueError:
                    await c.send({"t": "error", "error": "bad json"})
                    continue
                await self.dispatch(c, msg)
        except (ConnectionError, OSError):
            pass
        finally:
            await c.close()
            await self.drop(c)

    async def drop(self, c: Client, reelect: bool = True) -> None:
        if c.id and self.clients.get(c.id) is c:
            del self.clients[c.id]
            log.info("%s (%s) left", c.name, c.id)
            await self.broadcast({"t": "left", "id": c.id, "name": c.name})
            if self.leader is c and reelect:
                self.leader = next(iter(self.clients.values()), None)
                if self.leader:
                    await self.broadcast({"t": "leader", "id": self.leader.id})

    # ------------------------------------------------------------------ messages
    async def dispatch(self, c: Client, msg: dict) -> None:
        t = msg.get("t")
        if c.id is None:
            if t != "hello":
                await c.send({"t": "error", "error": "say hello first"})
                return
            await self.on_hello(c, msg)
            return
        fn = getattr(self, "on_" + str(t), None) if re.fullmatch(r"[a-z_]{1,32}", str(t)) and t != "hello" else None
        if fn is None:
            await c.send({"t": "error", "error": f"unknown message type {t!r}"})
            return
        await fn(c, msg)

    async def on_hello(self, c: Client, msg: dict) -> None:
        if msg.get("protocol") != PROTOCOL:
            await c.send({"t": "error", "fatal": True, "error": f"version mismatch: server speaks protocol {PROTOCOL}"})
            await c.close()
            return
        if self.password and not secrets.compare_digest(str(msg.get("password", "")), self.password):
            await c.send({"t": "error", "fatal": True, "error": "wrong server password"})
            await c.close()
            return
        key = str(msg.get("key", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
            await c.send({"t": "error", "fatal": True, "error": "missing or malformed player key"})
            await c.close()
            return
        name = str(msg.get("name", "")).strip()[:40] or "Player"
        p = self.store.player_for_key(key, name)
        old = self.clients.get(p["id"])
        was_leader = old is not None and self.leader is old
        if old:                                      # same player reconnecting: replace the stale session
            await old.send({"t": "kicked", "reason": "you connected from somewhere else"})
            await old.close()
            await self.drop(old, reelect=False)
        elif len(self.clients) >= self.max_players:
            await c.send({"t": "error", "fatal": True, "error": "server is full"})
            await c.close()
            return
        c.id, c.name = p["id"], name
        self.clients[c.id] = c
        if self.leader is None or was_leader:        # a reconnecting leader keeps the world clock
            self.leader = c
        log.info("%s (%s) joined from %s", c.name, c.id, c.addr)
        await c.send({
            "t": "welcome", "id": c.id, "server_version": VERSION, "motd": self.motd,
            "leader": self.leader.id, "world": self.world,
            "players": [o.public() for o in self.clients.values() if o is not c],
            "houses": self.store.list_houses(),
        })
        await self.broadcast({"t": "joined", "player": c.public()}, exclude=c)

    async def on_ping(self, c: Client, msg: dict) -> None:
        await c.send({"t": "pong", "time": now(), "echo": msg.get("echo")})

    async def on_pong(self, c: Client, msg: dict) -> None:
        pass

    async def on_state(self, c: Client, msg: dict) -> None:
        """Live Zoi state (position, facing, animation, current interaction, site...). Sent ~5-10x/s."""
        c.state = msg.get("state")
        await self.broadcast({"t": "state", "id": c.id, "state": c.state}, exclude=c)

    async def on_profile(self, c: Client, msg: dict) -> None:
        """The player's Zoi: name, appearance, traits. Stored so people who join later can build the Zoi."""
        self.store.set_profile(c.id, msg.get("profile"))
        await self.broadcast({"t": "profile", "id": c.id, "profile": msg.get("profile")}, exclude=c)

    async def on_world(self, c: Client, msg: dict) -> None:
        """Clock, weather and season. Only the leader's world is shared, everyone else follows it."""
        if c is not self.leader:
            return
        self.world = msg.get("world")
        await self.broadcast({"t": "world", "world": self.world}, exclude=c)

    async def on_take_leader(self, c: Client, msg: dict) -> None:
        self.leader = c
        await self.broadcast({"t": "leader", "id": c.id})

    async def on_chat(self, c: Client, msg: dict) -> None:
        text = str(msg.get("text", "")).strip()[:500]
        if text:
            log.info("[chat] %s: %s", c.name, text)
            await self.broadcast({"t": "chat", "id": c.id, "name": c.name, "text": text, "time": now()})

    async def on_event(self, c: Client, msg: dict) -> None:
        """Generic relay: {"t":"event","kind":"...","to":<player id or omitted for everyone>,"data":{...}}.
        Interactions, visit invites, gifts... anything new the companions agree on."""
        out = {"t": "event", "from": c.id, "kind": str(msg.get("kind", "")), "data": msg.get("data")}
        to = msg.get("to")
        if to:
            target = self.clients.get(str(to))
            if target:
                await target.send(out)
            else:
                await c.send({"t": "error", "error": f"{to} is not online", "ref": msg.get("ref")})
        else:
            await self.broadcast(out, exclude=c)

    async def on_house_put(self, c: Client, msg: dict) -> None:
        meta = self.store.put_house(c.id, msg.get("house"))
        log.info("%s uploaded their house (%s)", c.name, meta.get("name") or "unnamed")
        await self.broadcast({"t": "house_updated", "meta": meta})

    async def on_house_get(self, c: Client, msg: dict) -> None:
        owner = str(msg.get("owner", ""))
        d = self.store.get_house(owner)
        await c.send({"t": "house", "owner": owner, "meta": d and d["meta"], "house": d and d["house"]})

    async def on_house_list(self, c: Client, msg: dict) -> None:
        await c.send({"t": "house_list", "houses": self.store.list_houses()})

    async def on_who(self, c: Client, msg: dict) -> None:
        await c.send({"t": "who", "players": [o.public() for o in self.clients.values()]})

    # ------------------------------------------------------------------ keepalive
    async def keepalive(self) -> None:
        while True:
            await asyncio.sleep(PING_EVERY)
            await self.broadcast({"t": "ping", "time": now()})


async def start(args):
    """Start serving and return once listening: (asyncio server, keepalive task). The all-in-one app
    (client/launcher.py) calls this to host inside the same program as the companion."""
    store = Store(Path(args.data).expanduser().resolve())
    server = Server(store, password=args.password, max_players=args.max_players, motd=args.motd)
    srv = await asyncio.start_server(server.handle, args.host, args.port, limit=MAX_LINE)
    addrs = ", ".join(str(s.getsockname()[:2]) for s in srv.sockets)
    log.info("inZOI Multiplayer server %s listening on %s (data: %s)%s", VERSION, addrs, store.root,
             " - password required" if args.password else "")
    return srv, asyncio.ensure_future(server.keepalive())


async def main_async(args) -> None:
    srv, ka = await start(args)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):     # Windows: Ctrl+C raises KeyboardInterrupt instead
            pass
    async with srv:
        await stop.wait()
    ka.cancel()
    log.info("shutting down")


def main() -> None:
    ap = argparse.ArgumentParser(description="inZOI Multiplayer server")
    ap.add_argument("--host", default=os.environ.get("INZOI_MP_HOST", "0.0.0.0"), help="address to listen on (default all)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("INZOI_MP_PORT", 24242)))
    ap.add_argument("--password", default=os.environ.get("INZOI_MP_PASSWORD", ""), help="optional server password")
    ap.add_argument("--data", default=os.environ.get("INZOI_MP_DATA", str(Path(__file__).resolve().parent / "data")))
    ap.add_argument("--max-players", type=int, default=int(os.environ.get("INZOI_MP_MAX_PLAYERS", 16)))
    ap.add_argument("--motd", default=os.environ.get("INZOI_MP_MOTD", ""), help="message shown to players when they join")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        log.info("shutting down")


if __name__ == "__main__":
    main()
