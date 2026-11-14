import type { ReactNode } from "react";

/** The "?" that reopens a screen's guide (see useGuide). */
export function HelpButton({
  open,
  onToggle,
  label,
  controls,
}: {
  open: boolean;
  onToggle: () => void;
  label: string;
  controls: string;
}) {
  return (
    <button className="help-btn" aria-label={label} aria-expanded={open} aria-controls={controls} onClick={onToggle}>
      ?
    </button>
  );
}

export function Guide({
  id,
  title,
  items,
  onClose,
}: {
  id: string;
  title: string;
  items: { term: ReactNode; text: ReactNode; termClass?: string }[];
  onClose: () => void;
}) {
  return (
    <section id={id} className="guide" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="guide-title">
        {title}
      </h2>
      <dl className="guide-list">
        {items.map((item, i) => (
          <div key={i}>
            <dt className={item.termClass}>{item.term}</dt>
            <dd>{item.text}</dd>
          </div>
        ))}
      </dl>
      <button className="btn guide-close" onClick={onClose}>
        Got it
      </button>
    </section>
  );
}
