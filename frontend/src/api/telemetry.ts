import type { JsonRequestOptions } from "@/api/http";

type TelemetryProperty = string | number | boolean | null;

export type ClientEventName = "answer_upload_failed" | "answer_upload_succeeded" | "analysis_retry_requested" | "playback_access_failed";

export type ClientTelemetryEvent = {
  eventId: string;
  eventName: ClientEventName;
  occurredAt: string;
  sessionId: string | null;
  properties: Record<string, TelemetryProperty>;
};

export function createClientEvent(eventName: ClientEventName, sessionId: string | null, properties: Record<string, TelemetryProperty> = {}): ClientTelemetryEvent {
  return { eventId: crypto.randomUUID(), eventName, occurredAt: new Date().toISOString(), sessionId, properties };
}

export async function sendClientEvent(request: <T>(path: string, options?: JsonRequestOptions) => Promise<T>, event: ClientTelemetryEvent) {
  try {
    await request<void>("/api/v1/client-events", { method: "POST", body: event });
  } catch {
    // Telemetry must not block an interview or expose telemetry errors to the user.
  }
}
