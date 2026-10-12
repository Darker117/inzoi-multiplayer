"""The real "Multiplayer" item on inZOI's main menu, and the servers page inside the game, come from a small Lua script
(mod/ue4ss/InZOIMultiplayer) run by UE4SS, the open-source script loader for Unreal Engine games
(github.com/UE4SS-RE/RE-UE4SS, MIT license). UE4SS is one DLL (dwmapi.dll) and a "ue4ss" folder next to the game's
exe; nothing of the game's own is changed, and deleting them undoes it (uninstall() does exactly that).

The program installs them once the player says yes, and keeps the script up to date: a newer script is copied over
and the running game reloads it by itself (the "reload" signal). If UE4SS was already there (the player uses it for
other mods), only our script is added to it.
"""
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path

log = logging.getLogger("ue4ss")

GAME_EXE = "inZOI-Win64-Shipping.exe"
MOD = "InZOIMultiplayer"
OURS = "installed_by_inzoi_multiplayer.json"          # in ue4ss/: marks a UE4SS that this program put there
STEAM_APP = Path("steamapps") / "common" / "inZOI" / "BlueClient" / "Binaries" / "Win64"
# the UE4SS mods we don't want running (UE4SS ships them enabled): our mods.txt for a fresh install
MODS_TXT = """CheatManagerEnablerMod : 0
ConsoleCommandsMod : 0
ConsoleEnablerMod : 0
SplitScreenMod : 0
LineTraceMod : 0
BPML_GenericFunctions : 0
BPModLoaderMod : 0
InZOIMultiplayer : 1

; Built-in keybinds, do not move up!
Keybinds : 0
"""


def _root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def runtime_dir() -> Path:
    """UE4SS itself (dwmapi.dll, ue4ss/UE4SS.dll, its settings and license): in the exe, or build/ue4ss_runtime."""
    frozen = _root() / "ue4ss_runtime"
    return frozen if frozen.exists() else _root() / "build" / "ue4ss_runtime"


def script_dir() -> Path:
    """Our Lua script: in the exe, or mod/ue4ss/InZOIMultiplayer."""
    frozen = _root() / "ue4ss_mod" / MOD
    return frozen if frozen.exists() else _root() / "mod" / "ue4ss" / MOD


def available() -> bool:
    return (runtime_dir() / "dwmapi.dll").exists() and (script_dir() / "Scripts" / "main.lua").exists()


# ---------------------------------------------------------------------------------------------- finding the game
def _process_path(pid: int) -> Path | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        buf, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return Path(buf.value)
    finally:
        k32.CloseHandle(h)
    return None


def _running_game() -> Path | None:
    try:
        import menu
        hwnd = menu.game_window()
        if hwnd:
            p = _process_path(menu._pid(hwnd))
            if p and p.name.lower() == GAME_EXE.lower():
                return p.parent
    except Exception as e:                                      # noqa: BLE001
        log.debug("running game: %s", e)
    return None


