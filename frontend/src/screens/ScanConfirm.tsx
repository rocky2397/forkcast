import { useState } from "react";
import { api, pretty, type ScanProposal } from "../api";

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

  async function confirm() {
    setBusy(true);
    try {
      const names = proposals
        .filter((p, i) => checked[i] && p.canonical)
        .map((p) => p.canonical!) ;
      if (names.length) await api.addInventory(names);
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen">
      <h3>Found in your photo</h3>
      <p className="feedback">Uncheck anything that's wrong, then confirm.</p>
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
                {p.canonical ? pretty(p.canonical) : `${p.seen} (not recognized)`}
              </span>
              {p.quantity && <span className="scan-qty">{p.quantity}</span>}
              <span className="scan-conf">{Math.round(p.confidence * 100)}%</span>
            </label>
          </li>
        ))}
      </ul>
      <div className="add-row">
        <button onClick={confirm} disabled={busy || !checked.some((c, i) => c && proposals[i].canonical)}>
          Add {checked.filter((c, i) => c && proposals[i].canonical).length} items
        </button>
        <button className="secondary" onClick={onDone} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}
