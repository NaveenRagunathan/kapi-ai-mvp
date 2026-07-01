import { useState, useEffect, useCallback } from 'react';
import { DrawdownChart, ComparisonChart, SectorChart, FactorRadar, MetricsGrid, CorrelationHeatmap } from './Charts';
import { getCorrelationMatrix } from '../api/service';

const TABS = [
  { id: 'performance', label: 'Performance' },
  { id: 'risk', label: 'Risk' },
  { id: 'diversification', label: 'Diversification' },
  { id: 'correlation', label: 'Correlation' },
  { id: 'whatif', label: 'What-If' },
];

export default function VisualCanvas({ canvasState, sessionId }) {
  const [activeTab, setActiveTab] = useState('performance');
  const [correlationData, setCorrelationData] = useState(null);
  const [corrLoading, setCorrLoading] = useState(false);

  // Sync active tab when canvas_state.view changes
  useEffect(() => {
    if (canvasState?.view && canvasState.view !== 'none') {
      const map = { whatif: 'whatif', performance: 'performance', risk: 'risk', diversification: 'diversification' };
      if (map[canvasState.view]) setActiveTab(map[canvasState.view]);
    }
  }, [canvasState?.view]);

  // Fetch correlation matrix when correlation tab is active
  const fetchCorrelation = useCallback(async () => {
    if (!sessionId || correlationData) return;
    setCorrLoading(true);
    try {
      const data = await getCorrelationMatrix(sessionId);
      setCorrelationData(data);
    } catch {
      // silently fail - correlation data unavailable
    } finally {
      setCorrLoading(false);
    }
  }, [sessionId, correlationData]);

  useEffect(() => {
    if (activeTab === 'correlation') fetchCorrelation();
  }, [activeTab, fetchCorrelation]);

  if (!canvasState) {
    return (
      <div className="canvas-empty">
        <div className="canvas-empty-icon" aria-hidden="true">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/>
          </svg>
        </div>
        <p className="canvas-empty-title">Visual Analysis</p>
        <p className="canvas-empty-sub">Ask the AI analyst a question to populate charts here</p>
        <div className="canvas-empty-hints">
          <span>"What are my risk metrics?"</span>
          <span>"Show sector exposure"</span>
          <span>"Analyze performance vs Nifty 50"</span>
        </div>
      </div>
    );
  }

  const data = canvasState.data || {};

  return (
    <div className="canvas-panel">
      <div className="canvas-tabs" role="tablist" aria-label="Analysis views">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`canvas-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="canvas-content" role="tabpanel">
        {activeTab === 'performance' && (
          <>
            {data.portfolio_cagr !== undefined ? (
              <MetricsGrid metrics={{
                'Portfolio CAGR': data.portfolio_cagr,
                'Benchmark CAGR': data.benchmark_cagr,
                'Sharpe Ratio': data.portfolio_sharpe,
                'Active Return': data.active_return,
                'Sortino Ratio': data.sortino,
              }} />
            ) : <EmptyTab label="performance" />}
            {data.comparison && <ComparisonChart data={data.comparison} />}
          </>
        )}
        {activeTab === 'risk' && (
          <>
            {data.max_drawdown !== undefined ? (
              <MetricsGrid metrics={{
                'Max Drawdown': data.max_drawdown,
                'VaR (95%)': data.value_at_risk_95,
                'Portfolio Beta': data.portfolio_beta,
                'Ann. Volatility': data.volatility_annualized,
              }} />
            ) : <EmptyTab label="risk" />}
            {data.drawdown && <DrawdownChart data={data.drawdown} />}
          </>
        )}
        {activeTab === 'diversification' && (
          <>
            {data.sectors ? (
              <SectorChart data={Object.entries(data.sectors).map(([name, value]) => ({ name, value }))} />
            ) : <EmptyTab label="diversification" />}
            {data.factor_exposures && (
              <FactorRadar data={Object.entries(data.factor_exposures).map(([name, value]) => ({ name, value }))} />
            )}
          </>
        )}
        {activeTab === 'correlation' && (
          corrLoading ? (
            <div className="canvas-loading">
              <span className="dot-pulse" />
              <span>Computing correlation matrix&hellip;</span>
            </div>
          ) : correlationData ? (
            <CorrelationHeatmap data={correlationData} />
          ) : (
            <EmptyTab label="correlation" hint="Computing correlations requires a portfolio to be loaded." />
          )
        )}
        {activeTab === 'whatif' && (
          data.original_sharpe !== undefined ? (
            <>
              <MetricsGrid metrics={{
                'Original Sharpe': data.original_sharpe,
                'Simulated Sharpe': data.simulated_sharpe,
                'Original MDD': data.original_max_drawdown,
                'Simulated MDD': data.simulated_max_drawdown,
              }} />
              {data.message && <p className="whatif-message">{data.message}</p>}
            </>
          ) : <EmptyTab label="what-if simulation" hint='Try: "What if I replace 20% of RELIANCE with gold?"' />
        )}
      </div>
    </div>
  );
}

function EmptyTab({ label, hint }) {
  return (
    <div className="canvas-tab-empty">
      <p>No {label} data yet.</p>
      {hint && <p className="canvas-tab-hint">{hint}</p>}
    </div>
  );
}
