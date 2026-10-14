# Single-replay pilot

The existing CoHDB importer reads aggregate HTML statistics. This pilot adds an
independent `.rec` reader and a normalized, player-specific event dataset. It
does not update the public advisor, curated builds, or aggregate CoHDB snapshot.

## Reproduce the verified capture

Requires Python 3.12 and Rust 1.99.0. `cohlib` is pinned to commit
`d31ade03fa69301c571ceb7416d0d1e67eff99aa`; Cargo.lock pins its dependencies.

```sh
cargo build --locked --release --manifest-path tools/replay-reader/Cargo.toml
mkdir -p work/replays
curl -fL --max-time 60 'https://cohdb.com/replays/7283962/file?inflate=true' -o work/replays/88366979.rec
python scripts/import_replay.py \
  --replay work/replays/88366979.rec \
  --metadata data/replays/examples/match-88366979-metadata.json \
  --source-url https://cohdb.com/replays/7283962 \
  --output work/replays/88366979.json
```

The reader accepts plain and gzip-compressed replay downloads. If a source
blocks downloads, the importer reports the error; a normally downloaded local
file can be supplied instead. No browser challenge bypass is included.

For a direct check against CoHDB's build display:

```sh
curl -fL --max-time 60 https://cohdb.com/replays/7283962/builds -o work/replays/88366979-builds.html
python scripts/check_replay_cohdb.py \
  --dataset work/replays/88366979.json \
  --html work/replays/88366979-builds.html
```

## Capture verified on 14 October 2026

Match [88366979](https://cohdb.com/replays/7283962), patch 2.5.6/build 50313,
1v1, Angoville Farms. The replay produces 58 classified commands across two
players. All **57 unique, non-cancelled timed labels** match CoHDB's display
at its one-second resolution. The checked label fixture records the source URL
and capture date. This check covers names and command times, not production
completion or repeated identical commands within the same second.

| Player | Battlegroup | Reviewed production/tech commands | BG unlock commands |
| --- | --- | ---: | ---: |
| [GER] Miau | Breakthrough | 22 | 4 |
| Sir_Chifirdrink | Heavy Armor | 19 | 6 |

The British timeline contains a cancelled Dingo order and two suspect building
orders. All three remain in `actions` for review and are excluded from
`build_sequence`. The later, non-cancelled Dingo is retained.

The match overview identifies Axis as victor. Its displayed ELO values are
recorded separately: the capture does not independently establish that they
are pre-match ratings, so `rating_before` remains null. The parser identifies
this replay as `Custom`. Both player records consequently have
`eligible_for_ranked_statistics: false`. This is a technical validation sample,
not part of the planned Mechanized 1v1 ranked cohort and not a win-rate claim.

## Data contract

- Reader output: `coh3.replay-reader.v1`.
- Normalized output: `coh3.replay-dataset.v1`.
- Optional metadata: `coh3.match-metadata.v1`, joined by match ID and profile ID.
- Advisor mapping: `faction|mode|battlegroup`, only when the exact profile exists.
- Every command retains tick, command index, blueprint ID, resolved name, and
  cancellation/suspect flags. Eight ticks equal one second.
- `build_sequence` includes production, construction, and research commands
  with no exclusion flags. BG unlocks are a separate sequence.
- Times mean **command issued**, not unit built, completed, or arriving.
- Default starting squads are not enumerated by this production log;
  `starting_units` remains null rather than inventing a production command.
- Missing outcomes/ratings remain null. Displayed ratings are not substituted
  for pre-match ratings. Metadata with mismatching IDs, patch, mode, or faction
  is rejected.
- Game-data lookups can fall back across versions. The dataset records exact
  build coverage and unresolved names; missing coverage or unresolved names
  block ranked statistical eligibility.
- AI players, disconnects, mods, non-Automatch games, unsupported team sizes,
  absent profiles, and missing result/rating also block eligibility.

Metadata currently comes from the explicitly verified capture or a supplied
JSON file. A bulk downloader, automatic metadata adapter, opener aggregation,
and public frontend integration are later steps. Use match ID plus profile ID
to deduplicate different replay recordings of the same player/game.

## Checks

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
cargo test --locked --manifest-path tools/replay-reader/Cargo.toml
node tests/test_cohdb_runtime.mjs
```

The replay-specific workflow also smoke-tests a fixed upstream build-50313
replay fixture. It has read-only permissions and does not deploy the website.
