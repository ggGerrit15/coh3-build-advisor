# Our replay research database

The replay project now has a versioned **SQLite database**. It stores actual
match/player command sequences and evidence from multiple collections. Python's
standard library is sufficient; no database server, account or API key is
required. The public website is not connected to it yet.

This is a research store. It does not automatically turn frequently observed
openers into recommendations. Patch, mode, opponents, battlegroup and verified
rating context remain part of each comparison.

## Saved snapshots

The database binary, its SQL backup and collection-specific summaries are
kept in the user's saved data package. Code, schema and tests live in this PR.
Working `.sqlite3` files and raw replay binaries are excluded from git.
User-uploaded datasets and their analysis are not published to the repository.

## Initialize and import

Commands run from the repository root. On Windows, use `py -3` instead of
`python` if needed.

```sh
python scripts/replay_database.py init \
  --database work/replays/research/coh3-replays.sqlite3
python scripts/replay_database.py import \
  --database work/replays/research/coh3-replays.sqlite3 \
  --input data/replays/cohorts/mechanized-1600plus-1v1-2.5.6-2026-10-14 \
  --source-key cohort:mechanized-1600plus-20261014 \
  --source-kind cohort \
  --provenance data/replays/cohorts/mechanized-1600plus-1v1-2.5.6-2026-10-14/manifest.json
python scripts/replay_database.py stats \
  --database work/replays/research/coh3-replays.sqlite3 \
  --output-json work/replays/research/summary.json
```

For subsequent downloaded recordings, first use the
[local replay importer](local-replay-import.md). Supply its output folder to
the database's `--input` and its `manifest.json` to `--provenance`, choosing a
new source key and `--source-kind upload`. This imports every normalized
dataset in that folder, including games outside the batch importer's default
Mechanized comparison scope. It reads both players and stores their actual
battlegroups. No manual battlegroup sorting is needed.

Inputs can also be explicit normalized JSON files. Directories with a
`datasets/` child use that child; otherwise the importer considers their JSON
files and skips other known document/schema types. Raw `.rec` or ZIP files
are not SQL database inputs: they first go through the existing replay reader.

`--provenance` is stored as source documentation only. A user-provided 1600+
filter never populates individual ratings. A source key is immutable: reuse
it for the exact same source/provenance, or choose a new key for a different
collection. A changed source description is rejected rather than overwriting
the old receipt.

## Storage and deduplication

| Table | Identity and contents |
| --- | --- |
| `sources` | Collection key, kind, original provenance JSON and creation time |
| `matches` | One row per Relic match ID; exact version, mode, map and immutable command-core hash |
| `match_players` | One row per match ID + player profile ID; faction, battlegroup, team, AI/takeover markers |
| `replays` | Decompressed replay SHA-256; separate recordings can belong to one match |
| `datasets` | Immutable normalized observations, source URL and full original JSON |
| `source_datasets` | Source/file receipts pointing to observations; overlapping collections do not duplicate matches |
| `player_evidence` | Per-observation ratings, results, quality checks, ladder resolution and usable five/eight-command windows |
| `actions` | Ordered commands, cancellations, suspect/unresolved flags, blueprint IDs, build positions and battlegroup unlock positions |

Reimporting the same data is idempotent. Only the top-level normalization
timestamp is ignored when identifying a dataset; source and metadata changes
remain separate observations. Different recordings of the same match can be
retained without duplicating its commands when their stable core agrees.

A conflicting match identity/command timeline, contradictory known outcome
or conflicting verified rating rejects the whole import batch. Existing data
is preserved and the failure is explicit. Source registration and evidence
insertion use the same transaction. Reconciliation of contradictory evidence
requires an explicit follow-up rather than a silent overwrite.

Match IDs and player profile IDs must be known and positive. Unidentified
local recordings remain available in the folder import's review output; they
are not merged into a fictitious match or player in the research database.

## Evidence and quality

