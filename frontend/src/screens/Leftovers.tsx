import { useEffect, useState } from "react";
import { api, type Leftover } from "../api";
import { CloseIcon } from "../Icons";
import { errorText } from "../LoadError";

const fmt = (n: number) => Math.round(n).toLocaleString("en");
const portions = (n: number) => `${n === 0.5 ? "½" : n === 1.5 ? "1½" : Math.round(n * 100) / 100} portion${n === 1 ? "" : "s"}`;

/** "today", "yesterday", "on Monday", "on 12 Nov". made_at is UTC as SQLite writes it. */
function madeWhen(made_at: string): string {
  const made = new Date(made_at.replace(" ", "T") + "Z");
  if (Number.isNaN(made.getTime())) return "";
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const ago = Math.round((day(new Date()) - day(made)) / 86_400_000);
  if (ago <= 0) return "today";
  if (ago === 1) return "yesterday";
  if (ago < 7) return `on ${made.toLocaleDateString("en", { weekday: "long" })}`;
  return `on ${made.toLocaleDateString("en", { day: "numeric", month: "short" })}`;
}

/** D75: what's left of pots cooked ahead. On Cook, what's ready to eat; in the
 *  Kitchen, also the freezer and "It's gone". Eating a portion logs it as a
 *  share of the pot (D74) and counts down; Undo puts it back. */
export function Leftovers({
  where,
  onEaten,
}: {
  where: "cook" | "kitchen";
  /** The day's numbers changed. */
  onEaten?: () => void;
}) {
  const [items, setItems] = useState<Leftover[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The last portion eaten, for Undo.
  const [ate, setAte] = useState<{ item: Leftover; mealId: number; left: number } | null>(null);

  const load = () =>
    api
      .leftovers()
      .then((r) => setItems(r.items))
      .catch((e) => setError(errorText(e)));
  useEffect(() => {
    load();
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

  const eat = (item: Leftover) =>
    run(async () => {
      const r = await api.eatLeftover(item.id);
      setAte({ item, mealId: r.meal_log_id, left: r.portions_left });
      await load();
      onEaten?.();
    });

  const undo = () =>
    run(async () => {
      if (!ate) return;
      await api.deleteMeal(ate.mealId);
      await api.changeLeftover(ate.item.id, { portions_left: ate.item.portions_left });
      setAte(null);
      await load();
      onEaten?.();
    });

  const freeze = (item: Leftover, frozen: boolean) =>
    run(async () => setItems((await api.changeLeftover(item.id, { frozen })).items));

  const gone = (item: Leftover) =>
    run(async () => {
      setItems((await api.removeLeftover(item.id)).items);
      if (ate?.item.id === item.id) setAte(null);
    });

  if (!items || (items.length === 0 && !ate && !error)) return null;

  return (
    <section className={`leftovers leftovers-${where}`} aria-labelledby={`leftovers-${where}`}>
      <h2 id={`leftovers-${where}`} className="group-label">
        {where === "cook" ? "Cooked and ready" : "Cooked"}
      </h2>
      <ul className="leftover-list">
        {items.map((it) => (
          <li key={it.id} className={it.stale ? "leftover stale" : "leftover"}>
            <div className="leftover-main">
              <strong>{it.name}</strong>
              <span className="leftover-meta">
                {portions(it.portions_left)} left, made {madeWhen(it.made_at)}
                {it.frozen ? " · in the freezer" : ""} · {fmt(it.per_portion.calories)} kcal a portion
              </span>
              {it.stale && (
                <span className="leftover-ask">
                  In the fridge for {Math.floor(it.fridge_days ?? 0)} days: cooked food keeps three to four. Still good?
                </span>
              )}
            </div>
            <div className="leftover-actions">
              <button className="pill" onClick={() => eat(it)} disabled={busy} aria-label={`Eat a portion of ${it.name}`}>
                Eat a portion
              </button>
              {where === "kitchen" && (
                <button className="link-button" onClick={() => freeze(it, !it.frozen)} disabled={busy}>
                  {it.frozen ? "Back to the fridge" : "Move to the freezer"}
                </button>
              )}
              {(where === "kitchen" || it.stale) && (
                <button
                  className={where === "kitchen" ? "remove" : "link-button"}
                  onClick={() => gone(it)}
                  disabled={busy}
                  aria-label={`${it.name} is gone`}
                >
                  {where === "kitchen" ? <CloseIcon size={18} /> : "It's gone"}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {ate && (
        <p className="leftover-note" role="status">
          Logged a portion of {ate.item.name}. {ate.left > 0 ? `${portions(ate.left)} left.` : "That was the last one."}{" "}
          <button className="link-button" onClick={undo} disabled={busy}>
            Undo
          </button>
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
