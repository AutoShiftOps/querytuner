// Remembers a signed-in visitor's explicit AI Insights choice across visits.
// 'off' means they unchecked it themselves, so the signed-in default (on)
// must not turn it back on. Never throws: storage can be blocked or empty.
const KEY = 'qt_ai_insights';

export function readAiPreference() {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === 'on' || v === 'off' ? v : null;
  } catch {
    return null;
  }
}

export function writeAiPreference(enabled) {
  try {
    window.localStorage.setItem(KEY, enabled ? 'on' : 'off');
  } catch {
    /* ignore */
  }
}

/** Signed-in visitors get AI on by default unless they previously turned it off. */
export function shouldDefaultAiOn({ isSignedIn, aiAvailable, preference }) {
  return !!isSignedIn && !!aiAvailable && preference !== 'off';
}
