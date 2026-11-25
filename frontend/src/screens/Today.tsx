import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  localToday,
  noonOf,
  type MealIn,
  type MealIngredient,
  type MealSnapshot,
  isDemo,
  scansOn,
  type DayMeal,
  type DaySummary,
  type Product,
  type Profile,
  type RecentMeal,
  type Progress,
  type Targets,
  type WeightPlan,
  type WeightSummary,
} from "../api";
import { DayCheck, ProgressCard } from "./Progress";
import { WeightCard } from "./Weight";
import { CookingCard } from "../CookingCard";
import { ProfileForm } from "./ProfileForm";
import { rememberSample, usingSample } from "../sample";
import { detectBarcode } from "../barcode";
import { displayName } from "../format";
import { Guide, GuideHint, HelpButton } from "../Guide";
import { useGuide } from "../useGuide";
import { BackIcon, CloseIcon, ScanIcon } from "../Icons";
import { MealBuilder } from "./MealBuilder";
import { LogAgain } from "./LogAgain";
import {
  amountOf,
  asMealProduct,
  complete,
  defaultName,
  gramsOf,
  mealsText,
  productPart,
  totalsOf,
  wholeMealPart,
  wholeRow,
  type Part,
} from "../mealParts";
import { errorText } from "../LoadError";

const GOAL_WORDS: Record<Profile["goal"], string> = {
  cut: "losing fat",
  maintain: "keeping your weight",
  bulk: "building muscle",
};

const fmt = (n: number) => Math.round(n).toLocaleString("en");
/** Grams per 100 g: one decimal under 10 g (6.5 g protein, not 7), whole above. */
const grams = (n: number) => (n < 10 ? (Math.round(n * 10) / 10).toLocaleString("en") : fmt(n));
/** A value read off a label, or "?" when it couldn't be read (never a 0 that looks real). */
const shown = (n: number | null, g = true) => (n == null ? "?" : g ? grams(n) : fmt(n));

/** Calories as a ring: eaten against the daily target, what's left in the middle. */
function CalorieRing({ eaten, target }: { eaten: number; target: number }) {
  const r = 62;
  const c = 2 * Math.PI * r;
  const share = target > 0 ? Math.min(eaten / target, 1) : 0;
  const left = target - eaten;
  return (
    <figure className="ring" aria-label={`${fmt(eaten)} of ${fmt(target)} kcal eaten today`}>
      <svg viewBox="0 0 160 160" width="168" height="168" aria-hidden="true">
        <circle cx="80" cy="80" r={r} className="ring-track" />
        <circle
          cx="80"
          cy="80"
          r={r}
          className={left < 0 ? "ring-fill over" : "ring-fill"}
          strokeDasharray={`${share * c} ${c}`}
          transform="rotate(-90 80 80)"
        />
      </svg>
      <figcaption className="ring-center" aria-hidden="true">
        <span className="ring-value">{fmt(Math.abs(left))}</span>
        <span className="ring-label">{left >= 0 ? "kcal left" : "kcal over"}</span>
      </figcaption>
    </figure>
  );
}

/** D39: the goal-weight plan in one or two plain sentences. */
export function PlanLine({ plan }: { plan: WeightPlan }) {
  const goal = `${plan.goal_weight_kg} kg`; // not rounded: 72.5 stays 72.5
  let text: string;
  if (plan.direction === "keep") {
    text = `You're at your goal of ${goal}: about ${fmt(plan.calories)} kcal a day keeps you there.`;
  } else if (plan.weeks == null) {
    text = `Goal: ${goal}.`;
  } else {
    const more = plan.direction === "lose" ? "less" : "more";
    text =
      `To reach ${goal}: about ${fmt(plan.calories)} kcal a day, ${fmt(plan.change)} ${more} than you burn. ` +
      `At about ${plan.kg_per_week} kg a week${plan.pace_share && !plan.limited ? ` (${+(plan.pace_share * 100).toFixed(2)}% of your weight)` : ""}, ` +
      `that's roughly ${plan.weeks} weeks.`;
  }
  return (
    <p className="plan-line">
      {text}
      {plan.limited && <span className={plan.limited_warn ? "plan-limited" : "plan-note"}> {plan.limited}</span>}
    </p>
  );
}

function MacroBar({ label, value, target }: { label: string; value: number; target: number }) {
  const pct = target > 0 ? Math.min((value / target) * 100, 100) : 0;
  const diff = Math.round(target - value);
  return (
    <div className="macro">
      <div className="macro-head">
        <span className="macro-label">{label}</span>
        <span className="macro-value">
          {fmt(value)} / {fmt(target)} g
        </span>
      </div>
      <div className="meter-track" aria-hidden="true">
        <div className={diff < 0 ? "meter-fill over" : "meter-fill"} style={{ width: `${pct}%` }} />
      </div>
      <span className={diff < 0 ? "macro-note over" : "macro-note"}>
        {diff > 0 ? `${diff} g to go` : diff < 0 ? `${-diff} g over` : "Right on target"}
      </span>
    </div>
  );
}

