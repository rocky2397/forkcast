import { useEffect, useState } from "react";
import { api, type ListItem } from "../api";
import { CloseIcon } from "../Icons";
import { errorText } from "../LoadError";

const WHY: Record<ListItem["reason"], string> = {
  ran_out: "Ran out",
  missing: "For a recipe",
  worth_buying: "Worth buying",
  typed: "",
};

/** D71: what to buy. Things land here from "I ate it" (what ran out), a
 *  recipe's missing ingredients, Worth buying, or typed in; ticking what you
 *  bought puts it in the kitchen and takes it off the list. */
export function ShoppingList({ onKitchenChange }: { onKitchenChange: () => void }) {
  const [items, setItems] = useState<ListItem[] | null>(null);
  const [got, setGot] = useState<Set<string>>(new Set());
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .list()
      .then((r) => setItems(r.items))
      .catch((e) => setError(errorText(e)));
  }, []);

  async function run(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const add = () =>
    run(async () => {
      const parts = typed.split(",").map((s) => s.trim()).filter(Boolean);
      if (!parts.length) return;
      const r = await api.addToList(parts, "typed");
      setItems(r.items);
      setTyped("");
      setNote(
        [
          r.already.length ? `Already on the list: ${r.already.join(", ")}.` : "",
          r.unknown.length ? `Couldn't match ${r.unknown.map((u) => `“${u}”`).join(", ")}.` : "",
        ]
          .filter(Boolean)
          .join(" ") || null,
      );
    });

  const bought = () =>
    run(async () => {
      const r = await api.boughtFromList([...got]);
      setItems(r.items);
      setGot(new Set());
      setNote(r.moved.length ? `In your kitchen now: ${r.moved.join(", ")}.` : null);
      onKitchenChange();
    });

  const remove = (c: string) =>
    run(async () => {
      setItems((await api.removeFromList(c)).items);
      const next = new Set(got);
      next.delete(c);
      setGot(next);
    });

  const toggle = (c: string) => {
    const next = new Set(got);
    if (next.has(c)) next.delete(c);
    else next.add(c);
    setGot(next);
  };

  return (
    <section className="buy-list" aria-labelledby="buy-list-title">
      <h2 id="buy-list-title" className="group-label">
        Shopping list
      </h2>
      {items && items.length === 0 && (
        <p className="scan-hint">
          Nothing on it yet. What ran out after “I ate it”, what a recipe is missing and Worth buying picks can go
          here, or add something below.
        </p>
      )}
      {items && items.length > 0 && (
        <>
          <p className="scan-hint">Tick what you bought; it goes into your kitchen.</p>
          <ul className="scan-list">
            {items.map((it) => (
              <li key={it.canonical}>
                <label>
                  <input type="checkbox" checked={got.has(it.canonical)} onChange={() => toggle(it.canonical)} />
                  <span className="scan-name">
                    {it.name}
                    {it.in_kitchen && <span className="scan-why">Already in your kitchen</span>}
                  </span>
                  {WHY[it.reason] && <span className="scan-qty">{WHY[it.reason]}</span>}
                </label>
                <button
                  className="remove"
                  onClick={() => remove(it.canonical)}
                  disabled={busy}
                  aria-label={`Take ${it.name} off the list`}
                >
                  <CloseIcon size={18} />
                </button>
              </li>
            ))}
          </ul>
          {got.size > 0 && (
            <button className="btn buy-done" onClick={bought} disabled={busy}>
              Put {got.size} in your kitchen
            </button>
          )}
        </>
      )}
      <form
        className="add-row"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        <input
          aria-label="Add to the shopping list"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="e.g. milk, Haferflocken"
        />
        <button type="submit" className="btn secondary" disabled={busy || !typed.trim()}>
          Add to list
        </button>
      </form>
      {note && (
        <p className="scan-hint" role="status">
          {note}
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
