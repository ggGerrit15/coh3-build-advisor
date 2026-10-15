"""Compare non-cancelled replay actions with CoHDB's timed build labels.

The page renders desktop and mobile duplicates. Compare unique (profile ID,
second, label) tuples. This verifies names/times, not completion or multiplicity
of identical commands issued inside the same second.
"""
from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import re
from pathlib import Path


def label(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^(Selects|Uses)\s+", "", value)).strip()


class TimedLabels(HTMLParser):
    def __init__(self, players=()):
        super().__init__(convert_charrefs=True)
        self.player_id = None
        self.entries = set()
        self.names = {p["name"]: p["profile_id"] for p in players}
        if len(self.names) != len(players):
            raise ValueError("Ambiguous player names in CoHDB comparison")
        self.in_title = False
        self.match_id = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "title":
            self.in_title = True
        player = re.fullmatch(r"/players/(\d+)", values.get("href", ""))
        if tag == "a" and player:
            self.player_id = int(player.group(1))
        tooltip = values.get("data-tooltip-content-value")
        if self.player_id is None or not tooltip:
            return
        for item in re.split(r"<br\s*/?>", html.unescape(tooltip)):
            match = re.fullmatch(r"(\d+):(\d{2})\s*[—–-]\s*(.+)", item.strip())
            if match:
                seconds = int(match[1]) * 60 + int(match[2])
                self.entries.add((self.player_id, seconds, label(match[3])))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, value):
        if self.in_title:
            match = re.search(r"Match (\d+)", value)
            if match:
                self.match_id = int(match[1])
        if value.strip() in self.names:
            self.player_id = self.names[value.strip()]


def compare(dataset: dict, reference: set[tuple]) -> dict:
    actual = {(p["profile_id"], int(a["seconds"]), label(a["name"]))
              for p in dataset["players"] for a in p["actions"]
              if not a["cancelled"] and a["name_resolved"] and a.get("name")}
    ids = {p["profile_id"] for p in dataset["players"]}
    expected = {entry for entry in reference if entry[0] in ids}
    if not expected:
        raise ValueError("No CoHDB timed labels matched the replay's player IDs")
    return {"match_id": dataset["match"]["match_id"], "timing_resolution_seconds": 1,
            "scope": "unique non-cancelled timed labels; includes suspect actions for review",
            "matched": len(actual & expected), "reader_labels": len(actual),
            "cohdb_labels": len(expected),
            "reader_only": sorted(actual - expected), "cohdb_only": sorted(expected - actual),
            "exact_match": actual == expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    page = TimedLabels(dataset["players"])
    page.feed(args.html.read_text(encoding="utf-8"))
    if page.match_id != dataset["match"]["match_id"]:
        raise ValueError("CoHDB page match ID does not match replay")
    report = compare(dataset, page.entries)
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["exact_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
