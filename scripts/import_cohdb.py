#!/usr/bin/env python3
"""Import public CoHDB HTML into a normalized, reviewable snapshot.

CoHDB currently renders its statistics as server-side HTML rather than exposing
a documented public JSON endpoint.  This importer deliberately parses only the
semantic sections needed by the advisor and fails closed when the expected
structure disappears.

It does not modify curated advisor profiles or index.html.  The output is a
source snapshot for a later, separately reviewed integration step.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PATCHES = ("2.5.6", "2.5.5", "2.5.3", "2.5.2", "2.5.0")
MODES = ((None, "all"), ("ones", "1v1"), ("twos", "2v2"), ("threes", "3v3"), ("fours", "4v4"))
RATING_FILTERS = (
    ("bal:all", "balanced_all"),
    ("avg:under_1000", "avg_under_1000"),
    ("avg:1000_1200", "avg_1000_1200"),
    ("avg:1200_1400", "avg_1200_1400"),
    ("avg:1400_1600", "avg_1400_1600"),
    ("avg:1600_1800", "avg_1600_1800"),
    ("avg:1800_plus", "avg_1800_plus"),
)
FACTIONS = ("USF", "British", "Wehrmacht", "DAK")
NO_BATTLEGROUP = "No Battlegroup"


class ImportErrorWithContext(RuntimeError):
    """An expected source or parser failure with an actionable message."""


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    parent: "Node | None" = None
    children: list["Node"] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    order: int = 0

    def text(self) -> str:
        return " ".join(" ".join(self.data).split()) + (" " if self.children else "") + " ".join(
            child.text() for child in self.children
        ).strip()

    def raw_text(self) -> str:
        return " ".join((" ".join(self.data), *(child.raw_text() for child in self.children))).strip()

    def has_class(self, value: str) -> bool:
        return value in set(self.attrs.get("class", "").split())

    def find_all(self, predicate) -> list["Node"]:
        found: list[Node] = []
        for child in self.children:
            if predicate(child):
                found.append(child)
            found.extend(child.find_all(predicate))
        return found

    def closest(self, predicate) -> "Node | None":
        node: Node | None = self
        while node is not None:
            if predicate(node):
                return node
            node = node.parent
        return None


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]
        self.order = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.order += 1
        node = Node(tag.lower(), {key: value or "" for key, value in attrs}, self.stack[-1], order=self.order)
        self.stack[-1].children.append(node)
        if tag.lower() not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag.lower():
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].data.append(unescape(data))


def parse_html(content: str) -> Node:
    parser = TreeParser()
    parser.feed(content)
    parser.close()
    return parser.root


def compact(value: str) -> str:
    return " ".join(unescape(value).replace("\xa0", " ").split())


def number(value: str) -> int:
    return int(re.sub(r"[^0-9]", "", value))


def float_number(value: str) -> float:
    return float(value.replace("−", "-").replace(",", ".").replace(" ", "").strip())


def parse_record(text: str) -> dict[str, int | float]:
    normalized = compact(text).replace("–", "-").replace("—", "-")
    pattern = re.compile(
        r"Record\s+(?P<w>[\d,]+)\s*(?:-\s*)?(?P<l>[\d,]+).*?"
        r"Win%\s+(?P<wr>[\d.]+)%.*?"
        r"Adjusted\s+(?P<adjusted>[−+\-\d. ]+).*?"
        r"Selections\s+(?P<selections>[\d,]+)",
        re.IGNORECASE,
    )
    match = pattern.search(normalized)
    if not match:
        raise ImportErrorWithContext(f"Could not parse battlegroup record: {normalized[:240]}")
    return {
        "wins": number(match.group("w")),
        "losses": number(match.group("l")),
        "win_rate": float_number(match.group("wr")),
        "adjusted": float_number(match.group("adjusted")),
        "selections": number(match.group("selections")),
    }


def parse_games_record(text: str) -> dict[str, int | float]:
    normalized = compact(text).replace("–", "-").replace("—", "-")
    match = re.search(r"(?P<wr>[\d.]+)%\s+(?P<games>[\d,]+) games\s+(?P<w>[\d,]+)W\s*-\s*(?P<l>[\d,]+)L", normalized, re.I)
    if not match:
        raise ImportErrorWithContext(f"Could not parse build-order mode summary: {normalized[:240]}")
    return {
        "win_rate": float_number(match.group("wr")),
        "games": number(match.group("games")),
        "wins": number(match.group("w")),
        "losses": number(match.group("l")),
    }


def parse_rating_cards(panel: Node) -> dict[str, dict[str, int | float]]:
    grid = next((child for child in panel.children if child.tag == "div"), None)
    if grid is None:
        raise ImportErrorWithContext(f"Missing rating grid for panel {panel.attrs.get('data-panel')}")
    cards = [child for child in grid.children if child.tag == "div"]
    result: dict[str, dict[str, int | float]] = {}
    for card in cards:
        text = compact(card.text())
        match = re.search(r"(?P<label>Under\s+1000|1800\+|\d+\s*[–-]\s*\d+)\s+(?P<wr>[\d.]+)%\s+(?P<games>[\d,]+)g", text, re.I)
        if not match:
            continue
        label = compact(match.group("label")).replace("UNDER", "Under")
        result[label.replace("UNDER", "Under")] = {
            "win_rate": float_number(match.group("wr")),
            "games": number(match.group("games")),
        }
    if len(result) < 5:
        raise ImportErrorWithContext(f"Expected at least five rating bands in {panel.attrs.get('data-panel')}, found {len(result)}")
    return result


def section_with_heading(root: Node, title: str) -> Node:
    wanted = compact(title).upper()
    for heading in root.find_all(lambda node: node.tag == "h3" and compact(node.text()).upper() == wanted):
        section = heading.closest(lambda node: node.tag == "section")
        if section:
            return section
    raise ImportErrorWithContext(f"Missing CoHDB section: {title}")


def card_label(card: Node, labels: Iterable[str]) -> str | None:
    text = compact(card.text())
    for label in labels:
        if re.search(rf"\b{re.escape(label)}\b", text, re.I):
            return label
    return None


def extract_sequence_cards(section: Node, labels: Iterable[str]) -> list[dict[str, object]]:
    candidates = section.find_all(
        lambda node: node.tag == "div"
        and "bg-light" in node.attrs.get("class", "")
        and "border-lighter" in node.attrs.get("class", "")
        and "games" in compact(node.text()).lower()
    )
    cards: list[dict[str, object]] = []
    seen: set[int] = set()
    for card in sorted(candidates, key=lambda item: item.order):
        label = card_label(card, labels)
        if not label or card.order in seen:
            continue
        # The outer card contains the label, count and a vertical list of step rows.
        steps_parent = next(
            (
                node
                for node in card.find_all(
                    lambda child: child.tag == "div" and "flex-col" in child.attrs.get("class", "") and "gap-1.5" in child.attrs.get("class", "")
                )
            ),
            None,
        )
        steps: list[dict[str, str]] = []
        if steps_parent:
            for step in steps_parent.children:
                if step.tag != "div":
                    continue
                images = step.find_all(lambda node: node.tag == "img")
                spans = [compact(node.text()) for node in step.find_all(lambda node: node.tag == "span") if compact(node.text())]
                name = spans[-1] if spans else compact(step.text())
                if name:
                    steps.append({"name": name, "icon_url": images[0].attrs.get("src", "") if images else ""})
        count_match = re.search(r"([\d,]+) games", compact(card.text()), re.I)
        if not count_match or not steps:
            continue
        cards.append({"label": label, "games": number(count_match.group(1)), "steps": steps})
        seen.add(card.order)
    if not cards:
        raise ImportErrorWithContext(f"No sequence cards found in CoHDB section {compact(section.text())[:80]}")
    return cards


def parse_tech_paths(section: Node) -> list[dict[str, object]]:
    rows = section.find_all(lambda node: node.tag == "div" and "divide-y" in node.attrs.get("class", ""))
    if not rows:
        return []
    result: list[dict[str, object]] = []
    for row in rows[0].children:
        text = compact(row.text())
        if not text or "games" not in text:
            continue
        match = re.search(r"(?P<path>.+?)\s+(?P<games>[\d,]+) games\s+(?P<share>[\d.]+)%", text)
        if match:
            result.append({"path": match.group("path"), "games": number(match.group("games")), "share": float_number(match.group("share"))})
    return result


def parse_build_order_page(content: str, source_url: str, patch: dict[str, str]) -> dict[str, object]:
    root = parse_html(content)
    h1 = next(
        (
            node
            for node in root.find_all(lambda node: node.tag == "h1")
            if compact(node.text()).lower() != "cohdb"
        ),
        None,
    )
    if not h1:
        raise ImportErrorWithContext(f"Missing build-order title at {source_url}")
    win_section = section_with_heading(root, "Win Rate")
    mode_summaries: dict[str, dict[str, int | float]] = {}
    mode_names = {"all": "all", "ones": "1v1", "twos": "2v2", "threes": "3v3", "fours": "4v4"}
    for button in win_section.find_all(lambda node: node.tag == "button" and node.attrs.get("data-tab-panel") in mode_names):
        mode = mode_names[button.attrs["data-tab-panel"]]
        mode_summaries[mode] = parse_games_record(button.text())
    if len(mode_summaries) < 5:
        raise ImportErrorWithContext(f"Expected all five mode summaries at {source_url}, found {sorted(mode_summaries)}")

    rating_panels: dict[str, dict[str, dict[str, int | float]]] = {}
    for panel in root.find_all(lambda node: node.tag == "div" and node.attrs.get("data-panel") in mode_names):
        mode = mode_names[panel.attrs["data-panel"]]
        rating_panels[mode] = parse_rating_cards(panel)

    build_section = section_with_heading(root, "Build Order")
    followup_section = section_with_heading(root, "Common Followups")
    tech_section = section_with_heading(root, "Tech Paths")
    return {
        "title": compact(h1.text()),
        "source_url": source_url,
        "patch": patch,
        "mode_summaries": mode_summaries,
        "rating_bands": rating_panels,
        "most_common_and_variants": extract_sequence_cards(build_section, ("Most Common", "Variant 1", "Variant 2", "Variant 3", "Variant 4")),
        "followups": extract_sequence_cards(followup_section, ("Followup 1", "Followup 2", "Followup 3", "Followup 4", "Followup 5")),
        "tech_paths": parse_tech_paths(tech_section),
    }


def find_faction_headers(root: Node) -> list[tuple[int, str]]:
    headers: list[tuple[int, str]] = []
    for node in root.find_all(lambda item: item.tag == "span" and "font-semibold" in item.attrs.get("class", "")):
        text = compact(node.text())
        if text in FACTIONS:
            headers.append((node.order, text))
    return sorted(headers)


def parse_battlegroups_page(content: str, source_url: str, patch: dict[str, str], mode: str, rating_filter: str, opponent: str = "all") -> list[dict[str, object]]:
    root = parse_html(content)
    headers = find_faction_headers(root)
    if len(headers) != 4:
        raise ImportErrorWithContext(f"Expected four faction headers on {source_url}, found {headers}")
    rows = root.find_all(
        lambda node: node.tag == "div"
        and "bg-light" in node.attrs.get("class", "")
        and "border-lighter" in node.attrs.get("class", "")
        and all(token in compact(node.text()) for token in ("Record", "Win%", "Selections"))
    )
    # Keep only the outer row card. Nested nodes do not contain the three labels.
    rows = [row for row in rows if row.parent is None or not (
        "bg-light" in row.parent.attrs.get("class", "")
        and "border-lighter" in row.parent.attrs.get("class", "")
        and all(token in compact(row.parent.text()) for token in ("Record", "Win%", "Selections"))
    )]
    # Filtered rating cohorts can omit battlegroups with no observed selections.
    # Keep those pages sparse; the snapshot coverage records which rows are absent.
    if not rows or len(rows) > 32:
        raise ImportErrorWithContext(f"Expected between 1 and 32 battlegroup rows on {source_url}, found {len(rows)}")
    result: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda item: item.order):
        preceding = [header for order, header in headers if order < row.order]
        if not preceding:
            continue
        faction = preceding[-1]
        image = next((node for node in row.find_all(lambda item: item.tag == "img")), None)
        name = ""
        if image:
            name = compact(image.attrs.get("alt", "")).replace(" Battlegroup", "")
        if not name:
            name_node = next((node for node in row.find_all(lambda item: item.tag == "span" and "font-bold" in item.attrs.get("class", ""))), None)
            name = compact(name_node.text()) if name_node else ""
        if not name:
            if "No Battlegroup" in compact(row.text()):
                name = NO_BATTLEGROUP
            else:
                raise ImportErrorWithContext(f"Could not identify battlegroup name in {source_url}")
        record = parse_record(row.text())
        if record["wins"] + record["losses"] != record["selections"]:
            raise ImportErrorWithContext(f"Record/selections mismatch for {faction}/{name}: {record}")
        expected = round(100 * record["wins"] / record["selections"], 1) if record["selections"] else 0
        if abs(expected - record["win_rate"]) > 0.2:
            raise ImportErrorWithContext(f"Win-rate mismatch for {faction}/{name}: {record}")
        result.append({
            "faction": faction,
            "battlegroup": name,
            "mode": mode,
            "rating_filter": rating_filter,
            "map": "all",
            "opponent": opponent,
            "patch": patch,
            **record,
        })
    if len(result) != len(set((row["faction"], row["battlegroup"]) for row in result)):
        raise ImportErrorWithContext(f"Duplicate battlegroup rows in {source_url}")
    return result


def add_query(url: str, **values: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in values.items():
        query[key] = [value]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def fetch(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": "coh3-build-advisor-cohdb-importer/1.0", "Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:  # pragma: no cover - network failures are integration concerns
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        if "Just a moment" in body or "challenge-platform" in body or "Enable JavaScript and cookies" in body:
            raise ImportErrorWithContext(
                f"CoHDB returned a Cloudflare browser challenge for {url}. "
                "The importer will not bypass it; use the unfiltered public page or a documented export/API."
            ) from exc
        raise ImportErrorWithContext(f"Could not fetch {url}: HTTP {exc.code}") from exc
    except Exception as exc:  # pragma: no cover - network failures are integration concerns
        raise ImportErrorWithContext(f"Could not fetch {url}: {exc}") from exc


def discover_latest_patch(content: str, base_url: str) -> dict[str, str]:
    root = parse_html(content)
    links = root.find_all(lambda node: node.tag == "a" and "patch=" in node.attrs.get("href", ""))
    latest = next((link for link in links if "latest" in compact(link.text()).lower()), None)
    if latest is None:
        raise ImportErrorWithContext("Could not find CoHDB's latest patch link")
    patch_url = urljoin(base_url, latest.attrs["href"])
    query = parse_qs(urlparse(patch_url).query)
    patch_id = (query.get("patch") or [""])[0]
    if not patch_id:
        raise ImportErrorWithContext(f"Latest CoHDB patch link has no patch ID: {patch_url}")
    label = re.sub(r"\s*\(latest\)\s*", "", compact(latest.text()), flags=re.I)
    if not label:
        raise ImportErrorWithContext(f"Latest CoHDB patch link has no label: {patch_url}")
    return {"label": label, "id": patch_id, "url": patch_url}


def load_sources(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ImportErrorWithContext(f"Could not read source configuration {path}: {exc}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/cohdb/latest.json"))
    parser.add_argument("--sources", type=Path, default=Path("scripts/cohdb_sources.json"))
    parser.add_argument("--base-url", default="https://cohdb.com")
    parser.add_argument("--patch-id", help="Use a specific CoHDB patch ID instead of discovering the latest patch")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--skip-build-orders", action="store_true")
    parser.add_argument("--skip-battlegroups", action="store_true")
    parser.add_argument(
        "--include-filtered-battlegroups",
        action="store_true",
        help="Also request mode/rating-filtered battlegroup pages. CoHDB may require a browser challenge for these URLs.",
    )
    parser.add_argument("--max-battlegroup-requests", type=int, default=35)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        battlegroup_index_url = urljoin(args.base_url, "/battlegroups")
        index_html = fetch(battlegroup_index_url, args.timeout)
        patch = {"label": "custom", "id": args.patch_id or "", "url": ""}
        if args.patch_id:
            patch["url"] = add_query(battlegroup_index_url, patch=args.patch_id)
        else:
            patch = discover_latest_patch(index_html, battlegroup_index_url)
        patch_url = patch["url"]

        sources = load_sources(args.sources)
        snapshot: dict[str, object] = {
            "schema_version": "cohdb.snapshot.v1",
            "source": "CoHDB",
            "retrieved_at": retrieved_at,
            "parser": {"name": "coh3-build-advisor-cohdb-importer", "version": "1.0.0"},
            "patch": patch,
            "filter_scope": {
                "battlegroups": {
                    "mode": "selected",
                    "map": "all",
                    "opponent": "all",
                    "faction": "selected",
                    "battlegroup": "selected",
                    "rating": "each_band_and_derived_all",
                }
            },
            "coverage": {"battlegroups": [], "build_orders": []},
            "battlegroups": [],
            "build_orders": [],
            "warnings": [],
        }

        if not args.skip_battlegroups:
            expected_battlegroups: set[tuple[str, str]] = set()
            requests = 0
            battlegroup_requests = [(None, "all", "bal:all", "balanced_all")]
            if args.include_filtered_battlegroups:
                battlegroup_requests = [
                    (mode_query, mode_label, rating_query, rating_label)
                    for mode_query, mode_label in MODES
                    for rating_query, rating_label in RATING_FILTERS
                ]
            for mode_query, mode_label, rating_query, rating_label in battlegroup_requests:
                    if requests >= args.max_battlegroup_requests:
                        raise ImportErrorWithContext(f"Battlegroup request limit reached at {args.max_battlegroup_requests}")
                    url = battlegroup_index_url
                    if args.include_filtered_battlegroups:
                        url = add_query(patch_url, **({"mode": mode_query} if mode_query else {}), rating_range=rating_query)
                    html = fetch(url, args.timeout)
                    rows = parse_battlegroups_page(html, url, patch, mode_label, rating_label)
                    if mode_label == "all" and rating_label == "balanced_all":
                        if len(rows) != 32:
                            raise ImportErrorWithContext(
                                f"Expected 32 baseline battlegroup rows on {url}, found {len(rows)}"
                            )
                        expected_battlegroups = {
                            (row["faction"], row["battlegroup"]) for row in rows
                        }
                    if not expected_battlegroups:
                        raise ImportErrorWithContext("Missing the all-modes balanced baseline")
                    observed_battlegroups = {
                        (row["faction"], row["battlegroup"]) for row in rows
                    }
                    missing_battlegroups = sorted(expected_battlegroups - observed_battlegroups)
                    snapshot["battlegroups"].extend(rows)
                    snapshot["coverage"]["battlegroups"].append(
                        {
                            "mode": mode_label,
                            "rating_filter": rating_label,
                            "map": "all",
                            "opponent": "all",
                            "rows": len(rows),
                            "expected_rows": len(expected_battlegroups),
                            "missing_battlegroups": [
                                {"faction": faction, "battlegroup": battlegroup}
                                for faction, battlegroup in missing_battlegroups
                            ],
                            "source_url": url,
                        }
                    )
                    requests += 1
                    time.sleep(args.delay)
            if not args.include_filtered_battlegroups:
                snapshot["warnings"].append(
                    "Filtered battlegroup pages are not imported by default because CoHDB may require a browser challenge; the snapshot covers the public unfiltered table only."
                )

        if not args.skip_build_orders:
            for source in sources.get("build_orders", []):
                # CoHDB's build-order pages default to the latest patch.  In
                # the current deployment, adding a patch query to these
                # detail pages can trigger a 403 even though the same patch
                # query is supported by the battlegroup index.  Keep the
                # unmodified public detail URL and attach the patch discovered
                # from the index as the snapshot's provenance.
                source_url = urljoin(args.base_url, source["path"])
                parsed = parse_build_order_page(fetch(source_url, args.timeout), source_url, patch)
                parsed["id"] = source["id"]
                parsed["faction"] = source.get("faction")
                parsed["notes"] = source.get("notes", "")
                snapshot["build_orders"].append(parsed)
                snapshot["coverage"]["build_orders"].append(source["id"])
                time.sleep(args.delay)

        if not snapshot["battlegroups"] and not snapshot["build_orders"]:
            raise ImportErrorWithContext("Importer produced no data")
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(output)
        print(json.dumps({"output": str(output), "patch": patch, "battlegroups": len(snapshot["battlegroups"]), "build_orders": len(snapshot["build_orders"])}, ensure_ascii=False))
        return 0
    except ImportErrorWithContext as exc:
        print(f"CoHDB import failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
