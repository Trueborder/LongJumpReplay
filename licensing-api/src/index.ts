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
import type { Env, LicenseType } from "./config";
import {
  generateToken,
  generateVerificationCode,
  hashCode,
  randomId,
  sha256,
  signAuthorization,
  timingSafeEqual,
} from "./crypto";
import {
  activateDevice,
  activeDeviceCount,
  claimStripeEvent,
  createLicense,
  deactivateDevice,
  findActivatableLicense,
  findDevice,
  findLicenseById,
  findLicenseBySubscription,
  logEvent,
  normaliseEmail,
  now,
  rateLimit,
  setLicenseStatus,
  touchDevice,
  upsertCustomer,
} from "./db";
import { sendVerificationCode } from "./email";
import {
  ACTIVE_SUBSCRIPTION_STATUSES,
  DEAD_SUBSCRIPTION_STATUSES,
  SignatureError,
  stripeApi,
  verifySignature,
} from "./stripe";
import type { StripeEvent } from "./stripe";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MACHINE_PATTERN = /^[A-Za-z0-9_-]{16,128}$/;
const MAX_BODY_BYTES = 16_384;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
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

/* ------------------------------------------------------------------ Stripe */

function priceIdFromSession(session: Record<string, any>): string | null {
  const item = session?.line_items?.data?.[0];
  return item?.price?.id ?? null;
}

async function handleCheckoutCompleted(env: Env, event: StripeEvent): Promise<void> {
  const session = event.data.object;
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

async function requestCode(request: Request, env: Env): Promise<Response> {
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

  const license = await findActivatableLicense(env.DB, email);

  // Always the same response, whether or not a licence exists. Otherwise this
  // endpoint becomes an oracle for which addresses have bought the software.
  const generic = json({
    sent: true,
    expires_in_minutes: Math.floor(cfg.verificationCodeTtlSeconds / 60),
  });
  if (!license) {
    await logEvent(env.DB, "verification_requested", null, { result: "no license" });
    return generic;
  }

  // A new code invalidates any earlier unused one.
  await env.DB.prepare(
    "UPDATE verification_codes SET used_at = ? WHERE license_id = ? AND used_at IS NULL",
  )
    .bind(now(), license.id)
    .run();

  const code = generateVerificationCode();
  const timestamp = now();
  await env.DB.prepare(
    `INSERT INTO verification_codes (id, license_id, email, code_hash, created_at, expires_at, attempt_count)
     VALUES (?, ?, ?, ?, ?, ?, 0)`,
  )
    .bind(
      randomId("vc"),
      license.id,
      email,
      await hashCode(env.VERIFICATION_PEPPER, code),
      timestamp,
      timestamp + cfg.verificationCodeTtlSeconds,
    )
    .run();

  try {
    await sendVerificationCode(env, email, code, Math.floor(cfg.verificationCodeTtlSeconds / 60));
    await logEvent(env.DB, "verification_requested", license.id, { result: "sent" });
  } catch {
    await logEvent(env.DB, "verification_requested", license.id, { result: "send failed" });
    return fail("email_failed", "Could not send the verification email. Please try again shortly.", 502);
  }
  return generic;
}

async function verifyCode(request: Request, env: Env): Promise<Response> {
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

  const row = await env.DB.prepare(
    `SELECT * FROM verification_codes
      WHERE email = ? AND used_at IS NULL
      ORDER BY created_at DESC LIMIT 1`,
  )
    .bind(email)
    .first<{
      id: string;
      license_id: string;
      code_hash: string;
      expires_at: number;
      attempt_count: number;
    }>();

  if (!row) return fail("invalid_code", "That code is not valid. Request a new one.");
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
  const device = await activateDevice(env.DB, license.id, machineId, deviceName);
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
    return json({ valid: false, status, message: "This licence is no longer active." }, 403);
  }

  await touchDevice(env.DB, device.id);
  const authorization = await issueAuthorization(env, license, machineId);
  return json({
    valid: true,
    license_type: license.type,
    authorization: authorization.token,
    expires_at: authorization.expiresAt,
  });
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

/* ------------------------------------------------------------------ Router */

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    try {
      if (path === "/health" && request.method === "GET") {
        return json({ ok: true, service: "longjumpreplay-licensing", product: PRODUCT_ID });
      }
      if (request.method !== "POST") return fail("not_found", "Not found", 404);

      switch (path) {
        case "/api/stripe/webhook":
          return await handleWebhook(request, env);
        case "/api/license/request-code":
          return await requestCode(request, env);
        case "/api/license/verify-code":
          return await verifyCode(request, env);
        case "/api/license/activate":
          return await activate(request, env);
        case "/api/license/verify":
          return await verify(request, env);
        case "/api/license/deactivate-device":
          return await deactivate(request, env);
        default:
          return fail("not_found", "Not found", 404);
      }
    } catch (error) {
      // Never surface internals. The message is logged, not returned.
      console.error("unhandled", error instanceof Error ? error.message : "unknown");
      return fail("server_error", "Something went wrong. Please try again.", 500);
    }
  },
} satisfies ExportedHandler<Env>;
