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

## How it works

Double-click **inZOI-Multiplayer.exe**. inZOI starts, and its main menu has a **Multiplayer** button: joining a
server, hosting your own, your name and updates are all there. The program has no window of its own; it runs while
inZOI runs and closes by itself after inZOI closes.

The first time, it adds the Multiplayer button to inZOI and tells you where ([see below](#the-multiplayer-menu)).
If inZOI is already sitting on its main menu, it restarts inZOI once so the button shows up.

| | |
|---|---|
| **[Join a friend](#join-a-friend)** | A friend runs the server, you just play. *Most people.* |
| **[Host and play](#host-and-play)** | You run the server on your PC, and you play too. |
| **[Host only](#host-only)** | You run the server for your friends (on a PC or a Raspberry Pi), without playing on it. |

### Join a friend

Your host gives you **the server address** (it looks like `100.101.102.103`) and, if you don't live together,
**a Tailscale invite link**.

1. **Only if you got a Tailscale invite link** (once):
   install [Tailscale](https://tailscale.com/download), sign in (a Google, Microsoft, Apple or GitHub account is
   fine), open the invite link and click **Accept**. Tailscale has to be on (Connected) whenever you play.
2. Double-click **inZOI-Multiplayer.exe**. inZOI starts.
3. On the main menu, click **Multiplayer**, then **Private Servers**, **Add Server**. Type the address your host
   gave you (and the password, if the server has one) and click **Save and Join**. Servers anyone can join are
   under **Public Servers**: select one and click **Join**.
4. **The first time**, load the save you want to play with friends: the program offers to make a multiplayer copy
   of it ([see below](#your-multiplayer-save)). **After that**, just wait at the main menu: the program joins your
   server again and loads your multiplayer save for you. The **inZOI Multiplayer** panel appears on the left of
   the screen.

Friends see your Steam name. To change it, click **Your Name** on the Multiplayer page.

### Host and play

1. Double-click **inZOI-Multiplayer.exe**. inZOI starts.
2. On the main menu, click **Multiplayer**, then **Private Servers**, **Host a Server**. Give it a name and, if you
   like, a password, then click **Start Hosting**. If Windows asks whether inZOI Multiplayer may use the network,
   click **Allow**.
3. Select your server in the list: it shows the addresses to give your friends:
   - `100.x.x.x` for friends anywhere, through Tailscale ([see below](#playing-over-the-internet-tailscale))
   - `192.168.x.x` for friends in your home
4. Play as in [Join a friend](#join-a-friend), step 4. Your server runs while you play and comes back each time
   you start the program; **Stop Hosting** ends it.

### Host only

**On a Windows PC:** make a shortcut to **inZOI-Multiplayer.exe**, add ` --host-only` at the end of its *Target*,
and start the program with that shortcut. It opens a window with the address and password for your friends (it
asks for a password the first time); keep it open while they play. Typing `play` in that window turns the PC back
into a normal player.

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

## The Multiplayer menu

inZOI's main menu gets a real **Multiplayer** item under New Game: the game's own menu button, with its hover
butterfly and sounds. It opens the servers page **inside the game**: the game's own Mods page, turned into the
servers page, so the tabs, filters, server rows, details, buttons and dialogs are the game's own. **Back** or **Esc**
returns to the main menu.

The item and the page come from a small script run by [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) (an open-source
script loader for Unreal Engine games, MIT license). The program puts UE4SS and the script next to the game by
itself (`dwmapi.dll` and a `ue4ss` folder in inZOI's `BlueClient/Binaries/Win64`; a message says where) and
restarts inZOI if it's sitting on its main menu, so the button shows up right away. Nothing of the game's own
changes. To take it out, close inZOI and delete those two: they stay out (to put them back, start the program once
with `--menu-button`). Without them, the program draws a stand-in item over the menu and opens the servers page in a
full-screen browser window. In the game (a save loaded), the panel's
**Servers** button opens that browser page too.

- **Public Servers**: servers anyone can join, with players, ping and mods. Select one to see whether you can
  join: its version, room, password, and which of its mods you have or would download. **Join** gets you in, and
  the program offers the mods you're missing.
- **Private Servers**: servers you added by address (**Add Server**), and the one you host.
- **Host a Server**: run a server in the program and play on it. **Public** lists it for everyone; private means
  only people with the address can join.
- **Admin Console**: players online (kick, ban, make admin), settings (name, description, welcome message,
  password, max players, public or private), a message to everyone, restarting the server (everyone's game is
  saved first), earlier versions of the shared world, and the log. On your own server it's **Server Settings**;
  on another server you become an admin with the code its owner gives you (`inzoi_mp_server.py --admin-code`).
- Each server keeps its own multiplayer save: switching servers switches saves.
- **Your Name**: what friends see over your Zoi and in the chat (your Steam name to begin with).
- **Updates**: the program checks for a new version by itself. When one is out, inZOI shows a notice and the
  Multiplayer page offers it (**Update to …** at the top). **Update Now** downloads it and restarts the program in
  a few seconds; inZOI keeps running.

Public servers are listed by a server started with `--directory` (for example a Raspberry Pi everyone uses), which
checks each listed server can be reached.

## In the game

The **inZOI Multiplayer** panel (left of the screen; drag it by its title, `_` folds it away):

- **People**: who's online and what they're doing, **Join** (jump next to a friend's Zoi), and chat (messages also
  pop up as speech bubbles)
- **Houses**: share your house, or add a friend's house to your library
- **Mods**: the mods everyone uses, and downloading the ones you're missing
- **Settings**: your name, the server address, the password, and following the host's time of day
- **Servers** (title bar): opens the Multiplayer menu

Friends' Zois appear in your world when you're in the same city. To hang out, travel to the same place or press
**Join**.

**Visiting each other at home:** everyone plays their own save, so a friend's house isn't in your world until you
put it there. The owner saves their home to My Library (Build mode) and shares it in the **Houses** tab. Friends
click **Add to library** and place it, in Build mode, on the lot the panel names. Then the owner's Zoi walks
through the same rooms on everyone's screen.

## Your multiplayer save

Multiplayer plays in a save of its own, so your normal saves stay untouched by it (friends' Zois coming and
going, the shared clock, friends' houses).

- **The first time** you play multiplayer, the panel asks:
  **make a multiplayer copy** of the save you're in (recommended: the game saves, goes to the main menu for a
  moment and loads the copy; your original stays as it was), **use this save** as it is, or **not now**.
- **Coming back:** double-click the program and wait at inZOI's main menu. It loads your multiplayer save.
- **In any other save, multiplayer pauses:** friends' Zois leave it and the shared clock leaves it alone. If you
  load a save yourself, the program asks whether it's your multiplayer save. The panel's *Switch to my
  multiplayer save* saves that game and takes you back.
- The panel's **Settings** tab shows which save is your multiplayer save, and the version.

## Mods

Everyone needs the same mods to see each other's clothes, hair and things, and the program takes care of it:

- **Host and play:** the host's mods count. Anyone missing some is asked *"Download them now?"* in the game (on the
  Multiplayer page, or in the panel's **Mods** tab).
- **Stand-alone server (Host only, or a Raspberry Pi):** everyone's mods are shared, and each player is offered the
  ones the others have. If two players have different versions of a mod, the newer one wins.
- A progress bar shows the download (and the upload, for whoever shares) in the panel's **Mods** tab. Downloaded mods load the next time you start inZOI. Only enabled mods are shared, and a mod replaced by a newer
  version is moved to `%APPDATA%\inzoi-mp\replaced-mods`, never deleted.

## Time

- The **time of day is shared**. Pausing only pauses your own game, and when you carry on, your clock catches up
  with your friends'. Build mode and menus pause only you, too.
- The game runs at **normal speed while anyone's Zoi is awake**. When **everyone's Zoi is asleep**, time speeds up
  for everyone until somebody wakes up.
- Season and weather follow the host. (To keep your own time, turn off *Follow the host's time* in Settings.)

## If something's wrong

- **The Multiplayer button is dimmed, or the panel says the program isn't running:** inZOI was started without
  the program. Double-click inZOI-Multiplayer.exe (it's fine while inZOI runs).
- **Wrong server address or password:** on the Multiplayer page, select the server and click **Edit**.
- **"Can't reach the server":** check the address (**Edit**). If you play over the internet, check that Tailscale
  is on (Connected). Ask the host whether their server is running.
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
| Time | Shared time of day (pausing is your own), fast-forward while everyone sleeps, the host's season and weather |
| Mods | The host's mods (or everyone's, on a stand-alone server), downloaded after asking |

## How it works

- **The program** (`client/`) runs next to the game on each player's PC. It talks to inZOI through the game's
  built-in local control API (`127.0.0.1:11212`), which is on by default, and to the server over TCP (one JSON
  object per line).
- **The game mod** (`mod/InZOIMultiplayer/`) installs itself into `Documents\inZOI\Mods\InGame`. Its Lua
  controller brings friends' Zois into your world as puppets and drives them. Its panel is a UI mod that talks to
  the program on `127.0.0.1:24243`. No game files are changed.
- **The server** (`server/`) relays live state, chat and houses between players and remembers profiles. It also
  answers the servers page (info before joining, the admin console) and, with `--directory`, keeps the list of
  public servers. See [`server/PROTOCOL.md`](server/PROTOCOL.md).
- **The in-game Multiplayer page** (`mod/ue4ss/InZOIMultiplayer`, a UE4SS Lua script, installed by
  `client/ue4ss.py`) adds the main menu's Multiplayer item and turns the game's Mods page into the servers page out
  of the game's own widgets. The program decides what it shows and does what its buttons ask
  (`client/ingame.py`), through files in `%APPDATA%/inzoi-mp/ingame`.
- **The browser servers page** (`client/page/`) is served by the program and opened in a full-screen Edge window;
  without UE4SS, the **Multiplayer** item is a see-through window the program draws (`client/menu.py`). The page
  uses the Inter font (SIL Open Font License, `client/page/fonts/OFL.txt`).

## Build from source

Python 3.10+ on Windows.

- Run it: `python client/launcher.py`
- Build the exe and the release zip: `python tools/build_release.py` (the first run sets up `build/venv` with
  PyInstaller)
- Tests: `python server/test_server.py`, `python tools/test_servers_page.py` (servers page, two servers and a
  program), and the other `tools/test_*.py`
- Rehearse with a fake second player in your own game: `python tools/fake_player.py --help`

## Status

Beta. Tested in a single game with a simulated second player. Live two-PC sessions are next.
