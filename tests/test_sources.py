import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_renewal import extract_rows, INCLUDED_TYPES


class SourceTests(unittest.TestCase):
    def test_official_workbook_identifiers_and_classification(self):
        rows = extract_rows()
        self.assertEqual(len(rows), 496)
        self.assertEqual(len({r['business_id'] for r in rows}), 496)
        self.assertEqual(sum(r['type'] in INCLUDED_TYPES for r in rows), 358)
        self.assertEqual(len({r['district'] for r in rows}), 25)

    def test_kosis_spot_checks_and_official_seoul_reconciliation(self):
        with (ROOT / 'data/processed/housing_2025.csv').open(encoding='utf-8-sig') as stream:
            rows = {r['district']: r for r in csv.DictReader(stream)}
        # Independently checked against the official KOSIS table responses.
        self.assertEqual((int(rows['종로구']['old_homes']), int(rows['종로구']['homes'])), (17729, 47214))
        self.assertEqual((int(rows['노원구']['old_homes']), int(rows['노원구']['homes'])), (112588, 193185))
        self.assertEqual((int(rows['강동구']['old_homes']), int(rows['강동구']['homes'])), (28671, 170045))
        audit = json.loads((ROOT / 'data/processed/housing_audit.json').read_text(encoding='utf-8'))
        self.assertTrue(audit['old_homes_sum_matches_official'])
        self.assertTrue(audit['homes_sum_matches_official'])

    def test_boundary_and_analysis_join(self):
        from geopandas import read_file
        boundary = read_file(ROOT / 'data/processed/seoul_districts_5179.gpkg')
        preview = json.loads((ROOT / 'data/processed/analysis_preview.json').read_text(encoding='utf-8'))
        self.assertEqual(len(boundary), 25)
        self.assertEqual(boundary.crs.to_epsg(), 5179)
        self.assertEqual({r['district'] for r in preview['districts']}, set(boundary.name))
        self.assertIn(preview['status'], {'incomplete_missing_landcover', 'provisional_partial_coverage', 'complete'})
        if preview['status'] == 'incomplete_missing_landcover':
            self.assertTrue(all(r['density_adjusted'] is None for r in preview['districts']))
        else:
            self.assertTrue(all(r['density_adjusted'] is not None for r in preview['districts']))
            if preview['status'] == 'provisional_partial_coverage':
                self.assertTrue(any(r['tile_bbox_coverage_upper_bound'] < 0.999 for r in preview['districts']))


if __name__ == '__main__':
    unittest.main()
