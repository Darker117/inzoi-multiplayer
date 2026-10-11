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

## Decided (2026-10-11)

- When several people played together: the world comes from the last to leave; each player's own household (needs,
  skills, money, relationships, career) comes from that player's own copy.
- Before a server restart: everyone's game is saved first (main menu for a moment), uploaded, and reloaded after.

## Game experiments (in a copy of the test save)

- E1 PASSED: a copied world (renamed header) is listed as a valid save and loads (`game.load folder=`). Saves start
  paused after loading; the window must be in focus for the clock to run.
- E2 PASSED: a household built from a player's profile (`RegisterHousehold`, the puppet code path) can be played:
  `character.possess character_id= household_id=` switches to it with a normal HUD, needs, and its own money
  (M 30,000, like a new family). It starts without a home.
- E3 OPEN: moving that household into a lot mid-game. `game.list_move_in_sites` lists free lots for it, but
  `game.move_in` only works at a new game's first house pick. Next: the game's own map "move in" flow (by hand, or
  driven with ui.*).
- E4 PASSED: the controller's new `adopt` op drives an existing Zoi (Bella) like a puppet (it walked the given
  trail); `despawn` releases an adopted Zoi (free will back) instead of destroying it.
- E5 PASSED: the controller's `freeze` (FB2AutonomyOptionManager individual toggles) works on any Zoi; the CLI
  `autonomy.set_enable` reply is unreliable.
- E6: copy + load proven (E1) and file transfer proven (mod sync); the world round trip is built in stage 1.
