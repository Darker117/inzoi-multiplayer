"""Update the server on the Raspberry Pi the friendly way: copy the new server over, warn everyone (their programs
save their games first: 0.5.2 and newer), wait, restart, and check it's back.

    python tools/deploy_pi.py [--wait 60] [--host nox@nox.local] [--address 100.107.110.78] [--no-directory]

The Pi also keeps the list of public servers (INZOI_MP_DIRECTORY=1 in ~/inzoi-mp/server.env) unless --no-directory.

Tell the people playing before you run it: their game goes to the main menu for a moment and comes back.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd[:4]), "...")
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def ping(address: str) -> str:
    return run([sys.executable, str(ROOT / "tools" / "mp_ping.py"), address]).stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="nox@nox.local", help="ssh target (key login)")
    ap.add_argument("--address", default="100.107.110.78", help="the server's address for players")
    ap.add_argument("--wait", type=int, default=60, help="seconds between the warning and the restart")
    ap.add_argument("--no-directory", action="store_true", help="don't keep the list of public servers on the Pi")
    a = ap.parse_args()
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", a.host]
    print("before:", ping(a.address))
    r = run(["scp", "-o", "BatchMode=yes", "-q", str(ROOT / "server" / "inzoi_mp_server.py"),
             str(ROOT / "server" / "PROTOCOL.md"), f"{a.host}:~/inzoi-mp/"])
    if r.returncode:
        sys.exit(f"copying failed: {r.stderr}")
    env = "~/inzoi-mp/server.env"
    setting = (f"sed -i '/^INZOI_MP_DIRECTORY=/d' {env} 2>/dev/null; true" if a.no_directory else
               f"grep -qs '^INZOI_MP_DIRECTORY=' {env} || echo 'INZOI_MP_DIRECTORY=1' >> {env}")
    r = run(ssh + [setting])
    print("public server list:", "off" if a.no_directory else "on", (r.stderr or "").strip())
    r = run(ssh + [f"python3 ~/inzoi-mp/inzoi_mp_server.py --announce-restart {a.wait}"])
    print("announced:", (r.stdout or r.stderr).strip())
    if r.returncode == 0:
        print(f"waiting {a.wait} s while everyone's game saves...")
        time.sleep(a.wait)
    r = run(ssh + ["systemctl --user restart inzoi-mp && systemctl --user is-active inzoi-mp"])
    print("restart:", (r.stdout or r.stderr).strip())
    time.sleep(2)
    print("after:", ping(a.address))


if __name__ == "__main__":
    main()
