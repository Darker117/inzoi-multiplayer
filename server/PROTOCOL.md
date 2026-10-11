# inZOI Multiplayer wire protocol (v1)

TCP, one JSON object per line (UTF-8, `\n`-terminated). Every message has `t` (its type). Default port 24242.

## Joining

Client → `{"t":"hello","protocol":1,"key":"<16-128 chars, generated once per player and kept secret>","name":"Ana","password":""}`

Server → `{"t":"welcome","id":"p1a2b3c4","leader":"<player id>","world":{...}|null,"players":[Player...],"houses":[HouseMeta...],"motd":""}`
or `{"t":"error","fatal":true,"error":"..."}` and the connection closes.

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
| `ping` / `pong` | `echo?` | keepalive; the server pings every 15 s and drops clients silent for 45 s |

## Server → client

`welcome`, `joined {player}`, `left {id,name}`, `leader {id}`, `state {id,state}`, `profile {id,profile}`,
`world {world}`, `chat {id,name,text,time}`, `event {from,kind,data}`, `house_updated {meta}`, `house`, `house_list`,
`who`, `ping`, `pong`, `kicked {reason}`, `error {error, fatal?}`.

## What the companion puts in messages (the server relays them as-is)

- `state.state` = `{n, x, y, z, yaw, city, site, act, anim, outfit}`: sample counter, world position (cm) and facing
  (degrees) of the player's Zoi, its city map and lot, and
  - `act`: what it's doing, or null: `{bag}` alone, `{bag, player}` with another player's Zoi,
    `{bag, obj, ox, oy, oz}` with an object (table id + world position), `{bag, npc: true}` with someone only that
    world has
  - `anim`: the motion playing (shown when the action itself can't be copied)
  - `outfit`: the outfit category worn (Everyday, Sports, Swimwear...)
- `profile.profile` = `{first_name, last_name, gender, growth_step, personality, characteristics, voice,
  gender_identity, look}` (look = the game's appearanceSetting JSON).
- `house_put.house` = `{name, by, lot, site, files: {filename: base64}}`: a lot from the player's in-game library
  (Documents/inZOI/Creations/MySites/<id>/). The stored meta is `{owner, updated, name, by, lot}`.
- `world.world` = `{hour, minute, season, weather}` from the leader (clock sync is opt-in on the receiving side).

## Event kinds used by the companion (relayed opaquely by the server)

Defined by the companion app; the server never needs to know them. Planned: `visit_request`, `visit_reply`,
`interact` (one Zoi starts a social interaction with another player's Zoi), `interact_reply`, `emote`.
