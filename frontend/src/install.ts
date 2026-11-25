// D73: putting Forkcast on the home screen. The app could always be installed
// (it has a manifest and works offline), but nothing said so: iPhones never
// offer it, Android only sometimes, and inside the Hugging Face page (a frame)
// it can't be installed at all.
import { api } from "./api";

/** Chrome's install offer, kept until the button asks for it. Not in TypeScript's DOM types. */
interface InstallOffer extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

let offer: InstallOffer | null = null;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((f) => f());

/** Called once at startup: the offer can come before any screen is drawn. */
export function watchInstall() {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // our own button asks instead of the browser's bar
    offer = e as InstallOffer;
    changed();
  });
  window.addEventListener("appinstalled", () => {
    offer = null;
    api.step("app_installed");
    changed();
  });
}

export function onInstallChange(f: () => void): () => void {
  listeners.add(f);
  return () => listeners.delete(f);
}

/** Opened from the home screen (or as an installed app on a computer). */
export function installed(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function inFrame(): boolean {
  try {
    return window.self !== window.top;
  } catch {
    return true; // a frame on another site may not even say
  }
}

function iPhoneOrIPad(): boolean {
  // iPads say "Macintosh" but have a touch screen.
  return /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
}

/** How this browser can install it, if it can and hasn't yet:
 *  "offer": a button (Chrome, Edge, Samsung Internet); "ios": Share, then Add to
 *  Home Screen; "frame": open it on its own page first. */
export type InstallWay = "offer" | "ios" | "frame";

export function installWay(): InstallWay | null {
  if (installed()) return null;
  if (inFrame()) return "frame";
  if (offer) return "offer";
  if (iPhoneOrIPad()) return "ios";
  return null;
}

/** Shows the browser's own install question. */
export async function install(): Promise<void> {
  const o = offer;
  if (!o) return;
  offer = null; // it can only be asked once
  await o.prompt();
  await o.userChoice;
  changed();
}
