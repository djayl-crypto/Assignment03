import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from metrics import calculate_metrics, classify_priority, area_components
from analyze import validate_landcover_record


class MetricsTests(unittest.TestCase):
    def test_lq_and_weighted_seoul_density(self):
        rows = [
            {'code': '1', 'renewal_count': 2, 'old_homes': 30, 'homes': 100, 'total_km2': 10, 'forest_km2': 2, 'water_km2': 1, 'excluded_union_km2': 3},
            {'code': '2', 'renewal_count': 8, 'old_homes': 10, 'homes': 100, 'total_km2': 20, 'forest_km2': 0, 'water_km2': 0, 'excluded_union_km2': 0},
        ]
        result, summary = calculate_metrics(rows)
        self.assertAlmostEqual(summary['seoul_density_adjusted'], 10 / 27)
        self.assertAlmostEqual(result[0]['lq'], 1.5)
        self.assertTrue(result[0]['priority_adjusted'])
        self.assertFalse(result[1]['priority_adjusted'])

    def test_missing_denominator_is_not_zero(self):
        result, _ = calculate_metrics([{'code': '1', 'renewal_count': 0, 'old_homes': None, 'homes': 0, 'total_km2': 1, 'forest_km2': 0, 'water_km2': 0, 'excluded_union_km2': 0}])
        self.assertIsNone(result[0]['lq'])
        self.assertIsNone(result[0]['priority_adjusted'])

    def test_union_prevents_double_subtraction(self):
        from shapely.geometry import box
        result = area_components(box(0, 0, 10, 10), [box(0, 0, 5, 10)], [box(4, 0, 6, 10)])
        self.assertEqual(result['excluded_union_km2'], 60 / 1_000_000)
        self.assertEqual(result['remaining_km2'], 40 / 1_000_000)

    def test_partial_landcover_retains_unobserved_area(self):
        from shapely.geometry import box

        # Source polygons cover only part of the district; the missing part is not fabricated.
        area = area_components(box(0, 0, 10, 10), [box(0, 0, 2, 10)], [])
        self.assertEqual(area['excluded_union_km2'], 20 / 1_000_000)
        self.assertEqual(area['remaining_km2'], 80 / 1_000_000)
        rows, _ = calculate_metrics([{'code': '1', 'renewal_count': 8, 'old_homes': 30,
                                      'homes': 100, **area}])
        self.assertEqual(rows[0]['density_adjusted'], 8 / area['remaining_km2'])

    def test_classification_uses_unrounded_values(self):
        self.assertTrue(classify_priority(1.000001, 0.999999, 1.0))
        self.assertFalse(classify_priority(1.0, 0.9, 1.0))

    def test_rejects_inconsistent_landcover_area(self):
        invalid = {'total_km2': '10', 'forest_km2': '4', 'water_km2': '2',
                   'excluded_union_km2': '3', 'remaining_km2': '7'}
        with self.assertRaises(ValueError):
            validate_landcover_record(invalid, 10)


if __name__ == '__main__':
    unittest.main()
