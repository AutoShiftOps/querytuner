export default function Footer() {
  const year = new Date().getFullYear();

  return (
    <>
      <style>{`
        .qt-footer {
          border-top: 1px solid #1a2e45;
          padding: 14px 20px;
          display: flex; align-items: center;
          justify-content: space-between; flex-wrap: wrap;
          gap: 10px;
          background: #0f172a;
          font-family: 'IBM Plex Sans', system-ui, sans-serif;
        }
        .qt-footer-left {
          display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
        }
        .qt-footer-brand {
          display: flex; align-items: center; gap: 6px;
        }
        .qt-footer-dot {
          width: 5px; height: 5px; border-radius: 50%; background: #38bdf8;
        }
        .qt-footer-name {
          font-size: 11px; font-weight: 600;
          letter-spacing: 0.06em; text-transform: uppercase;
          color: #38bdf8;
        }
        .qt-footer-link {
          font-size: 11px; color: #4a6480;
          text-decoration: none; cursor: pointer;
          transition: color 0.15s;
        }
        .qt-footer-link:hover { color: #7fa3c4; }
        .qt-footer-right {
          font-size: 10px; color: #4a6480;
          font-family: 'JetBrains Mono', monospace;
        }
      `}</style>

      <footer className="qt-footer">
        <div className="qt-footer-left">
          <div className="qt-footer-brand">
            <div className="qt-footer-dot" />
            <span className="qt-footer-name">QueryTuner</span>
          </div>
          <a
            href="https://sql-query-analyzer-ekbk.onrender.com/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-footer-link"
          >
            API Docs
          </a>
          <a
            href="https://github.com/AutoShiftOps/sql-query-analyzer"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-footer-link"
          >
            GitHub
          </a>
          <a
            href="https://github.com/AutoShiftOps/sql-query-analyzer/blob/master/ROADMAP.md"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-footer-link"
          >
            Roadmap
          </a>
          <a
            href="https://github.com/AutoShiftOps/sql-query-analyzer/blob/master/LICENSE"
            target="_blank"
            rel="noopener noreferrer"
            className="qt-footer-link"
          >
            MIT License
          </a>
        </div>

        <div className="qt-footer-right">v0.2.0 · © {year} Sudhakar Sajja</div>
      </footer>
    </>
  );
}