const EMPTY_MEAL = { name: "", calories: "", protein_g: "", carbs_g: "", fat_g: "" };

/** "Wednesday, 18 November" for a local YYYY-MM-DD. */
function dayLabel(day: string, opts: Intl.DateTimeFormatOptions = { weekday: "long", day: "numeric", month: "long" }) {
  return new Date(`${day}T12:00:00`).toLocaleDateString("en", opts);
}

function shiftDay(day: string, by: number): string {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + by);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const SERVINGS = [0.5, 1, 1.5, 2, 3];
const servingsText = (n: number) => `${n === 0.5 ? "½" : n === 1.5 ? "1½" : n} serving${n > 1 ? "s" : ""}`;
/** D74: "1 of 4 portions", "½ of 6 portions". */
const portionText = (ate: number, pot: number) => `${ate === 0.5 ? "½" : ate === 1.5 ? "1½" : ate} of ${pot} portions`;
const num = (s: string) => Number(s.replace(",", "."));

/** D56: a product row of a logged meal, back in the form to edit it. */
function partFromLogged(i: MealIngredient): Part {
  const v = i.per_100g ?? { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 };
  // D73: a meal typed as numbers that joined this one whole.
  if (i.meals) return wholeRow(i.name, v, i.grams / i.meals, i.meals);
  const part = productPart(
    {
      barcode: i.barcode ?? null, name: i.name, brand: null, source: "openfoodfacts",
      calories_100g: v.calories, protein_g_100g: v.protein_g, carbs_g_100g: v.carbs_g, fat_g_100g: v.fat_g,
    },
    String(i.grams),
  );
  return { ...part, product: { barcode: i.barcode ?? null, source: "logged" } };
}

/** D56: a logged meal's ingredients and products, back as rows to change.
 *  D73: also how an earlier meal joins a new one ("Add to meal"). */
async function partsOfLogged(items: MealIngredient[]): Promise<Part[]> {
  return Promise.all(
    items.map(async (i): Promise<Part> => {
      if (i.product || !i.canonical) return partFromLogged(i);
      const { food } = await api.foodByKey(i.canonical);
      const canned = Boolean(i.canned && food.canned);
      const form = canned && food.canned ? food.canned : i.cooked && food.cooked ? food.cooked : food;
      return { food, ...amountOf(i.grams, form.portions), cooked: i.cooked, canned };
    }),
  );
}

