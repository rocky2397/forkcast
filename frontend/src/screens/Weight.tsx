import { useState } from "react";
import { api, type BurnEstimate, type WeightSummary } from "../api";

/** D41: weigh-ins, the smoothed trend, and the path to the goal weight. */

const kg = (n: number) => `${n.toLocaleString("en", { maximumFractionDigits: 1 })} kg`;

/** "late March": a projection from a few weeks of noisy weigh-ins isn't good
 *  to the day, and a day-exact date jumps with every weigh-in. */
function roughDate(iso: string) {
  const d = new Date(`${iso}T12:00:00`);
  const part = d.getDate() <= 10 ? "early" : d.getDate() <= 20 ? "mid" : "late";
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return `${part} ${d.toLocaleDateString("en-GB", { month: "long", ...(sameYear ? {} : { year: "numeric" }) })}`;
}

function statusText(w: WeightSummary): string | null {
  const p = w.projection;
  const pace = w.rate_kg_per_week;
  const signed = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1)}`;
  const paceText = pace == null ? "" : `${signed(pace)} kg a week`;
  const planText = p ? `plan ${signed(p.planned_kg_per_week)}` : "";
  switch (w.status) {
    case "not_enough_data":
      return "Weigh in a few times over the next week and Forkcast will show your pace.";
    case "at_goal":
      return "You're at your goal weight.";
    case "drifting":
      return p ? `You're ${kg(Math.abs(p.remaining_kg))} from your goal.` : null;
    case "ahead":
      return `Ahead of plan: ${paceText} over the last 3 weeks (${planText}).`;
    case "on_track":
      return `On track: ${paceText} over the last 3 weeks (${planText}).`;
    case "behind":
      return `Behind plan: ${paceText} over the last 3 weeks (${planText}).`;
    case "stalled":
      return "No clear change over the last 3 weeks. That's common for a while: water can hide fat loss.";
    default:
      return pace == null ? null : `Your trend: ${paceText} over the last 3 weeks.`;
  }
}

const kcal = (n: number) => `${Math.round(n).toLocaleString("en")} kcal`;

/** D65: one weigh-in spans no days yet, but it isn't nothing: say what's there. */
function weighIns(count: number, span: number, needed: number): string {
  if (count === 0) return `no weigh-ins yet (they need to spread over ${needed} days)`;
  if (count === 1) return `1 weigh-in so far; the next ones should spread over ${needed} days`;
  if (span === 0) return `${count} weigh-ins so far, to spread over ${needed} days`;
  return `${count} weigh-ins spread over ${span} of the ${needed} days it needs`;
}

/** D45: what you burn, and whether it's learned yet. */
function BurnLine({ b }: { b: BurnEstimate }) {
  if (b.measured == null) {
    const days = Math.min(b.complete_days, b.needed_days);
    const span = Math.min(b.weigh_in_days, b.needed_span);
    return (
      <p className="weight-status burn-line">
        <strong>What you burn: about {kcal(b.formula)} a day</strong>, from a formula for your body and activity. After
        about two weeks of complete days and weigh-ins, Forkcast learns your real number from them. So far:{" "}
        {days} of {b.needed_days} complete days, and {weighIns(b.weigh_ins ?? 0, span, b.needed_span)}.
      </p>
    );
  }
  const weeks = Math.round(b.window_days / 7);
  return (
    <p className="weight-status burn-line">
      <strong>What you burn: about {kcal(b.burn)} a day</strong>, learned from your meals and weigh-ins over the last{" "}
      {weeks} weeks (the formula says {kcal(b.formula)}). Your targets use it.
      {b.limited ? (
        <>
          {" "}
          Your log points to about {kcal(b.measured)}, but Forkcast moves at most 15% away from the formula.
          {b.measured < b.formula && " If meals are missing from your log, what you burn looks lower than it is."}
        </>
      ) : (
        b.trust < 0.7 && " It leans on the formula until there's more data."
      )}
    </p>
  );
}

