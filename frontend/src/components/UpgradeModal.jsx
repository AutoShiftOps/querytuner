import { useUser } from '@clerk/clerk-react';
import { X, Zap, History, Sparkles } from 'lucide-react';
import { buildProRequestMailto } from '../utils/proWaitlist';

// Phase 4: shown when a signed-in free-tier user hits FREE_LIMIT in App.jsx.
//
// CHECKOUT_ENABLED is a deliberate, explicit switch — separate from
// whether a Stripe Payment Link happens to be configured. Real checkout
// only ever shows when BOTH are true. This is intentional: an env var
// that's merely unset is too easy to flip on by accident later (someone
// sets VITE_STRIPE_PAYMENT_LINK for an unrelated reason and real
// payments silently go live). Until CHECKOUT_ENABLED is explicitly set
// to "true" in Vercel, every user sees the "coming soon" + free-request
// flow below, no matter what else is configured.
const CHECKOUT_ENABLED = (import.meta.env.VITE_PRO_CHECKOUT_ENABLED || '').toLowerCase() === 'true';
const PAYMENT_LINK = import.meta.env.VITE_STRIPE_PAYMENT_LINK || '';

const FEATURES = [
  { icon: Zap, text: 'Unlimited analyses' },
  { icon: History, text: 'Query history' },
  { icon: Sparkles, text: 'Priority AI (OpenAI)' },
];

export default function UpgradeModal({ isOpen, onClose, usageCount, title, subtitle }) {
  const { user } = useUser();

  if (!isOpen) return null;

  // title/subtitle let callers customize the pitch for the trigger that
  // opened the modal (monthly analysis count vs. a single query exceeding
  // the free-tier character limit) — default to the monthly-limit copy.
  const modalTitle =
    title ?? `You’ve used your ${usageCount >= 10 ? usageCount : 10} free analyses`;
  const modalSubtitle = subtitle ?? 'Upgrade to QueryTuner Pro for unlimited analyses';

  // Stripe Payment Links pass client_reference_id straight through to the
  // resulting Checkout Session — the backend webhook reads it off
  // checkout.session.completed to link this Clerk user to the Stripe
  // customer that was just created. Without it, the webhook has no way to
  // know which user just paid.
  const paymentUrl =
    PAYMENT_LINK && user?.id
      ? `${PAYMENT_LINK}${
          PAYMENT_LINK.includes('?') ? '&' : '?'
        }client_reference_id=${encodeURIComponent(user.id)}`
      : PAYMENT_LINK;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="upgrade-modal-title"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        background: 'rgba(15,23,42,0.75)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#1e293b',
          border: '1px solid #2d3f55',
          borderRadius: 12,
          padding: 32,
          maxWidth: 420,
          width: '100%',
          position: 'relative',
          fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
        }}
      >
        <button
          onClick={onClose}
          aria-label="Close"
          style={{
            position: 'absolute',
            top: 16,
            right: 16,
            background: 'none',
            border: 'none',
            color: '#7fa3c4',
            cursor: 'pointer',
            padding: 4,
            display: 'flex',
          }}
        >
          <X size={18} />
        </button>

        <h2
          id="upgrade-modal-title"
          style={{ fontSize: 18, fontWeight: 600, color: '#e2e8f0', margin: 0 }}
        >
          {modalTitle}
        </h2>
        <p style={{ fontSize: 13, color: '#7fa3c4', margin: '8px 0 20px' }}>{modalSubtitle}</p>

        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 12 }}>
          {FEATURES.map(({ icon: Icon, text }) => (
            <li key={text} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon size={16} style={{ color: '#38bdf8', flexShrink: 0 }} />
              <span style={{ fontSize: 13, color: '#e2e8f0' }}>{text}</span>
            </li>
          ))}
        </ul>

        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 4,
            margin: '24px 0 16px',
          }}
        >
          <span style={{ fontSize: 28, fontWeight: 700, color: '#e2e8f0' }}>$19</span>
          <span style={{ fontSize: 13, color: '#7fa3c4' }}>/month</span>
        </div>

        {CHECKOUT_ENABLED && PAYMENT_LINK ? (
          <a
            href={paymentUrl}
            rel="noopener noreferrer"
            style={{
              display: 'block',
              textAlign: 'center',
              background: '#38bdf8',
              color: '#0f172a',
              fontWeight: 600,
              fontSize: 14,
              padding: '10px 16px',
              borderRadius: 8,
              textDecoration: 'none',
            }}
          >
            Upgrade to Pro →
          </a>
        ) : (
          <div>
            <a
              href={buildProRequestMailto({
                email: user?.primaryEmailAddress?.emailAddress || null,
                userId: user?.id || null,
              })}
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'center',
                background: '#38bdf8',
                color: '#0f172a',
                fontWeight: 600,
                fontSize: 14,
                padding: '10px 16px',
                borderRadius: 8,
                textDecoration: 'none',
              }}
            >
              Pro is coming soon — request free early access →
            </a>
            <p style={{ fontSize: 11, color: '#7fa3c4', margin: '8px 0 0', textAlign: 'center' }}>
              We&rsquo;re not charging for Pro yet. Click above and we&rsquo;ll turn it on for your account, free.
            </p>
          </div>
        )}

        <button
          onClick={onClose}
          style={{
            display: 'block',
            width: '100%',
            textAlign: 'center',
            background: 'none',
            border: 'none',
            color: '#7fa3c4',
            fontSize: 12,
            marginTop: 12,
            padding: '8px 0',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          Continue with free tier
        </button>
      </div>
    </div>
  );
}
