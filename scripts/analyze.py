"""Join verified sources; publish only when all five source inputs are present."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import geopandas as gpd
from metrics import calculate_metrics

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / 'data/processed'
PUBLIC = ROOT / 'public/data'


def validate_landcover_record(row, boundary_area):
    values = {key: float(row[key]) for key in ['total_km2', 'forest_km2', 'water_km2', 'excluded_union_km2', 'remaining_km2']}
    total, forest, water, excluded, remaining = (values[k] for k in ['total_km2', 'forest_km2', 'water_km2', 'excluded_union_km2', 'remaining_km2'])
    tolerance = 1e-8
    if (abs(total - boundary_area) > tolerance or min(values.values()) < -tolerance
            or excluded + tolerance < max(forest, water)
            or excluded > forest + water + tolerance
            or excluded > total + tolerance
            or abs(total - excluded - remaining) > tolerance
            or remaining <= 0):
        raise ValueError('Land-cover area balance or bounds failed')
    return values


def read_unique(path, key):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    result = {r[key]: r for r in rows}
    if len(result) != len(rows) or len(rows) != 25:
        raise ValueError(f'Expected 25 unique {key} values in {path.name}')
    return result


def analyze():
    boundaries = gpd.read_file(PROCESSED / 'seoul_districts_5179.gpkg')
    if len(boundaries) != 25 or boundaries.crs.to_epsg() != 5179:
        raise ValueError('Invalid boundary input')
    renewal = read_unique(PROCESSED / 'renewal_counts_2026_06.csv', 'district')
    housing = read_unique(PROCESSED / 'housing_2025.csv', 'district')
    area_path = PROCESSED / 'landcover_areas.csv'
    areas = read_unique(area_path, 'district') if area_path.exists() else None
    partial_coverage = False
    if areas is not None:
        audit_path = PROCESSED / 'landcover_audit.json'
        if not audit_path.exists():
            raise ValueError('Missing land-cover processing audit')
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        if (audit.get('districts') != 25 or audit.get('calculation_crs') != 'EPSG:5179'
                or audit.get('classification_level') != 'EGIS level 3 (41 classes)'
                or set(audit.get('forest_codes', [])) != {'311', '321', '331'}
                or set(audit.get('water_codes', [])) != {'711', '712', '721'}
                or not audit.get('input_files')):
            raise ValueError('Incomplete land-cover processing audit')
        partial_coverage = any(
            float(a['tile_bbox_coverage_upper_bound']) < 0.999
            for a in areas.values() if a.get('tile_bbox_coverage_upper_bound')
        )
    names = set(boundaries.name)
    if set(renewal) != names or set(housing) != names or (areas is not None and set(areas) != names):
        raise ValueError('District join mismatch')
    records = []
    for b in boundaries.itertuples():
        a = areas[b.name] if areas else None
        source_area = b.geometry.area / 1_000_000
        if a:
            validate_landcover_record(a, source_area)
        records.append({'code': housing[b.name]['code'], 'source_boundary_code': b.source_code, 'district': b.name,
            'renewal_count': int(renewal[b.name]['renewal_count']),
            'old_homes': int(housing[b.name]['old_homes']), 'homes': int(housing[b.name]['homes']),
            'total_km2': source_area,
            'forest_km2': float(a['forest_km2']) if a else None,
            'water_km2': float(a['water_km2']) if a else None,
            'excluded_union_km2': float(a['excluded_union_km2']) if a else None,
            'tile_bbox_coverage_upper_bound': float(a['tile_bbox_coverage_upper_bound'])
                if a and a.get('tile_bbox_coverage_upper_bound') else None})
    records, summary = calculate_metrics(records)
    records.sort(key=lambda r: r['code'])
    PROCESSED.mkdir(parents=True, exist_ok=True)
    status = ('provisional_partial_coverage' if partial_coverage else 'complete') if areas else 'incomplete_missing_landcover'
    preview = {'status': status, 'summary': summary, 'districts': records}
    (PROCESSED / 'analysis_preview.json').write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding='utf-8')
    with (PROCESSED / 'analysis_preview.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    metadata_path = PROCESSED / 'metadata.json'
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        metadata['status'] = preview['status']
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    if status == 'complete':
        if not metadata_path.exists():
            raise ValueError('Missing source metadata for publication')
        cover_metadata = next((s for s in metadata['sources'] if s['title'] == '세분류 토지피복지도'), None)
        if not cover_metadata or cover_metadata.get('state') != 'collected' or not cover_metadata.get('reference_date') or '확인 필요' in cover_metadata.get('license', ''):
            raise ValueError('Land-cover source date, collection state, and usage terms must be recorded before publication')
        PUBLIC.mkdir(parents=True, exist_ok=True)
        (PUBLIC / 'district_analysis.json').write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding='utf-8')
        with (PUBLIC / 'district_analysis.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    else:
        for old_public in [PUBLIC / 'district_analysis.json', PUBLIC / 'district_analysis.csv']:
            old_public.unlink(missing_ok=True)
    print(f"Analysis: {len(records)} districts; status={preview['status']}; renewal={summary['renewal_count']}")


if __name__ == '__main__':
    analyze()
