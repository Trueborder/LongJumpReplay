/**
 * All D1 access. Every query is parameterised - no string interpolation of
 * user-supplied values anywhere in this file.
 */

import { randomId } from "./crypto";
import type { LicenseStatus, LicenseType } from "./config";

export interface CustomerRow {
  id: string;
  email: string;
  stripe_customer_id: string | null;
}

export interface LicenseRow {
  id: string;
  customer_id: string;
  product: string;
  type: LicenseType;
  status: LicenseStatus;
  max_devices: number;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  stripe_price_id: string | null;
  current_period_end: number | null;
}

export interface DeviceRow {
  id: string;
  license_id: string;
  machine_id: string;
  device_name: string | null;
  activated_at: number;
  last_verified_at: number | null;
  status: "active" | "deactivated";
}

export function now(): number {
  return Math.floor(Date.now() / 1000);
}

export function normaliseEmail(value: string): string {
  return value.trim().toLowerCase();
}

export async function logEvent(
  db: D1Database,
  type: string,
  licenseId: string | null,
  detail?: Record<string, unknown>,
): Promise<void> {
  // Detail is for operators. Never pass verification codes, tokens or secrets.
  await db
    .prepare("INSERT INTO events (id, license_id, type, detail, created_at) VALUES (?, ?, ?, ?, ?)")
    .bind(randomId("evt"), licenseId, type, detail ? JSON.stringify(detail) : null, now())
    .run();
}

export async function findCustomerByEmail(db: D1Database, email: string): Promise<CustomerRow | null> {
  return db
    .prepare("SELECT id, email, stripe_customer_id FROM customers WHERE email = ?")
    .bind(normaliseEmail(email))
    .first<CustomerRow>();
}

export async function upsertCustomer(
  db: D1Database,
  email: string,
  stripeCustomerId: string | null,
): Promise<CustomerRow> {
  const normalised = normaliseEmail(email);
  const existing = await findCustomerByEmail(db, normalised);
  if (existing) {
    if (stripeCustomerId && existing.stripe_customer_id !== stripeCustomerId) {
      await db
        .prepare("UPDATE customers SET stripe_customer_id = ?, updated_at = ? WHERE id = ?")
        .bind(stripeCustomerId, now(), existing.id)
        .run();
      return { ...existing, stripe_customer_id: stripeCustomerId };
    }
    return existing;
  }
  const id = randomId("cus");
  const timestamp = now();
  await db
    .prepare(
      "INSERT INTO customers (id, email, stripe_customer_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
    )
    .bind(id, normalised, stripeCustomerId, timestamp, timestamp)
    .run();
  return { id, email: normalised, stripe_customer_id: stripeCustomerId };
}

/**
 * The licence a customer activates with. A customer could in principle own
 * several; the most recently created active one wins, which matches the
 * common case of someone upgrading from subscription to lifetime.
 */
export async function findActivatableLicense(db: D1Database, email: string): Promise<LicenseRow | null> {
  return db
    .prepare(
      `SELECT l.* FROM licenses l
         JOIN customers c ON c.id = l.customer_id
        WHERE c.email = ? AND l.status = 'active'
        ORDER BY CASE l.type WHEN 'lifetime' THEN 0 ELSE 1 END, l.created_at DESC
        LIMIT 1`,
    )
    .bind(normaliseEmail(email))
    .first<LicenseRow>();
}

export async function findLicenseById(db: D1Database, id: string): Promise<LicenseRow | null> {
  return db.prepare("SELECT * FROM licenses WHERE id = ?").bind(id).first<LicenseRow>();
}

export async function findLicenseBySubscription(
  db: D1Database,
  subscriptionId: string,
): Promise<LicenseRow | null> {
  return db
    .prepare("SELECT * FROM licenses WHERE stripe_subscription_id = ?")
    .bind(subscriptionId)
    .first<LicenseRow>();
}

