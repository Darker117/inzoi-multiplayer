"""inZOI Multiplayer companion: runs next to the game on each player's PC.

- Installs the inZOI Multiplayer mod into the game and loads it (no Mod Kit needed).
- Publishes your Zoi to the server: its profile (looks, name, personality, voice) once, and ~5x per second where it
  is, which way it faces, what it's doing and what it's wearing.
- Mirrors everyone else: their Zois become puppets in your world (through the mod's in-game controller), appearing
  where they are, walking where they walk, using the same things, joining in on socials with your Zoi.
- Serves the in-game panel (players online, chat, join a friend) on http://127.0.0.1:24243.

    python client/companion.py [--server my-pi.local] [--port 24242] [--name Ana] [--password ...]

(Players run it through client/launcher.py, the "inZOI Multiplayer.exe", which can also host the server.)

Settings are remembered in %APPDATA%/inzoi-mp/config.json (the secret player key lives there too).
"""
import argparse
import asyncio
import collections
import json
import logging
import os
import secrets
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import houses  # noqa: E402
import install  # noqa: E402
import webui  # noqa: E402
from game import Game, GameError, describe_act  # noqa: E402
from lua_data import Registry  # noqa: E402
from mailbox import Mailbox  # noqa: E402
from profile import member_lua, profile_hash, read_profile  # noqa: E402
from reports import Reports  # noqa: E402

PROTOCOL = 1
VERSION = "0.3.0"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "inzoi-mp"
CONFIG_FILE = CONFIG_DIR / "config.json"

log = logging.getLogger("companion")


def first_run_setup(cfg: dict, ask_server: bool = True):
    """Ask for what a new player must know (it can be changed later in the in-game panel)."""
    what = "Two quick questions" if ask_server else "One quick question"
    print(f"\n  Welcome to inZOI Multiplayer! {what} (change it any time in the in-game panel).\n")
    name = input(f"  Your name, as friends will see it [{cfg.get('name') or os.environ.get('USERNAME', 'Player')}]: ").strip()
    if name:
        cfg["name"] = name
    while ask_server and not cfg.get("server"):
        addr = input("  Server address (ask whoever hosts, e.g. 192.168.1.20 or my-pi.local:24242): ").strip()
        if addr:
            host, _, port = addr.partition(":")
            cfg["server"] = host
            if port.isdigit():
                cfg["port"] = int(port)
    print()


def read_config() -> dict:
    return json.loads(CONFIG_FILE.read_text("utf-8")) if CONFIG_FILE.exists() else {}


def load_config(args, ask_server: bool = True) -> dict:
    """Saved settings + command line. Asks for what's still missing when someone is there to answer.
    ask_server=False when hosting: the companion then connects to the server in this same program."""
    cfg = read_config()
    need_server = ask_server and not cfg.get("server") and not args.server
    if (need_server or (not cfg.get("name") and not args.name)) and sys.stdin and sys.stdin.isatty():
        first_run_setup(cfg, need_server)
    cfg.setdefault("key", secrets.token_urlsafe(24))
    for k in ("server", "port", "name", "password"):
        v = getattr(args, k, None)
        if v is not None:
            cfg[k] = v
    if ask_server:
        cfg.setdefault("server", "localhost")
    cfg.setdefault("port", 24242)
    cfg.setdefault("name", os.environ.get("USERNAME", "Player"))
    cfg.setdefault("password", "")
    cfg.pop("mailbox", None)                     # old development setting: the mailbox now lives inside the mod
    save_config(cfg)
    return cfg


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=1), "utf-8")


class Remote:
    """Another player, as seen from here."""

    def __init__(self, pid: str, name: str):
        self.pid, self.name = pid, name
        self.profile = None
        self.profile_hash = None
        self.state = None
        self.spawned = False
        self.spawn_requested = 0.0
        self.hidden = False
        self.act_sig = None          # last mirrored action (json) / anim / outfit, to act on changes only
        self.anim = None
        self.outfit = None


