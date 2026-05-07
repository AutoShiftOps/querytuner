import { useState, useCallback } from 'react';

// ── Types / colors ─────────────────────────────────────────────────────────

const TOAST_STYLES = {
  success: { bar: '#34d399', badge: '#0d3328', text: '#34d399' },
  error: { bar: '#f87171', badge: '#3d1515', text: '#f87171' },
  warning: { bar: '#fbbf24', badge: '#3a2c0a', text: '#fbbf24' },
  info: { bar: '#38bdf8', badge: '#0c1f2e', text: '#38bdf8' },
};

// ── Hook ───────────────────────────────────────────────────────────────────

export function useToast() {
  const [toasts, setToasts] = useState([]);

  const showToast = useCallback((message, type = 'success', duration = 3000) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, showToast, dismissToast };
}

// ── Container ──────────────────────────────────────────────────────────────

export function ToastContainer({ toasts, onDismiss }) {
  if (!toasts || toasts.length === 0) return null;

  return (
    <>
      <style>{`
        .qt-toast-container {
          position: fixed; top: 56px; right: 16px;
          z-index: 1000;
          display: flex; flex-direction: column; gap: 6px;
          pointer-events: none;
          font-family: 'IBM Plex Sans', system-ui, sans-serif;
        }
        .qt-toast {
          display: flex; align-items: center; gap: 10px;
          padding: 10px 14px 10px 0;
          border-radius: 8px;
          background: #1e293b;
          border: 1px solid #2d3f55;
          font-size: 12px;
          min-width: 260px; max-width: 360px;
          pointer-events: all;
          cursor: pointer;
          animation: qt-toast-in 0.2s ease;
        }
        @keyframes qt-toast-in {
          from { opacity: 0; transform: translateX(12px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        .qt-toast-bar {
          width: 3px; height: 100%; min-height: 36px;
          border-radius: 8px 0 0 8px; flex-shrink: 0;
          margin-left: -1px;
        }
        .qt-toast-icon {
          width: 18px; height: 18px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          flex-shrink: 0; font-size: 10px; font-weight: 700;
        }
        .qt-toast-msg { flex: 1; color: #e2e8f0; line-height: 1.4; }
        .qt-toast-close {
          font-size: 14px; color: #4a6480;
          cursor: pointer; padding: 0 4px; flex-shrink: 0;
        }
        .qt-toast-close:hover { color: #7fa3c4; }
      `}</style>

      <div className="qt-toast-container">
        {toasts.map((toast) => {
          const style = TOAST_STYLES[toast.type] ?? TOAST_STYLES.info;
          const icons = { success: '✓', error: '✕', warning: '!', info: 'i' };
          return (
            <div
              key={toast.id}
              className="qt-toast"
              onClick={() => onDismiss?.(toast.id)}
              role="alert"
              aria-live="polite"
            >
              <div className="qt-toast-bar" style={{ background: style.bar }} />
              <div className="qt-toast-icon" style={{ background: style.badge, color: style.text }}>
                {icons[toast.type]}
              </div>
              <span className="qt-toast-msg">{toast.message}</span>
              <span className="qt-toast-close" aria-label="Dismiss">
                ×
              </span>
            </div>
          );
        })}
      </div>
    </>
  );
}
