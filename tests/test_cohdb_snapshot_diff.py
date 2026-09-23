import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "cohdb_snapshot_diff", "scripts/cohdb_snapshot_diff.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CoHDBSnapshotDiffTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "schema_version": "cohdb.snapshot.v1",
            "retrieved_at": "2026-09-22T18:13:39Z",
            "patch": {"id": "50313", "label": "2.5.6"},
            "battlegroups": [{"faction": "DAK", "selections": 100}],
        }

    def test_retrieval_timestamp_only_is_not_a_meaningful_change(self):
        candidate = {**self.snapshot, "retrieved_at": "2026-09-23T05:30:38Z"}
        self.assertFalse(MODULE.snapshots_meaningfully_differ(self.snapshot, candidate))

    def test_statistics_change_is_meaningful(self):
        candidate = {
            **self.snapshot,
            "retrieved_at": "2026-09-23T05:30:38Z",
            "battlegroups": [{"faction": "DAK", "selections": 101}],
        }
        self.assertTrue(MODULE.snapshots_meaningfully_differ(self.snapshot, candidate))

    def test_cli_keeps_existing_snapshot_when_only_timestamp_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "latest.json"
            candidate = root / "candidate.json"
            existing.write_text(json.dumps(self.snapshot), encoding="utf-8")
            candidate.write_text(
                json.dumps({**self.snapshot, "retrieved_at": "2026-09-23T05:30:38Z"}),
                encoding="utf-8",
            )

            old_main = MODULE.main
            old_argv = sys.argv
            try:
                sys.argv = [
                    "cohdb_snapshot_diff.py",
                    "--existing",
                    str(existing),
                    "--candidate",
                    str(candidate),
                ]
                self.assertEqual(MODULE.main(), 0)
            finally:
                MODULE.main = old_main
                sys.argv = old_argv

            self.assertFalse(candidate.exists())
            self.assertEqual(json.loads(existing.read_text(encoding="utf-8")), self.snapshot)


if __name__ == "__main__":
    unittest.main()
