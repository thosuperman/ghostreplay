import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
  reload: () => void;
}

/** Run an async loader whenever `deps` change; ignores stale responses. */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    const gen = ++generation.current;
    setLoading(true);
    setError(undefined);
    loader()
      .then((d) => {
        if (gen === generation.current) setData(d);
      })
      .catch((e: unknown) => {
        if (gen === generation.current) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (gen === generation.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
