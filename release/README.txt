inZOI Multiplayer  (beta)
=========================

Play inZOI together. Your friends' Zois show up in your world, looking exactly like theirs, and walk, sit, work
out, dance and chat where they really are. Your Zoi shows up in their worlds the same way. Greet a friend's Zoi
and it plays out on both screens.

Each player keeps playing their own save. Friends appear as visitors in it, in their own household (they don't
join your family, they don't age, get hungry or wander off: they only do what the real player does).


WHAT YOU NEED
-------------
- inZOI on Windows (everyone on the same game version).
- This program, "inZOI Multiplayer.exe". Nothing else to install: the game mod is inside it.
- One person hosts the server (see HOSTING below); everyone else connects to it.

The first time you open it, Windows may say "Windows protected your PC". That's because the program is new and
not code-signed. Click "More info", then "Run anyway".


PLAYING
-------
1. Put "inZOI Multiplayer.exe" anywhere (your Desktop is fine) and double-click it.
2. Pick 1 (Play). The first time it asks for your name and the server address the host gave you.
   Leave the window open while you play. Next time just press Enter: it remembers your choice.
3. Start inZOI and load your save. The program installs the mod into the game and loads it by itself.
4. The inZOI Multiplayer panel appears on the left of the screen in the game:
   - People: who's online and where they are ("Here with you" / "In another city"), what they're doing,
     Join (jump your Zoi right next to a friend's Zoi) and chat (messages also pop up as speech bubbles)
   - Houses: share a house from your library, or add a friend's shared house to yours (see VISITING)
   - Settings: your name, the server, its password, and "Match the host's time of day"
   Drag it by the title bar, "_" folds it away.

Friends' Zois appear in your world when you're in the same city. To hang out, meet in the same place: travel
there in the game, or press Join.


VISITING EACH OTHER AT HOME
---------------------------
Everyone plays their own save, so your friend's house isn't in your world until you put it there:
1. The host saves their home to their library (Build mode, save the lot to My Library), then shares it in the
   panel's Houses tab.
2. Visitors click "Add to library", then in Build mode place that house on the lot the panel names.
3. Now when the host walks around their home, their Zoi walks through the same rooms on your screen.
Friends' Zois are let in through your front door like invited guests.


HOSTING
-------
The server is tiny and needs no game. Anyone in the group can host it, with the same program:
- Pick 2 (Host and play) to run the server on your PC and play on it, or 3 (Host only) to just run the server,
  e.g. on a PC that stays on. The window then shows the address friends should enter. Keep it open while
  friends play.
- The first time, it asks for a password (optional). Friends type it in the panel's Settings.
- If Windows asks whether inZOI Multiplayer may use the network, allow it.
- Friends on other networks (over the internet) need a way in. Easiest is Tailscale (free):
    1. The host installs Tailscale (https://tailscale.com/download) on the server PC and, in the Tailscale admin
       console (Machines), uses "Share..." on that PC to get an invite link for each friend.
    2. Friends install Tailscale, sign in, and open the invite link.
    3. Friends enter the server's Tailscale name (the window shows it, e.g. my-pc.tailxxxxx.ts.net).
  The other way is forwarding port 24242 (TCP) to the host in the router.
- On a Raspberry Pi or Linux box: copy the "server for Raspberry Pi or Linux" folder over and run
      python3 inzoi_mp_server.py --password secret
  To keep it running all the time, see the notes at the top of inzoi-mp.service.
- Shortcuts: "inZOI Multiplayer.exe" --play, --host or --host-only skips the menu; with --host/--host-only,
  --port 24242, --password secret and --motd "Welcome!" set up your server.


GOOD TO KNOW
------------
- Close the window (or press Ctrl+C in it) when you're done, so friends' Zois leave your world cleanly. If the
  game ever saved while friends were visiting, the program tidies up next time.
- Building, menus and the map pause the game; friends' Zois wait until you're back.
- Objects in public places are the same in everyone's game, so a friend working out at the gym does it on the
  same machine in your world. Inside homes things can differ, so some actions only show as the motion.
- Settings and logs: %APPDATA%\inzoi-mp (companion.log; a hosted server keeps its data in the "server" folder).
- Some antivirus programs distrust any new unsigned program. If yours quarantines it, restore it and allow it.


UNINSTALL
---------
Delete  Documents\inZOI\Mods\InGame\InZOIMultiplayer  and  %APPDATA%\inzoi-mp, then the program.
