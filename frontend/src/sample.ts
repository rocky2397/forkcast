import type { Profile } from "./api";

/** D68: the demo's made-up person, for visitors who only want to look around. */
export const SAMPLE_PERSON: Profile = {
  sex: "f",
  age: 34,
  height_cm: 168,
  weight_kg: 68,
  activity: "moderate",
  goal: "cut",
  goal_weight_kg: 64,
  pace: "gentle", // steady hits the deficit cap, and the payoff screen would open on a warning
};

// D68: whether this browser's profile is the made-up person, so Today can say
// so until someone puts in their own numbers. Private-mode storage failures
// just mean the note doesn't show.
const SAMPLE_KEY = "forkcast.sample.v1";
export function usingSample(): boolean {
  try {
    return localStorage.getItem(SAMPLE_KEY) === "1";
  } catch {
    return false;
  }
}
export function rememberSample(on: boolean) {
  try {
    if (on) localStorage.setItem(SAMPLE_KEY, "1");
    else localStorage.removeItem(SAMPLE_KEY);
  } catch {
    // see above
  }
}