function mealTime(m: DayMeal): string {
  // logged_at is SQLite datetime('now'): UTC, space-separated.
  const d = new Date(m.logged_at.replace(" ", "T") + "Z");
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function Today({
  onOpenRecipe,
  startLogging = false,
}: { onOpenRecipe?: (id: number) => void; startLogging?: boolean } = {}) {
  const [day, setDay] = useState<DaySummary | null>(null);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [weight, setWeight] = useState<WeightSummary | null>(null);
  const [recent, setRecent] = useState<RecentMeal[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [sample, setSample] = useState(usingSample);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    if (startLogging && loaded)
      requestAnimationFrame(() => document.querySelector(".meal-form")?.scrollIntoView({ block: "start" }));
  }, [startLogging, loaded]);
  const [editing, setEditing] = useState(false);
  // D72: "Ate something else? Log it" on Cook opens Progress with the form open.
  const [adding, setAdding] = useState(startLogging);
  const [meal, setMeal] = useState(EMPTY_MEAL);
  // D49: a meal built from ingredients and amounts instead of typed numbers.
  const [parts, setParts] = useState<Part[]>([]);
  const [mealError, setMealError] = useState<string | null>(null);
  // D73: something logged before went into this meal ("Add to meal").
  const [fromEarlier, setFromEarlier] = useState(false);
  // D74: the ingredients are a whole pot: how many portions it made, how many you ate.
  const [pot, setPot] = useState<{ made: string; ate: string } | null>(null);
  // D58: the calories-and-macros fields, behind a link, so the form opens on
  // one box rather than two that look alike.
  const [typing, setTyping] = useState(false);
  const [busy, setBusy] = useState(false);
  const [product, setProduct] = useState<Product | null>(null);
  const [grams, setGrams] = useState("100");
  const [scanBusy, setScanBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  // D48: a barcode found on a pack that Open Food Facts doesn't have; the next
  // photo (the nutrition table) is read and remembered under it.
  const [pendingBarcode, setPendingBarcode] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const guide = useGuide("forkcast.todayguide.v1");

  const [loadError, setLoadError] = useState<string | null>(null);
  // D56: the day being looked at (today, or an earlier one to fill in),
  // the meal being edited, and the last one removed, for Undo.
  const [viewDay, setViewDay] = useState(localToday);
  const [editingId, setEditingId] = useState<number | null>(null);
  // D66: every meal removed while the bar shows, so Undo puts them all back.
  const [undo, setUndo] = useState<{ name: string; meal: MealSnapshot }[] | null>(null);
  const isToday = viewDay === localToday();
  const loggedAt = isToday ? undefined : noonOf(viewDay);

  const refresh = (d: string = viewDay) =>
    Promise.all([
      api.day(d === localToday() ? undefined : d), api.profile(), api.progress(), api.weight(),
      api.recentMeals().catch(() => ({ meals: [] })),
    ])
      .then(([d, p, g, w, r]) => {
        setRecent(r.meals);
        setDay(d);
        setProgress(g.progress);
        setWeight(w);
        setProfile(p.profile);
        setLoadError(null);
        setLoaded(true);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  useEffect(() => {
    refresh(viewDay);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewDay]);
  useEffect(() => {
    if (!undo) return;
    const t = setTimeout(() => setUndo(null), 10000);
    return () => clearTimeout(t);
  }, [undo]);

  function onSaved(p: Profile, _targets: Targets, _plan: unknown, sample: boolean) {
    rememberSample(sample); // D68: your own numbers replace the sample person
    setSample(sample);
    setProfile(p);
    setEditing(false);
    refresh();
  }

  async function addMeal() {
    if (busy) return;
    setBusy(true);
    setMealError(null);
    try {
      let body: MealIn;
      if (parts.length > 0) {
        // The server works the numbers out from the ingredients (D49).
        const ingredients = parts
          .filter((p) => !p.product)
          .map((p) => ({ canonical: p.food.canonical, grams: gramsOf(p), cooked: p.cooked, canned: Boolean(p.canned) }));
        const products = parts.filter((p) => p.product).map(asMealProduct);
        body = {
          name: meal.name.trim() || defaultName(parts),
          ...(ingredients.length > 0 && { ingredients }),
          ...(products.length > 0 && { products }),
          ...(fromEarlier && editingId === null && { source: "earlier" as const }),
          ...(pot && { pot: num(pot.made), portions: num(pot.ate) }),
        };
      } else {
        body = {
          name: meal.name.trim(),
          calories: Number(meal.calories) || 0,
          protein_g: Number(meal.protein_g) || 0,
          carbs_g: Number(meal.carbs_g) || 0,
          fat_g: Number(meal.fat_g) || 0,
        };
      }
      // D56: an edit keeps its time; a new meal on an earlier day goes at noon.
      if (editingId !== null) await api.editMeal(editingId, body);
      else await api.addMeal({ ...body, ...(loggedAt && { logged_at: loggedAt }) });
      closeForm();
      await refresh();
    } catch (e) {
      setMealError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  // D74: a pot makes more than one portion, and you can't eat more than it made.
  const potProblem = !pot
    ? null
    : !(num(pot.made) > 1)
      ? "A pot makes more than one portion."
      : !(num(pot.ate) > 0)
        ? "Say how many portions you ate."
        : num(pot.ate) > num(pot.made)
          ? `That's more than the ${pot.made} portions it made.`
          : null;
  const partsReady = parts.length > 0 && parts.every((p) => gramsOf(p) > 0) && !potProblem;

  function closeForm() {
    setMeal(EMPTY_MEAL);
    setParts([]);
    setFromEarlier(false);
    setPot(null);
    setAdding(false);
    setEditingId(null);
    setTyping(false);
    setProduct(null);
    setScanError(null);
    setMealError(null);
  }

  /** D60: from the button under the ring, the form opens further down: go there. */
  function openForm() {
    setAdding(true);
    requestAnimationFrame(() => {
      document.querySelector(".meal-form")?.scrollIntoView({ block: "start", behavior: "smooth" });
      document.querySelector<HTMLInputElement>("#builder-query")?.focus({ preventScroll: true });
    });
  }

  async function removeMeal(m: DayMeal) {
    const res = await api.deleteMeal(m.id);
    // D56: a mis-tap costs nothing: Undo puts it back as it was.
    const removed = { name: m.name ? (m.recipe_id !== null ? displayName(m.name) : m.name) : "the meal", meal: res.meal };
    setUndo((u) => [...(u ?? []), removed]);
    await refresh();
  }

  async function undoRemove() {
    if (!undo) return;
    const meals = undo;
    setUndo(null);
    for (const r of meals) await api.restoreMeal(r.meal);
    await refresh();
  }

  /** D73: a meal logged before joins the one being built: its ingredients and
   *  products as rows, at the amounts you had, or one row for a meal typed in as
   *  numbers. The totals add up as for any built meal. */
  async function addEarlier(m: RecentMeal) {
    setMealError(null);
    try {
      // D74: from a pot, only the share that meal was: 1 of 4 portions is a quarter of each ingredient.
      const share = m.pot ? (m.portions ?? 1) / m.pot : 1;
      const items = m.ingredients.map((i) => ({ ...i, grams: i.grams * share, meals: i.meals ? i.meals * share : i.meals }));
      const rows = items.length > 0 ? await partsOfLogged(items) : [wholeMealPart(m)];
      setParts((ps) => [...ps, ...rows]);
      setFromEarlier(true);
      setTyping(false);
    } catch (e) {
      setMealError(errorText(e));
    }
  }

  /** D73: "Add to meal" on Log again: a new meal, starting with that one. */
  async function startFromEarlier(m: RecentMeal) {
    closeForm();
    setAdding(true);
    await addEarlier(m);
    requestAnimationFrame(() => document.querySelector(".meal-form")?.scrollIntoView({ block: "start", behavior: "smooth" }));
  }

  /** D56: back into the form, filled in, to change and save over. */
  async function startEdit(m: DayMeal) {
    closeForm();
    if (m.ingredients.length > 0) {
      setParts(await partsOfLogged(m.ingredients));
      if (m.pot) setPot({ made: String(m.pot), ate: String(m.portions ?? 1) });
      setMeal({ ...EMPTY_MEAL, name: m.name ?? "" });
    } else {
      const v = (n: number | null) => (n == null ? "" : String(Math.round(n * 10) / 10));
      setMeal({ name: m.name ?? "", calories: v(m.calories), protein_g: v(m.protein_g), carbs_g: v(m.carbs_g), fat_g: v(m.fat_g) });
      setTyping(true);
    }
    setEditingId(m.id);
    setAdding(true);
    requestAnimationFrame(() => document.querySelector(".meal-form")?.scrollIntoView({ block: "start", behavior: "smooth" }));
  }

  async function changeServings(m: DayMeal, servings: number) {
    await api.setServings(m.id, servings);
    await refresh();
  }

  async function rate(m: DayMeal, thumb: boolean) {
    // tapping the active choice clears the rating
    const next = m.liked !== null && Boolean(m.liked) === thumb ? null : thumb;
    await api.rateMeal(m.id, next);
    await refresh();
  }

  async function onProductPhoto(file: File | undefined) {
    if (!file) return;
    setScanBusy(true);
    setScanError(null);
    setProduct(null);
    try {
      // barcode-first (D9): on-device detection costs nothing when supported
      const code = await detectBarcode(file);
      const listed = code ? await api.barcodeLookup(code).catch(() => null) : null;
      const res =
        listed && listed.product.calories_100g != null
          ? listed
          : await api.scanProduct(file, code ?? pendingBarcode);
      setProduct(res.product);
      setPendingBarcode(null);
      // D54: what you had last time; D52: else one serving, when Open Food Facts
      // knows it (a 30 g scoop, not 100 g); else 100 g.
      setGrams(String(res.product.last_grams ?? res.product.serving_g ?? 100));
    } catch (e) {
      const found = e instanceof ApiError ? (e.detail as { barcode?: string | null } | null)?.barcode : null;
      if (found) setPendingBarcode(found);
      setScanError(e instanceof Error ? e.message : String(e));
    } finally {
      setScanBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  /** D48: a label reading for a barcode Open Food Facts doesn't have, complete
   *  and adding up (D36), is remembered for that barcode when it's used. */
  function savable(p: Product): boolean {
    return (
      p.source === "label" &&
      Boolean(p.barcode) &&
      !p.check &&
      [p.calories_100g, p.protein_g_100g, p.carbs_g_100g, p.fat_g_100g].every((v) => v != null)
    );
  }

  async function useProduct() {
    if (!product) return;
    if (savable(product)) await api.saveProduct(product).catch(() => null);
    if (complete(product)) {
      // D51: a product joins the ingredient list like any other row.
      setParts([...parts, productPart(product, String(Number(grams) || 100))]);
      setProduct(null);
      return;
    }
    if (parts.length > 0) {
      setMealError("Some of this product's values couldn't be read, so it can't join the list. Log it as a meal of its own and type them in.");
      return;
    }
    const factor = (Number(grams) || 0) / 100;
    // One decimal: 30 g of something with 6.5 g protein per 100 g is 2 g, not 0 or 1.95.
    const scale = (v: number | null) => (v == null ? "" : String(Math.round(v * factor * 10) / 10));
    setTyping(true);
    setMeal({
      name: [product.name, `${Number(grams) || 0} g`].filter(Boolean).join(", "),
      calories: scale(product.calories_100g),
      protein_g: scale(product.protein_g_100g),
      carbs_g: scale(product.carbs_g_100g),
      fat_g: scale(product.fat_g_100g),
    });
    setProduct(null);
  }

  async function forgetProduct() {
    if (!product?.barcode) return;
    await api.forgetProduct(product.barcode).catch(() => null);
    setPendingBarcode(product.barcode);
    setProduct(null);
    setScanError(null);
  }

  if (loadError && !loaded) {
    return (
      <div className="screen">
        <p className="empty">Couldn't load your day.</p>
        <p className="feedback">{loadError}</p>
        <button className="btn" onClick={() => refresh()}>Try again</button>
      </div>
    );
  }
  if (!loaded)
    return (
      <div className="screen" aria-busy="true">
        <p className="empty-note">Loading your day…</p>
      </div>
    );

  if (!profile || editing) {
    return (
      <div className="screen narrow">
        {editing && (
          <button className="back" onClick={() => setEditing(false)}>
            <BackIcon size={20} /> Today
          </button>
        )}
        {/* D60: the sample person's numbers never pre-fill "your own". */}
        <ProfileForm
          initial={sample ? null : profile}
          kicker={sample ? "Your own numbers" : undefined}
          onSaved={onSaved}
        />
      </div>
    );
  }

  // D56: only the day in the heading: right after switching, the last day's
  // meals would otherwise show under the new day's name until it loads.
  const ready = day?.date === viewDay;
  const t = day?.targets;
  const totals = ready ? day?.totals : undefined;
  const date = dayLabel(viewDay);
  const short = dayLabel(viewDay, { weekday: "short", day: "numeric", month: "short" });
  const meals = ready ? (day?.meals ?? []) : [];

  return (
    <div className="screen">
      {/* D56: earlier days, to fill in a meal you forgot. */}
      <nav className="day-nav" aria-label="Day">
        <button className="link-button" onClick={() => setViewDay(shiftDay(viewDay, -1))}>
          ‹ Earlier
        </button>
        <p className="kicker">{date}</p>
        {isToday ? (
          <span className="day-nav-spacer" />
        ) : (
          <button className="link-button" onClick={() => setViewDay(shiftDay(viewDay, 1))}>
            Later ›
          </button>
        )}
      </nav>
      <div className="title-row">
        <h1 className="display">{isToday ? "Today" : dayLabel(viewDay, { weekday: "long" })}</h1>
        <HelpButton open={guide.open} onToggle={guide.toggle} label="How this page works" controls="today-guide" />
      </div>
      <p className="lead">
        {sample ? (
          // D68: say whose targets these are until someone puts in their own.
          <>
            Targets for a <strong>sample person</strong> (34, 168 cm, 68 kg, aiming for 64 kg).{" "}
            <button className="link" onClick={() => setEditing(true)}>
              Use my own numbers
            </button>
          </>
        ) : (
          <>
            Targets for {GOAL_WORDS[profile.goal]}, from your profile.{" "}
            <button className="link" onClick={() => setEditing(true)}>
              Edit profile
            </button>
          </>
        )}
        {!isToday && (
          <>
            {" "}
            <button className="link" onClick={() => setViewDay(localToday())}>
              Back to today
            </button>
          </>
        )}
      </p>
      {isToday && onOpenRecipe && <CookingCard onOpen={onOpenRecipe} />}

      {guide.hint && <GuideHint onOpen={guide.show} onDismiss={guide.dismiss} />}
      {guide.open && (
        <Guide
          id="today-guide"
          title="How this page works"
          onClose={guide.close}
          items={[
            {
              term: "The ring",
              text: "Calories eaten today against your daily target. The number in the middle is what's left.",
            },
            {
              term: "Protein, carbs, fat",
              text: "What you've eaten against each target. The recipe feed puts dishes first that fill whichever is furthest behind.",
            },
            {
              term: "Your targets",
              text: "Worked out from your profile: a widely used estimate of what your body burns from your sex, age, height and weight, then your activity level and goal. After about two weeks of complete days and weigh-ins, Forkcast learns what you really burn from them and uses that instead (the Weight card says which). With a goal weight, the line under the ring says how much less or more than you burn to eat, and roughly how long it takes. Change them under Edit profile.",
            },
            {
              term: "Log a meal",
              text: "Three ways: scan a barcode or a nutrition label, add the ingredients with how much of each, or type the numbers. A scanned product goes into the ingredient list, so skyr from a pack and a banana make one meal. Ingredient values are per 100 g from the USDA's food tables; each ingredient says which USDA food it used. Rice, pasta and beans can be weighed dry or cooked, which makes a big difference; beans and peas can also come from a can, drained. Each food starts at the amount you had last time, once you've logged it. Meals you typed or built in the last month wait under Log again, one tap each; star one to keep it there. Add to meal puts one into a new meal with other things, under a name of your own: a usual breakfast becomes one tap. Cooked a whole pot? Add everything that went in, say how many portions it made and how many you ate; the next portion is one tap under Log again.",
            },
            {
              term: "Liked · Not for me",
              text: "Rate the recipes you cook and the meals you build from two or more ingredients. Recipes close to them move up the feed; ones you mark Not for me stop counting. Meals typed in as numbers, and single foods like a banana, can't be rated: there's no dish for the feed to learn from.",
            },
            {
              term: "Weight",
              text: "Log your weight now and then, ideally in the morning. The line is a smoothed trend, so one day's water or salt doesn't count for much. With a goal weight, Forkcast compares your pace over the last three weeks with the plan and says when you'd reach the goal at that pace. Your daily target follows the trend.",
            },
            {
              term: "Done for today?",
              text: "Tell Forkcast when a day's log is complete. Confirmed days always count; days you mark incomplete never do. Without an answer, a day with less than half your target logged counts as not logged.",
            },
            {
              term: "Your days",
              text: "Below your meals: one dot per day for the last two weeks, coloured by whether you ate less than you burn, about the same, or more. The streak counts days within 10% of your target. Days logged under half the target count as not logged, and days under your minimum never count.",
            },
          ]}
        />
      )}

      <div className="today-layout">
        {t && totals && (
          <section className="today-summary" aria-label={isToday ? "Today's totals" : `Totals for ${date}`}>
            <CalorieRing eaten={totals.calories} target={t.calories} />
            <p className="ring-caption">
              {fmt(totals.calories)} of {fmt(t.calories)} kcal eaten
            </p>
            {/* D60: on a phone the meals start a screen further down; logging starts here. */}
            {!adding && (
              <button className="btn secondary log-btn log-btn-phone" onClick={openForm}>
                Log a meal
              </button>
            )}
            {day?.plan && <PlanLine plan={day.plan} />}
            <div className="macros">
              <MacroBar label="Protein" value={totals.protein_g} target={t.protein_g} />
              <MacroBar label="Carbs" value={totals.carbs_g} target={t.carbs_g} />
              <MacroBar label="Fat" value={totals.fat_g} target={t.fat_g} />
            </div>
          </section>
        )}

        <div className="today-main">
        <section aria-labelledby="meals-title">
          <h2 id="meals-title" className="section-title">{isToday ? "Today's meals" : `Meals on ${short}`}</h2>
          {!ready && <p className="empty-note" aria-busy="true">Loading…</p>}
          {ready && meals.length === 0 && (
            <p className="empty-note">
              {isToday
                ? 'Nothing logged yet. Cook a recipe and tap "I ate it", or log a meal.'
                : `Nothing logged on ${short}. Log what you ate that day.`}
            </p>
          )}
          {!adding && (
            <LogAgain meals={recent} onChange={() => refresh()} onAddToMeal={startFromEarlier} loggedAt={loggedAt} />
          )}
          {adding ? (
            <form
              className="meal-form"
              onSubmit={(e) => {
                e.preventDefault();
                addMeal();
              }}
            >
              <h3 className="form-title">
                {editingId !== null ? "Edit meal" : isToday ? "Log a meal" : `Log a meal for ${short}`}
              </h3>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                capture="environment"
                hidden
                onChange={(e) => onProductPhoto(e.target.files?.[0])}
              />
              <button type="button" className="scan-btn" onClick={() => fileRef.current?.click()} disabled={scanBusy}>
                <ScanIcon size={20} />
                {scanBusy
                  ? "Reading the product…"
                  : pendingBarcode
                    ? "Photograph the nutrition table"
                    : "Scan a barcode or nutrition label"}
              </button>
              {pendingBarcode ? (
                <p className="field-hint">
                  The next photo is read as the nutrition table for barcode {pendingBarcode}.{" "}
                  <button type="button" className="link-button" onClick={() => setPendingBarcode(null)}>
                    Different product
                  </button>
                </p>
              ) : (
                // D58: one line; the guide has the rest.
                <p className="field-hint">
                  A packed food: scan its barcode or nutrition table.
                  {isDemo() && scansOn() && " Labels are read by Anthropic's Claude; the photo isn't kept."}
                </p>
              )}
              {scanError && <p className="feedback error">{scanError}</p>}
              {product && (
                <div className="product-card">
                  <div className="product-head">
                    <strong>{product.name ?? "Unnamed product"}</strong>
                    <span className="product-source">
                      {product.source === "openfoodfacts"
                        ? "from Open Food Facts"
                        : product.source === "saved"
                          ? "saved from your earlier scan"
                          : "read from the label"}
                    </span>
                  </div>
                  <p className="product-macros">
                    Per 100 g: {shown(product.calories_100g, false)} kcal · {shown(product.protein_g_100g)} g protein ·{" "}
                    {shown(product.carbs_g_100g)} g carbs · {shown(product.fat_g_100g)} g fat
                  </p>
                  {product.check && (
                    <p className="feedback warning" role="alert">
                      {product.check}
                    </p>
                  )}
                  {savable(product) && (
                    <p className="field-hint product-note">
                      Barcode {product.barcode} isn't on Open Food Facts yet. When you add it, Forkcast remembers
                      these values for it, so the barcode alone works next time.{" "}
                      <a
                        href={`https://world.openfoodfacts.org/product/${product.barcode}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Add it to Open Food Facts
                      </a>{" "}
                      to make it work for everyone.
                    </p>
                  )}
                  {product.source === "saved" && (
                    <p className="field-hint product-note">
                      You scanned this label before.{" "}
                      <button type="button" className="link-button" onClick={forgetProduct}>
                        Wrong? Forget these values
                      </button>
                    </p>
                  )}
                  {product.last_grams != null ? (
                    <p className="field-hint product-note">
                      Starts at {fmt(product.last_grams)} g, what you had last time. Change it to what you had.
                    </p>
                  ) : (product.serving_g || product.pack_g) && (
                    <p className="field-hint product-note">
                      {/* D52: a suggestion from Open Food Facts, not a fixed amount. */}
                      {product.serving_g
                        ? `Starts at one serving, ${fmt(product.serving_g)} g according to Open Food Facts` +
                          (product.pack_g ? ` (the pack is ${fmt(product.pack_g)} g)` : "") +
                          ". Change it to what you had."
                        : `The pack is ${fmt(product.pack_g ?? 0)} g, according to Open Food Facts.`}
                    </p>
                  )}
                  <div className="product-use">
                    <label className="inline-label">
                      How much?
                      <input
                        type="number"
                        inputMode="decimal"
                        value={grams}
                        onChange={(e) => setGrams(e.target.value)}
                      />
                      g
                    </label>
                    <button type="button" className="btn" onClick={useProduct}>
                      {complete(product) ? "Add to meal" : "Use these values"}
                    </button>
                  </div>
                </div>
              )}
              <MealBuilder
                parts={parts}
                onChange={setParts}
                onDish={(dish) => setMeal((m) => (m.name.trim() ? m : { ...m, name: dish }))}
                more={
                  // D73: meals logged before, to put together into this one.
                  recent.length > 0 &&
                  !typing && (
                    <div className="earlier">
                      <p className="field-hint">Or add something you logged before:</p>
                      <div className="suggest-chips">
                        {recent.map((m) => (
                          <button
                            key={m.meal_id}
                            type="button"
                            className="suggest-chip earlier-chip"
                            aria-label={`Add ${m.name} to this meal`}
                            onClick={() => addEarlier(m)}
                          >
                            + {m.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  )
                }
              />
              {parts.length > 0 &&
                (pot ? (
                  <fieldset className="pot">
                    <legend>A whole pot</legend>
                    <div className="pot-row">
                      <label>
                        It made
                        <input
                          type="number"
                          inputMode="decimal"
                          min="1"
                          step="any"
                          value={pot.made}
                          onChange={(e) => setPot({ ...pot, made: e.target.value })}
                        />
                        portions
                      </label>
                      <label>
                        I ate
                        <input
                          type="number"
                          inputMode="decimal"
                          min="0"
                          step="any"
                          value={pot.ate}
                          onChange={(e) => setPot({ ...pot, ate: e.target.value })}
                        />
                      </label>
                    </div>
                    {potProblem ? (
                      <p className="field-hint">{potProblem}</p>
                    ) : (
                      <p className="field-hint pot-share">
                        {(() => {
                          const t = totalsOf(parts);
                          const f = num(pot.ate) / num(pot.made);
                          return `Your share: ${fmt(t.calories * f)} kcal · ${fmt(t.protein_g * f)} g protein · ${fmt(t.carbs_g * f)} g carbs · ${fmt(t.fat_g * f)} g fat. `;
                        })()}
                        Log the next portion under Log again, one tap.
                      </p>
                    )}
                    <button type="button" className="link-button" onClick={() => setPot(null)}>
                      I ate all of it
                    </button>
                  </fieldset>
                ) : (
                  <button type="button" className="link-button pot-open" onClick={() => setPot({ made: "4", ate: "1" })}>
                    Cooked a whole pot? Split it into portions
                  </button>
                ))}
              {parts.length === 0 && !typing && (
                <button type="button" className="link-button type-numbers" onClick={() => setTyping(true)}>
                  Or type the calories yourself
                </button>
              )}
              {(parts.length > 0 || typing) && (
              <label className="field">
                {parts.length > 0 ? "Name it (optional)" : "What did you eat?"}
                <input
                  placeholder={parts.length > 0 ? defaultName(parts) : "e.g. Skyr with berries"}
                  value={meal.name}
                  onChange={(e) => setMeal({ ...meal, name: e.target.value })}
                />
              </label>
              )}
              {parts.length > 0 && fromEarlier && editingId === null && (
                <p className="field-hint">
                  It waits under Log again by this name, one tap next time. Star it there to keep it at the top.
                </p>
              )}
              {parts.length === 0 && typing && (
              <div className="meal-form-grid">
                <label className="field">
                  kcal
                  <input type="number" inputMode="decimal" value={meal.calories} onChange={(e) => setMeal({ ...meal, calories: e.target.value })} />
                </label>
                <label className="field">
                  Protein g
                  <input type="number" inputMode="decimal" value={meal.protein_g} onChange={(e) => setMeal({ ...meal, protein_g: e.target.value })} />
                </label>
                <label className="field">
                  Carbs g
                  <input type="number" inputMode="decimal" value={meal.carbs_g} onChange={(e) => setMeal({ ...meal, carbs_g: e.target.value })} />
                </label>
                <label className="field">
                  Fat g
                  <input type="number" inputMode="decimal" value={meal.fat_g} onChange={(e) => setMeal({ ...meal, fat_g: e.target.value })} />
                </label>
              </div>
              )}
              {mealError && <p className="feedback error">{mealError}</p>}
              {/* D58: say why Log meal can't be pressed yet, rather than grey it silently. */}
              {parts.length > 0 && !partsReady && (
                <p className="field-hint">Every ingredient needs an amount above 0.</p>
              )}
              {parts.length === 0 && typing && (!meal.name.trim() || !meal.calories) && (
                <p className="field-hint">Give the meal a name and its calories.</p>
              )}
              <div className="form-actions">
                <button
                  type="submit"
                  className="btn"
                  disabled={busy || (parts.length > 0 ? !partsReady : !typing || !meal.name.trim() || !meal.calories)}
                >
                  {editingId !== null ? "Save changes" : "Log meal"}
                </button>
                <button type="button" className="btn secondary" onClick={closeForm}>
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <button className="btn secondary log-btn log-btn-wide" onClick={() => setAdding(true)}>
              Log a meal
            </button>
          )}
          <ol className="meal-list">
            {meals.map((m) => (
              <li key={m.id} className="meal">
                <span className="meal-time">{mealTime(m)}</span>
                <div className="meal-main">
                  <span className="meal-name">
                    {/* Clean up corpus recipe names; what you typed stays as typed. */}
                    {m.name ? (m.recipe_id !== null ? displayName(m.name) : m.name) : "Unnamed meal"}
                  </span>
                  <span className="meal-macros">
                    {m.servings != null && `${servingsText(m.servings)} · `}
                    {m.pot != null && `${portionText(m.portions ?? 1, m.pot)} · `}
                    {fmt(m.calories ?? 0)} kcal · {fmt(m.protein_g ?? 0)} g protein · {fmt(m.carbs_g ?? 0)} g carbs ·{" "}
                    {fmt(m.fat_g ?? 0)} g fat
                  </span>
                  {m.ingredients.length > 0 && (
                    <span className="meal-ingredients">
                      {m.pot != null && "Whole pot: "}
                      {m.ingredients
                        .map((i) =>
                          i.meals
                            ? `${i.name}, ${mealsText(i.meals)}`
                            : `${i.name} ${fmt(i.grams)} g${i.cooked ? " cooked" : i.canned ? " canned" : ""}`,
                        )
                        .join(" · ")}
                    </span>
                  )}
                  {m.rateable ? (
                    <span className="rate" role="group" aria-label={`Rate ${m.name}`}>
                      <button className="pill" aria-pressed={m.liked === 1} onClick={() => rate(m, true)}>
                        Liked
                      </button>
                      <button className="pill" aria-pressed={m.liked === 0} onClick={() => rate(m, false)}>
                        Not for me
                      </button>
                    </span>
                  ) : (
                    // A tester asked why these have no Liked button: ratings teach the
                    // recipe feed, which needs a dish to learn from (D46, D49).
                    <span className="rate-note">{m.rate_note}</span>
                  )}
                  {m.recipe_id !== null ? (
                    <label className="servings">
                      How much did you eat?
                      <select
                        value={m.servings ?? 1}
                        onChange={(e) => changeServings(m, Number(e.target.value))}
                        aria-label={`Servings of ${m.name}`}
                      >
                        {SERVINGS.map((n) => (
                          <option key={n} value={n}>
                            {servingsText(n)}
                          </option>
                        ))}
                      </select>
                    </label>
                  ) : (
                    <button className="link-button meal-edit" onClick={() => startEdit(m)} aria-label={`Edit ${m.name}`}>
                      Edit
                    </button>
                  )}
                </div>
                <button className="remove" onClick={() => removeMeal(m)} aria-label={`Remove ${m.name}`}>
                  <CloseIcon size={18} />
                </button>
              </li>
            ))}
          </ol>

        </section>
        {/* About now: shown on today, not on an earlier day being filled in. */}
        {isToday && progress && <DayCheck progress={progress} onChange={() => refresh()} />}
        {isToday && weight && profile && (
          <WeightCard key={`${weight.entries.length}:${weight.trend_kg}`} initial={weight} onChange={() => refresh()} />
        )}
        {isToday && progress && <ProgressCard progress={progress} />}
        </div>
      </div>
      {undo && (
        <div className="undo-bar" role="status">
          <span>Removed {undo.length === 1 ? undo[0].name : `${undo.length} meals`}.</span>
          <button className="link-button" onClick={undoRemove}>
            Undo
          </button>
        </div>
      )}
    </div>
  );
}
