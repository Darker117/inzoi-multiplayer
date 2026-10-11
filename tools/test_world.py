"""End-to-end test of the shared world, without the game: two copies of the real companion code (each with its own
Documents and settings folders) meet on a test server.
- Ana has a multiplayer save and no world exists: she's offered to make it everyone's world, and uploads it (v1).
- Ben downloads it: it becomes his multiplayer save (a save of its own, header renamed, pictures and ModInfo along).
- Ana's game saves again while she's alone in the world: her program uploads v2, and Ben's program fetches it.

    python tools/test_world.py
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
sys.path[:0] = [str(ROOT / "client"), str(ROOT / "server"), str(ROOT / "tools")]
FOLDER = "20260101-120000"


def make_save(documents: Path, data_tag: bytes):
    from test_mp_save import fake_save
    saves = documents / "inZOI" / "SaveGames" / FOLDER
    (saves / FOLDER / "Portrait").mkdir(parents=True, exist_ok=True)
    blob = fake_save(FOLDER, FOLDER) + data_tag
    (saves / f"{FOLDER}.usvx").write_bytes(blob)
    (saves / FOLDER / "Portrait" / "1.png").write_bytes(b"PNG" + data_tag)
    modinfo = documents / "inZOI" / "ModSave" / FOLDER / FOLDER
    modinfo.mkdir(parents=True, exist_ok=True)
    (modinfo / "ModInfo.json").write_text('{"ModInfo": []}')
    return blob


async def player(role: str, port: int, out: str):
    import companion
    import saves
    docs = Path(os.environ["INZOI_MP_DOCUMENTS"])
    cfg = {"key": secrets.token_urlsafe(24), "name": role, "server": "127.0.0.1", "port": port, "password": ""}
    if role == "Ana":
        make_save(docs, b"v1")
        cfg["mp_save"] = {"folder": FOLDER, "name": "Sawyer"}
    comp = companion.Companion(cfg)
    asyncio.create_task(comp.session())
    result = {}

    async def until(check, timeout=30):
        end = time.time() + timeout
        while time.time() < end:
            if check():
                return True
            await asyncio.sleep(0.2)
        return False
    if role == "Ana":
        assert await until(lambda: comp.world_box and comp.world_box["key"] == "make"), "not offered"
        comp.world_action("make", "make")
        assert await until(lambda: comp.local_world().get("version") == 1), "v1 not uploaded"
        result["v1"] = True
        await asyncio.sleep(4)                                    # Ben downloads v1
        time.sleep(1.1)
        make_save(docs, b"v2-after-playing")                      # the game saved again
        comp.world_meta = comp.world_meta or {"version": 1}
        await comp.maybe_upload_world()
        result["v2"] = comp.local_world().get("version") == 2
        await asyncio.sleep(5)
    else:
        assert await until(lambda: comp.local_world().get("version") == 1, 40), "v1 not downloaded"
        folder = comp.cfg["mp_save"]["folder"]
        h = saves.header(saves.SAVES / folder / f"{folder}.usvx")
        result["v1"] = {"folder": folder, "header": h["FolderName"], "pictures":
                        (saves.SAVES / folder / folder / "Portrait" / "1.png").read_bytes().decode(),
                        "modinfo": (saves.MODSAVE / folder / folder / "ModInfo.json").exists()}
        assert await until(lambda: comp.local_world().get("version") == 2, 40), "v2 not downloaded"
        result["v2_pictures"] = (saves.SAVES / folder / folder / "Portrait" / "1.png").read_bytes().decode()
        result["same_folder"] = comp.cfg["mp_save"]["folder"] == folder
    Path(out).write_text(json.dumps(result))


async def main():
    import inzoi_mp_server as mp
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        server = mp.Server(mp.Store(tmp / "server"))
        srv = await asyncio.start_server(server.handle, "127.0.0.1", 0, limit=mp.MAX_LINE)
        port = srv.sockets[0].getsockname()[1]

        def spawn(role):
            env = {**os.environ, "APPDATA": str(tmp / f"{role}-appdata"), "INZOI_MP_DOCUMENTS": str(tmp / f"{role}-docs"),
                   "INZOI_MP_GAME_URL": "http://127.0.0.1:9/mcp", "INZOI_MP_PANEL_PORT": "0"}
            return asyncio.create_subprocess_exec(sys.executable, __file__, "--player", role, "--port", str(port),
                                                  "--out", str(tmp / f"{role}.json"), env=env)
        a = await spawn("Ana")
        await asyncio.sleep(3)
        b = await spawn("Ben")
        await asyncio.wait_for(asyncio.gather(a.wait(), b.wait()), 120)
        srv.close()
        ra, rb = (json.loads((tmp / f"{r}.json").read_text()) for r in ("Ana", "Ben"))
        print("Ana:", ra)
        print("Ben:", rb)
        assert ra == {"v1": True, "v2": True}, ra
        assert rb["v1"]["header"] == rb["v1"]["folder"] and rb["v1"]["pictures"] == "PNGv1" and rb["v1"]["modinfo"]
        assert rb["v2_pictures"] == "PNGv2-after-playing" and rb["same_folder"]
        assert (server.store.world_save() or {}).get("version") == 2
        print("shared world tests passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--player")
    ap.add_argument("--port", type=int)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.player:
        import logging
        logging.basicConfig(level=logging.INFO, format=f"  {a.player}: %(message)s")
        asyncio.run(player(a.player, a.port, a.out))
    else:
        asyncio.run(main())
