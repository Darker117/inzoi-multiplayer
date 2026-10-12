"""End-to-end test of the servers page's calls, without the game: two real servers and a real companion, each with its
own folders and ports, talking through the same HTTP calls the page makes.
- "Nox Pi" keeps the public list (--directory); "Ana's place" is public and listed on it (--public --list-on).
- The companion starts on Nox Pi: it learns Nox Pi keeps a list, and Ana's place shows up in Public Servers.
- It checks Ana's place, joins it (switching servers), saves Nox Pi in its Private Servers, becomes an admin of Ana's
  place with its admin code, changes its welcome message, hosts a server of its own and plays there, stops hosting.
- Each server keeps its own multiplayer save (cfg by_server).
- A web page from elsewhere can't drive the program (its calls are refused).

    python tools/test_servers_page.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def call(panel: int, path: str, body: dict | None = None, origin: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(f"http://127.0.0.1:{panel}{path}", json.dumps(body or {}).encode(), headers)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def until(check, timeout=40, what="it"):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            last = check()
            if last:
                return last
        except (OSError, ValueError, KeyError) as e:
            last = e
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for {what} (last: {last!r})")


def main():
    procs = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        pi_port, ana_port, my_port, panel = free_port(), free_port(), free_port(), free_port()
        server = [sys.executable, str(ROOT / "server" / "inzoi_mp_server.py")]
        log = open(tmp / "companion.log", "w")
        try:
            procs.append(subprocess.Popen(server + ["--port", str(pi_port), "--data", str(tmp / "pi"), "--directory",
                                                    "--name", "Nox Pi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            procs.append(subprocess.Popen(server + ["--port", str(ana_port), "--data", str(tmp / "ana"), "--name",
                                                    "Ana's place", "--public", "--list-on", f"127.0.0.1:{pi_port}",
                                                    "--motd", "hi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            env = {**os.environ, "APPDATA": str(tmp / "appdata"), "INZOI_MP_DOCUMENTS": str(tmp / "docs"),
                   "INZOI_MP_GAME_URL": "http://127.0.0.1:9/mcp", "INZOI_MP_PANEL_PORT": str(panel),
                   "INZOI_MP_DIRECTORY_URL": "http://127.0.0.1:9/directory.json", "INZOI_MP_NO_MENU": "1",
                   "INZOI_MP_UPDATE_API": "http://127.0.0.1:9/latest"}
            procs.append(subprocess.Popen([sys.executable, str(ROOT / "client" / "companion.py"), "--server", "127.0.0.1",
                                           "--port", str(pi_port), "--name", "Tester"], env=env,
                                          stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT))
            state = lambda: call(panel, "/servers/state")                      # noqa: E731
            s = until(lambda: (st := state())["connected"] and st, what="the companion on Nox Pi")
            assert s["server"]["name"] == "Nox Pi" and s["server"]["directory"], s["server"]
            pi_id = s["server"]["id"]
            page = urllib.request.urlopen(f"http://127.0.0.1:{panel}/servers", timeout=5).read().decode()
            assert "servers.js" in page

            # A web page somewhere else can't use the program's calls.
            try:
                call(panel, "/servers/state", origin="https://evil.example")
                raise AssertionError("a foreign web page was let in")
            except urllib.error.HTTPError as e:
                assert e.code == 403

            # Public Servers: Ana's place, listed by Nox Pi, checked from here.
            pub = until(lambda: [r for r in state()["public"] if r["name"] == "Ana's place"], what="the public list")[0]
            assert pub["online"] and pub["check"]["verdict"] == "ready" and pub["public"] and pub["motd"] == "hi", pub
            checked = call(panel, "/servers/check", {"address": pub["address"]})
            assert checked["players"] == 0 and checked["ping"] is not None

            # Join it: the program switches servers.
            assert call(panel, "/servers/join", {"address": pub["address"]})["ok"]
            s = until(lambda: (st := state())["connected"] and st["server"]["name"] == "Ana's place" and st,
                      what="joining Ana's place")
            assert s["admin"] is False
            assert [r["name"] for r in s["saved"]] == ["Nox Pi"], s["saved"]  # the private server joined first; not public ones

            # Save Nox Pi in Private Servers, with a name.
            assert call(panel, "/servers/save", {"address": f"127.0.0.1:{pi_port}", "name": "The Pi"})["ok"]
            saved = {r["name"]: r for r in state()["saved"]}
            assert list(saved) == ["The Pi"] and saved["The Pi"]["server_name"] == "Nox Pi", saved.keys()  # your name wins

            # The admin console: not an admin; the admin code makes us one; change the welcome message.
            assert call(panel, "/admin", {"op": "status"})["ok"] is False
            code = json.loads((tmp / "ana" / "server.json").read_text())["admin_code"]
            assert call(panel, "/admin", {"op": "claim", "code": "wrong"})["ok"] is False
            assert call(panel, "/admin", {"op": "claim", "code": code})["ok"] is True
            st = call(panel, "/admin", {"op": "status"})
            assert st["ok"] and [p["name"] for p in st["players"]] == ["Tester"], st
            assert call(panel, "/admin", {"op": "set", "motd": "welcome back"})["ok"]
            assert json.loads((tmp / "ana" / "server.json").read_text())["motd"] == "welcome back"
            assert state()["admin"] is True

            # Host a server here and play on it; then stop and go back to a friend's.
            ho = call(panel, "/host/start", {"port": my_port, "name": "Tester's server", "password": "pw"})
            assert ho["ok"] and ho["hosting"]["port"] == my_port, ho
            s = until(lambda: (st := state())["connected"] and st["server"]["name"] == "Tester's server" and st,
                      what="playing on my own server")
            assert s["hosting"]["settings"]["password"] == "pw" and s["admin"] is True
            local = call(panel, "/admin", {"op": "status", "local": True})
            assert local["ok"] and local["hosted"] and local["settings"]["name"] == "Tester's server"
            assert call(panel, "/admin", {"op": "set", "local": True, "public": False, "motd": "my place"})["ok"]
            assert call(panel, "/host/stop")["ok"]
            assert state()["hosting"] is None
            assert call(panel, "/servers/join", {"address": f"127.0.0.1:{pi_port}"})["ok"]
            until(lambda: (st := state())["connected"] and st["server"]["name"] == "Nox Pi", what="back on Nox Pi")

            # Each server keeps its own multiplayer save slot.
            cfg = json.loads((tmp / "appdata" / "inzoi-mp" / "config.json").read_text())
            assert cfg["server_id"] == pi_id and len(cfg.get("by_server", {})) >= 2, cfg.get("by_server")
            assert cfg["host_motd"] == "my place"
            print("servers page tests passed")
        except Exception:
            log.flush()
            print((tmp / "companion.log").read_text()[-4000:])
            raise
        finally:
            for p in procs:
                p.terminate()
            for p in procs:
                try:
                    p.wait(10)
                except subprocess.TimeoutExpired:
                    p.kill()
            log.close()
            time.sleep(0.5)


if __name__ == "__main__":
    main()
