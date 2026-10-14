"""Source identity, bounded collection, deduplication and ordered-cohort tests."""
import copy
from argparse import Namespace
import gzip
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect_replays as collector
from import_replay import normalize
import replay_cohort as sources
import report_replay_cohort as report


class CohortTests(unittest.TestCase):
    def setUp(self):
        self.reader = json.loads((ROOT / "tests/fixtures/replay-reader-88366979.json").read_text())
        self.reader["players"][0]["battlegroup"]["name"] = "Mechanized Battlegroup"
        self.profiles = json.loads((ROOT / "coh3_build_advisor_data.json").read_text())["profiles"]
        self.scope = {"faction": "Wehrmacht", "battlegroup": "Mechanized", "mode": "1v1", "patch": "2.5.6"}
        self.raw = {"id": 88366979, "matchtype_id": 20, "description": "AUTOMATCH",
                    "matchhistoryreportresults": [
                        {"profile_id": 832443, "race_id": 203852, "resulttype": 0,
                         "matchhistorymember": {"oldrating": 886, "newrating": 875, "outcome": 0}},
                        {"profile_id": 63169, "race_id": 137123, "resulttype": 1,
                         "matchhistorymember": {"oldrating": 1083, "newrating": 1094, "outcome": 1}}]}

    def dataset(self, mid=None, rating=None, ranked=False):
        raw, reader = copy.deepcopy(self.raw), copy.deepcopy(self.reader)
        if mid:
            raw["id"] = reader["match"]["match_id"] = mid
        if rating:
            raw["matchhistoryreportresults"][1]["matchhistorymember"]["oldrating"] = rating
        if ranked:
            reader["match"]["game_type"] = "Automatch"
        metadata = sources.stats_metadata(raw, reader, {"url": "https://storage.coh3stats.com/example"})
        return normalize(reader, self.profiles, metadata, "https://cohdb.com/replays/7283962")

    def test_metadata_joins_ids_not_player_order(self):
        metadata = sources.stats_metadata(self.raw, self.reader, {})
        players = {p["profile_id"]: p for p in metadata["players"]}
        self.assertEqual((players[63169]["result"], players[63169]["rating_before"]), ("win", 1083))
        self.assertEqual(metadata["source_record"]["matchtype_id"], 20)

    def test_newrating_is_never_substituted_for_absent_oldrating(self):
        del self.raw["matchhistoryreportresults"][1]["matchhistorymember"]["oldrating"]
        metadata = sources.stats_metadata(self.raw, self.reader, {})
        p = next(p for p in metadata["players"] if p["profile_id"] == 63169)
        self.assertIsNone(p["rating_before"])
        self.assertEqual(p["rating_after"], 1094)

    def test_custom_daily_oldrating_is_retained_only_as_unverified(self):
        self.raw.update(matchtype_id=0, description="CUSTOM")
        metadata = sources.stats_metadata(self.raw, self.reader, {})
        player = next(p for p in metadata["players"] if p["profile_id"] == 63169)
        self.assertIsNone(player["rating_before"])
        self.assertEqual(player["rating_before_unverified"], 1083)

    def test_bad_metadata_identity_race_or_result_is_rejected(self):
        for change in ("match", "player", "race", "result"):
            raw = copy.deepcopy(self.raw)
            if change == "match": raw["id"] += 1
            if change == "player": raw["matchhistoryreportresults"][0]["profile_id"] += 1
            if change == "race": raw["matchhistoryreportresults"][0]["race_id"] = 129494
            if change == "result": raw["matchhistoryreportresults"][0]["matchhistorymember"]["outcome"] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                sources.stats_metadata(raw, self.reader, {})

    def test_duplicate_daily_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            sources.daily_index({"matches": [self.raw, self.raw]})

    def test_http_cache_accepts_observed_storage_redirect_and_decodes_gzip_once(self):
        class Response(io.BytesIO):
            headers = {"Content-Encoding": "gzip"}
            def geturl(self):
                return "https://cohdb-production.s3.us-east-005.backblazeb2.com/public-replay"
        body = b"replay bytes"
        with tempfile.TemporaryDirectory() as folder, patch.object(sources, "urlopen", return_value=Response(gzip.compress(body))) as request:
            cache = sources.HttpCache(Path(folder), delay=0)
            url = "https://cohdb.com/replays/7283962/file?inflate=true"
            self.assertEqual(cache.get(url), body)
            self.assertEqual(cache.get(url), body)
            self.assertEqual(request.call_count, 1)
            with self.assertRaises(ValueError):
                cache.get(url, limit=2)

    def listing(self, rid=7283962):
        date = "October 13, 2026, 11:59 PM UTC"
        return f'''<tr data-href="/replays/{rid}"><td>Angoville</td><td><a href="/players/832443">British</a></td>
        <td>99%</td><td><a href="/players/63169">Wehr</a></td><td>1%</td>
        <td><span>Axis</span><button>Reveal</button></td><td>886–1083</td><td>30:30</td>
        <td><span title="{date}">Yesterday</span></td></tr>'''

    def test_listing_uses_victor_not_predicted_probability_and_observed_pagination(self):
        html = self.listing() + '<turbo-frame id="load-page" src="/matches.turbo_stream?patch=50313&amp;page=observed"></turbo-frame>'
        rows, url = sources.listing(html)
        self.assertEqual(rows[0]["victor"], "Axis")
        self.assertEqual(rows[0]["profile_ids"], [63169, 832443])
        self.assertEqual(rows[0]["completed_at_utc"], "2026-10-13T23:59:00+00:00")
        self.assertEqual(url, "https://cohdb.com/matches.turbo_stream?patch=50313&page=observed")
        metadata = sources.listing_metadata(rows[0], self.reader)
        self.assertEqual(next(p for p in metadata["players"] if p["profile_id"] == 63169)["result"], "win")
        self.assertTrue(all(p["rating_before"] is None for p in metadata["players"]))

    def test_unexpected_pagination_host_is_rejected(self):
        with self.assertRaises(ValueError):
            sources.listing('<turbo-frame id="load-page" src="https://other.example/page"></turbo-frame>')

    def test_scope_never_combines_different_patch_mode_or_bg(self):
        dataset = self.dataset()
        self.assertEqual(len(sources.target_players(dataset, self.scope)), 1)
        for key, value in (("patch", "2.5.5"), ("mode", "2v2"), ("battlegroup", "Breakthrough")):
            self.assertEqual(sources.target_players(dataset, dict(self.scope, **{key: value})), [])

    def test_duplicate_match_player_counts_once_even_with_different_file_hash(self):
        a = self.dataset()
        b = copy.deepcopy(a)
        b["replay_sha256"] = "other recording"
        r = report.analyze([a, b], self.scope)
        self.assertEqual(r["counts"]["match_players"], 1)
        self.assertEqual(r["counts"]["duplicates_ignored"], 1)

    def test_conflicting_recordings_are_not_silently_deduplicated(self):
        a, b = self.dataset(), self.dataset()
        b["players"][0]["result"] = "loss"
        with self.assertRaises(ValueError):
            report.analyze([a, b], self.scope)

    def test_complete_sequence_order_is_preserved(self):
        a, b = self.dataset(), self.dataset(mid=88366980)
        p = b["players"][0]
        p["build_sequence"][1]["pbgid"], p["build_sequence"][2]["pbgid"] = p["build_sequence"][2]["pbgid"], p["build_sequence"][1]["pbgid"]
        r = report.analyze([a, b], self.scope)
        self.assertEqual(len(r["exploratory_openers"]), 2)
        self.assertTrue(all(g["games"] == 1 for g in r["exploratory_openers"]))

    def test_rating_and_opponent_bands_remain_separate(self):
        a, b = self.dataset(), self.dataset(mid=88366980, rating=1600)
        c = self.dataset(mid=88366981)
        c["players"][0]["opponent_factions"] = ["USF"]
        r = report.analyze([a, b, c], self.scope)
        self.assertEqual(len(r["exploratory_openers"]), 3)

    def test_custom_replay_never_becomes_ranked_from_daily_automatch_label(self):
        r = report.analyze([self.dataset()], self.scope)
        self.assertEqual(r["counts"]["with_pre_match_rating"], 1)
        self.assertEqual(r["counts"]["ranked_eligible_complete_openers"], 0)
        self.assertNotIn("win_rate", r["exploratory_openers"][0])
        self.assertEqual(r["ranked_exclusion_counts"], {"ranked_game": 1, "metadata_match_type_consistent": 1})

    def test_automatch_replay_with_custom_daily_metadata_is_not_ranked(self):
        reader = copy.deepcopy(self.reader)
        reader["match"]["game_type"] = "Automatch"
        raw = copy.deepcopy(self.raw)
        raw.update(description="CUSTOM", matchtype_id=0)
        metadata = sources.stats_metadata(raw, reader, {})
        dataset = normalize(reader, self.profiles, metadata)
        player = dataset["players"][0]
        self.assertFalse(player["quality_checks"]["metadata_match_type_consistent"])
        self.assertFalse(player["eligible_for_ranked_statistics"])

    def test_incomplete_or_uncertain_prefixes_do_not_enter_comparisons(self):
        a, b = self.dataset(), self.dataset(mid=88366980)
        a["players"][0]["build_sequence"] = a["players"][0]["build_sequence"][:3]
        b["players"][0]["actions"][0]["excluded_reasons"] = ["suspect_building"]
        r = report.analyze([a, b], self.scope)
        self.assertEqual(r["counts"]["usable_complete_openers"], 0)
        self.assertEqual(r["opener_exclusion_counts"], {"incomplete_opener_window": 1, "uncertain_opener_command": 1})

    def test_ranked_results_require_all_checks_and_show_uncertainty(self):
        a, b = self.dataset(ranked=True), self.dataset(mid=88366980, ranked=True)
        b["players"][0]["result"] = "loss"
        r = report.analyze([a, b], self.scope)
        g = r["ranked_openers"][0]
        self.assertEqual((g["games"], g["wins"], g["losses"], g["win_rate"]), (2, 1, 1, 0.5))
        self.assertEqual(g["evidence"], "too_sparse")
        self.assertLess(g["wilson_95"]["lower"], .5)
        self.assertGreater(g["wilson_95"]["upper"], .5)

    def test_collector_stops_at_target_and_does_not_fetch_next_page(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(Path(folder))
            requested = []
            def get(_, url, limit=0):
                requested.append(url)
                return (self.listing() + '<turbo-frame id="load-page" src="/matches.turbo_stream?page=next"></turbo-frame>').encode() if "/matches?" in url else b"replay"
            process = Namespace(stdout=json.dumps(self.reader))
            with patch.object(sources.HttpCache, "get", get), patch.object(collector.subprocess, "run", return_value=process):
                result = collector.collect(args)
            self.assertTrue(result["target_reached"])
            self.assertEqual(len(requested), 2)
            self.assertTrue((Path(folder) / "manifest.json").exists())
            self.assertEqual(result["records"][0]["eligible_players"], 0)

    def test_collector_records_access_failure_without_retrying(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(Path(folder))
            with patch.object(sources.HttpCache, "get", side_effect=HTTPError("https://cohdb.com/matches", 403, "Forbidden", {}, None)) as get:
                result = collector.collect(args)
            self.assertEqual(get.call_count, 1)
            self.assertFalse(result["target_reached"])
            self.assertIn("403", result["stopped_reason"])

    def test_committed_capture_reproduces_reports_and_metadata_joins(self):
        folder = ROOT / "data/replays/cohorts/mechanized-1v1-2.5.6-2026-10-14"
        manifest = json.loads((folder / "manifest.json").read_text())
        datasets = []
        for record in manifest["records"]:
            if record["status"] != "collected":
                continue
            dataset = json.loads((folder / record["dataset"]).read_text())
            metadata = json.loads((folder / "metadata" / f"match-{record['match_id']}.json").read_text())
            self.assertEqual(dataset["match"]["match_id"], metadata["match_id"])
            players = {p["profile_id"]: p for p in dataset["players"]}
            self.assertEqual(set(players), {p["profile_id"] for p in metadata["players"]})
            for p in metadata["players"]:
                self.assertEqual((players[p["profile_id"]]["result"], players[p["profile_id"]]["rating_before"]),
                                 (p["result"], p["rating_before"]))
            datasets.append(dataset)
        self.assertTrue(manifest["target_reached"])
        self.assertEqual(len(datasets), manifest["collected_players"])
        for name in ("report.json", "report-first5.json"):
            saved = json.loads((folder / name).read_text())
            regenerated = report.analyze(datasets, manifest["scope"], saved["prefix_length"], saved["max_opener_seconds"])
            for key in ("counts", "ranked_exclusion_counts", "opener_exclusion_counts", "exploratory_openers", "ranked_openers"):
                self.assertEqual(regenerated[key], saved[key])
        validation = json.loads((folder / "validation-88336093.json").read_text())
        self.assertTrue(validation["exact_match"])
        self.assertEqual(validation["matched"], 53)

    def args(self, root):
        return Namespace(**self.scope, source="cohdb", game_build=50313, target=1, max_pages=3, max_downloads=3,
                         max_consecutive_missing=2, delay=0, metadata_day=[], metadata_file=[], metadata_url=None,
                         reader=Path("reader"), advisor_data=ROOT / "coh3_build_advisor_data.json", output_dir=root,
                         completed_before=None)


if __name__ == "__main__":
    unittest.main()
