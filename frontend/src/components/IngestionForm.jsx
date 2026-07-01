import { useIngestion } from '../hooks/useIngestion';
import FormatGuide from './FormatGuide';

export default function IngestionForm({ onIngestStart, externalError }) {
  const {
    mode, setMode,
    text, setText,
    dragOver, setDragOver,
    fileRef,
    images, addImages, removeImage,
    handleFile, handleDrop,
    handleTextAreaPaste, handleTextAreaDrop,
    handleSubmit,
  } = useIngestion(onIngestStart);

  const error = externalError;

  return (
    <div className="ingestion-page">

      {/* Hero */}
      <div className="ingestion-hero">
        <div className="hero-glow" aria-hidden="true" />
        <div className="hero-eyebrow">
          <span className="eyebrow-dot" />
          Institutional-Grade AI Analysis
        </div>
        <h1 className="hero-heading">
          Portfolio Intelligence<br />
          <span className="hero-accent">Built for Every Investor {' '}</span>
        </h1>
        <p className="hero-sub">
          Drop in your holdings and get a full institutional-grade breakdown Sharpe ratio, max drawdown, sector exposure, factor overlaps, and AI-driven simulations.
        </p>
        <div className="hero-pills">
          <span className="hero-pill">Sharpe &amp; Sortino</span>
          <span className="hero-pill">Max Drawdown · VaR</span>
          <span className="hero-pill">Factor Exposure</span>
          <span className="hero-pill">Sector Heatmap</span>
          <span className="hero-pill">What-If Scenarios</span>
        </div>
      </div>

      {/* Upload Card */}
      <div className="upload-card glass">
        <div className="ingestion-tabs">
          <button
            className={`ingestion-tab ${mode === 'text' ? 'active' : ''}`}
            onClick={() => setMode('text')}
          >
            Paste Holdings
          </button>
          <button
            className={`ingestion-tab ${mode === 'upload' ? 'active' : ''}`}
            onClick={() => setMode('upload')}
          >
            Upload CSV / Excel
          </button>
        </div>

        {mode === 'text' ? (
          <div className="text-area-container">
            {images.length > 0 && (
              <div className="image-thumbnail-strip">
                {images.map((img, i) => (
                  <div className="image-thumbnail" key={img.previewUrl}>
                    <img src={img.previewUrl} alt={`Screenshot ${i + 1}`} />
                    <button
                      type="button"
                      className="image-thumbnail-remove"
                      onClick={() => removeImage(i)}
                      aria-label={`Remove screenshot ${i + 1}`}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
            <textarea
              className="text-area"
              placeholder={
                images.length > 0
                  ? 'Screenshots added — click Analyze, or paste/drop more (up to 5).'
                  : `Describe your portfolio naturally, or paste/drop a screenshot — AI reads any format:\n\nRELIANCE.NS: 10 shares @ 2450.50\nTCS.NS: 5 shares @ 3210.00\nGOLDBEES.NS: 200 qty @ 45.20\nAAPL: 25 shares @ 175.20`
              }
              value={text}
              onChange={(e) => setText(e.target.value)}
              onPaste={handleTextAreaPaste}
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleTextAreaDrop}
              rows={5}
            />
            <button
              className="btn-primary submit-btn"
              onClick={handleSubmit}
              disabled={!text.trim() && images.length === 0}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
              {images.length > 0 ? `Analyze ${images.length} Screenshot${images.length > 1 ? 's' : ''}` : 'Analyze Portfolio'}
            </button>
          </div>
        ) : (
          <div
            className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && fileRef.current?.click()}
            aria-label="Drop your CSV or Excel file here"
          >
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" hidden
              onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])} />
            <div className="drop-zone-icon" aria-hidden="true">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <p className="drop-zone-text">{dragOver ? 'Release to upload' : 'Drop CSV or Excel here'}</p>
            <p className="drop-zone-hint">Any column names work — AI maps them &middot; click to browse</p>
          </div>
        )}

        {error && (
          <div className="ingestion-error" role="alert">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {error}
          </div>
        )}
      </div>

      <FormatGuide />

    </div>
  );
}
