# inZOI Multiplayer wire protocol (v1)

TCP, one JSON object per line (UTF-8, `\n`-terminated). Every message has `t` (its type). Default port 24242.

## Joining

Client → `{"t":"hello","protocol":1,"key":"<16-128 chars, generated once per player and kept secret>","name":"Ana","password":"","host":false}`

Server → `{"t":"welcome","id":"p1a2b3c4","leader":"<player id>","host":"<player id>"|null,"world":{...}|null,"players":[Player...],"houses":[HouseMeta...],"modset":ModSet,"motd":""}`
or `{"t":"error","fatal":true,"error":"..."}` and the connection closes.

`host: true` counts only on a server started inside a player's program ("Host and play", `Server(hosted=True)`) and only
from that same PC (127.0.0.1): that player becomes the host (their mods are everyone's, they lead the clock).

A second connection with `"files": true` in its hello is the same player's mod file connection: the server answers
`{"t":"files_ok"}` and accepts only `blob_check`, `blob_put`, `blob_get` (and ping/pong) on it.

`Player` = `{"id","name","profile","state","leader"}`. The `id` is stable for a key, so houses and profiles survive reconnects.
Connecting again with the same key replaces the old session (it gets `{"t":"kicked"}`).

## Client → server

| `t` | fields | what happens |
|---|---|---|
| `state` | `state` | live Zoi state (position, rotation, animation, interaction, site); relayed to everyone else as `state` |
| `profile` | `profile` | the player's Zoi (name, appearance, traits); stored, relayed as `profile` |
| `world` | `world` | clock/weather/season; only accepted from the leader, relayed as `world` |
| `take_leader` | | become the world-clock leader; everyone gets `leader` |
| `chat` | `text` (≤500) | broadcast to everyone, including the sender, as `chat` |
| `event` | `kind`, `data`, `to?` | generic relay to one player (`to`) or everyone else; arrives as `event` with `from` |
| `house_put` | `house` | store a snapshot of your house; everyone gets `house_updated` |
| `house_get` | `owner` | reply `house` with `meta` and `house` (null if none) |
| `house_list` | | reply `house_list` |
| `who` | | reply `who` with everyone online |
| `mods` | `mods: [Mod]` | the player's enabled mods; stored; everyone gets `modset` if the set changed |
| `ping` / `pong` | `echo?` | keepalive; the server pings every 15 s and drops clients silent for 45 s |

## Mod file connection (`files: true`)

| `t` | fields | answer |
|---|---|---|
| `blob_check` | `h: [sha256]` | `blob_missing {h}`: the ones the server doesn't have yet |
| `blob_put` | `h, o (offset), d (base64), end` | in order, only files of your own mods; after `end`: `blob_ok {h}` or `blob_bad {h, error}` |
| `blob_get` | `h, o` | `blob {h, o, d, end}` (512 KB pieces), or `blob {h, error: "not shared" / "not uploaded yet"}` |

`Mod` = `{id, name, version, built, path, size, files: [{p, h, s}]}`: the mod_manifest's ProjectName, FriendlyName,
Version and PackageTime, its folder under Documents/inZOI/Mods, and each file's path, sha256 and size.
`ModSet` = `{source: "host"|"everyone", host, mods: [Mod + by: [names]]}`: hosted, the host's mods; otherwise everyone's
pooled (the newest build of a mod wins).

## Server → client

`welcome`, `joined {player}`, `left {id,name}`, `leader {id}`, `state {id,state}`, `profile {id,profile}`,
`world {world}`, `modset {source,host,mods}`, `chat {id,name,text,time}`, `event {from,kind,data}`, `house_updated {meta}`, `house`, `house_list`,
`who`, `ping`, `pong`, `kicked {reason}`, `error {error, fatal?}`.

## What the companion puts in messages (the server relays them as-is)

- `state.state` = `{n, x, y, z, yaw, city, site, act, anim, outfit, clock, sleep}`: sample counter, world position (cm) and facing
  (degrees) of the player's Zoi, its city map and lot, and
  - `act`: what it's doing, or null: `{bag}` alone, `{bag, player}` with another player's Zoi,
    `{bag, obj, ox, oy, oz}` with an object (table id + world position), `{bag, npc: true}` with someone only that
    world has
  - `anim`: the motion playing (shown when the action itself can't be copied)
  - `outfit`: the outfit category worn (Everyday, Sports, Swimwear...)
  - `clock`: `[hour, minute]` of the player's game while it runs (null while paused); a player who's behind catches
    up with whoever is furthest ahead
  - `sleep`: the player's Zoi is asleep; while everyone's is, everyone's game runs fast, otherwise at normal speed
- `profile.profile` = `{first_name, last_name, gender, growth_step, personality, characteristics, voice,
  gender_identity, look}` (look = the game's appearanceSetting JSON).
- `house_put.house` = `{name, by, lot, site, files: {filename: base64}}`: a lot from the player's in-game library
  (Documents/inZOI/Creations/MySites/<id>/). The stored meta is `{owner, updated, name, by, lot}`.
- `world.world` = `{season, weather}` from the leader; the others match them (unless they turned time sync off).

## Event kinds used by the companion (relayed opaquely by the server)

Defined by the companion app; the server never needs to know them. Planned: `visit_request`, `visit_reply`,
`interact` (one Zoi starts a social interaction with another player's Zoi), `interact_reply`, `emote`.