export async function createLicense(
  db: D1Database,
  fields: {
    customerId: string;
    type: LicenseType;
    maxDevices: number;
    stripeCustomerId: string | null;
    stripeSubscriptionId: string | null;
    stripePriceId: string | null;
    currentPeriodEnd: number | null;
  },
): Promise<LicenseRow> {
  const id = randomId("lic");
  const timestamp = now();
  await db
    .prepare(
      `INSERT INTO licenses
         (id, customer_id, product, type, status, max_devices, stripe_customer_id,
          stripe_subscription_id, stripe_price_id, current_period_end,
          created_at, updated_at, last_stripe_sync)
       VALUES (?, ?, 'LongJumpReplay', ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      id,
      fields.customerId,
      fields.type,
      fields.maxDevices,
      fields.stripeCustomerId,
      fields.stripeSubscriptionId,
      fields.stripePriceId,
      fields.currentPeriodEnd,
      timestamp,
      timestamp,
      timestamp,
    )
    .run();
  return (await findLicenseById(db, id))!;
}

export async function setLicenseStatus(
  db: D1Database,
  licenseId: string,
  status: LicenseStatus,
  currentPeriodEnd?: number | null,
): Promise<void> {
  const timestamp = now();
  if (currentPeriodEnd === undefined) {
    await db
      .prepare("UPDATE licenses SET status = ?, updated_at = ?, last_stripe_sync = ? WHERE id = ?")
      .bind(status, timestamp, timestamp, licenseId)
      .run();
    return;
  }
  await db
    .prepare(
      "UPDATE licenses SET status = ?, current_period_end = ?, updated_at = ?, last_stripe_sync = ? WHERE id = ?",
    )
    .bind(status, currentPeriodEnd, timestamp, timestamp, licenseId)
    .run();
}

export async function activeDeviceCount(db: D1Database, licenseId: string): Promise<number> {
  const row = await db
    .prepare("SELECT COUNT(*) AS n FROM devices WHERE license_id = ? AND status = 'active'")
    .bind(licenseId)
    .first<{ n: number }>();
  return row?.n ?? 0;
}

export async function findDevice(
  db: D1Database,
  licenseId: string,
  machineId: string,
): Promise<DeviceRow | null> {
  return db
    .prepare("SELECT * FROM devices WHERE license_id = ? AND machine_id = ?")
    .bind(licenseId, machineId)
    .first<DeviceRow>();
}

/** Re-activating a known machine refreshes it instead of consuming a seat. */
export async function activateDevice(
  db: D1Database,
  licenseId: string,
  machineId: string,
  deviceName: string | null,
): Promise<DeviceRow> {
  const existing = await findDevice(db, licenseId, machineId);
  const timestamp = now();
  if (existing) {
    await db
      .prepare(
        "UPDATE devices SET status = 'active', deactivated_at = NULL, last_verified_at = ?, device_name = COALESCE(?, device_name) WHERE id = ?",
      )
      .bind(timestamp, deviceName, existing.id)
      .run();
    return { ...existing, status: "active", last_verified_at: timestamp };
  }
  const id = randomId("dev");
  await db
    .prepare(
      `INSERT INTO devices (id, license_id, machine_id, device_name, activated_at, last_verified_at, status)
       VALUES (?, ?, ?, ?, ?, ?, 'active')`,
    )
    .bind(id, licenseId, machineId, deviceName, timestamp, timestamp)
    .run();
  return {
    id,
    license_id: licenseId,
    machine_id: machineId,
    device_name: deviceName,
    activated_at: timestamp,
    last_verified_at: timestamp,
    status: "active",
  };
}

export async function deactivateDevice(db: D1Database, licenseId: string, machineId: string): Promise<boolean> {
  const result = await db
    .prepare(
      "UPDATE devices SET status = 'deactivated', deactivated_at = ? WHERE license_id = ? AND machine_id = ? AND status = 'active'",
    )
    .bind(now(), licenseId, machineId)
    .run();
  return (result.meta.changes ?? 0) > 0;
}

export async function touchDevice(db: D1Database, deviceId: string): Promise<void> {
  await db.prepare("UPDATE devices SET last_verified_at = ? WHERE id = ?").bind(now(), deviceId).run();
}

/** Returns false when the event was already handled - the idempotency guard. */
export async function claimStripeEvent(db: D1Database, id: string, type: string): Promise<boolean> {
  try {
    await db
      .prepare("INSERT INTO stripe_events (id, type, processed_at) VALUES (?, ?, ?)")
      .bind(id, type, now())
      .run();
    return true;
  } catch {
    // Primary key collision: a redelivery of an event already processed.
    return false;
  }
}

/**
 * Fixed-window counter in D1. Good enough for the volumes here, and avoids a
 * second binding just for rate limiting.
 */
export async function rateLimit(
  db: D1Database,
  bucket: string,
  max: number,
  windowSeconds: number,
): Promise<boolean> {
  const current = now();
  const row = await db
    .prepare("SELECT count, window_start FROM rate_limits WHERE bucket = ?")
    .bind(bucket)
    .first<{ count: number; window_start: number }>();

  if (!row || current - row.window_start >= windowSeconds) {
    await db
      .prepare(
        `INSERT INTO rate_limits (bucket, count, window_start) VALUES (?, 1, ?)
         ON CONFLICT (bucket) DO UPDATE SET count = 1, window_start = excluded.window_start`,
      )
      .bind(bucket, current)
      .run();
    return true;
  }
  if (row.count >= max) return false;
  await db.prepare("UPDATE rate_limits SET count = count + 1 WHERE bucket = ?").bind(bucket).run();
  return true;
}
