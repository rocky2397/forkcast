/** First-run walkthrough (D16).
 *
 *  Someone opening a shared link lands on an empty Today tab with no idea that
 *  the app runs on an inventory they have to stock first. Each step says what
 *  to do and what comes back, because the payoff (a ranked feed, a learned
 *  taste profile) is invisible until the kitchen has something in it.
 */
export function Intro({ onStart, onSkip }: { onStart: () => void; onSkip: () => void }) {
  return (
    <div className="intro">
      <h1>Forkcast 🍴</h1>
      <p className="intro-tagline">What should I cook next?</p>

      <ol className="intro-steps">
        <li>
          <span className="intro-icon" aria-hidden="true">
            📦
          </span>
          <div>
            <strong>Stock your kitchen</strong>
            <p>
              Photograph your shopping or type it in. You get a checklist to untick
              misreads — nothing is saved until you confirm.
            </p>
          </div>
        </li>
        <li>
          <span className="intro-icon" aria-hidden="true">
            🍳
          </span>
          <div>
            <strong>Get told what to cook</strong>
            <p>
              87,861 recipes, ranked by what you can make right now — plus stand-ins
              when you're one ingredient short.
            </p>
          </div>
        </li>
        <li>
          <span className="intro-icon" aria-hidden="true">
            👅
          </span>
          <div>
            <strong>It learns you</strong>
            <p>
              Rate what you cook and the ranking follows your taste. Log meals by
              scanning a barcode or a Nährwerttabelle to track calories and macros.
            </p>
          </div>
        </li>
      </ol>

      <button className="intro-start" onClick={onStart}>
        Start cooking
      </button>
      <button className="intro-skip" onClick={onSkip}>
        skip for now
      </button>
    </div>
  );
}
