export const MODAL_CONTENT = {
  text: {
    title: '✍️ Free-text Paste Format',
    content: (
      <>
        <div>
          <p className="fguide-desc">Write naturally — our AI reads any format. Just include the ticker, how many shares, and what you paid.</p>
          <div className="format-code-block" style={{ marginTop: '10px' }}>
            <div><span className="fcode-ticker">RELIANCE.NS</span>: 10 shares @ ₹2450.50</div>
            <div><span className="fcode-ticker">TCS.NS</span>: 5 units @ 3210.00</div>
            <div><span className="fcode-ticker">GOLDBEES.NS</span>: 200 qty @ 45.20</div>
            <div><span className="fcode-ticker">AAPL</span>: 25 shares @ $175.20</div>
          </div>
          <p className="fguide-desc" style={{ marginTop: '10px' }}>Or plain English: <em style={{ color: 'var(--color-text)' }}>"I have 25 Apple shares bought at $175 and 10 Microsoft at $350"</em></p>
        </div>
      </>
    ),
  },
  csv: {
    title: '📊 CSV / Excel Format',
    content: (
      <>
        <div>
          <p className="fguide-desc">Any column names work — our AI maps non-standard headers automatically. You don't need to rename anything.</p>
          <div className="format-code-block" style={{ marginTop: '10px', padding: 'var(--space-sm) var(--space-md)' }}>
            <table className="format-table">
              <thead>
                <tr>
                  <th>Symbol <span className="fguide-alias">/ Ticker / Stock</span></th>
                  <th>Qty <span className="fguide-alias">/ Shares / Units</span></th>
                  <th>Buy Price <span className="fguide-alias">/ Avg Cost / Cost Price</span></th>
                </tr>
              </thead>
              <tbody>
                <tr><td>RELIANCE.NS</td><td>10</td><td>2450.50</td></tr>
                <tr><td>TCS.NS</td><td>5</td><td>3210.00</td></tr>
                <tr><td>GOLDBEES.NS</td><td>200</td><td>45.20</td></tr>
                <tr><td>AAPL</td><td>25</td><td>175.20</td></tr>
              </tbody>
            </table>
          </div>
          <p className="fguide-desc" style={{ marginTop: '10px' }}>Also accepted: <strong>Invested Amount</strong> column instead of per-share price — we back-calculate automatically.</p>
        </div>
      </>
    ),
  },
  screenshot: {
    title: '📸 Screenshot Format',
    content: (
      <>
        <div>
          <p className="fguide-desc">Paste (Ctrl/Cmd+V) or drag a screenshot of your broker app's holdings screen straight into the text box — no typing needed.</p>
          <div className="format-modal-tips" style={{ marginTop: '10px' }}>
            <div className="fguide-tip">
              <span className="fguide-tip-dot fguide-tip-dot--green" />
              <span>Crop to the holdings table so ticker, quantity, and price are clearly visible.</span>
            </div>
            <div className="fguide-tip">
              <span className="fguide-tip-dot fguide-tip-dot--blue" />
              <span>Up to 5 screenshots per submission — useful for multiple accounts or a scrolling list.</span>
            </div>
            <div className="fguide-tip">
              <span className="fguide-tip-dot fguide-tip-dot--amber" />
              <span>We only extract numbers that are actually legible — nothing is guessed or estimated.</span>
            </div>
          </div>
        </div>
      </>
    ),
  },
  tips: {
    title: '💡 Tips & What to Expect',
    content: (
      <>
        <div className="format-modal-tips">
          <div className="fguide-tip">
            <span className="fguide-tip-dot fguide-tip-dot--green" />
            <span><strong>Qty + Buy Price</strong> gives you full analysis — Sharpe ratio, P&L, drawdown, and all factor metrics.</span>
          </div>
          <div className="fguide-tip">
            <span className="fguide-tip-dot fguide-tip-dot--amber" />
            <span><strong>Weight-only</strong> (e.g. "50% AAPL, 50% MSFT") also works — risk and return metrics are still computed.</span>
          </div>
          <div className="fguide-tip">
            <span className="fguide-tip-dot fguide-tip-dot--blue" />
            <span><strong>NSE tickers</strong> — append <code>.NS</code> (e.g. RELIANCE.NS). US stocks use their plain symbol (AAPL, MSFT).</span>
          </div>
          <div className="fguide-tip">
            <span className="fguide-tip-dot" style={{ background: '#ef4444' }} />
            <span><strong>Mixed currencies</strong> not yet supported — keep all holdings in one currency (INR or USD).</span>
          </div>
          <div className="fguide-tip">
            <span className="fguide-tip-dot fguide-tip-dot--green" />
            <span><strong>Analysis takes ~15–20 seconds</strong> — we fetch 3 years of real market data and run your full quant pipeline.</span>
          </div>
        </div>
      </>
    ),
  },
};
