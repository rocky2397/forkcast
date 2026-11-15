export interface InventoryItem {
  canonical: string;
  added_at: string;
  /** Food class (D28), for grouping and colouring; null when unclassed. */
  family?: string | null;
}

export interface CookableRecipe {
  id: number;
  name: string;
  minutes: number;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  ingredients_needed: number;
  ingredients_missing: number;
  missing: string[];
  subs?: Record<string, string>;
  taste_sim?: number;
  /** The cooked dish this recipe is closest to, when the match is close (D31). */
  like_your?: { id: number; name: string };
  macro_fit?: number;
  /** Main ingredients for the card's dots: staples left out, at most six. */
  signature?: { canonical: string; family: string | null; have: boolean }[];
}

/** One pick from the shopping basket. `unlocks` counts recipes completed
 *  *given the items listed before it*, so the order is a basket, not a ranking. */
export interface ShoppingItem {
  canonical: string;
  unlocks: number;
  examples: string[];
}

/** The macro furthest behind today, when a profile exists and the day isn't done. */
export interface MacroFocus {
  macro: "protein_g" | "carbs_g" | "fat_g";
  grams: number;
}

export interface TasteProfile {
  meals_logged: number;
  profile: { ingredient: string; similarity: number }[];
}

export interface ScanProposal {
  seen: string;
  quantity: string | null;
  confidence: number;
  canonical: string | null;
}

export interface Profile {
  sex: "m" | "f";
  age: number;
  height_cm: number;
  weight_kg: number;
  activity: "sedentary" | "light" | "moderate" | "active" | "very_active";
  goal: "cut" | "maintain" | "bulk";
}

export interface Targets {
  calories: number;
  protein_g: number;
  fat_g: number;
  carbs_g: number;
}

export interface DayMeal {
  id: number;
  recipe_id: number | null;
  logged_at: string;
  liked: 0 | 1 | null;
  name: string | null;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
}

export interface DaySummary {
  date: string;
  meals: DayMeal[];
  totals: { calories: number; protein_g: number; carbs_g: number; fat_g: number };
  targets: Targets | null;
}

export interface Product {
  barcode: string | null;
  name: string | null;
  brand: string | null;
  calories_100g: number | null;
  protein_g_100g: number | null;
  carbs_g_100g: number | null;
  fat_g_100g: number | null;
  source: "openfoodfacts" | "label";
}

export interface RecipeDetail {
  id: number;
  name: string;
  minutes: number;
  description: string | null;
  steps: string[];
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  ingredients: {
    raw: string;
    canonical: string | null;
    in_inventory: boolean;
    staple: boolean;
    sub: string | null;
  }[];
}

// Set by App so an expired or missing session sends the whole UI back to the
// login screen instead of surfacing "401" inside whichever tab made the call.
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

// Public demo (D32): the server gives each visitor their own kitchen and names
// it in this header. Sending it back keeps every request in that kitchen. Kept
// in memory too, so a browser that refuses localStorage still has one kitchen
// per visit.
const KITCHEN_HEADER = "X-Forkcast-Kitchen";
const KITCHEN_KEY = "forkcast.demo.kitchen";
let kitchenId: string | null = (() => {
  try {
    return localStorage.getItem(KITCHEN_KEY);
  } catch {
    return null;
  }
})();
let demo = false;
let usageStats = false;
/** True on the public demo; known once api.session() has answered. */
export const isDemo = () => demo;
/** True when the demo keeps anonymous usage totals (D33), shown at /stats. */
export const keepsStats = () => usageStats;

function withKitchen(init?: RequestInit): RequestInit | undefined {
  if (!kitchenId) return init;
  const headers = new Headers(init?.headers);
  headers.set(KITCHEN_HEADER, kitchenId);
  return { ...init, headers };
}

