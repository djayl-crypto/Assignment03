"""Fetch 2025 district housing counts from two verified KOSIS tables."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/processed/housing_2025.csv'
AUDIT = ROOT / 'data/processed/housing_audit.json'
API = 'https://kosis.kr/openapi/Param/statisticsParameterData.do'
CODES = [str(i) for i in range(11010, 11251, 10)]


def fetch_table(key, table, item, age=None):
    params = {'method': 'getList', 'apiKey': key, 'orgId': '101', 'tblId': table,
              'objL1': '+'.join(['11', *CODES]), 'itmId': item, 'prdSe': 'Y',
              'startPrdDe': '2025', 'endPrdDe': '2025', 'format': 'json', 'jsonVD': 'Y'}
    if age:
        params['objL2'] = age
    try:
        response = requests.get(API, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f'KOSIS {table} request failed ({type(exc).__name__}); request URL suppressed') from None
    if not isinstance(data, list) or len(data) != 26:
        raise ValueError(f'KOSIS {table}: expected Seoul plus 25 districts, got {len(data) if isinstance(data, list) else "non-list"}')
    result = {}
    for row in data:
        code = str(row.get('C1'))
        if code not in {'11', *CODES} or code in result or row.get('PRD_DE') != '2025' or row.get('ITM_ID') != item:
            raise ValueError(f'Unexpected or duplicate KOSIS row in {table}')
        if age and str(row.get('C2')) != age:
            raise ValueError(f'Unexpected age class in {table}')
        raw = str(row.get('DT', '')).replace(',', '').strip()
        result[code] = {'name': row['C1_NM'], 'count': int(raw) if raw.isdecimal() else None, 'raw_marker': raw if not raw.isdecimal() else None}
    if set(result) != {'11', *CODES}:
        raise ValueError(f'Incomplete district codes in {table}')
    return result


def collect():
    key = dotenv_values(ROOT / '.env').get('KOSIS_API_KEY')
    if not key:
        raise RuntimeError('KOSIS_API_KEY is not configured')
    old = fetch_table(key, 'DT_1JU1521', 'T00', '130')
    total = fetch_table(key, 'DT_1JU1501', 'T10')
    records = []
    for code in CODES:
        if old[code]['name'] != total[code]['name']:
            raise ValueError(f'KOSIS district name mismatch at {code}')
        records.append({'code': code, 'district': old[code]['name'], 'old_homes': old[code]['count'], 'homes': total[code]['count']})
    if any(r['old_homes'] is None or r['homes'] is None or r['old_homes'] > r['homes'] for r in records):
        raise ValueError('Missing/suppressed or inconsistent district housing counts')
    old_sum = sum(r['old_homes'] for r in records)
    total_sum = sum(r['homes'] for r in records)
    audit = {'year': 2025, 'districts': 25, 'old_homes_district_sum': old_sum, 'homes_district_sum': total_sum,
             'old_homes_official_seoul': old['11']['count'], 'homes_official_seoul': total['11']['count'],
             'old_homes_sum_matches_official': old_sum == old['11']['count'],
             'homes_sum_matches_official': total_sum == total['11']['count'],
             'source_tables': {'old_homes': 'DT_1JU1521/T00/B130', 'homes': 'DT_1JU1501/T10'}}
    if not audit['old_homes_sum_matches_official'] or not audit['homes_sum_matches_official']:
        raise ValueError('District sum does not match official Seoul total')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=['code', 'district', 'old_homes', 'homes'])
        writer.writeheader()
        writer.writerows(records)
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'KOSIS 2025 housing: {len(records)} districts; both Seoul totals reconciled')


if __name__ == '__main__':
    collect()
