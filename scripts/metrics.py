"""Pure metric and projected-area calculations. All area inputs are km²."""
from __future__ import annotations

from math import isfinite
from shapely.ops import unary_union


def area_components(boundary, forests, waters):
    forest = unary_union(forests) if forests else boundary.intersection(boundary).difference(boundary)
    water = unary_union(waters) if waters else boundary.intersection(boundary).difference(boundary)
    forest = boundary.intersection(forest)
    water = boundary.intersection(water)
    excluded = forest.union(water)
    total = boundary.area / 1_000_000
    result = {
        'total_km2': total,
        'forest_km2': forest.area / 1_000_000,
        'water_km2': water.area / 1_000_000,
        'excluded_union_km2': excluded.area / 1_000_000,
        'remaining_km2': boundary.difference(excluded).area / 1_000_000,
    }
    if abs(result['total_km2'] - result['excluded_union_km2'] - result['remaining_km2']) > 1e-8:
        raise ValueError('Area balance failed')
    return result


def _safe_ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    if not isfinite(float(numerator)) or not isfinite(float(denominator)):
        return None
    return numerator / denominator


def classify_priority(lq, density, seoul_density):
    if lq is None or density is None or seoul_density is None:
        return None
    return bool(lq > 1 and density < seoul_density)


def calculate_metrics(rows):
    rows = [dict(row) for row in rows]
    if len({r['code'] for r in rows}) != len(rows):
        raise ValueError('Duplicate district code')
    if any(r.get('renewal_count') is None or r['renewal_count'] < 0 for r in rows):
        raise ValueError('Missing or negative renewal count')
    for r in rows:
        total = r.get('total_km2')
        excluded = r.get('excluded_union_km2')
        r['remaining_km2'] = None if total is None or excluded is None else total - excluded
        if r['remaining_km2'] is not None and (r['remaining_km2'] < -1e-9 or excluded < 0):
            raise ValueError('Invalid excluded area')
    complete_housing = all(r.get('old_homes') is not None and r.get('homes') is not None for r in rows)
    complete_total_area = all(r.get('total_km2') is not None for r in rows)
    complete_adjusted_area = all(r.get('remaining_km2') is not None for r in rows)
    old_sum = sum(r['old_homes'] for r in rows) if complete_housing else None
    homes_sum = sum(r['homes'] for r in rows) if complete_housing else None
    count_sum = sum(r['renewal_count'] for r in rows)
    seoul_old_share = _safe_ratio(old_sum, homes_sum)
    seoul_density_total = _safe_ratio(count_sum, sum(r['total_km2'] for r in rows)) if complete_total_area else None
    seoul_density_adjusted = _safe_ratio(count_sum, sum(r['remaining_km2'] for r in rows)) if complete_adjusted_area else None
    for r in rows:
        old = r.get('old_homes')
        homes = r.get('homes')
        if old is not None and homes is not None and (old < 0 or homes < 0 or old > homes):
            raise ValueError('Invalid housing counts')
        r['old_share'] = _safe_ratio(old, homes)
        r['lq'] = _safe_ratio(r['old_share'], seoul_old_share)
        r['density_total'] = _safe_ratio(r['renewal_count'], r.get('total_km2'))
        r['density_adjusted'] = _safe_ratio(r['renewal_count'], r['remaining_km2'])
        r['priority_total'] = classify_priority(r['lq'], r['density_total'], seoul_density_total)
        r['priority_adjusted'] = classify_priority(r['lq'], r['density_adjusted'], seoul_density_adjusted)
    for field, rank_field in [('density_total', 'rank_total'), ('density_adjusted', 'rank_adjusted')]:
        ordered = sorted((r for r in rows if r[field] is not None), key=lambda r: (-r[field], r['code']))
        for rank, r in enumerate(ordered, 1):
            r[rank_field] = rank
        for r in rows:
            r.setdefault(rank_field, None)
    for r in rows:
        r['rank_change'] = None if r['rank_total'] is None or r['rank_adjusted'] is None else r['rank_total'] - r['rank_adjusted']
    return rows, {'renewal_count': count_sum, 'old_homes': old_sum, 'homes': homes_sum,
                  'seoul_old_share': seoul_old_share, 'seoul_density_total': seoul_density_total,
                  'seoul_density_adjusted': seoul_density_adjusted}
