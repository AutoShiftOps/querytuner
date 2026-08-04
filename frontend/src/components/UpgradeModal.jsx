import { useUser } from '@clerk/clerk-react';
import { X, Zap, History, Sparkles } from 'lucide-react';

// Phase 4: shown when a signed-in free-tier user hits FREE_LIMIT in App.jsx.
//
// The CTA reads its target from VITE_STRIPE_PAYMENT_LINK rather than a
// hardcoded URL — there is no real Stripe Payment Link available yet (one
// must be created in the Stripe dashboard for price_1U0nGnDnampVVaUXDZ2MvqQc
// and the resulting https://buy.stripe.com/... URL set as that env var).
// Shipping a fake/placeholder URL in source would silently 404 for every
// user, so the button disables itself with an explicit note instead.
const PAYMENT_LINK = import.meta.env.VITE_STRIPE_PAYMENT_LINK || '';

const FEATURES = [
  { icon: Zap, text: 'Unlimited analyses' },
  { icon: History, text: 'Query history' },
  { icon: Sparkles, text: 'Priority AI (OpenAI)' },
];

export default function UpgradeModal({ isOpen, onClose, usageCount }) {
  const { user } = useUser();

  if (!isOpen) return null;

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
          You&rsquo;ve used your {usageCount >= 10 ? usageCount : 10} free analyses
        </h2>
        <p style={{ fontSize: 13, color: '#7fa3c4', margin: '8px 0 20px' }}>
          Upgrade to QueryTuner Pro for unlimited analyses
        </p>

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

        {PAYMENT_LINK ? (
          <a
            href={paymentUrl}
            target="_blank"
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
            <button
              disabled
              title="Stripe payment link not configured — set VITE_STRIPE_PAYMENT_LINK"
              style={{
                display: 'block',
                width: '100%',
                textAlign: 'center',
                background: '#2d3f55',
                color: '#7fa3c4',
                fontWeight: 600,
                fontSize: 14,
                padding: '10px 16px',
                borderRadius: 8,
                border: 'none',
                cursor: 'not-allowed',
              }}
            >
              Upgrade to Pro →
            </button>
            <p style={{ fontSize: 11, color: '#4a6480', margin: '8px 0 0' }}>
              Payment link not configured yet — create one in Stripe Dashboard → Payment Links for{' '}
              price_1U0nGnDnampVVaUXDZ2MvqQc, then set VITE_STRIPE_PAYMENT_LINK.
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
