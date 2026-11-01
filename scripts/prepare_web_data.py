"""Copy verified local aggregates into static assets; never call source APIs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/processed/analysis_preview.json'
BOUNDARY = ROOT / 'public/seoul_districts.geojson'
TARGET = ROOT / 'public/data/report.json'


def prepare() -> None:
    report = json.loads(SOURCE.read_text(encoding='utf-8'))
    boundary = json.loads(BOUNDARY.read_text(encoding='utf-8'))
    rows = report['districts']
    names = {row['district'] for row in rows}
    if (len(rows) != 25 or len(names) != 25 or
            {feature['properties']['name'] for feature in boundary['features']} != names or
            any(row['density_adjusted'] is None or row['lq'] is None for row in rows) or
            report['status'] != 'provisional_partial_coverage'):
        raise ValueError('Static report inputs are incomplete or inconsistent')
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print('Static report data: 25 verified districts; provisional partial coverage')


if __name__ == '__main__':
    prepare()
