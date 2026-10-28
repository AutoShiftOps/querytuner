import { useState } from 'react';
import { HelpCircle, Check, X, ChevronRight } from 'lucide-react';

// One question, answered independently of the others — clicking an
// option locks it in (no changing your answer) and reveals the real
// `reason` text QueryTuner already computed for this query, whether the
// pick was right or wrong. Per docs/querytuner-quiz-mode-issue.md item 3:
// "immediate right/wrong feedback with the real reason text shown either
// way."
function QuestionCard({ question, index, total }) {
  const [selected, setSelected] = useState(null);
  const answered = selected !== null;
  const pickedCorrect = answered && question.options[selected]?.isCorrect;

  return (
    <div className="p-4 rounded border border-slate-700 bg-slate-900/40">
      <p
        className="text-xs font-medium uppercase tracking-wider mb-2"
        style={{ color: '#4a6480', letterSpacing: '0.06em' }}
      >
        Question {index + 1} of {total}
      </p>
      <p className="text-white font-medium mb-3 text-sm">{question.prompt}</p>

      <div className="space-y-2">
        {question.options.map((opt, i) => {
          const isSelected = selected === i;
          let style = { borderColor: '#2d3f55', background: '#0f172a', color: '#cbd5e1' };
          if (answered) {
            if (opt.isCorrect) {
              style = {
                borderColor: '#34d399',
                background: 'rgba(52,211,153,0.1)',
                color: '#34d399',
              };
            } else if (isSelected) {
              style = {
                borderColor: '#f87171',
                background: 'rgba(248,113,113,0.1)',
                color: '#f87171',
              };
            } else {
              style = { borderColor: '#2d3f55', background: '#0f172a', color: '#4a6480' };
            }
          }
          return (
            <button
              key={i}
              type="button"
              disabled={answered}
              onClick={() => setSelected(i)}
              className="w-full text-left text-sm px-3 py-2 rounded border transition-colors flex items-center justify-between gap-2"
              style={{ ...style, cursor: answered ? 'default' : 'pointer' }}
            >
              <span>{opt.text}</span>
              {answered && opt.isCorrect && <Check className="w-4 h-4 flex-shrink-0" />}
              {answered && isSelected && !opt.isCorrect && <X className="w-4 h-4 flex-shrink-0" />}
            </button>
          );
        })}
      </div>

      {answered && (
        <div
          className="mt-3 text-xs rounded px-3 py-2"
          style={{
            background: pickedCorrect ? 'rgba(52,211,153,0.08)' : 'rgba(251,191,36,0.08)',
            border: `1px solid ${pickedCorrect ? 'rgba(52,211,153,0.2)' : 'rgba(251,191,36,0.2)'}`,
          }}
        >
          <p className="font-medium mb-1" style={{ color: pickedCorrect ? '#34d399' : '#fbbf24' }}>
            {pickedCorrect ? '✓ Correct' : '✗ Not quite'}
          </p>
          <p style={{ color: '#7fa3c4' }}>{question.reason}</p>
        </div>
      )}
    </div>
  );
}

// Opt-in "test yourself" card shown UNDER the findings (it used to gate
// them — visitors who came for the diagnosis had to answer or skip first).
// Collapsed by default; `onOpen` fires once when a visitor expands it, so the
// quiz-open rate can be measured in GA4. Questions are drawn from this
// query's own high-confidence findings — see docs/querytuner-quiz-mode-issue.md.
export default function QuizMode({ questions, onOpen }) {
  const [open, setOpen] = useState(false);
  if (!Array.isArray(questions) || questions.length === 0) return null;

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          onOpen?.();
        }}
        className="w-full text-left rounded-lg p-4 border border-slate-700 bg-slate-800 hover:border-slate-500 transition-colors flex items-center justify-between gap-3"
      >
        <span className="flex items-center gap-2">
          <HelpCircle className="w-3.5 h-3.5" style={{ color: '#38bdf8' }} />
          <span className="text-sm font-medium" style={{ color: '#e2e8f0' }}>
            Test yourself: spot what&rsquo;s wrong with this query
          </span>
          <span className="text-xs" style={{ color: '#4a6480' }}>
            optional
          </span>
        </span>
        <ChevronRight className="w-4 h-4" style={{ color: '#7fa3c4' }} />
      </button>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <HelpCircle className="w-3.5 h-3.5" style={{ color: '#38bdf8' }} />
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: '#38bdf8',
            }}
          >
            Quiz Mode
          </span>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs font-medium"
          style={{
            color: '#7fa3c4',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          Close
        </button>
      </div>
      <p className="text-xs mb-4" style={{ color: '#4a6480' }}>
        What do you think is wrong with this query? The findings above show the answer.
      </p>

      <div className="space-y-3">
        {questions.map((q, i) => (
          <QuestionCard key={q.id} question={q} index={i} total={questions.length} />
        ))}
      </div>
    </div>
  );
}
