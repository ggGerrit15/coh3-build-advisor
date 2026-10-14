"""Import one replay as reviewable evidence without changing advisor profiles.

Time values describe issued commands, not production completion. Match metadata
is optional and must be matched by match ID and player profile ID.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD_KINDS = {"construct_building", "train_unit", "research_upgrade"}
ALL_KINDS = BUILD_KINDS | {"select_battlegroup", "select_battlegroup_ability", "use_battlegroup_ability", "ai_takeover"}


def bg_key(name: str) -> str:
    name = re.sub(r"\s+battlegroup$", "", name.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", name.lower())


def integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"Invalid {label}: expected integer >= {minimum}")
    return value


def normalize(reader: dict, profiles: list[dict], metadata: dict | None = None,
              source_url: str | None = None) -> dict:
    if not isinstance(reader, dict) or reader.get("schema_version") != "coh3.replay-reader.v1":
        raise ValueError("Unsupported replay reader schema")
    match = dict(reader["match"])
    raw_players = reader["players"]
    if not raw_players:
        raise ValueError("Replay has no players")
    ids = [p["profile_id"] for p in raw_players if p.get("profile_id") is not None]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate replay profile IDs")
    sizes = list(Counter(integer(p["team"], "team") for p in raw_players).values())
    mode = f"{sizes[0]}v{sizes[0]}" if len(sizes) == 2 and sizes[0] == sizes[1] and sizes[0] <= 4 else None
    match["mode"] = mode
    if match.get("match_id") is not None:
        integer(match["match_id"], "match ID", 1)
    metadata_players = {}
    if metadata is not None:
        if not isinstance(metadata, dict) or metadata.get("schema_version") != "coh3.match-metadata.v1":
            raise ValueError("Unsupported match metadata schema")
        if match.get("match_id") is None or metadata.get("match_id") != match["match_id"]:
            raise ValueError("Metadata match ID does not match replay")
        for field in ("patch", "mode"):
            if metadata.get(field) is not None and metadata[field] != match.get(field):
                raise ValueError(f"Metadata {field} does not match replay")
        for player in metadata.get("players", []):
            pid = integer(player.get("profile_id"), "metadata profile ID", 1)
            if pid in metadata_players or pid not in ids:
                raise ValueError("Duplicate or unmatched metadata profile ID")
            metadata_players[pid] = player
    players = []
    for player in raw_players:
        faction = player["faction"]
        if faction not in {"USF", "British", "Wehrmacht", "DAK"}:
            raise ValueError(f"Unknown faction: {faction}")
        data = metadata_players.get(player.get("profile_id"), {})
        if data.get("faction") is not None and data["faction"] != faction:
            raise ValueError("Metadata faction does not match replay player")
        result, rating = data.get("result"), data.get("rating_before")
        if result not in (None, "win", "loss", "draw"):
            raise ValueError("Unknown match result")
        if rating is not None and (isinstance(rating, bool) or not isinstance(rating, (int, float)) or not math.isfinite(rating) or rating < 0):
            raise ValueError("Invalid pre-match rating")
        raw_bg = (player.get("battlegroup") or {}).get("name")
        names = {p["battlegroup"] for p in profiles if p["faction"] == faction
                 and raw_bg and bg_key(p["battlegroup"]) == bg_key(raw_bg)}
        bg_name = next(iter(names)) if len(names) == 1 else None
        has_profile = any(p["faction"] == faction and p["mode"] == mode
                          and p["battlegroup"] == bg_name for p in profiles)
        profile_key = f"{faction}|{mode}|{bg_name}" if has_profile else None
        actions, previous = [], (-1, -1)
        for event_index, action in enumerate(player["actions"]):
            tick = integer(action["tick"], "action tick")
            index = integer(action["command_index"], "command index")
            if (tick, index) < previous:
                raise ValueError("Actions are not in chronological order")
            previous = (tick, index)
            if action.get("kind") not in ALL_KINDS:
                raise ValueError("Unknown action kind")
            integer(action["pbgid"], "blueprint ID")
            for flag in ("cancelled", "suspect", "name_resolved"):
                if not isinstance(action.get(flag), bool):
                    raise ValueError(f"Invalid action flag: {flag}")
            item = dict(action)
            item.update(event_index=event_index, seconds=tick / 8,
                        time_label=f"{tick // 480}:{tick // 8 % 60:02d}")
            reasons = [label for flag, label in (("cancelled", "cancelled"), ("suspect", "suspect_building")) if item[flag]]
            if not item["name_resolved"] or not item.get("name"):
                reasons.append("unresolved_name")
            item["excluded_reasons"] = reasons
            actions.append(item)
        sequence = [a for a in actions if a["kind"] in BUILD_KINDS and not a["excluded_reasons"]]
        unlocks = [a for a in actions if a["kind"] == "select_battlegroup_ability" and not a["excluded_reasons"]]
        checks = {
            "supported_mode": mode is not None,
            "advisor_profile_mapped": profile_key is not None,
            "human_player": player.get("human") is True,
            "all_human_players": all(p.get("human") is True for p in raw_players),
            "no_ai_takeover": player.get("ai_takeover_at_tick") is None,
            "no_match_ai_takeover": all(p.get("ai_takeover_at_tick") is None for p in raw_players),
            "production_commands_available": bool(sequence),
            "result_available": result in ("win", "loss"),
            "pre_match_rating_available": rating is not None,
            "exact_patch_data": reader["parser"].get("exact_game_data_available") is True,
            "ranked_game": match.get("game_type") == "Automatch",
            "unmodded": match.get("mod_uuid") == "00000000-0000-0000-0000-000000000000",
            "names_resolved": all("unresolved_name" not in a["excluded_reasons"] for a in actions),
        }
        output = {k: v for k, v in player.items() if k != "actions"}
        output.update(battlegroup_advisor_name=bg_name, profile_key=profile_key,
                      opponent_factions=sorted({p["faction"] for p in raw_players if p["team"] != player["team"]}),
                      result=result, rating_before=rating, displayed_rating=data.get("displayed_rating"),
                      starting_units=None, actions=actions, build_sequence=sequence,
                      battlegroup_unlocks=unlocks, quality_checks=checks,
                      eligible_for_ranked_statistics=all(checks.values()))
        players.append(output)
    return {"schema_version": "coh3.replay-dataset.v1",
            "imported_at": datetime.now(timezone.utc).isoformat(), "source_url": source_url,
            "metadata_source": metadata.get("source") if metadata else None,
            "parser": reader["parser"], "replay_sha256": reader["replay_sha256"],
            "timing_semantics": "command_issued; not production completion or arrival",
            "match": match, "players": players}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--reader", type=Path, default=ROOT / "tools/replay-reader/target/release/coh3-replay-reader")
    parser.add_argument("--advisor-data", type=Path, default=ROOT / "coh3_build_advisor_data.json")
    parser.add_argument("--metadata", type=Path, help="Optional coh3.match-metadata.v1 JSON")
    parser.add_argument("--source-url")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        process = subprocess.run([str(args.reader.resolve()), str(args.replay.resolve())],
                                 check=True, capture_output=True, text=True, timeout=120)
        profiles = json.loads(args.advisor_data.read_text(encoding="utf-8"))["profiles"]
        metadata = json.loads(args.metadata.read_text(encoding="utf-8")) if args.metadata else None
        dataset = normalize(json.loads(process.stdout), profiles, metadata, args.source_url)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        temporary.write_text(json.dumps(dataset, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(args.output)
        print(json.dumps({"output": str(args.output), "match_id": dataset["match"]["match_id"],
                          "players": len(dataset["players"]),
                          "build_actions": sum(len(p["build_sequence"]) for p in dataset["players"])}))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(f"Replay import failed: {detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
