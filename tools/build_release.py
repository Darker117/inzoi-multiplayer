"""Build what friends download: one program, "inZOI Multiplayer.exe" (play, host, or both; the game mod is inside it),
and a zip with that exe, the README and the server script for a Raspberry Pi / Linux box.

    python tools/build_release.py
    python tools/build_release.py --publish notes.md     # and put it on GitHub as release v<version>

Every player's program updates itself from the latest GitHub release (client/updater.py), so publishing is how an
update reaches everyone. notes.md: its first line (without "#") is the release title, the rest its description.

The first run creates build/venv with PyInstaller in it (needs the internet once). Output in dist/:
    inZOI-Multiplayer.exe               the program on its own
    inZOI-Multiplayer-<version>.zip     inZOI Multiplayer.exe, README.txt, server for Raspberry Pi or Linux/
"""
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = ROOT / "dist"
VENV_PY = BUILD / "venv" / "Scripts" / "python.exe"
EXE_NAME = "inZOI Multiplayer"
LINUX_SERVER = ["inzoi_mp_server.py", "PROTOCOL.md", "inzoi-mp.service"]
SKIP_MOD = {"MPCmd.lua", "MPBulk.lua", "inject.json", "__pycache__", "out"}

BG, BLUE, MINT = (22, 34, 56), (90, 168, 240), (127, 209, 185)      # the in-game panel's colours


def pyinstaller() -> Path:
    if not VENV_PY.exists():
        subprocess.run([sys.executable, "-m", "venv", str(BUILD / "venv")], check=True)
        subprocess.run([str(VENV_PY), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "pyinstaller"],
                       check=True)
    return VENV_PY


# ---------------------------------------------------------------------------------------------------- icon
def _person(x, y, hx, hy, head, body, grow=0.0) -> bool:
    """A bust: round head at (hx, hy), shoulders below it (cut off by the icon's edge)."""
    if (x - hx) ** 2 + (y - hy) ** 2 <= (head + grow) ** 2:
        return True
    bx, by = hx, hy + head + 22 + body
    return ((x - bx) / (body + 8 + grow)) ** 2 + ((y - by) / (body + grow)) ** 2 <= 1


def _letter_i(x, y, cx, top, w, h, grow=0.0) -> bool:
    """A lowercase "i" (round dot over a rounded stem) - also a person: head and body."""
    r = w / 2 + grow
    if (x - cx) ** 2 + (y - (top + w / 2)) ** 2 <= (w * 0.58 + grow) ** 2:      # the dot
        return True
    y0, y1 = top + w * 1.55 + w / 2, top + h - w / 2                           # the stem: a capsule
    py = min(max(y, y0), y1)
    return (x - cx) ** 2 + (y - py) ** 2 <= r * r


def _shade(x, y):
    """Colour at a point of the 256x256 icon (None = transparent): two lowercase i's side by side, two players."""
    r = 56                                                      # rounded square, 8 px margin
    cx, cy = min(max(x, 8 + r), 248 - r), min(max(y, 8 + r), 248 - r)
    if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
        return None
    if _letter_i(x, y, 152, 46, 48, 168):
        return MINT
    if _letter_i(x, y, 152, 46, 48, 168, grow=11):             # a gap between the two
        return BG
    if _letter_i(x, y, 96, 70, 40, 140):
        return BLUE
    return BG


