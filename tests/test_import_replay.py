"""Single-replay identity, cancellation, and statistical eligibility checks."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("import_replay", ROOT / "scripts/import_replay.py")
importer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = importer
spec.loader.exec_module(importer)
spec = importlib.util.spec_from_file_location("check_replay_cohdb", ROOT / "scripts/check_replay_cohdb.py")
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


class ReplayImportTests(unittest.TestCase):
    def setUp(self):
        self.reader = json.loads((ROOT / "tests/fixtures/replay-reader-88366979.json").read_text())
        self.metadata = json.loads((ROOT / "data/replays/examples/match-88366979-metadata.json").read_text())
        self.profiles = json.loads((ROOT / "coh3_build_advisor_data.json").read_text())["profiles"]

    def dataset(self):
        return importer.normalize(self.reader, self.profiles, self.metadata)

    def test_metadata_joins_by_id_despite_different_player_order(self):
        players = {p["profile_id"]: p for p in self.dataset()["players"]}
        self.assertEqual(players[63169]["result"], "win")
        self.assertEqual(players[832443]["result"], "loss")
        self.assertEqual(players[63169]["profile_key"], "Wehrmacht|1v1|Breakthrough")
        self.assertEqual(players[832443]["profile_key"], "British|1v1|Heavy Armor")

    def test_cancelled_dingo_is_excluded_but_later_dingo_is_retained(self):
        british = next(p for p in self.dataset()["players"] if p["faction"] == "British")
        dingos = [a for a in british["actions"] if a["name"] == "Dingo Light Scout Car"]
        self.assertEqual([a["cancelled"] for a in dingos], [True, False])
        included = [a for a in british["build_sequence"] if a["name"] == "Dingo Light Scout Car"]
        self.assertEqual([a["tick"] for a in included], [1436])

    def test_suspect_buildings_are_retained_for_review_and_not_counted(self):
        british = next(p for p in self.dataset()["players"] if p["faction"] == "British")
        suspect = [a for a in british["actions"] if a["suspect"]]
        self.assertEqual(len(suspect), 2)
        included = {a["event_index"] for a in british["build_sequence"]}
        self.assertTrue(all(a["event_index"] not in included for a in suspect))

    def test_displayed_rating_and_custom_game_do_not_become_ranked_evidence(self):
        for player in self.dataset()["players"]:
            self.assertIsNotNone(player["displayed_rating"])
            self.assertIsNone(player["rating_before"])
            self.assertFalse(player["eligible_for_ranked_statistics"])
            self.assertFalse(player["quality_checks"]["ranked_game"])

    def test_mismatched_metadata_is_rejected(self):
        for field, value in (("match_id", 999), ("patch", "2.5.5"), ("mode", "4v4")):
            with self.subTest(field=field):
                metadata = copy.deepcopy(self.metadata)
                metadata[field] = value
                with self.assertRaises(ValueError):
                    importer.normalize(self.reader, self.profiles, metadata)
        for change in ({"profile_id": 999}, {"faction": "DAK"}):
            metadata = copy.deepcopy(self.metadata)
            metadata["players"][0].update(change)
            with self.assertRaises(ValueError):
                importer.normalize(self.reader, self.profiles, metadata)

    def test_unresolved_action_blocks_statistics_and_is_not_in_build(self):
        self.reader["match"]["game_type"] = "Automatch"
        for p in self.metadata["players"]:
            p["rating_before"] = 1200  # synthetic metadata for eligibility guard
        action = self.reader["players"][0]["actions"][0]
        action.update(name=None, name_resolved=False)
        player = self.dataset()["players"][0]
        self.assertFalse(player["eligible_for_ranked_statistics"])
        self.assertFalse(any(a["event_index"] == 0 for a in player["build_sequence"]))

    def test_ranked_evidence_requires_every_quality_check(self):
        self.reader["match"]["game_type"] = "Automatch"
        for p in self.metadata["players"]:
            p["rating_before"] = 1200  # synthetic, never saved to the real capture
        self.assertTrue(all(p["eligible_for_ranked_statistics"] for p in self.dataset()["players"]))
        self.reader["players"][0]["ai_takeover_at_tick"] = 100
        self.assertFalse(self.dataset()["players"][0]["eligible_for_ranked_statistics"])
        self.assertFalse(self.dataset()["players"][1]["eligible_for_ranked_statistics"])

    def test_ai_opponent_is_not_ranked_evidence_for_the_human_player(self):
        self.reader["match"]["game_type"] = "Automatch"
        for p in self.metadata["players"]:
            p["rating_before"] = 1200
        self.reader["players"][1]["human"] = False
        self.assertFalse(self.dataset()["players"][0]["eligible_for_ranked_statistics"])

    def test_out_of_order_actions_are_rejected(self):
        actions = self.reader["players"][0]["actions"]
        actions[0], actions[1] = actions[1], actions[0]
        with self.assertRaises(ValueError):
            self.dataset()

    def test_captured_cohdb_labels_match_the_complete_non_cancelled_timeline(self):
        capture = json.loads((ROOT / "tests/fixtures/cohdb-timed-labels-88366979.json").read_text())
        self.assertEqual(capture["match_id"], self.reader["match"]["match_id"])
        report = checker.compare(self.dataset(), {tuple(x) for x in capture["entries"]})
        self.assertTrue(report["exact_match"], report)


if __name__ == "__main__":
    unittest.main()
