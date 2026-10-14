"""Compare complete ordered replay prefixes; keep exploratory and ranked evidence separate."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from replay_cohort import target_players, write_json


def rating_band(value):
    if value is None:
        return "unknown"
    if value < 1000:
        return "under_1000"
    if value >= 1800:
        return "1800_plus"
    low = int(value // 200) * 200
    return f"{low}_{low + 200}"


def wilson(wins, games):
    if not games:
        return None
    z, p = 1.96, wins / games
    denominator = 1 + z * z / games
    center = (p + z * z / (2 * games)) / denominator
    half = z * math.sqrt(p * (1 - p) / games + z * z / (4 * games * games)) / denominator
    return {"lower": center - half, "upper": center + half}


def analyze(datasets, scope, length=8, max_seconds=600):
    if not 1 <= length <= 30 or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("Invalid opener window")
    selected, seen, duplicate_count = [], {}, 0
    for dataset in datasets:
        if dataset.get("schema_version") != "coh3.replay-dataset.v1":
            raise ValueError("Unsupported dataset schema")
        for player in target_players(dataset, scope):
            mid, pid = dataset["match"]["match_id"], player["profile_id"]
            key = (mid, pid)
            # Re-recordings can have different file hashes; same match/player still counts once.
            signature = json.dumps({"sequence": [(a["kind"], a["pbgid"], a["tick"]) for a in player["build_sequence"]],
                                    "result": player["result"], "rating": player["rating_before"],
                                    "opponents": player["opponent_factions"], "checks": player["quality_checks"]}, sort_keys=True)
            if key in seen:
                if seen[key] != signature:
                    raise ValueError(f"Conflicting recordings or metadata for match/player {key}")
                duplicate_count += 1
                continue
            seen[key] = signature
            checks = player["quality_checks"]
            eligible = all(checks.values())
            if player["eligible_for_ranked_statistics"] != eligible:
                raise ValueError("Statistical eligibility disagrees with quality checks")
            sequence = player["build_sequence"][:length]
            reasons = []
            required = ("supported_mode", "advisor_profile_mapped", "human_player", "all_human_players",
                        "no_ai_takeover", "no_match_ai_takeover", "production_commands_available", "exact_patch_data", "unmodded", "names_resolved")
            reasons.extend(k for k in required if not checks[k])
            if len(sequence) < length or sequence[-1]["seconds"] > max_seconds:
                reasons.append("incomplete_opener_window")
            if sequence and any(a["seconds"] <= sequence[-1]["seconds"] and any(
                    r in a["excluded_reasons"] for r in ("suspect_building", "unresolved_name")) for a in player["actions"]):
                reasons.append("uncertain_opener_command")
            selected.append({"match_id": mid, "profile_id": pid, "name": player["name"], "source_url": dataset["source_url"],
                             "map": dataset["match"]["map"], "game_type": dataset["match"]["game_type"],
                             "source_matchtype_id": (dataset.get("match_metadata") or {}).get("matchtype_id"),
                             "source_description": (dataset.get("match_metadata") or {}).get("description"),
                             "match_type_resolution": dataset["match"].get("match_type_resolution"),
                             "opponent_factions": player["opponent_factions"], "result": player["result"],
                             "rating_before": player["rating_before"], "rating_band": rating_band(player["rating_before"]),
                             "eligible_for_ranked_statistics": eligible, "ranked_exclusion_reasons": [k for k, v in checks.items() if not v],
                             "opener_exclusion_reasons": reasons,
                             "opener": [{k: a[k] for k in ("kind", "pbgid", "name", "seconds", "time_label", "tick")} for a in sequence],
                             "bg_unlocks": [{k: a[k] for k in ("name", "seconds", "time_label")} for a in player["battlegroup_unlocks"]]})

    selected.sort(key=lambda r: (r["match_id"], r["profile_id"]))

    def group(records, ranked):
        buckets = defaultdict(list)
        for row in records:
            opener = tuple((a["kind"], a["pbgid"]) for a in row["opener"])
            # Ratings and opponents remain separate even in the exploratory table.
            key = (tuple(row["opponent_factions"]), row["rating_band"], opener)
            buckets[key].append(row)
        result = []
        for (opponents, band, _), rows in buckets.items():
            item = {"opponent_factions": list(opponents), "rating_band": band, "map_scope": "all_maps_in_collected_sample",
                    "games": len(rows), "unique_players": len({r["profile_id"] for r in rows}),
                    "sequence": [{"kind": a["kind"], "pbgid": a["pbgid"], "name": a["name"].strip()} for a in rows[0]["opener"]],
                    "match_players": [{"match_id": r["match_id"], "profile_id": r["profile_id"]} for r in rows]}
            if ranked:
                wins = sum(r["result"] == "win" for r in rows)
                item.update(wins=wins, losses=len(rows) - wins, win_rate=wins / len(rows), wilson_95=wilson(wins, len(rows)),
                            evidence="too_sparse" if len(rows) < 30 else "weak" if len(rows) < 100 else "useful_but_uncertain" if len(rows) < 300 else "descriptive")
            result.append(item)
        # Frequency order only; never select each position independently or rank tiny WRs.
        return sorted(result, key=lambda g: (-g["games"], g["opponent_factions"], g["rating_band"], json.dumps(g["sequence"], sort_keys=True)))

    valid = [r for r in selected if not r["opener_exclusion_reasons"]]
    ranked = [r for r in valid if r["eligible_for_ranked_statistics"]]
    return {"schema_version": "coh3.replay-cohort-report.v1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "statistics_population": "Ladder-rated Automatch, including Quick Match; legacy ranked keys do not identify the Ranked queue.",
            "scope": scope, "prefix_length": length, "max_opener_seconds": max_seconds,
            "timing_semantics": "command_issued; not production completion or arrival",
            "counts": {"matches": len({r["match_id"] for r in selected}), "match_players": len(selected),
                       "unique_players": len({r["profile_id"] for r in selected}), "duplicates_ignored": duplicate_count,
                       "with_result": sum(r["result"] in ("win", "loss") for r in selected),
                       "with_pre_match_rating": sum(r["rating_before"] is not None for r in selected),
                       "usable_complete_openers": len(valid), "ranked_eligible_complete_openers": len(ranked)},
            "ranked_exclusion_counts": dict(Counter(reason for r in selected for reason in r["ranked_exclusion_reasons"])),
            "opener_exclusion_counts": dict(Counter(reason for r in selected for reason in r["opener_exclusion_reasons"])),
            "exploratory_openers": group(valid, False), "ranked_openers": group(ranked, True), "matches": selected,
            "limitations": ["Available-replay convenience sample; collection completeness is not guaranteed.",
                            "Repeated players, opponents and maps can confound outcomes; Wilson intervals do not remove those biases.",
                            "Prefixes require the full window; games ending before it are reported as incomplete rather than silently counted.",
                            "Battlegroup selection may occur after the opener; BG-specific cohort membership is retrospective.",
                            "Exploratory counts are not ranked win-rate evidence. No automatic best-build claim or advisor update."]}


def markdown(report, manifest=None):
    scope, counts = report["scope"], report["counts"]
    lines = ["# Mechanized replay pilot" if scope["battlegroup"] == "Mechanized" else "# Replay cohort pilot", "",
             f"Scope: {scope['faction']} / {scope['battlegroup']} / {scope['mode']} / patch {scope['patch']}. Generated {report['generated_at']}.", "",
             f"Collected **{counts['matches']} matches**, {counts['unique_players']} distinct target players. "
             f"Results: {counts['with_result']}/{counts['match_players']}; verified pre-match ELO: {counts['with_pre_match_rating']}/{counts['match_players']}.", "",
             f"Complete first-{report['prefix_length']} production/build/research prefixes within {report['max_opener_seconds']:g}s: "
             f"**{counts['usable_complete_openers']}**; eligible for rated-ladder comparisons: **{counts['ranked_eligible_complete_openers']}**.", "",
             "Times are issued commands, not production completion. Starting units are not recorded as production commands.", ""]
    if scope.get("min_player_rating") is not None or scope.get("max_player_rating") is not None:
        lines += [f"Verified target-player ELO window: minimum {scope.get('min_player_rating')}, exclusive maximum {scope.get('max_player_rating')}. "
                  f"Coarse discovery filter: {scope.get('listing_rating') or 'none'}.", ""]
    if manifest:
        lines += [f"Collection: target {manifest['target']}, attempted downloads {manifest['attempted_downloads']}, "
                  f"listing pages {len(manifest['pages'])}; stopped: `{manifest['stopped_reason']}`.", ""]
        if manifest.get("discovery"):
            discovery = manifest["discovery"]
            lines += [f"UTC completion-date window: {discovery.get('completed_after') or 'no lower cutoff'} inclusive "
                      f"to {discovery.get('completed_before') or 'no upper cutoff'} exclusive. "
                      f"Public build previews checked: {manifest.get('checked_build_previews', 0)}.", ""]
    lines += ["## Quality exclusions", "", "| Check | Target records failing |", "| --- | ---: |"]
    lines += [f"| {k} | {v} |" for k, v in report["ranked_exclusion_counts"].items()]
    if not report["ranked_exclusion_counts"]:
        lines.append("| None | 0 |")
    lines += ["", "## Observed complete openers — exploratory frequency", "",
              "Each row is one actual ordered prefix. Opponent and target-player rating bands are kept separate. No win rates are calculated for ineligible records.", "",
              "| Opponent | Player ELO band | Games | Distinct players | Ordered sequence |", "| --- | --- | ---: | ---: | --- |"]
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
    for g in report["exploratory_openers"]:
        sequence = " → ".join(escape(a["name"]) for a in g["sequence"])
        lines.append(f"| {', '.join(g['opponent_factions'])} | {g['rating_band']} | {g['games']} | {g['unique_players']} | {sequence} |")
    if not report["exploratory_openers"]:
        lines.append("| — | — | 0 | 0 | No complete verified prefixes available |")
    lines += ["", "## Rated-ladder outcomes", "",
              "These include Quick Match games assigned to Relic's isranked=1 ladders. They do not identify a separate Ranked queue. "
              "Groups below 30 games are too sparse for a best-build claim; repeated players are not independent evidence.", ""]
    if not report["ranked_openers"]:
        lines.append("No eligible rated-ladder comparison is available. Resolve the documented quality exclusions before interpreting outcomes.")
    else:
        lines += ["| Opponent | Player ELO band | Games | W–L | Raw WR | Wilson 95% | Evidence | Ordered sequence |", "| --- | --- | ---: | --- | ---: | --- | --- | --- |"]
        for g in report["ranked_openers"]:
            ci = g["wilson_95"]
            lines.append(f"| {', '.join(g['opponent_factions'])} | {g['rating_band']} | {g['games']} | {g['wins']}–{g['losses']} | {g['win_rate']:.1%} | {ci['lower']:.1%}–{ci['upper']:.1%} | {g['evidence']} | " + " → ".join(escape(a["name"]) for a in g["sequence"]) + " |")
    lines += ["", "## Match evidence", "", "| Match | Target player | Opponent | Pre-match ELO | Result | Replay / metadata / resolved type | First orders with times |", "| --- | --- | --- | ---: | --- | --- | --- |"]
    for r in report["matches"]:
        source = r["source_url"] or ""
        label = f"[{r['match_id']}]({source})" if source.startswith("https://") else str(r["match_id"])
        classification = f"{r['game_type']} / {r['source_description'] or 'unknown'} ({r['source_matchtype_id'] if r['source_matchtype_id'] is not None else 'unknown'})"
        classification += " / " + ((r.get("match_type_resolution") or {}).get("kind") or "unresolved")
        lines.append(f"| {label} | {escape(r['name'])} ({r['profile_id']}) | {', '.join(r['opponent_factions'])} | {r['rating_before'] if r['rating_before'] is not None else 'unknown'} | {r['result'] or 'unknown'} | {escape(classification)} | " + " → ".join(f"{a['time_label']} {escape(a['name'].strip())}" for a in r["opener"]) + " |")
    lines += ["", "## Limitations", ""] + ["- " + item for item in report["limitations"]]
    lines += ["", "Sources: [CoHDB](https://cohdb.com/matches), [CoH3Stats open data](https://coh3stats.com/other/open-data). Exact source URLs and IDs are retained in the JSON evidence.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-dir", type=Path, required=True)
    parser.add_argument("--prefix-length", type=int, default=8)
    parser.add_argument("--max-opener-seconds", type=float, default=600)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.collection_dir / "manifest.json").read_text())
    paths = sorted({r["dataset"] for r in manifest["records"] if r["status"] == "collected"})
    root = args.collection_dir.resolve()
    datasets = []
    for name in paths:
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Dataset path leaves collection directory")
        datasets.append(json.loads(path.read_text()))
    report = analyze(datasets, manifest["scope"], args.prefix_length, args.max_opener_seconds)
    report["collection"] = {k: manifest[k] for k in ("collected_at", "target", "target_reached", "attempted_downloads", "stopped_reason", "sampling")}
    for key in ("discovery", "checked_build_previews", "metadata_sources"):
        if key in manifest:
            report["collection"][key] = manifest[key]
    write_json(args.output_json, report)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(markdown(report, manifest), encoding="utf-8")
    print(json.dumps(report["counts"]))


if __name__ == "__main__":
    main()
