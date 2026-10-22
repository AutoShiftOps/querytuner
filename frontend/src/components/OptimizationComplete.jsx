// Shown once a rewritten query actually exists. Deliberately carries no
// numbers of its own: QueryTuner has no live DB connection, so it never
// measures execution time or rows scanned — see the "Est. improvement" cell
// in App.jsx's stat strip, which only surfaces what the model itself said.
export default function OptimizationComplete() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 14px',
        borderRadius: 8,
        background: 'rgba(52,211,153,0.08)',
        border: '1px solid rgba(52,211,153,0.25)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 20,
          height: 20,
          borderRadius: '50%',
          background: '#34d399',
          color: '#062018',
          fontSize: 12,
          fontWeight: 800,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        ✓
      </span>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>Optimization complete</div>
        <div style={{ fontSize: 11.5, color: '#94a3b8' }}>
          Rewrite ready to copy and test against your own EXPLAIN output.
        </div>
      </div>
    </div>
  );
}
