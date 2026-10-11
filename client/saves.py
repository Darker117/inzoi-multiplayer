"""The multiplayer save: each player plays multiplayer in a save of its own, so their normal saves stay untouched by
it (friends' Zois coming and going, the shared clock, friends' houses).

A save slot is Documents/inZOI/SaveGames/<folder>/<file>.usvx with its pictures in <folder>/<file>/, plus
Documents/inZOI/ModSave/<folder>/<file>/ModInfo.json (the mods it was saved with). The main slot's file is named like
its folder (a timestamp, YYYYMMDD-HHMMSS); autosaves add _AutoSave_<n>.

The game has no "save as" command, so the multiplayer copy is made on disk: the .usvx starts with a small header
(a JSON block, "IZTB", holding FolderName, FileName and SlotName) that must name the copy's own folder, or the game
would treat the copy as the original. The header and the whole file each carry a CRC32 (the file's is taken with its
own field zeroed); both are recomputed. New names are padded with spaces outside the JSON strings, so no length or
offset in the file changes.
"""
import json
import re
import shutil
import struct
import time
import zlib
from pathlib import Path

import install

INZOI = install.INSTALL_DIR.parents[2]                 # Documents/inZOI
SAVES = INZOI / "SaveGames"
MODSAVE = INZOI / "ModSave"


def _set(js: bytes, key: str, value: str) -> bytes:
    """Replace "key": "<old>" with the new value, padding with spaces so the block keeps its length."""
    m = re.search(rb'"' + key.encode() + rb'": "([^"]*)"', js)
    if not m:
        raise ValueError(f"save header has no {key}")
    new = f'"{key}": "{value}"'.encode()
    old = m.group(0)
    if len(new) > len(old):
        raise ValueError(f"new {key} is longer than the old one")
    return js[:m.start()] + new + b" " * (len(old) - len(new)) + js[m.end():]


def retitle(data: bytes, folder: str, file: str) -> bytes:
    """The save file renamed to belong to folder/file, as a manual save (not an autosave)."""
    if data[:4] != b"IZMS":
        raise ValueError("not an inZOI save file")
    first = struct.unpack("<I", data[24:28])[0]                # offset of the first block: the header
    if data[first:first + 4] != b"IZTB":
        raise ValueError("unexpected save file layout")
    size, jlen, crc = struct.unpack("<III", data[first + 4:first + 16])
    start = first + 16
    js = data[start:start + jlen]
    if zlib.crc32(js) != crc:
        raise ValueError("the save file's header is damaged")
    slot = re.sub(r"_AutoSave_\d+$", "", json.loads(js).get("SlotName", ""))
    js = _set(_set(_set(js, "FolderName", folder), "FileName", file), "SaveType", "Save")
    if slot:
        js = _set(js, "SlotName", slot)
    out = bytearray(data[:first + 12] + struct.pack("<I", zlib.crc32(js)) + js + data[start + jlen:])
    out[12:16] = b"\0\0\0\0"
    out[12:16] = struct.pack("<I", zlib.crc32(bytes(out)))
    return bytes(out)


def header(path: Path) -> dict:
    data = path.read_bytes()[:4096]
    first = struct.unpack("<I", data[24:28])[0]
    _, jlen, _ = struct.unpack("<III", data[first + 4:first + 16])
    return json.loads(data[first + 16:first + 16 + jlen])


def new_folder_name() -> str:
    t = time.time()
    while True:
        name = time.strftime("%Y%m%d-%H%M%S", time.localtime(t))
        if not (SAVES / name).exists() and not (MODSAVE / name).exists():
            return name
        t += 1


def copy_save(folder: str, file: str) -> str:
    """Copy one save slot into a new save of its own. Returns the new folder name."""
    src = SAVES / folder / f"{file}.usvx"
    new = new_folder_name()
    data = retitle(src.read_bytes(), new, new)
    dst = SAVES / new
    dst.mkdir(parents=True)
    try:
        (dst / f"{new}.usvx").write_bytes(data)
        if (SAVES / folder / file).is_dir():
            shutil.copytree(SAVES / folder / file, dst / new)
        if (MODSAVE / folder / file).is_dir():
            shutil.copytree(MODSAVE / folder / file, MODSAVE / new / new)
    except OSError:
        shutil.rmtree(dst, ignore_errors=True)
        shutil.rmtree(MODSAVE / new, ignore_errors=True)
        raise
    return new
