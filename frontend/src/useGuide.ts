import { useState } from "react";

/** A screen's "how to read this" card, behind its "?".
 *
 *  The rule (D30): every indicator either says what it means or is explained
 *  here, the first time someone meets it. Since D58 the first visit shows a
 *  one-line pointer to the guide rather than the guide itself: on a phone the
 *  full card pushed the screen two to three screens down. Bump a key's version
 *  suffix when its guide changes, so the pointer shows once more. */
export function useGuide(storageKey: string) {
  const [open, setOpen] = useState(false);
  const [seen, setSeen] = useState(() => {
    // Private-mode Safari throws on localStorage; then the pointer just shows.
    try {
      return localStorage.getItem(storageKey) === "1";
    } catch {
      return false;
    }
  });
  function markSeen() {
    setSeen(true);
    try {
      localStorage.setItem(storageKey, "1");
    } catch {
      // Unwritable storage: the pointer shows again next time, which is harmless.
    }
  }
  const show = () => {
    markSeen();
    setOpen(true);
  };
  const close = () => {
    markSeen();
    setOpen(false);
  };
  return {
    open,
    /** The first-visit pointer: until the guide is opened or the pointer dismissed. */
    hint: !seen && !open,
    show,
    close,
    dismiss: markSeen,
    toggle: () => (open ? close() : show()),
  };
}
