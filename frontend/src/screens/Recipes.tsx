import { useEffect, useState } from "react";
import {
  api,
  pretty,
  type CookableRecipe,
  type MacroFocus,
  type ShoppingItem,
  type TasteProfile,
} from "../api";
import { displayName, foodColor, mealOfDay } from "../format";
import { useMediaQuery } from "../useMediaQuery";
import { Guide, HelpButton } from "../Guide";
import { useGuide } from "../useGuide";
import { RecipeView } from "./RecipeView";

const MACRO_LABELS: Record<MacroFocus["macro"], string> = {
  protein_g: "protein",
  carbs_g: "carbs",
  fat_g: "fat",
};

const FILTERS = ["Cookable now", "One away", "Two away"];

export function Recipes() {
  const [maxMissing, setMaxMissing] = useState(0);
  const [recipes, setRecipes] = useState<CookableRecipe[]>([]);
  const [tasteInfo, setTasteInfo] = useState<TasteProfile | null>(null);
  const [focus, setFocus] = useState<MacroFocus | null>(null);
  const [basket, setBasket] = useState<ShoppingItem[]>([]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const guide = useGuide("forkcast.feedguide.v1");
  // From 960px the list and the open recipe sit side by side.
  const wide = useMediaQuery("(min-width: 960px)");

  useEffect(() => {
    api.taste().then(setTasteInfo).catch(() => {});
    // Slower than the feed (it scans the near-miss corpus), so it loads
    // independently instead of holding the recipe list back.
    api.shopping().then((s) => setBasket(s.items)).catch(() => {});
  }, []);

  // A tester wanted more than three. The picks are made one after another,
  // so the first three stay the same and two more are added below them.
  const [moreBusy, setMoreBusy] = useState(false);
  async function showMore() {
    setMoreBusy(true);
    try {
      setBasket((await api.shopping(5)).items);
    } finally {
      setMoreBusy(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    api
      .cookable(maxMissing, true)
      .then((r) => {
        setRecipes(r.recipes);
        setFocus(r.macro_focus);
      })
      .finally(() => setLoading(false));
  }, [maxMissing]);

  // On a wide screen something is always open: the top recipe by default.
  const selected = openId ?? (wide ? recipes[0]?.id ?? null : null);

  if (!wide && openId !== null) {
    return <RecipeView id={openId} onBack={() => setOpenId(null)} />;
  }

  const leans = tasteInfo && tasteInfo.meals_logged > 0
    ? tasteInfo.profile.slice(0, 3).map((p) => pretty(p.ingredient)).join(", ")
    : null;
  const weekday = new Date().toLocaleDateString("en", { weekday: "long" });

  const unlocksTotal = basket.reduce((n, i) => n + i.unlocks, 0);

  return (
    <div className="recipes-layout">
      <section className="screen" aria-label="Recipes">
        <p className="kicker">{weekday} · {mealOfDay()}</p>
        <h1 className="display">What's for {mealOfDay()}?</h1>
        {(leans || (focus && focus.grams > 0)) && (
          <p className="lead">
            {leans && (
              <>
                From what you've cooked, you lean towards <em>{leans}</em>.{" "}
              </>
            )}
            {focus && focus.grams > 0 && (
              <>
                You have <strong>{focus.grams} g {MACRO_LABELS[focus.macro]}</strong> to go today.
              </>
            )}
          </p>
        )}

        <div className="filter-row">
          <div className="filter-tabs" role="group" aria-label="How many ingredients you're missing">
            {FILTERS.map((label, n) => (
              <button key={label} aria-pressed={n === maxMissing} onClick={() => setMaxMissing(n)}>
                {label}
              </button>
            ))}
          </div>
          <HelpButton open={guide.open} onToggle={guide.toggle} label="How to read this list" controls="feed-guide" />
        </div>

        {guide.open && <FeedGuide onClose={guide.close} />}

        {loading && (
          <div aria-busy="true" aria-label="Searching 87,861 recipes">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton" aria-hidden="true">
                <span style={{ width: 90 }} />
                <span />
                <span />
              </div>
            ))}
          </div>
        )}
        {!loading && recipes.length === 0 && (
          <p className="empty">
            {maxMissing === 0
              ? "Nothing is cookable yet. Add what's in your kitchen, or look one ingredient away."
              : "Nothing this close yet. Add a few more ingredients to your kitchen."}
          </p>
        )}

        {!loading && (
          <ul className="recipe-list">
            {recipes.map((r) => (
              <li key={r.id}>
                <RecipeCard
                  recipe={r}
                  focus={focus}
                  current={wide && r.id === selected}
                  onOpen={() => {
                    setOpenId(r.id);
                    // On a phone the recipe replaces the list: start at its top.
                    if (!wide) window.scrollTo(0, 0);
                  }}
                />
              </li>
            ))}
          </ul>
        )}

        {basket.length > 0 && (
          <section className="shopping" aria-labelledby="worth-buying">
            <h2 id="worth-buying" className="section-title">Worth buying</h2>
            <p className="taste-note">
              These {basket.length} unlock {unlocksTotal} more recipes together.
            </p>
            <ol className="shopping-list">
              {basket.map((item, i) => (
                <li key={item.canonical} className="shopping-item">
                  <div className="shopping-head">
                    <span className="shopping-name">{pretty(item.canonical)}</span>
                    <span className="shopping-count">
                      {i === 0 ? `${item.unlocks} recipes` : `+${item.unlocks} more`}
                    </span>
                  </div>
                  <div className="bar" aria-hidden="true">
                    <span style={{ width: `${Math.max(4, (item.unlocks / basket[0].unlocks) * 100)}%` }} />
                  </div>
                  <div className="shopping-examples">
                    {item.examples.map(displayName).join(" · ")}
                  </div>
                </li>
              ))}
            </ol>
            {basket.length === 3 && (
              <button type="button" className="link-button" disabled={moreBusy} onClick={showMore}>
                {moreBusy ? "Finding two more…" : "Show 2 more"}
              </button>
            )}
          </section>
        )}
      </section>

      {wide && selected !== null && (
        <aside className="detail-pane" aria-label="Selected recipe">
          <RecipeView key={selected} id={selected} onBack={() => setOpenId(null)} />
        </aside>
      )}
    </div>
  );
}

