# Downloaded replays: local folder import

This imports already downloaded `.rec` and `.rec.gz` files without contacting
CoHDB, CoH3Stats or any other service. It creates a review folder containing
the observed commands, an import summary, comparison reports and any eligible
observed candidates. It does not publish changes to the advisor.

## Windows: first setup

Use a local checkout of this PR's `replay/pilot-import` branch. Open PowerShell
in its `coh3-build-advisor` folder. Python 3.12+ and Rust with Cargo must be
installed. The parser's Rust toolchain is pinned to 1.99.0. Its first build
downloads the pinned dependencies and therefore requires internet access;
subsequent replay imports themselves are offline.

Build the reader once:

```powershell
rustup toolchain install 1.99.0 --profile minimal
cargo +1.99.0 build --locked --release --manifest-path tools/replay-reader/Cargo.toml
```

The explicit `+1.99.0` selects the same version pinned in
`tools/replay-reader/rust-toolchain.toml`, including when running from the
repository root. The resulting Windows
reader is `tools/replay-reader/target/release/coh3-replay-reader.exe`; the
importer selects that `.exe` automatically on Windows. On Linux/macOS it uses
the corresponding executable without `.exe`. A different executable location
can be supplied with `--reader`.

## Import a folder

Put the regularly downloaded replay files in a folder, for example
`C:\CoH3-Replays`. Then run from the repository folder:

```powershell
py -3 scripts/import_local_replays.py "C:\CoH3-Replays" --patch 2.5.6
```

Here `2.5.6` explicitly selects the patch for comparison; it is not a claim
about the latest game version. The default comparison scope is **Wehrmacht /
Mechanized / 1v1**. The actual patch, factions, mode and battlegroups always
come from the parsed files. Other scopes are retained in datasets and the
summary, but excluded from this particular comparison.

The command prints its new output folder under `work/replays/local-…`. Open
`summary.md` there to see which files succeeded, which were duplicates or
outside the scope, and any errors. That folder is ignored by git. Original
replay files are read without modification.

For a predictable output folder:

```powershell
py -3 scripts/import_local_replays.py "C:\CoH3-Replays" --patch 2.5.6 --output-dir "work/replays/my-local-import"
```

The output folder must be new or empty. Use another name for the next batch;
existing evidence is never overwritten. Duplicate handling applies within a
batch, not across independent output folders. Do not add separate batch totals
together without match/player deduplication.

Multiple files or folders can be supplied in the same command. Use
`--recursive` to include subfolders, or choose another comparison scope:

```powershell
py -3 scripts/import_local_replays.py "C:\CoH3-Replays" --recursive --patch 2.5.6 --faction Wehrmacht --battlegroup Breakthrough --mode 1v1
```

The default limit is 200 replay files; `--max-files` changes it explicitly.
An empty input folder, an invalid input or a file count over the limit fails
before import. Uppercase extensions and paths containing spaces are supported.
On Linux/macOS, replace `py -3` with `python3` and use the local folder path.

## What the output contains

| File or folder | Purpose |
| --- | --- |
| `summary.md` | Status per input file, every imported player's first commands, unknown metadata and exclusion reasons |
| `manifest.json` | Local input filenames, content identity, metadata hashes, duplicates, errors and scope |
| `datasets/` | Normalized events for every unique imported replay, including games outside the comparison scope |
| `metadata/` | Copies of supplied canonical metadata, if available |
| `report-first5.md` / `.json` | Complete observed five-command prefixes within the selected scope |
| `report.md` / `.json` | Complete observed eight-command prefixes within the selected scope |
| `candidates.md` / `.json` | Verified-ladder eligible cores and their actual continuations, all observed-only |

Commands are issued orders, not unit completion or arrival times. Default
starting units are absent from the production log. Cancelled and uncertain
commands stay in the normalized actions with exclusion flags. The comparison
reports additionally check complete opener windows.

Without external metadata, ELO and results remain **unknown**. Such games can
still provide exploratory command sequences if their other quality checks
pass, but cannot enter eligible ladder outcomes or the verified candidate
export. An empty candidate file is expected in that case; it does not mean
the command import failed.

## Optional existing metadata

If canonical metadata from the existing pipeline is available locally, put it
in a separate folder using `match-<match_id>.json`, for example
`match-88366979.json`. The expected schema is `coh3.match-metadata.v1`, as used
by the existing single-replay importer and committed cohort metadata. Supply
that folder:

```powershell
py -3 scripts/import_local_replays.py "C:\CoH3-Replays" --patch 2.5.6 --metadata-dir "C:\CoH3-Metadata"
```

The match ID and player profile IDs must match the replay. Supplied faction,
patch and mode fields must also agree. A missing sidecar leaves that game's
metadata unknown. An invalid or conflicting sidecar rejects that file and
records the error; other files continue. The importer never silently drops
bad metadata and imports the same file as if it had no metadata.

Do not enter today's leaderboard rating as pre-match ELO or copy ELO from a
filename. A bare metadata label also cannot promote a raw Custom replay into
ladder evidence. The existing build-scoped Relic reference and identity
requirements still apply. This importer solves local replay ingestion;
obtaining verified external ratings/results remains a separate requirement.

## Duplicate and error handling

- The same file supplied through overlapping paths is discovered once.
- Plain and gzip copies of the same replay share the reader's decompressed
  replay identity and are counted once.
- Separate recordings with the same match ID count once only when their
  normalized player/event/quality evidence agrees. Conflicting recordings
  are reported as errors; the first accepted recording is retained.
- A broken replay or a parser timeout affects only that file. Inputs over
  128 MiB are rejected; the Rust reader also bounds decompression.
- Ctrl+C preserves completed datasets and writes a partial summary/reports.
  Start a new batch folder when importing again.

Exit codes: `0` completed without file errors (unknown metadata and games
outside scope are allowed), `2` completed with per-file errors, `1` invalid
setup/input, `130` interrupted. The manifest and summary distinguish these
conditions. No network fallback or access-control bypass is attempted.

## Validation

The Python tests cover missing and ID-matched metadata, wrong metadata,
duplicates and conflicting same-match recordings, broken-file continuation,
scope separation, filenames and gzip extensions, folder limits, preserved
output folders, interruption and subprocess input/timeout handling.

GitHub validation additionally runs the real pinned Rust reader on an upstream
binary replay fixture through this batch CLI. It imports plain and gzip
copies from a folder, requires exactly one dataset plus a duplicate receipt,
and verifies that missing ELO/results remain unknown with no eligible
candidates. Neither the fixture nor synthetic tests enlarge the research
cohort.