function Chart({ w }: { w: WeightSummary }) {
  const entries = w.entries;
  if (entries.length < 2 && !w.projection) return null;
  const day = (iso: string) => new Date(`${iso}T12:00:00`).getTime() / 86400000;
  const goal = w.projection?.goal_kg;
  const end = w.projection?.plan_date ?? w.today;
  const x0 = day(entries[0].date);
  const x1 = Math.max(day(end), day(w.today), x0 + 7);
  const ys = [...entries.flatMap((e) => [e.weight_kg, e.trend_kg]), ...(goal != null ? [goal] : [])];
  const pad = 0.6;
  const y0 = Math.min(...ys) - pad;
  const y1 = Math.max(...ys) + pad;
  const W = 320;
  const H = 142;
  const plotH = 124; // room for the date labels underneath
  const sx = (d: number) => 8 + ((d - x0) / (x1 - x0)) * (W - 16);
  const sy = (v: number) => 8 + ((y1 - v) / (y1 - y0)) * (plotH - 16);
  const short = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const trend = entries.map((e) => `${sx(day(e.date)).toFixed(1)},${sy(e.trend_kg).toFixed(1)}`).join(" ");
  const last = entries[entries.length - 1];
  const label =
    `Weight chart: ${entries.length} weigh-ins, trend ${w.trend_kg} kg` +
    (goal != null ? `, goal ${goal} kg${w.projection?.plan_date ? ` by ${roughDate(w.projection.plan_date)}` : ""}` : "");
  return (
    <svg className="weight-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {goal != null && (
        <>
          <line className="goal-line" x1={8} x2={W - 8} y1={sy(goal)} y2={sy(goal)} />
          <text className="goal-label" x={10} y={sy(goal) - 5}>
            Goal {kg(goal)}
          </text>
        </>
      )}
      {w.projection?.plan_date && (
        <line
          className="plan-line-svg"
          x1={sx(day(last.date))}
          y1={sy(last.trend_kg)}
          x2={sx(day(w.projection.plan_date))}
          y2={sy(w.projection.goal_kg)}
        />
      )}
      {entries.map((e) => (
        <circle key={e.id} className="weigh-in" cx={sx(day(e.date))} cy={sy(e.weight_kg)} r={2.6} />
      ))}
      {entries.length > 1 && <polyline className="trend-line" points={trend} />}
      <text className="goal-label" x={8} y={H - 2}>
        {short(entries[0].date)}
      </text>
      <text className="goal-label" x={W - 8} y={H - 2} textAnchor="end">
        {w.projection?.plan_date ? `${short(w.projection.plan_date)} (plan)` : short(w.today)}
      </text>
    </svg>
  );
}

export function WeightCard({ initial, onChange }: { initial: WeightSummary; onChange: () => void }) {
  const [w, setW] = useState(initial);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loggedToday = w.entries.some((e) => e.date === w.today);

  async function save() {
    const n = Number(value.replace(",", "."));
    if (!n) return;
    // D58: the app's own words, not the browser's (which spoke German in an English app).
    if (n < 35 || n > 250) {
      setError("Enter a weight between 35 and 250 kg.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setW(await api.logWeight(n));
      setValue("");
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function undoLast() {
    const last = w.entries[w.entries.length - 1];
    if (!last) return;
    setW(await api.deleteWeight(last.id));
    onChange();
  }

  const status = statusText(w);
  const p = w.projection;
  return (
    <section className="weight-card" aria-labelledby="weight-title">
      <h2 id="weight-title" className="section-title">
        Weight{w.trend_kg != null && <span className="weight-now"> · trend {kg(w.trend_kg)}</span>}
      </h2>
      <Chart w={w} />
      {status && <p className="weight-status">{status}</p>}
      {p && (p.actual_date || p.plan_date) && (
        <p className="weight-dates">
          {p.actual_date && (
            <>
              At this pace: <strong>{kg(p.goal_kg)} around {roughDate(p.actual_date)}</strong>.{" "}
            </>
          )}
          {p.plan_date && <>The plan says {roughDate(p.plan_date)}.</>}
        </p>
      )}
      {w.burn && <BurnLine b={w.burn} />}
      {w.too_fast && (
        <p className="weight-status warn-text">
          You're losing more than 1% of your weight a week. Faster isn't better: it costs muscle and is hard to keep up.
        </p>
      )}
      <form
        className="weigh-in-form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <label>
          <span className="visually-hidden">Today's weight in kg</span>
          <input
            type="number"
            inputMode="decimal"
            step={0.1}
            min={35}
            max={250}
            placeholder={loggedToday ? "Weighed in today" : "Today's weight, kg"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <button type="submit" className="btn secondary" disabled={busy || !value}>
          Log weight
        </button>
      </form>
      {error && <p className="feedback error">{error}</p>}
      <p className="progress-hint">
        Weigh in the same way each time, ideally in the morning. The line is a smoothed trend, so a day's water or salt
        doesn't throw it off; your daily target follows the trend.
        {w.entries.length > 0 && (
          <>
            {" "}
            <button type="button" className="link-button" onClick={undoLast}>
              Undo last weigh-in
            </button>
          </>
        )}
      </p>
    </section>
  );
}
