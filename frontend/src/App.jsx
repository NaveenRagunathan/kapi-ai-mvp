import { useState, useCallback } from 'react';
import './App.css';
import IngestionForm from './components/IngestionForm';
import ChatPanel from './components/ChatPanel';
import VisualCanvas from './components/VisualCanvas';
import { sendChatMessage } from './api/service';

export default function App() {
  const [view, setView] = useState('ingest');
  const [sessionId, setSessionId] = useState(null);
  const [holdings, setHoldings] = useState([]);
  const [messages, setMessages] = useState([]);
  const [canvasState, setCanvasState] = useState(null);
  const [suggestedPrompts, setSuggestedPrompts] = useState([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [injectionWarning, setInjectionWarning] = useState(null);

  const handleIngested = useCallback((data) => {
    setSessionId(data.session_id);
    setHoldings(data.holdings);
    setView('analysis');
    setMessages([{
      role: 'assistant',
      text: `Portfolio loaded with ${data.holdings?.length || 0} holdings. Ask me about performance, risk, diversification, or run a what-if simulation.`,
    }]);
    setSuggestedPrompts([
      'What is my portfolio Sharpe ratio?',
      'Show me the risk metrics and max drawdown',
      'Analyze my sector diversification',
    ]);
  }, []);

  const handleSend = useCallback(async (message) => {
    setInjectionWarning(null);
    setMessages((prev) => [...prev, { role: 'user', text: message }]);
    setChatLoading(true);
    try {
      const data = await sendChatMessage(sessionId, message);
      setMessages((prev) => [...prev, { role: 'assistant', text: data.text }]);
      if (data.canvas_state) setCanvasState(data.canvas_state);
      setSuggestedPrompts(data.suggested_prompts || []);
    } catch (e) {
      if (e.status === 400 && e.message.toLowerCase().includes('blocked')) {
        setInjectionWarning(e.message);
        setMessages((prev) => prev.slice(0, -1)); // remove the user message
      } else {
        setMessages((prev) => [...prev, { role: 'assistant', text: `Error: ${e.message}` }]);
      }
    } finally {
      setChatLoading(false);
    }
  }, [sessionId]);

  const handleReset = useCallback(() => {
    setView('ingest');
    setSessionId(null);
    setHoldings([]);
    setMessages([]);
    setCanvasState(null);
    setSuggestedPrompts([]);
    setInjectionWarning(null);
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
          <IngestionForm onIngested={handleIngested} />
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

      <div className="analysis-layout">
        <div className="analysis-chat">
          <ChatPanel
            messages={messages}
            onSend={handleSend}
            loading={chatLoading}
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
          />
        </div>
      </div>
    </div>
  );
}
