/**
 * LongJumpReplay licensing API.
 *
 *   POST /api/stripe/webhook          Stripe -> licence creation and sync
 *   POST /api/license/request-code    email -> verification code sent
 *   POST /api/license/verify-code     email + code -> short-lived grant
 *   POST /api/license/activate        grant + machine -> signed authorization
 *   POST /api/license/verify          refresh an authorization
 *   POST /api/license/deactivate-device
 *   GET  /health
 *
 * Documented in docs/LICENSE_SYSTEM.md.
 */

import { PRODUCT_ID, licenseTypeForPrice, rateLimits, settings } from "./config";
import { additionalComputerPrices, additionalComputerTotalCzk, eligibleAdditionalComputerOffers, LIFETIME_MAX_DEVICES } from "./additional-computers";
import type { Env, LicenseType } from "./config";
import {
  generateToken,
  generateActivationKey,
  normalizeActivationKey,
  encryptActivationKey,
  decryptActivationKey,
  generateVerificationCode,
  hashCode,
  randomId,
  sha256,
  signAuthorization,
  timingSafeEqual,
} from "./crypto";
import {
  activateDevice,
  applyAdditionalComputerPurchase,
  activeDeviceCount,
  claimStripeEvent,
  createPortalSession,
  createLicense,
  deactivateDevice,
  deactivateDeviceForCustomer,
  deleteDeactivatedDeviceForCustomer,
  deviceDetailsForCustomer,
  findActivationKeyByLicense,
  findActivationKeyByVerifier,
  findActivatableLicense,
  findCustomerById,
  findDevice,
  findLicenseById,
  findLicenseBySubscription,
  findPortalSession,
  listDevicesForCustomer,
  listLicensesForCustomer,
  logEvent,
  normaliseEmail,
  now,
  rateLimit,
  recordDeviceActivity,
  rotateActivationKey,
  saveActivationKey,
  setLicenseStatus,
  touchDevice,
  touchPortalSession,
  upsertCustomer,
  revokePortalSession,
  purgeOldDeviceActivity,
} from "./db";
import type { DeviceMetadata } from "./db";
import { sendContactMessage, sendVerificationCode } from "./email";
import {
  ACTIVE_SUBSCRIPTION_STATUSES,
  DEAD_SUBSCRIPTION_STATUSES,
  SignatureError,
  stripeApi,
  verifySignature,
} from "./stripe";
import type { StripeEvent } from "./stripe";
import { portalPageRoute } from "./portal-routing";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MACHINE_PATTERN = /^[A-Za-z0-9_-]{16,128}$/;
const MAX_BODY_BYTES = 16_384;
const PORTAL_SESSION_COOKIE = "ljr-portal-session";
const CONTACT_ORIGIN = "https://tomaspisar.cz";
const CONTACT_TOPICS = new Set(["support", "licence", "bug", "feedback", "general"]);

function json(data: unknown, status = 200, headers?: HeadersInit): Response {
  const responseHeaders = new Headers({
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  new Headers(headers).forEach((value, key) => responseHeaders.set(key, value));
  return new Response(JSON.stringify(data), {
    status,
    headers: responseHeaders,
  });
}

/** User-facing errors only. Never leaks table names, SQL or stack traces. */
function fail(code: string, message: string, status = 400): Response {
  return json({ error: code, message }, status);
}

async function readJson(request: Request): Promise<Record<string, unknown>> {
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) throw new Error("request too large");
  const parsed = JSON.parse(text);
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("JSON object required");
  }
  return parsed as Record<string, unknown>;
}

function str(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function clientKey(request: Request): string {
  return request.headers.get("CF-Connecting-IP") ?? "unknown";
}

function bounded(value: unknown, max: number): string | null {
  const result = str(value);
  return result ? result.slice(0, max) : null;
}

function deviceMetadata(data: Record<string, unknown>): DeviceMetadata {
  return {
    appVersion: bounded(data.app_version, 40),
    osVersion: bounded(data.os_version, 160),
    architecture: bounded(data.architecture, 40),
  };
}

function clientNetwork(request: Request): { ipAddress: string | null; country: string | null } {
  const cf = request.cf as { country?: string } | undefined;
  return {
    ipAddress: bounded(request.headers.get("CF-Connecting-IP"), 64),
    country: bounded(cf?.country ?? request.headers.get("CF-IPCountry"), 2),
  };
}

function portalMutationAllowed(request: Request, env: Env): boolean {
  const origin = request.headers.get("Origin");
  return !origin || origin === env.PORTAL_ORIGIN;
}

function portalCorsHeaders(request: Request, env: Env): Headers {
  const headers = new Headers();
  const origin = request.headers.get("Origin");
  if (origin && origin === env.PORTAL_ORIGIN) {
    headers.set("Access-Control-Allow-Origin", origin);
    headers.set("Access-Control-Allow-Credentials", "true");
    headers.set("Access-Control-Allow-Headers", "Content-Type");
    headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    headers.set("Vary", "Origin");
  }
  return headers;
}

function withPortalCors(response: Response, request: Request, env: Env): Response {
  const headers = new Headers(response.headers);
  portalCorsHeaders(request, env).forEach((value, key) => headers.set(key, value));
  return new Response(response.body, { status: response.status, headers });
}

function contactCorsHeaders(request: Request): Headers {
  const headers = new Headers();
  if (request.headers.get("Origin") === CONTACT_ORIGIN) {
    headers.set("Access-Control-Allow-Origin", CONTACT_ORIGIN);
    headers.set("Access-Control-Allow-Headers", "Content-Type");
    headers.set("Access-Control-Allow-Methods", "POST, OPTIONS");
    headers.set("Vary", "Origin");
  }
  return headers;
}

function withContactCors(response: Response, request: Request): Response {
  const headers = new Headers(response.headers);
  contactCorsHeaders(request).forEach((value, key) => headers.set(key, value));
  return new Response(response.body, { status: response.status, headers });
}

async function verifyContactTurnstile(request: Request, env: Env, token: string): Promise<boolean> {
  if (!env.CONTACT_TURNSTILE_SECRET) return false;
  const body = new URLSearchParams({
    secret: env.CONTACT_TURNSTILE_SECRET,
    response: token,
    ...(clientKey(request) !== "unknown" ? { remoteip: clientKey(request) } : {}),
  });
  const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!response.ok) return false;
  const result = await response.json() as { success?: boolean };
  return result.success === true;
}

