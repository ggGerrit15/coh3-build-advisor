# Replay collection and opener comparison

This extends the [single-replay pilot](replay-pilot.md) with a bounded collector,
an adapter for CoH3Stats daily match data, and an offline comparison report.
It does not change the public advisor's build recommendations.

## Capture verified on 14 October 2026

The [eight-command report](../data/replays/cohorts/mechanized-1v1-2.5.6-2026-10-14/report.md)
and [five-command report](../data/replays/cohorts/mechanized-1v1-2.5.6-2026-10-14/report-first5.md)
retain the manifest, all 30 normalized games, and ID-matched metadata.

- 85 recordings inspected across 30 listing pages; 30 target games from 23
  distinct Wehrmacht players, with 14 wins and 16 losses.
- 21 games against USF and 9 against British. The verified player ratings in
  this particular sample are all below 1400; it is not a high-level cohort.
- Outcomes matched for 30/30; verified pre-match rating for 29/30. One game
  is also Custom in daily metadata, so its oldrating remains unverified.
- 27 usable eight-command prefixes and 28 usable five-command prefixes.
  The exclusion checks can overlap; two matches have AI takeover, one has an
  unresolved name, and one does not reach eight commands within the window.
- Zero eligible ranked comparisons: all 30 replay files are classified as
  Custom; 29 of their daily records say AUTOMATCH. Resolve that mismatch
  before interpreting the sample as ranked build performance.