function RecipeCard({
  recipe: r,
  focus,
  current,
  onOpen,
}: {
  recipe: CookableRecipe;
  focus: MacroFocus | null;
  current: boolean;
  onOpen: () => void;
}) {
  const sig = r.signature ?? [];
  const have = r.ingredients_needed - r.ingredients_missing;
  const focusGrams = focus ? r[focus.macro] : null;
  const covers = focus && focus.grams > 0 && focusGrams != null && focusGrams >= focus.grams;
  return (
    <button className="recipe-card" aria-current={current ? "true" : undefined} onClick={onOpen}>
      <span className="signature">
        <span className="dots" aria-hidden="true">
          {sig.map((s) =>
            s.have ? (
              <span key={s.canonical} className="dot" style={{ background: foodColor(s.canonical, s.family) }} />
            ) : (
              <span key={s.canonical} className="dot missing" />
            ),
          )}
        </span>
        {have} of {r.ingredients_needed} in your kitchen
      </span>
      <span className="recipe-title">{displayName(r.name)}</span>
      <span className="recipe-meta">
        <span>{r.minutes} min</span>
        {r.calories != null && <span>{Math.round(r.calories)} kcal</span>}
        {r.protein_g != null && <span>{Math.round(r.protein_g)} g protein</span>}
      </span>
      {r.missing.length > 0 ? (
        r.missing.map((m) => (
          <span key={m} className="swap-line">
            Needs <strong>{pretty(m)}</strong>
            {r.subs?.[m] ? (
              <>
                {" "}— <em>use your {pretty(r.subs[m])} instead</em>
              </>
            ) : null}
          </span>
        ))
      ) : (
        <span className="recipe-tags">
          {r.like_your && <span className="tag-taste">Like your {displayName(r.like_your.name)}</span>}
          {covers ? (
            <span className="tag-fit">Covers today's {MACRO_LABELS[focus!.macro]}</span>
          ) : (
            r.macro_fit != null && r.macro_fit >= 0.8 && <span className="tag-fit">Fits what's left today</span>
          )}
        </span>
      )}
    </button>
  );
}

/** "How to read this list": shown until dismissed, back any time via "?". */
function FeedGuide({ onClose }: { onClose: () => void }) {
  return (
    <Guide
      id="feed-guide"
      title="How to read this list"
      onClose={onClose}
      items={[
        {
          term: (
            <>
              <span className="dots" aria-hidden="true">
                <span className="dot" style={{ background: "#D2553B" }} />
                <span className="dot" style={{ background: "#5B7F3F" }} />
                <span className="dot" style={{ background: "#E3B55B" }} />
                <span className="dot missing" />
              </span>
              <span className="visually-hidden">Coloured dots</span>
            </>
          ),
          text: "Each dot is one of the recipe's main ingredients, coloured by kind of food. A dashed dot is one you don't have.",
        },
        {
          term: "5 of 5 in your kitchen",
          text: "How many of those you have. Salt, pepper, oil, butter, flour and sugar are assumed, so they never count as missing.",
        },
        {
          term: "Like your Cherry Tomato Pasta",
          termClass: "tag-taste",
          text: "The dish you've cooked that this recipe is closest to, by its main ingredients. Recipes close to what you cook rank higher; dishes you marked Not for me don't count. It only appears when the match is close.",
        },
        {
          term: "Fits what's left today",
          termClass: "tag-fit",
          text: "The dish's mix of protein, carbs and fat suits the calories and macros you still have open today.",
        },
        {
          term: "One away · Two away",
          text: "Recipes you could cook after buying one or two things. If something in your kitchen works instead, the card says so.",
        },
      ]}
    />
  );
}
