import { useMemo, useState } from "react";
import { api, pretty, type InventoryItem, type ScanProposal } from "../api";
import { kitchenGroup } from "../format";
import { errorText } from "../LoadError";

/** What the photo reader said, when it isn't just the ingredient's own name
 *  (D38): "orange juice" became Fruit juice. Lets a wrong match show. */
function saidOtherwise(seen: string, canonical: string): boolean {
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z]/g, "").replace(/(es|s)$/, "");
  return norm(seen) !== norm(canonical.replace(/_/g, " "));
}

/** Groups a fridge photo can show: a kitchen item from these that the photo
 *  didn't find "looks gone" (D69). Pasta or spices aren't expected in a photo. */
const FRIDGE_GROUPS = new Set(["Vegetables", "Fruit", "Meat, fish & eggs", "Dairy & cheese"]);

/** D69: cupboard food a fridge photo can't see, offered as one-tap chips
 *  (ingredient, how the chip reads). Salt, oil, butter, flour and sugar are
 *  assumed anyway. */
const CUPBOARD: [string, string][] = [
  ["pasta", "Pasta"], ["rice", "Rice"], ["oat", "Oats"], ["lentil", "Lentils"],
  ["chickpea", "Chickpeas"], ["tuna", "Tuna"], ["coconut_milk", "Coconut milk"], ["soy_sauce", "Soy sauce"],
];

export type ScanOutcome = {
  added: string[];
  already: string[];
  unknown: string[];
  suggestions: Record<string, string[]>;
  removed: string[];
};

/** The checklist after a photo (D8, D69). The model's "Confident" items are
 *  ticked, "Not sure" ones aren't (Test 8: below 70% sure it is often wrong),
 *  and kitchen items the photo didn't show are offered for removal, never
 *  removed on their own: a photo misses things just out of shot. */
