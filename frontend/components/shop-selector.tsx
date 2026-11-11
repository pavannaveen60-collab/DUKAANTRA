"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, Store } from "lucide-react";
import { clearToken, getToken } from "@/lib/api";
import { clearActiveShopId, setActiveShopId } from "@/lib/shop-context";
import { fetchMyShops, type Shop } from "@/services/shops";

export default function ShopSelector() {
  const router = useRouter();
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadShops() {
      if (!getToken()) {
        router.replace("/dashboard");
        return;
      }

      try {
        const result = await fetchMyShops();
        if (!active) return;
        if (result.length === 0) {
          router.replace("/onboarding/shop");
          return;
        }
        if (result.length === 1) {
          setActiveShopId(result[0].id);
          router.replace("/dashboard");
          return;
        }
        setShops(result);
      } catch (cause) {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Unable to load your shops.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadShops();
    return () => {
      active = false;
    };
  }, [router]);

  function chooseShop(shop: Shop) {
    setActiveShopId(shop.id);
    router.replace("/dashboard");
  }

  function handleSignOut() {
    clearToken();
    clearActiveShopId();
    router.replace("/dashboard");
  }

  if (loading) {
    return (
      <main className="login-screen">
        <div className="onboarding-status" role="status">
          <RefreshCw className="spin" size={22} />
          <p>Loading your shops...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="login-screen">
      <section className="login-card onboarding-card">
        <div className="login-brand">
          <div className="brand-mark"><Store size={24} /></div>
          <span>DUKAANTRA</span>
        </div>
        <div className="login-heading">
          <span className="eyebrow">MERCHANT WORKSPACE</span>
          <h1>Select a shop.</h1>
          <p>Choose which authorized shop you want to open.</p>
        </div>
        {error && <div className="login-error" role="alert">{error}</div>}
        <div className="shop-selection-list">
          {shops.map((shop) => (
            <button
              className="shop-selection-card"
              key={shop.id}
              onClick={() => chooseShop(shop)}
            >
              <span className="brand-mark"><Store size={20} /></span>
              <span>
                <strong>{shop.shop_name}</strong>
                <small>{shop.business_type}</small>
              </span>
            </button>
          ))}
        </div>
        <p className="onboarding-switch">
          <button type="button" onClick={handleSignOut}>Sign out</button>
        </p>
      </section>
    </main>
  );
}
