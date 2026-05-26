import { useState } from 'react';

export default function ShareButton({ analysisId, onShare }) {
  const [state, setState] = useState('idle'); // "idle" | "copied" | "error"

  if (!analysisId) return null;

  const shareUrl = `${window.location.origin}/report/${analysisId}`;

  const handleShare = async () => {
    // Clipboard write in its own try-catch — visual state tied only to this
    try {
      await navigator.clipboard.writeText(shareUrl);
      setState('copied');
      setTimeout(() => setState('idle'), 2500);
    } catch {
      setState('error');
      setTimeout(() => setState('idle'), 2500);
      return; // Don't call onShare if copy failed
    }

    // onShare is outside the clipboard try-catch.
    // If the callback throws (e.g. analytics blocked), the button
    // visual state is already "copied" and won't revert to "error".
    try {
      if (onShare) onShare();
    } catch {
      // Silently ignore callback errors — clipboard copy already succeeded
    }
  };

  return (
    <button
      onClick={handleShare}
      title={state === 'idle' ? shareUrl : undefined}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 14px',
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 500,
        cursor: 'pointer',
        fontFamily: 'inherit',
        transition: 'all 0.15s',
        background:
          state === 'copied'
            ? 'rgba(52,211,153,0.08)'
            : state === 'error'
              ? 'rgba(248,113,113,0.08)'
              : 'transparent',
        border:
          state === 'copied'
            ? '1px solid #34d399'
            : state === 'error'
              ? '1px solid #f87171'
              : '1px solid #2d3f55',
        color: state === 'copied' ? '#34d399' : state === 'error' ? '#f87171' : '#7fa3c4',
      }}
      onMouseEnter={(e) => {
        if (state === 'idle') {
          e.currentTarget.style.borderColor = '#3b5268';
          e.currentTarget.style.color = '#e2e8f0';
        }
      }}
      onMouseLeave={(e) => {
        if (state === 'idle') {
          e.currentTarget.style.borderColor = '#2d3f55';
          e.currentTarget.style.color = '#7fa3c4';
        }
      }}
    >
      {state === 'copied' ? (
        <>
          <CheckIcon />
          Link copied!
        </>
      ) : state === 'error' ? (
        <>
          <LinkIcon />
          Copy failed — try again
        </>
      ) : (
        <>
          <LinkIcon />
          Share analysis
        </>
      )}
    </button>
  );
}

function LinkIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}
