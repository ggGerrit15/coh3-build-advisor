"""Offline batch import: truthful metadata, duplicate/conflict handling and partial failures."""
from argparse import Namespace
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import import_local_replays as local
import import_replay as single


class LocalReplayTests(unittest.TestCase):
    def setUp(self):
        self.reader = json.loads((ROOT / "tests/fixtures/replay-reader-88366979.json").read_text())
        self.reader["players"][0]["battlegroup"]["name"] = "Mechanized Battlegroup"
        self.metadata = json.loads((ROOT / "data/replays/examples/match-88366979-metadata.json").read_text())
        self.metadata["players"][0]["rating_before"] = 1600

    def args(self, folder):
        root = Path(folder)
        input_dir = root / "input files"
        input_dir.mkdir(exist_ok=True)
        (input_dir / "first replay.rec").write_bytes(b"test input")
        reader_path = root / "reader"
        reader_path.write_bytes(b"reader placeholder; mocked in tests")
        return Namespace(inputs=[input_dir], recursive=False, max_files=200, reader=reader_path,
            metadata_dir=None, advisor_data=ROOT / "coh3_build_advisor_data.json", output_dir=root / "output",
            patch="2.5.6", faction="Wehrmacht", battlegroup="Mechanized", mode="1v1")

    def metadata_folder(self, args, metadata):
        args.metadata_dir = args.output_dir.parent / "metadata"
        args.metadata_dir.mkdir()
        (args.metadata_dir / "match-88366979.json").write_text(json.dumps(metadata))

    def test_without_metadata_imports_commands_and_keeps_results_and_elo_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            with patch.object(local, "read_replay", return_value=self.reader):
                manifest = local.import_batch(args)
            self.assertEqual(manifest["import_counts"]["imported"], 1)
            self.assertEqual(manifest["attempted_downloads"], 0)
            dataset = json.loads((args.output_dir / manifest["records"][0]["dataset"]).read_text())
            self.assertTrue(any(p["build_sequence"] for p in dataset["players"]))
            for p in dataset["players"]:
                self.assertIsNone(p["rating_before"])
                self.assertIsNone(p["result"])
                self.assertFalse(p["eligible_for_ranked_statistics"])
            report = json.loads((args.output_dir / "report-first5.json").read_text())
            self.assertEqual(report["counts"]["matches"], 1)
            self.assertEqual(report["counts"]["with_pre_match_rating"], 0)
            self.assertEqual(report["counts"]["ranked_eligible_complete_openers"], 0)
            self.assertEqual(json.loads((args.output_dir / "candidates.json").read_text())["candidates"], [])
            self.assertIn("unknown", (args.output_dir / "summary.md").read_text())
            self.assertIn("Local files: 1", (args.output_dir / "report.md").read_text())

    def test_metadata_joins_by_match_and_profile_id_and_is_preserved_with_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            self.metadata["players"].reverse()
            self.metadata_folder(args, self.metadata)
            with patch.object(local, "read_replay", return_value=self.reader):
                manifest = local.import_batch(args)
            record = manifest["records"][0]
            dataset = json.loads((args.output_dir / record["dataset"]).read_text())
            by_id = {p["profile_id"]: p for p in dataset["players"]}
            self.assertEqual(by_id[63169]["result"], "win")
            # No bare metadata rating turns the fixture's Custom game into verified ladder evidence.
            self.assertFalse(by_id[63169]["eligible_for_ranked_statistics"])
            self.assertTrue(record["metadata_supplied"])
            self.assertEqual(len(record["metadata_sha256"]), 64)
            self.assertEqual(json.loads((args.output_dir / "metadata/match-88366979.json").read_text()), self.metadata)

    def test_wrong_match_metadata_is_rejected_without_losing_other_valid_files(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            (args.inputs[0] / "second.rec").write_bytes(b"second")
            bad_metadata = copy.deepcopy(self.metadata)
            bad_metadata["match_id"] = 999
            self.metadata_folder(args, bad_metadata)
            other = copy.deepcopy(self.reader)
            other["match"]["match_id"] = 88366980
            other["replay_sha256"] = "another replay"
            with patch.object(local, "read_replay", side_effect=[self.reader, other]):
                manifest = local.import_batch(args)
            self.assertEqual(manifest["import_counts"]["errors"], 1)
            self.assertEqual(manifest["import_counts"]["imported"], 1)
            self.assertFalse(manifest["target_reached"])
            self.assertIn("Metadata match ID", manifest["records"][0]["error"])
            self.assertTrue((args.output_dir / "summary.md").exists())

    def test_duplicate_files_and_identical_rerecordings_do_not_count_twice(self):
        for new_hash in (False, True):
            with self.subTest(new_hash=new_hash), tempfile.TemporaryDirectory() as folder:
                args = self.args(folder)
                (args.inputs[0] / "second.rec.gz").write_bytes(b"second file")
                duplicate = copy.deepcopy(self.reader)
                if new_hash:
                    duplicate["replay_sha256"] = "another recording hash"
                with patch.object(local, "read_replay", side_effect=[self.reader, duplicate]):
                    manifest = local.import_batch(args)
                self.assertEqual(manifest["import_counts"]["duplicates"], 1)
                self.assertEqual(manifest["import_counts"]["imported"], 1)
                self.assertEqual(manifest["collected_players"], 1)
                self.assertEqual(len(list((args.output_dir / "datasets").glob("*.json"))), 1)

    def test_conflicting_same_match_is_explicit_error_and_original_stays(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            (args.inputs[0] / "second.rec").write_bytes(b"second")
            conflict = copy.deepcopy(self.reader)
            conflict["replay_sha256"] = "other"
            conflict["players"][0]["actions"][0]["pbgid"] += 1
            with patch.object(local, "read_replay", side_effect=[self.reader, conflict]):
                manifest = local.import_batch(args)
            self.assertEqual(manifest["import_counts"]["errors"], 1)
            self.assertIn("Conflicting recordings", manifest["records"][1]["error"])
            self.assertEqual(manifest["import_counts"]["imported"], 1)

    def test_bad_file_is_recorded_and_following_file_is_processed(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            (args.inputs[0] / "second.rec").write_bytes(b"second")
            failure = subprocess.CalledProcessError(1, ["reader"], stderr="Invalid replay")
            with patch.object(local, "read_replay", side_effect=[failure, self.reader]) as read:
                manifest = local.import_batch(args)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(manifest["stopped_reason"], "completed_with_errors")
            self.assertEqual(manifest["records"][0]["error"], "Invalid replay")

    def test_different_patch_retains_dataset_without_contaminating_scope_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            other = copy.deepcopy(self.reader)
            other["match"]["patch"] = "2.5.5"
            with patch.object(local, "read_replay", return_value=other):
                manifest = local.import_batch(args)
            self.assertEqual(manifest["import_counts"]["outside_scope"], 1)
            self.assertTrue((args.output_dir / manifest["records"][0]["dataset"]).exists())
            self.assertEqual(json.loads((args.output_dir / "report.json").read_text())["counts"]["matches"], 0)
            self.assertIn("[GER] Miau", (args.output_dir / "summary.md").read_text())

    def test_discovery_supports_spaces_case_gzip_subfolders_and_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            nested = args.inputs[0] / "subfolder"
            nested.mkdir()
            (nested / "second.REC.GZ").write_bytes(b"gzip")
            (nested / "ignore.txt").write_text("ignored")
            self.assertEqual(len(local.discover(args.inputs)), 1)
            self.assertEqual(len(local.discover(args.inputs, recursive=True)), 2)
            self.assertEqual(len(local.discover(args.inputs + [args.inputs[0] / "first replay.rec"])), 1)
            with self.assertRaises(ValueError):
                local.discover(args.inputs, recursive=True, max_files=1)
            with self.assertRaises(ValueError):
                local.discover([nested / "ignore.txt"])

    def test_missing_match_or_player_ids_remain_reviewable_without_false_deduplication(self):
        for missing in ("match", "profile"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as folder:
                args = self.args(folder)
                (args.inputs[0] / "second.rec").write_bytes(b"second")
                first, second = copy.deepcopy(self.reader), copy.deepcopy(self.reader)
                second["match"]["match_id"] += 1
                second["replay_sha256"] = "different recording"
                second["players"][0]["actions"][0]["pbgid"] += 1
                for reader in (first, second):
                    if missing == "match":
                        reader["match"]["match_id"] = None
                    else:
                        reader["players"][0]["profile_id"] = None
                with patch.object(local, "read_replay", side_effect=[first, second]):
                    manifest = local.import_batch(args)
                self.assertEqual(manifest["import_counts"]["imported"], 2)
                self.assertEqual(manifest["import_counts"]["unidentified"], 2)
                self.assertEqual(manifest["import_counts"]["errors"], 0)
                self.assertTrue(all(r["status"] == "unidentified" for r in manifest["records"]))
                self.assertEqual(json.loads((args.output_dir / "report.json").read_text())["counts"]["matches"], 0)
                self.assertEqual(len(list((args.output_dir / "datasets").glob("*.json"))), 2)

    def test_existing_output_and_missing_reader_fail_before_import(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            args.output_dir.mkdir()
            sentinel = args.output_dir / "preserve.txt"
            sentinel.write_text("keep me")
            with patch.object(local, "read_replay") as read, self.assertRaises(ValueError):
                local.import_batch(args)
            read.assert_not_called()
            self.assertEqual(sentinel.read_text(), "keep me")
            args.reader.unlink()
            with self.assertRaisesRegex(ValueError, "reader missing"):
                local.import_batch(args)

    def test_interruption_saves_successes_and_reports_without_claiming_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            (args.inputs[0] / "second.rec").write_bytes(b"second")
            with patch.object(local, "read_replay", side_effect=[self.reader, KeyboardInterrupt]):
                manifest = local.import_batch(args)
            self.assertEqual(manifest["stopped_reason"], "interrupted")
            self.assertFalse(manifest["target_reached"])
            self.assertEqual(manifest["import_counts"]["imported"], 1)
            self.assertTrue((args.output_dir / "summary.md").exists())

    def test_reader_uses_argument_list_timeout_and_input_size_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            args = self.args(folder)
            replay = args.inputs[0] / "first replay.rec"
            with patch.object(single.subprocess, "run", return_value=Namespace(stdout=json.dumps(self.reader))) as run:
                self.assertEqual(single.read_replay(replay, args.reader), self.reader)
            run.assert_called_once_with([str(args.reader.resolve()), str(replay.resolve())], check=True, capture_output=True, text=True, timeout=120)
            with replay.open("wb") as file:
                file.truncate(128 * 1024 * 1024 + 1)
            with patch.object(single.subprocess, "run") as run, self.assertRaises(ValueError):
                single.read_replay(replay, args.reader)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
