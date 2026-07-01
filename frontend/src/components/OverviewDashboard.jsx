import React from 'react';

export default function OverviewDashboard({ baseline }) {
  if (!baseline) return null;

  const { summary, health } = baseline;
  const { swot } = health;

  // Format currency in INR format (e.g. ₹1,21,318.06)
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

  const scorePct = summary.health_score || 50;

  return (
    <div className="overview-dashboard">
      {/* 1. Header Cards Grid */}
      <div className="metrics-grid-top">
        <div className="metric-card-premium">
          <span className="metric-title-premium">Your Total Investment</span>
          <span className="metric-value-premium">{formatINR(summary.total_investment)}</span>
        </div>
        
        <div className="metric-card-premium">
          <span className="metric-title-premium">Portfolio Worth Today</span>
          <span className="metric-value-premium">{formatINR(summary.portfolio_worth)}</span>
        </div>

        <div className="metric-card-premium">
          <span className="metric-title-premium">Total Returns</span>
          <div className="metric-returns-container">
            <span className={`metric-value-premium ${summary.total_returns >= 0 ? 'text-gain' : 'text-loss'}`}>
              {formatINR(summary.total_returns)}
            </span>
            <span className={`metric-badge-pct ${summary.total_returns >= 0 ? 'badge-gain' : 'badge-loss'}`}>
              {formatPct(summary.total_returns_pct)}
            </span>
          </div>
        </div>

        <div className="metric-card-premium">
          <span className="metric-title-premium">Today's Gain / Loss</span>
          <div className="metric-returns-container">
            <span className={`metric-value-premium ${summary.today_gain >= 0 ? 'text-gain' : 'text-loss'}`}>
              {formatINR(summary.today_gain)}
            </span>
            <span className={`metric-badge-pct ${summary.today_gain >= 0 ? 'badge-gain' : 'badge-loss'}`}>
              {formatPct(summary.today_pct)}
            </span>
          </div>
        </div>

        <div className="metric-card-premium health-score-card">
          <span className="metric-title-premium">Portfolio Health</span>
          <div className="health-score-content">
            <div className="health-gauge">
              <svg viewBox="0 0 36 36" className="circular-chart">
                <path className="circle-bg"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                <path className="circle"
                  strokeDasharray={`${scorePct}, 100`}
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                <text x="18" y="20.35" className="percentage">{summary.health_grade}</text>
              </svg>
            </div>
            <div className="health-texts">
              <span className="health-grade-text">{summary.health_grade} Grade</span>
              <span className="health-score-val">{scorePct}/100</span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Core Portfolio Insights (SWOT) */}
      <div className="swot-analysis-card">
        <h3 className="swot-title">Core Portfolio Health Analysis</h3>
        <div className="swot-grid">
          <div className="swot-quadrant quadrant-strengths">
            <h4 className="quadrant-title"><span className="swot-icon">✓</span> Strengths</h4>
            <ul className="swot-list">
              {swot.strengths.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          </div>
          
          <div className="swot-quadrant quadrant-weaknesses">
            <h4 className="quadrant-title"><span className="swot-icon">⚠</span> Weaknesses</h4>
            <ul className="swot-list">
              {swot.weaknesses.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          </div>

          <div className="swot-quadrant quadrant-opportunities">
            <h4 className="quadrant-title"><span className="swot-icon">💡</span> Opportunities</h4>
            <ul className="swot-list">
              {swot.opportunities.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          </div>

          <div className="swot-quadrant quadrant-threats">
            <h4 className="quadrant-title"><span className="swot-icon">⚡</span> Threats</h4>
            <ul className="swot-list">
              {swot.threats.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
