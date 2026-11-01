"""Audit supplied EGIS shapefile tiles without treating their bounds as actual coverage."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely.geometry import box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / 'data/raw/landcover'
BOUNDARY = ROOT / 'data/processed/seoul_districts_5179.gpkg'
OUTPUT = ROOT / 'data/processed/landcover_inventory.json'


def inspect(input_dir: Path = INPUT, output: Path = OUTPUT) -> dict:
    files = sorted(input_dir.glob('*.shp'))
    if not files:
        raise FileNotFoundError('No EGIS shapefiles found')
    required = {'.shp', '.shx', '.dbf', '.prj'}
    for file in files:
        missing = [ext for ext in required if not file.with_suffix(ext).exists()]
        if missing:
            raise ValueError(f'Incomplete shapefile: {file.name}: {missing}')

    dates: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    crs: Counter[str] = Counter()
    tile_bounds = []
    feature_count = invalid_count = empty_count = 0
    for file in files:
        frame = pyogrio.read_dataframe(file, columns=['L3_CODE', 'IMG_DATE', 'INX_NUM'])
        if not {'L3_CODE', 'IMG_DATE', 'INX_NUM'}.issubset(frame.columns) or frame.crs is None:
            raise ValueError(f'EGIS fields or CRS missing: {file.name}')
        if set(frame.INX_NUM.astype(str)) != {file.stem}:
            raise ValueError(f'Tile ID mismatch: {file.name}')
        feature_count += len(frame)
        invalid_count += int((~frame.geometry.is_valid).sum())
        empty_count += int((frame.geometry.is_empty | frame.geometry.isna()).sum())
        dates.update(frame.IMG_DATE.dt.strftime('%Y-%m-%d').fillna('missing'))
        codes.update(frame.L3_CODE.astype(str).str.strip())
        crs.update([str(frame.crs.to_epsg())])
        tile_bounds.append(box(*frame.total_bounds))
    if set(crs) != {'5186'}:
        raise ValueError(f'Unexpected EGIS coordinate systems: {list(crs)}')

    bounds_union = unary_union(tile_bounds)
    districts = gpd.read_file(BOUNDARY).to_crs(5186)
    if len(districts) != 25:
        raise ValueError('Expected 25 districts')
    coverage = []
    for district in districts.itertuples():
        fraction = district.geometry.intersection(bounds_union).area / district.geometry.area
        coverage.append({'district': district.name, 'source_code': district.source_code,
                         'bbox_coverage_upper_bound': fraction,
                         'bbox_uncovered_km2_lower_bound': district.geometry.difference(bounds_union).area / 1_000_000})
    city = districts.geometry.union_all()
    report = {
        'checked_on': date.today().isoformat(),
        'source': 'user-supplied EGIS land-cover shapefiles',
        'tile_count': len(files), 'feature_count': feature_count,
        'crs_epsg_counts': dict(crs), 'img_date_attribute_counts': dict(sorted(dates.items())),
        'class_code_counts': dict(sorted(codes.items())),
        'invalid_geometry_count': invalid_count, 'empty_geometry_count': empty_count,
        'city_bbox_coverage_upper_bound': city.intersection(bounds_union).area / city.area,
        'district_bbox_coverage': coverage,
        'coverage_note': 'Tile bounding boxes overestimate actual polygon coverage. Values below 0.999 definitively fail the 99.9% coverage gate.',
        'reference_date_note': 'IMG_DATE is a source attribute; the formal map production year is not established by these files.',
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"EGIS inventory: {len(files)} tiles, {feature_count} features, city bbox coverage at most {report['city_bbox_coverage_upper_bound']:.4%}")
    return report


if __name__ == '__main__':
    inspect()
