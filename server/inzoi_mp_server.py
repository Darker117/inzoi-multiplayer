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
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import signal
import time
from pathlib import Path

VERSION = "0.5.1"
PROTOCOL = 1
MAX_LINE = 32 * 1024 * 1024        # house snapshots can be large
PING_EVERY = 15                    # seconds between keepalives
TIMEOUT = 45                       # drop a client that sent nothing for this long
CHUNK = 512 * 1024                 # mod file transfer: bytes per blob_get answer
SHA = re.compile(r"[0-9a-f]{64}")
FILE_MESSAGES = {"blob_check", "blob_put", "blob_get", "ping", "pong"}

log = logging.getLogger("inzoi-mp")


def now() -> float:
    return time.time()


class Store:
    """Everything that survives a restart: known players, their Zoi profiles and house snapshots."""

    def __init__(self, root: Path):
        self.root = root
        for sub in ("houses", "mods", "blobs"):
            (root / sub).mkdir(parents=True, exist_ok=True)
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

    # Mods: each player's list of enabled mods (with a sha256 per file), and the files themselves as blobs named by
    # their sha256, so a file several players have is stored once.
    mods_changed = 0                   # bumped on every set_mods, so the server knows its cached mod set is stale

    def set_mods(self, pid: str, name: str, mods: list) -> None:
        self._save(self.root / "mods" / f"{pid}.json", {"name": name, "updated": now(), "mods": mods})
        self.mods_changed += 1

    def all_mods(self) -> dict[str, dict]:
        out = {}
        for f in (self.root / "mods").glob("p*.json"):
            d = self._load(f, None)
            if d:
                out[f.stem] = d
        return out

    def blob(self, sha: str) -> Path:
        return self.root / "blobs" / sha

    # The shared world: one game save everyone plays, as files (blobs) plus a version that goes up with each upload.
    def world_save(self) -> dict | None:
        return self._load(self.root / "world_save.json", None)

    def set_world_save(self, meta: dict) -> None:
        self._save(self.root / "world_save.json", meta)


def clean_files(raw, limit: int = 5000) -> list[dict]:
    """[{p, h, s}] from a player: relative path, sha256, size. Malformed entries are dropped."""
    return [{"p": str(f["p"])[:400], "h": f["h"], "s": int(f["s"])} for f in (raw if isinstance(raw, list) else [])[:limit]
            if isinstance(f, dict) and SHA.fullmatch(str(f.get("h", ""))) and isinstance(f.get("s"), int)
            and 0 <= f["s"] < 1 << 32 and f.get("p")]


def content(mod: dict) -> set:
    """A mod's files, leaving out mod_manifest.json: the game rewrites it on each PC (load order, enabled...)."""
    return {(f["p"], f["h"]) for f in mod["files"] if f["p"] != "mod_manifest.json"}


