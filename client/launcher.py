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
import logging
import os
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "server")]
import companion  # noqa: E402
import inzoi_mp_server as mpserver  # noqa: E402
import menu  # noqa: E402
import netinfo  # noqa: E402
import updater  # noqa: E402

log = logging.getLogger("launcher")
MENU = [("play", "Join a friend", "connect to the server your friend hosts"),
        ("host", "Host and play", "your friends connect to you, and you play too"),
        ("host-only", "Host only", "just run the server for your friends (no game needed)")]
SERVER_DATA = companion.SERVER_DATA
GAME_URL = "steam://rungameid/2456740"


def interactive() -> bool:
    return companion.interactive()


def server_text(cfg: dict) -> str:
    port = int(cfg.get("port") or 24242)
    return (cfg.get("server") or "") + ("" if port == 24242 or not cfg.get("server") else f":{port}")


def choose_mode(cfg: dict) -> str:
    """The start menu: one of MENU's modes, or "settings"."""
    modes = [m for m, _, _ in MENU] + ["settings"]
    default = modes.index(cfg["mode"]) + 1 if cfg.get("mode") in modes else 1
    print(f"\n  inZOI Multiplayer {companion.VERSION}\n")
    for i, (mode, title, what) in enumerate(MENU, 1):
        if mode == "play" and cfg.get("server"):
            what += f" ({server_text(cfg)})"
        print(f"    {i}  {title:<16}{what}")
    print(f"    4  {'Settings':<16}change your name, the server address or the passwords")
    while True:
        pick = companion.ask(f"\n  Type 1, 2, 3 or 4 and press Enter [{default}]: ").strip() or str(default)
        if pick in ("1", "2", "3", "4"):
            print()
            return modes[int(pick) - 1]


def edit_settings(cfg: dict):
    """Menu 4: change what was typed in before. Enter keeps the value shown in [brackets]."""
    print("  Settings. Press Enter to keep what's in [brackets]. Type none to remove a password.\n")
    name = companion.ask(f"  Your name [{cfg.get('name') or ''}]: ").strip()
    if name:
        cfg["name"] = name
    print("\n  When you join a friend:")
    addr = companion.ask(f"  Server address [{server_text(cfg) or 'none'}]: ").strip()
    if addr:
        host, _, port = addr.partition(":")
        cfg["server"], cfg["port"] = host.strip(), int(port) if port.strip().isdigit() else 24242
    pw = companion.ask(f"  Password of that server [{cfg.get('password') or 'none'}]: ").strip()
    if pw:
        cfg["password"] = "" if pw.lower() == "none" else pw
    print("\n  When you host:")
    pw = companion.ask(f"  Password for your server [{cfg.get('host_password') or 'none'}]: ").strip()
    if pw:
        cfg["host_password"] = "" if pw.lower() == "none" else pw
    port = companion.ask(f"  Port for your server [{cfg.get('host_port') or 24242}]: ").strip()
    if port.isdigit():
        cfg["host_port"] = int(port)
    companion.save_config(cfg)
    print("\n  Saved.")


def host_settings(cfg: dict, args) -> tuple[int, str, str]:
    """Your own server's port/password/motd: from the command line, else remembered, else asked once."""
    if args.port:
        cfg["host_port"] = args.port
    if args.password is not None:
        cfg["host_password"] = args.password
    if args.motd is not None:
        cfg["host_motd"] = args.motd
    if "host_password" not in cfg and interactive():
        cfg["host_password"] = companion.ask("  Pick a password so only your friends can join (or just press Enter for none): ").strip()
        if cfg["host_password"]:
            print("  Friends type it in the in-game panel: Settings, Password, then Save.")
        print()
    cfg.setdefault("host_port", 24242)
    cfg.setdefault("host_password", "")
    cfg.setdefault("host_motd", "")
    return int(cfg["host_port"]), cfg["host_password"], cfg["host_motd"]


