"""Make a simplified, local-only display layer from observed EGIS forest/water polygons."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely import make_valid
from shapely.geometry import mapping
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/landcover'
BOUNDARY = ROOT / 'data/processed/seoul_districts_5179.gpkg'
OUT = ROOT / 'public/data/exclusion_areas.geojson'
AUDIT = ROOT / 'data/processed/exclusion_layer_audit.json'
CATEGORIES = {'forest': {'311', '321', '331'}, 'water': {'711', '712', '721'}}


def prepare() -> None:
    parts = {'forest': [], 'water': []}
    files = sorted(RAW.glob('*.shp'))
    for path in files:
        frame = gpd.read_file(path, columns=['L3_CODE'])
        frame['L3_CODE'] = frame['L3_CODE'].astype(str).str.strip()
        for category, codes in CATEGORIES.items():
            subset = frame.loc[frame.L3_CODE.isin(codes), ['geometry']].copy()
            if len(subset):
                invalid = ~subset.geometry.is_valid
                subset.loc[invalid, 'geometry'] = subset.loc[invalid, 'geometry'].map(make_valid)
                parts[category].extend(subset.to_crs(5179).geometry.tolist())
    city = gpd.read_file(BOUNDARY).geometry.union_all()
    features = []
    audit = {'source_files': len(files), 'display_crs': 'EPSG:4326', 'calculation_crs': 'EPSG:5179',
             'simplify_m': 15, 'note': 'Display geometry only; exact analytical areas come from landcover_areas.csv.'}
    for category, polygons in parts.items():
        clipped = unary_union(polygons).intersection(city)
        simplified = clipped.simplify(15, preserve_topology=True)
        display = gpd.GeoSeries([simplified], crs=5179).to_crs(4326).iloc[0]
        features.append({'type': 'Feature', 'properties': {'category': category}, 'geometry': mapping(display)})
        audit[category] = {'source_polygons': len(polygons), 'exact_clipped_km2': clipped.area / 1_000_000,
                           'display_simplified_km2': simplified.area / 1_000_000}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Display layer: {len(files)} EGIS tiles, forest and water features, {OUT.stat().st_size} bytes')


if __name__ == '__main__':
    prepare()
