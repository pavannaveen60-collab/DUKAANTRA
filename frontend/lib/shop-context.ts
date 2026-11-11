import { getToken } from "@/lib/api";

const ACTIVE_SHOP_KEY = "dukaantra_active_shop_id";

export function getActiveShopId(): string {
  if (typeof window === "undefined" || !getToken()) {
    throw new Error("Sign in to access your shop.");
  }

  const shopId = window.localStorage.getItem(ACTIVE_SHOP_KEY);
  if (!shopId) {
    throw new Error("Select a shop to continue.");
  }

  return shopId;
}

export function setActiveShopId(shopId: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACTIVE_SHOP_KEY, shopId);
}

export function clearActiveShopId(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACTIVE_SHOP_KEY);
}
