"""Candidate export checks: player dependence, identity, actual branches and exclusions."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import export_replay_candidates as candidates

CAPTURE = ROOT / "data/replays/cohorts/mechanized-1600plus-1v1-2.5.6-2026-10-14"


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.dataset = json.loads((CAPTURE / "datasets/match-88314882.json").read_text())
        self.scope = json.loads((CAPTURE / "manifest.json").read_text())["scope"]

    def game(self, mid, pid, alternative=False):
        dataset = copy.deepcopy(self.dataset)
        dataset["match"]["match_id"] = mid
        player = next(p for p in dataset["players"] if p["faction"] == "Wehrmacht")
        player["profile_id"] = pid
        if alternative:
            player["build_sequence"][0].update(pbgid=168613, name="Pioneer Squad")
        return dataset

    def test_frequent_player_does_not_count_as_multiple_distinct_players(self):
        games = [self.game(100 + i, 10, alternative=i >= 4) for i in range(6)]
        games += [self.game(200, 20), self.game(201, 30, alternative=True)]
        export = candidates.build_export(games, self.scope)
        core = export["candidates"][0]
        self.assertEqual(core["support"]["games"], 5)
        self.assertEqual(core["support"]["unique_players"], 2)
        self.assertAlmostEqual(core["support"]["game_frequency"], 5 / 8)
        self.assertAlmostEqual(core["support"]["equal_player_frequency"], (4 / 6 + 1 + 0) / 3)
        removed = core["support"]["without_largest_contributor"]
        self.assertEqual((removed["games"], removed["population_games"]), (1, 2))
        self.assertAlmostEqual(removed["game_frequency"], .5)
        self.assertAlmostEqual(sum(c["support"]["equal_player_frequency"] for c in export["candidates"]), 1)

    def test_continuations_are_observed_whole_sequences_not_positional_majorities(self):
        games = [self.game(100, 10), self.game(101, 20), self.game(102, 30, alternative=True)]
        player = next(p for p in games[1]["players"] if p["faction"] == "Wehrmacht")
        player["build_sequence"][5], player["build_sequence"][6] = player["build_sequence"][6], player["build_sequence"][5]
        export = candidates.build_export(games, self.scope)
        for core in export["candidates"]:
            self.assertEqual(core["recommendation_status"], "observed_only")
            for branch in core["followups"]:
                self.assertEqual(branch["sequence"][:5], core["sequence"])
                for ref in branch["match_players"]:
                    dataset = next(g for g in games if g["match"]["match_id"] == ref["match_id"])
                    player = next(p for p in dataset["players"] if p["profile_id"] == ref["profile_id"])
                    self.assertEqual(branch["sequence"], candidates.sequence(player["build_sequence"][:8]))
        self.assertEqual(len(export["candidates"][0]["followups"]), 2)

    def test_uncertain_longer_window_retains_short_core_with_explicit_exclusion(self):
        uncertain = json.loads((CAPTURE / "datasets/match-88161475.json").read_text())
        export = candidates.build_export([uncertain], self.scope)
        core = export["candidates"][0]
        self.assertEqual(core["support"]["games"], 1)
        self.assertEqual(core["usable_followup_games"], 0)
        self.assertEqual(core["followups"], [])
        self.assertIn("uncertain_opener_command", core["excluded_followups"][0]["reasons"])
        self.assertIsNone(core["support"]["without_largest_contributor"]["game_frequency"])

    def test_unverified_custom_record_cannot_enter_candidate_export(self):
        dataset = self.game(100, 10)
        player = next(p for p in dataset["players"] if p["faction"] == "Wehrmacht")
        player["quality_checks"]["ranked_game"] = False
        player["eligible_for_ranked_statistics"] = False
        export = candidates.build_export([dataset], self.scope)
        self.assertEqual(export["candidates"], [])
        self.assertEqual(export["core_counts"]["matches"], 1)
        self.assertEqual(export["ranked_exclusion_counts"]["ranked_game"], 1)

    def test_strata_stay_separate_and_duplicate_recording_is_counted_once(self):
        a, b, c = [self.game(100 + i, 10 + i) for i in range(3)]
        next(p for p in b["players"] if p["faction"] == "Wehrmacht")["rating_before"] = 1700
        next(p for p in c["players"] if p["faction"] == "Wehrmacht")["opponent_factions"] = ["British"]
        export = candidates.build_export([a, b, c, a], self.scope)
        self.assertEqual(len(export["populations"]), 3)
        self.assertEqual(len(export["candidates"]), 3)
        self.assertEqual(export["core_counts"]["duplicates_ignored"], 1)
        self.assertTrue(all(core["support"]["games"] == 1 for core in export["candidates"]))

    def test_invalid_windows_and_collection_path_escape_are_rejected(self):
        for core, followup in [(0, 8), (8, 8), (9, 8), (5, 31)]:
            with self.subTest(core=core, followup=followup), self.assertRaises(ValueError):
                candidates.build_export([], self.scope, core, followup)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text(json.dumps({"records": [{"status": "collected", "dataset": "../outside.json"}]}))
            with self.assertRaises(ValueError):
                candidates.load_collection(root)

    def test_committed_export_reproduces_with_manifest_and_dataset_hashes(self):
        datasets, scope, provenance = candidates.load_collection(CAPTURE)
        export = candidates.build_export(datasets, scope)
        export["provenance"] = provenance
        saved = json.loads((CAPTURE / "candidates.json").read_text())
        for result in (export, saved):
            result.pop("generated_at")
        self.assertEqual(export, saved)
        self.assertEqual(export["core_counts"]["ranked_eligible_complete_openers"], 30)
        self.assertEqual(export["followup_counts"]["ranked_eligible_complete_openers"], 29)
        self.assertEqual(sum(c["support"]["games"] for c in export["candidates"]), 30)
        self.assertEqual(sum(c["usable_followup_games"] for c in export["candidates"]), 29)
        self.assertEqual(len(provenance["datasets"]), 30)
        self.assertEqual(provenance["manifest_sha256"], hashlib.sha256((CAPTURE / "manifest.json").read_bytes()).hexdigest())
        self.assertEqual(candidates.markdown(export), (CAPTURE / "candidates.md").read_text())
        self.assertIsNone(export["starting_units"])
        self.assertFalse(export["frontend_integration"])
        self.assertTrue(all(c["recommendation_status"] == "observed_only" for c in export["candidates"]))


if __name__ == "__main__":
    unittest.main()