export async function contact(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  if (origin && origin !== CONTACT_ORIGIN) return fail("forbidden", "This request is not allowed.", 403);
  let data: Record<string, unknown>;
  try {
    data = await readJson(request);
  } catch {
    return fail("invalid_input", "Complete the form and try again.");
  }

  if (str(data.website)) return fail("invalid_input", "Complete the form and try again.");
  const name = str(data.name);
  const email = str(data.email).toLowerCase();
  const topic = str(data.topic).toLowerCase();
  const message = str(data.message);
  const turnstileToken = str(data.turnstile_token);
  if (name.length < 1 || name.length > 120 || !EMAIL_PATTERN.test(email) || email.length > 254
      || !CONTACT_TOPICS.has(topic) || message.length < 10 || message.length > 5000
      || turnstileToken.length < 1 || turnstileToken.length > 2048) {
    return fail("invalid_input", "Complete the form and try again.");
  }
  const limits = rateLimits(env).contact;
  if (!(await rateLimit(env.DB, `contactip:${clientKey(request)}`, ...limits))) {
    return fail("rate_limited", "Please wait before sending another message.", 429);
  }
  if (!(await rateLimit(env.DB, `contactemail:${await sha256(email)}`, ...limits))) {
    return fail("rate_limited", "Please wait before sending another message.", 429);
  }
  if (!(await verifyContactTurnstile(request, env, turnstileToken))) {
    return fail("verification_failed", "Please complete the security check and try again.", 403);
  }
  await sendContactMessage(env, { name, email, topic, message });
  return json({ sent: true });
}

function portalCookie(token: string, maxAge: number): string {
  return `${PORTAL_SESSION_COOKIE}=${encodeURIComponent(token)}; Max-Age=${maxAge}; Domain=.tomaspisar.cz; Path=/; HttpOnly; Secure; SameSite=Lax`;
}

function portalToken(request: Request): string | null {
  const cookie = request.headers.get("Cookie") ?? "";
  for (const part of cookie.split(";")) {
    const [name, ...value] = part.trim().split("=");
    if (name === PORTAL_SESSION_COOKIE) return decodeURIComponent(value.join("="));
  }
  return null;
}

function portalRedirect(request: Request, location: string): Response {
  return new Response(null, {
    status: 302,
    headers: {
      "Cache-Control": "no-store",
      Location: new URL(location, request.url).toString(),
    },
  });
}

async function portalPage(request: Request, env: Env, path: string): Promise<Response | null> {
  if (request.method !== "GET" && request.method !== "HEAD") return null;
  const isPortalPage = ["/", "/login", "/login/", "/dashboard", "/dashboard/"].includes(path)
    || path.startsWith("/dashboard/");
  if (!isPortalPage) return null;

  const route = portalPageRoute(path, Boolean(await authenticatedPortal(request, env)));
  if (!route) return null;
  if (route.kind === "redirect") return portalRedirect(request, route.location);

  const assetUrl = new URL(route.assetPath, request.url);
  const assetResponse = await env.ASSETS.fetch(new Request(assetUrl, request));
  const headers = new Headers(assetResponse.headers);
  headers.set("Cache-Control", "no-store");
  return new Response(assetResponse.body, {
    status: assetResponse.status,
    statusText: assetResponse.statusText,
    headers,
  });
}

/* ------------------------------------------------------------------ Stripe */

function priceIdFromSession(session: Record<string, any>): string | null {
  const item = session?.line_items?.data?.[0];
  return item?.price?.id ?? null;
}

async function handleAdditionalComputerCheckout(env: Env, event: StripeEvent): Promise<void> {
  const session = event.data.object;
  if (session.payment_status !== "paid") {
    await logEvent(env.DB, "additional_computers_payment_not_confirmed", null, { session: session.id, payment_status: session.payment_status ?? null });
    return;
  }
  const metadata = session.metadata ?? {};
  const customerId = typeof metadata.customer_id === "string" ? metadata.customer_id : "";
  const licenseId = typeof metadata.license_id === "string" ? metadata.license_id : "";
  const quantity = Number.parseInt(String(metadata.quantity ?? ""), 10);
  const customer = await findCustomerById(env.DB, customerId);
  const license = await findLicenseById(env.DB, licenseId);
  if (!customer || !license || license.customer_id !== customerId || license.type !== "lifetime" || license.status !== "active" || !Number.isInteger(quantity) || quantity < 1 || license.max_devices >= LIFETIME_MAX_DEVICES) {
    await logEvent(env.DB, "additional_computers_rejected", licenseId || null, { session: session.id, reason: "ownership, status, type, or capacity" });
    return;
  }
  let prices: number[];
  try { prices = additionalComputerPrices(quantity, license.max_devices); } catch {
    await logEvent(env.DB, "additional_computers_rejected", license.id, { session: session.id, reason: "invalid quantity" });
    return;
  }
  const expectedAmount = additionalComputerTotalCzk(quantity, license.max_devices) * 100;
  if (session.amount_total !== expectedAmount || String(session.currency ?? "").toLowerCase() !== "czk") {
    await logEvent(env.DB, "additional_computers_rejected", license.id, { session: session.id, reason: "amount mismatch" });
    return;
  }
  const result = await applyAdditionalComputerPurchase(env.DB, {
    stripeSessionId: session.id,
    stripePaymentIntentId: session.payment_intent ?? null,
    customerId,
    licenseId,
    quantity,
    amount: expectedAmount,
    currency: "czk",
  });
  if (result.duplicate) return;
  await logEvent(env.DB, result.applied ? "additional_computers_purchased" : "additional_computers_rejected", license.id, {
    quantity, amount: expectedAmount, currency: "czk", stripe_session_id: session.id,
    stripe_payment_intent_id: session.payment_intent ?? null, resulting_max_devices: result.resultingMaxDevices,
    reason: result.applied ? undefined : "capacity reached during processing",
  });
}
async function handleCheckoutCompleted(env: Env, event: StripeEvent): Promise<void> {
  const session = event.data.object;
  if (session.metadata?.purchase_type === "additional_computers") { await handleAdditionalComputerCheckout(env, event); return; }
  const email: string =
    session.customer_details?.email ?? session.customer_email ?? "";
  if (!EMAIL_PATTERN.test(email)) {
    await logEvent(env.DB, "license_creation_failed", null, { reason: "no usable email", session: session.id });
    return;
  }

  // The session in the event payload usually omits line items, so read the
  // price back from Stripe rather than guessing the product.
  let priceId = priceIdFromSession(session);
  if (!priceId && env.STRIPE_SECRET_KEY && session.id) {
    try {
      const items = await stripeApi(env.STRIPE_SECRET_KEY).getCheckoutLineItems(session.id);
      priceId = items[0]?.price?.id ?? null;
    } catch {
      priceId = null;
    }
  }

  let type: LicenseType | null = licenseTypeForPrice(env, priceId);
  if (!type && session.mode === "subscription") type = "subscription";
  if (!type && session.mode === "payment") type = "lifetime";
  if (!type) {
    // Unmapped price and unusable mode: flag rather than guess.
    await logEvent(env.DB, "license_creation_failed", null, {
      reason: "unmapped price",
      price: priceId,
      session: session.id,
    });
    return;
  }

  const subscriptionId: string | null = session.subscription ?? null;
  if (subscriptionId) {
    const existing = await findLicenseBySubscription(env.DB, subscriptionId);
    if (existing) return; // already provisioned by an earlier event
  }

  let periodEnd: number | null = null;
  if (type === "subscription" && subscriptionId && env.STRIPE_SECRET_KEY) {
    try {
      const subscription = await stripeApi(env.STRIPE_SECRET_KEY).getSubscription(subscriptionId);
      periodEnd = subscription.current_period_end ?? null;
    } catch {
      periodEnd = null;
    }
  }

  const customer = await upsertCustomer(env.DB, email, session.customer ?? null);
  const license = await createLicense(env.DB, {
    customerId: customer.id,
    type,
    maxDevices: settings(env).maxDevices,
    stripeCustomerId: session.customer ?? null,
    stripeSubscriptionId: subscriptionId,
    stripePriceId: priceId,
    currentPeriodEnd: periodEnd,
  });
  await logEvent(env.DB, "license_created", license.id, { type, session: session.id });
}

