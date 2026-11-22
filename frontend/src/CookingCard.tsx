import { useEffect, useState } from "react";
import { COOKING_EVENT, cookingNow } from "./cooking";

/** D70: the recipe pinned with "I'm cooking this", one tap from Today and
 *  Recipes until you say you ate it. */
export function CookingCard({ onOpen }: { onOpen: (id: number) => void }) {
  const [cooking, setCooking] = useState(cookingNow);
  useEffect(() => {
    const update = () => setCooking(cookingNow());
    window.addEventListener(COOKING_EVENT, update);
    return () => window.removeEventListener(COOKING_EVENT, update);
  }, []);
  if (!cooking) return null;
  return (
    <section className="cooking-card" aria-labelledby="cooking-now">
      <div>
        <p id="cooking-now" className="kicker">
          Cooking now
        </p>
        <p className="cooking-name">{cooking.name}</p>
      </div>
      <button className="btn secondary" onClick={() => onOpen(cooking.id)}>
        Back to the recipe
      </button>
    </section>
  );
}
