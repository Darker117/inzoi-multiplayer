"""Sharing houses through the game's own library, so a friend can visit you in a home that looks exactly like yours.

inZOI keeps saved lots as folders in Documents/inZOI/Creations/MySites/<32 hex>/ (meta.json + site.dat + thumbnails).
The host shares one of theirs (it goes to the server); a visitor adds it to their own library and places it on the
same lot with the normal build tools. Lot coordinates are the same in every save, so the host's Zoi then walks
through the right rooms on the visitor's screen.
"""
import base64
import json
import secrets
from pathlib import Path

from install import _documents

LIBRARY = _documents() / "inZOI" / "Creations" / "MySites"
MAX_FILE = 8 * 1024 * 1024


def _meta(folder: Path) -> dict | None:
    try:
        return json.loads((folder / "meta.json").read_text("utf-8-sig"))
    except (OSError, ValueError):
        return None


def my_houses() -> list[dict]:
    """Houses the player saved to their library themselves (not the game's automatic backups), newest first."""
    out = []
    for folder in LIBRARY.glob("*") if LIBRARY.exists() else []:
        m = _meta(folder)
        if not m or m.get("IsTempSaveSite") or not (folder / "site.dat").exists():
            continue
        out.append({"id": folder.name, "title": m.get("Title") or "Untitled", "created": m.get("CreateTime", 0),
                    "beds": m.get("BedNum", 0), "floors": m.get("GroundFloors", 0),
                    "size": f"{m.get('Width', 0) // 100}x{m.get('Depth', 0) // 100} m"})
    return sorted(out, key=lambda h: -h["created"])


def pack(house_id: str) -> dict:
    folder = LIBRARY / house_id
    m = _meta(folder)
    if not m:
        raise FileNotFoundError("that house isn't in your library any more")
    files = {}
    for f in folder.iterdir():
        if f.is_file() and f.stat().st_size <= MAX_FILE:
            files[f.name] = base64.b64encode(f.read_bytes()).decode()
    return {"name": m.get("Title") or "Untitled", "site": m.get("SiteId", ""), "files": files}


def unpack(house: dict, owner_name: str) -> str:
    """Add a shared house to this player's library. Returns its title there."""
    files = house.get("files") or {}
    if "meta.json" not in files or "site.dat" not in files:
        raise ValueError("the shared house is incomplete")
    folder = LIBRARY / secrets.token_hex(16).upper()
    folder.mkdir(parents=True)
    for name, data in files.items():
        if "/" in name or "\\" in name or name.startswith("."):
            continue                                    # only plain file names, never paths
        (folder / name).write_bytes(base64.b64decode(data))
    meta = json.loads((folder / "meta.json").read_text("utf-8-sig"))
    title = f"{house.get('name') or 'House'} ({owner_name})"
    meta["Title"] = title
    meta["IsTempSaveSite"] = 0                          # a normal library entry, not an automatic backup
    (folder / "meta.json").write_text(json.dumps(meta, indent="\t", ensure_ascii=False), "utf-8")
    return title
