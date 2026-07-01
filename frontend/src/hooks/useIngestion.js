import { useState, useRef, useCallback, useEffect } from 'react';

const MAX_IMAGES = 5;

/** Owns the text/upload mode toggle, drag-and-drop, paste, and submit handling for IngestionForm. */
export function useIngestion(onIngestStart) {
  const [mode, setMode] = useState('text');
  const [text, setText] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const [images, setImages] = useState([]); // [{ file, previewUrl }]
  const fileRef = useRef(null);

  // Revoke object URLs on unmount to avoid leaking blob references
  useEffect(() => {
    return () => {
      images.forEach((img) => URL.revokeObjectURL(img.previewUrl));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFile = useCallback((file) => {
    onIngestStart('file', file);
  }, [onIngestStart]);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const addImages = useCallback((fileList) => {
    const incoming = Array.from(fileList).filter((f) => f.type.startsWith('image/'));
    if (!incoming.length) return;
    setImages((prev) => {
      const room = MAX_IMAGES - prev.length;
      if (room <= 0) return prev;
      const accepted = incoming.slice(0, room).map((file) => ({
        file,
        previewUrl: URL.createObjectURL(file),
      }));
      return [...prev, ...accepted];
    });
  }, []);

  const removeImage = useCallback((index) => {
    setImages((prev) => {
      const target = prev[index];
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  const handleTextAreaPaste = useCallback((e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const pastedImages = Array.from(items)
      .filter((item) => item.type.startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter(Boolean);
    if (pastedImages.length) {
      e.preventDefault();
      addImages(pastedImages);
    }
  }, [addImages]);

  const handleTextAreaDrop = useCallback((e) => {
    const files = e.dataTransfer?.files;
    if (files && Array.from(files).some((f) => f.type.startsWith('image/'))) {
      e.preventDefault();
      addImages(files);
    }
  }, [addImages]);

  const handleSubmit = useCallback(() => {
    if (images.length > 0) {
      onIngestStart('images', images.map((img) => img.file));
      return;
    }
    if (!text.trim()) return;
    onIngestStart('text', text);
  }, [text, images, onIngestStart]);

  return {
    mode,
    setMode,
    text,
    setText,
    dragOver,
    setDragOver,
    fileRef,
    images,
    addImages,
    removeImage,
    handleFile,
    handleDrop,
    handleTextAreaPaste,
    handleTextAreaDrop,
    handleSubmit,
  };
}
