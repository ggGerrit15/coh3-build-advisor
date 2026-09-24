import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json_constant(html, name):
    marker = f"const {name}="
    start = html.find(marker)
    if start < 0:
        raise AssertionError(f"Missing {marker} in index.html")
    value, _ = json.JSONDecoder().raw_decode(html[start + len(marker):])
    return value


class CoHDBIntegrationTests(unittest.TestCase):
    def test_snapshot_is_embedded_without_replacing_curated_profiles(self):
        snapshot = json.loads((ROOT / "data/cohdb/latest.json").read_text(encoding="utf-8"))
        advisor_data = json.loads((ROOT / "coh3_build_advisor_data.json").read_text(encoding="utf-8"))
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertEqual(snapshot.get("schema_version"), "cohdb.snapshot.v1")
        self.assertTrue(snapshot.get("patch", {}).get("id"))
        self.assertTrue(snapshot.get("patch", {}).get("label"))
        self.assertGreaterEqual(len(snapshot.get("battlegroups", [])), 32)
        self.assertGreaterEqual(len(snapshot.get("build_orders", [])), 4)

        # CoHDB has many rows because each mode and rating scope is stored
        # separately. Verify required scopes instead of assuming one row per BG.
        modes = ("all", "1v1", "2v2", "3v3", "4v4")
        ratings = (
            "balanced_all",
            "avg_under_1000",
            "avg_1000_1200",
            "avg_1200_1400",
            "avg_1400_1600",
            "avg_1600_1800",
            "avg_1800_plus",
        )
        actual_scopes = {
            (row.get("mode"), row.get("rating_filter"))
            for row in snapshot.get("coverage", {}).get("battlegroups", [])
            if row.get("map", "all") == "all" and row.get("opponent", "all") == "all"
        }
        self.assertTrue(set((mode, rating) for mode in modes for rating in ratings) <= actual_scopes)

        embedded = read_json_constant(html, "COHDB_SNAPSHOT")
        self.assertEqual(embedded, snapshot)
        profiles = read_json_constant(html, "PROFILES")
        self.assertEqual(len(profiles), len(advisor_data.get("profiles", [])))
        self.assertGreater(len(profiles), 0)

        self.assertEqual(len(re.findall(r"const COHDB_SNAPSHOT=", html)), 1)
        self.assertIn("function cohdbComponent(p)", html)
        self.assertIn("function cohdbStatsSection(p)", html)
        self.assertRegex(html, r"function smartRows\([^)]*\)")
        self.assertIn("'All Modes': 'all'", html)
        self.assertNotIn('id="maptype"', html)
        self.assertNotIn('id="rmap"', html)


if __name__ == "__main__":
    unittest.main()
