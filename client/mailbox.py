"""The companion -> in-game controller channel: two Lua modules the B2 controller re-reads a few times a second.

MPCmd.lua  small, rewritten ~10x/s: one-shot ops (kept for a few seconds, the controller runs each id once) and the
           newest trail of every remote player.
MPBulk.lua big, rewritten only when a profile arrives: the rebuilt identities of remote players.
Both are written atomically (temp file + rename) so the game never reads half a file.
"""
import json
import os
import time
import uuid
from pathlib import Path


def lua(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(lua(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join(f"[{lua(k)}] = {lua(x)}" for k, x in v.items()) + "}"
    if isinstance(v, RawLua):
        return v.code
    raise TypeError(type(v))


class RawLua:
    def __init__(self, code: str):
        self.code = code


def write_atomic(path: Path, text: str):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:          # the game may be reading it right now
            time.sleep(0.02)
    raise PermissionError(path)


class Mailbox:
    def __init__(self, folder: Path, op_ttl: float = 4.0):
        self.cmd = folder / "MPCmd.lua"
        self.bulk = folder / "MPBulk.lua"
        self.ttl = op_ttl
        self.seq = int(time.time() * 10)
        self.bulk_seq = 0
        self.ops = []            # [(expires_at, op)]
        self.members = {}        # key -> Lua literal of FB1CustomizedCharacterInfo
        self.trails = {}         # key -> list of [n, x, y, z, yaw]

    def op(self, name: str, **fields):
        fields = {"id": uuid.uuid4().hex[:12], "op": name, **fields}
        self.ops.append((time.time() + self.ttl, fields))
        return fields["id"]

    def set_member(self, key: str, member_lua: str | None):
        if member_lua is None:
            self.members.pop(key, None)
        else:
            self.members[key] = member_lua
        self.bulk_seq += 1
        body = ", ".join(f"[{lua(k)}] = {v}" for k, v in self.members.items())
        write_atomic(self.bulk, f"return {{ seq = {self.bulk_seq}, members = {{ {body} }} }}\n")

    def add_point(self, key: str, n: int, x, y, z, yaw):
        t = self.trails.setdefault(key, [])
        t.append([n, x, y, z, yaw])
        del t[:-10]                      # the controller dedups by n; resending the last few covers missed polls

    def flush(self):
        now = time.time()
        self.ops = [(exp, o) for exp, o in self.ops if exp > now]
        ops = [o for _, o in self.ops]
        ops += [{"op": "trail", "key": k, "pts": pts} for k, pts in self.trails.items() if pts]
        self.seq += 1
        write_atomic(self.cmd, f"return {{ seq = {self.seq}, bulk = {self.bulk_seq}, ops = {lua(ops)} }}\n")
