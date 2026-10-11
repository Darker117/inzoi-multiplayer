"""inZOI Multiplayer, all in one program: play with friends, host the server for them, or both.

Double-click "inZOI Multiplayer.exe" (or run this file) and pick:
    1  Play            join a friend's server
    2  Host and play   run the server on this PC and play on it; friends connect to you
    3  Host only       just run the server (no game needed), e.g. on a PC that stays on
The choice is remembered and is the default next time (just press Enter).

    python client/launcher.py [--play | --host | --host-only] [--server ADDR] [--port N] [--password X]
                              [--name NAME] [--motd TEXT] [-v]

With --play, --server/--port/--password are the friend's server. With --host/--host-only, --port/--password/--motd
are your own server's (remembered). tools/build_release.py packages this with the companion, the server and the mod
into the exe.
"""
import argparse
import asyncio
import ipaddress
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "server")]
import companion  # noqa: E402
import inzoi_mp_server as mpserver  # noqa: E402

log = logging.getLogger("launcher")
MENU = [("play", "Play", "join a friend's server"),
        ("host", "Host and play", "run the server on this PC and play on it"),
        ("host-only", "Host only", "just run the server for friends (no game needed)")]
SERVER_DATA = companion.CONFIG_DIR / "server"
TAILNET = ipaddress.ip_network("100.64.0.0/10")


def interactive() -> bool:
    return bool(sys.stdin and sys.stdin.isatty())


def choose_mode(cfg: dict) -> str:
    modes = [m for m, _, _ in MENU]
    default = modes.index(cfg["mode"]) + 1 if cfg.get("mode") in modes else 1
    print(f"\n  inZOI Multiplayer {companion.VERSION}\n")
    for i, (mode, title, what) in enumerate(MENU, 1):
        if mode == "play" and cfg.get("server"):
            what += f" ({cfg['server']})"
        print(f"    {i}  {title:<15}{what}")
    while True:
        pick = input(f"\n  Pick 1-3 and press Enter [{default}]: ").strip() or str(default)
        if pick in ("1", "2", "3"):
            print()
            return modes[int(pick) - 1]


def host_settings(cfg: dict, args) -> tuple[int, str, str]:
    """Your own server's port/password/motd: from the command line, else remembered, else asked once."""
    if args.port:
        cfg["host_port"] = args.port
    if args.password is not None:
        cfg["host_password"] = args.password
    if args.motd is not None:
        cfg["host_motd"] = args.motd
    if "host_password" not in cfg and interactive():
        cfg["host_password"] = input("  A password for your server, so only friends can join (Enter for none): ").strip()
        if cfg["host_password"]:
            print("  Friends type it in the in-game panel: Settings, Password.")
        print()
    cfg.setdefault("host_port", 24242)
    cfg.setdefault("host_password", "")
    cfg.setdefault("host_motd", "")
    return int(cfg["host_port"]), cfg["host_password"], cfg["host_motd"]