def clean_mods(raw) -> list[dict]:
    """A player's mod list, keeping only well-formed entries (they are stored and passed on to other players)."""
    out = []
    for m in raw if isinstance(raw, list) else []:
        if not isinstance(m, dict) or not isinstance(m.get("files"), list) or not str(m.get("id", "")).strip():
            continue
        files = clean_files(m["files"])
        if files:
            out.append({"id": str(m["id"])[:200], "name": str(m.get("name") or m["id"])[:200],
                        "version": str(m.get("version", ""))[:100], "built": str(m.get("built", ""))[:40],
                        "path": str(m.get("path", ""))[:300],
                        "size": sum(f["s"] for f in files), "files": files})
    return out[:500]


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
        self.files = False                 # a second connection of a player, only for mod file transfers

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
    def __init__(self, store: Store, password: str = "", max_players: int = 16, motd: str = "",
                 hosted: bool = False):
        self.store = store
        self.password = password
        self.max_players = max_players
        self.motd = motd
        self.clients: dict[str, Client] = {}
        self.leader: Client | None = None      # whose world clock/weather everyone follows
        self.world: dict | None = None         # latest world state from the leader
        # hosted: the server runs inside a player's program ("Host and play"). That player (the one connecting from
        # this same PC and saying so) is the host: their mods are the ones everyone gets, their clock everyone follows.
        # Otherwise (a Raspberry Pi, "Host only") everyone's mods are pooled and the first player online sets the clock.
        self.hosted = hosted
        self.host_id: str | None = None
        self.modset_sent: str | None = None
        self.conns: set[Client] = set()        # every open connection, players' and file transfers'
        self.world_offers: dict[str, dict] = {}   # player id -> {sha: size} of the world files they're uploading

    # ------------------------------------------------------------------ plumbing
    async def broadcast(self, msg: dict, exclude: Client | None = None) -> None:
        await asyncio.gather(*(c.send(msg) for c in list(self.clients.values()) if c is not exclude))

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        c = Client(self, reader, writer)
        self.conns.add(c)
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
            self.conns.discard(c)
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
        if t == "announce_restart" and c.id is None and str((c.addr or ("",))[0]) in ("127.0.0.1", "::1"):
            await self.announce_restart(max(5, min(600, int(msg.get("in") or 60))))     # from this machine only
            await c.send({"t": "ok"})
            return
        if c.id is None:
            if t != "hello":
                await c.send({"t": "error", "error": "say hello first"})
                return
            await self.on_hello(c, msg)
            return
        if c.files != (t in FILE_MESSAGES - {"ping", "pong"}) and t not in ("ping", "pong"):
            await c.send({"t": "error", "error": f"{t!r} doesn't belong on this connection"})
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
        if msg.get("files"):                         # the player's file transfer connection: not a second player
            c.id, c.name, c.files = p["id"], name, True
            await c.send({"t": "files_ok"})
            return
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
        is_host = self.hosted and bool(msg.get("host")) and str((c.addr or ("",))[0]) in ("127.0.0.1", "::1")
        if is_host:
            self.host_id = c.id
        before = self.leader.id if self.leader else None
        if self.leader is None or was_leader or is_host:             # a reconnecting leader keeps the world clock
            self.leader = c
        log.info("%s (%s) joined from %s%s", c.name, c.id, c.addr, " - the host" if is_host else "")
        modset = self.modset()
        await c.send({
            "t": "welcome", "id": c.id, "server_version": VERSION, "motd": self.motd,
            "leader": self.leader.id, "world": self.world, "host": self.host_id,
            "players": [o.public() for o in self.clients.values() if o is not c],
            "houses": self.store.list_houses(), "modset": modset, "world_save": self.store.world_save(),
        })
        await self.broadcast({"t": "joined", "player": c.public()}, exclude=c)
        if before not in (None, self.leader.id):                    # the clock changed hands
            await self.broadcast({"t": "leader", "id": self.leader.id}, exclude=c)
        await self.send_modset(modset, exclude=c)        # it's in the welcome already

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

    # ------------------------------------------------------------------ mods
    def modset(self) -> dict:
        """The mods everyone should have. Hosted: the host's. Otherwise: everyone's together (for a mod two players
        have in different versions, the newest build). Each mod lists who has it."""
        key = (self.host_id, self.store.mods_changed)
        if getattr(self, "_modset", (None, None))[0] != key:
            self._modset = (key, self._compute_modset())
        return self._modset[1]

    def _compute_modset(self) -> dict:
        lists = self.store.all_mods()
        if self.hosted:
            d = lists.get(self.host_id or "", {})
            mods = [{**m, "by": [d.get("name", "")]} for m in d.get("mods", [])]
            return {"source": "host", "host": self.host_id, "mods": mods}
        merged: dict[str, dict] = {}
        for pid, d in sorted(lists.items(), key=lambda kv: kv[1].get("updated", 0)):
            for m in d.get("mods", []):
                same, name = merged.get(m["id"]), d.get("name", pid)
                if same and content(same) == content(m):            # the same mod, whatever each PC's manifest says
                    same["by"].append(name)
                elif not same or m.get("built", "") >= same.get("built", ""):     # an older build never wins
                    merged[m["id"]] = {**m, "by": [name]}
        return {"source": "everyone", "host": None, "mods": sorted(merged.values(), key=lambda m: m["name"].lower())}

    async def send_modset(self, modset: dict | None = None, exclude: Client | None = None) -> None:
        modset = modset or self.modset()
        text = json.dumps(modset, sort_keys=True)
        if text != self.modset_sent:
            self.modset_sent = text
            await self.broadcast({"t": "modset", **modset}, exclude=exclude)

    def shared_blobs(self) -> set[str]:
        return {f["h"] for m in self.modset()["mods"] for f in m["files"]}

    async def on_mods(self, c: Client, msg: dict) -> None:
        """A player's enabled mods: [{id, name, version, path, files: [{p, h, s}]}]."""
        mods = clean_mods(msg.get("mods"))
        self.store.set_mods(c.id, c.name, mods)
        log.info("%s has %d mod(s)", c.name, len(mods))
        await self.send_modset()

    async def on_blob_check(self, c: Client, msg: dict) -> None:
        """Which of these files (sha256) the server doesn't have yet: the client uploads those."""
        want = [h for h in msg.get("h", []) if isinstance(h, str) and SHA.fullmatch(h)]
        await c.send({"t": "blob_missing", "h": [h for h in want if not self.store.blob(h).exists()]})

    async def on_blob_put(self, c: Client, msg: dict) -> None:
        """Upload a file of one of your own mods, in order: {h, o (offset), d (base64), end}."""
        h, offset = str(msg.get("h", "")), msg.get("o")
        if getattr(c, "mine", (None,))[0] != self.store.mods_changed:
            c.mine = (self.store.mods_changed, {f["h"]: f["s"] for m in self.store.all_mods().get(c.id, {}).get("mods", [])
                                                for f in m["files"]})
        mine = {**c.mine[1], **self.world_offers.get(c.id, {})}
        if h not in mine:
            await c.send({"t": "blob_bad", "h": h, "error": "not a file of your mods or your world upload"})
            return
        part = self.store.blob(h).with_name(f"{h}.{c.id}.part")
        size = part.stat().st_size if part.exists() else 0
        if offset != size:
            await c.send({"t": "blob_bad", "h": h, "error": f"expected offset {size}", "o": size})
            return
        with part.open("ab") as f:
            f.write(base64.b64decode(str(msg.get("d", ""))))
        if not msg.get("end"):
            return
        digest = hashlib.sha256()
        with part.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                digest.update(block)
        if digest.hexdigest() != h or part.stat().st_size != mine[h]:
            part.unlink()
            await c.send({"t": "blob_bad", "h": h, "error": "the file didn't arrive intact"})
            return
        os.replace(part, self.store.blob(h))
        await c.send({"t": "blob_ok", "h": h})

    async def on_blob_get(self, c: Client, msg: dict) -> None:
        """Download a piece of a file that's part of the shared mods: {h, o} -> blob {h, o, d, end}."""
        h, offset = str(msg.get("h", "")), int(msg.get("o") or 0)
        path = self.store.blob(h)
        world = {f["h"] for f in (self.store.world_save() or {}).get("files", [])}
        if not SHA.fullmatch(h) or (h not in self.shared_blobs() and h not in world):
            await c.send({"t": "blob", "h": h, "error": "not shared"})
            return
        if not path.exists():
            await c.send({"t": "blob", "h": h, "error": "not uploaded yet"})
            return
        with path.open("rb") as f:
            f.seek(offset)
            data = f.read(CHUNK)
        await c.send({"t": "blob", "h": h, "o": offset, "d": base64.b64encode(data).decode(),
                      "end": offset + len(data) >= path.stat().st_size})

    # ------------------------------------------------------------------ the shared world
    async def on_world_save_offer(self, c: Client, msg: dict) -> None:
        """About to upload the world: {files: [{p, h, s}]}. Answers which files the server still needs."""
        files = clean_files(msg.get("files"), 2000)
        if not any(f["p"].endswith(".usvx") for f in files):
            await c.send({"t": "world_save_offer", "error": "no save file in the upload"})
            return
        self.world_offers[c.id] = {f["h"]: f["s"] for f in files}
        need = sorted({f["h"] for f in files if not self.store.blob(f["h"]).exists()})
        await c.send({"t": "world_save_offer", "need": need})

    async def on_world_save_put(self, c: Client, msg: dict) -> None:
        """The uploaded world becomes the new version, if it was based on the current one:
        {files, base (the version the player had loaded), name}."""
        files = clean_files(msg.get("files"), 2000)
        current = self.store.world_save() or {}
        version = current.get("version", 0)
        if msg.get("base") != version:
            await c.send({"t": "world_save_put", "ok": False, "version": version,
                          "error": f"the world changed since you loaded it (it's at version {version} now)"})
            return
        missing = [f["p"] for f in files if not self.store.blob(f["h"]).exists()]
        if missing or not files:
            await c.send({"t": "world_save_put", "ok": False, "version": version,
                          "error": f"files not uploaded yet: {', '.join(missing[:5])}"})
            return
        meta = {"version": version + 1, "by": c.name, "pid": c.id, "time": now(), "files": files,
                "name": str(msg.get("name", ""))[:100] or current.get("name", ""), "size": sum(f["s"] for f in files)}
        self.store.set_world_save(meta)
        self.world_offers.pop(c.id, None)
        log.info("%s saved the shared world: version %d (%d MB)", c.name, meta["version"], meta["size"] >> 20)
        await c.send({"t": "world_save_put", "ok": True, "version": meta["version"]})
        await self.broadcast({"t": "world_save", **meta}, exclude=c)

    async def announce_restart(self, seconds: int) -> None:
        """Before the server restarts: everyone saves their game (the world keeper also uploads it)."""
        keeper = self.leader.id if self.leader else None
        log.info("restart in %d s: asking everyone to save (world keeper %s)", seconds, keeper)
        await self.broadcast({"t": "restart_soon", "in": seconds, "keeper": keeper})
        await self.broadcast({"t": "chat", "id": None, "name": "Server", "time": now(),
                              "text": f"The server restarts in {seconds} seconds: your game is saved first."})

    # ------------------------------------------------------------------ keepalive
    async def keepalive(self) -> None:
        while True:
            await asyncio.sleep(PING_EVERY)
            await self.broadcast({"t": "ping", "time": now()})


