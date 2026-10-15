"""Enrich existing replay matches from local, hashed public metadata captures."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

from import_replay import ROOT, normalize
from replay_cohort import daily_index, stats_metadata, relic_history_metadata, write_json
from replay_match_type import relic_history_source
import replay_database as database


def load_captures(manifest_path):
    """No network requests: verify exact capture bytes before indexing records."""
    manifest_path = Path(manifest_path)
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    index, receipts = {}, []
    for capture in manifest["sources"]:
        path = manifest_path.parent / capture["file"]
        data = path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()
        if sha256 != capture["sha256"]:
            raise ValueError("Metadata capture hash mismatch")
        source = {"url": capture["url"], "sha256": sha256}
        if capture.get("captured_at"):
            source["captured_at"] = capture["captured_at"]
        payload = json.loads(data)
        daily = re.fullmatch(r"https://storage\.coh3stats\.com/matches/matches-[0-9]+\.json", source["url"])
        if daily:
            records, kind = daily_index(payload), "daily"
        elif relic_history_source(source):
            if payload.get("result", {}).get("code") != 0:
                raise ValueError("Relic history response was not successful")
            records, kind = daily_index({"matches": payload["matchHistoryStats"]}), "relic_history"
        else:
            raise ValueError("Unsupported metadata capture URL")
        receipts.append(dict(source, kind=kind, file=capture["file"]))
        for mid, raw in records.items():
            index.setdefault(mid, []).append((kind, source, raw))
    return index, {"capture_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(), "sources": receipts}


def enrich(dataset, observations, profiles):
    reader = {"schema_version": "coh3.replay-reader.v1", **{k: dataset[k] for k in ("match", "players", "parser", "replay_sha256")}}
    candidates = []
    for kind, source, raw in observations:
        adapter = stats_metadata if kind == "daily" else relic_history_metadata
        metadata = adapter(raw, reader, source)
        # All available exact sources must agree, even if one is not selected.
        signature = sorted((p["profile_id"], p["faction"], p.get("rating_before"),
                            p.get("rating_before_unverified"), p["result"]) for p in metadata["players"])
        if candidates and signature != candidates[0][3]:
            raise ValueError(f"Conflicting metadata observations for match {dataset['match']['match_id']}")
        candidates.append((kind, source, metadata, signature))
    if not candidates:
        return None
    kind, source, metadata, _ = min(candidates, key=lambda item: (item[0] != "daily", item[1]["url"]))
    result = normalize(reader, profiles, metadata, dataset.get("source_url"))
    if database.core_identity(result) != database.core_identity(dataset):
        raise ValueError("Metadata enrichment changed the replay command core")
    return result, {"match_id": dataset["match"]["match_id"], "selected_kind": kind,
                    "source_url": source["url"], "corroborating_sources": len(candidates),
                    "players": [{k: p.get(k) for k in ("profile_id", "faction", "rating_before", "rating_before_unverified", "result")} for p in result["players"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--captures", required=True, type=Path)
    parser.add_argument("--collection-source", required=True, action="append")
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        if not args.database.is_file():
            raise ValueError("An existing research database is required")
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise ValueError("Use a new or empty output folder")
        index, provenance = load_captures(args.captures)
        provenance["collection_sources"] = args.collection_source
        provenance["purpose"] = "metadata_enrichment"
        profiles = json.loads((ROOT / "coh3_build_advisor_data.json").read_text(encoding="utf-8"))["profiles"]
        with closing(database.connect(args.database)) as connection:
            placeholders = ",".join("?" for _ in args.collection_source)
            found = {r[0] for r in connection.execute(f"SELECT source_key FROM sources WHERE source_key IN ({placeholders})", args.collection_source)}
            if found != set(args.collection_source):
                raise ValueError("Unknown collection source key")
            rows = connection.execute(f"""SELECT DISTINCT b.match_id, b.dataset_sha256, d.payload_json
                FROM v_player_builds b JOIN datasets d USING(dataset_sha256)
                WHERE b.match_id IN (SELECT d2.match_id FROM datasets d2
                    JOIN source_datasets sd USING(dataset_sha256)
                    WHERE sd.source_key IN ({placeholders}))
                ORDER BY b.match_id, b.dataset_sha256""", args.collection_source).fetchall()
        datasets = {}
        for row in rows:
            datasets.setdefault(row["match_id"], json.loads(row["payload_json"]))
        enriched, matched, missing = [], [], []
        for mid, dataset in datasets.items():
            result = enrich(dataset, index.get(mid, []), profiles)
            if result is None:
                missing.append(mid)
            else:
                value, receipt = result
                enriched.append((f"match-{mid}.json", value))
                matched.append(receipt)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, dataset in enriched:
            write_json(args.output_dir / "datasets" / name, dataset)
        with closing(database.connect(args.database, create=True)) as connection:
            imported = database.ingest(connection, enriched, args.source_key, "upload", provenance) if enriched else None
            counts = database.statistics(connection)["counts"]
        report = {"schema_version": "coh3.metadata-enrichment.v1", "target_matches": len(datasets),
                  "matched": len(matched), "missing_match_ids": missing, "database_import": imported,
                  "matches": matched, "database_counts": counts, "provenance": provenance}
        write_json(args.output_dir / "enrichment-report.json", report)
        print(json.dumps({k: report[k] for k in ("target_matches", "matched", "missing_match_ids", "database_import", "database_counts")}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(f"Replay metadata enrichment error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
