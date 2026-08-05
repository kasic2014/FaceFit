import { ApiError } from "@/api/http";

export async function withAuthRetry<T>(
  canRetry: boolean,
  run: (accessToken: string | null) => Promise<T>,
  getAccessToken: () => string | null,
  refresh: () => Promise<{ accessToken?: string | null } | null>,
): Promise<T> {
  try {
    return await run(getAccessToken());
  } catch (error) {
    if (!canRetry || !(error instanceof ApiError) || error.status !== 401) throw error;
    const refreshed = await refresh();
    if (!refreshed?.accessToken) throw error;
    return run(refreshed.accessToken);
  }
}
