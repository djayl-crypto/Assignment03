import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Metric = 'density_adjusted' | 'lq' | 'density_total';
type BarMetric = 'density_adjusted' | 'lq';
type Row = {
  code: string; source_boundary_code: string; district: string; renewal_count: number;
  old_homes: number; homes: number; total_km2: number; forest_km2: number; water_km2: number;
  excluded_union_km2: number; remaining_km2: number; old_share: number; lq: number;
  density_total: number; density_adjusted: number; rank_total: number; rank_adjusted: number;
  rank_change: number; priority_total: boolean; priority_adjusted: boolean;
  tile_bbox_coverage_upper_bound: number;
};
type Report = { status: string; summary: {
  renewal_count: number; old_homes: number; homes: number; seoul_old_share: number;
  seoul_density_total: number; seoul_density_adjusted: number;
}; districts: Row[] };
type Geometry = { type: 'Polygon' | 'MultiPolygon'; coordinates: number[][][] | number[][][][] };
type Feature = { type: 'Feature'; properties: { name: string; source_code: string }; geometry: Geometry };
type Geo = { type: 'FeatureCollection'; features: Feature[] };
type ExclusionGeo = { type: 'FeatureCollection'; features: { properties: { category: 'forest' | 'water' }; geometry: Geometry }[] };

const COLORS = ['#FFFFB2', '#FECC5C', '#FD8D3C', '#F03B20', '#BD0026'];
const DENSITY_BREAKS = [0.3, 0.6, 0.9, 1.2];
const LQ_BREAKS = [0.8, 1, 1.2, 1.5];
const ADJUSTED_NAME = '단위면적당 진행 중 정비사업 수 (산림·수역 제외 면적)';
const nf = new Intl.NumberFormat('ko-KR');
const f = (n: number, digits = 2) => n.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const pct = (n: number, digits = 1) => `${f(n * 100, digits)}%`;
const metricValue = (r: Row, metric: Metric) => r[metric];
const metricBreaks = (metric: Metric) => metric === 'lq' ? LQ_BREAKS : DENSITY_BREAKS;
const metricColor = (value: number | null | undefined, metric: Metric) => {
  if (value == null || !Number.isFinite(value)) return '#CBD5E1';
  return COLORS[metricBreaks(metric).findIndex(b => value < b) === -1 ? 4 : metricBreaks(metric).findIndex(b => value < b)];
};
const metricLabel = (metric: Metric) => ({ density_adjusted: ADJUSTED_NAME, lq: '노후주택 LQ', density_total: '단위면적당 진행 중 정비사업 수 (전체 면적)' })[metric];
const metricUnit = (metric: Metric) => metric === 'lq' ? '배' : '구역/km²';
const metricDisplay = (value: number, metric: Metric) => f(value, metric === 'lq' ? 2 : 3);
const priorityNames = ['종로구', '강북구', '도봉구', '노원구', '강서구', '관악구'];

