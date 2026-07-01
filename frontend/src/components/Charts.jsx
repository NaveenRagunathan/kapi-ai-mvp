import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  Legend,
} from 'recharts';

export function DrawdownChart({ data }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="chart-card">
      <h4>Drawdown Curve</h4>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="drawdownFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef4444" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} domain={['auto', 0]} />
          <Tooltip
            contentStyle={{ background: 'rgba(0,45,32,0.95)', border: '1px solid rgba(0,136,94,0.3)', borderRadius: '8px', fontSize: '13px' }}
            formatter={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <Area type="monotone" dataKey="drawdown" stroke="#ef4444" fill="url(#drawdownFill)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ComparisonChart({ data }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="chart-card">
      <h4>Portfolio vs Benchmark</h4>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00885e" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#00885e" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="benchmarkFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ffffff" stopOpacity={0.15} />
              <stop offset="100%" stopColor="#ffffff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} />
          <YAxis tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${(v).toFixed(0)}`} />
          <Tooltip
            contentStyle={{ background: 'rgba(0,45,32,0.95)', border: '1px solid rgba(0,136,94,0.3)', borderRadius: '8px', fontSize: '13px' }}
          />
          <Legend wrapperStyle={{ fontSize: '12px' }} />
          <Area type="monotone" dataKey="portfolio" stroke="#00885e" fill="url(#portfolioFill)" strokeWidth={2} name="Portfolio" />
          <Area type="monotone" dataKey="benchmark" stroke="rgba(255,255,255,0.5)" fill="url(#benchmarkFill)" strokeWidth={2} strokeDasharray="4 2" name="Benchmark" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// Ordered palette for known sectors — teal/blue/amber family stays inside the
// app's emerald identity. "Unknown" is deliberately excluded and rendered
// with a hatched pattern instead, so it reads as "unclassified" rather than
// competing with real data for visual weight.
const SECTOR_PALETTE = ['#00c389', '#00885e', '#2dd4bf', '#38bdf8', '#a78bfa', '#f59e0b', '#fb7185', '#94a3b8'];

export function SectorChart({ data }) {
  if (!data || data.length === 0) return null;

  const sorted = [...data].sort((a, b) => b.value - a.value);
  const total = sorted.reduce((sum, d) => sum + (d.value || 0), 0) || 1;
  let known = 0;
  const segments = sorted.map((d) => {
    const isUnknown = d.name === 'Unknown';
    if (!isUnknown) known += d.value;
    return { ...d, pct: (d.value / total) * 100, isUnknown };
  });
  const knownPct = (known / total) * 100;

  return (
    <div className="sector-viz">
      <div className="sector-bar" role="img" aria-label="Sector allocation breakdown">
        {segments.map((seg, i) => (
          <div
            key={seg.name}
            className={`sector-bar-segment ${seg.isUnknown ? 'sector-bar-segment--unknown' : ''}`}
            style={{
              width: `${seg.pct}%`,
              background: seg.isUnknown ? undefined : SECTOR_PALETTE[i % SECTOR_PALETTE.length],
            }}
            title={`${seg.name}: ${seg.pct.toFixed(1)}%`}
          />
        ))}
      </div>

      <ul className="sector-legend">
        {segments.map((seg, i) => (
          <li key={seg.name} className="sector-legend-row">
            <span
              className={`sector-legend-dot ${seg.isUnknown ? 'sector-legend-dot--unknown' : ''}`}
              style={{ background: seg.isUnknown ? undefined : SECTOR_PALETTE[i % SECTOR_PALETTE.length] }}
            />
            <span className="sector-legend-name">{seg.name}</span>
            <span className="sector-legend-pct">{seg.pct.toFixed(1)}%</span>
          </li>
        ))}
      </ul>

      {knownPct < 50 && (
        <p className="sector-unknown-note">
          {knownPct === 0
            ? "Sector classification isn't available for these holdings yet — this fills in as coverage expands."
            : `Sector data is only classified for ${knownPct.toFixed(0)}% of this portfolio right now.`}
        </p>
      )}
    </div>
  );
}

const FACTOR_DEFINITIONS = {
  Size: 'Share of the portfolio in large, established companies vs. smaller ones.',
  Value: 'Tilt toward statistically "cheap" stocks (low price relative to earnings).',
  Momentum: 'Tilt toward stocks with strong recent price trends.',
};

export function FactorRadar({ data }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="factor-viz">
      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={data} margin={{ top: 8, right: 24, left: 24, bottom: 8 }}>
          <defs>
            <radialGradient id="factorFill" cx="50%" cy="50%" r="70%">
              <stop offset="0%" stopColor="#00c389" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#00885e" stopOpacity={0.12} />
            </radialGradient>
          </defs>
          <PolarGrid stroke="rgba(255,255,255,0.12)" />
          <PolarAngleAxis dataKey="name" tick={{ fontSize: 13, fill: 'rgba(255,255,255,0.75)', fontWeight: 600 }} />
          <PolarRadiusAxis angle={90} domain={[0, 1]} tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.35)' }} tickCount={5} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
          <Tooltip
            contentStyle={{ background: 'rgba(0,45,32,0.95)', border: '1px solid rgba(0,136,94,0.3)', borderRadius: '8px', fontSize: '13px' }}
            formatter={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <Radar dataKey="value" stroke="#00c389" fill="url(#factorFill)" strokeWidth={2.5} dot={{ r: 4, fill: '#00c389', strokeWidth: 0 }} />
        </RadarChart>
      </ResponsiveContainer>

      <ul className="factor-legend">
        {data.map((d) => (
          <li key={d.name} className="factor-legend-row">
            <span className="factor-legend-head">
              <span className="factor-legend-name">{d.name}</span>
              <span className="factor-legend-pct">{(d.value * 100).toFixed(0)}%</span>
            </span>
            {FACTOR_DEFINITIONS[d.name] && (
              <span className="factor-legend-def">{FACTOR_DEFINITIONS[d.name]}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MetricsGrid({ metrics }) {
  if (!metrics || Object.keys(metrics).length === 0) return null;
  return (
    <div className="metrics-grid">
      {Object.entries(metrics).map(([key, value]) => (
        <div key={key} className="metric-card">
          <span className="metric-label">{key.replace(/_/g, ' ')}</span>
          <span className={`metric-value ${typeof value === 'number' && value < 0 ? 'negative' : ''}`}>
            {typeof value === 'number'
              ? (Math.abs(value) > 1 ? value.toFixed(2) : (value * 100).toFixed(1) + '%')
              : value}
          </span>
        </div>
      ))}
    </div>
  );
}

export function CorrelationHeatmap({ data }) {
  if (!data || !data.matrix || data.matrix.length === 0) return null;
  const { tickers, matrix } = data;
  const n = tickers.length;
  const cellSize = Math.min(56, Math.floor(320 / n));

  function getColor(value) {
    // -1 = red, 0 = neutral, +1 = green (emerald)
    if (value >= 0) {
      const intensity = value;
      const l = 35 + (1 - intensity) * 30;
      const c = intensity * 0.18;
      return `oklch(${l}% ${c} 160)`;
    } else {
      const intensity = Math.abs(value);
      const l = 35 + (1 - intensity) * 30;
      const c = intensity * 0.18;
      return `oklch(${l}% ${c} 25)`;
    }
  }

  return (
    <div className="chart-card">
      <h4>Return Correlation Matrix (1Y daily)</h4>
      <div className="corr-heatmap" role="img" aria-label="Correlation heatmap">
        <div className="corr-grid" style={{ gridTemplateColumns: `auto repeat(${n}, ${cellSize}px)` }}>
          {/* Top-left empty */}
          <div className="corr-cell corr-empty" />
          {/* Column headers */}
          {tickers.map((t) => (
            <div key={t} className="corr-cell corr-header" style={{ width: cellSize }}>
              {t.replace('.NS', '').slice(0, 6)}
            </div>
          ))}
          {/* Rows */}
          {matrix.map((row, i) => (
            <>
              <div key={`row-${i}`} className="corr-cell corr-header corr-row-label">
                {tickers[i].replace('.NS', '').slice(0, 6)}
              </div>
              {row.map((val, j) => (
                <div
                  key={`${i}-${j}`}
                  className="corr-cell corr-value"
                  style={{ background: getColor(val), width: cellSize, height: cellSize }}
                  title={`${tickers[i]} / ${tickers[j]}: ${val.toFixed(2)}`}
                  aria-label={`${tickers[i]} to ${tickers[j]} correlation: ${val.toFixed(2)}`}
                >
                  <span style={{ fontSize: Math.max(9, cellSize * 0.22) + 'px' }}>
                    {val.toFixed(2)}
                  </span>
                </div>
              ))}
            </>
          ))}
        </div>
        <div className="corr-legend">
          <span style={{ color: 'oklch(35% 0.18 25)' }}>&minus;1.0 negative</span>
          <div className="corr-legend-bar" />
          <span style={{ color: 'oklch(35% 0.18 160)' }}>+1.0 positive</span>
        </div>
      </div>
    </div>
  );
}
