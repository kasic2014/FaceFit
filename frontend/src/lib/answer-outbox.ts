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

function openDatabase() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(databaseName, 1);
    request.onerror = () =>
      reject(request.error ?? new Error("Unable to open answer outbox."));
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(storeName))
        database.createObjectStore(storeName, { keyPath: "idempotencyKey" });
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
    store.getAll(),
  );
  return (
    records
      .filter(
        (record) =>
          record.sessionId === sessionId && record.questionId === questionId,
      )
      .sort((left, right) =>
        right.createdAt.localeCompare(left.createdAt),
      )[0] ?? null
  );
}