class Companion:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.game = Game()
        self.registry = Registry(self.game.lookup)
        self.mail = Mailbox(install.MAILBOX_DIR)
        self.reports = Reports(install.INSTALL_DIR / "out")
        self.remotes: dict[str, Remote] = {}
        self.me_id = None            # my player id on the server
        self.writer = None
        self.connected_at = 0.0
        self.n = 0                   # my position sample counter
        self.my_city = ""
        self.my_entity = None
        self.home = None             # {door, site} of my home, once known
        self.puppet_ids: dict[str, int] = {}     # player id -> puppet entity here (from the controller's heartbeat)
        self.mod = {"state": "waiting for the game", "beat": 0.0, "instance": None}
        self.chat = collections.deque(maxlen=60)
        self.notice = ""
        self.world = "out"
        self.leader = None           # player whose clock everyone may follow (the server picks; usually the host)
        self.leader_world = None     # latest {hour, minute, season, ...} from the leader
        self.world_synced = 0.0
        self.houses: dict[str, dict] = {}       # owner player id -> shared house meta {name, by, site, updated}
        self.house_waiters: dict[str, asyncio.Future] = {}
        self.objects = {}            # entity id -> object descriptor (or None), cached
        self.sent_profile = None     # fingerprint of the profile the server has
        self.cleaning = {}           # leftover puppet key -> when we asked to remove it
        self.hosting = None          # (port, password) when this program also runs the server (launcher "Host and play")
        install.MAILBOX_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ helpers
    async def g(self, fn, *a, **kw):
        """Run a (blocking) game call off the event loop."""
        return await asyncio.to_thread(fn, *a, **kw)

    def address(self) -> tuple[str, int, str]:
        """Where to connect: the server in this same program when hosting, else the one in the settings."""
        if self.hosting:
            return "127.0.0.1", self.hosting[0], self.hosting[1]
        return self.cfg["server"], int(self.cfg["port"]), self.cfg["password"]

    async def send(self, msg: dict):
        if self.writer:
            self.writer.write((json.dumps(msg, separators=(",", ":")) + "\n").encode())
            await self.writer.drain()

    def puppet_owner(self, entity_id: int) -> str | None:
        for pid, eid in self.puppet_ids.items():
            if eid == entity_id:
                return pid
        return None

    # ------------------------------------------------------------------ server connection
    async def run(self):
        try:
            await webui.serve(self.ui_routes())
        except OSError:
            raise SystemExit("inZOI Multiplayer is already running in another window. Use that one "
                             "(or close it first).") from None
        asyncio.create_task(self.game_loop())
        asyncio.create_task(self.mailbox_loop())
        backoff = 2
        while True:
            try:
                await self.session()
                backoff = 2
            except (OSError, asyncio.IncompleteReadError, ConnectionError) as e:
                log.warning("server connection lost: %s", e)
                self.notice = f"Can't reach the server ({self.address()[0]}): retrying"
            self.writer, self.me_id = None, None
            for r in list(self.remotes.values()):
                self.drop_remote(r)
            self.remotes.clear()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def session(self):
        host, port, password = self.address()
        log.info("connecting to %s:%d as %s", host, port, self.cfg["name"])
        reader, self.writer = await asyncio.open_connection(host, port, limit=32 * 1024 * 1024)
        self.connected_at = time.time()
        self.sent_profile = None
        await self.send({"t": "hello", "protocol": PROTOCOL, "key": self.cfg["key"], "name": self.cfg["name"],
                         "password": password})
        while True:
            line = await reader.readline()
            if not line:
                raise ConnectionError("server closed the connection")
            await self.on_message(json.loads(line))

    async def on_message(self, m: dict):
        t = m.get("t")
        if t == "welcome":
            self.me_id = m["id"]
            self.leader, self.leader_world, self.world_synced = m.get("leader"), m.get("world"), 0.0
            self.notice = ""
            log.info("joined as %s; %d other player(s) online%s", m["id"], len(m["players"]),
                     f" - {m['motd']}" if m.get("motd") else "")
            for p in m["players"]:
                self.update_remote(p)
            self.houses = {h["owner"]: h for h in m.get("houses") or []}
        elif t == "joined":
            log.info("%s joined", m["player"]["name"])
            self.update_remote(m["player"])
            self.system_line(f"{m['player']['name']} joined")
        elif t == "left":
            log.info("%s left", m.get("name"))
            r = self.remotes.pop(m["id"], None)
            if r:
                self.drop_remote(r)
            self.system_line(f"{m.get('name')} left")
        elif t == "profile":
            r = self.remotes.get(m["id"])
            if r:
                self.set_profile(r, m["profile"])
        elif t == "state":
            r = self.remotes.get(m["id"])
            if r:
                self.set_state(r, m["state"])
        elif t == "chat":
            await self.on_chat(m)
        elif t == "leader":
            self.leader = m.get("id")
        elif t == "house_updated":
            meta = m.get("meta") or {}
            self.houses[meta.get("owner")] = meta
            if meta.get("owner") != self.me_id:
                self.system_line(f"{meta.get('by') or 'Someone'} shared a house: {meta.get('name')}")
        elif t == "house":
            fut = self.house_waiters.pop(m.get("owner"), None)
            if fut and not fut.done():
                fut.set_result(m)
        elif t == "world":
            self.leader_world = m.get("world")
        elif t == "ping":
            await self.send({"t": "pong"})
        elif t == "kicked":
            log.warning("kicked: %s", m.get("reason"))
        elif t == "error":
            log.error("server: %s", m.get("error"))
            self.notice = f"Server: {m.get('error')}"
            if m.get("fatal"):
                raise ConnectionError(m.get("error"))

    # ------------------------------------------------------------------ chat
    def system_line(self, text: str):
        self.chat.append({"name": "", "text": text, "time": time.time(), "system": True})

    async def on_chat(self, m: dict):
        mine = m.get("id") == self.me_id
        self.chat.append({"name": m.get("name", "?"), "text": m.get("text", ""), "time": m.get("time", time.time()),
                          "mine": mine})
        log.info("[chat] %s: %s", m.get("name"), m.get("text"))
        who = self.my_entity if mine else self.puppet_ids.get(m.get("id"))
        if who:
            try:
                await self.g(self.game.bubble, who, m.get("text", ""))
            except GameError as e:
                log.debug("bubble: %s", e)

    # ------------------------------------------------------------------ remote players -> puppets
    def update_remote(self, p: dict):
        r = self.remotes.get(p["id"]) or Remote(p["id"], p["name"])
        r.name = p["name"]
        if p["id"] in self.puppet_ids:
            r.spawned = True                 # the controller already has their puppet
        self.remotes[p["id"]] = r
        if p.get("profile"):
            self.set_profile(r, p["profile"])
        if p.get("state"):
            self.set_state(r, p["state"])

    def set_profile(self, r: Remote, profile: dict):
        h = profile_hash(profile)
        if h == r.profile_hash:
            return
        first = r.profile_hash is None
        r.profile, r.profile_hash = profile, h
        lua, skipped = member_lua(profile, self.registry)
        if skipped:
            log.debug("profile of %s: skipped %s", r.name, skipped[:5])
        self.mail.set_member(r.pid, lua)
        if r.spawned and not first:      # their Zoi really changed (new look, name...): rebuild the puppet
            self.mail.op("despawn", key=r.pid)
            r.spawned = False
            self.puppet_ids.pop(r.pid, None)
        log.info("got %s's Zoi: %s %s (%s)", r.name, profile["first_name"], profile["last_name"], profile["gender"])

    def set_state(self, r: Remote, st: dict):
        r.state = st
        if not r.spawned:
            return
        if "n" in st:
            self.mail.add_point(r.pid, st["n"], st["x"], st["y"], st["z"], st.get("yaw", 0))
        if r.pid not in self.puppet_ids:
            return                       # puppet not confirmed yet; actions wait for it
        act = st.get("act")
        sig = json.dumps(act, sort_keys=True) if act else None
        if sig != r.act_sig:
            r.act_sig, r.anim = sig, None
            if act is None:
                self.mail.op("act_stop", key=r.pid)
            elif not act.get("npc"):
                op = {"bag": act["bag"], "x": st["x"], "y": st["y"]}
                if act.get("player"):
                    target = self.my_entity if act["player"] == self.me_id else self.puppet_ids.get(act["player"])
                    op["target"] = target    # None: with someone who isn't here, nothing to join in on
                elif act.get("obj"):
                    op.update({k: act[k] for k in ("obj", "ox", "oy", "oz")})
                    if st.get("anim"):
                        op["anim"] = st["anim"]
                if not act.get("player") or op["target"]:
                    self.mail.op("act", key=r.pid, **op)
        if act and act.get("npc") and st.get("anim") and st["anim"] != r.anim:
            r.anim = st["anim"]              # busy with someone only they have: at least show the motion
            self.mail.op("anim", key=r.pid, anim=st["anim"])
        if st.get("outfit") and st["outfit"] != r.outfit:
            r.outfit = st["outfit"]
            self.mail.op("outfit", key=r.pid, category=st["outfit"])

    def drop_remote(self, r: Remote):
        if r.spawned:
            self.mail.op("despawn", key=r.pid)
            r.spawned = False
        self.puppet_ids.pop(r.pid, None)
        self.mail.trails.pop(r.pid, None)

    async def manage_puppets(self):
        """Spawn puppets for players in my city, hide those who aren't."""
        if self.mod["state"] != "running":
            return                           # wait for the controller's heartbeat: it tells us which puppets exist
        for r in self.remotes.values():
            if not r.profile or not r.state:
                continue
            here = r.state.get("city") == self.my_city
            if not r.spawned and here and time.time() - r.spawn_requested > 8:
                tpl = await self.g(self.game.template_for, r.profile["gender"], r.profile["growth_step"])
                if tpl is None:
                    log.warning("no local %s %s Zoi to build %s's puppet on", r.profile["gender"],
                                r.profile["growth_step"], r.name)
                    continue
                extra = {"home_door": self.home["door"], "home_site": self.home["site"]} if self.home else {}
                self.mail.op("spawn", key=r.pid, template=tpl, near=self.my_entity,
                             x=r.state["x"], y=r.state["y"], z=r.state["z"], **extra)
                r.spawned, r.spawn_requested = True, time.time()
                r.act_sig = r.anim = r.outfit = None
                log.info("bringing %s's Zoi into your world", r.name)
            elif r.spawned and here == r.hidden:
                r.hidden = not here
                self.mail.op("hide", key=r.pid, on=r.hidden)

    async def sync_world(self):
        """The leader shares its clock and season; others match it if they ticked "Match the host's time"
        (it skips their game forward, so it's opt-in)."""
        if self.leader == self.me_id:
            env = await self.g(self.game.call, "environment.get_state")
            await self.send({"t": "world", "world": {k: env.get(k) for k in ("hour", "minute", "season", "weather")}})
            return
        w = self.leader_world
        if not w or not self.cfg.get("sync_time") or time.time() - self.world_synced < 600:
            return
        self.world_synced = time.time()
        env = await self.g(self.game.call, "environment.get_state")
        if w.get("season") and env.get("season") != w["season"]:
            await self.g(self.game.call, "environment.change_season", season=w["season"])
        behind = ((w["hour"] * 60 + w["minute"]) - (env["hour"] * 60 + env["minute"])) % 1440
        if 15 < behind < 720:            # only ever skip forward, and not by more than half a day
            log.info("matching the host's time: skipping %d minutes", behind)
            await self.g(self.game.call, "environment.time_skip", minutes=behind)

    async def check_home(self):
        """Know my home's front door, so friends' puppets can come in like invited guests (also after a move)."""
        home = await self.g(self.game.home_entry, self.my_entity)
        if not home:
            site = await self.g(self.game.home_site, self.my_entity)
            known = self.cfg.get("homes", {}).get(str(site))
            home = {"site": site, "door": known} if site and known else None
        if home and home != self.home:
            self.home = home
            self.cfg.setdefault("homes", {})[str(home["site"])] = home["door"]
            save_config(self.cfg)
            log.info("your home: lot %s, front door %s", home["site"], home["door"])
            for r in self.remotes.values():
                if r.spawned:
                    self.mail.op("admit", key=r.pid, door=home["door"], site=home["site"])

    # ------------------------------------------------------------------ the mod in the game
    async def ensure_mod(self):
        """Install the mod and make sure its in-game controller is running (heartbeat seen recently)."""
        changed = await self.g(install.install)
        alive = time.time() - self.mod["beat"] < 6
        if alive and not changed:
            return
        if alive:
            log.info("mod updated: reloading it in the game")
            await self.g(install.reload, self.game.call)
        else:
            self.mod["state"] = "loading"
            log.info("loading the multiplayer mod into the game: %s", await self.g(install.mount, self.game.call))
            for _ in range(16):
                await asyncio.sleep(0.5)
                if time.time() - self.mod["beat"] < 3:
                    return
            log.info("no answer from the mod yet: reloading Lua")
            await self.g(self.game.call, "luamod.reload")
            for _ in range(16):
                await asyncio.sleep(0.5)
                if time.time() - self.mod["beat"] < 3:
                    return
            self.mod["state"] = "not responding"
            log.warning("the mod isn't responding in the game")
        if changed and not alive:
            await self.g(self.game.call, "uimod.remount", mod_id=install.MOD_ID)    # pick up new panel files

    def on_report(self, kind: str, text: str):
        self.mod["beat"] = time.time()       # any report means the controller is there (on_begin runs even paused)
        if kind == "restart":
            self.mod["instance"] = text
            self.mod["state"] = "starting"   # its first heartbeat says which puppets it found
            log.info("in-game controller started (%s)", text)
            # a fresh controller re-reads the profiles; ops sent before it started were missed
            for r in self.remotes.values():
                r.act_sig = r.anim = r.outfit = None
        elif kind == "up":
            self.mod["beat"] = time.time()
            self.mod["state"] = "running"
            ids = {}
            for pair in filter(None, text.split(",")):
                key, _, eid = pair.partition("=")
                if eid.isdigit():
                    ids[key] = int(eid)
            self.puppet_ids = ids
            for key in ids:                  # puppets the controller already has (e.g. after a companion restart)
                r = self.remotes.get(key)
                if r and not r.spawned:
                    r.spawned, r.hidden = True, False
            # puppets nobody is playing any more (left while we were away, or saved into the game): remove
            if self.writer and self.me_id and time.time() - self.connected_at > 20:
                for key in ids:
                    r = self.remotes.get(key)
                    if (r is None or not r.spawned) and time.time() - self.cleaning.get(key, 0) > 15:
                        log.info("removing a leftover puppet (%s)", key)
                        self.cleaning[key] = time.time()
                        self.mail.op("despawn", key=key)
        elif kind == "spawned":
            key, _, eid = text.partition(" ")
            if eid.isdigit():
                self.puppet_ids[key] = int(eid)
        elif kind == "despawned":
            self.puppet_ids.pop(text, None)
        elif kind == "log":
            log.info("[game] %s", text)

    # ------------------------------------------------------------------ my Zoi -> server
    def describe_act(self, a: dict) -> dict | None:
        return describe_act(self.game, a, self.my_entity, self.puppet_owner, self.objects)

    async def game_loop(self):
        was_in_world, tick, last_profile_check, last_me = False, 0, 0.0, 0.0
        act, anim, outfit = None, None, None
        while True:
            try:
                world = self.world = await self.g(self.game.world)
                if world == "paused":
                    self.mod["beat"] = max(self.mod["beat"], time.time() - 3)   # no ticks while paused: not dead
                if world == "out":
                    if was_in_world:
                        log.info("left the world (menu / loading)")
                        self.mod["state"] = "waiting for the game"
                    was_in_world = False
                    await asyncio.sleep(2)
                    continue
                if not was_in_world:
                    was_in_world = True
                    await self.ensure_mod()
                tick += 1
                if time.time() - last_me > 1:
                    self.my_entity, last_me = await self.g(self.game.possessed), time.time()
                st = await self.g(self.game.state_of, self.my_entity)
                self.my_city = st["city"]
                if tick % 2 == 0:
                    a = await self.g(self.game.activity, self.my_entity)
                    act = await self.g(self.describe_act, a)
                    anim = a["anim"]["id"] if a.get("anim") else None
                if tick % 10 == 1:
                    try:
                        outfit = await self.g(self.game.outfit, self.my_entity)
                    except GameError:
                        pass
                if tick % 25 == 0 and time.time() - self.mod["beat"] > 10:
                    log.info("the mod went quiet: loading it again")
                    await self.ensure_mod()
                if self.writer and self.me_id:
                    if self.sent_profile is None or time.time() - last_profile_check > 30:
                        last_profile_check = time.time()
                        profile = await self.g(read_profile, self.game.call, self.my_entity)
                        h = profile_hash(profile)
                        if h != self.sent_profile:
                            await self.send({"t": "profile", "profile": profile})
                            self.sent_profile = h
                            log.info("shared your Zoi %s %s", profile["first_name"], profile["last_name"])
                        await self.check_home()
                    if tick % 50 == 3 and world == "play":
                        await self.sync_world()
                    self.n += 1
                    await self.send({"t": "state", "state": {"n": self.n, **st, "act": act, "anim": anim,
                                                              "outfit": outfit}})
                    await self.manage_puppets()
            except GameError as e:
                log.debug("game: %s", e)
                await asyncio.sleep(1)
            except (OSError, ConnectionError) as e:
                log.debug("send: %s", e)
            await asyncio.sleep(0.2)

    async def mailbox_loop(self):
        inject = install.MAILBOX_DIR / "inject.json"       # debugging: extra ops dropped in by tools
        while True:
            try:
                for kind, text in self.reports.poll():
                    self.on_report(kind, text)
                if inject.exists():
                    for op in json.loads(inject.read_text("utf-8")):
                        name = op.pop("op")
                        self.mail.op(name, **op)
                    inject.unlink()
                self.mail.flush()
            except PermissionError:
                pass                     # the game was reading the mailbox; next round
            except (OSError, ValueError) as e:
                log.warning("mailbox: %s", e)
            await asyncio.sleep(0.1)

    def despawn_all(self):
        """On the way out: take every puppet out of the world so none gets saved into the game."""
        for key in list(self.puppet_ids):
            self.mail.op("despawn", key=key)
        try:
            self.mail.flush()
        except OSError:
            pass

    # ------------------------------------------------------------------ in-game panel
    def ui_routes(self) -> dict:
        async def status(_):
            players = []
            for r in self.remotes.values():
                st = r.state or {}
                act = st.get("act") or {}
                players.append({"id": r.pid, "name": r.name,
                                "zoi": f"{r.profile['first_name']} {r.profile['last_name']}".strip() if r.profile else "",
                                "here": bool(r.pid in self.puppet_ids and not r.hidden),
                                "away": bool(st and st.get("city") != self.my_city),
                                "doing": act.get("bag", "")})
            return {"version": VERSION, "connected": bool(self.writer and self.me_id),
                    "server": "this PC" if self.hosting else self.cfg["server"],
                    "name": self.cfg["name"], "mod": self.mod["state"], "notice": self.notice,
                    "paused": self.world == "paused", "port": self.address()[1],
                    "host": self.leader == self.me_id, "sync_time": bool(self.cfg.get("sync_time")),
                    "players": players, "chat": list(self.chat)[-30:]}

        async def chat(body):
            text = str(body.get("text", "")).strip()[:500]
            if not text:
                return {"ok": False}
            if not self.writer:
                return {"error": "not connected to the server"}
            await self.send({"t": "chat", "text": text})
            return {"ok": True}

        async def join(body):
            eid = self.puppet_ids.get(body.get("id"))
            if not eid:
                return {"error": "they're not in your world right now"}
            await self.g(self.game.go_to, eid)
            return {"ok": True}

        async def settings(body):
            changed = False
            if self.hosting:                     # the panel shows "this PC": keep the friend's server for next time
                body = {k: v for k, v in body.items() if k not in ("server", "port", "password")}
            for k in ("name", "server", "password"):
                if k in body and str(body[k]).strip() and body[k] != self.cfg.get(k):
                    self.cfg[k] = str(body[k]).strip()
                    changed = True
            if "sync_time" in body:
                self.cfg["sync_time"] = bool(body["sync_time"])
                self.world_synced = 0.0
                save_config(self.cfg)
            if "port" in body and str(body["port"]).isdigit():
                changed = changed or int(body["port"]) != int(self.cfg["port"])
                self.cfg["port"] = int(body["port"])
            if changed:
                save_config(self.cfg)
                if self.writer:
                    self.writer.close()          # reconnect with the new settings
            return {"ok": True, "name": self.cfg["name"], "server": "this PC" if self.hosting else self.cfg["server"],
                    "port": self.address()[1], "sync_time": bool(self.cfg.get("sync_time"))}

        async def house_list(_):
            added = self.cfg.get("added_houses", {})
            shared = [{"owner": o, "name": h.get("name"), "by": h.get("by") or o, "lot": h.get("lot") or "",
                       "added": added.get(o) == h.get("updated")}
                      for o, h in self.houses.items() if o != self.me_id]
            mine = self.houses.get(self.me_id)
            return {"library": await self.g(houses.my_houses), "shared": shared,
                    "sharing": mine.get("name") if mine else None}

        async def share(body):
            if not self.writer:
                return {"error": "not connected to the server"}
            house = await self.g(houses.pack, str(body.get("id", "")))
            house["by"] = self.cfg["name"]
            if self.home:
                house["lot"] = await self.g(self.game.site_name, self.home["site"])
            await self.send({"t": "house_put", "house": house})
            log.info("shared your house %s", house["name"])
            return {"ok": True, "name": house["name"]}

        async def add_house(body):
            owner = str(body.get("owner", ""))
            if owner not in self.houses or not self.writer:
                return {"error": "that house isn't shared any more"}
            fut = self.house_waiters[owner] = asyncio.get_running_loop().create_future()
            await self.send({"t": "house_get", "owner": owner})
            m = await asyncio.wait_for(fut, 30)
            if not m.get("house"):
                return {"error": "that house isn't shared any more"}
            meta = m.get("meta") or {}
            title = await self.g(houses.unpack, m["house"], meta.get("by") or owner)
            self.cfg.setdefault("added_houses", {})[owner] = meta.get("updated")
            save_config(self.cfg)
            log.info("added %s to your library", title)
            return {"ok": True, "title": title}

        return {"/status": status, "/chat": chat, "/join": join, "/settings": settings,
                "/houses": house_list, "/share": share, "/add_house": add_house}


