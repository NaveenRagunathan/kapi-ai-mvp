import { useState, useRef, useCallback } from 'react';

/** Owns the text/upload mode toggle, drag-and-drop, and submit handling for IngestionForm. */
export function useIngestion(onIngestStart) {
  const [mode, setMode] = useState('text');
  const [text, setText] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);

  const handleFile = useCallback((file) => {
    onIngestStart('file', file);
  }, [onIngestStart]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleTextSubmit = useCallback(() => {
    if (!text.trim()) return;
    onIngestStart('text', text);
  }, [text, onIngestStart]);

  return {
    mode,
    setMode,
    text,
    setText,
    dragOver,
    setDragOver,
    fileRef,
    handleFile,
    handleDrop,
    handleTextSubmit,
  };
}