The importer recomputes sequences, quality checks and ladder resolution with
the existing normalizer, and rejects disagreements with stored sequences or
quality markers. The existing Relic reference validation still applies.
Derived five/eight-command eligibility uses the same cohort analyzer as the
reports, including uncertain commands and AI takeover exclusions.

Each observation retains its rating status:

- `verified_pre_match`: supplied pre-match rating with a captured daily-source
  or canonical Relic Steam history URL/hash, the source's expected oldrating
  field and the validated ladder resolution.
- `source_claim`: supplied pre-match value without that complete evidence chain.
- `unverified`: displayed or explicitly unverified ratings, never substituted
  into the verified-rating column.
- `unknown`: no rating evidence.

Relic history captures join the separate member and result arrays using exact
match/player IDs, factions and teams. Only `oldrating` supplies pre-match ELO;
`newrating` and a listing filter cannot fill a missing value. History results
use the existing `observed_source` status, with the exact Relic URL retained;
`matched_daily_source` remains reserved for daily dumps.

See [metadata enrichment](replay-metadata.md) for the offline capture workflow.

These labels preserve the captured pipeline's evidence; the database import
does not fetch live sources or authenticate an arbitrary third-party JSON file.
Only reviewed datasets and their provenance should be admitted. Missing ELO
and results remain NULL, including for a user-selected high-rating listing.

New metadata produces a new observation. Best-evidence views prefer verified
ratings, then daily-source outcomes, known outcomes and ladder eligibility.
They select an entire observation for a player rather than combining arbitrary
fields from several versions. Later unknown uploads cannot downgrade a known
verified rating, and all original observations remain available.

## Read-only analysis views

| View | Purpose |
| --- | --- |
| `v_player_builds` | One best-evidence row per match/player, preserving rating status and opener quality |
| `v_build_commands` | Actual ordered build/research commands, with issued-command times and context |
| `v_battlegroup_coverage` | Per-patch/mode/faction/battlegroup coverage, distinct players, usable windows and verified ratings |
| `v_best_player_evidence` | The provenance-preserving observation selected for each match/player |

Example: inspect coverage without mixing patches/modes:

```sql
SELECT * FROM v_battlegroup_coverage
WHERE patch = '2.5.6' AND mode = '1v1'
ORDER BY faction, battlegroup;
```

Example: select genuine verified 1600+ player records:

```sql
SELECT match_id, profile_id, name, faction, battlegroup,
       verified_rating_before, result
FROM v_player_builds
WHERE patch = '2.5.6' AND mode = '1v1'
  AND faction = 'Wehrmacht' AND battlegroup = 'Mechanized'
  AND verified_rating_before >= 1600
  AND ranked_eligible = 1 AND opener8_usable = 1;
```

Counts are player-game observations unless explicitly named matches. Opponent
factions remain in `opponent_factions_json`; keep them separate for build
comparisons. Do not rank tiny groups by raw win rate or treat late-game
commands as evidence of a causal advantage.

## Backup and future hosting

The first snapshot includes the SQLite file, a logical SQL dump, a machine-
readable summary and a short German README. The database stores the full
normalized payloads and source receipts, so this snapshot can be extended
without repeating the original replay downloads. Use the newest snapshot as
the next import's starting point; independently created snapshots are not a
shared, automatically synchronized database.

The CLI checks application/schema versions and refuses unrelated databases.
`stats` opens an existing database read-only. Schema version 1 has no automatic
migration or online hosting. A future hosted service can migrate the relational
model to PostgreSQL/Supabase and expose bounded read APIs; credentials,
permissions, hosted backups and website integration are separate work.

## Validation

Tests cover repeat imports, source receipts, rerecordings, user selection versus
verified ratings, metadata upgrades without downgrades, action ordering,
conflict rollback, immutable provenance, forged sequence/quality markers,
foreign keys and unrelated-database protection. GitHub additionally runs the
database CLI twice on the committed stronger capture and requires unchanged
30-match/60-player counts with 60 captured verified player ratings.
