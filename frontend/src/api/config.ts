export class ApiConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/$/, "") ?? "";

export function isApiConfigured() {
  return apiBaseUrl.length > 0;
}

export function getApiUrl(path: string) {
  if (!isApiConfigured()) {
    throw new ApiConfigurationError("VITE_API_BASE_URL is required before API requests can run.");
  }

  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}