async function handleSubscriptionChange(env: Env, event: StripeEvent): Promise<void> {
  const subscription = event.data.object;
  const license = await findLicenseBySubscription(env.DB, subscription.id);
  if (!license) return;

  const status: string = subscription.status ?? "";
  const periodEnd: number | null = subscription.current_period_end ?? null;

  if (ACTIVE_SUBSCRIPTION_STATUSES.has(status)) {
    await setLicenseStatus(env.DB, license.id, "active", periodEnd);
    await logEvent(env.DB, "stripe_sync", license.id, { status, result: "active" });
    return;
  }
  if (DEAD_SUBSCRIPTION_STATUSES.has(status)) {
    await setLicenseStatus(env.DB, license.id, "inactive", periodEnd);
    await logEvent(env.DB, "subscription_cancelled", license.id, { status });
    return;
  }
  await logEvent(env.DB, "stripe_sync", license.id, { status, result: "unchanged" });
}

async function handleWebhook(request: Request, env: Env): Promise<Response> {
  const payload = await request.text();
  try {
    await verifySignature(payload, request.headers.get("Stripe-Signature"), env.STRIPE_WEBHOOK_SECRET);
  } catch (error) {
    if (error instanceof SignatureError) return fail("invalid_signature", "Signature verification failed", 400);
    throw error;
  }

  let event: StripeEvent;
  try {
    event = JSON.parse(payload) as StripeEvent;
  } catch {
    return fail("invalid_payload", "Invalid JSON", 400);
  }
  if (!event?.id || !event?.type) return fail("invalid_payload", "Not a Stripe event", 400);

  // Stripe retries until it gets a 2xx, so the same event can arrive twice.
  if (!(await claimStripeEvent(env.DB, event.id, event.type))) {
    return json({ duplicate: event.id });
  }

  switch (event.type) {
    case "checkout.session.completed":
    case "checkout.session.async_payment_succeeded":
      await handleCheckoutCompleted(env, event);
      break;
    case "customer.subscription.created":
    case "customer.subscription.updated":
    case "customer.subscription.deleted":
    case "customer.subscription.paused":
    case "customer.subscription.resumed":
      await handleSubscriptionChange(env, event);
      break;
    case "invoice.payment_succeeded":
    case "invoice.payment_failed": {
      const subscriptionId = event.data.object.subscription;
      if (subscriptionId && env.STRIPE_SECRET_KEY) {
        try {
          const subscription = await stripeApi(env.STRIPE_SECRET_KEY).getSubscription(subscriptionId);
          await handleSubscriptionChange(env, {
            ...event,
            data: { object: subscription },
          });
        } catch {
          /* transient Stripe read failure; the next subscription event will resync */
        }
      }
      break;
    }
    default:
      break; // subscribed-to-but-unhandled types are acknowledged, not errors
  }

  return json({ received: event.id });
}

/* ------------------------------------------------------- Activation flow */

type VerificationPurpose = "activation" | "portal";

async function createEmailOnlyCode(
  env: Env,
  email: string,
  purpose: VerificationPurpose,
): Promise<string> {
  const customer = await upsertCustomer(env.DB, email, null);
  await env.DB.prepare(
    "UPDATE portal_login_codes SET used_at = ? WHERE customer_id = ? AND purpose = ? AND used_at IS NULL",
  )
    .bind(now(), customer.id, purpose)
    .run();

  const code = generateVerificationCode();
  const timestamp = now();
  await env.DB.prepare(
    `INSERT INTO portal_login_codes
       (id, customer_id, email, purpose, code_hash, created_at, expires_at, attempt_count)
     VALUES (?, ?, ?, ?, ?, ?, ?, 0)`,
  )
    .bind(
      randomId("pc"),
      customer.id,
      email,
      purpose,
      await hashCode(env.VERIFICATION_PEPPER, code),
      timestamp,
      timestamp + settings(env).verificationCodeTtlSeconds,
    )
    .run();
  return code;
}

