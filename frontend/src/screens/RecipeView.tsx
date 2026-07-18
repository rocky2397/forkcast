import { useEffect, useState } from "react";
import { api, pretty, type RecipeDetail } from "../api";

export function RecipeView({ id, onBack }: { id: number; onBack: () => void }) {
  const [recipe, setRecipe] = useState<RecipeDetail | null>(null);
  const [cooked, setCooked] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.recipe(id).then(setRecipe);
  }, [id]);

  async function logCooked() {
    if (busy || cooked) return;
    setBusy(true);
    try {
      await api.logCooked(id);
      setCooked(true);
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
          </li>
        ))}
      </ul>

      <h3>Steps</h3>
      <ol className="steps">
        {recipe.steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>

      <button className="cooked" onClick={logCooked} disabled={busy || cooked}>
        {cooked ? "Logged ✓ — enjoy!" : "I cooked this"}
      </button>
    </div>
  );
}
