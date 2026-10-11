# inZOI Multiplayer

Play inZOI together. Your friends' Zois show up in your world, looking exactly like theirs, and walk, sit, work out,
dance and chat where they really are. Your Zoi shows up in their worlds the same way. Greet a friend's Zoi and it
plays out on both screens.

Everyone keeps playing their own save. Friends appear in it as visitors in their own household: they don't join your
family, age, get hungry or wander off. They only do what the real player does.

> Fan-made beta. Not affiliated with or endorsed by KRAFTON.

## Download

**[Download inZOI-Multiplayer.exe](https://github.com/Darker117/inzoi-multiplayer/releases/latest/download/inZOI-Multiplayer.exe)**
(or see the [latest release](https://github.com/Darker117/inzoi-multiplayer/releases/latest)). That one file is all
you need: the game mod is inside it.

The first time you open it, Windows may say "Windows protected your PC", because the program is new and not
code-signed. Click **More info**, then **Run anyway**.

## Play

1. Double-click `inZOI-Multiplayer.exe` and pick **1 Play**. The first time, it asks for your name and the server
   address your host gave you. Keep the window open while you play.
2. Start inZOI and load your save. The program installs the mod into the game and loads it by itself.
3. The inZOI Multiplayer panel appears on the left of the screen:
   - **People**: who's online, where they are and what they're doing, **Join** (jump next to a friend), and chat
     (messages also pop up as speech bubbles)
   - **Houses**: share a house from your library, or add a friend's house to yours
   - **Settings**: your name, the server, its password, and matching the host's time of day

Friends' Zois appear when you're in the same city. Meet up by traveling there or pressing Join.

## Host

The server is tiny and needs no game. Anyone in the group can host with the same program:

- **2 Host and play**: run the server on your PC and play on it.
- **3 Host only**: just run the server, for example on a PC that stays on.

The window shows the address friends should enter, both for your home network and for Tailscale. For friends
on other networks, [Tailscale](https://tailscale.com/download) (free) is the easiest way in: share the host PC
with each friend from the Tailscale admin console (Machines, then Share). Forwarding TCP port 24242 in the router
works too.

**Raspberry Pi or Linux:** run `python3 server/inzoi_mp_server.py --password secret` (Python 3.9+, no packages
needed). [`server/inzoi-mp.service`](server/inzoi-mp.service) keeps it running at boot.

Command-line shortcuts: `--play`, `--host` or `--host-only` skip the menu. When hosting, `--port`, `--password`
and `--motd "Welcome!"` set up your server.

## What's shared

| | |
|---|---|
| Looks | Face, body, outfit, name, personality and voice; outfit changes as they happen |
| Moving | Position, facing, walking, running; a far jump teleports |
| Doing | Actions on objects (the same object in public places; homes can differ, so some actions only show as the motion), solo actions, socials toward your Zoi |
| Talking | Chat in the panel, with speech bubbles over their Zoi |
| Visiting | Houses shared through your library; friends' Zois are let in through your front door |
| Time | Optionally match the host's time of day and season |

## How it works

- **The program** (`client/`) runs next to the game on each player's PC. It talks to inZOI through the game's
  built-in local control API (`127.0.0.1:11212`), which is on by default, and to the server over TCP (one JSON
  object per line).
- **The game mod** (`mod/InZOIMultiplayer/`) installs itself into `Documents\inZOI\Mods\InGame`. Its Lua
  controller brings friends' Zois into your world as puppets and drives them. Its panel is a UI mod that talks to
  the program on `127.0.0.1:24243`. No game files are changed.
- **The server** (`server/`) relays live state, chat and houses between players and remembers profiles. It never
  needs updating for new features. See [`server/PROTOCOL.md`](server/PROTOCOL.md).

## Build from source

Python 3.10+ on Windows.

- Run it: `python client/launcher.py`
- Build the exe and the release zip: `python tools/build_release.py` (the first run sets up `build/venv` with
  PyInstaller)
- Server tests: `python server/test_server.py`
- Rehearse with a fake second player in your own game: `python tools/fake_player.py --help`

## Status

Beta. Tested in a single game with a simulated second player. Live two-PC sessions are next. Please report
problems in [Issues](https://github.com/Darker117/inzoi-multiplayer/issues) and include
`%APPDATA%\inzoi-mp\companion.log`.
