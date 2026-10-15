"""Collect a bounded, cached public replay cohort without editing advisor builds."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

from import_replay import ROOT, normalize
from replay_cohort import HttpCache, daily_index, listing, listing_metadata, stats_metadata, target_players, write_json, rating_in_scope, build_preview
from replay_match_type import MODES, RACES

FACTION_FILTER = {"Wehrmacht": "germans", "DAK": "afrika_korps", "USF": "americans", "British": "british_africa"}
MODE_FILTER = {"1v1": "ones", "2v2": "twos", "3v3": "threes", "4v4": "fours"}


def collect(args) -> dict:
    scope = {k: getattr(args, k) for k in ("faction", "battlegroup", "mode", "patch")}
    scope.update({k: getattr(args, k, None) for k in ("min_player_rating", "max_player_rating", "listing_rating")})
    intrinsic_scope = {k: scope[k] for k in ("faction", "battlegroup", "mode", "patch")}
    http = HttpCache(args.output_dir / "cache", args.delay)
    profiles = json.loads(args.advisor_data.read_text())["profiles"]
    manifest = {"schema_version": "coh3.replay-collection.v1", "collected_at": datetime.now(timezone.utc).isoformat(),
                "scope": scope, "target": args.target, "pages": [], "records": [], "stopped_reason": None,
                "sampling": "Newest available matches, no outcome filter; convenience sample, not population coverage"}
    manifest["discovery"] = {"source": args.source, "game_build": args.game_build,
                             "completed_after": getattr(args, "completed_after", None),
                             "completed_before": args.completed_before,
                             "metadata_days": args.metadata_day,
                             "preview_builds": getattr(args, "preview_builds", False),
                             "limits": {k: getattr(args, k, None) for k in ("max_pages", "max_downloads", "max_previews")}}
    manifest["checked_build_previews"] = 0
    index, sources = {}, {}

    def relevant(raw):
        return (MODES.get(raw.get("matchtype_id")) == args.mode or raw.get("matchtype_id") == 0) and any(
            RACES.get(p.get("race_id")) == args.faction for p in raw.get("matchhistoryreportresults", []))

    for path, url in [(p, args.metadata_url) for p in args.metadata_file]:
        data = path.read_bytes()
        source = {"url": url, "local_file": path.name, "sha256": hashlib.sha256(data).hexdigest()}
        for mid, match in daily_index(json.loads(data)).items():
            if not relevant(match):
                continue
            if mid in index and index[mid] != match:
                raise ValueError("Conflicting daily records for the same match")
            index[mid] = match
            sources[mid] = source
    for day in args.metadata_day:
        date = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if date.date() >= datetime.now(timezone.utc).date():
            raise ValueError("Daily metadata must be from a completed UTC day")
        url = f"https://storage.coh3stats.com/matches/matches-{int(date.timestamp())}.json"
        data = http.get(url, 256 * 1024 * 1024)
        source = {"url": url, "sha256": hashlib.sha256(data).hexdigest()}
        for mid, match in daily_index(json.loads(data)).items():
            if not relevant(match):
                continue
            if mid in index and index[mid] != match:
                raise ValueError("Conflicting daily records for the same match")
            index[mid], sources[mid] = match, source

    manifest["metadata_sources"] = sorted({json.dumps(s, sort_keys=True) for s in sources.values()})
    manifest["metadata_sources"] = [json.loads(s) for s in manifest["metadata_sources"]]

    qualified_profiles = None
    if scope["min_player_rating"] is not None or scope["max_player_rating"] is not None:
        if not index:
            raise ValueError("Verified player-rating selection requires daily metadata")
        qualified_profiles = {p["profile_id"] for raw in index.values()
                              if MODES.get(raw.get("matchtype_id")) == args.mode and raw.get("description") == "AUTOMATCH"
                              for p in raw.get("matchhistoryreportresults", [])
                              if RACES.get(p.get("race_id")) == args.faction
                              and rating_in_scope((p.get("matchhistorymember") or {}).get("oldrating"), scope)}
        manifest["candidate_profiles_from_daily_data"] = len(qualified_profiles)
    seen_replays, seen_players, seen_pages = set(), set(), set()
    matched, attempted = 0, 0

    def consume(row):
        nonlocal matched, attempted
        if row["source_url"] in seen_replays:
            return
        seen_replays.add(row["source_url"])
        attempted += 1
        record = {"source_url": row["source_url"], "download_url": row["download_url"], "status": "pending"}
        if row.get("preview_receipt"):
            record.update(row["preview_receipt"])
        manifest["records"].append(record)
        try:
            data = http.get(row["download_url"])
            file = args.output_dir / "raw" / (hashlib.sha256(row["download_url"].encode()).hexdigest() + ".rec")
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            process = subprocess.run([str(args.reader.resolve()), str(file.resolve())], capture_output=True, text=True, timeout=120, check=True)
            reader = json.loads(process.stdout)
            mid = reader["match"]["match_id"]
            if row.get("match_id") is not None and row["match_id"] != mid:
                raise ValueError("Replay match ID does not match requested source ID")
            # Filter replay evidence before attempting the optional metadata join.
            preliminary = normalize(reader, profiles, source_url=row["source_url"])
            if not target_players(preliminary, intrinsic_scope):
                record.update(status="outside_scope", match_id=mid)
                return
            metadata = stats_metadata(index[mid], reader, sources[mid]) if mid in index else listing_metadata(row, reader)
            dataset = normalize(reader, profiles, metadata, row["source_url"])
            players = target_players(dataset, scope)
            if not players:
                record.update(status="outside_player_rating", match_id=mid,
                              target_ratings=[p["rating_before"] for p in target_players(dataset, intrinsic_scope)])
                return
            keys = {(mid, p["profile_id"]) for p in players}
            if keys <= seen_players:
                record.update(status="duplicate_match_player", match_id=mid)
                return
            seen_players.update(keys)
            output = args.output_dir / "datasets" / f"match-{mid}.json"
            write_json(output, dataset)
            if metadata:
                write_json(args.output_dir / "metadata" / f"match-{mid}.json", metadata)
            matched += len(players)
            record.update(status="collected", match_id=mid, dataset=str(output.relative_to(args.output_dir)),
                          profile_ids=[p["profile_id"] for p in players], eligible_players=sum(p["eligible_for_ranked_statistics"] for p in players))
            print(json.dumps({"collected": matched, "match_id": mid, "eligible": record["eligible_players"]}), flush=True)
        except HTTPError as error:
            record.update(status="http_error", http_status=error.code)
            if error.code in (401, 403, 429):
                raise
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
            record.update(status="import_error", error=(error.stderr.strip()[:500] if isinstance(error, subprocess.CalledProcessError) else str(error)))
        finally:
            manifest.update(collected_players=matched, attempted_downloads=attempted, target_reached=matched >= args.target)
            write_json(args.output_dir / "manifest.json", manifest)

    try:
        if args.source == "coh3stats":
            candidates = sorted(index.values(), key=lambda m: (m.get("completiontime", 0), m["id"]), reverse=True)
            missing = 0
            for raw in candidates:
                if MODES.get(raw.get("matchtype_id")) != args.mode or not any(RACES.get(p.get("race_id")) == args.faction for p in raw.get("matchhistoryreportresults", [])):
                    continue
                consume({"match_id": raw["id"], "source_url": f"https://coh3stats.com/matches/{raw['id']}",
                         "download_url": f"https://replays.coh3stats.com/{raw['id']}.rec"})
                missing = missing + 1 if manifest["records"][-1].get("http_status") == 404 else 0
                if missing >= args.max_consecutive_missing:
                    manifest["stopped_reason"] = "consecutive_missing_replays"
                    break
                if matched >= args.target or attempted >= args.max_downloads:
                    break
        else:
            params = {"patch": args.game_build, "mode": MODE_FILTER[args.mode], "faction": FACTION_FILTER[args.faction]}
            if scope["listing_rating"]:
                params["rating"] = scope["listing_rating"]
            url = "https://cohdb.com/matches?" + urlencode(params)
            for _ in range(args.max_pages):
                if not url or url in seen_pages:
                    break
                seen_pages.add(url)
                data = http.get(url, 8 * 1024 * 1024)
                rows, next_url = listing(data.decode("utf-8"))
                manifest["pages"].append({"url": url, "sha256": hashlib.sha256(data).hexdigest(), "rows": len(rows)})
                if not rows:
                    manifest["stopped_reason"] = "empty_listing"
                    break
                for row in rows:
                    completed = row.get("completed_at_utc")
                    if (getattr(args, "completed_after", None) or args.completed_before) and completed is None:
                        manifest["records"].append({"source_url": row["source_url"], "status": "missing_completion_date"})
                        continue
                    if getattr(args, "completed_after", None) and completed[:10] < args.completed_after:
                        manifest["stopped_reason"] = "completed_date_window_end"
                        break
                    if args.completed_before:
                        if completed[:10] >= args.completed_before:
                            continue
                    if row["source_url"] in seen_replays:
                        continue
                    if qualified_profiles is not None and not qualified_profiles.intersection(row["profile_ids"]):
                        seen_replays.add(row["source_url"])
                        manifest["records"].append({"source_url": row["source_url"], "status": "no_metadata_qualified_target_profile",
                                                    "listing_profile_ids": row["profile_ids"]})
                        continue
                    if getattr(args, "preview_builds", False):
                        if manifest["checked_build_previews"] >= args.max_previews:
                            manifest["stopped_reason"] = "preview_limit"
                            break
                        preview_url = row["source_url"] + "/builds"
                        html = http.get(preview_url, 8 * 1024 * 1024)
                        manifest["checked_build_previews"] += 1
                        preview = build_preview(html.decode("utf-8"), row, args.battlegroup, profiles)
                        known_match = index.get(preview["match_id"])
                        if known_match and {p["profile_id"] for p in known_match["matchhistoryreportresults"]} != set(row["profile_ids"]):
                            known_match = None
                        if known_match:
                            target_ids = [p["profile_id"] for p in known_match["matchhistoryreportresults"] if RACES.get(p.get("race_id")) == args.faction]
                            preview = build_preview(html.decode("utf-8"), row, args.battlegroup, profiles, target_ids)
                        receipt = {"source_url": row["source_url"], "preview_url": preview_url,
                                   "preview_sha256": hashlib.sha256(html).hexdigest(), "preview": preview}
                        if not preview["possible_target"]:
                            seen_replays.add(row["source_url"])
                            manifest["records"].append(dict(receipt, status="preview_other_battlegroups"))
                            continue
                        if qualified_profiles is not None and known_match:
                            ratings = [(p.get("matchhistorymember") or {}).get("oldrating") for p in known_match["matchhistoryreportresults"]
                                       if RACES.get(p.get("race_id")) == args.faction]
                            if known_match.get("matchtype_id") == 0 or not any(rating_in_scope(v, scope) for v in ratings):
                                seen_replays.add(row["source_url"])
                                manifest["records"].append(dict(receipt, status="preview_no_verified_target_rating"))
                                continue
                        if preview["match_id"] is not None:
                            row["match_id"] = preview["match_id"]
                        row["preview_receipt"] = {k: v for k, v in receipt.items() if k != "source_url"}
                    row["download_url"] = row["source_url"] + "/file?inflate=true"
                    consume(row)
                    if matched >= args.target or attempted >= args.max_downloads:
                        break
                print(json.dumps({"pages": len(manifest["pages"]), "downloads": attempted, "collected": matched}), flush=True)
                if matched >= args.target or attempted >= args.max_downloads or manifest["stopped_reason"] is not None:
                    break
                url = next_url
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        manifest["stopped_reason"] = f"source_unavailable: {error}"
    except KeyboardInterrupt:
        manifest["stopped_reason"] = "interrupted; cached responses and completed datasets retained"
    manifest.update(collected_players=matched, attempted_downloads=attempted, target_reached=matched >= args.target)
    if manifest["stopped_reason"] is None:
        manifest["stopped_reason"] = "target_reached" if matched >= args.target else "collection_limit_or_end_of_listing"
    write_json(args.output_dir / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("cohdb", "coh3stats"), default="cohdb")
    parser.add_argument("--faction", choices=FACTION_FILTER, default="Wehrmacht")
    parser.add_argument("--battlegroup", default="Mechanized")
    parser.add_argument("--mode", choices=MODE_FILTER, default="1v1")
    parser.add_argument("--patch", required=True)
    parser.add_argument("--game-build", type=int, required=True)
    parser.add_argument("--target", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--max-downloads", type=int, default=200)
    parser.add_argument("--max-consecutive-missing", type=int, default=20)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--min-player-rating", type=int, help="Inclusive verified pre-match ELO minimum for the target player")
    parser.add_argument("--max-player-rating", type=int, help="Exclusive verified pre-match ELO maximum for the target player")
    parser.add_argument("--listing-rating", choices=("any", "min:1400", "min:1600", "min:1800", "avg:1600_1800", "avg:1800_plus", "bal:1600_1800", "bal:1800_plus"),
                        help="Coarse CoHDB discovery filter; final target-player ELO is independently verified")
    parser.add_argument("--completed-before", help="Exclusive YYYY-MM-DD UTC completion-date cutoff")
    parser.add_argument("--completed-after", help="Inclusive YYYY-MM-DD UTC completion-date cutoff")
    parser.add_argument("--preview-builds", action="store_true", help="Skip recognizable other battlegroups using the public build display before downloading")
    parser.add_argument("--max-previews", type=int, default=400)
    parser.add_argument("--metadata-day", action="append", default=[], help="Completed UTC day YYYY-MM-DD")
    parser.add_argument("--metadata-file", type=Path, action="append", default=[])
    parser.add_argument("--metadata-url", help="Provenance URL for supplied daily files")
    parser.add_argument("--reader", type=Path, default=ROOT / "tools/replay-reader/target/release/coh3-replay-reader")
    parser.add_argument("--advisor-data", type=Path, default=ROOT / "coh3_build_advisor_data.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if min(args.target, args.max_pages, args.max_downloads, args.max_previews, args.max_consecutive_missing, args.game_build) < 1:
            raise ValueError("Collection limits and game build must be positive")
        if args.completed_before:
            datetime.strptime(args.completed_before, "%Y-%m-%d")
        if args.completed_after:
            datetime.strptime(args.completed_after, "%Y-%m-%d")
            if args.completed_before and args.completed_after >= args.completed_before:
                raise ValueError("Invalid completion-date window")
        if any(v is not None and v < 0 for v in (args.min_player_rating, args.max_player_rating)) or (
                args.min_player_rating is not None and args.max_player_rating is not None and args.max_player_rating <= args.min_player_rating):
            raise ValueError("Invalid target-player rating window")
        if args.source == "coh3stats" and not (args.metadata_day or args.metadata_file):
            raise ValueError("CoH3Stats replay discovery requires daily metadata")
        manifest = collect(args)
        print(json.dumps({k: manifest[k] for k in ("collected_players", "target_reached", "stopped_reason")}))
        return 0 if manifest["target_reached"] else 2
    except (OSError, ValueError, KeyError, URLError) as error:
        print(f"Collection failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
