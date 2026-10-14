"""Shared, explicit source adapters for the replay cohort pilot (stdlib only)."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from import_replay import bg_key

RACES = {129494: "USF", 203852: "British", 137123: "Wehrmacht", 198437: "DAK"}
MODES = {1: "1v1", 20: "1v1", 2: "2v2", 21: "2v2", 3: "3v3", 22: "3v3", 4: "4v4", 23: "4v4"}
HOSTS = {"cohdb.com", "storage.coh3stats.com", "replays.coh3stats.com",
         "cohdb-production.s3.us-east-005.backblazeb2.com"}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def safe_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.port not in (None, 443) or parsed.username or parsed.password:
        raise ValueError("Unexpected public-source URL")
    return url


class HttpCache:
    """One request at a time, finite timeout/size, no challenge retries or bypass."""
    def __init__(self, root: Path, delay: float = 1.0):
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("Invalid request delay")
        self.root, self.delay, self.last = root, delay, 0.0
        root.mkdir(parents=True, exist_ok=True)

    def get(self, url: str, limit: int = 128 * 1024 * 1024) -> bytes:
        safe_url(url)
        path = self.root / hashlib.sha256(url.encode()).hexdigest()
        if path.exists():
            if path.stat().st_size > limit:
                raise ValueError("Cached response exceeds size limit")
            return path.read_bytes()
        time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        request = Request(url, headers={"User-Agent": "CoH3-Build-Advisor/replay-cohort-pilot", "Accept-Encoding": "gzip"})
        with urlopen(request, timeout=30) as response:
            safe_url(response.geturl())
            stream = gzip.GzipFile(fileobj=response) if response.headers.get("Content-Encoding", "").lower() == "gzip" else response
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Response exceeds size limit")
        if data.lstrip().lower().startswith((b"<!doctype html", b"<html")) and any(
                marker in data[:20000].lower() for marker in (b"just a moment", b"cf-chl-", b"challenge-platform")):
            raise ValueError("Public source returned a browser challenge")
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
        return data


class MatchListing(HTMLParser):
    """Read observed CoHDB rows and the actual next-page link; ignore predictions."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.next_url, self.row = [], None, None
        self.cell, self.text, self.skip = -1, [], 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "turbo-frame" and attrs.get("id") == "load-page" and attrs.get("src"):
            self.next_url = safe_url(urljoin("https://cohdb.com", attrs["src"]))
        if tag == "tr":
            match = re.fullmatch(r"/replays/(\d+)", attrs.get("data-href", ""))
            if match:
                self.row = {"replay_id": int(match[1]), "source_url": "https://cohdb.com" + match[0], "profile_ids": []}
                self.cell = -1
        if self.row is None:
            return
        if tag == "td":
            self.cell += 1
            self.text = []
        if tag == "button":
            self.skip += 1
        if tag == "a":
            player = re.fullmatch(r"/players/(\d+)", attrs.get("href", ""))
            if player:
                self.row["profile_ids"].append(int(player[1]))
        if attrs.get("title", "").endswith(" UTC"):
            try:
                date = datetime.strptime(attrs["title"], "%B %d, %Y, %I:%M %p UTC").replace(tzinfo=timezone.utc)
                self.row["completed_at_utc"] = date.isoformat()
            except ValueError:
                pass

    def handle_data(self, text):
        if self.row is not None and not self.skip:
            self.text.append(text)

    def handle_endtag(self, tag):
        if tag == "button" and self.skip:
            self.skip -= 1
        if self.row is None:
            return
        if tag == "td":
            value = " ".join("".join(self.text).split())
            if self.cell == 0:
                self.row["map_label"] = value
            elif self.cell == 5 and value in {"Axis", "Allies"}:
                self.row["victor"] = value
        if tag == "tr":
            self.row["profile_ids"] = sorted(set(self.row["profile_ids"]))
            self.rows.append(self.row)
            self.row, self.skip = None, 0


def listing(html: str) -> tuple[list[dict], str | None]:
    parser = MatchListing()
    parser.feed(html)
    return parser.rows, parser.next_url