async def start(args):
    """Start serving and return once listening: (asyncio server, keepalive task). The all-in-one app
    (client/launcher.py) calls this to host inside the same program as the companion."""
    store = Store(Path(args.data).expanduser().resolve())
    server = Server(store, password=args.password, max_players=args.max_players, motd=args.motd,
                    hosted=getattr(args, "hosted", False))
    srv = await asyncio.start_server(server.handle, args.host, args.port, limit=MAX_LINE)
    addrs = ", ".join(str(s.getsockname()[:2]) for s in srv.sockets)
    log.info("inZOI Multiplayer server %s listening on %s (data: %s)%s", VERSION, addrs, store.root,
             " - password required" if args.password else "")
    srv.mp_server = server
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
    await stop.wait()
    log.info("shutting down")
    await srv.mp_server.broadcast({"t": "chat", "id": None, "name": "Server", "time": now(),
                                   "text": "The server is restarting. You'll be reconnected in a moment."})
    await asyncio.sleep(0.5)
    srv.close()
    for c in list(srv.mp_server.conns):              # don't wait for players to hang up: a restart is instant
        await c.close()
    ka.cancel()
    try:
        await asyncio.wait_for(srv.wait_closed(), 5)
    except asyncio.TimeoutError:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="inZOI Multiplayer server")
    ap.add_argument("--host", default=os.environ.get("INZOI_MP_HOST", "0.0.0.0"), help="address to listen on (default all)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("INZOI_MP_PORT", 24242)))
    ap.add_argument("--password", default=os.environ.get("INZOI_MP_PASSWORD", ""), help="optional server password")
    ap.add_argument("--data", default=os.environ.get("INZOI_MP_DATA", str(Path(__file__).resolve().parent / "data")))
    ap.add_argument("--max-players", type=int, default=int(os.environ.get("INZOI_MP_MAX_PLAYERS", 16)))
    ap.add_argument("--motd", default=os.environ.get("INZOI_MP_MOTD", ""), help="message shown to players when they join")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--announce-restart", type=int, metavar="SECONDS",
                    help="tell the server running on this machine to have everyone save, then exit (restart it after)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    if args.announce_restart:
        async def announce():
            r, w = await asyncio.open_connection("127.0.0.1", args.port)
            w.write((json.dumps({"t": "announce_restart", "in": args.announce_restart}) + "\n").encode())
            await w.drain()
            print(json.loads(await asyncio.wait_for(r.readline(), 10)))
            w.close()
        asyncio.run(announce())
        return
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        log.info("shutting down")


if __name__ == "__main__":
    main()