def lan_address() -> str | None:
    """This PC's address on the home network (the interface that leads to the internet; nothing is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") or ipaddress.ip_address(ip) in TAILNET else ip
    except OSError:
        return None
    finally:
        s.close()


def tailscale_self() -> tuple[str | None, str | None]:
    """(MagicDNS name, Tailscale IPv4) of this PC, if it's on Tailscale."""
    exe = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
    try:
        out = subprocess.run([exe, "status", "--json", "--peers=false"], capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        me = json.loads(out.stdout).get("Self") or {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, None
    ips = [ip for ip in me.get("TailscaleIPs") or [] if "." in ip]
    return (me.get("DNSName") or "").rstrip(".") or None, ips[0] if ips else None


def show_addresses(port: int):
    at = "" if port == 24242 else f":{port}"
    print(f"\n  Your server is running. Friends put this address in the panel's Settings, Server:")
    lan = lan_address()
    if lan:
        print(f"    {lan + at:<44} friends on your home network")
    name, ts_ip = tailscale_self()
    if name or ts_ip:
        print(f"    {(name or ts_ip) + at:<44} friends anywhere, over Tailscale (share this PC with them in Tailscale)")
    else:
        print(f"  Friends on other networks need Tailscale (see the README), or port {port} (TCP) forwarded to this")
        print("  PC in your router.")
    print("  If Windows asks whether inZOI Multiplayer may use the network, allow it.")
    print("  Keep this window open while friends play.\n")


async def run(mode: str, cfg: dict, comp):
    if mode != "play":
        args = argparse.Namespace(host="0.0.0.0", port=cfg["host_port"], password=cfg["host_password"],
                                  motd=cfg["host_motd"], max_players=16, data=str(SERVER_DATA))
        try:
            hosted = await mpserver.start(args)          # noqa: F841 - keep it referenced while we run
        except OSError as e:
            raise SystemExit(f"Can't host on port {args.port}: {e.strerror or e}. Is a server already running on "
                             "this PC?") from None
        show_addresses(args.port)
    if comp:
        await comp.run()
    else:
        await asyncio.Event().wait()


def main():
    ap = argparse.ArgumentParser(description="inZOI Multiplayer: play together, host a server, or both")
    how = ap.add_mutually_exclusive_group()
    how.add_argument("--play", dest="mode", action="store_const", const="play", help="join a friend's server")
    how.add_argument("--host", dest="mode", action="store_const", const="host", help="host on this PC and play")
    how.add_argument("--host-only", dest="mode", action="store_const", const="host-only", help="just host")
    ap.add_argument("--server", help="the friend's server address (play)")
    ap.add_argument("--port", type=int, help="the server's port (play: theirs, host: yours)")
    ap.add_argument("--password", help="the server's password (play: theirs, host: yours)")
    ap.add_argument("--name", help="your name, as friends see it")
    ap.add_argument("--motd", help="welcome message for players joining your server (host)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.SetConsoleTitleW("inZOI Multiplayer")
        # In the classic console a click starts a text selection, and that freezes the program until Esc: turn off
        # QuickEdit (0x40), keeping ENABLE_EXTENDED_FLAGS (0x80) so the change sticks.
        stdin, mode = k32.GetStdHandle(-10), ctypes.c_uint()
        if k32.GetConsoleMode(stdin, ctypes.byref(mode)):
            k32.SetConsoleMode(stdin, (mode.value & ~0x40) | 0x80)
    companion.setup_logging(args.verbose)
    saved = companion.read_config()
    mode = args.mode or (choose_mode(saved) if interactive() else saved.get("mode", "play"))
    if mode == "host-only":
        cfg = saved                                       # a server needs no player settings
    else:
        joining = args if mode == "play" else argparse.Namespace(server=None, port=None, password=None,
                                                                 name=args.name)
        cfg = companion.load_config(joining, ask_server=mode == "play")
    if mode != "play":
        host_settings(cfg, args)
    cfg["mode"] = mode
    companion.save_config(cfg)

    comp = None
    if mode != "host-only":
        comp = companion.Companion(cfg)
        if mode == "host":
            comp.hosting = (int(cfg["host_port"]), cfg["host_password"])
        companion.on_console_close(comp.despawn_all)
        where = "your own server (this PC)" if mode == "host" else f"server {cfg['server']}:{cfg['port']}"
        log.info("inZOI Multiplayer %s - %s, your name %s", companion.VERSION, where, cfg["name"])
    try:
        asyncio.run(run(mode, cfg, comp))
    except KeyboardInterrupt:
        if comp:
            comp.despawn_all()
            time.sleep(0.5)
        log.info("stopped")


def pause():
    """A double-clicked exe's window closes the moment it exits: keep it open so the message can be read."""
    if getattr(sys, "frozen", False) and interactive():
        try:
            input("  Press Enter to close this window.")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except SystemExit as e:
        if e.code not in (None, 0):
            if isinstance(e.code, str):
                print(f"\n  {e.code}\n")
            pause()
            sys.exit(e.code if isinstance(e.code, int) else 1)
    except Exception:                                     # noqa: BLE001 - show it, don't just vanish
        traceback.print_exc()
        logging.getLogger().exception("crashed")
        print(f"\n  Something went wrong (details in {companion.CONFIG_DIR / 'companion.log'}).\n")
        pause()
        sys.exit(1)
