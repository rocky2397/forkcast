import { useEffect, useMemo, useState } from "react";
import { api, pretty, type RecipeDetail } from "../api";

export function RecipeView({ id, onBack }: { id: number; onBack: () => void }) {
  const [recipe, setRecipe] = useState<RecipeDetail | null>(null);
  const [cooked, setCooked] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [usedUp, setUsedUp] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.recipe(id).then(setRecipe);
  }, [id]);

  // What the cook could have run out of: in-inventory recipe ingredients
  // (staples excluded — nobody finishes the salt on one dish) plus any
  // suggested substitute, which is in the inventory by construction.
  const depletable = useMemo(() => {
    if (!recipe) return [];
    const seen = new Set<string>();
    const out: { canonical: string; usedFor: string | null }[] = [];
    for (const ing of recipe.ingredients) {
      const c = ing.in_inventory && !ing.staple ? ing.canonical : ing.sub;
      if (c && !seen.has(c)) {
        seen.add(c);
        out.push({ canonical: c, usedFor: ing.in_inventory ? null : ing.canonical });
      }
    }
    return out;
  }, [recipe]);

  function toggle(c: string) {
    setUsedUp((prev) => {
      const next = new Set(prev);
      next.has(c) ? next.delete(c) : next.add(c);
      return next;
    });
  }

  async function logCooked() {
    if (busy || cooked) return;
    if (!confirming && depletable.length > 0) {
      setConfirming(true);
      return;
    }
    setBusy(true);
    try {
      await api.logCooked(id, [...usedUp]);
      setCooked(true);
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }

  if (!recipe) return <p className="empty">Loading…</p>;

  return (
    <div className="screen">
      <button className="back" onClick={onBack}>
        ← back
      </button>
      <h2>{recipe.name}</h2>
      <div className="macros">
        <span>{recipe.minutes} min</span>
        {recipe.calories != null && <span>{Math.round(recipe.calories)} kcal</span>}
        {recipe.protein_g != null && <span>P {Math.round(recipe.protein_g)}g</span>}
        {recipe.carbs_g != null && <span>C {Math.round(recipe.carbs_g)}g</span>}
        {recipe.fat_g != null && <span>F {Math.round(recipe.fat_g)}g</span>}
      </div>
      {recipe.description && <p className="description">{recipe.description}</p>}

      <h3>Ingredients</h3>
      <ul className="ingredient-list">
        {recipe.ingredients.map((ing, i) => (
          <li key={i} className={ing.in_inventory ? "have" : "missing"}>
            {ing.in_inventory ? "✓" : "○"} {ing.canonical ? pretty(ing.canonical) : ing.raw}
            {ing.sub && <span className="sub-hint"> — you could use {pretty(ing.sub)}</span>}
          </li>
        ))}
      </ul>

      <h3>Steps</h3>
      <ol className="steps">
        {recipe.steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>

      {confirming && !cooked ? (
        <>
          <h3>Did anything run out?</h3>
          <p className="feedback">Check what's used up — it comes off your inventory.</p>
          <ul className="scan-list">
            {depletable.map((d) => (
              <li key={d.canonical}>
                <label>
                  <input
                    type="checkbox"
                    checked={usedUp.has(d.canonical)}
                    onChange={() => toggle(d.canonical)}
                  />
                  <span className="scan-name">
                    {pretty(d.canonical)}
                    {d.usedFor && <span className="sub-hint"> (used for {pretty(d.usedFor)})</span>}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="add-row">
            <button onClick={logCooked} disabled={busy}>
              {usedUp.size > 0 ? `Log cook — remove ${usedUp.size}` : "Log cook — nothing ran out"}
            </button>
            <button className="secondary" onClick={() => setConfirming(false)} disabled={busy}>
              Cancel
            </button>
          </div>
        </>
      ) : (
        <button className="cooked" onClick={logCooked} disabled={busy || cooked}>
          {cooked ? "Logged ✓ — enjoy!" : "I cooked this"}
        </button>
      )}
    </div>
  );
}
