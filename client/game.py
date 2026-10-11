"""Everything the companion asks the running game, through its built-in control server (http://127.0.0.1:11212/mcp)."""
import json
import math
import os
import urllib.request

GAME_MCP = os.environ.get("INZOI_MP_GAME_URL") or "http://127.0.0.1:11212/mcp"     # (tests point it elsewhere)


# Interactions that are just getting somewhere: a puppet's own follow logic covers them.
MOVE_BAGS = ("ClickMove", "SelfMove", "Move_", "WalkTo", "Run_", "Sprint")


class GameError(Exception):
    pass


def describe_act(game, a: dict, me: int, owner_of, cache: dict) -> dict | None:
    """What other players need to copy an action: the interaction bag plus what it's done with.
    -> None (nothing worth copying: idle, walking, or the reply half of someone else's social)
       {"bag"}                         on its own (dance, phone...)
       {"bag", "player": id}           with another player's Zoi (owner_of maps puppet entity -> player id)
       {"bag", "obj", "ox", "oy", "oz"} with an object (found again by table id near that spot)
       {"bag", "npc": True}            with a character only this world has"""
    bag = a.get("bag")
    if not bag or bag == "None" or bag.startswith(MOVE_BAGS) or bag.endswith("_FeedBack"):
        return None
    d = {"bag": bag}
    t = a.get("target") or -1
    if t > 0 and t != me:
        pid = owner_of(t)
        if pid:
            d["player"] = pid
        else:
            if t not in cache:
                cache[t] = game.object_at(t)
            if cache[t]:
                d.update(cache[t])
            else:
                d["npc"] = True
    return d