export async function requestCode(request: Request, env: Env, purpose: VerificationPurpose = "activation"): Promise<Response> {
  const cfg = settings(env);
  const data = await readJson(request);
  const email = normaliseEmail(str(data.email));
  if (!EMAIL_PATTERN.test(email)) return fail("invalid_email", "Enter a valid email address.");

  if (!(await rateLimit(env.DB, `code:${email}`, ...rateLimits(env).requestCode))) {
    return fail("rate_limited", "Too many code requests. Try again later.", 429);
  }
  if (!(await rateLimit(env.DB, `codeip:${clientKey(request)}`, ...rateLimits(env).requestCode))) {
    return fail("rate_limited", "Too many code requests. Try again later.", 429);
  }

  const generic = json({
    sent: true,
    expires_in_minutes: Math.floor(cfg.verificationCodeTtlSeconds / 60),
  });

  if (purpose === "portal") {
    // Portal access proves ownership of an email address, not ownership of a
    // licence. A later Stripe purchase using the same normalized address is
    // attached to this customer by upsertCustomer.
    try {
      const code = await createEmailOnlyCode(env, email, purpose);
      await sendVerificationCode(env, email, code, Math.floor(cfg.verificationCodeTtlSeconds / 60), purpose);
      await logEvent(env.DB, "portal_login_requested", null, { result: "sent" });
    } catch {
      await logEvent(env.DB, "portal_login_requested", null, { result: "send failed" });
      return fail("email_failed", "Could not send the verification email. Please try again shortly.", 502);
    }
    return generic;
  }

  const license = await findActivatableLicense(env.DB, email);

  // Activation stays indistinguishable for licensed and unlicensed addresses,
  // so this endpoint cannot reveal who has bought the software.
  if (!license) {
    try {
      const code = await createEmailOnlyCode(env, email, purpose);
      await sendVerificationCode(env, email, code, Math.floor(cfg.verificationCodeTtlSeconds / 60), purpose);
      await logEvent(env.DB, "verification_requested", null, { result: "sent before purchase" });
    } catch {
      await logEvent(env.DB, "verification_requested", null, { result: "send failed" });
      return fail("email_failed", "Could not send the verification email. Please try again shortly.", 502);
    }
    return generic;
  }

  // A new code invalidates any earlier unused one.
  await env.DB.prepare(
    "UPDATE verification_codes SET used_at = ? WHERE license_id = ? AND purpose = ? AND used_at IS NULL",
  )
    .bind(now(), license.id, purpose)
    .run();

  const code = generateVerificationCode();
  const timestamp = now();
  await env.DB.prepare(
    `INSERT INTO verification_codes (id, license_id, email, purpose, code_hash, created_at, expires_at, attempt_count)
     VALUES (?, ?, ?, ?, ?, ?, ?, 0)`,
  )
    .bind(
      randomId("vc"),
      license.id,
      email,
      purpose,
      await hashCode(env.VERIFICATION_PEPPER, code),
      timestamp,
      timestamp + cfg.verificationCodeTtlSeconds,
    )
    .run();

  try {
    await sendVerificationCode(env, email, code, Math.floor(cfg.verificationCodeTtlSeconds / 60), purpose);
    await logEvent(env.DB, "verification_requested", license.id, { result: "sent" });
  } catch {
    await logEvent(env.DB, "verification_requested", license.id, { result: "send failed" });
    return fail("email_failed", "Could not send the verification email. Please try again shortly.", 502);
  }
  return generic;
}

export async function verifyCode(request: Request, env: Env, purpose: VerificationPurpose = "activation"): Promise<Response> {
  const cfg = settings(env);
  const data = await readJson(request);
  const email = normaliseEmail(str(data.email));
  const code = str(data.code);
  if (!EMAIL_PATTERN.test(email) || !/^\d{6}$/.test(code)) {
    return fail("invalid_input", "Enter the six-digit code from your email.");
  }
  if (!(await rateLimit(env.DB, `verify:${email}`, ...rateLimits(env).verifyCode))) {
    return fail("rate_limited", "Too many attempts. Try again later.", 429);
  }

  if (purpose === "portal") {
    const row = await env.DB.prepare(
      `SELECT * FROM portal_login_codes
        WHERE email = ? AND purpose = ? AND used_at IS NULL
        ORDER BY created_at DESC LIMIT 1`,
    )
      .bind(email, purpose)
      .first<{
        id: string;
        customer_id: string;
        code_hash: string;
        expires_at: number;
        attempt_count: number;
      }>();

    if (!row) return fail("invalid_code", "That code is not valid. Request a new one.");
    if (row.expires_at < now()) return fail("code_expired", "That code has expired. Request a new one.");
    if (row.attempt_count >= cfg.maxVerificationAttempts) {
      return fail("too_many_attempts", "Too many incorrect attempts. Request a new code.", 429);
    }

    await env.DB.prepare("UPDATE portal_login_codes SET attempt_count = attempt_count + 1 WHERE id = ?")
      .bind(row.id)
      .run();
    const candidate = await hashCode(env.VERIFICATION_PEPPER, code);
    if (!timingSafeEqual(candidate, row.code_hash)) {
      await logEvent(env.DB, "portal_login_failed", null, {});
      return fail("invalid_code", "That code is not correct.");
    }

    await env.DB.prepare("UPDATE portal_login_codes SET used_at = ? WHERE id = ?").bind(now(), row.id).run();
    const customer = await findCustomerById(env.DB, row.customer_id);
    if (!customer) return fail("invalid_code", "That code is not valid. Request a new one.");
    const token = generateToken();
    const expiresAt = now() + cfg.portalSessionTtlSeconds;
    await createPortalSession(env.DB, customer.id, await sha256(token), expiresAt);
    await logEvent(env.DB, "portal_login_success", null, {});
    return json(
      { authenticated: true, expires_at: expiresAt },
      200,
      { "Set-Cookie": portalCookie(token, cfg.portalSessionTtlSeconds) },
    );
  }

  const row = await env.DB.prepare(
    `SELECT * FROM verification_codes
      WHERE email = ? AND purpose = ? AND used_at IS NULL
      ORDER BY created_at DESC LIMIT 1`,
  )
    .bind(email, purpose)
    .first<{
      id: string;
      license_id: string;
      code_hash: string;
      expires_at: number;
      attempt_count: number;
    }>();

  if (!row) {
    const emailOnly = await env.DB.prepare(
      `SELECT * FROM portal_login_codes
        WHERE email = ? AND purpose = 'activation' AND used_at IS NULL
        ORDER BY created_at DESC LIMIT 1`,
    )
      .bind(email)
      .first<{
        id: string;
        code_hash: string;
        expires_at: number;
        attempt_count: number;
      }>();

    if (!emailOnly) return fail("invalid_code", "That code is not valid. Request a new one.");
    if (emailOnly.expires_at < now()) return fail("code_expired", "That code has expired. Request a new one.");
    if (emailOnly.attempt_count >= cfg.maxVerificationAttempts) {
      return fail("too_many_attempts", "Too many incorrect attempts. Request a new code.", 429);
    }

    await env.DB.prepare("UPDATE portal_login_codes SET attempt_count = attempt_count + 1 WHERE id = ?")
      .bind(emailOnly.id)
      .run();
    const candidate = await hashCode(env.VERIFICATION_PEPPER, code);
    if (!timingSafeEqual(candidate, emailOnly.code_hash)) {
      await logEvent(env.DB, "verification_failed", null, { result: "email only" });
      return fail("invalid_code", "That code is not correct.");
    }

    await env.DB.prepare("UPDATE portal_login_codes SET used_at = ? WHERE id = ?")
      .bind(now(), emailOnly.id)
      .run();
    const currentLicense = await findActivatableLicense(env.DB, email);
    if (!currentLicense) {
      await logEvent(env.DB, "verification_success", null, { result: "no active license" });
      return fail(
        "no_license",
        "Email verified, but no active subscription or lifetime licence was found for this account.",
        403,
      );
    }

    const grant = generateToken();
    await env.DB.prepare(
      "INSERT INTO activation_grants (id, license_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
    )
      .bind(randomId("grant"), currentLicense.id, await sha256(grant), now(), now() + 600)
      .run();
    await logEvent(env.DB, "verification_success", currentLicense.id, { result: "purchased after code request" });
    return json({ verified: true, activation_grant: grant, expires_in_seconds: 600 });
  }
  if (row.expires_at < now()) return fail("code_expired", "That code has expired. Request a new one.");
  if (row.attempt_count >= cfg.maxVerificationAttempts) {
    return fail("too_many_attempts", "Too many incorrect attempts. Request a new code.", 429);
  }

  await env.DB.prepare("UPDATE verification_codes SET attempt_count = attempt_count + 1 WHERE id = ?")
    .bind(row.id)
    .run();

  const candidate = await hashCode(env.VERIFICATION_PEPPER, code);
  if (!timingSafeEqual(candidate, row.code_hash)) {
    await logEvent(env.DB, "verification_failed", row.license_id, {});
    return fail("invalid_code", "That code is not correct.");
  }

  await env.DB.prepare("UPDATE verification_codes SET used_at = ? WHERE id = ?").bind(now(), row.id).run();

  // Proof of email ownership, exchanged for an activation. Short-lived and
  // single-use, so it cannot be replayed to add devices later.
  const grant = generateToken();
  await env.DB.prepare(
    "INSERT INTO activation_grants (id, license_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
  )
    .bind(randomId("grant"), row.license_id, await sha256(grant), now(), now() + 600)
    .run();

  await logEvent(env.DB, "verification_success", row.license_id, {});
  return json({ verified: true, activation_grant: grant, expires_in_seconds: 600 });
}