def _png(size: int, rgba: bytes) -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\0" + rgba[y * size * 4:(y + 1) * size * 4] for y in range(size))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def make_icon(path: Path):
    images = []
    for size, ss in ((256, 2), (64, 3), (48, 4), (32, 4), (16, 4)):
        px = bytearray()
        for y in range(size):
            for x in range(size):
                r = g = b = n = 0
                for j in range(ss):
                    for i in range(ss):
                        c = _shade((x + (i + 0.5) / ss) * 256 / size, (y + (j + 0.5) / ss) * 256 / size)
                        if c:
                            r, g, b, n = r + c[0], g + c[1], b + c[2], n + 1
                px += bytes((r // n, g // n, b // n, 255 * n // (ss * ss))) if n else b"\0\0\0\0"
        images.append((size, _png(size, bytes(px))))
    path.with_suffix(".png").write_bytes(images[0][1])
    entries, blobs, offset = b"", b"", 6 + 16 * len(images)
    for size, data in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + entries + blobs)


# ---------------------------------------------------------------------------------------------------- exe
VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers=(@T@, 0), prodvers=(@T@, 0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'inZOI Multiplayer (fan-made)'),
      StringStruct('FileDescription', 'inZOI Multiplayer'),
      StringStruct('FileVersion', '@V@'),
      StringStruct('InternalName', 'inZOI Multiplayer'),
      StringStruct('LegalCopyright', 'Fan-made mod, not affiliated with KRAFTON'),
      StringStruct('OriginalFilename', 'inZOI Multiplayer.exe'),
      StringStruct('ProductName', 'inZOI Multiplayer'),
      StringStruct('ProductVersion', '@V@')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def sync_versions(version: str):
    """One version number everywhere: the program's (client/companion.py VERSION) goes into the game mod (its .uplugin,
    which also becomes the mod_manifest Version the game records in saves), the panel's manifest and the server."""
    nums = [int(x) for x in (version.split(".") + ["0", "0"])[:3]]
    mod = ROOT / "mod" / "InZOIMultiplayer"
    plugin = mod / "InZOIMultiplayer.uplugin"
    data = json.loads(plugin.read_text("utf-8"))
    data.update(VersionName=version, Version=nums[0] * 10000 + nums[1] * 100 + nums[2])
    plugin.write_text(json.dumps(data, indent="\t") + "\n", "utf-8")
    panel = mod / "ui" / "mp" / "uimod_manifest.json"
    data = json.loads(panel.read_text("utf-8"))
    data["version"] = version
    panel.write_text(json.dumps(data, indent="\t") + "\n", "utf-8")
    server = ROOT / "server" / "inzoi_mp_server.py"
    text = server.read_text("utf-8")
    server.write_text(re.sub(r'^VERSION = "[^"]*"', f'VERSION = "{version}"', text, count=1, flags=re.M), "utf-8")


def build_exe(version: str) -> Path:
    stage = BUILD / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(ROOT / "mod" / "InZOIMultiplayer", stage / "mod" / "InZOIMultiplayer",
                    ignore=lambda d, names: [n for n in names if n in SKIP_MOD])
    icon, vfile = BUILD / "icon.ico", BUILD / "version_info.txt"
    make_icon(icon)
    nums = ", ".join((version.split(".") + ["0", "0"])[:3])
    vfile.write_text(VERSION_INFO.replace("@T@", nums).replace("@V@", version), "utf-8")
    subprocess.run([
        str(pyinstaller()), "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
        "--onefile", "--console", "--name", EXE_NAME, "--icon", str(icon), "--version-file", str(vfile),
        "--paths", str(ROOT / "client"), "--paths", str(ROOT / "server"),
        "--add-data", f"{stage / 'mod'}{os.pathsep}mod",
        "--add-data", f"{ROOT / 'client' / 'struct_cache.json'}{os.pathsep}.",
        "--exclude-module", "tkinter", "--exclude-module", "unittest", "--exclude-module", "pydoc",
        "--distpath", str(BUILD / "exe"), "--workpath", str(BUILD / "pyinstaller"), "--specpath", str(BUILD),
        str(ROOT / "client" / "launcher.py")], check=True)
    return BUILD / "exe" / f"{EXE_NAME}.exe"


def main():
    version = re.search(r'VERSION = "([^"]+)"', (ROOT / "client" / "companion.py").read_text("utf-8")).group(1)
    sync_versions(version)
    exe = build_exe(version)
    name = f"inZOI-Multiplayer-{version}"
    out = DIST / name
    if out.exists():
        shutil.rmtree(out)
    linux = out / "server for Raspberry Pi or Linux"
    linux.mkdir(parents=True)
    shutil.copy2(exe, out / exe.name)
    shutil.copy2(ROOT / "release" / "README.txt", out / "README.txt")
    for f in LINUX_SERVER:
        shutil.copy2(ROOT / "server" / f, linux / f)
    zpath = DIST / f"{name}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, Path(name) / f.relative_to(out))
    shutil.copy2(exe, DIST / "inZOI-Multiplayer.exe")
    print(f"{DIST / 'inZOI-Multiplayer.exe'}  ({exe.stat().st_size // 1024} KB)")
    print(f"{zpath}  ({zpath.stat().st_size // 1024} KB)")
    return version, zpath


def publish(version: str, zpath: Path, notes: Path):
    """GitHub release v<version> with the exe (what programs update to) and the zip."""
    text = notes.read_text("utf-8").strip()
    title, _, body = text.partition("\n")
    subprocess.run(["gh", "release", "create", f"v{version}", str(DIST / "inZOI-Multiplayer.exe"), str(zpath),
                    "--title", title.lstrip("#").strip(), "--notes", body.strip()], check=True, cwd=ROOT)
    print(f"published v{version}: every player's program offers it within a couple of hours, or at its next start")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", type=Path, metavar="NOTES", help="also create the GitHub release, with these notes")
    a = ap.parse_args()
    v, z = main()
    if a.publish:
        publish(v, z, a.publish)
