// 업로드하지 못한 녹음을 기기(IndexedDB)에 보관한다.
// 수급자 이름 같은 식별정보는 넣지 않고 UUID와 날짜만 저장한다.
export interface PendingUpload {
  id: string;
  userId: string;
  recipientId: string;
  visitedOn: string;
  recordedAt: string;
  audio: Blob;
  lastError: string | null;
}

const DB_NAME = "csn-offline";
const STORE = "uploads";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE, { keyPath: "id" }).createIndex("userId", "userId");
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function run<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const req = fn(db.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  } finally {
    db.close();
  }
}

export async function savePending(u: PendingUpload): Promise<void> {
  await run("readwrite", (s) => s.put(u));
}

export function listPending(userId: string): Promise<PendingUpload[]> {
  return run("readonly", (s) => s.index("userId").getAll(userId));
}

export async function removePending(id: string): Promise<void> {
  await run("readwrite", (s) => s.delete(id));
}

export async function clearPending(userId: string): Promise<void> {
  for (const u of await listPending(userId)) await removePending(u.id);
}