async function issueAuthorization(env: Env, license: { id: string; type: LicenseType; max_devices: number }, machineId: string) {
  const cfg = settings(env);
  const issuedAt = now();
  const token = await signAuthorization(env.AUTHORIZATION_PRIVATE_KEY, {
    licenseId: license.id,
    licenseType: license.type,
    machineId,
    issuedAt,
    expiresAt: issuedAt + cfg.authorizationTtlSeconds,
    maxDevices: license.max_devices,
  });
  return { token, issuedAt, expiresAt: issuedAt + cfg.authorizationTtlSeconds };
}

async function activate(request: Request, env: Env): Promise<Response> {
  const data = await readJson(request);
  const grant = str(data.activation_grant);
  const machineId = str(data.machine_id);
  const deviceName = str(data.device_name) || null;
  const metadata = deviceMetadata(data);

  if (!grant || !MACHINE_PATTERN.test(machineId)) {
    return fail("invalid_input", "Missing or malformed activation request.");
  }
  if (!(await rateLimit(env.DB, `act:${clientKey(request)}`, ...rateLimits(env).activate))) {
    return fail("rate_limited", "Too many activation attempts. Try again later.", 429);
  }

  const row = await env.DB.prepare(
    "SELECT id, license_id, expires_at, used_at FROM activation_grants WHERE token_hash = ?",
  )
    .bind(await sha256(grant))
    .first<{ id: string; license_id: string; expires_at: number; used_at: number | null }>();

  if (!row || row.used_at !== null || row.expires_at < now()) {
    return fail("invalid_grant", "This activation has expired. Start again from your email address.", 401);
  }

  const license = await findLicenseById(env.DB, row.license_id);
  if (!license) return fail("no_license", "No licence found.", 404);
  if (license.status !== "active") {
    return fail("license_inactive", "This licence is not currently active. Please get in touch.", 403);
  }

  const existing = await findDevice(env.DB, license.id, machineId);
  if (!existing || existing.status !== "active") {
    if ((await activeDeviceCount(env.DB, license.id)) >= license.max_devices) {
      return fail(
        "device_limit",
        `This licence is already active on ${license.max_devices} computers. Deactivate one before activating another.`,
        409,
      );
    }
  }

  await env.DB.prepare("UPDATE activation_grants SET used_at = ? WHERE id = ?").bind(now(), row.id).run();
  const device = await activateDevice(env.DB, license.id, machineId, deviceName, "email", null, metadata);
  await recordDeviceActivity(env.DB, device, "activation", clientNetwork(request), metadata);
  const authorization = await issueAuthorization(env, license, machineId);
  await logEvent(env.DB, "device_activated", license.id, { device: device.id });

  return json({
    activated: true,
    license_type: license.type,
    max_devices: license.max_devices,
    authorization: authorization.token,
    expires_at: authorization.expiresAt,
  });
}

/** Periodic re-verification: refreshes the local authorization. */
async function verify(request: Request, env: Env): Promise<Response> {
  const data = await readJson(request);
  const licenseId = str(data.license_id);
  const machineId = str(data.machine_id);
  const metadata = deviceMetadata(data);
  if (!licenseId || !MACHINE_PATTERN.test(machineId)) {
    return fail("invalid_input", "Missing or malformed verification request.");
  }
  if (!(await rateLimit(env.DB, `ver:${licenseId}`, ...rateLimits(env).verify))) {
    return fail("rate_limited", "Too many verification attempts.", 429);
  }

  const license = await findLicenseById(env.DB, licenseId);
  if (!license) return fail("no_license", "No licence found.", 404);

  const device = await findDevice(env.DB, license.id, machineId);
  if (!device || device.status !== "active") {
    return fail("device_not_active", "This computer is not activated for that licence.", 403);
  }

  // A subscription that lapsed keeps working until the paid period plus grace
  // runs out, so a failed payment never disables software mid-competition.
  let status = license.status;
  if (license.type === "subscription" && license.current_period_end) {
    const deadline = license.current_period_end + settings(env).subscriptionGraceSeconds;
    if (status === "active" && now() > deadline) status = "expired";
  }
  if (status !== "active") {
    return fail("license_inactive", "This licence is no longer active.", 403);
  }

  await touchDevice(env.DB, device.id, metadata);
  await recordDeviceActivity(env.DB, device, "verification", clientNetwork(request), metadata);
  const authorization = await issueAuthorization(env, license, machineId);
  return json({
    valid: true,
    license_type: license.type,
    authorization: authorization.token,
    expires_at: authorization.expiresAt,
  });
}

