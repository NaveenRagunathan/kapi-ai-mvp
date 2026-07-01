import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
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

export function SectorChart({ data }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="chart-card">
      <h4>Sector Exposure</h4>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }} layout="vertical">
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 10, fill: 'rgba(255,255,255,0.4)' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} domain={[0, 1]} />
          <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.6)' }} tickLine={false} axisLine={false} width={90} />
          <Tooltip
            contentStyle={{ background: 'rgba(0,45,32,0.95)', border: '1px solid rgba(0,136,94,0.3)', borderRadius: '8px', fontSize: '13px' }}
            formatter={(v) => `${(v * 100).toFixed(1)}%`}
          />
          <Bar dataKey="value" fill="#00885e" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function FactorRadar({ data }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="chart-card">
      <h4>Factor Exposures</h4>
      <ResponsiveContainer width="100%" height={220}>
        <RadarChart data={data} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
          <PolarGrid stroke="rgba(255,255,255,0.1)" />
          <PolarAngleAxis dataKey="name" tick={{ fontSize: 11, fill: 'rgba(255,255,255,0.5)' }} />
          <PolarRadiusAxis angle={90} domain={[0, 1]} tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.3)' }} tickCount={4} />
          <Tooltip
            contentStyle={{ background: 'rgba(0,45,32,0.95)', border: '1px solid rgba(0,136,94,0.3)', borderRadius: '8px', fontSize: '13px' }}
            formatter={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <Radar dataKey="value" stroke="#00885e" fill="#00885e" fillOpacity={0.25} strokeWidth={2} />
        </RadarChart>
      </ResponsiveContainer>
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
