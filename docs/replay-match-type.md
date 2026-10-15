# Quick Match, replay AUTO flags, and ladder membership

## Verified finding

The pinned [`cohlib` decoder](https://github.com/ryantaylor/cohlib/blob/d31ade03fa69301c571ceb7416d0d1e67eff99aa/crates/replay/src/parsed.rs) reads the first byte of the replay's `DATAAUTO`
chunk. It calls the game Automatch only for value 1, and Custom for value 0.
Its own `Replay::game_type` documentation describes this as best-effort.

All 30 initial recordings have AUTO=0. However, 29 matching daily records use
match type 20 and description AUTOMATCH. This is a distinction between the
replay flag and **ladder membership**, not a translation or gzip error.

Relic's live public
[`getAvailableLeaderboards`](https://coh3-api.reliclink.com/community/leaderboard/getAvailableLeaderboards?title=coh3)
response captured on 14 October names type 20 `1V1_Unranked`, localized as
**Quick Match**, while assigning it to faction-specific **isranked=1** ladders.
For example, Wehrmacht uses leaderboard 2130261 with race 137123/type 20;
USF uses 2130255 with race 129494/type 20. Historical names must not override
the actual ranked leaderboard maps. This does not assert that Quick Match is
a separate Ranked queue.

An independent direct Relic match-history request for
[profile 1222282](https://coh3-api.reliclink.com/community/leaderboard/getrecentmatchhistory?profile_ids=%5B1222282%5D&title=coh3)
also returned match **88335815**, type 20, description AUTOMATCH. For both
players its IDs, races, outcomes and old/new ratings match the CoH3Stats daily
dump. The Wehrmacht player's rating changed 991 → 979 and the USF player's
1062 → 1074. The corresponding replay nevertheless has AUTO=0.

The raw definition response, its checksum/source receipt, and the selected
direct match-history verification are versioned under `data/replays/reference/`.
This establishes why AUTO=0 must not veto an independently verified
ladder-rated Quick Match. It does not establish why the game wrote that flag
or infer a universal rule for other game builds.

## Resolution policy

`match.game_type` remains the original `cohlib` label. The normalizer separately
stores `match.match_type_resolution`, its basis, reference hash, queue name,
applicable leaderboard IDs, and `raw_disagreement` diagnostic.

A Custom replay can qualify as `ladder_automatch` only with:

1. Complete same match/player IDs and matching factions in canonical metadata.
2. A CoH3Stats daily-source URL, AUTOMATCH description, Steam platform, and a
   mode matching the replay teams.
3. The exact verified Relic reference URL/hash/capture and a covered game build.
4. Exactly one isranked=1 leaderboard mapping for **each** player's faction and
   the recorded match type/mode.

The reference currently covers build **50313 / patch 2.5.6**. Future builds need
new evidence before a negative replay flag can be overridden. A bare
AUTOMATCH label, missing players, invalid reference hash, unsupported type,
or unmatched source cannot upgrade the replay. Type 0 remains a genuine
Custom game; its oldrating stays unverified and it cannot enter ladder WRs.

The remaining quality gates still apply: no mods, human players, no AI
takeover, exact game data, resolved commands, outcomes and pre-match ratings.
`metadata_match_type_consistent` now describes agreement after this documented
resolution; the original disagreement is retained separately. Existing JSON
keys named `ranked_game`, `eligible_for_ranked_statistics` and `ranked_openers`
are compatibility names for **ladder-rated** evidence, not the queue label.

## Stronger-player discovery

Use `--min-player-rating 1600`. Optionally add `--max-player-rating 1800` for an
exclusive upper bound. The report continues to separate 1600–1800 and 1800+
players and opposing factions.

`--listing-rating min:1600` is only a coarse CoHDB discovery filter. Every
selected target player's actual `oldrating` is checked independently after
the exact match/player join. An apparent CoHDB rating range is not used to
qualify the player. Unknown ratings are excluded from a requested rating
window.

To avoid downloading recordings that cannot satisfy the supplied daily data,
the collector first considers target-faction profile IDs known to meet the
requested rating window in those dumps. This is a discovery prefilter only:
the player's rating in the **specific parsed match** must still qualify.
Prefilter exclusions and actual download attempts are counted separately.
Losses are retained, and no build sequence is synthesized position by position.

`--preview-builds` checks the public CoHDB build display before downloading.
It can skip an explicitly recognized different battlegroup. An exact daily
roster can identify which profile belongs to the requested faction; without
that join, both listed battlegroups must be recognizable before rejecting the
recording. Unknown labels fall back to the binary download. A positive preview
never qualifies a game by itself: the parsed replay must still confirm the
match ID, faction, battlegroup, patch, mode and the particular player's rating.
Preview source hashes and exclusion reasons remain in the manifest.

## Checks

Tests cover Quick Match classification with and without a valid reference,
hash tampering, partial player joins, unsupported builds and AI match types,
true Custom exclusions, exact ELO boundaries, and the independence of the
coarse discovery filter from a particular match's pre-match rating.
