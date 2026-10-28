import { useEffect, useState } from 'react';
import { trackOwnQueryNudgeClicked, trackFollowUpSurveyAnswer } from '../utils/analytics';

// The survey waits this long so the visitor reads the findings first; the
// "try your own query" card is shown straight away.
const SURVEY_DELAY_MS = 15000;

const OPTIONS = [
  { id: 'privacy', label: "I wasn't sure it was safe to paste a real query" },
  { id: 'no_query', label: "I didn't have a slow query handy" },
  { id: 'no_need', label: 'The sample told me what I needed' },
  { id: 'not_useful', label: "It doesn't fit my database or workflow" },
  { id: 'other', label: 'Something else' },
];

/**
 * Shown under a result that came from a sample query. Two jobs:
 *  1. nudge the visitor to try their own slowest query (activation), and
 *  2. ask one question about what is stopping them (primary data for the
 *     dissertation). Answers are a fixed option id only.
 */
export default function ResultFollowUp({ onTryOwn }) {
  const [answered, setAnswered] = useState(false);
  const [surveyReady, setSurveyReady] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setSurveyReady(true), SURVEY_DELAY_MS);
    return () => clearTimeout(t);
  }, []);

  const answer = (id) => {
    trackFollowUpSurveyAnswer(id);
    setAnswered(true);
  };

  return (
    <div
      className="rounded-xl p-4 space-y-3"
      style={{ background: '#1e293b', border: '1px solid #2d3f55' }}
    >
      <div>
        <p className="text-sm font-semibold" style={{ color: '#e2e8f0' }}>
          Now try your own slowest query
        </p>
        <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>
          Paste the query that hurts most. Once it is in the box, a &ldquo;Sanitize before
          analyzing&rdquo; button appears underneath. It swaps your table and column names for
          generic ones first. Analysis runs without connecting to your database.
        </p>
        <button
          type="button"
          onClick={() => {
            trackOwnQueryNudgeClicked();
            onTryOwn();
          }}
          className="mt-2 text-xs font-semibold px-3 py-1.5 rounded-lg"
          style={{ background: '#38bdf8', color: '#0f172a' }}
        >
          Clear the sample and paste mine
        </button>
      </div>

      {surveyReady && (
        <div className="pt-3" style={{ borderTop: '1px solid #2d3f55' }}>
          {answered ? (
            <p className="text-xs" style={{ color: '#7fa3c4' }}>
              Thanks, that helps us improve QueryTuner.
            </p>
          ) : (
            <>
              <p className="text-xs mb-2" style={{ color: '#94a3b8' }}>
                Quick question: what would stop you from running your own query here?
              </p>
              <div className="flex flex-wrap gap-2">
                {OPTIONS.map((o) => (
                  <button
                    key={o.id}
                    type="button"
                    onClick={() => answer(o.id)}
                    className="text-xs px-2.5 py-1 rounded-full"
                    style={{ background: '#0f172a', border: '1px solid #2d3f55', color: '#cbd5e1' }}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
