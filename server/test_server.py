"""End-to-end test of the server with two fake players. Run: python server/test_server.py"""
import asyncio
import json
import secrets
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inzoi_mp_server as mp  # noqa: E402


class Fake:
    def __init__(self, port, name, key=None, password=""):
        self.port, self.name, self.password = port, name, password
        self.key = key or secrets.token_urlsafe(24)

    async def connect(self):
        self.r, self.w = await asyncio.open_connection("127.0.0.1", self.port, limit=mp.MAX_LINE)
        await self.send({"t": "hello", "protocol": mp.PROTOCOL, "key": self.key, "name": self.name, "password": self.password})
        return await self.expect("welcome", "error")

    async def send(self, msg):
        self.w.write((json.dumps(msg) + "\n").encode())
        await self.w.drain()

    async def expect(self, *types, timeout=3):
        while True:
            line = await asyncio.wait_for(self.r.readline(), timeout)
            assert line, f"{self.name}: connection closed while waiting for {types}"
            msg = json.loads(line)
            if msg["t"] in types:
                return msg
            assert msg["t"] == "ping", f"{self.name}: expected {types}, got {msg}"


async def run():
    with tempfile.TemporaryDirectory() as tmp:
        server = mp.Server(mp.Store(Path(tmp)), password="pw")
        srv = await asyncio.start_server(server.handle, "127.0.0.1", 0, limit=mp.MAX_LINE)
        port = srv.sockets[0].getsockname()[1]

        bad = Fake(port, "Mallory", password="nope")
        assert (await bad.connect())["error"] == "wrong server password"

        a = Fake(port, "Ana", password="pw")
        wa = await a.connect()
        assert wa["t"] == "welcome" and wa["players"] == [] and wa["leader"] == wa["id"]

        b = Fake(port, "Ben", password="pw")
        wb = await b.connect()
        assert [p["name"] for p in wb["players"]] == ["Ana"]
        assert (await a.expect("joined"))["player"]["name"] == "Ben"

        await a.send({"t": "profile", "profile": {"first_name": "Ana", "gender": "Female"}})
        assert (await b.expect("profile"))["profile"]["first_name"] == "Ana"

        await a.send({"t": "state", "state": {"x": 1, "y": 2, "z": 3, "yaw": 90, "anim": "Idle"}})
        st = await b.expect("state")
        assert st["id"] == wa["id"] and st["state"]["yaw"] == 90

        await b.send({"t": "world", "world": {"hour": 9}})           # not the leader: ignored
        await a.send({"t": "world", "world": {"hour": 8, "minute": 30}})
        assert (await b.expect("world"))["world"]["hour"] == 8

        await b.send({"t": "chat", "text": "hi!"})
        assert (await a.expect("chat"))["text"] == "hi!"
        assert (await b.expect("chat"))["name"] == "Ben"              # chat echoes to the sender too

        await b.send({"t": "event", "to": wa["id"], "kind": "visit_request", "data": {"msg": "can I come over?"}})
        ev = await a.expect("event")
        assert ev["from"] == wb["id"] and ev["kind"] == "visit_request"

        house = {"name": "Ana's place", "walls": [[0, 0, 100, 0]] * 2000, "objects": [{"table_id": "Sofa_01", "x": 1}] * 3000}
        await a.send({"t": "house_put", "house": house})
        assert (await b.expect("house_updated"))["meta"]["owner"] == wa["id"]
        assert (await a.expect("house_updated"))["meta"]["name"] == "Ana's place"   # uploader is told too
        await b.send({"t": "house_get", "owner": wa["id"]})
        h = await b.expect("house")
        assert h["house"] == house

        # Ana reconnects with the same key: same id, old session kicked, Ben is told she left and re-joined.
        a2 = Fake(port, "Ana", key=a.key, password="pw")
        wa2 = await a2.connect()
        assert wa2["id"] == wa["id"] and len(wa2["houses"]) == 1
        assert (await a.expect("kicked"))["t"] == "kicked"
        assert (await b.expect("left"))["id"] == wa["id"]
        assert (await b.expect("joined"))["player"]["profile"]["first_name"] == "Ana"

        # Leader hand-off when the leader disconnects.
        a2.w.close()
        assert (await b.expect("left"))["id"] == wa["id"]
        assert (await b.expect("leader"))["id"] == wb["id"]

        b.w.close()
        srv.close()
        await srv.wait_closed()
    await mods_shared()
    await mods_hosted()
    print("all server tests passed")


def sha(data: bytes) -> str:
    return mp.hashlib.sha256(data).hexdigest()


async def files_conn(port, player):
    f = Fake(port, player.name, key=player.key)
    f.r, f.w = await asyncio.open_connection("127.0.0.1", port, limit=mp.MAX_LINE)
    await f.send({"t": "hello", "protocol": mp.PROTOCOL, "key": player.key, "name": player.name, "password": "",
                  "files": True})
    await f.expect("files_ok")
    return f