- Match [88336093](https://cohdb.com/replays/7280907): all **53 unique,
  non-cancelled timed labels** match the CoHDB build display at one-second
  resolution. The capture preserves the comparison and source HTML hash.

The most frequent eight-command groups each appear twice, from one player
each. This highlights why repeat recordings, player identity and sample size
must remain visible before recommending a build.

Reproduce either report offline from the committed capture:

```sh
python scripts/report_replay_cohort.py \
  --collection-dir data/replays/cohorts/mechanized-1v1-2.5.6-2026-10-14 \
  --prefix-length 8 \
  --output-json work/replays/reproduced-report.json \
  --output-markdown work/replays/reproduced-report.md
```

## Run a small cohort

Build the pinned reader first, then collect public CoHDB recordings. This
example selects Wehrmacht Mechanized 1v1 on patch 2.5.6/build 50313. It skips
games completed on 14 October so the preceding day's complete metadata dump
can supply pre-match ratings and outcomes.

```sh
cargo build --locked --release --manifest-path tools/replay-reader/Cargo.toml
python scripts/collect_replays.py \
  --patch 2.5.6 --game-build 50313 \
  --faction Wehrmacht --battlegroup Mechanized --mode 1v1 \
  --target 30 --max-pages 80 --max-downloads 200 \
  --completed-before 2026-10-14 --metadata-day 2026-10-13 \
  --output-dir work/replays/mechanized-2026-10-14
python scripts/report_replay_cohort.py \
  --collection-dir work/replays/mechanized-2026-10-14 \
  --prefix-length 8 --max-opener-seconds 600 \
  --output-json work/replays/mechanized-2026-10-14/report.json \
  --output-markdown work/replays/mechanized-2026-10-14/report.md
```

`--metadata-file` can reuse an already downloaded CoH3Stats daily JSON, with
`--metadata-url` identifying its source. Repeat either option to supply more
days. `--source coh3stats` instead tries the public cached replay mirror for
IDs discovered in those daily dumps. A missing mirror file is recorded as a
404; the mirror is not assumed to contain every tracked match. No API calls
that request server-side replay generation are included.

The collector returns 0 when its requested target is reached, 2 for a partial
collection, and 1 for invalid setup. A partial collection still has a manifest
and can be reported. Cached responses and completed datasets are retained on
interruption. Re-running the same command reproduces the cached listing order
and reuses downloaded responses; use a new output directory for a fresh
listing sample. Limits count attempted downloads, including missing files and
out-of-scope games, not just successful target records.

## Source handling

- Follow the actual next-page URL in CoHDB's `load-page` frame. Do not invent a
  cursor, silently widen the selected mode, or use a winner-only list.
- Use the observed download route `/replays/{replay_id}/file?inflate=true`.
  CoHDB redirects it to its public Backblaze storage. Only the observed source
  hosts are accepted; signed redirect URLs are not saved in the evidence.
- Requests have finite timeouts and response-size limits, a one-second
  minimum interval, disk caching, and positive collection limits. Access
  failures 401/403/429 stop collection rather than retrying a challenge.
- The source manifest records listing URLs and hashes, attempted recordings,
  exclusions/errors, stopping reason, and whether the target was reached.
- Filter faction, battlegroup, patch and mode from the parsed replay itself.
  CoHDB replay IDs and Relic match IDs are different identifiers.

## Metadata identity and uncertainty

CoH3Stats publishes [open daily match data](https://coh3stats.com/other/open-data).
Join its `id` to the replay's match ID, and each report's `profile_id` to the
replay player. Require the complete same player set and matching races. The
existing normalizer additionally rejects a different mode.

Use `matchhistorymember.oldrating` for pre-match ELO. Do not substitute
`newrating`, a player's present-day leaderboard rating, or the displayed CoHDB
rating range. Results use `resulttype`: 1 win, 0 loss, 4 draw. Conflicting
`outcome` and `resulttype` are rejected. These mappings follow the public
[CoH3Stats types and rendering code](https://github.com/cohstats/coh3-stats).
Source URLs and a hash of the supplied dump are preserved in metadata.
For a daily record identified as Custom, CoH3Stats warns that its rating is
inaccurate. That `oldrating` is retained as `rating_before_unverified`, while
`rating_before` remains null and cannot enter a pre-match ELO comparison.

If daily metadata is unavailable, the CoHDB list's revealed victor can supply
an outcome for an exact, verified two-player human match. Predicted win
probabilities are never used as results. Pre-match ELO stays null.

The first observed cohort recordings are identified as `Custom` by the pinned
reader, while the joined daily records say `description: AUTOMATCH` and
`matchtype_id: 20`. Preserve both values. The metadata label does not override
the replay classification; those games remain ineligible for ranked
statistics pending investigation. `metadata_match_type_consistent` additionally
blocks the reverse conflict (an Automatch replay with Custom daily metadata).
The CoH3Stats frontend currently uses type
20 for 1v1, while its historical type name says `1V1_Unranked`, so a type number
alone must not be treated as independent proof of ranked status.

## What the report compares

- Deduplicate by **match ID + player profile ID**, even when two recordings
  have different hashes. Conflicting timelines or metadata are rejected.
- Compare entire ordered prefixes using `(action kind, blueprint ID)`.
  Retain repetitions, buildings, research, and command times; do not assemble
  a synthetic opener by independently choosing each position's most frequent
  unit. Default starting units are absent from this command log.
- The default prefix is the first eight usable production/construction/
  research commands within ten minutes. Cancelled commands are excluded.
  Suspect or unresolved commands inside the prefix window make it unusable.
  Short/incomplete windows are counted explicitly.
- Keep opponent faction and target-player pre-match ELO band separate.
  Group map scope is explicitly all maps in this available-replay sample.
  The report retains every individual map and source match for review.
- Exploratory tables show frequency only. Ranked outcome comparisons require
  every existing quality check, including exact patch data, unmodded human
  Automatch, no AI takeover, resolved names, result and pre-match ELO.
- Eligible outcome groups show wins/losses, raw WR and a 95% Wilson interval.
  Small samples are flagged; this neither corrects repeated-player dependence
  nor identifies a causal advantage. Groups are sorted by frequency, not WR.

This is a convenience sample of available recordings. Even 20–30 games are a
collection pilot, not evidence for a "best" build. Battlegroup membership is
retrospective: some players choose it after already playing their opener.
Recommendations still need a larger comparable sample and gameplay review.

## Files and verification

The working folder contains `manifest.json`, cached source responses, raw
replays, normalized `datasets/`, and canonical `metadata/`. It is ignored by
git. A reviewed capture can be copied into `data/replays/cohorts/`; raw replay
binaries and the entire daily dump should remain outside the repository.

The tests cover ID/race/result joins, absent pre-match ratings, ordered
prefixes, rating/opponent separation, repeated recordings, uncertain/short
openers, strict ranked eligibility, stopping at the requested target, and
access failure without retries.

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node tests/test_cohdb_runtime.mjs
```
