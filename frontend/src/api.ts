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
  /** D39: optional goal weight and the pace to reach it. */
  goal_weight_kg?: number | null;
  pace?: "gentle" | "steady" | null;
}

/** D39: how to reach the goal weight. */
export interface WeightPlan {
  goal_weight_kg: number;
  burn: number;
  healthy_range_kg: [number, number];
  direction: "lose" | "gain" | "keep";
  calories: number;
  change: number;
  kg_per_week: number;
  /** D44: the pace as a share of body weight per week (0.0075 = 0.75%). */
  pace_share?: number;
  weeks: number | null;
  limited: string | null;
}

/** D40: one day in the strip. */
export type DayClass = "deficit" | "maintenance" | "surplus" | "below_minimum" | "not_logged" | "today";

export interface Progress {
  today: string;
  target: number;
  burn: number;
  minimum: number;
  streak: number;
  strip: {
    date: string;
    calories: number;
    protein_g: number;
    meals: number;
    /** D42: the user's answer to "Done for today?" (null: not asked). */
    confirmed: boolean | null;
    status: DayClass;
    on_target: boolean;
  }[];
  totals: {
    deficit: number;
    maintenance: number;
    surplus: number;
    below_minimum: number;
    not_logged: number;
    on_target: number;
    days: number;
  };
  recap: {
    days: number;
    cooked: number;
    typed: number;
    new_recipes: number;
    liked: number;
    days_logged: number;
    days_on_target: number;
    protein_days: number;
    /** D42: eaten minus burned, averaged over logged days. */
    balance: { days: number; avg_per_day: number; planned_per_day: number; est_kg: number } | null;
  };
}

/** D45: what you burn, learned from complete days and weigh-ins once there
 *  is enough of both; until then measured is null and burn is the formula's. */
export interface BurnEstimate {
  formula: number;
  burn: number;
  measured: number | null;
  trust: number;
  limited: boolean;
  complete_days: number;
  needed_days: number;
  weigh_in_days: number;
  needed_span: number;
  window_days: number;
}

/** D41: weigh-ins, the trend and the projection to the goal weight. */
export interface WeightSummary {
  today: string;
  entries: { id: number; date: string; weight_kg: number; trend_kg: number }[];
  trend_kg: number | null;
  rate_kg_per_week: number | null;
  status: "ahead" | "on_track" | "behind" | "stalled" | "not_enough_data" | "at_goal" | "drifting" | null;
  too_fast?: boolean;
  projection: {
    goal_kg: number;
    remaining_kg: number;
    planned_kg_per_week: number;
    plan_date: string | null;
    actual_date: string | null;
  } | null;
  burn?: BurnEstimate | null;
}

/** The browser's offset from UTC in minutes, east positive (D40: local days). */
const tzMinutes = () => -new Date().getTimezoneOffset();

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
  plan?: WeightPlan | null;
  burn?: BurnEstimate | null;
}

export interface Product {
  barcode: string | null;
  name: string | null;
  brand: string | null;
  calories_100g: number | null;
  protein_g_100g: number | null;
  carbs_g_100g: number | null;
  fat_g_100g: number | null;
  /** label: just read off a photo; saved: a label reading remembered for its barcode (D48). */
  source: "openfoodfacts" | "label" | "saved";
  /** D36: a warning when label values are missing or don't add up. */
  check?: string | null;
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
let savedKitchens = false;
let demoScans = false;
let usageStats = false;
/** True on the public demo; known once api.session() has answered. */
export const isDemo = () => demo;
/** True when the demo keeps anonymous usage totals (D33), shown at /stats. */
export const keepsStats = () => usageStats;
/** True when the demo saves kitchens for 30 days after the last visit (D34). */
export const savesKitchens = () => savedKitchens;
/** True when the demo has photo and label scanning on (D38). */
export const scansOn = () => !demo || demoScans;

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

/** A readable message from an API error: a plain string, or FastAPI's list of
 *  validation problems ("weight_kg: Input should be less than or equal to 250"). */
function errorText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => {
      const field = Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null;
      return field ? `${String(field).replace(/_/g, " ")}: ${d?.msg ?? "invalid"}` : String(d?.msg ?? d);
    });
    return parts.join("; ") || null;
  }
  return null;
}

