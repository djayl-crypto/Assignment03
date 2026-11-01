"""Prepare official SGIS 2025-Q2 Seoul district geometry for web and area work."""
from __future__ import annotations

import json
from pathlib import Path
import geopandas as gpd
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'lecture04_spatial_data_analysis/bnd_all_00_2025_2Q/bnd_sigungu_00_2025_2Q.shp'
WEB = ROOT / 'public/seoul_districts.geojson'
METRIC = ROOT / 'data/processed/seoul_districts_5179.gpkg'


def prepare():
    source = gpd.read_file(SOURCE, encoding='utf-8')
    if source.crs.to_epsg() != 5179:
        raise ValueError(f'Unexpected boundary CRS: {source.crs}')
    seoul = source[source.SIGUNGU_CD.astype(str).str.startswith('11')].copy()
    if len(seoul) != 25 or seoul.BASE_DATE.nunique() != 1 or seoul.BASE_DATE.iloc[0] != '20250630':
        raise ValueError('Unexpected Seoul boundary count or date')
    if seoul.SIGUNGU_NM.nunique() != 25 or seoul.SIGUNGU_CD.nunique() != 25:
        raise ValueError('Duplicate district name or source code')
    if not seoul.geometry.is_valid.all() or seoul.geometry.is_empty.any():
        raise ValueError('Invalid boundary geometry')
    seoul = seoul[['SIGUNGU_CD', 'SIGUNGU_NM', 'geometry']].rename(columns={'SIGUNGU_CD': 'source_code', 'SIGUNGU_NM': 'name'})
    METRIC.parent.mkdir(parents=True, exist_ok=True)
    seoul.to_file(METRIC, driver='GPKG')
    web = seoul.to_crs(4326)
    features = [{'type': 'Feature', 'properties': {'source_code': row.source_code, 'name': row.name},
                 'geometry': mapping(row.geometry)} for row in web.itertuples()]
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text(json.dumps({'type': 'FeatureCollection', 'source': {'agency': '통계청 SGIS', 'date': '2025-06-30',
        'source_crs': 'EPSG:5179', 'display_crs': 'EPSG:4326'}, 'features': features}, ensure_ascii=False), encoding='utf-8')
    print(f'SGIS boundaries prepared: {len(features)} districts')


if __name__ == '__main__':
    prepare()