async function activateWithKey(request: Request, env: Env): Promise<Response> {
  const data = await readJson(request);
  const activationKey = normalizeActivationKey(str(data.activation_key));
  const machineId = str(data.machine_id);
  const deviceName = bounded(data.device_name, 120);
  const metadata = deviceMetadata(data);
  if (!activationKey || !MACHINE_PATTERN.test(machineId)) {
    return fail("invalid_input", "Enter a valid activation key and computer identifier.");
  }
  if (!(await rateLimit(env.DB, `actkey:${clientKey(request)}`, ...rateLimits(env).activationKey))) {
    return fail("rate_limited", "Too many activation attempts. Try again later.", 429);
  }
  const row = await findActivationKeyByVerifier(env.DB, await hashCode(env.VERIFICATION_PEPPER, activationKey));
  if (!row || row.status !== "active") return fail("invalid_key", "That activation key is not valid.", 401);
  const existing = await findDevice(env.DB, row.id, machineId);
  if ((!existing || existing.status !== "active") && await activeDeviceCount(env.DB, row.id) >= row.max_devices) {
    return fail("device_limit", `This licence is already active on ${row.max_devices} computers.`, 409);
  }
  const device = await activateDevice(env.DB, row.id, machineId, deviceName, "key", row.generation, metadata);
  await recordDeviceActivity(env.DB, device, "activation", clientNetwork(request), metadata);
  const authorization = await issueAuthorization(env, row, machineId);
  await logEvent(env.DB, "device_activated", row.id, { device: device.id, method: "key", generation: row.generation });
  return json({ activated: true, license_type: row.type, max_devices: row.max_devices,
    authorization: authorization.token, expires_at: authorization.expiresAt });
}

async function deactivate(request: Request, env: Env): Promise<Response> {
  const data = await readJson(request);
  const grant = str(data.activation_grant);
  const machineId = str(data.machine_id);
  if (!grant || !MACHINE_PATTERN.test(machineId)) {
    return fail("invalid_input", "Missing or malformed request.");
  }

  // Deactivation frees a paid seat, so it needs the same proof of email
  // ownership that activation does.
  const row = await env.DB.prepare(
    "SELECT id, license_id, expires_at, used_at FROM activation_grants WHERE token_hash = ?",
  )
    .bind(await sha256(grant))
    .first<{ id: string; license_id: string; expires_at: number; used_at: number | null }>();
  if (!row || row.used_at !== null || row.expires_at < now()) {
    return fail("invalid_grant", "This request has expired. Start again from your email address.", 401);
  }

  await env.DB.prepare("UPDATE activation_grants SET used_at = ? WHERE id = ?").bind(now(), row.id).run();
  const removed = await deactivateDevice(env.DB, row.license_id, machineId);
  if (removed) await logEvent(env.DB, "device_deactivated", row.license_id, {});
  return json({ deactivated: removed });
}

/* ------------------------------------------------------- Customer portal */

async function authenticatedPortal(request: Request, env: Env) {
  const token = portalToken(request);
  if (!token) return null;
  const session = await findPortalSession(env.DB, await sha256(token));
  if (!session) return null;
  if (session.expires_at < now()) {
    await revokePortalSession(env.DB, session.token_hash);
    return null;
  }
  const customer = await findCustomerById(env.DB, session.customer_id);
  if (!customer) return null;
  await touchPortalSession(env.DB, session.id);
  return { token, session, customer };
}

function publicLicense(license: Awaited<ReturnType<typeof findLicenseById>>) {
  if (!license) return null;
  return {
    id: license.id,
    type: license.type,
    status: license.status,
    max_devices: license.max_devices,
    stripe_subscription_id: license.stripe_subscription_id,
    current_period_end: license.current_period_end,
    created_at: license.created_at,
    updated_at: license.updated_at,
    last_stripe_sync: license.last_stripe_sync,
  };
}

async function portalAccount(request: Request, env: Env): Promise<Response> {
  const auth = await authenticatedPortal(request, env);
  if (!auth) return fail("not_authenticated", "Sign in to view your customer account.", 401);

  const licenses = await listLicensesForCustomer(env.DB, auth.customer.id);
  const devices = await listDevicesForCustomer(env.DB, auth.customer.id);
  let invoices: Record<string, unknown>[] = [];
  if (env.STRIPE_SECRET_KEY && auth.customer.stripe_customer_id) {
    try {
      const rows = await stripeApi(env.STRIPE_SECRET_KEY).getInvoices(auth.customer.stripe_customer_id);
      invoices = rows.map((invoice) => ({
        id: invoice.id,
        status: invoice.status,
        amount_paid: invoice.amount_paid,
        currency: invoice.currency,
        created: invoice.created,
        hosted_invoice_url: invoice.hosted_invoice_url ?? null,
        invoice_pdf: invoice.invoice_pdf ?? null,
      }));
    } catch {
      // The account view remains useful if Stripe is temporarily unavailable.
    }
  }

  const deviceCounts = await Promise.all(
    licenses.map(async (license) => [license.id, await activeDeviceCount(env.DB, license.id)] as const),
  );
  const keyStates = await Promise.all(licenses.map(async (license) => {
    const key = await findActivationKeyByLicense(env.DB, license.id);
    return [license.id, key ? { exists: true, generation: key.generation, created_at: key.created_at,
      rotated_at: key.rotated_at } : { exists: false }] as const;
  }));
  const counts = new Map(deviceCounts);
  const keys = Object.fromEntries(keyStates);
  return json({
    customer: { email: auth.customer.email },
    licenses: licenses.map((license) => ({ ...publicLicense(license), active_devices: counts.get(license.id) ?? 0 })),
    devices: devices.map((device) => ({
      id: device.id,
      license_id: device.license_id,
      device_name: device.device_name,
      activated_at: device.activated_at,
      last_verified_at: device.last_verified_at,
      deactivated_at: device.deactivated_at,
      status: device.status,
      activation_method: device.activation_method,
      activation_key_generation: device.activation_key_generation,
      app_version: device.app_version,
      os_version: device.os_version,
      architecture: device.architecture,
    })),
    activation_keys: keys,
    invoices,
    additional_computers: eligibleAdditionalComputerOffers(licenses),
    billing: {
      customer_portal_available: Boolean(env.STRIPE_SECRET_KEY && auth.customer.stripe_customer_id),
    },
    session_expires_at: auth.session.expires_at,
  });
}