/** An API error that keeps the server's detail, for errors that carry more
 *  than a message (D48: a scan that found a barcode says which). */
export class ApiError extends Error {
  detail: unknown;
  constructor(message: string, detail: unknown) {
    super(message);
    this.detail = detail;
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
    throw new ApiError(errorText(body.detail) ?? `${res.status} ${res.statusText}`, body.detail);
  }
  return res.json();
}

export const api = {
  session: async () => {
    const s = await req<{
      demo?: boolean;
      saved?: boolean;
      scans?: boolean;
      stats?: boolean;
      required: boolean;
      authenticated: boolean;
    }>("/api/session");
    demo = Boolean(s.demo);
    savedKitchens = Boolean(s.saved);
    demoScans = Boolean(s.scans);
    usageStats = Boolean(s.stats);
    return s;
  },
  /** Public demo (D34): delete this visitor's kitchen; the next request starts a new one. */
  deleteMyData: async () => {
    await req<{ deleted: boolean }>("/api/demo/kitchen", { method: "DELETE" });
    kitchenId = null;
    try {
      localStorage.removeItem(KITCHEN_KEY);
    } catch {
      // Memory only: already forgotten above.
    }
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
    // D46: suggestions holds "Did you mean…?" names for what wasn't recognised.
    req<{ added: string[]; unknown: string[]; suggestions?: Record<string, string[]> }>("/api/inventory", {
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
  shopping: (basket = 3) =>
    req<{
      personalized: boolean;
      unlocks_total: number;
      partial_scan: boolean;
      items: ShoppingItem[];
    }>(`/api/shopping?basket=${basket}`),
  scanPhoto: (file: File) => {
    const form = new FormData();
    form.append("photo", file);
    return req<{ proposals: ScanProposal[] }>("/api/vision/scan", { method: "POST", body: form });
  },
  profile: () => req<{ profile: Profile | null; targets: Targets | null }>(`/api/profile?tz=${tzMinutes()}`),
  saveProfile: (p: Profile) =>
    req<{ profile: Profile; targets: Targets }>(`/api/profile?tz=${tzMinutes()}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(p),
    }),
  day: (date?: string) =>
    req<DaySummary>(date ? `/api/day?date=${date}&tz=${tzMinutes()}` : `/api/day?tz=${tzMinutes()}`),
  progress: () => req<{ progress: Progress | null }>(`/api/progress?tz=${tzMinutes()}`),
  weight: () => req<WeightSummary>(`/api/weight?tz=${tzMinutes()}`),
  logWeight: (weight_kg: number) =>
    req<WeightSummary>(`/api/weight?tz=${tzMinutes()}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ weight_kg }),
    }),
  deleteWeight: (id: number) => req<WeightSummary>(`/api/weight/${id}?tz=${tzMinutes()}`, { method: "DELETE" }),
  checkDay: (day: string, complete: boolean | null) =>
    req<{ day: string; complete: boolean | null }>(`/api/days/${day}/check`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ complete }),
    }),
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
  /** `barcode`: one the app already has for this product (D48), so a label
   *  photo without its own barcode can be remembered under it. */
  scanProduct: (file: File, barcode?: string | null) => {
    const form = new FormData();
    form.append("photo", file);
    if (barcode) form.append("barcode", barcode);
    return req<{ product: Product }>("/api/nutrition/scan", { method: "POST", body: form });
  },
  saveProduct: (p: Product) =>
    req<{ product: Product }>("/api/nutrition/products", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        barcode: p.barcode,
        name: p.name,
        calories_100g: p.calories_100g,
        protein_g_100g: p.protein_g_100g,
        carbs_g_100g: p.carbs_g_100g,
        fat_g_100g: p.fat_g_100g,
      }),
    }),
  forgetProduct: (code: string) =>
    req<{ forgotten: string }>(`/api/nutrition/products/${encodeURIComponent(code)}`, { method: "DELETE" }),
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
