import { useState, useEffect } from 'react';
import { MODAL_CONTENT } from './formatGuideContent';

/** Capsule triggers + glassmorphism modal explaining accepted ingestion formats. */
export default function FormatGuide() {
  const [activeModal, setActiveModal] = useState(null);

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') setActiveModal(null); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const modal = activeModal ? MODAL_CONTENT[activeModal] : null;

  return (
    <>
      <div className="format-capsules">
        <button className="format-capsule" onClick={() => setActiveModal('text')}>
          <span className="format-capsule-dot" style={{ background: '#00885e' }} />
          How to paste holdings
        </button>
        <button className="format-capsule" onClick={() => setActiveModal('csv')}>
          <span className="format-capsule-dot" style={{ background: '#3b82f6' }} />
          CSV / Excel format
        </button>
        <button className="format-capsule" onClick={() => setActiveModal('tips')}>
          <span className="format-capsule-dot" style={{ background: '#d97706' }} />
          Tips &amp; what to expect
        </button>
      </div>

      {modal && (
        <div
          className="format-modal-overlay"
          onClick={(e) => { if (e.target === e.currentTarget) setActiveModal(null); }}
        >
          <div className="format-modal" role="dialog" aria-modal="true">
            <div className="format-modal-header">
              <div className="format-modal-title">{modal.title}</div>
              <button className="format-modal-close" onClick={() => setActiveModal(null)} aria-label="Close">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div>{modal.content}</div>
          </div>
        </div>
      )}
    </>
  );
}
