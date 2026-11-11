import assert from "node:assert/strict";
import test from "node:test";

import {
  fingerprintOrderRequest,
  readPendingOrderAttempts,
  removePendingOrderAttempt,
  writePendingOrderAttempts,
} from "./order-idempotency.ts";

function createStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
    entries: () => [...values.values()],
  };
}

test("canonical fingerprints ignore item order and split duplicate lines", async () => {
  const productA = "00000000-0000-0000-0000-000000000001";
  const productB = "00000000-0000-0000-0000-000000000002";
  const first = await fingerprintOrderRequest({
    customer_id: null,
    items: [
      { product_id: productA, quantity: 2 },
      { product_id: productB, quantity: 1 },
    ],
  });
  const equivalent = await fingerprintOrderRequest({
    customer_id: null,
    items: [
      { product_id: productB, quantity: 1 },
      { product_id: productA, quantity: 1 },
      { product_id: productA, quantity: 1 },
    ],
  });

  assert.equal(first, equivalent);
});

test("pending attempts are stored per shop without request payloads", async () => {
  const storage = createStorage();
  const fingerprint = await fingerprintOrderRequest({
    customer_id: null,
    items: [{ product_id: "00000000-0000-0000-0000-000000000001", quantity: 2 }],
  });
  const attempt = {
    fingerprint,
    key: "00000000-0000-4000-8000-000000000001",
  };

  writePendingOrderAttempts("shop-a", [attempt], storage);

  assert.deepEqual(readPendingOrderAttempts("shop-a", storage), [attempt]);
  assert.deepEqual(readPendingOrderAttempts("shop-b", storage), []);
  assert.equal(
    storage.entries().some((value) => value.includes("product_id")),
    false,
  );
  assert.deepEqual(removePendingOrderAttempt([attempt], fingerprint, attempt.key), []);
  writePendingOrderAttempts("shop-a", [], storage);
  assert.deepEqual(readPendingOrderAttempts("shop-a", storage), []);
});