async function portalAdditionalComputers(request: Request, env: Env): Promise<Response> {
  const auth = await authenticatedPortal(request, env);
  if (!auth) return fail("not_authenticated", "Sign in to purchase additional computers.", 401);
  const origin = request.headers.get("Origin");
  if (origin && origin !== env.PORTAL_ORIGIN) return fail("forbidden", "This request is not allowed.", 403);
  const data = await readJson(request);
  const licenseId = str(data.license_id);
  const quantity = typeof data.quantity === "number" ? data.quantity : Number(data.quantity);
  if (!licenseId || !Number.isInteger(quantity)) return fail("invalid_input", "Choose a whole number of computers.");
  const license = await findLicenseById(env.DB, licenseId);
  if (!license || license.customer_id !== auth.customer.id) return fail("not_found", "Licence not found.", 404);
  if (license.status !== "active" || license.type !== "lifetime") return fail("not_eligible", "Additional computers are available only for an active lifetime licence.", 403);
  const remaining = LIFETIME_MAX_DEVICES - license.max_devices;
  if (remaining < 1) return fail("at_limit", "This licence already has the maximum number of computers.", 409);
  if (quantity < 1 || quantity > remaining) return fail("invalid_quantity", "That quantity is not available for this licence.", 400);
  if (!env.STRIPE_SECRET_KEY || !auth.customer.stripe_customer_id) return fail("billing_unavailable", "Billing is not available for this account yet.", 503);
  const prices = additionalComputerPrices(quantity, license.max_devices);
  const url = await stripeApi(env.STRIPE_SECRET_KEY).createAdditionalComputerCheckout({
    customerId: auth.customer.stripe_customer_id, licenseId, quantity, pricesCzk: prices,
    successUrl: new URL("/dashboard?additional_computers=success", env.PORTAL_ORIGIN).toString(),
    cancelUrl: new URL("/dashboard?additional_computers=cancelled", env.PORTAL_ORIGIN).toString(),
  });
  await logEvent(env.DB, "additional_computers_checkout_created", license.id, { quantity, amount: prices.reduce((a, b) => a + b, 0) * 100, currency: "czk" });
  return json({ url, quantity, amount: prices.reduce((a, b) => a + b, 0) * 100, currency: "czk" });
}
async function portalBilling(request: Request, env: Env): Promise<Response> {
  const auth = await authenticatedPortal(request, env);
  if (!auth) return fail("not_authenticated", "Sign in to manage billing.", 401);
  if (!env.STRIPE_SECRET_KEY || !auth.customer.stripe_customer_id) {
    return fail("billing_unavailable", "Billing management is not available for this account yet.", 503);
  }
  const url = await stripeApi(env.STRIPE_SECRET_KEY).createBillingPortalSession(
    auth.customer.stripe_customer_id,
    new URL("/dashboard", env.PORTAL_ORIGIN).toString(),
  );
  await logEvent(env.DB, "billing_portal_opened", null, { customer: auth.customer.id });
  return json({ url });
}

async function portalDeactivateDevice(request: Request, env: Env): Promise<Response> {
  const auth = await authenticatedPortal(request, env);
  if (!auth) return fail("not_authenticated", "Sign in to manage devices.", 401);
  if (!portalMutationAllowed(request, env)) return fail("forbidden", "This request is not allowed.", 403);
  const data = await readJson(request);
  const deviceId = str(data.device_id);
  if (!/^dev_[A-Za-z0-9]{16,80}$/.test(deviceId)) return fail("invalid_input", "Missing or malformed device.");
  const result = await deactivateDeviceForCustomer(env.DB, auth.customer.id, deviceId);
  if (result.removed && result.licenseId) {
    await logEvent(env.DB, "device_deactivated", result.licenseId, { source: "portal" });
  }
  return json({ deactivated: result.removed });
}

async function ownedActiveLicense(request: Request, env: Env) {
  const auth = await authenticatedPortal(request, env);
  if (!auth) return { error: fail("not_authenticated", "Sign in to manage activation keys.", 401) } as const;
  const data = await readJson(request);
  const licenseId = str(data.license_id);
  const license = await findLicenseById(env.DB, licenseId);
  if (!license || license.customer_id !== auth.customer.id) return { error: fail("not_found", "Licence not found.", 404) } as const;
  if (license.status !== "active") return { error: fail("license_inactive", "This licence is not active.", 403) } as const;
  return { auth, license } as const;
}

async function makeStoredActivationKey(env: Env, licenseId: string, generation: number) {
  const key = generateActivationKey();
  const encrypted = await encryptActivationKey(env.ACTIVATION_KEY_ENCRYPTION_KEY ?? "", key);
  return { key, row: { license_id: licenseId, generation,
    verifier_hash: await hashCode(env.VERIFICATION_PEPPER, key), ciphertext: encrypted.ciphertext, nonce: encrypted.nonce } };
}

async function portalActivationKeyEnsure(request: Request, env: Env): Promise<Response> {
  if (!portalMutationAllowed(request, env)) return fail("forbidden", "This request is not allowed.", 403);
  const owned = await ownedActiveLicense(request, env);
  if ("error" in owned && owned.error) return owned.error;
  let stored = await findActivationKeyByLicense(env.DB, owned.license.id);
  if (!stored) {
    const generated = await makeStoredActivationKey(env, owned.license.id, 1);
    try { await saveActivationKey(env.DB, generated.row); }
    catch { /* Another concurrent request may have created it. */ }
    stored = await findActivationKeyByLicense(env.DB, owned.license.id);
  }
  if (!stored) throw new Error("activation key creation failed");
  return json({ exists: true, generation: stored.generation, created_at: stored.created_at, rotated_at: stored.rotated_at });
}

async function portalActivationKeyReveal(request: Request, env: Env): Promise<Response> {
  if (!portalMutationAllowed(request, env)) return fail("forbidden", "This request is not allowed.", 403);
  const owned = await ownedActiveLicense(request, env);
  if ("error" in owned && owned.error) return owned.error;
  const stored = await findActivationKeyByLicense(env.DB, owned.license.id);
  if (!stored) return fail("not_created", "Create an activation key first.", 404);
  const key = await decryptActivationKey(env.ACTIVATION_KEY_ENCRYPTION_KEY ?? "", stored.ciphertext, stored.nonce);
  return json({ key, generation: stored.generation });
}

