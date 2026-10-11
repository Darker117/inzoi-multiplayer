# inZOI Multiplayer

Play inZOI together. Your friends' Zois show up in your world, looking exactly like theirs, and walk, sit, work out,
dance and chat where they really are. Your Zoi shows up in their worlds the same way.

Everyone keeps playing their own save. Friends appear in it as visitors: they only do what the real player does.

> Fan-made beta. Not affiliated with or endorsed by KRAFTON.

## Download

### **[⬇ Download inZOI-Multiplayer.exe](https://github.com/Darker117/inzoi-multiplayer/releases/latest/download/inZOI-Multiplayer.exe)**

That one file is all you need: the game mod is inside it. Everyone needs inZOI on Windows, all on the same game
version.

The first time you open it, Windows may say **"Windows protected your PC"**. That's only because the program is
new and not code-signed. Click **More info**, then **Run anyway**.

## What do you want to do?

| | |
|---|---|
| **[Join a friend](#join-a-friend)** | A friend runs the server, you just play. *Most people.* |
| **[Host and play](#host-and-play)** | You run the server on your PC, and you play too. |
| **[Host only](#host-only)** | You run the server for your friends (on a PC or a Raspberry Pi), without playing on it. |
| **Settings** | Change your name, the server address or a password: open the program and type **4**. |

### Join a friend

Your host gives you **the server address** (it looks like `100.101.102.103`) and, if you don't live together,
**a Tailscale invite link**.

1. **Only if you got a Tailscale invite link** (once):
   install [Tailscale](https://tailscale.com/download), sign in (a Google, Microsoft, Apple or GitHub account is
   fine), open the invite link and click **Accept**. Tailscale has to be on (Connected) whenever you play.
2. Double-click **inZOI-Multiplayer.exe**. Type **1** and press Enter.
3. The first time, it asks for **your name** (what friends see) and the **server address** your host gave you.
   It remembers both: next time, just press Enter. To change them, type **4** (Settings) instead.
4. Start inZOI and load your save. The **inZOI Multiplayer** panel appears on the left of the screen.
   Keep the program's window open while you play.

If your host uses a password: open the program, type **4** (Settings) and enter it at *Password of that server*
(or in the game: the panel's **Settings**, **Password**, **Save**).

### Host and play

1. Double-click **inZOI-Multiplayer.exe**. Type **2** and press Enter.
2. The first time, it asks for your name and a password (optional: press Enter for none). To change them later,
   type **4** (Settings) instead.
   If Windows asks whether inZOI Multiplayer may use the network, click **Allow**.
3. The window shows the address and password to give your friends:
   - `100.x.x.x` for friends anywhere, through Tailscale ([see below](#playing-over-the-internet-tailscale))
   - `192.168.x.x` for friends in your home
4. Start inZOI and load your save. Keep the window open while you and your friends play.

### Host only

**On a Windows PC:** double-click **inZOI-Multiplayer.exe**, type **3** and press Enter. It works like
*Host and play*, without the game. The window shows the address for your friends; keep it open while they play.

**On a Raspberry Pi or another Linux computer:** copy the [`server`](server/) folder to it and run
`python3 inzoi_mp_server.py` (add `--password yourpassword` to use a password; Python 3.9+, nothing to install).
To keep it running all the time, even after a restart, follow the steps at the top of
[`server/inzoi-mp.service`](server/inzoi-mp.service). The address for your friends is the Pi's Tailscale address
(see below), or for friends in your home, its address on your network.

## Playing over the internet (Tailscale)

Friends who don't live with the host connect through [Tailscale](https://tailscale.com/download). It's a free app
that links their PCs to the server as if everyone were on the same home network. No router setup needed.

**The host, once:**
1. Install Tailscale on the computer that runs the server and sign in.
2. Open [login.tailscale.com/admin/machines](https://login.tailscale.com/admin/machines).
3. Find that computer in the list. The **100.x.x.x** number on its row is the server address for your friends.
4. Click the **⋯** at the end of its row, then **Share…**, and copy the invite link. Make a new link for each
   friend and send it with the 100.x.x.x address.

**Each friend, once:** install Tailscale, sign in, open the host's invite link and click **Accept**. Then follow
[Join a friend](#join-a-friend) with the 100.x.x.x address.

Without Tailscale, the host can forward TCP port 24242 to the server in their router; friends then use the host's
public IP address.

## In the game

The **inZOI Multiplayer** panel (left of the screen; drag it by its title, `_` folds it away):

- **People**: who's online and what they're doing, **Join** (jump next to a friend's Zoi), and chat (messages also
  pop up as speech bubbles)
- **Houses**: share your house, or add a friend's house to your library
- **Settings**: your name, the server address, the password, and matching the host's time of day

Friends' Zois appear in your world when you're in the same city. To hang out, travel to the same place or press
**Join**.

**Visiting each other at home:** everyone plays their own save, so a friend's house isn't in your world until you
put it there. The owner saves their home to My Library (Build mode) and shares it in the **Houses** tab. Friends
click **Add to library** and place it, in Build mode, on the lot the panel names. Then the owner's Zoi walks
through the same rooms on everyone's screen.

## If something's wrong

- **The panel says the program isn't running:** open inZOI-Multiplayer.exe and keep its window open.
- **Wrong server address, name or password:** close the program, open it again and type **4** (Settings), then
  **1** (or **2**) to start again.
- **"Can't reach the server":** check the address (type **4**, Settings). If you play over the internet, check
  that Tailscale is on (Connected). Ask the host whether their server window is open.
- **Switch between joining and hosting:** close the program and open it again. It shows the menu every time, and
  Enter picks what you chose last time.
- **Your antivirus removed the program:** restore it and allow it. It's flagged only because it's new and
  unsigned.
- **Reporting a problem:** open an [issue](https://github.com/Darker117/inzoi-multiplayer/issues) and attach
  `%APPDATA%\inzoi-mp\companion.log`.

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
- **The server** (`server/`) relays live state, chat and houses between players and remembers profiles. See
  [`server/PROTOCOL.md`](server/PROTOCOL.md).

## Build from source

Python 3.10+ on Windows.

- Run it: `python client/launcher.py`
- Build the exe and the release zip: `python tools/build_release.py` (the first run sets up `build/venv` with
  PyInstaller)
- Server tests: `python server/test_server.py`
- Rehearse with a fake second player in your own game: `python tools/fake_player.py --help`

## Status

Beta. Tested in a single game with a simulated second player. Live two-PC sessions are next.
