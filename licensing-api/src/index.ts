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
  createPortalSession,
  createLicense,
  deactivateDevice,
  deactivateDeviceForCustomer,
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
  setLicenseStatus,
  touchDevice,
  touchPortalSession,
  upsertCustomer,
  revokePortalSession,
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
import { portalPageRoute } from "./portal-routing";

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const MACHINE_PATTERN = /^[A-Za-z0-9_-]{16,128}$/;
const MAX_BODY_BYTES = 16_384;
const PORTAL_SESSION_COOKIE = "ljr-portal-session";

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
  if (!["/", "/login", "/login/", "/dashboard", "/dashboard/"].includes(path)) return null;

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

type VerificationPurpose = "activation" | "portal";

async function requestCode(request: Request, env: Env, purpose: VerificationPurpose = "activation"): Promise<Response> {
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
    const customer = await upsertCustomer(env.DB, email, null);
    await env.DB.prepare(
      "UPDATE portal_login_codes SET used_at = ? WHERE customer_id = ? AND used_at IS NULL",
    )
      .bind(now(), customer.id)
      .run();

    const code = generateVerificationCode();
    const timestamp = now();
    await env.DB.prepare(
      `INSERT INTO portal_login_codes
         (id, customer_id, email, code_hash, created_at, expires_at, attempt_count)
       VALUES (?, ?, ?, ?, ?, ?, 0)`,
    )
      .bind(
        randomId("pc"),
        customer.id,
        email,
        await hashCode(env.VERIFICATION_PEPPER, code),
        timestamp,
        timestamp + cfg.verificationCodeTtlSeconds,
      )
      .run();

    try {
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
    await logEvent(env.DB, "verification_requested", null, { result: "no license" });
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

async function verifyCode(request: Request, env: Env, purpose: VerificationPurpose = "activation"): Promise<Response> {
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
        WHERE email = ? AND used_at IS NULL
        ORDER BY created_at DESC LIMIT 1`,
    )
      .bind(email)
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
    return fail("license_inactive", "This licence is no longer active.", 403);
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
  const counts = new Map(deviceCounts);
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
    })),
    invoices,
    billing: {
      customer_portal_available: Boolean(env.STRIPE_SECRET_KEY && auth.customer.stripe_customer_id),
    },
    session_expires_at: auth.session.expires_at,
  });
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
  const data = await readJson(request);
  const deviceId = str(data.device_id);
  if (!/^dev_[A-Za-z0-9]{16,80}$/.test(deviceId)) return fail("invalid_input", "Missing or malformed device.");
  const result = await deactivateDeviceForCustomer(env.DB, auth.customer.id, deviceId);
  if (result.removed && result.licenseId) {
    await logEvent(env.DB, "device_deactivated", result.licenseId, { source: "portal" });
  }
  return json({ deactivated: result.removed });
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
      if (request.method === "OPTIONS" && path.startsWith("/api/portal/")) {
        return withPortalCors(new Response(null, { status: 204 }), request, env);
      }
      if (path === "/health" && request.method === "GET") {
        return json({ ok: true, service: "longjumpreplay-licensing", product: PRODUCT_ID });
      }
      if (path === "/api/portal/account" && request.method === "GET") {
        return withPortalCors(await portalAccount(request, env), request, env);
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
        case "/api/portal/deactivate-device":
          response = await portalDeactivateDevice(request, env);
          break;
        default:
          response = fail("not_found", "Not found", 404);
      }
      return path.startsWith("/api/portal/") ? withPortalCors(response, request, env) : response;
    } catch (error) {
      // Never surface internals. The message is logged, not returned.
      console.error("unhandled", error instanceof Error ? error.message : "unknown");
      const response = fail("server_error", "Something went wrong. Please try again.", 500);
      return path.startsWith("/api/portal/") ? withPortalCors(response, request, env) : response;
    }
  },
} satisfies ExportedHandler<Env>;
