import { isDemo } from "../api";

/** First-run walkthrough (D16).
 *
 *  Someone opening a shared link lands on an empty Today tab with no idea that
 *  the app runs on an inventory they have to stock first. Each step says what
 *  to do and what comes back, in the same words the screens use (D30), because
 *  the payoff (a ranked feed, a learned taste) is invisible until the kitchen
 *  has something in it.
 */
const STEPS = [
  {
    title: "Stock your kitchen",
    text: "Scan your shopping or type it in, in English or German. You tick a checklist first, so nothing misread is saved.",
  },
  {
    title: "Cook what fits",
    text: "87,861 recipes, ranked by what's in your kitchen, the dishes you like and what's left of today's calories and protein.",
  },
  {
    title: "Log what you eat",
    text: "Tap “I cooked this”, scan a pack or add ingredients. With your weigh-ins, Forkcast learns what you really burn and sets your daily target from it.",
  },
];

export function Intro({ onStart, onSkip }: { onStart: () => void; onSkip: () => void }) {
  return (
    <div className="intro">
      <p className="kicker">Welcome to</p>
      <h1>Forkcast</h1>
      <p className="intro-tagline">Cook what you have, eat what fits your goal. It works in three steps.</p>

      <ol className="intro-steps">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <span className="intro-num" aria-hidden="true">
              {i + 1}
            </span>
            <div>
              <strong>{s.title}</strong>
              <p>{s.text}</p>
            </div>
          </li>
        ))}
      </ol>

      {isDemo() && (
        // D57: what this demo kitchen starts with, said before anyone wonders.
        <p className="intro-note intro-demo">
          This demo kitchen starts with 25 ingredients and two dishes cooked earlier this week, so recipes can be
          matched to a taste. Your day starts empty, and you set up your own profile next.
        </p>
      )}
      <button className="btn" onClick={onStart}>
        Get started
      </button>
      <button className="intro-skip" onClick={onSkip}>
        Skip for now
      </button>
      <p className="intro-note">Every screen has a <span className="help-chip" aria-hidden="true">?</span> that explains it again.</p>
    </div>
  );
}
