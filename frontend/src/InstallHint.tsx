import { useEffect, useState } from "react";
import { install, installWay, onInstallChange } from "./install";

const HIDDEN = "forkcast.installhint.v1";

/** D73: a small card saying Forkcast can live on the home screen, with the
 *  steps this phone needs. Hidden once installed, or for good with "Hide this". */
export function InstallHint() {
  const [, redraw] = useState(0);
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(HIDDEN) === "1";
    } catch {
      return false; // private mode: it shows, and "Hide this" hides it until reload
    }
  });
  useEffect(() => onInstallChange(() => redraw((n) => n + 1)), []);

  const way = installWay();
  if (hidden || !way) return null;

  function hide() {
    try {
      localStorage.setItem(HIDDEN, "1");
    } catch {
      /* private mode */
    }
    setHidden(true);
  }

  return (
    <aside className="install-hint" aria-labelledby="install-title">
      <h2 id="install-title" className="group-label">
        Keep Forkcast on your home screen
      </h2>
      {way === "offer" && <p>Install it and it opens full screen, like any app, with no browser around it.</p>}
      {way === "ios" && (
        <p>
          Tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>. It then opens full screen, like any
          app.
        </p>
      )}
      {way === "frame" && (
        <p>
          This page shows Forkcast inside another site, where it can't be installed. Open it on its own page, then
          add it to your home screen from there. A kitchen started here may not come along.
        </p>
      )}
      <div className="install-actions">
        {way === "offer" && (
          <button className="btn" onClick={install}>
            Install Forkcast
          </button>
        )}
        {way === "frame" && (
          <a className="btn" href={window.location.href} target="_blank" rel="noopener noreferrer">
            Open Forkcast on its own
          </a>
        )}
        <button className="link" onClick={hide}>
          Hide this
        </button>
      </div>
    </aside>
  );
}
