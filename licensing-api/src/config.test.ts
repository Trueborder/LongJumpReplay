import { describe, expect, it } from "vitest";
import { licenseTypeForPrice, rateLimits, settings } from "./config";
import type { Env } from "./config";

function env(overrides: Partial<Env> = {}): Env {
  return {
    DB: {} as D1Database,
    ASSETS: {} as Fetcher,
    ENVIRONMENT: "test",
    MAX_DEVICES: "2",
    VERIFICATION_CODE_TTL_MINUTES: "10",
    MAX_VERIFICATION_ATTEMPTS: "5",
    OFFLINE_VERIFICATION_WINDOW_DAYS: "30",
    AUTHORIZATION_TTL_DAYS: "30",
    SUBSCRIPTION_GRACE_DAYS: "7",
    MAIL_FROM: "info@example.com",
    MAIL_FROM_NAME: "LongJumpReplay",
    PORTAL_ORIGIN: "https://account.example.com",
    PORTAL_SESSION_TTL_DAYS: "30",
    STRIPE_PRICE_LIFETIME: "price_lifetime",
    STRIPE_PRICE_SUBSCRIPTION: "price_subscription",
    STRIPE_WEBHOOK_SECRET: "webhook",
    STRIPE_SECRET_KEY: "stripe",
    VERIFICATION_PEPPER: "pepper",
    AUTHORIZATION_PRIVATE_KEY: "private",
    MAIL_API_KEY: "mail",
    ...overrides,
  };
}

describe("licensing configuration", () => {
  it("keeps the commercial timing contract in seconds", () => {
    const values = settings(env());
    expect(values.verificationCodeTtlSeconds).toBe(600);
    expect(values.offlineWindowSeconds).toBe(30 * 86400);
    expect(values.authorizationTtlSeconds).toBe(30 * 86400);
    expect(values.subscriptionGraceSeconds).toBe(7 * 86400);
    expect(values.portalSessionTtlSeconds).toBe(30 * 86400);
  });

  it("maps only the configured Stripe prices", () => {
    const values = env();
    expect(licenseTypeForPrice(values, "price_lifetime")).toBe("lifetime");
    expect(licenseTypeForPrice(values, "price_subscription")).toBe("subscription");
    expect(licenseTypeForPrice(values, "price_unknown")).toBeNull();
  });

  it("uses strict production defaults when overrides are absent", () => {
    const limits = rateLimits(env());
    expect(limits.requestCode).toEqual([5, 3600]);
    expect(limits.verifyCode).toEqual([10, 3600]);
    expect(limits.activate).toEqual([20, 3600]);
    expect(limits.verify).toEqual([120, 3600]);
  });
});