function rememberKitchen(res: Response) {
  const id = res.headers.get(KITCHEN_HEADER);
  if (!id || id === kitchenId) return;
  kitchenId = id;
  try {
    localStorage.setItem(KITCHEN_KEY, id);
  } catch {
    // Memory only: the kitchen lasts as long as this tab.
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, withKitchen(init));
  rememberKitchen(res);
  if (res.status === 401) {
    onUnauthorized?.();
    throw new Error("session expired");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  session: async () => {
    const s = await req<{ demo?: boolean; stats?: boolean; required: boolean; authenticated: boolean }>(
      "/api/session",
    );
    demo = Boolean(s.demo);
    usageStats = Boolean(s.stats);
    return s;
  },
  // Deliberately not routed through req(): a wrong password is also a 401, and
  // it must not trip the session-expired handler.
  login: async (password: string) => {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
    }
    return res.json() as Promise<{ authenticated: boolean }>;
  },
  logout: () => req<{ authenticated: boolean }>("/api/logout", { method: "POST" }),
  inventory: () => req<{ items: InventoryItem[] }>("/api/inventory"),
  addInventory: (items: string[]) =>
    req<{ added: string[]; unknown: string[] }>("/api/inventory", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ items }),
    }),
  removeInventory: (name: string) =>
    req<{ removed: string }>(`/api/inventory/${encodeURIComponent(name)}`, { method: "DELETE" }),
  normalize: (q: string) =>
    req<{ query: string; canonical: string | null }>(`/api/normalize?q=${encodeURIComponent(q)}`),
  /** `exact`: only recipes missing exactly `maxMissing` (the feed's tabs). */
  cookable: (maxMissing: number, exact = false) =>
    req<{
      count: number;
      personalized: boolean;
      macro_focus: MacroFocus | null;
      recipes: CookableRecipe[];
    }>(`/api/recipes/cookable?max_missing=${maxMissing}&min_missing=${exact ? maxMissing : 0}&limit=30`),
  taste: () => req<TasteProfile>("/api/taste"),
  shopping: () =>
    req<{
      personalized: boolean;
      unlocks_total: number;
      partial_scan: boolean;
      items: ShoppingItem[];
    }>("/api/shopping"),
  scanPhoto: (file: File) => {
    const form = new FormData();
    form.append("photo", file);
    return req<{ proposals: ScanProposal[] }>("/api/vision/scan", { method: "POST", body: form });
  },
  profile: () => req<{ profile: Profile | null; targets: Targets | null }>("/api/profile"),
  saveProfile: (p: Profile) =>
    req<{ profile: Profile; targets: Targets }>("/api/profile", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(p),
    }),
  day: (date?: string) => req<DaySummary>(date ? `/api/day?date=${date}` : "/api/day"),
  addMeal: (meal: { name: string; calories: number; protein_g: number; carbs_g: number; fat_g: number }) =>
    req<{ logged: boolean; meal_log_id: number }>("/api/meals", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(meal),
    }),
  deleteMeal: (id: number) => req<{ deleted: number }>(`/api/meals/${id}`, { method: "DELETE" }),
  rateMeal: (id: number, liked: boolean | null) =>
    req<{ id: number; liked: boolean | null }>(`/api/meals/${id}/rate`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ liked }),
    }),
  barcodeLookup: (code: string) =>
    req<{ product: Product }>(`/api/nutrition/barcode/${encodeURIComponent(code)}`),
  scanProduct: (file: File) => {
    const form = new FormData();
    form.append("photo", file);
    return req<{ product: Product }>("/api/nutrition/scan", { method: "POST", body: form });
  },
  recipe: (id: number) => req<RecipeDetail>(`/api/recipes/${id}`),
  logCooked: (id: number, usedUp: string[] = []) =>
    req<{ logged: boolean; meal_log_id: number; removed: string[] }>(`/api/recipes/${id}/cooked`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ used_up: usedUp }),
    }),
};

/** "black_pepper" -> "black pepper" for display */
export const pretty = (canonical: string) => canonical.replaceAll("_", " ");
