"""Validate prepared public assets without exposing any configured secret value."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from dotenv import dotenv_values
from analyze import validate_landcover_record

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / 'data/processed/analysis_preview.json'
OUT = ROOT / 'data/processed/validation.json'


def validate():
    data = json.loads(PREVIEW.read_text(encoding='utf-8'))
    rows = data['districts']
    if len(rows) != 25 or len({r['code'] for r in rows}) != 25 or len({r['district'] for r in rows}) != 25:
        raise ValueError('25-district completeness failed')
    if sum(r['renewal_count'] for r in rows) != data['summary']['renewal_count']:
        raise ValueError('Renewal count total mismatch')
    if sum(r['old_homes'] for r in rows) != data['summary']['old_homes'] or sum(r['homes'] for r in rows) != data['summary']['homes']:
        raise ValueError('Housing total mismatch')
    housing_audit = json.loads((ROOT / 'data/processed/housing_audit.json').read_text(encoding='utf-8'))
    if (not housing_audit['old_homes_sum_matches_official'] or not housing_audit['homes_sum_matches_official']
            or housing_audit['old_homes_official_seoul'] != data['summary']['old_homes']
            or housing_audit['homes_official_seoul'] != data['summary']['homes']):
        raise ValueError('Official Seoul housing reconciliation failed')
    landcover_passed = data['status'] in {'complete', 'provisional_partial_coverage'}
    if landcover_passed:
        if not (ROOT / 'data/processed/landcover_audit.json').exists():
            raise ValueError('Missing land-cover audit')
        for row in rows:
            validate_landcover_record(row, row['total_km2'])
        if data['status'] == 'provisional_partial_coverage':
            inventory = json.loads((ROOT / 'data/processed/landcover_inventory.json').read_text(encoding='utf-8'))
            cover_by_code = {r['source_code']: r['bbox_coverage_upper_bound'] for r in inventory['district_bbox_coverage']}
            if len(cover_by_code) != 25 or not any(v < 0.999 for v in cover_by_code.values()):
                raise ValueError('Partial coverage inventory missing or inconsistent')
            for row in rows:
                if abs(row['tile_bbox_coverage_upper_bound'] - cover_by_code[row['source_boundary_code']]) > 1e-12:
                    raise ValueError('District coverage provenance mismatch')
    secrets = [str(v).encode('utf-8') for v in dotenv_values(ROOT / '.env').values() if v and len(str(v)) >= 8]
    scanned = []
    for directory in [ROOT / 'public', ROOT / 'dist', ROOT / 'src', ROOT / 'docs', ROOT / 'scripts', ROOT / 'data/processed']:
        if directory.exists():
            for path in directory.rglob('*'):
                if path.is_file():
                    content = path.read_bytes()
                    if any(secret in content for secret in secrets):
                        raise ValueError(f'Configured secret present in public/build/source file: {path.relative_to(ROOT)}')
                    scanned.append(str(path.relative_to(ROOT)))
    report = {'checked_on': str(date.today()), 'districts': 25,
              'renewal_records': data['summary']['renewal_count'],
              'official_seoul_housing_totals_reconciled': housing_audit['old_homes_sum_matches_official'] and housing_audit['homes_sum_matches_official'],
              'boundary_crs_calculation': 'EPSG:5179',
              'secrets_found_in_public_build_source': False,
              'files_scanned': len(scanned),
              'landcover_area_check': 'passed' if landcover_passed else 'pending',
              'landcover_coverage': 'partial_bbox_upper_bound' if data['status'] == 'provisional_partial_coverage'
                  else 'complete' if landcover_passed else 'pending',
              'final_priority_classification': 'provisional' if data['status'] == 'provisional_partial_coverage'
                  else 'calculated' if landcover_passed else 'pending'}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Validation: {len(rows)} districts; {len(scanned)} public/build/source files scanned; status={data['status']}")


if __name__ == '__main__':
    validate()
