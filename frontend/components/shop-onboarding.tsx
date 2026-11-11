"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, Store } from "lucide-react";
import { clearToken, getToken } from "@/lib/api";
import {
  clearActiveShopId,
  getActiveShopId,
  setActiveShopId,
} from "@/lib/shop-context";
import { createShop, fetchMyShops, type Shop } from "@/services/shops";

export default function ShopOnboarding() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [shopName, setShopName] = useState("");
  const [businessType, setBusinessType] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");

  useEffect(() => {
    let active = true;

    async function checkOnboardingState() {
      if (!getToken()) {
        router.replace("/dashboard");
        return;
      }

      try {
        const shops = await fetchMyShops();
        if (!active) return;

        if (shops.length === 1) {
          setActiveShopId(shops[0].id);
          router.replace("/dashboard");
          return;
        }
        if (shops.length > 1) {
          let selectedShopId = "";
          try {
            selectedShopId = getActiveShopId();
          } catch {
            // A merchant with multiple shops must choose one explicitly.
          }
          if (shops.some((shop) => shop.id === selectedShopId)) {
            router.replace("/dashboard");
          } else {
            router.replace("/shops/select");
          }
          return;
        }
        setReady(true);
      } catch (cause) {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Unable to verify your shop access.",
          );
        }
      }
    }

    void checkOnboardingState();
    return () => {
      active = false;
    };
  }, [router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    const digits = phone.replace(/\D/g, "");
    if (digits.length < 7 || digits.length > 15) {
      setError("Enter a valid phone number with 7 to 15 digits.");
      return;
    }
    if (shopName.trim().length < 2 || businessType.trim().length < 2) {
      setError("Enter a shop name and business category.");
      return;
    }
    if (address.trim().length < 3) {
      setError("Enter your business address.");
      return;
    }

    setLoading(true);
    try {
      const shop: Shop = await createShop({
        shop_name: shopName.trim(),
        business_type: businessType.trim(),
        phone: phone.trim(),
        address: address.trim(),
      });
      setActiveShopId(shop.id);
      router.replace("/dashboard");
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to create your shop. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  function handleSignOut() {
    clearToken();
    clearActiveShopId();
    router.replace("/dashboard");
  }

  if (!ready) {
    return (
      <main className="login-screen">
        <div className="onboarding-status" role={error ? "alert" : "status"}>
          {error ? (
            <>
              <p>{error}</p>
              <button type="button" onClick={handleSignOut}>Sign out</button>
            </>
          ) : (
            <>
              <RefreshCw className="spin" size={22} />
              <p>Checking your shop setup...</p>
            </>
          )}
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
          <span className="eyebrow">SHOP SETUP · 1 OF 1</span>
          <h1>Tell us about your shop.</h1>
          <p>Your shop will be associated with your signed-in merchant account.</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="shop-name">
            Shop name
            <input
              id="shop-name"
              autoComplete="organization"
              minLength={2}
              maxLength={150}
              value={shopName}
              onChange={(event) => setShopName(event.target.value)}
              required
            />
          </label>
          <label htmlFor="business-type">
            Business type or category
            <input
              id="business-type"
              placeholder="For example, grocery or clothing"
              minLength={2}
              maxLength={100}
              value={businessType}
              onChange={(event) => setBusinessType(event.target.value)}
              required
            />
          </label>
          <label htmlFor="shop-phone">
            Business phone number
            <input
              id="shop-phone"
              type="tel"
              autoComplete="tel"
              minLength={7}
              maxLength={20}
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              required
            />
          </label>
          <label htmlFor="shop-address">
            Business address
            <textarea
              id="shop-address"
              autoComplete="street-address"
              minLength={3}
              maxLength={500}
              rows={3}
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              required
            />
          </label>

          {error && <div className="login-error" role="alert">{error}</div>}
          <button type="submit" disabled={loading}>
            {loading ? "Creating shop..." : "Create shop"}
          </button>
        </form>
        <p className="onboarding-switch">
          <button type="button" onClick={handleSignOut}>Sign out</button>
        </p>
      </section>
    </main>
  );
}
