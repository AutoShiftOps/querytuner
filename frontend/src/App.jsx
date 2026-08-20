import { useCallback, useEffect, useState, useRef } from 'react';
import { useUser, useAuth } from '@clerk/clerk-react';
import ShareButton from './components/ShareButton';
import QueryDiagnosis from './components/QueryDiagnosis';
import { AlertCircle, Zap, Shield } from 'lucide-react';
import QueryInput from './components/QueryInput';
import ResultsPanel from './components/ResultsPanel';
import OptimizationSuggestions from './components/OptimizationSuggestions';
import ExecutionPlan from './components/ExecutionPlan';
import SampleQueries from './components/SampleQueries';
import Header from './components/Header';
import Hero from './components/Hero';
import Footer from './components/Footer';
import UpgradeModal from './components/UpgradeModal';
import { ToastContainer, useToast } from './components/Toast';
import { getAiConfirmedTypes } from './utils/aiInsights';
import {
  buildUrlWithoutUpgradedParam,
  hasUpgradedParam,
  pollForProStatus,
} from './utils/upgradeRedirect';
import {
  trackAnalysisRun,
  trackAnalysisSuccess,
  trackAnalysisError,
  trackSampleQuerySelected,
  trackDbTypeChanged,
  trackAiToggle,
  trackShareClicked,
  trackUpgradeConversion,
  trackOptimizedQueryCopied,
  trackAiInsightsCopied,
} from './utils/analytics';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [query, setQuery] = useState('');
  const [explainPlan, setExplainPlan] = useState('');
  const [schemaDdl, setSchemaDdl] = useState('');
  const [dbType, setDbType] = useState('postgresql');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [caps, setCaps] = useState(null);
  const [llmProvider, setLlmProvider] = useState('huggingface');
  const [useLlm, setUseLlm] = useState(false);
  // Query sanitizer — null when not sanitized, substitution map when active.
  // Session-only: never persisted to localStorage/sessionStorage/cookies.
  const [substitutionMap, setSubstitutionMap] = useState(null);
  const { toasts, showToast, dismissToast } = useToast();
  const analyzeBtnRef = useRef(null);
  const [highlightAnalyze, setHighlightAnalyze] = useState(false);

  // ── Phase 4: Clerk auth + usage tracking ─────────────────────────────────
  const { isSignedIn } = useUser();
  const { getToken } = useAuth();
  const [usageCount, setUsageCount] = useState(0);
  const [isPro, setIsPro] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  // null = default "N free analyses used" copy (monthly limit trigger).
  // {title, subtitle} = custom copy for the query-too-large / anonymous-
  // limit / sign-in-required triggers.
  const [upgradeModalCopy, setUpgradeModalCopy] = useState(null);
  const FREE_LIMIT = 10;
  // Anonymous usage — session-only, resets on refresh, purely for immediate
  // UI feedback. Mirrors backend/app/main.py's ANONYMOUS_DAILY_LIMIT, but
  // isn't the source of truth: unlike usageCount (rehydrated from GET
  // /usage for signed-in users), there's no user_id to key an anonymous
  // count by, so this can't survive a refresh or be enforced for real —
  // the backend's own per-IP check is what actually matters here, same as
  // every other limit in this app.
  const [anonymousCount, setAnonymousCount] = useState(0);
  const ANONYMOUS_DAILY_LIMIT = 5;

  // Stripe Checkout redirect (?upgraded=true) — captured once, synchronously,
  // on the very first render, so it survives the URL being stripped and
  // isSignedIn changing as Clerk resolves auth state (both would otherwise
  // make a naive re-check of window.location.search below miss it).
  // upgradedRedirectHandledRef additionally guards against processing it
  // more than once (StrictMode's double effect-invoke in dev, or isSignedIn
  // changing again later).
  const hadUpgradedParamRef = useRef(
    typeof window !== 'undefined' && hasUpgradedParam(window.location.search)
  );
  const upgradedRedirectHandledRef = useRef(false);

  const canAnalyze = useCallback(() => {
    if (!isSignedIn) {
      // AI insights require signing in outright — heuristic-only stays
      // open, capped at the same daily count the backend enforces.
      if (useLlm) return false;
      return anonymousCount < ANONYMOUS_DAILY_LIMIT;
    }
    if (isPro) return true;
    if (usageCount >= FREE_LIMIT) return false;
    return true;
  }, [isSignedIn, isPro, usageCount, useLlm, anonymousCount]);

  // Hydrate usageCount/isPro from the backend's authoritative monthly count
  // on sign-in — without this, refreshing the page would silently reset the
  // free-tier counter back to 0 since React state doesn't persist reloads.
  useEffect(() => {
    if (!isSignedIn) return;
    (async () => {
      try {
        const token = await getToken();
        const r = await axios.get(`${API_BASE_URL}/usage`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        setUsageCount(r.data?.count ?? 0);
        setIsPro(!!r.data?.is_pro);
      } catch {
        // Usage endpoint unavailable — fall back to the local honour-system
        // count already held in state rather than blocking the UI.
      }
    })();
  }, [isSignedIn, getToken]);

  // ── Stripe Checkout redirect (?upgraded=true) ────────────────────────────
  // The redirect back to the site and Stripe's webhook (which is what
  // actually flips is_pro in Supabase — see backend/app/main.py's
  // stripe_webhook()) are two independent async paths from the same
  // checkout. Landing here doesn't mean the webhook has finished yet, so
  // this doesn't just trust the query param — it re-fetches GET /usage and
  // retries with a short backoff before either confirming Pro or falling
  // back to a softer "this can take a moment" message. Runs once
  // hadUpgradedParamRef was set on mount and isSignedIn has resolved to a
  // real boolean (not Clerk's transient undefined-while-loading state).
  useEffect(() => {
    if (!hadUpgradedParamRef.current || upgradedRedirectHandledRef.current) return;
    if (isSignedIn === undefined) return;
    upgradedRedirectHandledRef.current = true;

    // Strip the param regardless of what happens next, so a refresh doesn't
    // re-trigger this whole flow (toast + polling) a second time.
    window.history.replaceState({}, '', buildUrlWithoutUpgradedParam(window.location.href));

    if (!isSignedIn) return; // Checkout requires being signed in — shouldn't happen, but nothing to poll for without a user.

    // No cleanup-driven cancellation here on purpose: upgradedRedirectHandledRef
    // above is already the sole "run this once" guard. A `cancelled` flag set
    // from this effect's own cleanup would get flipped true by React
    // StrictMode's dev-only mount -> cleanup -> mount cycle before the async
    // work below resolves, silently discarding the one real result every
    // time (caught via visual verification, not theoretical — the toast
    // never appeared under StrictMode with this pattern). React 18+ already
    // no-ops state updates on an unmounted component, so there's nothing to
    // guard against by tracking cancellation ourselves.
    (async () => {
      const fetchUsage = async () => {
        const token = await getToken();
        const r = await axios.get(`${API_BASE_URL}/usage`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        return r.data;
      };

      const result = await pollForProStatus(fetchUsage);

      if (result.success) {
        setUsageCount(result.usage?.count ?? 0);
        setIsPro(true);
        // Only fires here — genuinely confirmed is_pro: true from a real
        // GET /usage response, never on the ?upgraded=true param alone.
        // Double-fire guard: this whole effect body only runs once per
        // real page load (hadUpgradedParamRef/upgradedRedirectHandledRef
        // above), and ?upgraded=true is stripped from the URL before this
        // branch can even be reached, so a refresh can't re-enter it —
        // no separate guard needed here.
        trackUpgradeConversion();
        showToast('Welcome to QueryTuner Pro! Unlimited analyses, unlocked.', 'success');
      } else {
        // Don't claim Pro status that isn't actually active — Stripe's
        // webhook may just be slow, or it may have failed outright. Either
        // way this is worth being able to find in the logs rather than
        // only ever surfacing as a user complaint with no trail.
        console.warn(
          '[QueryTuner] Checkout redirect: is_pro was still false after retrying GET /usage — ' +
            'the Stripe webhook may be delayed or failed. See backend/app/main.py stripe_webhook().'
        );
        showToast(
          "Payment received — this can take a moment to activate. Refresh shortly if Pro isn't showing yet.",
          'info'
        );
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn]);

  // ── Analyze — defined first so useEffects below can reference it ────────
  const handleAnalyze = useCallback(async () => {
    if (!canAnalyze()) {
      if (!isSignedIn && useLlm) {
        showToast(
          'Sign in to use AI insights. Heuristic analysis is available without an account.',
          'info'
        );
        return;
      }
      if (!isSignedIn) {
        setUpgradeModalCopy({
          title: "You've used today's free limit",
          subtitle: `Sign in for ${FREE_LIMIT} free analyses every month, or upgrade to Pro for unlimited.`,
        });
        setShowUpgradeModal(true);
        return;
      }
      showToast('Free limit reached — upgrade to Pro for unlimited analyses', 'warning');
      setUpgradeModalCopy(null);
      setShowUpgradeModal(true);
      return;
    }

    // Track intent before the API call
    trackAnalysisRun({
      db_type: dbType,
      use_llm: useLlm,
      llm_provider: llmProvider,
      query_length: query.length,
    });

    try {
      setLoading(true);
      setError(null);
      const token = isSignedIn ? await getToken() : null;
      const response = await axios.post(
        `${API_BASE_URL}/analyze`,
        {
          query,
          db_type: dbType,
          llm_provider: llmProvider,
          use_llm: useLlm,
          focus: 'performance',
          explain_plan: explainPlan,
          schema_info: schemaDdl || null,
        },
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );

      const data = response.data;
      setResult(data);
      showToast('Analysis complete · share link ready', 'success');

      if (isSignedIn && !isPro) {
        setUsageCount((prev) => prev + 1);
      } else if (!isSignedIn) {
        setAnonymousCount((prev) => prev + 1);
      }

      // Track successful result with outcome metrics
      trackAnalysisSuccess({
        db_type: dbType,
        issue_count: data.optimization_suggestions?.length ?? 0,
        severity: data.severity,
        analysis_time_ms: data.analysis_time_ms,
        has_optimized_query: !!data.optimized_query,
        has_ai_insights: !!data.ai_insights,
        analysis_id: data.analysis_id,
      });
    } catch (err) {
      setResult(null);
      // query_too_large, sign_in_required, and anonymous_limit_reached all
      // share a {error, message, ...} shape (not the usual {detail}
      // FastAPI HTTPException shape) — a structured, toast/modal-friendly
      // body rather than a generic 401/429 the frontend can't act on.
      const errorCode = err.response?.data?.error;
      const isQueryTooLarge = errorCode === 'query_too_large';
      const isSignInRequired = errorCode === 'sign_in_required';
      const isAnonymousLimitReached = errorCode === 'anonymous_limit_reached';
      const hasStructuredError = isQueryTooLarge || isSignInRequired || isAnonymousLimitReached;
      // upgrade_available is only true for free/anonymous users who hit the
      // smaller per-query character limit — that's Pro's actual pitch, so
      // show the upgrade modal instead of a toast the user just dismisses.
      const upgradeAvailable = isQueryTooLarge && err.response?.data?.upgrade_available === true;
      const detail = hasStructuredError
        ? err.response.data.message
        : err.response?.data?.detail || 'Analysis failed';
      setError(detail);
      if (upgradeAvailable) {
        setUpgradeModalCopy({
          title: 'Your query is too large for the free tier',
          subtitle:
            'QueryTuner Pro supports queries up to 32,000 characters — covering real production SQL.',
        });
        setShowUpgradeModal(true);
      } else if (isAnonymousLimitReached) {
        setUpgradeModalCopy({
          title: "You've used today's free limit",
          subtitle: `Sign in for ${FREE_LIMIT} free analyses every month, or upgrade to Pro for unlimited.`,
        });
        setShowUpgradeModal(true);
      } else if (isSignInRequired) {
        showToast(detail, 'info');
      } else if (isQueryTooLarge) {
        showToast(detail, 'warning');
      } else {
        showToast('Analysis failed — please check your query', 'error');
      }
      trackAnalysisError(err.response ? 'backend' : 'network', dbType);
    } finally {
      setLoading(false);
    }
  }, [
    query,
    dbType,
    llmProvider,
    useLlm,
    explainPlan,
    schemaDdl,
    showToast,
    canAnalyze,
    isSignedIn,
    isPro,
    getToken,
  ]);

  // ── Cmd/Ctrl + Enter shortcut ───────────────────────────────────────────
  useEffect(() => {
    const handleKeydown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        handleAnalyze();
      }
    };
    document.addEventListener('keydown', handleKeydown);
    return () => document.removeEventListener('keydown', handleKeydown);
  }, [handleAnalyze]);

  // ── AI toggle toast + analytics ─────────────────────────────────────────
  useEffect(() => {
    if (useLlm) {
      showToast('AI insights enabled', 'info');
      trackAiToggle(true, llmProvider);
    }
  }, [useLlm, showToast, llmProvider]);

  // ── Fetch backend capabilities ──────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API_BASE_URL}/capabilities`);
        setCaps(r.data);
        setLlmProvider(r.data?.default_provider || 'huggingface');
      } catch {
        setCaps(null);
      }
    })();
  }, []);

  // ── Derived values ───────────────────────────────────────────────────────
  const issueCount = Array.isArray(result?.optimization_suggestions)
    ? result.optimization_suggestions.length
    : 0;

  // Heuristic types the AI's most_impactful_improvements also flagged — only
  // computed when AI was actually used and returned usable content. Drives
  // the "✓ Confirmed by AI" badge in OptimizationSuggestions and suppresses
  // the same finding from being repeated in the AI Insights panel.
  const aiConfirmedTypes =
    result?.used_ai && result?.ai_insights && !result?.ai_error
      ? getAiConfirmedTypes(result.optimization_suggestions, result.ai_insights)
      : new Set();

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ background: '#0f172a' }} // flat — matches Header, Hero, Footer, ReportPage
    >
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
      <UpgradeModal
        isOpen={showUpgradeModal}
        onClose={() => setShowUpgradeModal(false)}
        usageCount={usageCount}
        title={upgradeModalCopy?.title}
        subtitle={upgradeModalCopy?.subtitle}
      />
      <Header isPro={isPro} showToast={showToast} />
      <Hero />

      {/* ── Main two-column grid ── */}
      <div className="flex-grow w-full mx-auto px-4 py-8" style={{ maxWidth: 1280 }}>
        <div
          className="grid gap-6"
          style={{
            gridTemplateColumns: result ? '1fr 1fr' : '1fr',
            alignItems: 'start',
          }}
        >
          {/* ── LEFT COLUMN — always visible ── */}
          <div className="space-y-4 min-w-0">
            <SampleQueries
              onSelect={(sql, db) => {
                setQuery(sql);
                setDbType(db);
                trackSampleQuerySelected(sql.slice(0, 40), db);

                // Scroll Analyze button into view + pulse highlight
                setTimeout(() => {
                  analyzeBtnRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  setHighlightAnalyze(true);
                  setTimeout(() => setHighlightAnalyze(false), 1600);
                }, 100);
              }}
            />
            <QueryInput
              ref={analyzeBtnRef}
              query={query}
              setQuery={setQuery}
              dbType={dbType}
              setDbType={(newDb) => {
                setDbType(newDb);
                trackDbTypeChanged(newDb);
              }}
              onAnalyze={handleAnalyze}
              loading={loading}
              useLlm={useLlm}
              setUseLlm={setUseLlm}
              llmProvider={llmProvider}
              setLlmProvider={setLlmProvider}
              caps={caps}
              explainPlan={explainPlan}
              setExplainPlan={setExplainPlan}
              schemaDdl={schemaDdl}
              setSchemaDdl={setSchemaDdl}
              substitutionMap={substitutionMap}
              setSubstitutionMap={setSubstitutionMap}
              highlightAnalyze={highlightAnalyze}
              isSignedIn={isSignedIn}
            />
            {error && (
              <div className="p-4 bg-red-900/20 border border-red-500 rounded-lg flex gap-3">
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-red-200 text-sm">{error}</p>
              </div>
            )}
          </div>

          {/* ── RIGHT COLUMN — appears only after analysis ── */}
          {result && (
            <div className="space-y-4 min-w-0">
              {/* Stat strip */}
              <div
                className="grid grid-cols-4 rounded-xl overflow-hidden"
                style={{
                  gap: 1,
                  background: '#2d3f55',
                  border: '1px solid #2d3f55',
                }}
              >
                {[
                  {
                    label: 'Analysis time',
                    value: `${Number(result.analysis_time_ms || 0).toFixed(1)}ms`,
                  },
                  {
                    label: 'Readability',
                    value: `${Math.round(Number(result.readability_score || 0))}/100`,
                  },
                  { label: 'Issues', value: issueCount, danger: issueCount > 0 },
                  {
                    label: 'Engine',
                    value: result.used_ai ? result.ai_provider || 'AI' : 'Heuristic',
                  },
                ].map(({ label, value, danger }) => (
                  <div
                    key={label}
                    className="flex flex-col gap-1 px-3 py-3"
                    style={{ background: '#1e293b' }}
                  >
                    <span
                      className="text-xs font-medium uppercase tracking-wider"
                      style={{ fontSize: 9, color: '#4a6480', letterSpacing: '0.08em' }}
                    >
                      {label}
                    </span>
                    <span
                      className="font-mono font-medium text-sm"
                      style={{ color: danger ? '#f87171' : '#38bdf8' }}
                    >
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              {/* Share button */}
              <div className="flex justify-end">
                <ShareButton
                  analysisId={result.analysis_id}
                  onShare={() => {
                    showToast('Share link copied to clipboard', 'success');
                    trackShareClicked(result.analysis_id);
                  }}
                />
              </div>

              {/* Query Diagnosis — structured dark renderer, no prose plugin needed */}
              {result.plain_explanation && <QueryDiagnosis content={result.plain_explanation} />}

              {/* Optimization findings */}
              <OptimizationSuggestions
                suggestions={result.optimization_suggestions || []}
                aiConfirmedTypes={aiConfirmedTypes}
                substitutionMap={substitutionMap}
              />

              {/* AI Insights — only show when AI was actually used and returned content */}
              {result.used_ai && result.ai_insights && !result.ai_error && (
                <ResultsPanel
                  title={`AI Insights${
                    result.ai_provider
                      ? ` (${result.ai_provider}${result.ai_model ? ` / ${result.ai_model}` : ''})`
                      : ''
                  }`}
                  content={result.ai_insights}
                  icon={Zap}
                  aiConfirmedTypes={aiConfirmedTypes}
                  substitutionMap={substitutionMap}
                  onShare={() => {
                    navigator.clipboard.writeText(result.ai_insights || '');
                    showToast('AI insights copied to clipboard', 'success');
                    trackAiInsightsCopied();
                  }}
                />
              )}

              {/* AI error — graceful fallback, no raw error strings shown to user */}
              {result.ai_error && (
                <div
                  className="rounded-xl p-4 flex gap-3 items-start"
                  style={{
                    background: 'rgba(251,191,36,0.06)',
                    border: '1px solid rgba(251,191,36,0.2)',
                  }}
                >
                  <Zap className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#fbbf24' }} />
                  <div>
                    <p className="text-sm font-medium" style={{ color: '#fbbf24' }}>
                      AI insights unavailable
                    </p>
                    <p className="text-xs mt-1" style={{ color: '#7fa3c4' }}>
                      The AI model is warming up (free tier cold start). Heuristic analysis above is
                      complete. Toggle AI off and re-analyze, or try again in 30 seconds.
                    </p>
                  </div>
                </div>
              )}

              {/* Optimized Query */}
              {result.optimized_query && (
                <div
                  className="rounded-xl overflow-hidden"
                  style={{ background: '#1e293b', border: '1px solid #2d3f55' }}
                >
                  <div
                    className="flex items-center justify-between px-4 py-2"
                    style={{ background: 'rgba(0,0,0,0.25)', borderBottom: '1px solid #2d3f55' }}
                  >
                    <div className="flex items-center gap-2">
                      <Zap className="w-4 h-4 text-blue-400" />
                      <span className="text-sm font-semibold text-white">Optimized Query</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        style={{
                          fontSize: 10,
                          color: '#34d399',
                          fontFamily: 'monospace',
                          fontWeight: 500,
                        }}
                      >
                        ✓ rewritten
                      </span>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(result.optimized_query);
                          showToast('Optimized query copied', 'success');
                          trackOptimizedQueryCopied();
                        }}
                        className="text-xs text-slate-400 hover:text-white border border-slate-600
                                   hover:border-slate-400 px-3 py-1 rounded transition-colors"
                      >
                        Copy
                      </button>
                    </div>
                  </div>
                  <pre
                    className="whitespace-pre-wrap text-sm leading-relaxed overflow-x-auto p-4"
                    style={{ color: '#34d399', fontFamily: "'JetBrains Mono', monospace" }}
                  >
                    {result.optimized_query}
                  </pre>
                </div>
              )}

              {/* Execution Plan */}
              {result.execution_plan && <ExecutionPlan plan={result.execution_plan} />}

              {/* Security Issues */}
              {Array.isArray(result.security_issues) && result.security_issues.length > 0 && (
                <div
                  className="rounded-xl p-5"
                  style={{
                    background: 'rgba(248,113,113,0.06)',
                    border: '1px solid rgba(248,113,113,0.3)',
                  }}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <Shield className="w-4 h-4 text-red-400" />
                    <h3 className="text-sm font-semibold text-white">Security Issues</h3>
                  </div>
                  <ul className="space-y-2">
                    {result.security_issues.map((issue, idx) => (
                      <li key={idx} className="text-sm text-red-200 flex gap-2">
                        <span style={{ color: '#f87171' }}>·</span>
                        {issue}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Empty state — shown before first analysis */}
        {!result && !loading && (
          <div className="mt-12 text-center" style={{ color: '#4a6480' }}>
            <p className="text-sm">
              Paste a query above and press{' '}
              <kbd
                className="px-2 py-0.5 rounded text-xs font-mono"
                style={{ background: '#1e293b', border: '1px solid #2d3f55', color: '#7fa3c4' }}
              >
                ⌘ Enter
              </kbd>{' '}
              to analyze
            </p>
          </div>
        )}
      </div>

      <Footer />
    </div>
  );
}

export default App;
