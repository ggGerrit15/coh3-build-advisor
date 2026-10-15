"""Versioned SQLite replay research store; reviewed observations retain provenance."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import sys

from import_replay import ROOT, normalize, integer
from report_replay_cohort import analyze
from replay_match_type import relic_history_source

APPLICATION_ID = 1129269299
SCHEMA_VERSION = 1


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def connect(path, create=False):
    path = Path(path).resolve()
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    else:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if create and app_id == 0 and version == 0 and not tables:
            connection.executescript((ROOT / "data/replays/schema.sql").read_text())
        elif app_id != APPLICATION_ID or version != SCHEMA_VERSION:
            raise ValueError("Not a supported CoH3 replay database; no migration was attempted")
        return connection
    except BaseException:
        connection.close()
        raise


def recheck(dataset):
    if dataset.get("schema_version") != "coh3.replay-dataset.v1":
        raise ValueError("Expected a normalized replay dataset")
    integer(dataset["match"].get("match_id"), "database match ID", 1)
    for player in dataset["players"]:
        integer(player.get("profile_id"), "database profile ID", 1)
        for key in ("rating_before_unverified", "displayed_rating"):
            value = player.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                raise ValueError(f"Invalid {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", dataset.get("replay_sha256", "")):
        raise ValueError("Invalid replay SHA-256")
    reader = dict(schema_version="coh3.replay-reader.v1", match=dataset["match"], players=dataset["players"],
                  parser=dataset["parser"], replay_sha256=dataset["replay_sha256"])
    has_metadata = dataset.get("metadata_source") is not None or dataset.get("match_metadata") is not None
    has_metadata |= any(any(p.get(k) is not None for k in ("result", "rating_before", "displayed_rating", "rating_before_unverified")) for p in dataset["players"])
    metadata = None
    if has_metadata:
        metadata = {"schema_version": "coh3.match-metadata.v1", "match_id": dataset["match"]["match_id"],
                    "patch": dataset["match"].get("patch"), "mode": dataset["match"].get("mode"),
                    "source": dataset.get("metadata_source"), "source_record": dataset.get("match_metadata"),
                    "players": [{k: p.get(k) for k in ("profile_id", "faction", "result", "rating_before", "displayed_rating", "rating_before_unverified")} for p in dataset["players"]]}
        marker = (dataset["match"].get("match_type_resolution") or {}).get("ladder_reference")
        if marker is not None:
            metadata["classification_reference"] = marker
    profiles = json.loads((ROOT / "coh3_build_advisor_data.json").read_text())["profiles"]
    checked = normalize(reader, profiles, metadata, dataset.get("source_url"))
    outcomes = [p["result"] for p in checked["players"]]
    if checked["match"].get("mode") == "1v1" and all(v is not None for v in outcomes):
        if sorted(outcomes) not in (["loss", "win"], ["draw", "draw"]):
            raise ValueError("Inconsistent pair of 1v1 outcomes")
    checked_by_id = {p["profile_id"]: p for p in checked["players"]}
    for original in dataset["players"]:
        actual = checked_by_id[original["profile_id"]]
        for field in ("build_sequence", "battlegroup_unlocks"):
            signature = lambda rows: [(a["event_index"], a["kind"], a["pbgid"], a["tick"]) for a in rows]
            if signature(original[field]) != signature(actual[field]):
                raise ValueError("Stored sequence disagrees with its underlying actions")
        if any(actual["quality_checks"].get(k) != v for k, v in original["quality_checks"].items()):
            raise ValueError("Stored quality checks disagree with revalidated evidence")
        if original["eligible_for_ranked_statistics"] != actual["eligible_for_ranked_statistics"]:
            raise ValueError("Stored ladder eligibility disagrees with revalidated evidence")
    return checked


def core_identity(dataset):
    match = {k: dataset["match"].get(k) for k in ("match_id", "game_build", "patch", "mode", "map", "mod_uuid", "duration_seconds")}
    players = []
    for player in sorted(dataset["players"], key=lambda p: p["profile_id"]):
        fields = {k: player.get(k) for k in ("profile_id", "name", "human", "faction", "team", "battlegroup", "ai_takeover_at_tick")}
        fields["actions"] = [{k: a.get(k) for k in ("tick", "command_index", "kind", "pbgid", "name", "cancelled", "suspect", "suspect_since_tick", "name_resolved")} for a in player["actions"]]
        players.append(fields)
    return digest({"match": match, "players": players})


def evidence_status(dataset, player):
    source = dataset.get("metadata_source") or {}
    resolution = dataset["match"].get("match_type_resolution") or {}
    daily = (re.fullmatch(r"https://storage\.coh3stats\.com/matches/matches-\d+\.json", source.get("url", "")) is not None
             and re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", "")) is not None)
    rating_field_verified = ((daily and source.get("rating_field") == "matchhistorymember.oldrating")
                             or (relic_history_source(source) and source.get("rating_field") == "matchHistoryStats.matchhistorymember.oldrating"))
    rating_verified = (rating_field_verified
                       and resolution.get("kind") == "ladder_automatch" and player["rating_before"] is not None)
    rating_status = "verified_pre_match" if rating_verified else "source_claim" if player["rating_before"] is not None else (
        "unverified" if any(player.get(k) is not None for k in ("displayed_rating", "rating_before_unverified")) else "unknown")
    result_status = "unknown" if player["result"] is None else "matched_daily_source" if daily and source.get("outcome_field") == "matchhistoryreportresults.resulttype" else "observed_source"
    return rating_status, result_status


def opener_checks(dataset):
    values = {p["profile_id"]: {5: False, 8: False} for p in dataset["players"]}
    scopes = {(p["faction"], p["battlegroup_advisor_name"]) for p in dataset["players"] if p["battlegroup_advisor_name"]}
    for faction, bg in scopes:
        scope = dict(faction=faction, battlegroup=bg, patch=dataset["match"].get("patch"), mode=dataset["match"].get("mode"))
        for length in (5, 8):
            report = analyze([dataset], scope, length)
            for row in report["matches"]:
                values[row["profile_id"]][length] = not row["opener_exclusion_reasons"]
    return values


def ingest(connection, inputs, source_key, source_kind, provenance):
    """One atomic batch; inputs are (relative input name, normalized dataset) pairs."""
    if not source_key or source_kind not in ("cohort", "upload", "single_replay"):
        raise ValueError("Supply a source key and supported source kind")
    if not inputs:
        raise ValueError("No normalized replay datasets supplied")
    result = {"inputs": len(inputs), "new_matches": 0, "new_datasets": 0, "new_source_links": 0}
    with connection:
        old_source = connection.execute("SELECT kind, provenance_json FROM sources WHERE source_key=?", (source_key,)).fetchone()
        source_json = canonical(provenance)
        if old_source and tuple(old_source) != (source_kind, source_json):
            raise ValueError("Source key already exists with different provenance")
        connection.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?)", (source_key, source_kind, source_json, datetime.now(timezone.utc).isoformat()))
        for input_name, original in inputs:
            dataset = recheck(original)
            match = dataset["match"]
            mid = match["match_id"]
            core_hash = core_identity(dataset)
            previous = connection.execute("SELECT core_sha256 FROM matches WHERE match_id=?", (mid,)).fetchone()
            if previous and previous[0] != core_hash:
                raise ValueError(f"Conflicting replay commands or match identity for match {mid}")
            if not previous:
                connection.execute("INSERT INTO matches VALUES(?,?,?,?,?,?,?,?)", (mid, match["game_build"], match.get("patch"), match.get("mode"), match["map"], match.get("mod_uuid"), match["duration_seconds"], core_hash))
                result["new_matches"] += 1
                for player in dataset["players"]:
                    pid = player["profile_id"]
                    connection.execute("INSERT INTO match_players VALUES(?,?,?,?,?,?,?,?,?)", (mid, pid, player["name"], player["faction"], player["battlegroup_advisor_name"], player["team"], int(player["human"]), player["ai_takeover_at_tick"], canonical(player["opponent_factions"])))
                    positions = {a["event_index"]: n for n, a in enumerate(player["build_sequence"], 1)}
                    unlocks = {a["event_index"]: n for n, a in enumerate(player["battlegroup_unlocks"], 1)}
                    for action in player["actions"]:
                        index = action["event_index"]
                        connection.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (mid, pid, index, action["tick"], action["command_index"], action["kind"], action["pbgid"], action["name"], int(action["cancelled"]), int(action["suspect"]), int(action["name_resolved"]), canonical(action["excluded_reasons"]), positions.get(index), unlocks.get(index), canonical(action)))
            replay_hash = dataset["replay_sha256"]
            replay = connection.execute("SELECT match_id FROM replays WHERE replay_sha256=?", (replay_hash,)).fetchone()
            if replay and replay[0] != mid:
                raise ValueError("Same replay hash assigned to conflicting matches")
            connection.execute("INSERT OR IGNORE INTO replays VALUES(?,?,?,?,?)", (replay_hash, mid, match.get("game_type"), match.get("recorded_at_local"), canonical(dataset["parser"])))
            stable_payload = {k: v for k, v in original.items() if k != "imported_at"}
            dataset_hash = digest(stable_payload)
            found = connection.execute("SELECT 1 FROM datasets WHERE dataset_sha256=?", (dataset_hash,)).fetchone()
            if not found:
                connection.execute("INSERT INTO datasets VALUES(?,?,?,?,?,?)", (dataset_hash, mid, replay_hash, dataset.get("source_url"), canonical(original), datetime.now(timezone.utc).isoformat()))
                windows = opener_checks(dataset)
                for player in dataset["players"]:
                    pid = player["profile_id"]
                    rating_status, result_status = evidence_status(dataset, player)
                    conflicts = connection.execute("SELECT rating_before, rating_status, result FROM player_evidence WHERE match_id=? AND profile_id=?", (mid, pid)).fetchall()
                    for old in conflicts:
                        if old["rating_status"] == rating_status == "verified_pre_match" and old["rating_before"] != player["rating_before"]:
                            raise ValueError(f"Conflicting verified ratings for match/player {mid}/{pid}")
                        if old["result"] is not None and player["result"] is not None and old["result"] != player["result"]:
                            raise ValueError(f"Conflicting outcomes for match/player {mid}/{pid}")
                    connection.execute("INSERT INTO player_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (dataset_hash, mid, pid, player["rating_before"], player.get("rating_before_unverified"), player.get("displayed_rating"), rating_status, player["result"], result_status, int(player["eligible_for_ranked_statistics"]), int(windows[pid][5]), int(windows[pid][8]), canonical(player["quality_checks"]), canonical(match["match_type_resolution"])))
                result["new_datasets"] += 1
            result["new_source_links"] += connection.execute("INSERT OR IGNORE INTO source_datasets VALUES(?,?,?)", (source_key, dataset_hash, input_name)).rowcount
    return result


def load_inputs(paths):
    result, seen = [], set()
    for path in paths:
        path = Path(path)
        if path.is_dir():
            base = path / "datasets" if (path / "datasets").is_dir() else path
            candidates = sorted(base.glob("*.json"))
        elif path.is_file():
            candidates = [path]
        else:
            raise ValueError(f"Input does not exist: {path}")
        for file in candidates:
            if file.resolve() in seen:
                continue
            seen.add(file.resolve())
            dataset = json.loads(file.read_text(encoding="utf-8"))
            if dataset.get("schema_version") != "coh3.replay-dataset.v1":
                if path.is_file():
                    raise ValueError("Explicit input is not a normalized replay dataset")
                continue
            result.append((file.name, dataset))
    return result


def statistics(connection):
    counts = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in (
        "matches", "match_players", "replays", "datasets", "sources", "actions")}
    counts.update(unique_profiles=connection.execute("SELECT COUNT(DISTINCT profile_id) FROM match_players").fetchone()[0],
        verified_player_ratings=connection.execute("SELECT COUNT(*) FROM v_player_builds WHERE rating_status='verified_pre_match'").fetchone()[0],
        player_ratings_without_verification=connection.execute("SELECT COUNT(*) FROM v_player_builds WHERE rating_status<>'verified_pre_match'").fetchone()[0],
        eligible_ladder_first8=connection.execute("SELECT COUNT(*) FROM v_player_builds WHERE ranked_eligible=1 AND opener8_usable=1 AND rating_status='verified_pre_match'").fetchone()[0])
    return {"schema_version": "coh3.replay-database-summary.v1", "database_schema_version": SCHEMA_VERSION,
            "counts": counts, "coverage": [dict(r) for r in connection.execute("SELECT * FROM v_battlegroup_coverage ORDER BY patch,mode,faction,battlegroup")],
            "source_counts": [dict(r) for r in connection.execute("SELECT s.source_key,s.kind,COUNT(DISTINCT d.match_id) AS matches FROM sources s JOIN source_datasets sd USING(source_key) JOIN datasets d USING(dataset_sha256) GROUP BY s.source_key,s.kind ORDER BY s.source_key")]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "import", "stats"))
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--input", nargs="+", type=Path)
    parser.add_argument("--source-key")
    parser.add_argument("--source-kind", choices=("cohort", "upload", "single_replay"))
    parser.add_argument("--provenance", type=Path, help="Optional immutable source manifest/review JSON; never becomes verified ELO")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    try:
        with closing(connect(args.database, create=args.command != "stats")) as connection:
            if args.command == "import":
                if not args.input:
                    raise ValueError("Import requires --input")
                provenance = json.loads(args.provenance.read_text()) if args.provenance else {}
                imported = ingest(connection, load_inputs(args.input), args.source_key, args.source_kind, provenance)
                print(json.dumps({"import": imported}))
            result = statistics(connection)
            if args.output_json:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
            print(json.dumps(result["counts"]))
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(f"Replay database error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
