import { useState } from "react";
import { api, type DayClass, type Progress } from "../api";

/** D40: streak, the last 14 days and the weekly recap. It rewards being on
 *  target, never eating less: a day under your minimum doesn't count. */

const LABEL: Record<DayClass, string> = {
  deficit: "Deficit",
  maintenance: "Maintenance",
  surplus: "Surplus",
  below_minimum: "Below your minimum",
  not_logged: "Not logged",
  today: "Today, in progress",
};

const fmt = (n: number) => Math.round(n).toLocaleString("en");

function dayName(iso: string) {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

/** D42: "Done for today?" — the user says whether a day's log is complete. */
export function DayCheck({ progress, onChange }: { progress: Progress; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  const today = progress.strip[progress.strip.length - 1];
  const yesterday = progress.strip[progress.strip.length - 2];
  async function answer(day: string, complete: boolean | null) {
    setBusy(true);
    try {
      await api.checkDay(day, complete);
      onChange();
    } finally {
      setBusy(false);
    }
  }
  if (yesterday && yesterday.meals > 0 && yesterday.confirmed === null) {
    return (
      <div className="day-check" role="group" aria-label="Was yesterday complete?">
        <p>
          Was yesterday's log complete? {fmt(yesterday.calories)} kcal in {plural(yesterday.meals, "meal")}.
        </p>
        <div className="day-check-actions">
          <button type="button" className="btn secondary" disabled={busy} onClick={() => answer(yesterday.date, true)}>
            Yes, complete
          </button>
          <button type="button" className="btn secondary" disabled={busy} onClick={() => answer(yesterday.date, false)}>
            No, I missed some
          </button>
        </div>
      </div>
    );
  }
  if (!today || today.meals === 0) return null;
  if (today.confirmed !== null) {
    return (
      <p className="day-check-done">
        {today.confirmed ? "Today is marked complete." : "Today is marked incomplete and won't count."}{" "}
        <button type="button" className="link-button" disabled={busy} onClick={() => answer(today.date, null)}>
          Undo
        </button>
      </p>
    );
  }
  return (
    <div className="day-check" role="group" aria-label="Done for today?">
      <p>
        Done for today?
        {today.meals === 1 && " Only one meal logged so far."} Confirming tells your streak this day is complete.
      </p>
      <div className="day-check-actions">
        <button type="button" className="btn secondary" disabled={busy} onClick={() => answer(today.date, true)}>
          Done for today
        </button>
      </div>
    </div>
  );
}

export function ProgressCard({ progress }: { progress: Progress }) {
  const { streak, strip, totals, recap } = progress;
  const logged = totals.days - totals.not_logged;
  return (
    <section className="progress-card" aria-labelledby="progress-title">
      <h2 id="progress-title" className="section-title">
        {streak > 0 ? `${plural(streak, "day")} in a row on target` : "Your days"}
      </h2>
      <p className="progress-hint">
        A day is on target when you ate within 10% of your {fmt(progress.target)} kcal. Days you logged less than half of
        it count as not logged and don't break the streak.
      </p>

      <ol className="day-strip" aria-label="The last 14 days">
        {strip.map((d) => (
          <li
            key={d.date}
            className={`day-dot ${d.status}${d.on_target ? " on-target" : ""}`}
            title={`${dayName(d.date)}: ${d.status === "not_logged" ? "not logged" : `${fmt(d.calories)} kcal`}, ${LABEL[d.status].toLowerCase()}${d.on_target ? ", on target" : ""}`}
          >
            <span className="visually-hidden">
              {dayName(d.date)}: {LABEL[d.status]}
              {d.status !== "not_logged" && `, ${fmt(d.calories)} kcal`}
              {d.on_target && ", on target"}
            </span>
          </li>
        ))}
      </ol>
      <ul className="day-legend" aria-hidden="true">
        <li className="deficit">Deficit</li>
        <li className="maintenance">Maintenance</li>
        <li className="surplus">Surplus</li>
        <li className="not_logged">Not logged</li>
        <li className="legend-target">On target</li>
      </ul>

      <p className="progress-totals">
        Last {totals.days} days: <strong>{totals.deficit}</strong> in a deficit · <strong>{totals.maintenance}</strong> at
        maintenance · <strong>{totals.surplus}</strong> in a surplus
        {totals.below_minimum > 0 && (
          <>
            {" "}
            · <strong className="warn-text">{totals.below_minimum}</strong> below your minimum
          </>
        )}{" "}
        · {totals.not_logged} not logged. Measured against the {fmt(progress.burn)} kcal you burn.
      </p>
      {logged > 0 && totals.below_minimum >= 2 && (
        <p className="progress-hint warn-text">
          Eating under {fmt(progress.minimum)} kcal regularly isn't a faster route: those days never count as on target.
        </p>
      )}

      <div className="recap" aria-labelledby="recap-title">
        <h3 id="recap-title" className="recap-title">
          Last {recap.days} days
        </h3>
        <ul className="recap-list">
          <li>
            <strong>{recap.cooked}</strong> {recap.cooked === 1 ? "meal" : "meals"} cooked
            {recap.new_recipes > 0 && <>, {plural(recap.new_recipes, "new recipe")}</>}
          </li>
          <li>
            <strong>{recap.days_on_target}</strong> of {recap.days_logged} logged {recap.days_logged === 1 ? "day" : "days"}{" "}
            on target
          </li>
          <li>
            <strong>{recap.protein_days}</strong> {recap.protein_days === 1 ? "day" : "days"} with your protein
          </li>
          {recap.balance && (
            <li>
              {recap.balance.avg_per_day <= 0 ? (
                <>
                  On average <strong>{fmt(-recap.balance.avg_per_day)} kcal a day under</strong> what you burn
                </>
              ) : (
                <>
                  On average <strong>{fmt(recap.balance.avg_per_day)} kcal a day over</strong> what you burn
                </>
              )}
              {recap.balance.planned_per_day !== 0 && (
                <>
                  {" "}
                  (plan: {fmt(Math.abs(recap.balance.planned_per_day))} {recap.balance.planned_per_day < 0 ? "under" : "over"})
                </>
              )}
              , over {plural(recap.balance.days, "logged day")}: roughly {Math.abs(recap.balance.est_kg).toFixed(1)} kg{" "}
              {recap.balance.est_kg <= 0 ? "less" : "more"}, as an estimate
            </li>
          )}
          {recap.liked > 0 && (
            <li>
              <strong>{recap.liked}</strong> {recap.liked === 1 ? "dish" : "dishes"} you liked
            </li>
          )}
        </ul>
      </div>
    </section>
  );
}
