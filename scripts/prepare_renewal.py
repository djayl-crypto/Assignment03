"""Extract the June 2026 residential renewal subset from Seoul's official workbook."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/raw/seoul_renewal_2026_06.xlsx'
OUTPUT = ROOT / 'data/processed/renewal_counts_2026_06.csv'
AUDIT = ROOT / 'data/processed/renewal_audit.json'
INCLUDED_TYPES = {'주택정비형 재개발', '공동주택재건축', '아파트지구재건축', '단독주택재건축'}
EXCLUDED_TYPES = {'도시정비형 재개발'}
ACTIVE_STAGES = {'구역지정', '추진위', '조합설립', '건축심의', '사업시행', '관리처분', '착공'}


def extract_rows(path=SOURCE):
    sheet = load_workbook(path, read_only=True, data_only=True).active
    rows = []
    for source_row, values in enumerate(sheet.values, 1):
        code = values[0]
        if not isinstance(code, int):
            continue
        rows.append({'source_row': source_row, 'business_id': str(code), 'district': str(values[2]).strip(),
                     'name': str(values[3]).strip(), 'type': str(values[8]).strip(), 'stage': str(values[9]).strip()})
    return rows


def prepare():
    rows = extract_rows()
    if len(rows) != 496:
        raise ValueError(f'Expected 496 identified June 2026 source records; got {len(rows)}')
    ids = [r['business_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate business CODE')
    types = {r['type'] for r in rows}
    stages = {r['stage'] for r in rows}
    if types != INCLUDED_TYPES | EXCLUDED_TYPES or stages != ACTIVE_STAGES:
        raise ValueError(f'Unreviewed source classification: types={types}; stages={stages}')
    included = [r for r in rows if r['type'] in INCLUDED_TYPES]
    names = {r['district'] for r in rows}
    if len(names) != 25:
        raise ValueError(f'Expected 25 districts; got {len(names)}')
    counts = Counter(r['district'] for r in included)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['district', 'renewal_count'])
        writer.writeheader()
        writer.writerows({'district': name, 'renewal_count': counts[name]} for name in sorted(names))
    audit = {'source_records': len(rows), 'unique_business_ids': len(set(ids)), 'included_records': len(included),
             'excluded_records': len(rows) - len(included), 'districts': len(names),
             'types': dict(Counter(r['type'] for r in rows)), 'stages': dict(Counter(r['stage'] for r in rows)),
             'rule': 'Include four residential redevelopment/reconstruction types at all seven active stages; exclude urban redevelopment type.'}
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Residential renewal records: {len(included)}; districts: {len(names)}; duplicate IDs: 0")


if __name__ == '__main__':
    prepare()
