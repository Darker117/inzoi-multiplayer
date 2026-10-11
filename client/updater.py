"""Updates itself from GitHub: every release of github.com/Darker117/inzoi-multiplayer carries inZOI-Multiplayer.exe.

check() asks GitHub for the latest release; a newer one is downloaded in the background into %APPDATA%/inzoi-mp/update
and checked against the sha256 GitHub lists for it. The program then asks whether to restart now; apply() swaps the
running exe for the new one (Windows lets a running exe be renamed, not overwritten: the old one becomes
"<name>.old.exe" and is deleted by the next start) and starts it in the same mode.

Only the packaged exe updates itself. Run from source (python client/launcher.py), it just says a new version exists.
"""
import hashlib
import json
import logging
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "Darker117/inzoi-multiplayer"
API = os.environ.get("INZOI_MP_UPDATE_API") or f"https://api.github.com/repos/{REPO}/releases/latest"   # (tests: other)
ASSET = "inZOI-Multiplayer.exe"
DIR = Path(os.environ.get("APPDATA", Path.home())) / "inzoi-mp" / "update"
log = logging.getLogger("update")


def version_tuple(v: str) -> tuple:
    out = []
    for part in str(v).lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out + [0] * (3 - len(out)))


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def latest(current: str) -> dict | None:
    """The latest release if it's newer than current: {version, title, url, size, sha256}."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"inZOI-Multiplayer/{current}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        rel = json.loads(r.read().decode("utf-8"))
    version = str(rel.get("tag_name", "")).lstrip("vV")
    if not version or version_tuple(version) <= version_tuple(current) or rel.get("draft") or rel.get("prerelease"):
        return None
    asset = next((a for a in rel.get("assets", []) if a.get("name") == ASSET), None)
    if not asset:
        return None
    digest = str(asset.get("digest") or "")
    return {"version": version, "title": rel.get("name") or f"inZOI Multiplayer {version}",
            "url": asset["browser_download_url"], "size": int(asset.get("size") or 0),
            "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else None}


def ready_file(version: str) -> Path:
    return DIR / f"inZOI-Multiplayer-{version}.exe"


def download(info: dict, progress=None) -> Path:
    """Fetch the new exe (resumes nothing: it's ~11 MB) and check it. Returns its path."""
    dest = ready_file(info["version"])
    if dest.exists() and (not info["sha256"] or sha256(dest) == info["sha256"]):
        return dest
    DIR.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    digest = hashlib.sha256()
    req = urllib.request.Request(info["url"], headers={"User-Agent": "inZOI-Multiplayer"})
    with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as f:
        while block := r.read(256 * 1024):
            f.write(block)
            digest.update(block)
            if progress:
                progress(len(block))
    if info["sha256"] and digest.hexdigest() != info["sha256"]:
        part.unlink()
        raise ValueError("the downloaded update doesn't match GitHub's fingerprint")
    os.replace(part, dest)
    return dest


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pending(current: str) -> Path | None:
    """A downloaded update newer than this version, waiting to be applied."""
    best = None
    for f in DIR.glob("inZOI-Multiplayer-*.exe") if DIR.exists() else []:
        v = f.stem.split("inZOI-Multiplayer-", 1)[1]
        if version_tuple(v) > version_tuple(current) and (best is None or version_tuple(v) > version_tuple(best[0])):
            best = (v, f)
    return best[1] if best else None


def apply(new_exe: Path, args: list[str]):
    """Put the new exe where this one is and start it (in a window of its own). The caller exits right after."""
    exe = Path(sys.executable)
    old = exe.with_name(exe.stem + ".old.exe")
    try:
        old.unlink()
    except FileNotFoundError:
        pass
    exe.rename(old)
    try:
        os.replace(new_exe, exe)
    except OSError:
        old.rename(exe)                                  # put things back as they were
        raise
    # A one-file exe started from another one would otherwise inherit its unpacked files (gone once this one exits).
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    subprocess.Popen([str(exe), *args], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                     close_fds=True, env=env)


def clean_old():
    """Delete the exe a previous update replaced (it was still running then)."""
    if frozen():
        exe = Path(sys.executable)
        try:
            exe.with_name(exe.stem + ".old.exe").unlink()
        except OSError:
            pass
    for f in DIR.glob("*.part") if DIR.exists() else []:
        f.unlink(missing_ok=True)
