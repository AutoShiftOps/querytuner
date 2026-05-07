import ReactMarkdown from 'react-markdown';
import { ToastContainer, useToast } from './components/Toast';

function ResultsPanel({ title, content, icon: Icon }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-5 h-5 text-blue-400" />}
          <h3 className="text-lg font-bold text-white">{title}</h3>
        </div>
        <button
          onClick={() => navigator.clipboard.writeText(content)}
          className="text-xs text-slate-400 hover:text-white border border-slate-600
                     hover:border-slate-400 px-3 py-1 rounded transition-colors"
        >
          Copy
        </button>
      </div>
      <div className="prose prose-invert prose-sm max-w-none text-slate-300">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}

export default ResultsPanel;
