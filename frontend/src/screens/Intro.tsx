import { useState } from "react";
import { api, isDemo, type Profile, type Targets, type WeightPlan } from "../api";
import { ProfileForm } from "./ProfileForm";
import { rememberSample } from "../sample";
import { PlanLine } from "./Today";

/** First visit (D68, replacing D16's walkthrough).
 *
 *  A growth PM's review: the old first screen explained how to set the app up, not
 *  what you get, and the profile could be skipped although nothing fits your
 *  day without it. So: what you get, how it works, your targets (required;
 *  the demo offers a made-up person instead of typing), then the payoff,
 *  your day in numbers. Anyone who already has a profile never sees this.
 */
type Stage = "value" | "how" | "profile" | "day";

const STEPS = [
  {
    title: "Your kitchen",
    text: "Scan your shopping or type it in, in English or German. You tick a checklist first, so nothing misread is saved.",
  },
  {
    title: "Pick a meal",
    text: "87,861 recipes, best fits first: what you have, the dishes you like and what's left of today's calories and protein.",
  },
  {
    title: "Say you ate it",
    text: "Tap “I ate it”, or log anything else by photo, barcode or a few words. With your weigh-ins, Forkcast learns what you really burn.",
  },
];

export function Intro({
  startAt,
  onWelcomed,
  onDone,
}: {
  /** "profile" for someone who has seen the first two screens before. */
  startAt: "value" | "profile";
  onWelcomed: () => void;
  /** Where to go next: the meal picks, or Today. */
  onDone: (next: "cook" | "today") => void;
}) {
  const [stage, setStage] = useState<Stage>(startAt);
  const [saved, setSaved] = useState<{ targets: Targets; plan: WeightPlan | null; sample: boolean } | null>(null);

  function to(next: Stage) {
    setStage(next);
    window.scrollTo(0, 0);
  }

  if (stage === "value")
    return (
      <div className="intro">
        <p className="kicker">Forkcast</p>
        <h1>Meals that fit your fridge and your goal.</h1>
        <p className="intro-tagline">
          It picks recipes from what you already have and what's left of today's calories and protein, and learns
          what your body really burns.
        </p>
        <button className="btn" onClick={() => to("how")}>
          Get started
        </button>
        {isDemo() && <p className="intro-note">A demo: no sign-up, private to this browser.</p>}
      </div>
    );

  if (stage === "how")
    return (
      <div className="intro">
        <p className="kicker">How it works</p>
        <h1>Three steps a day</h1>
        <ol className="intro-steps">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <span className="intro-num" aria-hidden="true">
                {i + 1}
              </span>
              <div>
                <strong>{s.title}</strong>
                <p>{s.text}</p>
              </div>
            </li>
          ))}
        </ol>
        {isDemo() && (
          // D57: what this demo kitchen starts with, said before anyone wonders.
          <p className="intro-note intro-demo">
            This demo kitchen already has 25 ingredients and two dishes cooked earlier this week, so you can pick a
            meal straight away.
          </p>
        )}
        <button
          className="btn"
          onClick={() => {
            api.step("welcome_finished");
            onWelcomed();
            to("profile");
          }}
        >
          Set my targets
        </button>
        <button className="intro-skip" onClick={() => to("value")}>
          Back
        </button>
      </div>
    );

  if (stage === "profile")
    return (
      <div className="screen intro-profile">
        <ProfileForm
          initial={null}
          kicker="Last step"
          offerSample={isDemo()}
          onSaved={(_p: Profile, targets, plan, sample) => {
            rememberSample(sample);
            setSaved({ targets, plan, sample });
            to("day");
          }}
        />
      </div>
    );

  const t = saved!.targets;
  return (
    <div className="intro">
      <p className="kicker">{saved!.sample ? "The sample person's targets" : "Your targets"}</p>
      <h1>Here's your day</h1>
      <div className="day-targets">
        <div>
          <strong>{Math.round(t.calories).toLocaleString("en-GB")}</strong> kcal a day
        </div>
        <div>
          <strong>{Math.round(t.protein_g)} g</strong> protein
        </div>
      </div>
      {saved!.plan && <PlanLine plan={saved!.plan} />}
      <p className="day-note">
        That's a formula's estimate. After about two weeks of weigh-ins and complete days, Forkcast learns what you
        really burn and adjusts it.
      </p>
      <button className="btn" onClick={() => onDone("cook")}>
        See meals that fit
      </button>
      <button className="intro-skip" onClick={() => onDone("today")}>
        See my day
      </button>
    </div>
  );
}
