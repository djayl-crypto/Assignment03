"""Download the June 2026 workbook from its official Seoul attachment form."""
from __future__ import annotations

import re
from pathlib import Path
from zipfile import ZipFile
import requests
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
PAGE = 'https://data.seoul.go.kr/dataList/OA-22856/F/1/datasetView.do'
DOWNLOAD = 'https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do'
OUT = ROOT / 'data/raw/seoul_renewal_2026_06.xlsx'


def collect():
    try:
        page = requests.get(PAGE, timeout=30)
        page.raise_for_status()
        matches = re.findall(r'title="[^"]*26년 6월기준[^"]*\.xlsx"[^>]*onclick="javascript:downloadFile\(\'(\d+)\'\)', page.text)
        if len(set(matches)) != 1:
            raise ValueError('June 2026 attachment not uniquely identified')
        response = requests.post(DOWNLOAD, params={'useCache': 'false'},
            data={'infId': 'OA-22856', 'infSeq': '2', 'seqNo': '', 'seq': matches[0]},
            headers={'Referer': PAGE}, timeout=60)
        response.raise_for_status()
        if response.content[:2] != b'PK':
            raise ValueError('Official attachment did not return an XLSX archive')
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_bytes(response.content)
        with ZipFile(OUT) as archive:
            if archive.testzip() is not None:
                raise ValueError('XLSX archive failed integrity check')
        sheet = load_workbook(OUT, read_only=True, data_only=True).active
        if sheet['A1'].value != 'CODE' or sheet['C1'].value != '자치구':
            raise ValueError('Unexpected workbook columns')
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError(f'Official Seoul workbook collection failed ({type(exc).__name__}); request details suppressed') from None
    print(f'Official June 2026 Seoul workbook verified: {OUT.name}')


if __name__ == '__main__':
    collect()
