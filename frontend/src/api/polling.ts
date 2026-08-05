import { ApiError } from "@/api/http";

export type PollingOptions<T> = {
  load: () => Promise<T>;
  shouldContinue: (value: T) => boolean;
  retryAfterMs?: (value: T) => number | null;
  onValue?: (value: T) => void;
  intervalMs: number | ((elapsedMs: number) => number);
  maxWaitMs: number;
  signal?: AbortSignal;
};

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      window.clearTimeout(timer);
      reject(new DOMException("Polling cancelled", "AbortError"));
    }, { once: true });
  });
}

export async function poll<T>(options: PollingOptions<T>): Promise<T> {
  const startedAt = Date.now();
  let retryCount = 0;

  while (true) {
    try {
      const value = await options.load();
      options.onValue?.(value);
      if (!options.shouldContinue(value)) return value;
      if (Date.now() - startedAt >= options.maxWaitMs) return value;
      const retryAfterMs = options.retryAfterMs?.(value);
      const intervalMs = typeof options.intervalMs === "function"
        ? options.intervalMs(Date.now() - startedAt)
        : options.intervalMs;
      await wait(retryAfterMs ?? intervalMs, options.signal);
      retryCount = 0;
    } catch (error) {
      const retryable = error instanceof ApiError && [429, 502, 503].includes(error.status) && retryCount < 3;
      if (!retryable) throw error;
      const retryAfterMs = error.payload?.retryAfterSec === undefined || error.payload.retryAfterSec === null
        ? (typeof options.intervalMs === "function" ? options.intervalMs(Date.now() - startedAt) : options.intervalMs) * (2 ** retryCount)
        : error.payload.retryAfterSec * 1000;
      retryCount += 1;
      await wait(retryAfterMs, options.signal);
    }
  }
}

export function createIdempotencyKey() {
  return crypto.randomUUID();
}
