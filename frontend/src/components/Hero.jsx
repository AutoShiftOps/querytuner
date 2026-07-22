export default function Hero() {
  return (
    <>
      <style>{`
        .qt-hero {
          padding: 28px 20px 22px;
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
        .qt-hero-stat-line1 {
          font-size: 13px; font-weight: 600;
          color: #e2e8f0; text-align: center;
        }
        .qt-hero-stat-line2 {
          font-size: 13px; color: #7fa3c4;
          text-align: center; margin-bottom: 16px;
        }
        .qt-hero-source {
          font-size: 10px; color: #4a6480;
          text-align: center; margin-top: 8px;
        }
        .qt-hero-title {
          font-size: 26px; font-weight: 600;
          color: #e2e8f0; letter-spacing: -0.025em;
          line-height: 1.25; margin-bottom: 10px;
        }
        .qt-hero-title-accent { color: #38bdf8; }
        .qt-hero-sub {
          font-size: 13px; color: #7fa3c4;
          max-width: 520px; margin: 0 auto 16px;
          line-height: 1.65;
        }
        .qt-hero-pills {
          display: flex; align-items: center;
          justify-content: center; gap: 6px; flex-wrap: wrap;
        }
        .qt-hero-pill {
          font-size: 11px; font-weight: 500;
          padding: 4px 12px; border-radius: 20px;
          background: rgba(56,189,248,0.07);
          color: #38bdf8;
          border: 1px solid rgba(56,189,248,0.15);
        }
        @media (max-width: 600px) {
          .qt-hero-title { font-size: 20px; }
          .qt-hero { padding: 20px 16px 18px; }
        }
      `}</style>

      <div className="qt-hero">
        <p className="qt-hero-stat-line1">Only 0.3% of developers are DBAs.</p>
        <p className="qt-hero-stat-line2">
          The SQL performance tools that exist were built for them.
        </p>

        <h1 className="qt-hero-title">
          Paste any query.
          <br />
          Get a <span className="qt-hero-title-accent">consultant-grade</span> diagnosis.
        </h1>

        <p className="qt-hero-sub">
          Heuristic engine + LLM rewrite across PostgreSQL, MySQL, Oracle, SQL Server, and SQLite.
          No database connection required.
        </p>

        <div className="qt-hero-pills">
          <span className="qt-hero-pill">A prioritised fix list</span>
          <span className="qt-hero-pill">A copy-pasteable rewritten query</span>
          <span className="qt-hero-pill">A security risk report</span>
          <span className="qt-hero-pill">A permanent shareable URL</span>
          <span className="qt-hero-pill">A /analyze API endpoint</span>
        </div>

        <p className="qt-hero-source">†Stack Overflow Developer Survey 2024, 65,000+ developers</p>
      </div>
    </>
  );
}
