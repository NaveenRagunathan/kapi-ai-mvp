import React from 'react';

export default function HoldingsTable({ holdings }) {
  if (!holdings || holdings.length === 0) return null;

  const formatINR = (val) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2
    }).format(val);
  };

  const formatPct = (val) => {
    const sign = val >= 0 ? '+' : '';
    return `${sign}${(val * 100).toFixed(2)}%`;
  };

  return (
    <div className="holdings-table-container">
      <div className="holdings-table-header">
        <h3 className="holdings-title">My Holdings</h3>
        <span className="holdings-subtitle">{holdings.length} stocks weighted by current value</span>
      </div>
      <div className="table-responsive">
        <table className="holdings-table">
          <thead>
            <tr>
              <th scope="col" className="text-left">Company / Ticker</th>
              <th scope="col" className="text-right">Weight</th>
              <th scope="col" className="text-right">Live Price</th>
              <th scope="col" className="text-right">Invested Value</th>
              <th scope="col" className="text-right">Current Value</th>
              <th scope="col" className="text-right">Today %</th>
              <th scope="col" className="text-right">Today P&L</th>
              <th scope="col" className="text-right">Overall %</th>
              <th scope="col" className="text-right">Overall P&L</th>
              <th scope="col" className="text-center">Signal</th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((h, idx) => {
              const weightPct = h.weight * 100;
              const isTodayGain = h.today_percent >= 0;
              const isOverallGain = h.pl_percent >= 0;

              return (
                <tr key={idx}>
                  <td className="ticker-cell">
                    <div className="holding-logo-placeholder">
                      {h.ticker.slice(0, 2)}
                    </div>
                    <div className="ticker-meta">
                      <span className="ticker-company">{h.name}</span>
                      <span className="ticker-sym">{h.ticker}</span>
                    </div>
                  </td>
                  
                  <td className="text-right weight-cell">
                    <span className="weight-badge">{(weightPct).toFixed(1)}%</span>
                  </td>

                  <td className="text-right font-mono">{formatINR(h.live_price)}</td>
                  
                  <td className="text-right font-mono">{formatINR(h.invested_value)}</td>
                  
                  <td className="text-right font-mono font-bold">{formatINR(h.current_value)}</td>
                  
                  <td className={`text-right font-mono ${isTodayGain ? 'text-gain' : 'text-loss'}`}>
                    {formatPct(h.today_percent)}
                  </td>
                  
                  <td className={`text-right font-mono ${isTodayGain ? 'text-gain' : 'text-loss'}`}>
                    {formatINR(h.today_pl)}
                  </td>

                  <td className={`text-right font-mono ${isOverallGain ? 'text-gain' : 'text-loss'}`}>
                    {formatPct(h.pl_percent)}
                  </td>
                  
                  <td className={`text-right font-mono ${isOverallGain ? 'text-gain' : 'text-loss'}`}>
                    {formatINR(h.pl_value)}
                  </td>

                  <td className="text-center">
                    <span className={`signal-pill ${
                      h.signal === 'Trending Up' ? 'signal-up' : 
                      h.signal === 'Downtrend' ? 'signal-down' : 
                      'signal-neutral'
                    }`}>
                      {h.signal}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
