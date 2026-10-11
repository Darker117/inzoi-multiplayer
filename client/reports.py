"""The in-game controller -> companion channel.

The B2 puppet controller sends each report to the B1 script on the player's Zoi (inzoi.message.send_to_client),
which saves it with the game's uimod.cfg_save as <mod>/out/m<slot>.cfg. A report reads
"<instance> <n> <kind> <text>": instance is random per controller start, n counts up, 32 slots are reused.
"""
from pathlib import Path


class Reports:
    def __init__(self, folder: Path):
        self.folder = folder
        self.instance = None         # the controller instance we're following (the newest one seen)
        self.last_n = 0
        self.mtimes = {}
        # Reports already on disk are history (maybe from an earlier session): skip them, but keep following
        # their controller if it's still running.
        newest = (0, None, 0)
        for f in folder.glob("m*.cfg") if folder.exists() else []:
            try:
                self.mtimes[f.name] = mt = f.stat().st_mtime_ns
                parts = f.read_text("utf-8", "replace").split(" ", 2)
            except OSError:
                continue
            if len(parts) >= 2 and parts[1].isdigit():
                newest = max(newest, (mt, parts[0], int(parts[1])))
        _, self.instance, self.last_n = newest

    def poll(self) -> list[tuple[str, str]]:
        """New reports since the last call, oldest first, as (kind, text). ("restart", instance) comes first when a
        new controller instance shows up (the mod was loaded or reloaded)."""
        if not self.folder.exists():
            return []
        fresh = []
        for f in self.folder.glob("m*.cfg"):
            try:
                mt = f.stat().st_mtime_ns
                if self.mtimes.get(f.name) == mt:
                    continue
                self.mtimes[f.name] = mt
                text = f.read_text("utf-8", "replace").strip()
            except OSError:
                continue
            parts = text.split(" ", 3)
            if len(parts) >= 3 and parts[1].isdigit():
                fresh.append((mt, parts[0], int(parts[1]), parts[2], parts[3] if len(parts) > 3 else ""))
        if not fresh:
            return []
        out = []
        newest = max(fresh)[1]
        if newest != self.instance:
            self.instance, self.last_n = newest, 0
            out.append(("restart", newest))
        for _, inst, n, kind, body in sorted((e for e in fresh if e[1] == self.instance), key=lambda e: e[2]):
            if n > self.last_n:
                self.last_n = n
                out.append((kind, body))
        return out