def _steam_libraries() -> list[Path]:
    roots = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
    roots.append(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam")
    libs = []
    for r in roots:
        libs.append(r)
        try:
            text = (r / "steamapps" / "libraryfolders.vdf").read_text("utf-8", "replace")
            libs += [Path(m.replace("\\\\", "\\")) for m in re.findall(r'"path"\s+"([^"]+)"', text)]
        except OSError:
            pass
    return list(dict.fromkeys(libs))


def game_binaries(cfg: dict | None = None) -> Path | None:
    """The folder with inZOI-Win64-Shipping.exe: the game's Binaries/Win64."""
    if os.environ.get("INZOI_MP_GAME_BIN"):                     # tests
        return Path(os.environ["INZOI_MP_GAME_BIN"])
    for cand in [_running_game(), Path(cfg["game_bin"]) if cfg and cfg.get("game_bin") else None,
                 *[lib / STEAM_APP for lib in _steam_libraries()]]:
        if cand and (cand / GAME_EXE).exists():
            return cand
    return None


# ---------------------------------------------------------------------------------------------- state
def state(binaries: Path | None) -> dict:
    """What's in the game folder: UE4SS (ours or the player's own), another DLL loader in its place, our script."""
    out = {"game": str(binaries) if binaries else None, "ue4ss": False, "ours": False, "other_loader": False,
           "script": None}
    if not binaries:
        return out
    u = binaries / "ue4ss"
    out["ue4ss"] = (binaries / "dwmapi.dll").exists() and (u / "UE4SS.dll").exists()
    out["ours"] = (u / OURS).exists()
    out["other_loader"] = (binaries / "dwmapi.dll").exists() and not out["ue4ss"]
    try:
        out["script"] = (u / "Mods" / MOD / "Scripts" / "version.txt").read_text("utf-8").strip()
    except OSError:
        pass
    return out


def _enable_in_mods_list(u: Path):
    """Our mod on in ue4ss/Mods/mods.txt (and mods.json, which newer UE4SS reads), keeping everything else."""
    mods = u / "Mods"
    txt = mods / "mods.txt"
    try:
        lines = txt.read_text("utf-8").splitlines()
    except OSError:
        lines = []
    if not any(re.match(rf"\s*{MOD}\s*:", ln) for ln in lines):
        # before the "Keybinds" lines, which UE4SS wants last
        at = next((i for i, ln in enumerate(lines) if "Keybinds" in ln or ln.startswith("; Built-in")), len(lines))
        lines.insert(at, f"{MOD} : 1")
    else:
        lines = [f"{MOD} : 1" if re.match(rf"\s*{MOD}\s*:", ln) else ln for ln in lines]
    txt.write_text("\n".join(lines) + "\n", "utf-8")
    js = mods / "mods.json"
    if js.exists():
        try:
            data = json.loads(js.read_text("utf-8"))
            if isinstance(data, list):
                found = False
                for m in data:
                    if m.get("mod_name") == MOD:
                        m["mod_enabled"], found = True, True
                if not found:
                    at = next((i for i, m in enumerate(data) if m.get("mod_name") == "Keybinds"), len(data))
                    data.insert(at, {"mod_name": MOD, "mod_enabled": True})
                js.write_text(json.dumps(data, indent=4) + "\n", "utf-8")
        except (OSError, ValueError):
            pass


# ---------------------------------------------------------------------------------------------- install, update
def install(binaries: Path, version: str, signals: Path | None = None) -> dict:
    """Put UE4SS (unless it's there already) and our script into the game's Binaries/Win64. Safe to call every
    start: it only copies what changed. With the game running, UE4SS itself can't be replaced (the game holds it),
    but a newer script is copied and the game is told to reload it. Returns state() plus "changed"/"restart"."""
    st = state(binaries)
    if st["other_loader"]:
        raise RuntimeError("another program's dwmapi.dll is in the game folder (a different mod loader), so UE4SS "
                           "can't go there too")
    rt, src = runtime_dir(), script_dir()
    u = binaries / "ue4ss"
    changed, restart = False, False
    if not st["ue4ss"]:
        (u / "Mods").mkdir(parents=True, exist_ok=True)
        for f in ("UE4SS.dll", "UE4SS-settings.ini", "LICENSE"):
            if (rt / "ue4ss" / f).exists():
                shutil.copy2(rt / "ue4ss" / f, u / f)
        (u / "Mods" / "mods.txt").write_text(MODS_TXT, "utf-8")
        (u / OURS).write_text(json.dumps({"by": "inZOI Multiplayer", "version": version}) + "\n", "utf-8")
        shutil.copy2(rt / "dwmapi.dll", binaries / "dwmapi.dll")       # last: UE4SS starts only once all is there
        changed = restart = True
        log.info("UE4SS installed in %s", binaries)
    _enable_in_mods_list(u)
    dest = u / "Mods" / MOD
    if st["script"] != version or not (dest / "Scripts" / "main.lua").exists():
        (dest / "Scripts").mkdir(parents=True, exist_ok=True)
        for f in (src / "Scripts").glob("*.lua"):
            shutil.copy2(f, dest / "Scripts" / f.name)
        stale = {p.name for p in (dest / "Scripts").glob("*.lua")} - {p.name for p in (src / "Scripts").glob("*.lua")}
        for name in stale:
            (dest / "Scripts" / name).unlink(missing_ok=True)
        (dest / "Scripts" / "signals_dir.txt").unlink(missing_ok=True)     # (a test folder never ships)
        (dest / "Scripts" / "version.txt").write_text(version + "\n", "utf-8")
        (dest / "enabled.txt").write_text("", "utf-8")
        changed = True
        restart = restart or not st["script"]                     # a new script loads when the game starts
        if signals and st["script"]:                              # an update, maybe with the game running
            signals.mkdir(parents=True, exist_ok=True)
            (signals / "reload").write_text(version, "utf-8")
        log.info("in-game script %s installed", version)
    out = state(binaries)
    out.update(changed=changed, restart=restart)
    return out


def uninstall(binaries: Path) -> bool:
    """Take our script out, and UE4SS too if this program put it there. The game must not be running."""
    st = state(binaries)
    u = binaries / "ue4ss"
    shutil.rmtree(u / "Mods" / MOD, ignore_errors=True)
    if st["ours"]:
        (binaries / "dwmapi.dll").unlink(missing_ok=True)
        shutil.rmtree(u, ignore_errors=True)
    else:
        try:
            txt = u / "Mods" / "mods.txt"
            txt.write_text("\n".join(ln for ln in txt.read_text("utf-8").splitlines()
                                     if not re.match(rf"\s*{MOD}\s*:", ln)) + "\n", "utf-8")
        except OSError:
            pass
    return True
