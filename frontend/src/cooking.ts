/** D70: the recipe you said you're cooking, pinned until you say you ate it.
 *  Kept on this device only, like the guides, and forgotten after 12 hours. */
const KEY = "forkcast.cooking.v1";
const FOR_MS = 12 * 60 * 60 * 1000;
export const COOKING_EVENT = "forkcast:cooking";

export type Cooking = { id: number; name: string; since: number };

export function cookingNow(): Cooking | null {
  try {
    const c = JSON.parse(localStorage.getItem(KEY) ?? "null") as Cooking | null;
    return c && Date.now() - c.since < FOR_MS ? c : null;
  } catch {
    return null; // private mode: no pin, which is harmless
  }
}

function changed() {
  window.dispatchEvent(new Event(COOKING_EVENT));
}

export function startCooking(id: number, name: string) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ id, name, since: Date.now() }));
  } catch {
    /* private mode */
  }
  changed();
}

/** Unpins `id`, or whatever is pinned when no id is given. */
export function stopCooking(id?: number) {
  try {
    if (id === undefined || cookingNow()?.id === id) localStorage.removeItem(KEY);
  } catch {
    /* private mode */
  }
  changed();
}
