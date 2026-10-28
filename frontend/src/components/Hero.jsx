// Compact pitch for signed-out visitors only (App.jsx skips it for signed-in
// users): the tool itself is the hero, so the editor and results start above
// the fold. The "what you get" list lives in the empty results panel
// (EmptyResults.jsx) instead of a row of chips here.
export default function Hero() {
  return (
    <>
      <style>{`
        .qt-hero {
          padding: 18px 20px 14px;
          text-align: center;
          border-bottom: 1px solid #1a2e45;
          font-family: 'IBM Plex Sans', system-ui, sans-serif;
          background: #0f172a;
          background-image: radial-gradient(
            ellipse 70% 60% at 50% -10%,
            rgba(56,189,248,0.06) 0%,
            transparent 60%
          );
        }
        .qt-hero-title {
          font-size: 22px; font-weight: 600;
          color: #e2e8f0; letter-spacing: -0.02em;
          line-height: 1.3; margin-bottom: 6px;
        }
        .qt-hero-title-accent { color: #38bdf8; }
        .qt-hero-sub {
          font-size: 13px; color: #7fa3c4;
          max-width: 640px; margin: 0 auto;
          line-height: 1.6;
        }
        @media (max-width: 600px) {
          .qt-hero-title { font-size: 18px; }
          .qt-hero { padding: 14px 16px 12px; }
        }
      `}</style>

      <div className="qt-hero">
        <h1 className="qt-hero-title">
          Paste any query. Get a <span className="qt-hero-title-accent">consultant-grade</span>{' '}
          diagnosis.
        </h1>
        <p className="qt-hero-sub">
          SQL tuning for developers, not just DBAs: heuristic engine + AI across PostgreSQL, MySQL,
          Oracle, SQL Server and SQLite. No database connection required.
        </p>
      </div>
    </>
  );
}
