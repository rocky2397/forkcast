import { useState } from "react";

/** A screen's "how to read this" card: shown until dismissed, back via "?".
 *  The rule (D30): every indicator either says what it means or is explained
 *  here once, the first time someone meets it. Bump a key's version suffix
 *  when its guide changes, so it shows once more. */
export function useGuide(storageKey: string) {
  const [open, setOpen] = useState(() => {
    // Private-mode Safari throws on localStorage; then the guide just shows.
    try {
      return localStorage.getItem(storageKey) !== "1";
    } catch {
      return true;
    }
  });
  function close() {
    setOpen(false);
    try {
      localStorage.setItem(storageKey, "1");
    } catch {
      // Unwritable storage: it shows again next time, which is harmless.
    }
  }
  return { open, show: () => setOpen(true), close, toggle: () => (open ? close() : setOpen(true)) };
}