function rings(geometry: Geometry): number[][][] {
  return geometry.type === 'Polygon' ? geometry.coordinates as number[][][] : (geometry.coordinates as number[][][][]).flat();
}
function mapProjection(geo: Geo) {
  const mercator = (p: number[]) => [(p[0] + 180) / 360, (1 - Math.asinh(Math.tan(p[1] * Math.PI / 180)) / Math.PI) / 2];
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const feature of geo.features) for (const ring of rings(feature.geometry)) for (const p of ring) {
    const [xx, yy] = mercator(p); minX = Math.min(minX, xx); maxX = Math.max(maxX, xx);
    minY = Math.min(minY, yy); maxY = Math.max(maxY, yy);
  }
  const scale = Math.min(820 / (maxX - minX), 540 / (maxY - minY));
  const left = (900 - (maxX - minX) * scale) / 2, top = (600 - (maxY - minY) * scale) / 2;
  const project = (p: number[]) => { const [xx, yy] = mercator(p); return [left + (xx - minX) * scale, top + (yy - minY) * scale]; };
  const path = (g: Geometry) => rings(g).map(ring => ring.map((p, i) => {
    const [x, y] = project(p); return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join('') + 'Z').join('');
  const center = (g: Geometry) => {
    let leftX = Infinity, rightX = -Infinity, lowY = Infinity, highY = -Infinity;
    for (const ring of rings(g)) for (const p of ring) { leftX = Math.min(leftX, p[0]); rightX = Math.max(rightX, p[0]); lowY = Math.min(lowY, p[1]); highY = Math.max(highY, p[1]); }
    return project([(leftX + rightX) / 2, (lowY + highY) / 2]);
  };
  const z = 11, n = 2 ** z, tiles: { x: number; y: number; left: number; top: number; size: number }[] = [];
  for (let x = Math.max(0, Math.floor((minX - left / scale) * n)); x <= Math.min(n - 1, Math.floor((minX + (900 - left) / scale) * n)); x++) {
    for (let y = Math.max(0, Math.floor((minY - top / scale) * n)); y <= Math.min(n - 1, Math.floor((minY + (600 - top) / scale) * n)); y++) {
      tiles.push({ x, y, left: left + (x / n - minX) * scale, top: top + (y / n - minY) * scale, size: scale / n });
    }
  }
  return { path, center, tiles, zoom: z };
}

function Legend({ metric }: { metric: Metric }) {
  const breaks = metricBreaks(metric);
  const label = (n: number) => f(n, 1);
  const intervals = [`< ${label(breaks[0])}`, ...breaks.slice(1).map((b, i) => `${label(breaks[i])}–${label(b)}`), `≥ ${label(breaks[3])}`];
  return <div className="legend"><div className="legend-title"><span>지표별 고정 구간 · 5단계</span><strong>{metricUnit(metric)}</strong></div><div className="legend-scale">{COLORS.map((color, i) => <div className="legend-item" key={color}><span style={{ background: color }} /><small>{intervals[i]}</small></div>)}</div><div className="legend-extra"><span className="priority-outline" /> 관심 지역 / 선택</div></div>;
}

function MapPanel({ report, geo, exclusion, selected, setSelected }: { report: Report; geo: Geo; exclusion: ExclusionGeo; selected: string; setSelected: (s: string) => void }) {
  const [metric, setMetric] = useState<Metric>('density_adjusted');
  const [showExcluded, setShowExcluded] = useState(true);
  const [basemapError, setBasemapError] = useState(false);
  const rows = useMemo(() => new Map(report.districts.map(r => [r.district, r])), [report]);
  const projection = useMemo(() => mapProjection(geo), [geo]);
  const active = rows.get(selected)!;
  return <section className="panel map-panel" id="map" aria-labelledby="map-title">
    <div className="section-head"><div><span className="eyebrow">01 / SPATIAL VIEW</span><h2 id="map-title">공간 분포를 읽다</h2><p>구 전체를 칠한 색은 자치구 집계값입니다. {ADJUSTED_NAME}의 단위는 구역/km²입니다.</p></div><span className="section-badge">25개 자치구</span></div>
    <div className="segmented map-modes" role="group" aria-label="지도 지표 선택">
      {(['density_adjusted', 'lq'] as Metric[]).map(m => <button key={m} className={metric === m ? 'active' : ''} onClick={() => setMetric(m)} aria-pressed={metric === m}>{m === 'density_adjusted' ? '진행 중 정비사업 수/km²' : '노후주택 LQ'}</button>)}
    </div>
    <div className="map-grid"><div className="map-stage"><div className="chart-topline"><strong>{metricLabel(metric)}</strong><span>{metric === 'lq' ? '2025 주택총조사' : '2026.06 정비사업 · EGIS 관측 도엽'}</span></div>
      <svg viewBox="0 0 900 600" role="img" aria-label={`서울 25개 자치구 ${metricLabel(metric)} 단계구분도`}>
        {projection.tiles.map(tile => <image key={`${tile.x}-${tile.y}`} href={`https://tile.openstreetmap.org/${projection.zoom}/${tile.x}/${tile.y}.png`} x={tile.left} y={tile.top} width={tile.size} height={tile.size} className="basemap-tile" onError={() => setBasemapError(true)} pointerEvents="none" />)}
        {geo.features.map(feature => { const row = rows.get(feature.properties.name); if (!row) return null; const isSelected = selected === row.district; const [cx, cy] = projection.center(feature.geometry); return <g key={row.code}>
          <path d={projection.path(feature.geometry)} fill={metricColor(metricValue(row, metric), metric)} fillOpacity={.72} fillRule="evenodd" stroke={isSelected ? '#1D4ED8' : '#FFFFFF'} strokeWidth={isSelected ? 3.5 : 1.4} className="district-shape" onClick={() => setSelected(row.district)} role="button" tabIndex={0} aria-label={`${row.district}, ${metricLabel(metric)} ${metricDisplay(metricValue(row, metric), metric)} ${metricUnit(metric)}`} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(row.district); } }}><title>{row.district}: {metricDisplay(metricValue(row, metric), metric)} {metricUnit(metric)}</title></path>
          {row.priority_adjusted && <circle cx={cx} cy={cy} r={isSelected ? 7 : 5.2} fill="#1D4ED8" stroke="white" strokeWidth="2" pointerEvents="none" />}
        </g>; })}
        {showExcluded && exclusion.features.map(feature => <path key={feature.properties.category} d={projection.path(feature.geometry)} fill={feature.properties.category === 'forest' ? '#64748B' : '#334155'} opacity={feature.properties.category === 'forest' ? .54 : .68} stroke="none" fillRule="evenodd" pointerEvents="none" />)}
        {showExcluded && geo.features.map(feature => { const row = rows.get(feature.properties.name); if (!row) return null; const [cx, cy] = projection.center(feature.geometry); return <g key={`outline-${row.code}`} pointerEvents="none">{selected === row.district && <path d={projection.path(feature.geometry)} fill="none" stroke="#1D4ED8" strokeWidth="3.5" />}{row.priority_adjusted && <circle cx={cx} cy={cy} r={selected === row.district ? 7 : 5.2} fill="#1D4ED8" stroke="white" strokeWidth="2" />}</g>; })}
      </svg>
       <div className="map-bottom"><Legend metric={metric} /><label className="toggle-line"><input type="checkbox" checked={showExcluded} onChange={e => setShowExcluded(e.target.checked)} /> 관측 산림·수역 영역 겹쳐 보기</label>{showExcluded && <div className="inline-note"><span className="overlay-chip forest" /> 산림 <span className="overlay-chip water" /> 수역 · 표시용 도형은 15m로 단순화했습니다. 정확한 면적 계산은 원본 도형을 사용했습니다.</div>}<div className="map-attribution">배경지도: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap 기여자</a>{basemapError && <span> · 배경지도 일부를 불러오지 못했습니다.</span>}</div></div>
    </div><aside className="district-card" aria-live="polite"><span className="eyebrow">선택한 자치구</span><div className="district-title"><h3>{active.district}</h3>{active.priority_adjusted && <span className="priority-tag">◆ 관심 지역</span>}</div><p className="detail-lede">{active.priority_adjusted ? '노후주택 LQ는 1을 넘고 산림·수역 제외 면적당 진행 중 정비사업 수는 서울 기준보다 낮습니다.' : '관심 지역의 두 조건을 동시에 충족하지 않습니다.'}</p><div className="metric-mini"><span>{ADJUSTED_NAME}</span><strong>{f(active.density_adjusted, 3)} <small>구역/km²</small></strong><span>노후주택 LQ</span><strong>{f(active.lq, 2)} <small>배</small></strong></div><dl className="detail-list"><div><dt>진행 중 정비사업</dt><dd>{nf.format(active.renewal_count)}구역</dd></div><div><dt>전체 / 제외 후 면적</dt><dd>{f(active.total_km2, 2)} / {f(active.remaining_km2, 2)}km²</dd></div><div><dt>관측 산림 / 수역</dt><dd>{f(active.forest_km2, 2)} / {f(active.water_km2, 2)}km²</dd></div><div><dt>30년 이상 / 전체 주택</dt><dd>{nf.format(active.old_homes)} / {nf.format(active.homes)}호</dd></div><div><dt>노후주택 비율</dt><dd>{pct(active.old_share, 1)}</dd></div><div><dt>전체 면적 기준 밀도</dt><dd>{f(active.density_total, 3)}구역/km²</dd></div><div><dt>도엽 커버리지 상한</dt><dd>{pct(Math.min(1, active.tile_bbox_coverage_upper_bound), 1)}</dd></div></dl></aside></div>
  </section>;
}

