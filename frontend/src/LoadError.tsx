// D66: a list that couldn't load says so, instead of looking empty.
export function LoadError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="load-error" role="alert">
      <p>{error}</p>
      <button type="button" className="btn secondary" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
