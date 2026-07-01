import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { onCLS, onINP, onLCP } from 'web-vitals';
import './index.css';
import App from './App';

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// Baseline Core Web Vitals logging (dev-time visibility, no
// external reporting endpoint wired up yet).
onCLS(console.log);
onINP(console.log);
onLCP(console.log);
