/**
 * analytics.js — Centralized GA4 event tracking for QueryTuner
 * Place at: frontend/src/utils/analytics.js
 *
 * All GA4 event calls go through this file.
 * Never call window.gtag() directly in components — always use these functions.
 *
 * Why centralized:
 *   - Single place to audit what's tracked
 *   - Easy to swap GA4 for Plausible/PostHog later
 *   - Silently no-ops if gtag isn't loaded (dev, ad-blockers)
 *   - EB-1A: clean event taxonomy = credible usage analytics screenshots
 *
 * GA4 SETUP CHECKLIST:
 *   1. Create GA4 property at analytics.google.com
 *   2. Add Data Stream → Web → querytuner.com
 *   3. Copy Measurement ID (G-XXXXXXXXXX)
 *   4. Replace both G-XXXXXXXXXX in index.html
 *   5. Add to Vercel: VITE_GA_MEASUREMENT_ID=G-XXXXXXXXXX (optional — index.html is enough)
 *   6. Verify in GA4 → Reports → Realtime after deploying
 */

// ── Safe gtag wrapper — silently no-ops if blocked or in dev ────────────────

function gtag(...args) {
  if (typeof window !== 'undefined' && typeof window.gtag === 'function') {
    window.gtag(...args);
  }
}

// ── Page tracking ─────────────────────────────────────────────────────────────

/**
 * Track a page view manually (useful for SPA route changes).
 * Called automatically on app load by gtag config — only call this
 * when navigating to /report/:id without a full page reload.
 *
 * @param {string} path - e.g. '/report/ea8266e3-...'
 * @param {string} title - page title
 */
export function trackPageView(path, title) {
  gtag('event', 'page_view', {
    page_location: `https://querytuner.com${path}`,
    page_title: title || document.title,
  });
}

// ── Core product events ───────────────────────────────────────────────────────

/**
 * Fired when user clicks "Analyze Query" or hits Cmd+Enter.
 * This is the PRIMARY conversion event for QueryTuner.
 *
 * @param {object} params
 * @param {string} params.db_type          - 'postgresql' | 'mysql' | 'oracle' | 'sqlserver' | 'sqlite'
 * @param {boolean} params.use_llm         - whether AI was enabled
 * @param {string} params.llm_provider     - 'huggingface' | 'openai'
 * @param {number} params.query_length     - character count of the input query
 */
export function trackAnalysisRun({ db_type, use_llm, llm_provider, query_length }) {
  gtag('event', 'analysis_run', {
    event_category: 'core',
    db_type,
    use_llm: use_llm ? 'enabled' : 'disabled',
    llm_provider: use_llm ? llm_provider : 'none',
    query_length_bucket: _lengthBucket(query_length),
  });
}

/**
 * Fired when analysis completes successfully.
 *
 * @param {object} params
 * @param {string} params.db_type
 * @param {number} params.issue_count      - number of findings returned
 * @param {string} params.severity         - 'low' | 'medium' | 'high' | 'critical'
 * @param {number} params.analysis_time_ms
 * @param {boolean} params.has_optimized_query
 * @param {boolean} params.has_ai_insights
 * @param {string|null} params.analysis_id - UUID if Supabase is wired
 */
export function trackAnalysisSuccess({
  db_type,
  issue_count,
  severity,
  analysis_time_ms,
  has_optimized_query,
  has_ai_insights,
  analysis_id,
}) {
  gtag('event', 'analysis_success', {
    event_category: 'core',
    db_type,
    issue_count,
    severity: severity || 'unknown',
    analysis_time_bucket: _timeBucket(analysis_time_ms),
    has_optimized_query,
    has_ai_insights,
    has_shareable_link: !!analysis_id,
  });
}

/**
 * Fired when analysis returns an error (network, backend, or validation).
 *
 * @param {string} error_type - 'network' | 'validation' | 'llm' | 'unknown'
 * @param {string} db_type
 */
export function trackAnalysisError(error_type, db_type) {
  gtag('event', 'analysis_error', {
    event_category: 'core',
    error_type,
    db_type,
  });
}

// ── Feature usage events ──────────────────────────────────────────────────────

/**
 * Fired when user clicks a sample query from the sample panel.
 *
 * @param {string} label  - display label of the sample (e.g. 'Correlated subquery')
 * @param {string} db_type
 */
export function trackSampleQuerySelected(label, db_type) {
  gtag('event', 'sample_query_selected', {
    event_category: 'engagement',
    sample_label: label,
    db_type,
  });
}

/**
 * Fired when user changes the database dialect selector.
 *
 * @param {string} db_type - new dialect selected
 */
export function trackDbTypeChanged(db_type) {
  gtag('event', 'db_type_changed', {
    event_category: 'engagement',
    db_type,
  });
}

/**
 * Fired when user toggles AI insights on or off.
 *
 * @param {boolean} enabled
 * @param {string} provider - 'huggingface' | 'openai'
 */
export function trackAiToggle(enabled, provider) {
  gtag('event', 'ai_toggle', {
    event_category: 'engagement',
    ai_enabled: enabled,
    llm_provider: provider,
  });
}

// ── Share & copy events ───────────────────────────────────────────────────────

/**
 * Fired when user clicks "Share analysis" and copies the link.
 * This is a KEY metric for viral coefficient.
 *
 * @param {string} analysis_id - UUID of the shared analysis
 */
export function trackShareClicked(analysis_id) {
  gtag('event', 'share_clicked', {
    event_category: 'viral',
    has_analysis_id: !!analysis_id,
  });
}

/**
 * Fired when user views a shared report page (not the main app).
 * Helps distinguish organic visits from shared-link visits.
 *
 * @param {string} analysis_id
 * @param {string} db_type
 */
export function trackReportViewed(analysis_id, db_type) {
  gtag('event', 'report_viewed', {
    event_category: 'viral',
    db_type: db_type || 'unknown',
    // Don't log analysis_id itself — keep PII out of GA
  });
}

/**
 * Fired when user copies the optimized query to clipboard.
 */
export function trackOptimizedQueryCopied() {
  gtag('event', 'optimized_query_copied', {
    event_category: 'engagement',
  });
}

/**
 * Fired when user copies AI insights to clipboard.
 */
export function trackAiInsightsCopied() {
  gtag('event', 'ai_insights_copied', {
    event_category: 'engagement',
  });
}

// ── Bucketing helpers (keeps GA4 reports readable) ───────────────────────────

function _lengthBucket(chars) {
  if (!chars) return 'unknown';
  if (chars < 50) return 'tiny (<50)';
  if (chars < 200) return 'small (50-200)';
  if (chars < 500) return 'medium (200-500)';
  if (chars < 2000) return 'large (500-2000)';
  return 'xlarge (2000+)';
}

function _timeBucket(ms) {
  if (!ms) return 'unknown';
  if (ms < 10) return 'fast (<10ms)';
  if (ms < 50) return 'normal (10-50ms)';
  if (ms < 200) return 'slow (50-200ms)';
  return 'very_slow (200ms+)';
}
