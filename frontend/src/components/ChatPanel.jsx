import { useState, useRef, useEffect } from 'react';

function formatMessageText(text) {
  if (!text) return '';
  
  const lines = text.split('\n');
  return (
    <div className="formatted-message">
      {lines.map((line, lineIdx) => {
        const trimmed = line.trim();
        const isBullet = trimmed.startsWith('* ') || trimmed.startsWith('- ');
        let content = line;
        
        if (isBullet) {
          content = trimmed.substring(2);
        }
        
        const parts = [];
        const regex = /\*\*(.*?)\*\*/g;
        let match;
        let lastIndex = 0;
        
        while ((match = regex.exec(content)) !== null) {
          if (match.index > lastIndex) {
            parts.push(content.substring(lastIndex, match.index));
          }
          parts.push(<strong key={match.index}>{match[1]}</strong>);
          lastIndex = regex.lastIndex;
        }
        
        if (lastIndex < content.length) {
          parts.push(content.substring(lastIndex));
        }
        
        if (isBullet) {
          return (
            <div key={lineIdx} className="bullet-item" style={{ display: 'flex', alignItems: 'flex-start', margin: '4px 0 4px 12px' }}>
              <span style={{ marginRight: '8px', color: 'var(--color-accent)' }}>•</span>
              <div>{parts}</div>
            </div>
          );
        }
        
        return (
          <p key={lineIdx} style={{ margin: '6px 0' }}>
            {parts}
          </p>
        );
      })}
    </div>
  );
}

export default function ChatPanel({ messages, onSend, loading, suggestedPrompts, onPromptClick, injectionWarning, onDismissWarning }) {
  const [input, setInput] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, suggestedPrompts]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    onSend(input.trim());
    setInput('');
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="chat-status-dot" aria-label="Online" />
          <h3>AI Analyst</h3>
        </div>
        <span className="tag">Live</span>
      </div>

      {injectionWarning && (
        <div className="injection-warning" role="alert">
          <div className="injection-warning-inner">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>{injectionWarning}</span>
          </div>
          <button className="injection-dismiss" onClick={onDismissWarning} aria-label="Dismiss warning">&times;</button>
        </div>
      )}

      <div className="chat-messages" role="log" aria-live="polite">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon" aria-hidden="true">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
            <p>Ask about performance, risk, or diversification</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg ${msg.role}`}>
            {msg.role === 'assistant' && (
              <div className="chat-avatar" aria-hidden="true">K</div>
            )}
            <div className="chat-bubble">
              {msg.statusText && !msg.text ? (
                <div className="chat-status-loading">
                  <span className="status-spinner-dot" />
                  <span className="status-text">{msg.statusText}</span>
                </div>
              ) : (
                formatMessageText(msg.text)
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {suggestedPrompts.length > 0 && (
        <div className="chat-prompts" role="group" aria-label="Suggested questions">
          {suggestedPrompts.slice(0, 3).map((prompt, i) => (
            <button
              key={i}
              className="prompt-chip"
              onClick={() => onPromptClick(prompt)}
              disabled={loading}
            >
              {prompt}
            </button>
          ))}
        </div>
      )}

      <form className="chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Ask about your portfolio\u2026"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
          aria-label="Chat message"
          maxLength={1000}
        />
        <button
          type="submit"
          className="btn-primary chat-send"
          disabled={loading || !input.trim()}
          aria-label="Send message"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </form>
    </div>
  );
}
