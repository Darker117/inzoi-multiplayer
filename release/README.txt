inZOI Multiplayer  (beta)
=========================

Play inZOI together. Your friends' Zois show up in your world, looking exactly like theirs, and walk, sit, work
out, dance and chat where they really are. Your Zoi shows up in their worlds the same way.

Everyone keeps playing their own save. Friends appear in it as visitors: they only do what the real player does.


WHAT DO YOU WANT TO DO?
-----------------------
  A. JOIN A FRIEND     a friend runs the server, you just play                    (most people)
  B. HOST AND PLAY     you run the server on your PC, and you play too
  C. HOST ONLY         you run the server for your friends (a PC or a Raspberry Pi), without playing on it

To change your name, the server address or a password later: open the program and type 4 (Settings).

Everyone needs inZOI on Windows (all on the same game version) and the file "inZOI Multiplayer.exe".

The first time you open "inZOI Multiplayer.exe", Windows may say "Windows protected your PC". That's only because
the program is new and not code-signed. Click "More info", then "Run anyway".


A. JOIN A FRIEND
----------------
Your host gives you:  the server address (it looks like 100.101.102.103)
                      and, if you don't live together, a Tailscale invite link.

1. Only if you got a Tailscale invite link (do this once):
     - Install Tailscale from https://tailscale.com/download and sign in (a Google, Microsoft, Apple or
       GitHub account is fine).
     - Open the invite link and click Accept.
   Tailscale has to be on (Connected) whenever you play.
2. Double-click "inZOI Multiplayer.exe". Type 1 and press Enter.
3. The first time, it asks two things:
     Your name ........... what your friends will see
     Server address ...... the address your host gave you
   It remembers them: next time, just press Enter. To change them, type 4 (Settings) instead of 1.
4. Start inZOI and load your save. The inZOI Multiplayer panel appears on the left of the screen.
   Keep the program's window open while you play. Close it when you're done.

If your host uses a password: open the program, type 4 (Settings) and enter it at "Password of that server".
(Or in the game: the panel's Settings, Password, Save.)


B. HOST AND PLAY
----------------
1. Double-click "inZOI Multiplayer.exe". Type 2 and press Enter.
2. The first time, it asks for your name and a password (optional: press Enter for none). To change them
   later, type 4 (Settings) instead of 2.
   If Windows asks whether inZOI Multiplayer may use the network, click Allow.
3. The window shows the address and password to give your friends:
     100.x.x.x ......... for friends anywhere, through Tailscale (see PLAYING OVER THE INTERNET below)
     192.168.x.x ....... for friends in your home
4. Start inZOI and load your save. Keep the window open while you and your friends play.


C. HOST ONLY
------------
On a Windows PC:
  Double-click "inZOI Multiplayer.exe", type 3 and press Enter. It works like B, without the game. The window
  shows the address and password to give your friends. Keep it open while they play. (Password or port: type 4.)

On a Raspberry Pi or another Linux computer:
  1. Copy the "server for Raspberry Pi or Linux" folder to it and run:   python3 inzoi_mp_server.py
     (add  --password yourpassword  to use a password)
  2. To keep it running all the time, even after a restart, follow the steps at the top of inzoi-mp.service.
  3. The address for your friends is the Pi's Tailscale address (100.x.x.x: see below), or for friends in your
     home, its address on your network (192.168.x.x).


PLAYING OVER THE INTERNET (TAILSCALE)
-------------------------------------
Friends who don't live with the host connect through Tailscale. It's a free app that links their PCs to the
server as if everyone were on the same home network. No router setup needed.

The host does this once:
  1. Install Tailscale on the computer that runs the server (https://tailscale.com/download) and sign in.
  2. Open https://login.tailscale.com/admin/machines in a browser.
  3. Find that computer in the list. Its address is the 100.x.x.x number on its row: that's the server address
     for your friends.
  4. Click the "..." at the end of its row, then "Share...", and copy the invite link.
     Make a new link for each friend and send it to them with the 100.x.x.x address.

Each friend does this once:
  1. Install Tailscale (https://tailscale.com/download) and sign in.
  2. Open the host's invite link and click Accept.
  Then they follow "A. JOIN A FRIEND" with the 100.x.x.x address.

(Without Tailscale: forward TCP port 24242 to the server in the host's router, and friends use the host's
public IP address.)


IN THE GAME
-----------
The inZOI Multiplayer panel (left of the screen; drag it by its title, "_" folds it away):
  - People: who's online and what they're doing, Join (jump your Zoi next to a friend's Zoi), and chat
    (messages also pop up as speech bubbles)
  - Houses: share your house, or add a friend's house to your library (see VISITING)
  - Mods: the mods everyone uses, and downloading the ones you're missing (see MODS)
  - Settings: your name, the server address, the password, and following the host's time of day

Friends' Zois appear in your world when you're in the same city. To hang out, travel to the same place, or press
Join.


MODS
----
Everyone needs the same mods to see each other's clothes, hair and things. The program takes care of it:
  - When someone hosts and plays (2), the host's mods count. Anyone missing some is asked "Download them now?",
    in the program's window and in the panel's Mods tab.
  - On a stand-alone server (3, or a Raspberry Pi), everyone's mods are shared: each player is offered the ones the
    others have. If two players have different versions of a mod, the newer one wins.
  - Downloaded mods load the next time you start inZOI. If you say no, the Mods tab can still get them later.
  - Only enabled mods are shared. A mod that gets replaced by a newer version is moved to
    %APPDATA%\inzoi-mp\replaced-mods, never deleted.


TIME
----
  - The time of day is shared. Pausing only pauses your own game; when you carry on, your clock catches up with
    your friends'. Build mode and menus pause only you, too.
  - The game runs at normal speed while anyone's Zoi is awake. When everyone's Zoi is asleep, time speeds up for
    everyone until somebody wakes up.
  - Season and weather follow the host. (To keep your own time, turn off "Follow the host's time" in Settings.)


VISITING EACH OTHER AT HOME
---------------------------
Everyone plays their own save, so a friend's house isn't in your world until you put it there:
  1. The owner saves their home to their library (Build mode, save the lot to My Library), then shares it in the
     panel's Houses tab.
  2. Friends click "Add to library", then in Build mode place that house on the lot the panel names.
  3. Now when the owner walks around their home, their Zoi walks through the same rooms on your screen.


IF SOMETHING'S WRONG
--------------------
- The panel says the program isn't running: open "inZOI Multiplayer.exe" and keep its window open.
- Wrong server address, name or password: close the program, open it again and type 4 (Settings). Then type 1
  (or 2) to start again.
- "Can't reach the server": check the address (type 4, Settings). If you play over the internet, check that
  Tailscale is on (Connected) on your PC. Ask the host whether their server window is open.
- To switch between joining and hosting: close the program and open it again. It shows the menu every time
  (Enter picks what you chose last time).
- Your antivirus removed the program: restore it and allow it. It's flagged only because it's new and unsigned.
- Logs (send them along when you report a problem): %APPDATA%\inzoi-mp\companion.log


GOOD TO KNOW
------------
- Building, menus and the map pause only your game. Friends' Zois wait in your world until you're back.
- Objects in public places are the same in everyone's game, so a friend working out at the gym uses the same
  machine in your world. Homes can differ, so there some actions only show as the motion.
- Close the program when you're done (the window's X or Ctrl+C), so friends' Zois leave your world cleanly.


UNINSTALL
---------
Delete  Documents\inZOI\Mods\InGame\InZOIMultiplayer  and  %APPDATA%\inzoi-mp, then the program.
