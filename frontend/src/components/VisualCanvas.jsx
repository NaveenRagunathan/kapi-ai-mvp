import { useState, useEffect, useCallback } from 'react';
import { DrawdownChart, ComparisonChart, SectorChart, FactorRadar, MetricsGrid, CorrelationHeatmap } from './Charts';
import { getCorrelationMatrix } from '../api/service';
import OverviewDashboard from './OverviewDashboard';
import HoldingsTable from './HoldingsTable';
import ConstructingWealthAnimation from './ConstructingWealthAnimation';

export default function VisualCanvas({ canvasState, sessionId, baseline, loadingBaseline, onResetCanvas, onSetCanvasState }) {
  const [correlationData, setCorrelationData] = useState(null);
  const [corrLoading, setCorrLoading] = useState(false);

  const activeView = canvasState?.view || 'none';
  const data = canvasState?.data || {};

  // Fetch correlation matrix when correlation view is active
  const fetchCorrelation = useCallback(async () => {
    if (!sessionId || correlationData) return;
    setCorrLoading(true);
    try {
      const data = await getCorrelationMatrix(sessionId);
      setCorrelationData(data);
    } catch {
      // silently fail
    } finally {
      setCorrLoading(false);
    }
  }, [sessionId, correlationData]);

  useEffect(() => {
    if (activeView === 'correlation') {
      fetchCorrelation();
    }
  }, [activeView, fetchCorrelation]);

  // Show loading animation while baseline is being calculated
  if (loadingBaseline) {
    return (
      <div className="canvas-panel canvas-panel--loading">
        <ConstructingWealthAnimation />
      </div>
    );
  }

  // If no portfolio loaded yet
  if (!baseline) {
    return (
      <div className="canvas-empty">
        <div className="canvas-empty-icon" aria-hidden="true">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/>
          </svg>
        </div>
      </div>
    );
  }

  const tabs = [
    { id: 'none', label: 'Overview' },
    { id: 'performance', label: 'Performance' },
    { id: 'risk', label: 'Risk' },
    { id: 'diversification', label: 'Diversification' },
    { id: 'correlation', label: 'Correlation' },
  ];

  if (activeView === 'whatif' || (canvasState?.data && canvasState.view === 'whatif')) {
    tabs.push({ id: 'whatif', label: 'What-If' });
  }

  return (
    <div className="canvas-panel">
      <div className="canvas-tabs" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeView === tab.id}
            className={`canvas-tab ${activeView === tab.id ? 'active' : ''}`}
            onClick={() => {
              if (tab.id === 'none') {
                onResetCanvas();
              } else {
                onSetCanvasState({ view: tab.id, data: activeView === tab.id ? data : {} });
              }
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeView === 'none' ? (
        <div className="canvas-panel-scrollable" style={{ flex: 1, minHeight: 0 }}>
          <OverviewDashboard baseline={baseline} />
          <HoldingsTable holdings={baseline.holdings} />
        </div>
      ) : (
        <div className="canvas-panel-focused" style={{ flex: 1, minHeight: 0, padding: 'var(--space-md) var(--space-lg)' }}>
          <div className="canvas-focused-header">
            <h3 className="focused-title">
              {activeView === 'performance' && 'Return Performance Analysis'}
              {activeView === 'risk' && 'Risk & Drawdown Analysis'}
              {activeView === 'diversification' && 'Sector & Factor Diversification'}
              {activeView === 'correlation' && 'Asset Correlation Matrix'}
              {activeView === 'whatif' && 'What-If Simulation Results'}
            </h3>
          </div>

          <div className="canvas-focused-content">
            {activeView === 'performance' && (
              <div className="focus-layout">
                <div className="focus-metrics">
                  <MetricsGrid metrics={{
                    'Portfolio CAGR': data.portfolio_cagr || baseline.performance.portfolio_cagr,
                    'Benchmark CAGR': data.benchmark_cagr || baseline.performance.benchmark_cagr,
                    'Sharpe Ratio': data.portfolio_sharpe || baseline.performance.portfolio_sharpe,
                    'Active Return': data.active_return || baseline.performance.active_return,
                    'Sortino Ratio': data.sortino || baseline.performance.sortino,
                  }} />
                </div>
                <div className="focus-chart-container">
                  <ComparisonChart data={data.comparison || baseline.performance.comparison} />
                </div>
              </div>
            )}

            {activeView === 'risk' && (
              <div className="focus-layout">
                <div className="focus-metrics">
                  <MetricsGrid metrics={{
                    'Max Drawdown': data.max_drawdown || baseline.risk.max_drawdown,
                    'VaR (95%)': data.value_at_risk_95 || baseline.risk.value_at_risk_95,
                    'Portfolio Beta': data.portfolio_beta || baseline.risk.portfolio_beta,
                    'Ann. Volatility': data.volatility_annualized || baseline.risk.volatility_annualized,
                  }} />
                </div>
                <div className="focus-chart-container">
                  <DrawdownChart data={data.drawdown || baseline.risk.drawdown} />
                </div>
              </div>
            )}

            {activeView === 'diversification' && (
              <div className="focus-layout-diversification">
                <div className="diversification-chart-box">
                  <span className="diversification-eyebrow">Concentration</span>
                  <h4>Sector Allocation</h4>
                  <SectorChart data={Object.entries(data.sectors || baseline.diversification.sectors).map(([name, value]) => ({ name, value }))} />
                </div>
                <div className="diversification-chart-box">
                  <span className="diversification-eyebrow">Style Tilt</span>
                  <h4>Factor Overlaps</h4>
                  <FactorRadar data={Object.entries(data.factor_exposures || baseline.diversification.factor_exposures).map(([name, value]) => ({ name, value }))} />
                </div>
              </div>
            )}

            {activeView === 'correlation' && (
              <div className="focus-layout-correlation">
                {corrLoading ? (
                  <div className="canvas-loading">
                    <span className="dot-pulse" />
                    <span>Computing correlation matrix&hellip;</span>
                  </div>
                ) : (correlationData || baseline.correlation) ? (
                  <CorrelationHeatmap data={correlationData || baseline.correlation} />
                ) : (
                  <div className="canvas-tab-empty">No correlation data available.</div>
                )}
              </div>
            )}

            {activeView === 'whatif' && (
              <div className="focus-layout">
                <div className="focus-metrics">
                  <MetricsGrid metrics={{
                    'Original Sharpe': data.original_sharpe,
                    'Simulated Sharpe': data.simulated_sharpe,
                    'Original MDD': data.original_max_drawdown,
                    'Simulated MDD': data.simulated_max_drawdown,
                  }} />
                </div>
                {data.message && (
                  <div className="whatif-delta-report">
                    <h4 className="delta-report-title">Simulation Analysis</h4>
                    <p className="whatif-message">{data.message}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
