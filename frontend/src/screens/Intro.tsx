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
    text: "Scan your shopping or type it in. You tick a checklist first, so nothing misread is saved.",
  },
  {
    title: "See what you can cook now",
    text: "87,861 recipes, ranked by what's in your kitchen. Coloured dots show each recipe's main ingredients, and “One away” suggests swaps from what you have.",
  },
  {
    title: "It learns your taste and your day",
    text: "Rate what you cook and “% like what you cook” follows you. Add a profile and dishes that fit the calories and macros you have left come first.",
  },
];

export function Intro({ onStart, onSkip }: { onStart: () => void; onSkip: () => void }) {
  return (
    <div className="intro">
      <p className="kicker">Welcome to</p>
      <h1>Forkcast</h1>
      <p className="intro-tagline">What should I cook next? It works in three steps.</p>

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