function Scatter({ report, selected, setSelected }: { report: Report; selected: string; setSelected: (s: string) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const W = 720, H = 460, L = 66, R = 25, T = 25, B = 58;
  const xMin = 0.45, xMax = 2.08, yMin = 0, yMax = 1.72;
  const x = (n: number) => L + (n - xMin) / (xMax - xMin) * (W - L - R);
  const y = (n: number) => H - B - (n - yMin) / (yMax - yMin) * (H - T - B);
  const active = report.districts.find(r => r.district === (hover || selected))!;
  return <section className="panel" id="scatter" aria-labelledby="scatter-title"><div className="section-head"><div><span className="eyebrow">02 / RELATIONSHIP</span><h2 id="scatter-title">두 지표의 교차점</h2><p>오른쪽 아래는 노후주택 비중이 서울보다 높고, 사업 Density는 서울보다 낮은 영역입니다.</p></div></div>
    <div className="plot-wrap"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`노후주택 LQ와 ${ADJUSTED_NAME} 산점도`}>
      <rect x={x(1)} y={y(report.summary.seoul_density_adjusted)} width={x(xMax) - x(1)} height={y(0) - y(report.summary.seoul_density_adjusted)} fill="#EFF6FF" />
      {[0, .4, .8, 1.2, 1.6].map(t => <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#E2E8F0" /><text x={L - 12} y={y(t) + 4} textAnchor="end" className="axis-tick">{t.toFixed(1)}</text></g>)}
      {[.5, 1, 1.5, 2].map(t => <g key={t}><line x1={x(t)} x2={x(t)} y1={T} y2={H - B} stroke="#F1F5F9" /><text x={x(t)} y={H - B + 24} textAnchor="middle" className="axis-tick">{t.toFixed(1)}</text></g>)}
      <line x1={x(1)} x2={x(1)} y1={T} y2={H - B} stroke="#1D4ED8" strokeDasharray="6 5" strokeWidth="1.5" /><line x1={L} x2={W - R} y1={y(report.summary.seoul_density_adjusted)} y2={y(report.summary.seoul_density_adjusted)} stroke="#1D4ED8" strokeDasharray="6 5" strokeWidth="1.5" />
      <text x={x(1) + 7} y={T + 12} className="reference-label">LQ = 1</text><text x={W - R - 6} y={y(report.summary.seoul_density_adjusted) - 8} textAnchor="end" className="reference-label">서울 {f(report.summary.seoul_density_adjusted, 3)}</text>
      <text x={x(1) + 15} y={y(.12)} className="quadrant-label">관심 영역 ↘</text>
      {report.districts.map(row => <g key={row.code} onMouseEnter={() => setHover(row.district)} onMouseLeave={() => setHover(null)}><circle cx={x(row.lq)} cy={y(row.density_adjusted)} r={row.district === selected ? 9 : 6.5} fill={metricColor(row.lq, 'lq')} stroke={row.district === selected || row.priority_adjusted ? '#1D4ED8' : '#334155'} strokeWidth={row.district === selected ? 3 : row.priority_adjusted ? 2 : 1} onClick={() => setSelected(row.district)} className="plot-point" tabIndex={0} role="button" aria-label={`${row.district}: LQ ${f(row.lq, 2)}, 산림·수역 제외 면적당 진행 중 정비사업 수 ${f(row.density_adjusted, 3)}`} onKeyDown={e => { if (e.key === 'Enter') setSelected(row.district); }}><title>{row.district}: LQ {f(row.lq, 2)}, Density {f(row.density_adjusted, 3)}</title></circle></g>)}
       <text x={W / 2} y={H - 7} textAnchor="middle" className="axis-label">노후주택 LQ · 배</text><text transform={`translate(16 ${H / 2}) rotate(-90)`} textAnchor="middle" className="axis-label">진행 중 정비사업 수 · 구역/km²</text>
    </svg></div><div className="plot-footer"><div><span className="dot" style={{ background: metricColor(active.lq, 'lq') }} /> <strong>{active.district}</strong> · LQ {f(active.lq, 2)} · Density {f(active.density_adjusted, 3)}구역/km²</div><span>점 색상: LQ 척도 · 파란 윤곽: 관심/선택</span></div><Legend metric="lq" /></section>;
}

function Ranking({ report, selected, setSelected }: { report: Report; selected: string; setSelected: (s: string) => void }) {
  const [metric, setMetric] = useState<BarMetric>('density_adjusted');
  const sorted = [...report.districts].sort((a, b) => b[metric] - a[metric]);
  const max = Math.max(...sorted.map(r => r[metric])) * 1.08;
  const baseline = metric === 'lq' ? 1 : report.summary.seoul_density_adjusted;
   return <section className="panel" id="ranking" aria-labelledby="ranking-title"><div className="section-head"><div><span className="eyebrow">03 / RANKING</span><h2 id="ranking-title">자치구별 순위</h2><p>같은 지표는 지도와 동일한 구간·색을 사용합니다. 행을 누르면 다른 차트에도 선택이 반영됩니다.</p></div><div className="segmented" role="group" aria-label="순위 지표"><button className={metric === 'density_adjusted' ? 'active' : ''} onClick={() => setMetric('density_adjusted')}>진행 중 정비사업 수/km²</button><button className={metric === 'lq' ? 'active' : ''} onClick={() => setMetric('lq')}>노후주택 LQ</button></div></div>
    <div className="bar-caption"><strong>{metricLabel(metric)}</strong><span>서울 기준 {f(baseline, metric === 'lq' ? 1 : 3)} {metricUnit(metric)}</span></div>
    <div className="bar-list">{sorted.map((row, i) => <button className={`bar-row ${selected === row.district ? 'selected' : ''}`} key={row.code} onClick={() => setSelected(row.district)}><span className="bar-rank">{String(i + 1).padStart(2, '0')}</span><span className="bar-name">{row.district}{row.priority_adjusted && <span className="small-diamond" title="관심 지역">◆</span>}</span><span className="bar-track"><span className="bar-baseline" style={{ left: `${baseline / max * 100}%` }} /><span className="bar-fill" style={{ width: `${row[metric] / max * 100}%`, background: metricColor(row[metric], metric) }} /></span><strong>{metricDisplay(row[metric], metric)}</strong></button>)}</div><Legend metric={metric} /></section>;
}

function Comparison({ report, selected, setSelected }: { report: Report; selected: string; setSelected: (s: string) => void }) {
  const sorted = [...report.districts].sort((a, b) => b.rank_change - a.rank_change);
  const max = Math.max(...report.districts.map(r => r.density_adjusted)) * 1.05;
  return <section className="panel" id="comparison" aria-labelledby="comparison-title"><div className="section-head"><div><span className="eyebrow">04 / DENOMINATOR SHIFT</span><h2 id="comparison-title">분모를 바꾸면 순위가 움직인다</h2><p>두 Density는 같은 358개 사업 목록을 사용합니다. 면적만 바꿔 영향을 비교합니다.</p></div><span className="section-badge">관심 지역 구성 6곳 → 6곳</span></div>
    <div className="compare-key"><span><i className="key-line full" /> 전체 면적</span><span><i className="key-line adjusted" /> 산림·수역 제외</span><span>공통 색 구간: Density 0.3 · 0.6 · 0.9 · 1.2 구역/km²</span></div>
    <div className="comparison-list">{sorted.map(row => <button key={row.code} className={`compare-row ${selected === row.district ? 'selected' : ''}`} onClick={() => setSelected(row.district)}><span className="compare-name">{row.district}</span><span className="pair-bars"><span className="pair-bar muted" style={{ width: `${row.density_total / max * 100}%`, background: metricColor(row.density_total, 'density_total') }} /><span className="pair-bar" style={{ width: `${row.density_adjusted / max * 100}%`, background: metricColor(row.density_adjusted, 'density_adjusted') }} /></span><span className="compare-values">{f(row.density_total, 2)} → <b>{f(row.density_adjusted, 2)}</b></span><span className={`rank-delta ${row.rank_change > 0 ? 'up' : ''}`}>{row.rank_change > 0 ? `↑${row.rank_change}` : row.rank_change < 0 ? `↓${-row.rank_change}` : '—'}</span></button>)}</div><p className="chart-note">예: 서초구는 보정 후 6계단, 강북구는 5계단 상승했습니다. 중랑구는 5계단 내려갔습니다. 전체 면적 기준과 보정 기준의 관심 지역 구성은 이번 자료에서 같습니다.</p></section>;
}

type SortKey = 'district' | 'renewal_count' | 'old_homes' | 'homes' | 'old_share' | 'total_km2' | 'forest_km2' | 'water_km2' | 'excluded_union_km2' | 'remaining_km2' | 'density_total' | 'density_adjusted' | 'lq' | 'rank_change' | 'tile_bbox_coverage_upper_bound' | 'priority_adjusted';
const tableCols: { key: SortKey; label: string; unit?: string }[] = [
  { key: 'district', label: '자치구' }, { key: 'renewal_count', label: '사업', unit: '구역' },
  { key: 'old_homes', label: '30년 이상', unit: '호' }, { key: 'homes', label: '전체 주택', unit: '호' },
  { key: 'old_share', label: '노후 비율', unit: '%' }, { key: 'total_km2', label: '전체 면적', unit: 'km²' },
  { key: 'forest_km2', label: '산림', unit: 'km²' }, { key: 'water_km2', label: '수역', unit: 'km²' },
  { key: 'excluded_union_km2', label: '제외 합집합', unit: 'km²' }, { key: 'remaining_km2', label: '제외 후 면적', unit: 'km²' }, { key: 'density_total', label: '전체 Density', unit: '구역/km²' },
   { key: 'density_adjusted', label: '진행 중 사업 수/제외 면적', unit: '구역/km²' }, { key: 'lq', label: 'LQ', unit: '배' },
  { key: 'rank_change', label: '순위 변화' }, { key: 'tile_bbox_coverage_upper_bound', label: '도엽 범위 상한', unit: '%' },
  { key: 'priority_adjusted', label: '관심 지역' },
];
function Table({ report, selected, setSelected }: { report: Report; selected: string; setSelected: (s: string) => void }) {
  const [sort, setSort] = useState<SortKey>('district'); const [ascending, setAscending] = useState(true);
  const rows = [...report.districts].sort((a, b) => { const av = a[sort], bv = b[sort]; const cmp = typeof av === 'string' ? av.localeCompare(String(bv), 'ko') : Number(av) - Number(bv); return (ascending ? 1 : -1) * cmp; });
  const sortBy = (key: SortKey) => { if (sort === key) setAscending(!ascending); else { setSort(key); setAscending(key === 'district'); } };
  const cell = (row: Row, key: SortKey) => key === 'district' ? <><strong>{row.district}</strong>{row.priority_adjusted && <span className="table-priority">◆</span>}</> : key === 'priority_adjusted' ? row.priority_adjusted ? '◆ 해당' : '—' : key === 'tile_bbox_coverage_upper_bound' ? pct(Math.min(1, row.tile_bbox_coverage_upper_bound), 1) : key === 'old_share' ? pct(row.old_share, 1) : ['renewal_count', 'old_homes', 'homes'].includes(key) ? nf.format(row[key] as number) : key === 'rank_change' ? `${row.rank_change > 0 ? '+' : ''}${row.rank_change}` : f(row[key] as number, ['density_total', 'density_adjusted'].includes(key) ? 3 : 2);
  const download = () => { const fields = ['code','district','renewal_count','old_homes','homes','old_share','total_km2','forest_km2','water_km2','excluded_union_km2','remaining_km2','density_total','density_adjusted','lq','rank_total','rank_adjusted','rank_change','priority_total','priority_adjusted','tile_bbox_coverage_upper_bound'] as const; const csv = '\uFEFF' + [fields.join(','), ...report.districts.map(row => fields.map(key => JSON.stringify(row[key])).join(','))].join('\r\n'); const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = 'seoul_district_analysis_provisional.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
  return <section className="panel table-panel" id="table" aria-labelledby="table-title"><div className="section-head"><div><span className="eyebrow">05 / DATA TABLE</span><h2 id="table-title">25개 자치구 결과표</h2><p>열 제목을 눌러 정렬할 수 있습니다. 파란 기호는 관심 지역, 행 선택은 모든 차트에 반영됩니다.</p></div><button className="primary-button" onClick={download}>CSV 내려받기 <span aria-hidden="true">↗</span></button></div><div className="table-scroll"><table><thead><tr>{tableCols.map(col => <th key={col.key} aria-sort={sort === col.key ? ascending ? 'ascending' : 'descending' : 'none'}><button onClick={() => sortBy(col.key)}>{col.label}{col.unit && <small>{col.unit}</small>}<span aria-hidden="true">{sort === col.key ? ascending ? ' ↑' : ' ↓' : ' ↕'}</span></button></th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.code} className={selected === row.district ? 'selected' : ''} onClick={() => setSelected(row.district)}>{tableCols.map(col => <td key={col.key}>{cell(row, col.key)}</td>)}</tr>)}</tbody></table></div><p className="table-foot">화면 표시값은 반올림했습니다. 계산과 관심 지역 판정에는 반올림 전 값을 사용합니다. CSV에는 원래 숫자를 저장합니다.</p></section>;
}

function App() {
  const [report, setReport] = useState<Report | null>(null); const [geo, setGeo] = useState<Geo | null>(null); const [exclusion, setExclusion] = useState<ExclusionGeo | null>(null);
   const [selected, setSelected] = useState('노원구'); const [error, setError] = useState('');
  useEffect(() => { const base = import.meta.env.BASE_URL; Promise.all([fetch(`${base}data/report.json`).then(r => { if (!r.ok) throw new Error('분석 데이터 응답 오류'); return r.json(); }), fetch(`${base}seoul_districts.geojson`).then(r => { if (!r.ok) throw new Error('경계 데이터 응답 오류'); return r.json(); }), fetch(`${base}data/exclusion_areas.geojson`).then(r => { if (!r.ok) throw new Error('제외 영역 응답 오류'); return r.json(); })]).then(([r, g, e]) => { setReport(r); setGeo(g); setExclusion(e); }).catch(e => setError(String(e))); }, []);
  if (error) return <main className="load-message">보고서 데이터를 불러오지 못했습니다. {error}</main>;
  if (!report || !geo || !exclusion) return <main className="load-message">서울 도시 연구 보고서를 불러오는 중입니다…</main>;
  const priorities = report.districts.filter(r => r.priority_adjusted);
   return <><header className="site-header"><div className="header-inner"><a className="brand" href="#top"><span className="brand-mark">S</span><span>SEOUL <b>URBAN ATLAS</b><small>도시데이터분석 과제 03</small></span></a><nav aria-label="주요 섹션"><a href="#map">공간 분석</a><a href="#scatter">지표 관계</a><a href="#comparison">보정 비교</a><a href="#method">분석 방법</a></nav><a className="header-cta" href="#table">전체 결과 보기 <span aria-hidden="true">↗</span></a></div></header>
    <main id="top"><section className="hero"><div className="hero-content"><div className="hero-meta"><span className="pill">URBAN RESEARCH REPORT · 2026</span><span>서울 25개 자치구 · 잠정 분석</span></div><h1>오래된 집은 많은데,<br/><em>정비사업은 어디에 적을까?</em></h1><p className="hero-question">서울시에서 노후주택의 상대적 집중도는 높지만, 산림·수역을 제외한 면적당 주거 정비사업 밀도는 낮은 자치구는 어디인가?</p><div className="hero-actions"><a className="primary-button" href="#map">분석 지도 살펴보기 <span aria-hidden="true">↗</span></a><a className="text-link" href="#method">분석 방법 읽기 <span aria-hidden="true">↓</span></a></div><div className="hero-source">정비사업 2026.06 <i /> 주택 2025.11.01 <i /> 경계 2025.06 <i /> EGIS 제공 도엽</div></div><div className="hero-visual" aria-hidden="true"><div className="visual-grid" /><div className="visual-ring ring-one"/><div className="visual-ring ring-two"/><div className="visual-card"><span>FOCUS DISTRICTS</span><strong>{String(priorities.length).padStart(2, '0')}</strong><small>노후주택 LQ &gt; 1<br/>산림·수역 제외 면적당 진행 중 정비사업 수 &lt; 서울 기준</small></div><div className="visual-coord">37°33′N<br/>126°58′E</div></div></section>
     <section className="content-wrap">
      <section className="kpi-grid" aria-label="핵심 결과"><div className="kpi"><span>관심 지역</span><strong>{priorities.length}<small>개 구</small></strong><p>LQ &gt; 1 · 산림·수역 제외 면적당 진행 중 정비사업 수 &lt; 서울</p></div><div className="kpi"><span>서울 산림·수역 제외 면적당 진행 중 정비사업 수</span><strong>{f(report.summary.seoul_density_adjusted, 3)}</strong><p>정비사업 구역/km²</p></div><div className="kpi"><span>분석 대상 사업</span><strong>{nf.format(report.summary.renewal_count)}</strong><p>주거 정비사업 구역</p></div><div className="kpi"><span>30년 이상 주택</span><strong>{nf.format(report.summary.old_homes)}</strong><p>서울 25개 구 합계 · 호</p></div></section>
      <div className="section-intro"><span className="eyebrow">THE QUESTION</span><h2>두 지표를 겹쳐 보면,<br/><em>서로 다른 도시의 표정이 보입니다.</em></h2><p>노후주택의 상대적 비중과 정비사업의 공간 밀도를 같은 자치구 단위에서 비교했습니다. 아래 시각화에서 구를 선택하면 수치와 순위를 함께 확인할 수 있습니다.</p></div>
      <MapPanel report={report} geo={geo} exclusion={exclusion} selected={selected} setSelected={setSelected} />
      <div className="two-col"><Scatter report={report} selected={selected} setSelected={setSelected} /><Ranking report={report} selected={selected} setSelected={setSelected} /></div>
      <Comparison report={report} selected={selected} setSelected={setSelected} />
      <Table report={report} selected={selected} setSelected={setSelected} />
      <section className="interpretation" id="findings"><div className="section-head"><div><span className="eyebrow">06 / READING THE CITY</span><h2>서울 자치구별 주요 결과</h2></div></div><div className="insight-grid"><article><span className="insight-number">01</span><h3>서로 다른 고점</h3><p><b>확인된 사실.</b> 산림·수역 제외 면적당 진행 중 정비사업 수는 영등포구 1.552, 양천구 1.512구역/km²가 높고 강서구 0.202가 낮습니다. LQ는 노원구 1.952, 도봉구 1.644가 높습니다. 높은 노후주택 비율과 높은 사업 밀도가 같은 곳에 모인 것은 아닙니다.</p></article><article><span className="insight-number">02</span><h3>관심 지역의 실제 규모</h3><p><b>확인된 사실.</b> 관심 지역은 종로·강북·도봉·노원·강서·관악구입니다. 노원구의 30년 이상 주택은 112,588호로 이 가운데 가장 많습니다. 종로구는 17,729호로 상대적 집중도와 절대 규모가 다릅니다.</p></article><article><span className="insight-number">03</span><h3>산림·수역 보정의 효과</h3><p><b>확인된 사실.</b> 서울 Density 기준은 전체 면적 0.591에서 보정 후 0.814구역/km²로 높아졌습니다. 서초구는 보정 후 순위가 6계단, 강북구는 5계단 올랐습니다. 관심 지역 구성은 이번 자료에서 변하지 않았습니다.</p></article></div></section>
      <section className="method" id="method"><div className="section-head"><div><span className="eyebrow">07 / METHODOLOGY</span><h2>지표와 자료를 만든 방법</h2><p>분석 단위는 서울 25개 자치구, 면적 계산 단위는 km², 사업 단위는 구역입니다.</p></div></div><div className="formula-grid"><article><span className="formula-index">01</span><h3>산림·수역 제외 면적당 진행 중 정비사업 수</h3><div className="formula">Dᵢ* = Rᵢ / Aᵢ*</div><p>Rᵢ: 주거 정비사업 구역 수<br/>Aᵢ*: 자치구 전체 면적에서 관측 산림·수역 합집합을 뺀 면적</p><small>단위: 구역/km² · 서울 기준 358 / 439.792 = 0.814</small></article><article><span className="formula-index">02</span><h3>노후주택 LQ</h3><div className="formula">LQᵢ = (Oᵢ/Hᵢ) / (Oₛ/Hₛ)</div><p>Oᵢ: 30년 이상 주택 수<br/>Hᵢ: 전체 주택 수 · ₛ: 서울 25개 구 합계</p><small>1보다 크면 노후주택 비율이 서울 전체보다 높음</small></article></div><div className="method-steps"><div><b>01 · 사업 선정</b><p>서울시 2026년 6월 도시정비사업 엑셀 496건에서 고유 CODE로 중복을 확인하고 주택정비형 재개발·공동주택/아파트지구/단독주택 재건축 358건을 포함했습니다. 도시정비형 재개발은 주거 여부를 일괄 확인할 수 없어 제외했습니다.</p></div><div><b>02 · 산림·수역 면적</b><p>EGIS 세분류 SHP의 실제 `L3_CODE` 중 산림 311·321·331, 수역 711·712·721을 사용했습니다. EPSG:5186 원본을 EPSG:5179로 변환하고 자기 교차 도형을 수선한 뒤, 자치구 경계에서 산림·수역의 합집합을 한 번만 차감했습니다. 습지·초지·나지는 제외하지 않았습니다.</p></div><div><b>03 · 비교와 분류</b><p>전체 면적당 진행 중 정비사업 수도 같은 358개 사업으로 계산했습니다. 서울 기준은 자치구 밀도의 평균이 아니라 사업 총수÷면적 총합입니다. 관심 지역은 반올림 전 LQ &gt; 1과 산림·수역 제외 면적당 진행 중 정비사업 수 &lt; 서울 산림·수역 제외 면적당 진행 중 정비사업 수를 동시에 적용했습니다.</p></div></div><div className="source-grid"><div><b>정비사업</b><a href="https://data.seoul.go.kr/dataList/OA-22856/F/1/datasetView.do" target="_blank" rel="noreferrer">서울열린데이터광장 · 2026.06 ↗</a></div><div><b>주택</b><a href="https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1JU1521" target="_blank" rel="noreferrer">KOSIS · 30년 이상 주택, 2025 ↗</a><a href="https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1JU1501" target="_blank" rel="noreferrer">KOSIS · 전체 주택, 2025 ↗</a></div><div><b>경계·피복</b><a href="https://sgis.kostat.go.kr/" target="_blank" rel="noreferrer">SGIS · 2025년 2분기 경계 ↗</a><a href="https://egis.me.go.kr/intro/land.do" target="_blank" rel="noreferrer">EGIS · 세분류 토지피복지도 ↗</a></div></div></section>
      <footer><div className="footer-brand">SEOUL <b>URBAN ATLAS</b><small>도시데이터분석 과제 03</small></div><a href="#top">맨 위로 ↑</a></footer>
    </section></main></>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
