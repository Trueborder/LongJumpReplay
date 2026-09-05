import { afterEach, describe, expect, it, vi } from "vitest";
import handler, { contact } from "./index";
import type { Env } from "./config";

function db(): D1Database {
  return {
    prepare() {
      const statement = {
        bind() { return statement; },
        async first() { return null; },
        async run() { return { success: true }; },
      };
      return statement;
    },
  } as unknown as D1Database;
}

function env(): Env {
  return {
    DB: db(), ASSETS: {} as Fetcher, ENVIRONMENT: "test", MAX_DEVICES: "2",
    VERIFICATION_CODE_TTL_MINUTES: "10", MAX_VERIFICATION_ATTEMPTS: "5",
    OFFLINE_VERIFICATION_WINDOW_DAYS: "30", AUTHORIZATION_TTL_DAYS: "30",
    SUBSCRIPTION_GRACE_DAYS: "7", MAIL_FROM: "info@example.com",
    MAIL_FROM_NAME: "LongJumpReplay", PORTAL_ORIGIN: "https://account.example.com",
    PORTAL_SESSION_TTL_DAYS: "30", STRIPE_PRICE_LIFETIME: "price_lifetime",
    STRIPE_PRICE_SUBSCRIPTION: "price_subscription", STRIPE_WEBHOOK_SECRET: "webhook",
    STRIPE_SECRET_KEY: "stripe", VERIFICATION_PEPPER: "pepper",
    AUTHORIZATION_PRIVATE_KEY: "private", MAIL_API_KEY: "re_test",
    CONTACT_TURNSTILE_SECRET: "turnstile-secret",
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("public contact endpoint", () => {
  it("verifies Turnstile and sends the visitor as Reply-To", async () => {
    const requests: Array<{ url: string; body?: string }> = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, body: typeof init?.body === "string" ? init.body : undefined });
      if (url.includes("siteverify")) return new Response(JSON.stringify({ success: true }), { status: 200 });
      return new Response(null, { status: 200 });
    }));
    const response = await handler.fetch(new Request("https://api.example.com/api/contact", {
      method: "POST",
      headers: { "Origin": "https://tomaspisar.cz", "CF-Connecting-IP": "192.0.2.10" },
      body: JSON.stringify({ name: "Ada", email: "ada@example.com", topic: "club", message: "Please quote a club licence.", turnstile_token: "token" }),
    }), env());

    expect(response.status).toBe(200);
    expect(requests.some((request) => request.url.includes("siteverify"))).toBe(true);
    const mail = requests.find((request) => request.url.includes("resend.com"));
    expect(mail?.body).toContain("ada@example.com");
    expect(mail?.body).toContain("Topic: club");
    expect(mail?.body).toContain("reply_to");
    expect(response.headers.get("Access-Control-Allow-Origin")).toBe("https://tomaspisar.cz");
  });

  it("rejects a foreign origin before processing the form", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const response = await contact(new Request("https://api.example.com/api/contact", {
      method: "POST",
      headers: { "Origin": "https://evil.example" },
      body: JSON.stringify({ name: "Ada", email: "ada@example.com", topic: "support", message: "Please help.", turnstile_token: "token" }),
    }), env());

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
