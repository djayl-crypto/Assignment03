"""Clip official EGIS level-3 vector land cover to SGIS districts.

Usage: python scripts/prepare_landcover.py --input data/raw/landcover --class-column <verified field>
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import geopandas as gpd
from shapely import make_valid
from shapely.ops import unary_union
from inspect_landcover import inspect as inspect_source
from metrics import area_components

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY = ROOT / 'data/processed/seoul_districts_5179.gpkg'
OUT = ROOT / 'data/processed/landcover_areas.csv'
AUDIT = ROOT / 'data/processed/landcover_audit.json'
FOREST = {'311', '321', '331'}
WATER = {'711', '712', '721'}


def prepare(input_path: Path, class_column: str):
    files = [input_path] if input_path.is_file() else sorted([*input_path.glob('*.shp'), *input_path.glob('*.gpkg'), *input_path.glob('*.geojson')])
    if not files:
        raise FileNotFoundError('No vector land-cover files found')
    inventory = None
    if input_path.is_dir() and all(p.suffix.lower() == '.shp' for p in files):
        inventory = inspect_source(input_path)
    frames = []
    repaired_count = 0
    repair_area_delta_m2 = 0.0
    for file in files:
        frame = gpd.read_file(file, columns=[class_column])
        if class_column not in frame.columns or frame.crs is None:
            raise ValueError(f'Class field or CRS missing: {file.name}')
        frame = frame[[class_column, 'geometry']].copy()
        frame[class_column] = frame[class_column].astype(str).str.strip()
        if not frame[class_column].str.fullmatch(r'\d{3}').all():
            raise ValueError(f'Expected three-digit EGIS level-3 codes: {file.name}')
        frame = frame.loc[frame[class_column].isin(FOREST | WATER)].copy()
        if frame.geometry.is_empty.any() or frame.geometry.isna().any():
            raise ValueError(f'Empty land-cover geometry: {file.name}')
        invalid = ~frame.geometry.is_valid
        if invalid.any():
            original = frame.loc[invalid, 'geometry']
            repaired = original.map(make_valid)
            if repaired.is_empty.any() or not repaired.is_valid.all():
                raise ValueError(f'Geometry repair failed: {file.name}')
            delta = sum(abs(a.area - b.area) for a, b in zip(original, repaired))
            if delta > 1e-4:
                raise ValueError(f'Geometry repair changed area materially: {file.name}')
            frame.loc[invalid, 'geometry'] = repaired
            repaired_count += int(invalid.sum())
            repair_area_delta_m2 += delta
        if not frame.geometry.geom_type.isin(['Polygon', 'MultiPolygon']).all():
            raise ValueError(f'Non-polygon land-cover geometry: {file.name}')
        frames.append(frame.to_crs(5179))
    cover = gpd.GeoDataFrame(__import__('pandas').concat(frames, ignore_index=True), crs=5179)
    codes = set(cover[class_column])
    if not (codes & FOREST) or not (codes & WATER):
        raise ValueError('Both forest and water classes must be present in source')
    districts = gpd.read_file(BOUNDARY)
    forest = unary_union(cover.loc[cover[class_column].isin(FOREST), 'geometry'].tolist())
    water = unary_union(cover.loc[cover[class_column].isin(WATER), 'geometry'].tolist())
    coverage_by_code = ({r['source_code']: r for r in inventory['district_bbox_coverage']}
                        if inventory else {})
    rows = []
    for district in districts.itertuples():
        areas = area_components(district.geometry, [forest], [water])
        coverage = coverage_by_code.get(district.source_code, {})
        rows.append({'source_code': district.source_code, 'district': district.name,
                     'tile_bbox_coverage_upper_bound': coverage.get('bbox_coverage_upper_bound'), **areas})
    if len(rows) != 25 or any(r['remaining_km2'] <= 0 for r in rows):
        raise ValueError('Missing district or nonpositive remainder')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    AUDIT.write_text(json.dumps({'input_files': [p.name for p in files], 'class_column': class_column,
        'source_codes_observed': sorted(inventory['class_code_counts'] if inventory else codes),
        'forest_codes': sorted(FOREST), 'water_codes': sorted(WATER),
        'repaired_self_intersections': repaired_count, 'repair_absolute_area_delta_m2': repair_area_delta_m2,
        'source_invalid_geometry_count': inventory['invalid_geometry_count'] if inventory else None,
        'city_tile_bbox_coverage_upper_bound': inventory['city_bbox_coverage_upper_bound'] if inventory else None,
        'coverage_policy': 'partial observed EGIS forest/water; unobserved land stays in full district denominator',
        'districts': len(rows), 'calculation_crs': 'EPSG:5179', 'overlap_rule': 'forest and water polygons are unioned before subtraction',
        'classification_level': 'EGIS level 3 (41 classes)'}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Land-cover areas: 25 districts; partial-coverage area balances checked')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--class-column', required=True)
    args = parser.parse_args()
    prepare(args.input, args.class_column)