async function portalActivationKeyRegenerate(request: Request, env: Env): Promise<Response> {
  if (!portalMutationAllowed(request, env)) return fail("forbidden", "This request is not allowed.", 403);
  const owned = await ownedActiveLicense(request, env);
  if ("error" in owned && owned.error) return owned.error;
  const stored = await findActivationKeyByLicense(env.DB, owned.license.id);
  if (!stored) return fail("not_created", "Create an activation key first.", 404);
  const generated = await makeStoredActivationKey(env, owned.license.id, stored.generation + 1);
  const disconnected = await rotateActivationKey(env.DB, owned.license.id, generated.row.generation,
    generated.row.verifier_hash, generated.row.ciphertext, generated.row.nonce);
  await logEvent(env.DB, "activation_key_regenerated", owned.license.id, { disconnected, generation: generated.row.generation });
  return json({ key: generated.key, generation: generated.row.generation, disconnected_devices: disconnected });
}

async function portalDeviceDetails(request: Request, env: Env): Promise<Response> {
  const auth = await authenticatedPortal(request, env);
  if (!auth) return fail("not_authenticated", "Sign in to view device details.", 401);
  const deviceId = new URL(request.url).searchParams.get("device_id") ?? "";
  if (!/^dev_[A-Za-z0-9]{16,80}$/.test(deviceId)) return fail("invalid_input", "Missing or malformed device.");
  const details = await deviceDetailsForCustomer(env.DB, auth.customer.id, deviceId);
  return details ? json(details) : fail("not_found", "Device not found.", 404);
}

async function portalDeleteDevice(request: Request, env: Env): Promise<Response> {
  const auth = await authenticatedPortal(request, env);
  if (!auth) return fail("not_authenticated", "Sign in to manage devices.", 401);
  if (!portalMutationAllowed(request, env)) return fail("forbidden", "This request is not allowed.", 403);
  const data = await readJson(request);
  const deviceId = str(data.device_id);
  if (!/^dev_[A-Za-z0-9]{16,80}$/.test(deviceId)) return fail("invalid_input", "Missing or malformed device.");
  const result = await deleteDeactivatedDeviceForCustomer(env.DB, auth.customer.id, deviceId);
  if (!result.deleted) return fail("not_deactivated", "Only a deactivated computer can be deleted.", 409);
  await logEvent(env.DB, "device_history_deleted", result.licenseId, { source: "portal" });
  return json({ deleted: true });
}

async function portalLogout(request: Request, env: Env): Promise<Response> {
  const token = portalToken(request);
  if (token) await revokePortalSession(env.DB, await sha256(token));
  return json(
    { logged_out: true },
    200,
    { "Set-Cookie": portalCookie("", 0) },
  );
}

/* ------------------------------------------------------------------ Router */

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    try {
      if (url.hostname === "account.tomaspisar.cz") {
        const page = await portalPage(request, env, url.pathname);
        if (page) return page;
        return env.ASSETS.fetch(request);
      }
      if (request.method === "OPTIONS" && path === "/api/contact") {
        if (request.headers.get("Origin") && request.headers.get("Origin") !== CONTACT_ORIGIN) {
          return new Response(null, { status: 403 });
        }
        return withContactCors(new Response(null, { status: 204 }), request);
      }
      if (request.method === "OPTIONS" && path.startsWith("/api/portal/")) {
        return withPortalCors(new Response(null, { status: 204 }), request, env);
      }
      if (path === "/health" && request.method === "GET") {
        return json({ ok: true, service: "longjumpreplay-licensing", product: PRODUCT_ID });
      }
      if (path === "/api/portal/account" && request.method === "GET") {
        return withPortalCors(await portalAccount(request, env), request, env);
      }
      if (path === "/api/portal/device-details" && request.method === "GET") {
        return withPortalCors(await portalDeviceDetails(request, env), request, env);
      }
      if (path === "/api/contact" && request.method === "POST") {
        return withContactCors(await contact(request, env), request);
      }
      if (request.method !== "POST") return fail("not_found", "Not found", 404);

      let response: Response;
      switch (path) {
        case "/api/stripe/webhook":
          response = await handleWebhook(request, env);
          break;
        case "/api/license/request-code":
          response = await requestCode(request, env);
          break;
        case "/api/license/verify-code":
          response = await verifyCode(request, env);
          break;
        case "/api/license/activate":
          response = await activate(request, env);
          break;
        case "/api/license/activate-key":
          response = await activateWithKey(request, env);
          break;
        case "/api/license/verify":
          response = await verify(request, env);
          break;
        case "/api/license/deactivate-device":
          response = await deactivate(request, env);
          break;
        case "/api/portal/request-code":
          response = await requestCode(request, env, "portal");
          break;
        case "/api/portal/verify-code":
          response = await verifyCode(request, env, "portal");
          break;
        case "/api/portal/logout":
          response = await portalLogout(request, env);
          break;
        case "/api/portal/billing":
          response = await portalBilling(request, env);
          break;
        case "/api/portal/additional-computers":
          response = await portalAdditionalComputers(request, env);
          break;
        case "/api/portal/deactivate-device":
          response = await portalDeactivateDevice(request, env);
          break;
        case "/api/portal/delete-device":
          response = await portalDeleteDevice(request, env);
          break;
        case "/api/portal/activation-key/ensure":
          response = await portalActivationKeyEnsure(request, env);
          break;
        case "/api/portal/activation-key/reveal":
          response = await portalActivationKeyReveal(request, env);
          break;
        case "/api/portal/activation-key/regenerate":
          response = await portalActivationKeyRegenerate(request, env);
          break;
        default:
          response = fail("not_found", "Not found", 404);
      }
      return path.startsWith("/api/portal/") ? withPortalCors(response, request, env) : response;
    } catch (error) {
      // Never surface internals. The message is logged, not returned.
      console.error("unhandled", error instanceof Error ? error.message : "unknown");
      const response = fail("server_error", "Something went wrong. Please try again.", 500);
      return path === "/api/contact" ? withContactCors(response, request)
        : path.startsWith("/api/portal/") ? withPortalCors(response, request, env) : response;
    }
  },
  async scheduled(_controller: ScheduledController, env: Env): Promise<void> {
    const removed = await purgeOldDeviceActivity(env.DB, now() - 365 * 86400);
    if (removed) console.log("purged device activity", removed);
  },
} satisfies ExportedHandler<Env>;
