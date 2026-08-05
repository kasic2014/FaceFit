export type AnswerOutboxRecord = {
  idempotencyKey: string;
  sessionId: string;
  questionId: string;
  blob: Blob;
  recordedDurationMs: number;
  endedBy: "USER_BUTTON" | "SPACE_KEY" | "SILENCE_CONFIRMED";
  createdAt: string;
};

const databaseName = "facefit-answer-outbox";
const storeName = "answers";
const bySessionQuestionIndex = "bySessionQuestion";
const staleAfterMs = 7 * 24 * 60 * 60 * 1000;

function openDatabase() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(databaseName, 2);
    request.onerror = () =>
      reject(request.error ?? new Error("Unable to open answer outbox."));
    request.onupgradeneeded = () => {
      const database = request.result;
      const store = database.objectStoreNames.contains(storeName)
        ? request.transaction!.objectStore(storeName)
        : database.createObjectStore(storeName, { keyPath: "idempotencyKey" });
      if (!store.indexNames.contains(bySessionQuestionIndex))
        store.createIndex(bySessionQuestionIndex, ["sessionId", "questionId"]);
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
) {
  const database = await openDatabase();
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = database.transaction(storeName, mode);
      const request = run(transaction.objectStore(storeName));
      request.onerror = () =>
        reject(request.error ?? new Error("Answer outbox request failed."));
      request.onsuccess = () => resolve(request.result);
    });
  } finally {
    database.close();
  }
}

export async function saveAnswerOutbox(record: AnswerOutboxRecord) {
  await withStore("readwrite", (store) => store.put(record));
}

export async function removeAnswerOutbox(idempotencyKey: string) {
  await withStore("readwrite", (store) => store.delete(idempotencyKey));
}

export async function getAnswerOutbox(sessionId: string, questionId: string) {
  const records = await withStore<AnswerOutboxRecord[]>("readonly", (store) =>
    store.index(bySessionQuestionIndex).getAll([sessionId, questionId]),
  );
  return records.sort((left, right) => right.createdAt.localeCompare(left.createdAt))[0] ?? null;
}

// ponytail: uploaded answers are already removed by removeAnswerOutbox; this only sweeps
// answers abandoned mid-recording (tab closed, interview left) so storage doesn't grow forever.
export async function pruneStaleAnswerOutbox(now = Date.now()) {
  const records = await withStore<AnswerOutboxRecord[]>("readonly", (store) => store.getAll());
  const staleKeys = records
    .filter((record) => now - new Date(record.createdAt).getTime() > staleAfterMs)
    .map((record) => record.idempotencyKey);
  await Promise.all(staleKeys.map((key) => removeAnswerOutbox(key)));
}
