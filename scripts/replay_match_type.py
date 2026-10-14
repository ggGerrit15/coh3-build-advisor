"""Resolve ladder membership separately from cohlib's best-effort AUTO flag."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "data/replays/reference/relic-leaderboards-2026-10-14.json"
SOURCE = REFERENCE.with_name("relic-leaderboards-2026-10-14-source.json")
RACES = {129494: "USF", 203852: "British", 137123: "Wehrmacht", 198437: "DAK"}
MODES = {1: "1v1", 20: "1v1", 2: "2v2", 21: "2v2", 3: "3v3", 22: "3v3", 4: "4v4", 23: "4v4"}


@lru_cache(maxsize=1)
def reference():
    raw = REFERENCE.read_bytes()
    source = json.loads(SOURCE.read_text())
    definitions = json.loads(raw)
    if hashlib.sha256(raw).hexdigest() != source["sha256"] or definitions.get("result", {}).get("code") != 0:
        raise ValueError("Relic classification reference failed verification")
    return definitions, source


def classification_reference():
    _, source = reference()
    return {k: source[k] for k in ("schema_version", "url", "sha256", "captured_at", "applicable_game_builds")}


def resolve(match, players, metadata):
    """A description alone never upgrades Custom; require the recorded API map."""
    raw_type = match.get("game_type")
    record = metadata.get("source_record") if metadata else None
    if record is not None and not isinstance(record, dict):
        raise ValueError("Invalid metadata source record")
    description = str((record or {}).get("description") or "").upper()
    type_id = (record or {}).get("matchtype_id")
    raw_disagreement = (description == "AUTOMATCH" and raw_type == "Custom") or (
        (description == "CUSTOM" or type_id == 0) and raw_type == "Automatch")
    resolution = {"raw_replay_type": raw_type, "api_matchtype_id": type_id,
                  "api_description": description or None, "raw_disagreement": raw_disagreement,
                  "kind": "replay_automatch" if raw_type == "Automatch" else "custom_or_unresolved",
                  "basis": "replay_flag_only", "ladder_reference": None, "leaderboards": []}
    consistent = not raw_disagreement
    rated = raw_type == "Automatch"
    if record and (type_id == 0 or description == "CUSTOM"):
        resolution.update(kind="custom", basis="matched_metadata_custom_type")
        return resolution, False, consistent
    if record and type_id is not None and type_id not in MODES:
        resolution.update(kind="unrated_or_unknown", basis="unsupported_api_match_type")
        return resolution, False, False
    marker = metadata.get("classification_reference") if metadata else None
    if marker is None:
        return resolution, rated, consistent
    definitions, source = reference()
    if not isinstance(marker, dict) or any(marker.get(k) != source[k] for k in
            ("schema_version", "url", "sha256", "captured_at", "applicable_game_builds")):
        raise ValueError("Metadata classification reference does not match the verified Relic capture")
    metadata_source = metadata.get("source") or {}
    source_url = metadata_source.get("url") or ""
    source_is_daily = re.fullmatch(r"https://storage\.coh3stats\.com/matches/matches-\d+\.json", source_url) is not None
    if not (source_is_daily and record and description == "AUTOMATCH" and record.get("platform") == "steam"
            and match.get("game_build") in source["applicable_game_builds"]
            and MODES.get(type_id) == match.get("mode") and raw_type in {"Custom", "Automatch", "Multiplayer"}):
        return resolution, rated, consistent
    joined = {p["profile_id"]: p for p in metadata.get("players", [])}
    if len(joined) != len(players) or set(joined) != {p["profile_id"] for p in players}:
        raise ValueError("Ladder classification requires the complete same player set")
    maps = []
    for player in players:
        if joined[player["profile_id"]].get("faction") != player["faction"]:
            raise ValueError("Ladder classification faction mismatch")
        candidates = []
        for leaderboard in definitions["leaderboards"]:
            if leaderboard.get("isranked") != 1 or not leaderboard["name"].lower().startswith(match["mode"].lower()):
                continue
            for mapping in leaderboard.get("leaderboardmap", []):
                if mapping.get("matchtype_id") == type_id and RACES.get(mapping.get("race_id")) == player["faction"]:
                    candidates.append({"profile_id": player["profile_id"], "race_id": mapping["race_id"],
                                       "leaderboard_id": leaderboard["id"], "leaderboard_name": leaderboard["name"],
                                       "isranked": leaderboard["isranked"]})
        if len(candidates) != 1:
            resolution.update(kind="unrated_or_unknown", basis="no_unambiguous_ranked_api_mapping")
            return resolution, False, False
        maps.extend(candidates)
    queue = next((t for t in definitions["matchTypes"] if t["id"] == type_id), {})
    resolution.update(kind="ladder_automatch", basis="matched_daily_record_and_relic_ranked_leaderboard_map",
                      queue_name=queue.get("localizedName") or queue.get("name"),
                      ladder_reference=marker, leaderboards=maps)
    return resolution, True, True
