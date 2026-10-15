# Enrich existing replays with match metadata

`scripts/enrich_replay_database.py` joins reviewed local public metadata
captures to existing database matches. It does not download replays, contact
remote services or change website recommendations.

Supported captures are CoH3Stats open daily match JSON and successful responses
from Relic's public Steam `getRecentMatchHistoryByProfileId` endpoint. Daily
data is preferred when both sources agree. A current-day daily dump may not
exist yet; a missing match stays unknown unless another exact source covers it.

## Capture manifest

Create a JSON manifest beside the captured files. Each entry gives the exact
public URL, local filename and SHA-256 of the complete response bytes. An
optional `captured_at` records retrieval time. For example, its `sources` array
can contain a daily capture URL of the form
`https://storage.coh3stats.com/matches/matches-<UTC-midnight-timestamp>.json`
or the canonical history URL
`https://coh3-api.reliclink.com/community/leaderboard/getRecentMatchHistoryByProfileId?title=coh3&profile_id=<positive-profile-ID>`.

The manifest shape is:

```json
{
  "sources": [
    {
      "file": "captured-response.json",
      "url": "<exact public source URL>",
      "sha256": "<SHA-256 of the captured bytes>",
      "captured_at": "<retrieval timestamp>"
    }
  ]
}
```

The placeholders must be replaced with real capture information. A checksum
detects changed local bytes; it does not authenticate an arbitrary JSON file.
Use captures actually obtained from the stated public sources. Keep raw
captures and collection-specific analysis out of the public code repository.

## Enrich a collection

```sh
python scripts/enrich_replay_database.py \
  --database work/replays/research/coh3-replays.sqlite3 \
  --captures work/replays/metadata/captures.json \
  --collection-source <existing-collection-source-key> \
  --source-key <new-metadata-source-key> \
  --output-dir work/replays/enriched
```

On Windows, use `py -3` instead of `python` if needed. Repeat
`--collection-source` to include several existing collections. The database
must exist, and the output folder must be new or empty. Repeating an import
with the same captures/source key in a fresh output folder is idempotent.

Every available observation for a match must agree on player identities,
factions, pre-match ratings and outcomes. Missing matches are listed explicitly.
A disagreement fails before database insertion. Database-level conflicts also
roll back the entire insertion batch.

The output retains enriched normalized datasets and `enrichment-report.json`
with selected/corroborating sources, missing IDs and import counts. Previous
unknown observations remain stored. Matches and commands are not duplicated.

## Direct Relic history checks

Relic puts results in `matchhistoryreportresults` and ratings in a separate
`matchhistorymember` array. The adapter joins the complete member set by
profile ID and requires each member/report's match ID, faction and team to
agree. It checks member outcomes against report outcomes. Only `oldrating`
is read as pre-match ELO; absent values remain unknown.

The exact endpoint's `title=coh3` selects Steam. Unsupported hosts/platforms,
missing capture hashes and requested profiles outside the replay are rejected.
Ladder classification still requires the captured Relic ranked leaderboard
reference and its applicable game build; an `AUTOMATCH` string alone is not
sufficient. Genuine Custom matches keep unverified ratings.

Quality exclusions remain independent of metadata coverage. A known result
or verified rating does not make AI-takeover games, unknown battlegroups or
uncertain opener windows eligible for comparisons.
