import { getApiUrl } from "@/api/config";

type JsonRecord = Record<string, unknown>;

export type ApiFieldError = {
  field: string;
  reason: string;
  rejectedValue?: unknown;
};

export type ApiErrorPayload = {
  fieldErrors?: ApiFieldError[];
  retryable?: boolean;
  retryAfterSec?: number | null;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly payload: ApiErrorPayload | null;

  constructor({ status, code, message, requestId, payload }: {
    status: number;
    code: string;
    message: string;
    requestId: string | null;
    payload: ApiErrorPayload | null;
  }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.payload = payload;
  }
}

export type JsonRequestOptions = Omit<RequestInit, "body" | "headers"> & {
  body?: unknown;
  headers?: HeadersInit;
  accessToken?: string | null;
};

export type MultipartRequestOptions = Omit<RequestInit, "body" | "headers"> & {
  formData: FormData;
  headers?: HeadersInit;
  accessToken?: string | null;
};

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isSuccessEnvelope(value: unknown): value is JsonRecord & { success: true; data: unknown } {
  return isRecord(value) && value.success === true && "data" in value;
}

function getErrorPayload(value: unknown): ApiErrorPayload | null {
  if (!isRecord(value) || !isRecord(value.data)) return null;

  const fieldErrors = Array.isArray(value.data.fieldErrors)
    ? value.data.fieldErrors.filter(isRecord).flatMap((error) => {
      if (typeof error.field !== "string" || typeof error.reason !== "string") return [];
      return [{ field: error.field, reason: error.reason, rejectedValue: error.rejectedValue }];
    })
    : undefined;

  return {
    fieldErrors,
    retryable: typeof value.data.retryable === "boolean" ? value.data.retryable : undefined,
    retryAfterSec: typeof value.data.retryAfterSec === "number" || value.data.retryAfterSec === null
      ? value.data.retryAfterSec
      : undefined,
  };
}

function toApiError(response: Response, body: unknown) {
  const error = isRecord(body) && isRecord(body.error) ? body.error : body;
  const code = isRecord(error) && typeof error.code === "string" ? error.code : "HTTP_ERROR";
  const message = isRecord(error) && typeof error.message === "string"
    ? error.message
    : "요청을 처리하지 못했습니다.";
  const requestId = isRecord(error) && typeof error.requestId === "string"
    ? error.requestId
    : response.headers.get("X-Request-Id");

  return new ApiError({
    status: response.status,
    code,
    message,
    requestId,
    payload: getErrorPayload(body),
  });
}

export type ApiResponse<T> = {
  data: T;
  headers: Headers;
  status: number;
};

async function readEnvelopeResponse<T>(path: string, requestInit: RequestInit, headers: Headers, body: BodyInit | undefined): Promise<ApiResponse<T>> {
  const response = await fetch(getApiUrl(path), {
    ...requestInit,
    headers,
    credentials: "include",
    body,
  });

  if (response.status === 204) return { data: undefined as T, headers: response.headers, status: response.status };

  const contentType = response.headers.get("Content-Type") ?? "";
  if (response.ok && !contentType.includes("application/json")) {
    return { data: undefined as T, headers: response.headers, status: response.status };
  }
  const responseBody = contentType.includes("application/json") ? await response.json() as unknown : null;

  if (!response.ok || !isSuccessEnvelope(responseBody)) throw toApiError(response, responseBody);

  return { data: responseBody.data as T, headers: response.headers, status: response.status };
}

async function readEnvelope<T>(path: string, requestInit: RequestInit, headers: Headers, body: BodyInit | undefined): Promise<T> {
  return (await readEnvelopeResponse<T>(path, requestInit, headers, body)).data;
}

export async function requestJson<T>(path: string, options: JsonRequestOptions = {}): Promise<T> {
  const { accessToken, body: requestBody, headers: requestHeaders, ...requestInit } = options;
  const headers = new Headers(requestHeaders);
  headers.set("Accept", "application/json");

  if (requestBody !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  return readEnvelope<T>(path, requestInit, headers, requestBody === undefined ? undefined : JSON.stringify(requestBody));
}

export async function requestJsonWithResponse<T>(path: string, options: JsonRequestOptions = {}): Promise<ApiResponse<T>> {
  const { accessToken, body: requestBody, headers: requestHeaders, ...requestInit } = options;
  const headers = new Headers(requestHeaders);
  headers.set("Accept", "application/json");

  if (requestBody !== undefined) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  return readEnvelopeResponse<T>(path, requestInit, headers, requestBody === undefined ? undefined : JSON.stringify(requestBody));
}

export async function requestMultipart<T>(path: string, options: MultipartRequestOptions): Promise<T> {
  const { accessToken, formData, headers: requestHeaders, ...requestInit } = options;
  const headers = new Headers(requestHeaders);
  headers.set("Accept", "application/json");
  headers.delete("Content-Type");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  return readEnvelope<T>(path, requestInit, headers, formData);
}

export type BinaryRequestOptions = {
  accessToken?: string | null;
  signal?: AbortSignal;
};

export async function requestBinary(url: string, { accessToken, signal }: BinaryRequestOptions = {}) {
  const targetUrl = /^https?:\/\//.test(url) ? url : getApiUrl(url);
  const headers = new Headers({ Accept: "audio/mpeg, application/json" });
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  const response = await fetch(targetUrl, { signal, headers, credentials: "include" });
  if (!response.ok && response.status !== 202) throw new ApiError({
    status: response.status,
    code: response.status === 401 ? "PLAYBACK_ACCESS_EXPIRED" : "MEDIA_REQUEST_FAILED",
    message: "미디어를 재생하지 못했습니다.",
    requestId: response.headers.get("X-Request-Id"),
    payload: null,
  });

  return response;
}
