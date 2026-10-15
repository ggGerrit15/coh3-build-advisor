"""Import local .rec files/folders offline, preserving unknown ratings and results."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from import_replay import ROOT, DEFAULT_READER, normalize, read_replay
from replay_cohort import target_players, write_json
from report_replay_cohort import analyze, markdown as cohort_markdown
from export_replay_candidates import build_export, markdown as candidate_markdown, load_collection


def replay_file(path):
    return path.is_file() and path.name.lower().endswith((".rec", ".rec.gz"))


def discover(inputs, recursive=False, max_files=200):
    if max_files < 1:
        raise ValueError("Maximum file count must be positive")
    files = set()
    for path in inputs:
        if path.is_dir():
            candidates = path.rglob("*") if recursive else path.iterdir()
            files.update(p.resolve() for p in candidates if replay_file(p))
        elif replay_file(path):
            files.add(path.resolve())
        else:
            raise ValueError(f"Not a replay file or folder: {path}")
        if len(files) > max_files:
            raise ValueError(f"More than {max_files} replay files; split the batch or increase --max-files")
    if not files:
        raise ValueError("No .rec or .rec.gz files found")
    return sorted(files)


def identity(dataset):
    # Retain full player/action/quality evidence. Do not silently accept conflicting recordings.
    return json.dumps({k: dataset[k] for k in ("match", "players", "parser", "match_metadata", "metadata_source")}, sort_keys=True)


def summary(manifest, datasets):
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
    scope = manifest["scope"]
    lines = ["# Local replay import", "", "Offline import. Ratings and results are unknown unless supplied in ID-matched metadata.", "",
        f"Analysis scope: {scope['faction']} / {scope['battlegroup']} / {scope['mode']} / patch {scope['patch']}.", "",
        "Files from other scopes are retained and listed below, but do not enter this scope's comparison reports.", "",
        "[First five commands](report-first5.md) · [First eight commands](report.md) · [Verified candidates](candidates.md)", "",
        "| File | Status | Match | Detail |", "| --- | --- | --- | --- |"]
    for record in manifest["records"]:
        detail = record.get("error") or record.get("duplicate_of") or record.get("dataset") or ""
        lines.append(f"| {escape(record['local_file'])} | {record['status']} | {record.get('match_id') or 'unknown'} | {escape(detail)} |")
    lines += ["", "## Imported players", "",
        "Issued commands only; default starting units are absent. Statistical eligibility does not guarantee a usable opener window; the comparison reports apply that additional check.", "",
        "| Match | Player | Faction / battlegroup | Pre-match ELO | Result | Ladder-statistics exclusions | First usable orders |",
        "| --- | --- | --- | --- | --- | --- | --- |"]
    for dataset in datasets:
        for player in dataset["players"]:
            exclusions = ", ".join(k for k, v in player["quality_checks"].items() if not v) or "none"
            orders = " → ".join(escape(a["name"]) for a in player["build_sequence"][:8])
            lines.append(f"| {dataset['match'].get('match_id') or 'unknown'} | {escape(player['name'])} | "
                f"{player['faction']} / {escape(player['battlegroup_advisor_name'] or 'unknown')} | "
                f"{player['rating_before'] if player['rating_before'] is not None else 'unknown'} | "
                f"{player['result'] or 'unknown'} | {exclusions} | {orders} |")
    lines += ["", "Unknown ELO/results are never inferred from filenames, current ratings or the raw Custom/Automatch label. "
        "Exact-version, human-player, ladder-membership and opener checks remain in force. "
        "Candidates are observed-only; the public advisor is not changed.", ""]
    return "\n".join(lines)


def import_batch(args):
    files = discover(args.inputs, args.recursive, args.max_files)
    if not args.reader.is_file():
        raise ValueError("Replay reader missing. Build it first: cargo +1.99.0 build --locked --release --manifest-path tools/replay-reader/Cargo.toml")
    if args.metadata_dir is not None and not args.metadata_dir.is_dir():
        raise ValueError("Metadata directory does not exist")
    profiles = json.loads(args.advisor_data.read_text(encoding="utf-8"))["profiles"]
    scope = {k: getattr(args, k) for k in ("patch", "mode", "faction", "battlegroup")}
    if not any(p["faction"] == args.faction and p["mode"] == args.mode and p["battlegroup"] == args.battlegroup for p in profiles):
        raise ValueError("No advisor profile matches the requested faction/mode/battlegroup")
    output = args.output_dir.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Output folder must be new or empty; existing imports are not overwritten")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"schema_version": "coh3.replay-collection.v1", "import_source": "local_files",
        "collected_at": datetime.now(timezone.utc).isoformat(), "scope": scope,
        "target": len(files), "target_unit": "local_input_files", "target_reached": False,
        "attempted_downloads": 0, "pages": [], "records": [], "collected_players": 0,
        "sampling": "User-supplied local recordings; selection and population coverage unknown",
        "stopped_reason": "importing", "import_counts": {"files": len(files), "imported": 0,
            "outside_scope": 0, "duplicates": 0, "errors": 0}}
    datasets, seen_hashes, seen_matches = [], {}, {}
    interrupted = False
    for path in files:
        record = {"local_file": path.name, "status": "pending", "source_url": None}
        manifest["records"].append(record)
        try:
            reader = read_replay(path, args.reader)
            mid = reader["match"].get("match_id")
            record["match_id"] = mid
            metadata = None
            if args.metadata_dir is not None and mid is not None:
                metadata_path = args.metadata_dir / f"match-{mid}.json"
                if metadata_path.exists():
                    data = metadata_path.read_bytes()
                    metadata = json.loads(data)
                    record["metadata_file"] = metadata_path.name
                    record["metadata_sha256"] = hashlib.sha256(data).hexdigest()
            dataset = normalize(reader, profiles, metadata)
            digest = dataset["replay_sha256"]
            record.update(match_id=mid, replay_sha256=digest, metadata_supplied=metadata is not None)
            signature = identity(dataset)
            if mid is not None and mid in seen_matches:
                previous_signature, previous = seen_matches[mid]
                if signature != previous_signature:
                    raise ValueError("Conflicting recordings or metadata for the same match; not counted twice")
                record.update(status="duplicate", duplicate_of=previous)
            elif digest in seen_hashes:
                record.update(status="duplicate", duplicate_of=seen_hashes[digest])
            else:
                # Use a hash of the reader digest as a safe, fixed filename component.
                token = hashlib.sha256(digest.encode()).hexdigest()[:16]
                name = f"datasets/match-{mid or 'unknown'}-{token}.json"
                write_json(output / name, dataset)
                if metadata is not None:
                    write_json(output / "metadata" / f"match-{mid}.json", metadata)
                players = target_players(dataset, scope)
                record.update(status="collected" if players else "outside_scope", dataset=name,
                    profile_ids=[p["profile_id"] for p in players],
                    eligible_players=sum(p["eligible_for_ranked_statistics"] for p in players))
                manifest["collected_players"] += len(players)
                manifest["import_counts"]["imported"] += 1
                manifest["import_counts"]["outside_scope"] += not bool(players)
                datasets.append(dataset)
                seen_hashes[digest] = name
                if mid is not None:
                    seen_matches[mid] = (signature, name)
            manifest["import_counts"]["duplicates"] += record["status"] == "duplicate"
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
            record.update(status="import_error", error=str(detail or error)[:1000])
            manifest["import_counts"]["errors"] += 1
        except KeyboardInterrupt:
            record.update(status="interrupted")
            interrupted = True
        finally:
            write_json(output / "manifest.json", manifest)
        if interrupted:
            break
    manifest["target_reached"] = not interrupted and manifest["import_counts"]["errors"] == 0
    manifest["stopped_reason"] = "interrupted" if interrupted else "completed_with_errors" if manifest["import_counts"]["errors"] else "local_import_complete"
    write_json(output / "manifest.json", manifest)
    (output / "summary.md").write_text(summary(manifest, datasets), encoding="utf-8")
    for length, stem in ((5, "report-first5"), (8, "report")):
        report = analyze(datasets, scope, length)
        report["collection"] = {k: manifest[k] for k in ("import_source", "import_counts", "collected_at", "target", "target_unit", "target_reached", "attempted_downloads", "stopped_reason", "sampling")}
        write_json(output / f"{stem}.json", report)
        (output / f"{stem}.md").write_text(cohort_markdown(report, manifest), encoding="utf-8")
    selected, _, provenance = load_collection(output)
    export = build_export(selected, scope)
    export["provenance"] = provenance
    write_json(output / "candidates.json", export)
    (output / "candidates.md").write_text(candidate_markdown(export), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="One or more replay files or folders")
    parser.add_argument("--recursive", action="store_true", help="Also search subfolders")
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--patch", required=True, help="Exact patch for comparison reports; other patches are retained separately")
    parser.add_argument("--faction", choices=("Wehrmacht", "DAK", "USF", "British"), default="Wehrmacht")
    parser.add_argument("--mode", choices=("1v1", "2v2", "3v3", "4v4"), default="1v1")
    parser.add_argument("--battlegroup", default="Mechanized")
    parser.add_argument("--metadata-dir", type=Path, help="Optional canonical match-ID metadata sidecars")
    parser.add_argument("--reader", type=Path, default=DEFAULT_READER)
    parser.add_argument("--advisor-data", type=Path, default=ROOT / "coh3_build_advisor_data.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "work/replays" / ("local-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")))
    args = parser.parse_args()
    try:
        manifest = import_batch(args)
        print(json.dumps({"output": str(args.output_dir.resolve()), "counts": manifest["import_counts"],
                          "scope_players": manifest["collected_players"], "status": manifest["stopped_reason"]}))
        if manifest["stopped_reason"] == "interrupted":
            return 130
        return 2 if manifest["import_counts"]["errors"] else 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Local replay import failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
