export default function Header() {
  return (
    <>
      <style>{`
        .qt-header {
          position: sticky; top: 0; z-index: 50;
          background: #0f172a;
          border-bottom: 1px solid #1e3a5f;
          height: 48px;
          display: flex; align-items: center;
          justify-content: space-between;
          padding: 0 20px;
          font-family: 'IBM Plex Sans', system-ui, sans-serif;
        }
        .qt-header-brand {
          display: flex; align-items: center; gap: 8px;
          text-decoration: none;
        }
        .qt-header-dot {
          width: 7px; height: 7px; border-radius: 50%;
          background: #38bdf8; box-shadow: 0 0 8px rgba(56,189,248,0.5);
        }
        .qt-header-name {
          font-size: 13px; font-weight: 600;
          letter-spacing: 0.06em; text-transform: uppercase;
          color: #38bdf8;
        }
        .qt-header-version {
          font-size: 9px; font-weight: 600;
          padding: 2px 6px; border-radius: 4px;
          background: rgba(56,189,248,0.1);
          color: #38bdf8;
          border: 1px solid rgba(56,189,248,0.2);
          text-transform: uppercase; letter-spacing: 0.04em;
          margin-left: 2px;
        }
        .qt-header-nav {
          display: flex; align-items: center; gap: 2px;
        }
        .qt-header-link {
          font-size: 12px; color: #7fa3c4;
          padding: 5px 10px; border-radius: 5px;
          cursor: pointer; text-decoration: none;
          transition: color 0.15s, background 0.15s;
          white-space: nowrap;
        }
        .qt-header-link:hover {
          color: #e2e8f0; background: #1e293b;
        }
        .qt-header-divider {
          width: 1px; height: 18px; background: #1e3a5f; margin: 0 4px;
        }
        .qt-header-btn {
          font-size: 12px; font-weight: 500;
          padding: 5px 12px; border-radius: 6px;
          cursor: pointer; font-family: 'IBM Plex Sans', system-ui, sans-serif;
          transition: all 0.15s; border: none;
        }
        .qt-header-signin {
          background: transparent;
          border: 1px solid #2d3f55 !important;
          color: #7fa3c4;
          margin-left: 4px;
        }
        .qt-header-signin:hover { border-color: #3b5268 !important; color: #e2e8f0; }
        .qt-header-pro {
          background: #38bdf8; color: #0f172a;
          font-weight: 600; margin-left: 6px;
        }
        .qt-header-pro:hover { background: #7dd3fc; }
        @media (max-width: 640px) {
          .qt-header-hide-mobile { display: none; }
          .qt-header-signin { display: none; }
        }
      `}</style>

      <header className="qt-header">
        <a href="/" className="qt-header-brand">
          <div className="qt-header-dot" />
          <span className="qt-header-name">QueryTuner</span>
          <span className="qt-header-version">v0.2.0</span>
        </a>

        <nav className="qt-header-nav">
          <a
            href="https://sql-query-analyzer-ekbk.onrender.com/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-header-link qt-header-hide-mobile"
          >
            API Docs
          </a>
          <a
            href="https://github.com/AutoShiftOps/sql-query-analyzer"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-header-link qt-header-hide-mobile"
          >
            GitHub
          </a>
          <a
            href="https://github.com/AutoShiftOps/sql-query-analyzer/blob/master/ROADMAP.md"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-header-link qt-header-hide-mobile"
          >
            Roadmap
          </a>

          <div className="qt-header-divider qt-header-hide-mobile" />

          {/* Phase 4 placeholder — wire to Clerk/Supabase Auth when ready */}
          <button className="qt-header-btn qt-header-signin" disabled title="Coming soon">
            Sign in
          </button>
          <button
            className="qt-header-btn qt-header-pro"
            onClick={() =>
              window.open('https://github.com/AutoShiftOps/sql-query-analyzer', '_blank')
            }
            title="Star us on GitHub"
          >
            ★ Star
          </button>
        </nav>
      </header>
    </>
  );
}
