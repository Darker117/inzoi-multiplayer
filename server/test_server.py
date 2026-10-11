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
    print("all server tests passed")


if __name__ == "__main__":
    asyncio.run(run())
