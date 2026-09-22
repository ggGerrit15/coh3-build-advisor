import importlib.util
import sys
import unittest


SPEC = importlib.util.spec_from_file_location("import_cohdb", "scripts/import_cohdb.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


PATCH = {"label": "2.5.6", "id": "50313", "url": "https://cohdb.com/battlegroups?patch=50313"}


class CoHDBImporterTests(unittest.TestCase):
    def test_latest_patch_discovery(self):
        html = '<a href="/battlegroups?patch=50313">2.5.6 (latest)</a>'
        self.assertEqual(MODULE.discover_latest_patch(html, "https://cohdb.com/battlegroups"), PATCH)

    def test_record_validation(self):
        record = MODULE.parse_record("Kriegsmarine Battlegroup Record 11–23 Win% 32.4% Adjusted − 17.90 Selections 34")
        self.assertEqual(record["wins"], 11)
        self.assertEqual(record["losses"], 23)
        self.assertEqual(record["selections"], 34)
        self.assertAlmostEqual(record["win_rate"], 32.4)

    def test_battlegroup_page_parser_assigns_rows_to_factions(self):
        parts = []
        for faction in MODULE.FACTIONS:
            parts.append(f'<span class="font-semibold text-sm">{faction}</span>')
            for index in range(7):
                parts.append(
                    '<div class="bg-light border-lighter">'
                    f'<img alt="{faction} Battlegroup {index}" src="icon.webp">'
                    '<span>Record 1–1 Win% 50.0% Adjusted + 0.00 Selections 2</span>'
                    '</div>'
                )
            parts.append(
                '<div class="bg-light border-lighter">'
                '<span class="font-bold">No Battlegroup</span>'
                '<span>Record 1–1 Win% 50.0% Adjusted + 0.00 Selections 2</span>'
                '</div>'
            )
        rows = MODULE.parse_battlegroups_page("".join(parts), "https://cohdb.com/battlegroups", PATCH, "all", "balanced_all")
        self.assertEqual(len(rows), 32)
        self.assertEqual({row["faction"] for row in rows}, set(MODULE.FACTIONS))
        self.assertEqual(sum(row["battlegroup"] == MODULE.NO_BATTLEGROUP for row in rows), 4)

    def test_build_order_mode_and_rating_parser(self):
        html = """
        <h1>Mechanized</h1>
        <section><h3>Win Rate</h3>
          <button data-tab-panel="all">All Modes 50.0% 100 games 50W – 50L</button>
          <button data-tab-panel="ones">1v1 55.0% 20 games 11W – 9L</button>
          <button data-tab-panel="twos">2v2 45.0% 20 games 9W – 11L</button>
          <button data-tab-panel="threes">3v3 50.0% 20 games 10W – 10L</button>
          <button data-tab-panel="fours">4v4 50.0% 40 games 20W – 20L</button>
          <div data-panel="all"><div><div><span>1800+</span><span>50.0%</span><span>10g</span></div><div><span>1600 – 1800</span><span>55.0%</span><span>20g</span></div><div><span>1400 – 1600</span><span>50.0%</span><span>20g</span></div><div><span>1200 – 1400</span><span>50.0%</span><span>20g</span></div><div><span>1000 – 1200</span><span>50.0%</span><span>20g</span></div></div></div>
          <div data-panel="ones"><div><div><span>1800+</span><span>50.0%</span><span>10g</span></div><div><span>1600 – 1800</span><span>55.0%</span><span>20g</span></div><div><span>1400 – 1600</span><span>50.0%</span><span>20g</span></div><div><span>1200 – 1400</span><span>50.0%</span><span>20g</span></div><div><span>1000 – 1200</span><span>50.0%</span><span>20g</span></div></div></div>
          <div data-panel="twos"><div><div><span>1800+</span><span>50.0%</span><span>10g</span></div><div><span>1600 – 1800</span><span>55.0%</span><span>20g</span></div><div><span>1400 – 1600</span><span>50.0%</span><span>20g</span></div><div><span>1200 – 1400</span><span>50.0%</span><span>20g</span></div><div><span>1000 – 1200</span><span>50.0%</span><span>20g</span></div></div></div>
          <div data-panel="threes"><div><div><span>1800+</span><span>50.0%</span><span>10g</span></div><div><span>1600 – 1800</span><span>55.0%</span><span>20g</span></div><div><span>1400 – 1600</span><span>50.0%</span><span>20g</span></div><div><span>1200 – 1400</span><span>50.0%</span><span>20g</span></div><div><span>1000 – 1200</span><span>50.0%</span><span>20g</span></div></div></div>
          <div data-panel="fours"><div><div><span>1800+</span><span>50.0%</span><span>10g</span></div><div><span>1600 – 1800</span><span>55.0%</span><span>20g</span></div><div><span>1400 – 1600</span><span>50.0%</span><span>20g</span></div><div><span>1200 – 1400</span><span>50.0%</span><span>20g</span></div><div><span>1000 – 1200</span><span>50.0%</span><span>20g</span></div></div></div>
        </section>
        <section><h3>Build Order</h3><div class="flex-none w-64 bg-light border-lighter"><span>Most Common</span><span>10 games</span><div class="flex flex-col gap-1.5"><div><img src="unit.webp"><span>Panzergrenadier Squad</span></div></div></div></section>
        <section><h3>Common Followups</h3><div class="flex-none w-64 bg-light border-lighter"><span>Followup 1</span><span>5 games</span><div class="flex flex-col gap-1.5"><div><span>8 Rad Armored Car</span></div></div></div></section>
        <section><h3>Tech Paths</h3><div class="divide-y"><div>Light Support Kompanie → Mechanized Kompanie 10 games 100.0%</div></div></section>
        """
        result = MODULE.parse_build_order_page("".join(html.splitlines()), "https://cohdb.com/build_orders/test?patch=50313", PATCH)
        self.assertEqual(result["title"], "Mechanized")
        self.assertEqual(result["mode_summaries"]["1v1"]["games"], 20)
        self.assertEqual(result["rating_bands"]["1v1"]["1600 – 1800"]["games"], 20)
        self.assertEqual(result["most_common_and_variants"][0]["steps"][0]["name"], "Panzergrenadier Squad")
        self.assertEqual(result["followups"][0]["steps"][0]["name"], "8 Rad Armored Car")


if __name__ == "__main__":
    unittest.main()
