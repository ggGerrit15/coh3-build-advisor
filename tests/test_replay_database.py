"""Database identity, provenance, evidence upgrades and transaction checks."""
import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import replay_database as database
from import_replay import normalize


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "replays.sqlite3"
        self.connection = database.connect(self.path, create=True)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.connection.close)
        path = ROOT / "data/replays/cohorts/mechanized-1600plus-1v1-2.5.6-2026-10-14/datasets/match-88314882.json"
        self.verified = json.loads(path.read_text())
        profiles = json.loads((ROOT / "coh3_build_advisor_data.json").read_text())["profiles"]
        self.unknown = normalize(dict(schema_version="coh3.replay-reader.v1", match=self.verified["match"],
            players=self.verified["players"], parser=self.verified["parser"], replay_sha256=self.verified["replay_sha256"]),
            profiles, source_url=self.verified["source_url"])

    def ingest(self, dataset, key="sample", provenance=None):
        return database.ingest(self.connection, [("match.json", dataset)], key, "upload", provenance or {})

    def test_same_match_and_file_reimports_are_idempotent_even_with_new_import_time(self):
        self.ingest(self.unknown)
        before = database.statistics(self.connection)["counts"]
        another = copy.deepcopy(self.unknown)
        another["imported_at"] = "a later processing time"
        result = self.ingest(another)
        self.assertEqual(result["new_matches"], 0)
        self.assertEqual(result["new_datasets"], 0)
        self.assertEqual(result["new_source_links"], 0)
        self.assertEqual(database.statistics(self.connection)["counts"], before)

    def test_duplicate_receipts_and_rerecordings_keep_one_set_of_actions(self):
        self.ingest(self.unknown)
        action_count = self.connection.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        other = copy.deepcopy(self.unknown)
        other["replay_sha256"] = "a" * 64
        self.ingest(other, key="second recording")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 1)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM replays").fetchone()[0], 2)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM actions").fetchone()[0], action_count)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM v_player_builds").fetchone()[0], 2)

    def test_user_rating_filter_never_becomes_a_verified_rating(self):
        self.ingest(self.unknown, provenance={"rating_filter": "1600+ ELO", "selected_by": "user"})
        stats = database.statistics(self.connection)
        self.assertEqual(stats["counts"]["verified_player_ratings"], 0)
        self.assertEqual(stats["counts"]["eligible_ladder_first8"], 0)
        self.assertTrue(all(r[0] is None for r in self.connection.execute("SELECT verified_rating_before FROM v_player_builds")))
        self.assertEqual(json.loads(self.connection.execute("SELECT provenance_json FROM sources").fetchone()[0])["rating_filter"], "1600+ ELO")

    def test_metadata_upgrade_preserves_unknown_observation_and_cannot_be_downgraded(self):
        self.ingest(self.unknown, key="without metadata")
        self.ingest(self.verified, key="verified metadata")
        stats = database.statistics(self.connection)["counts"]
        self.assertEqual((stats["matches"], stats["match_players"], stats["datasets"]), (1, 2, 2))
        self.assertEqual(stats["verified_player_ratings"], 2)
        self.ingest(self.unknown, key="later unknown upload")
        self.assertEqual(database.statistics(self.connection)["counts"]["verified_player_ratings"], 2)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM player_evidence WHERE rating_status='unknown'").fetchone()[0], 2)

    def test_conflicting_commands_roll_back_entire_source_batch(self):
        self.ingest(self.unknown)
        before = database.statistics(self.connection)["counts"]
        conflict = copy.deepcopy(self.unknown)
        # Changing the player name also changes the immutable replay core.
        conflict["players"][0]["name"] = "different identity"
        new = copy.deepcopy(self.unknown)
        new["match"]["match_id"] += 1
        new["replay_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "Conflicting replay"):
            database.ingest(self.connection, [("new.json", new), ("conflict.json", conflict)], "failed source", "upload", {})
        self.assertEqual(database.statistics(self.connection)["counts"], before)

    def test_conflicting_verified_rating_and_outcomes_are_rejected(self):
        self.ingest(self.verified)
        before = database.statistics(self.connection)["counts"]
        wrong_rating = copy.deepcopy(self.verified)
        wrong_rating["players"][0]["rating_before"] += 10
        with self.assertRaisesRegex(ValueError, "Conflicting verified ratings"):
            self.ingest(wrong_rating, key="bad ratings")
        wrong_result = copy.deepcopy(self.verified)
        for player in wrong_result["players"]:
            player["result"] = "loss" if player["result"] == "win" else "win"
        with self.assertRaisesRegex(ValueError, "Conflicting outcomes"):
            self.ingest(wrong_result, key="bad outcome")
        self.assertEqual(database.statistics(self.connection)["counts"], before)

    def test_changed_provenance_or_forged_quality_and_sequence_are_rejected(self):
        self.ingest(self.unknown, provenance={"batch": 1})
        with self.assertRaisesRegex(ValueError, "different provenance"):
            self.ingest(self.unknown, provenance={"batch": 2})
        for change in ("quality", "sequence"):
            forged = copy.deepcopy(self.unknown)
            if change == "quality":
                forged["players"][0]["quality_checks"]["ranked_game"] = True
            else:
                forged["players"][0]["build_sequence"][0] = dict(forged["players"][0]["build_sequence"][0])
                forged["players"][0]["build_sequence"][0]["pbgid"] += 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.ingest(forged, key=change)

    def test_commands_and_unlocks_keep_order_cancellations_and_flags(self):
        self.ingest(self.unknown)
        player = self.unknown["players"][0]
        actual = self.connection.execute("SELECT pbgid,tick FROM actions WHERE match_id=? AND profile_id=? AND build_position IS NOT NULL ORDER BY build_position", (self.unknown["match"]["match_id"], player["profile_id"])).fetchall()
        self.assertEqual([tuple(r) for r in actual], [(a["pbgid"], a["tick"]) for a in player["build_sequence"]])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM actions").fetchone()[0], sum(len(p["actions"]) for p in self.unknown["players"]))
        self.assertEqual(list(self.connection.execute("PRAGMA foreign_key_check")), [])
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_unrelated_database_is_never_initialized_or_modified(self):
        path = Path(self.temporary.name) / "other.sqlite3"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE preserve (value TEXT)")
            connection.execute("INSERT INTO preserve VALUES ('keep')")
        with self.assertRaises(ValueError):
            database.connect(path, create=True)
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute("SELECT value FROM preserve").fetchone()[0], "keep")
            self.assertEqual(connection.execute("PRAGMA application_id").fetchone()[0], 0)

    def test_committed_cohorts_import_once_and_preserve_every_profile(self):
        folder = ROOT / "data/replays/cohorts/mechanized-1600plus-1v1-2.5.6-2026-10-14"
        inputs = database.load_inputs([folder])
        self.assertEqual(len(inputs), 30)
        database.ingest(self.connection, inputs, "stronger", "cohort", {})
        stats = database.statistics(self.connection)["counts"]
        self.assertEqual(stats["matches"], 30)
        self.assertEqual(stats["match_players"], 60)
        self.assertEqual(stats["verified_player_ratings"], 60)
        self.assertEqual(database.ingest(self.connection, inputs, "stronger", "cohort", {})["new_datasets"], 0)


if __name__ == "__main__":
    unittest.main()
