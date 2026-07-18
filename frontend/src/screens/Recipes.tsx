import { useEffect, useState } from "react";
import { api, pretty, type CookableRecipe, type TasteProfile } from "../api";
import { RecipeView } from "./RecipeView";

export function Recipes() {
  const [maxMissing, setMaxMissing] = useState(0);
  const [recipes, setRecipes] = useState<CookableRecipe[]>([]);
  const [tasteInfo, setTasteInfo] = useState<TasteProfile | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.taste().then(setTasteInfo).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .cookable(maxMissing)
      .then((r) => setRecipes(r.recipes))
      .finally(() => setLoading(false));
  }, [maxMissing]);

  if (openId !== null) {
    return <RecipeView id={openId} onBack={() => setOpenId(null)} />;
  }

  return (
    <div className="screen">
      <div className="segmented">
        {[0, 1, 2].map((n) => (
          <button
            key={n}
            className={n === maxMissing ? "active" : ""}
            onClick={() => setMaxMissing(n)}
          >
            {n === 0 ? "Cookable now" : `Missing ≤ ${n}`}
          </button>
        ))}
      </div>
      {tasteInfo && tasteInfo.meals_logged > 0 && (
        <p className="taste-note">
          Learning from {tasteInfo.meals_logged} logged {tasteInfo.meals_logged === 1 ? "cook" : "cooks"} — your
          kitchen leans {tasteInfo.profile.slice(0, 3).map((p) => pretty(p.ingredient)).join(", ")}.
        </p>
      )}
      {loading && <p className="empty">Searching 87,861 recipes…</p>}
      {!loading && recipes.length === 0 && (
        <p className="empty">Nothing cookable yet — add more ingredients to your inventory.</p>
      )}
      <ul className="recipe-list">
        {recipes.map((r) => (
          <li key={r.id} onClick={() => setOpenId(r.id)}>
            <div className="recipe-head">
              <strong>{r.name}</strong>
              <span className="minutes">
                {r.taste_sim != null && r.taste_sim > 0 && (
                  <span className="match">♥ {Math.round(r.taste_sim * 100)}%</span>
                )}{" "}
                {r.minutes} min
              </span>
            </div>
            <div className="macros">
              {r.calories != null && <span>{Math.round(r.calories)} kcal</span>}
              {r.protein_g != null && <span>P {Math.round(r.protein_g)}g</span>}
              {r.carbs_g != null && <span>C {Math.round(r.carbs_g)}g</span>}
              {r.fat_g != null && <span>F {Math.round(r.fat_g)}g</span>}
            </div>
            {r.missing.length > 0 && (
              <div className="missing-chips">
                {r.missing.map((m) => (
                  <span key={m} className="chip">
                    needs {pretty(m)}
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
