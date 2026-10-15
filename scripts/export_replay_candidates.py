"""Export observed opener candidates and real continuations for gameplay review."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from replay_cohort import write_json
from report_replay_cohort import analyze


def sequence_key(actions):
    return tuple((a["kind"], a["pbgid"]) for a in actions)


def sequence(actions):
    return [{k: a[k].strip() if k == "name" else a[k] for k in ("kind", "pbgid", "name")} for a in actions]


def references(rows):
    return [{"match_id": r["match_id"], "profile_id": r["profile_id"], "source_url": r["source_url"]} for r in rows]


def support(rows, population):
    """Both frequencies are descriptive; equal-player weighting is not a bias correction."""
    counts = Counter(r["profile_id"] for r in rows)
    totals = Counter(r["profile_id"] for r in population)
    contributions = [{"profile_id": pid, "games": n} for pid, n in sorted(counts.items(), key=lambda p: (-p[1], p[0]))]
    largest = contributions[0]
    remaining_games = len(rows) - largest["games"]
    remaining_population = len(population) - totals[largest["profile_id"]]
    return {"games": len(rows), "unique_players": len(counts), "population_games": len(population),
            "population_unique_players": len(totals), "game_frequency": len(rows) / len(population),
            "equal_player_frequency": sum(counts[pid] / n for pid, n in totals.items()) / len(totals),
            "player_contributions": contributions, "largest_player_share": largest["games"] / len(rows),
            "without_largest_contributor": {"profile_id": largest["profile_id"], "games": remaining_games,
                "unique_players": len(counts) - 1, "population_games": remaining_population,
                "game_frequency": remaining_games / remaining_population if remaining_population else None}}


def build_export(datasets, scope, core_length=5, followup_length=8, max_seconds=600):
    if not 1 <= core_length < followup_length <= 30:
        raise ValueError("Require 1 <= core length < followup length <= 30")
    core = analyze(datasets, scope, core_length, max_seconds)
    extended = analyze(datasets, scope, followup_length, max_seconds)
    valid = [r for r in core["matches"] if r["eligible_for_ranked_statistics"] and not r["opener_exclusion_reasons"]]
    extended_by_id = {(r["match_id"], r["profile_id"]): r for r in extended["matches"]}
    strata = defaultdict(list)
    for row in valid:
        strata[(tuple(row["opponent_factions"]), row["rating_band"])].append(row)
    populations, candidates = [], []
    for (opponents, band), population in sorted(strata.items()):
        buckets = defaultdict(list)
        for row in population:
            buckets[sequence_key(row["opener"])].append(row)
        populations.append({"opponent_factions": list(opponents), "rating_band": band,
                            "games": len(population), "unique_players": len({r["profile_id"] for r in population})})
        ordered = sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0]))
        for key, rows in ordered:
            candidate_key = [scope, opponents, band, key]
            candidate_id = hashlib.sha256(json.dumps(candidate_key, sort_keys=True).encode()).hexdigest()[:16]
            followups, missing = defaultdict(list), []
            for row in rows:
                full = extended_by_id[(row["match_id"], row["profile_id"])]
                if sequence_key(full["opener"][:core_length]) != key:
                    raise ValueError("Continuation does not match the same match/player core")
                if full["eligible_for_ranked_statistics"] and not full["opener_exclusion_reasons"]:
                    followups[sequence_key(full["opener"])].append(full)
                else:
                    missing.append(dict(references([full])[0], reasons=full["opener_exclusion_reasons"] + full["ranked_exclusion_reasons"]))
            usable = [row for group in followups.values() for row in group]
            branches = []
            for _, branch_rows in sorted(followups.items(), key=lambda item: (-len(item[1]), item[0])):
                branches.append({"sequence": sequence(branch_rows[0]["opener"]),
                                 "additional_commands": sequence(branch_rows[0]["opener"][core_length:]),
                                 "support": support(branch_rows, usable), "match_players": references(branch_rows)})
            counts = support(rows, population)
            flags = ["gameplay_review_pending", "available_replay_selection"]
            if counts["games"] < 30:
                flags.append("sparse_exact_prefix")
            if counts["unique_players"] < 2:
                flags.append("single_player_only")
            if counts["games"] > counts["unique_players"]:
                flags.append("repeated_player_dependence")
            if missing:
                flags.append("incomplete_or_uncertain_followups")
            candidates.append({"candidate_id": candidate_id, "opponent_factions": list(opponents),
                "rating_band": band, "map_scope": "all_maps_in_collected_sample", "sequence": sequence(rows[0]["opener"]),
                "support": counts, "recommendation_status": "observed_only", "evidence_flags": flags,
                "match_players": references(rows), "usable_followup_games": len(usable),
                "followup_denominator": "Only the same core's eligible complete followup windows",
                "followups": branches, "excluded_followups": missing})
    return {"schema_version": "coh3.replay-build-candidates.v1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope, "core_length": core_length, "followup_length": followup_length, "max_opener_seconds": max_seconds,
            "recommendation_status": "observed_only", "frontend_integration": False,
            "starting_units": None, "timing_semantics": core["timing_semantics"],
            "core_counts": core["counts"], "followup_counts": extended["counts"],
            "ranked_exclusion_counts": core["ranked_exclusion_counts"],
            "core_exclusion_counts": core["opener_exclusion_counts"],
            "followup_exclusion_counts": extended["opener_exclusion_counts"],
            "populations": populations, "candidates": candidates,
            "limitations": ["Observed issued commands; starting units and unit completion are not inferred.",
                "Each continuation is an entire observed sequence from the same match/player; no synthetic positional majority.",
                "Opponent factions, exact core order, player rating bands and collection scope remain separate.",
                "Equal-player frequency averages each eligible player's within-stratum frequency, including zero uses; it is a sensitivity check, not an adjusted win rate.",
                "Removing the largest contributor excludes that player's games from both numerator and denominator; ties use the lowest profile ID.",
                "Continuation frequencies condition on reaching a complete usable window; excluded windows remain visible.",
                "Frequency and repeated-player sensitivity do not establish strength, tactical triggers or a best build.",
                "Gameplay review and a larger, more diverse sample are required before recommendations change."]}


def load_collection(folder):
    root = folder.resolve()
    manifest_path = root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    datasets, files = [], []
    for name in sorted({r["dataset"] for r in manifest["records"] if r["status"] == "collected"}):
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Dataset path leaves collection directory")
        data = path.read_bytes()
        datasets.append(json.loads(data))
        files.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
    provenance = {"manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(), "datasets": files,
                  "collected_at": manifest["collected_at"], "discovery": manifest.get("discovery"),
                  "sampling": manifest["sampling"]}
    return datasets, manifest["scope"], provenance


def markdown(export):
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
    def chain(actions):
        return " → ".join(escape(a["name"]) for a in actions)
    counts, scope = export["core_counts"], export["scope"]
    lines = ["# Observed opener candidates for review", "",
        f"Scope: {scope['faction']} / {scope['battlegroup']} / {scope['mode']} / patch {scope['patch']}.", "",
        f"{counts['matches']} matches, {counts['unique_players']} target players; "
        f"{counts['ranked_eligible_complete_openers']} eligible first-{export['core_length']} windows and "
        f"{export['followup_counts']['ranked_eligible_complete_openers']} eligible first-{export['followup_length']} windows.", "",
        "Status: **observed only**. These are issued commands, with starting units absent. No recommendation or frontend update is made.", "",
        "Game frequency uses all eligible core windows in the same opponent/rating stratum. Equal-player frequency gives every eligible player in that stratum equal weight, including players who never use that sequence. It is descriptive, not a win rate.", "",
        "| Opponent | ELO band | Games / eligible windows | Players using / eligible players | Game frequency | Equal-player frequency | Largest player's share | Ordered core |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for candidate in export["candidates"]:
        s = candidate["support"]
        lines.append(f"| {', '.join(candidate['opponent_factions'])} | {candidate['rating_band']} | "
                     f"{s['games']} / {s['population_games']} | {s['unique_players']} / {s['population_unique_players']} | "
                     f"{s['game_frequency']:.1%} | {s['equal_player_frequency']:.1%} | {s['largest_player_share']:.1%} | {chain(candidate['sequence'])} |")
    if not export["candidates"]:
        lines.append("| — | — | 0 | 0 | — | — | — | No eligible candidates |")
    lines += ["", "## Actual continuations and player sensitivity", "",
        "Each branch below continues that exact core in the same match/player. Counts use only usable longer windows; exclusions are listed separately. The JSON retains every source match and each player's contribution.", ""]
    for candidate in export["candidates"]:
        s = candidate["support"]
        removed = s["without_largest_contributor"]
        lines += [f"### {', '.join(candidate['opponent_factions'])} / {candidate['rating_band']} / `{candidate['candidate_id']}`", "",
            chain(candidate["sequence"]), "",
            f"Support — games: {s['games']}; players: {s['unique_players']}. After removing the largest contributor "
            f"({removed['profile_id']}), remaining uses: {removed['games']}; players: {removed['unique_players']}; "
            f"eligible population windows: {removed['population_games']}.", "",
            f"Usable continuations: {candidate['usable_followup_games']} / {s['games']} core windows.", "",
            "| Games | Players | Next issued commands |", "| ---: | ---: | --- |"]
        for branch in candidate["followups"]:
            lines.append(f"| {branch['support']['games']} | {branch['support']['unique_players']} | {chain(branch['additional_commands'])} |")
        if not candidate["followups"]:
            lines.append("| 0 | 0 | No usable continuation |")
        for row in candidate["excluded_followups"]:
            lines += ["", f"Excluded longer window: match {row['match_id']}, player {row['profile_id']}: " + ", ".join(row["reasons"]) + "."]
        lines += ["", "Review flags: " + ", ".join(candidate["evidence_flags"]) + ".", ""]
    lines += ["## Limits", ""] + ["- " + item for item in export["limitations"]] + [""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-dir", type=Path, required=True)
    parser.add_argument("--core-length", type=int, default=5)
    parser.add_argument("--followup-length", type=int, default=8)
    parser.add_argument("--max-opener-seconds", type=float, default=600)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    datasets, scope, provenance = load_collection(args.collection_dir)
    export = build_export(datasets, scope, args.core_length, args.followup_length, args.max_opener_seconds)
    export["provenance"] = provenance
    write_json(args.output_json, export)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(markdown(export), encoding="utf-8")
    print(json.dumps({"candidates": len(export["candidates"]), "core_counts": export["core_counts"], "followup_counts": export["followup_counts"]}))


if __name__ == "__main__":
    main()
