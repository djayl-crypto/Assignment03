# 도시데이터분석 과제 3 — 서울 도시 연구 보고서

연구 질문: **서울에서 30년 이상 주택의 상대적 집중도(LQ)는 높지만 산림·수역 제외 면적당 주거 정비사업 Density는 낮은 자치구는 어디인가?** 분석 범위는 서울 25개 자치구다. 로컬 웹 보고서가 구현되어 있다.

## 현재 상태

정비사업·주택·경계 자료와 사용자가 제공한 EGIS 세분류 토지피복지도 SHP 도엽 125개를 사용했다. [원자료 검증 기록](data/processed/landcover_inventory.json)에 따르면 도엽 외접 범위 기준 서울 커버리지는 최대 96.07%다. 사용자 지시에 따라 **관측된 산림·수역만 제외한 잠정 Density**를 [25개 구 분석 JSON](data/processed/analysis_preview.json)과 [CSV](data/processed/analysis_preview.csv)에 계산했다. 상태는 `provisional_partial_coverage`다. 누락 부분은 임의로 채우지 않으며 구별 커버리지 상한을 함께 제공한다. 이 결과는 로컬 검토용이며 외부 공개 전에는 원자료 이용조건 확인과 사용자 승인이 필요하다.

## 재실행

Python 의존성은 `requirements.txt`에 있다. 현재 실습 폴더 상위 `.venv`에 설치되어 있다. 명령 실행 전에 해당 환경을 활성화하거나 그 Python 경로를 직접 지정한다. PowerShell에서는 `npm.cmd`를 쓴다.

```powershell
cd Assignment03
npm.cmd install
python scripts/collect_renewal.py
python scripts/prepare_renewal.py
python scripts/collect_housing.py
python scripts/prepare_boundary.py
python scripts/inspect_landcover.py
python scripts/prepare_landcover.py --input data/raw/landcover --class-column L3_CODE
python scripts/analyze.py
python scripts/prepare_exclusion_layer.py
python scripts/prepare_web_data.py
python scripts/validate_outputs.py
python -m unittest discover -s tests -v
npm.cmd run typecheck
npm.cmd run build
```

KOSIS·서울 API 키는 `.env`에서 로컬 Python만 읽는다. 웹 빌드는 저장된 정적 파일만 사용하며 자료 재수집을 실행하지 않는다. 실제 키 값은 출력하지 않는다.

**해석 조건:** 관측된 제외 면적이 실제보다 작을 수 있으므로 보정 Density와 관심 지역 판정은 잠정치다. 커버리지가 낮은 중랑·노원·구로·강동구의 값을 특히 주의해 해석한다. 제작연도는 사용자 지시에 따라 계산 조건에서 제외했다. 원본은 `data/raw/`에 비공개로 둔다. VWorld 검토는 [이전 후보 평가](docs/vworld-review.md)로 남긴다.

잠정 수치와 해석은 [결과 요약](docs/results.md), 원자료·코드·이용조건은 [출처](docs/sources.md), 포함 범위·계산식·필드 의미는 [방법](docs/method.md), 진행 상태는 [체크리스트](docs/checklist.md)를 참조한다.

사용자는 2026-11-01에 로컬 결과물을 확인하고 이 Assignment03의 커밋·푸시·공개 배포를 명시적으로 승인했다. 비밀키와 비공개 원자료는 공개하지 않는다. 새 공개 승인 없이 연구 정의나 디자인을 크게 변경하지 않는다.

## 웹 보고서 로컬 미리보기

보고서는 검증된 정적 집계 JSON과 서울 25개 구 경계, 표시용 산림·수역 도형을 사용합니다. 표시용 도형은 15m로 단순화했으며 면적 계산은 원본 도형을 사용했습니다. 결과는 EGIS 도엽 일부 누락에 따른 잠정치입니다.

이 작업 경로에는 `#` 문자가 있어 Vite 개발 서버가 `/@vite/client`에 404를 보내고 TypeScript를 변환하지 못하는 문제가 확인됐습니다. 검증된 프로덕션 빌드를 정적 서버로 제공하세요.

```powershell
cd Assignment03
npm.cmd run typecheck
npm.cmd run build
..\.venv\Scripts\python.exe -m http.server 5174 --bind 127.0.0.1 --directory dist
```

미리보기 주소: **http://127.0.0.1:5174/**. 서버를 실행한 터미널에서 `Ctrl+C`로 종료합니다. 다시 시작할 때는 위의 빌드와 서버 명령을 실행합니다. 분석 데이터는 저장된 정적 집계만 사용합니다. 흑백 배경지도는 브라우저가 OpenStreetMap의 현재 화면에 필요한 타일만 직접 불러옵니다. CARTO 키와 API는 사용하지 않습니다. 지도에는 OpenStreetMap 출처를 표시합니다.

원자료를 다시 전처리할 때는 `scripts/prepare_landcover.py`, `scripts/analyze.py`, `scripts/prepare_exclusion_layer.py`, `scripts/prepare_web_data.py` 순으로 실행합니다.

Cloudflare Pages는 전용 저장소 루트(`/`)에서 `npm run build`를 실행하고 출력 디렉터리 `dist`, 운영 브랜치 `main`을 사용합니다. `.node-version`은 빌드용 Node 버전을 고정합니다. 빌드 과정에서 API를 다시 호출하지 않습니다.
