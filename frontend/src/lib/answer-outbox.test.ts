import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it } from "vitest";
import {
  getAnswerOutbox,
  pruneStaleAnswerOutbox,
  removeAnswerOutbox,
  saveAnswerOutbox,
  type AnswerOutboxRecord,
} from "@/lib/answer-outbox";

const record = (overrides: Partial<AnswerOutboxRecord> = {}): AnswerOutboxRecord => ({
  idempotencyKey: overrides.idempotencyKey ?? crypto.randomUUID(),
  sessionId: "session-1",
  questionId: "question-1",
  blob: new Blob(["x"]),
  recordedDurationMs: 1000,
  endedBy: "USER_BUTTON",
  createdAt: new Date().toISOString(),
  ...overrides,
});

beforeEach(async () => {
  await new Promise<void>((resolve) => {
    const deleteRequest = indexedDB.deleteDatabase("facefit-answer-outbox");
    deleteRequest.onsuccess = () => resolve();
    deleteRequest.onerror = () => resolve();
  });
});

describe("answer-outbox", () => {
  it("round-trips a saved record by session and question", async () => {
    const saved = record();
    await saveAnswerOutbox(saved);

    await expect(getAnswerOutbox("session-1", "question-1")).resolves.toMatchObject({
      idempotencyKey: saved.idempotencyKey,
    });
    await expect(getAnswerOutbox("session-1", "other-question")).resolves.toBeNull();
  });

  it("returns the newest record when a question was retried", async () => {
    await saveAnswerOutbox(record({ idempotencyKey: "old", createdAt: "2026-01-01T00:00:00Z" }));
    await saveAnswerOutbox(record({ idempotencyKey: "new", createdAt: "2026-01-02T00:00:00Z" }));

    await expect(getAnswerOutbox("session-1", "question-1")).resolves.toMatchObject({ idempotencyKey: "new" });
  });

  it("removes a record by key", async () => {
    const saved = record();
    await saveAnswerOutbox(saved);
    await removeAnswerOutbox(saved.idempotencyKey);

    await expect(getAnswerOutbox("session-1", "question-1")).resolves.toBeNull();
  });

  it("prunes only records older than the stale window", async () => {
    const fresh = record({ idempotencyKey: "fresh", createdAt: "2026-08-01T00:00:00Z" });
    const stale = record({ idempotencyKey: "stale", createdAt: "2026-06-01T00:00:00Z" });
    await saveAnswerOutbox(fresh);
    await saveAnswerOutbox(stale);

    await pruneStaleAnswerOutbox(new Date("2026-08-05T00:00:00Z").getTime());

    await expect(getAnswerOutbox("session-1", "question-1")).resolves.toMatchObject({ idempotencyKey: "fresh" });
  });
});