def setup_logging(verbose: bool):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    out = logging.StreamHandler()
    out.setFormatter(fmt)
    root.addHandler(out)
    f = RotatingFileHandler(CONFIG_DIR / "companion.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    f.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(f)


def on_console_close(fn):
    """Run fn when the console window is closed with its X (or Windows logs off / shuts down), not only on Ctrl+C.
    Windows allows a few seconds before it ends the process."""
    if os.name != "nt":
        return
    import ctypes

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
    def handler(event):
        if event in (2, 5, 6):                   # CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT
            fn()
            time.sleep(0.5)
            return 1
        return 0                                 # Ctrl+C: Python's own handler raises KeyboardInterrupt
    on_console_close.handler = handler           # keep the callback alive
    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)


def main():
    ap = argparse.ArgumentParser(description="inZOI Multiplayer companion")
    ap.add_argument("--server")
    ap.add_argument("--port", type=int)
    ap.add_argument("--name")
    ap.add_argument("--password")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    setup_logging(args.verbose)
    cfg = load_config(args)
    log.info("inZOI Multiplayer %s - server %s:%s, your name %s", VERSION, cfg["server"], cfg["port"], cfg["name"])
    comp = Companion(cfg)
    on_console_close(comp.despawn_all)
    try:
        asyncio.run(comp.run())
    except KeyboardInterrupt:
        comp.despawn_all()
        time.sleep(0.5)


if __name__ == "__main__":
    main()