class Game:
    def __init__(self, url: str = GAME_MCP):
        self.url = url
        self._templates = None          # (gender, growth) -> entity id of a local Zoi to build puppets on

    # ------------------------------------------------------------------ transport
    def call(self, tool: str, **args):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                           "params": {"name": tool.replace(".", "_"), "arguments": args}}).encode()
        req = urllib.request.Request(self.url, body, {"Content-Type": "application/json",
                                                      "Accept": "application/json, text/event-stream"})
        try:
            raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
        except OSError as e:
            raise GameError(f"inZOI isn't reachable ({e})") from None
        if raw.startswith(("event:", "data:")):
            raw = "\n".join(l[5:].strip() for l in raw.splitlines() if l.startswith("data:"))
        res = json.loads(raw).get("result", {})
        if res.get("structuredContent") is not None:
            out = res["structuredContent"]
        else:
            text = " ".join(c.get("text", "") for c in res.get("content", []))
            try:
                out = json.loads(text)
            except ValueError:
                out = {"_text": text}
        if res.get("isError") or (isinstance(out, dict) and "_error" in out):
            raise GameError(str(out))
        return out

    def lookup(self, struct: str) -> str:
        r = self.call("lua_api_lookup", type=struct)
        return r.get("_text", "") if isinstance(r, dict) else str(r)

    # ------------------------------------------------------------------ queries
    def in_world(self) -> bool:
        return self.world() != "out"

    def world(self) -> str:
        """'play' (the world is running), 'paused' (in the world, but held by build mode, menus, the map...),
        'stopped' (in the world, clock paused with the time controls), 'out'."""
        try:
            s = self.call("game.get_state")
        except GameError:
            return "out"
        if s.get("phase") not in ("in_game", "map_view") or (s.get("possessed_entity_id") or -1) <= 0:
            return "out"
        if s.get("phase") != "in_game" or (s.get("blocking") or {}).get("pause_reasons"):
            return "paused"
        try:
            if self.call("environment.get_simulation").get("is_paused"):
                return "stopped"                # the time controls are on pause: the mod's per-frame code stops too
        except GameError:
            pass
        return "play"

    def saves(self, limit: int = 10, autosave: bool = True, refresh: bool = False) -> list[dict]:
        """Save slots, newest first: {folder, file, slot, first_name, last_name, map, saved_time, is_broken, ...}."""
        r = self.call("game.list_saves", limit=limit, include_autosave=autosave, refresh=refresh)
        _, _, body = str(r.get("_text", "") if isinstance(r, dict) else r).partition("\n")
        return json.loads(body) if body.strip().startswith("[") else []

    def possessed(self) -> int:
        return int(self.call("entity.get_possessed")["entity_id"])

    def state_of(self, entity_id: int) -> dict:
        """Position, facing and whereabouts of a character: what other players need to mirror it."""
        r = self.call("entity.reflect", entity_id=entity_id)
        w = r["worldTransform"]
        t, q = w["translation"], w["rotation"]
        yaw = math.degrees(math.atan2(2 * (q["w"] * q["z"] + q["x"] * q["y"]), 1 - 2 * (q["y"] ** 2 + q["z"] ** 2)))
        return {"x": round(t["x"], 1), "y": round(t["y"], 1), "z": round(t["z"], 1), "yaw": round(yaw, 1),
                "city": r.get("locatedCityName") or "", "site": (r.get("locatedSiteId") or {}).get("value", -1)}

    def activity(self, entity_id: int) -> dict:
        """What a character is doing right now: interaction bag, its state/action type, target, and the motion."""
        cur = self.call("interaction.get_current", entity_id=entity_id)
        out = {"bag": cur.get("interaction_bag_id") if cur.get("playing") else None,
               "action": cur.get("action_type"), "target": cur.get("target_entity_id") or -1}
        try:
            m = self.call("motion.get_current", entity_id=entity_id)
            mo = (m.get("motions") or [None])[0]
            out["anim"] = mo and {"id": mo["anim_id"], "pos": mo.get("position", 0)}
        except GameError:
            out["anim"] = None
        return out

    def object_at(self, entity_id: int) -> dict | None:
        """Table id + world position of a game object, or None if it isn't one (a character, nothing)."""
        try:
            info = self.call("entity.get_object_info", entity_id=entity_id)
            t = self.call("entity.reflect", entity_id=entity_id)["worldTransform"]["translation"]
        except (GameError, KeyError):
            return None
        table = info.get("object_data_table_id")
        return table and {"obj": table, "ox": round(t["x"], 1), "oy": round(t["y"], 1), "oz": round(t["z"], 1)}

    def outfit(self, entity_id: int) -> str | None:
        """The outfit category a character is wearing now (situational overlays, like gym clothes, win)."""
        r = self.call("appearance.get_outfit_category", entity_id=entity_id)
        overlays = [o["category"] for o in r.get("active_overlays") or [] if o.get("category") not in (None, "None")]
        base = r.get("base_category")
        return overlays[-1] if overlays else (base if base not in (None, "None") else None)

    def bubble(self, entity_id: int, text: str, seconds: float = 6):
        self.call("entity.show_speech_bubble", entity_id=entity_id, text=text[:120], duration=seconds)

    def go_to(self, entity_id: int):
        """Teleport the player's Zoi next to another character."""
        self.call("movement.teleport_to", entity_id=entity_id)

    def template_for(self, gender: str, growth: str, exclude=()) -> int | None:
        """A local Zoi with the same gender and age: puppets borrow its body meshes and skeleton."""
        if self._templates is None:
            self._templates = {}
            for c in self.call("world.list_characters", limit=1000).get("characters", []):
                self._templates.setdefault((c.get("gender"), c.get("age_group")), []).append(c["entity_id"])
        for eid in self._templates.get((gender, growth), []):
            if eid not in exclude:
                return eid
        return None

    def home_site(self, entity_id: int) -> int | None:
        """Entity id of the lot a character lives on (None if homeless)."""
        hid = self.call("entity.get_character_info", entity_id=entity_id).get("home_site_id")
        if not hid or hid == "None":
            return None
        for s in self.call("world.get_loaded_sites").get("sites", []):
            if s.get("id") == hid:
                return s.get("entity_id")
        return None

    def site_name(self, site_entity: int) -> str:
        for s in self.call("world.get_loaded_sites").get("sites", []):
            if s.get("entity_id") == site_entity:
                return s.get("l10n") or s.get("id") or ""
        return ""

    def home_entry(self, entity_id: int) -> dict | None:
        """Front door + lot of a character's home, so visiting puppets can be let in like guests. The door can only
        be found while the character is at home (build.scan_objects scans the current lot): None until then."""
        site = self.home_site(entity_id)
        if site is None or self.state_of(entity_id)["site"] != site:
            return None
        try:
            objs = (self.call("build.scan_objects", table_id_prefix="Door", limit=0).get("objects", []))
        except GameError:
            return None
        doors = [o for o in objs if str(o.get("table_id", "")).startswith("Door") and "Bell" not in o["table_id"]]
        bells = [o for o in objs if "DoorBell" in str(o.get("table_id", ""))]
        if not doors:
            return None

        def d(a, b):
            la, lb = a["location"], b["location"]
            return math.hypot(la["x"] - lb["x"], la["y"] - lb["y"])
        front = min(doors, key=lambda o: min((d(o, b) for b in bells), default=0))
        return {"door": front["entity_id"], "site": site}
