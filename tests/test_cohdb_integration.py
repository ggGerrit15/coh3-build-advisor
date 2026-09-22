import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CoHDBIntegrationTests(unittest.TestCase):
    def test_snapshot_is_embedded_without_replacing_curated_profiles(self):
        snapshot = json.loads((ROOT / "data/cohdb/latest.json").read_text(encoding="utf-8"))
        advisor_data = json.loads((ROOT / "coh3_build_advisor_data.json").read_text(encoding="utf-8"))
        html = (ROOT / "index.html").read_text(encoding="utf-8")

        self.assertEqual(snapshot["patch"]["id"], "50313")
        self.assertEqual(len(snapshot["battlegroups"]), 32)
        self.assertEqual(len(snapshot["build_orders"]), 5)
        self.assertEqual(len(re.findall(r"const COHDB_SNAPSHOT=", html)), 1)
        self.assertIn("function cohdbComponent(p)", html)
        self.assertIn("function cohdbStatsSection(p)", html)
        self.assertIn("function smartRows(f,m,o,map,band,list=null)", html)
        self.assertIn("const COHDB_MIN_RATING_GAMES = 30", html)
        self.assertIn("Zu kleine Stichprobe", html)
        self.assertIn("do not influence the recommendation", html)
        self.assertIn("const COHDB_SNAPSHOT=", html)
        self.assertIn('advisorSectionHeader("Recommendation"', html)
        self.assertIn('advisorSectionHeader("Statistics"', html)

        # The import integration must not turn the curated profile store into
        # a generated replacement. It remains present and keeps its size.
        self.assertIn("const PROFILES=", html)
        self.assertEqual(len(advisor_data["profiles"]), 112)


if __name__ == "__main__":
    unittest.main()
