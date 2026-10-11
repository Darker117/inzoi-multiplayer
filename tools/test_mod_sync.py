"""End-to-end test of mod sync, without the game: two copies of the real companion code, each with its own fake Mods
folder and settings folder, meet on a test server, are offered the mods they're missing, say yes, and must end up
with identical files. An older copy of a mod is moved aside, and mods nobody asked for stay untouched.

    python tools/test_mod_sync.py

Scenario "host": host and play (the host's mods are everyone's). Scenario "shared": a stand-alone server like a
Raspberry Pi (everyone's mods are pooled; the newest build of a mod wins).
"""
import argparse
import asyncio
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "client"), str(ROOT / "server")]


def make_mod(root: Path, rel: str, mid: str, built: str, files: dict):
    d = root / rel
    for name, data in files.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)
    (d / "mod_manifest.json").write_text(json.dumps({"ProjectName": mid, "FriendlyName": mid, "Version": "1",
                                                     "PackageTime": built, "bEnable": True}))


async def player(role: str, port: int, hosting: bool, out: str):
    """One player's companion (no game: only its mod sync runs). Says yes to any mods offered."""
    import companion
    cfg = {"key": secrets.token_urlsafe(24), "name": role, "server": "127.0.0.1", "port": port, "password": ""}
    comp = companion.Companion(cfg)
    if hosting:
        comp.hosting = (port, "")
    asyncio.create_task(comp.mods_loop())
    asyncio.create_task(comp.session())
    result, deadline = {"state": "timeout"}, time.time() + 60
    while time.time() < deadline:
        await asyncio.sleep(0.3)
        o = comp.mod_offer
        if o and o["state"] == "ask":
            comp.answer_mods(o["key"], True)
        if o and o["state"] in ("done", "error", "close_game"):
            result = {"state": o["state"], "message": o["message"]}
            break
        if o is None and comp.mods_local is not None and comp.modset is not None and not comp.mod_share \
                and time.time() > deadline - 50:
            result = {"state": "nothing to get"}
    Path(out).write_text(json.dumps(result))
    await asyncio.sleep(3 if hosting or result["state"] == "done" else 0)   # let the other finish downloading


async def scenario(name: str, hosted: bool):
    import inzoi_mp_server as mp
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        a_mods, b_mods = tmp / "a-mods", tmp / "b-mods"
        pak = os.urandom(1_300_000)                   # bigger than one transfer chunk
        make_mod(a_mods, "88849/1_2/Top_X", "Top_X", "2026-09-08", {"Content/Paks/Windows/Top_X.pak": pak,
                                                                   "non_ufs/patch.json": b"{}"})
        make_mod(a_mods, "InGame/Hair_Y", "Hair_Y", "", {"lua/B2/Main.lua": b"-- hi"})
        make_mod(b_mods, "InGame/Top_X", "Top_X", "2026-01-01", {"old.pak": b"old"})     # an older build
        make_mod(b_mods, "InGame/Guest_Z", "Guest_Z", "", {"z.pak": b"z"})
        server = mp.Server(mp.Store(tmp / "server"), hosted=hosted)
        srv = await asyncio.start_server(server.handle, "127.0.0.1", 0, limit=mp.MAX_LINE)
        port = srv.sockets[0].getsockname()[1]

        def spawn(role, mods_dir, hosting):
            env = {**os.environ, "APPDATA": str(tmp / f"{role}-appdata"), "INZOI_MP_MODS_DIR": str(mods_dir),
                   "INZOI_MP_DOCUMENTS": str(tmp / f"{role}-documents"), "INZOI_MP_GAME_URL": "http://127.0.0.1:9/mcp"}
            return asyncio.create_subprocess_exec(
                sys.executable, __file__, "--player", role, "--port", str(port), "--out", str(tmp / f"{role}.json"),
                *(["--hosting"] if hosting else []), env=env)
        a = await spawn("Ana", a_mods, hosted)
        await asyncio.sleep(2)
        b = await spawn("Ben", b_mods, False)
        await asyncio.wait_for(asyncio.gather(a.wait(), b.wait()), 120)
        srv.close()
        ra, rb = (json.loads((tmp / f"{r}.json").read_text()) for r in ("Ana", "Ben"))
        print(f"[{name}] Ana: {ra}  Ben: {rb}")

        assert rb["state"] == "done", rb
        assert (b_mods / "88849/1_2/Top_X/Content/Paks/Windows/Top_X.pak").read_bytes() == pak
        assert (b_mods / "InGame/Hair_Y/lua/B2/Main.lua").read_bytes() == b"-- hi"
        assert not (b_mods / "InGame/Top_X").exists(), "the older Top_X should have been moved aside"
        aside = list((tmp / "Ben-appdata/inzoi-mp/replaced-mods").glob("Top_X-*"))
        assert aside and (aside[0] / "old.pak").read_bytes() == b"old"
        assert (b_mods / "InGame/Guest_Z/z.pak").read_bytes() == b"z"
        if hosted:                                    # the host's mods count: the guest's own aren't pushed to the host
            assert ra["state"] == "nothing to get", ra
            assert not (a_mods / "InGame/Guest_Z").exists()
        else:                                         # pooled: Ana gets Ben's mod, but not his older Top_X
            assert ra["state"] == "done", ra
            assert (a_mods / "InGame/Guest_Z/z.pak").read_bytes() == b"z"
            assert (a_mods / "88849/1_2/Top_X/Content/Paks/Windows/Top_X.pak").read_bytes() == pak
        print(f"[{name}] passed")


async def main():
    await scenario("host and play", hosted=True)
    await scenario("stand-alone server", hosted=False)
    print("mod sync tests passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--player")
    ap.add_argument("--port", type=int)
    ap.add_argument("--out")
    ap.add_argument("--hosting", action="store_true")
    args = ap.parse_args()
    if args.player:
        import logging
        logging.basicConfig(level=logging.INFO, format=f"  {args.player}: %(message)s")
        asyncio.run(player(args.player, args.port, args.hosting, args.out))
    else:
        asyncio.run(main())
