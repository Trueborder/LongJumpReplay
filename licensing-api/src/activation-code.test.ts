import { afterEach, describe, expect, it, vi } from "vitest";
import { requestCode, verifyCode } from "./index";
import type { Env } from "./config";
import { hashCode } from "./crypto";

function unlicensedDb(statements: Array<{ sql: string; params: unknown[] }>): D1Database {
  return {
    prepare(sql: string) {
      let params: unknown[] = [];
      const statement = {
        bind(...values: unknown[]) {
          params = values;
          return statement;
        },
        async first() {
          if (sql.includes("FROM rate_limits")) return null;
          if (sql.includes("FROM licenses l")) return null;
          if (sql.includes("FROM customers WHERE email")) {
            return { id: "cus_unlicensed", email: "new@example.com", stripe_customer_id: null };
          }
          throw new Error(`Unexpected first query: ${sql}`);
        },
        async run() {
          statements.push({ sql, params });
          return { success: true };
        },
      };
      return statement;
    },
  } as unknown as D1Database;
}

function env(db: D1Database): Env {
  return {
    DB: db,
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
    MAIL_API_KEY: "re_test",
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("activation code requests", () => {
  it("emails and stores a purpose-scoped code when no licence exists yet", async () => {
    const statements: Array<{ sql: string; params: unknown[] }> = [];
    const send = vi.fn(async () => new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", send);

    const response = await requestCode(
      new Request("https://api.example.com/api/license/request-code", {
        method: "POST",
        headers: { "Content-Type": "application/json", "CF-Connecting-IP": "192.0.2.1" },
        body: JSON.stringify({ email: "new@example.com" }),
      }),
      env(unlicensedDb(statements)),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ sent: true, expires_in_minutes: 10 });
    expect(send).toHaveBeenCalledOnce();
    expect(statements.some(({ sql, params }) =>
      sql.includes("INSERT INTO portal_login_codes") && params.includes("activation"),
    )).toBe(true);
  });

  it("verifies the email but refuses activation cleanly while no licence exists", async () => {
    const statements: Array<{ sql: string; params: unknown[] }> = [];
    const expectedHash = await hashCode("pepper", "123456");
    const db = {
      prepare(sql: string) {
        let params: unknown[] = [];
        const statement = {
          bind(...values: unknown[]) {
            params = values;
            return statement;
          },
          async first() {
            if (sql.includes("FROM rate_limits")) return null;
            if (sql.includes("FROM verification_codes")) return null;
            if (sql.includes("FROM portal_login_codes")) {
              return { id: "pc_1", code_hash: expectedHash, expires_at: 4_000_000_000, attempt_count: 0 };
            }
            if (sql.includes("FROM licenses l")) return null;
            throw new Error(`Unexpected first query: ${sql}`);
          },
          async run() {
            statements.push({ sql, params });
            return { success: true };
          },
        };
        return statement;
      },
    } as unknown as D1Database;

    const response = await verifyCode(
      new Request("https://api.example.com/api/license/verify-code", {
        method: "POST",
        headers: { "Content-Type": "application/json", "CF-Connecting-IP": "192.0.2.1" },
        body: JSON.stringify({ email: "new@example.com", code: "123456" }),
      }),
      env(db),
    );

    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ error: "no_license" });
    expect(statements.some(({ sql }) => sql.includes("SET used_at"))).toBe(true);
    expect(statements.some(({ sql }) => sql.includes("INSERT INTO activation_grants"))).toBe(false);
  });
});