async def upload(f, data, step=3):
    h = sha(data)
    for o in range(0, len(data), step):                              # tiny pieces, to exercise the offsets
        await f.send({"t": "blob_put", "h": h, "o": o, "d": mp.base64.b64encode(data[o:o + step]).decode(),
                      "end": o + step >= len(data)})
    return await f.expect("blob_ok", "blob_bad")


async def download(f, h):
    out, o = b"", 0
    while True:
        await f.send({"t": "blob_get", "h": h, "o": o})
        m = await f.expect("blob")
        if m.get("error"):
            return m["error"]
        out += mp.base64.b64decode(m["d"])
        o = len(out)
        if m["end"]:
            return out


async def mods_shared():
    """A Pi-style server: everyone's mods are pooled, files go up and come down intact, only shared files are served."""
    with tempfile.TemporaryDirectory() as tmp:
        server = mp.Server(mp.Store(Path(tmp)))
        srv = await asyncio.start_server(server.handle, "127.0.0.1", 0, limit=mp.MAX_LINE)
        port = srv.sockets[0].getsockname()[1]
        a, b = Fake(port, "Ana"), Fake(port, "Ben")
        await a.connect()
        await b.connect()
        await a.expect("joined")
        pak, cfg = b"PAK-DATA-1234567", b'{"ok":1}'
        mod = {"id": "Top_A1", "name": "Top", "version": "1", "path": "88849/1_2/Top_A1",
               "files": [{"p": "a.pak", "h": sha(pak), "s": len(pak)}, {"p": "m.json", "h": sha(cfg), "s": len(cfg)}]}
        await a.send({"t": "mods", "mods": [mod, {"id": "broken", "files": [{"p": "x", "h": "nothex", "s": 1}]}]})
        ms = await b.expect("modset")
        assert ms["source"] == "everyone" and [m["id"] for m in ms["mods"]] == ["Top_A1"] and ms["mods"][0]["by"] == ["Ana"]
        assert ms["mods"][0]["size"] == len(pak) + len(cfg)
        assert (await a.expect("modset"))["mods"][0]["id"] == "Top_A1"   # the sender gets it too
        fa, fb = await files_conn(port, a), await files_conn(port, b)
        await fa.send({"t": "blob_check", "h": [sha(pak), sha(cfg)]})
        assert len((await fa.expect("blob_missing"))["h"]) == 2
        assert await download(fb, sha(pak)) == "not uploaded yet"
        assert (await upload(fb, pak, step=len(pak)))["t"] == "blob_bad"   # Ben can't upload files of Ana's mods
        assert (await upload(fa, pak))["t"] == "blob_ok"
        assert (await upload(fa, cfg))["t"] == "blob_ok"
        assert await download(fb, sha(pak)) == pak and await download(fb, sha(cfg)) == cfg
        assert await download(fb, sha(b"secret")) == "not shared"
        await fb.send({"t": "chat", "text": "hi"})                         # player messages don't go on file connections
        assert "belong" in (await fb.expect("error"))["error"]
        await b.send({"t": "mods", "mods": [{**mod, "id": "Hair_B", "name": "Hair", "path": "InGame/Hair_B"}]})
        ms = await a.expect("modset")
        assert [m["id"] for m in ms["mods"]] == ["Hair_B", "Top_A1"]       # pooled, by name
        for x in (a, b, fa, fb):
            x.w.close()
        srv.close()
        await srv.wait_closed()


async def mods_hosted():
    """Host and play: the host's mods are what everyone gets, whatever the others have; the host leads the clock."""
    with tempfile.TemporaryDirectory() as tmp:
        server = mp.Server(mp.Store(Path(tmp)), hosted=True)
        srv = await asyncio.start_server(server.handle, "127.0.0.1", 0, limit=mp.MAX_LINE)
        port = srv.sockets[0].getsockname()[1]
        guest, host = Fake(port, "Guest"), Fake(port, "Host")
        wg = await guest.connect()
        assert wg["leader"] == wg["id"] and wg["modset"]["source"] == "host" and wg["modset"]["mods"] == []
        host.r, host.w = await asyncio.open_connection("127.0.0.1", port, limit=mp.MAX_LINE)
        await host.send({"t": "hello", "protocol": mp.PROTOCOL, "key": host.key, "name": "Host", "password": "",
                         "host": True})
        wh = await host.expect("welcome")
        assert wh["host"] == wh["id"] and wh["leader"] == wh["id"]
        assert (await guest.expect("joined"))["player"]["leader"] is True
        assert (await guest.expect("leader"))["id"] == wh["id"]           # the host takes over the clock
        assert (await guest.expect("modset"))["host"] == wh["id"]
        data = b"x" * 10
        await guest.send({"t": "mods", "mods": [{"id": "GuestMod", "files": [{"p": "g", "h": sha(data), "s": 10}]}]})
        await host.send({"t": "mods", "mods": [{"id": "HostMod", "files": [{"p": "h", "h": sha(data), "s": 10}]}]})
        ms = await guest.expect("modset")
        assert [m["id"] for m in ms["mods"]] == ["HostMod"] and ms["mods"][0]["by"] == ["Host"]
        for x in (guest, host):
            x.w.close()
        srv.close()
        await srv.wait_closed()


if __name__ == "__main__":
    asyncio.run(run())
