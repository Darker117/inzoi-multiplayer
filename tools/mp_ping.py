"""Check that an inZOI Multiplayer server is reachable and answering.

Usage:  python tools/mp_ping.py nox.local [port] [password]
"""
import json
import secrets
import socket
import sys
import time


def main(argv):
    host = argv[0] if argv else "127.0.0.1"
    port = int(argv[1]) if len(argv) > 1 else 24242
    password = argv[2] if len(argv) > 2 else ""
    t0 = time.perf_counter()
    try:
        s = socket.create_connection((host, port), timeout=5)
    except OSError as e:
        print(f"Can't reach {host}:{port} - {e}")
        return 1
    f = s.makefile("rwb")
    hello = {"t": "hello", "protocol": 1, "key": "ping-" + secrets.token_hex(12), "name": "ping test", "password": password}
    f.write((json.dumps(hello) + "\n").encode())
    f.flush()
    msg = json.loads(f.readline())
    ms = (time.perf_counter() - t0) * 1000
    if msg.get("t") != "welcome":
        print(f"{host}:{port} answered but refused: {msg.get('error')}")
        return 1
    print(f"OK {host}:{port} - server {msg.get('server_version')}, {len(msg['players'])} other player(s) online, "
          f"{len(msg['houses'])} house(s) stored, round trip {ms:.0f} ms")
    s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
