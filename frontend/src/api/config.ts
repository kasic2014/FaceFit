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
    throw new ApiConfigurationError("VITE_API_BASE_URL이 설정되지 않았습니다. 관리자에게 문의해 주세요.");
  }

  return `${apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
}
