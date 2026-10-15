# From verified replays to reviewable opener candidates

The [candidate export](../data/replays/cohorts/mechanized-1600plus-1v1-2.5.6-2026-10-14/candidates.md)
is the next offline step after the collection pilot. Its
[JSON](../data/replays/cohorts/mechanized-1600plus-1v1-2.5.6-2026-10-14/candidates.json)
is a review dataset, not a new recommended build or frontend data replacement.

## Reproduce

```sh
python scripts/export_replay_candidates.py \
  --collection-dir data/replays/cohorts/mechanized-1600plus-1v1-2.5.6-2026-10-14 \
  --output-json work/replays/candidates.json \
  --output-markdown work/replays/candidates.md
python -m unittest discover -s tests -p 'test_*.py' -v
```

The script reanalyzes normalized datasets from the collection manifest. It
does not trust counts copied from a previous report. The output records the
manifest hash and the path/hash of every input dataset. Regeneration changes
the generation timestamp; the remaining JSON content and Markdown reproduce
exactly from the capture.

## Observed core and actual continuations

The default core is the first five usable issued production, construction or
research commands, retaining repeats and order. A continuation extends that
same match/player to eight commands. Both windows must pass the existing
ladder, metadata and replay quality checks. The default time limit is ten
minutes. Cancelled or uncertain commands follow the existing report policy.

Every branch is an entire observed sequence. The exporter does not choose a
majority unit independently at each position. It does not infer starting
units, production completion, resource availability, opponent scouting or the
reason a player chose a branch. Battlegroup unlocks remain in the source
datasets; they are not mixed into the production sequence.

The exact patch, mode, faction, battlegroup and verified target-player ELO
scope come from the manifest. Opponent faction and pre-match ELO band remain
separate in every candidate. Match/player deduplication and conflict checks
are inherited from the existing cohort analyzer. Short/uncertain longer
windows stay visible and are excluded only from continuation counts, rather
than deleting an otherwise usable five-command core.

## Repeated-player sensitivity

Within each opponent/rating stratum, the export includes:

- Game frequency: games using the exact core divided by all eligible core
  windows in that stratum.
- Equal-player frequency: each eligible player's share of games using that
  core, averaged across all eligible players, including zero uses. This is
  a descriptive sensitivity check, not a win rate or a correction for all
  selection and matchup biases.
- Each contributing profile's game count and the largest contributor's share.
- Remaining uses, players and population windows after removing the core's
  largest contributor. All of that player's population games are removed
  from the denominator, including their other openers. Ties use the lowest
  profile ID for reproducibility.

For continuation support, the population is only the same core's usable
longer windows. Missing longer windows are retained as exclusions with the
match ID, player ID and reasons. These conditional counts cannot establish
that reaching a follow-up caused a win.

## Findings from the existing stronger capture

The sample still contains **30 games from 13 target players**, with 30 usable
five-command windows and 29 usable eight-command windows. The export has 15
core candidates across four opponent/rating strata, with every candidate
containing fewer than 30 observations. Eight of the 30 games belong to profile
353207. No additional matches have been added on 15 October.

For USF opponents in the 1800+ target-player band, there are 10 eligible core
windows from six players:

| Observed first five commands | Games | Players | Game frequency | Equal-player frequency |
| --- | ---: | ---: | ---: | ---: |
| Kettenkrad → Infanterie Kompanie → Grenadier → Grenadier → Grenadier | 5 | 3 | 50.0% | 41.7% |
| Pioneer → Infanterie Kompanie → Grenadier → Grenadier → Grenadier | 3 | 3 | 30.0% | 41.7% |

These are observed issued orders, with default starting units absent. Equal
player weighting removes the apparent frequency lead in this stratum. It does
not establish that the openers perform equally well. The small, varied
continuation groups do not support one default eight-command build yet.

Against British opponents at 1800+, the Kettenkrad/three-Grenadier core has
five games from two players; four games come from profile 353207. Removing
that player leaves one use among five remaining eligible windows. Match
88161475 contributes a valid five-command core, but its uncertain action
excludes the eight-command window. The exporter preserves that distinction.

## Collection status on 15 October 2026

The next collection goal is a larger same-patch sample with more distinct
players before any gameplay recommendation is changed. Today's access check
could not begin collection:

- CoHDB's filtered listing returned HTTP 403, Cloudflare error 1010.
- The CoH3Stats daily metadata URL also returned HTTP 403.

No new recordings or daily metadata were obtained. The existing captures and
their manifests remain unchanged; no attempt is made to bypass these access
failures. A subsequent successful collection should keep the existing source
limits, verified per-match ELO, losses, exact version scope and exclusion
receipts. Counts must be reported as the actual retrieved sample rather than
the requested target.

The previous PR head `e2dcdd1240d2d35c9eb07125a4c9ae0bc769b66f`
passed [all GitHub validation steps](https://github.com/ggGerrit15/coh3-build-advisor/actions/runs/38608850166),
including the pinned Rust build/tests, upstream replay smoke test and frontend
baseline. New exporter tests cover repeated-player sensitivity, actual branch
identity, uncertain longer windows, non-ladder exclusions, strata, duplicate
recordings, input paths and reproduction of the saved export.

Every exported candidate remains `observed_only`. Larger samples and gameplay
review are still required before selecting a playable default, assigning
tactical triggers, or integrating recommendations into the public advisor.
