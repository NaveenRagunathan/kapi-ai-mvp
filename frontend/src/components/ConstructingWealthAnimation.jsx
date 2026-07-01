import { useState, useEffect } from 'react';

export default function ConstructingWealthAnimation({ progressMax = 95 }) {
  const [progress, setProgress] = useState(0);
  const [activeStep, setActiveStep] = useState(0);

  const steps = [
    { label: 'Parsing portfolio holdings data', weight: 8 },
    { label: 'Resolving tickers against NSE / NYSE index', weight: 10 },
    { label: 'Fetching 1Y & 3Y historical pricing data', weight: 22 },
    { label: 'Evaluating CAGR, Sharpe ratio, and Sortino', weight: 15 },
    { label: 'Running Value-at-Risk & Drawdown simulations', weight: 18 },
    { label: 'Synthesizing sector & factor exposure metrics', weight: 14 },
    { label: 'Compiling institutional-grade baseline', weight: 8 },
  ];

  // Total weights (for step thresholds)
  const totalWeight = steps.reduce((s, x) => s + x.weight, 0);
  const stepThresholds = steps.map((_, i) =>
    Math.round((steps.slice(0, i + 1).reduce((s, x) => s + x.weight, 0) / totalWeight) * progressMax)
  );

  useEffect(() => {
    let raf;
    const startTime = performance.now();
    // Duration ~18s — matches typical backend baseline compute time
    const totalMs = 18000;

    const animate = (now) => {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / totalMs, 1);

      // Ease-out cubic: fast at start, decelerates smoothly near 95%
      // y = 1 - (1-t)^3  but we cap output at progressMax/100
      const eased = 1 - Math.pow(1 - t, 3);
      const pct = Math.round(eased * progressMax);

      setProgress(pct);

      // Figure out which step we're on based on pct vs thresholds
      let step = 0;
      for (let i = 0; i < stepThresholds.length; i++) {
        if (pct >= stepThresholds[i]) step = i + 1;
        else break;
      }
      setActiveStep(Math.min(step, steps.length - 1));

      if (t < 1) {
        raf = requestAnimationFrame(animate);
      }
    };

    raf = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="wealth-loader-container">
      <div className="wealth-loader-left">
        <div className="wealth-loader-header">
          <div className="loader-eyebrow">
            <span className="pulse-dot" />
            REAL-TIME QUANT PIPELINE
          </div>
          <h2>Constructing Portfolio Engine</h2>
          <p>Running historical market simulations across all your holdings. Fetching 3 years of pricing data and computing risk-adjusted metrics.</p>
        </div>

        <div className="wealth-steps">
          {steps.map((step, idx) => {
            let status = 'pending';
            if (idx < activeStep) status = 'done';
            else if (idx === activeStep) status = 'running';

            return (
              <div key={idx} className={`wealth-step-row ${status}`}>
                <div className="step-indicator">
                  {status === 'done' && (
                    <svg className="check-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  )}
                  {status === 'running' && <span className="running-dot" />}
                  {status === 'pending' && <span className="pending-dot" />}
                </div>
                <div className="step-details">
                  <span className="step-label">{step.label}</span>
                  {status === 'running' && <span className="step-status">Processing...</span>}
                  {status === 'done' && <span className="step-status done">Complete</span>}
                </div>
              </div>
            );
          })}
        </div>

        <div className="wealth-progress-container">
          <div className="progress-labels">
            <span>Overall Construction</span>
            <span>{progress}%</span>
          </div>
          <div className="progress-bar-track">
            <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </div>

      <div className="wealth-loader-right">
        <div className="wealth-core-visualization">
          <div className="core-ring core-ring-outer" />
          <div className="core-ring core-ring-middle" />
          <div className="core-ring core-ring-inner" />
          <div className="core-glow-center">
            <div className="glow-percentage">{progress}%</div>
            <div className="glow-label">SECURE</div>
          </div>
          <div className="core-radar-lines" />
        </div>
      </div>
    </div>
  );
}
