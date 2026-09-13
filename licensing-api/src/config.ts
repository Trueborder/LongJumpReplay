/**
 * Every tunable in one place. Nothing below should be duplicated elsewhere in
 * the Worker, and the website reads matching values from site.config.js so the
 * two cannot silently drift.
 */

export interface Env {
  DB: D1Database;
  ASSETS: Fetcher;

  ENVIRONMENT: string;
  MAX_DEVICES: string;
  VERIFICATION_CODE_TTL_MINUTES: string;
  MAX_VERIFICATION_ATTEMPTS: string;
  OFFLINE_VERIFICATION_WINDOW_DAYS: string;
  AUTHORIZATION_TTL_DAYS: string;
  SUBSCRIPTION_GRACE_DAYS: string;
  MAIL_FROM: string;
  MAIL_FROM_NAME: string;
  PORTAL_ORIGIN: string;
  PORTAL_SESSION_TTL_DAYS: string;
  STRIPE_PRICE_LIFETIME: string;
  STRIPE_PRICE_SUBSCRIPTION: string;

  // Optional rate-limit overrides; omit for the production defaults.
  RATE_LIMIT_WINDOW_SECONDS?: string;
  RATE_LIMIT_REQUEST_CODE?: string;
  RATE_LIMIT_VERIFY_CODE?: string;
  RATE_LIMIT_ACTIVATE?: string;
  RATE_LIMIT_PAIRING_STATUS?: string;
  RATE_LIMIT_ACTIVATION_KEY?: string;
  RATE_LIMIT_VERIFY?: string;
  RATE_LIMIT_CONTACT?: string;
  RATE_LIMIT_PASSWORD_LOGIN?: string;
  RATE_LIMIT_PASSWORD_RESET_REQUEST?: string;
  RATE_LIMIT_PASSWORD_RESET_VERIFY?: string;
  RATE_LIMIT_REGISTRATION_REQUEST?: string;
  RATE_LIMIT_REGISTRATION_VERIFY?: string;
  RATE_LIMIT_REGISTRATION_COMPLETE?: string;

  // Secrets - set with `wrangler secret put`, never in wrangler.jsonc.
  STRIPE_WEBHOOK_SECRET: string;
  STRIPE_SECRET_KEY: string;
  VERIFICATION_PEPPER: string;
  ACTIVATION_KEY_ENCRYPTION_KEY?: string;
  AUTHORIZATION_PRIVATE_KEY: string;
  MAIL_API_KEY: string;
  CONTACT_TURNSTILE_SECRET?: string;
}

export type LicenseType = "lifetime" | "subscription";
export type LicenseStatus = "active" | "inactive" | "expired" | "suspended";

export interface Settings {
  maxDevices: number;
  verificationCodeTtlSeconds: number;
  maxVerificationAttempts: number;
  offlineWindowSeconds: number;
  authorizationTtlSeconds: number;
  subscriptionGraceSeconds: number;
  portalSessionTtlSeconds: number;
}

function int(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function settings(env: Env): Settings {
  return {
    maxDevices: int(env.MAX_DEVICES, 2),
    verificationCodeTtlSeconds: int(env.VERIFICATION_CODE_TTL_MINUTES, 10) * 60,
    maxVerificationAttempts: int(env.MAX_VERIFICATION_ATTEMPTS, 5),
    offlineWindowSeconds: int(env.OFFLINE_VERIFICATION_WINDOW_DAYS, 30) * 86400,
    authorizationTtlSeconds: int(env.AUTHORIZATION_TTL_DAYS, 30) * 86400,
    subscriptionGraceSeconds: int(env.SUBSCRIPTION_GRACE_DAYS, 7) * 86400,
    portalSessionTtlSeconds: int(env.PORTAL_SESSION_TTL_DAYS, 30) * 86400,
  };
}

/**
 * Stripe price ID -> what kind of licence it grants.
 *
 * Returns null for anything unrecognised. That is deliberate: an unmapped price
 * must fail loudly and be flagged for manual attention rather than quietly
 * producing a licence of a guessed type.
 */
export function licenseTypeForPrice(env: Env, priceId: string | null | undefined): LicenseType | null {
  if (!priceId) return null;
  if (env.STRIPE_PRICE_LIFETIME && priceId === env.STRIPE_PRICE_LIFETIME) return "lifetime";
  if (env.STRIPE_PRICE_SUBSCRIPTION && priceId === env.STRIPE_PRICE_SUBSCRIPTION) return "subscription";
  return null;
}

export const PRODUCT_ID = "LongJumpReplay";

/** Authorization token format version, echoed in the payload. */
export const AUTHORIZATION_VERSION = 1;
export const AUTHORIZATION_PREFIX = "LJRA1";

/**
 * Rate limits as [max requests, window seconds] per bucket key. Overridable so
 * an automated test can raise them without the production defaults loosening;
 * unset means the tight default applies.
 */
export function rateLimits(env: Env) {
  const window = int(env.RATE_LIMIT_WINDOW_SECONDS, 3600);
  return {
    requestCode: [int(env.RATE_LIMIT_REQUEST_CODE, 5), window] as [number, number],
    verifyCode: [int(env.RATE_LIMIT_VERIFY_CODE, 10), window] as [number, number],
    activate: [int(env.RATE_LIMIT_ACTIVATE, 20), window] as [number, number],
    pairingStatus: [int(env.RATE_LIMIT_PAIRING_STATUS, 240), window] as [number, number],
    activationKey: [int(env.RATE_LIMIT_ACTIVATION_KEY, 30), window] as [number, number],
    verify: [int(env.RATE_LIMIT_VERIFY, 120), window] as [number, number],
    contact: [int(env.RATE_LIMIT_CONTACT, 3), window] as [number, number],
    passwordLogin: [int(env.RATE_LIMIT_PASSWORD_LOGIN, 10), window] as [number, number],
    passwordResetRequest: [int(env.RATE_LIMIT_PASSWORD_RESET_REQUEST, 5), window] as [number, number],
    passwordResetVerify: [int(env.RATE_LIMIT_PASSWORD_RESET_VERIFY, 10), window] as [number, number],
    registrationRequest: [int(env.RATE_LIMIT_REGISTRATION_REQUEST, 5), window] as [number, number],
    registrationVerify: [int(env.RATE_LIMIT_REGISTRATION_VERIFY, 10), window] as [number, number],
    registrationComplete: [int(env.RATE_LIMIT_REGISTRATION_COMPLETE, 10), window] as [number, number],
  };
}