def daily_index(data: dict) -> dict[int, dict]:
    if not isinstance(data, dict) or not isinstance(data.get("matches"), list):
        raise ValueError("Unsupported CoH3Stats daily dump")
    index = {}
    for match in data["matches"]:
        mid = match.get("id")
        if isinstance(mid, bool) or not isinstance(mid, int) or mid <= 0 or mid in index:
            raise ValueError("Invalid or duplicate daily match ID")
        index[mid] = match
    return index


def stats_metadata(raw: dict, reader: dict, source: dict) -> dict:
    """Join exact IDs and races; oldrating alone is the pre-match rating."""
    if raw.get("id") != reader["match"].get("match_id"):
        raise ValueError("Daily match ID does not match replay")
    reports = raw.get("matchhistoryreportresults", [])
    ids = [p.get("profile_id") for p in reports]
    expected = {p["profile_id"] for p in reader["players"]}
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("Daily player IDs do not match replay")
    players = []
    replay_players = {p["profile_id"]: p for p in reader["players"]}
    custom_metadata = raw.get("matchtype_id") == 0 or str(raw.get("description") or "").upper() == "CUSTOM"
    for report in reports:
        faction = RACES.get(report.get("race_id"))
        if faction != replay_players[report["profile_id"]]["faction"]:
            raise ValueError("Daily race does not match replay faction")
        member = report.get("matchhistorymember") or {}
        result_id = report.get("resulttype")
        if isinstance(result_id, bool) or (result_id is not None and not isinstance(result_id, int)):
            raise ValueError("Invalid resulttype")
        result = {0: "loss", 1: "win", 4: "draw"}.get(result_id)
        if member.get("outcome") in (0, 1) and result_id in (0, 1) and member["outcome"] != result_id:
            raise ValueError("Conflicting result and member outcome")
        rating = member.get("oldrating")
        if rating is not None and (isinstance(rating, bool) or not isinstance(rating, (int, float)) or not math.isfinite(rating) or rating < 0):
            raise ValueError("Invalid oldrating")
        players.append({"profile_id": report["profile_id"], "faction": faction, "result": result,
                        "rating_before": None if custom_metadata else rating,
                        "rating_before_unverified": rating if custom_metadata else None,
                        "rating_after": member.get("newrating")})
    source = dict(source, name="CoH3Stats open daily match data", rating_field="matchhistorymember.oldrating",
                  outcome_field="matchhistoryreportresults.resulttype")
    if custom_metadata:
        source["rating_note"] = "CoH3Stats warns that Custom-game ELO is not accurate; oldrating is retained as unverified, not pre-match ELO."
    return {"schema_version": "coh3.match-metadata.v1", "match_id": raw["id"],
            "mode": MODES.get(raw.get("matchtype_id")), "source": source, "players": players,
            "source_record": {k: raw.get(k) for k in ("matchtype_id", "description", "startgametime", "completiontime", "platform")}}


def listing_metadata(row: dict, reader: dict) -> dict | None:
    """List victor is usable only with the exact same two human profile IDs."""
    players = reader["players"]
    if len(players) != 2 or not all(p.get("human") for p in players) or row.get("victor") not in {"Axis", "Allies"}:
        return None
    if set(row.get("profile_ids", [])) != {p["profile_id"] for p in players}:
        raise ValueError("Listing player IDs do not match replay")
    if {"Axis" if p["faction"] in {"Wehrmacht", "DAK"} else "Allies" for p in players} != {"Axis", "Allies"}:
        return None
    return {"schema_version": "coh3.match-metadata.v1", "match_id": reader["match"]["match_id"],
            "source": {"name": "CoHDB public match listing", "url": row["source_url"],
                       "rating_note": "No individually verified pre-match rating in listing"},
            "players": [{"profile_id": p["profile_id"], "faction": p["faction"], "rating_before": None,
                         "result": "win" if ("Axis" if p["faction"] in {"Wehrmacht", "DAK"} else "Allies") == row["victor"] else "loss"} for p in players]}


def target_players(dataset: dict, scope: dict) -> list[dict]:
    if dataset["match"].get("patch") != scope["patch"] or dataset["match"].get("mode") != scope["mode"]:
        return []
    return [p for p in dataset["players"] if p["faction"] == scope["faction"]
            and bg_key((p.get("battlegroup") or {}).get("name") or "") == bg_key(scope["battlegroup"])]
