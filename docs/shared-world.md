# The shared world (design, in progress)

Decided 2026-10-11: multiplayer moves from "everyone plays their own save, friends visit as puppets" to **one shared
world kept on the server**, so buildings, NPCs, businesses and everyone's progress are the same for every player.

## How it will work

1. **The world lives on the server.** The server (the Raspberry Pi, or the host's PC) keeps the world save: the
   game's save files for one slot (`SaveGames/<folder>/<file>.usvx` + pictures + `ModSave/.../ModInfo.json`), with a
   version number. It starts as a copy of one player's save (their multiplayer save, chosen once).
2. **Joining:** the program downloads the newest world (only if it changed), installs it as the player's multiplayer
   save (renamed header, see `client/saves.py`), and loads it at the game's main menu. Mods are synced first (0.4).
3. **Each player has their own household in the world.** The first time a player joins, their Zoi (looks,
   personality, voice: the profile the program already shares) is added to the world as a household of its own, and
   they play it (`character.possess` / `household.possess`). After that it's saved in the world like any household.
4. **Playing together:** everyone runs the same world. Other players' Zois are their real characters in it (not
   spawned puppets), driven live from their player's stream (position, actions, outfit, needs, mood...), with their
   autonomy off while their player is online. Doors work like any visit: they're real households.
5. **Leaving:** the world goes back to the server. Proposed rule (to confirm): the world (lots, NPCs, businesses, time)
   comes from the last player to leave; each player's own household (needs, skills, money, relationships, career)
   comes from that player's own copy, applied to the uploaded world, so nobody's progress is overwritten.
6. **Server restarts:** players are warned in chat (0.5.1). Proposed: their games are saved (main menu for a moment),
   uploaded, and reloaded after the restart.

## Stages

| # | What | Status |
|---|---|---|
| 1 | World save on the server: upload, version, download, install, load | to build |
| 2 | Each player's household in the world (create from profile, move in, possess) | needs game experiments |
| 3 | Other players = their real characters, driven live (adopt instead of spawn) | needs game experiments |
| 4 | Leaving: upload the world, carry each player's household values over | to build |
| 5 | Full value sync while playing (needs, mood, skills, money, career, relationships) | API exists (stat, emotion, skill, relationships, currency, career) |
| 6 | NPCs: one player's game leads, the others' NPCs follow near players | later |
| 7 | Businesses, live building, object states | later |

## Game experiments needed (in a copy of the test save, while nobody plays)

- E1: a world copied from another PC loads (header renamed; no account in the header, so it should).
- E2: create a household + character from a profile in a loaded world, and possess it (`household.create`,
  `household.add_member`, `character.possess`).
- E3: move that household into a lot mid-game (no direct command found: `game.move_in` only works at a new game's
  site selection; look for the in-game move flow or a Lua route).
- E4: drive an existing character like a puppet (the controller spawns puppets today; adopt by entity id instead).
- E5: autonomy per character (`autonomy.set_enable`) holds while they're driven.
- E6: round trip: save, upload, download on "another PC", load: same world.
