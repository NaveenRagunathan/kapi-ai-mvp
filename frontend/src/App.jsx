import { useState, useCallback, useRef, lazy, Suspense } from 'react';
import './App.css';
import IngestionForm from './components/IngestionForm';
import { sendChatMessageStream, ingestPortfolioFile, ingestPortfolioText, ingestPortfolioImages } from './api/service';

// The analysis-view components are only needed after a portfolio is
// ingested, so keep them out of the initial bundle.
const ChatPanel = lazy(() => import('./components/ChatPanel'));
const VisualCanvas = lazy(() => import('./components/VisualCanvas'));

export default function App() {
  const [view, setView] = useState('ingest');
  const [sessionId, setSessionId] = useState(null);
  const [holdings, setHoldings] = useState([]);
  const [baseline, setBaseline] = useState(null);
  const [messages, setMessages] = useState([]);
  const [canvasState, setCanvasState] = useState(null);
  const [suggestedPrompts, setSuggestedPrompts] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [loadingBaseline, setLoadingBaseline] = useState(false);
  const [externalError, setExternalError] = useState(null);
  const [injectionWarning, setInjectionWarning] = useState(null);

  const chatLoadingRef = useRef(false);

  const handleIngestStart = useCallback(async (type, payload) => {
    setLoadingBaseline(true);
    setExternalError(null);
    setView('analysis');
    setCanvasState({ view: 'none', data: {} });
    setMessages([{
      role: 'assistant',
      text: 'Initializing portfolio analysis. Running core math engine to calculate baseline risk/return profile...',
    }]);

    try {
      let data;
      if (type === 'text') {
        data = await ingestPortfolioText(payload);
      } else if (type === 'images') {
        data = await ingestPortfolioImages(payload);
      } else {
        data = await ingestPortfolioFile(payload);
      }

      setSessionId(data.session_id);
      setHoldings(data.holdings || []);
      setBaseline(data.baseline);

      // Build a personalized welcome message from real baseline metrics
      const b = data.baseline;
      const n = data.holdings?.length || 0;
      const sharpe = b?.performance?.portfolio_sharpe;
      const mdd = b?.risk?.max_drawdown;
      const cagr = b?.performance?.portfolio_cagr;
      const grade = b?.health?.grade;
      const sectors = b?.diversification?.sectors || {};
      const topSector = Object.entries(sectors).sort((a, b) => b[1] - a[1])[0];
      const topSectorStr = topSector ? `${topSector[0]} (${(topSector[1] * 100).toFixed(0)}%)` : null;

      const sharpeStr = typeof sharpe === 'number' ? sharpe.toFixed(2) : null;
      const mddStr = typeof mdd === 'number' ? `${(mdd * 100).toFixed(1)}%` : null;
      const cagrStr = typeof cagr === 'number' ? `${(cagr * 100).toFixed(1)}%` : null;

      let welcomeText = `I've finished analyzing your ${n}-holding portfolio`;
      if (grade) welcomeText += ` — overall health grade **${grade}**`;
      welcomeText += '.';

      const highlights = [];
      if (cagrStr) highlights.push(`1-year CAGR of **${cagrStr}**`);
      if (sharpeStr) highlights.push(`Sharpe ratio of **${sharpeStr}**`);
      if (mddStr) highlights.push(`max drawdown of **${mddStr}**`);
      if (highlights.length) welcomeText += ` Key metrics: ${highlights.join(', ')}.`;

      if (topSector && topSector[1] > 0.35) {
        welcomeText += ` I noticed **${topSectorStr}** is your dominant sector — worth exploring concentration risk.`;
      }

      welcomeText += ' What would you like to dig into?';

      // Smart suggested prompts based on vulnerabilities
      const smartPrompts = [];
      if (typeof sharpe === 'number' && sharpe < 0.5) {
        smartPrompts.push('Why is my risk-adjusted return low?');
      } else {
        smartPrompts.push('What is my portfolio Sharpe ratio?');
      }
      if (topSector && topSector[1] > 0.35) {
        smartPrompts.push(`How does a ${topSector[0]} sector correction impact me?`);
      } else {
        smartPrompts.push('Analyze my sector diversification');
      }
      if (typeof mdd === 'number' && mdd < -0.2) {
        smartPrompts.push('Show me my max drawdown and tail risk');
      } else {
        smartPrompts.push('Run a what-if: sell my top holding and buy Gold ETF');
      }

      setMessages([{ role: 'assistant', text: welcomeText }]);
      setSuggestedPrompts(smartPrompts);
    } catch (e) {
      setView('ingest');
      setExternalError(e.message || 'Ingestion failed. Please check formatting guidelines.');
    } finally {
      setLoadingBaseline(false);
    }
  }, []);

  const handleSend = useCallback(async (message) => {
    if (chatLoadingRef.current) return;
    chatLoadingRef.current = true;
    setInjectionWarning(null);
    setMessages((prev) => [...prev, { role: 'user', text: message }]);
    setChatLoading(true);

    // Append an empty assistant message which we will fill progressively
    setMessages((prev) => [...prev, { role: 'assistant', text: '', statusText: 'Analyzing query...' }]);

    // Accumulate tokens in a ref, flush via rAF to avoid per-word re-renders
    let assistantText = '';
    const tokenBufferRef = { pending: '', rafId: null };

    const flushTokenBuffer = () => {
      tokenBufferRef.rafId = null;
      if (!tokenBufferRef.pending) return;
      assistantText += tokenBufferRef.pending;
      tokenBufferRef.pending = '';
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') {
          last.text = assistantText;
          last.statusText = null;
        }
        return next;
      });
    };

    try {
      await sendChatMessageStream(sessionId, message, (eventData) => {
        const { event, data } = eventData;
        if (event === 'status') {
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last && last.role === 'assistant') {
              last.statusText = data.message;
            }
            return next;
          });
        } else if (event === 'token') {
          // Buffer the token and schedule a single rAF flush
          tokenBufferRef.pending += data.text;
          if (!tokenBufferRef.rafId) {
            tokenBufferRef.rafId = requestAnimationFrame(flushTokenBuffer);
          }
        } else if (event === 'canvas') {
          // Flush any buffered tokens before updating canvas
          if (tokenBufferRef.rafId) {
            cancelAnimationFrame(tokenBufferRef.rafId);
            flushTokenBuffer();
          }
          setCanvasState({ view: data.view, data: data.data });
          setSuggestedPrompts(data.suggested_prompts || []);
        } else if (event === 'error') {
          if (tokenBufferRef.rafId) {
            cancelAnimationFrame(tokenBufferRef.rafId);
            tokenBufferRef.rafId = null;
          }
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last && last.role === 'assistant') {
              last.text = `Error: ${data.detail}`;
              last.statusText = null;
            }
            return next;
          });
        }
      });
      // Flush any remaining buffered tokens after stream ends
      if (tokenBufferRef.rafId) {
        cancelAnimationFrame(tokenBufferRef.rafId);
        flushTokenBuffer();
      }
    } catch (e) {
      if (tokenBufferRef.rafId) {
        cancelAnimationFrame(tokenBufferRef.rafId);
        tokenBufferRef.rafId = null;
      }
      if (e.message.toLowerCase().includes('blocked')) {
        setInjectionWarning(e.message);
        setMessages((prev) => prev.slice(0, -2));
      } else {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last && last.role === 'assistant') {
            last.text = `Connection Error: ${e.message}`;
            last.statusText = null;
          }
          return next;
        });
      }
    } finally {
      setChatLoading(false);
      chatLoadingRef.current = false;
    }
  }, [sessionId]);

  const handleReset = useCallback(() => {
    setView('ingest');
    setSessionId(null);
    setHoldings([]);
    setBaseline(null);
    setMessages([]);
    setCanvasState(null);
    setSuggestedPrompts([]);
    setInjectionWarning(null);
    chatLoadingRef.current = false;
    setChatLoading(false);
    setLoadingBaseline(false);
    setExternalError(null);
  }, []);

  const handleResetCanvas = useCallback(() => {
    setCanvasState({ view: 'none', data: {} });
  }, []);

  if (view === 'ingest') {
    return (
      <div className="app-ingest">
        <nav className="nav">
          <div className="nav-inner">
            <div className="nav-brand">
              <span className="nav-logo">K</span>
              <span className="nav-title">Kalpi AI</span>
            </div>
            <span className="nav-badge">Portfolio Analyzer</span>
          </div>
        </nav>
        <main className="ingest-main">
          <IngestionForm onIngestStart={handleIngestStart} externalError={externalError} />
        </main>
      </div>
    );
  }

  return (
    <div className="app-analysis">
      <nav className="nav">
        <div className="nav-inner">
          <div className="nav-brand" onClick={handleReset} style={{ cursor: 'pointer' }}>
            <span className="nav-logo">K</span>
            <span className="nav-title">Kalpi AI</span>
          </div>
          <div className="nav-center">
            <span className="holdings-badge">{holdings.length} holdings</span>
          </div>
          <button className="btn-secondary nav-new" onClick={handleReset}>
            New Portfolio
          </button>
        </div>
      </nav>

      <Suspense fallback={<div className="analysis-layout" />}>
        <div className="analysis-layout">
          <div className="analysis-chat">
            <ChatPanel
              messages={messages}
              onSend={handleSend}
              loading={chatLoading || loadingBaseline}
              suggestedPrompts={suggestedPrompts}
              onPromptClick={handleSend}
              injectionWarning={injectionWarning}
              onDismissWarning={() => setInjectionWarning(null)}
            />
          </div>
          <div className="analysis-canvas">
            <VisualCanvas
              canvasState={canvasState}
              sessionId={sessionId}
              baseline={baseline}
              loadingBaseline={loadingBaseline}
              onResetCanvas={handleResetCanvas}
              onSetCanvasState={setCanvasState}
            />
          </div>
        </div>
      </Suspense>
    </div>
  );
}
