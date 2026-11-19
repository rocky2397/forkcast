import { useState } from "react";
import { api, type Food, type FoodLookup } from "../api";
import { CloseIcon } from "../Icons";
import { cap, formOf, partTotals, totalsOf, type Part } from "../mealParts";

const fmt = (n: number) => Math.round(n).toLocaleString("en");

const PRODUCT_SOURCE = {
  openfoodfacts: "from Open Food Facts",
  label: "read from the label",
  saved: "saved from your earlier scan",
} as const;

/** A whole piece where the USDA has one (1 medium banana, 1 large egg), else 100 g. */
function newPart(food: Food): Part {
  const piece = food.portions.findIndex((p) => /^1 (medium|large)$/.test(p.label));
  return piece >= 0 ? { food, amount: "1", unit: piece, cooked: false } : { food, amount: "100", unit: -1, cooked: false };
}

export function MealBuilder({ parts, onChange }: { parts: Part[]; onChange: (parts: Part[]) => void }) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [miss, setMiss] = useState<FoodLookup | null>(null);

  async function add(q: string) {
    const text = q.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      const res = await api.findFood(text);
      if (res.food) {
        onChange([...parts, newPart(res.food)]);
        setQuery("");
        setMiss(null);
      } else {
        setMiss(res);
      }
    } catch (e) {
      setMiss({ query: text, canonical: null, food: null, suggestions: [] });
      console.warn(e);
    } finally {
      setBusy(false);
    }
  }

  function update(i: number, change: Partial<Part>) {
    onChange(parts.map((p, j) => (j === i ? { ...p, ...change } : p)));
  }

  const total = totalsOf(parts);

  return (
    <div className="builder">
      <label className="field" htmlFor="builder-query">
        Add an ingredient
      </label>
      <div className="add-row builder-add">
        <input
          id="builder-query"
          placeholder="e.g. banana, Haferflocken, rice"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            // Enter adds the ingredient; it mustn't log the meal around it.
            if (e.key === "Enter") {
              e.preventDefault();
              add(query);
            }
          }}
        />
        <button type="button" onClick={() => add(query)} disabled={busy || !query.trim()}>
          Add
        </button>
      </div>
      {miss && (
        <p className="feedback warning" role="status">
          {miss.canonical
            ? `No nutrition values for ${miss.canonical.replace(/_/g, " ")} yet. ` +
              (parts.length > 0
                ? "Log it as a meal of its own: scan its barcode or type its numbers."
                : "Scan its barcode or type the meal's numbers below instead.")
            : `Couldn't find "${miss.query}". Try another word, in English or German.`}
          {miss.suggestions.length > 0 && (
            <>
              {" "}Did you mean{" "}
              {miss.suggestions.map((s, i) => (
                <span key={s.canonical}>
                  {i > 0 && (i === miss.suggestions.length - 1 ? " or " : ", ")}
                  <button type="button" className="link-button" onClick={() => add(s.name)}>
                    {s.name}
                  </button>
                </span>
              ))}
              ?
            </>
          )}
        </p>
      )}

      {parts.length > 0 && (
        <ul className="builder-list">
          {parts.map((p, i) => {
            const form = formOf(p);
            const t = partTotals(p);
            return (
              <li key={i} className="builder-item">
                <div className="builder-head">
                  <strong>{p.product ? p.food.name : cap(p.food.name)}</strong>
                  <span className="builder-kcal">{fmt(t.calories)} kcal</span>
                  <button
                    type="button"
                    className="remove"
                    onClick={() => onChange(parts.filter((_, j) => j !== i))}
                    aria-label={`Remove ${p.food.name}`}
                  >
                    <CloseIcon size={16} />
                  </button>
                </div>
                <div className="builder-amount">
                  <input
                    type="number"
                    inputMode="decimal"
                    min="0"
                    step="any"
                    aria-label={`How much ${p.food.name}`}
                    value={p.amount}
                    onChange={(e) => update(i, { amount: e.target.value })}
                  />
                  <select
                    aria-label={`Unit for ${p.food.name}`}
                    value={p.unit}
                    onChange={(e) => update(i, { unit: Number(e.target.value) })}
                  >
                    <option value={-1}>g</option>
                    {form.portions.map((o, k) => (
                      <option key={o.label} value={k}>
                        × {o.label} ({fmt(o.grams)} g)
                      </option>
                    ))}
                  </select>
                  {p.food.cooked && (
                    <select
                      aria-label={`Weighed raw or cooked: ${p.food.name}`}
                      value={p.cooked ? "cooked" : "raw"}
                      onChange={(e) => update(i, { cooked: e.target.value === "cooked", unit: -1 })}
                    >
                      <option value="raw">weighed dry or raw</option>
                      <option value="cooked">weighed cooked</option>
                    </select>
                  )}
                </div>
                <span className="builder-source">
                  {p.product ? (
                    `Per 100 g ${PRODUCT_SOURCE[p.product.source]}`
                  ) : (
                    <>
                      USDA: {form.usda}
                      {!p.food.checked && " · matched by name only, check it's the right food"}
                    </>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {parts.length > 0 && (
        <p className="builder-total">
          Together: {fmt(total.calories)} kcal · {fmt(total.protein_g)} g protein · {fmt(total.carbs_g)} g carbs ·{" "}
          {fmt(total.fat_g)} g fat
        </p>
      )}
    </div>
  );
}
