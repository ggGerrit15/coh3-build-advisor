"""Synthetic metadata cases against the existing public replay fixture."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_replay import normalize
import replay_cohort as sources
import replay_database as database
import enrich_replay_database as enrichment


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.reader = json.loads((ROOT / "tests/fixtures/replay-reader-88366979.json").read_text())
        self.reader["players"][0]["battlegroup"]["name"] = "Mechanized Battlegroup"
        self.profiles = json.loads((ROOT / "coh3_build_advisor_data.json").read_text())["profiles"]
        self.unknown = normalize(self.reader, self.profiles)
        mid = self.reader["match"]["match_id"]
        races = {"British": 203852, "Wehrmacht": 137123}
        reports, members = [], []
        for i, p in enumerate(self.reader["players"]):
            shared = dict(matchhistory_id=mid, profile_id=p["profile_id"], race_id=races[p["faction"]], teamid=p["team"])
            reports.append(dict(shared, resulttype=i))
            members.append(dict(shared, oldrating=1600 + i * 100, newrating=1500 + i * 100, outcome=i))
        self.raw = dict(id=mid, matchtype_id=20, description="AUTOMATCH", matchhistoryreportresults=reports,
                        matchhistorymember=members, startgametime=1, completiontime=2)
        self.source = dict(url=f"https://coh3-api.reliclink.com/community/leaderboard/getRecentMatchHistoryByProfileId?title=coh3&profile_id={members[0]['profile_id']}", sha256="a" * 64)

    def metadata(self, raw=None, source=None):
        return sources.relic_history_metadata(raw or self.raw, self.reader, source or self.source)

    def test_relic_member_join_uses_profile_identity_and_oldrating(self):
        raw = copy.deepcopy(self.raw)
        raw["matchhistorymember"].reverse()
        metadata = self.metadata(raw)
        for i, player in enumerate(metadata["players"]):
            self.assertEqual(player["rating_before"], 1600 + i * 100)
        dataset = normalize(self.reader, self.profiles, metadata)
        self.assertEqual(dataset["match"]["match_type_resolution"]["kind"], "ladder_automatch")
        self.assertIn("relic_history", dataset["match"]["match_type_resolution"]["basis"])
        for p in dataset["players"]:
            self.assertEqual(database.evidence_status(dataset, p)[0], "verified_pre_match")
            self.assertEqual(database.evidence_status(dataset, p)[1], "observed_source")
        self.assertEqual(database.core_identity(dataset), database.core_identity(self.unknown))

    def test_missing_oldrating_never_uses_newrating(self):
        raw = copy.deepcopy(self.raw)
        del raw["matchhistorymember"][0]["oldrating"]
        metadata = self.metadata(raw)
        self.assertIsNone(metadata["players"][0]["rating_before"])
        dataset = normalize(self.reader, self.profiles, metadata)
        self.assertEqual(database.evidence_status(dataset, dataset["players"][0])[0], "unknown")

    def test_custom_history_cannot_become_verified_or_ranked(self):
        raw = dict(self.raw, description="CUSTOM", matchtype_id=0)
        metadata = self.metadata(raw)
        self.assertIsNone(metadata["players"][0]["rating_before"])
        dataset = normalize(self.reader, self.profiles, metadata)
        self.assertFalse(dataset["players"][0]["eligible_for_ranked_statistics"])
        self.assertEqual(database.evidence_status(dataset, dataset["players"][0])[0], "unverified")

    def test_member_report_identity_faction_team_outcome_and_duplicates_rejected(self):
        for change in ("member_match", "report_match", "member_player", "race", "team", "outcome", "duplicate", "missing"):
            raw = copy.deepcopy(self.raw)
            member = raw["matchhistorymember"][0]
            if change == "member_match": member["matchhistory_id"] += 1
            if change == "report_match": raw["matchhistoryreportresults"][0]["matchhistory_id"] += 1
            if change == "member_player": member["profile_id"] += 1
            if change == "race": member["race_id"] += 1
            if change == "team": member["teamid"] += 1
            if change == "outcome": member["outcome"] = 1 - member["outcome"]
            if change == "duplicate": raw["matchhistorymember"].append(member)
            if change == "missing": raw["matchhistorymember"].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.metadata(raw)

    def test_wrong_endpoint_platform_hash_or_requested_profile_rejected(self):
        for source in (dict(self.source, url=self.source["url"].replace("coh3-api.reliclink.com", "other.example")),
                       dict(self.source, url=self.source["url"].replace("title=coh3&", "title=coh3xbl&")),
                       dict(self.source, sha256="bad"),
                       dict(self.source, url=self.source["url"].rsplit("=", 1)[0] + "=999999999")):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.metadata(source=source)

    def test_daily_and_history_must_agree(self):
        daily = dict(self.raw, platform="steam", matchhistoryreportresults=[dict(r, matchhistorymember=m) for r, m in zip(self.raw["matchhistoryreportresults"], self.raw["matchhistorymember"])])
        source = dict(url="https://storage.coh3stats.com/matches/matches-1791849600.json", sha256="b" * 64)
        result, receipt = enrichment.enrich(self.unknown, [("relic_history", self.source, self.raw), ("daily", source, daily)], self.profiles)
        self.assertEqual(receipt["selected_kind"], "daily")
        self.assertEqual(receipt["corroborating_sources"], 2)
        bad = copy.deepcopy(self.raw)
        bad["matchhistorymember"][0]["oldrating"] += 1
        with self.assertRaisesRegex(ValueError, "Conflicting metadata"):
            enrichment.enrich(self.unknown, [("daily", source, daily), ("relic_history", self.source, bad)], self.profiles)

    def test_cli_enriches_without_duplicate_matches_and_verifies_capture_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            capture = root / "history.json"
            capture.write_text(json.dumps({"result": {"code": 0}, "matchHistoryStats": [self.raw]}))
            manifest = root / "captures.json"
            manifest.write_text(json.dumps({"sources": [{"url": self.source["url"], "file": capture.name, "sha256": hashlib.sha256(capture.read_bytes()).hexdigest()}]}))
            path = root / "research.sqlite3"
            connection = database.connect(path, create=True)
            database.ingest(connection, [("seed.json", self.unknown)], "seed", "upload", {})
            connection.close()
            for name in ("first", "second"):
                argv = ["enrich", "--database", str(path), "--captures", str(manifest), "--collection-source", "seed", "--source-key", "metadata", "--output-dir", str(root / name)]
                with patch.object(sys, "argv", argv): self.assertEqual(enrichment.main(), 0)
            connection = database.connect(path)
            try:
                counts = database.statistics(connection)["counts"]
                self.assertEqual((counts["matches"], counts["match_players"], counts["datasets"], counts["verified_player_ratings"]), (1, 2, 2, 2))
            finally:
                connection.close()
            capture.write_text("changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                enrichment.load_captures(manifest)


if __name__ == "__main__":
    unittest.main()
