import { useState } from "react";
import { api, pretty, type ScanProposal } from "../api";

/** What the photo reader said, when it isn't just the ingredient's own name
 *  (D38): "orange juice" became Fruit juice. Lets a wrong match show. */
function saidOtherwise(seen: string, canonical: string): boolean {
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z]/g, "").replace(/(es|s)$/, "");
  return norm(seen) !== norm(canonical.replace(/_/g, " "));
}

/** The checklist after a grocery photo (D8): a cheap vision model plus a
 *  mandatory human check, so nothing misread lands in the kitchen. */
export function ScanConfirm({
  proposals,
  onDone,
}: {
  proposals: ScanProposal[];
  onDone: () => void;
}) {
  // recognized items pre-checked; unrecognized shown unchecked for editing awareness
  const [checked, setChecked] = useState<boolean[]>(proposals.map((p) => p.canonical !== null));
  const [busy, setBusy] = useState(false);

  const count = checked.filter((c, i) => c && proposals[i].canonical).length;

  async function confirm() {
    setBusy(true);
    try {
      const names = proposals.filter((p, i) => checked[i] && p.canonical).map((p) => p.canonical!);
      if (names.length) await api.addInventory(names);
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen narrow">
      <p className="kicker">Scan</p>
      <h1 className="display">Found in your photo</h1>
      <p className="lead">
        Untick anything that's wrong. Nothing is added to your kitchen until you confirm.
      </p>
      <ul className="scan-list">
        {proposals.map((p, i) => (
          <li key={i} className={p.canonical ? "" : "unknown"}>
            <label>
              <input
                type="checkbox"
                checked={checked[i]}
                disabled={!p.canonical}
                onChange={() => setChecked(checked.map((c, j) => (j === i ? !c : c)))}
              />
              <span className="scan-name">
                {p.canonical ? pretty(p.canonical) : p.seen}
                {p.canonical && saidOtherwise(p.seen, p.canonical) && (
                  <span className="scan-why">Seen as “{p.seen}”</span>
                )}
                {!p.canonical && <span className="scan-why">Not in the ingredient list, so it can't be added.</span>}
              </span>
              {p.quantity && <span className="scan-qty">{p.quantity}</span>}
              {p.canonical && (
                <span className="scan-conf" title="How sure the photo reader is">
                  {Math.round(p.confidence * 100)}% sure
                </span>
              )}
            </label>
          </li>
        ))}
      </ul>
      <div className="form-actions">
        <button className="btn" onClick={confirm} disabled={busy || count === 0}>
          Add {count} {count === 1 ? "item" : "items"}
        </button>
        <button className="btn secondary" onClick={onDone} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}
