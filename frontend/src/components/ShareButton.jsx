import { useState } from 'react';

export default function ShareButton({ analysisId }) {
  const [state, setState] = useState('idle'); // "idle" | "copied" | "unavailable"

  if (!analysisId) return null; // Don't render if Supabase isn't configured yet

  const shareUrl = `${window.location.origin}/report/${analysisId}`;

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setState('copied');
      setTimeout(() => setState('idle'), 2500);
    } catch {
      setState('unavailable');
      setTimeout(() => setState('idle'), 2500);
    }
  };

  return (
    <button
      onClick={handleShare}
      title="Copy shareable link to this analysis"
      className={`
        inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg
        border transition-all duration-200 font-medium
        ${
          state === 'copied'
            ? 'bg-green-50 border-green-300 text-green-700'
            : 'bg-white border-gray-200 text-gray-600 hover:border-indigo-300 hover:text-indigo-600 hover:bg-indigo-50'
        }
      `}
    >
      {state === 'copied' ? (
        <>
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
          Link copied!
        </>
      ) : (
        <>
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
            />
          </svg>
          Share analysis
        </>
      )}
    </button>
  );
}

// =============================================================================
// App.js CHANGES — Issue #41
// =============================================================================
//
// 1. Install react-router-dom if not already installed:
//    npm install react-router-dom
//
// 2. Update your App.js to add the /report/:id route:
//
// import { BrowserRouter, Routes, Route } from 'react-router-dom';
// import ReportPage from './components/ReportPage';
// import App from './App';   // your existing main component
//
// function Root() {
//   return (
//     <BrowserRouter>
//       <Routes>
//         <Route path="/" element={<App />} />
//         <Route path="/report/:id" element={<ReportPage />} />
//       </Routes>
//     </BrowserRouter>
//   );
// }
//
// export default Root;
//
// 3. In your main.jsx / index.js, render <Root /> instead of <App />
//
// =============================================================================
// VITE CONFIG — ensure /report/:id works on Vercel refresh
// =============================================================================
//
// In vercel.json (create at repo root if it doesn't exist):
//
// {
//   "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
// }
//
// This prevents 404 on direct URL visits to /report/some-uuid
// =============================================================================
