import type { CreateOrderInput } from "@/services/orders";

export interface PendingOrderAttempt {
  fingerprint: string;
  key: string;
}

function storageKey(shopId: string): string {
  return `dukaantra_pending_order_attempts_${shopId}`;
}

function getStorage(storage?: Storage): Storage {
  if (storage) return storage;
  if (typeof window === "undefined") {
    throw new Error("Order retry state is only available in a browser.");
  }
  return window.localStorage;
}

export async function fingerprintOrderRequest(
  request: CreateOrderInput,
): Promise<string> {
  const quantities = new Map<string, number>();
  for (const item of request.items) {
    const productId = item.product_id.toLowerCase();
    quantities.set(
      productId,
      (quantities.get(productId) || 0) + item.quantity,
    );
  }

  const canonicalRequest = {
    customer_id: request.customer_id?.toLowerCase() ?? null,
    items: [...quantities.entries()]
      .sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))
      .map(([product_id, quantity]) => ({ product_id, quantity })),
  };
  const bytes = new TextEncoder().encode(JSON.stringify(canonicalRequest));
  const digest = await crypto.subtle.digest("SHA-256", bytes);

  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

export function readPendingOrderAttempts(
  shopId: string,
  storage?: Storage,
): PendingOrderAttempt[] {
  const serialized = getStorage(storage).getItem(storageKey(shopId));
  if (serialized === null) return [];

  let parsed: unknown;
  try {
    parsed = JSON.parse(serialized);
  } catch {
    throw new Error("Saved order retry details are invalid.");
  }

  if (
    !Array.isArray(parsed) ||
    !parsed.every(
      (attempt: unknown): attempt is PendingOrderAttempt =>
        typeof attempt === "object" &&
        attempt !== null &&
        "fingerprint" in attempt &&
        typeof attempt.fingerprint === "string" &&
        /^[a-f0-9]{64}$/.test(attempt.fingerprint) &&
        "key" in attempt &&
        typeof attempt.key === "string" &&
        /^[0-9a-f-]{36}$/i.test(attempt.key),
    )
  ) {
    throw new Error("Saved order retry details are invalid.");
  }

  return parsed;
}

export function writePendingOrderAttempts(
  shopId: string,
  attempts: PendingOrderAttempt[],
  storage?: Storage,
): void {
  const target = getStorage(storage);
  const key = storageKey(shopId);
  if (attempts.length === 0) {
    target.removeItem(key);
    return;
  }
  target.setItem(key, JSON.stringify(attempts));
}

export function removePendingOrderAttempt(
  attempts: PendingOrderAttempt[],
  fingerprint: string,
  key: string,
): PendingOrderAttempt[] {
  return attempts.filter(
    (attempt) =>
      attempt.fingerprint !== fingerprint || attempt.key !== key,
  );
}
