"""The Multiplayer page inside inZOI: what it shows and what its buttons do.

The page itself is drawn by the game: the UE4SS script (mod/ue4ss/InZOIMultiplayer) puts a real "Multiplayer" item
on the main menu and turns the game's own Mods page into the servers page, out of the game's own widgets. It can't
reach the network, so the program does the thinking and they talk through files in %APPDATA%/inzoi-mp/ingame:

  program.json   program -> game  every 2 s: the program is running (the menu item is dimmed otherwise)
  page.json      program -> game  what the page shows (a "view model": rows, details, buttons, dialog), by "rev"
  events/*.json  game -> program  one file per click or change (open, tab, select, button, dialog, ...)
  game.json      game -> program  every second while the script runs (the program then draws no overlay item)

Everything a button does goes through the same calls the browser page uses (servers.Servers.server_routes), so the
two pages can't disagree.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("ingame")

FILTERS = [
    ("Status", [("all", "All Status"), ("online", "Online"), ("room", "Has Room"), ("offline", "Offline")]),
    ("Version Compatibility", [("all", "All"), ("ready", "Ready to Join"), ("problem", "Can't Join")]),
    ("Mods", [("all", "All Mods"), ("have", "You Have Them All"), ("download", "Mods to Download"), ("none", "No Mods")]),
    ("Access", [("all", "All"), ("open", "No Password"), ("password", "Password")]),
    ("Server Type", [("all", "All"), ("hosted", "Hosted by a Player"), ("standalone", "Always On")]),
]
CITY_THUMBS = {"dowon": "city_red", "seoul": "city_red", "blisbay": "city_blue", "blissbay": "city_blue",
               "santa": "city_blue", "cahaya": "city_cat", "kucingan": "city_cat"}


def mb(n) -> str:
    n = float(n or 0)
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"


def ago(seconds) -> str:
    s = int(seconds or 0)
    if s < 120:
        return f"{s} s"
    if s < 7200:
        return f"{s // 60} min"
    if s < 172800:
        return f"{s // 3600} h"
    return f"{s // 86400} days"


def same_address(a, b) -> bool:
    def n(x):
        x = str(x or "").strip().lower()
        return x if ":" in x else x + ":24242"
    return bool(a) and bool(b) and n(a) == n(b)


class InGame:
    """The in-game page's brain. `api(path, body)` makes the same calls the browser page makes; `open_mods()` asks
    the game to open its Mods page (the script turns it into ours); `toast(text)` shows the game's own message."""

    def __init__(self, signals: Path, api, open_mods, toast=None):
        self.dir = signals
        self.events = signals / "events"
        self.api = api
        self.open_mods = open_mods
        self.game_toast = toast
        self.open = False
        self.state = None
        self.state_at = 0.0
        self.tab = "public"
        self.selected = {"public": None, "private": None}
        self.checked: set[str] = set()
        self.search = ""
        self.filters = ["all"] * len(FILTERS)
        self.modal = None
        self.busy = False
        self.rev = 0
        self.written = None
        self.alive_at = 0.0
        self.wake = asyncio.Event()

    # ------------------------------------------------------------------ files
    def game_running(self) -> bool:
        """The UE4SS script is running in the game right now (then the program draws no overlay item)."""
        try:
            return time.time() - float(json.loads((self.dir / "game.json").read_text("utf-8")).get("alive", 0)) < 5
        except (OSError, ValueError, TypeError, AttributeError):
            return False

    def _write(self, name: str, data: dict):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / (name + ".part")
        tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
        os.replace(tmp, self.dir / name)

    def heartbeat(self, version: str):
        if time.time() - self.alive_at >= 2:
            self.alive_at = time.time()
            self._write("program.json", {"alive": int(time.time()), "version": version})

    def take_events(self) -> list[dict]:
        out = []
        try:
            names = sorted(p.name for p in self.events.iterdir() if p.suffix == ".json")
        except OSError:
            return out
        for name in names:
            p = self.events / name
            try:
                out.append(json.loads(p.read_text("utf-8")))
            except (OSError, ValueError):
                pass
            try:
                p.unlink()
            except OSError:
                pass
        return out

    # ------------------------------------------------------------------ the loop
    async def run(self, version: str):
        self.events.mkdir(parents=True, exist_ok=True)
        for p in self.events.glob("*"):                       # clicks left over from an earlier run
            try:
                p.unlink()
            except OSError:
                pass
        while True:
            try:
                self.heartbeat(version)
                events = self.take_events()
                for e in events:
                    await self.handle(e)
                if self.open and (events or time.time() - self.state_at > 1.5):
                    await self.refresh()
                if self.open:
                    self.publish()
            except Exception:                                  # noqa: BLE001 - keep the page alive
                log.exception("in-game page")
            try:
                await asyncio.wait_for(self.wake.wait(), 0.1)
            except asyncio.TimeoutError:
                pass
            self.wake.clear()

    async def refresh(self):
        try:
            self.state = await self.api("/servers/state", {})
            self.state_at = time.time()
        except Exception as e:                                 # noqa: BLE001
            log.debug("state: %s", e)

    def publish(self):
        vm = self.view()
        body = json.dumps(vm, sort_keys=True)
        if body != self.written:
            self.written = body
            self.rev += 1
            vm["rev"] = self.rev
            self._write("page.json", vm)

    def say(self, text: str):
        if self.game_toast and text:
            asyncio.get_running_loop().create_task(self.game_toast(text))

    # ------------------------------------------------------------------ events from the game
    async def handle(self, e: dict):
        t = e.get("t")
        if t == "open":
            self.open, self.modal = True, None
            await self.refresh()
            self.publish()                                      # ready before the page is built
            await self.open_mods()
        elif t == "opened":
            self.open = True
        elif t == "closed":
            self.open, self.modal = False, None
        elif t == "tab":
            self.tab = "private" if e.get("value") == "private" else "public"
            self.checked.clear()
        elif t == "select":
            self.selected[self.tab] = e.get("id")
            asyncio.get_running_loop().create_task(self.check(e.get("id"), quiet=True))
        elif t == "check":
            (self.checked.add if e.get("on") else self.checked.discard)(e.get("id"))
        elif t == "uncheck_all":
            self.checked.clear()
        elif t == "search":
            self.search = str(e.get("value") or "")
        elif t == "filter":
            i = int(e.get("index") or 0) - 1
            if 0 <= i < len(FILTERS):
                labels = {label: key for key, label in FILTERS[i][1]}
                self.filters[i] = labels.get(e.get("value"), "all")
        elif t == "reset":
            self.search, self.filters = "", ["all"] * len(FILTERS)
        elif t == "pill":
            await self.action(e.get("id"), None)
        elif t == "button":
            await self.action(e.get("id"), self.selected_row())
        elif t == "dialog":
            await self.dialog_answer(e.get("button"), e.get("fields") or {})

    # ------------------------------------------------------------------ the rows
    def here_row(self):
        s = self.state or {}
        ho = s.get("hosting")
        if not ho:
            return None
        st = ho.get("settings") or {}
        return {"address": f"127.0.0.1:{ho.get('port')}", "here": True, "saved": False, "online": True,
                "name": ho.get("name"), "description": st.get("description"), "motd": st.get("motd"),
                "players": ho.get("players"), "max_players": st.get("max_players"), "password": bool(st.get("password")),
                "public": st.get("public"), "current": ho.get("playing_here"),
                "connected": ho.get("playing_here") and s.get("connected"), "version": s.get("version"), "ping": 0,
                "hosted": True, "check": {"verdict": "ready", "line": "Your server, running in this program",
                                          "mods": [], "problems": []}, "mods_count": None, "names": []}

    def all_rows(self) -> list[dict]:
        s = self.state or {}
        if self.tab == "public":
            return list(s.get("public") or [])
        out = list(s.get("saved") or [])
        here = self.here_row()
        return [here] + [r for r in out if not r.get("here")] if here else out

    @staticmethod
    def verdict(r) -> str:
        if r.get("here"):
            return "here"
        if not r.get("online"):
            return "problem"
        v = (r.get("check") or {}).get("verdict")
        return {"ready": "ready", "download": "download", "full": "problem", "incompatible": "problem"}.get(v, "")

    def rows(self) -> list[dict]:
        q = self.search.strip().lower()
        fs, fc, fm, fa, ft = self.filters
        out = []
        for r in self.all_rows():
            vc = self.verdict(r)
            c = r.get("check") or {}
            if fs == "online" and not r.get("online"):
                continue
            if fs == "room" and not (r.get("online") and (r.get("players") or 0) < (r.get("max_players") or 0)):
                continue
            if fs == "offline" and r.get("online"):
                continue
            if fc == "ready" and not (vc in ("ready", "here", "download") or c.get("verdict") == "old"):
                continue
            if fc == "problem" and vc != "problem":
                continue
            if fm == "have" and c.get("missing") != 0:
                continue
            if fm == "download" and vc != "download":
                continue
            if fm == "none" and r.get("mods_count"):
                continue
            if fa == "open" and r.get("password"):
                continue
            if fa == "password" and not r.get("password"):
                continue
            if ft == "hosted" and not r.get("hosted"):
                continue
            if ft == "standalone" and r.get("hosted"):
                continue
            if q:
                hay = " ".join(str(x or "") for x in (r.get("name"), r.get("server_name"), r.get("description"),
                                                      r.get("address"), r.get("host"), " ".join(r.get("names") or [])))
                if q not in hay.lower():
                    continue
            out.append(r)
        out.sort(key=lambda r: (not r.get("here"), not r.get("online"), -(r.get("players") or 0),
                                str(r.get("name") or "").lower()))
        return out

    def selected_row(self):
        sel = self.selected.get(self.tab)
        return next((r for r in self.all_rows() if r.get("address") == sel), None)

    # ------------------------------------------------------------------ what's shown
    @staticmethod
    def state_tag(r):
        if r.get("here"):
            return {"text": "Hosting", "style": "blue"}
        if r.get("connected"):
            return {"text": "Connected", "style": "blue"}
        if not r.get("online"):
            return {"text": "Offline", "style": "gray"}
        c = r.get("check") or {}
        v = c.get("verdict")
        if v == "download":
            n = c.get("missing") or 0
            return {"text": f"{n} Mod{'' if n == 1 else 's'} to Get", "style": "light"}
        if v == "full":
            return {"text": "Full", "style": "gray"}
        if v == "incompatible":
            return {"text": "Can't Join", "style": "gray"}
        if v == "old":
            return {"text": "Older Server", "style": "gray"}
        return None

    def thumb(self, r) -> str:
        world = r.get("world") or {}
        city = str(world.get("map") or world.get("city") or "").lower().replace("_map", "").replace(" ", "")
        return CITY_THUMBS.get(city, "empty_thumb")

    def row_view(self, r, i) -> dict:
        vc = self.verdict(r)
        tags = []
        st = self.state_tag(r)
        if st:
            tags.append(st)
        if r.get("password") and not (st and st["style"] == "light"):
            tags.append({"text": "Password", "style": "light"})
        info = []
        if r.get("online"):
            info.append({"icon": "people", "text": f"{r.get('players') or 0} / {r.get('max_players') or '?'}"})
            mc = r.get("mods_count")
            info.append({"icon": "mods", "text": (f"{mc} mods" if mc else "No mods") if mc is not None else "Mods: ?"})
            if r.get("version"):
                info.append({"icon": "version", "text": str(r["version"])})
        else:
            info.append({"icon": "caution", "text": r.get("error") or "Offline"})
        badge = None if r.get("here") else "shield_ok" if vc in ("ready", "") and r.get("online") else "shield_alert"
        sel = self.selected.get(self.tab)
        return {"id": r.get("address"), "num": str(i + 1), "name": r.get("name") or r.get("address"),
                "badge": badge, "thumb": self.thumb(r), "tags": tags, "info": info,
                "checked": r.get("address") in self.checked, "selected": r.get("address") == sel}

    def details_view(self, r):
        if not r:
            return None
        s = self.state or {}
        c = r.get("check") or {}
        if r.get("connected"):
            status = {"icon": "shield_ok", "text": "You're playing on your own server" if r.get("here")
                      else "You're on this server"}
        elif not r.get("online"):
            status = {"icon": "shield_alert", "text": "Can't reach this server", "more": r.get("error") or "Offline"}
        else:
            ok = self.verdict(r) in ("ready", "here", "")
            more = " ".join((c.get("problems") or [])[1:])
            status = {"icon": "shield_ok" if ok else "shield_alert", "text": c.get("line") or "Ready to join",
                      "more": more}
        run_by = "You" if r.get("here") else (f"{r['host']} (plays on it too)" if r.get("host") else "A player") \
            if r.get("hosted") else "A stand-alone server"
        names = ", ".join(r.get("names") or [])
        rows = [{"icon": "person", "text": "Run by " + run_by},
                {"icon": "people", "text": f"{r.get('players') or 0} of {r.get('max_players') or '?'} playing"
                 + (f": {names}" if names else "")}]
        up = []
        if r.get("uptime"):
            up.append("Up for " + ago(r["uptime"]))
        if r.get("online") and not r.get("here") and r.get("ping") is not None:
            up.append(f"{r['ping']} ms")
        if up:
            rows.append({"icon": "clock", "text": " · ".join(up)})
        if r.get("version"):
            rows.append({"icon": "version", "text": "inZOI Multiplayer " + str(r["version"])})
        desc = []
        if r.get("description"):
            desc.append(r["description"])
        if r.get("motd"):
            desc.append("Welcome message: " + r["motd"])
        if r.get("current"):
            desc.append(("Connected as " + str(s.get("name"))) if s.get("connected") else (s.get("error") or "Connecting..."))
            if s.get("save"):
                desc.append("Your multiplayer save here: " + s["save"] + ("" if s.get("in_game") else
                            ". It loads by itself when you go back to the main menu."))
            o = (s.get("mods") or {}).get("offer")
            if o and o.get("state") in ("downloading", "waiting"):
                desc.append(f"Downloading mods: {mb(o.get('done'))} of {mb(o.get('total'))}")
            elif o and o.get("state") == "installing":
                desc.append("Installing the mods...")
        mods = c.get("mods")
        if mods is not None:
            if not mods:
                desc.append("This server uses no mods.")
            else:
                lines = []
                for m in mods[:14]:
                    what = "you have it" if m.get("state") == "ok" else f"{mb(m.get('size'))} to get" \
                        if m.get("state") == "missing" else f"yours is different: {mb(m.get('size'))}"
                    mark = "✓" if m.get("state") == "ok" else "↓" if m.get("state") == "missing" else "≠"
                    lines.append(f"{mark} {m.get('name')}{' ' + m['version'] if m.get('version') else ''} — {what}")
                if len(mods) > 14:
                    lines.append(f"... and {len(mods) - 14} more")
                desc.append(f"Mods ({len(mods)}):\n" + "\n".join(lines))
        ho = s.get("hosting") if r.get("here") else None
        if ho:
            addrs = ho.get("addresses") or []
            desc.append("Friends join with: " + (", ".join(a["address"] for a in addrs) if addrs else
                        "no address yet (install Tailscale and share this PC, or forward port "
                        f"{ho.get('port')})") + (" and your password" if (ho.get("settings") or {}).get("password") else ""))
        sub = []
        sub.append("Password" if r.get("password") else "No password")
        sub.append("Hosted by a player" if r.get("hosted") else "Always on")
        if c.get("source"):
            sub.append("Host's mods" if c["source"] == "host" else "Everyone's mods")
        return {"status": status, "name": r.get("name") or r.get("address"), "thumb": self.thumb(r), "rows": rows,
                "desc": "\n\n".join(desc), "category": "Public" if r.get("public") else "Private",
                "subcategory": " | ".join(sub)}

    def side_view(self, r):
        s = self.state or {}
        if self.checked:
            n = len(self.checked)
            buttons = [{"id": "check_all", "text": "Check Again", "style": "fill", "icon": "refresh"}]
            if self.tab == "private":
                buttons.append({"id": "remove_all", "text": "Remove", "style": "line", "icon": "trash"})
            return {"title": "Checked", "count": str(n), "uncheck": True,
                    "sub": {"icon": "people", "text": f"{n} server{'' if n == 1 else 's'}"}, "buttons": buttons}
        if not r:
            buttons = [{"id": "join", "text": "Join", "style": "fill", "icon": "enter", "enabled": False},
                       {"id": "check", "text": "Check Again", "style": "line", "icon": "refresh", "enabled": False}]
            return {"title": "Selected", "count": "", "sub": {"icon": "people", "text": "No server selected"},
                    "buttons": buttons}
        c = r.get("check") or {}
        buttons = []
        if r.get("here"):
            if not r.get("current"):
                buttons.append({"id": "join", "text": "Play Here", "style": "fill", "icon": "enter"})
            buttons.append({"id": "settings", "text": "Server Settings", "style": "line", "icon": "settings"})
            buttons.append({"id": "stop", "text": "Stop Hosting", "style": "line", "icon": "stop"})
        else:
            can = r.get("online") and c.get("verdict") not in ("incompatible", "full")
            if r.get("connected"):
                buttons.append({"id": "join", "text": "Connected", "style": "fill", "icon": "enter", "enabled": False})
            else:
                buttons.append({"id": "join", "text": "Join and Get Mods" if c.get("verdict") == "download" else "Join",
                                "style": "fill", "icon": "enter", "enabled": bool(can) and not self.busy})
            buttons.append({"id": "check", "text": "Check Again", "style": "line", "icon": "refresh"})
            if r.get("connected"):
                buttons.append({"id": "admin", "text": "Admin Console" if s.get("admin") else "Admin Code",
                                "style": "line", "icon": "settings"})
            if r.get("saved"):
                buttons.append({"id": "edit", "text": "Edit", "style": "line", "icon": "edit"})
                buttons.append({"id": "remove", "text": "Remove", "style": "line", "icon": "trash"})
            else:
                buttons.append({"id": "save", "text": "Save to Private", "style": "line", "icon": "plus"})
        sub = "Your server" if r.get("here") else f"{r.get('players') or 0} playing now" if r.get("online") else "Offline"
        return {"title": r.get("name") or r.get("address"), "count": "", "sub": {"icon": "people", "text": sub},
                "buttons": buttons}

    def view(self) -> dict:
        s = self.state or {}
        rows = self.rows()
        everything = self.all_rows()
        if not self.state:
            empty = "Connecting to the inZOI Multiplayer program..."
        elif everything:
            empty = "No server matches these filters."
        elif self.tab == "public":
            empty = ("No public servers right now. Host one yourself in Private Servers and make it public."
                     if s.get("directories") else "The list of public servers comes from a server that keeps one "
                     "(like a friend's Raspberry Pi). Join one in Private Servers first, or host your own.")
        else:
            empty = "No saved servers yet. Add one with its address (the friend who hosts gives it to you), or host your own."
        pills = []
        if self.tab == "private":
            pills.append({"id": "add", "text": "Add Server", "icon": "plus"})
            if not s.get("hosting"):
                pills.append({"id": "host", "text": "Host a Server", "icon": "home"})
        where = (s.get("server") or {}).get("name") or s.get("current") if s.get("connected") else None
        footer = (f"Online on {where} as {s.get('name')}" if where else (s.get("error") or "Not connected")) + \
            f"   ·   inZOI Multiplayer {s.get('version') or ''}"
        filters = []
        for i, (label, opts) in enumerate(FILTERS):
            value = dict(opts).get(self.filters[i], opts[0][1])
            filters.append({"label": label, "options": [o[1] for o in opts], "value": value})
        sel = self.selected_row()
        return {
            "title": "Multiplayer", "tabs": ["Public Servers", "Private Servers"], "tab": self.tab,
            "heading": "Public Servers" if self.tab == "public" else "Private Servers", "count": str(len(everything)),
            "pills": pills, "filters": filters, "all_label": "All", "all_count": str(len(rows)),
            "rows": [self.row_view(r, i) for i, r in enumerate(rows)], "empty": empty,
            "details": self.details_view(sel),
            "details_empty": "You can view details by selecting a server from the list on the left.",
            "side": self.side_view(sel), "footer": footer, "footer_icon": "info", "dialog": self.modal,
        }

    # ------------------------------------------------------------------ buttons
    async def check(self, address, quiet=False):
        if not address:
            return
        try:
            fresh = await self.api("/servers/check", {"address": address})
            if fresh.get("error") and not fresh.get("address") and not quiet:
                self.say(fresh["error"])
        except Exception as e:                                 # noqa: BLE001
            log.debug("check: %s", e)
        await self.refresh()
        self.wake.set()

    async def action(self, what, r):
        loop = asyncio.get_running_loop()
        if what == "add":
            self.modal = self.server_dialog(None)
        elif what == "host":
            s = self.state or {}
            self.modal = {"id": "host", "title": "Host a Server",
                          "desc": "Your server runs in this program while it's open, and you play on it too. "
                                  "Everyone who joins gets your mods.",
                          "fields": [{"id": "name", "label": "Server name", "value": (s.get("name") or "My") + "'s server"},
                                     {"id": "password", "label": "Password (optional)", "value": "", "secret": True},
                                     {"id": "max_players", "label": "Max players", "value": "16"}],
                          "toggles": [{"id": "public", "label": "Public server: listed for everyone", "on": False}],
                          "buttons": [{"id": "cancel", "text": "Cancel", "style": "line"},
                                      {"id": "start", "text": "Start Hosting", "style": "fill"}]}
        elif what == "check_all":
            for a in list(self.checked):
                loop.create_task(self.check(a, quiet=True))
            self.say("Checking the servers...")
        elif what == "remove_all":
            n = len(self.checked)
            self.modal = {"id": "remove_all", "title": f"Remove {n} server{'' if n == 1 else 's'}?",
                          "desc": "They leave your Private Servers list. You can add them again with their addresses.",
                          "buttons": [{"id": "cancel", "text": "Cancel", "style": "line"},
                                      {"id": "remove", "text": "Remove", "style": "fill"}]}
        elif not r:
            return
        elif what == "join":
            await self.join(r)
        elif what == "check":
            self.say("Checking " + (r.get("name") or r["address"]) + "...")
            loop.create_task(self.check(r["address"]))
        elif what == "edit":
            self.modal = self.server_dialog(r)
        elif what == "save":
            self.modal = self.server_dialog(r, adding=True)
        elif what == "remove":
            self.modal = {"id": "remove", "address": r["address"], "title": "Remove " + (r.get("name") or r["address"]) + "?",
                          "desc": "It leaves your Private Servers list. You can add it again with its address. "
                                  "(Your multiplayer save for it stays on your PC.)",
                          "buttons": [{"id": "cancel", "text": "Cancel", "style": "line"},
                                      {"id": "remove", "text": "Remove", "style": "fill"}]}
        elif what == "stop":
            self.modal = {"id": "stop", "title": "Stop hosting?",
                          "desc": "Everyone on your server is disconnected. Your server's settings, players and world "
                                  "stay saved for the next time you host.",
                          "buttons": [{"id": "cancel", "text": "Cancel", "style": "line"},
                                      {"id": "stop", "text": "Stop Hosting", "style": "fill"}]}
        elif what in ("admin", "settings"):
            s = self.state or {}
            if s.get("admin") or r.get("here"):
                self.modal = {"id": "wait", "title": "Admin Console", "desc": "Asking the server...", "buttons": []}
                loop.create_task(self.console(bool(r.get("here"))))
            else:
                self.modal = {"id": "claim", "title": "Admin Code",
                              "desc": "The server's owner can give you its admin code (it's printed with "
                                      "'inzoi_mp_server.py --admin-code' on the server's machine).",
                              "fields": [{"id": "code", "label": "Admin code", "value": ""}],
                              "buttons": [{"id": "cancel", "text": "Cancel", "style": "line"},
                                          {"id": "claim", "text": "Become Admin", "style": "fill"}]}
        self.wake.set()

    def server_dialog(self, r, adding=False):
        editing = r is not None and not adding
        return {"id": "server", "old": r.get("address") if editing and r.get("saved") else None,
                "title": "Edit Server" if editing else "Add a Server",
                "desc": "The friend who runs the server gives you its address (for a server over Tailscale, the "
                        "100.x.x.x address of their PC or Raspberry Pi). Add :port at the end if it isn't 24242.",
                "fields": [{"id": "address", "label": "Address", "value": r.get("address") if r else ""},
                           {"id": "password", "label": "Password (if it has one)", "value": "", "secret": True},
                           {"id": "name", "label": "Name in your list",
                            "value": (r.get("name") if r and r.get("name") != r.get("address") else "") or ""}],
                "buttons": [{"id": "cancel", "text": "Cancel", "style": "line"},
                            {"id": "save", "text": "Save", "style": "line"},
                            {"id": "save_join", "text": "Save and Join", "style": "fill"}]}

    async def join(self, r):
        if r.get("connected"):
            return
        c = r.get("check") or {}
        if not r.get("here"):
            if not r.get("online"):
                return self.say("Can't reach this server right now.")
            if c.get("verdict") == "incompatible":
                return self.say(c.get("line") or "Can't join this server.")
            if c.get("verdict") == "full":
                return self.say("This server is full.")
            if r.get("password") and not r.get("password_saved"):
                self.modal = {"id": "password", "address": r["address"], "name": r.get("name"),
                              "title": "Password for " + (r.get("name") or r["address"]),
                              "desc": "This server needs a password: the person running it can give it to you.",
                              "fields": [{"id": "password", "label": "Password", "value": "", "secret": True}],
                              "buttons": [{"id": "cancel", "text": "Cancel", "style": "line"},
                                          {"id": "join", "text": "Join", "style": "fill"}]}
                return
        await self.do_join(r["address"], "", r.get("name"))

    async def do_join(self, address, password, name):
        res = await self.api("/servers/join", {"address": address, "password": password, "name": name})
        if res.get("error"):
            return self.say(res["error"])
        self.tab = self.tab
        self.selected[self.tab] = address
        self.say("Joining " + (name or address) + "...")
        asyncio.get_running_loop().create_task(self.watch_join(address, name))

    async def watch_join(self, address, name):
        for _ in range(30):
            await asyncio.sleep(1)
            await self.refresh()
            s = self.state or {}
            if s.get("connected") and same_address(s.get("current"), address):
                o = (s.get("mods") or {}).get("offer")
                if o and o.get("state") == "ask":
                    n = len(o.get("names") or [])
                    self.modal = {"id": "mods", "key": o.get("key"), "title": "Get the mods this server uses?",
                                  "desc": f"{n} mod{'' if n == 1 else 's'} you don't have ({mb(o.get('size'))}): "
                                          + ", ".join((o.get("names") or [])[:8]) + ("..." if n > 8 else "")
                                          + ". Without them, some of the other players' clothes and things won't "
                                            "show up for you.",
                                  "buttons": [{"id": "no", "text": "Not Now", "style": "line"},
                                              {"id": "download", "text": "Download", "style": "fill"}]}
                    self.wake.set()
                else:
                    self.say("You're on " + (name or address) + ".")
                return
            if s.get("error"):
                return self.say(s["error"])

    async def dialog_answer(self, button, fields):
        m = self.modal or {}
        self.modal = None
        kind = m.get("id")
        if button in (None, "cancel", "close") or (button == "back" and not kind.startswith("c_")):
            return
        if kind == "server":
            body = {"address": str(fields.get("address") or "").strip(), "name": str(fields.get("name") or "").strip()}
            if fields.get("password"):
                body["password"] = fields["password"]
            if m.get("old"):
                body["old"] = m["old"]
            res = await self.api("/servers/save", body)
            if res.get("error"):
                m["error"] = res["error"]
                for f in m.get("fields") or []:
                    f["value"] = fields.get(f["id"], f.get("value", "")) if not f.get("secret") else ""
                self.modal = m
                return
            self.tab = "private"
            row = res.get("row") or {}
            self.selected["private"] = row.get("address") or body["address"]
            await self.refresh()
            if button == "save_join" and row:
                await self.join(row)
        elif kind == "password" and button == "join":
            await self.do_join(m["address"], str(fields.get("password") or ""), m.get("name"))
        elif kind == "remove" and button == "remove":
            await self.api("/servers/remove", {"address": m["address"]})
            self.selected["private"] = None
            self.say("Removed from Private Servers.")
        elif kind == "remove_all" and button == "remove":
            for a in list(self.checked):
                await self.api("/servers/remove", {"address": a})
            self.checked.clear()
            self.say("Removed from Private Servers.")
        elif kind == "stop" and button == "stop":
            await self.api("/host/stop", {})
            self.selected["private"] = None
            self.say("Your server is stopped.")
        elif kind == "host" and button == "start":
            try:
                mx = max(1, min(64, int(str(fields.get("max_players") or "16").strip() or 16)))
            except ValueError:
                mx = 16
            res = await self.api("/host/start", {"name": str(fields.get("name") or "").strip(),
                                                 "password": str(fields.get("password") or ""),
                                                 "public": bool(fields.get("public")), "max_players": mx})
            if res.get("error"):
                m["error"] = res["error"]
                self.modal = m
                return
            self.tab = "private"
            hosting = ((await self.api("/servers/state", {})) or {}).get("hosting") or {}
            self.selected["private"] = f"127.0.0.1:{hosting.get('port', 24242)}"
            self.say("Your server is running. Friends join with the addresses shown on the page.")
        elif kind == "claim" and button == "claim":
            res = await self.api("/admin", {"op": "claim", "code": str(fields.get("code") or "").strip()})
            if not res.get("ok"):
                m["error"] = res.get("error") or "That code didn't work."
                self.modal = m
                return
            self.say("You're an admin of this server now.")
            await self.console(False)
        elif kind == "mods" and button == "download":
            await self.api("/servers/get_mods", {})
            self.say("Downloading mods...")
        elif kind == "mods" and button == "no":
            await self.api("/mods", {"key": m.get("key"), "answer": "no"})
        elif kind in ("console", "c_settings", "c_players", "c_say", "c_restart"):
            await self.console_answer(kind, button, fields)
        await self.refresh()

    # ------------------------------------------------------------------ the admin console (game popups)
    async def console(self, local, show=None, error=None):
        """The admin console: the server at a glance, and its tools (each one a popup of the game's own)."""
        res = await self.api("/admin", {"op": "status", "local": local})
        if not res.get("ok"):
            self.modal = {"id": "info", "title": "Admin Console", "desc": res.get("error") or "Couldn't reach the server.",
                          "buttons": [{"id": "close", "text": "Close", "style": "fill"}]}
            self.wake.set()
            return
        self.admin_status, self.admin_local = res, local
        if show == "settings":
            self.modal = self.settings_dialog(res, error)
        elif show == "players":
            self.modal = self.players_dialog(res, error)
        else:
            self.modal = self.console_dialog(res, error)
        self.wake.set()

    @staticmethod
    def console_dialog(st, error=None):
        sv = st.get("settings") or {}
        online = st.get("players") or []
        lines = [f"{sv.get('name') or st.get('shown_name') or 'Server'}  ·  "
                 f"{'Public' if sv.get('public') else 'Private'}  ·  "
                 f"{'password' if sv.get('password') else 'no password'}  ·  inZOI Multiplayer {st.get('version')}",
                 f"Up for {ago(st.get('uptime'))}  ·  {len(online)} of {sv.get('max_players') or '?'} playing"
                 + (": " + ", ".join(p.get("name") or "?" for p in online) if online else "")]
        if st.get("admins"):
            lines.append("Admins: " + ", ".join(a.get("name") or "?" for a in st["admins"]))
        if st.get("bans"):
            lines.append("Banned: " + ", ".join(b.get("name") or "?" for b in st["bans"]))
        w = st.get("world")
        if w:
            lines.append(f"Shared world: version {w.get('version')}" + (f", saved by {w['by']}" if w.get("by") else ""))
        if st.get("admin_code"):
            lines.append(f"Admin code (give it only to people you trust): {st['admin_code']}")
        buttons = [{"id": "c_settings", "text": "Server Settings", "style": "line"},
                   {"id": "c_players", "text": "Players", "style": "line"},
                   {"id": "c_say", "text": "Message Everyone", "style": "line"}]
        if st.get("restartable"):
            buttons.append({"id": "c_restart", "text": "Restart", "style": "line"})
        buttons.append({"id": "close", "text": "Close", "style": "fill"})
        return {"id": "console", "title": "Admin Console", "desc": "\n".join(lines), "error": error, "buttons": buttons}

    @staticmethod
    def settings_dialog(st, error=None):
        sv = st.get("settings") or {}
        return {"id": "c_settings", "title": "Server Settings", "error": error,
                "desc": "Everyone on the server sees the new name and welcome message right away.",
                "fields": [{"id": "name", "label": "Server name", "value": sv.get("name") or ""},
                           {"id": "description", "label": "Description", "value": sv.get("description") or ""},
                           {"id": "motd", "label": "Welcome message", "value": sv.get("motd") or ""},
                           {"id": "password", "label": "Password (empty: none)", "value": sv.get("password") or "",
                            "secret": True},
                           {"id": "max_players", "label": "Max players", "value": str(sv.get("max_players") or 16)}],
                "toggles": [{"id": "public", "label": "Public: listed in Public Servers for everyone",
                             "on": bool(sv.get("public"))}],
                "buttons": [{"id": "back", "text": "Back", "style": "line"},
                            {"id": "save", "text": "Save", "style": "fill"}]}

    @staticmethod
    def players_dialog(st, error=None):
        online = st.get("players") or []
        lines = ["Online: " + (", ".join(f"{p.get('name')}{' (admin)' if p.get('admin') else ''}"
                                         f"{' (host)' if p.get('host') else ''}" for p in online) or "nobody")]
        if st.get("bans"):
            lines.append("Banned: " + ", ".join(b.get("name") or "?" for b in st["bans"]))
        lines.append("Type a player's name, then pick what to do.")
        return {"id": "c_players", "title": "Players", "desc": "\n".join(lines), "error": error,
                "fields": [{"id": "who", "label": "Player name", "value": ""},
                           {"id": "reason", "label": "Reason (optional, they see it)", "value": ""}],
                "buttons": [{"id": "back", "text": "Back", "style": "line"},
                            {"id": "kick", "text": "Kick", "style": "line"},
                            {"id": "ban", "text": "Ban", "style": "line"},
                            {"id": "unban", "text": "Unban", "style": "line"},
                            {"id": "admin_add", "text": "Make Admin", "style": "fill"}]}

    def find_player(self, name):
        st = getattr(self, "admin_status", None) or {}
        name = str(name or "").strip().lower()
        for group in ("players", "known", "bans"):
            for p in st.get(group) or []:
                if str(p.get("name") or "").lower() == name or str(p.get("id") or "").lower() == name:
                    return p
        return None

    async def console_answer(self, kind, button, fields):
        local = getattr(self, "admin_local", False)
        if kind == "console":
            if button == "c_settings":
                return await self.console(local, show="settings")
            if button == "c_players":
                return await self.console(local, show="players")
            if button == "c_say":
                self.modal = {"id": "c_say", "title": "Message Everyone",
                              "desc": "Shows up in everyone's chat as a message from the server.",
                              "fields": [{"id": "text", "label": "Message", "value": ""}],
                              "buttons": [{"id": "back", "text": "Back", "style": "line"},
                                          {"id": "send", "text": "Send", "style": "fill"}]}
                return
            if button == "c_restart":
                self.modal = {"id": "c_restart", "title": "Restart the server?",
                              "desc": "Everyone gets a minute's warning and their game is saved first; then the "
                                      "server restarts and everyone reconnects by themselves.",
                              "buttons": [{"id": "back", "text": "Back", "style": "line"},
                                          {"id": "restart", "text": "Restart in 1 Minute", "style": "fill"}]}
                return
            return
        if button == "back":
            return await self.console(local)
        if kind == "c_settings" and button == "save":
            body = {"op": "set", "local": local, **{k: str(fields.get(k) or "") for k in
                                                     ("name", "description", "motd", "password")},
                    "public": bool(fields.get("public"))}
            try:
                body["max_players"] = max(1, min(64, int(str(fields.get("max_players") or "16").strip())))
            except ValueError:
                return await self.console(local, show="settings", error="Max players must be a number.")
            res = await self.api("/admin", body)
            if not res.get("ok"):
                return await self.console(local, show="settings", error=res.get("error") or "Couldn't save.")
            self.say("Server settings saved.")
            return await self.console(local)
        if kind == "c_players" and button in ("kick", "ban", "unban", "admin_add"):
            p = self.find_player(fields.get("who"))
            if not p:
                return await self.console(local, show="players",
                                          error="No player by that name has been on this server.")
            body = {"op": button, "local": local, "id": p["id"], "reason": str(fields.get("reason") or "")}
            res = await self.api("/admin", body)
            if not res.get("ok"):
                return await self.console(local, show="players", error=res.get("error") or "That didn't work.")
            done = {"kick": "kicked", "ban": "banned", "unban": "unbanned", "admin_add": "is an admin now"}[button]
            self.say(f"{p.get('name')} {done}.")
            return await self.console(local, show="players")
        if kind == "c_say" and button == "send":
            res = await self.api("/admin", {"op": "say", "local": local, "text": str(fields.get("text") or "")})
            if not res.get("ok"):
                return await self.console(local, error=res.get("error"))
            self.say("Message sent.")
            return await self.console(local)
        if kind == "c_restart" and button == "restart":
            res = await self.api("/admin", {"op": "restart", "local": local, "in": 60})
            self.say("The server restarts in a minute." if res.get("ok") else (res.get("error") or "Couldn't restart."))
            return await self.console(local)
