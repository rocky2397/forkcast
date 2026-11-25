import { useState } from "react";
import { api, type RecentMeal } from "../api";
import { StarIcon } from "../Icons";

const fmt = (n: number) => Math.round(n).toLocaleString("en");
const SHOWN = 4;

/** D50: meals typed or built before, to log again in one tap. Starred ones stay on top.
 *  D73: or to put together into a new meal of your own ("Add to meal"). */
export function LogAgain({
  meals,
  onChange,
  onAddToMeal,
  loggedAt,
}: {
  meals: RecentMeal[];
  onChange: () => Promise<unknown>;
  onAddToMeal: (meal: RecentMeal) => void;
  /** D56: log on an earlier day, at noon. */
  loggedAt?: string;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [all, setAll] = useState(false);
  if (meals.length === 0) return null;
  const shown = all ? meals : meals.slice(0, SHOWN);

  async function run(id: number, act: () => Promise<unknown>) {
    if (busy !== null) return;
    setBusy(id);
    try {
      await act();
      await onChange();
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="again" aria-labelledby="again-title">
      <h3 id="again-title" className="again-title">Log again</h3>
      <ul className="again-list">
        {shown.map((m) => (
          <li key={m.meal_id} className="again-item">
            <button
              type="button"
              className={m.favourite ? "star star-on" : "star"}
              aria-pressed={m.favourite}
              aria-label={m.favourite ? `Unstar ${m.name}` : `Star ${m.name}: keep it at the top`}
              onClick={() => run(m.meal_id, () => api.setFavourite(m.meal_id, !m.favourite))}
              disabled={busy !== null}
            >
              <StarIcon size={18} />
            </button>
            <span className="again-name">
              {m.name}
              <span className="again-kcal">{fmt(m.calories)} kcal</span>
            </span>
            <span className="again-actions">
              <button
                type="button"
                className="pill"
                aria-label={`Log ${m.name} again`}
                onClick={() => run(m.meal_id, () => api.logAgain(m.meal_id, loggedAt))}
                disabled={busy !== null}
              >
                {busy === m.meal_id ? "…" : "Log"}
              </button>
              <button
                type="button"
                className="link-button again-add"
                aria-label={`Add ${m.name} to a new meal`}
                onClick={() => onAddToMeal(m)}
                disabled={busy !== null}
              >
                Add to meal
              </button>
            </span>
          </li>
        ))}
      </ul>
      {meals.length > SHOWN && (
        <button type="button" className="link-button" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show ${meals.length - SHOWN} more`}
        </button>
      )}
    </section>
  );
}
