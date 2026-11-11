"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Store } from "lucide-react";
import { login, register } from "@/lib/api";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function RegistrationForm() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (fullName.trim().length < 2) {
      setError("Enter your full name (at least 2 characters).");
      return;
    }
    if (!EMAIL_PATTERN.test(email.trim())) {
      setError("Enter a valid email address.");
      return;
    }
    if (password.length < 8 || password.length > 128) {
      setError("Password must be between 8 and 128 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await register({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        password,
      });

      try {
        await login(email, password);
        router.replace("/onboarding/shop");
      } catch {
        setError(
          "Your account was created, but automatic sign-in failed. Please sign in to continue.",
        );
      }
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Unable to create your account. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-screen">
      <section className="login-card onboarding-card">
        <div className="login-brand">
          <div className="brand-mark"><Store size={24} /></div>
          <span>DUKAANTRA</span>
        </div>
        <div className="login-heading">
          <span className="eyebrow">MERCHANT REGISTRATION</span>
          <h1>Create your account.</h1>
          <p>Set up a secure merchant account to get started.</p>
        </div>

        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="register-name">
            Full name
            <input
              id="register-name"
              type="text"
              autoComplete="name"
              minLength={2}
              maxLength={150}
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              required
            />
          </label>
          <label htmlFor="register-email">
            Email address
            <input
              id="register-email"
              type="email"
              autoComplete="email"
              maxLength={255}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label htmlFor="register-password">
            Password
            <input
              id="register-password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <span className="form-hint">Use 8 to 128 characters.</span>
          </label>
          <label htmlFor="register-confirm-password">
            Confirm password
            <input
              id="register-confirm-password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
            />
          </label>

          {error && <div className="login-error" role="alert">{error}</div>}
          <button type="submit" disabled={loading}>
            {loading ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="onboarding-switch">
          Already registered? <Link href="/dashboard">Sign in</Link>
        </p>
        <p className="login-footer">Your password is securely hashed by the backend.</p>
      </section>
    </main>
  );
}
