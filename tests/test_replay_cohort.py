"""Source identity, bounded collection, deduplication and ordered-cohort tests."""
import copy
from argparse import Namespace
from datetime import datetime, timezone
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
import replay_match_type as match_types


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

    def test_build_preview_rejects_only_two_complete_recognized_other_bgs(self):
        row = {"profile_ids": [63169, 832443]}
        def page(first, second):
            return f'''<title>cohdb – Match 88366979</title><a href="/players/63169">Miau</a>
            <span data-tooltip-content-value="0:01 &amp;mdash; Selects {first}"></span>
            <a href="/players/832443">British</a>
            <span data-tooltip-content-value="0:02 &amp;mdash; Selects {second}"></span>'''
        other = sources.build_preview(page("Breakthrough Battlegroup", "Heavy Armor Battlegroup"), row, "Mechanized", self.profiles)
        self.assertTrue(other["both_battlegroups_recognized"])
        self.assertFalse(other["possible_target"])
        target = sources.build_preview(page("Mechanized Battlegroup", "Heavy Armor Battlegroup"), row, "Mechanized", self.profiles)
        self.assertTrue(target["possible_target"])
        unknown = sources.build_preview(page("Breakthrough Battlegroup", "Unknown BG"), row, "Mechanized", self.profiles)
        self.assertTrue(unknown["possible_target"])
        self.assertFalse(unknown["both_battlegroups_recognized"])
        target_known = sources.build_preview(page("Breakthrough Battlegroup", "Unknown BG"), row, "Mechanized", self.profiles, [63169])
        self.assertFalse(target_known["possible_target"])
        self.assertTrue(target_known["required_battlegroups_recognized"])

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

    def api_dataset(self):
        raw = dict(self.raw, platform="steam")
        metadata = sources.stats_metadata(raw, self.reader, {"url": "https://storage.coh3stats.com/matches/matches-1791849600.json"})
        return normalize(self.reader, self.profiles, metadata), metadata

    def test_quick_match_is_ladder_rated_only_with_the_verified_api_reference(self):
        dataset, metadata = self.api_dataset()
        resolution = dataset["match"]["match_type_resolution"]
        self.assertEqual(dataset["match"]["game_type"], "Custom")
        self.assertEqual(resolution["kind"], "ladder_automatch")
        self.assertEqual(resolution["queue_name"], "Quick Match")
        self.assertTrue(resolution["raw_disagreement"])
        self.assertEqual(len(resolution["leaderboards"]), 2)
        self.assertTrue(dataset["players"][0]["eligible_for_ranked_statistics"])
        del metadata["classification_reference"]
        unproved = normalize(self.reader, self.profiles, metadata)
        self.assertFalse(unproved["players"][0]["eligible_for_ranked_statistics"])

    def test_invalid_or_incomplete_api_reference_cannot_promote_a_replay(self):
        _, metadata = self.api_dataset()
        altered = copy.deepcopy(metadata)
        altered["classification_reference"]["sha256"] = "wrong"
        with self.assertRaises(ValueError):
            normalize(self.reader, self.profiles, altered)
        altered = copy.deepcopy(metadata)
        altered["players"] = altered["players"][:1]
        with self.assertRaises(ValueError):
            normalize(self.reader, self.profiles, altered)
        altered = copy.deepcopy(metadata)
        altered["source"]["url"] = "https://other.example/matches.json"
        self.assertFalse(normalize(self.reader, self.profiles, altered)["players"][0]["eligible_for_ranked_statistics"])

    def test_definition_scope_and_non_ladder_types_are_respected(self):
        _, metadata = self.api_dataset()
        reader = copy.deepcopy(self.reader)
        reader["match"]["game_build"] = 50314
        self.assertFalse(normalize(reader, self.profiles, metadata)["players"][0]["eligible_for_ranked_statistics"])
        reader["match"]["game_type"] = "Automatch"
        metadata["source_record"]["matchtype_id"] = 5
        self.assertFalse(normalize(reader, self.profiles, metadata)["players"][0]["eligible_for_ranked_statistics"])

    def test_target_rating_window_uses_verified_pre_match_values_and_exclusive_max(self):
        dataset = self.dataset()
        scope = dict(self.scope, min_player_rating=1600, max_player_rating=1800)
        for value, expected in ((1599, 0), (1600, 1), (1799, 1), (1800, 0), (None, 0)):
            dataset["players"][0]["rating_before"] = value
            dataset["players"][0]["displayed_rating"] = 2000
            self.assertEqual(len(sources.target_players(dataset, scope)), expected)

    def test_coarse_listing_rating_cannot_substitute_for_target_player_elo(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "daily.json"
            other = copy.deepcopy(self.raw)
            other["id"] += 1
            other["matchhistoryreportresults"][1]["matchhistorymember"]["oldrating"] = 1700
            path.write_text(json.dumps({"matches": [dict(self.raw, platform="steam"), dict(other, platform="steam")]}))
            args = self.args(root)
            args.min_player_rating, args.listing_rating = 1600, "min:1600"
            args.metadata_file, args.metadata_url = [path], "https://storage.coh3stats.com/matches/matches-1791849600.json"
            requested = []
            def get(_, url, limit=0):
                requested.append(url)
                return self.listing().encode() if "/matches?" in url else b"replay"
            with patch.object(sources.HttpCache, "get", get), patch.object(collector.subprocess, "run", return_value=Namespace(stdout=json.dumps(self.reader))):
                result = collector.collect(args)
            self.assertIn("rating=min%3A1600", requested[0])
            self.assertEqual(result["collected_players"], 0)
            self.assertEqual(result["records"][0]["status"], "outside_player_rating")

    def test_live_definition_and_direct_match_receipt_support_type20_ladder(self):
        definitions, provenance = match_types.reference()
        raw = json.loads((ROOT / "data/replays/reference/direct-api-match-88335815.json").read_text())
        self.assertTrue(raw["daily_values_match_direct_api"])
        self.assertEqual((raw["matchtype_id"], raw["replay_auto_byte"]), (20, 0))
        self.assertTrue(any(l["isranked"] == 1 and any(m["matchtype_id"] == 20 and m["race_id"] == 137123
                                                       for m in l["leaderboardmap"]) for l in definitions["leaderboards"]))
        self.assertIn(50313, provenance["applicable_game_builds"])

    def test_preview_cannot_use_ratings_from_a_different_player_roster(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            wrong_roster = copy.deepcopy(self.raw)
            wrong_roster["matchhistoryreportresults"][0]["profile_id"] = 9999
            other = copy.deepcopy(self.raw)
            other["id"] += 1
            other["matchhistoryreportresults"][1]["matchhistorymember"]["oldrating"] = 1700
            path = root / "daily.json"
            path.write_text(json.dumps({"matches": [wrong_roster, other]}))
            args = self.args(root)
            args.min_player_rating, args.preview_builds, args.max_previews = 1600, True, 3
            args.metadata_file, args.metadata_url = [path], "https://storage.coh3stats.com/matches/matches-1791849600.json"
            def get(_, url, limit=0):
                if "/matches?" in url:
                    return self.listing().encode()
                if url.endswith("/builds"):
                    return b'<title>cohdb - Match 88366979</title>'
                return b"replay"
            with patch.object(sources.HttpCache, "get", get), patch.object(collector.subprocess, "run", return_value=Namespace(stdout=json.dumps(self.reader))):
                result = collector.collect(args)
            self.assertEqual(result["attempted_downloads"], 1)
            self.assertEqual(result["records"][0]["status"], "import_error")
            self.assertIn("player", result["records"][0]["error"].lower())

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

    def test_missing_completion_date_does_not_end_the_date_window(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(Path(folder))
            args.completed_after, args.completed_before = "2026-10-07", "2026-10-14"
            unknown_date = self.listing(7283961).replace('title="October 13, 2026, 11:59 PM UTC"', '')
            def get(_, url, limit=0):
                return (unknown_date + self.listing()).encode() if "/matches?" in url else b"replay"
            with patch.object(sources.HttpCache, "get", get), patch.object(collector.subprocess, "run", return_value=Namespace(stdout=json.dumps(self.reader))):
                result = collector.collect(args)
            self.assertTrue(result["target_reached"])
            self.assertEqual(result["records"][0]["status"], "missing_completion_date")
            self.assertEqual(result["attempted_downloads"], 1)

    def test_preview_exclusions_save_downloads_and_positive_preview_keeps_binary_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(Path(folder))
            args.preview_builds, args.max_previews = True, 3
            requested = []
            def get(_, url, limit=0):
                requested.append(url)
                if "/matches?" in url:
                    return (self.listing(7283961) + self.listing()).encode()
                if url.endswith("/builds"):
                    bg = "Breakthrough" if "7283961" in url else "Mechanized"
                    return f'''<title>cohdb – Match 88366979</title><a href="/players/63169">Wehr</a>
                    <span data-tooltip-content-value="0:01 &amp;mdash; Selects {bg} Battlegroup"></span>
                    <a href="/players/832443">British</a>
                    <span data-tooltip-content-value="0:02 &amp;mdash; Selects Heavy Armor Battlegroup"></span>'''.encode()
                return b"replay"
            with patch.object(sources.HttpCache, "get", get), patch.object(collector.subprocess, "run", return_value=Namespace(stdout=json.dumps(self.reader))) as reader:
                result = collector.collect(args)
            self.assertTrue(result["target_reached"])
            self.assertEqual(result["checked_build_previews"], 2)
            self.assertEqual(result["records"][0]["status"], "preview_other_battlegroups")
            self.assertEqual(result["records"][1]["status"], "collected")
            self.assertTrue(result["records"][1]["preview"]["possible_target"])
            self.assertIn("preview_sha256", result["records"][1])
            self.assertEqual(reader.call_count, 1)
            self.assertEqual(sum("/file?" in url for url in requested), 1)
            self.assertEqual(result["records"][1]["eligible_players"], 0)

    def verify_capture(self, name):
        folder = ROOT / "data/replays/cohorts" / name
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
            if manifest["scope"].get("min_player_rating") is not None:
                targets = sources.target_players(dataset, manifest["scope"])
                self.assertTrue(targets)
                self.assertTrue(all(p["rating_before"] >= manifest["scope"]["min_player_rating"] for p in targets))
                self.assertEqual(dataset["match"]["match_type_resolution"]["kind"], "ladder_automatch")
                self.assertEqual(dataset["match"]["game_build"], manifest["discovery"]["game_build"])
                self.assertEqual(record["preview"]["match_id"], record["match_id"])
                day = datetime.fromtimestamp(dataset["match_metadata"]["completiontime"], timezone.utc).date().isoformat()
                self.assertGreaterEqual(day, manifest["discovery"]["completed_after"])
                self.assertLess(day, manifest["discovery"]["completed_before"])
                receipts = {(s["url"], s["sha256"]) for s in manifest["metadata_sources"]}
                self.assertIn((metadata["source"]["url"], metadata["source"]["sha256"]), receipts)
            datasets.append(dataset)
        self.assertTrue(manifest["target_reached"])
        self.assertEqual(len(datasets), manifest["collected_players"])
        for name in ("report.json", "report-first5.json"):
            saved = json.loads((folder / name).read_text())
            regenerated = report.analyze(datasets, manifest["scope"], saved["prefix_length"], saved["max_opener_seconds"])
            for key in ("counts", "ranked_exclusion_counts", "opener_exclusion_counts", "exploratory_openers", "ranked_openers"):
                self.assertEqual(regenerated[key], saved[key])
        return folder

    def test_committed_capture_reproduces_reports_and_metadata_joins(self):
        folder = self.verify_capture("mechanized-1v1-2.5.6-2026-10-14")
        validation = json.loads((folder / "validation-88336093.json").read_text())
        self.assertTrue(validation["exact_match"])
        self.assertEqual(validation["matched"], 53)

    def test_stronger_capture_reproduces_reports_and_verified_target_elo(self):
        folder = self.verify_capture("mechanized-1600plus-1v1-2.5.6-2026-10-14")
        validation = json.loads((folder / "validation-88314882.json").read_text())
        self.assertTrue(validation["exact_match"])
        self.assertEqual(validation["matched"], 27)

    def args(self, root):
        return Namespace(**self.scope, source="cohdb", game_build=50313, target=1, max_pages=3, max_downloads=3,
                         max_consecutive_missing=2, delay=0, metadata_day=[], metadata_file=[], metadata_url=None,
                         reader=Path("reader"), advisor_data=ROOT / "coh3_build_advisor_data.json", output_dir=root,
                         completed_before=None)


if __name__ == "__main__":
    unittest.main()