def show_addresses(port: int, password: str):
    at = "" if port == 24242 else f":{port}"
    _, ts_ip = netinfo.tailscale_self()                  # the IP, not the name: a renamed PC gets a new name
    lan = netinfo.lan_address()
    print("\n  Your server is running. Tell your friends to type this as the server address:\n")
    if ts_ip:
        print(f"    {ts_ip + at:<22} friends anywhere (over Tailscale: share this PC with them in Tailscale first)")
    if lan:
        print(f"    {lan + at:<22} friends in your home (on the same Wi-Fi or network)")
    if not ts_ip:
        print("\n  Friends outside your home can't reach this PC yet: install Tailscale here and share this PC with")
        print(f"  them (see the README), or forward port {port} (TCP) to this PC in your router.")
    print(f"\n  Password: {password}" if password else "\n  No password: anyone who can reach this PC can join.")
    print("  If Windows asks whether inZOI Multiplayer may use the network, click Allow.")
    print("  Keep this window open while friends play.\n")


async def fetch_update():
    """Host only (no game): download a newer version now and then; it's applied when the program next starts."""
    while updater.frozen():
        try:
            info = await asyncio.to_thread(updater.latest, companion.VERSION)
            if info and not updater.pending(companion.VERSION):
                await asyncio.to_thread(updater.download, info)
                log.info("inZOI Multiplayer %s is downloaded: it's applied the next time you start the program",
                         info["version"])
        except (OSError, ValueError) as e:
            log.debug("update check: %s", e)
        await asyncio.sleep(2 * 3600)


async def run(mode: str, cfg: dict, comp):
    if mode == "host-only":
        args = argparse.Namespace(host="0.0.0.0", port=cfg["host_port"], password=cfg["host_password"],
                                  motd=cfg["host_motd"], max_players=None, data=str(SERVER_DATA), hosted=False,
                                  name=cfg.get("host_name") or None, directory=bool(cfg.get("host_directory")))
        try:
            hosted = await mpserver.start(args)
        except OSError as e:
            raise SystemExit(f"Can't host on port {args.port}: {e.strerror or e}. Is a server already running on "
                             "this PC?") from None
        show_addresses(args.port, hosted[0].mp_server.password)
    elif mode == "host":
        try:
            await comp.start_hosting(play=True)          # host and play: the host's mods are everyone's
        except ValueError as e:
            raise SystemExit(str(e)) from None
        show_addresses(*comp.hosting)
    if comp:
        if mode == "play":
            print(f"\n  Connecting to {server_text(cfg)} as {cfg['name']}.")
            print("  (Wrong address or name? Change it in the in-game panel's Settings, or close this window, open")
            print("  the program again and type 4.)")
        print("  On inZOI's main menu, click Multiplayer to see servers, join one, or host your own.")
        if cfg.get("mp_save"):
            print("  Wait at the main menu and your multiplayer save loads by itself.")
        else:
            print("  Load the save you want to play with friends (you'll be asked about it).")
        print("  Keep this window open while you play, and close it when you're done.\n")
        await comp.run()
    else:
        asyncio.create_task(fetch_update())
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
    updater.clean_old()
    waiting = updater.pending(companion.VERSION) if updater.frozen() else None
    if waiting and interactive():
        version = waiting.stem.split("inZOI-Multiplayer-", 1)[1]
        answer = companion.ask(f"\n  inZOI Multiplayer {version} was downloaded last time. Update now? Type y or n [y]: ")
        if not answer.strip().lower().startswith("n"):
            updater.apply(waiting, sys.argv[1:])
            return
    saved = companion.read_config()
    mode = args.mode or (None if interactive() else saved.get("mode", "play"))
    while not mode:
        mode = choose_mode(saved)
        if mode == "settings":
            edit_settings(saved)
            mode = None
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
        comp.restart_args = [f"--{mode}"]
        companion.on_console_close(comp.shutdown)
        where = "your own server (this PC)" if mode == "host" else f"server {cfg['server']}:{cfg['port']}"
        log.info("inZOI Multiplayer %s - %s, your name %s", companion.VERSION, where, cfg["name"])
        offer_game()
    try:
        asyncio.run(run(mode, cfg, comp))
    except KeyboardInterrupt:
        if comp:
            comp.shutdown()
            time.sleep(0.5)
        log.info("stopped")


def offer_game():
    """The "Multiplayer" item on the game's main menu needs this program running: offer to start inZOI with it."""
    if os.name != "nt" or not interactive() or menu.game_window():
        return
    if not companion.ask("  inZOI isn't running. Start it now? Type y or n [y]: ").strip().lower().startswith("n"):
        os.startfile(GAME_URL)                                           # noqa: S606 - Steam starts the game
        print("  Starting inZOI...")


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