export function ScanConfirm({
  proposals,
  kitchen,
  photo,
  credit,
  compare = true,
  onDone,
}: {
  proposals: ScanProposal[];
  kitchen: InventoryItem[];
  photo?: string | null;
  credit?: string | null;
  /** False for the demo's sample fridge: it isn't your fridge, so nothing in
   *  your kitchen "looks gone" because of it. */
  compare?: boolean;
  onDone: (outcome: ScanOutcome | null) => void;
}) {
  const have = useMemo(() => new Set(compare ? kitchen.map((k) => k.canonical) : []), [kitchen, compare]);
  const seen = useMemo(() => new Set(proposals.map((p) => p.canonical).filter(Boolean)), [proposals]);
  const fresh = proposals.filter((p) => !p.canonical || !have.has(p.canonical));
  const sure = fresh.filter((p) => p.canonical && (p.sure ?? true));
  const unsure = fresh.filter((p) => !p.canonical || !(p.sure ?? true));
  const stillThere = proposals.filter((p) => p.canonical && have.has(p.canonical));
  const gone = compare
    ? kitchen.filter((k) => FRIDGE_GROUPS.has(kitchenGroup(k.canonical, k.family)) && !seen.has(k.canonical))
    : [];
  const owned = new Set(kitchen.map((k) => k.canonical));
  const chips = CUPBOARD.filter(([c]) => !owned.has(c) && !seen.has(c));

  // Your taps, on top of the model's sure / not sure. Kept apart from the
  // default so the kitchen arriving after the scan can't leave a stale tick.
  const [picked, setPicked] = useState<Map<string, boolean>>(new Map());
  const add = new Set(
    fresh
      .filter((p) => p.canonical && (picked.get(p.canonical) ?? (p.sure ?? true)))
      .map((p) => p.canonical!),
  );
  const [remove, setRemove] = useState<Set<string>>(new Set());
  const [extra, setExtra] = useState<string[]>([]);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, name: string) => {
    const next = new Set(set);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setter(next);
  };
  const addExtra = (name: string) => {
    const n = name.trim();
    if (n && !extra.includes(n)) setExtra([...extra, n]);
  };
  const typedExtras = extra.filter((x) => !CUPBOARD.some(([, label]) => label === x));

  const adding = add.size + extra.length;
  const summary = [adding && `add ${adding}`, remove.size && `remove ${remove.size}`].filter(Boolean).join(", ");

  async function confirm() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const names = [...add, ...extra];
      const res = names.length
        ? await api.addInventory(names)
        : { added: [], added_names: [], already: [], unknown: [], suggestions: {} };
      for (const name of remove) await api.removeInventory(name);
      onDone({
        added: res.added_names ?? res.added.map(pretty),
        already: res.already ?? [],
        unknown: res.unknown,
        suggestions: res.suggestions ?? {},
        removed: [...remove].map(pretty),
      });
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }

  const row = (p: ScanProposal, i: number) => (
    <li key={`${p.canonical ?? p.seen}-${i}`} className={p.canonical ? "" : "unknown"}>
      <label>
        <input
          type="checkbox"
          checked={!!p.canonical && add.has(p.canonical)}
          disabled={!p.canonical}
          onChange={() => p.canonical && setPicked(new Map(picked).set(p.canonical, !add.has(p.canonical)))}
        />
        <span className="scan-name">
          {p.canonical ? pretty(p.canonical) : p.seen}
          {p.canonical && saidOtherwise(p.seen, p.canonical) && <span className="scan-why">Seen as “{p.seen}”</span>}
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
  );

  return (
    <div className="screen narrow">
      <p className="kicker">Scan</p>
      <h1 className="display">Found in your photo</h1>
      <p className="lead">
        {compare
          ? "Check the list against your fridge. Nothing changes in your kitchen until you confirm."
          : "A scan of someone else's fridge, kept as the reader saw it, to show how scanning works. Check it against the photo: what you confirm goes into your demo kitchen."}
      </p>

      {photo && (
        <figure className="scan-photo">
          <img src={photo} alt="The photo that was read" />
          {credit && <figcaption>{credit}</figcaption>}
        </figure>
      )}

      {sure.length > 0 && (
        <section className="scan-section" aria-labelledby="scan-sure">
          <h2 id="scan-sure" className="group-label">Confident</h2>
          <p className="scan-hint">Ticked. Untick anything that isn't there.</p>
          <ul className="scan-list">{sure.map(row)}</ul>
        </section>
      )}

      {unsure.length > 0 && (
        <section className="scan-section" aria-labelledby="scan-unsure">
          <h2 id="scan-unsure" className="group-label">Not sure</h2>
          <p className="scan-hint">Not ticked. Tick what's really there.</p>
          <ul className="scan-list">{unsure.map(row)}</ul>
        </section>
      )}

      {stillThere.length > 0 && (
        <p className="scan-hint scan-still">
          Already in your kitchen: {stillThere.map((p) => pretty(p.canonical!)).join(", ")}.
        </p>
      )}

      {gone.length > 0 && (
        <section className="scan-section" aria-labelledby="scan-gone">
          <h2 id="scan-gone" className="group-label">Looks gone</h2>
          <p className="scan-hint">
            In your kitchen but not seen in this photo. Tick what you've used up; anything just out of shot stays.
          </p>
          <ul className="scan-list">
            {gone.map((k) => (
              <li key={k.canonical}>
                <label>
                  <input
                    type="checkbox"
                    checked={remove.has(k.canonical)}
                    onChange={() => toggle(remove, setRemove, k.canonical)}
                  />
                  <span className="scan-name">{k.name ?? pretty(k.canonical)}</span>
                  <span className="scan-qty">{remove.has(k.canonical) ? "Used up" : "Still have it"}</span>
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="scan-section" aria-labelledby="scan-missed">
        <h2 id="scan-missed" className="group-label">Missed something?</h2>
        <form
          className="add-row"
          onSubmit={(e) => {
            e.preventDefault();
            addExtra(typed);
            setTyped("");
          }}
        >
          <input
            id="scan-add"
            aria-label="Add an ingredient by name"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="e.g. flour, Gouda"
          />
          <button type="submit" className="btn secondary" disabled={!typed.trim()}>
            Add
          </button>
        </form>
        {typedExtras.length > 0 && <p className="scan-hint">Also adding: {typedExtras.join(", ")}.</p>}
        {chips.length > 0 && (
          <>
            <p className="scan-hint">From the cupboard, which a fridge photo can't see:</p>
            <div className="suggest-chips">
              {chips.map(([c, label]) => {
                const on = extra.includes(label);
                return (
                  <button
                    key={c}
                    type="button"
                    className={`suggest-chip${on ? " on" : ""}`}
                    aria-pressed={on}
                    onClick={() => (on ? setExtra(extra.filter((x) => x !== label)) : addExtra(label))}
                  >
                    {on ? "✓" : "+"} {label}
                  </button>
                );
              })}
            </div>
          </>
        )}
      </section>

      {error && <p className="error">{error}</p>}
      <div className="form-actions">
        <button className="btn" onClick={confirm} disabled={busy || (adding === 0 && remove.size === 0)}>
          {summary ? `Update kitchen: ${summary}` : "Nothing to change"}
        </button>
        <button className="btn secondary" onClick={() => onDone(null)} disabled={busy}>
          Cancel
        </button>
      </div>
    </div>
  );
}
